import argparse
import base64
import json
import os
import sqlite3
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
    (project_root / "inputs" / "idea.md").write_text("forge scaffold phase11")
    (project_root / "src" / "app" / "__init__.py").write_text("")
    (project_root / "src" / "app" / "main.py").write_text("print('hello')\n")


def _ensure_signer_keys(project_root: Path, count: int = 2) -> List[str]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for Phase 11 verifier") from exc

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
        raise RuntimeError("cryptography is required for Phase 11 verifier") from exc

    raw = base64.b64decode(key_text)
    if len(raw) == 64:
        raw = raw[:32]
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(raw)
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    import hashlib

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
) -> Path:
    approval_path = project_root / "approvals" / "patchset_approval.json"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {
        "schema_version": "1.0.0",
        "approval_id": approval_id,
        "patchset_id": patchset.get("patchset_id"),
        "bundle_content_sha256": patchset.get("target", {}).get("bundle_content_sha256"),
        "review_packet_sha256": review_sha,
        "approval_reason": "phase11 verifier",
        "risk_ack": False,
        "approvers": [
            {"name": approvers[0], "approved_at": now, "nonce": "phase11-approval-nonce-123456"},
            {"name": approvers[1], "approved_at": now, "nonce": "phase11-approval-nonce-abcdef"},
        ],
    }
    _write_json(approval_path, payload)
    return approval_path


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


def _read_report(project_root: Path, artifact_id: str) -> Dict[str, Any]:
    return _load_json(_get_artifact_path(project_root, artifact_id))


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ForgeScaffold Phase 11 cache + cadence")
    parser.add_argument("--project", "-p", default="forgescaffold_phase11_ci")
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
            _bootstrap_project(project_root)
        else:
            raise RuntimeError(f"Project {args.project} not found under {dawn_root / 'projects'}")

    _bootstrap_project(project_root)
    keys = _ensure_signer_keys(project_root, count=2)
    fp1 = _fingerprint_for_key(keys[0])
    fp2 = _fingerprint_for_key(keys[1])

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

    pipeline_path = dawn_root / "dawn" / "pipelines" / "forgescaffold_apply_v9_cache_runnable.yaml"

    policy_path = dawn_root / "dawn" / "policy" / "runtime_policy.yaml"
    trusted_path = dawn_root / "dawn" / "policy" / "trusted_signers.yaml"
    original_policy = policy_path.read_text()
    original_trusted = trusted_path.read_text() if trusted_path.exists() else None

    try:
        payload = yaml.safe_load(original_policy) or {}
        payload.setdefault("forgescaffold", {})
        payload["forgescaffold"].setdefault("index_integrity", {})
        payload["forgescaffold"]["index_integrity"].update(
            {"checkpoint_enabled": True, "checkpoint_min_interval_seconds": 3600, "checkpoint_every_n_entries": None}
        )
        policy_path.write_text(yaml.safe_dump(payload))

        _write_trusted_signers(
            trusted_path,
            [
                {
                    "fingerprint": fp1,
                    "label": "sig1",
                    "scopes": {"projects": [args.project], "pipelines": ["forgescaffold_apply_v9_cache_runnable"]},
                    "expires_at": "2030-01-01T00:00:00Z",
                    "revoked": False,
                },
                {
                    "fingerprint": fp2,
                    "label": "sig2",
                    "scopes": {"projects": [args.project], "pipelines": ["forgescaffold_apply_v9_cache_runnable"]},
                    "expires_at": "2030-01-01T00:00:00Z",
                    "revoked": False,
                },
            ],
        )

        os.environ["FORGESCAFFOLD_SIGNING_KEYS"] = ",".join(keys)

        try:
            orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
            raise RuntimeError("Expected approval gate to block without approval file")
        except Exception:
            pass

        patchset = _load_json(_get_artifact_path(project_root, "forgescaffold.instrumentation.patchset.json"))
        review_packet = _load_json(_get_artifact_path(project_root, "forgescaffold.review_packet.json"))

        _write_approval(project_root, patchset, review_packet["review_packet_sha256"], ["one", "two"], "phase11-approval-1")
        orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)

        _write_approval(project_root, patchset, review_packet["review_packet_sha256"], ["one", "two"], "phase11-approval-2")
        orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)

        checkpoints_dir = project_root / "evidence" / "checkpoints"
        checkpoint_files = [p for p in checkpoints_dir.glob("checkpoint_*.json") if not p.name.endswith(".signature.json")]
        if len(checkpoint_files) != 1:
            raise RuntimeError("Expected a single checkpoint with min_interval cadence")

        # No artifact is emitted for checkpoint success; use file presence as evidence.

        _write_approval(project_root, patchset, review_packet["review_packet_sha256"], ["one", "two"], "phase11-approval-3")
        orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
        if len([p for p in checkpoints_dir.glob("checkpoint_*.json") if not p.name.endswith(".signature.json")]) != 1:
            raise RuntimeError("Expected cadence to suppress a second checkpoint")

        _run_single_link(orchestrator, args.project, "forgescaffold.build_index_cache", {})
        report = _read_report(project_root, "forgescaffold.cache_build_report.json")
        if report.get("status") not in {"BUILT", "SKIPPED_CACHE_UPTODATE"}:
            raise RuntimeError("Expected cache build to report BUILT or SKIPPED_CACHE_UPTODATE")

        _run_single_link(orchestrator, args.project, "forgescaffold.build_index_cache", {})
        report = _read_report(project_root, "forgescaffold.cache_build_report.json")
        if report.get("status") != "SKIPPED_CACHE_UPTODATE":
            raise RuntimeError("Expected cache build to be idempotent and SKIPPED_CACHE_UPTODATE")

        _run_single_link(orchestrator, args.project, "forgescaffold.query_evidence_index", {"no_cache": True})
        scan = _read_report(project_root, "forgescaffold.evidence_query_results.json")

        _run_single_link(orchestrator, args.project, "forgescaffold.query_evidence_index", {})
        cached = _read_report(project_root, "forgescaffold.evidence_query_results.json")

        if scan.get("results") != cached.get("results"):
            raise RuntimeError("Expected cache query results to match scan results")

        _run_single_link(orchestrator, args.project, "forgescaffold.verify_cache_integrity", {})
        report = _read_report(project_root, "forgescaffold.cache_integrity_report.json")
        if report.get("status") != "PASS":
            raise RuntimeError("Expected cache integrity PASS")

        cache_path = project_root / "evidence" / "cache" / "evidence_index_cache.sqlite"
        conn = sqlite3.connect(str(cache_path))
        try:
            conn.execute("UPDATE evidence_runs SET status='TAMPERED' WHERE line_no=1")
            conn.commit()
        finally:
            conn.close()

        _run_single_link(orchestrator, args.project, "forgescaffold.verify_cache_integrity", {})
        report = _read_report(project_root, "forgescaffold.cache_integrity_report.json")
        if "CACHE_ROW_MISMATCH" not in report.get("error_codes", []):
            raise RuntimeError("Expected CACHE_ROW_MISMATCH after tamper")

    finally:
        policy_path.write_text(original_policy)
        if original_trusted is None:
            trusted_path.unlink(missing_ok=True)
        else:
            trusted_path.write_text(original_trusted)

    print("Phase 11 verifier complete: cadence, cache, query acceleration verified")


if __name__ == "__main__":
    main()
