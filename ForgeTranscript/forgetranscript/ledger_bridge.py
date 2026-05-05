"""
ForgeLedger bridge for ForgeTranscript.

Integrates ForgeTranscript into ForgeLedger's evidence chain by emitting
a LedgerEvent for each transcript session lifecycle event and optionally
for high-importance segments.

This ensures that transcript activity is visible in the unified
governance evidence trail alongside CONCORD admissions, ForgeGate
decisions, and Azul verdicts.

Bridge events use the EventType.AGENT_TOOL_CALL from ForgeLedger's
schema, extended with ForgeTranscript-specific payload fields.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from forgeledger.emitter import LedgerEmitter
    from forgeledger.schema import Actor, Tenant, SystemContext

from forgetranscript.schema import (
    SessionStatus,
    TranscriptSegment,
    TranscriptSession,
)


# Segment types that are bridged to ForgeLedger by default.
# These represent governance-significant events that should appear
# in the unified evidence trail.
_BRIDGED_SEGMENT_TYPES = frozenset({
    "decision_ref",
    "comprehension",
    "system_event",
    "error",
})


class LedgerBridge:
    """Bridges ForgeTranscript events into ForgeLedger's evidence chain.

    Usage:
        from forgeledger.emitter import LedgerEmitter
        bridge = LedgerBridge(ledger_emitter=emitter, tenant=tenant)

        # Automatically called by SessionManager on open/seal/revoke
        bridge.emit_session_opened(session)
        bridge.emit_session_sealed(session)
        bridge.emit_session_revoked(session)

        # Optionally called by TranscriptEmitter for high-importance segments
        bridge.emit_segment_captured(segment)
    """

    def __init__(
        self,
        ledger_emitter: Optional[LedgerEmitter] = None,
        tenant: Optional[Tenant] = None,
        bridge_all_segments: bool = False,
    ) -> None:
        self._emitter = ledger_emitter
        self._tenant = tenant
        self._bridge_all = bridge_all_segments

    @property
    def enabled(self) -> bool:
        """Whether the bridge is active (has a configured LedgerEmitter)."""
        return self._emitter is not None and self._tenant is not None

    def emit_session_opened(self, session: TranscriptSession) -> None:
        """Emit a LedgerEvent when a transcript session is opened."""
        if not self.enabled:
            return
        self._emit_session_event(session, "session_opened", "allow")

    def emit_session_sealed(self, session: TranscriptSession) -> None:
        """Emit a LedgerEvent when a transcript session is sealed normally."""
        if not self.enabled:
            return
        self._emit_session_event(session, "session_sealed", "allow")

    def emit_session_revoked(self, session: TranscriptSession) -> None:
        """Emit a LedgerEvent when a transcript session is revoked.

        Emitted as risk_level='high' since revocation indicates an
        anomaly that triggered CONCORD's kill-switch (UC1).
        """
        if not self.enabled:
            return
        self._emit_session_event(session, "session_revoked", "deny", risk_level="high")

    def should_bridge_segment(self, segment: TranscriptSegment) -> bool:
        """Determine if a segment should be bridged to ForgeLedger.

        By default, only governance-significant segment types are bridged.
        Set bridge_all_segments=True to bridge everything (high volume).
        """
        if self._bridge_all:
            return True
        return segment.segment_type.value in _BRIDGED_SEGMENT_TYPES

    def emit_segment_captured(self, segment: TranscriptSegment) -> None:
        """Emit a LedgerEvent for a captured transcript segment.

        Only bridges governance-significant segments by default.
        """
        if not self.enabled:
            return
        if not self.should_bridge_segment(segment):
            return

        from forgeledger.schema import (
            Actor,
            Decision,
            Evidence,
            EventType,
            SystemContext,
        )

        self._emitter.emit(
            event_type=EventType.AGENT_TOOL_CALL,
            actor=Actor(
                actor_type="agent",
                actor_id=segment.session_id,
                role="transcript_capture",
            ),
            tenant=self._tenant,
            system_context=SystemContext(
                source_module="ForgeTranscript",
                environment="local",
                deployment_id="forgetranscript-bridge",
            ),
            decision=Decision(
                decision_type="allow",
                reason=f"transcript_segment_{segment.segment_type.value}",
                risk_level="low",
            ),
            evidence=Evidence(
                evidence_refs=[segment.segment_id, segment.segment_hash],
                evidence_gaps=[],
                assertion_classes=["transcript_capture"],
            ),
            policy_id="forgetranscript_bridge",
            policy_hash="none",
            control_tags=["FORGETRANSCRIPT.BRIDGE"],
            payload={
                "segment_id": segment.segment_id,
                "session_id": segment.session_id,
                "segment_type": segment.segment_type.value,
                "sequence": segment.sequence,
                "source_module": segment.source_module,
                "segment_hash": segment.segment_hash,
                "redacted": segment.redacted,
            },
        )

    def _emit_session_event(
        self,
        session: TranscriptSession,
        reason: str,
        decision_type: str,
        risk_level: str = "low",
    ) -> None:
        """Internal: emit a session lifecycle event to ForgeLedger."""
        from forgeledger.schema import (
            Actor,
            Decision,
            Evidence,
            EventType,
            SystemContext,
        )

        self._emitter.emit(
            event_type=EventType.AGENT_TOOL_CALL,
            actor=Actor(
                actor_type="agent",
                actor_id=session.agent_id,
                role="transcript_session",
            ),
            tenant=self._tenant,
            system_context=SystemContext(
                source_module="ForgeTranscript",
                environment="local",
                deployment_id="forgetranscript-bridge",
            ),
            decision=Decision(
                decision_type=decision_type,
                reason=reason,
                risk_level=risk_level,
            ),
            evidence=Evidence(
                evidence_refs=[session.transcript_id, session.session_id],
                evidence_gaps=[],
                assertion_classes=["transcript_lifecycle"],
            ),
            policy_id="forgetranscript_bridge",
            policy_hash="none",
            control_tags=["FORGETRANSCRIPT.BRIDGE"],
            payload={
                "transcript_id": session.transcript_id,
                "session_id": session.session_id,
                "agent_id": session.agent_id,
                "trust_tier": session.trust_tier,
                "status": session.status.value,
                "segment_count": session.segment_count,
                "workflow_id": session.workflow_id,
            },
        )
