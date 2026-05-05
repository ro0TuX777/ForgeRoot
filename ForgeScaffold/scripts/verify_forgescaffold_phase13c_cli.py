import argparse
import base64
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(payload, fh, sort_keys=True, separators=(",", ":"))


def _bootstrap_project(root: Path) -> None:
    (root / "inputs").mkdir(parents=True, exist_ok=True)
    (root / "src" / "app").mkdir(parents=True, exist_ok=True)
    (root / "approvals").mkdir(parents=True, exist_ok=True)
    (root / "keys").mkdir(parents=True, exist_ok=True)
    (root / "inputs" / "idea.md").write_text("phase13c")
    (root / "src" / "app" / "__init__.py").write_text("")
    (root / "src" / "app" / "main.py").write_text("print('hello')\n")


def _ensure_signer_keys(project_root: Path, count: int = 2) -> None:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for Phase 13C verifier") from exc

    signers_dir = project_root / "keys" / "signers"
    signers_dir.mkdir(parents=True, exist_ok=True)
    existing = [p for p in signers_dir.iterdir() if p.is_file()]

    while len(existing) < count:
        private_key = ed25519.Ed25519PrivateKey.generate()
        raw = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_text = f"base64:{base64.b64encode(raw).decode()}"
        path = signers_dir / f"signer_{len(existing)+1}.key"
        path.write_text(key_text)
        existing.append(path)


def _fingerprint_for_key(key_text: str) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    if key_text.startswith("base64:"):
        raw = base64.b64decode(key_text.split(":", 1)[1])
    else:
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


def _write_trusted_signers(path: Path, entries: list) -> None:
    _write_json(path, {"trusted_signers": entries})


def _run_cli(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "scripts/forgescaffold_cli.py", *args], cwd=str(cwd), capture_output=True, text=True)


def _latest_file(path: Path) -> Path:
    files = list(path.glob("*.json"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ForgeScaffold Phase 13C CLI")
    parser.add_argument("--project", default="forgescaffold_phase13c_ci")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--profile", default="forgescaffold_apply_lowrisk")
    args = parser.parse_args()

    dawn_root = Path(__file__).resolve().parents[1]
    project_root = dawn_root / "projects" / args.project
    if not project_root.exists():
        if not args.bootstrap:
            raise RuntimeError("Project missing and --bootstrap not set")
        _bootstrap_project(project_root)

    _bootstrap_project(project_root)
    signers_dir = project_root / "keys" / "signers"
    if signers_dir.exists():
        for item in signers_dir.iterdir():
            if item.is_file():
                item.unlink()
    _ensure_signer_keys(project_root, count=2)
    signer_keys = [p.read_text().strip() for p in (project_root / "keys" / "signers").iterdir()]
    os.environ["FORGESCAFFOLD_SIGNING_KEYS"] = ",".join(signer_keys)

    trusted_path = dawn_root / "dawn" / "policy" / "trusted_signers.yaml"
    original_trusted = trusted_path.read_text() if trusted_path.exists() else None

    try:
        fingerprints = [_fingerprint_for_key(key) for key in signer_keys]
        _write_trusted_signers(
            trusted_path,
            [
                {
                    "fingerprint": fp,
                    "label": f"cli-signer-{idx+1}",
                    "scopes": {"projects": [args.project], "pipelines": ["forgescaffold_apply_v9_cache_runnable"]},
                    "expires_at": "2030-01-01T00:00:00Z",
                    "revoked": False,
                }
                for idx, fp in enumerate(fingerprints)
            ],
        )
        approval_file = project_root / "approvals" / "patchset_approval.json"
        if approval_file.exists():
            approval_file.unlink()
        used_file = project_root / "approvals" / "used_approvals.jsonl"
        if used_file.exists():
            used_file.unlink()
        evidence_dir = project_root / "evidence"
        if evidence_dir.exists():
            for item in evidence_dir.rglob("*"):
                if item.is_file():
                    item.unlink()
            for item in sorted(evidence_dir.rglob("*"), reverse=True):
                if item.is_dir():
                    item.rmdir()

        lock_path = project_root / ".locks" / "forgescaffold_apply.lock"
        if lock_path.exists():
            lock_path.unlink()

        # status --json
        proc = _run_cli(["status", "--project", args.project, "--profile", args.profile, "--json"], dawn_root)
        if proc.returncode != 0:
            raise RuntimeError("status command failed")
        status_path = project_root / "artifacts" / "forgescaffold.status" / "status.json"
        if not status_path.exists():
            raise RuntimeError("status.json missing")
        try:
            stdout_payload = json.loads(proc.stdout.strip())
            status_payload = json.loads(status_path.read_text())
        except Exception:
            raise RuntimeError("status --json output mismatch")
        if stdout_payload != status_payload:
            raise RuntimeError("status --json output mismatch")

        # apply should block and generate approval template
        proc = _run_cli(["apply", "--project", args.project, "--profile", args.profile, "--mode", "runnable_only"], dawn_root)
        if proc.returncode not in {31, 32}:
            raise RuntimeError("apply did not block as expected")

        template_path = project_root / "artifacts" / "forgescaffold.generate_approval_template" / "approval_template.json"
        if not template_path.exists():
            raise RuntimeError("approval template not generated")

        # approve
        proc = _run_cli(
            [
                "approve",
                "--project",
                args.project,
                "--profile",
                args.profile,
                "--approval",
                str(template_path),
                "--approver",
                "cli-approver",
                "--reason",
                "phase13c",
                "--yes",
            ],
            dawn_root,
        )
        if proc.returncode != 0:
            raise RuntimeError("approve failed")

        approval_receipt = project_root / "approvals" / "patchset_approval.json"
        if not approval_receipt.exists():
            raise RuntimeError("approval receipt missing")

        used_file = project_root / "approvals" / "used_approvals.jsonl"
        if used_file.exists():
            used_file.unlink()

        # apply runnable
        proc = _run_cli(
            ["apply", "--project", args.project, "--profile", args.profile, "--mode", "runnable_only", "--yes"],
            dawn_root,
        )
        if proc.returncode not in {0, 10}:
            raise RuntimeError("apply runnable failed")

        apply_summary = project_root / "artifacts" / "forgescaffold.cli" / "apply_summary.json"
        if not apply_summary.exists():
            raise RuntimeError("apply_summary.json missing")
        summary_payload = json.loads(apply_summary.read_text())
        if not summary_payload.get("entry_hash"):
            raise RuntimeError("apply_summary missing entry_hash")

        # lock held scenario
        lock_dir = project_root / ".locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / "forgescaffold_apply.lock"
        lock_payload = {
            "pid": 123,
            "hostname": "local",
            "started_at": _now_iso(),
            "pipeline_name": "cli_test",
            "patchset_id": "test",
        }
        _write_json(lock_path, lock_payload)

        proc = _run_cli(["apply", "--project", args.project, "--profile", args.profile, "--mode", "runnable_only"], dawn_root)
        if proc.returncode != 32:
            raise RuntimeError("lock held not detected")

        # explain --last
        proc = _run_cli(["explain", "--project", args.project, "--profile", args.profile, "--last"], dawn_root)
        if proc.returncode != 0:
            raise RuntimeError("explain failed")
        explain_path = project_root / "artifacts" / "forgescaffold.cli" / "explain.json"
        if not explain_path.exists():
            raise RuntimeError("explain.json missing")
        explain_payload = json.loads(explain_path.read_text())
        if explain_payload.get("code") != "LOCK_HELD":
            raise RuntimeError("explain did not target lock")

        lock_path.unlink(missing_ok=True)

        # query
        proc = _run_cli(["query", "--project", args.project, "--profile", args.profile, "--limit", "5"], dawn_root)
        if proc.returncode != 0:
            raise RuntimeError("query failed")
        query_path = project_root / "artifacts" / "forgescaffold.cli" / "query_results.json"
        if not query_path.exists():
            raise RuntimeError("query_results.json missing")
        query_payload = json.loads(query_path.read_text())
        if not query_payload.get("query_backend"):
            raise RuntimeError("query backend missing")

        # doctor
        proc = _run_cli(["doctor", "--project", args.project, "--profile", args.profile], dawn_root)
        if proc.returncode not in {0, 10}:
            raise RuntimeError("doctor failed")
        doctor_path = project_root / "artifacts" / "forgescaffold.cli" / "doctor_report.json"
        if not doctor_path.exists():
            raise RuntimeError("doctor_report.json missing")

        print("Phase 13C verifier complete: cli apply/approve/status/query/explain/doctor verified")
    finally:
        if original_trusted is None:
            if trusted_path.exists():
                trusted_path.unlink()
        else:
            trusted_path.write_text(original_trusted)


if __name__ == "__main__":
    main()
