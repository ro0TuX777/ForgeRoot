# Graph Report - .  (2026-05-04)

## Corpus Check
- Corpus is ~12,231 words - fits in a single context window. You may not need a graph.

## Summary
- 215 nodes · 348 edges · 13 communities detected
- Extraction: 56% EXTRACTED · 24% INFERRED · 0% AMBIGUOUS · INFERRED: 82 edges (avg confidence: 0.74)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]

## God Nodes (most connected - your core abstractions)
1. `run()` - 56 edges
2. `SemanticSearch` - 32 edges
3. `TestResponseShape` - 19 edges
4. `TestRankBySimilarity` - 13 edges
5. `health()` - 11 edges
6. `TestHappyPath` - 11 edges
7. `TestSemanticIntegrationInRun` - 10 edges
8. `TestCapabilityFiltering` - 9 edges
9. `TestHealth` - 9 edges
10. `TestSemanticSearchModelLoading` - 8 edges

## Surprising Connections (you probably didn't know these)
- `ForgeAtlas — ActionDiscovery Service entry point.  Callable via the importlib pa` --uses--> `SemanticSearch`  [INFERRED]
  run.py → semantic_search.py
- `Return (CapabilitySet, error_dict_or_None).` --uses--> `SemanticSearch`  [INFERRED]
  run.py → semantic_search.py
- `Return all ActionContracts from the registry, scoped by resource_type.` --uses--> `SemanticSearch`  [INFERRED]
  run.py → semantic_search.py
- `Handle a task_context query via semantic ranking + capability filter.      Order` --uses--> `SemanticSearch`  [INFERRED]
  run.py → semantic_search.py
- `Execute an ActionDiscovery query.      Args:         query:            Dict with` --uses--> `SemanticSearch`  [INFERRED]
  run.py → semantic_search.py

## Hyperedges (group relationships)
- **Three-Layer ActionDiscovery Architecture** — catalog_persistence_layer_concept, semantic_search_layer_concept, service_wrapper_layer_concept, action_discovery_core_spec_doc, forgeatlas_whitepaper_doc [1.0]
- **Semantic Query Security Flow** — run_semantic_function, semantic_rank_by_similarity_function, similarity_threshold_config, governed_discovery_invariant, action_discovery_response_contract [1.0]
- **QA Coverage for Service Contracts** — test_service_wrapper_suite, test_semantic_search_suite, test_integration_suite, run_function, health_function, governed_discovery_invariant, action_discovery_response_contract [0.96]
- **Runtime Configuration Surface** — action_discovery_service_config_module, catalog_path_config, default_session_id_config, default_max_results_config, similarity_threshold_config, embedding_model_config, requirements_file [0.94]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (8): Execute an ActionDiscovery query.      Args:         query:            Dict with, run(), TestSemanticIntegrationInRun, Tests for action_discovery_service/run.py — Phase 2 (P0-5, P0-6, P1-5, P1-8).  C, TestCapabilityFiltering, TestCapabilityResolution, TestErrorCodes, TestHappyPath

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (43): ActionDiscovery Core Specification, ActionDiscoveryResponse Contract, ActionDiscovery Config Module, Advisory Discovery Contract, ForgeAtlas AI Developer Briefing, Catalog Loader Startup, Catalog Path Config, Catalog Persistence Layer (+35 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (14): _normalise(), ForgeAtlas — Semantic search layer (Phase 3, P1-1 / P1-2).  Provides: - Semantic, Rank *candidates* by cosine similarity to *task_context*.          Args:, Return the cosine similarity between task_context and action description., Return unit-length vector; return v unchanged if norm is zero., Embedding-based similarity ranker for ActionContract descriptions.      Lifecycl, Attempt to load the embedding model.          Returns:             True if the m, Pre-compute and cache unit-normalised embeddings for every action.          Call (+6 more)

### Community 3 - "Community 3"
Cohesion: 0.16
Nodes (4): Response must match CONCORD v0.4 ActionDiscoveryResponse contract (P2-6)., Semantic path response must also match the contract., filtered_by.semantic_search must be True on semantic path., TestResponseShape

### Community 4 - "Community 4"
Cohesion: 0.13
Nodes (9): _load_module(), ForgeAtlas — Integration tests (Phase 4, P2-5 + P2-6).  Covers: - P2-5: ForgeWor, Verify all action families reachable through the service., T4-unrestricted cap should see all 10 change_request actions., ForgeWorks-style importlib import must work end-to-end (P2-5)., Catalog must be loaded — response must not be CATALOG_EMPTY., Semantic path (task_context) must work via importlib., TestEndToEndCoverage (+1 more)

### Community 5 - "Community 5"
Cohesion: 0.15
Nodes (6): health(), Return service health status., Simulate model not loaded: structured path must still work., When semantic is disabled, task_context falls back to keyword ranking., TestGracefulDegradation, TestHealth

### Community 6 - "Community 6"
Cohesion: 0.2
Nodes (12): _collect_candidates(), _deserialise_capability_set(), _deserialise_query(), _error(), _ok(), ForgeAtlas — ActionDiscovery Service entry point.  Callable via the importlib pa, Return (CapabilitySet, error_dict_or_None)., Return all ActionContracts from the registry, scoped by resource_type. (+4 more)

### Community 7 - "Community 7"
Cohesion: 0.33
Nodes (2): Capability filter runs AFTER semantic ranking — high-similarity         actions, TestSecurityInvariant

### Community 8 - "Community 8"
Cohesion: 0.5
Nodes (2): Service must be callable via importlib (ForgeWorks Pattern 1)., TestImportlibPattern

### Community 9 - "Community 9"
Cohesion: 1.0
Nodes (1): ForgeAtlas — environment variable configuration.  All settings have in-code defa

### Community 10 - "Community 10"
Cohesion: 1.0
Nodes (1): ForgeAtlas — Docker entrypoint (P1-7).  Validates service health at startup, log

### Community 12 - "Community 12"
Cohesion: 1.0
Nodes (1): ActionDiscovery Service Run Module

### Community 13 - "Community 13"
Cohesion: 1.0
Nodes (1): Semantic Search Module

## Knowledge Gaps
- **20 isolated node(s):** `ForgeAtlas — environment variable configuration.  All settings have in-code defa`, `ForgeAtlas — Semantic search layer (Phase 3, P1-1 / P1-2).  Provides: - Semantic`, `Embedding-based similarity ranker for ActionContract descriptions.      Lifecycl`, `Attempt to load the embedding model.          Returns:             True if the m`, `Pre-compute and cache unit-normalised embeddings for every action.          Call` (+15 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 7`** (6 nodes): `Capability filter runs AFTER semantic ranking — high-similarity         actions`, `TestSecurityInvariant`, `.test_exclusion_respected_in_semantic_path()`, `.test_restricted_resource_type_excluded_even_with_semantic()`, `.test_t2_agent_never_sees_approve_via_semantic()`, `.test_t2_agent_never_sees_deploy_via_semantic()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 8`** (4 nodes): `Service must be callable via importlib (ForgeWorks Pattern 1).`, `TestImportlibPattern`, `.test_importlib_callable()`, `.test_importlib_health_callable()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 9`** (2 nodes): `ForgeAtlas — environment variable configuration.  All settings have in-code defa`, `config.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 10`** (2 nodes): `ForgeAtlas — Docker entrypoint (P1-7).  Validates service health at startup, log`, `__main__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 12`** (1 nodes): `ActionDiscovery Service Run Module`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 13`** (1 nodes): `Semantic Search Module`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run()` connect `Community 0` to `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.388) - this node is a cross-community bridge._
- **Why does `SemanticSearch` connect `Community 2` to `Community 0`, `Community 5`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.217) - this node is a cross-community bridge._
- **Why does `Execute an ActionDiscovery query.      Args:         query:            Dict with` connect `Community 0` to `Community 2`?**
  _High betweenness centrality (0.116) - this node is a cross-community bridge._
- **Are the 48 inferred relationships involving `run()` (e.g. with `._ok_payload()` and `.test_semantic_response_shape()`) actually correct?**
  _`run()` has 48 INFERRED edges - model-reasoned connections that need verification._
- **Are the 25 inferred relationships involving `SemanticSearch` (e.g. with `ForgeAtlas — ActionDiscovery Service entry point.  Callable via the importlib pa` and `Return (CapabilitySet, error_dict_or_None).`) actually correct?**
  _`SemanticSearch` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `health()` (e.g. with `.test_health_reports_semantic_enabled_correctly()` and `.test_health_returns_dict()`) actually correct?**
  _`health()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ForgeAtlas — environment variable configuration.  All settings have in-code defa`, `ForgeAtlas — Semantic search layer (Phase 3, P1-1 / P1-2).  Provides: - Semantic`, `Embedding-based similarity ranker for ActionContract descriptions.      Lifecycl` to the rest of the system?**
  _20 weakly-connected nodes found - possible documentation gaps or missing edges._