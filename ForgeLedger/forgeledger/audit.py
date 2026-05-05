from __future__ import annotations

from typing import Optional

from forgeledger.emitter import LedgerEmitter
from forgeledger.schema import Actor, Decision, EventType, Evidence, SystemContext, Tenant


def emit_audit_event(
    audit_emitter: Optional[LedgerEmitter],
    *,
    event_type: EventType,
    payload: dict,
    reason: str,
    tenant_id: str = "ledger-audit",
    source_module: str = "ForgeLedger",
) -> None:
    """Emit a governance meta-event if an audit emitter is configured."""
    if audit_emitter is None:
        return

    audit_emitter.emit(
        event_type=event_type,
        actor=Actor(actor_type="system", actor_id="forgeledger.audit", role="audit_emitter"),
        tenant=Tenant(tenant_id=tenant_id, customer_boundary="ledger", data_residency="GLOBAL"),
        system_context=SystemContext(source_module=source_module, environment="local", deployment_id="audit"),
        decision=Decision(decision_type="allow", reason=reason, risk_level="low"),
        evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["AUDIT_EVENT"]),
        policy_id="forgeledger_audit_policy",
        policy_hash="internal",
        control_tags=["NZISM.LOGGING.EVENT_CAPTURE", "NZISM.LOGGING.TAMPER_PROTECTION"],
        payload=payload,
    )
