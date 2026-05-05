"""Tests for semantic_search.py and semantic query path in run.py — Phase 3.

P1-1: SemanticSearch class — model loading, embed_catalog
P1-2: rank_by_similarity — ordering, threshold, empty inputs
P1-3: Integration into run() — task_context triggers semantic path
P1-4: Graceful degradation — model unavailable, structured path survives

Test strategy:
- SemanticSearch unit tests use the real model (all-MiniLM-L6-v2, loaded once).
- Degradation tests use a fresh SemanticSearch with a bad model name.
- run() integration tests use the module-level singleton (model already loaded).
- Security invariant: capability filter always runs after semantic ranking.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────

_DAWN_ROOT = Path(__file__).resolve().parents[3] / "DAWN"
if str(_DAWN_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAWN_ROOT))

from dawn.concord.catalog_loader import CatalogLoader
from dawn.concord.types.entities import CapabilitySet
from dawn.concord.types.enums import TrustTier

from action_discovery_service.run import health, run
from action_discovery_service.semantic_search import SemanticSearch

# ── Real catalog fixture ──────────────────────────────────────────────────────

_REAL_CATALOG = _DAWN_ROOT / "action_catalogs"


@pytest.fixture(scope="module")
def loaded_semantic():
    """SemanticSearch with model loaded + real catalog embedded — shared across tests."""
    loader = CatalogLoader(_REAL_CATALOG)
    registry = loader.load()
    ss = SemanticSearch("all-MiniLM-L6-v2")
    ss.load_model()
    ss.embed_catalog(registry)
    return ss, registry


@pytest.fixture(scope="module")
def all_actions(loaded_semantic):
    _, registry = loaded_semantic
    candidates = []
    for rt in registry.registered_resource_types():
        for name in registry.registered_actions(rt):
            candidates.append(registry.lookup_action(rt, name))
    return candidates


# ── Capability set helpers ────────────────────────────────────────────────────

_CAP_T4_ALL = {
    "allowed_action_families": [],
    "restricted_resource_types": [],
    "trust_tier": "T4",
}

_CAP_T3_APPROVE_MUTATE = {
    "allowed_action_families": ["mutate", "approve"],
    "restricted_resource_types": [],
    "trust_tier": "T3",
}

_CAP_T2_MUTATE = {
    "allowed_action_families": ["mutate"],
    "restricted_resource_types": [],
    "trust_tier": "T2",
}


# ── TestSemanticSearchModelLoading (P1-1) ─────────────────────────────────────


class TestSemanticSearchModelLoading:
    def test_enabled_false_before_load(self):
        ss = SemanticSearch("all-MiniLM-L6-v2")
        assert ss.enabled is False

    def test_load_model_returns_true_on_success(self):
        ss = SemanticSearch("all-MiniLM-L6-v2")
        result = ss.load_model()
        assert result is True
        assert ss.enabled is True

    def test_load_model_returns_false_on_bad_model(self):
        ss = SemanticSearch("nonexistent-model-xyz-12345")
        result = ss.load_model()
        assert result is False
        assert ss.enabled is False

    def test_embed_catalog_is_noop_when_disabled(self):
        loader = CatalogLoader(_REAL_CATALOG)
        registry = loader.load()
        ss = SemanticSearch("nonexistent-model-xyz-12345")
        ss.load_model()  # will fail → enabled=False
        ss.embed_catalog(registry)  # must not raise
        assert ss._embeddings == {}

    def test_embed_catalog_populates_embeddings(self, loaded_semantic):
        ss, _ = loaded_semantic
        assert len(ss._embeddings) == 10  # 10 change_request actions

    def test_embedding_keys_are_resource_type_slash_name(self, loaded_semantic):
        ss, _ = loaded_semantic
        assert "change_request/approve_change_request" in ss._embeddings
        assert "change_request/deploy_change_request" in ss._embeddings


# ── TestRankBySimilarity (P1-2) ───────────────────────────────────────────────


class TestRankBySimilarity:
    def test_returns_list(self, loaded_semantic, all_actions):
        ss, _ = loaded_semantic
        result = ss.rank_by_similarity("deploy change request", all_actions)
        assert isinstance(result, list)

    def test_empty_candidates_returns_empty(self, loaded_semantic):
        ss, _ = loaded_semantic
        assert ss.rank_by_similarity("deploy", []) == []

    def test_threshold_zero_returns_all_candidates(self, loaded_semantic, all_actions):
        ss, _ = loaded_semantic
        result = ss.rank_by_similarity("deploy change request", all_actions, threshold=0.0)
        assert len(result) == len(all_actions)

    def test_threshold_one_returns_empty_or_one(self, loaded_semantic, all_actions):
        ss, _ = loaded_semantic
        # Threshold of 1.0 — only perfect self-matches; natural-language query won't hit it.
        result = ss.rank_by_similarity("deploy change request to production", all_actions, threshold=1.0)
        assert len(result) == 0

    def test_ordering_most_similar_first(self, loaded_semantic, all_actions):
        ss, _ = loaded_semantic
        result = ss.rank_by_similarity("approve the change request", all_actions, threshold=0.0)
        if len(result) >= 2:
            score_0 = ss.similarity_score("approve the change request", result[0])
            score_1 = ss.similarity_score("approve the change request", result[1])
            assert score_0 >= score_1

    def test_deploy_query_ranks_deploy_high(self, loaded_semantic, all_actions):
        ss, _ = loaded_semantic
        result = ss.rank_by_similarity("deploy to production environment", all_actions, threshold=0.0)
        names = [ac.action_name for ac in result]
        assert names.index("deploy_change_request") < len(names) // 2

    def test_review_query_ranks_approve_high(self, loaded_semantic, all_actions):
        ss, _ = loaded_semantic
        result = ss.rank_by_similarity(
            "review and approve the change request for production", all_actions, threshold=0.0
        )
        names = [ac.action_name for ac in result]
        assert "approve_change_request" in names[:5]

    def test_empty_task_context_returns_candidates_unchanged(self, loaded_semantic, all_actions):
        ss, _ = loaded_semantic
        result = ss.rank_by_similarity("", all_actions, threshold=0.3)
        assert len(result) == len(all_actions)

    def test_disabled_ss_returns_candidates_in_original_order(self, all_actions):
        ss = SemanticSearch("nonexistent-model-xyz")
        ss.load_model()  # fails → enabled=False
        result = ss.rank_by_similarity("deploy", all_actions, threshold=0.3)
        assert result == list(all_actions)

    def test_similarity_score_returns_float_when_enabled(self, loaded_semantic):
        ss, registry = loaded_semantic
        ac = registry.lookup_action("change_request", "deploy_change_request")
        score = ss.similarity_score("deploy", ac)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_similarity_score_returns_none_when_disabled(self, loaded_semantic):
        ss, registry = loaded_semantic
        ac = registry.lookup_action("change_request", "deploy_change_request")
        disabled_ss = SemanticSearch("bad-model")
        disabled_ss.load_model()
        score = disabled_ss.similarity_score("deploy", ac)
        assert score is None


# ── TestSemanticIntegrationInRun (P1-3) ──────────────────────────────────────


class TestSemanticIntegrationInRun:
    def test_task_context_triggers_semantic_path(self):
        result = run(
            query={"task_context": "get a code change reviewed and approved", "max_results": 5},
            capability_set=_CAP_T3_APPROVE_MUTATE,
        )
        assert result["status"] == "ok"
        assert result["payload"]["filtered_by"].get("semantic_search") is True

    def test_semantic_results_non_empty_for_relevant_query(self):
        result = run(
            query={"task_context": "review and approve a change", "max_results": 5},
            capability_set=_CAP_T3_APPROVE_MUTATE,
        )
        assert len(result["payload"]["available_actions"]) > 0

    def test_semantic_approve_query_includes_approve_action(self):
        result = run(
            query={"task_context": "approve or reject a change request under review"},
            capability_set=_CAP_T3_APPROVE_MUTATE,
        )
        names = [a["action_name"] for a in result["payload"]["available_actions"]]
        assert "approve_change_request" in names or "reject_change_request" in names

    def test_semantic_path_includes_similarity_threshold_in_filtered_by(self):
        result = run(
            query={"task_context": "submit a code change"},
            capability_set=_CAP_T2_MUTATE,
        )
        assert "similarity_threshold" in result["payload"]["filtered_by"]

    def test_semantic_plus_resource_type_filter(self):
        result = run(
            query={
                "task_context": "deploy to production",
                "resource_type": "change_request",
            },
            capability_set=_CAP_T4_ALL,
        )
        assert result["status"] == "ok"
        for a in result["payload"]["available_actions"]:
            assert a["resource_type"] == "change_request"

    def test_semantic_plus_action_family_filter(self):
        result = run(
            query={
                "task_context": "approve the change request",
                "action_family": "approve",
            },
            capability_set=_CAP_T3_APPROVE_MUTATE,
        )
        assert result["status"] == "ok"
        for a in result["payload"]["available_actions"]:
            assert a["action_family"] == "approve"

    def test_no_task_context_uses_structured_path(self):
        result = run(
            query={"resource_type": "change_request", "action_family": "mutate"},
            capability_set=_CAP_T2_MUTATE,
        )
        assert result["status"] == "ok"
        # structured path: filtered_by does not have semantic_search key
        assert "semantic_search" not in result["payload"]["filtered_by"]

    def test_catalog_version_present_in_semantic_response(self):
        result = run(
            query={"task_context": "submit a change"},
            capability_set=_CAP_T4_ALL,
        )
        assert result["payload"]["catalog_version"].startswith("sha256:")


# ── TestSecurityInvariant ─────────────────────────────────────────────────────


class TestSecurityInvariant:
    def test_t2_agent_never_sees_deploy_via_semantic(self):
        """Capability filter runs AFTER semantic ranking — high-similarity
        actions the agent cannot use must still be excluded."""
        result = run(
            query={"task_context": "deploy change request to production environment"},
            capability_set=_CAP_T2_MUTATE,  # T2, mutate-only: cannot deploy
        )
        names = [a["action_name"] for a in result["payload"]["available_actions"]]
        assert "deploy_change_request" not in names

    def test_t2_agent_never_sees_approve_via_semantic(self):
        result = run(
            query={"task_context": "approve or reject the change request"},
            capability_set=_CAP_T2_MUTATE,
        )
        names = {a["action_name"] for a in result["payload"]["available_actions"]}
        assert "approve_change_request" not in names
        assert "reject_change_request" not in names

    def test_restricted_resource_type_excluded_even_with_semantic(self):
        cap = {**_CAP_T4_ALL, "restricted_resource_types": ["change_request"]}
        result = run(
            query={"task_context": "approve the change request"},
            capability_set=cap,
        )
        assert result["payload"]["available_actions"] == []

    def test_exclusion_respected_in_semantic_path(self):
        cap = {**_CAP_T4_ALL, "exclusions": ["deploy_change_request"]}
        result = run(
            query={"task_context": "deploy to production"},
            capability_set=cap,
        )
        names = [a["action_name"] for a in result["payload"]["available_actions"]]
        assert "deploy_change_request" not in names


# ── TestGracefulDegradation (P1-4) ────────────────────────────────────────────


class TestGracefulDegradation:
    def test_load_model_failure_leaves_enabled_false(self):
        ss = SemanticSearch("this-model-does-not-exist-xyz")
        ok = ss.load_model()
        assert ok is False
        assert ss.enabled is False

    def test_rank_by_similarity_with_disabled_ss_returns_all(self, all_actions):
        ss = SemanticSearch("bad-model")
        ss.load_model()
        result = ss.rank_by_similarity("deploy", all_actions, threshold=0.9)
        # When disabled, no threshold filtering — all returned
        assert len(result) == len(all_actions)

    def test_health_reports_semantic_enabled_correctly(self):
        h = health()
        from action_discovery_service import run as run_module
        assert h["semantic_search_enabled"] == run_module._semantic.enabled

    def test_service_returns_ok_when_semantic_disabled(self, monkeypatch):
        """Simulate model not loaded: structured path must still work."""
        from action_discovery_service import run as run_module
        original = run_module._semantic.enabled
        monkeypatch.setattr(run_module._semantic, "enabled", False)
        try:
            result = run(
                query={"resource_type": "change_request", "action_family": "mutate"},
                capability_set=_CAP_T2_MUTATE,
            )
            assert result["status"] == "ok"
        finally:
            monkeypatch.setattr(run_module._semantic, "enabled", original)

    def test_semantic_disabled_task_context_falls_back_to_keyword(self, monkeypatch):
        """When semantic is disabled, task_context falls back to keyword ranking."""
        from action_discovery_service import run as run_module
        original = run_module._semantic.enabled
        monkeypatch.setattr(run_module._semantic, "enabled", False)
        try:
            result = run(
                query={"task_context": "submit change", "action_family": "mutate"},
                capability_set=_CAP_T2_MUTATE,
            )
            # Service must not error; keyword ranking is the fallback.
            assert result["status"] == "ok"
        finally:
            monkeypatch.setattr(run_module._semantic, "enabled", original)
