"""
ForgeRoot Governed Agent Demo — Phase 6.

Simulates the complete governed agent workflow for the scenario:

    "Design a 2PB local backup environment for a regulated customer
     with ransomware resilience, Veeam compatibility, local jurisdiction
     control, and a path to 10PB."

Pipeline exercised end-to-end:
  - All 9 ledger event types emitted in a realistic sequence
  - Hash-chain integrity (tamper-evident)
  - CONCORD admission → ForgeGate policy → Warden LLM call →
    Agent retrieval → Azul verdict → ForgeGate HIGH_BLAST_RADIUS escalation →
    Human review → Human approval → Final ForgeGate permit
  - Control coverage mapped across NZISM, HIPC_2020, SOC2, NIST_CSF_2_0
  - Evidence gap analysis
  - Full evidence package export (12 files, redaction applied)

Usage::

    from pathlib import Path
    from demo.governed_agent_demo import run_demo

    result = run_demo(Path("./demo_output"))
    print(result.scenario_summary)
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ForgeLedger
from forgeledger.hash_chain import attach_integrity
from forgeledger.jsonl_backend import JsonlBackend
from forgeledger.schema import (
    LEDGER_VERSION,
    Actor,
    Decision,
    Evidence,
    EvidenceGap,
    EventType,
    Integrity,
    LedgerEvent,
    Policy,
    RetentionClass,
    SystemContext,
    Tenant,
)
from integrations.azul_ledger_adapter import AzulLedgerAdapter
from integrations.concord_ledger_adapter import ConcordLedgerAdapter
from integrations.forgegate_ledger_adapter import ForgeGateLedgerAdapter
from integrations.types import (
    AzulVerdictRecord,
    ConcordAdmissionResult,
    ForgeGateEvaluationResult,
    WardenCallRecord,
)
from integrations.warden_ledger_adapter import WardenLedgerAdapter

# ForgeCompliance
from forgecompliance.control_registry import ControlRegistry
from forgecompliance.evidence_package import EvidencePackageBuilder
from forgecompliance.reports import generate_coverage_report

# ---------------------------------------------------------------------------
# Scenario constants
# ---------------------------------------------------------------------------

SCENARIO_QUERY = (
    "Design a 2PB local backup environment for a regulated customer "
    "with ransomware resilience, Veeam compatibility, local jurisdiction "
    "control, and a path to 10PB."
)

SCENARIO_AGENT_RESPONSE_SUMMARY = (
    "Recommended: 6x 400TB NAS nodes across two NZ sites (3+3 split), "
    "Veeam v12 with immutable S3-compatible backup targets, hardened proxy, "
    "and air-gapped off-site replica. 3-2-1-1-0 rule applied. "
    "Scale path to 10PB via modular NAS expansion + object storage tier. "
    "Requires architect sign-off due to blast radius of infrastructure change."
)

SCENARIO_EVIDENCE_REFS = [
    "doc:veeam_integration#immutable-backup-targets",
    "doc:nz_data_residency_policy#section-3-local-jurisdiction",
    "doc:ransomware_resilience_playbook#air-gap-strategy",
    "doc:msp_capacity_planning#2pb-to-10pb-scaling",
]

_DEMO_TENANT = Tenant(
    tenant_id="demo_msp_nz_001",
    customer_boundary="synthetic_customer_a",
    data_residency="NZ",
)

_DEMO_FRAMEWORKS = ["HIPC_2020", "NIST_CSF_2_0", "NZISM", "SOC2"]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class DemoResult:
    events: list                    # list[LedgerEvent]
    chain_report: dict
    coverage_report: dict
    evidence_package_dir: Path
    manifest: dict
    scenario_summary: dict


# ---------------------------------------------------------------------------
# Event construction helpers
# ---------------------------------------------------------------------------

def _evt(
    event_id: str,
    event_type: EventType,
    event_time: str,
    actor_id: str,
    actor_type: str,
    role: str,
    source_module: str,
    decision_type: str,
    reason: str,
    risk_level: str,
    control_tags: list[str],
    evidence_refs: Optional[list[str]] = None,
    evidence_gaps: Optional[list[EvidenceGap]] = None,
    retention_class: RetentionClass = RetentionClass.AUDIT_7Y,
    policy_id: str = "forgeroot_policy_nz_msp_v0.1",
    policy_hash: str = "sha256:policy_hash_placeholder",
    payload: Optional[dict] = None,
) -> LedgerEvent:
    return LedgerEvent(
        event_id=event_id,
        ledger_version=LEDGER_VERSION,
        event_type=event_type,
        event_time=event_time,
        actor=Actor(actor_type=actor_type, actor_id=actor_id, role=role),
        tenant=_DEMO_TENANT,
        system_context=SystemContext(
            source_module=source_module,
            environment="local",
            deployment_id="forgeroot-demo",
        ),
        decision=Decision(
            decision_type=decision_type,
            reason=reason,
            risk_level=risk_level,
        ),
        evidence=Evidence(
            evidence_refs=evidence_refs or [],
            evidence_gaps=evidence_gaps or [],
            assertion_classes=["FACT", "RECOMMENDATION"],
        ),
        policy=Policy(
            policy_id=policy_id,
            policy_hash=policy_hash,
            retention_class=retention_class,
        ),
        control_tags=control_tags,
        integrity=Integrity(previous_hash=None, event_hash=""),
        payload=payload,
    )


def _emit_demo_events(backend: JsonlBackend) -> list[LedgerEvent]:
    """
    Emit the nine-event governed agent sequence for the 2PB backup scenario.
    Returns the fully integrity-attached event list.
    """
    raw: list[
        LedgerEvent
        | AzulVerdictRecord
        | ConcordAdmissionResult
        | ForgeGateEvaluationResult
        | WardenCallRecord
    ] = [

        # 1. CONCORD admits the Solution Designer agent
        ConcordAdmissionResult(
            agent_id="agent.solution_designer",
            admitted=True,
            reason="within_capability_budget",
            risk_level="low",
            tenant_id=_DEMO_TENANT.tenant_id,
            customer_boundary=_DEMO_TENANT.customer_boundary,
            data_residency=_DEMO_TENANT.data_residency,
            policy_id="forgeroot_policy_nz_msp_v0.1",
            policy_hash="sha256:policy_hash_placeholder",
            frameworks=_DEMO_FRAMEWORKS,
            evidence_refs=["doc:concord_admission_policy#v0.5"],
            agent_class="solution_engineer",
            environment="local",
            deployment_id="forgeroot-demo",
        ),

        # 2. ForgeGate evaluates policy before LLM call
        ForgeGateEvaluationResult(
            actor_id="forgegate.policy_engine",
            decision_type="allow",
            reason="policy_evaluation_passed",
            risk_level="low",
            tenant_id=_DEMO_TENANT.tenant_id,
            customer_boundary=_DEMO_TENANT.customer_boundary,
            data_residency=_DEMO_TENANT.data_residency,
            policy_id="forgeroot_policy_nz_msp_v0.1",
            policy_hash="sha256:policy_hash_placeholder",
            frameworks=["NIST_CSF_2_0", "NZISM"],
            action_type="policy_evaluation",
            environment="local",
            deployment_id="forgeroot-demo",
        ),

        # 3. Warden records LLM call — contains sensitive prompt data
        WardenCallRecord(
            actor_id="warden.llm_gateway",
            decision_type="allow",
            reason="llm_call_within_policy",
            risk_level="low",
            tenant_id=_DEMO_TENANT.tenant_id,
            customer_boundary=_DEMO_TENANT.customer_boundary,
            data_residency=_DEMO_TENANT.data_residency,
            policy_id="forgeroot_policy_nz_msp_v0.1",
            policy_hash="sha256:policy_hash_placeholder",
            prompt=SCENARIO_QUERY,
            response=None,
            data_sensitivity="llm_prompt_pii_suspected",
            prompt_class="design_query",
            response_class="technical_recommendation",
            model_provider="anthropic",
            frameworks=["NZISM", "SOC2"],
            environment="local",
            deployment_id="forgeroot-demo",
        ),

        # 4. Agent calls document retrieval tool
        _evt(
            event_id="demo-evt-004",
            event_type=EventType.AGENT_TOOL_CALL,
            event_time="2026-04-29T09:00:03Z",
            actor_id="agent.solution_designer",
            actor_type="agent",
            role="solution_engineer",
            source_module="CONCORD",
            decision_type="allow",
            reason="retrieval_authorised",
            risk_level="low",
            control_tags=["NZISM.LOGGING.EVENT_CAPTURE"],
            evidence_refs=SCENARIO_EVIDENCE_REFS,
            payload={
                "tool": "document_retrieval",
                "query": "2PB backup Veeam NZ data residency ransomware",
                "results_count": 4,
            },
        ),

        # 5. Azul safety verdict — response is safe to return
        AzulVerdictRecord(
            actor_id="azul.safety_engine",
            verdict="allow",
            reason="response_meets_safety_and_quality_standards",
            tenant_id=_DEMO_TENANT.tenant_id,
            customer_boundary=_DEMO_TENANT.customer_boundary,
            data_residency=_DEMO_TENANT.data_residency,
            policy_id="forgeroot_policy_nz_msp_v0.1",
            policy_hash="sha256:policy_hash_placeholder",
            safety_score=0.96,
            frameworks=["SOC2", "NZISM"],
            evidence_refs=SCENARIO_EVIDENCE_REFS,
            environment="local",
            deployment_id="forgeroot-demo",
        ),

        # 6. ForgeGate detects HIGH blast radius — escalate to human
        ForgeGateEvaluationResult(
            actor_id="forgegate.blast_radius_guard",
            decision_type="review",
            reason="blast_radius_exceeds_threshold_infrastructure_change",
            risk_level="high",
            tenant_id=_DEMO_TENANT.tenant_id,
            customer_boundary=_DEMO_TENANT.customer_boundary,
            data_residency=_DEMO_TENANT.data_residency,
            policy_id="forgeroot_policy_nz_msp_v0.1",
            policy_hash="sha256:policy_hash_placeholder",
            blast_radius_score=0.82,
            evidence_refs=SCENARIO_EVIDENCE_REFS,
            evidence_gaps=["missing_bom_pricing"],
            frameworks=["NZISM", "SOC2"],
            action_type="infrastructure_design",
            environment="local",
            deployment_id="forgeroot-demo",
        ),

        # 7. Agent escalates — human review required
        _evt(
            event_id="demo-evt-007",
            event_type=EventType.AGENT_HUMAN_REVIEW_REQUIRED,
            event_time="2026-04-29T09:00:06Z",
            actor_id="agent.solution_designer",
            actor_type="agent",
            role="solution_engineer",
            source_module="CONCORD",
            decision_type="review",
            reason="high_impact_infrastructure_design_requires_human_approval",
            risk_level="high",
            control_tags=["NZISM.CHANGE.HUMAN_APPROVAL", "SOC2.CC8.1"],
            evidence_refs=SCENARIO_EVIDENCE_REFS,
            evidence_gaps=[
                EvidenceGap(gap_type="customer_capacity_confirmation_required", blocking=True),
            ],
        ),

        # 8. Human architect approves the recommendation
        _evt(
            event_id="demo-evt-008",
            event_type=EventType.HUMAN_APPROVAL_DECISION,
            event_time="2026-04-29T09:05:00Z",
            actor_id="human.lead_architect",
            actor_type="human",
            role="lead_architect",
            source_module="CONCORD",
            decision_type="allow",
            reason="architect_approved_2pb_design_with_conditions",
            risk_level="low",
            control_tags=["NZISM.CHANGE.HUMAN_APPROVAL", "SOC2.CC8.1"],
            evidence_refs=SCENARIO_EVIDENCE_REFS,
            payload={
                "approval_note": (
                    "Approved subject to: (1) final BOM review, "
                    "(2) customer sign-off on capacity assumptions."
                ),
            },
        ),

        # 9. ForgeGate issues final allow after human approval
        ForgeGateEvaluationResult(
            actor_id="forgegate.policy_engine",
            decision_type="allow",
            reason="human_approval_received_action_permitted",
            risk_level="low",
            tenant_id=_DEMO_TENANT.tenant_id,
            customer_boundary=_DEMO_TENANT.customer_boundary,
            data_residency=_DEMO_TENANT.data_residency,
            policy_id="forgeroot_policy_nz_msp_v0.1",
            policy_hash="sha256:policy_hash_placeholder",
            evidence_refs=SCENARIO_EVIDENCE_REFS,
            frameworks=["NZISM", "SOC2"],
            action_type="final_approval",
            environment="local",
            deployment_id="forgeroot-demo",
        ),
    ]

    # Attach hash chain and persist
    finalized: list[LedgerEvent] = []
    prev_hash: Optional[str] = None
    concord_adapter = ConcordLedgerAdapter(backend)
    forgegate_adapter = ForgeGateLedgerAdapter(backend)
    warden_adapter = WardenLedgerAdapter(backend)
    azul_adapter = AzulLedgerAdapter(backend)
    for event in raw:
        if isinstance(event, ConcordAdmissionResult):
            emitted = concord_adapter.emit_admission_result(event)
            finalized.append(emitted)
            prev_hash = emitted.integrity.event_hash
            continue
        if isinstance(event, ForgeGateEvaluationResult):
            if event.action_type == "policy_evaluation":
                emitted = forgegate_adapter.emit_policy_evaluation_result(event)
            else:
                emitted = forgegate_adapter.emit_evaluation_result(event)
            finalized.append(emitted)
            prev_hash = emitted.integrity.event_hash
            continue
        if isinstance(event, WardenCallRecord):
            emitted = warden_adapter.emit_call_record(event)
            finalized.append(emitted)
            prev_hash = emitted.integrity.event_hash
            continue
        if isinstance(event, AzulVerdictRecord):
            emitted = azul_adapter.emit_verdict_record(event)
            finalized.append(emitted)
            prev_hash = emitted.integrity.event_hash
            continue
        chained = attach_integrity(event, prev_hash)
        backend.append_event(chained)
        finalized.append(chained)
        prev_hash = chained.integrity.event_hash

    return finalized


# ---------------------------------------------------------------------------
# Scenario summary builder
# ---------------------------------------------------------------------------

def _build_scenario_summary(
    events: list[LedgerEvent],
    chain_report: dict,
    coverage_report: dict,
    manifest: dict,
) -> dict:
    event_types = [e.event_type.value for e in events]
    human_review = EventType.AGENT_HUMAN_REVIEW_REQUIRED.value in event_types
    human_approved = EventType.HUMAN_APPROVAL_DECISION.value in event_types
    frameworks = coverage_report.get("frameworks_analysed", [])

    covered_counts = {
        fw: coverage_report["framework_reports"][fw]["covered"]
        for fw in frameworks
        if fw in coverage_report.get("framework_reports", {})
    }

    all_tags: set[str] = set()
    for e in events:
        all_tags.update(e.control_tags)

    return {
        "scenario": "2PB Regulated Backup Environment Design",
        "query": SCENARIO_QUERY,
        "agent_response_summary": SCENARIO_AGENT_RESPONSE_SUMMARY,
        "assertion_classes": ["FACT", "RECOMMENDATION", "APPROVAL_REQUIRED"],
        "evidence_refs": SCENARIO_EVIDENCE_REFS,
        "evidence_gaps_present": True,
        "human_review_triggered": human_review,
        "human_approval_received": human_approved,
        "total_events": len(events),
        "chain_valid": chain_report.get("valid", False),
        "frameworks_analysed": frameworks,
        "covered_controls_per_framework": covered_counts,
        "control_tags_emitted": sorted(all_tags),
        "evidence_package_claim_boundary": manifest.get("claim_boundary", ""),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_demo(
    output_dir: Path,
    framework_ids: Optional[list[str]] = None,
) -> DemoResult:
    """
    Run the full governed agent demo workflow.

    Emits nine ledger events covering the 2PB backup design scenario, builds a
    compliance coverage report for the requested frameworks, and exports a
    complete evidence package to `output_dir/evidence_package/`.

    Args:
        output_dir: Directory to write ledger.jsonl and evidence_package/.
        framework_ids: Frameworks to include in coverage analysis.
            Defaults to HIPC_2020, NIST_CSF_2_0, NZISM, SOC2.

    Returns:
        DemoResult with events, reports, and the evidence package manifest.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pkg_dir = output_dir / "evidence_package"
    framework_ids = framework_ids or _DEMO_FRAMEWORKS

    backend = JsonlBackend(output_dir / "ledger.jsonl")
    events = _emit_demo_events(backend)

    registry = ControlRegistry()
    coverage = generate_coverage_report(registry, events, framework_ids)
    chain_report = dataclasses.asdict(backend.verify_chain())

    builder = EvidencePackageBuilder(
        events,
        framework_ids=framework_ids,
        registry=registry,
        package_id="demo-pkg-2pb-backup-001",
        time_range_from=events[0].event_time,
        time_range_to=events[-1].event_time,
    )
    manifest = builder.build(pkg_dir)

    summary = _build_scenario_summary(events, chain_report, coverage, manifest)

    return DemoResult(
        events=events,
        chain_report=chain_report,
        coverage_report=coverage,
        evidence_package_dir=pkg_dir,
        manifest=manifest,
        scenario_summary=summary,
    )


# ---------------------------------------------------------------------------
# CLI convenience
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("./demo_output")
    result = run_demo(out)

    print("\n=== ForgeRoot Governed Agent Demo ===")
    print(f"Scenario : {result.scenario_summary['scenario']}")
    print(f"Events   : {result.scenario_summary['total_events']}")
    print(f"Chain OK : {result.scenario_summary['chain_valid']}")
    print(f"Frameworks: {', '.join(result.scenario_summary['frameworks_analysed'])}")
    print(f"Coverage  : {result.scenario_summary['covered_controls_per_framework']}")
    print(f"Human review triggered : {result.scenario_summary['human_review_triggered']}")
    print(f"Human approval received: {result.scenario_summary['human_approval_received']}")
    print(f"\nEvidence package: {result.evidence_package_dir}")
    print(f"Claim boundary  : {result.scenario_summary['evidence_package_claim_boundary']}")
