from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent


@dataclass
class AppendResult:
    success: bool
    event_id: str
    event_hash: str
    sequence_number: int
    error: Optional[str] = None


@dataclass
class LedgerQuery:
    from_time: Optional[str] = None
    to_time: Optional[str] = None
    actor_id: Optional[str] = None
    source_module: Optional[str] = None
    event_types: Optional[list[str]] = None
    tenant_id: Optional[str] = None
    max_results: int = 1000


@dataclass
class HoldSelector:
    tenant_id: str
    reason: str
    event_ids: Optional[list[str]] = None
    from_time: Optional[str] = None
    to_time: Optional[str] = None


@dataclass
class HoldResult:
    applied_count: int
    hold_id: str
    error: Optional[str] = None


@dataclass
class ChainValidationReport:
    valid: bool
    total_events: int
    first_event_id: Optional[str]
    last_event_id: Optional[str]
    broken_at_sequence: Optional[int]  # None if valid
    error: Optional[str]


@dataclass
class ExportSelector:
    from_time: Optional[str] = None
    to_time: Optional[str] = None
    tenant_id: Optional[str] = None
    framework_profiles: Optional[list[str]] = None


class LedgerBackend(ABC):
    @abstractmethod
    def append_event(self, event: "LedgerEvent") -> AppendResult: ...

    @abstractmethod
    def read_events(self, query: LedgerQuery) -> list["LedgerEvent"]: ...

    @abstractmethod
    def get_latest_hash(self) -> Optional[str]: ...

    @abstractmethod
    def verify_chain(self) -> ChainValidationReport: ...

    @abstractmethod
    def apply_legal_hold(self, selector: HoldSelector) -> HoldResult: ...

    @abstractmethod
    def release_legal_hold(self, hold_id: str, reason: str) -> HoldResult: ...

    @abstractmethod
    def is_on_hold(self, event_id: str) -> bool: ...

    @abstractmethod
    def export_slice(self, selector: ExportSelector) -> dict: ...

    @abstractmethod
    def health_check(self) -> dict: ...

    def import_slice(self, slice_data: dict) -> dict:
        """
        Import events from an export_slice result into this backend.

        The slice's chain integrity is verified before any writes. Import stops
        at the first write failure to preserve chain consistency.

        Returns: {imported_count, chain_valid_after_import, errors}
        """
        from forgeledger.hash_chain import verify_chain
        from forgeledger.schema import event_from_dict

        raw_events = slice_data.get("events", [])
        events = [event_from_dict(e) for e in raw_events]

        pre_check = verify_chain(events)
        if not pre_check.valid:
            return {
                "imported_count": 0,
                "chain_valid_after_import": False,
                "errors": [f"Slice chain invalid before import: {pre_check.error}"],
            }

        errors: list[str] = []
        imported = 0
        for event in events:
            result = self.append_event(event)
            if result.success:
                imported += 1
            else:
                errors.append(f"Failed to import {event.event_id}: {result.error}")
                break  # stop to keep chain intact

        post_check = self.verify_chain()
        return {
            "imported_count": imported,
            "chain_valid_after_import": post_check.valid,
            "errors": errors,
        }
