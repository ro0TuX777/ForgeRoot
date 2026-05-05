"""SOC 2 TSC plugin — generic, jurisdiction-neutral service organisations."""
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from forgecompliance.plugins.base import CompliancePlugin

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent, RetentionClass


class GenericSOC2Plugin(CompliancePlugin):
    profile_id: ClassVar[str] = "generic_soc2"
    jurisdiction: ClassVar[str] = "GLOBAL"
    sector: ClassVar[str] = "service_organizations"

    def retention_override(self, event: "LedgerEvent") -> "RetentionClass | None":
        """
        SOC 2 Type II evidence is typically required for the audit period (1 year)
        plus a look-back buffer. Override security-relevant events to support_1y
        if they are currently classified lower.
        """
        from forgeledger.schema import RetentionClass

        if event.policy.legal_hold:
            return None

        soc2_event_types = {
            "concord.admission_decision",
            "forgegate.decision_record",
            "human.approval_decision",
            "agent.human_review_required",
        }
        if event.event_type.value in soc2_event_types:
            if event.policy.retention_class in (
                RetentionClass.EPHEMERAL,
                RetentionClass.OPERATIONAL_30D,
            ):
                return RetentionClass.SUPPORT_1Y
        return None
