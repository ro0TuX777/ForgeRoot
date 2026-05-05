import json

from azul.lifecycle import begin_provisioning, begin_evaluation, begin_gating, complete
from azul.loop.orchestrator import LoopOrchestrator
from azul.ticket import create_ticket
from azul.ticket_store import AzulTicketStore
from azul.training_pairs import TrainingPairStore


def _make_completed_ticket():
    ticket = create_ticket(
        ticket_type="ci_gate",
        domain="ci_change_control",
        change_summary="Loop trigger test",
        change_payload={"diff": "--- a/x\n+++ b/x\n"},
    )
    ticket.review_bundle = {"metrics": {"total_score": 92.0, "deny_count": 0}, "bundle_id": "rb-1"}
    begin_provisioning(ticket)
    begin_evaluation(ticket)
    begin_gating(ticket)
    complete(ticket, xp=5)
    return ticket


def test_orchestrator_threshold_trigger(tmp_path, monkeypatch):
    monkeypatch.setenv("AZUL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FORGE_LOOP_THRESHOLD_WINDOW", "1")

    contracts = tmp_path / "contracts" / "active"
    policies = tmp_path / "policies"
    contracts.mkdir(parents=True)
    policies.mkdir(parents=True)
    (contracts / "external_subprocess.yaml").write_text(
        "unit_id: external.subprocess\nactions:\n  - id: check_call\n    guard_predicates: ['safe']\n",
        encoding="utf-8",
    )
    (policies / "default.yaml").write_text(
        "min_score: 70\nwarn_score: 80\nmax_deny_count: 2\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FORGE_ATLAS_CATALOG_PATH", str(tmp_path / "contracts"))
    monkeypatch.setenv("AZUL_GATE_POLICIES_DIR", str(policies))

    store = AzulTicketStore(active_dir=tmp_path / "tickets" / "active", completed_dir=tmp_path / "tickets" / "completed")
    ticket = _make_completed_ticket()
    store.save(ticket)

    orchestrator = LoopOrchestrator(ticket_store=store)
    result = orchestrator.on_ticket_completed(ticket)

    assert result is not None
    assert result["status"] == "ok"
    report_path = result["report_path"]
    assert report_path
    payload = json.loads((tmp_path / "loop_state.json").read_text(encoding="utf-8"))
    assert payload["last_ticket_id"] == ticket.ticket_id


def test_orchestrator_records_metadata_labels(tmp_path, monkeypatch):
    monkeypatch.setenv("AZUL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FORGE_LOOP_THRESHOLD_WINDOW", "1000")

    ticket = _make_completed_ticket()
    ticket.metadata = {
        "verdict_override": {
            "original_verdict": {"verdict": "reject", "reason": "strict block"},
            "approved_verdict": {"verdict": "pass", "reason": "human approved"},
            "reviewer_id": "lead_one",
            "reason": "known-safe exception",
        },
        "policy_edit": {
            "policy_name": "ci_change_control",
            "original": {"min_score": 70},
            "approved": {"min_score": 75},
            "reviewer_id": "lead_two",
        },
    }

    orchestrator = LoopOrchestrator()
    orchestrator.on_ticket_completed(ticket)

    labels_file = tmp_path / "gold_labels" / "gold_labels.jsonl"
    rows = [json.loads(line) for line in labels_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    artifact_types = {row["artifact_type"] for row in rows}
    assert "verdict_override" in artifact_types
    assert "gate_policy_recommendation" in artifact_types


def test_orchestrator_distillation_batch_data_prep_only(tmp_path, monkeypatch):
    monkeypatch.setenv("AZUL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FORGE_LOOP_DISTILL_BATCH_SIZE", "2")
    monkeypatch.setenv("FORGE_LOOP_DISTILL_MIN_SCORE", "90")

    pairs_dir = tmp_path / "training_pairs"
    pairs_dir.mkdir(parents=True)
    (pairs_dir / "tp-1.json").write_text(
        json.dumps({"pair_id": "tp-1", "verification_score": 91.0, "domain": "ci_change_control"}),
        encoding="utf-8",
    )
    (pairs_dir / "tp-2.json").write_text(
        json.dumps({"pair_id": "tp-2", "verification_score": 93.0, "domain": "ci_change_control"}),
        encoding="utf-8",
    )

    orchestrator = LoopOrchestrator(pair_store=TrainingPairStore(directory=pairs_dir))
    batch = orchestrator.run_distillation_batch()
    assert batch is not None
    manifest = json.loads(open(batch.manifest_path, "r", encoding="utf-8").read())
    assert manifest["mode"] == "data_prep_only"
    assert manifest["pair_count"] == 2
