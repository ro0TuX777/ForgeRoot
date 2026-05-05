import base64
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

COMMON_DIR = Path(__file__).resolve().parents[1] / "forgescaffold_common"
import sys
sys.path.append(str(COMMON_DIR))

from index_utils import canonical_json, index_file_sha256, load_index, policy_snapshot_hash  # noqa: E402


def _load_policy(repo_root: Path) -> Dict[str, Any]:
    policy_path = repo_root / "dawn" / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        return {}
    return yaml.safe_load(policy_path.read_text()) or {}


def _load_trusted_signers(repo_root: Path) -> List[Dict[str, Any]]:
    policy_path = repo_root / "dawn" / "policy" / "trusted_signers.yaml"
    if not policy_path.exists():
        return []
    payload = yaml.safe_load(policy_path.read_text()) or {}
    return payload.get("trusted_signers", []) or []


def _trusted_policy_hash(policy: Dict[str, Any], trusted: List[Dict[str, Any]]) -> str:
    payload = {
        "trusted_signers": trusted,
        "min_signatures_by_risk": policy.get("forgescaffold", {}).get("min_signatures_by_risk"),
    }
    return policy_snapshot_hash({"forgescaffold": payload})


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _latest_checkpoint(checkpoints_dir: Path) -> Optional[Path]:
    if not checkpoints_dir.exists():
        return None
    files = [p for p in checkpoints_dir.glob("checkpoint_*.json") if not p.name.endswith(".signature.json")]
    return sorted(files)[-1] if files else None


def _cache_meta(cache_path: Path) -> Optional[Dict[str, Any]]:
    if not cache_path.exists():
        return None
    conn = sqlite3.connect(str(cache_path))
    try:
        cur = conn.execute(
            "SELECT schema_version, source_index_sha256, source_entry_count, source_last_entry_hash, "
            "checkpoint_last_entry_hash, checkpoint_path, checkpoint_timestamp FROM cache_meta LIMIT 1"
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    if row[0] not in {"1.0.0", "1.0.1", "1.0.2"}:
        return None
    return {
        "schema_version": row[0],
        "source_index_sha256": row[1],
        "source_entry_count": row[2],
        "source_last_entry_hash": row[3],
        "checkpoint_last_entry_hash": row[4],
        "checkpoint_path": row[5],
        "checkpoint_timestamp": row[6],
    }


def _load_private_keys(repo_root: Path, project_root: Path) -> List[Tuple[bytes, Any]]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for catalog signing") from exc

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

    def _load_private_key_from_text(key_text: str) -> Tuple[bytes, Any]:
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

    return [_load_private_key_from_text(key_text) for key_text in keys]


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    repo_root = Path(__file__).resolve().parents[3]
    if not sandbox:
        raise RuntimeError("Sandbox missing")

    policy = _load_policy(repo_root)
    global_policy = policy.get("forgescaffold", {}).get("global_catalog", {})
    if not global_policy.get("enabled", False):
        raise RuntimeError("GLOBAL_CATALOG_DISABLED")

    config = link_config.get("config", {}) if isinstance(link_config, dict) else {}
    allowlist = config.get("projects") or global_policy.get("projects_allowlist") or []
    if not allowlist:
        raise RuntimeError("GLOBAL_CATALOG_ALLOWLIST_EMPTY")

    write_root = global_policy.get("write_root", "evidence/global")
    write_dir = repo_root / write_root
    write_dir.mkdir(parents=True, exist_ok=True)

    trusted = _load_trusted_signers(repo_root)
    trusted_hash = _trusted_policy_hash(policy, trusted)

    projects = []
    timestamps: List[datetime] = []

    for project in sorted(allowlist):
        proj_root = repo_root / "projects" / project
        index_path = proj_root / "evidence" / "evidence_index.jsonl"
        entries = load_index(index_path)
        entry_count = len(entries)
        last_entry_hash = entries[-1].get("entry_hash") if entries else None
        index_sha = index_file_sha256(index_path)
        for entry in entries:
            if entry.get("timestamp"):
                try:
                    timestamps.append(_parse_datetime(entry.get("timestamp")))
                except Exception:
                    pass

        cache_path = proj_root / "evidence" / "cache" / "evidence_index_cache.sqlite"
        cache_meta = _cache_meta(cache_path)
        cache_uptodate = False
        cache_source_index_sha256 = None
        cache_source_last_entry_hash = None
        if cache_meta:
            cache_source_index_sha256 = cache_meta.get("source_index_sha256")
            cache_source_last_entry_hash = cache_meta.get("source_last_entry_hash")
            cache_uptodate = (
                cache_source_index_sha256 == index_sha
                and cache_source_last_entry_hash == last_entry_hash
                and int(cache_meta.get("source_entry_count") or 0) == entry_count
            )

        checkpoints_dir = proj_root / "evidence" / "checkpoints"
        latest_checkpoint = _latest_checkpoint(checkpoints_dir)
        latest_checkpoint_last_entry_hash = None
        latest_checkpoint_path = None
        if latest_checkpoint:
            latest_checkpoint_path = str(latest_checkpoint)
            try:
                payload = json.loads(latest_checkpoint.read_text())
                latest_checkpoint_last_entry_hash = payload.get("last_entry_hash")
            except Exception:
                latest_checkpoint_last_entry_hash = None

        projects.append(
            {
                "project": project,
                "index_path": str(index_path),
                "index_sha256": index_sha,
                "entry_count": entry_count,
                "last_entry_hash": last_entry_hash,
                "cache_path": str(cache_path) if cache_path.exists() else None,
                "cache_source_index_sha256": cache_source_index_sha256,
                "cache_source_last_entry_hash": cache_source_last_entry_hash,
                "cache_uptodate": cache_uptodate,
                "latest_checkpoint_path": latest_checkpoint_path,
                "latest_checkpoint_last_entry_hash": latest_checkpoint_last_entry_hash,
                "trusted_signer_policy_hash": trusted_hash,
            }
        )

    built_at = "1970-01-01T00:00:00Z"
    if timestamps:
        built_at = max(timestamps).isoformat().replace("+00:00", "Z")

    catalog = {
        "schema_version": "1.0.0",
        "built_at": built_at,
        "projects": projects,
    }

    catalog_path = write_dir / "catalog.json"
    catalog_path.write_text(canonical_json(catalog))

    outputs: Dict[str, Dict[str, str]] = {
        "forgescaffold.global_catalog.json": {"path": str(catalog_path)}
    }

    if global_policy.get("sign_catalog", False):
        catalog_bytes = canonical_json(catalog).encode("utf-8")
        catalog_hash = _sha256_bytes(catalog_bytes)
        keys = _load_private_keys(repo_root, project_root)
        signatures = []
        for public_bytes, private_key in keys:
            signature = private_key.sign(catalog_bytes)
            signatures.append(
                {
                    "fingerprint": _sha256_bytes(public_bytes),
                    "alg": "ed25519",
                    "sig": base64.b64encode(signature).decode(),
                    "public_key": base64.b64encode(public_bytes).decode(),
                    "signed_at": datetime.utcnow().isoformat() + "Z",
                }
            )
        signature_payload = {
            "schema_version": "1.1.0",
            "algorithm": "ed25519",
            "manifest_hash": catalog_hash,
            "manifest_sha256": catalog_hash,
            "signatures": signatures,
        }
        signature_path = write_dir / "catalog.signature.json"
        signature_path.write_text(json.dumps(signature_payload, sort_keys=True, separators=(",", ":")))
        outputs["forgescaffold.global_catalog.signature.json"] = {"path": str(signature_path)}

    return {
        "status": "SUCCEEDED",
        "outputs": outputs,
        "metrics": {"projects": len(projects)},
    }
