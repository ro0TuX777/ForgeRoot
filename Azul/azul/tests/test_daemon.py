"""
test_daemon.py — Azul daemon tests  (P2-2)
==========================================
Tests daemon lifecycle, reconciliation of stalled tickets,
socket listener (framing + dispatch), and health check.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import json
import socket
import threading
import time
import pytest
from pathlib import Path

from azul.ticket import create_ticket, TicketStatus
from azul.ticket_store import AzulTicketStore
from azul.xp_ledger import XPLedger
from azul.daemon import AzulDaemon


# ── Shared mock verify ────────────────────────────────────────────────────────

def _fast_verify(ticket, store=None, ledger=None):
    from azul.lifecycle import begin_provisioning, begin_evaluation, begin_gating, complete
    begin_provisioning(ticket)
    begin_evaluation(ticket)
    begin_gating(ticket)
    complete(ticket, xp=5)
    if store:
        store.save(ticket)
    return {
        "status": "ok", "verdict": "pass", "severity": "ok",
        "ticket_id": ticket.ticket_id,
        "ticket_status": TicketStatus.COMPLETED.value,
        "alerts": [], "xp_awarded": 5,
    }


@pytest.fixture
def tmp_store(tmp_path):
    return AzulTicketStore(
        active_dir=tmp_path / "active",
        completed_dir=tmp_path / "completed",
    )


@pytest.fixture
def tmp_ledger(tmp_path):
    return XPLedger(path=tmp_path / "xp.jsonl")


@pytest.fixture
def daemon(monkeypatch, tmp_path, tmp_store, tmp_ledger):
    """Fully mocked daemon with a short /tmp/ socket path and monkeypatched verify()."""
    import azul.queue_worker as qw
    import azul.adapters.api as api_mod

    monkeypatch.setattr(qw,      "verify", _fast_verify)
    monkeypatch.setattr(api_mod, "verify", _fast_verify)

    # Use /tmp/ directly — pytest tmp_path is too long for Unix sockets on macOS (104 char limit)
    sock_path = f"/tmp/azul_test_{os.getpid()}.sock"
    try:
        Path(sock_path).unlink(missing_ok=True)
    except Exception:
        pass

    d = AzulDaemon(
        num_workers        = 2,
        reconcile_interval = 60.0,   # very long — we call _run_reconciliation() directly
        stall_timeout      = 1,      # 1 second stall for tests
        socket_path        = sock_path,
        store              = tmp_store,
        ledger             = tmp_ledger,
    )
    d.start()
    yield d
    d.shutdown(drain=False)


def send_socket_request(sock_path: str, request: dict) -> dict:
    """Send a framed JSON request to the daemon socket and return the response."""
    data = json.dumps(request).encode()
    header = len(data).to_bytes(4, "big")

    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(5.0)
    conn.connect(sock_path)
    conn.sendall(header + data)

    resp_header = conn.recv(4)
    resp_len = int.from_bytes(resp_header, "big")
    resp_data = b""
    while len(resp_data) < resp_len:
        chunk = conn.recv(resp_len - len(resp_data))
        if not chunk:
            break
        resp_data += chunk
    conn.close()
    return json.loads(resp_data)


# ── Daemon lifecycle ──────────────────────────────────────────────────────────

class TestDaemonLifecycle:
    def test_start_sets_running(self, daemon):
        assert daemon._running is True

    def test_shutdown_clears_running(self, daemon):
        daemon.shutdown(drain=False)
        assert daemon._running is False

    def test_double_shutdown_is_safe(self, daemon):
        daemon.shutdown(drain=False)
        daemon.shutdown(drain=False)  # must not raise

    def test_health_returns_healthy(self, daemon):
        h = daemon.health()
        assert h["healthy"] is True
        assert h["uptime_seconds"] >= 0
        assert "pool" in h


# ── Reconciliation ────────────────────────────────────────────────────────────

class TestReconciliation:
    def test_stalled_submitted_ticket_requeued(self, daemon, tmp_store, monkeypatch):
        """A SUBMITTED ticket older than stall_timeout is requeued."""
        import datetime
        from azul.ticket import create_ticket

        t = create_ticket(
            ticket_type="ci_gate",
            domain="ci_change_control",
            change_summary="Stalled ticket",
        )
        # Backdate updated_at so it's 'stalled'
        t.updated_at = (datetime.datetime.now(datetime.timezone.utc)
                        - datetime.timedelta(seconds=10)).isoformat()
        tmp_store.save(t)

        # Pool receives the ticket during reconciliation
        requeued_ids = []
        real_submit = daemon._pool.submit
        def capturing_submit(ticket, **kwargs):
            requeued_ids.append(ticket.ticket_id)
            # Don't actually queue it in this test
        monkeypatch.setattr(daemon._pool, "submit", capturing_submit)

        daemon._run_reconciliation()
        assert t.ticket_id in requeued_ids

    def test_stalled_in_flight_ticket_marked_failed(self, daemon, tmp_store):
        """A ticket stuck in PROVISIONING beyond stall_timeout → FAILED."""
        import datetime
        from azul.ticket import create_ticket
        from azul.lifecycle import begin_provisioning

        t = create_ticket(
            ticket_type="ci_gate",
            domain="ci_change_control",
            change_summary="In-flight stall",
        )
        begin_provisioning(t)
        t.updated_at = (datetime.datetime.now(datetime.timezone.utc)
                        - datetime.timedelta(seconds=10)).isoformat()
        tmp_store.save(t)

        daemon._run_reconciliation()

        reloaded = tmp_store.get(t.ticket_id)
        assert reloaded.status == TicketStatus.FAILED

    def test_fresh_ticket_not_reconciled(self, daemon, tmp_store):
        """A fresh ticket (recent updated_at) is left alone."""
        t = create_ticket(
            ticket_type="ci_gate",
            domain="ci_change_control",
            change_summary="Fresh ticket",
        )
        tmp_store.save(t)

        daemon._run_reconciliation()

        reloaded = tmp_store.get(t.ticket_id)
        assert reloaded.status == TicketStatus.SUBMITTED  # untouched

    def test_terminal_ticket_not_reconciled(self, daemon, tmp_store):
        """A COMPLETED ticket should never be touched by reconciliation."""
        import datetime
        from azul.lifecycle import begin_provisioning, begin_evaluation, begin_gating, complete

        t = create_ticket(
            ticket_type="ci_gate",
            domain="ci_change_control",
            change_summary="Terminal ticket",
        )
        begin_provisioning(t); begin_evaluation(t); begin_gating(t)
        complete(t, xp=5)
        t.updated_at = (datetime.datetime.now(datetime.timezone.utc)
                        - datetime.timedelta(seconds=10)).isoformat()
        tmp_store.save(t)  # saves to completed/

        daemon._run_reconciliation()

        # Should still be COMPLETED
        reloaded = tmp_store.get(t.ticket_id)
        assert reloaded.status == TicketStatus.COMPLETED


# ── Socket listener ───────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"),
    reason="Unix domain sockets are not available on this platform",
)
class TestSocketListener:
    def _wait_for_socket(self, path, timeout=3.0):
        """Poll until a connect() to the socket succeeds — not just file existence."""
        import socket as sock_mod
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if Path(path).exists():
                try:
                    c = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
                    c.settimeout(0.2)
                    c.connect(path)
                    c.close()
                    return True
                except (ConnectionRefusedError, OSError):
                    pass
            time.sleep(0.05)
        return False

    def test_socket_file_created(self, daemon):
        assert self._wait_for_socket(daemon._socket_path)

    def test_health_action_via_socket(self, daemon):
        assert self._wait_for_socket(daemon._socket_path)
        resp = send_socket_request(daemon._socket_path, {"action": "health", "payload": {}})
        assert resp["status"] == "ok"
        assert resp["data"]["healthy"] is True

    def test_submit_and_get_via_socket(self, daemon):
        assert self._wait_for_socket(daemon._socket_path)

        resp = send_socket_request(daemon._socket_path, {
            "action": "submit",
            "payload": {
                "ticket_type":    "ci_gate",
                "domain":         "ci_change_control",
                "change_summary": "Socket test",
            },
        })
        assert resp["status"] == "ok"
        assert resp["data"]["verdict"] == "pass"
        tid = resp["data"]["ticket_id"]

        # Retrieve it
        get_resp = send_socket_request(daemon._socket_path, {
            "action":  "get_ticket",
            "payload": {"ticket_id": tid},
        })
        assert get_resp["status"] == "ok"
        assert get_resp["data"]["ticket_id"] == tid

    def test_unknown_action_via_socket(self, daemon):
        assert self._wait_for_socket(daemon._socket_path)
        resp = send_socket_request(daemon._socket_path, {"action": "explode", "payload": {}})
        assert resp["status"] == "error"

    def test_socket_cleaned_up_on_shutdown(self, daemon):
        sock_path = daemon._socket_path
        assert self._wait_for_socket(sock_path)
        daemon.shutdown(drain=False)
        time.sleep(0.2)
        assert not Path(sock_path).exists()
