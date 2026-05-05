"""
FrameworkMapper — maps LedgerEvents to compliance control IDs.

A control is "touched" by an event when the event's event_type appears in the
control's required_event_types list. The mapper does not validate field
presence — that is the GapAnalyzer's job.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from forgecompliance.control_registry import ControlRegistry

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent


@dataclass
class ControlTag:
    framework: str
    control_id: str
    event_type: str
    confidence: str


class FrameworkMapper:
    def __init__(self, registry: ControlRegistry) -> None:
        self._registry = registry

    def map_event(self, event: "LedgerEvent") -> list[ControlTag]:
        """
        Return every ControlTag this event provides evidence for.
        A tag is produced for each (framework, control) that lists this
        event's event_type in its required_event_types.
        """
        tags: list[ControlTag] = []
        event_type_str = event.event_type.value
        for framework_id, ctrl in self._registry.controls_requiring_event_type(event_type_str):
            tags.append(ControlTag(
                framework=framework_id,
                control_id=ctrl.control_id,
                event_type=event_type_str,
                confidence=ctrl.mapping_confidence,
            ))
        return tags

    def generate_coverage_map(
        self, events: "list[LedgerEvent]"
    ) -> dict[str, set[str]]:
        """
        Build a coverage map from an event list.
        Returns {framework_id: set_of_covered_control_ids}.
        A control is "covered" when at least one event of each required type
        is present in the event list.
        """
        # Collect which event types are present
        present_types: set[str] = {e.event_type.value for e in events}

        coverage: dict[str, set[str]] = {}
        for framework_id in self._registry.list_frameworks():
            profile = self._registry.get_profile(framework_id)
            if profile is None:
                continue
            covered: set[str] = set()
            for ctrl in profile.controls:
                required = set(ctrl.required_event_types)
                if required and required.issubset(present_types):
                    covered.add(ctrl.control_id)
            coverage[framework_id] = covered

        return coverage
