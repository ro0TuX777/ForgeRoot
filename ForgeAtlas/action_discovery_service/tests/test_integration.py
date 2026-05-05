"""ForgeAtlas — Integration tests (Phase 4, P2-5 + P2-6).

Covers:
- P2-5: ForgeWorks importlib pattern — spec_from_file_location → module_from_spec →
        exec_module → run() and health() callable on a loaded catalog.
- P2-6: Response shape matches CONCORD v0.4 ActionDiscoveryResponse contract:
        available_actions, filtered_by, total_available, recommendation, catalog_version
        all present; no authoritative_for_mutation field anywhere.
"""

from __future__ import annotations

import importlib.util
import pathlib
from typing import Any, Dict

import pytest

# ── Locate run.py (works from any working directory) ─────────────────────────

_RUN_PY = pathlib.Path(__file__).parents[2] / "action_discovery_service" / "run.py"

# ── ForgeWorks importlib helper (mirrors _import_fs_module pattern) ───────────


def _load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Shared capability sets ────────────────────────────────────────────────────

_CAP_T4_ALL = {
    "allowed_action_families": [],
    "restricted_resource_types": [],
    "trust_tier": "T4",
}

_CAP_T2_MUTATE = {
    "allowed_action_families": ["mutate"],
    "restricted_resource_types": [],
    "trust_tier": "T2",
}


# ── P2-5: Importlib pattern ───────────────────────────────────────────────────


class TestImportlibPattern:
    """ForgeWorks-style importlib import must work end-to-end (P2-5)."""

    def test_run_callable_via_importlib(self):
        mod = _load_module("forge_atlas_integ", _RUN_PY)
        result = mod.run(
            query={"resource_type": "change_request", "action_family": "mutate"},
            capability_set=_CAP_T2_MUTATE,
        )
        assert result["status"] == "ok"

    def test_health_callable_via_importlib(self):
        mod = _load_module("forge_atlas_integ_health", _RUN_PY)
        h = mod.health()
        assert h["status"] in ("healthy", "degraded", "unhealthy")

    def test_importlib_returns_dict_not_raises(self):
        mod = _load_module("forge_atlas_integ_safe", _RUN_PY)
        result = mod.run(query="malformed", capability_set=None)
        assert isinstance(result, dict)
        assert "status" in result

    def test_importlib_run_catalog_loaded(self):
        """Catalog must be loaded — response must not be CATALOG_EMPTY."""
        mod = _load_module("forge_atlas_integ_catalog", _RUN_PY)
        result = mod.run(
            query={"resource_type": "change_request"},
            capability_set=_CAP_T4_ALL,
        )
        # Must not be a catalog error
        if result["status"] == "error":
            assert result["error"]["code"] != "CATALOG_EMPTY", (
                f"Catalog is empty: {result}"
            )
        else:
            assert result["status"] == "ok"

    def test_importlib_semantic_query(self):
        """Semantic path (task_context) must work via importlib."""
        mod = _load_module("forge_atlas_integ_semantic", _RUN_PY)
        result = mod.run(
            query={"task_context": "approve a change request"},
            capability_set=_CAP_T4_ALL,
        )
        assert result["status"] == "ok"
        assert "available_actions" in result["payload"]


# ── P2-6: Response shape ──────────────────────────────────────────────────────


class TestResponseShape:
    """Response must match CONCORD v0.4 ActionDiscoveryResponse contract (P2-6)."""

    def _ok_payload(self) -> Dict[str, Any]:
        from action_discovery_service.run import run
        result = run(
            query={"resource_type": "change_request"},
            capability_set=_CAP_T4_ALL,
        )
        assert result["status"] == "ok", f"Expected ok, got: {result}"
        return result["payload"]

    def test_available_actions_present(self):
        assert "available_actions" in self._ok_payload()

    def test_filtered_by_present(self):
        assert "filtered_by" in self._ok_payload()

    def test_total_available_present(self):
        assert "total_available" in self._ok_payload()

    def test_recommendation_key_present(self):
        # Key must exist even when None
        assert "recommendation" in self._ok_payload()

    def test_catalog_version_present(self):
        assert "catalog_version" in self._ok_payload()

    def test_catalog_version_is_sha256(self):
        assert self._ok_payload()["catalog_version"].startswith("sha256:")

    def test_no_authoritative_for_mutation_in_payload(self):
        payload = self._ok_payload()
        assert "authoritative_for_mutation" not in payload

    def test_no_authoritative_for_mutation_in_actions(self):
        actions = self._ok_payload()["available_actions"]
        assert len(actions) > 0
        for action in actions:
            assert "authoritative_for_mutation" not in action

    def test_available_actions_is_list(self):
        assert isinstance(self._ok_payload()["available_actions"], list)

    def test_total_available_is_int(self):
        assert isinstance(self._ok_payload()["total_available"], int)

    def test_action_shape_has_required_fields(self):
        actions = self._ok_payload()["available_actions"]
        assert len(actions) > 0
        for action in actions:
            for field in ("action_name", "resource_type", "action_family",
                          "risk_level", "description", "guard_summary"):
                assert field in action, f"action missing field: {field}"

    def test_filtered_by_has_session_id(self):
        assert "session_id" in self._ok_payload()["filtered_by"]

    def test_filtered_by_has_capability_set_id(self):
        assert "capability_set_id" in self._ok_payload()["filtered_by"]

    def test_semantic_response_shape(self):
        """Semantic path response must also match the contract."""
        from action_discovery_service.run import run
        result = run(
            query={"task_context": "submit a change request for review"},
            capability_set=_CAP_T2_MUTATE,
        )
        assert result["status"] == "ok"
        payload = result["payload"]
        for key in ("available_actions", "filtered_by", "total_available",
                    "recommendation", "catalog_version"):
            assert key in payload, f"semantic response missing: {key}"
        assert "authoritative_for_mutation" not in payload

    def test_semantic_filtered_by_has_semantic_flag(self):
        """filtered_by.semantic_search must be True on semantic path."""
        from action_discovery_service.run import run, _semantic
        if not _semantic.enabled:
            pytest.skip("Semantic search not available")
        result = run(
            query={"task_context": "submit a change request"},
            capability_set=_CAP_T2_MUTATE,
        )
        assert result["status"] == "ok"
        assert result["payload"]["filtered_by"].get("semantic_search") is True

    def test_error_envelope_shape(self):
        from action_discovery_service.run import run
        result = run(query={}, capability_set=None)
        assert result["status"] == "error"
        assert set(result["error"].keys()) >= {"code", "message", "stage", "details"}
        assert "authoritative_for_mutation" not in result


# ── End-to-end action family coverage ────────────────────────────────────────


class TestEndToEndCoverage:
    """Verify all action families reachable through the service."""

    def test_mutate_actions_reachable(self):
        from action_discovery_service.run import run
        result = run(
            query={"resource_type": "change_request", "action_family": "mutate"},
            capability_set=_CAP_T2_MUTATE,
        )
        assert result["status"] == "ok"
        assert len(result["payload"]["available_actions"]) > 0

    def test_approve_actions_reachable(self):
        from action_discovery_service.run import run
        cap = {"allowed_action_families": ["approve"], "restricted_resource_types": [], "trust_tier": "T3"}
        result = run(
            query={"resource_type": "change_request", "action_family": "approve"},
            capability_set=cap,
        )
        assert result["status"] == "ok"
        assert len(result["payload"]["available_actions"]) > 0

    def test_deploy_actions_reachable(self):
        from action_discovery_service.run import run
        cap = {"allowed_action_families": ["deploy"], "restricted_resource_types": [], "trust_tier": "T4"}
        result = run(
            query={"resource_type": "change_request", "action_family": "deploy"},
            capability_set=cap,
        )
        assert result["status"] == "ok"
        assert len(result["payload"]["available_actions"]) > 0

    def test_total_catalog_size(self):
        """T4-unrestricted cap should see all 10 change_request actions."""
        from action_discovery_service.run import run
        result = run(
            query={"resource_type": "change_request", "max_results": 50},
            capability_set=_CAP_T4_ALL,
        )
        assert result["status"] == "ok"
        assert result["payload"]["total_available"] == 10
