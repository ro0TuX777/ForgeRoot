from __future__ import annotations

from typing import Any, Callable, Dict, List

from pydantic import BaseModel


class ActionContract(BaseModel):
    action_name: str
    action_family: str
    minimum_trust_tier: int
    cost: int
    cost_category: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    guards: List[str] = []
    idempotent: bool = False


ACTION_REGISTRY: Dict[str, ActionContract] = {}


def register_action(contract: ActionContract):
    ACTION_REGISTRY[contract.action_name] = contract


GUARD_REGISTRY: Dict[str, Callable[..., Dict[str, Any]]] = {}


def register_guard(name: str, func: Callable[..., Dict[str, Any]]):
    GUARD_REGISTRY[name] = func


EXECUTOR_REGISTRY: Dict[str, Callable[..., Any]] = {}


def register_executor(action_name: str, func: Callable[..., Any]):
    EXECUTOR_REGISTRY[action_name] = func


NORMALIZER_REGISTRY: Dict[str, Callable[..., Any]] = {}


def register_normalizer(action_name: str, func: Callable[..., Any]):
    NORMALIZER_REGISTRY[action_name] = func
