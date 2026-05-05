"""APRA CPS 234 plugin — Australian finance sector (APRA-regulated entities)."""
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from forgecompliance.plugins.base import CompliancePlugin

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent, RetentionClass

_CPS234_CONTROL_TAGS = {
    "CPS234.P15.CAPABILITY",
    "CPS234.P18.POLICY",
    "CPS234.P24.INCIDENT",
    "CPS234.P28.AUDIT",
    "CPS234.P26.TESTING",
}


class AUFinancePlugin(CompliancePlugin):
    profile_id: ClassVar[str] = "au_finance"
    jurisdiction: ClassVar[str] = "AU"
    sector: ClassVar[str] = "finance"

    def retention_override(self, event: "LedgerEvent") -> "RetentionClass | None":
        """
        APRA CPS 234: information security capability evidence → audit_7y.
        Applies to AU-residency events tagged with CPS 234 control IDs.
        """
        from forgeledger.schema import RetentionClass

        if event.policy.legal_hold:
            return None

        if event.tenant.data_residency not in ("AU", "NZ"):
            return None

        if any(tag in _CPS234_CONTROL_TAGS for tag in event.control_tags):
            return RetentionClass.AUDIT_7Y

        return None
