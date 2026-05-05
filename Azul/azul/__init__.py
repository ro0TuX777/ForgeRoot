"""
azul — Agentic Change Verification System
==========================================
Package-level exports for Phase 1 (ticket lifecycle).
"""

from .ticket import (
    AzulTicket,
    TicketStatus,
    TicketType,
    TicketPriority,
    TERMINAL_STATUSES,
    create_ticket,
)
from .lifecycle import (
    can_transition,
    begin_analysis,
    begin_provisioning,
    begin_evaluation,
    begin_gating,
    complete,
    reject,
    warn,
    fail,
)
from .ticket_store import AzulTicketStore
from .xp_ledger import XPLedger, calculate_xp
from .training_pairs import emit_training_pair, TrainingPairStore

__all__ = [
    # Entities
    "AzulTicket",
    "TicketStatus",
    "TicketType",
    "TicketPriority",
    "TERMINAL_STATUSES",
    "create_ticket",
    # Lifecycle
    "can_transition",
    "begin_analysis",
    "begin_provisioning",
    "begin_evaluation",
    "begin_gating",
    "complete",
    "reject",
    "warn",
    "fail",
    # Storage
    "AzulTicketStore",
    # XP
    "XPLedger",
    "calculate_xp",
    # Training pairs
    "emit_training_pair",
    "TrainingPairStore",
]
