import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Any

import yaml

def _get_jsonschema_validate():
    try:
        from jsonschema import validate  # type: ignore
        return validate
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "jsonschema is required to validate ForgeScaffold artifacts. "
            "Install with: python3 -m pip install jsonschema"
        ) from exc


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r") as fh:
        return json.load(fh)


def _sha256_file(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _read_events(project_root: Path) -> List[Dict[str, Any]]:
    events_file = project_root / "ledger" / "events.jsonl"
    if not events_file.exists():
        raise RuntimeError("Ledger events are missing")
    events = []
    with events_file.open("r") as fh:
        for line in fh:
            if not line.strip():
                continue
            events.append(json.loads(line))
    return events


def ensure_artifacts(artifact_index: Dict[str, Dict[str, Any]], artifact_ids: List[str]) -> None:
    missing = [art for art in artifact_ids if art not in artifact_index]
    if missing:
        raise RuntimeError(f"Missing artifacts: {missing}")
    missing_files = []
    for art in artifact_ids:
        entry = artifact_index.get(art, {})
        path = Path(entry.get("path", ""))
        if not path.exists():
            missing_files.append(art)
    if missing_files:
        raise RuntimeError(f"Artifact files missing on disk: {missing_files}")


def ensure_ledger_events(events: List[Dict[str, Any]], project_id: str, pipeline_id: str, links: List[str]) -> None:
    grouped = {link: {"start": [], "complete": [], "failed": []} for link in links}
    for ev in events:
        if ev.get("project_id") != project_id or ev.get("pipeline_id") != pipeline_id:
            continue
        link_id = ev.get("link_id")
        if link_id not in grouped:
            continue
        step = ev.get("step_id")
        status = ev.get("status")
        if step == "link_start":
            grouped[link_id]["start"].append(ev)
        elif step == "link_complete":
            grouped[link_id]["complete"].append(ev)
            if status != "SUCCEEDED":
                grouped[link_id]["failed"].append(ev)
    for link, payload in grouped.items():
        if not payload["start"]:
            raise RuntimeError(f"Missing start event for {link}")
        if not payload["complete"]:
            raise RuntimeError(f"Missing completion event for {link}")
        if payload["failed"]:
            raise RuntimeError(f"Link {link} recorded failure: {payload['failed']}")


def _validate_schema(schema_path: Path, artifact_path: Path) -> None:
    validate = _get_jsonschema_validate()
    schema = _load_json(schema_path)
    if artifact_path.suffix.lower() in {".yaml", ".yml"}:
        payload = yaml.safe_load(artifact_path.read_text())
    else:
        payload = _load_json(artifact_path)
    validate(instance=payload, schema=schema)


def _validate_log_envelope_example(schema_path: Path) -> None:
    example = {
        "schema_version": "1.0.0",
        "timestamp": "1970-01-01T00:00:00Z",
        "severity": "INFO",
        "run_id": "example_run_1234",
        "unit_id": "module.example",
        "operation": "startup",
        "result": "ok",
        "duration_ms": 1,
        "message": "ok",
    }
    schema = _load_json(schema_path)
    validate = _get_jsonschema_validate()
    validate(instance=example, schema=schema)


def _enforce_patchset_determinism(patchset: Dict[str, Any]) -> None:
    generator = patchset.get("generator", {})
    if "run_id" in generator:
        raise RuntimeError("Patchset must not include generator.run_id (nondeterministic)")

    target = patchset.get("target", {})
    if "bundle_sha256" in target:
        raise RuntimeError("Patchset must not include target.bundle_sha256 (nondeterministic)")

    if "created_at" in patchset:
        ext = patchset.get("ext", {})
        if "generated_at" not in ext:
            raise RuntimeError("Patchset created_at is only allowed under ext.generated_at for determinism")


def _bootstrap_project(project_root: Path) -> None:
    (project_root / "inputs").mkdir(parents=True, exist_ok=True)
    (project_root / "src" / "app").mkdir(parents=True, exist_ok=True)
    (project_root / "inputs" / "idea.md").write_text("forge scaffold bootstrap")
    (project_root / "src" / "app" / "__init__.py").write_text("")
    (project_root / "src" / "app" / "main.py").write_text("print('hello')\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ForgeScaffold Phase 2 blueprint")
    parser.add_argument("--project", "-p", default="app_mvp", help="DAWN project ID to target")
    parser.add_argument("--bootstrap", action="store_true", help="Create a minimal project if missing")
    args = parser.parse_args()

    dawn_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(dawn_root))

    from dawn.runtime.orchestrator import Orchestrator

    links_dirs = [str(dawn_root / "dawn" / "links")]
    orchestrator = Orchestrator(links_dirs, str(dawn_root / "projects"))
    pipeline_path = dawn_root / "dawn" / "pipelines" / "forgescaffold_blueprint_v2.yaml"

    project_root = dawn_root / "projects" / args.project
    if not project_root.exists():
        if args.bootstrap:
            _bootstrap_project(project_root)
        else:
            raise RuntimeError(f"Project {args.project} not found under {dawn_root / 'projects'}")

    print(f"Running ForgeScaffold Phase 2 pipeline for project={args.project}")
    orchestrator.run_pipeline(args.project, str(pipeline_path))

    artifact_index_path = project_root / "artifact_index.json"
    artifact_index = _load_json(artifact_index_path)

    expected_artifacts = [
        "forgescaffold.system_catalog.json",
        "forgescaffold.dataflow_map.json",
        "forgescaffold.log_envelope.schema.json",
        "forgescaffold.observability_recommendations.md",
        "forgescaffold.instrumentation.patchset.json",
        "forgescaffold.test_matrix.yaml",
        "forgescaffold.test_harness.manifest.json",
    ]
    ensure_artifacts(artifact_index, expected_artifacts)

    schema_root = dawn_root / "dawn" / "schemas"
    _validate_schema(schema_root / "system_catalog.schema.json", Path(artifact_index["forgescaffold.system_catalog.json"]["path"]))
    _validate_schema(schema_root / "dataflow_map.schema.json", Path(artifact_index["forgescaffold.dataflow_map.json"]["path"]))
    _validate_schema(schema_root / "test_matrix.schema.json", Path(artifact_index["forgescaffold.test_matrix.yaml"]["path"]))
    _validate_schema(schema_root / "instrumentation.patchset.schema.json", Path(artifact_index["forgescaffold.instrumentation.patchset.json"]["path"]))

    log_schema_path = schema_root / "log_envelope.schema.json"
    _validate_log_envelope_example(log_schema_path)

    patchset_payload = _load_json(Path(artifact_index["forgescaffold.instrumentation.patchset.json"]["path"]))
    _enforce_patchset_determinism(patchset_payload)

    harness_manifest_path = Path(artifact_index["forgescaffold.test_harness.manifest.json"]["path"]).parent
    if not harness_manifest_path.exists():
        raise RuntimeError("Test harness folder is missing")

    expected_harness_files = [
        harness_manifest_path / "README.md",
        harness_manifest_path / "manifest.json",
    ]
    for file_path in expected_harness_files:
        if not file_path.exists():
            raise RuntimeError(f"Missing harness file: {file_path}")

    events = _read_events(project_root)
    links_to_track = [
        "ingest.project_bundle",
        "forgescaffold.system_catalog",
        "forgescaffold.map_dataflow",
        "forgescaffold.obs_define_schema",
        "forgescaffold.obs_instrument_patchset",
        "forgescaffold.test_matrix",
    ]
    ensure_ledger_events(events, args.project, "forgescaffold_blueprint_v2", links_to_track)

    def snapshot() -> Dict[str, str]:
        paths = [
            Path(artifact_index["forgescaffold.instrumentation.patchset.json"]["path"]),
            Path(artifact_index["forgescaffold.test_matrix.yaml"]["path"]),
            Path(artifact_index["forgescaffold.test_harness.manifest.json"]["path"]),
        ]
        return {str(p): _sha256_file(p) for p in paths}

    first = snapshot()

    print("Re-running Phase 2 pipeline to verify deterministic outputs")
    rerun_context = orchestrator.run_pipeline(args.project, str(pipeline_path))
    artifact_index = _load_json(artifact_index_path)
    second = snapshot()

    if first != second:
        raise RuntimeError("Phase 2 artifacts diverged after rerun, determinism broken")

    print("Phase 2 verify complete: artifacts stable, schemas valid, harness present")
    print("Rerun status summary:")
    for link, status in rerun_context.get("status_index", {}).items():
        print(f"  {link}: {status}")


if __name__ == "__main__":
    main()
