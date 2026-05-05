# ActionDiscovery Service — Punch List

**Status:** Draft v0.1 — 2026-03-07
**Companion to:** Core Specification v0.1, Implementation Plan v0.1
**Convention:** P0 = blocks all downstream work. P1 = blocks release. P2 = should ship. P3 = nice to have.

---

## P0 — Blocks Everything

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P0-1 | Create `action_catalogs/` directory structure with domain subdirectories | 1 | Directories exist: `ci_change_control/`, `it_ops_runbook/`, `_shared/` |
| P0-2 | Write seed ActionContract YAML manifests for `change_request` resource | 1 | Minimum 5 valid YAML files covering: `submit_change_request`, `approve_change_request`, `deploy_change_request`, `update_change_request`, `read_change_request`. Each must pass `load_action_contract()` Pydantic validation without modification. |
| P0-3 | Build `catalog_loader.py` — directory walker + YAML parser + registry hydrator | 1 | `CatalogLoader(path).load()` returns a populated `ContractRegistry`. Invalid files are skipped with logged errors. Empty directory returns empty registry with warning. |
| P0-4 | Implement `catalog_version` as SHA-256 of sorted file paths + contents | 1 | Hash changes when any manifest file is added, removed, or modified. Hash is stable (deterministic) for identical catalog state. |
| P0-5 | Build `run.py` with `run(query, capability_set, session_context)` entry point | 2 | Returns `_ok/_error` envelope dict. Deserializes inputs into existing dataclasses. Calls `execute_discovery()` from kernel. Never raises — always returns dict. |
| P0-6 | Implement session/capability resolution in service wrapper | 2 | Accepts raw `capability_set` dict OR `session_context` with `agent_class_id`. Returns `MISSING_CAPABILITY_CONTEXT` error if neither provided. |

---

## P1 — Blocks Release

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P1-1 | Build `semantic_search.py` — embedding model loader + vector store | 3 | Loads `all-MiniLM-L6-v2` (or configured model). Embeds all action descriptions at startup. Stores embeddings in memory (NumPy array or FAISS flat index). |
| P1-2 | Implement `rank_by_similarity(task_context, candidates, threshold)` | 3 | Returns candidates ranked by cosine similarity to embedded task_context. Excludes results below threshold. |
| P1-3 | Integrate semantic search into `run()` — task_context triggers ranking before kernel filtering | 3 | When `task_context` present: semantic rank first, then capability filter. When absent: structured filter only (existing behavior). |
| P1-4 | Graceful degradation when embedding model unavailable | 3 | If model fails to load, semantic search is disabled. Structured filtering works. Health reports `semantic_search_enabled: false`. Service does not crash. |
| P1-5 | Build `health()` function | 2 | Returns dict with: status (healthy/degraded/unhealthy), catalog_loaded, contracts_registered, contracts_failed, semantic_search_enabled, catalog_version, uptime_seconds. |
| P1-6 | Write Dockerfile with multi-stage build | 4 | Container builds successfully. Catalog directory is a mounted volume. Environment variables set defaults per Core Spec §6.3. |
| P1-7 | Startup sequence logs catalog load summary | 4 | Container logs: N contracts loaded, M failed, semantic search enabled/disabled, catalog_version. Zero contracts → health reports `unhealthy`. |
| P1-8 | All error codes from Core Spec §5.4 implemented | 2 | `CATALOG_EMPTY`, `CATALOG_LOAD_PARTIAL`, `MISSING_CAPABILITY_CONTEXT`, `SEMANTIC_SEARCH_UNAVAILABLE`, `INVALID_QUERY` — each returns correct structured error envelope. |

---

## P2 — Should Ship

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P2-1 | Write 3 additional `it_ops_runbook` domain manifests | 1 | At least `execute_runbook_step`, `escalate_incident`, `close_incident`. Valid YAML, passes Pydantic. Demonstrates cross-domain catalog. |
| P2-2 | Implement `include_schemas` query parameter | 2 | When `false` (default): return ActionSummary (name, family, risk, description, guard summary). When `true`: include full input/output schema refs. |
| P2-3 | Implement `recommendation` field in response | 2 | When semantic search is active and a clear top result exists (similarity > 0.7), populate `recommendation` with the top action and a one-line rationale. Otherwise null. |
| P2-4 | Configurable similarity threshold via environment variable | 3 | `ACTION_DISCOVERY_SIMILARITY_THRESHOLD` controls minimum cosine similarity. Default 0.3. Changing it actually changes filtering behavior. |
| P2-5 | Integration test: ForgeWorks imports service via importlib | 4 | Matches `_import_fs_module()` pattern from `forgescaffold_coding_context.py`. ForgeWorks can call `run()` and `health()` against a loaded catalog. |
| P2-6 | Verify response shape matches CONCORD v0.4 ActionDiscoveryResponse contract | 4 | `available_actions`, `filtered_by`, `total_available`, `recommendation`, `catalog_version` — all present. No `authoritative_for_mutation` field. |
| P2-7 | `requirements.txt` with pinned versions | 4 | All dependencies version-pinned. `pip install -r requirements.txt` succeeds cleanly in Docker. |

---

## P3 — Nice to Have (Not Required for v1.0)

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P3-1 | File watcher for catalog hot-reload | 1+ | Manifest file changes trigger re-load without service restart. Catalog_version updates. New embeddings computed for changed actions. |
| P3-2 | Structured filter composition logging | 2 | `filtered_by` in response includes a step-by-step trace of which filters narrowed the result set and by how much (e.g., "capability_filter: 42→18, resource_type_filter: 18→7, trust_tier_filter: 7→5"). |
| P3-3 | Embedding cache on disk | 3 | Pre-computed embeddings saved to disk alongside catalog. On restart, if catalog_version matches cached version, skip re-embedding. Saves startup time when catalog is large. |
| P3-4 | Alternative embedding model support | 3 | `EMBEDDING_MODEL` env var selects from multiple pre-tested models. Fallback chain if primary model unavailable. |
| P3-5 | Catalog validation CLI command | 1+ | `python -m action_discovery_service.validate action_catalogs/` — validates all manifests without starting the service. Reports errors. Exit code 0 if all pass. |
| P3-6 | Metrics endpoint for observability | 4 | Exposes: queries_served, average_response_time_ms, cache_hit_rate (if caching added), catalog_reload_count. Matches CONCORD CoordinationTelemetry conventions where applicable. |

---

## Dependency Map

```
P0-1 (directory) ──→ P0-2 (seed manifests) ──→ P0-3 (loader) ──→ P0-4 (versioning)
                                                      │
                                                      ▼
                                                P0-5 (run.py) ──→ P0-6 (capability resolution)
                                                      │
                                              ┌───────┴────────┐
                                              ▼                ▼
                                        P1-5 (health)    P1-8 (error codes)
                                              │
                                              ▼
                                        P1-1 (embeddings) ──→ P1-2 (similarity) ──→ P1-3 (integration)
                                              │
                                              ▼
                                        P1-4 (degradation)
                                              │
                                              ▼
                                        P1-6 (Dockerfile) ──→ P1-7 (startup logs)
                                              │
                                              ▼
                                        P2-5 (integration test) ──→ P2-6 (contract verification)
```

---

## Test Coverage Summary

| Phase | Test file | Target count | Covers |
|---|---|---|---|
| 1 | `test_catalog_loader.py` | 10–15 | Directory walking, YAML parsing, validation failures, empty catalog, catalog versioning, partial load |
| 2 | `test_service_wrapper.py` | 10–15 | Happy path query, missing context, invalid query, error envelopes, health function, include_schemas, capability resolution |
| 3 | `test_semantic_search.py` | 10–15 | Relevant query ranking, irrelevant query exclusion, threshold filtering, structured + semantic composition, model load failure degradation |
| 4 | `test_integration.py` | 5–10 | importlib import, ForgeWorks-style invocation, response shape validation, Docker startup verification |
| **Total** | | **35–55** | |

---

## Definition of Done

The service is complete when:

1. All P0 and P1 items pass their acceptance criteria
2. All P2 items pass or have documented deferral reasons
3. Test count is ≥ 35 with zero failures
4. Docker container builds and starts successfully
5. Health endpoint reports `healthy` with correct catalog stats
6. A ForgeWorks-style importlib caller can successfully query the service and receive a valid `_ok` response with filtered, ranked actions
7. Response shape matches CONCORD v0.4 ActionDiscoveryResponse contract
8. No `authoritative_for_mutation` field appears anywhere in responses

---

*End of punch list. 6 P0s, 8 P1s, 7 P2s, 6 P3s. Critical path: P0-1 through P0-6, then P1-1 through P1-7.*
