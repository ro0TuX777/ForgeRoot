import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import threading
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from forgeharbor_types import ExecutionEnvironment, EnvironmentStatus
from lifecycle_engine import provision, on_warm_complete, on_provision_failure, assign, begin_drain, on_drain_complete, recycle, get_blocking_intents
from provider import EnvironmentProvider
from environment_spec import EnvironmentSpec

class PoolManager:
    """Manages a pool of execution environments with automatic provisioning and lifecycle management."""

    def __init__(
        self,
        provider: EnvironmentProvider,
        target_pool_size: int = 3,
        min_ready: int = 1,
        max_environments: int = 5,
        provision_timeout_ms: int = 60000,
        assignment_timeout_ms: int = 5000
    ):
        self.provider = provider
        self.target_pool_size = target_pool_size
        self.min_ready = min_ready
        self.max_environments = max_environments
        self.provision_timeout_ms = provision_timeout_ms
        self.assignment_timeout_ms = assignment_timeout_ms

        self.environments: Dict[str, ExecutionEnvironment] = {}
        self.assignment_lock = threading.Lock()

    def reconcile(self) -> None:
        """Run one pass of the pool reconciliation loop."""
        # Count environments by status
        counts = {}
        for env in self.environments.values():
            status = env.status.value
            counts[status] = counts.get(status, 0) + 1

        ready_count = counts.get('ready', 0)
        total_count = len(self.environments)

        # Provision new environments if below min_ready and under max
        while ready_count < self.min_ready and total_count < self.max_environments:
            self._provision_new_environment()
            total_count += 1
            ready_count += 1  # Assume provision succeeds immediately for simplicity

        # Check WARMING timeouts
        now = datetime.now()
        for env in list(self.environments.values()):
            if env.status == EnvironmentStatus.WARMING:
                if env.provision_started_at:
                    elapsed_ms = (now - env.provision_started_at).total_seconds() * 1000
                    if elapsed_ms > self.provision_timeout_ms:
                        on_provision_failure(env)

        # Check DRAINING completion
        for env in list(self.environments.values()):
            if env.status == EnvironmentStatus.DRAINING:
                if not get_blocking_intents(env.environment_id):
                    on_drain_complete(env)

        # Remove TERMINATED environments (or recycle if needed)
        terminated = [eid for eid, env in self.environments.items() if env.status == EnvironmentStatus.TERMINATED]
        for eid in terminated:
            self.provider.terminate(eid)
            del self.environments[eid]

        # Provision replacements if below target after cleanup
        ready_count = sum(1 for env in self.environments.values() if env.status == EnvironmentStatus.READY)
        while ready_count < self.target_pool_size and len(self.environments) < self.max_environments:
            self._provision_new_environment()
            ready_count += 1

    def _provision_new_environment(self) -> None:
        """Provision a new environment and add to pool."""
        env_id = str(uuid.uuid4())
        env = ExecutionEnvironment(environment_id=env_id, status=EnvironmentStatus.COLD)

        # Physical provisioning
        spec = EnvironmentSpec(
            image=os.environ.get("FORGE_HARBOR_IMAGE", "dawn-runtime:latest"),
            network_mode=os.environ.get("FORGE_HARBOR_NETWORK", "bridge"),
        )
        result = self.provider.provision(env_id, spec)
        if not result.success:
            # Failed, don't add to pool
            return

        # Logical provisioning
        provision_result = provision(env)
        if isinstance(provision_result, dict):
            # Error, terminate physical
            self.provider.terminate(env_id)
            return

        env.provision_started_at = datetime.now()
        self.environments[env_id] = env

        # For simplicity in Phase 3, immediately complete warming
        on_warm_complete(env)

    def request_environment(self, session_id: str) -> Dict[str, Any]:
        """Request an available READY environment for assignment."""
        with self.assignment_lock:
            for env in self.environments.values():
                if env.status == EnvironmentStatus.READY:
                    assign_result = assign(env, session_id)
                    if isinstance(assign_result, ExecutionEnvironment):
                        try:
                            connection_info = self.provider.get_connection_info(env.environment_id)
                            return {
                                "status": "ok",
                                "payload": {
                                    "environment_id": env.environment_id,
                                    "connection_info": connection_info
                                }
                            }
                        except Exception as e:
                            # Revert assignment
                            env.status = EnvironmentStatus.READY
                            env.assigned_session_id = None
                            env.assigned_at = None
                            return {
                                "status": "error",
                                "error": {
                                    "code": "PROVIDER_ERROR",
                                    "message": f"Failed to get connection info: {e}"
                                }
                            }
                    else:
                        return assign_result  # Error from assign

            return {
                "status": "error",
                "error": {
                    "code": "ENVIRONMENT_UNAVAILABLE",
                    "message": "No READY environment available",
                    "details": {"ready_count": sum(1 for e in self.environments.values() if e.status == EnvironmentStatus.READY)}
                }
            }

    def release_environment(self, environment_id: str) -> Dict[str, Any]:
        """Release an ASSIGNED environment, triggering drain."""
        if environment_id not in self.environments:
            return {
                "status": "error",
                "error": {
                    "code": "ENVIRONMENT_NOT_FOUND",
                    "message": f"Environment {environment_id} not found"
                }
            }

        env = self.environments[environment_id]
        drain_result = begin_drain(env)
        if isinstance(drain_result, ExecutionEnvironment):
            ready_count = sum(1 for e in self.environments.values() if e.status == EnvironmentStatus.READY)
            while ready_count < self.target_pool_size and len(self.environments) < self.max_environments:
                self._provision_new_environment()
                ready_count += 1
            return {"status": "ok"}
        else:
            return drain_result  # Error from begin_drain

    def get_pool_status(self) -> Dict[str, Any]:
        """Get current pool status."""
        counts = {}
        for env in self.environments.values():
            status = env.status.value
            counts[status] = counts.get(status, 0) + 1

        return {
            "pool_size": len(self.environments),
            "counts": counts,
            "target_pool_size": self.target_pool_size,
            "min_ready": self.min_ready,
            "max_environments": self.max_environments,
            "utilization_rate": counts.get('assigned', 0) / max(len(self.environments), 1),
            "environment_pool_utilization": counts.get('assigned', 0) / max(len(self.environments), 1),  # Alias for CONCORD
            "average_provision_time_ms": 1000,  # Placeholder - would track actual times
            "environment_recycle_rate": 0.1  # Placeholder - recycles per minute
        }