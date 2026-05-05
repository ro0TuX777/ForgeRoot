import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load_artifact(artifact_store, artifact_id: str) -> Dict[str, Any]:
    meta = artifact_store.get(artifact_id)
    if not meta:
        raise RuntimeError(f"Missing required artifact: {artifact_id}")
    with open(meta["path"], "r") as fh:
        return json.load(fh)


def _canonical_json(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_private_key_from_text(key_text: str) -> Tuple[bytes, Any]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for evidence signing") from exc

    if not key_text:
        raise RuntimeError("Signing key missing. Set FORGESCAFFOLD_SIGNING_KEY or projects/<project>/keys/ed25519_private.key")

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


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    artifact_store = project_context.get("artifact_store")
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not artifact_store or not sandbox:
        raise RuntimeError("Sandbox or artifact store missing")

    manifest = _load_artifact(artifact_store, "forgescaffold.evidence_manifest.json")
    approval = _load_artifact(artifact_store, "forgescaffold.approval_receipt.json")

    manifest_bytes = _canonical_json(manifest)
    manifest_sha = _sha256_bytes(manifest_bytes)
    approval_sha = _sha256_bytes(_canonical_json(approval))

    keys = _load_private_keys(project_root)

    signatures = []
    for public_bytes, private_key in keys:
        signature = private_key.sign(manifest_bytes)
        signature_b64 = base64.b64encode(signature).decode()
        public_b64 = base64.b64encode(public_bytes).decode()
        public_fingerprint = _sha256_bytes(public_bytes)
        signatures.append(
            {
                "fingerprint": public_fingerprint,
                "alg": "ed25519",
                "sig": signature_b64,
                "public_key": public_b64,
                "signed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )

    signature_payload = {
        "schema_version": "1.1.0",
        "algorithm": "ed25519",
        "manifest_hash": manifest_sha,
        "manifest_sha256": manifest_sha,
        "signatures": signatures,
    }

    if len(signatures) == 1:
        signature_payload["public_key"] = signatures[0]["public_key"]
        signature_payload["public_key_fingerprint"] = signatures[0]["fingerprint"]
        signature_payload["signature"] = signatures[0]["sig"]

    receipt_payload = {
        "schema_version": "1.0.0",
        "manifest_sha256": manifest_sha,
        "patchset_id": approval.get("patchset_id"),
        "approver": approval.get("approver"),
        "approval_receipt_sha256": approval_sha,
        "public_key_fingerprint": signatures[0]["fingerprint"],
        "signature": signatures[0]["sig"],
        "signature_algorithm": "ed25519",
    }

    signature_path = sandbox.publish(
        "forgescaffold.evidence_signature.json",
        "evidence_signature.json",
        signature_payload,
        schema="json",
    )
    receipt_path = sandbox.publish(
        "forgescaffold.evidence_receipt.json",
        "evidence_receipt.json",
        receipt_payload,
        schema="json",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {
            "forgescaffold.evidence_signature.json": {"path": signature_path},
            "forgescaffold.evidence_receipt.json": {"path": receipt_path},
        },
        "metrics": {"manifest_sha256": manifest_sha},
    }
