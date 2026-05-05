"""
Append-only storage backend for ForgeTranscript sessions and segments.

Follows ForgeLedger's LedgerBackend pattern with an abstract base class
and a concrete JSONL implementation for local/testing use.

Design principles:
    - Append-only: segments can never be modified or deleted after write
    - Session-indexed: segments are stored per-session for efficient retrieval
    - Chain-aware: tracks chain_head per session for hash chain continuation
"""
from __future__ import annotations

import json
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from forgetranscript.schema import (
    SegmentType,
    SessionStatus,
    TranscriptQuery,
    TranscriptSegment,
    TranscriptSession,
)


@dataclass
class AppendSegmentResult:
    """Result of appending a segment to the store."""
    success: bool
    segment_id: str
    segment_hash: str
    sequence: int
    error: Optional[str] = None


@dataclass
class StoreHealthReport:
    """Health status of the transcript store."""
    healthy: bool
    total_sessions: int
    active_sessions: int
    total_segments: int
    error: Optional[str] = None


class TranscriptStore(ABC):
    """Abstract base class for transcript storage backends."""

    @abstractmethod
    def create_session(self, session: TranscriptSession) -> TranscriptSession:
        """Persist a new transcript session. Raises if session_id already exists."""
        ...

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[TranscriptSession]:
        """Retrieve a session by its CONCORD session_id."""
        ...

    @abstractmethod
    def update_session_status(
        self,
        session_id: str,
        status: SessionStatus,
        sealed_at: Optional[str] = None,
    ) -> TranscriptSession:
        """Update session lifecycle status (seal or revoke)."""
        ...

    @abstractmethod
    def list_sessions(
        self,
        status: Optional[SessionStatus] = None,
        agent_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> list[TranscriptSession]:
        """List sessions with optional filtering."""
        ...

    @abstractmethod
    def append_segment(self, segment: TranscriptSegment) -> AppendSegmentResult:
        """Append a segment to the store. Append-only: no updates or deletes."""
        ...

    @abstractmethod
    def read_segments(self, query: TranscriptQuery) -> list[TranscriptSegment]:
        """Read segments matching the query parameters."""
        ...

    @abstractmethod
    def get_chain_head(self, session_id: str) -> Optional[str]:
        """Get the hash of the most recent segment in a session's chain."""
        ...

    @abstractmethod
    def get_segment_count(self, session_id: str) -> int:
        """Get the number of segments in a session."""
        ...

    @abstractmethod
    def health_check(self) -> StoreHealthReport:
        """Return the health status of the store."""
        ...


class JSONLTranscriptStore(TranscriptStore):
    """JSONL-based transcript store for local deployment and testing.

    Storage layout:
        base_dir/
        ├── sessions.jsonl          # One session record per line
        └── segments/
            ├── <session_id_1>.jsonl # One segment per line, append-only
            ├── <session_id_2>.jsonl
            └── ...

    Thread-safe via a reentrant lock.
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir)
        self._segments_dir = self._base_dir / "segments"
        self._sessions_file = self._base_dir / "sessions.jsonl"
        self._lock = threading.RLock()
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._segments_dir.mkdir(parents=True, exist_ok=True)

    def create_session(self, session: TranscriptSession) -> TranscriptSession:
        with self._lock:
            existing = self.get_session(session.session_id)
            if existing is not None:
                raise ValueError(f"Session {session.session_id!r} already exists")
            self._append_session_record(session)
            return session

    def get_session(self, session_id: str) -> Optional[TranscriptSession]:
        with self._lock:
            sessions = self._read_all_sessions()
            for s in sessions:
                if s.session_id == session_id:
                    return s
            return None

    def update_session_status(
        self,
        session_id: str,
        status: SessionStatus,
        sealed_at: Optional[str] = None,
    ) -> TranscriptSession:
        with self._lock:
            sessions = self._read_all_sessions()
            updated = None
            for i, s in enumerate(sessions):
                if s.session_id == session_id:
                    sessions[i] = TranscriptSession(
                        transcript_id=s.transcript_id,
                        session_id=s.session_id,
                        agent_id=s.agent_id,
                        trust_tier=s.trust_tier,
                        status=status,
                        opened_at=s.opened_at,
                        sealed_at=sealed_at or s.sealed_at,
                        segment_count=s.segment_count,
                        chain_head=s.chain_head,
                        workflow_id=s.workflow_id,
                        transcript_version=s.transcript_version,
                    )
                    updated = sessions[i]
                    break
            if updated is None:
                raise ValueError(f"Session {session_id!r} not found")
            self._rewrite_sessions(sessions)
            return updated

    def list_sessions(
        self,
        status: Optional[SessionStatus] = None,
        agent_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> list[TranscriptSession]:
        with self._lock:
            sessions = self._read_all_sessions()
            if status is not None:
                sessions = [s for s in sessions if s.status == status]
            if agent_id is not None:
                sessions = [s for s in sessions if s.agent_id == agent_id]
            if workflow_id is not None:
                sessions = [s for s in sessions if s.workflow_id == workflow_id]
            return sessions

    def append_segment(self, segment: TranscriptSegment) -> AppendSegmentResult:
        with self._lock:
            segment_file = self._segments_dir / f"{segment.session_id}.jsonl"
            try:
                record = _segment_to_dict(segment)
                with open(segment_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")

                # Update session's segment count and chain head
                sessions = self._read_all_sessions()
                for i, s in enumerate(sessions):
                    if s.session_id == segment.session_id:
                        sessions[i] = TranscriptSession(
                            transcript_id=s.transcript_id,
                            session_id=s.session_id,
                            agent_id=s.agent_id,
                            trust_tier=s.trust_tier,
                            status=s.status,
                            opened_at=s.opened_at,
                            sealed_at=s.sealed_at,
                            segment_count=s.segment_count + 1,
                            chain_head=segment.segment_hash,
                            workflow_id=s.workflow_id,
                            transcript_version=s.transcript_version,
                        )
                        break
                self._rewrite_sessions(sessions)

                return AppendSegmentResult(
                    success=True,
                    segment_id=segment.segment_id,
                    segment_hash=segment.segment_hash,
                    sequence=segment.sequence,
                )
            except Exception as e:
                return AppendSegmentResult(
                    success=False,
                    segment_id=segment.segment_id,
                    segment_hash=segment.segment_hash,
                    sequence=segment.sequence,
                    error=str(e),
                )

    def read_segments(self, query: TranscriptQuery) -> list[TranscriptSegment]:
        with self._lock:
            segments: list[TranscriptSegment] = []

            if query.session_id:
                segments = self._read_session_segments(query.session_id)
            elif query.workflow_id:
                # Cross-agent tracing (UC5): read segments across all sessions in workflow
                sessions = self.list_sessions(workflow_id=query.workflow_id)
                for s in sessions:
                    segments.extend(self._read_session_segments(s.session_id))
                segments.sort(key=lambda seg: seg.timestamp)
            elif query.agent_id:
                # Agent quality analysis (UC3): read segments across all agent's sessions
                sessions = self.list_sessions(agent_id=query.agent_id)
                for s in sessions:
                    segments.extend(self._read_session_segments(s.session_id))
                segments.sort(key=lambda seg: seg.timestamp)
            else:
                # Read all segments (expensive, capped by max_results)
                for seg_file in self._segments_dir.glob("*.jsonl"):
                    session_id = seg_file.stem
                    segments.extend(self._read_session_segments(session_id))
                segments.sort(key=lambda seg: seg.timestamp)

            # Apply filters
            if query.segment_types:
                type_values = {t.value if isinstance(t, SegmentType) else t for t in query.segment_types}
                segments = [s for s in segments if s.segment_type.value in type_values]

            if query.from_time:
                segments = [s for s in segments if s.timestamp >= query.from_time]

            if query.to_time:
                segments = [s for s in segments if s.timestamp <= query.to_time]

            if query.search_text:
                search_lower = query.search_text.lower()
                segments = [s for s in segments if search_lower in s.content.lower()]

            return segments[:query.max_results]

    def get_chain_head(self, session_id: str) -> Optional[str]:
        session = self.get_session(session_id)
        return session.chain_head if session else None

    def get_segment_count(self, session_id: str) -> int:
        session = self.get_session(session_id)
        return session.segment_count if session else 0

    def health_check(self) -> StoreHealthReport:
        try:
            sessions = self._read_all_sessions()
            active = sum(1 for s in sessions if s.status == SessionStatus.ACTIVE)
            total_segments = sum(s.segment_count for s in sessions)
            return StoreHealthReport(
                healthy=True,
                total_sessions=len(sessions),
                active_sessions=active,
                total_segments=total_segments,
            )
        except Exception as e:
            return StoreHealthReport(
                healthy=False,
                total_sessions=0,
                active_sessions=0,
                total_segments=0,
                error=str(e),
            )

    # --- Internal helpers ---

    def _append_session_record(self, session: TranscriptSession) -> None:
        record = _session_to_dict(session)
        with open(self._sessions_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")

    def _read_all_sessions(self) -> list[TranscriptSession]:
        if not self._sessions_file.exists():
            return []
        sessions = []
        with open(self._sessions_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    sessions.append(_session_from_dict(json.loads(line)))
        return sessions

    def _rewrite_sessions(self, sessions: list[TranscriptSession]) -> None:
        with open(self._sessions_file, "w", encoding="utf-8") as f:
            for s in sessions:
                f.write(json.dumps(_session_to_dict(s), sort_keys=True, ensure_ascii=False) + "\n")

    def _read_session_segments(self, session_id: str) -> list[TranscriptSegment]:
        segment_file = self._segments_dir / f"{session_id}.jsonl"
        if not segment_file.exists():
            return []
        segments = []
        with open(segment_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    segments.append(_segment_from_dict(json.loads(line)))
        return segments


# --- Serialization helpers ---

def _session_to_dict(session: TranscriptSession) -> dict:
    return {
        "transcript_id": session.transcript_id,
        "session_id": session.session_id,
        "agent_id": session.agent_id,
        "trust_tier": session.trust_tier,
        "status": session.status.value,
        "opened_at": session.opened_at,
        "sealed_at": session.sealed_at,
        "segment_count": session.segment_count,
        "chain_head": session.chain_head,
        "workflow_id": session.workflow_id,
        "transcript_version": session.transcript_version,
    }


def _session_from_dict(d: dict) -> TranscriptSession:
    return TranscriptSession(
        transcript_id=d["transcript_id"],
        session_id=d["session_id"],
        agent_id=d["agent_id"],
        trust_tier=d["trust_tier"],
        status=SessionStatus(d["status"]),
        opened_at=d["opened_at"],
        sealed_at=d.get("sealed_at"),
        segment_count=d.get("segment_count", 0),
        chain_head=d.get("chain_head"),
        workflow_id=d.get("workflow_id"),
        transcript_version=d.get("transcript_version", "0.1"),
    )


def _segment_to_dict(segment: TranscriptSegment) -> dict:
    return {
        "segment_id": segment.segment_id,
        "session_id": segment.session_id,
        "sequence": segment.sequence,
        "segment_type": segment.segment_type.value,
        "timestamp": segment.timestamp,
        "content": segment.content,
        "metadata": segment.metadata,
        "source_module": segment.source_module,
        "previous_hash": segment.previous_hash,
        "segment_hash": segment.segment_hash,
        "redacted": segment.redacted,
        "redaction_receipt_hash": segment.redaction_receipt_hash,
    }


def _segment_from_dict(d: dict) -> TranscriptSegment:
    return TranscriptSegment(
        segment_id=d["segment_id"],
        session_id=d["session_id"],
        sequence=d["sequence"],
        segment_type=SegmentType(d["segment_type"]),
        timestamp=d["timestamp"],
        content=d["content"],
        metadata=d.get("metadata"),
        source_module=d.get("source_module", "ForgeTranscript"),
        previous_hash=d.get("previous_hash"),
        segment_hash=d.get("segment_hash", ""),
        redacted=d.get("redacted", False),
        redaction_receipt_hash=d.get("redaction_receipt_hash"),
    )
