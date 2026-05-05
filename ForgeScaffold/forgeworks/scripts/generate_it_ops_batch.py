#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2))


def _write_text(path: Path, content: str) -> None:
    path.write_text(content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an IT ops runbook batch template")
    parser.add_argument("--out", required=True, help="Output folder, e.g. ingest/it_ops_runbook/batch_001")
    parser.add_argument("--env", default="prod", help="Environment label")
    parser.add_argument("--service-tier", default="tier1", dest="service_tier")
    parser.add_argument("--queue-pressure", type=float, default=0.3, dest="queue_pressure")
    parser.add_argument("--echo-fidelity", default="D4", dest="echo_fidelity")
    parser.add_argument("--retry-count", type=int, default=0, dest="retry_count")
    parser.add_argument("--incident", default="service_down", help="Incident type")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    runbook = "# Runbook: Service Down\n\n1) Check health endpoint\n2) Verify dependencies\n3) Roll back recent change if needed\n"
    _write_text(out_dir / "runbook_service_down.md", runbook)

    incident_log = (
        "[ALERT] service_down detected\n"
        "timestamp=2026-01-01T00:00:00Z\n"
        "symptom=5xx spike\n"
    )
    _write_text(out_dir / "incident_log_01.txt", incident_log)

    metrics = {
        "timestamp": "2026-01-01T00:00:00Z",
        "env": args.env,
        "queue.pressure": args.queue_pressure,
        "service.tier": args.service_tier,
        "error_rate": 0.15,
    }
    _write_json(out_dir / "metrics_snapshot.json", metrics)

    metadata = {
        "priority": "HIGH",
        "queue_pressure": args.queue_pressure,
        "echo_fidelity": args.echo_fidelity,
        "retry_count": args.retry_count,
        "mode_hint": "ramped",
        "incident": args.incident,
    }
    _write_json(out_dir / "metadata.json", metadata)

    print("Batch: OK")
    print(f"Output: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
