import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

import yaml


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r") as fh:
        return json.load(fh)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(payload, fh, indent=2)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _make_apply_only_pipeline(project_root: Path) -> Path:
    pipeline_path = project_root / ".forgescaffold_apply_only.yaml"
    payload = {"pipelineId": "forgescaffold_apply_only", "links": [{"id": "forgescaffold.apply_patchset"}]}
    with pipeline_path.open("w") as fh:
        yaml.safe_dump(payload, fh)
    return pipeline_path


def _get_artifact_path(project_root: Path, artifact_id: str) -> Path:
    index_path = project_root / "artifact_index.json"
    if not index_path.exists():
        raise RuntimeError("artifact_index.json missing")
    index = _load_json(index_path)
    entry = index.get(artifact_id)
    if not entry:
        raise RuntimeError(f"Artifact {artifact_id} missing from index")
    return Path(entry["path"])


def _assert_apply_status(project_root: Path, expected: str) -> None:
    report_path = _get_artifact_path(project_root, "forgescaffold.apply_report.json")
    report = _load_json(report_path)
    status = report.get("status")
    if status != expected:
        raise RuntimeError(f"Expected apply status {expected}, got {status}")


def _validate_verification_report(report: Dict[str, Any]) -> None:
    status = report.get("status")
    mode = report.get("mode", "strict")
    results = report.get("results", [])

    failed = [r for r in results if r.get("status") == "FAIL"]
    skipped = [r for r in results if str(r.get("status", "")).startswith("SKIPPED_")]
    skipped_dep = [r for r in results if r.get("status") == "SKIPPED_DEP_MISSING"]

    if mode == "runnable_only":
        if status not in {"PASS", "WARN"}:
            raise RuntimeError(f"Expected verification status PASS/WARN in runnable_only, got {status}")
        if failed:
            raise RuntimeError("Runnable-only verification has failed commands")
        if status == "WARN" and not skipped_dep:
            raise RuntimeError("WARN requires at least one SKIPPED_DEP_MISSING result")
    else:
        if status != "PASS":
            raise RuntimeError(f"Expected verification status PASS in strict mode, got {status}")


def _bootstrap_project(project_root: Path) -> None:
    (project_root / "inputs").mkdir(parents=True, exist_ok=True)
    (project_root / "src" / "app").mkdir(parents=True, exist_ok=True)
    (project_root / "inputs" / "idea.md").write_text("forge scaffold phase3")
    (project_root / "src" / "app" / "__init__.py").write_text("")
    (project_root / "src" / "app" / "main.py").write_text("print('hello')\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ForgeScaffold Phase 3 apply/gates")
    parser.add_argument("--project", "-p", default="app_mvp")
    parser.add_argument("--profile", default="forgescaffold_apply_lowrisk")
    parser.add_argument("--bootstrap", action="store_true", help="Create a minimal project if missing")
    parser.add_argument(
        "--pipeline",
        default="dawn/pipelines/forgescaffold_apply_v1.yaml",
        help="Pipeline path to run before verification.",
    )
    parser.add_argument(
        "--mode",
        choices=["strict", "runnable_only", "auto"],
        default="auto",
        help="Expected verification mode (auto reads from report).",
    )
    args = parser.parse_args()

    dawn_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(dawn_root))

    from dawn.runtime.orchestrator import Orchestrator

    links_dirs = [str(dawn_root / "dawn" / "links")]
    orchestrator = Orchestrator(links_dirs, str(dawn_root / "projects"))

    project_root = dawn_root / "projects" / args.project
    if not project_root.exists():
        if args.bootstrap:
            _bootstrap_project(project_root)
        else:
            raise RuntimeError(f"Project {args.project} not found under {dawn_root / 'projects'}")

    # Ensure patchset exists
    phase2_pipeline = dawn_root / "dawn" / "pipelines" / "forgescaffold_blueprint_v2.yaml"
    orchestrator.run_pipeline(args.project, str(phase2_pipeline), profile=args.profile)

    apply_only_pipeline = _make_apply_only_pipeline(project_root)

    # Drift refusal test
    idea_path = project_root / "inputs" / "idea.md"
    original_idea = idea_path.read_text() if idea_path.exists() else ""
    _write_text(idea_path, original_idea + "\nDRIFT_TEST")
    orchestrator.run_pipeline(args.project, str(apply_only_pipeline), profile=args.profile)
    _assert_apply_status(project_root, "REFUSED_DRIFT")
    _write_text(idea_path, original_idea)

    # Forbidden path refusal test
    patchset_path = _get_artifact_path(project_root, "forgescaffold.instrumentation.patchset.json")
    original_patchset = _load_json(patchset_path)
    bundle_path = _get_artifact_path(project_root, "dawn.project.bundle")
    bundle = _load_json(bundle_path)
    forbidden_patchset = {
        "schema_version": "1.0.1",
        "patchset_id": "forbidden",
        "generator": {"name": "forgescaffold.obs_instrument_patchset", "version": "1.0.0"},
        "target": {
            "project_id": args.project,
            "bundle_content_sha256": bundle.get("bundle_content_sha256", "")
        },
        "operations": [
            {
                "op": "modify",
                "path": "dawn/runtime/orchestrator.py",
                "content": "# forbidden\n",
                "content_sha256": "5d04c4122bc4b90a8165746ea38ad5416c5d0e58cd2e0f43b1cba959f4a4602f",
                "tags": ["observability"],
            }
        ],
    }
    _write_json(patchset_path, forbidden_patchset)
    orchestrator.run_pipeline(args.project, str(apply_only_pipeline), profile=args.profile)
    _assert_apply_status(project_root, "REFUSED_SCOPE")
    _write_json(patchset_path, original_patchset)

    # Full apply pipeline
    apply_pipeline = Path(args.pipeline)
    if not apply_pipeline.is_absolute():
        apply_pipeline = dawn_root / apply_pipeline
    orchestrator.run_pipeline(args.project, str(apply_pipeline), profile=args.profile)

    # Verify required outputs
    _get_artifact_path(project_root, "forgescaffold.apply_report.json")
    _get_artifact_path(project_root, "forgescaffold.rollback_patchset.json")
    _get_artifact_path(project_root, "forgescaffold.workspace_snapshot.json")
    verification_path = _get_artifact_path(project_root, "forgescaffold.verification_report.json")
    _get_artifact_path(project_root, "forgescaffold.test_results.manifest.json")
    _get_artifact_path(project_root, "forgescaffold.evidence_pack.manifest.json")

    report = _load_json(verification_path)
    report_mode = report.get("mode", "strict")
    expected_mode = report_mode if args.mode == "auto" else args.mode
    if args.mode != "auto" and report_mode != expected_mode:
        raise RuntimeError(f"Verification report mode {report_mode} does not match expected {expected_mode}")
    report["mode"] = expected_mode
    _validate_verification_report(report)

    print("Phase 3 verifier complete: drift + scope gates validated, apply + evidence outputs present")


if __name__ == "__main__":
    main()
