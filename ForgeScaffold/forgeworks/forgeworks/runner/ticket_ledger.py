"""
ForgeWorks Ticket Ledger
=========================
SQLite-backed ledger that tracks every ticket run AND enforces the
"one ticket at a time" constraint via an atomic SQLite claim lock.

Ported from SAM's AutonomousActionLedger (s11 Poll-Claim-Work-Repeat pattern).
All SAM-specific fields (XP, weights) are retained as they're useful for
future ForgeWorks scoring. Zero external dependencies — stdlib only.

## Claim Lock Design

The UNIQUE constraint on ``ticket_claims.ticket_id`` is the coordinator-free
lock. Only one INSERT per ticket_id can ever succeed:

    +----------+            +----------+
    | Runner A |--INSERT--> | SQLite   | → OK   → gets claim_id
    | Runner B |--INSERT--> | UNIQUE!  | → IntegrityError → returns None
    +----------+            +----------+

Crash recovery: claims have a TTL (default 30 min). ``reap_expired_claims()``
is called at the top of each run to free stale locks from crashed processes.

## Usage in sam_like_runner.py

    from forgeworks.runner.ticket_ledger import get_ticket_ledger

    ledger = get_ticket_ledger()
    ledger.reap_expired_claims()             # clean stale locks each run

    for ticket in ordered:
        ticket_id = ticket["ticket_id"]
        claim_id = ledger.try_claim(ticket_id, agent_id="forgeworks.runner")
        if claim_id is None:
            continue                         # another worker owns this ticket

        run_id = ledger.start_run(ticket_id)
        try:
            # ... run all 5 phases with RelayBaton ...
            ledger.complete_run(run_id)
        except Exception as e:
            ledger.fail_run(run_id, error=e)
        finally:
            ledger.release_claim(claim_id)   # frees UNIQUE slot immediately
"""

import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path("data") / "ledger" / "ticket_ledger.db"


class TicketLedger:
    """
    Persistent record of every ForgeWorks ticket run, with an atomic
    claim table that enforces one-ticket-at-a-time execution.

    Schema — ticket_runs:
        run_id        TEXT UNIQUE  — UUID, correlation ID for all log lines
        ticket_id     TEXT         — e.g. CI-001
        started_at    TEXT         — ISO timestamp
        completed_at  TEXT
        duration_sec  REAL
        outcome       TEXT         — SUCCESS | FAILURE | SKIPPED | IN_PROGRESS
        error_type    TEXT         — exception class name if FAILURE
        error_message TEXT         — first 500 chars of the exception
        metadata      TEXT         — JSON blob (phases visited, baton path, etc.)

    Schema — ticket_claims:
        claim_id   TEXT PRIMARY KEY
        ticket_id  TEXT NOT NULL UNIQUE   ← coordinator-free lock
        agent_id   TEXT NOT NULL
        claimed_at TEXT NOT NULL
        expires_at TEXT NOT NULL
        status     TEXT NOT NULL DEFAULT 'active'
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"📒 TicketLedger initialized at {self.db_path}")

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_runs (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id        TEXT    NOT NULL UNIQUE,
                    ticket_id     TEXT    NOT NULL,
                    started_at    TEXT    NOT NULL,
                    completed_at  TEXT,
                    duration_sec  REAL,
                    outcome       TEXT    DEFAULT 'IN_PROGRESS',
                    error_type    TEXT,
                    error_message TEXT,
                    metadata      TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tr_ticket  ON ticket_runs(ticket_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tr_outcome ON ticket_runs(outcome)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tr_run_id  ON ticket_runs(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tr_started ON ticket_runs(started_at)")

            # Claim table — UNIQUE(ticket_id) is the atomic coordinator lock.
            # Only one INSERT per ticket_id can succeed at a time.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_claims (
                    claim_id   TEXT PRIMARY KEY,
                    ticket_id  TEXT NOT NULL UNIQUE,
                    agent_id   TEXT NOT NULL,
                    claimed_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    status     TEXT NOT NULL DEFAULT 'active'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tc_ticket ON ticket_claims(ticket_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tc_status ON ticket_claims(status)")

            # Approval gate table — blocks supervised-mode ticket runs until a human
            # (or API caller) resolves the gate. Inspired by OpenFang's oneshot channel
            # ApprovalManager, implemented here via SQLite polling.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS approval_gates (
                    gate_id      TEXT PRIMARY KEY,
                    run_id       TEXT NOT NULL,
                    ticket_id    TEXT NOT NULL,
                    phase_name   TEXT NOT NULL,
                    action_id    TEXT NOT NULL,
                    risk_tier    TEXT NOT NULL DEFAULT 'med',
                    status       TEXT NOT NULL DEFAULT 'pending',
                    requested_at TEXT NOT NULL,
                    resolved_at  TEXT,
                    resolved_by  TEXT,
                    decision     TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ag_run    ON approval_gates(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ag_status ON approval_gates(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ag_ticket ON approval_gates(ticket_id)")
            conn.commit()

    # ------------------------------------------------------------------
    # Run Tracking API
    # ------------------------------------------------------------------

    def start_run(self, ticket_id: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Open a new run record. Returns the run_id (UUID) — thread it through
        all log calls for this ticket run.
        """
        run_id = str(uuid.uuid4())
        started_at = datetime.utcnow().isoformat()
        meta_json = json.dumps(metadata or {})
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO ticket_runs (run_id, ticket_id, started_at, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, ticket_id, started_at, meta_json),
            )
            conn.commit()
        logger.debug(f"📒 Ledger: run started  ticket={ticket_id!r} run_id={run_id}")
        return run_id

    def complete_run(self, run_id: str, metadata_update: Optional[Dict[str, Any]] = None) -> None:
        """Mark a run as SUCCESS."""
        self._close_run(run_id, outcome="SUCCESS", metadata_update=metadata_update)

    def fail_run(
        self,
        run_id: str,
        error: Exception,
        metadata_update: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark a run as FAILURE and record error classification."""
        self._close_run(run_id, outcome="FAILURE", error=error, metadata_update=metadata_update)

    def skip_run(self, run_id: str, reason: str = "") -> None:
        """Mark a run as SKIPPED (e.g. preconditions not met)."""
        self._close_run(run_id, outcome="SKIPPED", metadata_update={"skip_reason": reason})

    def _close_run(
        self,
        run_id: str,
        outcome: str,
        error: Optional[Exception] = None,
        metadata_update: Optional[Dict[str, Any]] = None,
    ) -> None:
        completed_at = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT started_at, metadata FROM ticket_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if not row:
                logger.warning(f"📒 Ledger: unknown run_id={run_id}")
                return
            started_dt = datetime.fromisoformat(row[0])
            existing_meta = json.loads(row[1] or "{}")

        duration_sec = (datetime.utcnow() - started_dt).total_seconds()
        if metadata_update:
            existing_meta.update(metadata_update)

        error_type = type(error).__name__ if error else None
        error_msg = str(error)[:500] if error else None

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE ticket_runs
                SET completed_at  = ?,
                    duration_sec  = ?,
                    outcome       = ?,
                    error_type    = ?,
                    error_message = ?,
                    metadata      = ?
                WHERE run_id = ?
                """,
                (
                    completed_at,
                    duration_sec,
                    outcome,
                    error_type,
                    error_msg,
                    json.dumps(existing_meta),
                    run_id,
                ),
            )
            conn.commit()
        logger.debug(
            f"📒 Ledger: run closed  run_id={run_id[:8]} outcome={outcome} err={error_type}"
        )

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single run by its correlation run_id."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM ticket_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_runs_for_ticket(self, ticket_id: str) -> List[Dict[str, Any]]:
        """Return all runs for a specific ticket, newest first."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT run_id, ticket_id, started_at, completed_at,
                       duration_sec, outcome, error_type, error_message
                FROM ticket_runs
                WHERE ticket_id = ?
                ORDER BY started_at DESC
                """,
                (ticket_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return the N most recent runs across all tickets."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT run_id, ticket_id, started_at, completed_at,
                       duration_sec, outcome, error_type, error_message
                FROM ticket_runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self, ticket_id: Optional[str] = None) -> Dict[str, Any]:
        """Return outcome stats — pass ticket_id to scope to one ticket, or None for all."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            where = "WHERE ticket_id = ?" if ticket_id else ""
            params = (ticket_id,) if ticket_id else ()
            row = conn.execute(
                f"""
                SELECT
                    COUNT(*)                                              AS total_runs,
                    SUM(CASE WHEN outcome='SUCCESS' THEN 1 ELSE 0 END)  AS success_count,
                    SUM(CASE WHEN outcome='FAILURE' THEN 1 ELSE 0 END)  AS failure_count,
                    SUM(CASE WHEN outcome='SKIPPED' THEN 1 ELSE 0 END)  AS skip_count,
                    AVG(CASE WHEN outcome NOT IN ('IN_PROGRESS','SKIPPED') THEN duration_sec END) AS avg_duration_sec
                FROM ticket_runs {where}
                """,
                params,
            ).fetchone()
        total = row["total_runs"] or 0
        success = row["success_count"] or 0
        return {
            "ticket_id": ticket_id or "ALL",
            "total_runs": total,
            "success_count": success,
            "failure_count": row["failure_count"] or 0,
            "skip_count": row["skip_count"] or 0,
            "success_rate": round(success / total, 3) if total else 0.0,
            "avg_duration_sec": round(row["avg_duration_sec"] or 0.0, 2),
        }

    # ------------------------------------------------------------------
    # Claim API — coordinator-free "one ticket at a time" lock
    # ------------------------------------------------------------------

    def try_claim(
        self,
        ticket_id: str,
        agent_id: str,
        ttl_sec: int = 1800,
    ) -> Optional[str]:
        """
        Atomically claim a ticket slot for this agent.

        Uses the UNIQUE constraint on ``ticket_claims.ticket_id`` as a
        coordinator-free lock. If another agent already holds an active
        claim for this ticket, the INSERT fails silently and ``None`` is
        returned — the caller should skip this ticket or wait.

        Args:
            ticket_id: The ticket to claim (e.g. ``"CI-001"``).
            agent_id:  Stable identifier for this runner process.
            ttl_sec:   Claim TTL in seconds. After this the claim can be
                       reaped by ``reap_expired_claims()``, recovering from
                       crashed processes automatically.

        Returns:
            UUID ``claim_id`` string on success, or ``None`` if already claimed.
        """
        claim_id = str(uuid.uuid4())
        claimed_at = datetime.utcnow()
        expires_at = (claimed_at + timedelta(seconds=ttl_sec)).isoformat()
        claimed_at_iso = claimed_at.isoformat()

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO ticket_claims
                        (claim_id, ticket_id, agent_id, claimed_at, expires_at, status)
                    VALUES (?, ?, ?, ?, ?, 'active')
                    """,
                    (claim_id, ticket_id, agent_id, claimed_at_iso, expires_at),
                )
                conn.commit()
            logger.debug(
                f"🔒 Claim ACQUIRED: ticket={ticket_id!r} agent={agent_id} "
                f"claim_id={claim_id[:8]} ttl={ttl_sec}s"
            )
            return claim_id
        except sqlite3.IntegrityError:
            # UNIQUE constraint violation — another agent holds this ticket slot
            logger.debug(
                f"🔒 Claim FAILED (already claimed): ticket={ticket_id!r} agent={agent_id}"
            )
            return None

    def release_claim(self, claim_id: str, status: str = "done") -> None:
        """
        Release a previously acquired claim by DELETING its row.

        Deleting (rather than updating to 'done') frees the UNIQUE(ticket_id)
        slot immediately so the next agent's INSERT can succeed without waiting.

        Args:
            claim_id: The UUID returned by :meth:`try_claim`.
            status:   Final status for logging — ``"done"`` or ``"failed"``.
        """
        if status not in ("done", "failed"):
            logger.warning(f"release_claim: unknown status {status!r}, using 'done'")
            status = "done"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM ticket_claims WHERE claim_id = ?",
                (claim_id,),
            )
            conn.commit()
        logger.debug(
            f"🔓 Claim RELEASED (deleted): claim_id={claim_id[:8]} status={status}"
        )

    def reap_expired_claims(self) -> int:
        """
        Delete all expired active claims, freeing their UNIQUE(ticket_id) slots.

        Call this at the top of every ``run_workcell()`` invocation so that
        stale claims from previous crashed runners are automatically recovered.

        Returns:
            Number of claims reaped (deleted).
        """
        now_iso = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                DELETE FROM ticket_claims
                WHERE  status = 'active'
                  AND  expires_at <= ?
                """,
                (now_iso,),
            )
            reaped = cursor.rowcount
            conn.commit()
        if reaped:
            logger.info(f"♻️  Reaped {reaped} expired ticket claim(s)")
        return reaped

    def is_ticket_claimed(self, ticket_id: str) -> bool:
        """Return True if this ticket currently has an active (non-expired) claim."""
        now_iso = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT 1 FROM ticket_claims
                WHERE  ticket_id = ?
                  AND  status    = 'active'
                  AND  expires_at > ?
                LIMIT 1
                """,
                (ticket_id, now_iso),
            ).fetchone()
        return row is not None

    def get_active_claims(self) -> List[Dict[str, Any]]:
        """Return all currently active (non-expired) claim rows. Useful for dashboards."""
        now_iso = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT claim_id, ticket_id, agent_id, claimed_at, expires_at
                FROM   ticket_claims
                WHERE  status = 'active'
                  AND  expires_at > ?
                ORDER BY claimed_at
                """,
                (now_iso,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Approval Gate API (supervised mode blocking gate)
    # ------------------------------------------------------------------
    # OpenFang uses Tokio oneshot channels to block an async task.
    # We use SQLite polling — semantically equivalent: the runner thread
    # loops with sleep until the gate is resolved via resolve_gate() which
    # can be called from a CLI, API, or dashboard.

    def request_gate(
        self,
        run_id: str,
        ticket_id: str,
        phase_name: str,
        action_id: str,
        risk_tier: str = "med",
    ) -> str:
        """
        Create a pending approval gate for a specific phase action.
        Returns the gate_id. The caller should then call wait_for_gate().
        """
        gate_id = str(uuid.uuid4())
        requested_at = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO approval_gates
                    (gate_id, run_id, ticket_id, phase_name, action_id, risk_tier,
                     status, requested_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (gate_id, run_id, ticket_id, phase_name, action_id, risk_tier, requested_at),
            )
            conn.commit()
        logger.info(
            f"🔐 Approval gate OPENED: ticket={ticket_id!r} phase={phase_name!r} "
            f"gate_id={gate_id[:8]} risk={risk_tier}"
        )
        return gate_id

    def wait_for_gate(
        self,
        gate_id: str,
        timeout_sec: int = 300,
        poll_interval_sec: float = 2.0,
    ) -> str:
        """
        Block (poll SQLite) until the gate is resolved or timeout expires.

        Returns the decision string: 'approved' | 'denied' | 'timed_out'.

        In supervised mode, this is called right before executing a
        high-risk phase action. The runner literally waits here while a
        human (or automation) calls resolve_gate() via the API or CLI.
        """
        deadline = datetime.utcnow().timestamp() + timeout_sec
        while datetime.utcnow().timestamp() < deadline:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT status, decision FROM approval_gates WHERE gate_id = ?",
                    (gate_id,),
                ).fetchone()
            if row and row["status"] != "pending":
                decision = row["decision"] or row["status"]
                logger.info(f"🔐 Gate resolved: gate_id={gate_id[:8]} decision={decision}")
                return decision
            import time as _time
            _time.sleep(poll_interval_sec)

        # Timeout — mark as timed_out and return
        self._expire_gate(gate_id)
        logger.warning(f"🔐 Gate TIMED OUT: gate_id={gate_id[:8]}")
        return "timed_out"

    def resolve_gate(
        self,
        gate_id: str,
        decision: str,
        resolved_by: str = "system",
    ) -> bool:
        """
        Resolve a pending gate. decision must be 'approved' or 'denied'.
        Returns True if the gate existed and was pending, False otherwise.
        """
        if decision not in ("approved", "denied"):
            raise ValueError(f"decision must be 'approved' or 'denied', got {decision!r}")
        resolved_at = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE approval_gates
                SET status = ?, decision = ?, resolved_at = ?, resolved_by = ?
                WHERE gate_id = ? AND status = 'pending'
                """,
                (decision, decision, resolved_at, resolved_by, gate_id),
            )
            conn.commit()
            updated = cursor.rowcount > 0
        if updated:
            logger.info(
                f"🔐 Gate RESOLVED: gate_id={gate_id[:8]} decision={decision} by={resolved_by}"
            )
        else:
            logger.warning(f"🔐 Gate not found or already resolved: gate_id={gate_id[:8]}")
        return updated

    def _expire_gate(self, gate_id: str) -> None:
        resolved_at = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE approval_gates
                SET status = 'timed_out', decision = 'timed_out', resolved_at = ?
                WHERE gate_id = ? AND status = 'pending'
                """,
                (resolved_at, gate_id),
            )
            conn.commit()

    def get_pending_gates(self) -> List[Dict[str, Any]]:
        """Return all pending approval gates. Used by CLI/dashboard to show what needs approval."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT gate_id, run_id, ticket_id, phase_name, action_id,
                       risk_tier, requested_at
                FROM   approval_gates
                WHERE  status = 'pending'
                ORDER BY requested_at
                """
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Ledger Eviction (Change 4)
    # ------------------------------------------------------------------

    def evict_old_runs(self, keep_days: int = 30) -> int:
        """
        Delete ticket_runs rows older than keep_days where outcome is terminal
        (SUCCESS, FAILURE, or SKIPPED). IN_PROGRESS rows are never evicted.

        Call this at the top of run_workcell() alongside reap_expired_claims()
        to prevent the ledger from growing unboundedly.

        Returns:
            Number of rows evicted.
        """
        cutoff = (datetime.utcnow() - timedelta(days=keep_days)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                DELETE FROM ticket_runs
                WHERE  started_at  <= ?
                  AND  outcome     IN ('SUCCESS', 'FAILURE', 'SKIPPED')
                """,
                (cutoff,),
            )
            evicted = cursor.rowcount
            conn.commit()
        if evicted:
            logger.info(f"🗑️  Evicted {evicted} old ticket run(s) older than {keep_days} days")
        return evicted

_ledger_instance: Optional[TicketLedger] = None


def get_ticket_ledger(db_path: Optional[str] = None) -> TicketLedger:
    """Get or create the global TicketLedger singleton."""
    global _ledger_instance
    if _ledger_instance is None:
        _ledger_instance = TicketLedger(db_path=db_path)
    return _ledger_instance
