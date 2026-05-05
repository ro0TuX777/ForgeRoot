"""
WormBackend — WORM-overlay backend for Phase 4.

Wraps JsonlBackend with an immutability contract:
- Append is allowed (same as JSONL).
- Legal holds can be applied but never released (simulates Object Lock COMPLIANCE mode).
- All read and export operations work normally.

On production infrastructure this would delegate storage to S3 Object Lock,
Azure Immutable Blob, or an equivalent WORM store. This implementation provides
the contract and testing surface against a local file backend.
"""
from __future__ import annotations

from pathlib import Path

from forgeledger.backend import HoldResult
from forgeledger.jsonl_backend import JsonlBackend


class WormViolationError(Exception):
    """Raised when a mutation is attempted on a WORM backend."""


class WormBackend(JsonlBackend):
    """
    Append-only backend that enforces immutability of written records.

    Legal holds applied to this backend are permanent — release attempts
    raise WormViolationError to reflect COMPLIANCE-mode Object Lock semantics.
    """

    backend_type: str = "worm"

    def __init__(self, ledger_path: Path) -> None:
        super().__init__(ledger_path)

    def release_legal_hold(self, hold_id: str, _reason: str) -> HoldResult:
        raise WormViolationError(
            f"WORM backend: legal hold {hold_id!r} cannot be released. "
            "Records are immutable once written under COMPLIANCE-mode retention."
        )

    def health_check(self) -> dict:
        result = super().health_check()
        result["backend_type"] = "worm"
        result["immutable"] = True
        return result
