from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from forgeledger.audit import emit_audit_event
from forgeledger.backend import LedgerBackend
from forgeledger.retention import get_retention_policy
from forgeledger.schema import EventType, LedgerEvent, RetentionClass


@dataclass
class RetentionAction:
    event_id: str
    action: str
    reason: str
    effective_at: str


@dataclass
class RetentionScanReport:
    scanned_count: int
    actions: list[RetentionAction]
    blocked_by_legal_hold: list[str]
    errors: list[str]


@dataclass
class RetentionApplyResult:
    dry_run: bool
    applied_actions: list[RetentionAction]
    metadata_only_records: list[dict]
    blocked_by_backend: list[str]
    errors: list[str]


class RetentionLifecycleManager:
    """Retention lifecycle scanner/applicator with dry-run as the safe default."""

    def __init__(self, audit_emitter: object | None = None) -> None:
        self._audit_emitter = audit_emitter

    def scan(self, events: Iterable[LedgerEvent], now: datetime) -> RetentionScanReport:
        fixed_now = _as_aware_utc(now)
        effective_at = fixed_now.isoformat()
        event_list = list(events)
        actions: list[RetentionAction] = []
        blocked_by_legal_hold: list[str] = []
        errors: list[str] = []

        for event in event_list:
            try:
                retention_class = _retention_value(event)
                policy = (
                    get_retention_policy(event.policy.retention_class)
                    if isinstance(event.policy.retention_class, RetentionClass)
                    else {}
                )
                if not policy:
                    errors.append(f"{event.event_id}: unknown retention class {retention_class!r}")
                    continue

                if event.policy.legal_hold or event.policy.retention_class == RetentionClass.LEGAL_HOLD:
                    blocked_by_legal_hold.append(event.event_id)
                    actions.append(RetentionAction(
                        event_id=event.event_id,
                        action="blocked_by_legal_hold",
                        reason="legal hold overrides retention lifecycle",
                        effective_at=effective_at,
                    ))
                    continue

                event_time = _parse_event_time(event.event_time)
                age = fixed_now - event_time
                retain_days = policy.get("retain_for_days")
                if retain_days is None:
                    actions.append(RetentionAction(
                        event_id=event.event_id,
                        action="retain",
                        reason=f"{retention_class} has no automatic expiry",
                        effective_at=effective_at,
                    ))
                    continue

                if age < timedelta(days=int(retain_days)):
                    actions.append(RetentionAction(
                        event_id=event.event_id,
                        action="retain",
                        reason=f"{retention_class} retention period has not expired",
                        effective_at=effective_at,
                    ))
                    continue

                if policy.get("preserve_metadata_only"):
                    action = "metadata_only"
                    reason = f"{retention_class} expired; preserve metadata only"
                elif retention_class in {RetentionClass.SUPPORT_1Y.value, RetentionClass.HEALTH_10Y.value}:
                    action = "archive"
                    reason = f"{retention_class} expired; archive candidate"
                elif policy.get("deletion_allowed", True):
                    action = "delete"
                    reason = f"{retention_class} expired; delete candidate"
                else:
                    action = "retain"
                    reason = f"{retention_class} expired but deletion is not allowed"

                actions.append(RetentionAction(
                    event_id=event.event_id,
                    action=action,
                    reason=reason,
                    effective_at=effective_at,
                ))
            except ValueError as exc:
                errors.append(f"{event.event_id}: {exc}")

        report = RetentionScanReport(
            scanned_count=len(event_list),
            actions=actions,
            blocked_by_legal_hold=blocked_by_legal_hold,
            errors=errors,
        )
        emit_audit_event(
            self._audit_emitter,
            event_type=EventType.LEDGER_RETENTION_SCAN_COMPLETED,
            reason="retention_scan_completed",
            payload={
                "scanned_count": report.scanned_count,
                "action_counts": _action_counts(report.actions),
                "blocked_by_legal_hold": list(report.blocked_by_legal_hold),
                "error_count": len(report.errors),
                "timestamp": effective_at,
            },
        )
        return report

    def apply(
        self,
        report: RetentionScanReport,
        backend: LedgerBackend,
        archive_backend: object | None = None,
        dry_run: bool = True,
    ) -> RetentionApplyResult:
        applied: list[RetentionAction] = []
        metadata_only_records: list[dict] = []
        blocked_by_backend: list[str] = []
        errors = list(report.errors)

        if dry_run:
            return RetentionApplyResult(
                dry_run=True,
                applied_actions=[],
                metadata_only_records=[],
                blocked_by_backend=[],
                errors=errors,
            )

        events_by_id = {event.event_id: event for event in _read_all_backend_events(backend)}
        for action in report.actions:
            event = events_by_id.get(action.event_id)
            if action.action == "blocked_by_legal_hold":
                applied.append(action)
                continue
            if event is not None and (event.policy.legal_hold or event.policy.retention_class == RetentionClass.LEGAL_HOLD):
                blocked = RetentionAction(
                    event_id=action.event_id,
                    action="blocked_by_legal_hold",
                    reason="legal hold overrides retention lifecycle",
                    effective_at=action.effective_at,
                )
                applied.append(blocked)
                continue
            if action.action == "metadata_only":
                record = _metadata_only_record(event, action)
                metadata_only_records.append(record)
                applied.append(action)
                continue
            if action.action in {"delete", "archive"}:
                blocked_by_backend.append(action.event_id)
                applied.append(RetentionAction(
                    event_id=action.event_id,
                    action="blocked_by_backend",
                    reason=f"{action.action} is not supported by append-only backend API",
                    effective_at=action.effective_at,
                ))
                continue
            applied.append(action)

        emit_audit_event(
            self._audit_emitter,
            event_type=EventType.LEDGER_RETENTION_ACTION_APPLIED,
            reason="retention_action_applied",
            payload={
                "dry_run": False,
                "action_counts": _action_counts(applied),
                "metadata_only_count": len(metadata_only_records),
                "blocked_by_backend": list(blocked_by_backend),
                "error_count": len(errors),
            },
        )
        return RetentionApplyResult(
            dry_run=False,
            applied_actions=applied,
            metadata_only_records=metadata_only_records,
            blocked_by_backend=blocked_by_backend,
            errors=errors,
        )


def _parse_event_time(value: str) -> datetime:
    if not value:
        raise ValueError("missing event_time")
    try:
        return _as_aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as exc:
        raise ValueError("invalid event_time") from exc


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _retention_value(event: LedgerEvent) -> str:
    retention = event.policy.retention_class
    return retention.value if isinstance(retention, RetentionClass) else str(retention)


def _read_all_backend_events(backend: LedgerBackend) -> list[LedgerEvent]:
    from forgeledger.backend import LedgerQuery

    return backend.read_events(LedgerQuery(max_results=100_000))


def _metadata_only_record(event: LedgerEvent | None, action: RetentionAction) -> dict:
    return {
        "event_id": action.event_id,
        "event_type": event.event_type.value if event is not None else None,
        "event_hash": event.integrity.event_hash if event is not None else None,
        "retention_action": action.action,
        "reason": action.reason,
        "effective_at": action.effective_at,
    }


def _action_counts(actions: list[RetentionAction]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for action in actions:
        counts[action.action] = counts.get(action.action, 0) + 1
    return counts
