import base64
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

COMMON_DIR = Path(__file__).resolve().parents[1] / "forgescaffold_common"
import sys
sys.path.append(str(COMMON_DIR))

from index_utils import canonical_json, policy_snapshot_hash  # noqa: E402


def _load_policy(project_root: Path) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    policy_path = repo_root / "dawn" / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        policy_path = project_root / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        return {}
    return yaml.safe_load(policy_path.read_text()) or {}


def _load_private_key_from_text(key_text: str) -> Tuple[bytes, Any]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for summary signing") from exc

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


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _read_cache_meta(cache_path: Path) -> Optional[Dict[str, Any]]:
    if not cache_path.exists():
        return None
    conn = sqlite3.connect(str(cache_path))
    try:
        cur = conn.execute(
            "SELECT schema_version, built_at, source_index_sha256, source_entry_count, source_last_entry_hash, "
            "checkpoint_last_entry_hash, policy_snapshot_hash FROM cache_meta LIMIT 1"
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "schema_version": row[0],
        "built_at": row[1],
        "source_index_sha256": row[2],
        "source_entry_count": row[3],
        "source_last_entry_hash": row[4],
        "checkpoint_last_entry_hash": row[5],
        "policy_snapshot_hash": row[6],
    }


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not sandbox:
        raise RuntimeError("Sandbox missing")

    cache_path = project_root / "evidence" / "cache" / "evidence_index_cache.sqlite"
    meta = _read_cache_meta(cache_path)
    if not meta:
        return {"status": "SUCCEEDED", "outputs": {}, "metrics": {"summary": "skipped_no_cache"}}

    policy = _load_policy(project_root)
    policy_hash = policy_snapshot_hash(policy)

    summary = {
        "schema_version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_index_sha256": meta.get("source_index_sha256"),
        "source_last_entry_hash": meta.get("source_last_entry_hash"),
        "source_entry_count": meta.get("source_entry_count"),
        "cache_path": str(cache_path),
        "cache_meta_sha256": _sha256_bytes(canonical_json(meta).encode("utf-8")),
        "policy_snapshot_hash": meta.get("policy_snapshot_hash") or policy_hash,
    }

    summary_bytes = canonical_json(summary).encode("utf-8")
    summary_hash = _sha256_bytes(summary_bytes)

    keys = _load_private_keys(project_root)
    signatures = []
    for public_bytes, private_key in keys:
        signature = private_key.sign(summary_bytes)
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
        "manifest_hash": summary_hash,
        "manifest_sha256": summary_hash,
        "signatures": signatures,
    }

    summary_dir = project_root / "evidence" / "compaction"
    summary_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary_path = summary_dir / f"summary_{timestamp}.json"
    signature_path = summary_dir / f"summary_{timestamp}.signature.json"
    summary_path.write_text(summary_bytes.decode("utf-8"))
    signature_path.write_text(json.dumps(signature_payload, sort_keys=True, separators=(",", ":")))

    return {
        "status": "SUCCEEDED",
        "outputs": {
            "forgescaffold.compaction_summary.json": {"path": str(summary_path)},
            "forgescaffold.compaction_summary.signature.json": {"path": str(signature_path)},
        },
        "metrics": {"summary_hash": summary_hash},
    }
