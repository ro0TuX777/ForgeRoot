from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from jsonschema import Draft202012Validator, ValidationError

from app.actions import register_actions
from app.executors import register_executors
from app.guards import register_guards
from app.normalizers import register_normalizers
from app.models import ExecutionResult, Intent, IntentRequest, Receipt, Session
from app.registry import ACTION_REGISTRY, EXECUTOR_REGISTRY, GUARD_REGISTRY, NORMALIZER_REGISTRY


class InMemorySessionStore:
    def __init__(self) -> None:
        self.sessions: Dict[str, Session] = {}
        self._create_default_session()

    def _create_default_session(self) -> None:
        session_id = "session-default"
        now = datetime.now(timezone.utc)
        session = Session(
            session_id=session_id,
            trust_tier=1,
            expires_at=now + timedelta(hours=4),
            budget_total=1000,
            budget_consumed=0,
            max_lifetime_at=now + timedelta(hours=8),
        )
        self.sessions[session_id] = session

    def get(self, session_id: str) -> Optional[Session]:
        session = self.sessions.get(session_id)
        if session and session.is_expired():
            session.expires_at = session.expires_at
            return None
        return session

    def update(self, session: Session) -> None:
        self.sessions[session.session_id] = session


class InMemoryReceiptStore:
    def __init__(self) -> None:
        self.receipts: Dict[str, Receipt] = {}

    def store(self, receipt: Receipt) -> None:
        self.receipts[receipt.receipt_id] = receipt

    def get(self, receipt_id: str) -> Optional[Receipt]:
        return self.receipts.get(receipt_id)

    def find_by_idempotency_key(self, idempotency_key: str) -> Optional[Receipt]:
        for receipt in self.receipts.values():
            if getattr(receipt, "idempotency_key", None) == idempotency_key:
                return receipt
        return None


class InMemoryIntentStore:
    def __init__(self) -> None:
        self.intents: Dict[str, Intent] = {}

    def store(self, intent: Intent) -> None:
        self.intents[intent.intent_id] = intent

    def get(self, intent_id: str) -> Optional[Intent]:
        return self.intents.get(intent_id)


class AdmissionPipeline:
    def __init__(self) -> None:
        register_actions()
        register_guards()
        register_executors()
        register_normalizers()

        self.session_store = InMemorySessionStore()
        self.intent_store = InMemoryIntentStore()
        self.receipt_store = InMemoryReceiptStore()

    def process_intent(self, request: IntentRequest) -> Tuple[bool, Dict[str, Any]]:
        session = self._stage_session_resolution(request.session_id)
        if not session:
            return False, {"error_code": "SESSION_NOT_FOUND"}

        action_contract = self._stage_action_resolution(request.action_name)
        if not action_contract:
            return False, {"error_code": "ACTION_NOT_FOUND"}

        if not self._stage_trust_gate(session, action_contract):
            return False, {"error_code": "TRUST_INSUFFICIENT"}

        if action_contract.cost and not self._stage_budget_gate(session, action_contract):
            return False, {"error_code": "BUDGET_EXCEEDED"}

        valid, validation_detail = self._stage_input_validation(request.parameters, action_contract)
        if not valid:
            return False, {"error_code": "INVALID_PARAMETERS", "detail": validation_detail}

        if action_contract.guards:
            guard_result = self._stage_guard_evaluation(request.parameters, session, action_contract)
            if not guard_result.get("passed"):
                return False, {"error_code": "GUARD_FAILED", "detail": guard_result}

        if request.idempotency_key and self._stage_idempotency_check(request.idempotency_key):
            return False, {"error_code": "IDEMPOTENCY_CONFLICT"}

        intent = self._stage_intent_creation(request)

        executor = EXECUTOR_REGISTRY.get(action_contract.action_name)
        if not executor:
            return False, {"error_code": "EXECUTOR_NOT_FOUND"}

        execution_result = executor(request.parameters, session, action_contract)
        if not execution_result.success:
            return False, {
                "error_code": execution_result.error_code or "EXECUTION_FAILED",
                "detail": execution_result.error_detail,
            }

        if action_contract.output_schema:
            normalizer = NORMALIZER_REGISTRY.get(action_contract.action_name)
            if not normalizer:
                return False, {"error_code": "NORMALIZER_NOT_FOUND"}
            norm = normalizer(execution_result.result_summary, action_contract)
            if not norm.success:
                return False, {
                    "error_code": "OUTPUT_NORMALIZATION_FAILED",
                    "detail": norm.error_detail,
                }
            result_summary = norm.normalized
        else:
            result_summary = execution_result.result_summary

        receipt = self._stage_receipt_minting(intent, action_contract, result_summary)
        return True, {"receipt_id": receipt.receipt_id, "result": receipt.result_summary}

    def _stage_session_resolution(self, session_id: str) -> Optional[Session]:
        session = self.session_store.get(session_id)
        return session

    def _stage_action_resolution(self, action_name: str) -> Optional[Any]:
        return ACTION_REGISTRY.get(action_name)

    def _stage_trust_gate(self, session: Session, action_contract: Any) -> bool:
        return session.trust_tier >= action_contract.minimum_trust_tier

    def _stage_budget_gate(self, session: Session, action_contract: Any) -> bool:
        return session.remaining_budget >= action_contract.cost

    def _stage_guard_evaluation(self, parameters: Dict[str, Any], session: Session, action_contract: Any) -> Dict[str, Any]:
        for guard_name in action_contract.guards:
            guard_fn = GUARD_REGISTRY.get(guard_name)
            if not guard_fn:
                return {"passed": False, "guard_name": guard_name, "reason": "guard implementation missing"}
            result = guard_fn(parameters, session, action_contract)
            if not result.get("passed"):
                return result
        return {"passed": True}

    def _stage_input_validation(self, parameters: Dict[str, Any], action_contract: Any) -> Tuple[bool, Dict[str, Any]]:
        try:
            validator = Draft202012Validator(action_contract.input_schema)
            errors = list(validator.iter_errors(parameters))
            if errors:
                detail = {"errors": [self._format_validation_error(e) for e in errors]}
                return False, detail
            return True, {}
        except ValidationError as e:
            return False, {"errors": [str(e)]}

    def _stage_idempotency_check(self, idempotency_key: str) -> bool:
        return self.receipt_store.find_by_idempotency_key(idempotency_key) is not None

    def _stage_intent_creation(self, request: IntentRequest) -> Intent:
        intent = Intent(
            intent_id=str(uuid.uuid4()),
            session_id=request.session_id,
            action_name=request.action_name,
            parameters=request.parameters,
            status="admitted",
            idempotency_key=request.idempotency_key,
        )
        self.intent_store.store(intent)
        return intent

    def get_operation_context(self, session_id: str, action_name: str) -> Tuple[bool, Dict[str, Any]]:
        session = self.session_store.get(session_id)
        if not session:
            return False, {"error_code": "SESSION_NOT_FOUND"}
        action = ACTION_REGISTRY.get(action_name)
        if not action:
            return False, {"error_code": "ACTION_NOT_FOUND"}

        guard_evaluations = []
        for guard_name in action.guards:
            guard_fn = GUARD_REGISTRY.get(guard_name)
            if not guard_fn:
                guard_evaluations.append({
                    "guard_name": guard_name,
                    "passed": False,
                    "reason": "guard implementation missing",
                })
                continue
            guard_result = guard_fn({}, session, action)
            guard_evaluations.append(guard_result)

        can_execute = (
            session.trust_tier >= action.minimum_trust_tier
            and session.remaining_budget >= action.cost
            and all(item.get("passed") for item in guard_evaluations)
        )

        return True, {
            "session_id": session.session_id,
            "action_name": action.action_name,
            "action_family": action.action_family,
            "minimum_trust_tier": action.minimum_trust_tier,
            "cost": action.cost,
            "input_schema": action.input_schema,
            "output_schema": action.output_schema,
            "guards": action.guards,
            "trust_sufficient": session.trust_tier >= action.minimum_trust_tier,
            "budget_remaining": session.remaining_budget,
            "guard_evaluations": guard_evaluations,
            "can_execute": can_execute,
            "session_expires_at": session.expires_at,
        }

    def get_budget_status(self, session_id: str) -> Tuple[bool, Dict[str, Any]]:
        session = self.session_store.get(session_id)
        if not session:
            return False, {"error_code": "SESSION_NOT_FOUND"}
        total = session.budget_total
        consumed = session.budget_consumed
        remaining = session.remaining_budget
        return True, {
            "session_id": session.session_id,
            "budget_profile_id": "default-profile",
            "total": total,
            "consumed": consumed,
            "remaining": remaining,
            "percent_used": round((consumed / total * 100) if total else 0, 2),
            "expires_at": session.expires_at,
        }

    def get_budget_estimate(self, session_id: str, action_name: str) -> Tuple[bool, Dict[str, Any]]:
        session = self.session_store.get(session_id)
        if not session:
            return False, {"error_code": "SESSION_NOT_FOUND"}
        action = ACTION_REGISTRY.get(action_name)
        if not action:
            return False, {"error_code": "ACTION_NOT_FOUND"}

        guard_evaluations = []
        for guard_name in action.guards:
            guard_fn = GUARD_REGISTRY.get(guard_name)
            if not guard_fn:
                guard_evaluations.append({
                    "guard_name": guard_name,
                    "passed": False,
                    "reason": "guard implementation missing",
                })
                continue
            guard_evaluations.append({
                "guard_name": guard_name,
                "passed": None,
                "reason": "parameters unavailable for estimate",
            })

        estimated_cost = action.cost or 0
        trust_sufficient = session.trust_tier >= action.minimum_trust_tier
        budget_sufficient = session.remaining_budget >= estimated_cost
        can_execute = trust_sufficient and budget_sufficient and not any(item.get("passed") is False for item in guard_evaluations)

        return True, {
            "session_id": session.session_id,
            "action_name": action.action_name,
            "cost": estimated_cost,
            "trust_sufficient": trust_sufficient,
            "budget_sufficient": budget_sufficient,
            "remaining_budget": session.remaining_budget,
            "guard_evaluations": guard_evaluations,
            "can_execute": can_execute,
        }

    def get_receipt(self, receipt_id: str) -> Tuple[bool, Dict[str, Any]]:
        receipt = self.receipt_store.get(receipt_id)
        if not receipt:
            return False, {"error_code": "RECEIPT_NOT_FOUND"}
        return True, receipt.model_dump()

    def refresh_session(self, session_id: str, extension_ms: int) -> Tuple[bool, Dict[str, Any]]:
        session = self.session_store.get(session_id)
        if not session:
            return False, {"error_code": "SESSION_NOT_FOUND"}

        requested_extension = timedelta(milliseconds=extension_ms)
        new_expires_at = session.expires_at + requested_extension
        if new_expires_at > session.max_lifetime_at:
            return False, {"error_code": "SESSION_MAX_LIFETIME_REACHED", "detail": "Requested extension exceeds max lifetime."}
        if session.extensions_count >= session.max_extensions:
            return False, {"error_code": "SESSION_MAX_EXTENSIONS_REACHED", "detail": "Maximum session extensions reached."}

        old_expires = session.expires_at
        session.expires_at = new_expires_at
        session.extensions_count += 1
        session.last_refreshed_at = datetime.now(timezone.utc)
        self.session_store.update(session)
        return True, {
            "session_id": session.session_id,
            "old_expires_at": old_expires,
            "new_expires_at": session.expires_at,
            "extensions_count": session.extensions_count,
            "max_extensions": session.max_extensions,
            "max_lifetime_at": session.max_lifetime_at,
            "remaining_extensions": session.max_extensions - session.extensions_count,
        }

    def _stage_receipt_minting(self, intent: Intent, action_contract: Any, result_summary: Any) -> Receipt:
        validation_passed = True
        validation_errors: List[Dict[str, Any]] = []
        try:
            if action_contract.output_schema:
                validator = Draft202012Validator(action_contract.output_schema)
                errors = list(validator.iter_errors(result_summary))
                if errors:
                    validation_passed = False
                    validation_errors = [self._format_validation_error(e) for e in errors]
        except ValidationError as e:
            validation_passed = False
            validation_errors = [{"error": str(e)}]

        receipt = Receipt(
            receipt_id=str(uuid.uuid4()),
            session_id=intent.session_id,
            intent_id=intent.intent_id,
            action_name=intent.action_name,
            status="completed",
            result_summary=result_summary,
            validation_passed=validation_passed,
            validation_skipped=not bool(action_contract.output_schema),
            validation_errors=validation_errors,
            idempotency_key=intent.idempotency_key,
            cost_deducted=0,
            created_at=datetime.now(timezone.utc),
        )

        if action_contract.cost:
            receipt.cost_deducted = action_contract.cost
            session = self.session_store.get(intent.session_id)
            if session:
                session.budget_consumed += action_contract.cost
                self.session_store.update(session)

        self.receipt_store.store(receipt)
        return receipt

    @staticmethod
    def _format_validation_error(error: ValidationError) -> Dict[str, Any]:
        return {
            "path": "/" + "/".join(str(p) for p in error.absolute_path) if error.absolute_path else "/",
            "message": error.message,
            "validator": error.validator,
        }


admission_pipeline = AdmissionPipeline()
