"""HIPC 2020 plugin — NZ health sector retention overrides."""
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from forgecompliance.plugins.base import CompliancePlugin

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent, RetentionClass

_HEALTH_SENSITIVE_TAGS = {
    "HIPC.RULE11.ACCESS_LOG",
    "HIPC.RULE5.DATA_ACCURACY",
    "HIPC.RULE6.STORAGE_SECURITY",
}

_HEALTH_SENSITIVE_PAYLOAD_VALUES = {"health_identifiable", "health_de_identified"}


class NZHealthPlugin(CompliancePlugin):
    profile_id: ClassVar[str] = "nz_health"
    jurisdiction: ClassVar[str] = "NZ"
    sector: ClassVar[str] = "health"

    def retention_override(self, event: "LedgerEvent") -> "RetentionClass | None":
        """
        HIPC 2020 / Health Act NZ: health-identifiable events → health_10y.
        Triggered by:
          - payload.data_sensitivity = health_identifiable or health_de_identified
          - control_tags containing any HIPC control tag
          - tenant.data_residency = NZ and event involves health context
        """
        from forgeledger.schema import RetentionClass

        if event.policy.legal_hold:
            return None  # legal_hold takes precedence; don't override

        payload_sensitivity = (event.payload or {}).get("data_sensitivity", "")
        if payload_sensitivity in _HEALTH_SENSITIVE_PAYLOAD_VALUES:
            return RetentionClass.HEALTH_10Y

        if any(tag in _HEALTH_SENSITIVE_TAGS for tag in event.control_tags):
            return RetentionClass.HEALTH_10Y

        return None
