import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
from forgeharbor_types import EnvironmentStatus
from pool_manager import PoolManager
from mock_provider import MockProvider

class TestPoolManager(unittest.TestCase):

    def setUp(self):
        self.provider = MockProvider()
        self.pool = PoolManager(
            provider=self.provider,
            target_pool_size=3,
            min_ready=1,
            max_environments=5
        )

    def test_initial_reconcile_provisions_pool(self):
        """After initial reconcile, pool has target_size READY environments."""
        self.pool.reconcile()
        status = self.pool.get_pool_status()

        self.assertEqual(status["pool_size"], 3)
        self.assertEqual(status["counts"]["ready"], 3)
        self.assertEqual(len(self.pool.environments), 3)

        # Verify all are READY
        for env in self.pool.environments.values():
            self.assertEqual(env.status, EnvironmentStatus.READY)

    def test_request_environment_assigns_ready(self):
        """Request assigns a READY environment."""
        self.pool.reconcile()

        result = self.pool.request_environment("sess-1")
        self.assertEqual(result["status"], "ok")
        self.assertIn("environment_id", result["payload"])
        self.assertIn("connection_info", result["payload"])

        env_id = result["payload"]["environment_id"]
        self.assertIn(env_id, self.pool.environments)
        env = self.pool.environments[env_id]
        self.assertEqual(env.status, EnvironmentStatus.ASSIGNED)
        self.assertEqual(env.assigned_session_id, "sess-1")

        # Pool status updated
        status = self.pool.get_pool_status()
        self.assertEqual(status["counts"]["ready"], 2)
        self.assertEqual(status["counts"]["assigned"], 1)

    def test_request_environment_no_ready_available(self):
        """Request fails when no READY environments."""
        # Assign all
        self.pool.reconcile()
        for _ in range(3):
            result = self.pool.request_environment(f"sess-{_}")
            self.assertEqual(result["status"], "ok")

        # Now none ready
        result = self.pool.request_environment("sess-4")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "ENVIRONMENT_UNAVAILABLE")

    def test_release_environment_triggers_drain(self):
        """Release triggers ASSIGNED -> DRAINING."""
        self.pool.reconcile()
        assign_result = self.pool.request_environment("sess-1")
        self.assertEqual(assign_result["status"], "ok")

        env_id = assign_result["payload"]["environment_id"]
        release_result = self.pool.release_environment(env_id)
        self.assertEqual(release_result["status"], "ok")

        env = self.pool.environments[env_id]
        self.assertEqual(env.status, EnvironmentStatus.DRAINING)

    def test_release_nonexistent_environment(self):
        """Release nonexistent environment returns error."""
        result = self.pool.release_environment("nonexistent")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "ENVIRONMENT_NOT_FOUND")

    def test_reconcile_provisions_replacements(self):
        """Reconcile provisions replacements after termination."""
        self.pool.reconcile()
        initial_count = len(self.pool.environments)

        # Simulate terminating one
        env_id = list(self.pool.environments.keys())[0]
        self.provider.terminate(env_id)
        # Manually set to TERMINATED
        self.pool.environments[env_id].status = EnvironmentStatus.TERMINATED

        # Reconcile should clean up and provision replacement
        self.pool.reconcile()

        # Should still have 3, with terminated removed and new one added
        self.assertEqual(len(self.pool.environments), 3)
        status = self.pool.get_pool_status()
        self.assertEqual(status["counts"]["ready"], 3)

    def test_respects_max_environments(self):
        """Pool respects max_environments limit."""
        small_pool = PoolManager(
            provider=self.provider,
            target_pool_size=10,
            max_environments=2
        )
        small_pool.reconcile()

        # Should only have 2, not 10
        self.assertEqual(len(small_pool.environments), 2)
        status = small_pool.get_pool_status()
        self.assertEqual(status["pool_size"], 2)

    def test_get_pool_status(self):
        """get_pool_status returns correct information."""
        self.pool.reconcile()
        status = self.pool.get_pool_status()

        expected_keys = ["pool_size", "counts", "target_pool_size", "min_ready", "max_environments", "utilization_rate"]
        for key in expected_keys:
            self.assertIn(key, status)

        self.assertEqual(status["target_pool_size"], 3)
        self.assertEqual(status["min_ready"], 1)
        self.assertEqual(status["max_environments"], 5)
        self.assertEqual(status["utilization_rate"], 0.0)  # No assigned

if __name__ == '__main__':
    unittest.main()