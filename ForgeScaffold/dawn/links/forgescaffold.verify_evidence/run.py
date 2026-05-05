import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


def _load_artifact(artifact_store, artifact_id: str) -> Dict[str, Any]:
    meta = artifact_store.get(artifact_id)
    if not meta:
        raise RuntimeError(f"Missing required artifact: {artifact_id}")
    with open(meta["path"], "r") as fh:
        return json.load(fh)


def _canonical_json(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_trusted_signers(project_root: Path) -> List[Dict[str, Any]]:
    repo_root = Path(__file__).resolve().parents[3]
    policy_path = repo_root / "dawn" / "policy" / "trusted_signers.yaml"
    if not policy_path.exists():
        policy_path = project_root / "policy" / "trusted_signers.yaml"
    if not policy_path.exists():
        return []
    payload = yaml.safe_load(policy_path.read_text()) or {}
    return payload.get("trusted_signers", []) or []


def _is_trusted(fingerprint: str, signers: List[Dict[str, Any]]) -> Tuple[bool, Dict[str, Any]]:
    for signer in signers:
        if signer.get("fingerprint") == fingerprint:
            if signer.get("revoked"):
                return False, signer
            return True, signer
    return False, {}


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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


def _load_policy(project_root: Path) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    policy_path = repo_root / "dawn" / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        policy_path = project_root / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        return {}
    return yaml.safe_load(policy_path.read_text()) or {}


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    artifact_store = project_context.get("artifact_store")
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not artifact_store or not sandbox:
        raise RuntimeError("Sandbox or artifact store missing")

    manifest = _load_artifact(artifact_store, "forgescaffold.evidence_manifest.json")
    signature = _load_artifact(artifact_store, "forgescaffold.evidence_signature.json")
    receipt = _load_artifact(artifact_store, "forgescaffold.evidence_receipt.json")
    approval = _load_artifact(artifact_store, "forgescaffold.approval_receipt.json")
    patchset = _load_artifact(artifact_store, "forgescaffold.instrumentation.patchset.json")
    review_meta = artifact_store.get("forgescaffold.review_packet.json")
    review_packet = _load_artifact(artifact_store, "forgescaffold.review_packet.json") if review_meta else None

    report = {
        "status": "PASS",
        "signer": {
            "fingerprint": signature.get("public_key_fingerprint"),
            "trusted": False,
        },
        "signers": [],
        "manifest": {},
        "receipt": {},
        "approval": {},
        "errors": [],
    }

    # Verify signature
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for evidence verification") from exc

    manifest_bytes = _canonical_json(manifest)
    manifest_sha = _sha256_bytes(manifest_bytes)

    signatures = signature.get("signatures")
    if not signatures:
        if signature.get("signature") and signature.get("public_key"):
            signatures = [
                {
                    "fingerprint": signature.get("public_key_fingerprint"),
                    "alg": signature.get("algorithm", "ed25519"),
                    "sig": signature.get("signature"),
                    "public_key": signature.get("public_key"),
                }
            ]
        else:
            signatures = []

    signature_valid_count = 0
    signers = _load_trusted_signers(project_root)
    policy = _load_policy(project_root)
    project_id = project_context.get("project_id", "")
    pipeline_id = project_context.get("pipeline_id", "")

    signer_errors = set()
    for entry in signatures:
        signer_report = {
            "fingerprint": entry.get("fingerprint"),
            "signature_valid": False,
            "trusted": False,
            "scope_ok": True,
            "expired": False,
            "errors": [],
        }

        signature_bytes = base64.b64decode(entry.get("sig", ""))
        public_bytes = base64.b64decode(entry.get("public_key", ""))
        if entry.get("fingerprint") is None and public_bytes:
            signer_report["fingerprint"] = _sha256_bytes(public_bytes)

        try:
            Ed25519PublicKey.from_public_bytes(public_bytes).verify(signature_bytes, manifest_bytes)
            signer_report["signature_valid"] = True
        except Exception:
            signer_report["errors"].append("SIGNATURE_INVALID")

        trusted, signer_entry = _is_trusted(signer_report["fingerprint"], signers)
        signer_report["trusted"] = trusted
        signer_report["entry"] = signer_entry if signer_entry else None
        if not trusted:
            signer_report["errors"].append("SIGNER_UNTRUSTED")

        if signer_entry.get("expires_at"):
            try:
                expires_at = _parse_datetime(str(signer_entry.get("expires_at")))
                if expires_at < datetime.now(timezone.utc):
                    signer_report["expired"] = True
                    signer_report["errors"].append("SIGNER_EXPIRED")
            except Exception:
                signer_report["errors"].append("SIGNER_EXPIRED")

        if signer_entry and signer_entry.get("scopes"):
            if not _scope_allows(signer_entry, project_id, pipeline_id):
                signer_report["scope_ok"] = False
                signer_report["errors"].append("SIGNER_SCOPE_VIOLATION")

        if signer_report["signature_valid"] and signer_report["trusted"] and signer_report["scope_ok"] and not signer_report["expired"]:
            signature_valid_count += 1

        report["signers"].append(signer_report)
        signer_errors.update(signer_report["errors"])

    if signature.get("manifest_sha256") != manifest_sha:
        report["errors"].append("MANIFEST_HASH_MISMATCH")
        report["manifest"]["hash_match"] = False
    else:
        report["manifest"]["hash_match"] = True

    if receipt.get("manifest_sha256") != manifest_sha:
        report["errors"].append("RECEIPT_MANIFEST_MISMATCH")
        report["receipt"]["manifest_match"] = False
    else:
        report["receipt"]["manifest_match"] = True

    # Approval linkage
    if approval.get("patchset_id") != patchset.get("patchset_id"):
        report["errors"].append("APPROVAL_PATCHSET_MISMATCH")
    if approval.get("bundle_content_sha256") != patchset.get("target", {}).get("bundle_content_sha256"):
        report["errors"].append("APPROVAL_BUNDLE_MISMATCH")

    # Trust status for legacy fields
    trusted, signer_entry = _is_trusted(signature.get("public_key_fingerprint"), signers)
    report["signer"]["trusted"] = trusted
    report["signer"]["entry"] = signer_entry if signer_entry else None
    if signature.get("public_key_fingerprint") and not trusted:
        report["errors"].append("SIGNER_UNTRUSTED")

    if "SIGNER_EXPIRED" in signer_errors:
        report["errors"].append("SIGNER_EXPIRED")
    if "SIGNER_SCOPE_VIOLATION" in signer_errors:
        report["errors"].append("SIGNER_SCOPE_VIOLATION")
    if "SIGNER_UNTRUSTED" in signer_errors:
        report["errors"].append("SIGNER_UNTRUSTED")

    if signatures and signature_valid_count == 0:
        report["errors"].append("SIGNATURE_INVALID")

    overall_risk = "medium"
    if review_packet and review_packet.get("overall_risk"):
        overall_risk = review_packet["overall_risk"]
    elif approval.get("risk_level"):
        overall_risk = approval.get("risk_level")

    required_signatures = _required_signatures(overall_risk, policy)
    report["required_signatures"] = required_signatures
    report["valid_signatures"] = signature_valid_count
    if signature_valid_count < required_signatures:
        report["errors"].append("INSUFFICIENT_SIGNATURES")

    # Rollback report optional check
    rollback_meta = artifact_store.get("forgescaffold.rollback_report.json")
    if rollback_meta:
        rollback_report = _load_artifact(artifact_store, "forgescaffold.rollback_report.json")
        if rollback_report.get("status") != "PASS":
            report["errors"].append("ROLLBACK_NOT_PASS")

    if report["errors"]:
        report["status"] = "FAIL"

    report_path = sandbox.publish(
        "forgescaffold.evidence_verification_report.json",
        "evidence_verification_report.json",
        report,
        schema="json",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {"forgescaffold.evidence_verification_report.json": {"path": report_path}},
        "metrics": {"errors": len(report["errors"])},
    }
