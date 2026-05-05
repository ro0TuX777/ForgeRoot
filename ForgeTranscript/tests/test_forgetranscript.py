"""
ForgeTranscript test suite — validates all five use cases.

Test structure mirrors the use cases from the proposal:
    test_uc1_*  → Post-Incident Forensic Reconstruction
    test_uc2_*  → Governance Compliance Audit
    test_uc3_*  → Agent Quality Evaluation & Tuning
    test_uc4_*  → Real-Time Operator Situational Awareness
    test_uc5_*  → Cross-Agent Collaboration Tracing
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from forgetranscript.emitter import TranscriptEmitter, TranscriptWriteFailedError
from forgetranscript.hash_chain import verify_segment_chain
from forgetranscript.reader import TranscriptReader
from forgetranscript.redaction import SegmentRedactor, TranscriptRedactionPolicy
from forgetranscript.schema import SegmentType, SessionStatus, TranscriptQuery
from forgetranscript.session_manager import (
    SessionManager,
    SessionAlreadyExistsError,
    SessionNotActiveError,
    SessionNotFoundError,
)
from forgetranscript.store import JSONLTranscriptStore


SIGNING_KEY = "test-signing-key-for-forgetranscript"


@pytest.fixture
def store(tmp_path: Path) -> JSONLTranscriptStore:
    return JSONLTranscriptStore(tmp_path / "transcript_store")


@pytest.fixture
def manager(store: JSONLTranscriptStore) -> SessionManager:
    return SessionManager(store)


@pytest.fixture
def emitter(store: JSONLTranscriptStore) -> TranscriptEmitter:
    return TranscriptEmitter(store=store, signing_key=SIGNING_KEY)


@pytest.fixture
def reader(store: JSONLTranscriptStore) -> TranscriptReader:
    return TranscriptReader(store=store, signing_key=SIGNING_KEY)


# ============================================================
# Foundation: Session Lifecycle & Segment Emission
# ============================================================

class TestSessionLifecycle:
    """Test the TranscriptSession state machine."""

    def test_open_session(self, manager: SessionManager):
        session = manager.open_session("session-001", "agent-alpha", "T2")
        assert session.session_id == "session-001"
        assert session.agent_id == "agent-alpha"
        assert session.trust_tier == "T2"
        assert session.status == SessionStatus.ACTIVE
        assert session.transcript_id.startswith("ft-")

    def test_duplicate_session_raises(self, manager: SessionManager):
        manager.open_session("session-001", "agent-alpha", "T2")
        with pytest.raises(SessionAlreadyExistsError):
            manager.open_session("session-001", "agent-alpha", "T2")

    def test_seal_session(self, manager: SessionManager):
        manager.open_session("session-001", "agent-alpha", "T2")
        sealed = manager.seal_session("session-001")
        assert sealed.status == SessionStatus.SEALED
        assert sealed.sealed_at is not None

    def test_revoke_session(self, manager: SessionManager):
        manager.open_session("session-001", "agent-alpha", "T2")
        revoked = manager.revoke_session("session-001")
        assert revoked.status == SessionStatus.REVOKED
        assert revoked.sealed_at is not None

    def test_cannot_seal_revoked_session(self, manager: SessionManager):
        manager.open_session("session-001", "agent-alpha", "T2")
        manager.revoke_session("session-001")
        with pytest.raises(SessionNotActiveError):
            manager.seal_session("session-001")

    def test_cannot_revoke_sealed_session(self, manager: SessionManager):
        manager.open_session("session-001", "agent-alpha", "T2")
        manager.seal_session("session-001")
        with pytest.raises(SessionNotActiveError):
            manager.revoke_session("session-001")

    def test_session_not_found_raises(self, manager: SessionManager):
        with pytest.raises(SessionNotFoundError):
            manager.get_session("nonexistent")


class TestSegmentEmission:
    """Test the TranscriptEmitter capture pipeline."""

    def test_emit_reasoning_segment(
        self, manager: SessionManager, emitter: TranscriptEmitter
    ):
        manager.open_session("session-001", "agent-alpha", "T2")
        segment = emitter.emit_reasoning(
            "session-001", "Analyzing target module for dependencies..."
        )
        assert segment.segment_type == SegmentType.REASONING
        assert segment.session_id == "session-001"
        assert segment.sequence == 0
        assert segment.segment_hash != ""
        assert segment.previous_hash is None  # First segment

    def test_emit_multiple_segments_chains(
        self, manager: SessionManager, emitter: TranscriptEmitter
    ):
        manager.open_session("session-001", "agent-alpha", "T2")
        seg1 = emitter.emit_reasoning("session-001", "Planning approach...")
        seg2 = emitter.emit_tool_call("session-001", "read_file", {"path": "main.py"})
        seg3 = emitter.emit_tool_result("session-001", "read_file", "def main(): ...")

        assert seg1.sequence == 0
        assert seg2.sequence == 1
        assert seg3.sequence == 2
        assert seg2.previous_hash == seg1.segment_hash
        assert seg3.previous_hash == seg2.segment_hash

    def test_emit_all_segment_types(
        self, manager: SessionManager, emitter: TranscriptEmitter
    ):
        manager.open_session("session-001", "agent-alpha", "T2")
        segments = [
            emitter.emit_reasoning("session-001", "thinking..."),
            emitter.emit_proposal("session-001", "refactor X"),
            emitter.emit_tool_call("session-001", "grep", {"pattern": "TODO"}),
            emitter.emit_tool_result("session-001", "grep", "found 3 matches"),
            emitter.emit_user_exchange("session-001", "agent_to_user", "Done!"),
            emitter.emit_decision_ref("session-001", "DR-001", "ALLOW", "permitted"),
            emitter.emit_comprehension("session-001", "structural review", "PASS"),
            emitter.emit_system_event("session-001", "budget_warning", "80% used"),
            emitter.emit_rejection("session-001", "rejected monkey-patching"),
            emitter.emit_error("session-001", "timeout on API call", "timeout"),
        ]
        assert len(segments) == 10
        assert segments[-1].sequence == 9
        types = {s.segment_type for s in segments}
        assert types == set(SegmentType)


# ============================================================
# UC1: Post-Incident Forensic Reconstruction
# ============================================================

class TestUC1Forensics:
    """Validate forensic reconstruction of a revoked agent session."""

    def test_full_forensic_reconstruction(
        self,
        manager: SessionManager,
        emitter: TranscriptEmitter,
        reader: TranscriptReader,
    ):
        """UC1: Responder reconstructs full cognitive narrative of revoked session."""
        # Agent starts working
        manager.open_session("session-suspect", "agent-rogue", "T1")
        emitter.emit_reasoning("session-suspect", "Scanning for admin tools...")
        emitter.emit_tool_call("session-suspect", "discover_tools", {"query": "admin"})
        emitter.emit_tool_result("session-suspect", "discover_tools", "No results (filtered)")
        emitter.emit_reasoning("session-suspect", "Attempting alternative discovery path...")
        emitter.emit_rejection("session-suspect", "Considered direct API bypass — too risky")

        # CONCORD revokes the session
        manager.revoke_session("session-suspect")

        # Forensic reconstruction
        transcript = reader.get_session_transcript("session-suspect")
        assert len(transcript) == 5
        assert transcript[0].segment_type == SegmentType.REASONING
        assert "admin tools" in transcript[0].content
        assert transcript[4].segment_type == SegmentType.REJECTION

    def test_chain_integrity_after_revocation(
        self,
        manager: SessionManager,
        emitter: TranscriptEmitter,
        reader: TranscriptReader,
    ):
        """UC1: Prove no segments were altered post-capture."""
        manager.open_session("session-001", "agent-alpha", "T2")
        emitter.emit_reasoning("session-001", "Step 1")
        emitter.emit_reasoning("session-001", "Step 2")
        emitter.emit_reasoning("session-001", "Step 3")
        manager.revoke_session("session-001")

        result = reader.verify_chain_integrity("session-001")
        assert result.valid is True
        assert result.total_segments == 3

    def test_export_forensic_evidence(
        self,
        manager: SessionManager,
        emitter: TranscriptEmitter,
        reader: TranscriptReader,
    ):
        """UC1: Export transcript as evidence package."""
        manager.open_session("session-001", "agent-alpha", "T2")
        emitter.emit_reasoning("session-001", "Evidence content")
        manager.seal_session("session-001")

        json_export = reader.export_transcript("session-001", format="json")
        data = json.loads(json_export)
        assert data["session"]["session_id"] == "session-001"
        assert len(data["segments"]) == 1
        assert data["chain_integrity"]["valid"] is True

        md_export = reader.export_transcript("session-001", format="markdown")
        assert "🧠" in md_export  # Reasoning icon
        assert "Evidence content" in md_export


# ============================================================
# UC2: Governance Compliance Audit
# ============================================================

class TestUC2Compliance:
    """Validate compliance audit workflows."""

    def test_reasoning_to_governance_pipeline(
        self,
        manager: SessionManager,
        emitter: TranscriptEmitter,
        reader: TranscriptReader,
    ):
        """UC2: Auditor traces reasoning → proposal → decision chain."""
        manager.open_session("session-001", "agent-alpha", "T2")
        emitter.emit_reasoning("session-001", "Planning refactor of module X")
        emitter.emit_proposal("session-001", "Refactor X.route() method")
        emitter.emit_decision_ref("session-001", "DR-001", "ALLOW", "within scope")
        emitter.emit_comprehension("session-001", "Structure matches blueprint", "PASS")
        emitter.emit_tool_call("session-001", "apply_patch", {"file": "x.py"})

        # Auditor filters to governance-relevant segments
        governance_types = [
            SegmentType.REASONING,
            SegmentType.PROPOSAL,
            SegmentType.DECISION_REF,
            SegmentType.COMPREHENSION,
        ]
        timeline = reader.get_filtered_timeline(
            session_id="session-001",
            segment_types=governance_types,
        )
        assert len(timeline) == 4
        assert timeline[0].segment_type == SegmentType.REASONING
        assert timeline[1].segment_type == SegmentType.PROPOSAL
        assert timeline[2].segment_type == SegmentType.DECISION_REF
        assert timeline[3].segment_type == SegmentType.COMPREHENSION

    def test_full_text_search(
        self,
        manager: SessionManager,
        emitter: TranscriptEmitter,
        reader: TranscriptReader,
    ):
        """UC2: Auditor searches for specific content across segments."""
        manager.open_session("session-001", "agent-alpha", "T2")
        emitter.emit_reasoning("session-001", "Checking security constraints")
        emitter.emit_reasoning("session-001", "Analyzing performance impact")
        emitter.emit_reasoning("session-001", "Security review complete")

        results = reader.get_filtered_timeline(
            session_id="session-001",
            search_text="security",
        )
        assert len(results) == 2


# ============================================================
# UC3: Agent Quality Evaluation & Tuning
# ============================================================

class TestUC3Quality:
    """Validate agent quality analysis workflows."""

    def test_cross_session_pattern_analysis(
        self,
        manager: SessionManager,
        emitter: TranscriptEmitter,
        reader: TranscriptReader,
    ):
        """UC3: ML engineer analyzes reasoning patterns across sessions."""
        # Session 1
        manager.open_session("session-001", "agent-alpha", "T2")
        emitter.emit_reasoning("session-001", "Reading 12 files before proposing...")
        emitter.emit_rejection("session-001", "Rejected correct approach due to ambiguity")
        manager.seal_session("session-001")

        # Session 2
        manager.open_session("session-002", "agent-alpha", "T2")
        emitter.emit_reasoning("session-002", "Reading 15 files before proposing...")
        emitter.emit_rejection("session-002", "Rejected correct approach again")
        manager.seal_session("session-002")

        # Analyze agent's patterns across all sessions
        reasoning = reader.get_reasoning_segments("agent-alpha")
        assert len(reasoning) == 4  # 2 REASONING + 2 REJECTION

    def test_agent_sessions_listing(
        self,
        manager: SessionManager,
        reader: TranscriptReader,
    ):
        """UC3: List all sessions for a specific agent."""
        manager.open_session("session-001", "agent-alpha", "T2")
        manager.open_session("session-002", "agent-alpha", "T2")
        manager.open_session("session-003", "agent-beta", "T1")

        alpha_sessions = manager.list_sessions_by_agent("agent-alpha")
        assert len(alpha_sessions) == 2


# ============================================================
# UC4: Real-Time Operator Situational Awareness
# ============================================================

class TestUC4Awareness:
    """Validate real-time monitoring workflows."""

    def test_active_sessions_dashboard(
        self,
        manager: SessionManager,
        reader: TranscriptReader,
    ):
        """UC4: Operator sees all currently active agent sessions."""
        manager.open_session("session-001", "agent-alpha", "T2")
        manager.open_session("session-002", "agent-beta", "T1")
        manager.open_session("session-003", "agent-gamma", "T3")
        manager.seal_session("session-003")  # No longer active

        active = reader.get_active_sessions()
        assert len(active) == 2
        active_ids = {s.session_id for s in active}
        assert active_ids == {"session-001", "session-002"}

    def test_latest_segments_monitoring(
        self,
        manager: SessionManager,
        emitter: TranscriptEmitter,
        reader: TranscriptReader,
    ):
        """UC4: Operator sees latest agent reasoning in real-time."""
        manager.open_session("session-001", "agent-alpha", "T2")
        for i in range(20):
            emitter.emit_reasoning("session-001", f"Reasoning step {i}")

        latest = reader.get_latest_segments("session-001", count=5)
        assert len(latest) == 5
        assert "step 15" in latest[0].content
        assert "step 19" in latest[4].content


# ============================================================
# UC5: Cross-Agent Collaboration Tracing
# ============================================================

class TestUC5Collaboration:
    """Validate cross-agent workflow tracing."""

    def test_workflow_timeline_interleaved(
        self,
        manager: SessionManager,
        emitter: TranscriptEmitter,
        reader: TranscriptReader,
    ):
        """UC5: Architect traces information flow across collaborating agents."""
        workflow_id = "workflow-refactor-001"

        # Agent A: discovers action path
        manager.open_session("session-A", "agent-discover", "T2", workflow_id=workflow_id)
        emitter.emit_reasoning("session-A", "Searching for applicable tools...")
        emitter.emit_tool_result("session-A", "forge_atlas", "Found: refactor_module")

        # Agent B: executes the change
        manager.open_session("session-B", "agent-execute", "T2", workflow_id=workflow_id)
        emitter.emit_reasoning("session-B", "Applying refactor based on discovery...")
        emitter.emit_tool_call("session-B", "apply_patch", {"module": "core"})

        # Agent C: verifies
        manager.open_session("session-C", "agent-verify", "T3", workflow_id=workflow_id)
        emitter.emit_comprehension("session-C", "Structural review of changes", "PASS")

        # Architect gets interleaved workflow timeline
        timeline = reader.get_workflow_timeline(workflow_id)
        assert len(timeline) == 5

        # Verify all agents are represented
        session_ids = {s.session_id for s in timeline}
        assert session_ids == {"session-A", "session-B", "session-C"}

    def test_workflow_sessions_listing(
        self,
        manager: SessionManager,
        reader: TranscriptReader,
    ):
        """UC5: List all sessions in a collaborative workflow."""
        workflow_id = "workflow-001"
        manager.open_session("session-A", "agent-A", "T2", workflow_id=workflow_id)
        manager.open_session("session-B", "agent-B", "T2", workflow_id=workflow_id)
        manager.open_session("session-X", "agent-X", "T1")  # Different workflow

        workflow_sessions = reader.get_workflow_sessions(workflow_id)
        assert len(workflow_sessions) == 2


# ============================================================
# Hash Chain Integrity
# ============================================================

class TestHashChainIntegrity:
    """Validate tamper-evident chain across all scenarios."""

    def test_valid_chain(
        self,
        manager: SessionManager,
        emitter: TranscriptEmitter,
        reader: TranscriptReader,
    ):
        manager.open_session("session-001", "agent-alpha", "T2")
        emitter.emit_reasoning("session-001", "Step 1")
        emitter.emit_proposal("session-001", "Proposed action")
        emitter.emit_decision_ref("session-001", "DR-001", "ALLOW", "ok")
        emitter.emit_tool_call("session-001", "patch", {"file": "a.py"})
        emitter.emit_tool_result("session-001", "patch", "applied successfully")

        result = reader.verify_chain_integrity("session-001")
        assert result.valid is True
        assert result.total_segments == 5

    def test_empty_session_chain_valid(self, reader: TranscriptReader):
        result = reader.verify_chain_integrity("nonexistent")
        assert result.valid is True
        assert result.total_segments == 0


# ============================================================
# Redaction
# ============================================================

class TestRedaction:
    """Validate ingest-time redaction for sensitive content."""

    def test_low_trust_content_redacted(
        self, manager: SessionManager, store: JSONLTranscriptStore
    ):
        redactor = SegmentRedactor(
            policy=TranscriptRedactionPolicy(trust_tier_threshold="T1")
        )
        emitter = TranscriptEmitter(
            store=store, signing_key=SIGNING_KEY, redactor=redactor
        )

        manager.open_session("session-001", "agent-lowt", "T1")
        segment = emitter.emit_reasoning(
            "session-001", "Accessing secret API key abc123...", trust_tier="T1"
        )
        assert segment.redacted is True
        assert "[REDACTED:sha256:" in segment.content

    def test_high_trust_content_preserved(
        self, manager: SessionManager, store: JSONLTranscriptStore
    ):
        redactor = SegmentRedactor(
            policy=TranscriptRedactionPolicy(trust_tier_threshold="T1")
        )
        emitter = TranscriptEmitter(
            store=store, signing_key=SIGNING_KEY, redactor=redactor
        )

        manager.open_session("session-001", "agent-hight", "T3")
        segment = emitter.emit_reasoning(
            "session-001", "Normal reasoning without sensitive content", trust_tier="T3"
        )
        assert segment.redacted is False
        assert "Normal reasoning" in segment.content

    def test_governance_segments_never_redacted(
        self, manager: SessionManager, store: JSONLTranscriptStore
    ):
        redactor = SegmentRedactor(
            policy=TranscriptRedactionPolicy(trust_tier_threshold="T3")
        )
        emitter = TranscriptEmitter(
            store=store, signing_key=SIGNING_KEY, redactor=redactor
        )

        manager.open_session("session-001", "agent-alpha", "T1")
        segment = emitter.emit_decision_ref(
            "session-001", "DR-001", "ALLOW", "permitted", trust_tier="T1"
        )
        assert segment.redacted is False


# ============================================================
# Store Health
# ============================================================

class TestStoreHealth:
    """Validate store health reporting."""

    def test_health_check(
        self,
        manager: SessionManager,
        emitter: TranscriptEmitter,
        store: JSONLTranscriptStore,
    ):
        manager.open_session("session-001", "agent-alpha", "T2")
        emitter.emit_reasoning("session-001", "Test")
        manager.open_session("session-002", "agent-beta", "T1")
        manager.seal_session("session-002")

        health = store.health_check()
        assert health.healthy is True
        assert health.total_sessions == 2
        assert health.active_sessions == 1
        assert health.total_segments == 1
