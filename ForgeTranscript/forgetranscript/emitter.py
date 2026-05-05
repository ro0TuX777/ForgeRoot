"""
TranscriptEmitter — capture layer for agent cognitive output.

Mirrors ForgeLedger's LedgerEmitter pattern with a ForgeTranscript-specific
emission pipeline:

    1. Build TranscriptSegment from raw agent output
    2. Classify segment type via SegmentClassifier
    3. Apply ingest-time redaction (if configured)
    4. Attach HMAC-SHA256 hash chain
    5. Persist to TranscriptStore (fail-closed)
    6. Optionally bridge to ForgeLedger for evidence chain integration

The emitter is the primary integration point for agent runtimes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from forgetranscript.hash_chain import attach_segment_hash
from forgetranscript.schema import SegmentType, TranscriptSegment

if TYPE_CHECKING:
    from forgetranscript.redaction import SegmentRedactor
    from forgetranscript.store import TranscriptStore


class TranscriptWriteFailedError(Exception):
    """Raised when the transcript store rejects a segment append.

    Following ForgeLedger's fail-closed principle: if the transcript
    record cannot be written, the caller must treat this as a hard failure.
    """

    def __init__(self, segment_id: str, error: str) -> None:
        super().__init__(f"Transcript write failed for segment {segment_id!r}: {error}")
        self.segment_id = segment_id
        self.backend_error = error


class TranscriptEmitter:
    """Capture layer that transforms raw agent output into chained transcript segments.

    This is the primary API for agent runtimes to emit cognitive output into
    ForgeTranscript. Each emit() call:

        1. Builds a TranscriptSegment with auto-generated ID and timestamp
        2. Applies redaction if configured (sensitive content removal)
        3. Computes and attaches HMAC-SHA256 hash linked to previous segment
        4. Persists to the configured TranscriptStore (fail-closed)

    Thread-safe: the emitter delegates thread safety to the underlying store.

    Usage:
        emitter = TranscriptEmitter(store=store, signing_key="session-key")

        emitter.emit(
            session_id="concord-session-7f2b",
            segment_type=SegmentType.REASONING,
            content="Analyzing target module for dependency conflicts...",
            trust_tier="T2",
        )
    """

    def __init__(
        self,
        store: TranscriptStore,
        signing_key: str,
        redactor: Optional[SegmentRedactor] = None,
        source_module: str = "ForgeTranscript",
    ) -> None:
        self._store = store
        self._signing_key = signing_key
        self._redactor = redactor
        self._source_module = source_module

    def emit(
        self,
        session_id: str,
        segment_type: SegmentType,
        content: str,
        trust_tier: str = "T2",
        metadata: Optional[dict] = None,
        source_module: Optional[str] = None,
    ) -> TranscriptSegment:
        """Capture a single unit of agent output as a chained transcript segment.

        Args:
            session_id: CONCORD session identifier the segment belongs to.
            segment_type: Classification of the content (REASONING, TOOL_CALL, etc.).
            content: Raw text content of the segment.
            trust_tier: Agent's trust tier (used for redaction policy).
            metadata: Optional structured data (tool name, decision_record_id, etc.).
            source_module: Override the default source module label.

        Returns:
            The persisted TranscriptSegment with hash chain attached.

        Raises:
            TranscriptWriteFailedError: If the store rejects the append (fail-closed).
        """
        segment_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        sequence = self._store.get_segment_count(session_id)
        previous_hash = self._store.get_chain_head(session_id)

        # Step 1: Build provisional segment
        segment = TranscriptSegment(
            segment_id=segment_id,
            session_id=session_id,
            sequence=sequence,
            segment_type=segment_type,
            timestamp=timestamp,
            content=content,
            metadata=metadata,
            source_module=source_module or self._source_module,
        )

        # Step 2: Apply redaction if configured
        if self._redactor is not None:
            segment, _receipts = self._redactor.redact(segment, trust_tier, timestamp)

        # Step 3: Attach HMAC-SHA256 hash chain
        segment = attach_segment_hash(segment, self._signing_key, previous_hash)

        # Step 4: Persist (fail-closed)
        result = self._store.append_segment(segment)
        if not result.success:
            raise TranscriptWriteFailedError(segment_id, result.error or "unknown store error")

        return segment

    def emit_reasoning(
        self, session_id: str, content: str, trust_tier: str = "T2",
    ) -> TranscriptSegment:
        """Convenience: emit a REASONING segment (agent chain-of-thought)."""
        return self.emit(session_id, SegmentType.REASONING, content, trust_tier)

    def emit_proposal(
        self, session_id: str, content: str, trust_tier: str = "T2",
        metadata: Optional[dict] = None,
    ) -> TranscriptSegment:
        """Convenience: emit a PROPOSAL segment (action proposal before ForgeGate)."""
        return self.emit(
            session_id, SegmentType.PROPOSAL, content, trust_tier, metadata,
            source_module="ForgeGate",
        )

    def emit_tool_call(
        self, session_id: str, tool_name: str, tool_args: dict,
        trust_tier: str = "T2",
    ) -> TranscriptSegment:
        """Convenience: emit a TOOL_CALL segment."""
        return self.emit(
            session_id, SegmentType.TOOL_CALL,
            content=f"Tool call: {tool_name}",
            trust_tier=trust_tier,
            metadata={"tool_name": tool_name, "tool_args": tool_args},
        )

    def emit_tool_result(
        self, session_id: str, tool_name: str, result: str,
        trust_tier: str = "T2",
    ) -> TranscriptSegment:
        """Convenience: emit a TOOL_RESULT segment."""
        return self.emit(
            session_id, SegmentType.TOOL_RESULT,
            content=result,
            trust_tier=trust_tier,
            metadata={"tool_name": tool_name},
        )

    def emit_user_exchange(
        self, session_id: str, direction: str, content: str,
        trust_tier: str = "T2",
    ) -> TranscriptSegment:
        """Convenience: emit a USER_EXCHANGE segment (agent ↔ operator message)."""
        return self.emit(
            session_id, SegmentType.USER_EXCHANGE,
            content=content,
            trust_tier=trust_tier,
            metadata={"direction": direction},  # "agent_to_user" or "user_to_agent"
        )

    def emit_decision_ref(
        self, session_id: str, decision_record_id: str, decision_type: str,
        summary: str, trust_tier: str = "T2",
    ) -> TranscriptSegment:
        """Convenience: emit a DECISION_REF segment (ForgeGate decision inline)."""
        return self.emit(
            session_id, SegmentType.DECISION_REF,
            content=f"ForgeGate: {decision_type} — {summary}",
            trust_tier=trust_tier,
            metadata={
                "decision_record_id": decision_record_id,
                "decision_type": decision_type,
            },
            source_module="ForgeGate",
        )

    def emit_comprehension(
        self, session_id: str, review_content: str, verdict: str,
        trust_tier: str = "T2",
    ) -> TranscriptSegment:
        """Convenience: emit a COMPREHENSION segment (Azul ComprehensionReview)."""
        return self.emit(
            session_id, SegmentType.COMPREHENSION,
            content=review_content,
            trust_tier=trust_tier,
            metadata={"verdict": verdict},
            source_module="Azul",
        )

    def emit_rejection(
        self, session_id: str, content: str, trust_tier: str = "T2",
    ) -> TranscriptSegment:
        """Convenience: emit a REJECTION segment (discarded alternative)."""
        return self.emit(session_id, SegmentType.REJECTION, content, trust_tier)

    def emit_system_event(
        self, session_id: str, event_type: str, content: str,
        trust_tier: str = "T2",
    ) -> TranscriptSegment:
        """Convenience: emit a SYSTEM_EVENT segment (budget, circuit-breaker, etc.)."""
        return self.emit(
            session_id, SegmentType.SYSTEM_EVENT,
            content=content,
            trust_tier=trust_tier,
            metadata={"event_type": event_type},
            source_module="CONCORD",
        )

    def emit_error(
        self, session_id: str, error_message: str, error_type: str = "unknown",
        trust_tier: str = "T2",
    ) -> TranscriptSegment:
        """Convenience: emit an ERROR segment (failure, exception, recovery)."""
        return self.emit(
            session_id, SegmentType.ERROR,
            content=error_message,
            trust_tier=trust_tier,
            metadata={"error_type": error_type},
        )
