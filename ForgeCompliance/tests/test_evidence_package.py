"""
Phase 3 tests:
1. Package manifest is generated.
2. Package hash detects tampering.
3. Package contains chain validation report.
4. Package contains control coverage report.
5. Package contains evidence gap report.
6. Sensitive prompts/responses are redacted or hashed when policy requires.
7. Auditor README includes claim boundary.
"""
import dataclasses
import hashlib
import json

import pytest

from forgeledger.hash_chain import attach_integrity
from forgeledger.backend import LedgerQuery
from forgeledger.emitter import LedgerEmitter
from forgeledger.jsonl_backend import JsonlBackend
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
)
from forgecompliance.control_registry import ControlRegistry
from forgecompliance.evidence_package import EvidencePackageBuilder, decrypt_evidence_package


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    event_type: EventType = EventType.CONCORD_ADMISSION_DECISION,
    event_id: str = "evt-001",
    retention_class: RetentionClass = RetentionClass.AUDIT_7Y,
    legal_hold: bool = False,
    data_sensitivity: str | None = None,
    extra_payload: dict | None = None,
) -> LedgerEvent:
    payload: dict | None = None
    if data_sensitivity or extra_payload:
        payload = {}
        if data_sensitivity:
            payload["data_sensitivity"] = data_sensitivity
        if extra_payload:
            payload.update(extra_payload)
    return LedgerEvent(
        event_id=event_id,
        ledger_version=LEDGER_VERSION,
        event_type=event_type,
        event_time="2026-04-28T10:00:00Z",
        actor=Actor(actor_type="agent", actor_id="test.agent", role="test"),
        tenant=Tenant(tenant_id="t-001", customer_boundary="b", data_residency="NZ"),
        system_context=SystemContext(source_module="CONCORD", environment="local", deployment_id="test"),
        decision=Decision(decision_type="allow", reason="test", risk_level="low"),
        evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["FACT"]),
        policy=Policy(
            policy_id="p-001",
            policy_hash="abc",
            retention_class=retention_class,
            legal_hold=legal_hold,
        ),
        control_tags=[],
        integrity=Integrity(previous_hash=None, event_hash=""),
        payload=payload,
    )


def _chain(*events: LedgerEvent) -> list[LedgerEvent]:
    """Attach integrity to a sequence of events forming a proper chain."""
    result: list[LedgerEvent] = []
    prev: str | None = None
    for e in events:
        e = attach_integrity(e, prev)
        result.append(e)
        prev = e.integrity.event_hash
    return result


@pytest.fixture
def sample_events() -> list[LedgerEvent]:
    return _chain(
        _make_event(EventType.CONCORD_ADMISSION_DECISION, "e1"),
        _make_event(EventType.FORGEGATE_DECISION_RECORD, "e2"),
        _make_event(EventType.HUMAN_APPROVAL_DECISION, "e3"),
    )


@pytest.fixture
def registry() -> ControlRegistry:
    return ControlRegistry()


@pytest.fixture
def builder(sample_events, registry) -> EvidencePackageBuilder:
    return EvidencePackageBuilder(
        sample_events,
        framework_ids=["NZISM", "SOC2"],
        registry=registry,
    )


# ---------------------------------------------------------------------------
# Test 1: Package manifest is generated
# ---------------------------------------------------------------------------

def test_manifest_is_generated(builder, tmp_path):
    builder.build(tmp_path)
    manifest_file = tmp_path / "manifest.json"

    assert manifest_file.exists()
    data = json.loads(manifest_file.read_text())

    for key in ("package_id", "created_at", "framework_profiles", "event_count",
                "chain_valid", "open_gaps", "claim_boundary", "time_range"):
        assert key in data, f"manifest missing key: {key!r}"

    assert data["event_count"] == 3
    assert data["chain_valid"] is True


def test_manifest_framework_profiles_match(builder, tmp_path):
    builder.build(tmp_path)
    data = json.loads((tmp_path / "manifest.json").read_text())
    assert set(data["framework_profiles"]) == {"NZISM", "SOC2"}


def test_all_twelve_files_present(builder, tmp_path):
    builder.build(tmp_path)
    expected = {
        "manifest.json",
        "package_hash.txt",
        "ledger_slice.jsonl",
        "chain_validation_report.json",
        "control_coverage_report.json",
        "retention_policy_report.json",
        "legal_hold_report.json",
        "event_type_summary.csv",
        "evidence_gap_report.json",
        "human_review_decisions.json",
        "model_provider_boundary_report.json",
        "README_AUDITOR.md",
    }
    actual = {p.name for p in tmp_path.iterdir() if p.is_file()}
    assert expected == actual, f"Missing: {expected - actual}, Extra: {actual - expected}"


# ---------------------------------------------------------------------------
# Test 2: Package hash detects tampering
# ---------------------------------------------------------------------------

def test_package_hash_covers_all_files(builder, tmp_path):
    builder.build(tmp_path)
    pkg_hash = json.loads((tmp_path / "package_hash.txt").read_text())

    assert pkg_hash["algorithm"] == "sha256"
    covered = set(pkg_hash["files"].keys())
    all_files = {p.name for p in tmp_path.iterdir() if p.is_file() and p.name != "package_hash.txt"}
    assert covered == all_files


def test_package_hash_verifies_clean_package(builder, tmp_path):
    builder.build(tmp_path)
    pkg_hash = json.loads((tmp_path / "package_hash.txt").read_text())

    for fname, expected_hash in pkg_hash["files"].items():
        actual = hashlib.sha256((tmp_path / fname).read_bytes()).hexdigest()
        assert actual == expected_hash, f"Hash mismatch for {fname}"


def test_package_hash_detects_tampering(builder, tmp_path):
    builder.build(tmp_path)
    pkg_hash = json.loads((tmp_path / "package_hash.txt").read_text())

    # Tamper: flip chain_valid in chain_validation_report.json
    report_path = tmp_path / "chain_validation_report.json"
    original = json.loads(report_path.read_text())
    original["valid"] = not original["valid"]
    report_path.write_text(json.dumps(original))

    expected_hash = pkg_hash["files"]["chain_validation_report.json"]
    actual_hash = hashlib.sha256(report_path.read_bytes()).hexdigest()
    assert actual_hash != expected_hash


# ---------------------------------------------------------------------------
# Test 3: Package contains chain validation report
# ---------------------------------------------------------------------------

def test_chain_validation_report_present_and_valid(builder, tmp_path):
    builder.build(tmp_path)
    data = json.loads((tmp_path / "chain_validation_report.json").read_text())

    assert "valid" in data
    assert "total_events" in data
    assert data["valid"] is True
    assert data["total_events"] == 3


def test_chain_validation_report_detects_broken_chain(tmp_path, registry):
    events = _chain(
        _make_event(EventType.CONCORD_ADMISSION_DECISION, "e1"),
        _make_event(EventType.FORGEGATE_DECISION_RECORD, "e2"),
    )
    # Break the chain
    broken = dataclasses.replace(
        events[1],
        integrity=dataclasses.replace(events[1].integrity, previous_hash="bad_hash"),
    )
    builder = EvidencePackageBuilder([events[0], broken], ["NZISM"], registry)
    builder.build(tmp_path)

    data = json.loads((tmp_path / "chain_validation_report.json").read_text())
    assert data["valid"] is False
    assert data["error"] is not None


# ---------------------------------------------------------------------------
# Test 4: Package contains control coverage report
# ---------------------------------------------------------------------------

def test_control_coverage_report_present(builder, tmp_path):
    builder.build(tmp_path)
    data = json.loads((tmp_path / "control_coverage_report.json").read_text())

    assert "framework_reports" in data
    assert "NZISM" in data["framework_reports"]
    assert "SOC2" in data["framework_reports"]
    assert "total_events_analysed" in data


def test_control_coverage_report_event_count_matches(builder, tmp_path):
    builder.build(tmp_path)
    data = json.loads((tmp_path / "control_coverage_report.json").read_text())
    assert data["total_events_analysed"] == 3


# ---------------------------------------------------------------------------
# Test 5: Package contains evidence gap report
# ---------------------------------------------------------------------------

def test_evidence_gap_report_present(builder, tmp_path):
    builder.build(tmp_path)
    data = json.loads((tmp_path / "evidence_gap_report.json").read_text())

    assert "frameworks" in data
    assert "total_open_gaps" in data
    assert isinstance(data["total_open_gaps"], int)
    assert "NZISM" in data["frameworks"]
    assert "SOC2" in data["frameworks"]


def test_evidence_gap_report_open_gaps_matches_manifest(builder, tmp_path):
    builder.build(tmp_path)
    gap_data = json.loads((tmp_path / "evidence_gap_report.json").read_text())
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert gap_data["total_open_gaps"] == manifest["open_gaps"]


# ---------------------------------------------------------------------------
# Test 6: Sensitive prompts/responses are redacted or hashed
# ---------------------------------------------------------------------------

def test_health_identifiable_payload_is_hashed(tmp_path, registry):
    events = _chain(
        _make_event(
            EventType.AGENT_TOOL_CALL, "e1",
            data_sensitivity="health_identifiable",
        )
    )
    EvidencePackageBuilder(events, ["NZISM"], registry).build(tmp_path)

    lines = (tmp_path / "ledger_slice.jsonl").read_text().strip().splitlines()
    record = json.loads(lines[0])

    assert record["payload"] is not None
    redacted_val = record["payload"]["data_sensitivity"]
    assert redacted_val != "health_identifiable"
    assert "REDACTED" in redacted_val
    assert "sha256" in redacted_val


def test_pii_suspected_payload_is_hashed(tmp_path, registry):
    events = _chain(
        _make_event(
            EventType.WARDEN_LLM_CALL_METADATA, "e1",
            retention_class=RetentionClass.SUPPORT_1Y,
            data_sensitivity="llm_prompt_pii_suspected",
            extra_payload={"prompt": "What is the patient name?"},
        )
    )
    EvidencePackageBuilder(events, ["NZISM"], registry).build(tmp_path)

    lines = (tmp_path / "ledger_slice.jsonl").read_text().strip().splitlines()
    record = json.loads(lines[0])

    assert "REDACTED" in record["payload"]["data_sensitivity"]
    assert "REDACTED" in record["payload"]["prompt"]


def test_ephemeral_event_payload_is_stripped(tmp_path, registry):
    events = _chain(
        _make_event(
            EventType.WARDEN_LLM_CALL_METADATA, "e1",
            retention_class=RetentionClass.EPHEMERAL,
            data_sensitivity="llm_prompt_pii_suspected",
        )
    )
    EvidencePackageBuilder(events, ["NZISM"], registry).build(tmp_path)

    lines = (tmp_path / "ledger_slice.jsonl").read_text().strip().splitlines()
    record = json.loads(lines[0])
    assert record["payload"] is None


def test_non_sensitive_event_payload_passthrough(tmp_path, registry):
    events = _chain(
        _make_event(
            EventType.CONCORD_ADMISSION_DECISION, "e1",
            extra_payload={"context": "standard"},
        )
    )
    EvidencePackageBuilder(events, ["NZISM"], registry).build(tmp_path)

    lines = (tmp_path / "ledger_slice.jsonl").read_text().strip().splitlines()
    record = json.loads(lines[0])
    assert record["payload"] == {"context": "standard"}


# ---------------------------------------------------------------------------
# Test 7: Auditor README includes claim boundary
# ---------------------------------------------------------------------------

def test_readme_contains_claim_boundary(builder, tmp_path):
    builder.build(tmp_path)
    readme = (tmp_path / "README_AUDITOR.md").read_text()
    assert "Evidence support only. Not a compliance certification." in readme


def test_readme_avoids_compliance_overclaiming(builder, tmp_path):
    builder.build(tmp_path)
    readme = (tmp_path / "README_AUDITOR.md").read_text()
    assert "not a certification" in readme.lower()


def test_readme_lists_all_package_files(builder, tmp_path):
    builder.build(tmp_path)
    readme = (tmp_path / "README_AUDITOR.md").read_text()
    for fname in (
        "manifest.json", "package_hash.txt", "ledger_slice.jsonl",
        "chain_validation_report.json", "control_coverage_report.json",
        "evidence_gap_report.json",
    ):
        assert fname in readme, f"README missing reference to {fname}"


def test_readme_explains_verification(builder, tmp_path):
    builder.build(tmp_path)
    readme = (tmp_path / "README_AUDITOR.md").read_text()
    assert "package_hash.txt" in readme
    assert "sha256" in readme.lower()


# ---------------------------------------------------------------------------
# Phase 7d: Export audit events
# ---------------------------------------------------------------------------

def _audit_emitter(tmp_path):
    backend = JsonlBackend(tmp_path / "audit_ledger.jsonl")
    return backend, LedgerEmitter(backend)


def _audit_events(backend: JsonlBackend):
    return backend.read_events(LedgerQuery(max_results=100))


def test_build_emits_evidence_package_exported_event_to_audit_emitter(sample_events, registry, tmp_path):
    audit_backend, audit = _audit_emitter(tmp_path)
    EvidencePackageBuilder(sample_events, ["NZISM"], registry, audit_emitter=audit).build(tmp_path / "pkg")

    assert _audit_events(audit_backend)[0].event_type == EventType.LEDGER_EVIDENCE_PACKAGE_EXPORTED


def test_evidence_package_exported_event_contains_package_id(sample_events, registry, tmp_path):
    audit_backend, audit = _audit_emitter(tmp_path)
    EvidencePackageBuilder(
        sample_events,
        ["NZISM"],
        registry,
        package_id="pkg-001",
        audit_emitter=audit,
    ).build(tmp_path / "pkg")

    assert _audit_events(audit_backend)[0].payload["package_id"] == "pkg-001"


def test_evidence_package_exported_event_contains_package_hash(sample_events, registry, tmp_path):
    audit_backend, audit = _audit_emitter(tmp_path)
    EvidencePackageBuilder(sample_events, ["NZISM"], registry, audit_emitter=audit).build(tmp_path / "pkg")

    assert len(_audit_events(audit_backend)[0].payload["package_hash"]) == 64


def test_evidence_package_exported_event_contains_event_count(sample_events, registry, tmp_path):
    audit_backend, audit = _audit_emitter(tmp_path)
    EvidencePackageBuilder(sample_events, ["NZISM"], registry, audit_emitter=audit).build(tmp_path / "pkg")

    assert _audit_events(audit_backend)[0].payload["event_count"] == len(sample_events)


def test_evidence_package_exported_event_records_encryption_status(sample_events, registry, tmp_path):
    audit_backend, audit = _audit_emitter(tmp_path)
    EvidencePackageBuilder(
        sample_events,
        ["NZISM"],
        registry,
        audit_emitter=audit,
        encryption_key="secret",
    ).build(tmp_path / "pkg")

    assert _audit_events(audit_backend)[0].payload["encrypted"] is True


# ---------------------------------------------------------------------------
# Phase 7d: Evidence package encryption
# ---------------------------------------------------------------------------

def test_encrypted_package_content_files_are_not_plaintext_readable(builder, tmp_path):
    builder._encryption_key = "secret"
    builder.build(tmp_path)

    ledger_ciphertext = (tmp_path / "ledger_slice.jsonl.enc").read_bytes()
    assert b"concord.admission_decision" not in ledger_ciphertext
    assert not (tmp_path / "ledger_slice.jsonl").exists()


def test_manifest_records_encrypted_true_when_key_provided(sample_events, registry, tmp_path):
    EvidencePackageBuilder(sample_events, ["NZISM"], registry, encryption_key="secret").build(tmp_path)

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["encrypted"] is True
    assert manifest["encryption_algorithm"] == "AES-256-GCM"
    assert "ledger_slice.jsonl.enc" in manifest["files"]


def test_manifest_records_encrypted_false_when_no_key(builder, tmp_path):
    builder.build(tmp_path)

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["encrypted"] is False


def test_decrypt_package_with_correct_key_restores_all_files(sample_events, registry, tmp_path):
    EvidencePackageBuilder(sample_events, ["NZISM"], registry, encryption_key="secret").build(tmp_path)

    restored = decrypt_evidence_package(tmp_path, "secret")

    restored_names = {p.name for p in restored}
    assert "ledger_slice.jsonl" in restored_names
    assert "package_hash.txt" in restored_names
    assert "concord.admission_decision" in (tmp_path / "ledger_slice.jsonl").read_text()


def test_decrypt_package_with_wrong_key_raises(sample_events, registry, tmp_path):
    EvidencePackageBuilder(sample_events, ["NZISM"], registry, encryption_key="secret").build(tmp_path)

    with pytest.raises(ValueError, match="decryption failed"):
        decrypt_evidence_package(tmp_path, "wrong-secret")


def test_package_hash_computed_over_ciphertext_not_plaintext(sample_events, registry, tmp_path):
    EvidencePackageBuilder(sample_events, ["NZISM"], registry, encryption_key="secret").build(tmp_path)

    decrypted_hash_files = decrypt_evidence_package(tmp_path, "secret")
    package_hash = json.loads((tmp_path / "package_hash.txt").read_text())
    ciphertext_hash = hashlib.sha256((tmp_path / "ledger_slice.jsonl.enc").read_bytes()).hexdigest()
    plaintext_hash = hashlib.sha256((tmp_path / "ledger_slice.jsonl").read_bytes()).hexdigest()

    assert package_hash["files"]["ledger_slice.jsonl.enc"] == ciphertext_hash
    assert package_hash["files"]["ledger_slice.jsonl.enc"] != plaintext_hash
    assert any(p.name == "package_hash.txt" for p in decrypted_hash_files)
