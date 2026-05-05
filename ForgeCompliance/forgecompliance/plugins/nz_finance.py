"""RBNZ BS11 plugin — NZ finance sector (registered banks, outsourcing policy)."""
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from forgecompliance.plugins.base import CompliancePlugin

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent, RetentionClass

_FINANCE_CONTROL_TAGS = {
    "BS11.S3.GOVERNANCE",
    "BS11.S4.RISK_MANAGEMENT",
    "BS11.S5.SERVICE_AGREEMENT",
    "BS11.S5.AUDIT_ACCESS",
}


class NZFinancePlugin(CompliancePlugin):
    profile_id: ClassVar[str] = "nz_finance"
    jurisdiction: ClassVar[str] = "NZ"
    sector: ClassVar[str] = "finance"

    def retention_override(self, event: "LedgerEvent") -> "RetentionClass | None":
        """
        RBNZ BS11: outsourcing-related events for NZ-registered banks → audit_7y minimum.
        Triggered by BS11 control tags or finance_outsourcing payload sensitivity.
        """
        from forgeledger.schema import RetentionClass

        if event.policy.legal_hold:
            return None

        payload_sensitivity = (event.payload or {}).get("data_sensitivity", "")
        if payload_sensitivity == "finance_outsourcing":
            return RetentionClass.AUDIT_7Y

        if any(tag in _FINANCE_CONTROL_TAGS for tag in event.control_tags):
            return RetentionClass.AUDIT_7Y

        return None
