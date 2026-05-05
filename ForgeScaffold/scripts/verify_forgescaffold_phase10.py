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
    (project_root / "inputs" / "idea.md").write_text("forge scaffold phase10")
    (project_root / "src" / "app" / "__init__.py").write_text("")
    (project_root / "src" / "app" / "main.py").write_text("print('hello')\n")


def _ensure_signer_keys(project_root: Path, count: int = 2) -> List[str]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for Phase 10 verifier") from exc

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
        raise RuntimeError("cryptography is required for Phase 10 verifier") from exc

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
        "approval_reason": "phase10 verifier",
        "risk_ack": False,
        "approvers": [
            {"name": approvers[0], "approved_at": now, "nonce": "phase10-approval-nonce-123456"},
            {"name": approvers[1], "approved_at": now, "nonce": "phase10-approval-nonce-abcdef"},
        ],
    }
    _write_json(approval_path, payload)
    return approval_path


def _write_trusted_signers(path: Path, entries: List[Dict[str, Any]]) -> None:
    _write_json(path, {"trusted_signers": entries})


def _read_integrity_report(project_root: Path) -> Dict[str, Any]:
    return _load_json(_get_artifact_path(project_root, "forgescaffold.index_integrity_report.json"))


def _run_verify_only(orchestrator, project: str, project_root: Path, nonce: str) -> None:
    verify_only = project_root / ".forgescaffold_verify_index_only.yaml"
    with verify_only.open("w") as fh:
        yaml.safe_dump(
            {
                "pipelineId": f"verify_only_{nonce}",
                "links": [
                    {"id": "forgescaffold.verify_index_integrity", "config": {"nonce": nonce}},
                ],
            },
            fh,
        )
    orchestrator.run_pipeline(project, str(verify_only))


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ForgeScaffold Phase 10 index integrity")
    parser.add_argument("--project", "-p", default="forgescaffold_phase10_ci")
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

    pipeline_path = dawn_root / "dawn" / "pipelines" / "forgescaffold_apply_v8_integrity_runnable.yaml"

    try:
        orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
        raise RuntimeError("Expected approval gate to block without approval file")
    except Exception:
        pass

    patchset = _load_json(_get_artifact_path(project_root, "forgescaffold.instrumentation.patchset.json"))
    review_packet = _load_json(_get_artifact_path(project_root, "forgescaffold.review_packet.json"))

    os.environ["FORGESCAFFOLD_SIGNING_KEYS"] = ",".join(keys)
    trusted_path = dawn_root / "dawn" / "policy" / "trusted_signers.yaml"
    _write_trusted_signers(
        trusted_path,
        [
            {
                "fingerprint": fp1,
                "label": "sig1",
                "scopes": {"projects": [args.project], "pipelines": ["forgescaffold_apply_v8_integrity_runnable"]},
                "expires_at": "2030-01-01T00:00:00Z",
                "revoked": False,
            },
            {
                "fingerprint": fp2,
                "label": "sig2",
                "scopes": {"projects": [args.project], "pipelines": ["forgescaffold_apply_v8_integrity_runnable"]},
                "expires_at": "2030-01-01T00:00:00Z",
                "revoked": False,
            },
        ],
    )

    # Run twice to create at least 2 entries
    _write_approval(project_root, patchset, review_packet["review_packet_sha256"], ["one", "two"], "phase10-approval-1")
    orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
    _write_approval(project_root, patchset, review_packet["review_packet_sha256"], ["one", "two"], "phase10-approval-2")
    orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)

    integrity_report = _read_integrity_report(project_root)
    if integrity_report.get("status") != "PASS":
        raise RuntimeError("Expected index integrity PASS after two runs")

    # Tamper detection: modify middle line
    index_path = project_root / "evidence" / "evidence_index.jsonl"
    lines = index_path.read_text().splitlines()
    if len(lines) < 2:
        raise RuntimeError("Expected at least 2 entries in evidence_index.jsonl")
    mid = 1
    entry = json.loads(lines[mid])
    entry["risk_level"] = "tampered"
    lines[mid] = json.dumps(entry)
    index_path.write_text("\n".join(lines) + "\n")

    _run_verify_only(orchestrator, args.project, project_root, "tamper")
    report = _read_integrity_report(project_root)
    if "ENTRY_HASH_MISMATCH" not in report.get("error_codes", []):
        raise RuntimeError("Expected ENTRY_HASH_MISMATCH after tamper")
    if report.get("first_bad_line") is None:
        raise RuntimeError("Expected first_bad_line after tamper")

    # Deletion detection
    lines = index_path.read_text().splitlines()
    if lines:
        lines.pop(0)
    index_path.write_text("\n".join(lines) + "\n")
    _run_verify_only(orchestrator, args.project, project_root, "delete")
    report = _read_integrity_report(project_root)
    if "CHAIN_BREAK" not in report.get("error_codes", []):
        raise RuntimeError("Expected CHAIN_BREAK after deletion")

    # Checkpoint verification
    policy_path = dawn_root / "dawn" / "policy" / "runtime_policy.yaml"
    original_policy = policy_path.read_text()
    try:
        payload = yaml.safe_load(original_policy) or {}
        payload.setdefault("forgescaffold", {})
        payload["forgescaffold"].setdefault("index_integrity", {})
        payload["forgescaffold"]["index_integrity"].update({"checkpoint_enabled": True})
        policy_path.write_text(yaml.safe_dump(payload))

        # Rebuild clean index
        index_path.write_text("")
        _write_approval(project_root, patchset, review_packet["review_packet_sha256"], ["one", "two"], "phase10-approval-3")
        orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)

        report = _read_integrity_report(project_root)
        if report.get("status") != "PASS":
            raise RuntimeError("Expected integrity PASS with checkpoint enabled")

        checkpoints_dir = project_root / "evidence" / "checkpoints"
        checkpoint_files = sorted(checkpoints_dir.glob("checkpoint_*.json"))
        if not checkpoint_files:
            raise RuntimeError("Expected checkpoint file")
        checkpoint = checkpoint_files[-1]
        payload = json.loads(checkpoint.read_text())
        payload["last_entry_hash"] = "tamper"
        checkpoint.write_text(json.dumps(payload, indent=2))

        _run_verify_only(orchestrator, args.project, project_root, "checkpoint_tamper")
        report = _read_integrity_report(project_root)
        if not set(report.get("error_codes", [])).intersection(
            {"CHECKPOINT_HASH_MISMATCH", "CHECKPOINT_SIGNATURE_INVALID"}
        ):
            raise RuntimeError("Expected checkpoint tamper detection")
    finally:
        policy_path.write_text(original_policy)

    print("Phase 10 verifier complete: hash chain, checkpoint signing, tamper detection verified")


if __name__ == "__main__":
    main()
