# ForgeHarbor — Core Specification

**Status:** Draft v0.1 — 2026-03-07
**Framework:** CONCORD v0.4 (ExecutionEnvironment entity), DAWN (execution substrate)
**Depends on:** environment_kernel.py (unhealthy/teardown path — existing), ExecutionEnvironment entity (existing)
**Deployment:** Long-running daemon (Docker container managing other Docker containers)

---

## 1 — Purpose

ForgeHarbor is the warm-pool orchestrator for ExecutionEnvironment instances. It manages the full lifecycle of isolated execution environments — provisioning, warming, assignment to agent sessions, heartbeat monitoring, graceful draining, and teardown — so that agents can be dispatched into ready environments without cold-start delays.

ForgeHarbor manages the containers that DAWN runs inside. Each ForgeHarbor environment is a Docker container pre-loaded with the DAWN runtime, relevant codebase artifacts, and service dependencies. When a session needs an execution environment, ForgeHarbor assigns one from the warm pool in seconds rather than provisioning from scratch.

---

## 2 — Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    ForgeHarbor Daemon                         │
│                                                              │
│  ┌────────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │  Pool Manager   │  │  Lifecycle    │  │  Heartbeat      │ │
│  │                 │  │  Engine       │  │  Monitor        │ │
│  │  Maintains      │  │              │  │                  │ │
│  │  target pool    │  │  Drives the  │  │  Watches live    │ │
│  │  size, assigns  │  │  state       │  │  environments,   │ │
│  │  environments,  │  │  machine     │  │  detects         │ │
│  │  recycles       │  │              │  │  failures        │ │
│  └───────┬─────────┘  └──────┬───────┘  └───────┬──────────┘ │
│          │                   │                   │            │
│          └───────────┬───────┘                   │            │
│                      ▼                           │            │
│          ┌───────────────────────┐               │            │
│          │  Provider Interface    │◀──────────────┘            │
│          │  (abstract)           │                            │
│          └───────────┬───────────┘                            │
│                      │                                        │
│              ┌───────┴───────┐                                │
│              ▼               ▼                                │
│     ┌──────────────┐ ┌──────────────┐                        │
│     │ DockerProvider│ │ K8sProvider  │                        │
│     │ (v1.0)       │ │ (future)     │                        │
│     └──────────────┘ └──────────────┘                        │
└─────────────────────────────────────────────────────────────┘
         │
         │ manages
         ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ Environment A    │  │ Environment B    │  │ Environment C    │
│ (Docker container│  │ (Docker container│  │ (Docker container│
│  running DAWN)   │  │  running DAWN)   │  │  running DAWN)   │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

Four components:

| Component | Responsibility |
|---|---|
| Pool Manager | Maintains target pool size (3 for v1.0). Provisions new environments when pool drops below target. Assigns ready environments to sessions. Recycles terminated environments. |
| Lifecycle Engine | Drives the ExecutionEnvironment state machine: COLD → WARMING → READY → ASSIGNED → DRAINING → TERMINATED. Enforces valid transitions. |
| Heartbeat Monitor | Background loop that checks liveness of all ASSIGNED and WARMING environments. Detects failures and triggers the existing unhealthy/teardown path in environment_kernel.py. |
| Provider Interface | Abstract interface for environment provisioning/teardown. DockerProvider is the v1.0 implementation. K8sProvider is a future addition behind the same interface. |

---

## 3 — ExecutionEnvironment State Machine

The full lifecycle that needs to be built. The existing `environment_kernel.py` only handles the UNHEALTHY → TERMINATED path (shown in red).

```
    ┌──────┐
    │ COLD │  Environment record created, not yet provisioning
    └──┬───┘
       │ provision()
       ▼
    ┌──────────┐
    │ WARMING  │  Container starting, preload manifest executing
    └──┬───────┘
       │ on_warm_complete()
       ▼
    ┌──────────┐
    │ READY    │  In warm pool, awaiting assignment
    └──┬───────┘
       │ assign(session_id)
       ▼
    ┌──────────┐
    │ ASSIGNED │  Bound to a session, DAWN running inside
    └──┬───────┘
       │                          │
       │ session ends normally    │ heartbeat fails / error
       │                          │
       ▼                          ▼
    ┌──────────┐           ┌───────────┐
    │ DRAINING │           │ UNHEALTHY │  ← existing kernel handles this
    └──┬───────┘           └──┬────────┘
       │ all intents          │ compensate blocking intents
       │ resolved             │
       ▼                      ▼
    ┌────────────┐      ┌────────────┐
    │ TERMINATED │      │ TERMINATED │  ← existing kernel drives this
    └────────────┘      └────────────┘
       │
       │ recycle (pool below target)
       ▼
    ┌──────┐
    │ COLD │  New environment record, cycle restarts
    └──────┘
```

### 3.1 Transition table

| From | To | Trigger | Guard |
|---|---|---|---|
| COLD | WARMING | `provision()` | Pool below target size |
| WARMING | READY | `on_warm_complete()` | Preload manifest completed successfully |
| WARMING | TERMINATED | Provisioning failure or timeout | Provider reports error |
| READY | ASSIGNED | `assign(session_id)` | Session is valid and needs environment |
| READY | DRAINING | Pool above target (scale-down) | No session assigned |
| ASSIGNED | DRAINING | Session ends normally | Session status is terminal |
| ASSIGNED | UNHEALTHY | Heartbeat failure or error | Existing kernel path |
| DRAINING | TERMINATED | All blocking intents resolved | `get_blocking_intents()` returns empty |
| UNHEALTHY | TERMINATED | Compensation complete | Existing kernel path |

### 3.2 Transition guard: `can_transition(from_status, to_status)`

A validator function that enforces the state machine topology. Every transition must pass through this guard. Invalid transitions are rejected with a structured error. This prevents direct jumps (e.g., COLD → ASSIGNED) that would bypass provisioning.

---

## 4 — Pool Manager

### 4.1 Pool policy

| Parameter | v1.0 value | Configurable |
|---|---|---|
| `target_pool_size` | 3 | Yes (environment variable) |
| `min_ready` | 1 | Yes — minimum READY environments maintained at all times |
| `max_environments` | 5 | Yes — hard ceiling including all statuses |
| `provision_timeout_ms` | 60000 | Yes — WARMING → READY deadline |
| `assignment_timeout_ms` | 5000 | Yes — max time to find and assign a READY environment |

### 4.2 Pool reconciliation loop

The Pool Manager runs a periodic reconciliation loop (every N seconds, configurable):

```
1. Count environments by status
2. If READY < min_ready AND total < max_environments:
   → Provision new environments (COLD → WARMING)
3. If total > max_environments AND READY > min_ready:
   → Drain excess READY environments (READY → DRAINING → TERMINATED)
4. Check WARMING environments for provision_timeout:
   → Timed out → TERMINATED
5. Check ASSIGNED environments for session liveness:
   → Session ended → DRAINING
```

### 4.3 Assignment

When a caller requests an environment:

```
1. Find first environment with status = READY
2. If found:
   → Transition READY → ASSIGNED
   → Set assigned_session_id
   → Set assigned_at timestamp
   → Return environment_id
3. If no READY environment available:
   → Return ENVIRONMENT_UNAVAILABLE error with estimated wait time
   → Trigger immediate provision if pool below target
```

Assignment must be atomic — two concurrent requests must not be assigned the same environment. This is enforced by the lifecycle engine's transition lock.

---

## 5 — Heartbeat Monitor

### 5.1 Design

A background thread/async loop that runs every `heartbeat_check_interval_ms` (default: 15000ms, configurable).

For every environment in ASSIGNED or WARMING status:

```
1. Query provider for container health (docker inspect or equivalent)
2. If container is running and responsive:
   → Update last_heartbeat timestamp
3. If container is not running OR last_heartbeat exceeds heartbeat_interval_ms:
   → Call existing mark_environment_unhealthy()
   → Existing kernel handles compensation and teardown
```

### 5.2 Integration with existing kernel

The heartbeat monitor is the **trigger** for the existing `environment_kernel.py` unhealthy path. When it detects a failure:

```
Heartbeat Monitor
    │ detects failure
    ▼
mark_environment_unhealthy(env)          ← existing function
    │
    ▼
handle_unhealthy_environment(            ← existing function
    env, session_intents, compensate_fn
)
    │
    ▼
TERMINATED (or stays UNHEALTHY if compensation incomplete)
```

ForgeHarbor calls the existing kernel functions. It does not reimplement the unhealthy/teardown logic.

---

## 6 — Provider Interface

### 6.1 Abstract interface

```python
class EnvironmentProvider:
    """Abstract interface for environment provisioning backends."""

    def provision(self, environment_id: str, spec: EnvironmentSpec) -> ProvisionResult:
        """Start a new environment. Returns when container is running (not necessarily ready)."""

    def check_health(self, environment_id: str) -> HealthStatus:
        """Check if the environment's container is running and responsive."""

    def terminate(self, environment_id: str) -> TerminateResult:
        """Stop and remove the environment's container."""

    def get_connection_info(self, environment_id: str) -> ConnectionInfo:
        """Return how to reach the environment (e.g., container ID, IP, mount paths)."""
```

### 6.2 EnvironmentSpec

What the provider needs to provision a container:

```
EnvironmentSpec:
    image:              str         Docker image (e.g., "dawn-runtime:latest")
    preload_manifest:   list        Artifacts/repos to mount or copy in
    resource_limits:    dict        CPU, memory, storage constraints
    network_mode:       str         Container network configuration
    environment_vars:   dict        Environment variables for DAWN runtime
    mounts:             list        Volume mounts (catalog directories, artifact stores, etc.)
```

### 6.3 DockerProvider (v1.0)

Implements EnvironmentProvider using the Docker SDK for Python (`docker` package).

| Operation | Docker SDK call |
|---|---|
| `provision()` | `client.containers.run(image, detach=True, ...)` |
| `check_health()` | `container.reload(); container.status` |
| `terminate()` | `container.stop(); container.remove()` |
| `get_connection_info()` | `container.attrs["NetworkSettings"]` |

### 6.4 Future: K8sProvider

Not built in v1.0. The provider interface is designed so that a KubernetesProvider can be added by implementing the same four methods using the `kubernetes` Python client. Pool Manager and Lifecycle Engine don't change.

---

## 7 — Service Interface

ForgeHarbor is a **long-running daemon**, not a stateless importlib call. It exposes functions for callers, but it also runs background loops (pool reconciliation, heartbeat monitoring) that execute independently of caller requests.

### 7.1 Caller-facing functions

```python
def request_environment(session_id: str, spec: dict | None = None) -> dict:
    """
    Request an execution environment for a session.
    Returns _ok with environment_id and connection_info, 
    or _error with ENVIRONMENT_UNAVAILABLE.
    """

def release_environment(environment_id: str) -> dict:
    """
    Signal that a session is done with an environment.
    Triggers ASSIGNED → DRAINING transition.
    Returns _ok or _error.
    """

def get_environment_status(environment_id: str) -> dict:
    """
    Query current status of a specific environment.
    Returns _ok with full environment state.
    """

def get_pool_status() -> dict:
    """
    Pool-wide status: counts by status, pool utilization, 
    average provision time, average assignment time.
    """

def health() -> dict:
    """
    Daemon health: pool status, heartbeat monitor running, 
    provider reachable, uptime.
    """
```

### 7.2 Response envelope

Same `_ok/_error` convention as ForgeAtlas and ForgeWorks:

```json
// Success
{"status": "ok", "payload": {"environment_id": "env-1", "connection_info": {...}}}

// Error
{"status": "error", "error": {"code": "ENVIRONMENT_UNAVAILABLE", "message": "...", "details": {"ready_count": 0, "warming_count": 1, "estimated_wait_ms": 15000}}}
```

### 7.3 Error codes

| Code | Meaning | Retryable |
|---|---|---|
| `ENVIRONMENT_UNAVAILABLE` | No READY environment in pool | Yes — with estimated_wait_ms |
| `ENVIRONMENT_NOT_FOUND` | Unknown environment_id | No |
| `INVALID_TRANSITION` | Requested transition violates state machine | No |
| `PROVISION_FAILED` | Docker provider failed to start container | Yes |
| `PROVISION_TIMEOUT` | Container didn't reach READY within deadline | Yes |
| `PROVIDER_UNREACHABLE` | Cannot connect to Docker daemon | No — operational issue |
| `POOL_AT_CAPACITY` | max_environments reached, no room to provision | Yes — wait for draining |
| `ASSIGNMENT_CONFLICT` | Environment was assigned to another session concurrently | Yes — retry assignment |

---

## 8 — CONCORD Integration Points

ForgeHarbor manages the ExecutionEnvironment entity defined in CONCORD v0.4. The integration points:

| CONCORD entity | ForgeHarbor interaction |
|---|---|
| ExecutionEnvironment | ForgeHarbor owns the lifecycle. Every state transition is reflected on the entity. |
| Session | `assigned_session_id` on the environment is set during assignment. Session's `environment_id` field (v0.4) should reference the ForgeHarbor-assigned environment. |
| Receipt | `environment_id` on Receipts (v0.4 field) traces back to the ForgeHarbor-managed environment. |
| BudgetProfile | `max_parallel_environments` field (v0.4) should be checked before assignment — if a session's AgentClass has hit its environment ceiling, assignment is denied. |
| CoordinationTelemetry | ForgeHarbor emits: `environment_pool_utilization`, `average_provision_time_ms`, `environment_recycle_rate` (v0.4 fields). |

---

## 9 — DAWN Integration Points

ForgeHarbor provisions the containers that DAWN executes inside.

| Concern | Integration |
|---|---|
| DAWN runtime image | The Docker image used by ForgeHarbor contains the DAWN runtime. The image is specified in EnvironmentSpec. |
| Artifact Store | ForgeHarbor mounts the artifact store directory into the container so DAWN links can read/write artifacts. |
| Ledger | DAWN's ledger (events.jsonl) is written inside the container. ForgeHarbor's drain path should ensure the ledger is flushed before termination. |
| Sandbox isolation | DAWN's sandbox isolation (per-link write paths) operates within the container. ForgeHarbor provides the container-level isolation; DAWN provides the link-level isolation within it. |

---

## 10 — What ForgeHarbor Must NOT Do

| Out of scope | Reason |
|---|---|
| Intent admission | ForgeHarbor provisions environments; it doesn't decide whether work is allowed. CONCORD handles admission. |
| Action discovery | ForgeAtlas handles tool discovery. ForgeHarbor doesn't know what actions exist. |
| Pipeline orchestration | ForgeWorks and DAWN handle pipeline execution inside the environment. ForgeHarbor manages the environment itself. |
| ForgeGate evaluation | Governance decisions are ForgeGate's responsibility. ForgeHarbor doesn't evaluate proposed actions. |
| Saga compensation logic | The existing environment_kernel.py handles compensation when environments go unhealthy. ForgeHarbor triggers the kernel; it doesn't reimplement compensation. |
| Session management | CONCORD manages sessions. ForgeHarbor reads session_id from callers; it doesn't create or validate sessions. |

---

*End of core specification. Long-running daemon with four components: Pool Manager, Lifecycle Engine, Heartbeat Monitor, Provider Interface. Docker-first with abstract provider for future K8s support. Pool size of 3. Wraps existing unhealthy/teardown kernel.*
