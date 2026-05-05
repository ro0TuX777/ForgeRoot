# Azul — Implementation Plan

**Status:** Draft v0.1 — 2026-03-08
**Prerequisite:** Azul Core Specification v0.1
**Target:** AI Dev (new application build)
**Deployment:** Docker container (long-running daemon)

---

## Overview

Azul is the first application built on the Forge framework ecosystem. Unlike ForgeAtlas and ForgeHarbor (which are single-purpose services), Azul is a multi-component application that orchestrates all seven frameworks into a verification workflow.

This plan builds Azul in six phases. Each phase produces a testable increment. Phase 1 is pure logic (no framework dependencies). Framework integrations are added incrementally in Phases 2–4.

### Existing assets Azul consumes

| Asset | Framework | Status |
|---|---|---|
| `execute_planner_request()` | ForgeWorks | ✅ Built — runs full pipeline, returns receipt + ReviewBundle |
| `FWResultGate.evaluate()` | Extracted from SAM | ✅ To be extracted — gate policy evaluation |
| `_build_planner_spec()` pattern | Extracted from SAM | ✅ Pattern documented — Azul builds its own version |
| ForgeScaffold blueprint analysis | ForgeScaffold | ✅ Built — System Catalog + Dataflow Map |
| ForgeHarbor `request_environment()` / `release_environment()` | ForgeHarbor | ✅ Built — warm pool assignment |
| ForgeAtlas `run()` | ForgeAtlas | ✅ Built — action discovery |
| CONCORD admission pipeline | CONCORD v0.4 | ✅ Built — trust, budgets, sessions |
| DAWN execution engine | DAWN | ✅ Built — link contracts, sandboxes, ledger |

---

## Phase 1 — Ticket Lifecycle (Pure Logic)

**Goal:** AzulTicket entity, status machine, persistent storage, XP ledger. No framework calls.

**Duration estimate:** 2–3 sessions

### Deliverables

1. **`ticket.py`**: AzulTicket dataclass with all fields from Core Spec §4.1. Status enum with all 8 statuses.

2. **`lifecycle.py`**: Status machine with `can_transition()` guard (same pattern as ForgeHarbor's lifecycle engine). Transition functions: `begin_analysis()`, `begin_provisioning()`, `begin_evaluation()`, `begin_gating()`, `complete()`, `reject()`, `warn()`, `fail()`.

3. **`ticket_store.py`**: Persistent JSON file store. Save/load tickets to `azul_data/tickets/active/` and `azul_data/tickets/completed/`. List with optional status/type filters. Move to completed on terminal status.

4. **`xp_ledger.py`**: Append-only JSONL ledger for XP awards. `award_xp(ticket)` calculates and records. `get_summary()` returns totals by domain, type, and time window.

5. **`training_pairs.py`**: Training pair emission and storage. `emit_training_pair(ticket)` writes to `azul_data/training_pairs/`. `get_pairs(domain, min_score)` queries stored pairs.

6. **Tests**: All status transitions (valid and invalid). Ticket persistence (save, load, list, filter). XP calculation and ledger append. Training pair emission on pass, suppression on reject.

### Validation criteria

```python
ticket = create_ticket(ticket_type="ci_gate", domain="ci_change_control", 
                        change_summary="Fix null check in auth module", ...)
assert ticket.status == SUBMITTED

ticket = begin_analysis(ticket)
assert ticket.status == ANALYZING

# Invalid transition
result = complete(ticket)  # can't jump from ANALYZING to COMPLETED
assert result is error

# Full happy path
ticket = begin_provisioning(ticket)
ticket = begin_evaluation(ticket)
ticket = begin_gating(ticket)
ticket = complete(ticket, xp=25)
assert ticket.status == COMPLETED
assert ticket.xp_awarded == 25

# Persistence
store.save(ticket)
loaded = store.get(ticket.ticket_id)
assert loaded.status == COMPLETED
```

### Files created

| File | Purpose |
|---|---|
| `ticket.py` | AzulTicket dataclass + status enum |
| `lifecycle.py` | Status machine with transition guards |
| `ticket_store.py` | JSON file persistence |
| `xp_ledger.py` | XP calculation + append-only ledger |
| `training_pairs.py` | Training pair emission + storage |
| `config.py` | Environment variable handling + defaults |
| `tests/test_lifecycle.py` | Status transition tests |
| `tests/test_ticket_store.py` | Persistence tests |
| `tests/test_xp_ledger.py` | XP calculation tests |
| `tests/test_training_pairs.py` | Training pair tests |

---

## Phase 2 — Gate Extraction + Verification Spec Builder

**Goal:** Extract FWResultGate from SAM. Build the planner spec constructor. Gate evaluation works standalone.

**Duration estimate:** 2–3 sessions

### Deliverables

1. **`gate.py`**: FWResultGate extracted from SAM's `fw_result_gate.py`. Includes `evaluate()`, `GateResult`, `DEFAULT_GATE_POLICY`, severity logic (ok/warn/critical). Per-ticket policy override support. No modification to the logic — direct extraction.

2. **`spec_builder.py`**: Constructs planner_spec.v0_1 dicts from AzulTickets. Follows `_build_planner_spec()` pattern from SAM. Handles all 5 ticket types:
   - `ci_gate` / `refactor` / `security_patch` → domain `ci_change_control`
   - `policy_compliance` → domain `it_ops_runbook`
   - `distillation_pair` → domain from ticket metadata

3. **`gate_policies/`**: YAML configuration files for per-domain gate policies. Default policy + domain overrides.

4. **`domain_config.py`**: Oracle paths, scoring paths, mode defaults per domain. Equivalent to SAM's `FORGEWORKS_ORACLE_PATHS` / `FORGEWORKS_SCORING_PATHS`.

5. **Tests**: Gate evaluation with all severity levels. Spec construction for each ticket type. Per-ticket policy override. Domain config resolution.

### Validation criteria

```python
# Gate evaluation
bundle = {"metrics": {"total_score": 91.5, "pass_fail": True, "deny_count": 0, ...}}
result = gate.evaluate(bundle, DEFAULT_GATE_POLICY)
assert result.passed == True
assert result.severity == "ok"

# Below min_score → critical
bundle["metrics"]["total_score"] = 65.0
result = gate.evaluate(bundle, DEFAULT_GATE_POLICY)
assert result.passed == False
assert result.severity == "critical"

# Spec construction
ticket = create_ticket(ticket_type="ci_gate", domain="ci_change_control", ...)
spec = build_verification_spec(ticket)
assert spec["schema_version"] == "0.1"
assert spec["domain"] == "ci_change_control"
assert spec["mode"] == "shadow"
```

### Files created

| File | Purpose |
|---|---|
| `gate.py` | FWResultGate extraction (evaluate + GateResult + policy) |
| `spec_builder.py` | Planner spec construction from AzulTicket |
| `domain_config.py` | Per-domain oracle/scoring/mode configuration |
| `gate_policies/default.yaml` | Default gate policy |
| `gate_policies/ci_change_control.yaml` | CI domain policy |
| `gate_policies/it_ops_runbook.yaml` | IT ops domain policy |
| `tests/test_gate.py` | Gate evaluation tests |
| `tests/test_spec_builder.py` | Spec construction tests |

---

## Phase 3 — Verification Engine (Framework Integration)

**Goal:** The core verification flow — ForgeScaffold analysis, ForgeHarbor provisioning, ForgeWorks shadow run, gate evaluation — wired end to end.

**Duration estimate:** 3–4 sessions

### Deliverables

1. **`verification_engine.py`**: The `verify(ticket)` function from Core Spec §5.1. Orchestrates all framework calls in sequence: analyze → provision → build spec → evaluate → release → gate.

2. **Framework integration modules**:
   - `integrations/forge_scaffold.py` — importlib call to ForgeScaffold for blast radius analysis
   - `integrations/forge_harbor.py` — daemon call to ForgeHarbor for environment request/release
   - `integrations/forge_works.py` — importlib call to `execute_planner_request()`
   - `integrations/forge_atlas.py` — importlib call to ForgeAtlas for action discovery

3. **Error handling at every stage**: Each framework call is wrapped in try/except. Failures at any stage transition the ticket to FAILED with the error details. ForgeHarbor environments are always released, even on failure (finally block).

4. **Skip logic**: ForgeScaffold analysis skipped for non-codebase domains. ForgeHarbor skipped when `AZUL_FORGE_HARBOR_ENABLED=false`. ForgeAtlas optional for v1.0 (called if enabled, skipped if not).

5. **Tests**: Full happy path (mock all frameworks). Each stage failure transitions to FAILED. Environment release on failure. Skip logic for non-codebase domains. ReviewBundle attached to ticket.

### Validation criteria

```python
# Happy path with mocked frameworks
ticket = create_ticket(ticket_type="ci_gate", ...)
verified = verify(ticket)
assert verified.status in (COMPLETED, WARNED, REJECTED)
assert verified.review_bundle is not None
assert verified.gate_result is not None
assert verified.verdict in ("pass", "reject")

# ForgeWorks failure → FAILED (not REJECTED)
with mock_forgeworks_error():
    verified = verify(ticket)
    assert verified.status == FAILED  # operational failure, not behavioral rejection

# Environment released on failure
with mock_forgeworks_error():
    verified = verify(ticket)
    assert forge_harbor.release_called  # environment always released
```

### Files created

| File | Purpose |
|---|---|
| `verification_engine.py` | Core verify() orchestration |
| `integrations/forge_scaffold.py` | ForgeScaffold blast radius integration |
| `integrations/forge_harbor.py` | ForgeHarbor environment management |
| `integrations/forge_works.py` | ForgeWorks pipeline integration |
| `integrations/forge_atlas.py` | ForgeAtlas action discovery integration |
| `tests/test_verification_engine.py` | End-to-end verification tests (mocked frameworks) |
| `tests/mocks/` | Mock implementations for each framework |

---

## Phase 4 — Entry Adapters

**Goal:** Five entry adapters that normalize triggers into AzulTickets.

**Duration estimate:** 2–3 sessions

### Deliverables

1. **`adapters/ci_webhook.py`**: Parses CI webhook payloads (GitHub/GitLab format). Extracts diff, commit SHA, changed files. Creates `ci_gate` ticket.

2. **`adapters/cli.py`**: Command-line interface. `azul verify --diff path --domain domain`. Creates ticket and optionally waits for verdict.

3. **`adapters/api.py`**: JSON payload via importlib (Pattern 1). Generic entry point for programmatic callers.

4. **`adapters/scanner.py`**: Accepts drift scan or security advisory events. Creates `refactor` or `security_patch` tickets.

5. **`adapters/distillation.py`**: Accepts training pair candidates. Creates `distillation_pair` tickets.

6. **Tests**: Each adapter produces a valid AzulTicket from its expected input format. Invalid inputs return structured errors. Adapter-specific fields are correctly mapped.

### Files created

| File | Purpose |
|---|---|
| `adapters/ci_webhook.py` | CI webhook → AzulTicket |
| `adapters/cli.py` | CLI → AzulTicket |
| `adapters/api.py` | JSON API → AzulTicket |
| `adapters/scanner.py` | Drift/security event → AzulTicket |
| `adapters/distillation.py` | Training pair → AzulTicket |
| `tests/test_adapters.py` | Adapter tests for all 5 types |

---

## Phase 5 — Daemon + Queue Processing

**Goal:** Azul runs as a long-running daemon with concurrent ticket processing.

**Duration estimate:** 2–3 sessions

### Deliverables

1. **`daemon.py`**: Main entry point. Startup sequence: load config, initialize integrations, start queue processor, expose caller-facing functions. Graceful shutdown.

2. **`queue.py`**: Ticket processing queue. Dequeues SUBMITTED tickets, runs `verify()` for each. Configurable worker count (`AZUL_QUEUE_WORKERS`). Thread-safe.

3. **Caller-facing functions**: `submit()`, `get_ticket()`, `get_verdict()`, `list_tickets()`, `get_xp_summary()`, `get_training_pairs()`, `health()`. All return `_ok/_error` envelopes.

4. **Health endpoint**: Reports queue depth, framework connectivity (ForgeHarbor reachable, ForgeWorks importable, etc.), tickets processed, uptime.

5. **Tests**: Queue processes tickets in order. Concurrent workers don't conflict. Graceful shutdown completes in-progress tickets. Health endpoint reports accurate state.

### Files created

| File | Purpose |
|---|---|
| `daemon.py` | Main daemon entry point |
| `queue.py` | Ticket processing queue with workers |
| `tests/test_daemon.py` | Daemon lifecycle tests |
| `tests/test_queue.py` | Queue processing tests |

---

## Phase 6 — Docker Packaging + Integration Tests

**Goal:** Azul runs in a Docker container and orchestrates real framework calls.

**Duration estimate:** 1–2 sessions

### Deliverables

1. **Dockerfile**: Azul container with all dependencies. Mounts `azul_data/` for persistence. Configuration via environment variables.

2. **`requirements.txt`**: Pinned dependencies.

3. **Integration tests**: Full lifecycle against real (or realistic mock) framework calls. CI gate ticket: submit → analyze → provision → evaluate → gate → verdict.

4. **CONCORD telemetry**: Azul emits verification metrics: tickets_processed, average_verification_time_ms, pass_rate, reject_rate, xp_awarded_total.

### Files created

| File | Purpose |
|---|---|
| `Dockerfile` | Container definition |
| `requirements.txt` | Pinned dependencies |
| `tests/test_integration.py` | End-to-end integration tests |

---

## Phase Summary

| Phase | Builds | Framework deps | Test count target |
|---|---|---|---|
| Phase 1: Ticket Lifecycle | Entity, status machine, persistence, XP, training pairs | None | 20–25 |
| Phase 2: Gate + Spec Builder | FWResultGate extraction, planner spec construction | None (extracted code) | 15–20 |
| Phase 3: Verification Engine | Core verify() flow with all framework integrations | All (mocked in tests) | 20–25 |
| Phase 4: Entry Adapters | 5 adapters for all use cases | None | 10–15 |
| Phase 5: Daemon + Queue | Long-running daemon, concurrent processing | All (mocked in tests) | 10–15 |
| Phase 6: Docker Packaging | Dockerfile, integration tests, telemetry | All (real in integration) | 5–10 |

**Total estimated test count: 80–110**
**Total estimated duration: 12–18 sessions**

---

## Files the Dev Must Read Before Starting

| # | File | Why |
|---|---|---|
| 1 | ForgeHarbor `lifecycle_engine.py` | The status machine pattern Azul's lifecycle follows |
| 2 | SAM `fw_result_gate.py` | The gate logic being extracted into Azul |
| 3 | SAM `forge_planner_agent.py` → `_build_planner_spec()` | The spec construction pattern Azul follows |
| 4 | ForgeWorks `service_wrapper.py` | The `_ok/_error` envelope convention + `execute_planner_request()` interface |
| 5 | ForgeHarbor `daemon.py` | The daemon pattern Azul follows (startup, background loops, shutdown) |
| 6 | ForgeAtlas `run.py` | The importlib service pattern for framework integration |
| 7 | Azul Core Specification | The full architectural spec this plan implements |

---

*End of implementation plan. Six phases. Phase 1 is pure logic. Phases 2–4 add framework integration. Phase 5 makes it a daemon. Phase 6 packages it. 80–110 tests across 12–18 sessions.*
