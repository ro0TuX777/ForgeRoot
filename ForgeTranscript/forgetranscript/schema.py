"""
ForgeTranscript schema definitions.

Defines the core data structures for agent reasoning observability:
- TranscriptSession: top-level container bound 1:1 to a CONCORD session
- TranscriptSegment: individual unit of agent output, typed and classified
- SegmentType: classification taxonomy for segment content
- SessionStatus: lifecycle states of a transcript session

All structures are immutable dataclasses designed for HMAC-SHA256 chaining
via the ForgeLedger evidence infrastructure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


TRANSCRIPT_VERSION = "0.1"


class SegmentType(str, Enum):
    """Classification taxonomy for transcript segments.

    Each segment type maps to a specific observability need identified
    in the five ForgeTranscript use cases:

    UC1 (Forensics):    REASONING, REJECTION, TOOL_CALL, TOOL_RESULT, ERROR
    UC2 (Compliance):   REASONING, PROPOSAL, DECISION_REF, COMPREHENSION
    UC3 (Quality):      REASONING, REJECTION, TOOL_CALL, SYSTEM_EVENT
    UC4 (Awareness):    All types — live-streamed to operator dashboard
    UC5 (Collaboration): TOOL_RESULT → REASONING handoffs across sessions
    """
    REASONING      = "reasoning"       # Chain-of-thought, planning, deliberation
    PROPOSAL       = "proposal"        # Concrete action proposals before ForgeGate
    TOOL_CALL      = "tool_call"       # Tool invocation request + parameters
    TOOL_RESULT    = "tool_result"     # Tool execution output returned to agent
    USER_EXCHANGE  = "user_exchange"   # Natural-language messages agent ↔ operator
    DECISION_REF   = "decision_ref"   # Inline reference to ForgeGate DecisionRecord
    COMPREHENSION  = "comprehension"  # ComprehensionReview from Azul verification
    SYSTEM_EVENT   = "system_event"   # Budget warnings, trust changes, circuit-breakers
    REJECTION      = "rejection"      # Discarded alternatives with agent's stated reason
    ERROR          = "error"          # Failures, exceptions, recovery attempts


class SessionStatus(str, Enum):
    """Lifecycle states of a transcript session.

    State machine:
        ACTIVE → SEALED     (normal termination)
        ACTIVE → REVOKED    (CONCORD revocation — UC1 forensics)
        SEALED is terminal  (session complete, transcript immutable)
        REVOKED is terminal (session killed, transcript preserved for forensics)
    """
    ACTIVE  = "active"   # Session is open, segments are being captured
    SEALED  = "sealed"   # Session completed normally, transcript is finalized
    REVOKED = "revoked"  # Session was revoked by CONCORD mid-execution


@dataclass(frozen=True)
class TranscriptSegment:
    """A single, immutable unit of agent output within a transcript session.

    Each segment is typed, timestamped, and chained to its predecessor via
    HMAC-SHA256. The chain extends ForgeLedger's evidence model to provide
    tamper-evident cognitive traceability.

    Attributes:
        segment_id: Unique identifier for this segment.
        session_id: Parent TranscriptSession identifier.
        sequence: Monotonically increasing position within the session.
        segment_type: Classification from the SegmentType taxonomy.
        timestamp: ISO 8601 UTC timestamp of capture.
        content: The raw content of the segment (reasoning text, tool args, etc.).
        metadata: Optional structured metadata (tool name, decision_record_id, etc.).
        source_module: ForgeRoot subsystem that generated this segment.
        previous_hash: HMAC-SHA256 hash of the preceding segment (None for first).
        segment_hash: HMAC-SHA256 hash of this segment's content.
        redacted: Whether content was redacted at ingest time.
        redaction_receipt_hash: SHA-256 of original content if redacted.
    """
    segment_id: str
    session_id: str
    sequence: int
    segment_type: SegmentType
    timestamp: str
    content: str
    metadata: Optional[dict] = None
    source_module: str = "ForgeTranscript"
    previous_hash: Optional[str] = None
    segment_hash: str = ""
    redacted: bool = False
    redaction_receipt_hash: Optional[str] = None


@dataclass
class TranscriptSession:
    """Top-level container for an agent's transcript, bound 1:1 to a CONCORD session.

    Lifecycle:
        - Opened when CONCORD issues an admission receipt
        - Segments are appended as the agent operates
        - Sealed when the session terminates normally
        - Revoked if CONCORD revokes the session mid-execution

    Attributes:
        transcript_id: Unique identifier for this transcript.
        session_id: CONCORD session identifier (1:1 binding).
        agent_id: Identifier of the agent whose output is being captured.
        trust_tier: Agent's trust tier at session start (e.g., "T1", "T2", "T3").
        status: Current lifecycle state of the session.
        opened_at: ISO 8601 UTC timestamp when the session was opened.
        sealed_at: ISO 8601 UTC timestamp when the session was sealed/revoked.
        segment_count: Number of segments captured so far.
        chain_head: Hash of the most recent segment in the chain.
        workflow_id: Optional shared workflow ID for cross-agent tracing (UC5).
        transcript_version: Schema version for forward compatibility.
    """
    transcript_id: str
    session_id: str
    agent_id: str
    trust_tier: str
    status: SessionStatus = SessionStatus.ACTIVE
    opened_at: str = ""
    sealed_at: Optional[str] = None
    segment_count: int = 0
    chain_head: Optional[str] = None
    workflow_id: Optional[str] = None
    transcript_version: str = TRANSCRIPT_VERSION


@dataclass
class TranscriptQuery:
    """Query parameters for retrieving transcript segments.

    Supports all five use cases:
        UC1: Filter by session_id of a revoked session
        UC2: Filter by segment_types=[REASONING, PROPOSAL, DECISION_REF]
        UC3: Filter by agent_id across time range for pattern analysis
        UC4: Filter by status=ACTIVE for live monitoring
        UC5: Filter by workflow_id for cross-agent timeline
    """
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    workflow_id: Optional[str] = None
    segment_types: Optional[list[SegmentType]] = None
    from_time: Optional[str] = None
    to_time: Optional[str] = None
    status_filter: Optional[SessionStatus] = None
    search_text: Optional[str] = None
    max_results: int = 1000
