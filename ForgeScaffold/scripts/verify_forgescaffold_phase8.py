import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
    (project_root / "inputs" / "idea.md").write_text("forge scaffold phase8")
    (project_root / "src" / "app" / "__init__.py").write_text("")
    (project_root / "src" / "app" / "main.py").write_text("print('hello')\n")


def _ensure_signer_keys(project_root: Path, count: int = 2) -> List[str]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for Phase 8 verifier") from exc

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
        raise RuntimeError("cryptography is required for Phase 8 verifier") from exc

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
        "approval_reason": "phase8 verifier",
        "risk_ack": risk_ack,
        "approvers": [
            {"name": approvers[0], "approved_at": now, "nonce": "phase8-approval-nonce-123456"},
            {"name": approvers[1], "approved_at": now, "nonce": "phase8-approval-nonce-abcdef"},
        ],
    }
    _write_json(approval_path, payload)
    return approval_path


def _write_trusted_signers(path: Path, entries: List[Dict[str, Any]]) -> None:
    _write_json(path, {"trusted_signers": entries})


def _read_errors(project_root: Path) -> List[str]:
    report = _load_json(_get_artifact_path(project_root, "forgescaffold.evidence_verification_report.json"))
    return report.get("errors", [])


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ForgeScaffold Phase 8 multisig + scopes + expiry")
    parser.add_argument("--project", "-p", default="forgescaffold_phase8_ci")
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

    pipeline_path = dawn_root / "dawn" / "pipelines" / "forgescaffold_apply_v6_multisig_runnable.yaml"

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
    review_packet_path = _get_artifact_path(project_root, "forgescaffold.review_packet.json")
    review_packet = _load_json(review_packet_path)

    # Scope violation
    _write_approval(
        project_root,
        patchset,
        review_packet["review_packet_sha256"],
        ["one", "two"],
        risk_ack=False,
        approval_id="phase8-approval-1",
    )
    os.environ["FORGESCAFFOLD_SIGNING_KEYS"] = keys[0]
    trusted_path = dawn_root / "dawn" / "policy" / "trusted_signers.yaml"
    _write_trusted_signers(
        trusted_path,
        [
            {
                "fingerprint": fp1,
                "label": "scope-test",
                "scopes": {"projects": ["other"], "pipelines": ["other"]},
                "expires_at": "2030-01-01T00:00:00Z",
                "revoked": False,
            }
        ],
    )
    orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
    if "SIGNER_SCOPE_VIOLATION" not in _read_errors(project_root):
        raise RuntimeError("Expected SIGNER_SCOPE_VIOLATION")

    # Expired signer
    _write_approval(
        project_root,
        patchset,
        review_packet["review_packet_sha256"],
        ["one", "two"],
        risk_ack=False,
        approval_id="phase8-approval-2",
    )
    _write_trusted_signers(
        trusted_path,
        [
            {
                "fingerprint": fp1,
                "label": "expired-test",
                "scopes": {"projects": [args.project], "pipelines": ["forgescaffold_apply_v6_multisig_runnable"]},
                "expires_at": "2000-01-01T00:00:00Z",
                "revoked": False,
            }
        ],
    )
    orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
    if "SIGNER_EXPIRED" not in _read_errors(project_root):
        raise RuntimeError("Expected SIGNER_EXPIRED")

    # High-risk requires two signatures (verify-only after pipeline run)
    _write_approval(
        project_root,
        patchset,
        review_packet["review_packet_sha256"],
        ["one", "two"],
        risk_ack=False,
        approval_id="phase8-approval-3",
    )
    verify_only = project_root / ".forgescaffold_verify_only.yaml"
    with verify_only.open("w") as fh:
        yaml.safe_dump({"pipelineId": "verify_only", "links": [{"id": "forgescaffold.verify_evidence"}]}, fh)

    _write_trusted_signers(
        trusted_path,
        [
            {
                "fingerprint": fp1,
                "label": "sig1",
                "scopes": {"projects": [args.project], "pipelines": ["forgescaffold_apply_v6_multisig_runnable"]},
                "expires_at": "2030-01-01T00:00:00Z",
                "revoked": False,
            }
        ],
    )
    os.environ["FORGESCAFFOLD_SIGNING_KEYS"] = keys[0]
    orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)

    review_packet["overall_risk"] = "high"
    review_packet["required_signatures"] = 2
    review_packet_path.write_text(json.dumps(review_packet, indent=2))
    orchestrator.run_pipeline(args.project, str(verify_only), profile=args.profile)
    if "INSUFFICIENT_SIGNATURES" not in _read_errors(project_root):
        raise RuntimeError("Expected INSUFFICIENT_SIGNATURES")

    _write_trusted_signers(
        trusted_path,
        [
            {
                "fingerprint": fp1,
                "label": "sig1",
                "scopes": {"projects": [args.project], "pipelines": ["forgescaffold_apply_v6_multisig_runnable"]},
                "expires_at": "2030-01-01T00:00:00Z",
                "revoked": False,
            },
            {
                "fingerprint": fp2,
                "label": "sig2",
                "scopes": {"projects": [args.project], "pipelines": ["forgescaffold_apply_v6_multisig_runnable"]},
                "expires_at": "2030-01-01T00:00:00Z",
                "revoked": False,
            },
        ],
    )
    os.environ["FORGESCAFFOLD_SIGNING_KEYS"] = f"{keys[0]},{keys[1]}"
    _write_approval(
        project_root,
        patchset,
        review_packet["review_packet_sha256"],
        ["one", "two"],
        risk_ack=False,
        approval_id="phase8-approval-4",
    )
    orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
    orchestrator.run_pipeline(args.project, str(verify_only), profile=args.profile)

    # Query evidence index
    query_pipeline = project_root / ".forgescaffold_query.yaml"
    with query_pipeline.open("w") as fh:
        yaml.safe_dump(
            {
                "pipelineId": "query_only",
                "links": [
                    {
                        "id": "forgescaffold.query_evidence_index",
                        "config": {"patchset_id": patchset.get("patchset_id"), "limit": 5},
                    }
                ],
            },
            fh,
        )

    orchestrator.run_pipeline(args.project, str(query_pipeline), profile=args.profile)
    results = _load_json(_get_artifact_path(project_root, "forgescaffold.evidence_query_results.json"))
    if results.get("count", 0) < 1:
        raise RuntimeError("Evidence query returned no results")

    print("Phase 8 verifier complete: multisig, trust, query verified")


if __name__ == "__main__":
    main()
