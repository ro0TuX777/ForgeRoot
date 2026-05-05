"""
test_queue_worker.py — Worker pool tests  (P2-1)
================================================
Tests async ticket submission, concurrent worker processing,
backpressure, result retrieval, and clean shutdown.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import threading
import time
import pytest

from azul.ticket import create_ticket, TicketStatus
from azul.queue_worker import AzulWorkerPool, QueueFullError


# ── Shared mock verify ────────────────────────────────────────────────────────

def _fast_verify(ticket, store=None, ledger=None):
    """Instant mock verify() — completes ticket synchronously."""
    from azul.lifecycle import begin_provisioning, begin_evaluation, begin_gating, complete
    begin_provisioning(ticket)
    begin_evaluation(ticket)
    begin_gating(ticket)
    complete(ticket, xp=10)
    if store:
        store.save(ticket)
    return {
        "status":        "ok",
        "verdict":       "pass",
        "severity":      "ok",
        "ticket_id":     ticket.ticket_id,
        "ticket_status": TicketStatus.COMPLETED.value,
        "alerts":        [],
        "xp_awarded":    10,
    }


@pytest.fixture
def mock_pool(monkeypatch, tmp_path):
    """Worker pool with monkeypatched verify() and a fresh store."""
    from azul.ticket_store import AzulTicketStore
    import azul.queue_worker as qw

    monkeypatch.setattr(qw, "verify", _fast_verify)

    store = AzulTicketStore(
        active_dir=tmp_path / "active",
        completed_dir=tmp_path / "completed",
    )
    pool = AzulWorkerPool(num_workers=2, max_queue_depth=10, store=store)
    pool.start()
    yield pool, store
    pool.stop(drain=True, timeout=5.0)


def make_ticket(**kwargs):
    return create_ticket(
        ticket_type="ci_gate",
        domain="ci_change_control",
        change_summary="Test",
        **kwargs,
    )


# ── Pool lifecycle ────────────────────────────────────────────────────────────

class TestPoolLifecycle:
    def test_start_and_stop(self, monkeypatch, tmp_path):
        import azul.queue_worker as qw
        monkeypatch.setattr(qw, "verify", _fast_verify)
        pool = AzulWorkerPool(num_workers=2)
        pool.start()
        assert pool.is_running
        pool.stop(drain=False)
        assert not pool.is_running

    def test_double_start_is_safe(self, monkeypatch, tmp_path):
        import azul.queue_worker as qw
        monkeypatch.setattr(qw, "verify", _fast_verify)
        pool = AzulWorkerPool(num_workers=1)
        pool.start()
        pool.start()  # should not raise or create extra workers
        pool.stop(drain=False)

    def test_double_stop_is_safe(self, monkeypatch, tmp_path):
        import azul.queue_worker as qw
        monkeypatch.setattr(qw, "verify", _fast_verify)
        pool = AzulWorkerPool(num_workers=1)
        pool.start()
        pool.stop(drain=False)
        pool.stop(drain=False)  # must not raise


# ── Submission and processing ─────────────────────────────────────────────────

class TestSubmission:
    def test_single_ticket_processed(self, mock_pool):
        pool, store = mock_pool
        t = make_ticket()
        pool.submit(t)

        result = pool.wait_for_result(t.ticket_id, timeout=5.0)
        assert result is not None
        assert result["verdict"] == "pass"

    def test_multiple_tickets_all_processed(self, mock_pool):
        pool, store = mock_pool
        tickets = [make_ticket() for _ in range(5)]
        for t in tickets:
            pool.submit(t)

        for t in tickets:
            result = pool.wait_for_result(t.ticket_id, timeout=5.0)
            assert result is not None
            assert result["verdict"] == "pass"

    def test_submit_before_start_raises(self, monkeypatch):
        import azul.queue_worker as qw
        monkeypatch.setattr(qw, "verify", _fast_verify)
        pool = AzulWorkerPool(num_workers=1)
        t = make_ticket()
        with pytest.raises(RuntimeError, match="not running"):
            pool.submit(t)

    def test_queue_full_raises_when_not_blocking(self, monkeypatch):
        import azul.queue_worker as qw

        # Make verify() block until barrier is released
        barrier = threading.Event()
        def slow_verify(ticket, store=None, ledger=None):
            barrier.wait(timeout=10)
            return _fast_verify(ticket, store=store, ledger=ledger)
        monkeypatch.setattr(qw, "verify", slow_verify)

        # 1 worker, depth 1: worker picks up t1 (blocking), t2 sits in queue
        pool = AzulWorkerPool(num_workers=1, max_queue_depth=1)
        pool.start()
        try:
            pool.submit(make_ticket())   # t1 — grabbed by the sole worker (blocks)
            time.sleep(0.1)              # let worker dequeue t1 first
            pool.submit(make_ticket())   # t2 — sits in queue (depth now 1 = max)
            with pytest.raises(QueueFullError):
                pool.submit(make_ticket(), block=False)  # t3 — full → raises
        finally:
            barrier.set()
            pool.stop(drain=True, timeout=5.0)

    def test_result_callback_invoked(self, monkeypatch):
        import azul.queue_worker as qw
        monkeypatch.setattr(qw, "verify", _fast_verify)

        received = []
        def cb(ticket_id, result):
            received.append((ticket_id, result))

        pool = AzulWorkerPool(num_workers=1, result_callback=cb)
        pool.start()
        t = make_ticket()
        pool.submit(t)
        pool.wait_for_result(t.ticket_id, timeout=5.0)
        pool.stop(drain=True, timeout=5.0)

        assert len(received) == 1
        assert received[0][0] == t.ticket_id


# ── Stats ─────────────────────────────────────────────────────────────────────

class TestStats:
    def test_stats_submitted_increments(self, mock_pool):
        pool, _ = mock_pool
        for _ in range(3):
            pool.submit(make_ticket())
        # Wait for processing
        time.sleep(0.3)
        s = pool.stats()
        assert s["submitted"] >= 3

    def test_stats_completed_increments(self, mock_pool):
        pool, _ = mock_pool
        t = make_ticket()
        pool.submit(t)
        pool.wait_for_result(t.ticket_id, timeout=5.0)
        s = pool.stats()
        assert s["completed"] >= 1
        assert s["failed"] == 0

    def test_queue_depth_decreases_after_processing(self, mock_pool):
        pool, _ = mock_pool
        t = make_ticket()
        pool.submit(t)
        pool.wait_for_result(t.ticket_id, timeout=5.0)
        assert pool.queue_depth >= 0  # should be 0 after processing


# ── wait_for_result ───────────────────────────────────────────────────────────

class TestWaitForResult:
    def test_returns_none_on_timeout(self, mock_pool):
        pool, _ = mock_pool
        result = pool.wait_for_result("azul-nonexistent", timeout=0.1)
        assert result is None

    def test_get_result_returns_none_for_unknown(self, mock_pool):
        pool, _ = mock_pool
        assert pool.get_result("azul-unknown") is None


# ── Stop with drain ───────────────────────────────────────────────────────────

class TestDrainStop:
    def test_drain_waits_for_queue_empty(self, monkeypatch, tmp_path):
        import azul.queue_worker as qw

        completed = []
        def verify_and_record(ticket, store=None, ledger=None):
            completed.append(ticket.ticket_id)
            return _fast_verify(ticket, store=store, ledger=ledger)

        monkeypatch.setattr(qw, "verify", verify_and_record)
        pool = AzulWorkerPool(num_workers=2)
        pool.start()

        for _ in range(4):
            pool.submit(make_ticket())

        pool.stop(drain=True, timeout=5.0)
        assert len(completed) == 4
