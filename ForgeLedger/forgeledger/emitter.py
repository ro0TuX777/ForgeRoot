from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from forgeledger.backend import AppendResult, LedgerBackend

if TYPE_CHECKING:
    from forgeledger.key_management import KeyProvider
    from forgeledger.redaction import IngestRedactor


class LedgerWriteFailedError(Exception):
    """
    Raised when the ledger backend rejects an append.

    Callers must treat this as a hard failure — the governed action must not
    proceed if the evidence record cannot be written (fail-closed principle).
    """

    def __init__(self, event_id: str, backend_error: str) -> None:
        super().__init__(f"Ledger write failed for event {event_id!r}: {backend_error}")
        self.event_id = event_id
        self.backend_error = backend_error


from forgeledger.hash_chain import attach_integrity
from forgeledger.retention import classify_event
from forgeledger.schema import (
    LEDGER_VERSION,
    Actor,
    Decision,
    EventType,
    Evidence,
    Integrity,
    LedgerEvent,
    Policy,
    RetentionClass,
    SystemContext,
    Tenant,
)


class LedgerEmitter:
    """
    Thin emission helper.  Pipeline (in order):

        build event
        → IngestRedactor.redact()       (if configured)
        → classify/reclassify retention (data_sensitivity preserved, still correct)
        → attach_integrity              (hash covers the redacted form)
        → sign                          (HMAC covers the hash)
        → backend.append_event

    Signing with a secret_key requires the caller to also pass the matching
    public material to verify_signature() for chain auditing.
    """

    def __init__(
        self,
        backend: LedgerBackend,
        redactor: Optional[IngestRedactor] = None,
        secret_key: Optional[str] = None,
        key_provider: Optional["KeyProvider"] = None,
        audit_emitter: Optional["LedgerEmitter"] = None,
    ) -> None:
        if secret_key is not None and key_provider is not None:
            raise ValueError("provide either secret_key or key_provider, not both")
        self._backend = backend
        self._redactor = redactor
        self._secret_key = secret_key
        self._key_provider = key_provider
        self._audit_emitter = audit_emitter

    def emit(
        self,
        event_type: EventType,
        actor: Actor,
        tenant: Tenant,
        system_context: SystemContext,
        decision: Decision,
        evidence: Evidence,
        policy_id: str,
        policy_hash: str,
        control_tags: list[str],
        legal_hold: bool = False,
        payload: Optional[dict] = None,
    ) -> AppendResult:
        event_id = str(uuid.uuid4())
        event_time = datetime.now(timezone.utc).isoformat()

        # Step 1: build provisional event (interim retention class, no integrity yet).
        provisional = LedgerEvent(
            event_id=event_id,
            ledger_version=LEDGER_VERSION,
            event_type=event_type,
            event_time=event_time,
            actor=actor,
            tenant=tenant,
            system_context=system_context,
            decision=decision,
            evidence=evidence,
            policy=Policy(
                policy_id=policy_id,
                policy_hash=policy_hash,
                retention_class=RetentionClass.OPERATIONAL_30D,
                legal_hold=legal_hold,
            ),
            control_tags=control_tags,
            integrity=Integrity(previous_hash=None, event_hash=""),
            payload=payload,
        )

        # Step 2: redact content-bearing payload fields before anything is hashed.
        # Governance classification fields (data_sensitivity, prompt_class, etc.)
        # are preserved so retention classification works correctly in step 3.
        if self._redactor is not None:
            provisional = self._redactor.redact(provisional)
        redaction_receipts_before_audit = list(provisional.redaction_receipts)

        # Step 3: classify retention now that the payload is in its final form.
        retention_class = classify_event(provisional)

        event = dataclasses.replace(
            provisional,
            policy=Policy(
                policy_id=policy_id,
                policy_hash=policy_hash,
                retention_class=retention_class,
                legal_hold=legal_hold,
            ),
        )

        key_material = self._key_provider.get_signing_key() if self._key_provider is not None else None
        if key_material is not None:
            event = dataclasses.replace(
                event,
                integrity=dataclasses.replace(event.integrity, signing_key_id=key_material.key_id),
            )

        # Step 4: attach integrity — hash covers the redacted event.
        previous_hash = self._backend.get_latest_hash()
        event = attach_integrity(event, previous_hash)

        # Step 5: sign if a key is configured.
        if key_material is not None:
            from forgeledger.signing import sign_event
            event = sign_event(event, key_material.secret, key_material.key_id)
        elif self._secret_key is not None:
            from forgeledger.signing import sign_event
            event = sign_event(event, self._secret_key)

        redaction_audit_payload = None
        if redaction_receipts_before_audit:
            redaction_audit_payload = {
                "original_event_id": event.event_id,
                "original_event_hash": event.integrity.event_hash,
                "primary_event_hash": event.integrity.event_hash,
                "fields_redacted": [r.field_path for r in redaction_receipts_before_audit],
                "redaction_receipts": redaction_receipts_before_audit,
                "tenant_id": event.tenant.tenant_id,
            }

        # Step 6: persist — fail-closed.
        result = self._backend.append_event(event)
        if not result.success:
            raise LedgerWriteFailedError(result.event_id, result.error or "unknown backend error")
        if redaction_audit_payload is not None:
            from forgeledger.audit import emit_audit_event
            tenant_id_for_audit = str(redaction_audit_payload.pop("tenant_id"))
            emit_audit_event(
                self._audit_emitter,
                event_type=EventType.LEDGER_REDACTION_APPLIED,
                reason="redaction_applied",
                tenant_id=tenant_id_for_audit,
                payload=redaction_audit_payload,
            )
        return result
