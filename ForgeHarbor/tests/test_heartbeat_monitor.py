import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
from unittest.mock import patch
from forgeharbor_types import EnvironmentStatus
from pool_manager import PoolManager
from mock_provider import MockProvider
from heartbeat_monitor import HeartbeatMonitor

class TestHeartbeatMonitor(unittest.TestCase):

    def setUp(self):
        self.provider = MockProvider()
        self.pool = PoolManager(provider=self.provider, target_pool_size=2)
        self.pool.reconcile()  # Create 2 READY environments
        self.monitor = HeartbeatMonitor(self.pool, self.provider, interval_ms=100)  # Fast for testing

    def test_check_once_healthy_environments(self):
        """check_once does nothing when environments are healthy."""
        # Assign one environment
        result = self.pool.request_environment("sess-1")
        self.assertEqual(result["status"], "ok")
        env_id = result["payload"]["environment_id"]

        # Check once - should remain ASSIGNED
        self.monitor.check_once()
        env = self.pool.environments[env_id]
        self.assertEqual(env.status, EnvironmentStatus.ASSIGNED)

    def test_check_once_detects_failed_assigned(self):
        """check_once triggers unhealthy path for failed ASSIGNED environment."""
        # Assign environment
        result = self.pool.request_environment("sess-1")
        self.assertEqual(result["status"], "ok")
        env_id = result["payload"]["environment_id"]

        # Simulate failure
        self.provider.simulate_failure(env_id)

        # Check once - should trigger unhealthy
        self.monitor.check_once()
        env = self.pool.environments[env_id]
        self.assertEqual(env.status, EnvironmentStatus.TERMINATED)  # After handle_unhealthy_environment

    def test_check_once_detects_failed_warming(self):
        """check_once triggers unhealthy path for failed WARMING environment."""
        # Manually create WARMING environment
        from lifecycle_engine import provision
        env_id = list(self.pool.environments.keys())[0]
        env = self.pool.environments[env_id]
        env.status = EnvironmentStatus.WARMING

        # Simulate failure
        self.provider.simulate_failure(env_id)

        # Check once
        self.monitor.check_once()
        self.assertEqual(env.status, EnvironmentStatus.TERMINATED)

    def test_check_once_ignores_ready_and_terminated(self):
        """check_once only checks ASSIGNED and WARMING environments."""
        # READY environment
        ready_env_id = None
        for eid, env in self.pool.environments.items():
            if env.status == EnvironmentStatus.READY:
                ready_env_id = eid
                break

        # Simulate failure on READY (should be ignored)
        self.provider.simulate_failure(ready_env_id)
        self.monitor.check_once()
        env = self.pool.environments[ready_env_id]
        self.assertEqual(env.status, EnvironmentStatus.READY)  # Unchanged

    def test_background_loop_can_be_started_and_stopped(self):
        """Background loop starts and stops without error."""
        self.monitor.start()
        self.assertTrue(self.monitor.running)
        self.assertIsNotNone(self.monitor.thread)

        self.monitor.stop()
        self.assertFalse(self.monitor.running)

if __name__ == '__main__':
    unittest.main()