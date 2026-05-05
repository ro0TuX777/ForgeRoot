# ForgeHarbor — Implementation Plan

**Status:** Draft v0.1 — 2026-03-07
**Prerequisite:** ForgeHarbor Core Specification v0.1
**Target:** New AI Dev
**Deployment:** Long-running Docker daemon managing a pool of Docker containers

---

## Overview

This plan builds ForgeHarbor in five phases. Each phase produces a testable increment. Phase 1 is pure logic (no Docker dependency) and can be tested entirely in-memory. Phases 2–4 add Docker integration, background loops, and the caller-facing service interface. Phase 5 packages everything.

### Existing code assets

| Asset | Location | Status |
|---|---|---|
| `ExecutionEnvironment` entity | `dawn/concord/types/entities.py` | ✅ Built (v0.4) |
| `EnvironmentStatus` enum | `dawn/concord/types/enums.py` | ✅ Built (includes COLD, WARMING, READY, ASSIGNED, DRAINING, UNHEALTHY, TERMINATED) |
| `EnvironmentClass`, `IsolationLevel`, `ProvisioningStatus` enums | `dawn/concord/types/enums.py` | ✅ Built |
| `mark_environment_unhealthy()` | `dawn/concord/environment_kernel.py` | ✅ Built — sets UNHEALTHY |
| `get_blocking_intents()` | `dawn/concord/environment_kernel.py` | ✅ Built — filters ADMITTED/EXECUTING |
| `handle_unhealthy_environment()` | `dawn/concord/environment_kernel.py` | ✅ Built — full unhealthy→teardown path |
| Forward lifecycle (COLD→WARMING→READY→ASSIGNED→DRAINING) | — | ❌ Not built |
| Pool management | — | ❌ Not built |
| Heartbeat monitoring | — | ❌ Not built |
| Docker provisioning | — | ❌ Not built |
| Daemon / background loops | — | ❌ Not built |

---

## Phase 1 — Lifecycle Engine (Pure Logic, No Docker)

**Goal:** The full ExecutionEnvironment state machine is implemented as testable pure Python. No Docker, no I/O, no background threads.

**Duration estimate:** 1–2 sessions

### Deliverables

1. **`lifecycle_engine.py`**: Drives the state machine for a single ExecutionEnvironment.

   Functions:
   - `can_transition(from_status, to_status) → bool` — enforces the transition table topology
   - `provision(env) → env` — COLD → WARMING
   - `on_warm_complete(env) → env` — WARMING → READY
   - `on_provision_failure(env) → env` — WARMING → TERMINATED
   - `assign(env, session_id) → env` — READY → ASSIGNED
   - `begin_drain(env) → env` — ASSIGNED → DRAINING (or READY → DRAINING for scale-down)
   - `on_drain_complete(env) → env` — DRAINING → TERMINATED
   - `recycle(env) → env` — TERMINATED → new COLD environment (resets fields, new environment_id)

2. **Transition guard enforcement**: Every function checks `can_transition()` before mutating status. Invalid transitions return a structured error (not an exception).

3. **Integration with existing kernel**: `begin_drain()` checks `get_blocking_intents()`. If blocking intents exist, environment stays ASSIGNED (cannot drain yet). The unhealthy path remains in the existing kernel — lifecycle engine does NOT reimplement it.

4. **Tests**: Every valid transition. Every invalid transition (rejected by guard). Assign sets session_id and assigned_at. Drain blocks when intents are active. Recycle produces a new environment_id.

### Validation criteria

```python
env = create_cold_environment(spec)
assert env.status == COLD

env = provision(env)
assert env.status == WARMING

env = on_warm_complete(env)
assert env.status == READY

env = assign(env, "sess-1")
assert env.status == ASSIGNED
assert env.assigned_session_id == "sess-1"

env = begin_drain(env)  # no blocking intents
assert env.status == DRAINING

env = on_drain_complete(env)
assert env.status == TERMINATED

# Invalid transition
result = assign(env, "sess-2")  # TERMINATED → ASSIGNED is invalid
assert result is error with INVALID_TRANSITION
```

### Files created

| File | Purpose |
|---|---|
| `lifecycle_engine.py` | State machine logic for full environment lifecycle |
| `tests/test_lifecycle_engine.py` | Lifecycle transition tests |

---

## Phase 2 — Provider Interface + DockerProvider

**Goal:** ForgeHarbor can provision, health-check, and terminate real Docker containers.

**Duration estimate:** 2–3 sessions

### Deliverables

1. **`provider.py`**: Abstract `EnvironmentProvider` base class with four methods: `provision()`, `check_health()`, `terminate()`, `get_connection_info()`.

2. **`docker_provider.py`**: Concrete implementation using `docker` Python SDK.
   - `provision()`: `client.containers.run(image, detach=True, ...)` with resource limits, mounts, env vars from EnvironmentSpec
   - `check_health()`: `container.reload(); container.status` → running/stopped/error
   - `terminate()`: `container.stop(timeout=10); container.remove()`
   - `get_connection_info()`: Container ID, IP address, mount paths

3. **`environment_spec.py`**: EnvironmentSpec dataclass defining what the provider needs (image, preload_manifest, resource_limits, network_mode, environment_vars, mounts).

4. **Provider error handling**: All Docker SDK exceptions caught and translated to structured errors. Provider never raises to the caller.

5. **Tests**: Provision creates a running container. Health check detects running vs stopped. Terminate removes container. Invalid image returns structured error. Tests require Docker daemon (mark as integration tests, skippable in CI without Docker).

### Validation criteria

```python
provider = DockerProvider()
spec = EnvironmentSpec(image="dawn-runtime:latest", ...)

result = provider.provision("env-1", spec)
assert result.success
assert result.container_id is not None

health = provider.check_health("env-1")
assert health.status == "running"

provider.terminate("env-1")
health = provider.check_health("env-1")
assert health.status == "not_found"
```

### Files created

| File | Purpose |
|---|---|
| `provider.py` | Abstract EnvironmentProvider interface |
| `docker_provider.py` | Docker SDK implementation |
| `environment_spec.py` | EnvironmentSpec dataclass |
| `tests/test_docker_provider.py` | Docker integration tests |

### Dependencies added

| Package | Purpose |
|---|---|
| `docker` | Docker SDK for Python (container lifecycle management) |

---

## Phase 3 — Pool Manager

**Goal:** ForgeHarbor maintains a warm pool of target size 3 with automatic provisioning, assignment, and recycling.

**Duration estimate:** 2–3 sessions

### Deliverables

1. **`pool_manager.py`**: Manages the collection of environments. Core operations:
   - `reconcile()` — one pass of the reconciliation loop (provision if below target, drain excess, check timeouts)
   - `request_environment(session_id) → environment_id or error` — find and assign a READY environment
   - `release_environment(environment_id) → ok or error` — trigger ASSIGNED → DRAINING
   - `get_pool_status() → dict` — counts by status, utilization rate

2. **Thread-safe assignment**: A lock ensures two concurrent `request_environment()` calls cannot be assigned the same environment.

3. **Pool policy configuration**: `target_pool_size`, `min_ready`, `max_environments`, `provision_timeout_ms`, `assignment_timeout_ms` — all configurable via environment variables or constructor parameters.

4. **Reconciliation logic**:
   - READY count < min_ready AND total < max_environments → provision new
   - WARMING environments past provision_timeout → terminate
   - ASSIGNED environments whose sessions have ended → begin drain
   - DRAINING environments with no blocking intents → terminate
   - TERMINATED environments removed from pool tracking (or recycled if below target)

5. **Tests**: Pool starts with target_size environments provisioned. Assignment returns a READY environment and transitions it to ASSIGNED. Double-assignment prevented by lock. Release triggers draining. Reconciliation provisions replacements for terminated environments. Pool respects max_environments ceiling.

### Validation criteria

```python
pool = PoolManager(target_pool_size=3, provider=MockProvider())
pool.reconcile()  # initial provisioning
assert pool.count_by_status(READY) == 3

# Assignment
result = pool.request_environment("sess-1")
assert result["status"] == "ok"
assert pool.count_by_status(READY) == 2
assert pool.count_by_status(ASSIGNED) == 1

# Release
pool.release_environment(result["payload"]["environment_id"])
# After reconciliation, pool replenishes
pool.reconcile()
assert pool.count_by_status(READY) == 3  # replenished
```

### Files created

| File | Purpose |
|---|---|
| `pool_manager.py` | Pool management with reconciliation, assignment, release |
| `tests/test_pool_manager.py` | Pool behavior tests (uses MockProvider) |
| `mock_provider.py` (in tests/) | In-memory provider for unit testing without Docker |

---

## Phase 4 — Heartbeat Monitor + Daemon

**Goal:** ForgeHarbor runs as a long-lived process with background pool reconciliation and heartbeat monitoring.

**Duration estimate:** 2–3 sessions

### Deliverables

1. **`heartbeat_monitor.py`**: Background loop that checks health of all ASSIGNED and WARMING environments via the provider's `check_health()`. On failure detection, calls the existing `mark_environment_unhealthy()` and `handle_unhealthy_environment()` from `environment_kernel.py`.

2. **`daemon.py`**: Main entry point that:
   - Initializes DockerProvider
   - Initializes PoolManager with configured pool policy
   - Starts heartbeat monitor background loop
   - Starts pool reconciliation background loop
   - Exposes caller-facing functions: `request_environment()`, `release_environment()`, `get_environment_status()`, `get_pool_status()`, `health()`

3. **Graceful shutdown**: Signal handler (SIGTERM/SIGINT) that drains all assigned environments, waits for blocking intents to resolve (with timeout), terminates all containers, and exits cleanly.

4. **Startup sequence**:
   ```
   1. Load configuration from environment variables
   2. Initialize DockerProvider (verify Docker daemon reachable)
   3. Initialize PoolManager with target_pool_size=3
   4. Run initial reconciliation (provision 3 environments)
   5. Start heartbeat monitor loop
   6. Start reconciliation loop
   7. Log startup summary: pool status, provider type, configuration
   8. Daemon ready
   ```

5. **Tests**: Heartbeat detects failed container and triggers unhealthy path. Reconciliation loop provisions replacements. Graceful shutdown drains and terminates. Startup logs expected summary.

### Validation criteria

```python
# Heartbeat detection
pool = PoolManager(target_pool_size=1, provider=mock_provider)
pool.reconcile()
env_id = pool.request_environment("sess-1")["payload"]["environment_id"]

# Simulate container death
mock_provider.kill(env_id)

# Heartbeat monitor detects
monitor = HeartbeatMonitor(pool, mock_provider, interval_ms=100)
monitor.check_once()

# Environment should be UNHEALTHY or TERMINATED
status = pool.get_environment_status(env_id)
assert status in (UNHEALTHY, TERMINATED)
```

### Files created

| File | Purpose |
|---|---|
| `heartbeat_monitor.py` | Background health check loop |
| `daemon.py` | Main daemon entry point with background loops |
| `tests/test_heartbeat_monitor.py` | Heartbeat detection tests |
| `tests/test_daemon.py` | Daemon lifecycle tests |

---

## Phase 5 — Docker Packaging & Integration

**Goal:** ForgeHarbor runs as a Docker container that manages other Docker containers (Docker-in-Docker or socket mount pattern).

**Duration estimate:** 1–2 sessions

### Deliverables

1. **Dockerfile**: ForgeHarbor container that mounts the host's Docker socket (`/var/run/docker.sock`) so it can manage sibling containers. Not Docker-in-Docker — ForgeHarbor talks to the same Docker daemon as the host.

2. **`requirements.txt`**: Pinned dependencies (docker, pyyaml, numpy for any CONCORD type dependencies).

3. **Configuration via environment variables**:

   | Variable | Default | Purpose |
   |---|---|---|
   | `FORGE_HARBOR_POOL_SIZE` | `3` | Target warm pool size |
   | `FORGE_HARBOR_MIN_READY` | `1` | Minimum READY environments |
   | `FORGE_HARBOR_MAX_ENVIRONMENTS` | `5` | Hard ceiling |
   | `FORGE_HARBOR_PROVISION_TIMEOUT_MS` | `60000` | WARMING → READY deadline |
   | `FORGE_HARBOR_HEARTBEAT_INTERVAL_MS` | `15000` | Health check frequency |
   | `FORGE_HARBOR_RECONCILE_INTERVAL_MS` | `10000` | Pool reconciliation frequency |
   | `FORGE_HARBOR_DAWN_IMAGE` | `dawn-runtime:latest` | Docker image for environments |
   | `LOG_LEVEL` | `INFO` | Daemon log level |

4. **Integration test**: ForgeHarbor daemon starts, provisions 3 environments, assigns one to a session, releases it, and the pool replenishes — all against real Docker.

5. **CONCORD telemetry verification**: `get_pool_status()` returns fields matching CONCORD v0.4 CoordinationTelemetry extensions: `environment_pool_utilization`, `average_provision_time_ms`, `environment_recycle_rate`.

### Files created

| File | Purpose |
|---|---|
| `Dockerfile` | ForgeHarbor container definition |
| `requirements.txt` | Pinned dependencies |
| `tests/test_integration.py` | End-to-end Docker integration tests |

---

## Phase Summary

| Phase | Builds | Docker required | Test count target |
|---|---|---|---|
| Phase 1: Lifecycle Engine | State machine (pure logic) | No | 15–20 |
| Phase 2: Provider Interface | DockerProvider + abstract interface | Yes (integration tests) | 10–15 |
| Phase 3: Pool Manager | Pool reconciliation, assignment, release | No (MockProvider) | 15–20 |
| Phase 4: Heartbeat + Daemon | Background loops, graceful shutdown | Yes (integration tests) | 10–15 |
| Phase 5: Docker Packaging | Dockerfile, config, integration | Yes | 5–10 |

**Total estimated test count: 55–80**
**Total estimated duration: 8–12 sessions**

---

## Files the Dev Must Read Before Starting

| # | File | Why |
|---|---|---|
| 1 | `dawn/concord/environment_kernel.py` | The existing unhealthy/teardown path. ForgeHarbor calls these functions, doesn't reimplement them. |
| 2 | `dawn/concord/types/entities.py` (ExecutionEnvironment) | The entity you're managing the lifecycle of. |
| 3 | `dawn/concord/types/enums.py` (EnvironmentStatus, EnvironmentClass, IsolationLevel, ProvisioningStatus) | The status values the state machine transitions between. |
| 4 | `forgeworks/sam/service_wrapper.py` | The `_ok/_error` envelope convention your service must match. |
| 5 | ForgeHarbor Core Specification | The full architectural spec this plan implements. |
| 6 | CONCORD v0.4 Gap Analysis §Gap 1 (ExecutionEnvironment) | The original entity proposal with normative rules. |

---

*End of implementation plan. Five phases. Phase 1 is pure logic (no Docker). Phases 2–5 add Docker, background loops, and packaging. The kernel's unhealthy path is reused, not rebuilt.*
