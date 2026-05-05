import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
from unittest.mock import patch
from datetime import datetime
from forgeharbor_types import ExecutionEnvironment, EnvironmentStatus
from lifecycle_engine import (
    can_transition, provision, on_warm_complete, on_provision_failure,
    assign, begin_drain, on_drain_complete, recycle, get_blocking_intents
)

class TestLifecycleEngine(unittest.TestCase):

    def setUp(self):
        self.env = ExecutionEnvironment(
            environment_id="test-env-1",
            status=EnvironmentStatus.COLD
        )

    def test_can_transition_valid(self):
        """Test all valid transitions return True"""
        valid_transitions = [
            (EnvironmentStatus.COLD, EnvironmentStatus.WARMING),
            (EnvironmentStatus.WARMING, EnvironmentStatus.READY),
            (EnvironmentStatus.WARMING, EnvironmentStatus.TERMINATED),
            (EnvironmentStatus.READY, EnvironmentStatus.ASSIGNED),
            (EnvironmentStatus.READY, EnvironmentStatus.DRAINING),
            (EnvironmentStatus.ASSIGNED, EnvironmentStatus.DRAINING),
            (EnvironmentStatus.DRAINING, EnvironmentStatus.TERMINATED),
            (EnvironmentStatus.UNHEALTHY, EnvironmentStatus.TERMINATED),
            (EnvironmentStatus.TERMINATED, EnvironmentStatus.COLD),
        ]
        for from_status, to_status in valid_transitions:
            with self.subTest(from_status=from_status, to_status=to_status):
                self.assertTrue(can_transition(from_status, to_status))

    def test_can_transition_invalid(self):
        """Test invalid transitions return False"""
        invalid_transitions = [
            (EnvironmentStatus.COLD, EnvironmentStatus.READY),
            (EnvironmentStatus.READY, EnvironmentStatus.WARMING),
            (EnvironmentStatus.ASSIGNED, EnvironmentStatus.READY),
            (EnvironmentStatus.TERMINATED, EnvironmentStatus.ASSIGNED),
            (EnvironmentStatus.UNHEALTHY, EnvironmentStatus.ASSIGNED),
        ]
        for from_status, to_status in invalid_transitions:
            with self.subTest(from_status=from_status, to_status=to_status):
                self.assertFalse(can_transition(from_status, to_status))

    def test_provision_valid(self):
        """Test COLD -> WARMING"""
        result = provision(self.env)
        self.assertIsInstance(result, ExecutionEnvironment)
        self.assertEqual(result.status, EnvironmentStatus.WARMING)

    def test_provision_invalid(self):
        """Test invalid transition from READY"""
        self.env.status = EnvironmentStatus.READY
        result = provision(self.env)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "INVALID_TRANSITION")

    def test_on_warm_complete_valid(self):
        """Test WARMING -> READY"""
        self.env.status = EnvironmentStatus.WARMING
        result = on_warm_complete(self.env)
        self.assertIsInstance(result, ExecutionEnvironment)
        self.assertEqual(result.status, EnvironmentStatus.READY)

    def test_on_warm_complete_invalid(self):
        """Test invalid transition from COLD"""
        result = on_warm_complete(self.env)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "error")

    def test_on_provision_failure_valid(self):
        """Test WARMING -> TERMINATED"""
        self.env.status = EnvironmentStatus.WARMING
        result = on_provision_failure(self.env)
        self.assertIsInstance(result, ExecutionEnvironment)
        self.assertEqual(result.status, EnvironmentStatus.TERMINATED)

    def test_on_provision_failure_invalid(self):
        """Test invalid transition from READY"""
        self.env.status = EnvironmentStatus.READY
        result = on_provision_failure(self.env)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "error")

    def test_assign_valid(self):
        """Test READY -> ASSIGNED, sets session_id and assigned_at"""
        self.env.status = EnvironmentStatus.READY
        session_id = "sess-1"
        result = assign(self.env, session_id)
        self.assertIsInstance(result, ExecutionEnvironment)
        self.assertEqual(result.status, EnvironmentStatus.ASSIGNED)
        self.assertEqual(result.assigned_session_id, session_id)
        self.assertIsInstance(result.assigned_at, datetime)

    def test_assign_invalid(self):
        """Test invalid transition from COLD"""
        result = assign(self.env, "sess-1")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "error")

    def test_begin_drain_from_ready(self):
        """Test READY -> DRAINING"""
        self.env.status = EnvironmentStatus.READY
        result = begin_drain(self.env)
        self.assertIsInstance(result, ExecutionEnvironment)
        self.assertEqual(result.status, EnvironmentStatus.DRAINING)

    def test_begin_drain_from_assigned_no_blocking(self):
        """Test ASSIGNED -> DRAINING when no blocking intents"""
        self.env.status = EnvironmentStatus.ASSIGNED
        self.env.assigned_session_id = "sess-1"
        result = begin_drain(self.env)
        self.assertIsInstance(result, ExecutionEnvironment)
        self.assertEqual(result.status, EnvironmentStatus.DRAINING)

    @patch('lifecycle_engine.get_blocking_intents')
    def test_begin_drain_from_assigned_with_blocking(self, mock_get_blocking):
        """Test ASSIGNED stays ASSIGNED when blocking intents exist"""
        mock_get_blocking.return_value = [{"id": "intent-1", "status": "EXECUTING"}]
        self.env.status = EnvironmentStatus.ASSIGNED
        result = begin_drain(self.env)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "DRAIN_BLOCKED")
        self.assertEqual(result["error"]["details"]["blocking_intents_count"], 1)
        # Status should remain ASSIGNED
        self.assertEqual(self.env.status, EnvironmentStatus.ASSIGNED)

    def test_begin_drain_invalid(self):
        """Test invalid transition from COLD"""
        result = begin_drain(self.env)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "error")

    def test_on_drain_complete_valid(self):
        """Test DRAINING -> TERMINATED"""
        self.env.status = EnvironmentStatus.DRAINING
        result = on_drain_complete(self.env)
        self.assertIsInstance(result, ExecutionEnvironment)
        self.assertEqual(result.status, EnvironmentStatus.TERMINATED)

    def test_on_drain_complete_invalid(self):
        """Test invalid transition from READY"""
        self.env.status = EnvironmentStatus.READY
        result = on_drain_complete(self.env)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "error")

    def test_recycle_valid(self):
        """Test TERMINATED -> new COLD environment with new ID"""
        self.env.status = EnvironmentStatus.TERMINATED
        original_id = self.env.environment_id
        result = recycle(self.env)
        self.assertIsInstance(result, ExecutionEnvironment)
        self.assertEqual(result.status, EnvironmentStatus.COLD)
        self.assertNotEqual(result.environment_id, original_id)
        # Check other fields are copied
        self.assertEqual(result.resource_spec, self.env.resource_spec)
        self.assertEqual(result.preload_manifest, self.env.preload_manifest)

    def test_recycle_invalid(self):
        """Test invalid transition from READY"""
        self.env.status = EnvironmentStatus.READY
        result = recycle(self.env)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "error")

if __name__ == '__main__':
    unittest.main()