"""ISO/IEC 27001:2022 plugin — generic, applicable across sectors."""
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from forgecompliance.plugins.base import CompliancePlugin

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent, RetentionClass

_ISO_LOGGING_TAGS = {"ISO27001.A8.15.LOGGING", "ISO27001.A8.16.MONITORING"}


class GenericISO27001Plugin(CompliancePlugin):
    profile_id: ClassVar[str] = "generic_iso27001"
    jurisdiction: ClassVar[str] = "GLOBAL"
    sector: ClassVar[str] = "all"

    def retention_override(self, event: "LedgerEvent") -> "RetentionClass | None":
        """
        ISO 27001 A.8.15 requires log retention aligned with risk.
        Events tagged with ISO logging controls → support_1y minimum.
        """
        from forgeledger.schema import RetentionClass

        if event.policy.legal_hold:
            return None

        if any(tag in _ISO_LOGGING_TAGS for tag in event.control_tags):
            if event.policy.retention_class in (
                RetentionClass.EPHEMERAL,
                RetentionClass.OPERATIONAL_30D,
            ):
                return RetentionClass.SUPPORT_1Y
        return None

    def extra_control_tags(self, _event: "LedgerEvent") -> list[str]:
        return []
