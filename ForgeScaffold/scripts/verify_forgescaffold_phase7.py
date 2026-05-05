import argparse
import base64
import json
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
    (project_root / "inputs" / "idea.md").write_text("forge scaffold phase7")
    (project_root / "src" / "app" / "__init__.py").write_text("")
    (project_root / "src" / "app" / "main.py").write_text("print('hello')\n")


def _ensure_keys(project_root: Path) -> None:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for Phase 7 verifier") from exc

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


def _load_policy(policy_path: Path) -> Dict[str, Any]:
    if not policy_path.exists():
        return {}
    return yaml.safe_load(policy_path.read_text()) or {}


def _risk_requirements(overall_risk: str, rules: Dict[str, Any]) -> Tuple[int, bool]:
    required_approvals = 2 if overall_risk in rules.get("require_two_person_for", []) else 1
    required_risk_ack = overall_risk in rules.get("require_risk_ack_for", [])
    return required_approvals, required_risk_ack


def _write_approval_from_template(project_root: Path, template: Dict[str, Any], approvers: List[str], risk_ack: bool, risk_override: bool = False) -> Path:
    approval_path = project_root / "approvals" / "patchset_approval.json"
    payload = {
        "schema_version": template.get("schema_version", "1.0.0"),
        "patchset_id": template.get("patchset_id"),
        "bundle_content_sha256": template.get("bundle_content_sha256"),
        "review_packet_sha256": template.get("review_packet_sha256"),
        "approval_reason": "phase7 verifier",
        "ticket": "PHASE7-1",
        "risk_ack": risk_ack,
        "risk_override": risk_override,
    }

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if len(approvers) == 1:
        payload.update(
            {
                "approver": approvers[0],
                "approved_at": now,
                "nonce": "phase7-approval-nonce-123456",
            }
        )
    else:
        payload["approvers"] = [
            {"name": approvers[0], "approved_at": now, "nonce": "phase7-approval-nonce-123456"},
            {"name": approvers[1], "approved_at": now, "nonce": "phase7-approval-nonce-abcdef"},
        ]

    _write_json(approval_path, payload)
    return approval_path


def _load_link_run(path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("forgescaffold_gate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load link from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run


def _manual_gate(project_root: Path, patchset: Dict[str, Any], review_packet: Dict[str, Any], approval: Dict[str, Any]) -> None:
    from dawn.runtime.artifact_store import ArtifactStore
    from dawn.runtime.sandbox import Sandbox

    store = ArtifactStore(str(project_root))
    patchset_path = store.write_artifact("manual", "instrumentation.patchset.json", patchset)
    review_path = store.write_artifact("manual", "review_packet.json", review_packet)
    store.register("forgescaffold.instrumentation.patchset.json", str(patchset_path), schema="json", producer_link_id="manual")
    store.register("forgescaffold.review_packet.json", str(review_path), schema="json", producer_link_id="manual")

    approval_path = project_root / "approvals" / "patchset_approval.json"
    _write_json(approval_path, approval)

    sandbox = Sandbox(str(project_root), "forgescaffold.gate_patchset_approval")
    sandbox.artifact_store = store

    gate_run = _load_link_run(project_root.parent.parent / "dawn" / "links" / "forgescaffold.gate_patchset_approval" / "run.py")

    project_context = {
        "project_root": str(project_root),
        "artifact_store": store,
        "sandbox": sandbox,
        "profile": "forgescaffold_apply_lowrisk",
    }
    gate_run(project_context, {})


def _read_index_lines(index_path: Path) -> List[str]:
    if not index_path.exists():
        return []
    return [line for line in index_path.read_text().splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ForgeScaffold Phase 7 risk gating + evidence index")
    parser.add_argument("--project", "-p", default="forgescaffold_phase7_ci")
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

    policy_path = dawn_root / "dawn" / "policy" / "runtime_policy.yaml"
    policy = _load_policy(policy_path)
    risk_rules = policy.get("forgescaffold", {}).get("risk_rules", {})

    pipeline_path = dawn_root / "dawn" / "pipelines" / "forgescaffold_apply_v5_risk_index_runnable.yaml"

    # First run: generate review packet + approval template, expect gate to block
    approval_file = project_root / "approvals" / "patchset_approval.json"
    if approval_file.exists():
        approval_file.unlink()
    try:
        orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
        raise RuntimeError("Expected approval gate to block without approval file")
    except Exception as exc:
        if "patchset_approval.json" not in str(exc):
            raise RuntimeError("Gate failure did not mention approval file") from exc

    patchset = _load_json(_get_artifact_path(project_root, "forgescaffold.instrumentation.patchset.json"))
    review_packet = _load_json(_get_artifact_path(project_root, "forgescaffold.review_packet.json"))
    template = _load_json(_get_artifact_path(project_root, "forgescaffold.approval_template.json"))

    expected_approvals, expected_risk_ack = _risk_requirements(review_packet.get("overall_risk", "medium"), risk_rules)
    if template.get("patchset_id") != patchset.get("patchset_id"):
        raise RuntimeError("Approval template patchset_id mismatch")
    if template.get("bundle_content_sha256") != patchset.get("target", {}).get("bundle_content_sha256"):
        raise RuntimeError("Approval template bundle_content_sha256 mismatch")
    if template.get("review_packet_sha256") != review_packet.get("review_packet_sha256"):
        raise RuntimeError("Approval template review_packet_sha256 mismatch")
    if template.get("required_approvals") != expected_approvals:
        raise RuntimeError("Approval template required_approvals mismatch")
    if template.get("required_risk_ack") != expected_risk_ack:
        raise RuntimeError("Approval template required_risk_ack mismatch")
    if review_packet.get("overall_risk") == "high":
        approvers = template.get("approvers")
        if not isinstance(approvers, list) or len(approvers) != 2:
            raise RuntimeError("High-risk template must include two approver placeholders")

    # High-risk enforcement via direct gate invocation
    high_patchset = {
        "schema_version": "1.0.1",
        "patchset_id": "phase7-high-risk",
        "created_at": "",
        "generator": {"name": "forgescaffold.obs_instrument_patchset", "version": "1.0.0"},
        "target": {"project_id": args.project, "bundle_content_sha256": "deadbeef" * 8},
        "operations": [
            {"op": "delete", "path": "src/app/old_config.py"},
        ],
    }
    high_review = {
        "schema_version": "1.0.0",
        "patchset_id": "phase7-high-risk",
        "bundle_content_sha256": "deadbeef" * 8,
        "review_packet_sha256": "phase7-review-sha",
        "overall_risk": "high",
        "operations": [{"path": "src/app/old_config.py", "op": "delete", "risk": "high", "hunks": []}],
    }

    approval_one = {
        "schema_version": "1.0.0",
        "patchset_id": "phase7-high-risk",
        "bundle_content_sha256": "deadbeef" * 8,
        "review_packet_sha256": "phase7-review-sha",
        "approver": "one",
        "approval_reason": "phase7",
        "approved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "nonce": "phase7-approval-nonce-123456",
        "risk_ack": False,
        "risk_override": True,
    }
    try:
        _manual_gate(project_root, high_patchset, high_review, approval_one)
        raise RuntimeError("Expected high-risk gate to fail with one approver and no risk_ack")
    except Exception:
        pass

    approval_two = {
        "schema_version": "1.0.0",
        "patchset_id": "phase7-high-risk",
        "bundle_content_sha256": "deadbeef" * 8,
        "review_packet_sha256": "phase7-review-sha",
        "approvers": [
            {"name": "one", "approved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "nonce": "phase7-approval-nonce-123456"},
            {"name": "two", "approved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "nonce": "phase7-approval-nonce-abcdef"},
        ],
        "approval_reason": "phase7",
        "risk_ack": True,
        "risk_override": True,
    }
    _manual_gate(project_root, high_patchset, high_review, approval_two)

    # Prepare approval for pipeline run
    _write_approval_from_template(project_root, template, ["phase7"], risk_ack=False, risk_override=False)

    # First pipeline run with untrusted signer should not index
    trusted_path = dawn_root / "dawn" / "policy" / "trusted_signers.yaml"
    _write_json(trusted_path, {"trusted_signers": []})
    index_path = project_root / "evidence" / "evidence_index.jsonl"
    before_lines = _read_index_lines(index_path)
    try:
        orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
    except Exception:
        pass
    after_lines = _read_index_lines(index_path)
    if len(after_lines) != len(before_lines):
        raise RuntimeError("Evidence index should not update on failed verification")

    # Trust signer and run twice to confirm append-only
    signature_payload = _load_json(_get_artifact_path(project_root, "forgescaffold.evidence_signature.json"))
    fingerprint = signature_payload.get("public_key_fingerprint")
    _write_json(trusted_path, {"trusted_signers": [{"fingerprint": fingerprint, "label": "phase7", "revoked": False}]})

    orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
    lines_after_first = _read_index_lines(index_path)

    orchestrator.run_pipeline(args.project, str(pipeline_path), profile=args.profile)
    lines_after_second = _read_index_lines(index_path)

    if len(lines_after_first) == 0:
        raise RuntimeError("Evidence index not created")
    if len(lines_after_second) != len(lines_after_first) + 1:
        raise RuntimeError("Evidence index is not append-only")

    print("Phase 7 verifier complete: template, risk gate, index verified")


if __name__ == "__main__":
    main()
