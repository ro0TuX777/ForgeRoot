"""
daemon.py — Azul long-running daemon process  (P2-2)
======================================================
Manages the complete Azul runtime:

  • Worker pool (AzulWorkerPool) for async ticket processing
  • Reconciliation loop — requeues SUBMITTED tickets that were never picked up
    (handles crashes during PROVISIONING/EVALUATING that left stale non-terminal
    tickets by setting them to FAILED after the stall timeout)
  • Socket listener — exposes AzulAPIHandler over a Unix domain socket so the
    CLI and CI adapters can submit tickets without importing Azul directly
  • Signal handling — SIGTERM / SIGINT trigger graceful drain-and-stop

This mirrors ForgeHarbor's ForgeHarborDaemon structure:
    __init__ → start() → background threads → shutdown()

The daemon is designed for single-machine deployment in Phase 5.
Distributed queue (Redis/Celery) is a Phase 6+ concern.

Usage:
    daemon = AzulDaemon()
    daemon.start()          # spawns workers + reconciler + socket listener

    # --- or as __main__ ---
    python -m azul.daemon
"""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .queue_worker import AzulWorkerPool, QueueFullError
from .ticket_store import AzulTicketStore
from .xp_ledger import XPLedger
from .adapters.api import AzulAPIHandler
from .config import (
    AZUL_QUEUE_WORKERS,
    AZUL_DATA_DIR,
    ensure_data_dirs,
)

logger = logging.getLogger(__name__)

# ── Configuration defaults ────────────────────────────────────────────────────

_DEFAULT_SOCKET_PATH    = str(Path(AZUL_DATA_DIR) / "azul.sock")
_DEFAULT_RECONCILE_MS   = int(os.environ.get("AZUL_RECONCILE_INTERVAL_MS", "30000"))
_DEFAULT_STALL_TIMEOUT  = int(os.environ.get("AZUL_STALL_TIMEOUT_S", "300"))  # 5 min
_DEFAULT_MAX_QUEUE      = int(os.environ.get("AZUL_MAX_QUEUE_DEPTH", "200"))
_SOCKET_RECV_BYTES      = 65536


class AzulDaemon:
    """
    Main Azul daemon process.

    Args:
        num_workers:         Thread pool size (default: AZUL_QUEUE_WORKERS).
        reconcile_interval:  Seconds between stall-scan passes.
        stall_timeout:       Seconds before a non-terminal ticket is failed.
        socket_path:         Unix socket path for the API listener.
        store:               Optional injected ticket store (default: created).
        ledger:              Optional injected XP ledger (default: created).
    """

    def __init__(
        self,
        num_workers:        int  = AZUL_QUEUE_WORKERS,
        reconcile_interval: float = _DEFAULT_RECONCILE_MS / 1000,
        stall_timeout:      float = _DEFAULT_STALL_TIMEOUT,
        socket_path:        str  = _DEFAULT_SOCKET_PATH,
        store:              Optional[AzulTicketStore] = None,
        ledger:             Optional[XPLedger]        = None,
    ) -> None:
        ensure_data_dirs()

        self._store  = store  or AzulTicketStore()
        self._ledger = ledger or XPLedger()

        self._pool = AzulWorkerPool(
            num_workers     = num_workers,
            max_queue_depth = _DEFAULT_MAX_QUEUE,
            store           = self._store,
            ledger          = self._ledger,
        )

        self._api_handler = AzulAPIHandler(
            store  = self._store,
            ledger = self._ledger,
        )

        self._reconcile_interval = reconcile_interval
        self._stall_timeout      = stall_timeout
        self._socket_path        = socket_path

        self._running          = False
        self._stop_event       = threading.Event()
        self._reconcile_thread: Optional[threading.Thread] = None
        self._socket_thread:    Optional[threading.Thread] = None
        self._start_time:       float = 0.0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start all daemon subsystems."""
        if self._running:
            logger.warning("[AzulDaemon] already running")
            return

        self._running    = True
        self._start_time = time.monotonic()
        self._stop_event.clear()

        # Worker pool
        self._pool.start()

        # Reconciliation loop
        self._reconcile_thread = threading.Thread(
            target=self._reconcile_loop,
            name="azul-reconciler",
            daemon=True,
        )
        self._reconcile_thread.start()

        # Unix socket listener (non-fatal if socket creation fails)
        try:
            self._socket_thread = threading.Thread(
                target=self._socket_listener,
                name="azul-socket",
                daemon=True,
            )
            self._socket_thread.start()
        except Exception as exc:
            logger.warning(f"[AzulDaemon] Socket listener failed to start: {exc}")

        # OS signal handlers
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT,  self._signal_handler)
        except (OSError, ValueError):
            pass  # Not in main thread — skip signal registration

        pool_stats = self._pool.stats()
        logger.info(
            f"[AzulDaemon] Started — workers={pool_stats['num_workers']} "
            f"socket={self._socket_path}"
        )
        print(
            f"Azul daemon started: {pool_stats['num_workers']} workers, "
            f"socket={self._socket_path}"
        )

    def shutdown(self, drain: bool = True) -> None:
        """
        Graceful shutdown:
          1. Stop accepting new socket connections
          2. Drain the worker queue (or timeout at 30 s)
          3. Stop workers
          4. Clean up socket file
        """
        if not self._running:
            return

        print("[AzulDaemon] Shutting down...")
        self._running = False
        self._stop_event.set()

        # Drain and stop worker pool
        self._pool.stop(drain=drain, timeout=30.0)

        # Join background threads (they're daemons so they'll die anyway)
        for t in (self._reconcile_thread, self._socket_thread):
            if t and t.is_alive():
                t.join(timeout=3.0)

        # Remove socket file
        self._cleanup_socket()

        logger.info("[AzulDaemon] Shutdown complete")
        print("[AzulDaemon] Shutdown complete")

    def _signal_handler(self, signum, frame) -> None:
        logger.info(f"[AzulDaemon] Received signal {signum} — initiating shutdown")
        threading.Thread(target=self.shutdown, daemon=True).start()

    # ── Reconciliation loop ───────────────────────────────────────────────────

    def _reconcile_loop(self) -> None:
        """
        Periodically scan for stalled tickets and mark them FAILED.

        A ticket is considered stalled if it has been in a non-terminal,
        non-SUBMITTED state for longer than _stall_timeout seconds.
        SUBMITTED tickets that predate the stall window are requeued.
        """
        logger.debug("[azul-reconciler] Started")
        while not self._stop_event.wait(self._reconcile_interval):
            if not self._running:
                break
            try:
                self._run_reconciliation()
            except Exception as exc:
                logger.error(f"[azul-reconciler] Error during reconciliation: {exc}")

        logger.debug("[azul-reconciler] Exiting")

    def _run_reconciliation(self) -> None:
        """Execute one reconciliation pass."""
        from .ticket import TicketStatus, TERMINAL_STATUSES
        from .lifecycle import fail

        active_tickets = self._store.list_active()
        if not active_tickets:
            return

        now         = time.time()
        stalled     = []
        requeued    = 0

        for ticket in active_tickets:
            # Parse updated_at timestamp
            try:
                import datetime
                updated = datetime.datetime.fromisoformat(ticket.updated_at)
                age_s   = now - updated.timestamp()
            except Exception:
                continue

            if age_s < self._stall_timeout:
                continue  # Still in-progress

            if ticket.status == TicketStatus.SUBMITTED:
                # Requeue — never got picked up
                try:
                    self._pool.submit(ticket, block=False)
                    requeued += 1
                    logger.info(f"[reconciler] Requeued stalled SUBMITTED ticket {ticket.ticket_id}")
                except QueueFullError:
                    logger.warning(f"[reconciler] Queue full — cannot requeue {ticket.ticket_id}")
            else:
                # Non-terminal, non-SUBMITTED, stalled → FAILED
                stalled.append(ticket)

        for ticket in stalled:
            fail(ticket, reason=f"Stall timeout after {self._stall_timeout}s — daemon reconciliation")
            self._store.save(ticket)
            logger.warning(f"[reconciler] Marked stalled ticket {ticket.ticket_id} as FAILED "
                           f"(was {ticket.status.value})")

        if stalled or requeued:
            logger.info(f"[reconciler] Pass complete: {requeued} requeued, {len(stalled)} failed")

    # ── Unix socket listener ──────────────────────────────────────────────────

    def _cleanup_socket(self) -> None:
        try:
            Path(self._socket_path).unlink(missing_ok=True)
        except Exception:
            pass

    def _socket_listener(self) -> None:
        """
        Accept JSON-encoded request dicts over a Unix domain socket and
        dispatch them to AzulAPIHandler.

        Protocol:
            Client sends: <length:4 bytes big-endian><json payload>
            Server sends: <length:4 bytes big-endian><json response>
        """
        self._cleanup_socket()
        Path(self._socket_path).parent.mkdir(parents=True, exist_ok=True)

        try:
            server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind(self._socket_path)
            server_sock.listen(10)
            server_sock.settimeout(1.0)
        except Exception as exc:
            logger.error(f"[socket] Failed to bind {self._socket_path}: {exc}")
            return

        logger.info(f"[socket] Listening on {self._socket_path}")

        while self._running and not self._stop_event.is_set():
            try:
                conn, _ = server_sock.accept()
            except socket.timeout:
                continue
            except Exception as exc:
                if self._running:
                    logger.warning(f"[socket] accept() error: {exc}")
                break

            threading.Thread(
                target=self._handle_connection,
                args=(conn,),
                daemon=True,
            ).start()

        try:
            server_sock.close()
        except Exception:
            pass

        self._cleanup_socket()
        logger.info("[socket] Listener stopped")

    def _handle_connection(self, conn: socket.socket) -> None:
        """Read one request, dispatch to API handler, send response."""
        try:
            raw = self._recv_framed(conn)
            if not raw:
                return

            request = json.loads(raw)
            response = self._api_handler.handle(request)
            self._send_framed(conn, json.dumps(response).encode())

        except Exception as exc:
            logger.warning(f"[socket] Connection error: {exc}")
            try:
                error_resp = json.dumps({"status": "error", "error": str(exc)})
                self._send_framed(conn, error_resp.encode())
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @staticmethod
    def _recv_framed(conn: socket.socket) -> Optional[bytes]:
        """Read a length-prefixed message (4-byte big-endian header)."""
        header = conn.recv(4)
        if len(header) < 4:
            return None
        length = int.from_bytes(header, "big")
        if length == 0 or length > _SOCKET_RECV_BYTES:
            return None
        data = b""
        while len(data) < length:
            chunk = conn.recv(length - len(data))
            if not chunk:
                break
            data += chunk
        return data if len(data) == length else None

    @staticmethod
    def _send_framed(conn: socket.socket, data: bytes) -> None:
        """Send a length-prefixed message."""
        header = len(data).to_bytes(4, "big")
        conn.sendall(header + data)

    # ── Status ────────────────────────────────────────────────────────────────

    def health(self) -> Dict[str, Any]:
        """Return daemon health summary."""
        pool_stats = self._pool.stats()
        return {
            "healthy":        self._running,
            "uptime_seconds": round(time.monotonic() - self._start_time, 1),
            "pool":           pool_stats,
            "socket_path":    self._socket_path,
        }


# ── __main__ entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    daemon = AzulDaemon()
    daemon.start()

    try:
        while daemon._running:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        daemon.shutdown(drain=True)
