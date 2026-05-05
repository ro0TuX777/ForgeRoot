#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import List


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2))


def _write_text(path: Path, content: str) -> None:
    path.write_text(content)


def _build_test_names(count: int) -> List[str]:
    return [f"tests/test_case_{idx:03d}.py::test_case_{idx:03d}" for idx in range(1, count + 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a CI change-control batch template")
    parser.add_argument("--out", required=True, help="Output folder, e.g. ingest/ci_change_control/batch_002")
    parser.add_argument("--count", type=int, default=5, help="Number of failing tests to include")
    parser.add_argument("--priority", default="HIGH", help="Ticket priority")
    parser.add_argument("--queue-pressure", type=float, default=0.25, dest="queue_pressure")
    parser.add_argument("--echo-fidelity", default="D4", dest="echo_fidelity")
    parser.add_argument("--retry-count", type=int, default=0, dest="retry_count")
    parser.add_argument("--touches-ci-config", action="store_true", dest="touches_ci_config")
    parser.add_argument("--touches-core-paths", action="store_true", dest="touches_core_paths")
    parser.add_argument("--core-path", default="src/auth.py", dest="core_path")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    test_names = _build_test_names(args.count)

    log_lines = ["Run pytest -q"]
    for name in test_names:
        log_lines.append(f"FAILED {name} - AssertionError: expected success, got failure")
    log_lines.append(f"{args.count} failed, 0 passed")
    _write_text(out_dir / "ci_log_01.txt", "\n".join(log_lines) + "\n")

    failing = {
        "ticket_seed_id": "CI-BATCH-GEN",
        "failing_tests": test_names,
        "failure_class": "unit_test_failure",
        "severity": "medium",
    }
    _write_json(out_dir / "failing_tests.json", failing)

    candidate_files = [args.core_path] + [name.split("::")[0] for name in test_names]
    if args.touches_ci_config:
        candidate_files.append(".github/workflows/ci.yml")

    repo_manifest = {
        "repo": "sample-service",
        "commit": "unknown",
        "candidate_files": candidate_files,
        "forbidden_paths": [".github/workflows/", "sam/orchestration/"],
        "core_paths": [args.core_path],
        "touches_ci_config": bool(args.touches_ci_config),
        "touches_core_paths": bool(args.touches_core_paths),
    }
    _write_json(out_dir / "repo_snapshot_manifest.json", repo_manifest)

    policy = {
        "allowed_action_classes": ["code_patch", "test_fix"],
        "forbidden_actions": ["disable_tests", "edit_ci_workflows"],
        "max_files_changed": 3,
        "require_approval_if_core_path_touched": True,
    }
    _write_json(out_dir / "policy.json", policy)

    metadata = {
        "priority": args.priority,
        "queue_pressure": args.queue_pressure,
        "echo_fidelity": args.echo_fidelity,
        "retry_count": args.retry_count,
        "mode_hint": "supervised",
    }
    _write_json(out_dir / "metadata.json", metadata)

    print("Batch: OK")
    print(f"Output: {out_dir}")
    print(f"Tests: {args.count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
