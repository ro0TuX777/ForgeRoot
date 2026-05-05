import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r") as fh:
        return json.load(fh)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(payload, fh, indent=2)


def _bootstrap_project(project_root: Path) -> None:
    (project_root / "inputs").mkdir(parents=True, exist_ok=True)
    (project_root / "src" / "app").mkdir(parents=True, exist_ok=True)
    (project_root / "approvals").mkdir(parents=True, exist_ok=True)
    (project_root / "keys").mkdir(parents=True, exist_ok=True)
    (project_root / "inputs" / "idea.md").write_text("forge scaffold phase12")
    (project_root / "src" / "app" / "__init__.py").write_text("")
    (project_root / "src" / "app" / "main.py").write_text("print('hello')\n")


def _ensure_signer_keys(project_root: Path, count: int = 2) -> List[str]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for Phase 12 verifier") from exc

    signers_dir = project_root / "keys" / "signers"
    signers_dir.mkdir(parents=True, exist_ok=True)

    keys = []
    existing = sorted([p for p in signers_dir.iterdir() if p.is_file()])
    for path in existing:
        keys.append(path.read_text().strip())

    while len(keys) < count:
        private_key = ed25519.Ed25519PrivateKey.generate()
        raw = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_text = base64.b64encode(raw).decode()
        path = signers_dir / f"signer_{len(keys)+1}.key"
        path.write_text(key_text)
        keys.append(key_text)

    return keys[:count]


def _fingerprint_for_key(key_text: str) -> str:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for Phase 12 verifier") from exc

    raw = base64.b64decode(key_text)
    if len(raw) == 64:
        raw = raw[:32]
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(raw)
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(public_bytes).hexdigest()


def _get_artifact_path(project_root: Path, artifact_id: str) -> Path:
    index_path = project_root / "artifact_index.json"
    if not index_path.exists():
        raise RuntimeError("artifact_index.json missing")
    index = _load_json(index_path)
    entry = index.get(artifact_id)
    if not entry:
        raise RuntimeError(f"Artifact {artifact_id} missing from index")
    return Path(entry["path"])


def _write_approval(
    project_root: Path,
    patchset: Dict[str, Any],
    review_sha: str,
    approvers: List[str],
    approval_id: str,
) -> None:
    approval_path = project_root / "approvals" / "patchset_approval.json"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {
        "schema_version": "1.0.0",
        "approval_id": approval_id,
        "patchset_id": patchset.get("patchset_id"),
        "bundle_content_sha256": patchset.get("target", {}).get("bundle_content_sha256"),
        "review_packet_sha256": review_sha,
        "approval_reason": "phase12 verifier",
        "risk_ack": False,
        "approvers": [
            {"name": approvers[0], "approved_at": now, "nonce": "phase12-approval-nonce-123456"},
            {"name": approvers[1], "approved_at": now, "nonce": "phase12-approval-nonce-abcdef"},
        ],
    }
    _write_json(approval_path, payload)


def _write_trusted_signers(path: Path, entries: List[Dict[str, Any]]) -> None:
    _write_json(path, {"trusted_signers": entries})


def _run_single_link(orchestrator, project: str, link_id: str, config: Dict[str, Any]) -> None:
    nonce = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    merged = dict(config or {})
    merged.setdefault("nonce", nonce)
    pipeline_path = Path(f"/tmp/forgescaffold_{link_id.replace('.', '_')}.yaml")
    with pipeline_path.open("w") as fh:
        yaml.safe_dump(
            {
                "pipelineId": f"verify_only_{link_id}_{nonce}",
                "links": [{"id": link_id, "config": merged}],
            },
            fh,
        )
    orchestrator.run_pipeline(project, str(pipeline_path))


def _sha256_file(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ForgeScaffold Phase 12 global ops")
    parser.add_argument("--project", "-p", default="forgescaffold_phase12_ci")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--profile", default="forgescaffold_apply_lowrisk")
    args = parser.parse_args()

    dawn_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(dawn_root))

    from dawn.runtime.orchestrator import Orchestrator

    links_dirs = [str(dawn_root / "dawn" / "links")]
    orchestrator = Orchestrator(links_dirs, str(dawn_root / "projects"))

    coord_project = args.project
    project_a = "forgescaffold_phase12_a_ci"
    project_b = "forgescaffold_phase12_b_ci"

    coord_root = dawn_root / "projects" / coord_project
    if not coord_root.exists():
        if args.bootstrap:
            _bootstrap_project(coord_root)
        else:
            raise RuntimeError(f"Project {coord_project} not found under {dawn_root / 'projects'}")

    for project in [project_a, project_b]:
        project_root = dawn_root / "projects" / project
        if not project_root.exists():
            if args.bootstrap:
                _bootstrap_project(project_root)
            else:
                raise RuntimeError(f"Project {project} not found under {dawn_root / 'projects'}")
        _bootstrap_project(project_root)

        evidence_dir = project_root / "evidence"
        if evidence_dir.exists():
            for item in evidence_dir.rglob("*"):
                if item.is_file():
                    item.unlink()
            for item in sorted(evidence_dir.rglob("*"), reverse=True):
                if item.is_dir():
                    item.rmdir()

        approval_file = project_root / "approvals" / "patchset_approval.json"
        if approval_file.exists():
            approval_file.unlink()
        used_approvals = project_root / "approvals" / "used_approvals.jsonl"
        if used_approvals.exists():
            used_approvals.unlink()

    keys = _ensure_signer_keys(dawn_root / "projects" / project_a, count=2)
    fp1 = _fingerprint_for_key(keys[0])
    fp2 = _fingerprint_for_key(keys[1])

    policy_path = dawn_root / "dawn" / "policy" / "runtime_policy.yaml"
    trusted_path = dawn_root / "dawn" / "policy" / "trusted_signers.yaml"
    original_policy = policy_path.read_text()
    original_trusted = trusted_path.read_text() if trusted_path.exists() else None

    try:
        payload = yaml.safe_load(original_policy) or {}
        payload.setdefault("forgescaffold", {})
        payload["forgescaffold"].setdefault("global_catalog", {})
        payload["forgescaffold"]["global_catalog"].update(
            {"enabled": True, "write_root": "evidence/global", "projects_allowlist": [project_a, project_b], "sign_catalog": False}
        )
        policy_path.write_text(yaml.safe_dump(payload))

        _write_trusted_signers(
            trusted_path,
            [
                {
                    "fingerprint": fp1,
                    "label": "sig1",
                    "scopes": {"projects": [project_a, project_b], "pipelines": ["forgescaffold_apply_v9_cache_runnable"]},
                    "expires_at": "2030-01-01T00:00:00Z",
                    "revoked": False,
                },
                {
                    "fingerprint": fp2,
                    "label": "sig2",
                    "scopes": {"projects": [project_a, project_b], "pipelines": ["forgescaffold_apply_v9_cache_runnable"]},
                    "expires_at": "2030-01-01T00:00:00Z",
                    "revoked": False,
                },
            ],
        )

        os.environ["FORGESCAFFOLD_SIGNING_KEYS"] = ",".join(keys)

        pipeline_path = dawn_root / "dawn" / "pipelines" / "forgescaffold_apply_v9_cache_runnable.yaml"

        for project in [project_a, project_b]:
            try:
                orchestrator.run_pipeline(project, str(pipeline_path), profile=args.profile)
                raise RuntimeError("Expected approval gate to block without approval file")
            except Exception:
                pass

            project_root = dawn_root / "projects" / project
            patchset = _load_json(_get_artifact_path(project_root, "forgescaffold.instrumentation.patchset.json"))
            review_packet = _load_json(_get_artifact_path(project_root, "forgescaffold.review_packet.json"))

            _write_approval(project_root, patchset, review_packet["review_packet_sha256"], ["one", "two"], f"{project}-approval-1")
            orchestrator.run_pipeline(project, str(pipeline_path), profile=args.profile)

            _write_approval(project_root, patchset, review_packet["review_packet_sha256"], ["one", "two"], f"{project}-approval-2")
            orchestrator.run_pipeline(project, str(pipeline_path), profile=args.profile)

        # Build catalog and ensure deterministic
        _run_single_link(orchestrator, args.project, "forgescaffold.build_global_catalog", {"projects": [project_a, project_b]})
        catalog_path = dawn_root / "evidence" / "global" / "catalog.json"
        first_hash = _sha256_file(catalog_path)
        _run_single_link(orchestrator, args.project, "forgescaffold.build_global_catalog", {"projects": [project_a, project_b]})
        second_hash = _sha256_file(catalog_path)
        if first_hash != second_hash:
            raise RuntimeError("Global catalog hash changed across identical runs")

        # Force scan fallback for one project
        cache_b = dawn_root / "projects" / project_b / "evidence" / "cache" / "evidence_index_cache.sqlite"
        if cache_b.exists():
            cache_b.unlink()

        _run_single_link(orchestrator, args.project, "forgescaffold.build_global_catalog", {"projects": [project_a, project_b]})

        patchset_id = _load_json(
            _get_artifact_path(dawn_root / "projects" / project_a, "forgescaffold.instrumentation.patchset.json")
        ).get("patchset_id")

        _run_single_link(
            orchestrator,
            args.project,
            "forgescaffold.query_global_evidence",
            {"patchset_id": patchset_id, "projects": [project_a, project_b]},
        )
        query_report = _load_json(
            _get_artifact_path(dawn_root / "projects" / args.project, "forgescaffold.evidence_global_query_results.json")
        )
        projects_seen = sorted({entry.get("project") for entry in query_report.get("results", [])})
        if projects_seen != sorted([project_a, project_b]):
            raise RuntimeError("Expected results from both projects in global query")
        backend = query_report.get("query_backend_summary", {})
        if project_b not in backend.get("scan_jsonl_projects", []):
            raise RuntimeError("Expected project_b to use scan_jsonl backend")

        # Batch cache build
        _run_single_link(orchestrator, args.project, "forgescaffold.build_all_caches", {})
        batch_report = _load_json(
            _get_artifact_path(dawn_root / "projects" / args.project, "forgescaffold.cache_batch_report.json")
        )
        statuses = {entry.get("project"): entry.get("status") for entry in batch_report.get("projects", [])}
        if statuses.get(project_b) != "BUILT":
            raise RuntimeError("Expected stale project cache to be rebuilt")

        _run_single_link(orchestrator, args.project, "forgescaffold.build_all_caches", {})
        batch_report = _load_json(
            _get_artifact_path(dawn_root / "projects" / args.project, "forgescaffold.cache_batch_report.json")
        )
        if any(entry.get("status") != "SKIPPED" for entry in batch_report.get("projects", [])):
            raise RuntimeError("Expected all cache builds to be SKIPPED on rerun")

        # Global status
        _run_single_link(orchestrator, args.project, "forgescaffold.build_global_catalog", {"projects": [project_a, project_b]})
        _run_single_link(orchestrator, args.project, "forgescaffold.status_global", {})
        status_report = _load_json(
            _get_artifact_path(dawn_root / "projects" / args.project, "forgescaffold.status_global.json")
        )
        if status_report.get("cache_coverage_percent", 0) < 100:
            raise RuntimeError("Expected cache coverage to be 100% after rebuild")
        if status_report.get("stale_caches"):
            raise RuntimeError("Expected no stale caches after rebuild")
        if len(status_report.get("recent_runs", [])) < 4:
            raise RuntimeError("Expected recent runs to include entries from both projects")

    finally:
        policy_path.write_text(original_policy)
        if original_trusted is None:
            trusted_path.unlink(missing_ok=True)
        else:
            trusted_path.write_text(original_trusted)

    print("Phase 12 verifier complete: global catalog, cross-project query, cache batch, global status verified")


if __name__ == "__main__":
    main()
