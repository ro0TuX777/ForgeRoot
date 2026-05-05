from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timezone


CLAIM_BOUNDARY = "Evidence support only. Not a compliance certification."
VALID_APPROVAL_STATUSES = {"draft", "reviewed", "approved", "deprecated"}


@dataclass
class MappingProvenance:
    framework: str
    control_id: str
    mapping_version: str
    source_reference: str | None
    source_retrieved_at: str | None
    mapped_by: str
    reviewed_by: str | None
    approved_by: str | None
    approval_status: str
    claim_boundary: str
    notes: str | None = None


@dataclass
class MappingGovernanceReport:
    total_mappings: int
    approved_count: int
    reviewed_count: int
    draft_count: int
    deprecated_count: int
    missing_claim_boundary: list[str]
    missing_reviewer: list[str]
    missing_approver: list[str]
    generated_at: str


def validate_mapping_provenance(mapping: MappingProvenance) -> list[str]:
    errors: list[str] = []
    label = f"{mapping.framework}/{mapping.control_id}"

    if mapping.approval_status not in VALID_APPROVAL_STATUSES:
        errors.append(f"{label}: invalid approval_status {mapping.approval_status!r}")
    if not mapping.claim_boundary:
        errors.append(f"{label}: claim_boundary is required")
    if mapping.approval_status == "approved":
        if not mapping.reviewed_by:
            errors.append(f"{label}: approved mapping requires reviewed_by")
        if not mapping.approved_by:
            errors.append(f"{label}: approved mapping requires approved_by")
    if mapping.approval_status == "reviewed" and not mapping.reviewed_by:
        errors.append(f"{label}: reviewed mapping requires reviewed_by")
    return errors


def apply_customer_overlay(
    base: MappingProvenance,
    *,
    approval_status: str | None = None,
    notes: str | None = None,
    claim_boundary: str | None = None,
    reviewed_by: str | None = None,
    approved_by: str | None = None,
) -> MappingProvenance:
    """Return an overlaid provenance record without mutating the base mapping."""
    return dataclasses.replace(
        base,
        approval_status=approval_status if approval_status is not None else base.approval_status,
        notes=notes if notes is not None else base.notes,
        claim_boundary=claim_boundary if claim_boundary is not None else base.claim_boundary,
        reviewed_by=reviewed_by if reviewed_by is not None else base.reviewed_by,
        approved_by=approved_by if approved_by is not None else base.approved_by,
    )


def active_mappings(
    mappings: list[MappingProvenance],
    *,
    include_deprecated: bool = False,
) -> list[MappingProvenance]:
    if include_deprecated:
        return list(mappings)
    return [mapping for mapping in mappings if mapping.approval_status != "deprecated"]


def generate_mapping_governance_report(
    mappings: list[MappingProvenance],
    *,
    generated_at: str | None = None,
) -> MappingGovernanceReport:
    ordered = sorted(mappings, key=lambda m: (m.framework, m.control_id, m.mapping_version))
    missing_claim_boundary: list[str] = []
    missing_reviewer: list[str] = []
    missing_approver: list[str] = []
    counts = {status: 0 for status in VALID_APPROVAL_STATUSES}

    for mapping in ordered:
        label = f"{mapping.framework}/{mapping.control_id}"
        if mapping.approval_status in counts:
            counts[mapping.approval_status] += 1
        if not mapping.claim_boundary:
            missing_claim_boundary.append(label)
        if mapping.approval_status in {"reviewed", "approved"} and not mapping.reviewed_by:
            missing_reviewer.append(label)
        if mapping.approval_status == "approved" and not mapping.approved_by:
            missing_approver.append(label)

    return MappingGovernanceReport(
        total_mappings=len(ordered),
        approved_count=counts["approved"],
        reviewed_count=counts["reviewed"],
        draft_count=counts["draft"],
        deprecated_count=counts["deprecated"],
        missing_claim_boundary=missing_claim_boundary,
        missing_reviewer=missing_reviewer,
        missing_approver=missing_approver,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
    )
