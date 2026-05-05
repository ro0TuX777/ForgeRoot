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
    Integrity,
    LedgerEvent,
    Policy,
    RetentionClass,
    SystemContext,
    Tenant,
)
from forgeledger.validators import validate_event

from integrations._common import control_tags_from_frameworks, stored_event_by_id
from integrations.types import ConcordAdmissionResult, normalize_concord_output


class ConcordLedgerAdapter:
    def __init__(self, backend: LedgerBackend) -> None:
        self._backend = backend
        self._emitter = LedgerEmitter(backend)

    def emit_admission_result(self, result: ConcordAdmissionResult):
        if not result.agent_id:
            raise ValueError("agent_id is required")

        append = self._emitter.emit(
            event_type=EventType.CONCORD_ADMISSION_DECISION,
            actor=Actor(actor_type="agent", actor_id=result.agent_id, role=result.agent_class),
            tenant=Tenant(
                tenant_id=result.tenant_id,
                customer_boundary=result.customer_boundary,
                data_residency=result.data_residency,
            ),
            system_context=SystemContext(
                source_module="CONCORD",
                environment=result.environment,
                deployment_id=result.deployment_id,
            ),
            decision=Decision(
                decision_type="allow" if result.admitted else "deny",
                reason=result.reason,
                risk_level=result.risk_level,
            ),
            evidence=Evidence(
                evidence_refs=result.evidence_refs,
                evidence_gaps=[],
                assertion_classes=["FACT"],
            ),
            policy_id=result.policy_id,
            policy_hash=result.policy_hash,
            control_tags=control_tags_from_frameworks(result.frameworks, ["NZISM.ACCESS.AUTHORISATION"]),
        )
        event = stored_event_by_id(self._backend, append.event_id)
        errors = validate_event(event)
        if errors:
            raise ValueError(f"Concord adapter emitted invalid event: {errors}")
        return event


def concord_runtime_output_to_admission_result(data: dict) -> ConcordAdmissionResult:
    return ConcordAdmissionResult.from_runtime_output(data)


def build_ledger_event_from_concord(data: dict) -> LedgerEvent:
    admitted = bool(data.get("admitted", False))
    event = LedgerEvent(
        event_id=str(uuid.uuid4()),
        ledger_version=LEDGER_VERSION,
        event_type=EventType.CONCORD_ADMISSION_DECISION,
        event_time=datetime.now(timezone.utc).isoformat(),
        actor=Actor(
            actor_type="agent",
            actor_id=f"concord.admission.{str(data.get('agent_class', 'unknown')).lower()}",
            role=str(data.get("agent_class", "unknown")),
        ),
        tenant=Tenant(
            tenant_id=str(data.get("tenant_id", "unknown")),
            customer_boundary=str(data.get("customer_boundary", "")),
            data_residency=str(data.get("data_residency", "UNKNOWN")),
        ),
        system_context=SystemContext(
            source_module="CONCORD",
            environment=str(data.get("environment", "local")),
            deployment_id=str(data.get("deployment_id", "unknown")),
        ),
        decision=Decision(
            decision_type="allow" if admitted else "deny",
            reason=str(data.get("reason", "")),
            risk_level=str(data.get("risk_level", "low")),
        ),
        evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["FACT"]),
        policy=Policy(
            policy_id=str(data.get("policy_id", "concord_policy_unknown")),
            policy_hash=str(data.get("policy_hash", "")),
            retention_class=RetentionClass.AUDIT_7Y,
        ),
        control_tags=control_tags_from_frameworks(
            list(data.get("frameworks", [])),
            ["NZISM.ACCESS.AUTHORISATION", "SOC2.CC6.1", "NIST_CSF.GV"],
        ),
        integrity=Integrity(previous_hash=None, event_hash=""),
        payload={
            "intent_id": data.get("intent_id"),
            "trust_tier": data.get("trust_tier"),
            "capabilities_checked": data.get("capabilities_checked", []),
        },
    )
    return dataclasses.replace(
        event,
        policy=dataclasses.replace(event.policy, retention_class=classify_event(event)),
    )
