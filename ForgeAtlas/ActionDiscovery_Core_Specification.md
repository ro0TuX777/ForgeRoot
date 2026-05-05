# ActionDiscovery Service — Core Specification

**Status:** Draft v0.1 — 2026-03-07
**Framework:** CONCORD v0.4
**Depends on:** discovery_kernel.py (existing), ContractRegistry (existing), ActionDiscoveryQuery/Response (existing)
**Deployment:** Docker container

---

## 1 — Purpose

ActionDiscovery is a queryable service that resolves available actions for a given agent context and task intent. It prevents token explosion from loading full action catalogs into agent context. It wraps the existing `execute_discovery()` kernel with three new capabilities the kernel does not have: catalog persistence, service exposure, and semantic search.

---

## 2 — Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                ActionDiscovery Service                    │
│                (Docker container)                         │
│                                                          │
│  ┌──────────────┐   ┌──────────────┐   ┌─────────────┐ │
│  │  Catalog      │   │  Semantic     │   │  Service     │ │
│  │  Persistence  │   │  Search      │   │  Wrapper     │ │
│  │  Layer        │   │  Layer        │   │  Layer       │ │
│  │               │   │               │   │              │ │
│  │  YAML/JSON    │   │  Embedding    │   │  importlib   │ │
│  │  manifests    │   │  model +      │   │  pattern     │ │
│  │  on disk      │   │  vector store │   │  (Pattern 1) │ │
│  │       │       │   │       │       │   │      │       │ │
│  │       ▼       │   │       ▼       │   │      ▼       │ │
│  │  ContractReg. │   │  Similarity   │   │  _ok/_error  │ │
│  │  hydration    │   │  ranking      │   │  envelope    │ │
│  └───────┬───────┘   └───────┬───────┘   └──────┬──────┘ │
│          │                   │                   │        │
│          └───────────┬───────┘                   │        │
│                      ▼                           │        │
│          ┌───────────────────┐                   │        │
│          │ execute_discovery()│◀──────────────────┘        │
│          │ (existing kernel)  │                            │
│          └───────────────────┘                            │
└─────────────────────────────────────────────────────────┘
```

Three layers, each with a single responsibility:

| Layer | Responsibility | New or existing |
|---|---|---|
| Catalog Persistence | Load ActionContracts from disk into ContractRegistry on startup; reload on file change | **New** |
| Semantic Search | Embed action descriptions; rank results by similarity to task_context query | **New** |
| Service Wrapper | Expose execute_discovery() as a callable service following Pattern 1 (importlib); return _ok/_error envelopes | **New** (wraps existing kernel) |

---

## 3 — Catalog Persistence Layer

### 3.1 Problem

ContractRegistry is in-memory only. It's an empty singleton until a caller populates it. No code outside test fixtures registers contracts. ActionDiscovery needs a catalog to query against that survives process restarts and is editable by humans.

### 3.2 Design

ActionContracts are stored as **YAML manifest files** in a designated directory. On service startup, the persistence layer walks the directory, validates each file through the existing `load_action_contract()` Pydantic path, and registers them into ContractRegistry.

```
action_catalogs/
├── ci_change_control/
│   ├── submit_change_request.yaml
│   ├── approve_change_request.yaml
│   ├── deploy_change_request.yaml
│   └── ...
├── it_ops_runbook/
│   ├── execute_runbook_step.yaml
│   ├── escalate_incident.yaml
│   └── ...
└── _shared/
    ├── read_resource.yaml
    └── request_lease.yaml
```

### 3.3 Manifest format

Each YAML file contains one ActionContract as a dict matching the existing `load_action_contract(data: dict)` input format. Example:

```yaml
# action_catalogs/ci_change_control/submit_change_request.yaml
action_name: submit_change_request
description: "Submit a drafted change request for review. Validates required fields and transitions state from draft to submitted."
resource_type: change_request
action_family: mutate
input_schema_ref: schemas/change_request_submit_input.json
output_schema_ref: schemas/change_request_submit_output.json
guard_predicates:
  - name: state_is_draft
  - name: required_fields_complete
  - name: edit_lease_held
required_capabilities:
  - change_request_modify
required_trust_tier: T2/bounded
idempotency_required: true
idempotency_scope: resource
retry_class: recheck_then_retry
risk_level: moderate
participates_in_saga: true
compensation_strategy: inverse_action
compensation_order_hint: 20
consistency_profile: EVENTUAL
authoritative_recheck_required: true
budget_cost_units: 3.0
budget_dimensions_consumed:
  - mutate
```

### 3.4 Loading behavior

| Event | Behavior |
|---|---|
| Service startup | Walk `action_catalogs/` directory, load all YAML files, validate through Pydantic, register into ContractRegistry. Log count and any validation failures. Service starts even if some files fail validation (degraded mode with warnings). |
| File change (optional, v1.1) | Watch directory for changes, reload affected contracts. Not required for v1.0. |
| Invalid manifest | Log error with file path and validation failure details. Skip the file. Do not crash. |

### 3.5 Catalog versioning

The service exposes a `catalog_version` field in every response. This is a content-addressed hash of all loaded manifest files (sorted by path, concatenated, SHA-256). If the catalog changes, the version changes. Consumers can cache discovery results keyed on catalog_version.

---

## 4 — Semantic Search Layer

### 4.1 Problem

The existing `execute_discovery()` kernel filters by structured fields: resource_type, action_family, trust_tier, capability exclusions. This handles "show me all mutate actions for change_request" but not "what tools help me handle a failing CI pipeline?" Semantic search adds the ability to match actions by natural language task description against action descriptions.

### 4.2 Design

On catalog load, each ActionContract's `description` field is embedded using a sentence-level embedding model. Embeddings are stored in an in-memory vector store. When a query includes `task_context` (natural language), the semantic search layer ranks all actions by cosine similarity to the task_context embedding, then passes the ranked results to the existing kernel for capability/trust filtering.

```
Query with task_context
│
├── 1. Embed task_context string
├── 2. Cosine similarity against all action embeddings
├── 3. Rank by similarity, take top N candidates
├── 4. Pass candidates to execute_discovery() for capability/trust filtering
├── 5. Return filtered + ranked results
│
▼
ActionDiscoveryResponse
```

### 4.3 Embedding model

| Requirement | Decision |
|---|---|
| Model | sentence-transformers (e.g., `all-MiniLM-L6-v2`) — small, fast, runs locally in Docker |
| Embedding dimension | 384 (for MiniLM-L6-v2) |
| Storage | In-memory NumPy array or FAISS flat index. No external database. |
| Rebuild | On catalog load. Embeddings are computed at startup and cached in memory. |
| Fallback | If embedding model fails to load, semantic search is disabled. Structured filtering still works. Service logs a warning but does not crash. |

### 4.4 Search behavior

| Query field | Behavior |
|---|---|
| `task_context` present | Semantic search runs first, produces ranked candidates. Kernel filters for permissions. Results are ordered by similarity score. |
| `task_context` absent | No semantic search. Kernel runs structured filtering only. Results are ordered by action_name (deterministic). |
| `task_context` + `resource_type` or `action_family` | Structured filters narrow the candidate set first, then semantic search ranks within that set. |

### 4.5 Similarity threshold

Results below a configurable similarity threshold (default: 0.3) are excluded even if they pass capability filtering. This prevents low-relevance actions from appearing in results. The threshold is configurable via environment variable (`ACTION_DISCOVERY_SIMILARITY_THRESHOLD`).

---

## 5 — Service Wrapper Layer

### 5.1 Transport pattern

Following the established ForgeWorks convention (Pattern 1), the service is exposed as a Python module with a `run()` function that can be imported via `importlib.util.spec_from_file_location`. No HTTP server. No gRPC. No subprocess piping.

```python
# action_discovery_service/run.py

def run(query: dict, capability_set: dict, session_context: dict | None = None) -> dict:
    """
    Entry point for ActionDiscovery.
    
    Matches _ok/_error envelope convention from service_wrapper.py.
    
    Args:
        query: ActionDiscoveryQuery fields as a dict
        capability_set: CapabilitySet fields as a dict
        session_context: Optional session metadata for trust_tier resolution
    
    Returns:
        {"status": "ok", "payload": ActionDiscoveryResponse as dict}
        or
        {"status": "error", "error": {"code": "...", "message": "...", ...}}
    """
```

### 5.2 Response envelope

Matches the `_ok()` / `_error()` convention already established in `service_wrapper.py`:

```json
// Success
{
  "status": "ok",
  "payload": {
    "available_actions": [...],
    "filtered_by": {...},
    "total_available": 42,
    "recommendation": {...},
    "catalog_version": "sha256:abc123..."
  }
}

// Error
{
  "status": "error",
  "error": {
    "code": "CATALOG_EMPTY",
    "message": "No ActionContracts loaded. Check action_catalogs/ directory.",
    "stage": "discovery",
    "details": {}
  }
}
```

### 5.3 Session/capability resolution

The existing kernel expects a `CapabilitySet` object. The service wrapper resolves this from the caller-supplied dict:

| Input | Resolution |
|---|---|
| `capability_set` dict provided | Deserialize into CapabilitySet dataclass directly |
| `session_context` with `agent_class_id` provided | Look up AgentClass → resolve CapabilitySet(s) → compose. Requires AgentClass definitions in the catalog. |
| Neither provided | Return error: `MISSING_CAPABILITY_CONTEXT` |

### 5.4 Error codes

| Code | Meaning | Retryable |
|---|---|---|
| `CATALOG_EMPTY` | No ActionContracts loaded on startup | No — operational issue |
| `CATALOG_LOAD_PARTIAL` | Some manifests failed validation; catalog is degraded | No — warning, not blocking |
| `MISSING_CAPABILITY_CONTEXT` | No capability_set or session_context provided | No — caller error |
| `SEMANTIC_SEARCH_UNAVAILABLE` | Embedding model failed to load | No — degraded mode, structured search still works |
| `INVALID_QUERY` | Query dict doesn't match ActionDiscoveryQuery schema | No — caller error |

---

## 6 — Docker Packaging

### 6.1 Container contents

```
action_discovery_service/
├── Dockerfile
├── run.py                          # Service wrapper entry point
├── catalog_loader.py               # Persistence layer
├── semantic_search.py              # Embedding + vector search
├── config.py                       # Environment variable handling
├── action_catalogs/                # Mounted volume or baked in
│   ├── ci_change_control/
│   ├── it_ops_runbook/
│   └── _shared/
├── requirements.txt                # sentence-transformers, numpy, pyyaml, faiss-cpu
└── tests/
    ├── test_catalog_loader.py
    ├── test_semantic_search.py
    └── test_service_wrapper.py
```

### 6.2 Startup sequence

```
1. Load config from environment variables
2. Walk action_catalogs/ directory
3. Validate and register all YAML manifests into ContractRegistry
4. Compute catalog_version hash
5. Load embedding model (sentence-transformers)
6. Embed all action descriptions
7. Build vector index
8. Log startup summary: N contracts loaded, M failed, semantic search enabled/disabled
9. Service ready
```

### 6.3 Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ACTION_CATALOG_DIR` | `./action_catalogs` | Path to YAML manifest directory |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model name |
| `ACTION_DISCOVERY_SIMILARITY_THRESHOLD` | `0.3` | Minimum cosine similarity for semantic results |
| `ACTION_DISCOVERY_MAX_RESULTS` | `10` | Default max_results if not specified in query |
| `LOG_LEVEL` | `INFO` | Service log level |

### 6.4 Health check

The container exposes a simple health check via a `health()` function (not HTTP — called by the orchestrator via importlib, same as `run()`):

```python
def health() -> dict:
    return {
        "status": "healthy" | "degraded" | "unhealthy",
        "catalog_loaded": True | False,
        "contracts_registered": 42,
        "contracts_failed": 0,
        "semantic_search_enabled": True | False,
        "catalog_version": "sha256:abc123...",
        "uptime_seconds": 3600
    }
```

---

## 7 — Normative Rules (from CONCORD v0.4 spec)

These rules are inherited from the ActionDiscovery contract in the CONCORD v0.4 gap analysis and must be preserved in the service implementation:

1. ActionDiscovery MUST filter results by the requesting session's AgentClass and CapabilitySet. An agent MUST NOT discover actions it cannot admit.
2. When `include_schemas = false` (default), the service returns lightweight summaries to minimize context consumption. Full schemas are fetched on demand.
3. ActionDiscovery responses are **advisory** (consistent with OperationContext semantics). Discovery of an action does not guarantee admission.
4. The service MUST cache and version its catalog. Cache invalidation MUST occur when manifests are added, removed, or modified.
5. The response MUST carry no `authoritative_for_mutation` field — it is advisory throughout.

---

## 8 — What This Service Does NOT Do

| Out of scope | Reason |
|---|---|
| Intent admission | ActionDiscovery is advisory. Admission is CONCORD's coordination layer. |
| Action execution | Discovery tells you what's available, not how to run it. |
| ForgeGate policy evaluation | ForgeGate is a separate seam. ActionDiscovery may discover actions that ForgeGate would later deny. |
| Cross-service HTTP API | Transport is importlib (Pattern 1). No HTTP server in v1.0. |
| Real-time catalog sync from external sources | v1.0 loads from disk at startup. Live sync is a future extension. |
| AgentClass/CapabilitySet persistence | Those are CONCORD entities. ActionDiscovery reads them; it doesn't own them. |

---

*End of core specification. Three layers: catalog persistence (YAML manifests → ContractRegistry), semantic search (embeddings + vector ranking), service wrapper (importlib + _ok/_error envelope).*
