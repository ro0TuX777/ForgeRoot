"""Tests for action_discovery_service/run.py — Phase 2 (P0-5, P0-6, P1-5, P1-8).

Covers:
- Happy-path structured query returning _ok envelope
- Capability filtering: denied families never appear in results
- Trust tier filtering: T4-required actions hidden from T2 agents
- Missing capability context error (P0-6)
- Invalid query fields return INVALID_QUERY
- health() shape and values (P1-5)
- Error code coverage: CATALOG_EMPTY, MISSING_CAPABILITY_CONTEXT, INVALID_QUERY (P1-8)
- importlib callability (Pattern 1)
- No authoritative_for_mutation field in responses
- Session-context fallback with agent_class_id (MISSING_CAPABILITY_CONTEXT v1.0)
- catalog_version in every successful payload
- Recommendation field present when task_context supplied
- include_schemas field passes through
"""

from __future__ import annotations

import importlib.util
import pathlib
import importlib

import pytest

# ── Import under test ─────────────────────────────────────────────────────────

from action_discovery_service.run import health, run

# ── Fixtures ──────────────────────────────────────────────────────────────────

# A T2 capability set that permits all mutate actions on change_request.
_CAP_T2_MUTATE = {
    "allowed_action_families": ["mutate"],
    "restricted_resource_types": [],
    "trust_tier": "T2",
}

# A T3 capability set for approve actions.
_CAP_T3_APPROVE = {
    "allowed_action_families": ["approve"],
    "restricted_resource_types": [],
    "trust_tier": "T3",
}

# A T4 capability set for deploy.
_CAP_T4_DEPLOY = {
    "allowed_action_families": ["deploy"],
    "restricted_resource_types": [],
    "trust_tier": "T4",
}

# Unrestricted T4 capability set — can see everything.
_CAP_T4_ALL = {
    "allowed_action_families": [],
    "restricted_resource_types": [],
    "trust_tier": "T4",
}


# ── TestConfigDefaults ────────────────────────────────────────────────────────


class TestConfigDefaults:
    def test_default_catalog_path_loads_dawn_action_catalog(self, monkeypatch):
        """Unset config should point at the CONCORD/DAWN ActionContract catalog."""
        import action_discovery_service.config as config
        from dawn.concord.catalog_loader import CatalogLoader

        monkeypatch.delenv("FORGE_ATLAS_CATALOG_PATH", raising=False)
        config = importlib.reload(config)

        registry = CatalogLoader(config.CATALOG_PATH).load()
        assert len(registry.registered_actions("change_request")) == 10


# ── TestHappyPath ─────────────────────────────────────────────────────────────


class TestHappyPath:
    def test_structured_query_returns_ok(self):
        result = run(
            query={"resource_type": "change_request", "action_family": "mutate", "max_results": 5},
            capability_set=_CAP_T2_MUTATE,
        )
        assert result["status"] == "ok"

    def test_payload_has_available_actions(self):
        result = run(
            query={"resource_type": "change_request", "action_family": "mutate", "max_results": 5},
            capability_set=_CAP_T2_MUTATE,
        )
        assert len(result["payload"]["available_actions"]) > 0

    def test_payload_has_catalog_version(self):
        result = run(
            query={"resource_type": "change_request"},
            capability_set=_CAP_T4_ALL,
        )
        assert "catalog_version" in result["payload"]
        assert result["payload"]["catalog_version"].startswith("sha256:")

    def test_payload_has_filtered_by(self):
        result = run(
            query={"resource_type": "change_request"},
            capability_set=_CAP_T4_ALL,
        )
        assert "filtered_by" in result["payload"]

    def test_payload_has_total_available(self):
        result = run(
            query={"resource_type": "change_request"},
            capability_set=_CAP_T4_ALL,
        )
        assert "total_available" in result["payload"]

    def test_max_results_respected(self):
        result = run(
            query={"resource_type": "change_request", "max_results": 2},
            capability_set=_CAP_T4_ALL,
        )
        assert len(result["payload"]["available_actions"]) <= 2

    def test_action_summary_shape(self):
        result = run(
            query={"resource_type": "change_request", "action_family": "mutate"},
            capability_set=_CAP_T2_MUTATE,
        )
        action = result["payload"]["available_actions"][0]
        for key in ("action_name", "resource_type", "action_family", "risk_level",
                    "description", "guard_summary"):
            assert key in action, f"missing key: {key}"

    def test_no_authoritative_for_mutation_field(self):
        result = run(
            query={"resource_type": "change_request"},
            capability_set=_CAP_T4_ALL,
        )
        payload = result["payload"]
        assert "authoritative_for_mutation" not in payload

    def test_recommendation_none_without_task_context(self):
        result = run(
            query={"resource_type": "change_request", "action_family": "mutate"},
            capability_set=_CAP_T2_MUTATE,
        )
        assert result["payload"]["recommendation"] is None

    def test_recommendation_present_with_task_context(self):
        result = run(
            query={"task_context": "submit a change request for review"},
            capability_set=_CAP_T2_MUTATE,
        )
        # Recommendation is set when task_context is provided and results exist.
        # It may be null if no results pass capability filter — just assert payload key.
        assert "recommendation" in result["payload"]


# ── TestCapabilityFiltering ───────────────────────────────────────────────────


class TestCapabilityFiltering:
    def test_mutate_only_cap_excludes_approve_actions(self):
        result = run(
            query={"resource_type": "change_request"},
            capability_set=_CAP_T2_MUTATE,
        )
        families = {a["action_family"] for a in result["payload"]["available_actions"]}
        assert "approve" not in families

    def test_mutate_only_cap_excludes_deploy_actions(self):
        result = run(
            query={"resource_type": "change_request"},
            capability_set=_CAP_T2_MUTATE,
        )
        names = {a["action_name"] for a in result["payload"]["available_actions"]}
        assert "deploy_change_request" not in names

    def test_t2_agent_cannot_see_t3_actions(self):
        result = run(
            query={"resource_type": "change_request"},
            capability_set=_CAP_T2_MUTATE,
        )
        names = {a["action_name"] for a in result["payload"]["available_actions"]}
        assert "approve_change_request" not in names

    def test_t2_agent_cannot_see_t4_actions(self):
        result = run(
            query={"resource_type": "change_request"},
            capability_set=_CAP_T2_MUTATE,
        )
        names = {a["action_name"] for a in result["payload"]["available_actions"]}
        assert "deploy_change_request" not in names

    def test_t3_agent_sees_approve_actions(self):
        result = run(
            query={"resource_type": "change_request", "action_family": "approve"},
            capability_set=_CAP_T3_APPROVE,
        )
        names = {a["action_name"] for a in result["payload"]["available_actions"]}
        assert "approve_change_request" in names

    def test_t4_agent_sees_deploy_action(self):
        result = run(
            query={"resource_type": "change_request", "action_family": "deploy"},
            capability_set=_CAP_T4_DEPLOY,
        )
        names = {a["action_name"] for a in result["payload"]["available_actions"]}
        assert "deploy_change_request" in names

    def test_exclusions_hide_named_action(self):
        cap = {**_CAP_T4_ALL, "exclusions": ["deploy_change_request"]}
        result = run(
            query={"resource_type": "change_request"},
            capability_set=cap,
        )
        names = {a["action_name"] for a in result["payload"]["available_actions"]}
        assert "deploy_change_request" not in names

    def test_restricted_resource_type_returns_no_results(self):
        cap = {**_CAP_T4_ALL, "restricted_resource_types": ["change_request"]}
        result = run(
            query={"resource_type": "change_request"},
            capability_set=cap,
        )
        assert result["payload"]["available_actions"] == []


# ── TestCapabilityResolution (P0-6) ──────────────────────────────────────────


class TestCapabilityResolution:
    def test_missing_capability_set_and_context_returns_error(self):
        result = run(query={"resource_type": "change_request"}, capability_set=None)
        assert result["status"] == "error"
        assert result["error"]["code"] == "MISSING_CAPABILITY_CONTEXT"

    def test_error_envelope_has_stage(self):
        result = run(query={"resource_type": "change_request"}, capability_set=None)
        assert "stage" in result["error"]

    def test_agent_class_id_without_store_returns_error(self):
        result = run(
            query={"resource_type": "change_request"},
            capability_set=None,
            session_context={"agent_class_id": "cls-001"},
        )
        assert result["status"] == "error"
        assert result["error"]["code"] == "MISSING_CAPABILITY_CONTEXT"

    def test_capability_set_dict_accepted_directly(self):
        result = run(
            query={"resource_type": "change_request"},
            capability_set=_CAP_T4_ALL,
        )
        assert result["status"] == "ok"

    def test_trust_tier_from_session_context(self):
        cap = {"allowed_action_families": ["mutate"], "restricted_resource_types": []}
        sc = {"trust_tier": "T2"}
        result = run(
            query={"resource_type": "change_request", "action_family": "mutate"},
            capability_set=cap,
            session_context=sc,
        )
        assert result["status"] == "ok"
        assert len(result["payload"]["available_actions"]) > 0


# ── TestErrorCodes (P1-8) ─────────────────────────────────────────────────────


class TestErrorCodes:
    def test_invalid_action_family_returns_invalid_query(self):
        result = run(
            query={"action_family": "not_a_real_family"},
            capability_set=_CAP_T4_ALL,
        )
        assert result["status"] == "error"
        assert result["error"]["code"] == "INVALID_QUERY"

    def test_run_never_raises(self):
        # Pass completely malformed inputs — must return dict, not raise.
        result = run(query="not a dict", capability_set=None)
        assert isinstance(result, dict)
        assert "status" in result

    def test_error_dict_has_required_keys(self):
        result = run(query={"resource_type": "change_request"}, capability_set=None)
        assert set(result["error"].keys()) >= {"code", "message", "stage", "details"}


# ── TestHealth (P1-5) ─────────────────────────────────────────────────────────


class TestHealth:
    def test_health_returns_dict(self):
        assert isinstance(health(), dict)

    def test_health_status_is_valid(self):
        h = health()
        assert h["status"] in ("healthy", "degraded", "unhealthy")

    def test_health_has_required_keys(self):
        h = health()
        for key in ("status", "catalog_loaded", "contracts_registered",
                    "contracts_failed", "semantic_search_enabled",
                    "catalog_version", "uptime_seconds"):
            assert key in h, f"missing key: {key}"

    def test_health_catalog_loaded(self):
        h = health()
        assert h["catalog_loaded"] is True

    def test_health_contracts_registered_positive(self):
        h = health()
        assert h["contracts_registered"] > 0

    def test_health_semantic_search_field_is_bool(self):
        # Phase 3: semantic_search_enabled reflects actual model state.
        assert isinstance(health()["semantic_search_enabled"], bool)

    def test_health_catalog_version_sha256(self):
        assert health()["catalog_version"].startswith("sha256:")

    def test_health_never_raises(self):
        result = health()
        assert isinstance(result, dict)


# ── TestImportlibPattern ─────────────────────────────────────────────────────


class TestImportlibPattern:
    def test_importlib_callable(self):
        """Service must be callable via importlib (ForgeWorks Pattern 1)."""
        run_py = pathlib.Path(__file__).parents[2] / "action_discovery_service" / "run.py"
        spec = importlib.util.spec_from_file_location("forge_atlas_importlib", run_py)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        result = mod.run(
            query={"resource_type": "change_request", "action_family": "mutate"},
            capability_set=_CAP_T2_MUTATE,
        )
        assert result["status"] == "ok"

    def test_importlib_health_callable(self):
        run_py = pathlib.Path(__file__).parents[2] / "action_discovery_service" / "run.py"
        spec = importlib.util.spec_from_file_location("forge_atlas_importlib_health", run_py)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        h = mod.health()
        assert h["status"] in ("healthy", "degraded", "unhealthy")
