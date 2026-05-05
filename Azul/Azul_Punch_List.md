# Azul — Punch List

**Status:** Draft v0.1 — 2026-03-08
**Companion to:** Core Specification v0.1, Implementation Plan v0.1
**Convention:** P0 = blocks all downstream work. P1 = blocks release. P2 = should ship. P3 = nice to have.

---

## P0 — Blocks Everything

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P0-1 | AzulTicket dataclass with all fields from Core Spec §4.1 | 1 | All fields present. Status enum with 8 values. ticket_type enum with 5 values. |
| P0-2 | Status machine with `can_transition()` guard | 1 | All valid transitions from §4.3 pass. All invalid transitions rejected with structured error. Same pattern as ForgeHarbor lifecycle_engine. |
| P0-3 | Ticket store — save, load, list, filter | 1 | Tickets persist as JSON files. Active tickets in `active/`, terminal tickets moved to `completed/`. List with status and type filters. |
| P0-4 | Extract FWResultGate from SAM into `gate.py` | 2 | `evaluate()` returns GateResult with severity (ok/warn/critical) and passed boolean. DEFAULT_GATE_POLICY matches SAM defaults. Per-ticket policy override works. |
| P0-5 | Spec builder — `build_verification_spec(ticket)` | 2 | Produces valid planner_spec.v0_1 dict for all 5 ticket types. Domain resolution correct. Oracle/scoring paths resolved from domain config. |
| P0-6 | Verification engine — `verify(ticket)` | 3 | Orchestrates: analyze → provision → build spec → evaluate → release → gate. Updates ticket status at each stage. Attaches ReviewBundle and gate result to ticket. |
| P0-7 | ForgeWorks integration — calls `execute_planner_request()` | 3 | Spec passed, receipt returned, ReviewBundle extracted. Error handling wraps pipeline failures as FAILED (not REJECTED). |

---

## P1 — Blocks Release

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P1-1 | XP ledger — calculate, award, persist | 1 | XP calculated per Core Spec §6.1 formula. Appended to JSONL ledger. Summary by domain/type/time. XP = 0 for rejected tickets. |
| P1-2 | Training pair emission | 1 | Verified distillation tickets emit training pairs. Rejected tickets do not. Pair includes verification_score and bundle_id provenance. |
| P1-3 | Domain configuration — oracle paths, scoring paths, mode defaults | 2 | Per-domain YAML config. Resolves correct paths for ci_change_control and it_ops_runbook. Fallback to defaults for unknown domains. |
| P1-4 | Gate policy YAML files — default + per-domain | 2 | default.yaml matches DEFAULT_GATE_POLICY. Domain overrides loaded and applied when present. |
| P1-5 | ForgeHarbor integration — request/release environment | 3 | Environment requested at PROVISIONING stage. Released on completion AND on failure (finally block). ENVIRONMENT_UNAVAILABLE handled gracefully (retry or FAILED). |
| P1-6 | ForgeScaffold integration — blast radius analysis | 3 | Called for codebase domains. Skipped for non-codebase domains. blast_radius populated on ticket. Failure → FAILED (not blocking for non-codebase). |
| P1-7 | Error handling — every framework call wrapped | 3 | Any framework failure transitions to FAILED with error details. Environment always released. Ticket always persisted on failure. |
| P1-8 | CI webhook adapter | 4 | Parses GitHub/GitLab webhook payload. Creates ci_gate ticket. Extracts diff, SHA, changed files. |
| P1-9 | CLI adapter | 4 | `azul verify --diff path --domain domain` creates ticket. Optional `--wait` blocks until verdict. |
| P1-10 | API adapter (importlib Pattern 1) | 4 | `submit()` accepts JSON payload, creates ticket, returns ticket_id. |
| P1-11 | Daemon with queue processing | 5 | Startup: load config, init integrations, start workers. Process SUBMITTED tickets. Graceful shutdown completes in-progress tickets. |
| P1-12 | Caller-facing functions — submit, get_ticket, get_verdict, list_tickets, health | 5 | All return _ok/_error envelopes. Health reports queue depth, framework connectivity, uptime. |
| P1-13 | Dockerfile | 6 | Container builds. azul_data/ mounted for persistence. Config via env vars. |

---

## P2 — Should Ship

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P2-1 | Scanner/event adapter | 4 | Drift scan and security advisory events create refactor/security_patch tickets. |
| P2-2 | Distillation adapter | 4 | Training pair candidates create distillation_pair tickets. |
| P2-3 | ForgeAtlas integration — action discovery | 3 | Called during EVALUATING if enabled. Discovered actions inform spec construction. Optional for v1.0 (skipped if ForgeAtlas unavailable). |
| P2-4 | Concurrent queue workers | 5 | AZUL_QUEUE_WORKERS configurable. Multiple tickets verified in parallel. Thread-safe ticket store. |
| P2-5 | `get_xp_summary()` — XP totals by domain, type, time window | 5 | Returns aggregated XP data. Filterable by domain and ticket_type. |
| P2-6 | `get_training_pairs()` — query verified pairs | 5 | Returns pairs filtered by domain and min_score. Ordered by verification_score descending. |
| P2-7 | Integration test — full CI gate lifecycle | 6 | Submit CI diff → analyze → provision → evaluate → gate → verdict. Against real (or realistic) framework calls. |
| P2-8 | CONCORD telemetry fields | 6 | tickets_processed, average_verification_time_ms, pass_rate, reject_rate, xp_awarded_total. |
| P2-9 | `requirements.txt` with pinned versions | 6 | All dependencies pinned. Clean install in Docker. |

---

## P3 — Nice to Have (Not Required for v1.0)

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P3-1 | Verdict notification (webhook callback to CI) | 4+ | On verdict, POST result to a configured callback URL so CI can update PR status. |
| P3-2 | Retry logic for transient framework failures | 3+ | PROVISIONING and EVALUATING failures retried N times before FAILED. Configurable retry count. |
| P3-3 | Ticket priority queue | 5+ | Critical tickets processed before normal. Priority ordering in queue. |
| P3-4 | XP decay / time-weighted scoring | 1+ | Recent XP weighted more heavily in summaries. Encourages continuous verification. |
| P3-5 | Per-use-case dashboard data endpoint | 5+ | Returns aggregated stats per use case: CI gate pass rate, refactor success rate, distillation pair yield, etc. |
| P3-6 | REPLAN support in verification engine | 3+ | If ForgeWorks returns REPLAN, Azul constructs adjusted spec and retries (up to loop_policy limits). Currently single-shot. |
| P3-7 | Blast radius visualization data | 3+ | ForgeScaffold analysis results formatted for visual rendering (affected modules, dependency paths). |

---

## Dependency Map

```
P0-1 (ticket entity) ──→ P0-2 (status machine) ──→ P0-3 (ticket store)
         │                                                    │
         ▼                                                    ▼
P1-1 (XP ledger) ──→ P1-2 (training pairs)          P0-4 (gate extraction)
                                                              │
                                                              ▼
                                                     P0-5 (spec builder)
                                                              │
                                                     P1-3 (domain config) + P1-4 (gate policies)
                                                              │
                                              ┌───────────────┴───────────────┐
                                              ▼                               ▼
                                     P0-6 (verify engine)            P0-7 (ForgeWorks integration)
                                              │
                              ┌───────────────┼───────────────┐
                              ▼               ▼               ▼
                     P1-5 (ForgeHarbor)  P1-6 (ForgeScaffold)  P1-7 (error handling)
                                              │
                                              ▼
                              ┌───────────────┼───────────────┐
                              ▼               ▼               ▼
                     P1-8 (CI webhook)  P1-9 (CLI)     P1-10 (API adapter)
                                              │
                                              ▼
                                     P1-11 (daemon) ──→ P1-12 (caller functions)
                                              │
                                              ▼
                                     P1-13 (Dockerfile) ──→ P2-7 (integration test)
```

---

## Test Coverage Summary

| Phase | Test files | Target count |
|---|---|---|
| 1 | test_lifecycle, test_ticket_store, test_xp_ledger, test_training_pairs | 20–25 |
| 2 | test_gate, test_spec_builder | 15–20 |
| 3 | test_verification_engine | 20–25 |
| 4 | test_adapters | 10–15 |
| 5 | test_daemon, test_queue | 10–15 |
| 6 | test_integration | 5–10 |
| **Total** | | **80–110** |

---

## Definition of Done

Azul is complete when:

1. All P0 and P1 items pass their acceptance criteria
2. All P2 items pass or have documented deferral reasons
3. Test count ≥ 80 with zero failures
4. Docker container builds and starts successfully
5. `submit()` accepts a CI diff and returns a ticket_id
6. `get_verdict()` returns pass/reject/warn with ReviewBundle reference
7. XP is awarded on pass, not on reject
8. Training pairs are emitted for verified distillation tickets only
9. Health endpoint reports accurate framework connectivity
10. No regression in ForgeAtlas, ForgeHarbor, or DAWN test suites
11. Gate policy matches SAM defaults (pass_fail + min_score 70 = hard gate; deny/oracle = warn)

---

*End of punch list. 7 P0s, 13 P1s, 9 P2s, 7 P3s. Critical path: P0-1 → P0-2 → P0-4 → P0-5 → P0-6 → P0-7 → P1-11 → P1-13.*
