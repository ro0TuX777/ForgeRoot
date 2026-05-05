"""
ForgeLedgerClient — lightweight SDK entry point for Phase 5.

Downstream systems use this API without importing internal schema types. The
SDK handles event construction, tenant boundary locking, optional HMAC signing,
optional replay protection, integrity attachment, and backend delegation.

The returned event dict is canonical JSON-compatible and schema-identical to
events emitted via LedgerEmitter (direct-call path), proving that bus migration
is a drop-in swap — the envelope is the same regardless of emission path.

Bus compatibility guarantee:
    event_from_dict(client.emit_event(...)) == valid LedgerEvent
    set(sdk_dict.keys()) == set(direct_dict.keys())  # same schema
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from forgeledger.backend import LedgerBackend
from forgeledger.canonical_json import canonical_json
from forgeledger.hash_chain import attach_integrity
from forgeledger.replay_protection import ReplayProtector
from forgeledger.schema import (
    LEDGER_VERSION,
    Actor,
    Decision,
    Evidence,
    EventType,
    Integrity,
    LedgerEvent,
    Policy,
    RetentionClass,
    SystemContext,
    Tenant,
)
from forgeledger.signing import sign_event
from forgeledger.validators import validate_event


class TenantBoundaryViolationError(Exception):
    """Raised when an event or incoming message crosses tenant boundaries."""


class InvalidEventError(Exception):
    """Raised when a constructed event fails schema validation."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__(f"Event validation failed: {errors}")
        self.errors = errors


class ForgeLedgerClient:
    """
    Lightweight SDK for downstream systems.

    Callers interact via emit_event() using only primitive types. The client
    locks all events to its tenant_id, optionally signs them, optionally guards
    against replay, and delegates persistence to the configured backend.

    The SDK does not expose ForgeLedger schema types in its public API surface.
    """

    def __init__(
        self,
        backend: LedgerBackend,
        tenant_id: str,
        customer_boundary: str = "",
        data_residency: str = "GLOBAL",
        *,
        secret_key: Optional[str] = None,
        signing_enabled: bool = False,
        replay_protection: bool = True,
    ) -> None:
        if signing_enabled and not secret_key:
            raise ValueError("signing_enabled=True requires secret_key")
        self._backend = backend
        self._tenant_id = tenant_id
        self._customer_boundary = customer_boundary
        self._data_residency = data_residency
        self._secret_key = secret_key
        self._signing_enabled = signing_enabled
        self._replay: Optional[ReplayProtector] = (
            ReplayProtector() if replay_protection else None
        )

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    def emit_event(
        self,
        event_type: str,
        actor_id: str,
        decision_type: str,
        *,
        role: str = "sdk_caller",
        actor_type: str = "system",
        reason: str = "sdk_emission",
        risk_level: str = "low",
        evidence_refs: Optional[list[str]] = None,
        control_tags: Optional[list[str]] = None,
        source_module: str = "SDK",
        environment: str = "unknown",
        deployment_id: str = "sdk",
        policy_id: str = "sdk_default",
        policy_hash: str = "none",
        retention_class: str = "operational_30d",
        legal_hold: bool = False,
        payload: Optional[dict] = None,
        _event_id: Optional[str] = None,  # testing hook — do not use in production
    ) -> dict:
        """
        Emit a ledger event and return the bus-compatible serialized event dict.

        The tenant is always locked to the client's tenant_id — callers cannot
        override it.

        Raises:
            InvalidEventError: event_type unknown or schema validation fails.
            ReplayDetectedError: event_id already processed (replay guard active).
        """
        try:
            et = EventType(event_type)
        except ValueError:
            raise InvalidEventError([f"unknown event_type: {event_type!r}"])

        event_id = _event_id or str(uuid.uuid4())

        event = LedgerEvent(
            event_id=event_id,
            ledger_version=LEDGER_VERSION,
            event_type=et,
            event_time=datetime.now(timezone.utc).isoformat(),
            actor=Actor(actor_type=actor_type, actor_id=actor_id, role=role),
            tenant=Tenant(
                tenant_id=self._tenant_id,
                customer_boundary=self._customer_boundary,
                data_residency=self._data_residency,
            ),
            system_context=SystemContext(
                source_module=source_module,
                environment=environment,
                deployment_id=deployment_id,
            ),
            decision=Decision(
                decision_type=decision_type,
                reason=reason,
                risk_level=risk_level,
            ),
            evidence=Evidence(
                evidence_refs=evidence_refs or [],
                evidence_gaps=[],
                assertion_classes=[],
            ),
            policy=Policy(
                policy_id=policy_id,
                policy_hash=policy_hash,
                retention_class=RetentionClass(retention_class),
                legal_hold=legal_hold,
            ),
            control_tags=control_tags or [],
            integrity=Integrity(previous_hash=None, event_hash=""),
            payload=payload,
        )

        previous_hash = self._backend.get_latest_hash()
        event = attach_integrity(event, previous_hash)

        if self._signing_enabled and self._secret_key:
            event = sign_event(event, self._secret_key)

        errors = validate_event(event)
        if errors:
            raise InvalidEventError(errors)

        if self._replay is not None:
            self._replay.check_and_register(event.event_id)

        self._backend.append_event(event)

        return json.loads(canonical_json(event))

    def validate_incoming(self, event_dict: dict) -> None:
        """
        Validate that an event dict arriving from a bus belongs to this tenant.

        In a bus scenario the SDK must reject events from other tenants before
        processing them. Call this on every inbound message.

        Raises:
            TenantBoundaryViolationError: if the event's tenant_id does not
                match this client's tenant_id.
        """
        incoming_tenant = (event_dict.get("tenant") or {}).get("tenant_id")
        if incoming_tenant != self._tenant_id:
            raise TenantBoundaryViolationError(
                f"Incoming event tenant {incoming_tenant!r} does not match "
                f"client tenant {self._tenant_id!r}. Cross-tenant writes are not permitted."
            )
