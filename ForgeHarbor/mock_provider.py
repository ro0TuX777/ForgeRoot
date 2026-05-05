import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from typing import Dict, Any, List, Optional
from provider import EnvironmentProvider, ProvisionResult, HealthStatus, TerminateResult, ConnectionInfo
from environment_spec import EnvironmentSpec

class MockProvider(EnvironmentProvider):
    """In-memory mock implementation of EnvironmentProvider for unit testing without Docker."""

    def __init__(self):
        self.containers: Dict[str, Dict[str, Any]] = {}  # environment_id -> container info

    def provision(self, environment_id: str, spec: EnvironmentSpec) -> ProvisionResult:
        """Simulate provisioning a container."""
        if environment_id in self.containers:
            return ProvisionResult(success=False, error="Container already exists")

        # Simulate successful provisioning
        self.containers[environment_id] = {
            "status": "running",
            "spec": spec,
            "container_id": f"mock-{environment_id}",
            "ip_address": "192.168.1.100",
            "mounts": spec.mounts.copy()
        }

        return ProvisionResult(success=True, container_id=f"mock-{environment_id}")

    def check_health(self, environment_id: str) -> HealthStatus:
        """Check simulated container health."""
        if environment_id not in self.containers:
            return HealthStatus(status="error", details={"error": "container not found"})

        container = self.containers[environment_id]
        return HealthStatus(status=container["status"], details={"container_id": container["container_id"]})

    def terminate(self, environment_id: str) -> TerminateResult:
        """Simulate terminating a container."""
        if environment_id not in self.containers:
            return TerminateResult(success=True)  # Already gone

        del self.containers[environment_id]
        return TerminateResult(success=True)

    def get_connection_info(self, environment_id: str) -> ConnectionInfo:
        """Get simulated connection info."""
        if environment_id not in self.containers:
            raise ValueError(f"Container {environment_id} not found")

        container = self.containers[environment_id]
        return ConnectionInfo(
            container_id=container["container_id"],
            ip_address=container["ip_address"],
            mounts=container["mounts"]
        )

    # Additional methods for testing
    def simulate_failure(self, environment_id: str):
        """Simulate container failure for testing."""
        if environment_id in self.containers:
            self.containers[environment_id]["status"] = "error"

    def simulate_stop(self, environment_id: str):
        """Simulate container stopping."""
        if environment_id in self.containers:
            self.containers[environment_id]["status"] = "stopped"