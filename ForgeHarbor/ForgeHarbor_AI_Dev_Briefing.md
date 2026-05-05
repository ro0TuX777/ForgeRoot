# ForgeHarbor — AI Developer Briefing

**Application:** ForgeHarbor (Warm-Pool ExecutionEnvironment Orchestrator)
**Date:** March 2026
**Audience:** New AI Developer assigned to build ForgeHarbor
**Companion documents:** ForgeHarbor Core Specification, Implementation Plan, Punch List

---

## What You're Building

ForgeHarbor is the warm-pool orchestrator for agent execution environments. When an agent session needs an isolated place to run — a container pre-loaded with the DAWN runtime, relevant code, and dependencies — ForgeHarbor assigns one from a warm pool in seconds instead of cold-starting from scratch.

The name comes from its role: a harbor where execution environments are provisioned, sheltered, and dispatched to agent sessions on demand.

The closest industry parallel is Stripe's "devbox pool" — pre-warmed EC2 instances where each coding agent gets its own isolated developer environment that mirrors what human engineers have. Stripe spins these up in ~10 seconds from a warm pool. ForgeHarbor is our version, built to manage Docker containers running the DAWN execution engine.

---

## Why This Exists

The system you're joining has five frameworks plus one recently completed service:

| Framework/Service | Role |
|---|---|
| **CONCORD** | Governance specification — who can do what, under what rules |
| **ForgeGate** | Intent governance — ALLOW/DENY on proposed actions |
| **ForgeWorks** | T&E pipeline — runs governed agent workflows, scores outcomes |
| **ForgeScaffold** | Blueprint generation — maps codebases, governs change application |
| **DAWN** | Execution engine — runs pipelines with sandboxed links and audit ledgers |
| **ForgeAtlas** | Action discovery — agents query available tools (just completed, 95 tests) |

Agents need isolated environments to execute in. Without a pool manager, every agent session starts cold — provisioning a container, loading dependencies, cloning repos. That's slow and breaks the parallelization model where one engineer dispatches multiple agent sessions simultaneously.

ForgeHarbor solves this by maintaining a warm pool (target: 3 containers) of pre-provisioned execution environments. When a session needs one, ForgeHarbor assigns a warm environment instantly. When the session ends, ForgeHarbor drains the environment and recycles it.

---

## How It Fits in the Architecture

```
CONCORD (governance)
│
├── ForgeAtlas ← discovers actions (planning phase)
│
│   ...admission pipeline...
│
├── ForgeHarbor ← provisions environments  ◀── YOU ARE HERE
│       │
│       │ assigns warm container
│       ▼
DAWN (execution engine inside the container)
│
├── ForgeWorks pipeline runs here
├── ForgeScaffold analysis runs here
├── ForgeGate evaluates here
```

ForgeHarbor sits between the governance layer (CONCORD admits an agent session) and the execution layer (DAWN runs work inside a container). It manages the containers that DAWN runs inside. It doesn't know what work happens inside the container — that's DAWN's job.

---

## What Already Exists

The ExecutionEnvironment entity and part of its lifecycle are already built. You're completing the lifecycle and building the pool management around it.

### Existing code you'll use

| Asset | Location | What it does |
|---|---|---|
| `ExecutionEnvironment` entity | `dawn/concord/types/entities.py` | The dataclass you're managing. Has fields for environment_id, status, assigned_session_id, resource_spec, preload_manifest, heartbeat_interval_ms, etc. |
| `EnvironmentStatus` enum | `dawn/concord/types/enums.py` | COLD, WARMING, READY, ASSIGNED, DRAINING, UNHEALTHY, TERMINATED — the statuses your state machine transitions between. |
| `mark_environment_unhealthy()` | `dawn/concord/environment_kernel.py` | Sets status → UNHEALTHY. Already built. You call this; you don't rebuild it. |
| `get_blocking_intents()` | `dawn/concord/environment_kernel.py` | Finds intents in ADMITTED or EXECUTING status. Used to gate teardown. Already built. |
| `handle_unhealthy_environment()` | `dawn/concord/environment_kernel.py` | Full unhealthy → compensate → terminate path. Already built. Your heartbeat monitor triggers this when it detects a failed container. |

### What does NOT exist (you're building this)

| Component | Purpose |
|---|---|
| **Lifecycle Engine** | The forward state machine: COLD → WARMING → READY → ASSIGNED → DRAINING → TERMINATED. Transition guards. Assign/drain/recycle logic. |
| **Provider Interface** | Abstract interface for provisioning backends. DockerProvider as v1.0 implementation. |
| **Pool Manager** | Maintains warm pool at target size. Assigns environments. Reconciliation loop. |
| **Heartbeat Monitor** | Background loop detecting container failures. Triggers existing unhealthy path. |
| **Daemon** | Long-running process with background loops, caller-facing functions, graceful shutdown. |

---

## The Key Difference From ForgeAtlas

ForgeAtlas is **stateless** — load catalog, answer query, done. Every call is independent.

ForgeHarbor is **stateful** — it manages a pool of live containers with ongoing lifecycle transitions, heartbeats, and background reconciliation. It's a long-running daemon, not a request-response service. This fundamentally changes the architecture:

| Dimension | ForgeAtlas | ForgeHarbor |
|---|---|---|
| Process model | Stateless, importlib callable | Long-running daemon |
| Background work | None | Pool reconciliation loop + heartbeat monitor loop |
| State | Catalog loaded once at startup | Pool state changes continuously (environments transition, get assigned, get recycled) |
| Concurrency | Single-threaded per call | Thread-safe pool assignment + background threads |
| Shutdown | Just stop | Graceful drain: wait for intents, terminate containers, clean exit |
| Docker dependency | None (runs inside a container) | Manages other containers (Docker socket mount) |

---

## The State Machine (Your Core Deliverable)

This is the full lifecycle you need to implement. The existing kernel only covers the UNHEALTHY → TERMINATED path (the right side). You build everything else.

```
COLD ──provision()──→ WARMING ──on_warm_complete()──→ READY
                         │                              │
                    on_provision_failure()          assign(session_id)
                         │                              │
                         ▼                              ▼
                    TERMINATED                     ASSIGNED
                         ▲                           │         │
                         │                   session ends    heartbeat fails
                    on_drain_complete()           │              │
                         │                        ▼              ▼
                      DRAINING               DRAINING       UNHEALTHY
                                                │              │
                                         on_drain_complete()   │
                                                │         (existing kernel)
                                                ▼              │
                                           TERMINATED ◀────────┘
```

Every transition must pass through `can_transition(from, to)`. No direct jumps. Invalid transitions return structured errors.

---

## The Provider Interface

ForgeHarbor manages Docker containers via an abstract provider interface. This means the pool management logic (Phase 1 + 3) can be tested entirely without Docker using a MockProvider.

```python
class EnvironmentProvider:
    def provision(self, environment_id, spec) → result
    def check_health(self, environment_id) → health_status
    def terminate(self, environment_id) → result
    def get_connection_info(self, environment_id) → connection_info
```

v1.0 ships DockerProvider. The interface is designed so KubernetesProvider can be added later without changing pool management logic.

---

## The Pool (Target: 3 Warm Environments)

ForgeHarbor maintains 3 READY environments at all times. When one is assigned to a session, the reconciliation loop provisions a replacement. When a session ends, the environment is drained and recycled.

```
Steady state:  [READY] [READY] [READY]

After assignment:  [ASSIGNED] [READY] [READY]
                   └── reconcile: provision 1 more ──→ [WARMING]

After warm-up:  [ASSIGNED] [READY] [READY] [READY]
                (4 total, back to 3 ready)

After release:  [DRAINING] [READY] [READY] [READY]
                └── drain complete → TERMINATED → removed from pool
                
Final:  [READY] [READY] [READY]  (back to steady state)
```

---

## Files You Must Read Before Writing Code

In this order:

| # | File | Why |
|---|---|---|
| 1 | `dawn/concord/environment_kernel.py` | The existing unhealthy/teardown path. You trigger this; you don't rebuild it. |
| 2 | `dawn/concord/types/entities.py` (ExecutionEnvironment) | The entity you're managing. Know every field. |
| 3 | `dawn/concord/types/enums.py` (EnvironmentStatus, EnvironmentClass, IsolationLevel) | The status values your state machine uses. |
| 4 | `forgeworks/sam/service_wrapper.py` | The `_ok/_error` envelope convention your caller-facing functions must match. |
| 5 | ForgeHarbor Core Specification | The full architectural spec. |
| 6 | CONCORD v0.4 Gap Analysis §Gap 1 | The original ExecutionEnvironment entity proposal with normative rules. |

---

## What Success Looks Like

When you're done:

```python
# Daemon starts, provisions 3 environments
harbor = ForgeHarborDaemon(config)
harbor.start()
# Logs: "ForgeHarbor started: 3 environments READY, DockerProvider, pool target=3"

# Request an environment for a session
result = harbor.request_environment("sess-1")
# result == {"status": "ok", "payload": {"environment_id": "env-1", "connection_info": {...}}}

# Pool replenishes automatically (reconciliation loop)
status = harbor.get_pool_status()
# 2 READY, 1 ASSIGNED, 1 WARMING (replacement being provisioned)

# Session ends, release the environment
harbor.release_environment("env-1")
# env-1 transitions: ASSIGNED → DRAINING → TERMINATED
# Pool reconciles back to 3 READY

# Container dies unexpectedly
# Heartbeat monitor detects → calls mark_environment_unhealthy()
# Existing kernel handles compensation and teardown
# Pool reconciles: provisions replacement

# Shutdown
harbor.shutdown()
# All environments drained, all containers terminated, clean exit
```

---

## What You Must NOT Build

| Out of scope | Why |
|---|---|
| Intent admission | CONCORD handles whether work is allowed. ForgeHarbor provisions where it runs. |
| Action discovery | ForgeAtlas handles tool discovery. |
| Pipeline execution | DAWN handles execution inside the container. |
| ForgeGate evaluation | Governance decisions happen above ForgeHarbor. |
| Saga compensation logic | The existing environment_kernel.py handles compensation. You trigger it via the heartbeat monitor. |
| Session creation/validation | CONCORD manages sessions. ForgeHarbor reads session_id from callers. |
| KubernetesProvider | v1.0 is Docker only. The abstract interface supports future K8s, but don't build it now. |

---

## Build Phases (Summary)

| Phase | What you build | Docker required | Tests |
|---|---|---|---|
| **1. Lifecycle Engine** | State machine (pure logic) | No | 15–20 |
| **2. Provider Interface** | Abstract provider + DockerProvider | Yes (integration) | 10–15 |
| **3. Pool Manager** | Reconciliation, assignment, release | No (MockProvider) | 15–20 |
| **4. Heartbeat + Daemon** | Background loops, shutdown, entry point | Partial | 10–15 |
| **5. Docker Packaging** | Dockerfile, config, integration test | Yes | 5–10 |

**Total: 55–80 tests across 8–12 sessions.**

Phase 1 is pure logic — start there. You can build and test the entire state machine without Docker. That's intentional.

---

## The Forge Family

For context on where ForgeHarbor sits in the naming:

| Framework/Service | Role |
|---|---|
| **ForgeWorks** | Builds and evaluates (T&E pipeline) |
| **ForgeGate** | Governs actions (intent gate) |
| **ForgeScaffold** | Maps structure (blueprint generation) |
| **ForgeAtlas** | Discovers tools (action catalog + search) |
| **ForgeHarbor** | Provisions environments (warm pool orchestrator) |

They all run on **DAWN** (execution engine) under **CONCORD** (governance specification).

---

*End of briefing. Read the six files listed above, then start with Phase 1: lifecycle engine. The entire state machine can be built and tested as pure Python with no Docker dependency. That's your foundation.*
