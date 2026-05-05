from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime

class EnvironmentStatus(Enum):
    COLD = "cold"
    WARMING = "warming"
    READY = "ready"
    ASSIGNED = "assigned"
    DRAINING = "draining"
    UNHEALTHY = "unhealthy"
    TERMINATED = "terminated"

class EnvironmentClass(Enum):
    STANDARD = "standard"
    HIGH_PERFORMANCE = "high_performance"
    SECURE = "secure"

class IsolationLevel(Enum):
    CONTAINER = "container"
    VM = "vm"
    BARE_METAL = "bare_metal"

class ProvisioningStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class ExecutionEnvironment:
    environment_id: str
    status: EnvironmentStatus
    assigned_session_id: Optional[str] = None
    resource_spec: Dict[str, Any] = field(default_factory=dict)
    preload_manifest: List[str] = field(default_factory=list)
    heartbeat_interval_ms: int = 15000
    assigned_at: Optional[datetime] = None
    provision_started_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def update_status(self, new_status: EnvironmentStatus):
        self.status = new_status
        self.updated_at = datetime.now()