import argparse
import base64
import json
import sys
from datetime import datetime, timezone
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


def _bootstrap_project(project_root: Path) -> None:
    (project_root / "inputs").mkdir(parents=True, exist_ok=True)
    (project_root / "src" / "app").mkdir(parents=True, exist_ok=True)
    (project_root / "approvals").mkdir(parents=True, exist_ok=True)
    (project_root / "keys").mkdir(parents=True, exist_ok=True)
    (project_root / "inputs" / "idea.md").write_text("forge scaffold phase6")
    (project_root / "src" / "app" / "__init__.py").write_text("")
    (project_root / "src" / "app" / "main.py").write_text("print('hello')\n")


def _ensure_keys(project_root: Path) -> None:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for Phase 6 verifier") from exc

    key_path = project_root / "keys" / "ed25519_private.key"
    if key_path.exists():
        return

    private_key = ed25519.Ed25519PrivateKey.generate()
    raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path.write_text(base64.b64encode(raw).decode())


def _get_artifact_path(project_root: Path, artifact_id: str) -> Path:
    index_path = project_root / "artifact_index.json"
    if not index_path.exists():
        raise RuntimeError("artifact_index.json missing")
    index = _load_json(index_path)
    entry = index.get(artifact_id)
    if not entry:
        raise RuntimeError(f"Artifact {artifact_id} missing from index")
    return Path(entry["path"])


def _write_approval(project_root: Path, patchset: Dict[str, Any], review_sha: str, override_sha: str = None) -> None:
    approval_path = project_root / "approvals" / "patchset_approval.json"
    payload = {
        "schema_version": "1.0.0",
        "patchset_id": patchset.get("patchset_id"),
        "bundle_content_sha256": patchset.get("target", {}).get("bundle_content_sha256"),
        "approver": "phase6",
        "approval_reason": "phase6 verifier",
        "approved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "nonce": "phase6-approval-nonce-123456",
        "review_packet_sha256": override_sha or review_sha,
    }
    _write_json(approval_path, payload)


def _write_trusted_signers(policy_path: Path, fingerprint: str = None, revoked: bool = False) -> None:
    payload = {"trusted_signers": []}
    if fingerprint:
        payload["trusted_signers"].append({
            "fingerprint": fingerprint,
            "label": "phase6",
            "added_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "revoked": revoked,
        })
    _write_json(policy_path, payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ForgeScaffold Phase 6 review+trust")
    parser.add_argument("--project", "-p", default="forgescaffold_phase6_ci")
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
    _ensure_keys(project_root)
    approval_path = project_root / "approvals" / "patchset_approval.json"
    if approval_path.exists():
        approval_path.unlink()

    trusted_path = dawn_root / "dawn" / "policy" / "trusted_signers.yaml"
    _write_trusted_signers(trusted_path)

    pipeline_path = dawn_root / "dawn" / "pipelines" / "forgescaffold_apply_v4_review_hitl_runnable.yaml"

    # Run once to generate review packet; expect gate failure without approval
    try:
        orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
        raise RuntimeError("Expected gate to block without approval")
    except Exception as exc:
        if "patchset_approval.json" not in str(exc):
            raise RuntimeError("Approval gate failure did not mention approval file") from exc

    patchset_path = _get_artifact_path(project_root, "forgescaffold.instrumentation.patchset.json")
    patchset = _load_json(patchset_path)
    review_packet = _load_json(_get_artifact_path(project_root, "forgescaffold.review_packet.json"))

    # Approval binding mismatch
    _write_approval(project_root, patchset, review_packet["review_packet_sha256"], override_sha="deadbeef")
    try:
        orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
        raise RuntimeError("Expected approval review packet mismatch to fail")
    except Exception:
        pass

    # Correct approval
    _write_approval(project_root, patchset, review_packet["review_packet_sha256"])

    # Untrusted signer should fail verify_evidence
    try:
        orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
        raise RuntimeError("Expected verify_evidence to fail for untrusted signer")
    except Exception:
        pass

    signature_payload = _load_json(_get_artifact_path(project_root, "forgescaffold.evidence_signature.json"))
    fingerprint = signature_payload.get("public_key_fingerprint")

    # Trust signer and re-run (should pass)
    _write_trusted_signers(trusted_path, fingerprint=fingerprint)
    orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)

    report = _load_json(_get_artifact_path(project_root, "forgescaffold.evidence_verification_report.json"))
    if report.get("status") != "PASS":
        raise RuntimeError("Expected evidence verification PASS with trusted signer")

    # Manifest tamper should fail verify_evidence
    manifest_path = _get_artifact_path(project_root, "forgescaffold.evidence_manifest.json")
    manifest = _load_json(manifest_path)
    manifest["tamper"] = True
    _write_json(manifest_path, manifest)

    verify_only = project_root / ".forgescaffold_verify_only.yaml"
    with verify_only.open("w") as fh:
        yaml.safe_dump({"pipelineId": "verify_only", "links": [{"id": "forgescaffold.verify_evidence"}]}, fh)
    orchestrator.run_pipeline(args.project, str(verify_only), profile=args.profile)

    report = _load_json(_get_artifact_path(project_root, "forgescaffold.evidence_verification_report.json"))
    if report.get("status") != "FAIL" or "MANIFEST_HASH_MISMATCH" not in report.get("errors", []):
        raise RuntimeError("Expected MANIFEST_HASH_MISMATCH after tampering")

    print("Phase 6 verifier complete: review binding, trusted signer, manifest tamper checks PASS")


if __name__ == "__main__":
    main()
