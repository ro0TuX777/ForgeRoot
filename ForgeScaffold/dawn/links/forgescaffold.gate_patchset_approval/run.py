import json
import uuid
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


def _load_policy(project_root: Path) -> Dict[str, Any]:
    policy_path = project_root / "dawn" / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        policy_path = project_root / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        return {}
    return yaml.safe_load(policy_path.read_text())


def _parse_datetime(value: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception as exc:
        raise RuntimeError(f"approved_at must be date-time ISO8601, got {value}") from exc


def _normalize_approvers(approval: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    approvers = []
    if isinstance(approval.get("approvers"), list):
        approvers = approval["approvers"]
    else:
        approver = approval.get("approver")
        if approver:
            approvers.append(
                {
                    "name": approver,
                    "approved_at": approval.get("approved_at"),
                    "nonce": approval.get("nonce"),
                }
            )
        co_approver = approval.get("co_approver")
        if co_approver:
            approvers.append(
                {
                    "name": co_approver,
                    "approved_at": approval.get("co_approved_at"),
                    "nonce": approval.get("co_nonce"),
                }
            )
    names = [entry.get("name") for entry in approvers if entry.get("name")]
    return approvers, names


def _validate_approval(approval: Dict[str, Any], patchset: Dict[str, Any], allow_legacy_id: bool) -> None:
    required = ["schema_version", "patchset_id", "bundle_content_sha256", "approval_reason"]
    missing = [field for field in required if field not in approval]
    if missing:
        raise RuntimeError(f"Approval file missing fields: {missing}")
    if not approval.get("approval_id"):
        if not allow_legacy_id:
            raise RuntimeError("Approval file missing approval_id")

    approvers, names = _normalize_approvers(approval)
    if not approvers:
        raise RuntimeError("Approval file missing approver information")

    for approver in approvers:
        if len(str(approver.get("nonce", ""))) < 16:
            raise RuntimeError("Approval nonce must be at least 16 characters")
        if not approver.get("approved_at"):
            raise RuntimeError("Approval approved_at is required for each approver")
        _parse_datetime(str(approver.get("approved_at")))

    patchset_id = patchset.get("patchset_id")
    bundle_sha = patchset.get("target", {}).get("bundle_content_sha256")

    if approval["patchset_id"] != patchset_id:
        raise RuntimeError("Approval patchset_id does not match patchset")
    if approval["bundle_content_sha256"] != bundle_sha:
        raise RuntimeError("Approval bundle_content_sha256 does not match patchset")

    if len(set(names)) != len(names):
        raise RuntimeError("Approval approvers must be distinct")


def _overall_risk(review_packet: Dict[str, Any]) -> str:
    if review_packet.get("overall_risk"):
        return review_packet["overall_risk"]
    order = {"low": 0, "medium": 1, "high": 2}
    highest = "low"
    for op in review_packet.get("operations", []):
        risk = op.get("risk", "low")
        if order.get(risk, 0) > order.get(highest, 0):
            highest = risk
    return highest


def _risk_defaults() -> Dict[str, Any]:
    return {
        "require_risk_ack_for": ["high"],
        "require_two_person_for": ["high"],
        "max_risk_without_auto_block": None,
        "sensitive_path_prefixes": ["dawn/", ".git/", "ci/", "infra/"],
        "high_risk_ops": ["delete", "rename"],
        "high_risk_path_match": [],
    }


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    artifact_store = project_context.get("artifact_store")
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not artifact_store or not sandbox:
        raise RuntimeError("Sandbox or artifact store missing")

    patchset = _load_artifact(artifact_store, "forgescaffold.instrumentation.patchset.json")
    review_meta = artifact_store.get("forgescaffold.review_packet.json")
    review_packet = None
    if review_meta:
        review_packet = _load_artifact(artifact_store, "forgescaffold.review_packet.json")
    mode = link_config.get("config", {}).get("mode", "hitl")

    policy = _load_policy(project_root)
    risk_rules = _risk_defaults()
    risk_rules.update(policy.get("forgescaffold", {}).get("risk_rules", {}) or {})
    profile_name = project_context.get("profile", "normal")
    profile = policy.get("profiles", {}).get(profile_name, {})
    allow_auto = bool(profile.get("allow_auto_approval", False))
    allow_legacy_id = bool(link_config.get("config", {}).get("allow_legacy_approval_id", False))

    approval_path = project_root / "approvals" / "patchset_approval.json"

    if mode == "auto":
        if not allow_auto:
            raise RuntimeError("AUTO approval requested but profile does not allow auto approval")
        approval = {
            "schema_version": "1.0.0",
            "approval_id": uuid.uuid4().hex,
            "patchset_id": patchset.get("patchset_id"),
            "bundle_content_sha256": patchset.get("target", {}).get("bundle_content_sha256"),
            "approver": "auto",
            "approval_reason": "auto-approved by policy",
            "approved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "nonce": "auto-approval-nonce",
            "mode": "auto",
        }
    else:
        if not approval_path.exists():
            raise RuntimeError(
                f"Approval file missing. Create {approval_path} with patchset_id and bundle_content_sha256."
            )
        approval = json.loads(approval_path.read_text())
        _validate_approval(approval, patchset, allow_legacy_id)
        approval["mode"] = "hitl"

    if approval.get("review_packet_sha256"):
        if not review_packet:
            raise RuntimeError("Approval requires review_packet_sha256 but review packet is missing")
        if approval["review_packet_sha256"] != review_packet.get("review_packet_sha256"):
            raise RuntimeError("Approval review_packet_sha256 does not match review packet")

    approvers, names = _normalize_approvers(approval)
    overall_risk = None
    required_approvals = 1
    required_risk_ack = False
    if review_packet:
        overall_risk = _overall_risk(review_packet)
        max_risk = risk_rules.get("max_risk_without_auto_block")
        if max_risk:
            order = {"low": 0, "medium": 1, "high": 2}
            if order.get(overall_risk, 0) > order.get(max_risk, 0):
                if approval.get("risk_override") is not True:
                    raise RuntimeError(f"Risk level {overall_risk} exceeds policy max_risk_without_auto_block")

        if overall_risk in risk_rules.get("require_risk_ack_for", []):
            required_risk_ack = True
            if approval.get("risk_ack") is not True:
                raise RuntimeError("Risk acknowledgment required for high-risk approval")
        if overall_risk in risk_rules.get("require_two_person_for", []):
            required_approvals = 2
            if len(names) < 2:
                raise RuntimeError("Two-person approval required for high-risk patchset")

    approval_id_status = "consumed"
    if not approval.get("approval_id"):
        approval_id_status = "legacy_missing"

    # replay guard
    approval_id = approval.get("approval_id")
    used_approvals_path = project_root / "approvals" / "used_approvals.jsonl"
    if approval_id:
        used_approvals_path.parent.mkdir(parents=True, exist_ok=True)
        if used_approvals_path.exists():
            for line in used_approvals_path.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get("approval_id") == approval_id:
                    raise RuntimeError("Approval replay detected: approval_id already used")

    ticket_value = approval.get("ticket_id") or approval.get("ticket")
    receipt = {
        "schema_version": approval.get("schema_version", "1.0.0"),
        "approval_id": approval.get("approval_id"),
        "approval_id_status": approval_id_status,
        "patchset_id": approval["patchset_id"],
        "bundle_content_sha256": approval["bundle_content_sha256"],
        "approvers": names,
        "approval_reason": approval["approval_reason"],
        "approved_at": approval.get("approved_at"),
        "nonce": approval.get("nonce"),
        "co_approver": approval.get("co_approver"),
        "ticket_id": ticket_value,
        "risk_ack": approval.get("risk_ack"),
        "risk_override": approval.get("risk_override"),
        "risk_level": overall_risk,
        "required_approvals": required_approvals,
        "required_risk_ack": required_risk_ack,
        "mode": approval.get("mode"),
        "approval_file": str(approval_path) if mode != "auto" else None,
        "profile": profile_name,
    }

    if approval_id:
        used_entry = {
            "approval_id": approval_id,
            "consumed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "patchset_id": approval["patchset_id"],
            "bundle_content_sha256": approval["bundle_content_sha256"],
            "review_packet_sha256": approval.get("review_packet_sha256"),
            "approvers": names,
            "pipeline_name": project_context.get("pipeline_id"),
        }
        with used_approvals_path.open("a") as fh:
            fh.write(json.dumps(used_entry) + "\n")

    receipt_path = sandbox.publish(
        "forgescaffold.approval_receipt.json",
        "approval_receipt.json",
        receipt,
        schema="json",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {"forgescaffold.approval_receipt.json": {"path": receipt_path}},
        "metrics": {"mode": mode},
    }
