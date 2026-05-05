import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

COMMON_DIR = Path(__file__).resolve().parents[1] / "forgescaffold_common"
import sys
sys.path.append(str(COMMON_DIR))

from index_utils import canonical_json, compute_entry_hash, load_index, policy_snapshot_hash, verify_index_chain  # noqa: E402


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


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _resolve_checkpoint_dir(project_root: Path, index_policy: Dict[str, Any]) -> Path:
    root_value = index_policy.get("checkpoint_write_root", "evidence/checkpoints")
    path = Path(root_value)
    if path.is_absolute():
        return path
    repo_root = Path(__file__).resolve().parents[3]
    if str(root_value).startswith("projects/"):
        return repo_root / path
    return project_root / path


def _scope_allows(entry: Dict[str, Any], project_id: str, pipeline_id: str) -> bool:
    scopes = entry.get("scopes")
    if not scopes:
        return True
    projects = scopes.get("projects", ["*"])
    pipelines = scopes.get("pipelines", ["*"])
    return ("*" in projects or project_id in projects) and ("*" in pipelines or pipeline_id in pipelines)


def _required_signatures(overall_risk: str, policy: Dict[str, Any]) -> int:
    defaults = {"low": 1, "medium": 1, "high": 2}
    rules = policy.get("forgescaffold", {}).get("min_signatures_by_risk", {})
    merged = {**defaults, **(rules or {})}
    return int(merged.get(overall_risk, 1))


def _verify_checkpoint_signature(
    checkpoint_path: Path,
    signature_path: Path,
    policy: Dict[str, Any],
    trusted_signers: List[Dict[str, Any]],
    project_id: str,
    pipeline_id: str,
) -> Tuple[bool, List[Dict[str, Any]], List[str]]:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for checkpoint verification") from exc

    checkpoint = json.loads(checkpoint_path.read_text())
    signature = json.loads(signature_path.read_text())
    checkpoint_bytes = canonical_json(checkpoint).encode("utf-8")

    signatures = signature.get("signatures") or []
    signer_reports = []
    errors = []
    valid_count = 0

    for entry in signatures:
        report = {
            "fingerprint": entry.get("fingerprint"),
            "signature_valid": False,
            "trusted": False,
            "scope_ok": True,
            "expired": False,
            "errors": [],
        }
        sig_bytes = base64.b64decode(entry.get("sig", ""))
        public_bytes = base64.b64decode(entry.get("public_key", ""))
        if entry.get("fingerprint") is None and public_bytes:
            report["fingerprint"] = _sha256_bytes(public_bytes)

        try:
            Ed25519PublicKey.from_public_bytes(public_bytes).verify(sig_bytes, checkpoint_bytes)
            report["signature_valid"] = True
        except Exception:
            report["errors"].append("CHECKPOINT_SIGNATURE_INVALID")

        signer_entry = None
        for signer in trusted_signers:
            if signer.get("fingerprint") == report.get("fingerprint"):
                signer_entry = signer
                break
        if signer_entry:
            if signer_entry.get("revoked"):
                report["errors"].append("CHECKPOINT_SIGNER_UNTRUSTED")
            else:
                report["trusted"] = True
        else:
            report["errors"].append("CHECKPOINT_SIGNER_UNTRUSTED")

        if signer_entry and signer_entry.get("expires_at"):
            try:
                expires_at = _parse_datetime(str(signer_entry.get("expires_at")))
                if expires_at < datetime.now(timezone.utc):
                    report["expired"] = True
                    report["errors"].append("CHECKPOINT_SIGNER_EXPIRED")
            except Exception:
                report["errors"].append("CHECKPOINT_SIGNER_EXPIRED")

        if signer_entry and signer_entry.get("scopes"):
            if not _scope_allows(signer_entry, project_id, pipeline_id):
                report["scope_ok"] = False
                report["errors"].append("CHECKPOINT_SCOPE_VIOLATION")

        if report["signature_valid"] and report["trusted"] and report["scope_ok"] and not report["expired"]:
            valid_count += 1

        signer_reports.append(report)
        errors.extend(report["errors"])

    overall_risk = "medium"
    required = _required_signatures(overall_risk, policy)
    if valid_count < required:
        errors.append("CHECKPOINT_SIGNATURE_INVALID")

    if signature.get("manifest_sha256") != _sha256_bytes(checkpoint_bytes):
        errors.append("CHECKPOINT_SIGNATURE_INVALID")

    return len(errors) == 0, signer_reports, errors


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not sandbox:
        raise RuntimeError("Sandbox missing")

    index_path = project_root / "evidence" / "evidence_index.jsonl"
    entries = load_index(index_path)
    ok, bad_line, error = verify_index_chain(index_path)

    report = {
        "status": "PASS",
        "entry_count": len(entries),
        "first_bad_line": None,
        "error_codes": [],
        "computed_last_entry_hash": entries[-1].get("entry_hash") if entries else None,
        "checkpoint_last_entry_hash": None,
        "signers": [],
    }

    if not ok:
        report["status"] = "FAIL"
        report["first_bad_line"] = bad_line
        report["error_codes"].append(error)

    policy = _load_policy(project_root)
    index_policy = policy.get("forgescaffold", {}).get("index_integrity", {})

    checkpoints_dir = _resolve_checkpoint_dir(project_root, index_policy)
    checkpoint_files = []
    if checkpoints_dir.exists():
        for path in checkpoints_dir.glob("checkpoint_*.json"):
            if path.name.endswith(".signature.json"):
                continue
            checkpoint_files.append(path)
        checkpoint_files = sorted(checkpoint_files)

    if index_policy.get("checkpoint_enabled", False):
        if not checkpoint_files:
            report["status"] = "FAIL"
            report["error_codes"].append("CHECKPOINT_MISSING")
        else:
            checkpoint_path = checkpoint_files[-1]
            signature_path = checkpoint_path.with_suffix(".signature.json")
            if not signature_path.exists():
                report["status"] = "FAIL"
                report["error_codes"].append("CHECKPOINT_SIGNATURE_INVALID")
            else:
                checkpoint = json.loads(checkpoint_path.read_text())
                report["checkpoint_last_entry_hash"] = checkpoint.get("last_entry_hash")
                if checkpoint.get("last_entry_hash") != report.get("computed_last_entry_hash"):
                    report["status"] = "FAIL"
                    report["error_codes"].append("CHECKPOINT_HASH_MISMATCH")
                if checkpoint.get("policy_snapshot_hash") != policy_snapshot_hash(policy):
                    report["status"] = "FAIL"
                    report["error_codes"].append("POLICY_SNAPSHOT_MISMATCH")

                trusted = _load_trusted_signers(project_root)
                ok_sig, signer_reports, errors = _verify_checkpoint_signature(
                    checkpoint_path,
                    signature_path,
                    policy,
                    trusted,
                    project_context.get("project_id", ""),
                    project_context.get("pipeline_id", ""),
                )
                report["signers"] = signer_reports
                if not ok_sig:
                    report["status"] = "FAIL"
                    report["error_codes"].extend(errors)

    report_path = sandbox.publish(
        "forgescaffold.index_integrity_report.json",
        "index_integrity_report.json",
        report,
        schema="json",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {"forgescaffold.index_integrity_report.json": {"path": report_path}},
        "metrics": {"errors": len(report.get("error_codes", []))},
    }
