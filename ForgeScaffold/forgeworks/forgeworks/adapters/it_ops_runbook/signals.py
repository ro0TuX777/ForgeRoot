import json
from pathlib import Path
from typing import Dict, List


def _load_json(path: Path) -> Dict:
    return json.loads(path.read_text())


def extract_signals(raw_dir: str, ticket_ids: List[str]) -> List[Dict]:
    base = Path(raw_dir)
    metrics = _load_json(base / "metrics_snapshot.json")
    runbook_path = base / "runbook_service_down.md"
    if not runbook_path.exists():
        runbook_path = base / "runbook_service_health.md"
    runbook_present = runbook_path.exists() and bool(runbook_path.read_text().strip())

    service_context_path = base / "service_context.json"
    policy_path = base / "policy.json"
    metadata_path = base / "metadata.json"
    service_context = _load_json(service_context_path) if service_context_path.exists() else {}
    policy = _load_json(policy_path) if policy_path.exists() else {}
    metadata = _load_json(metadata_path) if metadata_path.exists() else {}

    queue_pressure = float(metrics.get("queue_pressure", 0.2))
    blast_radius = metrics.get("blast_radius", "low")
    service_tier = metrics.get("service_tier", "tier-2")

    signals: List[Dict] = []
    for ticket_id in ticket_ids:
        signals.append(
            {
                "schema_version": "0.1",
                "ticket_id": ticket_id,
                "values": {
                    "queue.pressure": queue_pressure,
                    "echo.fidelity": "D3",
                    "retry.count": int(metrics.get("retry_count", 0)),
                    "env": service_context.get("env", metrics.get("env", "prod")),
                    "blast_radius": blast_radius,
                    "service.tier": service_context.get("service_tier", service_tier),
                    "runbook.present": runbook_present,
                    "action.is_destructive": bool(policy.get("action_is_destructive", False)),
                    "metric.latency_ms": float(metrics.get("latency_ms", 0.0)),
                    "metric.error_rate": float(metrics.get("error_rate", 0.0)),
                    "queue.pressure_source": metadata.get("queue_pressure_source", "metrics_snapshot"),
                },
            }
        )
    return signals
