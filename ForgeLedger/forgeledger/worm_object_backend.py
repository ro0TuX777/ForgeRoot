from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from forgeledger.canonical_json import canonical_json
from forgeledger.worm_backend import WormViolationError


@dataclass
class WormObjectManifest:
    object_id: str
    object_path: str
    sha256: str
    created_at: str
    retention_until: str | None
    legal_hold: bool
    backend_type: str


@dataclass
class WormVerificationReport:
    valid: bool
    object_count: int
    mismatched_objects: list[str]
    missing_objects: list[str]
    error: str | None = None


class WormObjectBackend(ABC):
    @abstractmethod
    def write_object(
        self,
        object_id: str,
        data: bytes | str,
        *,
        retention_until: str | None = None,
        legal_hold: bool = False,
    ) -> WormObjectManifest: ...

    @abstractmethod
    def load_manifest(self) -> list[WormObjectManifest]: ...

    @abstractmethod
    def verify_manifest(self) -> WormVerificationReport: ...


class LocalWormObjectBackend(WormObjectBackend):
    """
    Local write-once object simulation with manifest-based tamper detection.

    This is not production infrastructure immutability. Production-grade WORM
    requires S3 Object Lock, Azure Immutable Blob, Wasabi WORM, or an
    equivalent externally enforced retention system.
    """

    backend_type = "local_worm_simulation"

    def __init__(self, object_dir: Path, manifest_path: Path | None = None) -> None:
        self._object_dir = object_dir
        self._manifest_path = manifest_path or object_dir / "worm_manifest.jsonl"
        self._object_dir.mkdir(parents=True, exist_ok=True)
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._manifest_path.exists():
            self._manifest_path.touch()

    def write_object(
        self,
        object_id: str,
        data: bytes | str,
        *,
        retention_until: str | None = None,
        legal_hold: bool = False,
    ) -> WormObjectManifest:
        object_path = self._resolve_object_path(object_id)
        if any(entry.object_id == object_id for entry in self.load_manifest()) or object_path.exists():
            raise WormViolationError(f"WORM object {object_id!r} already exists")

        raw = data.encode("utf-8") if isinstance(data, str) else data
        with open(object_path, "xb") as f:
            f.write(raw)
            f.flush()

        manifest = WormObjectManifest(
            object_id=object_id,
            object_path=str(object_path),
            sha256=hashlib.sha256(raw).hexdigest(),
            created_at=datetime.now(timezone.utc).isoformat(),
            retention_until=retention_until,
            legal_hold=legal_hold,
            backend_type=self.backend_type,
        )
        with open(self._manifest_path, "a", encoding="utf-8") as f:
            f.write(canonical_json(manifest) + "\n")
            f.flush()
        return manifest

    def delete_object(self, object_id: str) -> None:
        raise WormViolationError(f"WORM object {object_id!r} cannot be deleted")

    def mutate_object(self, object_id: str, data: bytes | str) -> None:
        raise WormViolationError(f"WORM object {object_id!r} cannot be mutated")

    def update_object(self, object_id: str, data: bytes | str) -> None:
        raise WormViolationError(f"WORM object {object_id!r} cannot be updated")

    def load_manifest(self) -> list[WormObjectManifest]:
        manifests: list[WormObjectManifest] = []
        with open(self._manifest_path, "r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    raw = json.loads(stripped)
                    manifests.append(WormObjectManifest(
                        object_id=raw["object_id"],
                        object_path=raw["object_path"],
                        sha256=raw["sha256"],
                        created_at=raw["created_at"],
                        retention_until=raw.get("retention_until"),
                        legal_hold=raw["legal_hold"],
                        backend_type=raw["backend_type"],
                    ))
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise ValueError(f"Invalid WORM manifest JSONL at line {line_number}: {exc}") from exc
        return manifests

    def verify_manifest(self) -> WormVerificationReport:
        try:
            manifests = self.load_manifest()
        except ValueError as exc:
            return WormVerificationReport(
                valid=False,
                object_count=0,
                mismatched_objects=[],
                missing_objects=[],
                error=str(exc),
            )

        mismatched: list[str] = []
        missing: list[str] = []
        for entry in manifests:
            path = Path(entry.object_path)
            if not path.exists():
                missing.append(entry.object_id)
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != entry.sha256:
                mismatched.append(entry.object_id)

        valid = not mismatched and not missing
        error = None
        if missing:
            error = f"missing WORM objects: {missing}"
        elif mismatched:
            error = f"mismatched WORM objects: {mismatched}"
        return WormVerificationReport(
            valid=valid,
            object_count=len(manifests),
            mismatched_objects=mismatched,
            missing_objects=missing,
            error=error,
        )

    def _resolve_object_path(self, object_id: str) -> Path:
        if not object_id or Path(object_id).is_absolute() or ".." in Path(object_id).parts:
            raise ValueError("object_id must be a relative write-once object name")
        return self._object_dir / object_id


class S3ObjectLockBackend(WormObjectBackend):
    """Production WORM placeholder for S3 Object Lock."""

    def write_object(
        self,
        object_id: str,
        data: bytes | str,
        *,
        retention_until: str | None = None,
        legal_hold: bool = False,
    ) -> WormObjectManifest:
        raise NotImplementedError("S3 Object Lock backend is not implemented")

    def load_manifest(self) -> list[WormObjectManifest]:
        raise NotImplementedError("S3 Object Lock backend is not implemented")

    def verify_manifest(self) -> WormVerificationReport:
        raise NotImplementedError("S3 Object Lock backend is not implemented")


class AzureImmutableBlobBackend(WormObjectBackend):
    """Production WORM placeholder for Azure Immutable Blob."""

    def write_object(
        self,
        object_id: str,
        data: bytes | str,
        *,
        retention_until: str | None = None,
        legal_hold: bool = False,
    ) -> WormObjectManifest:
        raise NotImplementedError("Azure Immutable Blob backend is not implemented")

    def load_manifest(self) -> list[WormObjectManifest]:
        raise NotImplementedError("Azure Immutable Blob backend is not implemented")

    def verify_manifest(self) -> WormVerificationReport:
        raise NotImplementedError("Azure Immutable Blob backend is not implemented")


class WasabiWormBucketBackend(WormObjectBackend):
    """Production WORM placeholder for Wasabi WORM buckets."""

    def write_object(
        self,
        object_id: str,
        data: bytes | str,
        *,
        retention_until: str | None = None,
        legal_hold: bool = False,
    ) -> WormObjectManifest:
        raise NotImplementedError("Wasabi WORM bucket backend is not implemented")

    def load_manifest(self) -> list[WormObjectManifest]:
        raise NotImplementedError("Wasabi WORM bucket backend is not implemented")

    def verify_manifest(self) -> WormVerificationReport:
        raise NotImplementedError("Wasabi WORM bucket backend is not implemented")
