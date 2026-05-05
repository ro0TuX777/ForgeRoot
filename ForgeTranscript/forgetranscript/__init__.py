"""
ForgeTranscript — Agent Reasoning Observability Subsystem for ForgeRoot.

Captures, indexes, and surfaces the full natural-language and tool-interaction
output of every governed agent session as a first-class, tamper-evident,
queryable transcript record.

Architecture position:
    Agent Runtime → ForgeTranscript Capture Layer → {TranscriptReader, ForgeLedger, SIEM}

Integration points:
    CONCORD  — SessionID anchors every transcript
    ForgeLedger — Segments are HMAC-SHA256 chained into the evidence trail
    ForgeGate — DecisionRecords are cross-referenced inline
    Azul — ComprehensionReviews are embedded in the transcript timeline
"""
from __future__ import annotations

__version__ = "0.1.0"

from forgetranscript.schema import (
    SegmentType,
    SessionStatus,
    TranscriptSegment,
    TranscriptSession,
)
from forgetranscript.emitter import TranscriptEmitter
from forgetranscript.session_manager import SessionManager
from forgetranscript.reader import TranscriptReader

__all__ = [
    "SegmentType",
    "SessionStatus",
    "TranscriptSegment",
    "TranscriptSession",
    "TranscriptEmitter",
    "SessionManager",
    "TranscriptReader",
]
