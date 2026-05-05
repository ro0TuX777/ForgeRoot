"""
Schema for framework mapping YAML files.

Each YAML file describes one compliance framework profile. The schema is
intentionally narrow: it validates structure, not regulatory accuracy.
The claim_boundary field on every profile makes the evidence-support-only
position explicit to consumers and automated validators alike.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CLAIM_BOUNDARY_REQUIRED = "Evidence support only. Not a compliance certification."

VALID_CONFIDENCE_LEVELS = {"high", "medium", "low"}


@dataclass
class ControlMapping:
    control_id: str
    objective: str
    required_event_types: list[str]
    required_fields: list[str]       # dot-notation paths, e.g. "actor.actor_id"
    evidence_artifacts: list[str]
    retention_expectation: str       # must be a RetentionClass value
    mapping_confidence: str          # "high" | "medium" | "low"
    notes: str = ""


@dataclass
class FrameworkProfile:
    framework: str
    profile_version: str
    jurisdiction: str
    sector: str
    claim_boundary: str
    controls: list[ControlMapping]


def load_framework_profile(yaml_path: Path) -> FrameworkProfile:
    """Load and parse a framework mapping YAML into a FrameworkProfile."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    controls = [
        ControlMapping(
            control_id=c["control_id"],
            objective=c["objective"],
            required_event_types=c.get("required_event_types", []),
            required_fields=c.get("required_fields", []),
            evidence_artifacts=c.get("evidence_artifacts", []),
            retention_expectation=c.get("retention_expectation", "operational_30d"),
            mapping_confidence=c.get("mapping_confidence", "low"),
            notes=c.get("notes", ""),
        )
        for c in data.get("controls", [])
    ]

    return FrameworkProfile(
        framework=data["framework"],
        profile_version=data.get("profile_version", "0.1"),
        jurisdiction=data.get("jurisdiction", ""),
        sector=data.get("sector", ""),
        claim_boundary=data.get("claim_boundary", ""),
        controls=controls,
    )


def validate_framework_profile(profile: FrameworkProfile) -> list[str]:
    """
    Validate a FrameworkProfile for structural correctness.
    Returns a list of error strings; empty list means valid.
    """
    from forgeledger.schema import EventType, RetentionClass

    errors: list[str] = []

    if not profile.framework:
        errors.append("framework is required")
    if not profile.profile_version:
        errors.append("profile_version is required")
    if not profile.claim_boundary:
        errors.append("claim_boundary is required")
    if profile.claim_boundary and CLAIM_BOUNDARY_REQUIRED not in profile.claim_boundary:
        errors.append(
            f"claim_boundary must contain: '{CLAIM_BOUNDARY_REQUIRED}' — "
            f"got: '{profile.claim_boundary}'"
        )
    if not profile.controls:
        errors.append("controls list must not be empty")

    valid_event_types = {et.value for et in EventType}
    valid_retention   = {rc.value for rc in RetentionClass}

    for ctrl in profile.controls:
        prefix = f"control {ctrl.control_id!r}"

        if not ctrl.control_id:
            errors.append("a control is missing control_id")
        if not ctrl.objective:
            errors.append(f"{prefix}: objective is required")
        if not ctrl.required_event_types:
            errors.append(f"{prefix}: required_event_types must not be empty")
        for et in ctrl.required_event_types:
            if et not in valid_event_types:
                errors.append(f"{prefix}: unknown event_type {et!r}")
        if ctrl.retention_expectation not in valid_retention:
            errors.append(
                f"{prefix}: unknown retention_expectation {ctrl.retention_expectation!r}"
            )
        if ctrl.mapping_confidence not in VALID_CONFIDENCE_LEVELS:
            errors.append(
                f"{prefix}: mapping_confidence must be one of "
                f"{sorted(VALID_CONFIDENCE_LEVELS)}, got {ctrl.mapping_confidence!r}"
            )

    return errors
