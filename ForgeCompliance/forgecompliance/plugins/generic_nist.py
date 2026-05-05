"""NIST CSF 2.0 plugin — generic, international alignment."""
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from forgecompliance.plugins.base import CompliancePlugin

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent, RetentionClass


class GenericNISTPlugin(CompliancePlugin):
    profile_id: ClassVar[str] = "generic_nist"
    jurisdiction: ClassVar[str] = "GLOBAL"
    sector: ClassVar[str] = "all"

    def retention_override(self, _event: "LedgerEvent") -> "RetentionClass | None":
        """
        NIST CSF 2.0 does not prescribe specific retention periods.
        Defers to the ForgeLedger core retention engine.
        """
        return None
