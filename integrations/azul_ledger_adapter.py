from __future__ import annotations

from forgeledger.backend import LedgerBackend
from forgeledger.emitter import LedgerEmitter
from forgeledger.schema import Actor, Decision, EventType, Evidence, SystemContext, Tenant
from forgeledger.validators import validate_event

from integrations._common import control_tags_from_frameworks, stored_event_by_id
from integrations.types import AzulVerdictRecord, normalize_azul_output


class AzulLedgerAdapter:
    def __init__(self, backend: LedgerBackend) -> None:
        self._backend = backend
        self._emitter = LedgerEmitter(backend)

    def emit_verdict_record(self, record: AzulVerdictRecord):
        verdict = record.verdict.lower()
        decision_type = "deny" if verdict == "deny" else "allow"
        risk_level = "high" if decision_type == "deny" else "low"

        append = self._emitter.emit(
            event_type=EventType.AZUL_VERDICT_SUMMARY,
            actor=Actor(actor_type="system", actor_id=record.actor_id, role="safety_assessor"),
            tenant=Tenant(
                tenant_id=record.tenant_id,
                customer_boundary=record.customer_boundary,
                data_residency=record.data_residency,
            ),
            system_context=SystemContext(
                source_module="Azul",
                environment=record.environment,
                deployment_id=record.deployment_id,
            ),
            decision=Decision(
                decision_type=decision_type,
                reason=record.reason,
                risk_level=risk_level,
            ),
            evidence=Evidence(
                evidence_refs=record.evidence_refs,
                evidence_gaps=[],
                assertion_classes=["SAFETY_VERDICT"],
            ),
            policy_id=record.policy_id,
            policy_hash=record.policy_hash,
            control_tags=control_tags_from_frameworks(record.frameworks, ["SOC2.CC7.2"]),
            payload={
                "safety_score": record.safety_score,
                "flagged_categories": record.flagged_categories,
                "verdict": record.verdict,
            },
        )
        event = stored_event_by_id(self._backend, append.event_id)
        errors = validate_event(event)
        if errors:
            raise ValueError(f"Azul adapter emitted invalid event: {errors}")
        return event


def azul_runtime_output_to_verdict_record(data: dict) -> AzulVerdictRecord:
    return AzulVerdictRecord.from_runtime_output(data)
