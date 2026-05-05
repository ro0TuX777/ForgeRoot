"""
SessionManager — lifecycle controller for ForgeTranscript sessions.

Manages the TranscriptSession state machine:
    ACTIVE → SEALED     (normal termination)
    ACTIVE → REVOKED    (CONCORD revocation)

Integration points:
    CONCORD admission receipt → open_session()
    CONCORD session termination → seal_session()
    CONCORD anomaly revocation → revoke_session() (UC1: forensics)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from forgetranscript.schema import SessionStatus, TranscriptSession
from forgetranscript.store import TranscriptStore


class SessionAlreadyExistsError(Exception):
    """Raised when attempting to open a session with a session_id that already exists."""


class SessionNotFoundError(Exception):
    """Raised when the requested session does not exist in the store."""


class SessionNotActiveError(Exception):
    """Raised when attempting to modify a session that is already sealed or revoked."""


class SessionManager:
    """Manages the lifecycle of ForgeTranscript sessions.

    Each TranscriptSession is bound 1:1 to a CONCORD-admitted session.
    The SessionManager enforces the state machine and provides the
    session-level operations needed by all five use cases.

    Usage:
        manager = SessionManager(store=store)

        # UC4: Open session when CONCORD admits an agent
        session = manager.open_session(
            session_id="concord-session-7f2b",
            agent_id="agent-alpha-01",
            trust_tier="T2",
        )

        # ... agent operates, emitter captures segments ...

        # Seal session on normal completion
        manager.seal_session("concord-session-7f2b")

        # OR revoke session on anomaly detection (UC1)
        manager.revoke_session("concord-session-7f2b")
    """

    def __init__(self, store: TranscriptStore) -> None:
        self._store = store

    def open_session(
        self,
        session_id: str,
        agent_id: str,
        trust_tier: str,
        workflow_id: Optional[str] = None,
    ) -> TranscriptSession:
        """Open a new transcript session bound to a CONCORD admission.

        Called when CONCORD issues an admission receipt. Creates the
        TranscriptSession container that will hold all segments captured
        during this agent's execution.

        Args:
            session_id: CONCORD session identifier (1:1 binding).
            agent_id: Identifier of the admitted agent.
            trust_tier: Agent's trust tier at admission time.
            workflow_id: Optional shared workflow ID for cross-agent tracing (UC5).

        Returns:
            The newly created TranscriptSession.

        Raises:
            SessionAlreadyExistsError: If a session with this ID already exists.
        """
        transcript_id = f"ft-{uuid.uuid4().hex[:12]}"
        opened_at = datetime.now(timezone.utc).isoformat()

        session = TranscriptSession(
            transcript_id=transcript_id,
            session_id=session_id,
            agent_id=agent_id,
            trust_tier=trust_tier,
            status=SessionStatus.ACTIVE,
            opened_at=opened_at,
            workflow_id=workflow_id,
        )

        try:
            return self._store.create_session(session)
        except ValueError as e:
            raise SessionAlreadyExistsError(str(e)) from e

    def seal_session(self, session_id: str) -> TranscriptSession:
        """Seal a session on normal completion.

        The session transitions to SEALED status and becomes immutable.
        No further segments can be appended.

        Used by:
            UC2 (Compliance): Auditor sees session is finalized
            UC3 (Quality): ML engineer queries completed sessions for patterns
        """
        session = self._get_active_session(session_id)
        sealed_at = datetime.now(timezone.utc).isoformat()
        return self._store.update_session_status(
            session_id, SessionStatus.SEALED, sealed_at=sealed_at,
        )

    def revoke_session(self, session_id: str) -> TranscriptSession:
        """Revoke a session due to CONCORD anomaly detection.

        The session transitions to REVOKED status. The transcript is
        preserved in full for forensic reconstruction (UC1) but no
        further segments can be appended.

        This is the ForgeTranscript side of CONCORD's sub-second
        revocation capability (Kill-Switch Test, Milestone 1).
        """
        session = self._get_active_session(session_id)
        sealed_at = datetime.now(timezone.utc).isoformat()
        return self._store.update_session_status(
            session_id, SessionStatus.REVOKED, sealed_at=sealed_at,
        )

    def get_session(self, session_id: str) -> TranscriptSession:
        """Retrieve a session by its CONCORD session_id.

        Raises:
            SessionNotFoundError: If no session with this ID exists.
        """
        session = self._store.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session {session_id!r} not found")
        return session

    def list_active_sessions(self) -> list[TranscriptSession]:
        """List all currently active sessions.

        Used by UC4 (Real-Time Awareness): Operator dashboard showing
        all agents currently executing governed workflows.
        """
        return self._store.list_sessions(status=SessionStatus.ACTIVE)

    def list_sessions_by_agent(self, agent_id: str) -> list[TranscriptSession]:
        """List all sessions for a specific agent.

        Used by UC3 (Quality): ML engineer reviewing an agent's
        reasoning patterns across multiple sessions.
        """
        return self._store.list_sessions(agent_id=agent_id)

    def list_sessions_by_workflow(self, workflow_id: str) -> list[TranscriptSession]:
        """List all sessions within a shared workflow.

        Used by UC5 (Collaboration): System architect tracing
        information flow across collaborating agents.
        """
        return self._store.list_sessions(workflow_id=workflow_id)

    def is_session_active(self, session_id: str) -> bool:
        """Check if a session is still accepting segments."""
        try:
            session = self.get_session(session_id)
            return session.status == SessionStatus.ACTIVE
        except SessionNotFoundError:
            return False

    def _get_active_session(self, session_id: str) -> TranscriptSession:
        """Retrieve a session and validate it is still ACTIVE."""
        session = self.get_session(session_id)
        if session.status != SessionStatus.ACTIVE:
            raise SessionNotActiveError(
                f"Session {session_id!r} is {session.status.value}, "
                f"cannot modify. Terminal sessions are immutable."
            )
        return session
