"""
Replay protection for Phase 5.

Tracks seen event_ids and raises ReplayDetectedError on duplicates. In
production this would be backed by a distributed cache (Redis, DynamoDB TTL
keyed on event_id) so multiple SDK instances share the same guard. v0.1 uses
an in-memory set sufficient for single-process use and testing.
"""
from __future__ import annotations


class ReplayDetectedError(Exception):
    """Raised when an event_id has already been processed."""

    def __init__(self, event_id: str) -> None:
        super().__init__(
            f"Replay detected: event_id {event_id!r} has already been processed."
        )
        self.event_id = event_id


class ReplayProtector:
    """
    In-memory replay guard.

    Tracks processed event_ids; raises ReplayDetectedError on duplicates.
    v0.1: in-memory set. Phase 5+: replace backing store with distributed cache.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def check_and_register(self, event_id: str) -> None:
        """Register event_id or raise ReplayDetectedError if already seen."""
        if event_id in self._seen:
            raise ReplayDetectedError(event_id)
        self._seen.add(event_id)

    def is_seen(self, event_id: str) -> bool:
        return event_id in self._seen

    def reset(self) -> None:
        self._seen.clear()
