"""Phase 8e retention lifecycle tests."""
import dataclasses
from datetime import datetime, timezone

from forgeledger.backend import LedgerQuery
from forgeledger.emitter import LedgerEmitter
from forgeledger.hash_chain import attach_integrity
from forgeledger.jsonl_backend import JsonlBackend
from forgeledger.retention_lifecycle import RetentionLifecycleManager
from forgeledger.schema import (
    LEDGER_VERSION,
    Actor,
    Decision,
    EventType,
    Evidence,
    Integrity,
    LedgerEvent,
    Policy,
    RetentionClass,
    SystemContext,
    Tenant,
)
from forgeledger.worm_backend import WormBackend


NOW = datetime(2026, 4, 30, tzinfo=timezone.utc)
SENSITIVE_PROMPT = "Customer Jane Doe NZBN 9429040000000 needs payroll help"


def _event(
    event_id: str,
    retention_class: RetentionClass | str,
    event_time: str,
    *,
    legal_hold: bool = False,
    event_type: EventType = EventType.AGENT_TOOL_CALL,
    payload: dict | None = None,
) -> LedgerEvent:
    event = LedgerEvent(
        event_id=event_id,
        ledger_version=LEDGER_VERSION,
        event_type=event_type,
        event_time=event_time,
        actor=Actor(actor_type="system", actor_id="retention-test", role="tester"),
        tenant=Tenant(tenant_id="tenant-001", customer_boundary="boundary", data_residency="NZ"),
        system_context=SystemContext(source_module="ForgeLedger", environment="local", deployment_id="test"),
        decision=Decision(decision_type="allow", reason="retention_test", risk_level="low"),
        evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["TEST"]),
        policy=Policy(
            policy_id="policy-001",
            policy_hash="hash-001",
            retention_class=retention_class,  # type: ignore[arg-type]
            legal_hold=legal_hold,
        ),
        control_tags=["NZISM.LOGGING"],
        integrity=Integrity(previous_hash=None, event_hash=""),
        payload=payload,
    )
    return attach_integrity(event, None)


def _backend_with(event: LedgerEvent, path) -> JsonlBackend:
    backend = JsonlBackend(path)
    backend.append_event(event)
    return backend


def _scan_one(event: LedgerEvent):
    return RetentionLifecycleManager().scan([event], NOW)


def test_retention_scan_identifies_expired_transient_event():
    event = _event("evt-001", RetentionClass.EPHEMERAL, "2026-04-29T00:00:00+00:00")

    report = _scan_one(event)

    assert report.actions[0].action == "metadata_only"


def test_retention_scan_retains_audit_7y_event_before_expiry():
    event = _event("evt-001", RetentionClass.AUDIT_7Y, "2026-04-01T00:00:00+00:00")

    report = _scan_one(event)

    assert report.actions[0].action == "retain"


def test_retention_scan_identifies_archive_candidate():
    event = _event("evt-001", RetentionClass.SUPPORT_1Y, "2024-01-01T00:00:00+00:00")

    report = _scan_one(event)

    assert report.actions[0].action == "archive"


def test_legal_hold_blocks_deletion():
    event = _event("evt-001", RetentionClass.EPHEMERAL, "2024-01-01T00:00:00+00:00", legal_hold=True)

    report = _scan_one(event)

    assert report.actions[0].action == "blocked_by_legal_hold"
    assert report.blocked_by_legal_hold == ["evt-001"]


def test_dry_run_does_not_modify_backend(tmp_path):
    event = _event("evt-001", RetentionClass.EPHEMERAL, "2024-01-01T00:00:00+00:00")
    backend = _backend_with(event, tmp_path / "ledger.jsonl")
    before = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8")

    result = RetentionLifecycleManager().apply(_scan_one(event), backend)

    assert result.dry_run is True
    assert (tmp_path / "ledger.jsonl").read_text(encoding="utf-8") == before


def test_apply_metadata_only_preserves_event_id_type_hash(tmp_path):
    event = _event("evt-001", RetentionClass.EPHEMERAL, "2024-01-01T00:00:00+00:00")
    backend = _backend_with(event, tmp_path / "ledger.jsonl")

    result = RetentionLifecycleManager().apply(_scan_one(event), backend, dry_run=False)

    metadata = result.metadata_only_records[0]
    assert metadata["event_id"] == event.event_id
    assert metadata["event_type"] == event.event_type.value
    assert metadata["event_hash"] == event.integrity.event_hash
    assert metadata["retention_action"] == "metadata_only"


def test_apply_delete_attempt_against_worm_backend_reports_blocked(tmp_path):
    event = _event("evt-001", RetentionClass.OPERATIONAL_30D, "2024-01-01T00:00:00+00:00")
    backend = WormBackend(tmp_path / "ledger.jsonl")
    backend.append_event(event)

    result = RetentionLifecycleManager().apply(_scan_one(event), backend, dry_run=False)

    assert result.blocked_by_backend == ["evt-001"]
    assert result.applied_actions[0].action == "blocked_by_backend"


def test_retention_scan_emits_audit_event_when_configured(tmp_path):
    audit_backend = JsonlBackend(tmp_path / "audit.jsonl")
    audit_emitter = LedgerEmitter(audit_backend)
    event = _event("evt-001", RetentionClass.EPHEMERAL, "2024-01-01T00:00:00+00:00")

    RetentionLifecycleManager(audit_emitter=audit_emitter).scan([event], NOW)

    audit_event = audit_backend.read_events(LedgerQuery(event_types=[EventType.LEDGER_RETENTION_SCAN_COMPLETED.value]))[0]
    assert audit_event.payload["scanned_count"] == 1
    assert audit_event.payload["action_counts"]["metadata_only"] == 1


def test_retention_action_never_deletes_legal_hold_event(tmp_path):
    original = _event("evt-001", RetentionClass.OPERATIONAL_30D, "2024-01-01T00:00:00+00:00")
    held = dataclasses.replace(original, policy=dataclasses.replace(original.policy, legal_hold=True))
    backend = _backend_with(held, tmp_path / "ledger.jsonl")
    stale_delete_report = _scan_one(original)

    result = RetentionLifecycleManager().apply(stale_delete_report, backend, dry_run=False)

    assert result.applied_actions[0].action == "blocked_by_legal_hold"


def test_retention_report_is_deterministic_with_fixed_now():
    event = _event("evt-001", RetentionClass.EPHEMERAL, "2024-01-01T00:00:00+00:00")
    manager = RetentionLifecycleManager()

    first = manager.scan([event], NOW)
    second = manager.scan([event], NOW)

    assert first == second


def test_retention_scan_handles_missing_event_time_as_error():
    event = _event("evt-001", RetentionClass.EPHEMERAL, "2024-01-01T00:00:00+00:00")
    event = dataclasses.replace(event, event_time="")

    report = _scan_one(event)

    assert "missing event_time" in report.errors[0]


def test_retention_scan_handles_unknown_retention_class_as_error():
    event = _event("evt-001", "unknown_class", "2024-01-01T00:00:00+00:00")

    report = _scan_one(event)

    assert "unknown retention class" in report.errors[0]


def test_retention_audit_event_does_not_include_sensitive_payload(tmp_path):
    audit_backend = JsonlBackend(tmp_path / "audit.jsonl")
    audit_emitter = LedgerEmitter(audit_backend)
    event = _event(
        "evt-001",
        RetentionClass.SUPPORT_1Y,
        "2024-01-01T00:00:00+00:00",
        payload={"prompt": SENSITIVE_PROMPT},
    )

    RetentionLifecycleManager(audit_emitter=audit_emitter).scan([event], NOW)

    assert SENSITIVE_PROMPT not in (tmp_path / "audit.jsonl").read_text(encoding="utf-8")


def test_retention_apply_requires_explicit_dry_run_false_for_mutation(tmp_path):
    event = _event("evt-001", RetentionClass.EPHEMERAL, "2024-01-01T00:00:00+00:00")
    backend = _backend_with(event, tmp_path / "ledger.jsonl")

    result = RetentionLifecycleManager().apply(_scan_one(event), backend)

    assert result.dry_run is True
    assert result.metadata_only_records == []
