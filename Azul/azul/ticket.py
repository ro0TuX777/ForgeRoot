"""
ticket.py — AzulTicket entity + enums  (P0-1)
==============================================
Pure data model.  No framework imports.  No I/O.

Covers Core Specification §4.1 and §4.2.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ─────────────────────────────────────────────────────────────────────

class TicketStatus(str, Enum):
    """All eight lifecycle statuses (Core Spec §4.2)."""
    SUBMITTED    = "SUBMITTED"
    ANALYZING    = "ANALYZING"
    PROVISIONING = "PROVISIONING"
    EVALUATING   = "EVALUATING"
    GATING       = "GATING"
    COMPLETED    = "COMPLETED"
    REJECTED     = "REJECTED"
    WARNED       = "WARNED"
    FAILED       = "FAILED"


class TicketType(str, Enum):
    """Five use-case ticket types (Core Spec §3)."""
    CI_GATE             = "ci_gate"
    REFACTOR            = "refactor"
    SECURITY_PATCH      = "security_patch"
    POLICY_COMPLIANCE   = "policy_compliance"
    DISTILLATION_PAIR   = "distillation_pair"


class TicketPriority(str, Enum):
    LOW      = "low"
    NORMAL   = "normal"
    HIGH     = "high"
    CRITICAL = "critical"


# ── Terminal statuses (no further transitions allowed) ────────────────────────

TERMINAL_STATUSES: frozenset[TicketStatus] = frozenset({
    TicketStatus.COMPLETED,
    TicketStatus.REJECTED,
    TicketStatus.WARNED,
    TicketStatus.FAILED,
})


# ── Helper ────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_ticket_id() -> str:
    short = uuid.uuid4().hex[:8]
    return f"azul-{short}"


# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class AzulTicket:
    """
    Core ticket entity.  All fields map 1-to-1 to Core Spec §4.1.

    Create via ``create_ticket()`` rather than instantiating directly so that
    defaults (ticket_id, created_at, status) are populated correctly.
    """

    # Identity
    ticket_id:   str
    ticket_type: TicketType
    priority:    TicketPriority

    # Lifecycle
    status: TicketStatus

    # Domain routing
    domain: str
    mode:   str   # "shadow" | "supervised" | "ramped"

    # Change description
    change_summary: str
    change_payload: Dict[str, Any]
    source:         Dict[str, Any]
    target_files:   List[str]

    # Verification context (populated during pipeline)
    blast_radius:   Optional[Dict[str, Any]]
    environment_id: Optional[str]
    planner_spec:   Optional[Dict[str, Any]]

    # Results (populated after evaluation)
    review_bundle: Optional[Dict[str, Any]]
    gate_result:   Optional[Dict[str, Any]]
    verdict:       Optional[str]    # "pass" | "reject" | "warn"
    verdict_reason: Optional[str]

    # Reward
    xp_awarded:   int
    training_pair: Optional[Dict[str, Any]]

    # Per-ticket gate policy override (None → use default)
    gate_policy: Optional[Dict[str, Any]]

    # Timestamps
    created_at:   str
    updated_at:   str
    completed_at: Optional[str]

    # Extensible metadata
    metadata: Dict[str, Any]

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict (JSON-safe — all values are primitives or dicts/lists)."""
        return {
            "ticket_id":     self.ticket_id,
            "ticket_type":   self.ticket_type.value,
            "priority":      self.priority.value,
            "status":        self.status.value,
            "domain":        self.domain,
            "mode":          self.mode,
            "change_summary":  self.change_summary,
            "change_payload":  self.change_payload,
            "source":          self.source,
            "target_files":    self.target_files,
            "blast_radius":    self.blast_radius,
            "environment_id":  self.environment_id,
            "planner_spec":    self.planner_spec,
            "review_bundle":   self.review_bundle,
            "gate_result":     self.gate_result,
            "verdict":         self.verdict,
            "verdict_reason":  self.verdict_reason,
            "xp_awarded":      self.xp_awarded,
            "training_pair":   self.training_pair,
            "gate_policy":     self.gate_policy,
            "created_at":      self.created_at,
            "updated_at":      self.updated_at,
            "completed_at":    self.completed_at,
            "metadata":        self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AzulTicket":
        """Deserialize from a plain dict (as produced by ``to_dict()``)."""
        return cls(
            ticket_id       = d["ticket_id"],
            ticket_type     = TicketType(d["ticket_type"]),
            priority        = TicketPriority(d["priority"]),
            status          = TicketStatus(d["status"]),
            domain          = d["domain"],
            mode            = d["mode"],
            change_summary  = d["change_summary"],
            change_payload  = d.get("change_payload", {}),
            source          = d.get("source", {}),
            target_files    = d.get("target_files", []),
            blast_radius    = d.get("blast_radius"),
            environment_id  = d.get("environment_id"),
            planner_spec    = d.get("planner_spec"),
            review_bundle   = d.get("review_bundle"),
            gate_result     = d.get("gate_result"),
            verdict         = d.get("verdict"),
            verdict_reason  = d.get("verdict_reason"),
            xp_awarded      = d.get("xp_awarded", 0),
            training_pair   = d.get("training_pair"),
            gate_policy     = d.get("gate_policy"),
            created_at      = d["created_at"],
            updated_at      = d["updated_at"],
            completed_at    = d.get("completed_at"),
            metadata        = d.get("metadata", {}),
        )

    def touch(self) -> None:
        """Update ``updated_at`` to now (mutates in place)."""
        self.updated_at = _now_iso()


# ── Factory ───────────────────────────────────────────────────────────────────

def create_ticket(
    ticket_type: str | TicketType,
    domain: str,
    change_summary: str,
    change_payload: Optional[Dict[str, Any]] = None,
    source: Optional[Dict[str, Any]] = None,
    target_files: Optional[List[str]] = None,
    priority: str | TicketPriority = TicketPriority.NORMAL,
    mode: str = "shadow",
    gate_policy: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ticket_id: Optional[str] = None,
) -> AzulTicket:
    """
    Create a new AzulTicket in SUBMITTED status.

    All fields not supplied default to safe empty values.  The caller only
    needs to provide the fields that are meaningful for the use case.
    """
    now = _now_iso()
    return AzulTicket(
        ticket_id       = ticket_id or _new_ticket_id(),
        ticket_type     = TicketType(ticket_type) if isinstance(ticket_type, str) else ticket_type,
        priority        = TicketPriority(priority) if isinstance(priority, str) else priority,
        status          = TicketStatus.SUBMITTED,
        domain          = domain,
        mode            = mode,
        change_summary  = change_summary,
        change_payload  = change_payload or {},
        source          = source or {},
        target_files    = target_files or [],
        blast_radius    = None,
        environment_id  = None,
        planner_spec    = None,
        review_bundle   = None,
        gate_result     = None,
        verdict         = None,
        verdict_reason  = None,
        xp_awarded      = 0,
        training_pair   = None,
        gate_policy     = gate_policy,
        created_at      = now,
        updated_at      = now,
        completed_at    = None,
        metadata        = metadata or {},
    )
