import base64
import hashlib
from pathlib import Path
from typing import Tuple


class SigningError(Exception):
    pass


class CryptoUnavailableError(SigningError):
    pass


def _require_crypto():
    try:
        from cryptography.hazmat.primitives import serialization  # noqa: F401
        from cryptography.hazmat.primitives.asymmetric import ed25519  # noqa: F401
    except ModuleNotFoundError as exc:
        raise CryptoUnavailableError("cryptography not installed; install with pip install -e '.[crypto]'") from exc


def _load_key_bytes(path: str) -> bytes:
    raw = Path(path).read_bytes().strip()
    if raw.startswith(b"-----BEGIN"):
        return raw
    text = raw.decode("utf-8", errors="ignore").strip()
    if text.startswith("base64:"):
        text = text.split(":", 1)[1]
    try:
        return base64.b64decode(text)
    except Exception as exc:
        raise SigningError("invalid key encoding") from exc


def load_ed25519_private_key(path: str):
    _require_crypto()
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    key_bytes = _load_key_bytes(path)
    if key_bytes.startswith(b"-----BEGIN"):
        key = serialization.load_pem_private_key(key_bytes, password=None)
        if not isinstance(key, ed25519.Ed25519PrivateKey):
            raise SigningError("invalid ed25519 private key")
        return key
    if len(key_bytes) == 64:
        key_bytes = key_bytes[:32]
    if len(key_bytes) != 32:
        raise SigningError("invalid ed25519 private key length")
    return ed25519.Ed25519PrivateKey.from_private_bytes(key_bytes)


def load_ed25519_public_key(path: str):
    _require_crypto()
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    key_bytes = _load_key_bytes(path)
    if key_bytes.startswith(b"-----BEGIN"):
        key = serialization.load_pem_public_key(key_bytes)
        if not isinstance(key, ed25519.Ed25519PublicKey):
            raise SigningError("invalid ed25519 public key")
        return key
    if len(key_bytes) != 32:
        raise SigningError("invalid ed25519 public key length")
    return ed25519.Ed25519PublicKey.from_public_bytes(key_bytes)


def sign_bytes(private_key, payload: bytes) -> str:
    signature = private_key.sign(payload)
    return base64.b64encode(signature).decode()


def verify_bytes(public_key, payload: bytes, signature_b64: str) -> bool:
    try:
        signature = base64.b64decode(signature_b64)
        public_key.verify(signature, payload)
        return True
    except Exception:
        return False


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint_public_key(public_key) -> str:
    _require_crypto()
    from cryptography.hazmat.primitives import serialization

    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return sha256_hex(public_bytes)
