import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..core.hashutil import compute_workcell_hash
from ..core.io import load_json, load_jsonl
from ..core.preflight import PreflightError, run_preflight
from ..core.validate import validate_workcell
from ..core.drift_inject import DriftPlanError, apply_drift_events, load_drift_plan, validate_drift_plan
from .approvals import ApprovalPolicyError, resolve_approval
from .forgegate_bridge import ForgeGateBridgeError, evaluate_action
from .outcomes import write_approvals, write_ledger, write_run_summary, write_ticket_outcome
from .tokio_baton import RelayBaton
from .ticket_ledger import get_ticket_ledger
from .phases import run_builder, run_deployer, run_judge, run_legislator, run_scout
from .phase_transition import PhaseTransitionController, assert_vram_clear
from .step_config import PHASE_CONFIG_BY_NAME, ErrorMode


class RunnerError(Exception):
    pass


def _stable_ticket_order(tickets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(tickets, key=lambda t: t.get("ticket_id", ""))


def _signals_by_ticket(signals: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    for record in signals:
        ticket_id = record.get("ticket_id")
        if not ticket_id:
            continue
        mapping[ticket_id] = record
    return mapping


def _phase_actions() -> List[Tuple[str, str]]:
    return [
        ("Scout", "phase.scout"),
        ("Legislator", "phase.legislator"),
        ("Builder", "phase.builder"),
    ]


def _action_risk(action_id: str) -> Tuple[str, str]:
    mapping = {
        "phase.scout": ("low", "none"),
        "phase.legislator": ("low", "none"),
        "phase.builder": ("med", "write"),
        "execute_sandbox_test": ("critical", "external_write"),
        "deploy_verified_artifact": ("high", "write"),
    }
    return mapping.get(action_id, ("med", "write"))


def _proposed_action(ticket: Dict[str, Any], action_id: str, phase: str) -> Dict[str, Any]:
    risk_tier, side_effect = _action_risk(action_id)
    return {
        "schema_version": "0.1",
        "action_id": action_id,
        "actor_id": "forgeworks.runner",
        "actor_profile": "shadow",
        "params": {
            "ticket_id": ticket.get("ticket_id"),
            "domain": ticket.get("domain"),
            "phase": phase,
            "type": ticket.get("type"),
        },
        "metadata": {"risk_tier": risk_tier, "side_effect": side_effect},
    }


def _ticket_intent(ticket: Dict[str, Any]) -> str:
    intent = ticket.get("ticket_intent")
    if intent:
        return intent
    ticket_type = ticket.get("type", "")
    failing_test = ticket.get("inputs", {}).get("failing_test")
    if failing_test:
        return f"Fix CI failure: {failing_test}"
    if ticket_type:
        return f"{ticket_type} ticket"
    return f"Ticket {ticket.get('ticket_id', '')}"


def _run_id(workcell_hash: str, mode: str) -> str:
    return hashlib.sha256(f"{workcell_hash}:{mode}".encode("utf-8")).hexdigest()[:8]


def run_workcell(workcell_path: str, out_dir: str, mode: str = "shadow", drift_plan_path: str | None = None) -> Dict[str, Any]:
    if mode not in {"shadow", "supervised", "ramped"}:
        raise RunnerError("unsupported mode")

    workcell = Path(workcell_path)
    validate_workcell(str(workcell))

    tickets = load_jsonl(workcell / "tickets.jsonl")
    signals = load_jsonl(workcell / "signals.jsonl")
    run_config = load_json(workcell / "run_config.json")

    if os.environ.get("FORGEWORKS_RUN_PREFLIGHT") == "1":
        try:
            run_preflight(run_config)
        except PreflightError as exc:
            raise RunnerError(f"preflight failed: {exc}") from exc

    intent_path = run_config.get("intent_bundle_path", "")
    if not intent_path:
        raise RunnerError("intent_bundle_path missing in run_config")

    intent_bundle_path = str((workcell / intent_path).resolve())

    ordered = _stable_ticket_order(tickets)
    signal_map = _signals_by_ticket(signals)

    ledger_entries: List[Dict[str, Any]] = []
    approval_records: List[Dict[str, Any]] = []
    drift_events: List[Dict[str, Any]] = []
    out = Path(out_dir)
    ledger = get_ticket_ledger()
    ledger.reap_expired_claims()
    ledger.evict_old_runs(keep_days=30)  # trim rows older than 30 days

    # Pre-flight: ensure VRAM is clear before beginning any ticket run.
    # This evicts any lingering model from a previous run or manual test.
    assert_vram_clear()
    controller = PhaseTransitionController()

    drift_plan = None
    if drift_plan_path:
        try:
            drift_plan = load_drift_plan(drift_plan_path)
            validate_drift_plan(drift_plan)
        except DriftPlanError as exc:
            raise RunnerError(str(exc)) from exc
    events = drift_plan.get("events", []) if drift_plan else []
    step_counter = 0

    for ticket in ordered:
        ticket_id = ticket.get("ticket_id")
        domain = ticket.get("domain", "")
        claim_id = ledger.try_claim(str(ticket_id), agent_id="forgeworks.runner")
        if claim_id is None:
            continue
        run_id = ledger.start_run(str(ticket_id), metadata={"mode": mode})
        phases_visited: List[str] = []
        actions_proposed: List[str] = []
        decisions_received: List[str] = []
        approval_events: List[Dict[str, Any]] = []
        signal_record = signal_map.get(ticket_id, {"schema_version": "0.1", "values": {}})
        signals_values = dict(signal_record.get("values", {}))
        work_dir = out / "work" / str(ticket_id)
        work_dir.mkdir(parents=True, exist_ok=True)
        baton = RelayBaton(ticket_id=str(ticket_id), ticket_intent=_ticket_intent(ticket))
        baton.save_to_disk(str(work_dir / "baton.json"))

        def record_decision(phase: str, action_id: str, decision: Dict[str, Any], proposed: Dict[str, Any]) -> None:
            nonlocal step_counter
            approval_event = None
            if mode in {"supervised", "ramped"}:
                try:
                    approval_event = resolve_approval(ticket_id, action_id, decision, proposed, mode, run_config)
                except ApprovalPolicyError as exc:
                    raise RunnerError(str(exc)) from exc
                approval_records.append(approval_event)
            decisions_received.append(decision.get("decision", ""))
            ledger_entries.append(
                {
                    "schema_version": "0.1",
                    "ticket_id": ticket_id,
                    "domain": domain,
                    "phase": phase,
                    "action_id": action_id,
                    "decision_record": decision,
                }
            )
            if approval_event:
                approval_events.append(approval_event)
            step_counter += 1

        try:
            # ── Phase 1: Scout (reasoning_model) ──────────────────────────────
            phases_visited.append("Scout")
            actions_proposed.append("phase.scout")
            if events:
                drift_events.extend(apply_drift_events(events, step_counter, signals_values))
            proposed = _proposed_action(ticket, "phase.scout", "Scout")
            try:
                decision = evaluate_action(intent_bundle_path, proposed, {"schema_version": "0.1", "values": signals_values})
            except ForgeGateBridgeError as exc:
                raise RunnerError(str(exc)) from exc
            record_decision("Scout", "phase.scout", decision, proposed)
            _t0 = __import__("time").monotonic()
            with controller.transition(from_phase=None, to_phase=1, ticket_id=ticket_id):
                run_scout(baton, str(work_dir))
            baton.record_phase_metric("Scout", __import__("time").monotonic() - _t0)
            baton.save_to_disk(str(work_dir / "baton.json"))

            # ── Phase 2: Legislator (reasoning_model) ─────────────────────────
            phases_visited.append("Legislator")
            actions_proposed.append("phase.legislator")
            if events:
                drift_events.extend(apply_drift_events(events, step_counter, signals_values))
            proposed = _proposed_action(ticket, "phase.legislator", "Legislator")
            try:
                decision = evaluate_action(intent_bundle_path, proposed, {"schema_version": "0.1", "values": signals_values})
            except ForgeGateBridgeError as exc:
                raise RunnerError(str(exc)) from exc
            record_decision("Legislator", "phase.legislator", decision, proposed)
            _t0 = __import__("time").monotonic()
            with controller.transition(from_phase=1, to_phase=2, ticket_id=ticket_id):
                run_legislator(baton, str(work_dir))
            baton.record_phase_metric("Legislator", __import__("time").monotonic() - _t0)
            baton.save_to_disk(str(work_dir / "baton.json"))

            # ── Phase 3: Builder (code_model) ─────────────────────────────────
            phases_visited.append("Builder")
            actions_proposed.append("phase.builder")
            if events:
                drift_events.extend(apply_drift_events(events, step_counter, signals_values))
            proposed = _proposed_action(ticket, "phase.builder", "Builder")
            try:
                decision = evaluate_action(intent_bundle_path, proposed, {"schema_version": "0.1", "values": signals_values})
            except ForgeGateBridgeError as exc:
                raise RunnerError(str(exc)) from exc
            record_decision("Builder", "phase.builder", decision, proposed)
            # ── Approval gate: supervised mode blocks before Builder (write risk) ──
            if mode == "supervised":
                gate_id = ledger.request_gate(
                    run_id=run_id, ticket_id=str(ticket_id),
                    phase_name="Builder", action_id="phase.builder", risk_tier="med"
                )
                if os.environ.get("FORGEWORKS_AUTO_APPROVE") == "1":
                    ledger.resolve_gate(gate_id, "approved", resolved_by="auto")
                    decision_str = "approved"
                else:
                    decision_str = ledger.wait_for_gate(gate_id, timeout_sec=450)
                if decision_str != "approved":
                    ledger.skip_run(run_id, reason=f"Builder gate {decision_str}")
                    ledger.release_claim(claim_id, status="done")
                    continue
            _t0 = __import__("time").monotonic()
            with controller.transition(from_phase=2, to_phase=3, ticket_id=ticket_id):
                run_builder(baton, str(work_dir))
            baton.record_phase_metric("Builder", __import__("time").monotonic() - _t0)
            baton.save_to_disk(str(work_dir / "baton.json"))

            # Phase 4 (Judge) with retry loop
            while True:
                phases_visited.append("Judge")
                actions_proposed.append("execute_sandbox_test")
                if events:
                    drift_events.extend(apply_drift_events(events, step_counter, signals_values))
                proposed = _proposed_action(ticket, "execute_sandbox_test", "Judge")
                decision = run_judge(baton, str(work_dir))
                record_decision("Judge", "execute_sandbox_test", decision, proposed)
                baton.save_to_disk(str(work_dir / "baton.json"))

                if baton.current_phase == 3:
                    # Judge kicked back — retry Builder (code_model) then Judge again
                    phases_visited.append("Builder")
                    actions_proposed.append("phase.builder")
                    if events:
                        drift_events.extend(apply_drift_events(events, step_counter, signals_values))
                    proposed = _proposed_action(ticket, "phase.builder", "Builder")
                    try:
                        decision = evaluate_action(
                            intent_bundle_path, proposed, {"schema_version": "0.1", "values": signals_values}
                        )
                    except ForgeGateBridgeError as exc:
                        raise RunnerError(str(exc)) from exc
                    record_decision("Builder", "phase.builder", decision, proposed)
                    # No from_phase here — VRAM was already clean after Judge (no LLM)
                    _t0 = __import__("time").monotonic()
                    with controller.transition(from_phase=None, to_phase=3, ticket_id=ticket_id):
                        run_builder(baton, str(work_dir))
                    baton.record_phase_metric(
                        f"Builder_retry{baton.retry_count}", __import__("time").monotonic() - _t0
                    )
                    baton.save_to_disk(str(work_dir / "baton.json"))
                    continue

                break

            # Phase 5 (Deployer) if Judge succeeded
            if baton.current_phase == 5:
                phases_visited.append("Deployer")
                actions_proposed.append("deploy_verified_artifact")
                if events:
                    drift_events.extend(apply_drift_events(events, step_counter, signals_values))
                proposed = _proposed_action(ticket, "deploy_verified_artifact", "Deployer")
                # ── Approval gate: supervised mode blocks before Deployer (high risk write) ──
                if mode == "supervised":
                    gate_id = ledger.request_gate(
                        run_id=run_id, ticket_id=str(ticket_id),
                        phase_name="Deployer", action_id="deploy_verified_artifact",
                        risk_tier="high"
                    )
                    if os.environ.get("FORGEWORKS_AUTO_APPROVE") == "1":
                        ledger.resolve_gate(gate_id, "approved", resolved_by="auto")
                        decision_str = "approved"
                    else:
                        decision_str = ledger.wait_for_gate(gate_id, timeout_sec=450)
                    if decision_str != "approved":
                        ledger.skip_run(run_id, reason=f"Deployer gate {decision_str}")
                        ledger.release_claim(claim_id, status="done")
                        continue
                _t0 = __import__("time").monotonic()
                decision = run_deployer(baton, str(work_dir), shadow=(mode == "shadow"))
                baton.record_phase_metric("Deployer", __import__("time").monotonic() - _t0)
                record_decision("Deployer", "deploy_verified_artifact", decision, proposed)
                baton.save_to_disk(str(work_dir / "baton.json"))

            outcome = {
                "ticket_id": ticket_id,
                "domain": domain,
                "phases_visited": phases_visited,
                "actions_proposed": actions_proposed,
                "decisions_received": decisions_received,
                "approval_events": approval_events,
                "final_status": "failed" if baton.current_phase == 99 else "completed",
                "phase_timing": baton.phase_timing,
                "phase_tokens": baton.phase_tokens,
            }
            write_ticket_outcome(out, ticket_id, outcome)
            ledger.complete_run(
                run_id,
                metadata_update={
                    "final_status": outcome["final_status"],
                    "phase_timing": baton.phase_timing,
                    "phase_tokens": baton.phase_tokens,
                },
            )
        except Exception as exc:
            ledger.fail_run(run_id, error=exc)
            raise
        finally:
            ledger.release_claim(claim_id, status="done")

    ledger_path = write_ledger(out, ledger_entries)
    approval_path = None
    if mode in {"supervised", "ramped"}:
        approval_path = write_approvals(out, approval_records)

    penalty_summary_md = out / "penalty_trigger_summary.md"
    penalty_summary_json = out / "penalty_trigger_summary.json"

    workcell_hash = compute_workcell_hash(str(workcell))
    run_id = _run_id(workcell_hash, mode)

    approval_count = len(approval_records)
    approved_count = len([a for a in approval_records if a.get("approval_outcome") == "APPROVED"])
    rejected_count = len([a for a in approval_records if a.get("approval_outcome") == "REJECTED"])
    escalation_count = len(
        [
            entry
            for entry in ledger_entries
            if entry.get("decision_record", {}).get("decision") == "ESCALATE"
        ]
    )
    escalation_rate = escalation_count / max(1, len(ledger_entries))
    deny_count = len(
        [
            entry
            for entry in ledger_entries
            if entry.get("decision_record", {}).get("decision") == "DENY"
        ]
    )
    deny_rate = deny_count / max(1, len(ledger_entries))

    summary = {
        "run_id": run_id,
        "workcell_path": str(workcell),
        "mode": mode,
        "ticket_count": len(ordered),
        "decision_count": len(ledger_entries),
        "approval_count": approval_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "escalation_count": escalation_count,
        "escalation_rate": round(escalation_rate, 4),
        "deny_count": deny_count,
        "deny_rate": round(deny_rate, 4),
        "ledger_path": str(ledger_path),
        "approval_records_path": str(approval_path) if approval_path else None,
        "penalty_trigger_summary_md": str(penalty_summary_md) if penalty_summary_md.exists() else None,
        "penalty_trigger_summary_json": str(penalty_summary_json) if penalty_summary_json.exists() else None,
        "workcell_hash": workcell_hash,
        "drift_events_applied": drift_events,
    }
    write_run_summary(out, summary)
    return summary


def run_shadow(workcell_path: str, out_dir: str) -> Dict[str, Any]:
    return run_workcell(workcell_path, out_dir, mode="shadow")
