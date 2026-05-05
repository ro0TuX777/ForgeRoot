"""
TranscriptReader — query and analysis interface for ForgeTranscript.

Provides the API surface that powers the TranscriptReader UI and
programmatic access to transcript data. Supports all five use cases:

    UC1 (Forensics):      get_session_transcript(), verify_chain_integrity()
    UC2 (Compliance):     get_filtered_timeline(), export_transcript()
    UC3 (Quality):        get_agent_patterns(), get_reasoning_segments()
    UC4 (Awareness):      get_active_sessions(), get_latest_segments()
    UC5 (Collaboration):  get_workflow_timeline()
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from forgetranscript.hash_chain import verify_segment_chain, ChainValidationResult
from forgetranscript.schema import (
    SegmentType,
    SessionStatus,
    TranscriptQuery,
    TranscriptSegment,
    TranscriptSession,
)
from forgetranscript.store import TranscriptStore


class TranscriptReader:
    """Read-only query interface for ForgeTranscript data.

    This class provides the backend API for the TranscriptReader UI
    and programmatic analysis tools. It does not modify any data.

    Usage:
        reader = TranscriptReader(store=store, signing_key="session-key")

        # UC1: Forensic reconstruction of a revoked session
        transcript = reader.get_session_transcript("concord-session-7f2b")
        integrity = reader.verify_chain_integrity("concord-session-7f2b")

        # UC2: Compliance audit — reasoning-to-governance pipeline
        timeline = reader.get_filtered_timeline(
            session_id="concord-session-7f2b",
            segment_types=[SegmentType.REASONING, SegmentType.PROPOSAL, SegmentType.DECISION_REF],
        )

        # UC5: Cross-agent collaboration tracing
        workflow_timeline = reader.get_workflow_timeline("workflow-abc123")
    """

    def __init__(self, store: TranscriptStore, signing_key: str) -> None:
        self._store = store
        self._signing_key = signing_key

    # --- UC1: Post-Incident Forensic Reconstruction ---

    def get_session_transcript(self, session_id: str) -> list[TranscriptSegment]:
        """Retrieve the complete, ordered transcript for a session.

        Returns all segments in chronological order. For forensic
        reconstruction (UC1), this provides the full cognitive narrative.
        """
        query = TranscriptQuery(session_id=session_id)
        return self._store.read_segments(query)

    def verify_chain_integrity(self, session_id: str) -> ChainValidationResult:
        """Verify the HMAC-SHA256 chain integrity of a session's transcript.

        Returns a ChainValidationResult indicating whether the chain is
        intact. A broken chain means segments were tampered with post-capture.

        Used by:
            UC1: Incident responder proving transcript wasn't altered
            UC2: Auditor verifying evidence integrity
        """
        segments = self.get_session_transcript(session_id)
        return verify_segment_chain(segments, self._signing_key)

    # --- UC2: Governance Compliance Audit ---

    def get_filtered_timeline(
        self,
        session_id: Optional[str] = None,
        segment_types: Optional[list[SegmentType]] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        search_text: Optional[str] = None,
        max_results: int = 1000,
    ) -> list[TranscriptSegment]:
        """Retrieve segments matching filter criteria.

        This is the primary query method for the TranscriptReader UI,
        supporting type-based filtering, time ranges, and full-text search.

        For compliance (UC2), auditors typically filter to:
            [REASONING, PROPOSAL, DECISION_REF, COMPREHENSION]
        to see the cognitive-to-governance pipeline.
        """
        query = TranscriptQuery(
            session_id=session_id,
            segment_types=segment_types,
            from_time=from_time,
            to_time=to_time,
            search_text=search_text,
            max_results=max_results,
        )
        return self._store.read_segments(query)

    # --- UC3: Agent Quality Evaluation & Tuning ---

    def get_agent_patterns(
        self,
        agent_id: str,
        segment_types: Optional[list[SegmentType]] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
    ) -> list[TranscriptSegment]:
        """Retrieve all segments for an agent across all sessions.

        Used by UC3 for pattern analysis: identifying reasoning
        inefficiencies, dead ends, and tool-use anti-patterns.
        """
        query = TranscriptQuery(
            agent_id=agent_id,
            segment_types=segment_types,
            from_time=from_time,
            to_time=to_time,
        )
        return self._store.read_segments(query)

    def get_reasoning_segments(self, agent_id: str) -> list[TranscriptSegment]:
        """Convenience: get all REASONING + REJECTION segments for an agent.

        UC3 shortcut for studying the agent's decision-making quality.
        """
        return self.get_agent_patterns(
            agent_id=agent_id,
            segment_types=[SegmentType.REASONING, SegmentType.REJECTION],
        )

    # --- UC4: Real-Time Operator Situational Awareness ---

    def get_active_sessions(self) -> list[TranscriptSession]:
        """List all currently active transcript sessions.

        Used by UC4's operator dashboard to show all agents
        currently executing governed workflows.
        """
        return self._store.list_sessions(status=SessionStatus.ACTIVE)

    def get_latest_segments(
        self,
        session_id: str,
        count: int = 10,
    ) -> list[TranscriptSegment]:
        """Retrieve the N most recent segments from an active session.

        Used by UC4 for live monitoring: the operator sees the
        latest agent reasoning as it happens.
        """
        all_segments = self.get_session_transcript(session_id)
        return all_segments[-count:] if len(all_segments) > count else all_segments

    # --- UC5: Cross-Agent Collaboration Tracing ---

    def get_workflow_timeline(self, workflow_id: str) -> list[TranscriptSegment]:
        """Retrieve interleaved segments across all sessions in a workflow.

        Returns segments from all agents in the workflow, sorted
        chronologically. Used by UC5 for tracing information flow
        and identifying context loss at agent handoff boundaries.
        """
        query = TranscriptQuery(workflow_id=workflow_id)
        return self._store.read_segments(query)

    def get_workflow_sessions(self, workflow_id: str) -> list[TranscriptSession]:
        """List all sessions participating in a workflow.

        Used by UC5 to identify which agents are part of a
        multi-agent collaboration.
        """
        return self._store.list_sessions(workflow_id=workflow_id)

    # --- Export (UC2: Compliance) ---

    def export_transcript(
        self,
        session_id: str,
        format: str = "json",
    ) -> str:
        """Export a complete transcript for offline review.

        Supported formats:
            'json': Full segment data as JSON array
            'markdown': Human-readable timeline with segment labels

        Used by UC1 (forensic evidence package) and UC2 (compliance export).
        """
        segments = self.get_session_transcript(session_id)
        session = self._store.get_session(session_id)

        if format == "markdown":
            return self._export_markdown(session, segments)
        else:
            return self._export_json(session, segments)

    def _export_json(
        self,
        session: Optional[TranscriptSession],
        segments: list[TranscriptSegment],
    ) -> str:
        """Export as JSON with session metadata and segment array."""
        from forgetranscript.store import _session_to_dict, _segment_to_dict

        data = {
            "export_version": "0.1",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "session": _session_to_dict(session) if session else None,
            "segments": [_segment_to_dict(s) for s in segments],
            "chain_integrity": None,
        }

        # Include chain verification in export
        if segments:
            chain_result = verify_segment_chain(segments, self._signing_key)
            data["chain_integrity"] = {
                "valid": chain_result.valid,
                "total_segments": chain_result.total_segments,
                "error": chain_result.error,
            }

        return json.dumps(data, indent=2, ensure_ascii=False)

    def _export_markdown(
        self,
        session: Optional[TranscriptSession],
        segments: list[TranscriptSegment],
    ) -> str:
        """Export as human-readable Markdown timeline."""
        lines = ["# ForgeTranscript Export\n"]

        if session:
            lines.append(f"**Session:** {session.session_id}")
            lines.append(f"**Agent:** {session.agent_id}")
            lines.append(f"**Trust Tier:** {session.trust_tier}")
            lines.append(f"**Status:** {session.status.value}")
            lines.append(f"**Opened:** {session.opened_at}")
            if session.sealed_at:
                lines.append(f"**Sealed:** {session.sealed_at}")
            lines.append(f"**Segments:** {session.segment_count}")
            lines.append("")
            lines.append("---\n")

        _type_icons = {
            SegmentType.REASONING: "🧠",
            SegmentType.PROPOSAL: "📋",
            SegmentType.TOOL_CALL: "🔧",
            SegmentType.TOOL_RESULT: "📤",
            SegmentType.USER_EXCHANGE: "💬",
            SegmentType.DECISION_REF: "⚖️",
            SegmentType.COMPREHENSION: "🔍",
            SegmentType.SYSTEM_EVENT: "⚙️",
            SegmentType.REJECTION: "❌",
            SegmentType.ERROR: "🚨",
        }

        for seg in segments:
            icon = _type_icons.get(seg.segment_type, "•")
            label = seg.segment_type.value.upper()
            time_short = seg.timestamp.split("T")[1][:8] if "T" in seg.timestamp else seg.timestamp
            redacted_marker = " [REDACTED]" if seg.redacted else ""

            lines.append(f"### {time_short} {icon} [{label}]{redacted_marker}")
            lines.append("")

            if seg.source_module != "ForgeTranscript":
                lines.append(f"*Source: {seg.source_module}*\n")

            lines.append(f"{seg.content}")
            lines.append("")

            if seg.metadata:
                lines.append(f"<details><summary>Metadata</summary>\n")
                lines.append(f"```json\n{json.dumps(seg.metadata, indent=2)}\n```\n")
                lines.append(f"</details>\n")

            lines.append("---\n")

        return "\n".join(lines)
