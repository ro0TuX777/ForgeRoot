"""Phase 8c key management abstraction tests."""
import json

import pytest

from forgeledger.backend import LedgerQuery
from forgeledger.checkpoint import CheckpointManager
from forgeledger.emitter import LedgerEmitter
from forgeledger.hash_chain import attach_integrity
from forgeledger.jsonl_backend import JsonlBackend
from forgeledger.key_management import (
    EnvironmentKeyProvider,
    FileKeyProvider,
    HsmKeyProvider,
    KeyMaterial,
    KmsKeyProvider,
    StaticKeyProvider,
)
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
from forgeledger.signing import verify_signature


SECRET = "phase-8c-super-secret"


def _actor() -> Actor:
    return Actor(actor_type="system", actor_id="key-test", role="tester")


def _tenant() -> Tenant:
    return Tenant(tenant_id="tenant-001", customer_boundary="boundary", data_residency="NZ")


def _system_context() -> SystemContext:
    return SystemContext(source_module="ForgeLedger", environment="local", deployment_id="test")


def _decision() -> Decision:
    return Decision(decision_type="allow", reason="key_provider_test", risk_level="low")


def _evidence() -> Evidence:
    return Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["TEST"])


def _make_event(event_id: str = "evt-001") -> LedgerEvent:
    return LedgerEvent(
        event_id=event_id,
        ledger_version=LEDGER_VERSION,
        event_type=EventType.CONCORD_ADMISSION_DECISION,
        event_time="2026-04-30T00:00:00+00:00",
        actor=_actor(),
        tenant=_tenant(),
        system_context=_system_context(),
        decision=_decision(),
        evidence=_evidence(),
        policy=Policy(policy_id="p-001", policy_hash="abc123", retention_class=RetentionClass.AUDIT_7Y),
        control_tags=["NZISM.LOGGING"],
        integrity=Integrity(previous_hash=None, event_hash=""),
    )


def _make_chain(n: int) -> list[LedgerEvent]:
    events: list[LedgerEvent] = []
    previous_hash = None
    for index in range(n):
        event = attach_integrity(_make_event(f"evt-{index:03d}"), previous_hash)
        events.append(event)
        previous_hash = event.integrity.event_hash
    return events


def _emit_with_provider(path, provider: StaticKeyProvider):
    backend = JsonlBackend(path)
    emitter = LedgerEmitter(backend, key_provider=provider)
    emitter.emit(
        event_type=EventType.CONCORD_ADMISSION_DECISION,
        actor=_actor(),
        tenant=_tenant(),
        system_context=_system_context(),
        decision=_decision(),
        evidence=_evidence(),
        policy_id="policy-001",
        policy_hash="hash-001",
        control_tags=["NZISM.LOGGING"],
        payload={"message": "signed via provider"},
    )
    return backend


def test_static_key_provider_returns_key_material():
    provider = StaticKeyProvider(secret=SECRET, key_id="static-001")

    material = provider.get_signing_key()

    assert material.key_id == "static-001"
    assert material.algorithm == "HMAC-SHA256"
    assert material.secret == SECRET.encode("utf-8")


def test_environment_key_provider_reads_secret(monkeypatch):
    monkeypatch.setenv("FORGELEDGER_SIGNING_KEY", SECRET)
    provider = EnvironmentKeyProvider("FORGELEDGER_SIGNING_KEY", key_id="env-001")

    material = provider.get_signing_key()

    assert material.key_id == "env-001"
    assert material.secret == SECRET.encode("utf-8")


def test_environment_key_provider_missing_env_raises(monkeypatch):
    monkeypatch.delenv("FORGELEDGER_SIGNING_KEY", raising=False)
    provider = EnvironmentKeyProvider("FORGELEDGER_SIGNING_KEY", key_id="env-001")

    with pytest.raises(KeyError):
        provider.get_signing_key()


def test_file_key_provider_reads_secret(tmp_path):
    key_path = tmp_path / "signing.key"
    key_path.write_text(SECRET + "\n", encoding="utf-8")
    provider = FileKeyProvider(key_path, key_id="file-001")

    material = provider.get_signing_key()

    assert material.key_id == "file-001"
    assert material.secret == SECRET.encode("utf-8")


def test_file_key_provider_missing_file_raises(tmp_path):
    provider = FileKeyProvider(tmp_path / "missing.key", key_id="file-001")

    with pytest.raises(FileNotFoundError):
        provider.get_signing_key()


def test_kms_key_provider_stub_not_implemented():
    with pytest.raises(NotImplementedError):
        KmsKeyProvider().get_signing_key("kms-001")


def test_hsm_key_provider_stub_not_implemented():
    with pytest.raises(NotImplementedError):
        HsmKeyProvider().get_signing_key("hsm-001")


def test_emitter_uses_key_provider_for_signature(tmp_path):
    provider = StaticKeyProvider(secret=SECRET, key_id="provider-001")
    backend = _emit_with_provider(tmp_path / "ledger.jsonl", provider)
    event = backend.read_events(LedgerQuery())[0]

    assert event.integrity.signature is not None
    assert event.integrity.signing_key_id == "provider-001"
    assert verify_signature(event, SECRET) is True


def test_checkpoint_uses_key_provider_for_signature(tmp_path):
    provider = StaticKeyProvider(secret=SECRET, key_id="checkpoint-key-001")
    manager = CheckpointManager(tmp_path / "checkpoints.jsonl", interval=3, key_provider=provider)

    checkpoint = manager.maybe_checkpoint(_make_chain(3))

    assert checkpoint is not None
    assert checkpoint.signature is not None
    assert checkpoint.key_id == "checkpoint-key-001"


def test_key_id_recorded_without_secret_leakage(tmp_path):
    provider = StaticKeyProvider(secret=SECRET, key_id="provider-001")
    _emit_with_provider(tmp_path / "ledger.jsonl", provider)

    raw = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8")
    stored = json.loads(raw)

    assert stored["integrity"]["signing_key_id"] == "provider-001"
    assert SECRET not in raw


def test_secret_value_not_present_in_ledger_jsonl(tmp_path):
    provider = StaticKeyProvider(secret=SECRET, key_id="provider-001")
    _emit_with_provider(tmp_path / "ledger.jsonl", provider)

    assert SECRET not in (tmp_path / "ledger.jsonl").read_text(encoding="utf-8")


def test_secret_value_not_present_in_checkpoint_jsonl(tmp_path):
    provider = StaticKeyProvider(secret=SECRET, key_id="checkpoint-key-001")
    manager = CheckpointManager(tmp_path / "checkpoints.jsonl", interval=3, key_provider=provider)
    manager.maybe_checkpoint(_make_chain(3))

    raw = (tmp_path / "checkpoints.jsonl").read_text(encoding="utf-8")
    stored = json.loads(raw)
    assert stored["key_id"] == "checkpoint-key-001"
    assert SECRET not in raw


def test_provider_rejects_unsupported_algorithm():
    with pytest.raises(ValueError):
        KeyMaterial(key_id="bad", algorithm="RSA", secret=b"secret")


def test_key_material_requires_non_empty_secret():
    with pytest.raises(ValueError):
        KeyMaterial(key_id="empty", algorithm="HMAC-SHA256", secret=b"")


def test_both_secret_key_and_key_provider_raise_clear_error(tmp_path):
    provider = StaticKeyProvider(secret=SECRET, key_id="provider-001")

    with pytest.raises(ValueError, match="provide either secret_key or key_provider"):
        LedgerEmitter(JsonlBackend(tmp_path / "ledger.jsonl"), secret_key=SECRET, key_provider=provider)

    with pytest.raises(ValueError, match="provide either secret_key or key_provider"):
        CheckpointManager(tmp_path / "checkpoints.jsonl", interval=3, secret_key=SECRET, key_provider=provider)


def test_environment_key_provider_trims_newline_or_preserves_expected_bytes_by_policy(monkeypatch):
    monkeypatch.setenv("FORGELEDGER_SIGNING_KEY", SECRET + "\n")
    provider = EnvironmentKeyProvider("FORGELEDGER_SIGNING_KEY", key_id="env-001")

    assert provider.get_signing_key().secret == SECRET.encode("utf-8")
