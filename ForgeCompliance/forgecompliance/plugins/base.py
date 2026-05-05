"""
CompliancePlugin — abstract base for sector/framework-specific behaviour.

Each plugin can:
  1. Override retention classification for events in its sector.
  2. Add extra control tags beyond what the YAML mapping provides.
  3. Validate an evidence package against sector-specific requirements.

Plugins are stateless and do not hold backend references.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent, RetentionClass


class CompliancePlugin(ABC):
    profile_id: ClassVar[str]
    jurisdiction: ClassVar[str]
    sector: ClassVar[str]

    @abstractmethod
    def retention_override(self, event: "LedgerEvent") -> "RetentionClass | None":
        """
        Return an override RetentionClass for this event, or None to use the
        ForgeLedger default. Called after the core retention engine runs.
        """
        ...

    def extra_control_tags(self, _event: "LedgerEvent") -> list[str]:
        """Return additional control tags to attach to this event. Default: none."""
        return []

    def validate_package(self, _package: dict) -> list[str]:
        """
        Validate a completed evidence package dict against sector requirements.
        Returns a list of error strings; empty list means valid.
        Default: no additional validation.
        """
        return []
