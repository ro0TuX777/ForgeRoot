import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml


def _load_artifact(artifact_store, artifact_id: str) -> Dict[str, Any]:
    meta = artifact_store.get(artifact_id)
    if not meta:
        raise RuntimeError(f"Missing required artifact: {artifact_id}")
    with open(meta["path"], "r") as fh:
        return json.load(fh)


def _load_policy(project_root: Path) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    policy_path = repo_root / "dawn" / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        policy_path = project_root / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        return {}
    return yaml.safe_load(policy_path.read_text()) or {}


def _risk_defaults() -> Dict[str, Any]:
    return {
        "require_risk_ack_for": ["high"],
        "require_two_person_for": ["high"],
    }


def _required_from_risk(overall_risk: str, rules: Dict[str, Any]) -> Tuple[int, bool]:
    required_approvals = 2 if overall_risk in rules.get("require_two_person_for", []) else 1
    required_risk_ack = overall_risk in rules.get("require_risk_ack_for", [])
    return required_approvals, required_risk_ack


def _required_signatures(overall_risk: str, policy: Dict[str, Any]) -> int:
    defaults = {"low": 1, "medium": 1, "high": 2}
    rules = policy.get("forgescaffold", {}).get("min_signatures_by_risk", {})
    merged = {**defaults, **(rules or {})}
    return int(merged.get(overall_risk, 1))


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    artifact_store = project_context.get("artifact_store")
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not artifact_store or not sandbox:
        raise RuntimeError("Sandbox or artifact store missing")

    patchset = _load_artifact(artifact_store, "forgescaffold.instrumentation.patchset.json")
    review_packet = _load_artifact(artifact_store, "forgescaffold.review_packet.json")

    policy = _load_policy(project_root)
    risk_rules = _risk_defaults()
    risk_rules.update(policy.get("forgescaffold", {}).get("risk_rules", {}) or {})

    overall_risk = review_packet.get("overall_risk", "medium")
    required_approvals, required_risk_ack = _required_from_risk(overall_risk, risk_rules)
    required_signatures = _required_signatures(overall_risk, policy)
    max_risk = risk_rules.get("max_risk_without_auto_block")
    order = {"low": 0, "medium": 1, "high": 2}
    needs_override = False
    if max_risk and order.get(overall_risk, 0) > order.get(max_risk, 0):
        needs_override = True

    guidance = None
    if overall_risk == "high":
        guidance = "High-risk change: capture two approvers when feasible."
        if required_signatures >= 2:
            guidance = f"{guidance} Requires two evidence signatures."

    template: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "approval_id": uuid.uuid4().hex,
        "patchset_id": patchset.get("patchset_id"),
        "bundle_content_sha256": patchset.get("target", {}).get("bundle_content_sha256"),
        "review_packet_sha256": review_packet.get("review_packet_sha256"),
        "required_approvals": required_approvals,
        "required_risk_ack": required_risk_ack,
        "required_signatures": required_signatures,
        "guidance": guidance,
        "approval_reason": "",
        "approved_at": "",
        "nonce": "",
        "ticket_id": "",
        "risk_ack": False if required_risk_ack else None,
        "risk_override": False if needs_override else None,
    }

    if overall_risk == "high":
        template["approvers"] = [
            {"name": "", "approved_at": "", "nonce": "", "approval_reason": ""},
            {"name": "", "approved_at": "", "nonce": "", "approval_reason": ""},
        ]
    elif required_approvals == 1:
        template["approver"] = ""
    else:
        template["approvers"] = [
            {"name": "", "approved_at": "", "nonce": ""},
            {"name": "", "approved_at": "", "nonce": ""},
        ]

    instructions = [
        "# ForgeScaffold Approval Instructions",
        "",
        "- Fill in approver identity, approval_reason, approved_at (UTC), and nonce(s).",
        "- If required_approvals=2, provide two distinct approver names.",
        "- If required_risk_ack=true, set risk_ack=true.",
    ]

    template_path = sandbox.publish(
        "forgescaffold.approval_template.json",
        "approval_template.json",
        template,
        schema="json",
    )
    instructions_path = sandbox.write_text("approval_instructions.md", "\n".join(instructions))

    return {
        "status": "SUCCEEDED",
        "outputs": {
            "forgescaffold.approval_template.json": {"path": template_path},
            "forgescaffold.approval_instructions.md": {"path": instructions_path},
        },
        "metrics": {"required_approvals": required_approvals, "required_risk_ack": required_risk_ack},
    }
