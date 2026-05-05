import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

COMMON_DIR = Path(__file__).resolve().parents[1] / "forgescaffold_common"
sys.path.append(str(COMMON_DIR))

from lock_utils import load_policy, release_lock  # noqa: E402
from index_utils import append_index_entry  # noqa: E402
from ticket_utils import normalize_ticket_id  # noqa: E402


def _load_artifact(artifact_store, artifact_id: str) -> Dict[str, Any]:
    meta = artifact_store.get(artifact_id)
    if not meta:
        raise RuntimeError(f"Missing required artifact: {artifact_id}")
    with open(meta["path"], "r") as fh:
        return json.load(fh)


def _approvers_from_receipt(receipt: Dict[str, Any]) -> List[str]:
    approvers = receipt.get("approvers")
    if isinstance(approvers, list) and approvers:
        return approvers
    names = []
    if receipt.get("approver"):
        names.append(receipt["approver"])
    if receipt.get("co_approver"):
        names.append(receipt["co_approver"])
    return names


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    artifact_store = project_context.get("artifact_store")
    project_root = Path(project_context["project_root"])
    if not artifact_store:
        raise RuntimeError("Artifact store missing")

    try:
        policy = load_policy(project_root)
        ticket_policy = policy.get("forgescaffold", {}).get("tickets", {}) if isinstance(policy, dict) else {}
        allowed_regex = ticket_policy.get("allowed_id_regex")

        verification = _load_artifact(artifact_store, "forgescaffold.evidence_verification_report.json")
        if verification.get("status") != "PASS":
            return {
                "status": "SUCCEEDED",
                "outputs": {},
                "metrics": {"indexed": 0, "skipped": 1, "reason": "verification_failed"},
            }

        rollback = _load_artifact(artifact_store, "forgescaffold.rollback_report.json")
        if rollback.get("status") != "PASS":
            return {
                "status": "SUCCEEDED",
                "outputs": {},
                "metrics": {"indexed": 0, "skipped": 1, "reason": "rollback_failed"},
            }

        manifest_meta = artifact_store.get("forgescaffold.evidence_manifest.json")
        if not manifest_meta:
            raise RuntimeError("Evidence manifest missing")
        manifest = _load_artifact(artifact_store, "forgescaffold.evidence_manifest.json")
        signature = _load_artifact(artifact_store, "forgescaffold.evidence_signature.json")
        approval = _load_artifact(artifact_store, "forgescaffold.approval_receipt.json")
        patchset = _load_artifact(artifact_store, "forgescaffold.instrumentation.patchset.json")
        review_packet = _load_artifact(artifact_store, "forgescaffold.review_packet.json")
        verify_post_apply = None
        if artifact_store.get("forgescaffold.verification_report.json"):
            verify_post_apply = _load_artifact(artifact_store, "forgescaffold.verification_report.json")
        apply_report = None
        if artifact_store.get("forgescaffold.apply_report.json"):
            apply_report = _load_artifact(artifact_store, "forgescaffold.apply_report.json")
        ticket_receipt = None
        if artifact_store.get("forgescaffold.ticket_event_receipt.json"):
            ticket_receipt = _load_artifact(artifact_store, "forgescaffold.ticket_event_receipt.json")

        index_dir = project_root / "evidence"
        index_dir.mkdir(parents=True, exist_ok=True)
        index_path = index_dir / "evidence_index.jsonl"

        evidence_pack_path = str(Path(manifest_meta["path"]).parent)

        signer_fingerprints = []
        signatures = signature.get("signatures") or []
        if signatures:
            signer_fingerprints = [entry.get("fingerprint") for entry in signatures if entry.get("fingerprint")]
        elif signature.get("public_key_fingerprint"):
            signer_fingerprints = [signature.get("public_key_fingerprint")]

        ticket_id = None
        ticket_id_status = None
        ticket_event_id = None
        if ticket_receipt:
            ticket_id = ticket_receipt.get("ticket_id")
            ticket_id_status = ticket_receipt.get("ticket_id_status")
            ticket_event_id = ticket_receipt.get("ticket_event_id")
        else:
            raw_ticket = approval.get("ticket_id") or approval.get("ticket")
            if raw_ticket:
                try:
                    ticket_id = normalize_ticket_id(raw_ticket, allowed_regex=allowed_regex)
                    ticket_id_status = "bound"
                except Exception:
                    ticket_id = None
            if not ticket_id_status:
                if ticket_policy.get("enabled") and ticket_policy.get("require_ticket_id"):
                    ticket_id_status = "missing_blocked"
                else:
                    ticket_id_status = "missing_allowed"

        entry = {
            "schema_version": "2.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "patchset_id": patchset.get("patchset_id"),
            "bundle_content_sha256": patchset.get("target", {}).get("bundle_content_sha256"),
            "review_packet_sha256": review_packet.get("review_packet_sha256"),
            "approvers": _approvers_from_receipt(approval),
            "risk_level": review_packet.get("overall_risk") or approval.get("risk_level"),
            "signer_fingerprints": signer_fingerprints,
            "signature_count_required": verification.get("required_signatures"),
            "signature_count_valid": verification.get("valid_signatures"),
            "pipeline_name": project_context.get("pipeline_id"),
            "verification_mode": (verify_post_apply or {}).get("mode"),
            "approval_id": approval.get("approval_id"),
            "approval_id_status": approval.get("approval_id_status"),
            "lock_forced": bool((apply_report or {}).get("lock_forced")),
            "lock_ttl_minutes": (apply_report or {}).get("lock_ttl_minutes"),
            "evidence_pack_path": evidence_pack_path,
            "manifest_hash": signature.get("manifest_sha256"),
            "status": "PASS",
            "ticket_id": ticket_id,
            "ticket_id_status": ticket_id_status,
            "ticket_event_id": ticket_event_id,
        }

        append_index_entry(index_path, entry)

        return {
            "status": "SUCCEEDED",
            "outputs": {},
            "metrics": {"indexed": 1},
        }
    finally:
        release_lock(project_root)
