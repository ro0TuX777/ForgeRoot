"""
Phase 6 tests:
1. Demo query generates the expected ledger event sequence.
2. High-impact design triggers human review.
3. Control coverage is generated across framework profiles.
4. Evidence package is fully exported from the demo.
5. Sensitive prompt is not present in raw form when policy blocks it.
"""
import json
import inspect

import pytest

from forgeledger.schema import EventType
from forgeledger.validators import validate_event
from demo.governed_agent_demo import (
    SCENARIO_QUERY,
    DemoResult,
    _emit_demo_events,
    run_demo,
)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def demo_result(tmp_path_factory) -> DemoResult:
    """Run the demo once and share the result across all tests in this module."""
    out = tmp_path_factory.mktemp("demo_run")
    return run_demo(out)


# ---------------------------------------------------------------------------
# Test 1: Demo query generates ledger events
# ---------------------------------------------------------------------------

def test_demo_produces_exactly_nine_events(demo_result):
    assert len(demo_result.events) == 9


def test_demo_includes_all_required_event_types(demo_result):
    types = {e.event_type for e in demo_result.events}
    required = {
        EventType.CONCORD_ADMISSION_DECISION,
        EventType.FORGEGATE_POLICY_EVALUATION,
        EventType.WARDEN_LLM_CALL_METADATA,
        EventType.AGENT_TOOL_CALL,
        EventType.AZUL_VERDICT_SUMMARY,
        EventType.FORGEGATE_DECISION_RECORD,
        EventType.AGENT_HUMAN_REVIEW_REQUIRED,
        EventType.HUMAN_APPROVAL_DECISION,
    }
    missing = required - types
    assert not missing, f"Missing event types: {missing}"


def test_all_demo_events_pass_schema_validation(demo_result):
    for event in demo_result.events:
        errors = validate_event(event)
        assert errors == [], f"Event {event.event_id} invalid: {errors}"


def test_demo_chain_is_valid(demo_result):
    assert demo_result.chain_report["valid"] is True
    assert demo_result.chain_report["total_events"] == len(demo_result.events)


def test_demo_events_form_contiguous_chain(demo_result):
    events = demo_result.events
    for i in range(1, len(events)):
        assert events[i].integrity.previous_hash == events[i - 1].integrity.event_hash, (
            f"Chain broken between event {i-1} and {i}"
        )


def test_adapter_emitted_demo_events_pass_schema_validation(demo_result):
    adapter_event_types = {
        EventType.CONCORD_ADMISSION_DECISION,
        EventType.FORGEGATE_POLICY_EVALUATION,
        EventType.WARDEN_LLM_CALL_METADATA,
        EventType.AZUL_VERDICT_SUMMARY,
        EventType.FORGEGATE_DECISION_RECORD,
    }
    for event in demo_result.events:
        if event.event_type in adapter_event_types:
            assert validate_event(event) == []


def test_no_manual_evt_calls_for_subsystem_adapter_events():
    source = inspect.getsource(_emit_demo_events)
    for event_type in (
        "CONCORD_ADMISSION_DECISION",
        "FORGEGATE_POLICY_EVALUATION",
        "WARDEN_LLM_CALL_METADATA",
        "AZUL_VERDICT_SUMMARY",
        "FORGEGATE_DECISION_RECORD",
    ):
        assert f"event_type=EventType.{event_type}" not in source


def test_scenario_query_is_embedded_in_summary(demo_result):
    assert SCENARIO_QUERY in demo_result.scenario_summary["query"]


# ---------------------------------------------------------------------------
# Test 2: High-impact design triggers human review
# ---------------------------------------------------------------------------

def test_human_review_is_triggered(demo_result):
    assert demo_result.scenario_summary["human_review_triggered"] is True


def test_human_approval_is_recorded(demo_result):
    assert demo_result.scenario_summary["human_approval_received"] is True


def test_high_blast_radius_forgegate_event_is_review(demo_result):
    """The ForgeGate decision that triggers escalation must have decision_type='review'."""
    review_events = [
        e for e in demo_result.events
        if e.event_type == EventType.FORGEGATE_DECISION_RECORD
        and e.decision.decision_type == "review"
    ]
    assert review_events, "No ForgeGate 'review' decision found in event sequence"
    assert any(
        gap.gap_type == "high_blast_radius"
        for e in review_events
        for gap in e.evidence.evidence_gaps
    ), "ForgeGate review event should carry a high_blast_radius evidence gap"


def test_human_approval_actor_is_human(demo_result):
    human_approvals = [
        e for e in demo_result.events
        if e.event_type == EventType.HUMAN_APPROVAL_DECISION
    ]
    assert human_approvals
    for e in human_approvals:
        assert e.actor.actor_type == "human"
        assert e.decision.decision_type == "allow"


def test_final_forgegate_decision_is_allow(demo_result):
    """After human approval the last ForgeGate record must be 'allow'."""
    forgegate_events = [
        e for e in demo_result.events
        if e.event_type == EventType.FORGEGATE_DECISION_RECORD
    ]
    assert forgegate_events[-1].decision.decision_type == "allow"


# ---------------------------------------------------------------------------
# Test 3: Control coverage is generated
# ---------------------------------------------------------------------------

def test_coverage_report_contains_nzism(demo_result):
    assert "NZISM" in demo_result.coverage_report.get("framework_reports", {})


def test_coverage_report_contains_soc2(demo_result):
    assert "SOC2" in demo_result.coverage_report.get("framework_reports", {})


def test_nzism_has_at_least_one_covered_control(demo_result):
    nzism = demo_result.coverage_report["framework_reports"]["NZISM"]
    assert nzism["covered"] >= 1, (
        f"Expected at least one NZISM control covered, got {nzism['covered']}"
    )


def test_control_tags_are_emitted_on_events(demo_result):
    events_with_tags = [e for e in demo_result.events if e.control_tags]
    assert events_with_tags, "No events emitted with control tags"
    all_tags = {tag for e in events_with_tags for tag in e.control_tags}
    assert any("NZISM" in tag for tag in all_tags)
    assert any("SOC2" in tag for tag in all_tags)


def test_scenario_summary_lists_covered_controls(demo_result):
    covered = demo_result.scenario_summary["covered_controls_per_framework"]
    assert "NZISM" in covered
    assert covered["NZISM"] >= 1


# ---------------------------------------------------------------------------
# Test 4: Evidence package is fully exported
# ---------------------------------------------------------------------------

def test_evidence_package_directory_exists(demo_result):
    assert demo_result.evidence_package_dir.exists()
    assert demo_result.evidence_package_dir.is_dir()


def test_evidence_package_contains_all_twelve_files(demo_result):
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
    actual = {p.name for p in demo_result.evidence_package_dir.iterdir() if p.is_file()}
    missing = expected - actual
    assert not missing, f"Missing evidence package files: {missing}"


def test_manifest_chain_valid(demo_result):
    manifest = demo_result.manifest
    assert manifest["chain_valid"] is True


def test_manifest_event_count_matches(demo_result):
    assert demo_result.manifest["event_count"] == len(demo_result.events)


def test_manifest_contains_claim_boundary(demo_result):
    assert "not a certification" in demo_result.manifest["claim_boundary"].lower()


def test_chain_validation_report_in_package(demo_result):
    report_path = demo_result.evidence_package_dir / "chain_validation_report.json"
    data = json.loads(report_path.read_text())
    assert data["valid"] is True
    assert data["total_events"] == len(demo_result.events)


def test_human_review_decisions_file_has_events(demo_result):
    path = demo_result.evidence_package_dir / "human_review_decisions.json"
    data = json.loads(path.read_text())
    assert data["total_human_review_events"] >= 2  # review_required + approval


def test_model_provider_boundary_report_has_llm_event(demo_result):
    path = demo_result.evidence_package_dir / "model_provider_boundary_report.json"
    data = json.loads(path.read_text())
    assert data["total_llm_boundary_events"] >= 1
    assert data["events"][0]["model_provider"] == "anthropic"


def test_readme_contains_claim_boundary(demo_result):
    readme = (demo_result.evidence_package_dir / "README_AUDITOR.md").read_text()
    assert "Evidence support only. Not a compliance certification." in readme


# ---------------------------------------------------------------------------
# Test 5: Sensitive prompt is not raw in ledger slice
# ---------------------------------------------------------------------------

def test_llm_prompt_pii_is_redacted_in_ledger_slice(demo_result):
    """The Warden LLM call event has data_sensitivity=llm_prompt_pii_suspected.
    The evidence package builder must redact it in ledger_slice.jsonl."""
    slice_path = demo_result.evidence_package_dir / "ledger_slice.jsonl"
    lines = slice_path.read_text().strip().splitlines()

    warden_line = next(
        (l for l in lines if '"warden.llm_call_metadata"' in l),
        None,
    )
    assert warden_line is not None, "Warden LLM event not found in ledger_slice.jsonl"

    record = json.loads(warden_line)
    payload = record.get("payload") or {}

    # The raw sensitivity value must not appear
    assert payload.get("data_sensitivity") != "llm_prompt_pii_suspected", (
        "data_sensitivity was not redacted in ledger_slice.jsonl"
    )
    assert "REDACTED" in str(payload.get("data_sensitivity", "")), (
        "Expected [REDACTED:sha256:...] marker in data_sensitivity field"
    )


def test_raw_prompt_text_is_redacted_in_ledger_slice(demo_result):
    """The literal user query must not appear in raw form in the ledger slice."""
    slice_path = demo_result.evidence_package_dir / "ledger_slice.jsonl"
    lines = slice_path.read_text().strip().splitlines()

    warden_line = next(
        (l for l in lines if '"warden.llm_call_metadata"' in l),
        None,
    )
    assert warden_line is not None
    record = json.loads(warden_line)
    payload = record.get("payload") or {}

    # The raw query text must not be present as the prompt value
    raw_query = "Design a 2PB local backup environment"
    assert raw_query not in str(payload.get("prompt", "")), (
        "Raw prompt text found in ledger slice — should have been redacted"
    )
    assert "REDACTED" in str(payload.get("prompt", "")), (
        "Expected [REDACTED:sha256:...] in prompt field"
    )


def test_scenario_query_absent_from_raw_ledger(demo_result):
    ledger_path = demo_result.evidence_package_dir.parent / "ledger.jsonl"
    assert SCENARIO_QUERY not in ledger_path.read_text(encoding="utf-8")


def test_stored_warden_prompt_is_redacted_before_export(demo_result):
    warden = next(e for e in demo_result.events if e.event_type == EventType.WARDEN_LLM_CALL_METADATA)
    assert str(warden.payload.get("prompt", "")).startswith("[REDACTED:sha256:")


def test_non_sensitive_events_are_not_redacted(demo_result):
    """CONCORD admission event has no sensitive payload — must not be altered."""
    slice_path = demo_result.evidence_package_dir / "ledger_slice.jsonl"
    lines = slice_path.read_text().strip().splitlines()

    concord_line = next(
        (l for l in lines if '"concord.admission_decision"' in l),
        None,
    )
    assert concord_line is not None
    record = json.loads(concord_line)
    # CONCORD event has no payload — must be null, not redacted garbage
    assert record["payload"] is None


def test_evidence_gap_report_avoids_compliance_overclaiming(demo_result):
    """The gap report must never claim the system is compliant."""
    gap_path = demo_result.evidence_package_dir / "evidence_gap_report.json"
    content = gap_path.read_text().lower()
    assert "certified" not in content
    assert "compliant" not in content or "not" in content
