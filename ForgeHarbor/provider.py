from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from environment_spec import EnvironmentSpec

@dataclass
class ProvisionResult:
    success: bool
    container_id: Optional[str] = None
    error: Optional[str] = None

@dataclass
class HealthStatus:
    status: str  # "running", "stopped", "error"
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}

@dataclass
class TerminateResult:
    success: bool
    error: Optional[str] = None

@dataclass
class ConnectionInfo:
    container_id: str
    ip_address: Optional[str] = None
    mounts: List[Dict[str, str]] = None

    def __post_init__(self):
        if self.mounts is None:
            self.mounts = []

class EnvironmentProvider(ABC):
    """Abstract interface for environment provisioning backends."""

    @abstractmethod
    def provision(self, environment_id: str, spec: EnvironmentSpec) -> ProvisionResult:
        """Start a new environment. Returns when container is running (not necessarily ready)."""
        pass

    @abstractmethod
    def check_health(self, environment_id: str) -> HealthStatus:
        """Check if the environment's container is running and responsive."""
        pass

    @abstractmethod
    def terminate(self, environment_id: str) -> TerminateResult:
        """Stop and remove the environment's container."""
        pass

    @abstractmethod
    def get_connection_info(self, environment_id: str) -> ConnectionInfo:
        """Return how to reach the environment (e.g., container ID, IP, mount paths)."""
        pass