"""
Deterministic report generators for Phase 2 coverage and retention analysis.
Phase 3 wraps these into the full evidence package.
"""
from __future__ import annotations

import dataclasses
from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from forgecompliance.control_registry import ControlRegistry
from forgecompliance.gap_analyzer import GapAnalyzer
from forgecompliance.mapping_governance import generate_mapping_governance_report

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent


def _report_to_dict(obj: object) -> object:
    """Recursively convert dataclasses to dicts for JSON serialisation."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _report_to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, list):
        return [_report_to_dict(i) for i in obj]
    return obj


def generate_coverage_report(
    registry: ControlRegistry,
    events: "list[LedgerEvent]",
    framework_ids: list[str] | None = None,
) -> dict:
    """
    Generate a deterministic coverage report for the given frameworks.
    framework_ids=None means all loaded frameworks.
    """
    analyzer = GapAnalyzer(registry)
    targets = framework_ids or registry.list_frameworks()

    stable_ts = _stable_timestamp(events)
    framework_reports: dict[str, object] = {}
    for fw in sorted(targets):
        report = analyzer.analyze(fw, events, generated_at=stable_ts)
        framework_reports[fw] = _report_to_dict(report)

    return {
        "generated_at": _stable_timestamp(events),
        "total_events_analysed": len(events),
        "frameworks_analysed": sorted(targets),
        "claim_boundary": "Evidence support only. Not a compliance certification.",
        "mapping_governance": _report_to_dict(
            generate_mapping_governance_report(
                [
                    mapping
                    for mapping in registry.all_mapping_provenance(include_deprecated=False)
                    if mapping.framework in targets
                ],
                generated_at=stable_ts,
            )
        ),
        "framework_reports": framework_reports,
    }


def generate_retention_report(events: "list[LedgerEvent]") -> dict:
    """Summarise retention class distribution across the event set."""
    counts: Counter = Counter()
    held: list[str] = []

    for e in events:
        counts[e.policy.retention_class.value] += 1
        if e.policy.legal_hold:
            held.append(e.event_id)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_events": len(events),
        "retention_class_counts": dict(sorted(counts.items())),
        "legal_hold_count": len(held),
        "legal_hold_event_ids": sorted(held),
    }


def generate_event_type_summary(events: "list[LedgerEvent]") -> list[dict]:
    """Return a sorted list of {event_type, count} dicts — deterministic."""
    counts: Counter = Counter(e.event_type.value for e in events)
    return [
        {"event_type": et, "count": cnt}
        for et, cnt in sorted(counts.items())
    ]


def _stable_timestamp(events: "list[LedgerEvent]") -> str:
    """
    Use the latest event_time from the set for report timestamp so the
    report is deterministic given the same inputs (avoids datetime.now drift).
    Falls back to now() for an empty set.
    """
    if not events:
        return datetime.now(timezone.utc).isoformat()
    return max(e.event_time for e in events)
