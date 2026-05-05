import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import signal
import time
import threading
from typing import Dict, Any, Optional
from pool_manager import PoolManager
from heartbeat_monitor import HeartbeatMonitor
from docker_provider import DockerProvider
from mock_provider import MockProvider
from forgeharbor_types import EnvironmentStatus

class ForgeHarborDaemon:
    """Main daemon process for ForgeHarbor warm pool management."""

    def __init__(self, use_mock_provider: bool = False):
        # Load configuration from environment variables
        self.config = {
            'pool_size': int(os.environ.get('FORGE_HARBOR_POOL_SIZE', '3')),
            'min_ready': int(os.environ.get('FORGE_HARBOR_MIN_READY', '1')),
            'max_environments': int(os.environ.get('FORGE_HARBOR_MAX_ENVIRONMENTS', '5')),
            'provision_timeout_ms': int(os.environ.get('FORGE_HARBOR_PROVISION_TIMEOUT_MS', '60000')),
            'heartbeat_interval_ms': int(os.environ.get('FORGE_HARBOR_HEARTBEAT_INTERVAL_MS', '15000')),
            'reconcile_interval_ms': int(os.environ.get('FORGE_HARBOR_RECONCILE_INTERVAL_MS', '10000')),
        }

        # Initialize provider
        if use_mock_provider:
            self.provider = MockProvider()
            self.provider_type = "MockProvider"
        else:
            self.provider = DockerProvider()
            self.provider_type = "DockerProvider"

        # Initialize pool manager
        self.pool = PoolManager(
            provider=self.provider,
            target_pool_size=self.config['pool_size'],
            min_ready=self.config['min_ready'],
            max_environments=self.config['max_environments'],
            provision_timeout_ms=self.config['provision_timeout_ms']
        )

        # Initialize heartbeat monitor
        self.heartbeat_monitor = HeartbeatMonitor(
            pool_manager=self.pool,
            provider=self.provider,
            interval_ms=self.config['heartbeat_interval_ms']
        )

        self.running = False
        self.reconcile_thread = None
        self.stop_event = threading.Event()

    def start(self) -> None:
        """Start the daemon with background loops."""
        if self.running:
            return

        self.running = True
        self.stop_event.clear()

        # Initial reconciliation
        self.pool.reconcile()

        # Start background loops
        self.heartbeat_monitor.start()
        self.reconcile_thread = threading.Thread(target=self._reconcile_loop, daemon=True)
        self.reconcile_thread.start()

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Log startup summary
        status = self.pool.get_pool_status()
        print(f"ForgeHarbor started: {status['pool_size']} environments, {self.provider_type}, pool target={self.config['pool_size']}")

    def shutdown(self) -> None:
        """Graceful shutdown: drain environments, terminate containers, clean exit."""
        if not self.running:
            return

        print("ForgeHarbor shutting down...")
        self.running = False
        self.stop_event.set()

        # Stop background loops
        self.heartbeat_monitor.stop()
        if self.reconcile_thread:
            self.reconcile_thread.join(timeout=5)

        # Drain all assigned environments
        assigned_envs = [env for env in self.pool.environments.values() if env.status == EnvironmentStatus.ASSIGNED]
        for env in assigned_envs:
            self.pool.release_environment(env.environment_id)

        # The reconciliation loop is stopped, so shutdown owns final cleanup.
        # Terminate containers directly after initiating drain.
        for env_id in list(self.pool.environments.keys()):
            try:
                self.provider.terminate(env_id)
            except Exception as e:
                print(f"Error terminating {env_id}: {e}")

        print("ForgeHarbor shutdown complete")
        # In real daemon, sys.exit(0)

    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals."""
        self.shutdown()

    def _reconcile_loop(self) -> None:
        """Background pool reconciliation loop."""
        while not self.stop_event.wait(self.config['reconcile_interval_ms'] / 1000):
            if not self.running:
                break
            try:
                self.pool.reconcile()
            except Exception as e:
                print(f"Reconciliation error: {e}")
                continue

    # Caller-facing functions

    def request_environment(self, session_id: str) -> Dict[str, Any]:
        """Request an execution environment for a session."""
        try:
            result = self.pool.request_environment(session_id)
            if result['status'] == 'ok':
                return {"status": "ok", "payload": result['payload']}
            else:
                return result
        except Exception as e:
            return {"status": "error", "error": {"code": "INTERNAL_ERROR", "message": str(e)}}

    def release_environment(self, environment_id: str) -> Dict[str, Any]:
        """Signal that a session is done with an environment."""
        try:
            result = self.pool.release_environment(environment_id)
            return result
        except Exception as e:
            return {"status": "error", "error": {"code": "INTERNAL_ERROR", "message": str(e)}}

    def get_environment_status(self, environment_id: str) -> Dict[str, Any]:
        """Query current status of a specific environment."""
        try:
            if environment_id not in self.pool.environments:
                return {"status": "error", "error": {"code": "ENVIRONMENT_NOT_FOUND", "message": f"Environment {environment_id} not found"}}
            env = self.pool.environments[environment_id]
            return {
                "status": "ok",
                "payload": {
                    "environment_id": env.environment_id,
                    "status": env.status.value,
                    "assigned_session_id": env.assigned_session_id,
                    "assigned_at": env.assigned_at.isoformat() if env.assigned_at else None,
                    "created_at": env.created_at.isoformat(),
                    "updated_at": env.updated_at.isoformat()
                }
            }
        except Exception as e:
            return {"status": "error", "error": {"code": "INTERNAL_ERROR", "message": str(e)}}

    def get_pool_status(self) -> Dict[str, Any]:
        """Pool-wide status."""
        try:
            status = self.pool.get_pool_status()
            return {"status": "ok", "payload": status}
        except Exception as e:
            return {"status": "error", "error": {"code": "INTERNAL_ERROR", "message": str(e)}}

    def health(self) -> Dict[str, Any]:
        """Daemon health check."""
        try:
            status = self.pool.get_pool_status()
            healthy = (
                self.running and
                self.heartbeat_monitor.running and
                status['pool_size'] >= self.config['min_ready']
            )
            return {
                "status": "ok",
                "payload": {
                    "healthy": healthy,
                    "pool_status": status,
                    "heartbeat_running": self.heartbeat_monitor.running,
                    "uptime_seconds": time.time() - time.time()  # Would track start time
                }
            }
        except Exception as e:
            return {"status": "error", "error": {"code": "INTERNAL_ERROR", "message": str(e)}}