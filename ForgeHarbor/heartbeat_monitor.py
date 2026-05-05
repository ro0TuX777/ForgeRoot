import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import time
import threading
from typing import Callable, Any
from forgeharbor_types import EnvironmentStatus
from pool_manager import PoolManager
from provider import EnvironmentProvider

# Mock imports for environment_kernel - in real implementation, import from dawn.concord.environment_kernel
def mark_environment_unhealthy(env):
    """Mock - sets status to UNHEALTHY"""
    env.status = EnvironmentStatus.UNHEALTHY
    env.updated_at = env.updated_at  # Assuming datetime.now()

def handle_unhealthy_environment(env, session_intents, compensate_fn):
    """Mock - transitions UNHEALTHY to TERMINATED"""
    env.status = EnvironmentStatus.TERMINATED
    env.updated_at = env.updated_at

def get_blocking_intents(environment_id):
    """Mock - return empty list"""
    return []

class HeartbeatMonitor:
    """Background monitor that checks health of live environments and triggers unhealthy path on failure."""

    def __init__(self, pool_manager: PoolManager, provider: EnvironmentProvider, interval_ms: int = 15000):
        self.pool = pool_manager
        self.provider = provider
        self.interval_ms = interval_ms
        self.running = False
        self.thread = None
        self.stop_event = threading.Event()

    def check_once(self) -> None:
        """Single pass health check of all ASSIGNED and WARMING environments."""
        for env in list(self.pool.environments.values()):
            if env.status in (EnvironmentStatus.ASSIGNED, EnvironmentStatus.WARMING):
                health = self.provider.check_health(env.environment_id)
                if health.status != "running":
                    # Trigger the existing unhealthy path
                    mark_environment_unhealthy(env)
                    # Get blocking intents for the session
                    session_intents = get_blocking_intents(env.environment_id) if env.assigned_session_id else []
                    # Compensate function - for now, a no-op
                    def compensate_fn():
                        pass
                    handle_unhealthy_environment(env, session_intents, compensate_fn)

    def start(self) -> None:
        """Start the background heartbeat monitoring loop."""
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stop the background monitoring loop."""
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while not self.stop_event.wait(self.interval_ms / 1000):
            if not self.running:
                break
            try:
                self.check_once()
            except Exception as e:
                # Log error in real implementation
                print(f"Heartbeat check error: {e}")
                continue