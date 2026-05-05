from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from forgeledger.backend import HoldSelector, HoldResult


@dataclass
class Hold:
    hold_id: str
    tenant_id: str
    reason: str
    event_ids: list[str]
    applied_at: str
    released: bool = False
    release_reason: Optional[str] = None
    released_at: Optional[str] = None


class HoldRegistry:
    """
    In-memory legal hold registry for Phase 1.

    The JsonlBackend persists holds independently in a sidecar file. This class
    is useful for unit tests and for in-process hold checks decoupled from a backend.
    """

    def __init__(self) -> None:
        self._holds: dict[str, Hold] = {}

    def apply(self, selector: HoldSelector, event_ids: list[str]) -> HoldResult:
        hold_id = str(uuid.uuid4())
        self._holds[hold_id] = Hold(
            hold_id=hold_id,
            tenant_id=selector.tenant_id,
            reason=selector.reason,
            event_ids=list(event_ids),
            applied_at=datetime.now(timezone.utc).isoformat(),
        )
        return HoldResult(applied_count=len(event_ids), hold_id=hold_id)

    def release(self, hold_id: str, reason: str) -> HoldResult:
        if hold_id not in self._holds:
            return HoldResult(applied_count=0, hold_id=hold_id, error="Hold not found")
        hold = self._holds[hold_id]
        hold.released = True
        hold.release_reason = reason
        hold.released_at = datetime.now(timezone.utc).isoformat()
        return HoldResult(applied_count=len(hold.event_ids), hold_id=hold_id)

    def is_on_hold(self, event_id: str) -> bool:
        return any(
            not h.released and event_id in h.event_ids
            for h in self._holds.values()
        )

    def get_active_holds(self) -> list[Hold]:
        return [h for h in self._holds.values() if not h.released]

    def get_held_event_ids(self) -> set[str]:
        held: set[str] = set()
        for h in self._holds.values():
            if not h.released:
                held.update(h.event_ids)
        return held
