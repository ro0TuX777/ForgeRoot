"""Phase 8f control mapping governance tests."""
from dataclasses import asdict

from forgecompliance.control_registry import ControlRegistry
from forgecompliance.mapping_governance import (
    CLAIM_BOUNDARY,
    MappingProvenance,
    active_mappings,
    apply_customer_overlay,
    generate_mapping_governance_report,
    validate_mapping_provenance,
)
from forgecompliance.reports import generate_coverage_report


def _mapping(
    *,
    status: str = "approved",
    claim_boundary: str = CLAIM_BOUNDARY,
    reviewed_by: str | None = "reviewer",
    approved_by: str | None = "approver",
    source_reference: str | None = None,
) -> MappingProvenance:
    return MappingProvenance(
        framework="NZISM",
        control_id="NZISM.LOGGING.EVENT_CAPTURE",
        mapping_version="0.1",
        source_reference=source_reference,
        source_retrieved_at="2026-04-30T00:00:00+00:00" if source_reference else None,
        mapped_by="mapper",
        reviewed_by=reviewed_by,
        approved_by=approved_by,
        approval_status=status,
        claim_boundary=claim_boundary,
        notes=None,
    )


def test_mapping_requires_claim_boundary():
    mapping = _mapping(claim_boundary="")

    assert "claim_boundary is required" in validate_mapping_provenance(mapping)[0]


def test_approved_mapping_requires_reviewer_and_approver():
    mapping = _mapping(status="approved", reviewed_by=None, approved_by=None)
    errors = validate_mapping_provenance(mapping)

    assert any("requires reviewed_by" in error for error in errors)
    assert any("requires approved_by" in error for error in errors)


def test_reviewed_mapping_requires_reviewer():
    mapping = _mapping(status="reviewed", reviewed_by=None, approved_by=None)

    assert any("reviewed mapping requires reviewed_by" in error for error in validate_mapping_provenance(mapping))


def test_draft_mapping_allowed_without_approver():
    mapping = _mapping(status="draft", reviewed_by=None, approved_by=None)

    assert validate_mapping_provenance(mapping) == []


def test_deprecated_mapping_excluded_from_active_coverage():
    approved = _mapping(status="approved")
    deprecated = _mapping(status="deprecated")

    assert active_mappings([approved, deprecated]) == [approved]


def test_mapping_governance_report_counts_statuses():
    mappings = [
        _mapping(status="approved"),
        _mapping(status="reviewed", approved_by=None),
        _mapping(status="draft", reviewed_by=None, approved_by=None),
        _mapping(status="deprecated"),
    ]

    report = generate_mapping_governance_report(mappings, generated_at="2026-04-30T00:00:00+00:00")

    assert report.approved_count == 1
    assert report.reviewed_count == 1
    assert report.draft_count == 1
    assert report.deprecated_count == 1


def test_control_coverage_report_includes_mapping_version():
    report = generate_coverage_report(ControlRegistry(), [], ["NZISM"])

    control = report["framework_reports"]["NZISM"]["controls"][0]
    assert control["mapping_version"] == "0.1"


def test_control_coverage_report_includes_claim_boundary():
    report = generate_coverage_report(ControlRegistry(), [], ["NZISM"])

    control = report["framework_reports"]["NZISM"]["controls"][0]
    assert control["claim_boundary"] == CLAIM_BOUNDARY


def test_missing_claim_boundary_reported_as_gap():
    mapping = _mapping(claim_boundary="")

    report = generate_mapping_governance_report([mapping], generated_at="2026-04-30T00:00:00+00:00")

    assert report.missing_claim_boundary == ["NZISM/NZISM.LOGGING.EVENT_CAPTURE"]


def test_customer_specific_mapping_overlay_can_override_status():
    base = _mapping(status="approved")

    overlay = apply_customer_overlay(base, approval_status="draft", notes="customer review pending")

    assert overlay.approval_status == "draft"
    assert overlay.notes == "customer review pending"


def test_customer_specific_overlay_does_not_mutate_base_mapping():
    base = _mapping(status="approved", claim_boundary=CLAIM_BOUNDARY)

    overlay = apply_customer_overlay(base, approval_status="draft", claim_boundary="Customer evidence support boundary")

    assert base.approval_status == "approved"
    assert base.claim_boundary == CLAIM_BOUNDARY
    assert overlay.claim_boundary == "Customer evidence support boundary"


def test_mapping_governance_report_is_deterministic():
    mappings = [
        _mapping(status="draft", reviewed_by=None, approved_by=None),
        _mapping(status="approved"),
    ]

    first = generate_mapping_governance_report(mappings, generated_at="2026-04-30T00:00:00+00:00")
    second = generate_mapping_governance_report(list(reversed(mappings)), generated_at="2026-04-30T00:00:00+00:00")

    assert asdict(first) == asdict(second)


def test_report_never_uses_certification_language():
    report = generate_coverage_report(ControlRegistry(), [], ["NZISM"])
    text = str(report).lower()

    assert "certified" not in text
    assert "certifies" not in text


def test_invalid_approval_status_rejected():
    mapping = _mapping(status="rubber_stamp")

    assert any("invalid approval_status" in error for error in validate_mapping_provenance(mapping))


def test_mapping_source_reference_optional_but_reported_when_present():
    mapping = _mapping(source_reference="https://example.test/control-source")

    assert validate_mapping_provenance(mapping) == []
    assert mapping.source_reference == "https://example.test/control-source"
