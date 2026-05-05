from typing import Union, Dict, Any, List
from datetime import datetime
import uuid
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from forgeharbor_types import ExecutionEnvironment, EnvironmentStatus

# Mock for get_blocking_intents - in real implementation, import from dawn.concord.environment_kernel
def get_blocking_intents(environment_id: str) -> List[Dict[str, Any]]:
    """
    Mock implementation. In real code, this would be imported from dawn.concord.environment_kernel
    Returns list of intents in ADMITTED or EXECUTING status for the environment.
    """
    # For Phase 1 testing, return empty list (no blocking intents)
    return []

def can_transition(from_status: EnvironmentStatus, to_status: EnvironmentStatus) -> bool:
    """
    Enforces the ExecutionEnvironment state machine topology.
    Returns True for valid transitions, False for invalid.
    """
    valid_transitions = {
        EnvironmentStatus.COLD: [EnvironmentStatus.WARMING],
        EnvironmentStatus.WARMING: [EnvironmentStatus.READY, EnvironmentStatus.TERMINATED],
        EnvironmentStatus.READY: [EnvironmentStatus.ASSIGNED, EnvironmentStatus.DRAINING],
        EnvironmentStatus.ASSIGNED: [EnvironmentStatus.DRAINING],
        EnvironmentStatus.DRAINING: [EnvironmentStatus.TERMINATED],
        EnvironmentStatus.UNHEALTHY: [EnvironmentStatus.TERMINATED],
        EnvironmentStatus.TERMINATED: [EnvironmentStatus.COLD],  # for recycle
    }
    return to_status in valid_transitions.get(from_status, [])

def _create_error(code: str, message: str, details: Dict[str, Any] = None) -> Dict[str, Any]:
    """Helper to create structured error response."""
    return {
        "status": "error",
        "error": {
            "code": code,
            "message": message,
            "details": details or {}
        }
    }

def provision(env: ExecutionEnvironment) -> Union[ExecutionEnvironment, Dict[str, Any]]:
    """
    Transition COLD -> WARMING.
    Sets status to WARMING.
    """
    if not can_transition(env.status, EnvironmentStatus.WARMING):
        return _create_error(
            "INVALID_TRANSITION",
            f"Cannot transition from {env.status.value} to {EnvironmentStatus.WARMING.value}",
            {"from_status": env.status.value, "to_status": EnvironmentStatus.WARMING.value}
        )
    env.update_status(EnvironmentStatus.WARMING)
    return env

def on_warm_complete(env: ExecutionEnvironment) -> Union[ExecutionEnvironment, Dict[str, Any]]:
    """
    Transition WARMING -> READY.
    Sets status to READY.
    """
    if not can_transition(env.status, EnvironmentStatus.READY):
        return _create_error(
            "INVALID_TRANSITION",
            f"Cannot transition from {env.status.value} to {EnvironmentStatus.READY.value}",
            {"from_status": env.status.value, "to_status": EnvironmentStatus.READY.value}
        )
    env.update_status(EnvironmentStatus.READY)
    return env

def on_provision_failure(env: ExecutionEnvironment) -> Union[ExecutionEnvironment, Dict[str, Any]]:
    """
    Transition WARMING -> TERMINATED.
    Used when provisioning fails or times out.
    """
    if not can_transition(env.status, EnvironmentStatus.TERMINATED):
        return _create_error(
            "INVALID_TRANSITION",
            f"Cannot transition from {env.status.value} to {EnvironmentStatus.TERMINATED.value}",
            {"from_status": env.status.value, "to_status": EnvironmentStatus.TERMINATED.value}
        )
    env.update_status(EnvironmentStatus.TERMINATED)
    return env

def assign(env: ExecutionEnvironment, session_id: str) -> Union[ExecutionEnvironment, Dict[str, Any]]:
    """
    Transition READY -> ASSIGNED.
    Sets assigned_session_id and assigned_at.
    """
    if not can_transition(env.status, EnvironmentStatus.ASSIGNED):
        return _create_error(
            "INVALID_TRANSITION",
            f"Cannot transition from {env.status.value} to {EnvironmentStatus.ASSIGNED.value}",
            {"from_status": env.status.value, "to_status": EnvironmentStatus.ASSIGNED.value}
        )
    env.assigned_session_id = session_id
    env.assigned_at = datetime.now()
    env.update_status(EnvironmentStatus.ASSIGNED)
    return env

def begin_drain(env: ExecutionEnvironment) -> Union[ExecutionEnvironment, Dict[str, Any]]:
    """
    Transition ASSIGNED or READY -> DRAINING.
    For ASSIGNED, checks if blocking intents exist. If yes, stays ASSIGNED.
    For READY, no check needed.
    """
    if not can_transition(env.status, EnvironmentStatus.DRAINING):
        return _create_error(
            "INVALID_TRANSITION",
            f"Cannot transition from {env.status.value} to {EnvironmentStatus.DRAINING.value}",
            {"from_status": env.status.value, "to_status": EnvironmentStatus.DRAINING.value}
        )

    if env.status == EnvironmentStatus.ASSIGNED:
        blocking_intents = get_blocking_intents(env.environment_id)
        if blocking_intents:
            return _create_error(
                "DRAIN_BLOCKED",
                "Cannot drain environment with active blocking intents",
                {"blocking_intents_count": len(blocking_intents)}
            )

    env.update_status(EnvironmentStatus.DRAINING)
    return env

def on_drain_complete(env: ExecutionEnvironment) -> Union[ExecutionEnvironment, Dict[str, Any]]:
    """
    Transition DRAINING -> TERMINATED.
    Assumes all blocking intents have been resolved.
    """
    if not can_transition(env.status, EnvironmentStatus.TERMINATED):
        return _create_error(
            "INVALID_TRANSITION",
            f"Cannot transition from {env.status.value} to {EnvironmentStatus.TERMINATED.value}",
            {"from_status": env.status.value, "to_status": EnvironmentStatus.TERMINATED.value}
        )
    env.update_status(EnvironmentStatus.TERMINATED)
    return env

def recycle(env: ExecutionEnvironment) -> Union[ExecutionEnvironment, Dict[str, Any]]:
    """
    Transition TERMINATED -> new COLD environment.
    Resets fields and generates new environment_id.
    """
    if not can_transition(env.status, EnvironmentStatus.COLD):
        return _create_error(
            "INVALID_TRANSITION",
            f"Cannot transition from {env.status.value} to {EnvironmentStatus.COLD.value}",
            {"from_status": env.status.value, "to_status": EnvironmentStatus.COLD.value}
        )

    # Create new environment with reset fields
    new_env = ExecutionEnvironment(
        environment_id=str(uuid.uuid4()),
        status=EnvironmentStatus.COLD,
        resource_spec=env.resource_spec.copy(),
        preload_manifest=env.preload_manifest.copy(),
        heartbeat_interval_ms=env.heartbeat_interval_ms
    )
    return new_env