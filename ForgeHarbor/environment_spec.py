from dataclasses import dataclass, field
from typing import Dict, Any, List

@dataclass
class EnvironmentSpec:
    """Specification for provisioning an execution environment."""
    image: str
    preload_manifest: List[str] = field(default_factory=list)
    resource_limits: Dict[str, Any] = field(default_factory=dict)
    network_mode: str = "bridge"
    environment_vars: Dict[str, str] = field(default_factory=dict)
    mounts: List[Dict[str, str]] = field(default_factory=list)  # [{"source": "/host/path", "target": "/container/path", "type": "bind"}]