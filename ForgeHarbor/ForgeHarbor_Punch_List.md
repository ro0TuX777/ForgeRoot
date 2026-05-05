# ForgeHarbor — Punch List

**Status:** Draft v0.1 — 2026-03-07
**Companion to:** Core Specification v0.1, Implementation Plan v0.1
**Convention:** P0 = blocks all downstream work. P1 = blocks release. P2 = should ship. P3 = nice to have.

---

## P0 — Blocks Everything

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P0-1 | `can_transition(from_status, to_status)` transition guard | 1 | Returns True for all valid transitions in the state machine. Returns False for all invalid transitions. Covers all 9 valid transitions and rejects direct jumps (e.g., COLD→ASSIGNED). |
| P0-2 | Forward lifecycle functions: `provision()`, `on_warm_complete()`, `assign()`, `begin_drain()`, `on_drain_complete()`, `recycle()` | 1 | Each function checks `can_transition()` before mutating. Returns structured error on invalid transition. Assign sets `assigned_session_id` and `assigned_at`. Drain checks `get_blocking_intents()` — blocks if intents active. |
| P0-3 | `on_provision_failure()` — WARMING → TERMINATED | 1 | Provisioning failure or timeout transitions to TERMINATED. No compensation needed (nothing was assigned). |
| P0-4 | Abstract `EnvironmentProvider` interface | 2 | Four methods defined: `provision()`, `check_health()`, `terminate()`, `get_connection_info()`. All return structured result types, not raw exceptions. |
| P0-5 | `DockerProvider` implementation | 2 | Provisions a container from an image. Health check detects running/stopped. Terminate stops and removes container. All Docker SDK exceptions caught and returned as structured errors. |
| P0-6 | `PoolManager` with `reconcile()`, `request_environment()`, `release_environment()` | 3 | Pool starts at target_size after first reconcile. Assignment returns READY environment. Release triggers ASSIGNED→DRAINING. Reconciliation provisions replacements for terminated environments. |
| P0-7 | Thread-safe assignment lock | 3 | Two concurrent `request_environment()` calls never assigned the same environment. Test with threading. |

---

## P1 — Blocks Release

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P1-1 | `HeartbeatMonitor` with `check_once()` and background loop | 4 | Detects failed container via provider `check_health()`. Calls existing `mark_environment_unhealthy()`. Configurable interval via `FORGE_HARBOR_HEARTBEAT_INTERVAL_MS`. |
| P1-2 | Integration with existing `environment_kernel.py` unhealthy path | 4 | Heartbeat failure → `mark_environment_unhealthy()` → `handle_unhealthy_environment()` → TERMINATED or stays UNHEALTHY. ForgeHarbor does not reimplement this logic. |
| P1-3 | `daemon.py` main entry point with startup sequence | 4 | Initializes provider, pool, heartbeat. Logs startup summary (pool status, provider type, config). Starts background loops. |
| P1-4 | Graceful shutdown (SIGTERM/SIGINT) | 4 | Signal triggers: drain all ASSIGNED environments, wait for blocking intents (with timeout), terminate all containers, clean exit. |
| P1-5 | Pool policy configuration via environment variables | 3/5 | All 8 variables from Core Spec §7.3 are read and applied. Defaults are correct when not set. |
| P1-6 | `health()` function | 4 | Returns: status (healthy/degraded/unhealthy), pool counts by status, heartbeat_running, provider_reachable, uptime_seconds. |
| P1-7 | `get_pool_status()` with CONCORD telemetry fields | 3 | Returns: environment_pool_utilization, average_provision_time_ms, environment_recycle_rate. Matches CONCORD v0.4 CoordinationTelemetry schema. |
| P1-8 | Dockerfile with Docker socket mount | 5 | Container builds. Mounts `/var/run/docker.sock`. Can provision/manage sibling containers. Not Docker-in-Docker. |
| P1-9 | All error codes from Core Spec §7.3 implemented | 2/3 | `ENVIRONMENT_UNAVAILABLE`, `ENVIRONMENT_NOT_FOUND`, `INVALID_TRANSITION`, `PROVISION_FAILED`, `PROVISION_TIMEOUT`, `PROVIDER_UNREACHABLE`, `POOL_AT_CAPACITY`, `ASSIGNMENT_CONFLICT` — each returns correct structured error envelope. |
| P1-10 | `_ok/_error` envelope on all caller-facing functions | 4 | `request_environment`, `release_environment`, `get_environment_status`, `get_pool_status`, `health` — all return envelope dicts. None raise exceptions to caller. |

---

## P2 — Should Ship

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P2-1 | `EnvironmentSpec` dataclass with image, preload_manifest, resource_limits, mounts | 2 | Configurable per-environment. DockerProvider translates to `containers.run()` kwargs. |
| P2-2 | `MockProvider` for unit tests | 3 | In-memory provider that simulates provision/health/terminate without Docker. Pool Manager and Heartbeat tests use this. |
| P2-3 | Provision timeout enforcement | 3 | WARMING environments past `provision_timeout_ms` are transitioned to TERMINATED during reconciliation. Tested. |
| P2-4 | `max_environments` ceiling enforcement | 3 | Pool never provisions beyond `max_environments`. Request when at capacity returns `POOL_AT_CAPACITY`. |
| P2-5 | `min_ready` enforcement | 3 | Reconciliation always provisions up to `min_ready` READY environments, even if `target_pool_size` is satisfied by ASSIGNED environments. |
| P2-6 | Estimated wait time in ENVIRONMENT_UNAVAILABLE error | 3 | Error includes `estimated_wait_ms` based on average provision time or current WARMING count. |
| P2-7 | Integration test: full lifecycle against real Docker | 5 | Daemon starts → provisions 3 containers → assigns one → releases it → pool replenishes → shutdown terminates all. All against real Docker. |
| P2-8 | `requirements.txt` with pinned versions | 5 | All dependencies version-pinned. Clean install in Docker. |

---

## P3 — Nice to Have (Not Required for v1.0)

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P3-1 | Preload manifest execution during WARMING | 2+ | Provider runs preload steps (repo clone, dependency install, service start) inside the container after creation. WARMING→READY only after preload completes. |
| P3-2 | K8sProvider implementation | 2+ | Second provider using `kubernetes` Python client. Same four methods. Pool Manager works unchanged. |
| P3-3 | Environment recycling optimization | 3+ | Instead of TERMINATED → new COLD, reset an existing container (stop processes, clear sandbox, keep base image warm). Faster than full re-provision. |
| P3-4 | BudgetProfile `max_parallel_environments` check | 3+ | Before assignment, check if the session's AgentClass has exceeded its environment ceiling. Deny with `BUDGET_EXCEEDED` if so. |
| P3-5 | Pool scaling events emitted to DAWN ledger | 4+ | Provision, assign, release, drain, terminate events written to a ForgeHarbor-specific ledger for audit. |
| P3-6 | Container resource utilization metrics | 4+ | Health check includes CPU/memory usage from `docker stats`. Surfaced in pool status for capacity planning. |
| P3-7 | Configurable DAWN runtime image per domain | 5+ | Different domains (ci_change_control, it_ops_runbook) may need different base images. EnvironmentSpec supports domain→image mapping. |

---

## Dependency Map

```
P0-1 (transition guard) ──→ P0-2 (lifecycle functions) ──→ P0-3 (provision failure)
                                      │
                              ┌───────┴───────┐
                              ▼               ▼
                    P0-4 (provider interface)  P0-6 (pool manager)
                              │               │
                              ▼               ▼
                    P0-5 (DockerProvider)     P0-7 (assignment lock)
                              │               │
                              └───────┬───────┘
                                      ▼
                              P1-1 (heartbeat monitor)
                                      │
                                      ▼
                              P1-2 (kernel integration)
                                      │
                                      ▼
                              P1-3 (daemon.py) ──→ P1-4 (graceful shutdown)
                                      │
                                      ▼
                              P1-8 (Dockerfile) ──→ P2-7 (integration test)
```

---

## Test Coverage Summary

| Phase | Test file | Target count | Docker required |
|---|---|---|---|
| 1 | `test_lifecycle_engine.py` | 15–20 | No |
| 2 | `test_docker_provider.py` | 10–15 | Yes (integration) |
| 3 | `test_pool_manager.py` | 15–20 | No (MockProvider) |
| 4 | `test_heartbeat_monitor.py` + `test_daemon.py` | 10–15 | Partial (MockProvider + real Docker) |
| 5 | `test_integration.py` | 5–10 | Yes |
| **Total** | | **55–80** | |

---

## Definition of Done

ForgeHarbor is complete when:

1. All P0 and P1 items pass their acceptance criteria
2. All P2 items pass or have documented deferral reasons
3. Test count is ≥ 55 with zero failures
4. Docker daemon starts, provisions target_pool_size containers, and reports healthy
5. Assignment returns a running environment within assignment_timeout_ms
6. Heartbeat detects container failure and triggers existing kernel unhealthy path
7. Graceful shutdown terminates all managed containers cleanly
8. Pool replenishes after assignment + release cycle
9. No regression in DAWN test suite
10. CONCORD telemetry fields present in pool status output

---

*End of punch list. 7 P0s, 10 P1s, 8 P2s, 7 P3s. Critical path: P0-1 → P0-2 → P0-6 → P1-1 → P1-3 → P1-8.*
