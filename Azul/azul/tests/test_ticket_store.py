"""
test_ticket_store.py — Persistence tests  (P0-3)
=================================================
Tests save, load, list, filter, and active→completed movement.
Uses a tmp directory so tests are isolated from production azul_data/.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import json
import pytest
import tempfile
from pathlib import Path

from azul.ticket import create_ticket, TicketStatus, TicketType
from azul.ticket_store import AzulTicketStore
from azul.lifecycle import (
    begin_provisioning, begin_evaluation, begin_gating, complete, reject, fail
)


@pytest.fixture
def tmp_store(tmp_path):
    """Fresh store backed by a temp directory for each test."""
    return AzulTicketStore(
        active_dir=tmp_path / "active",
        completed_dir=tmp_path / "completed",
    )


def make_ticket(**kwargs):
    defaults = dict(
        ticket_type="ci_gate",
        domain="ci_change_control",
        change_summary="Test",
    )
    defaults.update(kwargs)
    return create_ticket(**defaults)


# ── Save and load ─────────────────────────────────────────────────────────────

class TestSaveLoad:
    def test_save_and_get_submitted_ticket(self, tmp_store):
        t = make_ticket()
        tmp_store.save(t)
        loaded = tmp_store.get(t.ticket_id)
        assert loaded is not None
        assert loaded.ticket_id == t.ticket_id
        assert loaded.status == TicketStatus.SUBMITTED

    def test_get_nonexistent_returns_none(self, tmp_store):
        assert tmp_store.get("azul-does-not-exist") is None

    def test_save_updates_existing(self, tmp_store):
        t = make_ticket()
        tmp_store.save(t)
        begin_provisioning(t)
        tmp_store.save(t)
        loaded = tmp_store.get(t.ticket_id)
        assert loaded.status == TicketStatus.PROVISIONING

    def test_terminal_ticket_moves_to_completed(self, tmp_store):
        t = make_ticket()
        tmp_store.save(t)
        # Active path exists
        assert (tmp_store._active / f"{t.ticket_id}.json").exists()

        # Advance to terminal
        begin_provisioning(t)
        begin_evaluation(t)
        begin_gating(t)
        complete(t, xp=10)
        tmp_store.save(t)

        # Should be in completed, not in active
        assert (tmp_store._completed / f"{t.ticket_id}.json").exists()
        assert not (tmp_store._active / f"{t.ticket_id}.json").exists()

    def test_rejected_ticket_in_completed(self, tmp_store):
        t = make_ticket()
        begin_provisioning(t)
        begin_evaluation(t)
        begin_gating(t)
        reject(t)
        tmp_store.save(t)
        loaded = tmp_store.get(t.ticket_id)
        assert loaded.status == TicketStatus.REJECTED

    def test_failed_ticket_in_completed(self, tmp_store):
        t = make_ticket()
        fail(t)
        tmp_store.save(t)
        loaded = tmp_store.get(t.ticket_id)
        assert loaded.status == TicketStatus.FAILED

    def test_roundtrip_preserves_all_fields(self, tmp_store):
        t = make_ticket(
            ticket_type="distillation_pair",
            domain="my_domain",
            change_summary="Pair A",
            change_payload={"input": "Q", "output": "A"},
            source={"origin": "agent"},
            target_files=["foo.py"],
            priority="high",
            metadata={"loop_policy": {"max_iterations": 3}},
        )
        tmp_store.save(t)
        loaded = tmp_store.get(t.ticket_id)
        assert loaded.ticket_type.value == "distillation_pair"
        assert loaded.domain == "my_domain"
        assert loaded.change_payload == {"input": "Q", "output": "A"}
        assert loaded.target_files == ["foo.py"]
        assert loaded.priority.value == "high"
        assert loaded.metadata["loop_policy"]["max_iterations"] == 3

    def test_audit_signature_present_on_save(self, tmp_store):
        t = make_ticket()
        tmp_store.save(t)
        loaded = tmp_store.get(t.ticket_id)
        assert loaded is not None
        audit = loaded.metadata.get("audit", {})
        assert audit.get("algorithm") == "HMAC-SHA256"
        assert audit.get("signature")
        assert audit.get("payload_hash")
        assert "verdict" in audit.get("signed_fields", [])

    def test_audit_chain_hash_links_completed_tickets(self, tmp_store):
        first = make_ticket(change_summary="first")
        begin_provisioning(first); begin_evaluation(first); begin_gating(first); complete(first, xp=5)
        tmp_store.save(first)

        second = make_ticket(change_summary="second")
        begin_provisioning(second); begin_evaluation(second); begin_gating(second); complete(second, xp=5)
        tmp_store.save(second)

        loaded_first = tmp_store.get(first.ticket_id)
        loaded_second = tmp_store.get(second.ticket_id)
        assert loaded_first is not None and loaded_second is not None
        first_chain = loaded_first.metadata.get("audit", {}).get("chain_hash")
        second_prev = loaded_second.metadata.get("audit", {}).get("prev_chain_hash")
        assert first_chain
        assert second_prev == first_chain


# ── List and filter ───────────────────────────────────────────────────────────

class TestListAndFilter:
    def test_list_all(self, tmp_store):
        t1 = make_ticket(); tmp_store.save(t1)
        t2 = make_ticket(); tmp_store.save(t2)
        t3 = make_ticket(); tmp_store.save(t3)
        tickets = tmp_store.list()
        assert len(tickets) == 3

    def test_list_by_status(self, tmp_store):
        t1 = make_ticket(); tmp_store.save(t1)  # SUBMITTED
        t2 = make_ticket()
        begin_provisioning(t2); tmp_store.save(t2)  # PROVISIONING
        t3 = make_ticket()
        fail(t3); tmp_store.save(t3)  # FAILED

        submitted = tmp_store.list(status="SUBMITTED")
        assert len(submitted) == 1
        assert submitted[0].ticket_id == t1.ticket_id

        failed = tmp_store.list(status="FAILED")
        assert len(failed) == 1

    def test_list_by_ticket_type(self, tmp_store):
        t1 = make_ticket(ticket_type="ci_gate"); tmp_store.save(t1)
        t2 = make_ticket(ticket_type="refactor"); tmp_store.save(t2)
        t3 = make_ticket(ticket_type="ci_gate"); tmp_store.save(t3)

        ci_tickets = tmp_store.list(ticket_type="ci_gate")
        assert len(ci_tickets) == 2

    def test_list_active_excludes_terminal(self, tmp_store):
        active = make_ticket(); tmp_store.save(active)
        terminal = make_ticket()
        fail(terminal); tmp_store.save(terminal)

        result = tmp_store.list_active()
        assert len(result) == 1
        assert result[0].ticket_id == active.ticket_id

    def test_list_completed_only_terminal(self, tmp_store):
        active = make_ticket(); tmp_store.save(active)
        t = make_ticket()
        begin_provisioning(t); begin_evaluation(t); begin_gating(t)
        complete(t, xp=5); tmp_store.save(t)

        result = tmp_store.list_completed()
        assert len(result) == 1
        assert result[0].ticket_id == t.ticket_id

    def test_exists(self, tmp_store):
        t = make_ticket(); tmp_store.save(t)
        assert tmp_store.exists(t.ticket_id)
        assert not tmp_store.exists("azul-missing")

    def test_delete(self, tmp_store):
        t = make_ticket(); tmp_store.save(t)
        assert tmp_store.exists(t.ticket_id)
        deleted = tmp_store.delete(t.ticket_id)
        assert deleted
        assert not tmp_store.exists(t.ticket_id)
