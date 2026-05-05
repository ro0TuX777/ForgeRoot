import json
from pathlib import Path
from typing import Any, Dict

COMMON_DIR = Path(__file__).resolve().parents[1] / "forgescaffold_common"
import sys
sys.path.append(str(COMMON_DIR))

from lock_utils import load_policy  # noqa: E402
from ticket_utils import append_ticket_event, normalize_ticket_id, validate_ticket_ref  # noqa: E402


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not sandbox:
        raise RuntimeError("Sandbox missing")

    config = link_config.get("config", {}) if isinstance(link_config, dict) else {}
    policy = load_policy(project_root)
    ticket_policy = policy.get("forgescaffold", {}).get("tickets", {}) if isinstance(policy, dict) else {}
    allowed_regex = ticket_policy.get("allowed_id_regex")

    ticket_id = config.get("ticket_id")
    ticket_ref = config.get("ticket_ref")
    if not ticket_id and isinstance(ticket_ref, dict):
        ok, errors = validate_ticket_ref(ticket_ref, allowed_regex=allowed_regex)
        if not ok:
            raise RuntimeError(f"TICKET_ID_INVALID: {errors}")
        ticket_id = ticket_ref.get("ticket_id")

    try:
        ticket_id = normalize_ticket_id(ticket_id, allowed_regex=allowed_regex)
    except Exception as exc:
        raise RuntimeError("TICKET_ID_INVALID") from exc

    event_type = config.get("event_type")
    if not event_type:
        raise RuntimeError("event_type is required")

    actor = config.get("actor")
    payload = config.get("payload") or {}

    events_path = project_root / "tickets" / "ticket_events.jsonl"
    event = append_ticket_event(
        events_path,
        ticket_id=ticket_id,
        event_type=event_type,
        actor=actor,
        payload=payload,
        event_id=config.get("event_id"),
        timestamp=config.get("timestamp"),
    )

    receipt = {
        "schema_version": "1.0.0",
        "ticket_id": ticket_id,
        "ticket_event_id": event.get("event_id"),
        "event_type": event_type,
        "event_hash": event.get("event_hash"),
        "prev_event_hash": event.get("prev_event_hash"),
    }

    receipt_path = sandbox.publish(
        "forgescaffold.ticket_event_receipt.json",
        "ticket_event_receipt.json",
        receipt,
        schema="json",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {"forgescaffold.ticket_event_receipt.json": {"path": receipt_path}},
        "metrics": {"event_type": event_type},
    }
