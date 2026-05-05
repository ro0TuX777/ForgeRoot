"""
GapAnalyzer — detects missing control evidence in a set of LedgerEvents.

Coverage classification per control:
  covered  — all required_event_types are present AND all sampled events
              of those types have the required fields populated
  partial  — some required_event_types are present, or all are present
              but some required fields are missing on sampled events
  gap      — none of the required_event_types are present in the ledger
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from forgecompliance.control_registry import ControlRegistry

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent

_SAMPLE_SIZE = 5  # events per type to check for field presence


@dataclass
class ControlCoverage:
    control_id: str
    objective: str
    status: str                        # "covered" | "partial" | "gap"
    present_event_types: list[str]
    missing_event_types: list[str]
    missing_required_fields: list[str] # field paths absent on sampled events
    confidence: str
    mapping_version: str
    claim_boundary: str
    approval_status: str
    source_reference: str | None


@dataclass
class FrameworkGapReport:
    framework: str
    profile_version: str
    claim_boundary: str
    generated_at: str
    total_controls: int
    covered: int
    partial: int
    gaps: int
    coverage_percent: float
    controls: list[ControlCoverage]


def _get_field(event: "LedgerEvent", path: str) -> Any:
    """Traverse a dot-notation field path. Returns None if any segment is absent."""
    obj: Any = event
    for part in path.split("."):
        if obj is None:
            return None
        obj = getattr(obj, part, None)
    return obj


def _field_present(event: "LedgerEvent", path: str) -> bool:
    val = _get_field(event, path)
    if val is None:
        return False
    if isinstance(val, str) and not val:
        return False
    return True


class GapAnalyzer:
    def __init__(self, registry: ControlRegistry) -> None:
        self._registry = registry

    def analyze(
        self,
        framework_id: str,
        events: "list[LedgerEvent]",
        generated_at: str | None = None,
    ) -> FrameworkGapReport:
        """Analyze evidence coverage for a single framework against a set of events."""
        profile = self._registry.get_profile(framework_id)
        if profile is None:
            raise ValueError(f"Unknown framework: {framework_id!r}")

        # Index events by type for quick lookup
        by_type: dict[str, list[LedgerEvent]] = {}
        for e in events:
            by_type.setdefault(e.event_type.value, []).append(e)

        control_coverages: list[ControlCoverage] = []
        covered = partial = gaps = 0

        for ctrl in profile.controls:
            provenance = self._registry.get_mapping_provenance(framework_id, ctrl.control_id)
            required_types = set(ctrl.required_event_types)
            present_types  = required_types & set(by_type.keys())
            missing_types  = required_types - present_types

            # Determine field gaps on sampled events of present types
            missing_fields: list[str] = []
            for et in present_types:
                sample = by_type[et][:_SAMPLE_SIZE]
                for field_path in ctrl.required_fields:
                    if any(not _field_present(ev, field_path) for ev in sample):
                        if field_path not in missing_fields:
                            missing_fields.append(field_path)

            if not present_types:
                status = "gap"
                gaps += 1
            elif missing_types or missing_fields:
                status = "partial"
                partial += 1
            else:
                status = "covered"
                covered += 1

            control_coverages.append(ControlCoverage(
                control_id=ctrl.control_id,
                objective=ctrl.objective,
                status=status,
                present_event_types=sorted(present_types),
                missing_event_types=sorted(missing_types),
                missing_required_fields=missing_fields,
                confidence=ctrl.mapping_confidence,
                mapping_version=provenance.mapping_version if provenance else profile.profile_version,
                claim_boundary=provenance.claim_boundary if provenance else profile.claim_boundary,
                approval_status=provenance.approval_status if provenance else "draft",
                source_reference=provenance.source_reference if provenance else None,
            ))

        total = len(profile.controls)
        pct = round((covered / total * 100) if total else 0.0, 1)

        return FrameworkGapReport(
            framework=framework_id,
            profile_version=profile.profile_version,
            claim_boundary=profile.claim_boundary,
            generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
            total_controls=total,
            covered=covered,
            partial=partial,
            gaps=gaps,
            coverage_percent=pct,
            controls=control_coverages,
        )

    def analyze_all(
        self, events: "list[LedgerEvent]"
    ) -> dict[str, FrameworkGapReport]:
        return {
            fw: self.analyze(fw, events)
            for fw in self._registry.list_frameworks()
        }
