from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from forgeledger.audit import emit_audit_event
from forgeledger.backend import (
    AppendResult,
    ChainValidationReport,
    ExportSelector,
    HoldResult,
    HoldSelector,
    LedgerBackend,
    LedgerQuery,
)
from forgeledger.schema import Actor, EventType, LedgerEvent


class AuditedLedgerBackend(LedgerBackend):
    """
    Wrapper that adds opt-in read-access audit events.

    It deliberately audits only query metadata and result counts. Returned
    events and payload values are never copied into the read-access audit event.
    Set audit_reads=False when wrapping the audit ledger itself to avoid
    recursive read-access events.
    """

    def __init__(
        self,
        wrapped: LedgerBackend,
        *,
        audit_emitter: object | None = None,
        source_ledger_id: str | None = None,
        audit_reads: bool = True,
    ) -> None:
        self._wrapped = wrapped
        self._audit_emitter = audit_emitter
        self._source_ledger_id = source_ledger_id or self._infer_source_ledger_id(wrapped)
        self._audit_reads = audit_reads

    def audited_read_events(
        self,
        query: LedgerQuery,
        *,
        actor: Actor,
        reason: str,
    ) -> list[LedgerEvent]:
        events = self._wrapped.read_events(query)
        if self._audit_emitter is not None and self._audit_reads:
            payload = {
                "queried_by": actor.actor_id,
                "actor_id": actor.actor_id,
                "actor_type": actor.actor_type,
                "actor_role": actor.role,
                "reason": reason,
                "query": self._query_payload(query),
                "result_count": len(events),
                "source_ledger_id": self._source_ledger_id,
                "source_path": self._source_ledger_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            emit_audit_event(
                self._audit_emitter,
                event_type=EventType.LEDGER_READ_ACCESS,
                reason="read_access",
                tenant_id=query.tenant_id or "ledger-audit",
                payload=payload,
            )
        return events

    def append_event(self, event: LedgerEvent) -> AppendResult:
        return self._wrapped.append_event(event)

    def read_events(self, query: LedgerQuery) -> list[LedgerEvent]:
        return self._wrapped.read_events(query)

    def get_latest_hash(self) -> Optional[str]:
        return self._wrapped.get_latest_hash()

    def verify_chain(self) -> ChainValidationReport:
        return self._wrapped.verify_chain()

    def apply_legal_hold(self, selector: HoldSelector) -> HoldResult:
        return self._wrapped.apply_legal_hold(selector)

    def release_legal_hold(self, hold_id: str, reason: str) -> HoldResult:
        return self._wrapped.release_legal_hold(hold_id, reason)

    def is_on_hold(self, event_id: str) -> bool:
        return self._wrapped.is_on_hold(event_id)

    def export_slice(self, selector: ExportSelector) -> dict:
        return self._wrapped.export_slice(selector)

    def health_check(self) -> dict:
        result = self._wrapped.health_check()
        result["audited_wrapper"] = True
        result["read_auditing_enabled"] = self._audit_emitter is not None and self._audit_reads
        return result

    @staticmethod
    def _query_payload(query: LedgerQuery) -> dict:
        return {key: value for key, value in asdict(query).items() if value is not None}

    @staticmethod
    def _infer_source_ledger_id(wrapped: LedgerBackend) -> str:
        path = getattr(wrapped, "_path", None)
        if path is not None:
            return str(path)
        return wrapped.__class__.__name__
