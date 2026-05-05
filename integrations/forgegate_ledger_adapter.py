from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone

from forgeledger.backend import LedgerBackend
from forgeledger.emitter import LedgerEmitter
from forgeledger.retention import classify_event
from forgeledger.schema import (
    LEDGER_VERSION,
    Actor,
    Decision,
    EventType,
    Evidence,
    EvidenceGap,
    Integrity,
    LedgerEvent,
    Policy,
    RetentionClass,
    SystemContext,
    Tenant,
)
from forgeledger.validators import validate_event

from integrations._common import control_tags_from_frameworks, stored_event_by_id
from integrations.types import ForgeGateEvaluationResult, normalize_forgegate_output


class ForgeGateLedgerAdapter:
    def __init__(self, backend: LedgerBackend) -> None:
        self._backend = backend
        self._emitter = LedgerEmitter(backend)

    def emit_evaluation_result(self, result: ForgeGateEvaluationResult):
        return self._emit(result, EventType.FORGEGATE_DECISION_RECORD)

    def emit_policy_evaluation_result(self, result: ForgeGateEvaluationResult):
        return self._emit(result, EventType.FORGEGATE_POLICY_EVALUATION)

    def _emit(self, result: ForgeGateEvaluationResult, event_type: EventType):
        gaps = [EvidenceGap(gap_type=gap, blocking=True) for gap in result.evidence_gaps]
        if result.blast_radius_score is not None and result.blast_radius_score > 0.7:
            if not any(g.gap_type == "high_blast_radius" for g in gaps):
                gaps.append(EvidenceGap(gap_type="high_blast_radius", blocking=True))

        append = self._emitter.emit(
            event_type=event_type,
            actor=Actor(actor_type="system", actor_id=result.actor_id, role="policy_engine"),
            tenant=Tenant(
                tenant_id=result.tenant_id,
                customer_boundary=result.customer_boundary,
                data_residency=result.data_residency,
            ),
            system_context=SystemContext(
                source_module="ForgeGate",
                environment=result.environment,
                deployment_id=result.deployment_id,
            ),
            decision=Decision(
                decision_type=result.decision_type,
                reason=result.reason,
                risk_level=result.risk_level,
            ),
            evidence=Evidence(
                evidence_refs=result.evidence_refs,
                evidence_gaps=gaps,
                assertion_classes=["FACT"],
            ),
            policy_id=result.policy_id,
            policy_hash=result.policy_hash,
            control_tags=control_tags_from_frameworks(result.frameworks, ["NZISM.LOGGING.TAMPER_PROTECTION"]),
            payload={
                "action_type": result.action_type,
                "blast_radius_score": result.blast_radius_score,
            },
        )
        event = stored_event_by_id(self._backend, append.event_id)
        errors = validate_event(event)
        if errors:
            raise ValueError(f"ForgeGate adapter emitted invalid event: {errors}")
        return event


def forgegate_runtime_output_to_evaluation_result(data: dict) -> ForgeGateEvaluationResult:
    return ForgeGateEvaluationResult.from_runtime_output(data)


def build_ledger_event_from_forgegate(data: dict) -> LedgerEvent:
    blast_radius = data.get("blast_radius_score")
    gaps: list[EvidenceGap] = []
    if blast_radius is not None and blast_radius > 0.7:
        gaps.append(EvidenceGap(gap_type="high_blast_radius", blocking=True))

    event = LedgerEvent(
        event_id=str(uuid.uuid4()),
        ledger_version=LEDGER_VERSION,
        event_type=EventType.FORGEGATE_DECISION_RECORD,
        event_time=datetime.now(timezone.utc).isoformat(),
        actor=Actor(
            actor_type="system",
            actor_id="forgegate.policy_evaluator",
            role=str(data.get("agent_class", "unknown")),
        ),
        tenant=Tenant(
            tenant_id=str(data.get("tenant_id", "unknown")),
            customer_boundary=str(data.get("customer_boundary", "")),
            data_residency=str(data.get("data_residency", "UNKNOWN")),
        ),
        system_context=SystemContext(
            source_module="ForgeGate",
            environment=str(data.get("environment", "local")),
            deployment_id=str(data.get("deployment_id", "unknown")),
        ),
        decision=Decision(
            decision_type=str(data.get("decision", "deny")),
            reason=str(data.get("reason", "")),
            risk_level=str(data.get("risk_level", "low")),
        ),
        evidence=Evidence(evidence_refs=[], evidence_gaps=gaps, assertion_classes=["FACT"]),
        policy=Policy(
            policy_id=str(data.get("policy_id", "forgegate_policy_unknown")),
            policy_hash=str(data.get("policy_hash", "")),
            retention_class=RetentionClass.AUDIT_7Y,
        ),
        control_tags=control_tags_from_frameworks(
            list(data.get("frameworks", [])),
            ["NZISM.LOGGING.TAMPER_PROTECTION", "SOC2.CC7.2", "NIST_CSF.GV"],
        ),
        integrity=Integrity(previous_hash=None, event_hash=""),
        payload={
            "decision_id": data.get("decision_id"),
            "action_type": data.get("action_type"),
            "blast_radius_score": blast_radius,
        },
    )
    return dataclasses.replace(
        event,
        policy=dataclasses.replace(event.policy, retention_class=classify_event(event)),
    )
