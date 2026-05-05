from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


def _require(raw: dict[str, Any], field_name: str) -> Any:
    value = raw.get(field_name)
    if value is None or value == "":
        raise ValueError(f"missing required field: {field_name}")
    return value


def _optional_list(raw: dict[str, Any], field_name: str) -> list:
    value = raw.get(field_name, [])
    if value is None:
        return []
    return list(value)


@dataclass
class ConcordAdmissionResult:
    agent_id: str
    admitted: bool
    reason: str
    risk_level: str
    tenant_id: str
    customer_boundary: str
    data_residency: str
    policy_id: str
    policy_hash: str
    frameworks: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    agent_class: str = "unknown"
    trust_tier: str = "unknown"
    capabilities_checked: list[str] = field(default_factory=list)
    environment: str = "local"
    deployment_id: str = "unknown"

    @classmethod
    def from_runtime_output(cls, data: dict[str, Any]) -> "ConcordAdmissionResult":
        return cls(
            agent_id=str(data.get("agent_id") or data.get("agent") or ""),
            admitted=bool(data.get("admitted", data.get("allow", False))),
            reason=str(data.get("reason", "")),
            risk_level=str(data.get("risk_level", "low")),
            tenant_id=str(data.get("tenant_id", "unknown")),
            customer_boundary=str(data.get("customer_boundary", "")),
            data_residency=str(data.get("data_residency", "UNKNOWN")),
            policy_id=str(data.get("policy_id", "concord_policy_unknown")),
            policy_hash=str(data.get("policy_hash", "")),
            frameworks=list(data.get("frameworks", [])),
            evidence_refs=list(data.get("evidence_refs", [])),
            agent_class=str(data.get("agent_class", "unknown")),
            trust_tier=str(data.get("trust_tier", "unknown")),
            capabilities_checked=list(data.get("capabilities_checked", [])),
            environment=str(data.get("environment", "local")),
            deployment_id=str(data.get("deployment_id", "unknown")),
        )


def normalize_concord_output(raw: dict[str, Any]) -> ConcordAdmissionResult:
    """Strict CONCORD normalizer. Unknown fields are ignored by policy."""
    return ConcordAdmissionResult(
        agent_id=str(_require(raw, "agent_id")),
        admitted=bool(_require(raw, "admitted")),
        reason=str(_require(raw, "reason")),
        risk_level=str(_require(raw, "risk_level")),
        tenant_id=str(_require(raw, "tenant_id")),
        customer_boundary=str(_require(raw, "customer_boundary")),
        data_residency=str(_require(raw, "data_residency")),
        policy_id=str(_require(raw, "policy_id")),
        policy_hash=str(_require(raw, "policy_hash")),
        frameworks=_optional_list(raw, "frameworks"),
        evidence_refs=_optional_list(raw, "evidence_refs"),
        agent_class=str(raw.get("agent_class", "unknown")),
        trust_tier=str(raw.get("trust_tier", "unknown")),
        capabilities_checked=_optional_list(raw, "capabilities_checked"),
        environment=str(raw.get("environment", "local")),
        deployment_id=str(raw.get("deployment_id", "unknown")),
    )


@dataclass
class ForgeGateEvaluationResult:
    actor_id: str
    decision_type: str
    reason: str
    risk_level: str
    tenant_id: str
    customer_boundary: str
    data_residency: str
    policy_id: str
    policy_hash: str
    blast_radius_score: Optional[float] = None
    evidence_refs: list[str] = field(default_factory=list)
    evidence_gaps: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    action_type: str = "unknown"
    environment: str = "local"
    deployment_id: str = "unknown"

    @classmethod
    def from_runtime_output(cls, data: dict[str, Any]) -> "ForgeGateEvaluationResult":
        return cls(
            actor_id=str(data.get("actor_id", "forgegate.policy_evaluator")),
            decision_type=str(data.get("decision_type") or data.get("decision") or "deny"),
            reason=str(data.get("reason", "")),
            risk_level=str(data.get("risk_level", "low")),
            tenant_id=str(data.get("tenant_id", "unknown")),
            customer_boundary=str(data.get("customer_boundary", "")),
            data_residency=str(data.get("data_residency", "UNKNOWN")),
            policy_id=str(data.get("policy_id", "forgegate_policy_unknown")),
            policy_hash=str(data.get("policy_hash", "")),
            blast_radius_score=data.get("blast_radius_score"),
            evidence_refs=list(data.get("evidence_refs", [])),
            evidence_gaps=list(data.get("evidence_gaps", [])),
            frameworks=list(data.get("frameworks", [])),
            action_type=str(data.get("action_type", "unknown")),
            environment=str(data.get("environment", "local")),
            deployment_id=str(data.get("deployment_id", "unknown")),
        )


def normalize_forgegate_output(raw: dict[str, Any]) -> ForgeGateEvaluationResult:
    """Strict ForgeGate normalizer. Unknown fields are ignored by policy."""
    decision = raw.get("decision_type", raw.get("decision"))
    if decision is None or decision == "":
        raise ValueError("missing required field: decision_type")
    return ForgeGateEvaluationResult(
        actor_id=str(_require(raw, "actor_id")),
        decision_type=str(decision),
        reason=str(_require(raw, "reason")),
        risk_level=str(_require(raw, "risk_level")),
        tenant_id=str(_require(raw, "tenant_id")),
        customer_boundary=str(_require(raw, "customer_boundary")),
        data_residency=str(_require(raw, "data_residency")),
        policy_id=str(_require(raw, "policy_id")),
        policy_hash=str(_require(raw, "policy_hash")),
        blast_radius_score=raw.get("blast_radius_score"),
        evidence_refs=_optional_list(raw, "evidence_refs"),
        evidence_gaps=_optional_list(raw, "evidence_gaps"),
        frameworks=_optional_list(raw, "frameworks"),
        action_type=str(_require(raw, "action_type")),
        environment=str(raw.get("environment", "local")),
        deployment_id=str(raw.get("deployment_id", "unknown")),
    )


@dataclass
class WardenCallRecord:
    actor_id: str
    decision_type: str
    reason: str
    risk_level: str
    tenant_id: str
    customer_boundary: str
    data_residency: str
    policy_id: str
    policy_hash: str
    prompt: str
    response: Optional[str]
    data_sensitivity: str
    prompt_class: str
    response_class: str
    model_provider: str
    latency_ms: Optional[int] = None
    frameworks: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    environment: str = "local"
    deployment_id: str = "unknown"

    @classmethod
    def from_runtime_output(cls, data: dict[str, Any]) -> "WardenCallRecord":
        return cls(
            actor_id=str(data.get("actor_id", "warden.llm_gateway")),
            decision_type=str(data.get("decision_type", "allow")),
            reason=str(data.get("reason", "llm_call_recorded")),
            risk_level=str(data.get("risk_level", "low")),
            tenant_id=str(data.get("tenant_id", "unknown")),
            customer_boundary=str(data.get("customer_boundary", "")),
            data_residency=str(data.get("data_residency", "UNKNOWN")),
            policy_id=str(data.get("policy_id", "warden_policy_unknown")),
            policy_hash=str(data.get("policy_hash", "")),
            prompt=str(data.get("prompt", "")),
            response=data.get("response"),
            data_sensitivity=str(data.get("data_sensitivity", "public")),
            prompt_class=str(data.get("prompt_class", "unknown")),
            response_class=str(data.get("response_class", "unknown")),
            model_provider=str(data.get("model_provider", "unknown")),
            latency_ms=data.get("latency_ms"),
            frameworks=list(data.get("frameworks", [])),
            evidence_refs=list(data.get("evidence_refs", [])),
            environment=str(data.get("environment", "local")),
            deployment_id=str(data.get("deployment_id", "unknown")),
        )


def normalize_warden_output(raw: dict[str, Any]) -> WardenCallRecord:
    """Strict Warden normalizer. Unknown fields are ignored by policy."""
    return WardenCallRecord(
        actor_id=str(_require(raw, "actor_id")),
        decision_type=str(_require(raw, "decision_type")),
        reason=str(_require(raw, "reason")),
        risk_level=str(_require(raw, "risk_level")),
        tenant_id=str(_require(raw, "tenant_id")),
        customer_boundary=str(_require(raw, "customer_boundary")),
        data_residency=str(_require(raw, "data_residency")),
        policy_id=str(_require(raw, "policy_id")),
        policy_hash=str(_require(raw, "policy_hash")),
        prompt=str(_require(raw, "prompt")),
        response=raw.get("response"),
        data_sensitivity=str(_require(raw, "data_sensitivity")),
        prompt_class=str(_require(raw, "prompt_class")),
        response_class=str(_require(raw, "response_class")),
        model_provider=str(_require(raw, "model_provider")),
        latency_ms=raw.get("latency_ms"),
        frameworks=_optional_list(raw, "frameworks"),
        evidence_refs=_optional_list(raw, "evidence_refs"),
        environment=str(raw.get("environment", "local")),
        deployment_id=str(raw.get("deployment_id", "unknown")),
    )


@dataclass
class AzulVerdictRecord:
    actor_id: str
    verdict: str
    reason: str
    tenant_id: str
    customer_boundary: str
    data_residency: str
    policy_id: str
    policy_hash: str
    safety_score: float
    flagged_categories: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    environment: str = "local"
    deployment_id: str = "unknown"

    @classmethod
    def from_runtime_output(cls, data: dict[str, Any]) -> "AzulVerdictRecord":
        return cls(
            actor_id=str(data.get("actor_id", "azul.safety_engine")),
            verdict=str(data.get("verdict", "allow")),
            reason=str(data.get("reason", "")),
            tenant_id=str(data.get("tenant_id", "unknown")),
            customer_boundary=str(data.get("customer_boundary", "")),
            data_residency=str(data.get("data_residency", "UNKNOWN")),
            policy_id=str(data.get("policy_id", "azul_policy_unknown")),
            policy_hash=str(data.get("policy_hash", "")),
            safety_score=float(data.get("safety_score", 1.0)),
            flagged_categories=list(data.get("flagged_categories", [])),
            evidence_refs=list(data.get("evidence_refs", [])),
            frameworks=list(data.get("frameworks", [])),
            environment=str(data.get("environment", "local")),
            deployment_id=str(data.get("deployment_id", "unknown")),
        )


def normalize_azul_output(raw: dict[str, Any]) -> AzulVerdictRecord:
    """Strict Azul normalizer. Unknown fields are ignored by policy."""
    return AzulVerdictRecord(
        actor_id=str(_require(raw, "actor_id")),
        verdict=str(_require(raw, "verdict")),
        reason=str(_require(raw, "reason")),
        tenant_id=str(_require(raw, "tenant_id")),
        customer_boundary=str(_require(raw, "customer_boundary")),
        data_residency=str(_require(raw, "data_residency")),
        policy_id=str(_require(raw, "policy_id")),
        policy_hash=str(_require(raw, "policy_hash")),
        safety_score=float(_require(raw, "safety_score")),
        flagged_categories=_optional_list(raw, "flagged_categories"),
        evidence_refs=_optional_list(raw, "evidence_refs"),
        frameworks=_optional_list(raw, "frameworks"),
        environment=str(raw.get("environment", "local")),
        deployment_id=str(raw.get("deployment_id", "unknown")),
    )
