import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


def _canonical_json(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _load_policy(project_root: Path) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    policy_path = repo_root / "dawn" / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        policy_path = project_root / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        return {}
    return yaml.safe_load(policy_path.read_text()) or {}


def _resolve_checkpoint_dir(project_root: Path, index_policy: Dict[str, Any]) -> Path:
    root_value = index_policy.get("checkpoint_write_root", "evidence/checkpoints")
    path = Path(root_value)
    if path.is_absolute():
        return path
    repo_root = Path(__file__).resolve().parents[3]
    if str(root_value).startswith("projects/"):
        return repo_root / path
    return project_root / path


def _load_private_key_from_text(key_text: str) -> Tuple[bytes, Any]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for checkpoint signing") from exc

    if not key_text:
        raise RuntimeError("Signing key missing. Set FORGESCAFFOLD_SIGNING_KEY(S) or provide projects/<project>/keys.")

    if "BEGIN" in key_text:
        private_key = serialization.load_pem_private_key(key_text.encode(), password=None)
    else:
        if key_text.startswith("base64:"):
            raw = base64.b64decode(key_text.split(":", 1)[1])
        elif key_text.startswith("hex:"):
            raw = bytes.fromhex(key_text.split(":", 1)[1])
        else:
            raw = base64.b64decode(key_text)
        if len(raw) == 64:
            raw = raw[:32]
        if len(raw) != 32:
            raise RuntimeError("Ed25519 private key must be 32 bytes")
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(raw)

    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return public_bytes, private_key


def _load_private_keys(project_root: Path) -> List[Tuple[bytes, Any]]:
    keys: List[str] = []
    env_multi = os.environ.get("FORGESCAFFOLD_SIGNING_KEYS")
    if env_multi:
        keys = [item.strip() for item in env_multi.split(",") if item.strip()]
    else:
        env_single = os.environ.get("FORGESCAFFOLD_SIGNING_KEY")
        if env_single:
            keys = [env_single.strip()]

    if not keys:
        signers_dir = project_root / "keys" / "signers"
        if signers_dir.exists():
            for path in sorted(signers_dir.iterdir()):
                if path.is_file():
                    keys.append(path.read_text().strip())

    if not keys:
        key_path = project_root / "keys" / "ed25519_private.key"
        if key_path.exists():
            keys = [key_path.read_text().strip()]

    if not keys:
        raise RuntimeError("Signing key missing. Set FORGESCAFFOLD_SIGNING_KEY(S) or provide projects/<project>/keys.")

    return [_load_private_key_from_text(key_text) for key_text in keys]


def _policy_snapshot_hash(policy: Dict[str, Any]) -> str:
    forgescaffold = policy.get("forgescaffold", {}) if isinstance(policy, dict) else {}
    snapshot = {
        "risk_rules": forgescaffold.get("risk_rules"),
        "min_signatures_by_risk": forgescaffold.get("min_signatures_by_risk"),
        "retention": forgescaffold.get("retention"),
        "lock_ttl_minutes": forgescaffold.get("lock_ttl_minutes"),
        "index_integrity": forgescaffold.get("index_integrity"),
    }
    return _sha256_bytes(_canonical_json(snapshot))


def _load_index_lines(index_path: Path) -> List[str]:
    if not index_path.exists():
        return []
    return [line for line in index_path.read_text().splitlines() if line.strip()]


def _latest_checkpoint(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    files = [p for p in path.glob("checkpoint_*.json") if not p.name.endswith(".signature.json")]
    files = sorted(files)
    return files[-1] if files else None


def _should_emit_checkpoint(
    entry_count: int,
    latest_checkpoint: Optional[Path],
    index_policy: Dict[str, Any],
) -> Tuple[bool, str]:
    if entry_count <= 0:
        return False, "no_entries"

    min_interval = int(index_policy.get("checkpoint_min_interval_seconds", 0) or 0)
    every_n = index_policy.get("checkpoint_every_n_entries")
    try:
        every_n = int(every_n) if every_n is not None else None
    except (TypeError, ValueError):
        every_n = None

    every_n_ok = False
    if every_n and every_n > 0:
        every_n_ok = (entry_count % every_n) == 0

    interval_ok = True
    if latest_checkpoint and min_interval > 0:
        latest_payload = json.loads(latest_checkpoint.read_text())
        created_at = latest_payload.get("created_at")
        if created_at:
            last_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            interval_ok = (datetime.now(timezone.utc) - last_dt).total_seconds() >= min_interval

    if every_n_ok:
        return True, "emitted_every_n"
    if interval_ok:
        return True, "emitted_min_interval"
    return False, "cadence_blocked"


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not sandbox:
        raise RuntimeError("Sandbox missing")

    policy = _load_policy(project_root)
    index_policy = policy.get("forgescaffold", {}).get("index_integrity", {})
    if not index_policy.get("checkpoint_enabled", False):
        return {
            "status": "SUCCEEDED",
            "outputs": {},
            "metrics": {"checkpoint_emitted": False, "reason": "disabled"},
        }

    if index_policy.get("checkpoint_on_success_only", True):
        report_meta = project_context.get("artifact_store", {}).get("forgescaffold.evidence_verification_report.json")
        if report_meta:
            report = json.loads(Path(report_meta["path"]).read_text())
            if report.get("status") != "PASS":
                return {
                    "status": "SUCCEEDED",
                    "outputs": {},
                    "metrics": {"checkpoint_emitted": False, "reason": "skipped_not_pass"},
                }

    checkpoint_dir = _resolve_checkpoint_dir(project_root, index_policy)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    index_path = project_root / "evidence" / "evidence_index.jsonl"
    lines = _load_index_lines(index_path)
    entry_count = len(lines)
    last_entry_hash = None
    if lines:
        last = json.loads(lines[-1])
        last_entry_hash = last.get("entry_hash")

    latest = _latest_checkpoint(checkpoint_dir)
    should_emit, reason = _should_emit_checkpoint(entry_count, latest, index_policy)
    if not should_emit:
        return {
            "status": "SUCCEEDED",
            "outputs": {},
            "metrics": {"checkpoint_emitted": False, "reason": reason},
        }

    checkpoint = {
        "schema_version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "project": project_context.get("project_id"),
        "pipeline_name": project_context.get("pipeline_id"),
        "index_path": str(index_path),
        "entry_count": entry_count,
        "last_entry_hash": last_entry_hash,
        "index_file_sha256": _sha256_bytes(index_path.read_bytes()) if index_path.exists() else _sha256_bytes(b""),
        "policy_snapshot_hash": _policy_snapshot_hash(policy),
        "emit_reason": reason,
    }

    checkpoint_bytes = _canonical_json(checkpoint)
    checkpoint_hash = _sha256_bytes(checkpoint_bytes)

    keys = _load_private_keys(project_root)
    signatures = []
    for public_bytes, private_key in keys:
        signature = private_key.sign(checkpoint_bytes)
        signatures.append(
            {
                "fingerprint": _sha256_bytes(public_bytes),
                "alg": "ed25519",
                "sig": base64.b64encode(signature).decode(),
                "public_key": base64.b64encode(public_bytes).decode(),
                "signed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )

    signature_payload = {
        "schema_version": "1.1.0",
        "algorithm": "ed25519",
        "manifest_hash": checkpoint_hash,
        "manifest_sha256": checkpoint_hash,
        "signatures": signatures,
    }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    checkpoint_name = f"checkpoint_{timestamp}.json"
    signature_name = f"checkpoint_{timestamp}.signature.json"

    checkpoint_path = checkpoint_dir / checkpoint_name
    signature_path = checkpoint_dir / signature_name
    checkpoint_path.write_text(checkpoint_bytes.decode("utf-8"))
    signature_path.write_text(json.dumps(signature_payload, sort_keys=True, separators=(",", ":")))

    return {
        "status": "SUCCEEDED",
        "outputs": {
            "forgescaffold.index_checkpoint.json": {"path": str(checkpoint_path)},
            "forgescaffold.index_checkpoint.signature.json": {"path": str(signature_path)},
        },
        "metrics": {
            "entry_count": entry_count,
            "checkpoint_hash": checkpoint_hash,
            "checkpoint_emitted": True,
            "reason": reason,
        },
    }
