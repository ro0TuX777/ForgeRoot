"""
ControlRegistry — loads all framework mapping YAMLs and indexes them for lookup.

Default mappings dir: forgecompliance/mappings/*.yaml
Custom dirs can be passed to the constructor for tests or embedded use.
"""
from __future__ import annotations

from pathlib import Path

from forgecompliance.mapping_schema import (
    ControlMapping,
    FrameworkProfile,
    load_framework_profile,
    validate_framework_profile,
)
from forgecompliance.mapping_governance import CLAIM_BOUNDARY, MappingProvenance, active_mappings

_MAPPINGS_DIR = Path(__file__).parent / "mappings"


class ControlRegistry:
    """
    In-memory index of all loaded FrameworkProfiles.

    Profiles are keyed by profile.framework (e.g., "NZISM", "SOC2").
    """

    def __init__(self, mappings_dir: Path = _MAPPINGS_DIR) -> None:
        self._profiles: dict[str, FrameworkProfile] = {}
        self._load_all(mappings_dir)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_all(self, mappings_dir: Path) -> None:
        if not mappings_dir.exists():
            return
        for yaml_file in sorted(mappings_dir.glob("*.yaml")):
            profile = load_framework_profile(yaml_file)
            self._profiles[profile.framework] = profile

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_frameworks(self) -> list[str]:
        return sorted(self._profiles.keys())

    def get_profile(self, framework_id: str) -> FrameworkProfile | None:
        return self._profiles.get(framework_id)

    def get_control(self, framework_id: str, control_id: str) -> ControlMapping | None:
        profile = self._profiles.get(framework_id)
        if profile is None:
            return None
        for ctrl in profile.controls:
            if ctrl.control_id == control_id:
                return ctrl
        return None

    def get_mapping_provenance(self, framework_id: str, control_id: str) -> MappingProvenance | None:
        profile = self._profiles.get(framework_id)
        control = self.get_control(framework_id, control_id)
        if profile is None or control is None:
            return None
        return MappingProvenance(
            framework=framework_id,
            control_id=control.control_id,
            mapping_version=profile.profile_version,
            source_reference=None,
            source_retrieved_at=None,
            mapped_by="ForgeCompliance baseline mapping",
            reviewed_by="ForgeCompliance baseline review",
            approved_by="ForgeCompliance baseline approval",
            approval_status="approved",
            claim_boundary=profile.claim_boundary or CLAIM_BOUNDARY,
            notes=control.notes or None,
        )

    def all_mapping_provenance(self, include_deprecated: bool = True) -> list[MappingProvenance]:
        mappings = [
            self.get_mapping_provenance(fw_id, ctrl.control_id)
            for fw_id, ctrl in self.all_controls()
        ]
        materialized = [mapping for mapping in mappings if mapping is not None]
        return active_mappings(materialized, include_deprecated=include_deprecated)

    def controls_requiring_event_type(
        self, event_type: str
    ) -> list[tuple[str, ControlMapping]]:
        """Return all (framework_id, control) pairs that require this event type."""
        results = []
        for framework_id, profile in self._profiles.items():
            for ctrl in profile.controls:
                if event_type in ctrl.required_event_types:
                    results.append((framework_id, ctrl))
        return results

    def all_controls(self) -> list[tuple[str, ControlMapping]]:
        """Return every (framework_id, control) pair across all loaded profiles."""
        return [
            (fw_id, ctrl)
            for fw_id, profile in self._profiles.items()
            for ctrl in profile.controls
        ]

    def validate_all(self) -> dict[str, list[str]]:
        """Validate every loaded profile. Returns {framework_id: [errors]}."""
        return {
            fw_id: validate_framework_profile(profile)
            for fw_id, profile in self._profiles.items()
        }
