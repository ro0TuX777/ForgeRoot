"""Phase 8g captured/representative subsystem fixture validation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from forgecompliance.control_registry import ControlRegistry
from forgecompliance.evidence_package import EvidencePackageBuilder
from forgeledger.backend import LedgerQuery
from forgeledger.hash_chain import verify_chain
from forgeledger.jsonl_backend import JsonlBackend
from forgeledger.schema import EventType
from forgeledger.validators import validate_event
from integrations._common import (
    normalize_azul_output,
    normalize_concord_output,
    normalize_forgegate_output,
    normalize_warden_output,
)
from integrations.azul_ledger_adapter import AzulLedgerAdapter
from integrations.concord_ledger_adapter import ConcordLedgerAdapter
from integrations.forgegate_ledger_adapter import ForgeGateLedgerAdapter
from integrations.warden_ledger_adapter import WardenLedgerAdapter


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "integrations" / "fixtures"
RAW_PROMPT = "Customer Jane Doe NZBN 9429040000000 needs payroll help"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _fixture_payload(raw: dict) -> dict:
    data = dict(raw)
    data.pop("fixture_provenance", None)
    data.pop("subsystem", None)
    return data


def _emit_fixture_events(backend: JsonlBackend):
    events = []
    concord = ConcordLedgerAdapter(backend)
    forgegate = ForgeGateLedgerAdapter(backend)
    warden = WardenLedgerAdapter(backend)
    azul = AzulLedgerAdapter(backend)

    events.append(concord.emit_admission_result(
        normalize_concord_output(_fixture_payload(_fixture("concord_admission_allow.json")))
    ))
    events.append(concord.emit_admission_result(
        normalize_concord_output(_fixture_payload(_fixture("concord_admission_deny.json")))
    ))
    events.append(forgegate.emit_policy_evaluation_result(
        normalize_forgegate_output(_fixture_payload(_fixture("forgegate_policy_review.json")))
    ))
    events.append(forgegate.emit_evaluation_result(
        normalize_forgegate_output(_fixture_payload(_fixture("forgegate_decision_allow.json")))
    ))
    events.append(warden.emit_call_record(
        normalize_warden_output(_fixture_payload(_fixture("warden_llm_call_sensitive.json")))
    ))
    events.append(azul.emit_verdict_record(
        normalize_azul_output(_fixture_payload(_fixture("azul_verdict_summary.json")))
    ))
    return events


def test_concord_captured_allow_output_normalizes():
    record = normalize_concord_output(_fixture_payload(_fixture("concord_admission_allow.json")))

    assert record.agent_id == "agent.research.assistant"
    assert record.admitted is True


def test_concord_captured_deny_output_normalizes():
    record = normalize_concord_output(_fixture_payload(_fixture("concord_admission_deny.json")))

    assert record.admitted is False
    assert record.risk_level == "high"


def test_forgegate_captured_review_output_normalizes():
    record = normalize_forgegate_output(_fixture_payload(_fixture("forgegate_policy_review.json")))

    assert record.decision_type == "review"
    assert record.blast_radius_score == 0.74


def test_forgegate_captured_allow_output_normalizes():
    record = normalize_forgegate_output(_fixture_payload(_fixture("forgegate_decision_allow.json")))

    assert record.decision_type == "allow"
    assert record.evidence_gaps == []


def test_warden_captured_sensitive_output_normalizes():
    record = normalize_warden_output(_fixture_payload(_fixture("warden_llm_call_sensitive.json")))

    assert record.prompt == RAW_PROMPT
    assert record.data_sensitivity == "llm_prompt_pii_suspected"
    assert record.model_provider == "local"


def test_warden_captured_sensitive_output_redacts_before_storage(tmp_path):
    path = tmp_path / "ledger.jsonl"
    backend = JsonlBackend(path)
    record = normalize_warden_output(_fixture_payload(_fixture("warden_llm_call_sensitive.json")))

    event = WardenLedgerAdapter(backend).emit_call_record(record)

    assert event.payload["prompt"].startswith("[REDACTED:sha256:")
    assert event.payload["response"].startswith("[REDACTED:sha256:")
    assert RAW_PROMPT not in path.read_text(encoding="utf-8")


def test_azul_captured_verdict_output_normalizes():
    record = normalize_azul_output(_fixture_payload(_fixture("azul_verdict_summary.json")))

    assert record.verdict == "deny"
    assert record.flagged_categories == ["unsafe_instruction"]


def test_all_captured_outputs_emit_valid_ledger_events(tmp_path):
    events = _emit_fixture_events(JsonlBackend(tmp_path / "ledger.jsonl"))

    assert len(events) == 6
    assert all(validate_event(event) == [] for event in events)


def test_schema_drift_missing_required_field_fails_loudly():
    raw = _fixture_payload(_fixture("warden_llm_call_sensitive.json"))
    raw.pop("prompt")

    with pytest.raises(ValueError, match="missing required field: prompt"):
        normalize_warden_output(raw)


def test_unknown_extra_fields_preserved_or_ignored_by_policy():
    raw = _fixture_payload(_fixture("concord_admission_allow.json"))
    raw["unexpected_runtime_field"] = {"opaque": True}

    record = normalize_concord_output(raw)

    assert not hasattr(record, "unexpected_runtime_field")
    assert record.agent_id == "agent.research.assistant"


def test_runtime_fixture_event_chain_valid(tmp_path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    _emit_fixture_events(backend)

    events = backend.read_events(LedgerQuery(max_results=100))
    report = verify_chain(events)

    assert report.valid is True
    assert report.total_events == 6


def test_runtime_fixture_evidence_package_builds(tmp_path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    _emit_fixture_events(backend)
    events = backend.read_events(LedgerQuery(max_results=100))

    manifest = EvidencePackageBuilder(
        events,
        ["NZISM", "SOC2"],
        ControlRegistry(),
        package_id="fixture-runtime-package",
    ).build(tmp_path / "evidence_package")

    assert manifest["event_count"] == 6
    assert (tmp_path / "evidence_package" / "manifest.json").exists()


@pytest.mark.skip(reason="live CONCORD module smoke test is optional and disabled by default")
def test_live_concord_to_ledger_smoke():
    pass


@pytest.mark.skip(reason="live ForgeGate module smoke test is optional and disabled by default")
def test_live_forgegate_to_ledger_smoke():
    pass


@pytest.mark.skip(reason="live Warden module smoke test is optional and disabled by default")
def test_live_warden_to_ledger_smoke():
    pass


@pytest.mark.skip(reason="live Azul module smoke test is optional and disabled by default")
def test_live_azul_to_ledger_smoke():
    pass
