import base64
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

COMMON_DIR = Path(__file__).resolve().parents[1] / "forgescaffold_common"
import sys
sys.path.append(str(COMMON_DIR))

from index_utils import canonical_json, index_file_sha256, load_index, policy_snapshot_hash  # noqa: E402


def _load_policy(project_root: Path) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    policy_path = repo_root / "dawn" / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        policy_path = project_root / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        return {}
    return yaml.safe_load(policy_path.read_text()) or {}


def _load_trusted_signers(project_root: Path) -> List[Dict[str, Any]]:
    repo_root = Path(__file__).resolve().parents[3]
    policy_path = repo_root / "dawn" / "policy" / "trusted_signers.yaml"
    if not policy_path.exists():
        policy_path = project_root / "policy" / "trusted_signers.yaml"
    if not policy_path.exists():
        return []
    payload = yaml.safe_load(policy_path.read_text()) or {}
    return payload.get("trusted_signers", []) or []


def _resolve_checkpoint_dir(project_root: Path, index_policy: Dict[str, Any]) -> Path:
    root_value = index_policy.get("checkpoint_write_root", "evidence/checkpoints")
    path = Path(root_value)
    if path.is_absolute():
        return path
    repo_root = Path(__file__).resolve().parents[3]
    if str(root_value).startswith("projects/"):
        return repo_root / path
    return project_root / path


def _latest_summary(compaction_dir: Path) -> Optional[Path]:
    if not compaction_dir.exists():
        return None
    files = [p for p in compaction_dir.glob("summary_*.json") if not p.name.endswith(".signature.json")]
    return sorted(files)[-1] if files else None


def _latest_checkpoint(checkpoints_dir: Path) -> Optional[Path]:
    if not checkpoints_dir.exists():
        return None
    files = [p for p in checkpoints_dir.glob("checkpoint_*.json") if not p.name.endswith(".signature.json")]
    return sorted(files)[-1] if files else None


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _scope_allows(entry: Dict[str, Any], project_id: str, pipeline_id: str) -> bool:
    scopes = entry.get("scopes")
    if not scopes:
        return True
    projects = scopes.get("projects", ["*"])
    pipelines = scopes.get("pipelines", ["*"])
    return ("*" in projects or project_id in projects) and ("*" in pipelines or pipeline_id in pipelines)


def _verify_summary_signature(
    summary_path: Path,
    signature_path: Path,
    policy: Dict[str, Any],
    trusted_signers: List[Dict[str, Any]],
    project_id: str,
    pipeline_id: str,
) -> Tuple[bool, List[str]]:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for summary verification") from exc

    summary = json.loads(summary_path.read_text())
    signature = json.loads(signature_path.read_text())
    summary_bytes = canonical_json(summary).encode("utf-8")

    signatures = signature.get("signatures") or []
    errors = []
    valid_count = 0

    for entry in signatures:
        sig_bytes = base64.b64decode(entry.get("sig", ""))
        public_bytes = base64.b64decode(entry.get("public_key", ""))
        fingerprint = entry.get("fingerprint") or _sha256_bytes(public_bytes)
        try:
            Ed25519PublicKey.from_public_bytes(public_bytes).verify(sig_bytes, summary_bytes)
            signature_valid = True
        except Exception:
            signature_valid = False
            errors.append("SUMMARY_SIGNATURE_INVALID")

        signer_entry = None
        for signer in trusted_signers:
            if signer.get("fingerprint") == fingerprint:
                signer_entry = signer
                break

        if signer_entry:
            if signer_entry.get("revoked"):
                errors.append("SUMMARY_SIGNATURE_INVALID")
        else:
            errors.append("SUMMARY_SIGNATURE_INVALID")

        if signer_entry and signer_entry.get("expires_at"):
            try:
                expires_at = _parse_datetime(str(signer_entry.get("expires_at")))
                if expires_at < datetime.now(timezone.utc):
                    errors.append("SUMMARY_SIGNATURE_INVALID")
            except Exception:
                errors.append("SUMMARY_SIGNATURE_INVALID")

        if signer_entry and signer_entry.get("scopes"):
            if not _scope_allows(signer_entry, project_id, pipeline_id):
                errors.append("SUMMARY_SIGNATURE_INVALID")

        if signature_valid and signer_entry and not signer_entry.get("revoked"):
            valid_count += 1

    required = policy.get("forgescaffold", {}).get("min_signatures_by_risk", {}).get("medium", 1)
    if valid_count < required:
        errors.append("SUMMARY_SIGNATURE_INVALID")

    if signature.get("manifest_sha256") != _sha256_bytes(summary_bytes):
        errors.append("SUMMARY_SIGNATURE_INVALID")

    return len(errors) == 0, errors


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not sandbox:
        raise RuntimeError("Sandbox missing")

    report = {
        "status": "PASS",
        "error_codes": [],
    }

    index_path = project_root / "evidence" / "evidence_index.jsonl"
    cache_path = project_root / "evidence" / "cache" / "evidence_index_cache.sqlite"

    entries = load_index(index_path)
    index_sha = index_file_sha256(index_path)
    entry_count = len(entries)
    last_hash = entries[-1].get("entry_hash") if entries else None

    if not cache_path.exists():
        report["status"] = "FAIL"
        report["error_codes"].append("CACHE_META_MISMATCH")
    else:
        conn = sqlite3.connect(str(cache_path))
        try:
            cur = conn.execute(
                "SELECT schema_version, built_at, source_index_sha256, source_entry_count, source_last_entry_hash, checkpoint_last_entry_hash, "
                "checkpoint_path, checkpoint_timestamp, policy_snapshot_hash FROM cache_meta LIMIT 1"
            )
            row = cur.fetchone()
            if not row:
                report["status"] = "FAIL"
                report["error_codes"].append("CACHE_META_MISMATCH")
            else:
                meta = {
                    "schema_version": row[0],
                    "built_at": row[1],
                    "source_index_sha256": row[2],
                    "source_entry_count": row[3],
                    "source_last_entry_hash": row[4],
                    "checkpoint_last_entry_hash": row[5],
                    "checkpoint_path": row[6],
                    "checkpoint_timestamp": row[7],
                    "policy_snapshot_hash": row[8],
                }
                policy = _load_policy(project_root)
                policy_hash = policy_snapshot_hash(policy)
                checkpoint_last = None
                checkpoint_path = None
                checkpoint_timestamp = None
                index_policy = policy.get("forgescaffold", {}).get("index_integrity", {})
                if index_policy.get("checkpoint_enabled", False):
                    checkpoints_dir = _resolve_checkpoint_dir(project_root, index_policy)
                    latest_checkpoint = _latest_checkpoint(checkpoints_dir)
                    if latest_checkpoint:
                        checkpoint_payload = json.loads(latest_checkpoint.read_text())
                        checkpoint_last = checkpoint_payload.get("last_entry_hash")
                        checkpoint_path = str(latest_checkpoint)
                        checkpoint_timestamp = checkpoint_payload.get("created_at")
                if (
                    meta.get("source_index_sha256") != index_sha
                    or int(meta.get("source_entry_count") or 0) != entry_count
                    or meta.get("source_last_entry_hash") != last_hash
                    or meta.get("policy_snapshot_hash") != policy_hash
                    or (index_policy.get("checkpoint_enabled", False) and meta.get("checkpoint_last_entry_hash") != checkpoint_last)
                    or (index_policy.get("checkpoint_enabled", False) and meta.get("checkpoint_path") != checkpoint_path)
                    or (index_policy.get("checkpoint_enabled", False) and meta.get("checkpoint_timestamp") != checkpoint_timestamp)
                ):
                    report["status"] = "FAIL"
                    report["error_codes"].append("CACHE_META_MISMATCH")

                def _row_for(line_no: int) -> Optional[Dict[str, Any]]:
                    cur2 = conn.execute(
                        "SELECT line_no, timestamp, patchset_id, approval_id, risk_level, pipeline_name, verification_mode, status, review_packet_sha256, bundle_content_sha256, entry_hash, prev_entry_hash, signer_fingerprints_json, signature_count_required, signature_count_valid, approvers_json, ticket_id, ticket_id_status, ticket_event_id "
                        "FROM evidence_runs WHERE line_no=?",
                        (line_no,),
                    )
                    row2 = cur2.fetchone()
                    if not row2:
                        return None
                    return {
                        "line_no": row2[0],
                        "timestamp": row2[1],
                        "patchset_id": row2[2],
                        "approval_id": row2[3],
                        "risk_level": row2[4],
                        "pipeline_name": row2[5],
                        "verification_mode": row2[6],
                        "status": row2[7],
                        "review_packet_sha256": row2[8],
                        "bundle_content_sha256": row2[9],
                        "entry_hash": row2[10],
                        "prev_entry_hash": row2[11],
                        "signer_fingerprints_json": row2[12],
                        "signature_count_required": row2[13],
                        "signature_count_valid": row2[14],
                        "approvers_json": row2[15],
                        "ticket_id": row2[16],
                        "ticket_id_status": row2[17],
                        "ticket_event_id": row2[18],
                    }

                sample_lines = []
                if entry_count >= 1:
                    sample_lines.append(1)
                if entry_count >= 2:
                    sample_lines.append((entry_count // 2) + 1)
                if entry_count >= 3:
                    sample_lines.append(entry_count)

                for line_no in dict.fromkeys(sample_lines):
                    entry = entries[line_no - 1]
                    row2 = _row_for(line_no)
                    if not row2:
                        report["status"] = "FAIL"
                        report["error_codes"].append("CACHE_ROW_MISMATCH")
                        continue
                    expected_signers = json.dumps(entry.get("signer_fingerprints", []) or [], sort_keys=True, separators=(",", ":"))
                    expected_approvers = json.dumps(entry.get("approvers", []) or [], sort_keys=True, separators=(",", ":"))
                    comparisons = {
                        "timestamp": entry.get("timestamp"),
                        "patchset_id": entry.get("patchset_id"),
                        "approval_id": entry.get("approval_id"),
                        "risk_level": entry.get("risk_level"),
                        "pipeline_name": entry.get("pipeline_name"),
                        "verification_mode": entry.get("verification_mode"),
                        "status": entry.get("status"),
                        "review_packet_sha256": entry.get("review_packet_sha256"),
                        "bundle_content_sha256": entry.get("bundle_content_sha256"),
                        "entry_hash": entry.get("entry_hash"),
                        "prev_entry_hash": entry.get("prev_entry_hash"),
                        "signature_count_required": entry.get("signature_count_required"),
                        "signature_count_valid": entry.get("signature_count_valid"),
                        "ticket_id": entry.get("ticket_id") or entry.get("ticket"),
                        "ticket_id_status": entry.get("ticket_id_status"),
                        "ticket_event_id": entry.get("ticket_event_id"),
                    }
                    for key, expected in comparisons.items():
                        if row2.get(key) != expected:
                            report["status"] = "FAIL"
                            report["error_codes"].append("CACHE_ROW_MISMATCH")
                            break
                    if row2.get("signer_fingerprints_json") != expected_signers or row2.get("approvers_json") != expected_approvers:
                        report["status"] = "FAIL"
                        report["error_codes"].append("CACHE_ROW_MISMATCH")
        finally:
            conn.close()

    policy = _load_policy(project_root)
    compaction_dir = project_root / "evidence" / "compaction"
    summary_path = _latest_summary(compaction_dir)
    if summary_path:
        signature_path = summary_path.with_suffix(".signature.json")
        if not signature_path.exists():
            report["status"] = "FAIL"
            report["error_codes"].append("SUMMARY_SIGNATURE_INVALID")
        else:
            summary = json.loads(summary_path.read_text())
            cache_meta = {
                "schema_version": None,
                "built_at": None,
                "source_index_sha256": index_sha,
                "source_entry_count": entry_count,
                "source_last_entry_hash": last_hash,
                "checkpoint_last_entry_hash": None,
                "policy_snapshot_hash": policy_snapshot_hash(policy),
            }
            if cache_path.exists():
                conn = sqlite3.connect(str(cache_path))
                try:
                    cur = conn.execute(
                        "SELECT schema_version, built_at, source_index_sha256, source_entry_count, source_last_entry_hash, checkpoint_last_entry_hash, policy_snapshot_hash "
                        "FROM cache_meta LIMIT 1"
                    )
                    row = cur.fetchone()
                    if row:
                        cache_meta = {
                            "schema_version": row[0],
                            "built_at": row[1],
                            "source_index_sha256": row[2],
                            "source_entry_count": row[3],
                            "source_last_entry_hash": row[4],
                            "checkpoint_last_entry_hash": row[5],
                            "policy_snapshot_hash": row[6],
                        }
                finally:
                    conn.close()

            cache_meta_sha = _sha256_bytes(canonical_json(cache_meta).encode("utf-8"))
            if summary.get("cache_meta_sha256") != cache_meta_sha:
                report["status"] = "FAIL"
                report["error_codes"].append("SUMMARY_HASH_MISMATCH")
            if summary.get("source_index_sha256") != cache_meta.get("source_index_sha256"):
                report["status"] = "FAIL"
                report["error_codes"].append("SUMMARY_HASH_MISMATCH")
            if summary.get("source_last_entry_hash") != cache_meta.get("source_last_entry_hash"):
                report["status"] = "FAIL"
                report["error_codes"].append("SUMMARY_HASH_MISMATCH")
            if summary.get("source_entry_count") != cache_meta.get("source_entry_count"):
                report["status"] = "FAIL"
                report["error_codes"].append("SUMMARY_HASH_MISMATCH")
            if summary.get("policy_snapshot_hash") != cache_meta.get("policy_snapshot_hash"):
                report["status"] = "FAIL"
                report["error_codes"].append("SUMMARY_HASH_MISMATCH")

            trusted = _load_trusted_signers(project_root)
            ok_sig, errors = _verify_summary_signature(
                summary_path,
                signature_path,
                policy,
                trusted,
                project_context.get("project_id", ""),
                project_context.get("pipeline_id", ""),
            )
            if not ok_sig:
                report["status"] = "FAIL"
                report["error_codes"].extend(errors)

    report_path = sandbox.publish(
        "forgescaffold.cache_integrity_report.json",
        "cache_integrity_report.json",
        report,
        schema="json",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {"forgescaffold.cache_integrity_report.json": {"path": report_path}},
        "metrics": {"errors": len(report.get("error_codes", []))},
    }
