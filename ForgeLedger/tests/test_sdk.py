"""
Phase 5 tests:
1. SDK emits a valid event.
2. Invalid event is rejected.
3. Replay event is rejected.
4. Signature validation works.
5. Tenant boundary is enforced.
6. Bus payload matches library payload schema.
"""
import json

import pytest

from forgeledger.backend import LedgerQuery
from forgeledger.canonical_json import canonical_json
from forgeledger.hash_chain import attach_integrity
from forgeledger.jsonl_backend import JsonlBackend
from forgeledger.replay_protection import ReplayDetectedError, ReplayProtector
from forgeledger.schema import (
    LEDGER_VERSION,
    Actor,
    Decision,
    Evidence,
    EventType,
    Integrity,
    LedgerEvent,
    Policy,
    RetentionClass,
    SystemContext,
    Tenant,
    event_from_dict,
)
from forgeledger.sdk import (
    ForgeLedgerClient,
    InvalidEventError,
    TenantBoundaryViolationError,
)
from forgeledger.signing import sign_event, verify_signature
from forgeledger.validators import validate_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client(tmp_path, tenant_id: str = "t-001", **kwargs) -> ForgeLedgerClient:
    backend = JsonlBackend(tmp_path / f"{tenant_id}.jsonl")
    return ForgeLedgerClient(backend, tenant_id=tenant_id, **kwargs)


def _minimal_emit(client: ForgeLedgerClient, **overrides) -> dict:
    defaults = dict(
        event_type="concord.admission_decision",
        actor_id="partner.agent",
        decision_type="allow",
        reason="within_policy",
        risk_level="low",
    )
    defaults.update(overrides)
    return client.emit_event(**defaults)


def _make_bare_event(event_id: str = "evt-001") -> LedgerEvent:
    """Directly-constructed LedgerEvent for schema comparison (library path)."""
    return attach_integrity(
        LedgerEvent(
            event_id=event_id,
            ledger_version=LEDGER_VERSION,
            event_type=EventType.CONCORD_ADMISSION_DECISION,
            event_time="2026-04-29T10:00:00Z",
            actor=Actor(actor_type="system", actor_id="partner.agent", role="sdk_caller"),
            tenant=Tenant(tenant_id="t-001", customer_boundary="", data_residency="GLOBAL"),
            system_context=SystemContext(source_module="SDK", environment="unknown", deployment_id="sdk"),
            decision=Decision(decision_type="allow", reason="sdk_emission", risk_level="low"),
            evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=[]),
            policy=Policy(policy_id="sdk_default", policy_hash="none", retention_class=RetentionClass.OPERATIONAL_30D),
            control_tags=[],
            integrity=Integrity(previous_hash=None, event_hash=""),
        ),
        None,
    )


# ---------------------------------------------------------------------------
# Test 1: SDK emits a valid event
# ---------------------------------------------------------------------------

def test_sdk_emits_valid_event(tmp_path):
    client = _client(tmp_path)
    event_dict = _minimal_emit(client)

    event = event_from_dict(event_dict)
    errors = validate_event(event)
    assert errors == [], f"Validation errors: {errors}"


def test_sdk_event_is_persisted_to_backend(tmp_path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    client = ForgeLedgerClient(backend, tenant_id="t-001")
    _minimal_emit(client)

    events = backend.read_events(LedgerQuery())
    assert len(events) == 1
    assert events[0].actor.actor_id == "partner.agent"


def test_sdk_event_has_event_hash(tmp_path):
    client = _client(tmp_path)
    event_dict = _minimal_emit(client)
    assert event_dict["integrity"]["event_hash"]  # non-empty


def test_sdk_locks_tenant_id(tmp_path):
    client = _client(tmp_path, tenant_id="locked-tenant")
    event_dict = _minimal_emit(client)
    assert event_dict["tenant"]["tenant_id"] == "locked-tenant"


def test_sdk_event_dict_round_trips_via_event_from_dict(tmp_path):
    client = _client(tmp_path)
    event_dict = _minimal_emit(client)
    event = event_from_dict(event_dict)
    assert event.event_type == EventType.CONCORD_ADMISSION_DECISION
    assert event.tenant.tenant_id == "t-001"


# ---------------------------------------------------------------------------
# Test 2: Invalid event is rejected
# ---------------------------------------------------------------------------

def test_sdk_rejects_unknown_event_type(tmp_path):
    client = _client(tmp_path)
    with pytest.raises(InvalidEventError) as exc_info:
        client.emit_event(
            event_type="unknown.not.real",
            actor_id="agent",
            decision_type="allow",
        )
    assert "unknown event_type" in str(exc_info.value)


def test_sdk_rejects_empty_actor_id(tmp_path):
    client = _client(tmp_path)
    with pytest.raises(InvalidEventError) as exc_info:
        client.emit_event(
            event_type="concord.admission_decision",
            actor_id="",           # empty — schema violation
            decision_type="allow",
        )
    assert exc_info.value.errors  # non-empty error list


def test_sdk_rejects_unknown_retention_class(tmp_path):
    client = _client(tmp_path)
    with pytest.raises((InvalidEventError, ValueError)):
        client.emit_event(
            event_type="concord.admission_decision",
            actor_id="agent",
            decision_type="allow",
            retention_class="invalid_class",
        )


def test_invalid_event_error_carries_error_list(tmp_path):
    client = _client(tmp_path)
    try:
        client.emit_event(
            event_type="concord.admission_decision",
            actor_id="",
            decision_type="allow",
        )
        pytest.fail("Expected InvalidEventError")
    except InvalidEventError as exc:
        assert isinstance(exc.errors, list)
        assert len(exc.errors) > 0


# ---------------------------------------------------------------------------
# Test 3: Replay event is rejected
# ---------------------------------------------------------------------------

def test_replay_protector_raises_on_duplicate():
    protector = ReplayProtector()
    protector.check_and_register("evt-unique-001")
    with pytest.raises(ReplayDetectedError) as exc_info:
        protector.check_and_register("evt-unique-001")
    assert exc_info.value.event_id == "evt-unique-001"


def test_replay_protector_allows_different_ids():
    protector = ReplayProtector()
    protector.check_and_register("evt-001")
    protector.check_and_register("evt-002")  # should not raise


def test_sdk_replay_protection_blocks_duplicate_event_id(tmp_path):
    client = _client(tmp_path, replay_protection=True)
    # First emission with a known ID succeeds
    client.emit_event(
        event_type="concord.admission_decision",
        actor_id="agent",
        decision_type="allow",
        _event_id="fixed-evt-id-001",
    )
    # Second emission with the same ID is a replay
    with pytest.raises(ReplayDetectedError):
        client.emit_event(
            event_type="concord.admission_decision",
            actor_id="agent",
            decision_type="allow",
            _event_id="fixed-evt-id-001",
        )


def test_sdk_without_replay_protection_allows_duplicate_ids(tmp_path):
    client = _client(tmp_path, replay_protection=False)
    # Without replay protection, same ID can be emitted twice (no guard)
    client.emit_event(
        event_type="concord.admission_decision",
        actor_id="agent",
        decision_type="allow",
        _event_id="fixed-evt-id-002",
    )
    client.emit_event(
        event_type="concord.admission_decision",
        actor_id="agent",
        decision_type="allow",
        _event_id="fixed-evt-id-002",
    )


# ---------------------------------------------------------------------------
# Test 4: Signature validation
# ---------------------------------------------------------------------------

def test_sign_event_adds_signature():
    event = _make_bare_event()
    assert event.integrity.signature is None
    signed = sign_event(event, "my-secret")
    assert signed.integrity.signature is not None
    assert len(signed.integrity.signature) == 64  # SHA-256 hex


def test_verify_signature_correct_key():
    event = _make_bare_event()
    signed = sign_event(event, "correct-secret")
    assert verify_signature(signed, "correct-secret") is True


def test_verify_signature_wrong_key():
    event = _make_bare_event()
    signed = sign_event(event, "correct-secret")
    assert verify_signature(signed, "wrong-secret") is False


def test_verify_signature_unsigned_event():
    event = _make_bare_event()
    assert verify_signature(event, "any-key") is False


def test_signing_does_not_break_event_hash():
    """Signing adds a signature but must not invalidate the event_hash."""
    event = _make_bare_event()
    signed = sign_event(event, "secret")
    # event_hash was computed before signing; it should still verify correctly
    # since event_hash covers integrity.signature=None (cleared before hashing)
    # and signing sets signature AFTER hash computation
    assert signed.integrity.event_hash == event.integrity.event_hash


def test_sdk_signing_enabled_produces_signature(tmp_path):
    client = _client(
        tmp_path,
        secret_key="sdk-secret-key",
        signing_enabled=True,
    )
    event_dict = _minimal_emit(client)
    assert event_dict["integrity"]["signature"] is not None


def test_sdk_signing_disabled_produces_no_signature(tmp_path):
    client = _client(tmp_path, signing_enabled=False)
    event_dict = _minimal_emit(client)
    assert event_dict["integrity"]["signature"] is None


# ---------------------------------------------------------------------------
# Test 5: Tenant boundary is enforced
# ---------------------------------------------------------------------------

def test_sdk_emitted_events_always_carry_client_tenant_id(tmp_path):
    client = _client(tmp_path, tenant_id="msp-customer-alpha")
    for _ in range(3):
        event_dict = _minimal_emit(client)
        assert event_dict["tenant"]["tenant_id"] == "msp-customer-alpha"


def test_validate_incoming_accepts_correct_tenant(tmp_path):
    client = _client(tmp_path, tenant_id="t-001")
    event_dict = _minimal_emit(client)
    client.validate_incoming(event_dict)  # should not raise


def test_validate_incoming_rejects_wrong_tenant(tmp_path):
    client_a = _client(tmp_path, tenant_id="tenant-a")
    client_b = _client(tmp_path, tenant_id="tenant-b")

    event_from_b = client_b.emit_event(
        event_type="concord.admission_decision",
        actor_id="agent",
        decision_type="allow",
    )

    with pytest.raises(TenantBoundaryViolationError) as exc_info:
        client_a.validate_incoming(event_from_b)

    assert "tenant-b" in str(exc_info.value)
    assert "tenant-a" in str(exc_info.value)


def test_validate_incoming_rejects_missing_tenant(tmp_path):
    client = _client(tmp_path, tenant_id="t-001")
    with pytest.raises(TenantBoundaryViolationError):
        client.validate_incoming({})  # no tenant field


def test_two_clients_cannot_share_tenant_events(tmp_path):
    """Events from client A are invalid for client B's tenant boundary check."""
    client_a = _client(tmp_path, tenant_id="org-a")
    client_b = _client(tmp_path, tenant_id="org-b")

    event_a = _minimal_emit(client_a)
    event_b = _minimal_emit(client_b)

    client_a.validate_incoming(event_a)   # OK
    client_b.validate_incoming(event_b)   # OK

    with pytest.raises(TenantBoundaryViolationError):
        client_a.validate_incoming(event_b)  # cross-tenant: rejected

    with pytest.raises(TenantBoundaryViolationError):
        client_b.validate_incoming(event_a)  # cross-tenant: rejected


# ---------------------------------------------------------------------------
# Test 6: Bus payload matches library payload schema
# ---------------------------------------------------------------------------

def test_sdk_dict_has_same_top_level_keys_as_direct_event(tmp_path):
    client = _client(tmp_path)
    sdk_dict = _minimal_emit(client)

    direct_event = _make_bare_event()
    direct_dict = json.loads(canonical_json(direct_event))

    assert set(sdk_dict.keys()) == set(direct_dict.keys())


def test_sdk_dict_nested_structure_matches_direct_event(tmp_path):
    client = _client(tmp_path)
    sdk_dict = _minimal_emit(client)

    direct_event = _make_bare_event()
    direct_dict = json.loads(canonical_json(direct_event))

    for nested_key in ("actor", "tenant", "system_context", "decision",
                       "evidence", "policy", "integrity"):
        assert set(sdk_dict[nested_key].keys()) == set(direct_dict[nested_key].keys()), (
            f"Key mismatch in {nested_key!r}: "
            f"sdk={set(sdk_dict[nested_key].keys())} "
            f"direct={set(direct_dict[nested_key].keys())}"
        )


def test_sdk_event_deserializes_with_event_from_dict(tmp_path):
    client = _client(tmp_path)
    sdk_dict = _minimal_emit(client)
    event = event_from_dict(sdk_dict)
    assert validate_event(event) == []


def test_sdk_and_direct_paths_produce_same_canonical_json_structure(tmp_path):
    """
    Proves bus migration is a drop-in swap: the canonical JSON schema is
    identical whether an event is emitted via the SDK or via LedgerEmitter.
    Only values like event_id and event_time legitimately differ.
    """
    client = _client(tmp_path)
    sdk_dict = _minimal_emit(client)

    direct_event = _make_bare_event()
    direct_dict = json.loads(canonical_json(direct_event))

    # Schema-level check: same keys at every level
    def _key_tree(d: dict, prefix: str = "") -> set[str]:
        keys: set[str] = set()
        for k, v in d.items():
            full = f"{prefix}.{k}" if prefix else k
            keys.add(full)
            if isinstance(v, dict):
                keys |= _key_tree(v, full)
        return keys

    assert _key_tree(sdk_dict) == _key_tree(direct_dict)
