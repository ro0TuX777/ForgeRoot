from __future__ import annotations

import dataclasses
import hashlib
from typing import TYPE_CHECKING

from forgeledger.canonical_json import canonical_json

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent
    from forgeledger.backend import ChainValidationReport


def compute_event_hash(event: "LedgerEvent") -> str:
    """
    Compute sha256 over the canonical JSON of the event with integrity.event_hash cleared.

    The previous_hash is already embedded in event.integrity.previous_hash, so it is
    included in the canonical JSON automatically. Clearing only event_hash avoids the
    circular dependency of hashing a field that isn't known yet.
    """
    # Clear both event_hash (avoids circularity) and signature (added after hashing;
    # must not be part of the hash input so verify_chain works on signed events).
    cleared_integrity = dataclasses.replace(event.integrity, event_hash="", signature=None)
    cleared_event = dataclasses.replace(event, integrity=cleared_integrity)
    content = canonical_json(cleared_event)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def attach_integrity(
    event: "LedgerEvent",
    previous_hash: "str | None",
) -> "LedgerEvent":
    """
    Return a new event with integrity.previous_hash set and integrity.event_hash computed.
    Call this immediately before appending to the backend.
    """
    event_with_prev = dataclasses.replace(
        event,
        integrity=dataclasses.replace(
            event.integrity,
            previous_hash=previous_hash,
            event_hash="",
        ),
    )
    event_hash = compute_event_hash(event_with_prev)
    return dataclasses.replace(
        event_with_prev,
        integrity=dataclasses.replace(event_with_prev.integrity, event_hash=event_hash),
    )


def verify_chain(events: "list[LedgerEvent]") -> "ChainValidationReport":
    """
    Verify the integrity of an ordered event sequence.

    Fails if any event_hash does not recompute, if any previous_hash link is broken,
    or if events are missing or reordered.
    """
    from forgeledger.backend import ChainValidationReport

    if not events:
        return ChainValidationReport(
            valid=True,
            total_events=0,
            first_event_id=None,
            last_event_id=None,
            broken_at_sequence=None,
            error=None,
        )

    expected_previous: "str | None" = None

    for seq, event in enumerate(events):
        if event.integrity.previous_hash != expected_previous:
            return ChainValidationReport(
                valid=False,
                total_events=len(events),
                first_event_id=events[0].event_id,
                last_event_id=events[-1].event_id,
                broken_at_sequence=seq,
                error=(
                    f"previous_hash mismatch at sequence {seq}: "
                    f"event_id={event.event_id} "
                    f"expected={expected_previous!r} "
                    f"got={event.integrity.previous_hash!r}"
                ),
            )

        expected_hash = compute_event_hash(event)
        if event.integrity.event_hash != expected_hash:
            return ChainValidationReport(
                valid=False,
                total_events=len(events),
                first_event_id=events[0].event_id,
                last_event_id=events[-1].event_id,
                broken_at_sequence=seq,
                error=(
                    f"event_hash mismatch at sequence {seq}: "
                    f"event_id={event.event_id}"
                ),
            )

        expected_previous = event.integrity.event_hash

    return ChainValidationReport(
        valid=True,
        total_events=len(events),
        first_event_id=events[0].event_id,
        last_event_id=events[-1].event_id,
        broken_at_sequence=None,
        error=None,
    )
