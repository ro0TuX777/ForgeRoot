import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
from unittest.mock import patch, MagicMock
from daemon import ForgeHarborDaemon
from forgeharbor_types import EnvironmentStatus

class TestForgeHarborDaemon(unittest.TestCase):

    def setUp(self):
        self.daemon = ForgeHarborDaemon(use_mock_provider=True)

    def tearDown(self):
        if self.daemon.running:
            self.daemon.shutdown()

    def test_startup_sequence(self):
        """Daemon starts, initializes pool, starts loops."""
        self.daemon.start()
        self.assertTrue(self.daemon.running)
        self.assertTrue(self.daemon.heartbeat_monitor.running)
        self.assertIsNotNone(self.daemon.reconcile_thread)

        # Check pool is initialized
        status = self.daemon.get_pool_status()
        self.assertEqual(status["status"], "ok")
        self.assertEqual(status["payload"]["pool_size"], 3)  # target_pool_size

    def test_shutdown_terminates_containers(self):
        """Shutdown terminates all containers."""
        self.daemon.start()

        # Assign an environment
        result = self.daemon.request_environment("sess-1")
        self.assertEqual(result["status"], "ok")
        env_id = result["payload"]["environment_id"]

        # Mock terminate to track calls
        with patch.object(self.daemon.provider, 'terminate', wraps=self.daemon.provider.terminate) as mock_terminate:
            self.daemon.shutdown()

            # Should have terminated all environments
            self.assertTrue(mock_terminate.called)
            # At least the assigned one
            call_args = [call[0][0] for call in mock_terminate.call_args_list]
            self.assertIn(env_id, call_args)

        self.assertFalse(self.daemon.running)

    def test_request_environment_integration(self):
        """request_environment works through daemon."""
        self.daemon.start()

        result = self.daemon.request_environment("sess-1")
        self.assertEqual(result["status"], "ok")
        self.assertIn("environment_id", result["payload"])
        self.assertIn("connection_info", result["payload"])

    def test_release_environment_integration(self):
        """release_environment works through daemon."""
        self.daemon.start()

        # Request
        req_result = self.daemon.request_environment("sess-1")
        self.assertEqual(req_result["status"], "ok")
        env_id = req_result["payload"]["environment_id"]

        # Release
        rel_result = self.daemon.release_environment(env_id)
        self.assertEqual(rel_result["status"], "ok")

        # Check status
        status_result = self.daemon.get_environment_status(env_id)
        self.assertEqual(status_result["status"], "ok")
        self.assertEqual(status_result["payload"]["status"], "draining")

    def test_get_environment_status(self):
        """get_environment_status returns correct info."""
        self.daemon.start()

        req_result = self.daemon.request_environment("sess-1")
        env_id = req_result["payload"]["environment_id"]

        status = self.daemon.get_environment_status(env_id)
        self.assertEqual(status["status"], "ok")
        payload = status["payload"]
        self.assertEqual(payload["environment_id"], env_id)
        self.assertEqual(payload["status"], "assigned")
        self.assertEqual(payload["assigned_session_id"], "sess-1")
        self.assertIsNotNone(payload["assigned_at"])

    def test_get_environment_status_not_found(self):
        """get_environment_status for nonexistent environment."""
        self.daemon.start()

        status = self.daemon.get_environment_status("nonexistent")
        self.assertEqual(status["status"], "error")
        self.assertEqual(status["error"]["code"], "ENVIRONMENT_NOT_FOUND")

    def test_get_pool_status(self):
        """get_pool_status returns pool information."""
        self.daemon.start()

        status = self.daemon.get_pool_status()
        self.assertEqual(status["status"], "ok")
        payload = status["payload"]
        self.assertIn("pool_size", payload)
        self.assertIn("counts", payload)
        self.assertIn("utilization_rate", payload)

    def test_health_check(self):
        """health() returns daemon health."""
        self.daemon.start()

        health = self.daemon.health()
        self.assertEqual(health["status"], "ok")
        payload = health["payload"]
        self.assertIn("healthy", payload)
        self.assertIn("pool_status", payload)
        self.assertIn("heartbeat_running", payload)
        self.assertTrue(payload["heartbeat_running"])

    def test_shutdown_stops_loops(self):
        """Shutdown stops background loops."""
        self.daemon.start()
        self.assertTrue(self.daemon.heartbeat_monitor.running)

        self.daemon.shutdown()
        self.assertFalse(self.daemon.heartbeat_monitor.running)
        self.assertFalse(self.daemon.running)

if __name__ == '__main__':
    unittest.main()