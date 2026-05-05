import json
from pathlib import Path
from typing import Dict, List, Tuple

from .canonicalize import canonical_json
from .signing import load_ed25519_private_key, load_ed25519_public_key, sha256_hex, sign_bytes, verify_bytes


class BundleSignatureError(Exception):
    def __init__(self, message: str, code: str = "invalid") -> None:
        super().__init__(message)
        self.code = code


EXCLUDE_DIRS = {"signatures", ".git", "__pycache__"}
EXCLUDE_NAMES = {".DS_Store"}
EXCLUDE_SUFFIXES = {".pyc", ".log"}


def _iter_bundle_files(bundle_path: Path) -> List[Path]:
    files: List[Path] = []
    for path in bundle_path.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(bundle_path)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if rel.name in EXCLUDE_NAMES:
            continue
        if rel.suffix in EXCLUDE_SUFFIXES:
            continue
        files.append(path)
    return sorted(files, key=lambda p: str(p.relative_to(bundle_path)))


def build_manifest(bundle_path: str) -> Dict[str, object]:
    root = Path(bundle_path)
    files = []
    for path in _iter_bundle_files(root):
        rel = str(path.relative_to(root))
        data = path.read_bytes()
        digest = sha256_hex(data)
        files.append({"path": rel, "sha256": digest, "size_bytes": len(data)})
    manifest = {"schema_version": "0.1", "bundle_root": "IntentBundle", "files": files}
    return manifest


def write_manifest(bundle_path: str) -> Tuple[str, bytes, Path]:
    root = Path(bundle_path)
    manifest = build_manifest(bundle_path)
    canonical = canonical_json(manifest).encode("utf-8")
    manifest_hash = sha256_hex(canonical)
    sig_dir = root / "signatures"
    sig_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = sig_dir / "bundle.manifest.json"
    manifest_path.write_text(canonical.decode("utf-8"))
    return manifest_hash, canonical, manifest_path


def sign_bundle(bundle_path: str, key_path: str) -> Path:
    manifest_hash, canonical, _ = write_manifest(bundle_path)
    private_key = load_ed25519_private_key(key_path)
    signature = sign_bytes(private_key, canonical)
    sig_path = Path(bundle_path) / "signatures" / "bundle.sig.json"
    payload = {
        "schema_version": "0.1",
        "alg": "ed25519",
        "manifest_sha256": manifest_hash,
        "signature_b64": signature,
    }
    sig_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return sig_path


def verify_bundle(bundle_path: str, pubkey_path: str) -> Dict[str, object]:
    root = Path(bundle_path)
    manifest_path = root / "signatures" / "bundle.manifest.json"
    sig_path = root / "signatures" / "bundle.sig.json"

    if not sig_path.exists():
        raise BundleSignatureError("bundle.sig.json missing", code="missing")
    if not manifest_path.exists():
        raise BundleSignatureError("bundle.manifest.json missing", code="missing")

    manifest = json.loads(manifest_path.read_text())
    canonical_manifest = canonical_json(manifest).encode("utf-8")
    expected_manifest = build_manifest(bundle_path)
    canonical_expected = canonical_json(expected_manifest).encode("utf-8")

    if canonical_manifest != canonical_expected:
        expected_map = {f["path"]: f for f in expected_manifest.get("files", [])}
        stored_map = {f["path"]: f for f in manifest.get("files", []) if isinstance(f, dict)}
        mismatch = None
        for path, item in expected_map.items():
            stored = stored_map.get(path)
            if not stored:
                mismatch = f"missing file: {path}"
                break
            if stored.get("sha256") != item.get("sha256"):
                mismatch = f"hash mismatch: {path}"
                break
            if stored.get("size_bytes") != item.get("size_bytes"):
                mismatch = f"size mismatch: {path}"
                break
        if mismatch is None and stored_map.keys() != expected_map.keys():
            extra = next(iter(set(stored_map.keys()) - set(expected_map.keys())), None)
            mismatch = f"unexpected file: {extra}" if extra else "file list mismatch"
        raise BundleSignatureError(mismatch or "manifest mismatch")

    sig_payload = json.loads(sig_path.read_text())
    manifest_hash = sha256_hex(canonical_manifest)
    if sig_payload.get("manifest_sha256") != manifest_hash:
        raise BundleSignatureError("manifest hash mismatch")

    public_key = load_ed25519_public_key(pubkey_path)
    signature = sig_payload.get("signature_b64", "")
    if not verify_bytes(public_key, canonical_manifest, signature):
        raise BundleSignatureError("signature invalid")

    return {"status": "PASS", "manifest_sha256": manifest_hash, "signature": signature}
