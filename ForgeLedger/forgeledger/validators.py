from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_REDACTED_MARKER_RE = re.compile(r"^\[REDACTED:sha256:([0-9a-f]{64})\]$")


def _is_valid_iso8601(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return True


def validate_event(event: "LedgerEvent") -> list[str]:
    """
    Validate a LedgerEvent for schema completeness.
    Returns a list of error strings; empty list means valid.
    """
    from forgeledger.schema import EventType, RetentionClass
    errors: list[str] = []

    if not event.event_id:
        errors.append("event_id is required")
    if not event.ledger_version:
        errors.append("ledger_version is required")
    if not isinstance(event.event_type, EventType):
        errors.append(f"event_type is invalid: {event.event_type!r}")
    if not event.event_time:
        errors.append("event_time is required")

    # actor
    if not event.actor.actor_id:
        errors.append("actor.actor_id is required")
    if not event.actor.actor_type:
        errors.append("actor.actor_type is required")
    if not event.actor.role:
        errors.append("actor.role is required")

    # tenant
    if not event.tenant.tenant_id:
        errors.append("tenant.tenant_id is required")
    if not event.tenant.data_residency:
        errors.append("tenant.data_residency is required")

    # system_context
    if not event.system_context.source_module:
        errors.append("system_context.source_module is required")
    if not event.system_context.deployment_id:
        errors.append("system_context.deployment_id is required")

    # decision
    if not event.decision.decision_type:
        errors.append("decision.decision_type is required")
    if not event.decision.reason:
        errors.append("decision.reason is required")
    if not event.decision.risk_level:
        errors.append("decision.risk_level is required")

    # policy
    if not event.policy.policy_id:
        errors.append("policy.policy_id is required")
    if not event.policy.policy_hash:
        errors.append("policy.policy_hash is required")
    if not isinstance(event.policy.retention_class, RetentionClass):
        errors.append(f"policy.retention_class is invalid: {event.policy.retention_class!r}")

    # integrity: event_hash is required; signature is HMAC-SHA256 lowercase hex.
    if not event.integrity.event_hash:
        errors.append("integrity.event_hash is required")
    if event.integrity.signature is not None:
        if not isinstance(event.integrity.signature, str) or not _SHA256_HEX_RE.fullmatch(event.integrity.signature):
            errors.append("integrity.signature must be 64 lowercase hex chars when present")

    receipt_hashes_by_field: dict[str, str] = {}
    for index, receipt in enumerate(event.redaction_receipts):
        field_path = getattr(receipt, "field_path", None)
        sha256_of_original = getattr(receipt, "sha256_of_original", None)
        redacted_at = getattr(receipt, "redacted_at", None)

        if not field_path:
            errors.append(f"redaction_receipts[{index}].field_path is required")
        elif not isinstance(field_path, str) or not field_path.startswith("payload."):
            errors.append(f"redaction_receipts[{index}].field_path must start with 'payload.'")

        if not isinstance(sha256_of_original, str) or not _SHA256_HEX_RE.fullmatch(sha256_of_original):
            errors.append(f"redaction_receipts[{index}].sha256_of_original must be 64 lowercase hex chars")

        if not isinstance(redacted_at, str) or not _is_valid_iso8601(redacted_at):
            errors.append(f"redaction_receipts[{index}].redacted_at must be valid ISO-8601")

        if isinstance(field_path, str) and isinstance(sha256_of_original, str):
            receipt_hashes_by_field[field_path] = sha256_of_original

    if event.payload is not None:
        for key, value in event.payload.items():
            if not isinstance(value, str):
                continue
            match = _REDACTED_MARKER_RE.fullmatch(value)
            if match is None:
                continue
            field_path = f"payload.{key}"
            receipt_hash = receipt_hashes_by_field.get(field_path)
            if receipt_hash is None:
                errors.append(f"{field_path} has redacted marker without matching redaction receipt")
            elif receipt_hash != match.group(1):
                errors.append(f"{field_path} redacted marker hash does not match redaction receipt")

        for field_path, receipt_hash in receipt_hashes_by_field.items():
            payload_key = field_path.removeprefix("payload.")
            value = event.payload.get(payload_key)
            if not isinstance(value, str):
                errors.append(f"{field_path} has redaction receipt without redacted payload marker")
                continue
            match = _REDACTED_MARKER_RE.fullmatch(value)
            if match is None or match.group(1) != receipt_hash:
                errors.append(f"{field_path} has redaction receipt without matching redacted payload marker")

    return errors
