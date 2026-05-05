import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List


def _load_json(path: Path) -> Dict:
    with path.open("r") as fh:
        return json.load(fh)


def _compute_digest(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _read_events(project_root: Path) -> List[Dict]:
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


def ensure_artifacts(artifact_index: Dict[str, Dict], artifact_ids: List[str]) -> None:
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


def ensure_digests(artifact_index: Dict[str, Dict], artifact_ids: List[str]) -> None:
    missing = [art for art in artifact_ids if not artifact_index.get(art, {}).get("digest")]
    if missing:
        raise RuntimeError(f"Artifacts missing digest entries: {missing}")


def ensure_ledger_events(events: List[Dict], project_id: str, pipeline_id: str, links: List[str]) -> None:
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


def rerun_pipeline(orchestrator, project_id: str, pipeline_path: str):
    return orchestrator.run_pipeline(project_id, pipeline_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ForgeScaffold Phase 1 blueprint")
    parser.add_argument("--project", "-p", default="app_mvp", help="DAWN project ID to target")
    parser.add_argument("--dawn-root", default="/Users/vinsoncornejo/DAWN", help="Path to the DAWN runtime clone")
    args = parser.parse_args()

    extension_root = Path(__file__).resolve().parents[1]
    dawn_root = Path(args.dawn_root).resolve()
    sys.path.insert(0, str(dawn_root))

    from dawn.runtime.orchestrator import Orchestrator

    links_dirs = [str(dawn_root / "dawn" / "links"), str(extension_root / "dawn_extensions" / "links")]
    orchestrator = Orchestrator(links_dirs, str(dawn_root / "projects"))
    pipeline_path = extension_root / "dawn_extensions" / "pipelines" / "forgescaffold_blueprint.yaml"

    project_root = dawn_root / "projects" / args.project
    if not project_root.exists():
        raise RuntimeError(f"Project {args.project} not found under {dawn_root / 'projects'}")

    print(f"Running ForgeScaffold pipeline for project={args.project}")
    orchestrator.run_pipeline(args.project, str(pipeline_path))

    artifact_index_path = project_root / "artifact_index.json"
    artifact_index = _load_json(artifact_index_path)

    expected_artifacts = [
        "forgescaffold.system_catalog.json",
        "forgescaffold.dataflow_map.json",
        "forgescaffold.test_matrix.yaml",
    ]
    ensure_artifacts(artifact_index, expected_artifacts)
    ensure_digests(artifact_index, expected_artifacts)

    events = _read_events(project_root)
    links_to_track = [
        "ingest.project_bundle",
        "forgescaffold.system_catalog",
        "forgescaffold.map_dataflow",
        "forgescaffold.test_matrix",
    ]
    ensure_ledger_events(events, args.project, "forgescaffold_blueprint", links_to_track)

    initial_digests = {
        art: artifact_index[art]["digest"] for art in expected_artifacts
    }

    print("Re-running pipeline to verify deterministic outputs")
    rerun_context = rerun_pipeline(orchestrator, args.project, str(pipeline_path))
    artifact_index = _load_json(artifact_index_path)
    rerun_digests = {art: artifact_index[art]["digest"] for art in expected_artifacts}

    if initial_digests != rerun_digests:
        raise RuntimeError("Artifact digests diverged after rerun, determinism broken")

    print("Verify complete: artifacts stable, ledger recorded, rerun deterministic")
    print("Rerun status summary:")
    for link, status in rerun_context.get("status_index", {}).items():
        print(f"  {link}: {status}")


if __name__ == "__main__":
    main()
