"""
Ingest-time redaction for ForgeLedger.

Redaction runs BEFORE attach_integrity so the hash chain covers exactly the
form of the event that is persisted.  Governance classification fields
(data_sensitivity, prompt_class, response_class, model_provider, latency_ms)
are deliberately NEVER redacted — they are needed for retention classification,
reporting, and policy mapping after the event is stored.

Only content-bearing fields listed in RedactionPolicy.content_fields are
replaced with [REDACTED:sha256:<hex>].
"""
from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from forgeledger.schema import LedgerEvent, RedactionReceipt

# These fields carry governance metadata that must survive redaction intact.
_GOVERNANCE_FIELDS = frozenset({
    "data_sensitivity",
    "prompt_class",
    "response_class",
    "model_provider",
    "latency_ms",
    "redaction_applied",
})


@dataclass
class RedactionPolicy:
    allow_raw_storage: bool = False
    sensitive_marker: str = "llm_prompt_pii_suspected"
    # Only content-bearing fields are redacted.  Governance fields are always kept.
    content_fields: list[str] = field(
        default_factory=lambda: ["prompt", "response", "tool_args", "credentials"]
    )


class IngestRedactor:
    def __init__(
        self,
        policy: RedactionPolicy | None = None,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._policy = policy or RedactionPolicy()
        self._now_factory = now_factory or (lambda: datetime.now(timezone.utc))

    def redact(self, event: LedgerEvent) -> LedgerEvent:
        """
        Return a new event with content-bearing payload fields replaced by
        [REDACTED:sha256:<hex>] markers and redaction_receipts populated.

        Returns the event unchanged if:
        - allow_raw_storage is True
        - payload is None
        - payload.data_sensitivity does not match the sensitive_marker
        """
        if self._policy.allow_raw_storage:
            return event
        if event.payload is None:
            return event
        if event.payload.get("data_sensitivity") != self._policy.sensitive_marker:
            return event

        new_payload = dict(event.payload)
        new_receipts: list[RedactionReceipt] = []
        redacted_at = self._now_factory().isoformat()

        for field_name in self._policy.content_fields:
            if field_name not in new_payload:
                continue
            if field_name in _GOVERNANCE_FIELDS:
                continue
            original = str(new_payload[field_name])
            sha = hashlib.sha256(original.encode("utf-8")).hexdigest()
            new_payload[field_name] = f"[REDACTED:sha256:{sha}]"
            new_receipts.append(RedactionReceipt(
                field_path=f"payload.{field_name}",
                sha256_of_original=sha,
                redacted_at=redacted_at,
            ))

        new_payload["redaction_applied"] = True

        return dataclasses.replace(
            event,
            payload=new_payload,
            redaction_receipts=list(event.redaction_receipts) + new_receipts,
        )
