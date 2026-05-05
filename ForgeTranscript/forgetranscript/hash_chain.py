"""
HMAC-SHA256 hash chain for ForgeTranscript segments.

Extends ForgeLedger's evidence chain model to transcript segments.
Each segment is chained to its predecessor within a session, providing
tamper-evident cognitive traceability.

Chain structure:
    Segment[n].hash = HMAC-SHA256(
        key  = session_signing_key,
        data = content || type || timestamp || Segment[n-1].hash
    )

Modifying or deleting any segment invalidates the chain from that point forward.
"""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
from typing import Optional

from forgetranscript.schema import TranscriptSegment


def compute_segment_hash(
    segment: TranscriptSegment,
    signing_key: str,
) -> str:
    """Compute HMAC-SHA256 over a segment's content and chain position.

    The hash covers:
        - segment content (the agent's raw output)
        - segment type (classification)
        - timestamp (ordering proof)
        - previous_hash (chain linkage)
        - metadata serialized (if present)

    This ensures that modifying any field — including reclassifying
    a segment's type — invalidates the chain.
    """
    chain_data = (
        f"{segment.content}"
        f"|{segment.segment_type.value}"
        f"|{segment.timestamp}"
        f"|{segment.previous_hash or 'genesis'}"
        f"|{_serialize_metadata(segment.metadata)}"
    )
    return hmac.new(
        signing_key.encode("utf-8"),
        chain_data.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def attach_segment_hash(
    segment: TranscriptSegment,
    signing_key: str,
    previous_hash: Optional[str] = None,
) -> TranscriptSegment:
    """Return a new segment with previous_hash set and segment_hash computed.

    Call this immediately before persisting the segment.
    Mirrors ForgeLedger's attach_integrity pattern.
    """
    segment_with_prev = dataclasses.replace(
        segment,
        previous_hash=previous_hash,
        segment_hash="",
    )
    computed_hash = compute_segment_hash(segment_with_prev, signing_key)
    return dataclasses.replace(
        segment_with_prev,
        segment_hash=computed_hash,
    )


def verify_segment_chain(
    segments: list[TranscriptSegment],
    signing_key: str,
) -> ChainValidationResult:
    """Verify the integrity of an ordered segment sequence within a session.

    Validates:
        1. Each segment_hash recomputes correctly
        2. Each previous_hash links to the preceding segment
        3. Sequence numbers are monotonically increasing

    Used by:
        UC1 (Forensics): Prove no segments were altered post-capture
        UC2 (Compliance): Auditor verifies chain integrity
    """
    if not segments:
        return ChainValidationResult(
            valid=True,
            total_segments=0,
            broken_at_sequence=None,
            error=None,
        )

    expected_previous: Optional[str] = None

    for idx, segment in enumerate(segments):
        # Check chain linkage
        if segment.previous_hash != expected_previous:
            return ChainValidationResult(
                valid=False,
                total_segments=len(segments),
                broken_at_sequence=segment.sequence,
                error=(
                    f"previous_hash mismatch at sequence {segment.sequence}: "
                    f"segment_id={segment.segment_id} "
                    f"expected={expected_previous!r} "
                    f"got={segment.previous_hash!r}"
                ),
            )

        # Recompute and verify hash
        expected_hash = compute_segment_hash(
            dataclasses.replace(segment, segment_hash=""),
            signing_key,
        )
        if segment.segment_hash != expected_hash:
            return ChainValidationResult(
                valid=False,
                total_segments=len(segments),
                broken_at_sequence=segment.sequence,
                error=(
                    f"segment_hash mismatch at sequence {segment.sequence}: "
                    f"segment_id={segment.segment_id}"
                ),
            )

        # Check monotonic sequence
        if idx > 0 and segment.sequence <= segments[idx - 1].sequence:
            return ChainValidationResult(
                valid=False,
                total_segments=len(segments),
                broken_at_sequence=segment.sequence,
                error=(
                    f"non-monotonic sequence at index {idx}: "
                    f"sequence={segment.sequence} "
                    f"previous_sequence={segments[idx - 1].sequence}"
                ),
            )

        expected_previous = segment.segment_hash

    return ChainValidationResult(
        valid=True,
        total_segments=len(segments),
        broken_at_sequence=None,
        error=None,
    )


@dataclasses.dataclass
class ChainValidationResult:
    """Result of a segment chain integrity verification."""
    valid: bool
    total_segments: int
    broken_at_sequence: Optional[int]
    error: Optional[str]


def _serialize_metadata(metadata: Optional[dict]) -> str:
    """Deterministically serialize metadata for hash computation."""
    if metadata is None:
        return "null"
    import json
    return json.dumps(metadata, sort_keys=True, separators=(",", ":"))
