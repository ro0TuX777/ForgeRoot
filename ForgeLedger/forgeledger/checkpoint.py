from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from forgeledger.canonical_json import canonical_json
from forgeledger.hash_chain import verify_chain
from forgeledger.schema import EventType, LedgerEvent

if TYPE_CHECKING:
    from forgeledger.anchoring import AnchorBackend, AnchorRecord, AnchorVerificationReport
    from forgeledger.key_management import KeyProvider


@dataclass
class ChainCheckpoint:
    checkpoint_id: str
    event_count: int
    latest_event_hash: str
    timestamp: str
    signature: Optional[str] = None
    key_id: Optional[str] = None


@dataclass
class CheckpointVerificationReport:
    valid: bool
    tail_truncation_detected: bool
    recomputation_detected: bool
    signature_failures: int
    error: Optional[str] = None


class CheckpointManager:
    """
    Append-only chain checkpoint manager.

    Signatures use the current ForgeLedger signing model: HMAC-SHA256 encoded
    as 64 lowercase hex characters over the checkpoint with signature cleared.
    """

    def __init__(
        self,
        checkpoint_path: Path,
        interval: int,
        secret_key: Optional[str] = None,
        key_provider: "KeyProvider | None" = None,
        audit_emitter: object | None = None,
        anchor_backend: "AnchorBackend | None" = None,
    ) -> None:
        if interval <= 0:
            raise ValueError("checkpoint interval must be greater than zero")
        if secret_key is not None and key_provider is not None:
            raise ValueError("provide either secret_key or key_provider, not both")
        self._path = checkpoint_path
        self._interval = interval
        self._secret_key = secret_key
        self._key_provider = key_provider
        self._audit_emitter = audit_emitter
        self._anchor_backend = anchor_backend
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.touch()

    def maybe_checkpoint(self, events_so_far: list[LedgerEvent]) -> Optional[ChainCheckpoint]:
        event_count = len(events_so_far)
        if event_count == 0 or event_count % self._interval != 0:
            return None
        if any(cp.event_count == event_count for cp in self.load_checkpoints()):
            return None

        key_material = self._key_provider.get_signing_key() if self._key_provider is not None else None
        checkpoint = ChainCheckpoint(
            checkpoint_id=str(uuid.uuid4()),
            event_count=event_count,
            latest_event_hash=events_so_far[-1].integrity.event_hash,
            timestamp=datetime.now(timezone.utc).isoformat(),
            key_id=key_material.key_id if key_material is not None else None,
        )
        if key_material is not None:
            checkpoint = self._sign_checkpoint(checkpoint, key_material.secret)
        elif self._secret_key is not None:
            checkpoint = self._sign_checkpoint(checkpoint, self._secret_key)

        with open(self._path, "a", encoding="utf-8") as f:
            f.write(canonical_json(checkpoint) + "\n")
            f.flush()

        if self._anchor_backend is not None:
            self._anchor_backend.publish_anchor(checkpoint)

        from forgeledger.audit import emit_audit_event
        emit_audit_event(
            self._audit_emitter,
            event_type=EventType.LEDGER_CHECKPOINT_CREATED,
            reason="checkpoint_created",
            payload={
                "checkpoint_id": checkpoint.checkpoint_id,
                "event_count": checkpoint.event_count,
                "latest_event_hash": checkpoint.latest_event_hash,
                "checkpoint_signature_present": checkpoint.signature is not None,
            },
        )
        return checkpoint

    def load_checkpoints(self) -> list[ChainCheckpoint]:
        checkpoints: list[ChainCheckpoint] = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    raw = json.loads(stripped)
                    checkpoints.append(ChainCheckpoint(
                        checkpoint_id=raw["checkpoint_id"],
                        event_count=raw["event_count"],
                        latest_event_hash=raw["latest_event_hash"],
                        timestamp=raw["timestamp"],
                        signature=raw.get("signature"),
                        key_id=raw.get("key_id"),
                    ))
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise ValueError(f"Invalid checkpoint JSONL at line {line_number}: {exc}") from exc
        return checkpoints

    @classmethod
    def verify_with_checkpoints(
        cls,
        events: list[LedgerEvent],
        checkpoints: list[ChainCheckpoint],
        secret_key: Optional[str] = None,
    ) -> CheckpointVerificationReport:
        chain_report = verify_chain(events)
        if not chain_report.valid:
            return CheckpointVerificationReport(
                valid=False,
                tail_truncation_detected=False,
                recomputation_detected=False,
                signature_failures=0,
                error=chain_report.error,
            )

        signature_failures = 0
        if secret_key is not None:
            signature_failures = sum(
                0 if cp.signature is not None and cls._verify_checkpoint_signature(cp, secret_key) else 1
                for cp in checkpoints
            )

        latest_checkpoint_count = max((cp.event_count for cp in checkpoints), default=0)
        if len(events) < latest_checkpoint_count:
            return CheckpointVerificationReport(
                valid=False,
                tail_truncation_detected=True,
                recomputation_detected=False,
                signature_failures=signature_failures,
                error=(
                    f"event count {len(events)} is less than latest checkpoint "
                    f"event_count {latest_checkpoint_count}"
                ),
            )

        recomputation_detected = False
        for checkpoint in checkpoints:
            if checkpoint.event_count == 0 or checkpoint.event_count > len(events):
                continue
            event_hash_at_checkpoint = events[checkpoint.event_count - 1].integrity.event_hash
            if event_hash_at_checkpoint != checkpoint.latest_event_hash:
                recomputation_detected = True
                break

        valid = signature_failures == 0 and not recomputation_detected
        error = None
        if signature_failures:
            error = f"{signature_failures} checkpoint signature failure(s)"
        elif recomputation_detected:
            error = "checkpoint hash mismatch: chain appears recomputed after checkpoint"

        return CheckpointVerificationReport(
            valid=valid,
            tail_truncation_detected=False,
            recomputation_detected=recomputation_detected,
            signature_failures=signature_failures,
            error=error,
        )

    @classmethod
    def verify_with_anchors(
        cls,
        checkpoints: list[ChainCheckpoint],
        anchors: list["AnchorRecord"],
        *,
        require_anchors: bool = True,
        anchor_backend: "AnchorBackend | None" = None,
    ) -> "AnchorVerificationReport":
        from forgeledger.anchoring import LocalAnchorBackend

        return LocalAnchorBackend.verification_report(
            checkpoints,
            anchors,
            require_anchors=require_anchors,
            backend=anchor_backend,
        )

    @classmethod
    def _sign_checkpoint(cls, checkpoint: ChainCheckpoint, secret_key: str | bytes) -> ChainCheckpoint:
        cleared = dataclasses.replace(checkpoint, signature=None)
        secret_bytes = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
        signature = hmac.new(
            secret_bytes,
            canonical_json(cleared).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return dataclasses.replace(checkpoint, signature=signature)

    @classmethod
    def _verify_checkpoint_signature(cls, checkpoint: ChainCheckpoint, secret_key: str) -> bool:
        if checkpoint.signature is None:
            return False
        expected = cls._sign_checkpoint(checkpoint, secret_key).signature
        return hmac.compare_digest(expected or "", checkpoint.signature)
