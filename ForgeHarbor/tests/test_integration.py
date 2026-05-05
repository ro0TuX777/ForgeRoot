import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
import time
from docker.errors import DockerException, NotFound
from daemon import ForgeHarborDaemon

class TestIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Check if Docker is available for integration tests."""
        try:
            from docker_provider import DockerProvider
            provider = DockerProvider()
            provider.client.ping()
            cls.docker_available = True
        except (DockerException, RuntimeError):
            cls.docker_available = False

    def setUp(self):
        if not self.docker_available:
            self.skipTest("Docker daemon not available for integration tests")
        # Use real Docker for integration
        self.daemon = ForgeHarborDaemon(use_mock_provider=False)

    def tearDown(self):
        if self.docker_available and hasattr(self, 'daemon'):
            try:
                self.daemon.shutdown()
            except:
                pass

    def test_full_lifecycle_integration(self):
        """Integration test: daemon starts, provisions 3 containers, assigns one, releases, pool replenishes, shutdown terminates all."""
        # Start daemon
        self.daemon.start()

        # Wait for initial pool provisioning
        time.sleep(2)  # Allow time for provisioning

        # Check pool has 3 READY environments
        status = self.daemon.get_pool_status()
        self.assertEqual(status["status"], "ok")
        initial_pool_size = status["payload"]["pool_size"]
        self.assertGreaterEqual(initial_pool_size, 3)
        self.assertGreaterEqual(status["payload"]["counts"].get("ready", 0), 3)

        # Request an environment
        req_result = self.daemon.request_environment("integration-test-session")
        self.assertEqual(req_result["status"], "ok")
        env_id = req_result["payload"]["environment_id"]

        # Verify environment is assigned
        env_status = self.daemon.get_environment_status(env_id)
        self.assertEqual(env_status["status"], "ok")
        self.assertEqual(env_status["payload"]["status"], "assigned")

        # Pool should have one less ready
        status_after_assign = self.daemon.get_pool_status()
        self.assertEqual(status_after_assign["payload"]["counts"].get("assigned", 0), 1)
        self.assertEqual(status_after_assign["payload"]["counts"].get("ready", 0), initial_pool_size - 1)

        # Release the environment
        rel_result = self.daemon.release_environment(env_id)
        self.assertEqual(rel_result["status"], "ok")

        # Environment should be draining, then terminated
        time.sleep(1)  # Allow reconciliation
        env_status_after_release = self.daemon.get_environment_status(env_id)
        # May be draining or terminated depending on timing
        self.assertIn(env_status_after_release["payload"]["status"], ["draining", "terminated"])

        # Pool should replenish
        final_status = self.daemon.get_pool_status()
        self.assertGreaterEqual(final_status["payload"]["counts"].get("ready", 0), 3)

        # Shutdown should terminate all containers
        # Track containers before shutdown
        client = self.daemon.provider.client
        containers_before = set()
        for env in self.daemon.pool.environments.values():
            try:
                container = client.containers.get(env.environment_id)
                containers_before.add(container.id)
            except:
                pass

        self.daemon.shutdown()

        # Verify containers are terminated
        time.sleep(1)  # Allow termination
        for container_id in containers_before:
            try:
                container = client.containers.get(container_id)
                self.fail(f"Container {container_id} was not terminated")
            except NotFound:
                # Expected - container terminated
                pass

    def test_configuration_from_environment(self):
        """Test that daemon reads configuration from environment variables."""
        import os
        old_env = os.environ.copy()
        try:
            os.environ['FORGE_HARBOR_POOL_SIZE'] = '2'
            os.environ['FORGE_HARBOR_MIN_READY'] = '1'
            os.environ['FORGE_HARBOR_HEARTBEAT_INTERVAL_MS'] = '20000'

            daemon = ForgeHarborDaemon(use_mock_provider=True)
            self.assertEqual(daemon.config['pool_size'], 2)
            self.assertEqual(daemon.config['min_ready'], 1)
            self.assertEqual(daemon.config['heartbeat_interval_ms'], 20000)
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def test_error_handling_invalid_environment_id(self):
        """Test error handling for invalid environment IDs."""
        self.daemon.start()
        time.sleep(1)

        # Release nonexistent environment
        result = self.daemon.release_environment("invalid-id")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "ENVIRONMENT_NOT_FOUND")

        # Get status of nonexistent
        result = self.daemon.get_environment_status("invalid-id")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "ENVIRONMENT_NOT_FOUND")

    def test_pool_metrics_calculation(self):
        """Test pool metrics are calculated correctly."""
        self.daemon.start()
        time.sleep(1)

        # Initially no assigned
        status = self.daemon.get_pool_status()
        self.assertEqual(status["payload"]["utilization_rate"], 0.0)

        # Assign one
        req_result = self.daemon.request_environment("test-session")
        self.assertEqual(req_result["status"], "ok")

        status = self.daemon.get_pool_status()
        pool_size = status["payload"]["pool_size"]
        assigned = status["payload"]["counts"].get("assigned", 0)
        self.assertEqual(status["payload"]["utilization_rate"], assigned / pool_size)

    def test_health_endpoint_comprehensive(self):
        """Test health endpoint provides comprehensive status."""
        self.daemon.start()
        time.sleep(1)

        health = self.daemon.health()
        self.assertEqual(health["status"], "ok")
        payload = health["payload"]
        self.assertIn("healthy", payload)
        self.assertIn("pool_status", payload)
        self.assertIn("heartbeat_running", payload)
        self.assertIn("uptime_seconds", payload)

        # Should be healthy
        self.assertTrue(payload["healthy"])
        self.assertTrue(payload["heartbeat_running"])

    def test_daemon_restarts_gracefully(self):
        """Test daemon can be restarted after shutdown."""
        self.daemon.start()
        time.sleep(1)
        self.daemon.shutdown()

        # Restart
        self.daemon.start()
        time.sleep(1)

        # Should work again
        status = self.daemon.get_pool_status()
        self.assertEqual(status["status"], "ok")

        self.daemon.shutdown()