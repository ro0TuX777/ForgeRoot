"""Phase 8d read-access auditing tests."""
from forgeledger.audited_backend import AuditedLedgerBackend
from forgeledger.backend import LedgerQuery
from forgeledger.emitter import LedgerEmitter
from forgeledger.hash_chain import attach_integrity
from forgeledger.jsonl_backend import JsonlBackend
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
from forgeledger.validators import validate_event


SENSITIVE_PROMPT = "Customer Jane Doe NZBN 9429040000000 needs payroll help"
SENSITIVE_RESPONSE = "Private payroll guidance response"


def _reader() -> Actor:
    return Actor(actor_type="human", actor_id="analyst-001", role="compliance_analyst")


def _make_event(event_id: str = "evt-001", tenant_id: str = "tenant-001") -> LedgerEvent:
    event = LedgerEvent(
        event_id=event_id,
        ledger_version=LEDGER_VERSION,
        event_type=EventType.WARDEN_LLM_CALL_METADATA,
        event_time="2026-04-30T00:00:00+00:00",
        actor=Actor(actor_type="system", actor_id="warden.llm", role="llm_gateway"),
        tenant=Tenant(tenant_id=tenant_id, customer_boundary="boundary", data_residency="NZ"),
        system_context=SystemContext(source_module="Warden", environment="local", deployment_id="test"),
        decision=Decision(decision_type="allow", reason="recorded", risk_level="low"),
        evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["LLM_METADATA"]),
        policy=Policy(policy_id="policy-001", policy_hash="hash-001", retention_class=RetentionClass.SUPPORT_1Y),
        control_tags=["NZISM.LOGGING.EVENT_CAPTURE"],
        integrity=Integrity(previous_hash=None, event_hash=""),
        payload={
            "prompt": SENSITIVE_PROMPT,
            "response": SENSITIVE_RESPONSE,
            "data_sensitivity": "llm_prompt_pii_suspected",
        },
    )
    return attach_integrity(event, None)


def _audit_emitter(path):
    audit_backend = JsonlBackend(path)
    return audit_backend, LedgerEmitter(audit_backend)


def _primary_backend(path, event_count: int = 1):
    backend = JsonlBackend(path)
    previous_hash = None
    for index in range(event_count):
        event = _make_event(f"evt-{index:03d}")
        event = attach_integrity(
            event,
            previous_hash,
        )
        backend.append_event(event)
        previous_hash = event.integrity.event_hash
    return backend


def _audit_events(audit_backend):
    return audit_backend.read_events(LedgerQuery(event_types=[EventType.LEDGER_READ_ACCESS.value], max_results=100))


def test_audited_read_events_emits_ledger_read_access_event(tmp_path):
    primary = _primary_backend(tmp_path / "ledger.jsonl")
    audit_backend, audit = _audit_emitter(tmp_path / "audit_ledger.jsonl")
    audited = AuditedLedgerBackend(primary, audit_emitter=audit)

    audited.audited_read_events(LedgerQuery(), actor=_reader(), reason="case review")

    assert _audit_events(audit_backend)[0].event_type == EventType.LEDGER_READ_ACCESS


def test_read_access_event_contains_actor(tmp_path):
    primary = _primary_backend(tmp_path / "ledger.jsonl")
    audit_backend, audit = _audit_emitter(tmp_path / "audit_ledger.jsonl")

    AuditedLedgerBackend(primary, audit_emitter=audit).audited_read_events(
        LedgerQuery(),
        actor=_reader(),
        reason="case review",
    )

    payload = _audit_events(audit_backend)[0].payload
    assert payload["queried_by"] == "analyst-001"
    assert payload["actor_type"] == "human"
    assert payload["actor_role"] == "compliance_analyst"


def test_read_access_event_contains_reason(tmp_path):
    primary = _primary_backend(tmp_path / "ledger.jsonl")
    audit_backend, audit = _audit_emitter(tmp_path / "audit_ledger.jsonl")

    AuditedLedgerBackend(primary, audit_emitter=audit).audited_read_events(
        LedgerQuery(),
        actor=_reader(),
        reason="evidence package preparation",
    )

    assert _audit_events(audit_backend)[0].payload["reason"] == "evidence package preparation"


def test_read_access_event_contains_query_filters(tmp_path):
    primary = _primary_backend(tmp_path / "ledger.jsonl")
    audit_backend, audit = _audit_emitter(tmp_path / "audit_ledger.jsonl")
    query = LedgerQuery(
        tenant_id="tenant-001",
        source_module="Warden",
        event_types=[EventType.WARDEN_LLM_CALL_METADATA.value],
        max_results=10,
    )

    AuditedLedgerBackend(primary, audit_emitter=audit).audited_read_events(
        query,
        actor=_reader(),
        reason="filtered read",
    )

    assert _audit_events(audit_backend)[0].payload["query"] == {
        "tenant_id": "tenant-001",
        "source_module": "Warden",
        "event_types": [EventType.WARDEN_LLM_CALL_METADATA.value],
        "max_results": 10,
    }


def test_read_access_event_contains_result_count(tmp_path):
    primary = _primary_backend(tmp_path / "ledger.jsonl", event_count=2)
    audit_backend, audit = _audit_emitter(tmp_path / "audit_ledger.jsonl")

    AuditedLedgerBackend(primary, audit_emitter=audit).audited_read_events(
        LedgerQuery(source_module="Warden"),
        actor=_reader(),
        reason="count results",
    )

    assert _audit_events(audit_backend)[0].payload["result_count"] == 2


def test_read_access_event_passes_validate_event(tmp_path):
    primary = _primary_backend(tmp_path / "ledger.jsonl")
    audit_backend, audit = _audit_emitter(tmp_path / "audit_ledger.jsonl")

    AuditedLedgerBackend(primary, audit_emitter=audit).audited_read_events(
        LedgerQuery(),
        actor=_reader(),
        reason="validate audit event",
    )

    assert validate_event(_audit_events(audit_backend)[0]) == []


def test_no_read_access_event_when_no_audit_emitter(tmp_path):
    primary = _primary_backend(tmp_path / "ledger.jsonl")

    AuditedLedgerBackend(primary).audited_read_events(
        LedgerQuery(),
        actor=_reader(),
        reason="unaudited read path",
    )

    assert primary.read_events(LedgerQuery()) != []


def test_audit_ledger_read_does_not_recursively_audit_itself(tmp_path):
    primary = _primary_backend(tmp_path / "ledger.jsonl")
    audit_backend, audit = _audit_emitter(tmp_path / "audit_ledger.jsonl")
    AuditedLedgerBackend(primary, audit_emitter=audit).audited_read_events(
        LedgerQuery(),
        actor=_reader(),
        reason="create one audit event",
    )
    audit_reader = AuditedLedgerBackend(
        audit_backend,
        audit_emitter=audit,
        source_ledger_id="audit_ledger",
        audit_reads=False,
    )

    audit_reader.audited_read_events(LedgerQuery(), actor=_reader(), reason="inspect audit ledger")

    assert len(_audit_events(audit_backend)) == 1


def test_read_access_does_not_leak_sensitive_payload_values(tmp_path):
    primary = _primary_backend(tmp_path / "ledger.jsonl")
    audit_backend, audit = _audit_emitter(tmp_path / "audit_ledger.jsonl")

    AuditedLedgerBackend(primary, audit_emitter=audit).audited_read_events(
        LedgerQuery(),
        actor=_reader(),
        reason="sensitive read",
    )
    raw_audit = (tmp_path / "audit_ledger.jsonl").read_text(encoding="utf-8")

    assert SENSITIVE_PROMPT not in raw_audit
    assert SENSITIVE_RESPONSE not in raw_audit


def test_read_access_event_references_source_ledger(tmp_path):
    primary_path = tmp_path / "ledger.jsonl"
    primary = _primary_backend(primary_path)
    audit_backend, audit = _audit_emitter(tmp_path / "audit_ledger.jsonl")

    AuditedLedgerBackend(primary, audit_emitter=audit).audited_read_events(
        LedgerQuery(),
        actor=_reader(),
        reason="source ledger reference",
    )

    payload = _audit_events(audit_backend)[0].payload
    assert payload["source_ledger_id"] == str(primary_path)
    assert payload["source_path"] == str(primary_path)


def test_audited_read_returns_same_events_as_wrapped_backend(tmp_path):
    primary = _primary_backend(tmp_path / "ledger.jsonl", event_count=2)
    audit_backend, audit = _audit_emitter(tmp_path / "audit_ledger.jsonl")
    query = LedgerQuery(source_module="Warden")

    audited_events = AuditedLedgerBackend(primary, audit_emitter=audit).audited_read_events(
        query,
        actor=_reader(),
        reason="compare read results",
    )

    assert audited_events == primary.read_events(query)


def test_read_access_event_uses_audit_retention_class(tmp_path):
    primary = _primary_backend(tmp_path / "ledger.jsonl")
    audit_backend, audit = _audit_emitter(tmp_path / "audit_ledger.jsonl")

    AuditedLedgerBackend(primary, audit_emitter=audit).audited_read_events(
        LedgerQuery(),
        actor=_reader(),
        reason="retention check",
    )

    assert _audit_events(audit_backend)[0].policy.retention_class == RetentionClass.AUDIT_7Y


def test_read_access_event_records_tenant_filter_when_present(tmp_path):
    primary = _primary_backend(tmp_path / "ledger.jsonl")
    audit_backend, audit = _audit_emitter(tmp_path / "audit_ledger.jsonl")

    AuditedLedgerBackend(primary, audit_emitter=audit).audited_read_events(
        LedgerQuery(tenant_id="tenant-001"),
        actor=_reader(),
        reason="tenant filter",
    )

    assert _audit_events(audit_backend)[0].payload["query"]["tenant_id"] == "tenant-001"


def test_read_access_event_records_event_type_filter_when_present(tmp_path):
    primary = _primary_backend(tmp_path / "ledger.jsonl")
    audit_backend, audit = _audit_emitter(tmp_path / "audit_ledger.jsonl")

    AuditedLedgerBackend(primary, audit_emitter=audit).audited_read_events(
        LedgerQuery(event_types=[EventType.WARDEN_LLM_CALL_METADATA.value]),
        actor=_reader(),
        reason="event type filter",
    )

    assert _audit_events(audit_backend)[0].payload["query"]["event_types"] == [
        EventType.WARDEN_LLM_CALL_METADATA.value
    ]
