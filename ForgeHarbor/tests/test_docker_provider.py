import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
from docker.errors import DockerException
from provider import ProvisionResult, HealthStatus, TerminateResult, ConnectionInfo
from docker_provider import DockerProvider
from environment_spec import EnvironmentSpec

class TestDockerProvider(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Check if Docker is available, skip tests if not."""
        try:
            cls.provider = DockerProvider()
            # Test connection
            cls.provider.client.ping()
            cls.docker_available = True
        except (DockerException, RuntimeError):
            cls.docker_available = False

    def setUp(self):
        if not self.docker_available:
            self.skipTest("Docker daemon not available")
        self.provider = DockerProvider()
        self.test_env_id = f"test-env-{id(self)}"  # Unique ID for each test

    def tearDown(self):
        """Clean up any containers created during tests."""
        if self.docker_available:
            try:
                result = self.provider.terminate(self.test_env_id)
                # Ignore result, just try to clean up
            except:
                pass

    def test_provision_valid_image(self):
        """Test provisioning with a valid image creates a running container."""
        spec = EnvironmentSpec(image="alpine:latest", environment_vars={"TEST": "value"})
        result = self.provider.provision(self.test_env_id, spec)

        self.assertIsInstance(result, ProvisionResult)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.container_id)
        self.assertIsNone(result.error)

        # Verify container is running
        health = self.provider.check_health(self.test_env_id)
        self.assertEqual(health.status, "running")

    def test_provision_invalid_image(self):
        """Test provisioning with invalid image returns error."""
        spec = EnvironmentSpec(image="nonexistent:latest")
        result = self.provider.provision(self.test_env_id, spec)

        self.assertIsInstance(result, ProvisionResult)
        self.assertFalse(result.success)
        self.assertIsNone(result.container_id)
        self.assertIsNotNone(result.error)

    def test_check_health_running(self):
        """Test health check on running container."""
        spec = EnvironmentSpec(image="alpine:latest")
        provision_result = self.provider.provision(self.test_env_id, spec)
        self.assertTrue(provision_result.success)

        health = self.provider.check_health(self.test_env_id)
        self.assertIsInstance(health, HealthStatus)
        self.assertEqual(health.status, "running")
        self.assertIn("container_id", health.details)

    def test_check_health_nonexistent(self):
        """Test health check on nonexistent container."""
        health = self.provider.check_health("nonexistent-env")
        self.assertIsInstance(health, HealthStatus)
        self.assertEqual(health.status, "error")
        self.assertEqual(health.details.get("error"), "container not found")

    def test_terminate_running_container(self):
        """Test terminating a running container."""
        spec = EnvironmentSpec(image="alpine:latest")
        provision_result = self.provider.provision(self.test_env_id, spec)
        self.assertTrue(provision_result.success)

        # Terminate
        result = self.provider.terminate(self.test_env_id)
        self.assertIsInstance(result, TerminateResult)
        self.assertTrue(result.success)
        self.assertIsNone(result.error)

        # Verify container is gone
        health = self.provider.check_health(self.test_env_id)
        self.assertEqual(health.status, "error")
        self.assertEqual(health.details.get("error"), "container not found")

    def test_terminate_nonexistent_container(self):
        """Test terminating nonexistent container (should succeed)."""
        result = self.provider.terminate("nonexistent-env")
        self.assertIsInstance(result, TerminateResult)
        self.assertTrue(result.success)

    def test_get_connection_info(self):
        """Test getting connection info for running container."""
        spec = EnvironmentSpec(image="alpine:latest")
        provision_result = self.provider.provision(self.test_env_id, spec)
        self.assertTrue(provision_result.success)

        info = self.provider.get_connection_info(self.test_env_id)
        self.assertIsInstance(info, ConnectionInfo)
        self.assertEqual(info.container_id, provision_result.container_id)
        self.assertIsInstance(info.mounts, list)

    def test_get_connection_info_nonexistent(self):
        """Test getting connection info for nonexistent container raises error."""
        with self.assertRaises(ValueError):
            self.provider.get_connection_info("nonexistent-env")

if __name__ == '__main__':
    unittest.main()