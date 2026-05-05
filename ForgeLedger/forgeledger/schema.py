from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

LEDGER_VERSION = "0.1"


class EventType(str, Enum):
    CONCORD_ADMISSION_DECISION   = "concord.admission_decision"
    FORGEGATE_DECISION_RECORD    = "forgegate.decision_record"
    FORGEGATE_POLICY_EVALUATION  = "forgegate.policy_evaluation"
    AZUL_VERDICT_SUMMARY         = "azul.verdict_summary"
    WARDEN_LLM_CALL_METADATA     = "warden.llm_call_metadata"
    AGENT_TOOL_CALL              = "agent.tool_call"
    AGENT_HUMAN_REVIEW_REQUIRED  = "agent.human_review_required"
    HUMAN_APPROVAL_DECISION      = "human.approval_decision"
    RETENTION_LEGAL_HOLD_APPLIED = "retention.legal_hold_applied"
    LEDGER_REDACTION_APPLIED     = "ledger.redaction_applied"
    LEDGER_CHECKPOINT_CREATED    = "ledger.checkpoint_created"
    LEDGER_ANCHOR_PUBLISHED      = "ledger.anchor_published"
    LEDGER_EVIDENCE_PACKAGE_EXPORTED = "ledger.evidence_package_exported"
    LEDGER_READ_ACCESS           = "ledger.read_access"
    LEDGER_RETENTION_SCAN_COMPLETED = "ledger.retention_scan_completed"
    LEDGER_RETENTION_ACTION_APPLIED = "ledger.retention_action_applied"


class RetentionClass(str, Enum):
    EPHEMERAL        = "ephemeral"
    OPERATIONAL_30D  = "operational_30d"
    SUPPORT_1Y       = "support_1y"
    AUDIT_7Y         = "audit_7y"
    HEALTH_10Y       = "health_10y"
    LEGAL_HOLD       = "legal_hold"
    CUSTOMER_DEFINED = "customer_defined"


@dataclass
class Actor:
    actor_type: str  # "agent" | "human" | "system"
    actor_id: str
    role: str


@dataclass
class Tenant:
    tenant_id: str
    customer_boundary: str
    data_residency: str  # "NZ" | "AU" | "GLOBAL"


@dataclass
class SystemContext:
    source_module: str   # "CONCORD" | "ForgeGate" | "Azul" | "Warden"
    environment: str     # "local" | "private_cloud" | "cloud"
    deployment_id: str


@dataclass
class Decision:
    decision_type: str  # "allow" | "deny" | "review" | "escalate"
    reason: str
    risk_level: str     # "low" | "medium" | "high" | "critical"


@dataclass
class EvidenceGap:
    gap_type: str
    blocking: bool


@dataclass
class RedactionReceipt:
    field_path: str           # e.g. "payload.prompt"
    sha256_of_original: str   # hex SHA-256 of the raw value before redaction
    redacted_at: str          # ISO 8601 UTC timestamp


@dataclass
class Evidence:
    evidence_refs: list[str]
    evidence_gaps: list[EvidenceGap]
    assertion_classes: list[str]


@dataclass
class Policy:
    policy_id: str
    policy_hash: str         # sha256 of policy content at evaluation time
    retention_class: RetentionClass
    legal_hold: bool = False


@dataclass
class Integrity:
    previous_hash: Optional[str]  # None for genesis event
    event_hash: str               # sha256(canonical_json(event_with_event_hash=""))
    signature: Optional[str] = None  # reserved for Phase 5
    signing_key_id: Optional[str] = None


@dataclass
class LedgerEvent:
    event_id: str
    ledger_version: str
    event_type: EventType
    event_time: str          # ISO 8601 UTC
    actor: Actor
    tenant: Tenant
    system_context: SystemContext
    decision: Decision
    evidence: Evidence
    policy: Policy
    control_tags: list[str]  # e.g. ["NZISM.LOGGING", "SOC2.CC6.1"]
    integrity: Integrity
    payload: Optional[dict] = None
    redaction_receipts: list[RedactionReceipt] = field(default_factory=list)


def event_from_dict(d: dict) -> LedgerEvent:
    """Deserialize a LedgerEvent from a plain dict (as produced by canonical_json)."""
    return LedgerEvent(
        event_id=d["event_id"],
        ledger_version=d["ledger_version"],
        event_type=EventType(d["event_type"]),
        event_time=d["event_time"],
        actor=Actor(
            actor_type=d["actor"]["actor_type"],
            actor_id=d["actor"]["actor_id"],
            role=d["actor"]["role"],
        ),
        tenant=Tenant(
            tenant_id=d["tenant"]["tenant_id"],
            customer_boundary=d["tenant"]["customer_boundary"],
            data_residency=d["tenant"]["data_residency"],
        ),
        system_context=SystemContext(
            source_module=d["system_context"]["source_module"],
            environment=d["system_context"]["environment"],
            deployment_id=d["system_context"]["deployment_id"],
        ),
        decision=Decision(
            decision_type=d["decision"]["decision_type"],
            reason=d["decision"]["reason"],
            risk_level=d["decision"]["risk_level"],
        ),
        evidence=Evidence(
            evidence_refs=d["evidence"]["evidence_refs"],
            evidence_gaps=[
                EvidenceGap(gap_type=g["gap_type"], blocking=g["blocking"])
                for g in d["evidence"]["evidence_gaps"]
            ],
            assertion_classes=d["evidence"]["assertion_classes"],
        ),
        policy=Policy(
            policy_id=d["policy"]["policy_id"],
            policy_hash=d["policy"]["policy_hash"],
            retention_class=RetentionClass(d["policy"]["retention_class"]),
            legal_hold=d["policy"].get("legal_hold", False),
        ),
        control_tags=d["control_tags"],
        integrity=Integrity(
            previous_hash=d["integrity"]["previous_hash"],
            event_hash=d["integrity"]["event_hash"],
            signature=d["integrity"].get("signature"),
            signing_key_id=d["integrity"].get("signing_key_id"),
        ),
        payload=d.get("payload"),
        redaction_receipts=[
            RedactionReceipt(
                field_path=r["field_path"],
                sha256_of_original=r["sha256_of_original"],
                redacted_at=r["redacted_at"],
            )
            for r in d.get("redaction_receipts", [])
        ],
    )
