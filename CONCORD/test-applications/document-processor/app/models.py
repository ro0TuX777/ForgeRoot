from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TrustTier(int, Enum):
    T0 = 0
    T1 = 1
    T2 = 2
    T3 = 3
    T4 = 4


class Session(BaseModel):
    session_id: str
    trust_tier: TrustTier
    expires_at: datetime
    budget_total: int
    budget_consumed: int = 0
    max_extensions: int = 3
    extensions_count: int = 0
    max_lifetime_at: datetime
    last_refreshed_at: Optional[datetime] = None

    @property
    def remaining_budget(self) -> int:
        return max(0, self.budget_total - self.budget_consumed)

    def is_expired(self) -> bool:
        return datetime.now(self.expires_at.tzinfo or None) >= self.expires_at


class IntentRequest(BaseModel):
    session_id: str
    action_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None


class SessionRefreshRequest(BaseModel):
    session_id: str
    extension_ms: int


class Intent(BaseModel):
    intent_id: str
    session_id: str
    action_name: str
    parameters: Dict[str, Any]
    status: str
    idempotency_key: Optional[str] = None


class NormalizationResult(BaseModel):
    normalized: Optional[Dict[str, Any]] = None
    success: bool = True
    warnings: List[str] = Field(default_factory=list)
    error_detail: Optional[str] = None


class Receipt(BaseModel):
    receipt_id: str
    session_id: str
    intent_id: str
    action_name: str
    status: str
    result_summary: Optional[Dict[str, Any]] = None
    validation_passed: bool = True
    validation_skipped: bool = False
    validation_errors: List[Dict[str, Any]] = Field(default_factory=list)
    idempotency_key: Optional[str] = None
    cost_deducted: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ExecutionResult(BaseModel):
    success: bool
    result_summary: Optional[Any] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    zero_cost: bool = False
