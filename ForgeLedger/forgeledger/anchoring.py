from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from forgeledger.audit import emit_audit_event
from forgeledger.canonical_json import canonical_json
from forgeledger.checkpoint import ChainCheckpoint
from forgeledger.schema import EventType

if TYPE_CHECKING:
    from forgeledger.key_management import KeyProvider


@dataclass
class AnchorRecord:
    anchor_id: str
    checkpoint_id: str
    event_count: int
    latest_event_hash: str
    checkpoint_signature: str | None
    anchored_at: str
    anchor_backend: str
    anchor_reference: str
    anchor_signature: str | None = None
    anchor_key_id: str | None = None


@dataclass
class AnchorVerificationReport:
    valid: bool
    missing_anchors: list[str]
    mismatched_anchors: list[str]
    signature_failures: list[str]
    error: str | None = None


class AnchorBackend(ABC):
    @abstractmethod
    def publish_anchor(self, checkpoint: ChainCheckpoint) -> AnchorRecord: ...

    @abstractmethod
    def load_anchors(self) -> list[AnchorRecord]: ...

    @abstractmethod
    def verify_anchor(self, checkpoint: ChainCheckpoint, anchor: AnchorRecord) -> bool: ...


class LocalAnchorBackend(AnchorBackend):
    """
    Append-only local anchor JSONL backend.

    This is a local trust-target simulation and interface discipline, not a
    claim of infrastructure-level immutability.
    """

    def __init__(
        self,
        anchor_path: Path,
        *,
        secret_key: Optional[str] = None,
        key_provider: "KeyProvider | None" = None,
        audit_emitter: object | None = None,
    ) -> None:
        if secret_key is not None and key_provider is not None:
            raise ValueError("provide either secret_key or key_provider, not both")
        self._path = anchor_path
        self._secret_key = secret_key
        self._key_provider = key_provider
        self._audit_emitter = audit_emitter
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.touch()

    def publish_anchor(self, checkpoint: ChainCheckpoint) -> AnchorRecord:
        key_material = self._key_provider.get_signing_key() if self._key_provider is not None else None
        anchor = AnchorRecord(
            anchor_id=str(uuid.uuid4()),
            checkpoint_id=checkpoint.checkpoint_id,
            event_count=checkpoint.event_count,
            latest_event_hash=checkpoint.latest_event_hash,
            checkpoint_signature=checkpoint.signature,
            anchored_at=datetime.now(timezone.utc).isoformat(),
            anchor_backend="local_jsonl",
            anchor_reference=str(self._path),
            anchor_key_id=key_material.key_id if key_material is not None else None,
        )
        if key_material is not None:
            anchor = self._sign_anchor(anchor, key_material.secret)
        elif self._secret_key is not None:
            anchor = self._sign_anchor(anchor, self._secret_key)

        with open(self._path, "a", encoding="utf-8") as f:
            f.write(canonical_json(anchor) + "\n")
            f.flush()

        emit_audit_event(
            self._audit_emitter,
            event_type=EventType.LEDGER_ANCHOR_PUBLISHED,
            reason="anchor_published",
            payload={
                "anchor_id": anchor.anchor_id,
                "checkpoint_id": anchor.checkpoint_id,
                "event_count": anchor.event_count,
                "latest_event_hash": anchor.latest_event_hash,
                "anchor_backend": anchor.anchor_backend,
                "anchor_reference": anchor.anchor_reference,
                "anchor_signature_present": anchor.anchor_signature is not None,
                "anchor_key_id": anchor.anchor_key_id,
            },
        )
        return anchor

    def load_anchors(self) -> list[AnchorRecord]:
        anchors: list[AnchorRecord] = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    raw = json.loads(stripped)
                    anchors.append(AnchorRecord(
                        anchor_id=raw["anchor_id"],
                        checkpoint_id=raw["checkpoint_id"],
                        event_count=raw["event_count"],
                        latest_event_hash=raw["latest_event_hash"],
                        checkpoint_signature=raw.get("checkpoint_signature"),
                        anchored_at=raw["anchored_at"],
                        anchor_backend=raw["anchor_backend"],
                        anchor_reference=raw["anchor_reference"],
                        anchor_signature=raw.get("anchor_signature"),
                        anchor_key_id=raw.get("anchor_key_id"),
                    ))
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise ValueError(f"Invalid anchor JSONL at line {line_number}: {exc}") from exc
        return anchors

    def verify_anchor(self, checkpoint: ChainCheckpoint, anchor: AnchorRecord) -> bool:
        fields_match = (
            anchor.checkpoint_id == checkpoint.checkpoint_id
            and anchor.event_count == checkpoint.event_count
            and anchor.latest_event_hash == checkpoint.latest_event_hash
            and anchor.checkpoint_signature == checkpoint.signature
        )
        if not fields_match:
            return False
        if self._secret_key is not None:
            return self._verify_anchor_signature(anchor, self._secret_key)
        return True

    @staticmethod
    def verification_report(
        checkpoints: list[ChainCheckpoint],
        anchors: list[AnchorRecord],
        *,
        require_anchors: bool = True,
        backend: AnchorBackend | None = None,
    ) -> AnchorVerificationReport:
        anchors_by_checkpoint = {anchor.checkpoint_id: anchor for anchor in anchors}
        missing: list[str] = []
        mismatched: list[str] = []
        signature_failures: list[str] = []

        for checkpoint in checkpoints:
            anchor = anchors_by_checkpoint.get(checkpoint.checkpoint_id)
            if anchor is None:
                if require_anchors:
                    missing.append(checkpoint.checkpoint_id)
                continue

            fields_match = (
                anchor.event_count == checkpoint.event_count
                and anchor.latest_event_hash == checkpoint.latest_event_hash
                and anchor.checkpoint_signature == checkpoint.signature
            )
            if not fields_match:
                mismatched.append(checkpoint.checkpoint_id)
                continue

            if backend is not None and not backend.verify_anchor(checkpoint, anchor):
                signature_failures.append(checkpoint.checkpoint_id)

        valid = not missing and not mismatched and not signature_failures
        error = None
        if missing:
            error = f"missing anchors: {missing}"
        elif mismatched:
            error = f"mismatched anchors: {mismatched}"
        elif signature_failures:
            error = f"anchor signature failures: {signature_failures}"

        return AnchorVerificationReport(
            valid=valid,
            missing_anchors=missing,
            mismatched_anchors=mismatched,
            signature_failures=signature_failures,
            error=error,
        )

    @classmethod
    def _sign_anchor(cls, anchor: AnchorRecord, secret_key: str | bytes) -> AnchorRecord:
        cleared = dataclasses.replace(anchor, anchor_signature=None)
        secret_bytes = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
        signature = hmac.new(
            secret_bytes,
            canonical_json(cleared).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return dataclasses.replace(anchor, anchor_signature=signature)

    @classmethod
    def _verify_anchor_signature(cls, anchor: AnchorRecord, secret_key: str) -> bool:
        if anchor.anchor_signature is None:
            return False
        expected = cls._sign_anchor(anchor, secret_key).anchor_signature
        return hmac.compare_digest(expected or "", anchor.anchor_signature)


class CloudImmutableAnchorBackend(AnchorBackend):
    """Placeholder for future externally controlled immutable anchor targets."""

    def publish_anchor(self, checkpoint: ChainCheckpoint) -> AnchorRecord:
        raise NotImplementedError("Cloud immutable anchor backend is not implemented")

    def load_anchors(self) -> list[AnchorRecord]:
        raise NotImplementedError("Cloud immutable anchor backend is not implemented")

    def verify_anchor(self, checkpoint: ChainCheckpoint, anchor: AnchorRecord) -> bool:
        raise NotImplementedError("Cloud immutable anchor backend is not implemented")
