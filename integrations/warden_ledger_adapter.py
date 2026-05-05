from __future__ import annotations

from forgeledger.backend import LedgerBackend
from forgeledger.emitter import LedgerEmitter
from forgeledger.redaction import IngestRedactor
from forgeledger.schema import Actor, Decision, EventType, Evidence, SystemContext, Tenant
from forgeledger.validators import validate_event

from integrations._common import control_tags_from_frameworks, stored_event_by_id
from integrations.types import WardenCallRecord, normalize_warden_output


class WardenLedgerAdapter:
    def __init__(self, backend: LedgerBackend, redactor: IngestRedactor | None = None) -> None:
        self._backend = backend
        self._emitter = LedgerEmitter(backend, redactor=redactor or IngestRedactor())

    def emit_call_record(self, record: WardenCallRecord):
        payload = {
            "prompt": record.prompt,
            "data_sensitivity": record.data_sensitivity,
            "prompt_class": record.prompt_class,
            "response_class": record.response_class,
            "model_provider": record.model_provider,
        }
        if record.response is not None:
            payload["response"] = record.response
        if record.latency_ms is not None:
            payload["latency_ms"] = record.latency_ms

        append = self._emitter.emit(
            event_type=EventType.WARDEN_LLM_CALL_METADATA,
            actor=Actor(actor_type="system", actor_id=record.actor_id, role="llm_gateway"),
            tenant=Tenant(
                tenant_id=record.tenant_id,
                customer_boundary=record.customer_boundary,
                data_residency=record.data_residency,
            ),
            system_context=SystemContext(
                source_module="Warden",
                environment=record.environment,
                deployment_id=record.deployment_id,
            ),
            decision=Decision(
                decision_type=record.decision_type,
                reason=record.reason,
                risk_level=record.risk_level,
            ),
            evidence=Evidence(
                evidence_refs=record.evidence_refs,
                evidence_gaps=[],
                assertion_classes=["LLM_METADATA"],
            ),
            policy_id=record.policy_id,
            policy_hash=record.policy_hash,
            control_tags=control_tags_from_frameworks(record.frameworks, ["NZISM.LOGGING.EVENT_CAPTURE", "SOC2.CC7.2"]),
            payload=payload,
        )
        event = stored_event_by_id(self._backend, append.event_id)
        errors = validate_event(event)
        if errors:
            raise ValueError(f"Warden adapter emitted invalid event: {errors}")
        return event


def warden_runtime_output_to_call_record(data: dict) -> WardenCallRecord:
    return WardenCallRecord.from_runtime_output(data)
