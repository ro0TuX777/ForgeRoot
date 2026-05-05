"""
Event signing for Phase 5 — HMAC-SHA256 over canonical JSON.

The signature covers the full event with integrity.signature cleared to None,
so the signature is not included in its own input (avoids circularity). This
is the same pattern used for integrity.event_hash.

This is HMAC-based authentication for systems that share the secret.
"""
from __future__ import annotations

import dataclasses
import hashlib
import hmac

from forgeledger.canonical_json import canonical_json
from forgeledger.schema import LedgerEvent


def _secret_bytes(secret_key: str | bytes) -> bytes:
    return secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key


def sign_event(event: LedgerEvent, secret_key: str | bytes, key_id: str | None = None) -> LedgerEvent:
    """Return a new event with integrity.signature set to HMAC-SHA256(canonical_json)."""
    event_to_sign = event
    if key_id is not None and event.integrity.signing_key_id != key_id:
        event_to_sign = dataclasses.replace(
            event,
            integrity=dataclasses.replace(event.integrity, signing_key_id=key_id),
        )
    cleared = dataclasses.replace(
        event_to_sign,
        integrity=dataclasses.replace(event_to_sign.integrity, signature=None),
    )
    sig = hmac.new(
        _secret_bytes(secret_key),
        canonical_json(cleared).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return dataclasses.replace(
        event_to_sign,
        integrity=dataclasses.replace(event_to_sign.integrity, signature=sig),
    )


def verify_signature(event: LedgerEvent, secret_key: str | bytes) -> bool:
    """
    Verify the event's HMAC-SHA256 signature.
    Returns False if the signature field is absent or does not match.
    """
    if event.integrity.signature is None:
        return False
    cleared = dataclasses.replace(
        event,
        integrity=dataclasses.replace(event.integrity, signature=None),
    )
    expected = hmac.new(
        _secret_bytes(secret_key),
        canonical_json(cleared).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, event.integrity.signature)
