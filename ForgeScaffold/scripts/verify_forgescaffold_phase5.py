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
    (project_root / "inputs" / "idea.md").write_text("forge scaffold phase5")
    (project_root / "src" / "app" / "__init__.py").write_text("")
    (project_root / "src" / "app" / "main.py").write_text("print('hello')\n")


def _ensure_keys(project_root: Path) -> Path:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for Phase 5 verifier") from exc

    key_path = project_root / "keys" / "ed25519_private.key"
    if key_path.exists():
        return key_path

    private_key = ed25519.Ed25519PrivateKey.generate()
    raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path.write_text(base64.b64encode(raw).decode())
    return key_path


def _get_artifact_path(project_root: Path, artifact_id: str) -> Path:
    index_path = project_root / "artifact_index.json"
    if not index_path.exists():
        raise RuntimeError("artifact_index.json missing")
    index = _load_json(index_path)
    entry = index.get(artifact_id)
    if not entry:
        raise RuntimeError(f"Artifact {artifact_id} missing from index")
    return Path(entry["path"])


def _canonical_json(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _verify_signature(manifest: Dict[str, Any], signature_payload: Dict[str, Any]) -> None:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for signature verification") from exc

    manifest_bytes = _canonical_json(manifest)
    signature = base64.b64decode(signature_payload["signature"])
    public_bytes = base64.b64decode(signature_payload["public_key"])
    Ed25519PublicKey.from_public_bytes(public_bytes).verify(signature, manifest_bytes)


def _write_approval(project_root: Path, patchset: Dict[str, Any], approver: str, patchset_id: str = None, bundle_sha: str = None) -> Path:
    approval_path = project_root / "approvals" / "patchset_approval.json"
    payload = {
        "schema_version": "1.0.0",
        "patchset_id": patchset_id or patchset.get("patchset_id"),
        "bundle_content_sha256": bundle_sha or patchset.get("target", {}).get("bundle_content_sha256"),
        "approver": approver,
        "approval_reason": "phase5 verifier",
        "approved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "nonce": "phase5-approval-nonce-123456",
    }
    _write_json(approval_path, payload)
    return approval_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ForgeScaffold Phase 5 HITL + signing + rollback")
    parser.add_argument("--project", "-p", default="forgescaffold_phase5_ci")
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

    pipeline_path = dawn_root / "dawn" / "pipelines" / "forgescaffold_apply_v3_hitl_runnable.yaml"

    # HITL gate blocks when approval missing
    approval_file = project_root / "approvals" / "patchset_approval.json"
    if approval_file.exists():
        approval_file.unlink()
    try:
        orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
        raise RuntimeError("Expected HITL gate to block without approval file")
    except Exception as exc:
        if "patchset_approval.json" not in str(exc):
            raise RuntimeError("HITL gate failure did not reference approval path") from exc

    # Load patchset from artifacts
    patchset_path = _get_artifact_path(project_root, "forgescaffold.instrumentation.patchset.json")
    patchset = _load_json(patchset_path)

    # Approval mismatch should fail
    _write_approval(project_root, patchset, approver="mismatch", patchset_id="wrong")
    try:
        orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
        raise RuntimeError("Expected HITL gate to fail on patchset mismatch")
    except Exception:
        pass

    # Correct approval
    _write_approval(project_root, patchset, approver="phase5")
    orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)

    approval_receipt = _load_json(_get_artifact_path(project_root, "forgescaffold.approval_receipt.json"))
    if approval_receipt.get("patchset_id") != patchset.get("patchset_id"):
        raise RuntimeError("Approval receipt patchset_id mismatch")

    evidence_manifest = _load_json(_get_artifact_path(project_root, "forgescaffold.evidence_manifest.json"))
    signature_payload = _load_json(_get_artifact_path(project_root, "forgescaffold.evidence_signature.json"))
    receipt_payload = _load_json(_get_artifact_path(project_root, "forgescaffold.evidence_receipt.json"))

    _verify_signature(evidence_manifest, signature_payload)

    if receipt_payload.get("patchset_id") != patchset.get("patchset_id"):
        raise RuntimeError("Evidence receipt patchset_id mismatch")
    if receipt_payload.get("approver") != approval_receipt.get("approver"):
        raise RuntimeError("Evidence receipt approver mismatch")

    rollback_report = _load_json(_get_artifact_path(project_root, "forgescaffold.rollback_report.json"))
    if rollback_report.get("status") != "PASS":
        raise RuntimeError("Rollback verification did not PASS")

    print("Phase 5 verifier complete: HITL gate, signing, rollback verified")


if __name__ == "__main__":
    main()
