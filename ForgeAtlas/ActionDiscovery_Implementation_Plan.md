# ActionDiscovery Service — Implementation Plan

**Status:** Draft v0.1 — 2026-03-07
**Prerequisite:** ActionDiscovery Core Specification v0.1
**Target:** New AI Dev (greenfield service build)
**Deployment:** Docker container

---

## Overview

This plan builds the ActionDiscovery service in four phases. Each phase produces a testable, deployable increment. No phase depends on external services — the service is self-contained within its Docker container.

The existing code assets are:

| Asset | Location | Status |
|---|---|---|
| `execute_discovery()` | `dawn/concord/discovery_kernel.py` | ✅ Built, tested, stable |
| `ActionDiscoveryQuery` dataclass | `dawn/concord/types/` | ✅ Built, stable |
| `ActionDiscoveryResponse` dataclass | `dawn/concord/types/` | ✅ Built, stable |
| `ActionSummary` dataclass | `dawn/concord/types/` | ✅ Built, stable |
| `ContractRegistry` | `dawn/concord/` kernel layer | ✅ Built, in-memory only |
| `load_action_contract()` | `dawn/concord/` kernel layer | ✅ Built, Pydantic validation |
| `is_action_permitted()` | `dawn/concord/discovery_kernel.py` | ✅ Built, 5-check filter chain |
| Catalog persistence | — | ❌ Does not exist |
| Semantic search | — | ❌ Does not exist |
| Service wrapper | — | ❌ Does not exist |
| YAML manifest directory | — | ❌ Does not exist |
| Docker packaging | — | ❌ Does not exist |

---

## Phase 1 — Catalog Persistence Layer

**Goal:** ActionContracts live on disk as YAML files and are loaded into ContractRegistry on startup.

**Duration estimate:** 1–2 sessions

### Deliverables

1. **Directory structure**: Create `action_catalogs/` with subdirectories per domain (`ci_change_control/`, `it_ops_runbook/`, `_shared/`).

2. **Seed manifests**: Write 5–8 ActionContract YAML files covering the `change_request` reference resource from the CONCORD v0.3 Runtime Contract Schemas worked example (§8). These are real contracts, not test stubs. They should include `submit_change_request`, `approve_change_request`, `deploy_change_request`, `update_change_request`, `read_change_request`, `request_edit_lease`, `request_review_token`, `withdraw_change_request`.

3. **`catalog_loader.py`**: Module that walks a directory, reads YAML files, validates each through `load_action_contract()`, and registers them into a `ContractRegistry` instance. Must handle partial failures (skip invalid files, log errors, continue loading).

4. **`catalog_version` computation**: SHA-256 hash of sorted file paths + contents. Exposed as a field on the loader for consumers to cache against.

5. **Tests**: Loader correctly populates registry from disk. Invalid YAML files are skipped with logged errors. Empty directory produces empty registry with warning. Catalog version changes when a file is modified.

### Validation criteria

```
catalog_loader = CatalogLoader("action_catalogs/")
registry = catalog_loader.load()
assert registry.count_actions() >= 5
assert catalog_loader.catalog_version is not None
assert catalog_loader.failures == []  # for valid manifests
```

### Files created

| File | Purpose |
|---|---|
| `catalog_loader.py` | Directory walker + YAML loader + registry hydrator |
| `action_catalogs/ci_change_control/*.yaml` | Seed ActionContract manifests |
| `action_catalogs/_shared/*.yaml` | Cross-domain shared actions |
| `tests/test_catalog_loader.py` | Loader unit tests |

---

## Phase 2 — Service Wrapper

**Goal:** `execute_discovery()` is callable via the established importlib Pattern 1 with `_ok/_error` envelope.

**Duration estimate:** 1 session

### Deliverables

1. **`run.py`**: Entry point with `run(query, capability_set, session_context)` function. Imports `execute_discovery` from the kernel. Deserializes input dicts into the existing dataclass types. Returns `_ok/_error` envelope dicts.

2. **Session/capability resolution**: Accept either a raw `capability_set` dict or a `session_context` with `agent_class_id`. If `agent_class_id` is provided, resolve to CapabilitySet(s). If neither is provided, return `MISSING_CAPABILITY_CONTEXT` error.

3. **`health()` function**: Returns service health status including catalog stats and semantic search availability.

4. **Error handling**: All exceptions caught and returned as structured `_error` envelopes. The service never raises — it always returns a dict.

5. **Tests**: Happy path query returns filtered results. Missing capability context returns error. Invalid query returns error. Health function returns expected shape.

### Validation criteria

```
from action_discovery_service.run import run, health

# Happy path
result = run(
    query={"resource_type": "change_request", "action_family": "mutate", "max_results": 5},
    capability_set={"allowed_action_families": ["mutate"], "restricted_resource_types": []},
)
assert result["status"] == "ok"
assert len(result["payload"]["available_actions"]) > 0
assert "catalog_version" in result["payload"]

# Missing context
result = run(query={"resource_type": "change_request"}, capability_set=None)
assert result["status"] == "error"
assert result["error"]["code"] == "MISSING_CAPABILITY_CONTEXT"

# Health
h = health()
assert h["status"] in ("healthy", "degraded", "unhealthy")
```

### Files created

| File | Purpose |
|---|---|
| `run.py` | Service wrapper entry point |
| `config.py` | Environment variable handling |
| `tests/test_service_wrapper.py` | Wrapper unit tests |

---

## Phase 3 — Semantic Search Layer

**Goal:** Queries with `task_context` return results ranked by natural language similarity to action descriptions.

**Duration estimate:** 2–3 sessions

### Deliverables

1. **`semantic_search.py`**: Module that embeds ActionContract descriptions on catalog load and provides a `rank_by_similarity(task_context, candidates, threshold)` function.

2. **Embedding model integration**: Load `all-MiniLM-L6-v2` (or configurable alternative) from sentence-transformers. Compute embeddings for all action descriptions at startup. Store in NumPy array or FAISS flat index.

3. **Search integration with kernel**: When `task_context` is present in the query, semantic search runs first to rank candidates, then `execute_discovery()` filters by capability/trust. When `task_context` is absent, structured filtering only (existing behavior).

4. **Similarity threshold**: Results below threshold (default 0.3, configurable) are excluded. Threshold is exposed as `ACTION_DISCOVERY_SIMILARITY_THRESHOLD` environment variable.

5. **Graceful degradation**: If the embedding model fails to load (disk issue, dependency missing), semantic search is disabled. Structured filtering continues to work. Health endpoint reports `semantic_search_enabled: false`.

6. **Tests**: Semantic search returns relevant results for natural language queries. Irrelevant queries return empty results (below threshold). Structured filters compose with semantic ranking. Model load failure degrades gracefully.

### Validation criteria

```
from action_discovery_service.run import run

# Semantic search
result = run(
    query={"task_context": "I need to get a code change reviewed and approved", "max_results": 5},
    capability_set={"allowed_action_families": ["mutate", "approve"], "restricted_resource_types": []},
)
assert result["status"] == "ok"
actions = result["payload"]["available_actions"]
# approve_change_request and submit_change_request should rank high
action_names = [a["action_name"] for a in actions]
assert "approve_change_request" in action_names or "submit_change_request" in action_names

# Semantic + structured filter
result = run(
    query={"task_context": "deploy to production", "action_family": "deploy", "max_results": 3},
    capability_set={"allowed_action_families": ["deploy"], "restricted_resource_types": []},
)
assert result["status"] == "ok"
for a in result["payload"]["available_actions"]:
    assert a["action_family"] == "deploy"
```

### Files created

| File | Purpose |
|---|---|
| `semantic_search.py` | Embedding model loader + vector store + similarity ranking |
| `tests/test_semantic_search.py` | Semantic search unit tests |

### Dependencies added

| Package | Purpose | Size |
|---|---|---|
| `sentence-transformers` | Embedding model | ~500MB with model |
| `torch` (CPU) | Required by sentence-transformers | ~200MB |
| `faiss-cpu` | Vector similarity search (optional, NumPy fallback acceptable) | ~20MB |

---

## Phase 4 — Docker Packaging & Integration

**Goal:** Service runs in a Docker container, loads catalog from mounted volume, and is callable by ForgeWorks via importlib.

**Duration estimate:** 1 session

### Deliverables

1. **Dockerfile**: Multi-stage build. Install dependencies, copy service code, set environment defaults. Catalog directory is a mounted volume (not baked in) so manifests can be updated without rebuilding the image.

2. **`requirements.txt`**: Pinned dependencies.

3. **Startup validation**: Container logs catalog load summary on startup (N contracts loaded, M failed, semantic search enabled/disabled, catalog_version). If zero contracts load, health reports `unhealthy`.

4. **Integration test**: ForgeWorks can import the service via importlib and call `run()` / `health()` successfully. Follows the same `_import_fs_module()` pattern from `forgescaffold_coding_context.py`.

5. **Integration seam confirmation**: Verify the service matches the ActionDiscovery contract from CONCORD v0.4 — response shape matches ActionDiscoveryResponse, capability filtering matches the 5-check chain, advisory semantics are preserved (no authoritative_for_mutation field).

### Validation criteria

```bash
# Build
docker build -t action-discovery-service .

# Run with catalog mounted
docker run -v ./action_catalogs:/app/action_catalogs action-discovery-service

# Logs show:
# ActionDiscovery startup: 8 contracts loaded, 0 failed, semantic search enabled
# Catalog version: sha256:abc123...
# Service ready
```

### Files created

| File | Purpose |
|---|---|
| `Dockerfile` | Container definition |
| `requirements.txt` | Pinned dependencies |
| `tests/test_integration.py` | End-to-end integration tests |

---

## Phase Summary

| Phase | Builds | Depends on | Test count target |
|---|---|---|---|
| Phase 1: Catalog Persistence | YAML manifests + loader + registry hydration | Existing ContractRegistry + load_action_contract | 10–15 |
| Phase 2: Service Wrapper | run() + health() + _ok/_error envelope | Phase 1 (needs loaded registry) | 10–15 |
| Phase 3: Semantic Search | Embedding + vector store + similarity ranking | Phase 1 (needs loaded catalog) + Phase 2 (integrates into run()) | 10–15 |
| Phase 4: Docker Packaging | Dockerfile + startup sequence + integration tests | Phases 1–3 | 5–10 |

**Total estimated test count: 35–55**
**Total estimated duration: 5–7 sessions**

---

## Existing Code the Dev Must Read Before Starting

| File | Why |
|---|---|
| `dawn/concord/discovery_kernel.py` | The kernel being wrapped. Understand `execute_discovery()`, `is_action_permitted()`, and the 5-check filter chain. |
| `dawn/concord/types/` (ActionDiscoveryQuery, ActionDiscoveryResponse, ActionSummary, CapabilitySet, ActionContract) | The dataclasses the service serializes/deserializes. |
| `dawn/concord/types/enums.py` | TrustTier, RiskLevel, ActionFamily, ConsistencyProfile — needed for YAML manifest values. |
| `forgeworks/sam/service_wrapper.py` | The `_ok()` / `_error()` envelope convention. The `execute_planner_request()` function as an example of the Pattern 1 service style. |
| `forgeworks/runner/forgescaffold_coding_context.py` | The `_import_fs_module()` importlib pattern this service must match. |
| CONCORD v0.3 Runtime Contract Schemas §8 (worked example) | The `change_request` reference resource. Seed manifests in Phase 1 should implement these exact contracts. |

---

*End of implementation plan. Four phases, each independently testable. The kernel is ready; you're building persistence, search, and the service shell around it.*
