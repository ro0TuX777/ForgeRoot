from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_SIGNING_ALGORITHM = "HMAC-SHA256"


@dataclass
class KeyMaterial:
    key_id: str
    algorithm: str
    secret: bytes
    created_at: str | None = None
    expires_at: str | None = None

    def __post_init__(self) -> None:
        if self.algorithm != SUPPORTED_SIGNING_ALGORITHM:
            raise ValueError(f"unsupported signing algorithm: {self.algorithm}")
        if not self.key_id:
            raise ValueError("key_id is required")
        if not self.secret:
            raise ValueError("secret must be non-empty")


class KeyProvider(ABC):
    @abstractmethod
    def get_signing_key(self, key_id: str | None = None) -> KeyMaterial: ...


class StaticKeyProvider(KeyProvider):
    """Static test/dev provider. Do not use for production secret storage."""

    def __init__(
        self,
        key_material: KeyMaterial | None = None,
        *,
        secret: bytes | str | None = None,
        key_id: str = "static-key",
    ) -> None:
        if key_material is not None and secret is not None:
            raise ValueError("provide either key_material or secret, not both")
        if key_material is None:
            if secret is None:
                raise ValueError("secret is required when key_material is not provided")
            raw = secret.encode("utf-8") if isinstance(secret, str) else secret
            key_material = KeyMaterial(
                key_id=key_id,
                algorithm=SUPPORTED_SIGNING_ALGORITHM,
                secret=raw,
            )
        self._key_material = key_material

    def get_signing_key(self, key_id: str | None = None) -> KeyMaterial:
        if key_id is not None and key_id != self._key_material.key_id:
            raise KeyError(f"signing key {key_id!r} is not available")
        return self._key_material


class EnvironmentKeyProvider(KeyProvider):
    """Loads HMAC-SHA256 signing material from an environment variable."""

    def __init__(self, env_var: str, *, key_id: str) -> None:
        self._env_var = env_var
        self._key_id = key_id

    def get_signing_key(self, key_id: str | None = None) -> KeyMaterial:
        resolved_key_id = key_id or self._key_id
        value = os.environ.get(self._env_var)
        if value is None:
            raise KeyError(f"missing signing key environment variable: {self._env_var}")
        return KeyMaterial(
            key_id=resolved_key_id,
            algorithm=SUPPORTED_SIGNING_ALGORITHM,
            secret=value.rstrip("\r\n").encode("utf-8"),
        )


class FileKeyProvider(KeyProvider):
    """Loads HMAC-SHA256 signing material from a local file."""

    def __init__(self, key_path: Path, *, key_id: str) -> None:
        self._key_path = key_path
        self._key_id = key_id

    def get_signing_key(self, key_id: str | None = None) -> KeyMaterial:
        if not self._key_path.exists():
            raise FileNotFoundError(f"signing key file not found: {self._key_path}")
        return KeyMaterial(
            key_id=key_id or self._key_id,
            algorithm=SUPPORTED_SIGNING_ALGORITHM,
            secret=self._key_path.read_bytes().rstrip(b"\r\n"),
        )


class KmsKeyProvider(KeyProvider):
    """Future production provider for cloud KMS-backed signing keys."""

    def get_signing_key(self, key_id: str | None = None) -> KeyMaterial:
        raise NotImplementedError("KMS key provider is not implemented")


class HsmKeyProvider(KeyProvider):
    """Future production provider for HSM-backed signing keys."""

    def get_signing_key(self, key_id: str | None = None) -> KeyMaterial:
        raise NotImplementedError("HSM key provider is not implemented")
