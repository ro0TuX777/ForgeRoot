"""
Phase 2 tests 1 & 6:
1. All mapping YAML files validate against schema.
6. Every mapping includes a claim boundary.
"""
from pathlib import Path

import pytest

from forgecompliance.mapping_schema import (
    CLAIM_BOUNDARY_REQUIRED,
    load_framework_profile,
    validate_framework_profile,
)

_MAPPINGS_DIR = Path(__file__).parent.parent / "forgecompliance" / "mappings"
_YAML_FILES   = sorted(_MAPPINGS_DIR.glob("*.yaml"))


# ---------------------------------------------------------------------------
# Test 1: All YAMLs validate against schema
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("yaml_file", _YAML_FILES, ids=lambda p: p.stem)
def test_yaml_validates_against_schema(yaml_file: Path):
    """Every mapping YAML must load cleanly and pass structural validation."""
    profile = load_framework_profile(yaml_file)
    errors = validate_framework_profile(profile)
    assert errors == [], f"{yaml_file.name} validation errors:\n" + "\n".join(errors)


def test_all_expected_frameworks_are_present():
    """Verify all 8 Phase 2 frameworks are present."""
    expected = {
        "NZISM", "HIPC_2020", "RBNZ_BS11", "ESSENTIAL_EIGHT",
        "APRA_CPS_234", "ISO27001_2022", "SOC2", "NIST_CSF_2_0",
    }
    loaded = {load_framework_profile(f).framework for f in _YAML_FILES}
    missing = expected - loaded
    assert not missing, f"Missing framework YAMLs: {missing}"


def test_each_yaml_loads_to_framework_profile():
    for yaml_file in _YAML_FILES:
        profile = load_framework_profile(yaml_file)
        assert profile.framework
        assert profile.controls


def test_all_controls_have_required_event_types():
    for yaml_file in _YAML_FILES:
        profile = load_framework_profile(yaml_file)
        for ctrl in profile.controls:
            assert ctrl.required_event_types, (
                f"{profile.framework}/{ctrl.control_id}: required_event_types is empty"
            )


def test_all_controls_have_valid_confidence():
    from forgecompliance.mapping_schema import VALID_CONFIDENCE_LEVELS
    for yaml_file in _YAML_FILES:
        profile = load_framework_profile(yaml_file)
        for ctrl in profile.controls:
            assert ctrl.mapping_confidence in VALID_CONFIDENCE_LEVELS, (
                f"{profile.framework}/{ctrl.control_id}: "
                f"invalid confidence {ctrl.mapping_confidence!r}"
            )


# ---------------------------------------------------------------------------
# Test 6: Every mapping includes a claim boundary
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("yaml_file", _YAML_FILES, ids=lambda p: p.stem)
def test_mapping_includes_claim_boundary(yaml_file: Path):
    """claim_boundary must be present and must contain the required text."""
    profile = load_framework_profile(yaml_file)
    assert profile.claim_boundary, f"{yaml_file.name}: claim_boundary is empty"
    assert CLAIM_BOUNDARY_REQUIRED in profile.claim_boundary, (
        f"{yaml_file.name}: claim_boundary must contain '{CLAIM_BOUNDARY_REQUIRED}'"
    )


def test_claim_boundary_text_is_consistent():
    """All mappings use exactly the same claim boundary text."""
    boundaries = {
        load_framework_profile(f).claim_boundary
        for f in _YAML_FILES
    }
    assert len(boundaries) == 1, (
        f"Inconsistent claim boundaries across mappings: {boundaries}"
    )
