import argparse
import base64
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
    (project_root / "inputs" / "idea.md").write_text("forge scaffold phase9")
    (project_root / "src" / "app" / "__init__.py").write_text("")
    (project_root / "src" / "app" / "main.py").write_text("print('hello')\n")


def _ensure_signer_keys(project_root: Path, count: int = 2) -> List[str]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for Phase 9 verifier") from exc

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
        raise RuntimeError("cryptography is required for Phase 9 verifier") from exc

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
    risk_ack: bool,
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
        "approval_reason": "phase9 verifier",
        "risk_ack": risk_ack,
        "approvers": [
            {"name": approvers[0], "approved_at": now, "nonce": "phase9-approval-nonce-123456"},
            {"name": approvers[1], "approved_at": now, "nonce": "phase9-approval-nonce-abcdef"},
        ],
    }
    _write_json(approval_path, payload)
    return approval_path


def _write_trusted_signers(path: Path, entries: List[Dict[str, Any]]) -> None:
    _write_json(path, {"trusted_signers": entries})


def _load_last_index_entry(project_root: Path) -> Dict[str, Any]:
    index_path = project_root / "evidence" / "evidence_index.jsonl"
    if not index_path.exists():
        raise RuntimeError("evidence_index.jsonl missing")
    lines = [line for line in index_path.read_text().splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("evidence_index.jsonl is empty")
    return json.loads(lines[-1])


def _run_query(orchestrator, project: str, project_root: Path) -> None:
    query_pipeline = project_root / ".forgescaffold_query_only.yaml"
    with query_pipeline.open("w") as fh:
        yaml.safe_dump({"pipelineId": "query_only", "links": [{"id": "forgescaffold.query_evidence_index"}]}, fh)
    orchestrator.run_pipeline(project, str(query_pipeline))


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ForgeScaffold Phase 9 operational hardening")
    parser.add_argument("--project", "-p", default="forgescaffold_phase9_ci")
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

    pipeline_path = dawn_root / "dawn" / "pipelines" / "forgescaffold_apply_v7_operational_runnable.yaml"

    approval_file = project_root / "approvals" / "patchset_approval.json"
    if approval_file.exists():
        approval_file.unlink()
    used_approvals = project_root / "approvals" / "used_approvals.jsonl"
    if used_approvals.exists():
        used_approvals.unlink()

    try:
        orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
        raise RuntimeError("Expected approval gate to block without approval file")
    except Exception as exc:
        if "patchset_approval.json" not in str(exc):
            raise RuntimeError("Gate failure did not mention approval file") from exc

    patchset = _load_json(_get_artifact_path(project_root, "forgescaffold.instrumentation.patchset.json"))
    review_packet = _load_json(_get_artifact_path(project_root, "forgescaffold.review_packet.json"))

    _write_approval(project_root, patchset, review_packet["review_packet_sha256"], ["one", "two"], False, "approval-1")

    os.environ["FORGESCAFFOLD_SIGNING_KEYS"] = ",".join(keys)
    trusted_path = dawn_root / "dawn" / "policy" / "trusted_signers.yaml"
    _write_trusted_signers(
        trusted_path,
        [
            {
                "fingerprint": fp1,
                "label": "sig1",
                "scopes": {"projects": [args.project], "pipelines": ["forgescaffold_apply_v7_operational_runnable"]},
                "expires_at": "2030-01-01T00:00:00Z",
                "revoked": False,
            },
            {
                "fingerprint": fp2,
                "label": "sig2",
                "scopes": {"projects": [args.project], "pipelines": ["forgescaffold_apply_v7_operational_runnable"]},
                "expires_at": "2030-01-01T00:00:00Z",
                "revoked": False,
            },
        ],
    )

    orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)

    entry = _load_last_index_entry(project_root)
    required_fields = [
        "schema_version",
        "signer_fingerprints",
        "signature_count_required",
        "signature_count_valid",
        "pipeline_name",
        "verification_mode",
        "approval_id",
        "approval_id_status",
        "lock_forced",
        "lock_ttl_minutes",
    ]
    for field in required_fields:
        if field not in entry:
            raise RuntimeError(f"Index missing field {field}")

    # Query supports mixed v1/v2 entries
    v1_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "patchset_id": "legacy",
        "approvers": ["legacy"],
        "risk_level": "low",
        "status": "PASS",
    }
    index_path = project_root / "evidence" / "evidence_index.jsonl"
    with index_path.open("a") as fh:
        fh.write(json.dumps(v1_entry) + "\n")

    _run_query(orchestrator, args.project, project_root)

    # Replay guard
    try:
        orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
        raise RuntimeError("Expected replay guard to block reuse of approval_id")
    except Exception as exc:
        if "approval_id" not in str(exc):
            raise RuntimeError("Replay guard failure did not mention approval_id") from exc

    # Lock enforcement
    lock_dir = project_root / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "forgescaffold_apply.lock"
    lock_payload = {
        "pid": 12345,
        "hostname": "test",
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "pipeline_name": "forgescaffold_apply_v7_operational_runnable",
        "patchset_id": patchset.get("patchset_id"),
    }
    lock_path.write_text(json.dumps(lock_payload))

    _write_approval(project_root, patchset, review_packet["review_packet_sha256"], ["one", "two"], False, "approval-2")
    orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
    apply_report = _load_json(_get_artifact_path(project_root, "forgescaffold.apply_report.json"))
    if apply_report.get("status") != "REFUSED_LOCK_HELD":
        raise RuntimeError("Expected REFUSED_LOCK_HELD when lock present")

    if lock_path.exists():
        lock_path.unlink()

    # Retention prune dry_run
    policy_path = dawn_root / "dawn" / "policy" / "runtime_policy.yaml"
    original_policy = policy_path.read_text()
    try:
        payload = yaml.safe_load(original_policy) or {}
        payload.setdefault("forgescaffold", {})
        payload["forgescaffold"].setdefault("retention", {})
        payload["forgescaffold"]["retention"].update(
            {"enabled": True, "max_packs": 1, "max_days": None, "max_index_lines": None, "prune_mode": "dry_run"}
        )
        policy_path.write_text(yaml.safe_dump(payload))

        prune_pipeline = project_root / ".forgescaffold_prune_only.yaml"
        with prune_pipeline.open("w") as fh:
            yaml.safe_dump({"pipelineId": "prune_only", "links": [{"id": "forgescaffold.prune_evidence"}]}, fh)
        orchestrator.run_pipeline(args.project, str(prune_pipeline), profile=args.profile)
        prune_report = _load_json(_get_artifact_path(project_root, "forgescaffold.prune_report.json"))
        if prune_report.get("status") == "SKIPPED_DISABLED":
            raise RuntimeError("Expected prune report to run when retention enabled")
    finally:
        policy_path.write_text(original_policy)

    # Status link
    status_pipeline = project_root / ".forgescaffold_status_only.yaml"
    with status_pipeline.open("w") as fh:
        yaml.safe_dump({"pipelineId": "status_only", "links": [{"id": "forgescaffold.status"}]}, fh)
    orchestrator.run_pipeline(args.project, str(status_pipeline), profile=args.profile)
    status = _load_json(_get_artifact_path(project_root, "forgescaffold.status.json"))
    for key in ["policy", "latest_runs", "signers", "lock"]:
        if key not in status:
            raise RuntimeError(f"Status missing {key}")

    print("Phase 9 verifier complete: index v2, replay guard, locks, retention, status verified")


if __name__ == "__main__":
    main()
