"""ForgeAtlas — ActionDiscovery Service entry point.

Callable via the importlib pattern established by ForgeWorks:

    import importlib.util
    spec = importlib.util.spec_from_file_location("forge_atlas", "run.py")
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.run(query=..., capability_set=..., session_context=...)

Public API
----------
run(query, capability_set, session_context)  → _ok / _error dict
health()                                     → health status dict

Response envelopes
------------------
Success:  {"status": "ok",    "payload": { ... }}
Failure:  {"status": "error", "error": {"code": str, "message": str,
                                        "stage": str, "details": {}}}

Security invariant
------------------
Every code path that returns actions passes through the five-check
CapabilitySet filter (is_action_permitted).  There is no unfiltered path —
semantic ranking runs BEFORE capability filtering so a high-similarity action
the agent cannot use is always excluded.

Query routing
-------------
task_context present + semantic enabled:
    1. Collect all candidates from registry (scoped by resource_type filter)
    2. rank_by_similarity → threshold-filtered, similarity-sorted list
    3. is_action_permitted filter (capability + trust tier)
    4. action_family filter
    5. Truncate to max_results; build response

task_context absent OR semantic disabled:
    execute_discovery() — structured filter path (keyword ranking fallback)
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

_LOG = logging.getLogger(__name__)

# ── Ensure DAWN is importable ─────────────────────────────────────────────────
# DAWN_ROOT env var overrides the file-relative default (used in Docker).
_DAWN_ROOT = Path(
    os.environ.get(
        "DAWN_ROOT",
        str(Path(__file__).resolve().parents[2] / "DAWN"),
    )
)
if str(_DAWN_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAWN_ROOT))

from dawn.concord.catalog_loader import CatalogLoader
from dawn.concord.discovery_kernel import (
    _action_to_summary,
    execute_discovery,
    is_action_permitted,
)
from dawn.concord.types.contracts import (
    ActionDiscoveryQuery,
    ActionDiscoveryRecommendation,
    ActionDiscoveryResponse,
)
from dawn.concord.types.entities import CapabilitySet
from dawn.concord.types.enums import ActionFamily, TrustTier

try:
    from . import config  # package import (normal usage)
except ImportError:
    import importlib.util as _ilu  # importlib direct-file import
    _spec = _ilu.spec_from_file_location(
        "config", Path(__file__).with_name("config.py")
    )
    config = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(config)

try:
    from .semantic_search import SemanticSearch  # package import
except ImportError:
    import importlib.util as _ilu2
    _spec2 = _ilu2.spec_from_file_location(
        "semantic_search", Path(__file__).with_name("semantic_search.py")
    )
    _ss_mod = _ilu2.module_from_spec(_spec2)
    _spec2.loader.exec_module(_ss_mod)
    SemanticSearch = _ss_mod.SemanticSearch

# ── Module-level startup ──────────────────────────────────────────────────────

_START_TIME: float = time.time()
_loader: CatalogLoader
_registry = None

try:
    _loader = CatalogLoader(config.CATALOG_PATH)
    _registry = _loader.load()
except FileNotFoundError as _exc:
    # Registry stays None; health() reports unhealthy.
    _loader = CatalogLoader.__new__(CatalogLoader)
    _loader.catalog_version = ""
    _loader.contracts_loaded = 0
    _loader.failures = [{"path": config.CATALOG_PATH, "error": str(_exc)}]

# Semantic search — load model then embed catalog.  Failures are non-fatal.
_semantic: SemanticSearch = SemanticSearch(config.EMBEDDING_MODEL)
_semantic.load_model()
if _semantic.enabled and _registry is not None:
    try:
        _semantic.embed_catalog(_registry)
    except Exception:
        _semantic.enabled = False

# ── Startup summary log (P1-7) ────────────────────────────────────────────────
_LOG.info(
    "ActionDiscovery startup: %d contracts loaded, %d failed, semantic search %s",
    _loader.contracts_loaded,
    len(_loader.failures),
    "enabled" if _semantic.enabled else "disabled",
)
if _loader.catalog_version:
    _LOG.info("Catalog version: %s", _loader.catalog_version)
if _loader.contracts_loaded == 0:
    _LOG.warning(
        "No contracts loaded from '%s' — service will report unhealthy.",
        config.CATALOG_PATH,
    )


# ── Trust tier mapping ────────────────────────────────────────────────────────

_TRUST_TIER_MAP: dict[str, TrustTier] = {
    "T0": TrustTier.T0_OBSERVE,
    "T0/observe": TrustTier.T0_OBSERVE,
    "T1": TrustTier.T1_PROPOSE,
    "T1/propose": TrustTier.T1_PROPOSE,
    "T2": TrustTier.T2_BOUNDED,
    "T2/bounded": TrustTier.T2_BOUNDED,
    "T3": TrustTier.T3_PRIVILEGED,
    "T3/privileged": TrustTier.T3_PRIVILEGED,
    "T4": TrustTier.T4_GOVERNED_CRITICAL,
    "T4/governed_critical": TrustTier.T4_GOVERNED_CRITICAL,
}

# ── Envelope helpers (matches ForgeWorks convention) ─────────────────────────


def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "ok", "payload": payload}


def _error(
    code: str,
    message: str,
    stage: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "status": "error",
        "error": {
            "code": code,
            "message": message,
            "stage": stage,
            "details": details or {},
        },
    }


# ── Capability resolution (P0-6) ─────────────────────────────────────────────


def _resolve_capability_set(
    capability_set: Optional[Dict[str, Any]],
    session_context: Optional[Dict[str, Any]],
) -> tuple[Optional[CapabilitySet], Optional[Dict[str, Any]]]:
    """Return (CapabilitySet, error_dict_or_None)."""
    if capability_set is not None:
        try:
            cs = _deserialise_capability_set(capability_set)
            return cs, None
        except Exception as exc:
            return None, _error(
                "INVALID_CAPABILITY_SET",
                f"capability_set could not be deserialised: {exc}",
                "capability_resolution",
            )

    if session_context is not None and session_context.get("agent_class_id"):
        return None, _error(
            "MISSING_CAPABILITY_CONTEXT",
            "agent_class_id resolution is not yet supported in v1.0. "
            "Supply capability_set directly.",
            "capability_resolution",
            {"agent_class_id": session_context["agent_class_id"]},
        )

    return None, _error(
        "MISSING_CAPABILITY_CONTEXT",
        "Either capability_set or session_context with agent_class_id is required.",
        "capability_resolution",
    )


def _deserialise_capability_set(raw: Dict[str, Any]) -> CapabilitySet:
    return CapabilitySet(
        id=raw.get("id", "caller-supplied"),
        allowed_action_families=raw.get("allowed_action_families", []),
        allowed_resource_types=raw.get("allowed_resource_types", []),
        restricted_resource_types=raw.get("restricted_resource_types", []),
        restricted_resource_tags=raw.get("restricted_resource_tags", []),
        lease_permissions=raw.get("lease_permissions", []),
        exclusions=raw.get("exclusions", []),
    )


def _deserialise_query(raw: Dict[str, Any]) -> ActionDiscoveryQuery:
    action_family = None
    if raw.get("action_family"):
        try:
            action_family = ActionFamily(raw["action_family"])
        except ValueError as exc:
            raise ValueError(f"Unknown action_family '{raw['action_family']}'") from exc

    return ActionDiscoveryQuery(
        session_id=raw.get("session_id", config.DEFAULT_SESSION_ID),
        resource_type=raw.get("resource_type"),
        action_family=action_family,
        task_context=raw.get("task_context"),
        max_results=int(raw.get("max_results", config.DEFAULT_MAX_RESULTS)),
        include_schemas=bool(raw.get("include_schemas", False)),
    )


def _summary_to_dict(summary) -> Dict[str, Any]:
    return {
        "action_name": summary.action_name,
        "resource_type": summary.resource_type,
        "action_family": summary.action_family.value,
        "risk_level": summary.risk_level.value,
        "description": summary.description,
        "guard_summary": summary.guard_summary,
    }


def _collect_candidates(resource_type: Optional[str]):
    """Return all ActionContracts from the registry, scoped by resource_type."""
    resource_types = _registry.registered_resource_types()
    if resource_type:
        resource_types = resource_types & {resource_type}
    candidates = []
    for rt in sorted(resource_types):
        for name in _registry.registered_actions(rt):
            try:
                candidates.append(_registry.lookup_action(rt, name))
            except KeyError:
                pass
    return candidates


# ── Semantic query path ───────────────────────────────────────────────────────


def _run_semantic(
    discovery_query: ActionDiscoveryQuery,
    capability: CapabilitySet,
    agent_trust_tier: Optional[TrustTier],
) -> Dict[str, Any]:
    """Handle a task_context query via semantic ranking + capability filter.

    Ordering (critical for security invariant):
    1. Collect raw candidates (registry scope by resource_type)
    2. rank_by_similarity → threshold-filtered, similarity-ordered list
    3. is_action_permitted → capability + trust tier filter
    4. action_family filter
    5. Truncate to max_results
    """
    # 1. Candidates
    candidates = _collect_candidates(discovery_query.resource_type)

    # 2. Semantic ranking (threshold filtering included)
    ranked = _semantic.rank_by_similarity(
        discovery_query.task_context,
        candidates,
        threshold=config.SIMILARITY_THRESHOLD,
    )

    # 3. Capability filter — AFTER semantic ranking
    permitted = [
        ac for ac in ranked
        if is_action_permitted(ac, capability, agent_trust_tier=agent_trust_tier)
    ]

    # 4. action_family filter
    if discovery_query.action_family is not None:
        permitted = [
            ac for ac in permitted
            if ac.action_family == discovery_query.action_family
        ]

    # 5. Truncate
    total_available = len(permitted)
    page = permitted[: discovery_query.max_results]
    summaries = [_action_to_summary(ac) for ac in page]

    # filtered_by transparency
    filtered_by: Dict[str, Any] = {
        "session_id": discovery_query.session_id,
        "capability_set_id": capability.id,
        "semantic_search": True,
        "similarity_threshold": config.SIMILARITY_THRESHOLD,
    }
    if discovery_query.resource_type:
        filtered_by["resource_type"] = discovery_query.resource_type
    if discovery_query.action_family:
        filtered_by["action_family"] = discovery_query.action_family.value
    filtered_by["task_context"] = discovery_query.task_context
    filtered_by["max_results"] = discovery_query.max_results

    # Recommendation: top result when similarity is high enough
    recommendation = None
    if summaries:
        top_score = _semantic.similarity_score(discovery_query.task_context, page[0])
        if top_score is not None and top_score >= 0.7:
            recommendation = {
                "action_name": summaries[0].action_name,
                "rationale": (
                    f"Highest semantic similarity ({top_score:.2f}) to "
                    f"task context '{discovery_query.task_context}'."
                ),
                "confidence": round(float(top_score), 3),
            }

    payload: Dict[str, Any] = {
        "available_actions": [_summary_to_dict(s) for s in summaries],
        "filtered_by": filtered_by,
        "total_available": total_available,
        "catalog_version": _loader.catalog_version,
        "recommendation": recommendation,
    }
    return _ok(payload)


# ── Public API ────────────────────────────────────────────────────────────────


def run(
    query: Optional[Dict[str, Any]] = None,
    capability_set: Optional[Dict[str, Any]] = None,
    session_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute an ActionDiscovery query.

    Args:
        query:            Dict with optional keys: resource_type, action_family,
                          task_context, max_results, include_schemas, session_id.
        capability_set:   Dict with CapabilitySet fields.  Takes priority over
                          session_context.  One of capability_set or session_context
                          is required.
        session_context:  Dict with trust_tier and/or agent_class_id.

    Returns:
        _ok envelope with payload keys: available_actions, filtered_by,
        total_available, catalog_version, recommendation.
        _error envelope on any failure.  Never raises.
    """
    # ── 1. Catalog must be loaded ─────────────────────────────────────────────
    if _registry is None:
        return _error(
            "CATALOG_EMPTY",
            "Catalog failed to load at startup. No contracts are available.",
            "startup",
            {"catalog_path": config.CATALOG_PATH},
        )

    if _loader.contracts_loaded == 0 and not _loader.failures:
        return _error(
            "CATALOG_EMPTY",
            "Catalog is empty — no action contracts were found.",
            "startup",
            {"catalog_path": config.CATALOG_PATH},
        )

    # ── 2. Deserialise query ──────────────────────────────────────────────────
    if query is None:
        query = {}
    if not isinstance(query, dict):
        return _error("INVALID_QUERY", "query must be a dict.", "query_parse")

    try:
        discovery_query = _deserialise_query(query)
    except ValueError as exc:
        return _error("INVALID_QUERY", str(exc), "query_parse")

    # ── 3. Resolve capability set (P0-6) ─────────────────────────────────────
    capability, err = _resolve_capability_set(capability_set, session_context)
    if err is not None:
        return err

    # ── 4. Resolve optional trust tier ───────────────────────────────────────
    agent_trust_tier: Optional[TrustTier] = None
    raw_tier = (
        (session_context or {}).get("trust_tier")
        or (capability_set or {}).get("trust_tier")
    )
    if raw_tier:
        agent_trust_tier = _TRUST_TIER_MAP.get(raw_tier)

    # ── 5. Route: semantic or structured ─────────────────────────────────────
    try:
        if discovery_query.task_context and _semantic.enabled:
            return _run_semantic(discovery_query, capability, agent_trust_tier)

        # Structured path — execute_discovery handles keyword ranking fallback.
        response = execute_discovery(
            _registry,
            query=discovery_query,
            capability_set=capability,
            agent_trust_tier=agent_trust_tier,
            catalog_version=_loader.catalog_version,
        )
    except Exception as exc:
        return _error(
            "DISCOVERY_FAILED",
            f"Discovery raised an unexpected error: {exc}",
            "discovery",
        )

    # ── 6. Serialise structured response ─────────────────────────────────────
    payload: Dict[str, Any] = {
        "available_actions": [_summary_to_dict(s) for s in response.available_actions],
        "filtered_by": response.filtered_by,
        "total_available": response.total_available,
        "catalog_version": response.catalog_version,
        "recommendation": (
            {
                "action_name": response.recommendation.action_name,
                "rationale": response.recommendation.rationale,
                "confidence": response.recommendation.confidence,
            }
            if response.recommendation is not None
            else None
        ),
    }
    return _ok(payload)


def health() -> Dict[str, Any]:
    """Return service health status."""
    catalog_loaded = _registry is not None
    contracts_registered = _loader.contracts_loaded if catalog_loaded else 0
    contracts_failed = len(_loader.failures)

    if not catalog_loaded:
        status = "unhealthy"
    elif contracts_registered == 0:
        status = "unhealthy"
    elif contracts_failed > 0:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "catalog_loaded": catalog_loaded,
        "contracts_registered": contracts_registered,
        "contracts_failed": contracts_failed,
        "semantic_search_enabled": _semantic.enabled,
        "catalog_version": _loader.catalog_version,
        "uptime_seconds": round(time.time() - _START_TIME, 2),
    }
