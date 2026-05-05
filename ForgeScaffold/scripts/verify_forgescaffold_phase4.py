import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


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


def _bootstrap_project(project_root: Path) -> Path:
    (project_root / "inputs").mkdir(parents=True, exist_ok=True)
    (project_root / "src" / "app").mkdir(parents=True, exist_ok=True)
    (project_root / "inputs" / "idea.md").write_text("forge scaffold phase4")
    target = project_root / "src" / "app" / "phase4_target.txt"
    target.write_text("alpha\nbeta\ngamma\nbeta\nomega\n")
    return target


def _ensure_bundle(orchestrator, project: str, pipeline_path: Path, profile: str) -> None:
    orchestrator.run_pipeline(project, str(pipeline_path), profile=profile)


def _get_artifact_index(project_root: Path) -> Dict[str, Any]:
    index_path = project_root / "artifact_index.json"
    if index_path.exists():
        return _load_json(index_path)
    return {}


def _write_patchset(project_root: Path, patchset: Dict[str, Any]) -> Path:
    patch_path = project_root / "artifacts" / "forgescaffold.obs_instrument_patchset" / "instrumentation.patchset.json"
    _write_json(patch_path, patchset)
    index = _get_artifact_index(project_root)
    index["forgescaffold.instrumentation.patchset.json"] = {
        "path": str(patch_path),
        "producer_link_id": "forgescaffold.obs_instrument_patchset",
    }
    _write_json(project_root / "artifact_index.json", index)
    return patch_path


def _get_apply_report(project_root: Path) -> Dict[str, Any]:
    index = _get_artifact_index(project_root)
    entry = index.get("forgescaffold.apply_report.json")
    if not entry:
        raise RuntimeError("apply_report missing from artifact index")
    return _load_json(Path(entry["path"]))


def _get_rollback_patchset(project_root: Path) -> Dict[str, Any]:
    index = _get_artifact_index(project_root)
    entry = index.get("forgescaffold.rollback_patchset.json")
    if not entry:
        raise RuntimeError("rollback_patchset missing from artifact index")
    return _load_json(Path(entry["path"]))


def _bundle_content_sha(project_root: Path) -> str:
    index = _get_artifact_index(project_root)
    entry = index.get("dawn.project.bundle")
    if not entry:
        return ""
    bundle = _load_json(Path(entry["path"]))
    return bundle.get("bundle_content_sha256", "")


def _make_apply_only_pipeline(project_root: Path) -> Path:
    pipeline_path = project_root / ".forgescaffold_apply_only.yaml"
    payload = {"pipelineId": "forgescaffold_apply_only", "links": [{"id": "forgescaffold.apply_patchset"}]}
    with pipeline_path.open("w") as fh:
        yaml.safe_dump(payload, fh)
    return pipeline_path


def _assert_status(report: Dict[str, Any], expected: str) -> None:
    status = report.get("status")
    if status != expected:
        raise RuntimeError(f"Expected status {expected}, got {status}")


def _assert_hunk_status(report: Dict[str, Any], expected: str) -> None:
    ops = report.get("operations", {})
    for bucket in ("applied", "failed", "skipped"):
        for entry in ops.get(bucket, []):
            for hunk in entry.get("hunks", []):
                if hunk.get("status") == expected:
                    return
    raise RuntimeError(f"Expected hunk status {expected} not found in report")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ForgeScaffold Phase 4 hunk apply")
    parser.add_argument("--project", "-p", default="forgescaffold_phase4_ci")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--profile", default="forgescaffold_apply_lowrisk")
    args = parser.parse_args()

    dawn_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(dawn_root))

    from dawn.runtime.orchestrator import Orchestrator

    links_dirs = [str(dawn_root / "dawn" / "links")]
    orchestrator = Orchestrator(links_dirs, str(dawn_root / "projects"))

    project_root = dawn_root / "projects" / args.project
    if not project_root.exists():
        if args.bootstrap:
            target_file = _bootstrap_project(project_root)
        else:
            raise RuntimeError(f"Project {args.project} not found under {dawn_root / 'projects'}")
    else:
        target_file = project_root / "src" / "app" / "phase4_target.txt"
        if not target_file.exists():
            if args.bootstrap:
                target_file = _bootstrap_project(project_root)
            else:
                raise RuntimeError("phase4_target.txt missing; rerun with --bootstrap")

    bundle_pipeline = project_root / ".forgescaffold_bundle_only.yaml"
    with bundle_pipeline.open("w") as fh:
        yaml.safe_dump({"pipelineId": "bundle_only", "links": [{"id": "ingest.project_bundle"}]}, fh)

    _ensure_bundle(orchestrator, args.project, bundle_pipeline, args.profile)
    apply_only = _make_apply_only_pipeline(project_root)

    baseline_content = "alpha\nbeta\ngamma\nbeta\nomega\n"
    target_file.write_text(baseline_content)
    original_content = baseline_content

    # Success path
    before = "beta\n"
    after = "beta2\n"
    patchset = {
        "schema_version": "1.0.1",
        "patchset_id": "phase4_success",
        "generator": {"name": "phase4", "version": "1.0.0"},
        "target": {
            "project_id": args.project,
            "bundle_content_sha256": _bundle_content_sha(project_root),
        },
        "operations": [
            {
                "op": "modify",
                "path": "src/app/phase4_target.txt",
                "tags": ["observability"],
                "patch": [
                    {
                        "anchor": {"type": "line_range", "value": "L2-L2"},
                        "action": "replace",
                        "content": after,
                        "expected_before_sha256": _sha256_text(before),
                        "expected_after_sha256": _sha256_text(after),
                    }
                ],
            }
        ],
    }
    _write_patchset(project_root, patchset)
    orchestrator.run_pipeline(args.project, str(apply_only), profile=args.profile)
    report = _get_apply_report(project_root)
    _assert_status(report, "APPLIED")
    _assert_hunk_status(report, "APPLIED")
    rollback_snapshot = _get_rollback_patchset(project_root)
    if target_file.read_text() == original_content:
        raise RuntimeError("Expected file to change on apply")

    # Idempotency
    post_apply = target_file.read_text()
    orchestrator.run_pipeline(args.project, str(apply_only), profile=args.profile)
    report = _get_apply_report(project_root)
    _assert_hunk_status(report, "SKIPPED_ALREADY_APPLIED")
    if target_file.read_text() != post_apply:
        raise RuntimeError("Unexpected change on idempotent apply")

    # Anchor not found
    target_file.write_text(original_content)
    patchset_not_found = {
        **patchset,
        "patchset_id": "phase4_not_found",
        "operations": [
            {
                "op": "modify",
                "path": "src/app/phase4_target.txt",
                "tags": ["observability"],
                "patch": [
                    {
                        "anchor": {"type": "literal", "value": "missing_literal"},
                        "action": "replace",
                        "content": after,
                    }
                ],
            }
        ],
    }
    _write_patchset(project_root, patchset_not_found)
    orchestrator.run_pipeline(args.project, str(apply_only), profile=args.profile)
    report = _get_apply_report(project_root)
    _assert_status(report, "FAILED")
    _assert_hunk_status(report, "CONFLICT_ANCHOR_NOT_FOUND")

    # Ambiguous anchor
    target_file.write_text(original_content)
    patchset_ambiguous = {
        **patchset,
        "patchset_id": "phase4_ambiguous",
        "operations": [
            {
                "op": "modify",
                "path": "src/app/phase4_target.txt",
                "tags": ["observability"],
                "patch": [
                    {
                        "anchor": {"type": "regex", "value": "beta"},
                        "action": "replace",
                        "content": after,
                    }
                ],
            }
        ],
    }
    _write_patchset(project_root, patchset_ambiguous)
    orchestrator.run_pipeline(args.project, str(apply_only), profile=args.profile)
    report = _get_apply_report(project_root)
    _assert_status(report, "FAILED")
    _assert_hunk_status(report, "CONFLICT_ANCHOR_AMBIGUOUS")

    # Before-hash mismatch
    target_file.write_text(original_content)
    patchset_before_mismatch = {
        **patchset,
        "patchset_id": "phase4_before_mismatch",
        "operations": [
            {
                "op": "modify",
                "path": "src/app/phase4_target.txt",
                "tags": ["observability"],
                "patch": [
                    {
                        "anchor": {"type": "literal", "value": before, "occurrence": 1},
                        "action": "replace",
                        "content": after,
                        "expected_before_sha256": "deadbeef",
                    }
                ],
            }
        ],
    }
    _write_patchset(project_root, patchset_before_mismatch)
    orchestrator.run_pipeline(args.project, str(apply_only), profile=args.profile)
    report = _get_apply_report(project_root)
    _assert_status(report, "FAILED")
    _assert_hunk_status(report, "CONFLICT_BEFORE_HASH_MISMATCH")

    # Rollback correctness
    target_file.write_text(original_content)
    _write_patchset(project_root, patchset)
    orchestrator.run_pipeline(args.project, str(apply_only), profile=args.profile)
    report = _get_apply_report(project_root)
    _assert_status(report, "APPLIED")
    rollback_path = project_root / "artifacts" / "forgescaffold.obs_instrument_patchset" / "instrumentation.patchset.json"
    _write_json(rollback_path, rollback_snapshot)
    orchestrator.run_pipeline(args.project, str(apply_only), profile=args.profile)
    if target_file.read_text() != original_content:
        raise RuntimeError("Rollback did not restore original content")

    print("Phase 4 verifier complete: hunk apply, conflicts, idempotency, rollback verified")


if __name__ == "__main__":
    main()
