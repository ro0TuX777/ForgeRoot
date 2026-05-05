"""NZISM plugin — NZ government sector retention overrides."""
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from forgecompliance.plugins.base import CompliancePlugin

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent, RetentionClass

_GOVERNANCE_EVENT_TYPES = {
    "concord.admission_decision",
    "forgegate.decision_record",
    "forgegate.policy_evaluation",
    "human.approval_decision",
    "agent.human_review_required",
    "retention.legal_hold_applied",
}


class NZGovernmentPlugin(CompliancePlugin):
    profile_id: ClassVar[str] = "nz_government"
    jurisdiction: ClassVar[str] = "NZ"
    sector: ClassVar[str] = "government"

    def retention_override(self, event: "LedgerEvent") -> "RetentionClass | None":
        """NZ government: all governance decision events → audit_7y minimum."""
        from forgeledger.schema import RetentionClass
        if event.tenant.data_residency == "NZ" and event.event_type.value in _GOVERNANCE_EVENT_TYPES:
            current = event.policy.retention_class
            if current in (RetentionClass.EPHEMERAL, RetentionClass.OPERATIONAL_30D, RetentionClass.SUPPORT_1Y):
                return RetentionClass.AUDIT_7Y
        return None
