"""
queue_worker.py — Async ticket queue and worker pool  (P2-1)
=============================================================
Implements a thread-safe FIFO queue and a configurable worker pool that
processes AzulTickets asynchronously by calling verify().

Design decisions mirroring ForgeHarbor's pool pattern:
  - Workers are daemon threads — they die when the main process exits.
  - Backpressure: submit() blocks (or raises QueueFullError) when the queue
    is at capacity.  Callers decide whether to block or reject.
  - Each worker logs its own ticket outcomes.
  - The pool is started/stopped explicitly; it is safe to call stop() twice.
  - Completed results are retrievable via a result_callback or polled from
    the completed_results dict (keyed by ticket_id).

Usage:
    pool = AzulWorkerPool(num_workers=3)
    pool.start()
    pool.submit(ticket)               # non-blocking (raises if full)
    pool.submit(ticket, block=True)   # blocks until queue has room
    pool.stop(drain=True)             # wait for in-flight work to finish
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, Optional

from .ticket import AzulTicket, TicketStatus
from .ticket_store import AzulTicketStore
from .xp_ledger import XPLedger
from .verification_engine import verify
from .config import AZUL_QUEUE_WORKERS

logger = logging.getLogger(__name__)

# Sentinel — placed on the queue to signal a worker thread to exit cleanly
_SHUTDOWN = object()


class QueueFullError(Exception):
    """Raised when submit() is called on a full queue (non-blocking)."""


class AzulWorkerPool:
    """
    Thread pool that consumes AzulTickets from an internal queue and calls
    verify() on each one.

    Args:
        num_workers:      Number of worker threads (default: AZUL_QUEUE_WORKERS env var).
        max_queue_depth:  Maximum pending tickets before submit() raises/blocks.
        store:            Ticket store injected into verify().
        ledger:           XP ledger injected into verify().
        result_callback:  Optional callable(ticket_id, result_dict) called after
                          each verify() completes.
    """

    def __init__(
        self,
        num_workers:     int                                    = AZUL_QUEUE_WORKERS,
        max_queue_depth: int                                    = 100,
        store:           Optional[AzulTicketStore]              = None,
        ledger:          Optional[XPLedger]                     = None,
        result_callback: Optional[Callable[[str, Dict], None]]  = None,
    ) -> None:
        self._num_workers     = num_workers
        self._queue:          queue.Queue = queue.Queue(maxsize=max_queue_depth)
        self._store           = store
        self._ledger          = ledger
        self._result_callback = result_callback

        self._workers:        list[threading.Thread] = []
        self._running:        bool                   = False
        self._stop_event:     threading.Event        = threading.Event()
        self._lock:           threading.Lock         = threading.Lock()

        # Thread-safe dict of completed results: ticket_id → result_dict
        self._results:        Dict[str, Dict[str, Any]]  = {}
        self._results_lock:   threading.Lock             = threading.Lock()

        # Counters
        self._submitted:   int = 0
        self._completed:   int = 0
        self._failed:      int = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the worker pool. Safe to call only once."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()

            for i in range(self._num_workers):
                t = threading.Thread(
                    target=self._worker_loop,
                    name=f"azul-worker-{i}",
                    daemon=True,
                )
                t.start()
                self._workers.append(t)

            logger.info(f"[AzulWorkerPool] Started {self._num_workers} workers")

    def stop(self, drain: bool = True, timeout: float = 30.0) -> None:
        """
        Stop the worker pool.

        Args:
            drain:   If True, wait for the queue to empty before shutting down.
            timeout: Max seconds to wait when draining.
        """
        with self._lock:
            if not self._running:
                return
            self._running = False

        if drain:
            deadline = time.monotonic() + timeout
            while not self._queue.empty() and time.monotonic() < deadline:
                time.sleep(0.05)

        # Send one _SHUTDOWN sentinel per worker
        for _ in self._workers:
            try:
                self._queue.put(_SHUTDOWN, block=False)
            except queue.Full:
                pass

        self._stop_event.set()

        for t in self._workers:
            t.join(timeout=5.0)

        self._workers.clear()
        logger.info("[AzulWorkerPool] Stopped")

    # ── Submission ────────────────────────────────────────────────────────────

    def submit(self, ticket: AzulTicket, block: bool = False, timeout: float = 5.0) -> None:
        """
        Enqueue a ticket for async verification.

        Args:
            ticket:  AzulTicket in SUBMITTED status.
            block:   If True, block until queue has room (up to timeout seconds).
            timeout: Seconds to wait when block=True.

        Raises:
            QueueFullError: If queue is full and block=False.
            RuntimeError:   If pool is not running.
        """
        if not self._running:
            raise RuntimeError("AzulWorkerPool is not running. Call start() first.")

        try:
            self._queue.put(ticket, block=block, timeout=timeout if block else None)
            with self._lock:
                self._submitted += 1
            logger.debug(f"[pool] Enqueued ticket {ticket.ticket_id} (depth={self.queue_depth})")
        except queue.Full:
            raise QueueFullError(
                f"Queue is full (depth={self._queue.maxsize}). "
                "Use block=True or wait for workers to catch up."
            )

    # ── Worker loop ───────────────────────────────────────────────────────────

    def _worker_loop(self) -> None:
        """Main loop for each worker thread."""
        thread_name = threading.current_thread().name
        logger.debug(f"[{thread_name}] Worker started")

        while True:
            try:
                item = self._queue.get(block=True, timeout=1.0)
            except queue.Empty:
                # Check if we should shut down
                if not self._running and self._stop_event.is_set():
                    break
                continue

            # Shutdown sentinel
            if item is _SHUTDOWN:
                self._queue.task_done()
                break

            ticket: AzulTicket = item
            try:
                logger.info(f"[{thread_name}] Processing ticket {ticket.ticket_id}")
                result = verify(ticket, store=self._store, ledger=self._ledger)

                with self._results_lock:
                    self._results[ticket.ticket_id] = result

                with self._lock:
                    if result.get("status") == "ok":
                        self._completed += 1
                    else:
                        self._failed += 1

                if self._result_callback:
                    try:
                        self._result_callback(ticket.ticket_id, result)
                    except Exception as cb_exc:
                        logger.warning(f"[{thread_name}] result_callback error: {cb_exc}")

                logger.info(
                    f"[{thread_name}] Ticket {ticket.ticket_id} → "
                    f"verdict={result.get('verdict')} status={result.get('ticket_status')}"
                )

            except Exception as exc:
                logger.exception(f"[{thread_name}] Unhandled worker error: {exc}")
                with self._lock:
                    self._failed += 1
            finally:
                self._queue.task_done()

        logger.debug(f"[{thread_name}] Worker exiting")

    # ── Result access ─────────────────────────────────────────────────────────

    def get_result(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Return the verify() result for a completed ticket, or None if pending."""
        with self._results_lock:
            return self._results.get(ticket_id)

    def wait_for_result(self, ticket_id: str, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """
        Poll until the result for ticket_id is available or timeout elapses.
        Returns None on timeout.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.get_result(ticket_id)
            if result is not None:
                return result
            time.sleep(0.05)
        return None

    # ── Status ────────────────────────────────────────────────────────────────

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        return self._running

    def stats(self) -> Dict[str, Any]:
        """Return pool statistics."""
        with self._lock:
            return {
                "running":     self._running,
                "num_workers": self._num_workers,
                "queue_depth": self.queue_depth,
                "submitted":   self._submitted,
                "completed":   self._completed,
                "failed":      self._failed,
                "in_flight":   self._submitted - self._completed - self._failed,
            }
