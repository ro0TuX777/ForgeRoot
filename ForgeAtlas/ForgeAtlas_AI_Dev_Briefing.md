# ForgeAtlas — AI Developer Briefing

**Application:** ForgeAtlas (ActionDiscovery Service)
**Date:** March 2026
**Audience:** New AI Developer assigned to build ForgeAtlas
**Companion documents:** ForgeAtlas Core Specification, Implementation Plan, Punch List

---

## What You're Building

ForgeAtlas is the action discovery and tool selection service for a multi-framework agentic engineering system. When an agent needs to know "what can I do right now, given who I am and what I'm working on?" — ForgeAtlas answers that question.

The name comes from its role: it's the atlas — the map — of all available actions across the system. Agents query ForgeAtlas to discover which tools, actions, and capabilities are available to them without needing every action definition loaded into their context window.

The closest industry parallel is Stripe's "tool shed" — a centralized meta-tool that helps agents discover and select from hundreds of available tools. ForgeAtlas is our version, built to integrate with our specific governance and execution frameworks.

---

## Why This Exists

The system you're joining has five frameworks that work together:

| Framework | Role | One-liner |
|---|---|---|
| **CONCORD** | Governance specification | Defines who can do what, under what rules, with what accountability |
| **ForgeGate** | Intent governance | Deterministic gate that returns ALLOW/DENY on proposed actions |
| **ForgeWorks** | T&E pipeline | Ingests domain data, runs governed agent workflows, scores outcomes |
| **ForgeScaffold** | Blueprint generation | Analyzes codebases, produces structural maps, governs change application |
| **DAWN** | Execution engine | Runs pipelines with sandboxed links, artifact contracts, and audit ledgers |

As the number of ActionContracts grows (actions an agent can take), you hit a scaling problem: you can't load 500 action definitions into an agent's context window. The agent needs a way to query "show me the relevant actions for my task" and get back a focused, filtered, ranked list.

ForgeAtlas solves this. It's a queryable catalog that:

1. **Persists** ActionContracts as YAML manifests on disk (they don't exist on disk today — only in test memory)
2. **Filters** results by the agent's trust tier and capabilities (an agent never discovers actions it can't use)
3. **Ranks** results by semantic similarity when the agent describes their task in natural language
4. **Serves** results via the same Python import pattern the rest of the system uses

---

## How It Fits in the Architecture

```
╔═══════════════════════════════════════════════════╗
║              CONCORD (governance)                  ║
║                                                    ║
║  AgentClass ── CapabilitySet ── BudgetProfile      ║
║  Session ── Intent ── Lease ── Receipt             ║
║                                                    ║
║       ┌──────────────────────┐                     ║
║       │     ForgeAtlas        │ ◀── YOU ARE HERE   ║
║       │  ActionDiscovery      │                     ║
║       │  Service              │                     ║
║       └──────────┬───────────┘                     ║
║                  │                                  ║
║    Agents query ForgeAtlas to discover              ║
║    available actions before forming Intents         ║
║                  │                                  ║
╚══════════════════╪══════════════════════════════════╝
                   │
          ForgeAtlas responses are ADVISORY
          (discovery ≠ admission)
                   │
          Agent forms Intent → CONCORD admits or rejects
                                    │
                              ForgeGate evaluates (step 5)
                                    │
                              DAWN executes
```

ForgeAtlas sits in the planning phase — before an agent commits to an action. It tells the agent what's available. The agent then forms an Intent, which goes through CONCORD's admission pipeline (where ForgeGate is called at step 5). ForgeAtlas is never authoritative — discovering an action doesn't guarantee it will be admitted.

---

## What Already Exists (You're Wrapping, Not Rebuilding)

The core filtering logic is built and tested. You are building the service shell around it.

### Existing code you'll use

| Asset | Location | What it does |
|---|---|---|
| `execute_discovery()` | `dawn/concord/discovery_kernel.py` | The main query function. Takes a registry, a query, and a capability set. Returns filtered results. This is the engine inside ForgeAtlas. |
| `is_action_permitted()` | `dawn/concord/discovery_kernel.py` | Five-check filter chain: exclusions → restricted_resource_types → allowed_resource_types → allowed_action_families → required_trust_tier. Runs in order, first failure = denied. |
| `ActionDiscoveryQuery` | `dawn/concord/types/` | Dataclass for the query input (resource_type, action_family, task_context, max_results, include_schemas) |
| `ActionDiscoveryResponse` | `dawn/concord/types/` | Dataclass for the query output (available_actions, filtered_by, total_available, recommendation, catalog_version) |
| `ActionSummary` | `dawn/concord/types/` | Lightweight action representation returned in results (name, family, risk, description, guard summary) |
| `ContractRegistry` | `dawn/concord/` kernel layer | In-memory registry backed by two dicts. Has `register_action()` and lookup methods. Currently **empty** — nothing populates it outside test fixtures. |
| `load_action_contract()` | `dawn/concord/` kernel layer | Takes a Python dict, validates through Pydantic, returns an ActionContract dataclass. This is your YAML → registry bridge. |

### What does NOT exist (you're building this)

| Component | Purpose |
|---|---|
| **Catalog persistence layer** | YAML manifests on disk → loaded into ContractRegistry on startup |
| **Semantic search layer** | Embed action descriptions → rank by similarity to natural language queries |
| **Service wrapper** | `run()` function callable via importlib, returning `_ok/_error` envelope dicts |
| **Docker packaging** | Container that runs the service with catalog as a mounted volume |

---

## The Transport Pattern You Must Follow

The system does **not** use HTTP between services. It uses direct Python imports via `importlib`. This pattern is already established and you must match it exactly.

The reference implementation is in `forgeworks/runner/forgescaffold_coding_context.py`:

```python
def _import_fs_module(link_name: str):
    """Dynamically import a ForgeScaffold run.py as a module."""
    import importlib.util
    run_py = FS_LINKS / link_name / "run.py"
    spec = importlib.util.spec_from_file_location(f"fs_{link_name}", run_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
```

Your service must expose a `run.py` with a `run()` function and a `health()` function. Callers import it with this pattern and call the functions directly. No HTTP server, no gRPC, no subprocess piping.

The response envelope convention is from `forgeworks/sam/service_wrapper.py`:

```python
# Success
{"status": "ok", "payload": { ... }}

# Failure  
{"status": "error", "error": {"code": "...", "message": "...", "stage": "...", "details": {}}}
```

Your `run()` function must never raise exceptions to the caller. All errors are caught internally and returned as structured `_error` dicts.

---

## The Key Design Constraint

**An agent must never discover actions it cannot admit.**

This is the security invariant. ForgeAtlas filters every result through the requesting agent's CapabilitySet and trust tier. If an agent is T1/propose with no `deploy` capability, it will never see `deploy_change_request` in results — even if that action exists in the catalog and even if the semantic search would rank it highly.

The five-check filter chain in `is_action_permitted()` enforces this. You don't need to rebuild it — it's already implemented. But your service wrapper must ensure that every query path (structured, semantic, or combined) passes through this filter. There is no code path that returns unfiltered results.

---

## The Semantic Search Requirement

ForgeAtlas must support natural language queries. When an agent asks "what tools help me handle a failing CI pipeline?" the service should return relevant actions ranked by similarity, not just exact-match filtering on resource_type or action_family.

This requires:

1. An embedding model (`all-MiniLM-L6-v2` from sentence-transformers — runs locally, no external API)
2. Embedding all ActionContract `description` fields at startup
3. A cosine similarity ranking step that runs before the capability filter
4. A configurable threshold (default 0.3) below which results are excluded

Semantic search is additive — it ranks candidates before the existing kernel filters them. It never bypasses capability filtering.

If the embedding model fails to load, the service must degrade gracefully: structured filtering still works, semantic search is disabled, health endpoint reports `semantic_search_enabled: false`. ForgeAtlas must never crash because a model file is missing.

---

## Files You Must Read Before Writing Code

In this order:

| # | File | Why |
|---|---|---|
| 1 | `dawn/concord/discovery_kernel.py` | The engine you're wrapping. Understand every function. |
| 2 | `dawn/concord/types/` — ActionDiscoveryQuery, ActionDiscoveryResponse, ActionSummary, CapabilitySet, ActionContract | The data contracts you serialize/deserialize. |
| 3 | `dawn/concord/types/enums.py` | TrustTier, RiskLevel, ActionFamily, ConsistencyProfile — you'll use these in YAML manifests. |
| 4 | `forgeworks/sam/service_wrapper.py` | The `_ok/_error` convention and `execute_planner_request()` as an example of the service style you're matching. |
| 5 | `forgeworks/runner/forgescaffold_coding_context.py` | The importlib pattern your service must be callable through. |
| 6 | CONCORD v0.3 Runtime Contract Schemas §8 | The `change_request` worked example. Your seed YAML manifests implement these exact contracts. |

---

## What Success Looks Like

When you're done, this works:

```python
# A caller imports ForgeAtlas via importlib (same pattern as ForgeScaffold)
atlas = _import_module("forge_atlas")

# Structured query: "show me mutate actions for change_request"
result = atlas.run(
    query={"resource_type": "change_request", "action_family": "mutate", "max_results": 5},
    capability_set={"allowed_action_families": ["mutate"], "restricted_resource_types": []},
)
# result["status"] == "ok"
# result["payload"]["available_actions"] → list of ActionSummary dicts
# result["payload"]["catalog_version"] → "sha256:abc123..."

# Semantic query: "I need to get a code change approved"
result = atlas.run(
    query={"task_context": "I need to get a code change reviewed and approved", "max_results": 5},
    capability_set={"allowed_action_families": ["mutate", "approve"], "restricted_resource_types": []},
)
# result["payload"]["available_actions"] → ranked by relevance
# approve_change_request and submit_change_request should rank high

# Capability filtering: agent without deploy rights never sees deploy actions
result = atlas.run(
    query={"task_context": "deploy to production"},
    capability_set={"allowed_action_families": ["mutate"], "restricted_resource_types": []},
)
# deploy_change_request does NOT appear — agent lacks deploy capability

# Health check
health = atlas.health()
# health["status"] == "healthy"
# health["contracts_registered"] == 8
# health["semantic_search_enabled"] == True
```

---

## What You Must NOT Build

| Out of scope | Why |
|---|---|
| Intent admission logic | ForgeAtlas is advisory. CONCORD's admission pipeline handles authorization. |
| HTTP server or API | Transport is importlib. No FastAPI, no Flask, no sockets. |
| Action execution | ForgeAtlas discovers actions. It doesn't run them. |
| ForgeGate integration | ForgeGate is a separate seam. ForgeAtlas may discover actions that ForgeGate would later deny at phase level. |
| AgentClass/CapabilitySet storage | Those are CONCORD entities. ForgeAtlas reads them from caller-supplied dicts. |
| Cross-run catalog sync | v1.0 loads from disk at startup. Live sync from external sources is future work. |
| UI | ForgeAtlas is a programmatic service. No web interface. |

---

## Build Phases (Summary)

| Phase | What you build | Tests |
|---|---|---|
| **1. Catalog Persistence** | YAML manifests on disk + loader + registry hydration | 10–15 tests |
| **2. Service Wrapper** | `run()` + `health()` + `_ok/_error` envelope + capability resolution | 10–15 tests |
| **3. Semantic Search** | Embedding model + vector store + similarity ranking + graceful degradation | 10–15 tests |
| **4. Docker Packaging** | Dockerfile + startup sequence + integration tests + contract verification | 5–10 tests |

**Total: 35–55 tests across 5–7 sessions.**

Detailed acceptance criteria for every deliverable are in the Punch List document.

---

## The Forge Family

For context on where ForgeAtlas sits in the naming:

| Framework | Role |
|---|---|
| **ForgeWorks** | Builds and evaluates (T&E pipeline) |
| **ForgeGate** | Governs actions (intent gate) |
| **ForgeScaffold** | Maps structure (blueprint generation) |
| **ForgeAtlas** | Discovers tools (action catalog + search) |

They all run on **DAWN** (execution engine) under **CONCORD** (governance specification).

---

*End of briefing. Read the six files listed above, then start with Phase 1: catalog persistence. The kernel is ready — you're building the world around it.*
