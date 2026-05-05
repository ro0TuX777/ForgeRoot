# Phase 9 Control Mapping Review Workflow

## 1. Mapping Lifecycle

- Draft: mapping proposed but not reviewed.
- Reviewed: mapping has reviewer sign-off but not final approval.
- Approved: mapping has reviewer and approver metadata.
- Deprecated: mapping should not count as active coverage by default.

## 2. Required Metadata

- `framework`
- `control_id`
- `mapping_version`
- `source_reference`
- `source_retrieved_at`
- `mapped_by`
- `reviewed_by`
- `approved_by`
- `approval_status`
- `claim_boundary`
- `notes`

## 3. Review Workflow

1. A mapper proposes or updates a mapping.
2. A Control Mapping Reviewer reviews objective, required event types, required fields, evidence artifacts, retention expectation, and confidence.
3. A separate approver approves high-confidence or customer-facing mappings.
4. Disputes are recorded in `notes` and kept in draft/reviewed state until resolved.
5. Deprecated mappings remain visible for provenance but are excluded from active coverage unless explicitly requested.

## 4. Customer Overlays

Customer overlays are allowed when a customer needs different approval status, notes, or claim boundary.

Rules:
- Overlay must not mutate the base mapping.
- Overlay must record customer-specific claim boundary if it differs.
- Overlay status must remain explicit.
- Deprecated overlays must not count as active coverage by default.

## 5. Claim Boundary Review

Required phrase:

> Evidence support only. Not a compliance certification.

This phrase must appear in mapping governance outputs and customer-facing evidence language.

## 6. Evidence Package Impact

Mapping status affects coverage reporting:
- Approved/reviewed/draft mappings may be visible in governance reports.
- Deprecated mappings are excluded from active coverage by default.
- Coverage reports provide evidence support; they do not certify compliance.
