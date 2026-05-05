"""
test_training_pairs.py — Training pair emission tests  (P1-2)
=============================================================
Verifies that:
- Verified distillation_pair tickets emit a training pair.
- Rejected / failed tickets do NOT emit.
- Non-distillation ticket types do NOT emit.
- TrainingPairStore queries work correctly (domain filter, min_score).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import json
import pytest
from pathlib import Path

from azul.ticket import create_ticket, TicketStatus, TicketType
from azul.lifecycle import begin_provisioning, begin_evaluation, begin_gating, complete, reject, warn, fail
from azul.training_pairs import emit_training_pair, TrainingPairStore


@pytest.fixture
def tmp_pair_store(tmp_path, monkeypatch):
    """Monkeypatch TRAINING_PAIRS_DIR so pairs land in tmp_path."""
    import azul.training_pairs as tp_module
    monkeypatch.setattr(tp_module, "TRAINING_PAIRS_DIR", tmp_path)
    store = TrainingPairStore(directory=tmp_path)
    return store, tmp_path


def make_distillation_ticket(
    score: float = 92.0,
    verdict: str = "pass",   # set after construction for flexibility
    status = None,
    xp: int = 14,
) -> "AzulTicket":
    t = create_ticket(
        ticket_type="distillation_pair",
        domain="ci_change_control",
        change_summary="Candidate pair",
        change_payload={"input": "What is 2+2?", "output": "4"},
    )
    t.review_bundle = {
        "metrics": {"total_score": score, "pass_fail": True},
        "bundle_id": "b-dist-001",
    }
    begin_provisioning(t)
    begin_evaluation(t)
    begin_gating(t)
    if verdict == "pass":
        complete(t, xp=xp)
    else:
        reject(t)
    return t


# ── Emission ──────────────────────────────────────────────────────────────────

class TestEmitTrainingPair:
    def test_emit_on_completed_distillation(self, tmp_pair_store):
        store, tmp_path = tmp_pair_store
        t = make_distillation_ticket(score=92.0, xp=14)
        pair = emit_training_pair(t)

        assert pair is not None
        assert pair["pair_id"] == f"tp-{t.ticket_id}"
        assert pair["input"] == "What is 2+2?"
        assert pair["output"] == "4"
        assert pair["verification_score"] == 92.0
        assert pair["verification_bundle_id"] == "b-dist-001"
        assert pair["xp_awarded"] == 14
        assert pair["domain"] == "ci_change_control"
        assert pair["ticket_id"] == t.ticket_id

        # File should be written
        pair_file = tmp_path / f"tp-{t.ticket_id}.json"
        assert pair_file.exists()

    def test_no_emit_on_rejected_distillation(self, tmp_pair_store):
        store, tmp_path = tmp_pair_store
        t = make_distillation_ticket(verdict="reject")
        pair = emit_training_pair(t)
        assert pair is None
        # No file written
        assert list(tmp_path.glob("*.json")) == []

    def test_no_emit_for_ci_gate_type(self, tmp_pair_store):
        store, tmp_path = tmp_pair_store
        t = create_ticket(
            ticket_type="ci_gate",
            domain="ci_change_control",
            change_summary="CI ticket",
            change_payload={"diff": "--- a/foo.py"},
        )
        begin_provisioning(t)
        begin_evaluation(t)
        begin_gating(t)
        complete(t, xp=10)
        pair = emit_training_pair(t)
        assert pair is None

    def test_no_emit_without_input_output(self, tmp_pair_store):
        store, tmp_path = tmp_pair_store
        t = create_ticket(
            ticket_type="distillation_pair",
            domain="ci_change_control",
            change_summary="Bad pair",
            change_payload={"raw": "no input/output"},  # missing required fields
        )
        begin_provisioning(t)
        begin_evaluation(t)
        begin_gating(t)
        complete(t, xp=5)
        pair = emit_training_pair(t)
        assert pair is None

    def test_emit_warned_distillation(self, tmp_pair_store):
        """WARNED verdict (pass with warnings) also emits a pair."""
        store, tmp_path = tmp_pair_store
        t = create_ticket(
            ticket_type="distillation_pair",
            domain="ci_change_control",
            change_summary="Warned pair",
            change_payload={"input": "Q2", "output": "A2"},
        )
        t.review_bundle = {"metrics": {"total_score": 75.0, "pass_fail": True}, "bundle_id": "b-warn"}
        begin_provisioning(t)
        begin_evaluation(t)
        begin_gating(t)
        warn(t, xp=12)
        pair = emit_training_pair(t)
        assert pair is not None
        assert pair["input"] == "Q2"

    def test_provenance_bundle_id_none_when_no_bundle(self, tmp_pair_store):
        """If ticket has no review_bundle, bundle_id is None and score is 0."""
        store, tmp_path = tmp_pair_store
        t = create_ticket(
            ticket_type="distillation_pair",
            domain="ci_change_control",
            change_summary="No bundle",
            change_payload={"input": "X", "output": "Y"},
        )
        begin_provisioning(t)
        begin_evaluation(t)
        begin_gating(t)
        complete(t, xp=5)
        pair = emit_training_pair(t)
        assert pair is not None
        assert pair["verification_bundle_id"] is None
        assert pair["verification_score"] == 0.0


# ── TrainingPairStore query ───────────────────────────────────────────────────

class TestTrainingPairStore:
    def test_get_pairs_returns_all(self, tmp_pair_store):
        store, tmp_path = tmp_pair_store
        t1 = make_distillation_ticket(score=90.0)
        t2 = make_distillation_ticket(score=75.0)
        emit_training_pair(t1)
        emit_training_pair(t2)

        pairs = store.get_pairs()
        assert len(pairs) == 2
        # Sorted by score descending
        assert pairs[0]["verification_score"] >= pairs[1]["verification_score"]

    def test_get_pairs_min_score_filter(self, tmp_pair_store):
        store, tmp_path = tmp_pair_store
        t1 = make_distillation_ticket(score=90.0)
        t2 = make_distillation_ticket(score=60.0)
        emit_training_pair(t1)
        emit_training_pair(t2)

        pairs = store.get_pairs(min_score=80.0)
        assert len(pairs) == 1
        assert pairs[0]["verification_score"] == 90.0

    def test_get_pairs_domain_filter(self, tmp_pair_store):
        store, tmp_path = tmp_pair_store
        t1 = make_distillation_ticket(score=90.0)
        t1.domain = "some_other_domain"  # Mutate after construction
        # Re-emit with mutated domain
        import azul.training_pairs as tp
        import json
        pair = {
            "pair_id": f"tp-{t1.ticket_id}",
            "input": "Q", "output": "A",
            "verification_score": 90.0,
            "verification_bundle_id": None,
            "xp_awarded": 0, "domain": "some_other_domain",
            "verified_at": "2026-01-01T00:00:00Z",
            "ticket_id": t1.ticket_id,
        }
        (tmp_path / f"tp-{t1.ticket_id}.json").write_text(json.dumps(pair))

        t2 = make_distillation_ticket(score=85.0)
        emit_training_pair(t2)

        ci_pairs = store.get_pairs(domain="ci_change_control")
        assert all(p["domain"] == "ci_change_control" for p in ci_pairs)

    def test_count(self, tmp_pair_store):
        store, tmp_path = tmp_pair_store
        assert store.count() == 0
        t = make_distillation_ticket()
        emit_training_pair(t)
        assert store.count() == 1

    def test_empty_store_returns_empty_list(self, tmp_pair_store):
        store, _ = tmp_pair_store
        assert store.get_pairs() == []
