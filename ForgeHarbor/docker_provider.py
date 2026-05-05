import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from typing import Dict, Any, List
import docker
from docker.errors import DockerException, APIError, NotFound
from provider import EnvironmentProvider, ProvisionResult, HealthStatus, TerminateResult, ConnectionInfo
from environment_spec import EnvironmentSpec

class DockerProvider(EnvironmentProvider):
    """Docker implementation of EnvironmentProvider using Docker SDK."""

    def __init__(self):
        try:
            self.client = docker.from_env()
        except DockerException as e:
            raise RuntimeError(f"Failed to connect to Docker daemon: {e}")

    def provision(self, environment_id: str, spec: EnvironmentSpec) -> ProvisionResult:
        """Provision a new Docker container for the environment."""
        try:
            # Convert mounts to docker Mount objects
            mounts = []
            for mount in spec.mounts:
                mounts.append(
                    docker.types.Mount(
                        target=mount["target"],
                        source=mount.get("source"),
                        type=mount.get("type", "bind"),
                        read_only=mount.get("read_only", False)
                    )
                )

            # Convert resource limits
            resources = {}
            if "cpu" in spec.resource_limits:
                resources["cpu_quota"] = spec.resource_limits["cpu"] * 100000  # Convert cores to microseconds
                resources["cpu_period"] = 100000
            if "memory" in spec.resource_limits:
                resources["mem_limit"] = spec.resource_limits["memory"]

            # Run the container
            container = self.client.containers.run(
                image=spec.image,
                command=["tail", "-f", "/dev/null"],
                name=environment_id,  # Use environment_id as container name
                detach=True,
                network_mode=spec.network_mode,
                environment=spec.environment_vars,
                mounts=mounts,
                **resources
            )

            return ProvisionResult(success=True, container_id=container.id)

        except (APIError, DockerException) as e:
            return ProvisionResult(success=False, error=str(e))

    def check_health(self, environment_id: str) -> HealthStatus:
        """Check the health of the Docker container."""
        try:
            container = self.client.containers.get(environment_id)
            container.reload()  # Refresh status
            status = container.status

            if status == "running":
                return HealthStatus(status="running", details={"container_id": container.id})
            elif status in ["exited", "stopped"]:
                return HealthStatus(status="stopped", details={"exit_code": container.attrs.get("State", {}).get("ExitCode")})
            else:
                return HealthStatus(status="error", details={"status": status})

        except NotFound:
            return HealthStatus(status="error", details={"error": "container not found"})
        except (APIError, DockerException) as e:
            return HealthStatus(status="error", details={"error": str(e)})

    def terminate(self, environment_id: str) -> TerminateResult:
        """Stop and remove the Docker container."""
        try:
            container = self.client.containers.get(environment_id)
            container.stop(timeout=10)
            container.remove()
            return TerminateResult(success=True)

        except NotFound:
            # Container already gone, consider success
            return TerminateResult(success=True)
        except (APIError, DockerException) as e:
            return TerminateResult(success=False, error=str(e))

    def get_connection_info(self, environment_id: str) -> ConnectionInfo:
        """Get connection information for the container."""
        try:
            container = self.client.containers.get(environment_id)
            container.reload()

            # Get network settings
            network_settings = container.attrs.get("NetworkSettings", {})
            host_config = container.attrs.get("HostConfig", {})
            network_mode = host_config.get("NetworkMode", "bridge")
            ip_address = None
            if network_mode != "host":
                # For bridge network, get IP
                networks = network_settings.get("Networks", {})
                if networks:
                    network = networks.get(network_mode) or next(iter(networks.values()))
                    ip_address = network.get("IPAddress")

            # Mounts info
            mounts = []
            for mount in container.attrs.get("Mounts", []):
                mounts.append({
                    "source": mount.get("Source"),
                    "target": mount.get("Destination"),
                    "type": mount.get("Type")
                })

            return ConnectionInfo(
                container_id=container.id,
                ip_address=ip_address,
                mounts=mounts
            )

        except NotFound:
            raise ValueError(f"Container {environment_id} not found")
        except (APIError, DockerException) as e:
            raise RuntimeError(f"Failed to get connection info: {e}")