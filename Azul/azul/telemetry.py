"""
telemetry.py — CONCORD telemetry emitter  (P3-1)
==================================================
Emits Azul verification metrics to CONCORD's telemetry layer.

Metrics emitted per verification cycle:
    - tickets_processed          total count
    - pass_count / reject_count / warn_count / fail_count
    - average_verification_time_ms
    - pass_rate / reject_rate
    - xp_awarded_total
    - queue_depth (real-time)

When AZUL_TELEMETRY_ENABLED=false (default), metrics are written to a local
JSONL log file only (no network calls).

When AZUL_TELEMETRY_ENABLED=true, metrics are posted to the CONCORD telemetry
endpoint (AZUL_TELEMETRY_ENDPOINT) and also written to the local log.

The emitter is append-only: each verification cycle appends one record.
The `TelemetryReporter` aggregates records on demand for the health endpoint.

CONCORD metric convention (from CONCORD v0.4 brief):
    {
        "source":     "azul",
        "metric":     str,
        "value":      float | int,
        "labels":     dict,
        "timestamp":  ISO-8601
    }
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

AZUL_TELEMETRY_ENABLED: bool = (
    os.environ.get("AZUL_TELEMETRY_ENABLED", "false").lower() == "true"
)

AZUL_TELEMETRY_ENDPOINT: str = os.environ.get(
    "AZUL_TELEMETRY_ENDPOINT", ""
)

_DEFAULT_METRICS_PATH = Path(os.environ.get("AZUL_DATA_DIR", "azul_data")) / "metrics.jsonl"


# ── Metric builders ────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metric(name: str, value: float, labels: Optional[Dict] = None) -> Dict[str, Any]:
    return {
        "source":    "azul",
        "metric":    name,
        "value":     value,
        "labels":    labels or {},
        "timestamp": _ts(),
    }


# ── Main emitter class ────────────────────────────────────────────────────────

class TelemetryEmitter:
    """
    Appends per-verification telemetry records to a local JSONL file and
    optionally POSTs to a CONCORD telemetry endpoint.

    Thread-safe (one lock per emitter instance).
    """

    def __init__(
        self,
        metrics_path: Optional[Path] = None,
        enabled:      bool           = AZUL_TELEMETRY_ENABLED,
        endpoint:     str            = AZUL_TELEMETRY_ENDPOINT,
    ) -> None:
        self._path     = Path(metrics_path or _DEFAULT_METRICS_PATH)
        self._enabled  = enabled
        self._endpoint = endpoint

        import threading
        self._lock = threading.Lock()

        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record_verification(
        self,
        ticket_id:        str,
        verdict:          Optional[str],
        severity:         Optional[str],
        domain:           str,
        ticket_type:      str,
        xp_awarded:       int,
        duration_ms:      float,
        queue_depth:      int = 0,
    ) -> None:
        """
        Append one per-verification telemetry record.
        Called by the daemon after each verify() call.
        """
        record = {
            "ticket_id":   ticket_id,
            "verdict":     verdict,
            "severity":    severity,
            "domain":      domain,
            "ticket_type": ticket_type,
            "xp_awarded":  xp_awarded,
            "duration_ms": round(duration_ms, 1),
            "queue_depth": queue_depth,
            "timestamp":   _ts(),
        }

        with self._lock:
            try:
                with self._path.open("a") as fh:
                    fh.write(json.dumps(record) + "\n")
            except Exception as exc:
                logger.warning(f"[telemetry] Failed to write record: {exc}")

        if self._enabled and self._endpoint:
            self._post_to_concord(record)

    def _post_to_concord(self, record: Dict[str, Any]) -> None:
        """POST a metric record to the CONCORD telemetry endpoint."""
        try:
            import urllib.request
            payload = json.dumps({
                "source":    "azul",
                "record":    record,
                "timestamp": _ts(),
            }).encode()
            req = urllib.request.Request(
                self._endpoint,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status not in (200, 202, 204):
                    logger.warning(f"[telemetry] CONCORD endpoint returned {resp.status}")
        except Exception as exc:
            logger.warning(f"[telemetry] POST to CONCORD failed (non-fatal): {exc}")


# ── Reporter (aggregates local JSONL) ─────────────────────────────────────────

class TelemetryReporter:
    """
    Reads the local metrics.jsonl and returns aggregated summaries.
    Used by the health endpoint and the `get_xp_summary` daemon function.
    """

    def __init__(self, metrics_path: Optional[Path] = None) -> None:
        self._path = Path(metrics_path or _DEFAULT_METRICS_PATH)

    def load_records(self) -> List[Dict[str, Any]]:
        """Return all telemetry records."""
        if not self._path.exists():
            return []
        records = []
        with self._path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def summary(
        self,
        domain:      Optional[str] = None,
        ticket_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return aggregated metrics, optionally filtered.

        Returns:
            {
                "tickets_processed":          int,
                "pass_count":                 int,
                "reject_count":               int,
                "warn_count":                 int,
                "fail_count":                 int,
                "pass_rate":                  float,   # 0.0 to 1.0
                "reject_rate":                float,
                "average_verification_time_ms": float,
                "xp_awarded_total":           int,
                "by_domain":                  dict,
                "by_ticket_type":             dict,
            }
        """
        records = self.load_records()

        if domain:
            records = [r for r in records if r.get("domain") == domain]
        if ticket_type:
            records = [r for r in records if r.get("ticket_type") == ticket_type]

        total    = len(records)
        passes   = sum(1 for r in records if r.get("verdict") == "pass")
        rejects  = sum(1 for r in records if r.get("verdict") == "reject")
        warns    = sum(1 for r in records if r.get("severity") == "warn")
        fails    = sum(1 for r in records if r.get("verdict") not in ("pass", "reject"))
        xp_total = sum(r.get("xp_awarded", 0) for r in records)
        avg_ms   = (
            sum(r.get("duration_ms", 0) for r in records) / total
            if total > 0 else 0.0
        )

        by_domain: Dict[str, int] = defaultdict(int)
        by_type:   Dict[str, int] = defaultdict(int)
        for r in records:
            by_domain[r.get("domain", "unknown")] += 1
            by_type[r.get("ticket_type", "unknown")] += 1

        return {
            "tickets_processed":             total,
            "pass_count":                    passes,
            "reject_count":                  rejects,
            "warn_count":                    warns,
            "fail_count":                    fails,
            "pass_rate":                     round(passes / total, 3) if total else 0.0,
            "reject_rate":                   round(rejects / total, 3) if total else 0.0,
            "average_verification_time_ms":  round(avg_ms, 1),
            "xp_awarded_total":              xp_total,
            "by_domain":                     dict(by_domain),
            "by_ticket_type":                dict(by_type),
        }
