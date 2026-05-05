# Azul — AI Developer Briefing

**Application:** Azul (Agentic Change Verification System)
**Date:** March 2026
**Audience:** AI Developer assigned to build Azul
**Companion documents:** Azul Core Specification, Implementation Plan, Punch List

---

## What You're Building

Azul is the first application built on top of the Forge framework ecosystem. It answers one question: **"Is this change safe?"** before the change takes effect.

A developer pushes a PR. A drift scanner proposes a refactor. A security advisory triggers a dependency bump. An agent generates training data. In every case, Azul takes the proposed change, runs it through a governed behavioral evaluation using the full Forge stack, and returns a structured verdict: **pass**, **reject**, or **warn** — with a complete evidence trail.

The name "Azul" represents the system's role as the clear verification layer across all Forge frameworks.

---

## Why This Exists

The Forge ecosystem has seven frameworks and services:

| Framework/Service | Role |
|---|---|
| **CONCORD** | Governance — who can do what, under what rules |
| **ForgeGate** | Intent governance — ALLOW/DENY on proposed actions |
| **ForgeWorks** | T&E pipeline — governed agent workflows, scores outcomes |
| **ForgeScaffold** | Blueprint generation — structural codebase analysis |
| **DAWN** | Execution engine — sandboxed links, audit ledgers |
| **ForgeAtlas** | Action discovery — agents query available tools |
| **ForgeHarbor** | Environment pool — warm Docker containers for agent execution |

These frameworks are powerful individually but have never been orchestrated together into a single workflow. Azul is that orchestration. It's the product that turns seven independent frameworks into one coherent verification system.

---

## Five Use Cases (All in v1.0 Scope)

| # | Use case | Trigger | Ticket type |
|---|---|---|---|
| 1 | **CI Pipeline Gate** | PR opened, CI webhook fires | `ci_gate` |
| 2 | **Agent-Proposed Refactors** | Drift scanner or autonomous agent proposes a fix | `refactor` |
| 3 | **Dependency/Security Patches** | Security advisory, lockfile delta | `security_patch` |
| 4 | **Domain Policy Compliance** | Runbook or procedure update | `policy_compliance` |
| 5 | **Distillation Training Gate** | Agent produces candidate training pairs | `distillation_pair` |

All five share the same core flow: **submit change → verify through Forge stack → return verdict.** The differences are in how the change enters the system (entry adapters) and what domain configuration is used (oracle paths, scoring paths, gate policies).

---

## How It Fits in the Architecture

```
         ┌─────────────────────────────────────┐
         │              AZUL                    │
         │   "Is this change safe?"             │
         │                                      │
         │   submit → verify → verdict          │
         │      │                   │            │
         │      ▼                   ▼            │
         │   Ticket             XP + Training    │
         │   Lifecycle          Pair Emission    │
         └──────────────┬───────────────────────┘
                        │
            orchestrates all frameworks
                        │
         ┌──────────────┼──────────────────────┐
         ▼              ▼              ▼        ▼
   ForgeScaffold   ForgeHarbor    ForgeAtlas  ForgeWorks
   (blast radius)  (environment)  (tools)     (shadow run)
                                                  │
                                              ForgeGate
                                              (5 gates/ticket)
                                                  │
                                                DAWN
                                              (execution)
                                                  │
                                              CONCORD
                                            (coordination)
```

---

## The Core Flow

This is the single most important thing to understand. Every use case runs through this:

```
1. SUBMITTED      Entry adapter creates AzulTicket from trigger
2. ANALYZING      ForgeScaffold maps blast radius (codebase domains only)
3. PROVISIONING   ForgeHarbor assigns a warm Docker container
4. EVALUATING     ForgeWorks runs governed shadow pipeline inside container
                  (ForgeGate governs each of 5 phases per ticket)
                  ReviewBundle returned with full evidence
5. GATING         FWResultGate evaluates ReviewBundle against policy
6. COMPLETED      Verdict = pass → XP awarded, training pair emitted (if distillation)
   REJECTED       Verdict = reject → evidence documents why
   WARNED         Verdict = pass with warnings → XP awarded, alerts fired
   FAILED         Operational error (not behavioral rejection)
```

---

## What Already Exists (You're Orchestrating, Not Rebuilding)

Every framework call Azul makes already has a working implementation. Your job is to wire them together, not rebuild them.

| Framework call | Entry point | Status |
|---|---|---|
| ForgeScaffold blast radius | importlib Pattern 1 → ForgeScaffold `run.py` | ✅ Built |
| ForgeHarbor request/release | `request_environment()` / `release_environment()` on daemon | ✅ Built (59 tests) |
| ForgeAtlas action discovery | importlib Pattern 1 → ForgeAtlas `run.py` | ✅ Built (95 tests) |
| ForgeWorks shadow pipeline | importlib Pattern 1 → `execute_planner_request()` | ✅ Built |
| ForgeGate phase governance | Called internally by ForgeWorks (5x per ticket) | ✅ Built |
| CONCORD coordination | Trust, budgets, sessions | ✅ Built (Level 6 readiness) |
| DAWN execution | Links, sandboxes, ledger | ✅ Built |
| FWResultGate | SAM `fw_result_gate.py` → extract into Azul | ✅ To be extracted |
| Planner spec builder | SAM `_build_planner_spec()` pattern → follow in Azul | ✅ Pattern documented |

### Two things you extract from SAM

1. **FWResultGate** (`fw_result_gate.py`): The gate evaluation logic. `evaluate()` takes a ReviewBundle and gate policy, returns a GateResult with severity (ok/warn/critical) and a passed boolean. Extract as-is into Azul's `gate.py`. Do not modify the logic.

2. **Planner spec construction pattern** (`_build_planner_spec()` in `forge_planner_agent.py`): The pattern for translating a ticket into a ForgeWorks planner_spec.v0_1 dict. Don't copy the function — build your own `build_verification_spec()` following the same structure but working from AzulTickets instead of SAM's ResearchTickets.

---

## The Gate Policy (What "Pass" Means)

```python
DEFAULT_GATE_POLICY = {
    "min_score":            70.0,   # CRITICAL (hard block) if below
    "warn_score":           80.0,   # WARN if below (but >= 70)
    "max_deny_count":       0,      # WARN if > 0 (not a hard block)
    "max_oracle_mismatch":  0,      # WARN if > 0 (not a hard block)
    "max_escalation_count": 2,      # WARN if > 2
    "require_pass_fail":    True,   # CRITICAL if pass_fail=False
}
```

**Hard gate (blocks):** `pass_fail = False` OR `total_score < 70` → verdict = reject.
**Soft alerts (warns):** deny_count > 0, oracle_mismatch > 0 → verdict = pass with warnings.

Gate policy is configurable per-ticket and per-domain via YAML files.

---

## The XP System

XP is awarded on successful verification (COMPLETED or WARNED). It serves two purposes:

1. **Tracks verification throughput** — XP totals show how much verified work flows through the system over time.
2. **Feeds future training** — for the distillation use case, XP on training pairs indicates verification quality. Higher-scoring pairs are more valuable training data.

XP is never awarded on REJECTED or FAILED tickets. The XP ledger is append-only (JSONL).

---

## Files You Must Read Before Writing Code

In this order:

| # | File | Why |
|---|---|---|
| 1 | ForgeHarbor `lifecycle_engine.py` | The status machine pattern you follow for Azul's ticket lifecycle |
| 2 | SAM `fw_result_gate.py` | The gate logic you extract into Azul |
| 3 | SAM `forge_planner_agent.py` → `_build_planner_spec()` | The spec construction pattern you follow |
| 4 | ForgeWorks `service_wrapper.py` | The `_ok/_error` envelope convention + `execute_planner_request()` interface |
| 5 | ForgeHarbor `daemon.py` | The daemon pattern you follow (startup, background loops, shutdown) |
| 6 | ForgeAtlas `run.py` | The importlib service pattern for framework calls |
| 7 | Azul Core Specification | The full architectural spec |

---

## What Success Looks Like

When you're done:

```python
# Developer pushes a PR, CI fires a webhook
result = azul.submit({
    "ticket_type": "ci_gate",
    "domain": "ci_change_control",
    "change_summary": "Fix null check in auth module",
    "change_payload": {"diff": unified_diff_text},
    "target_files": ["auth/validator.py"],
})
# result == {"status": "ok", "payload": {"ticket_id": "azul-001"}}

# Azul processes the ticket:
# 1. ForgeScaffold analyzes blast radius of auth/validator.py
# 2. ForgeHarbor assigns a warm Docker container
# 3. ForgeWorks shadow-runs the change inside the container
# 4. ForgeGate governs each phase (5 gates)
# 5. ReviewBundle comes back: score 91.5, pass_fail=True, 0 denies
# 6. FWResultGate: severity=ok, passed=True
# 7. Verdict: pass. XP awarded: 25.

verdict = azul.get_verdict("azul-001")
# verdict == {"status": "ok", "payload": {
#     "ticket_id": "azul-001",
#     "verdict": "pass",
#     "verdict_reason": "Shadow run passed: score 91.5, 0 denies, 0 oracle mismatches",
#     "review_bundle": {...},
#     "xp_awarded": 25,
# }}

# CI marks the PR as verified ✅
```

---

## What You Must NOT Build

| Out of scope | Why |
|---|---|
| Apply changes to production | Azul verifies. The caller applies based on the verdict. |
| Clone repos or manage branches | Azul receives diffs. Source control is the caller's domain. |
| Duplicate ForgeWorks pipeline | Azul calls `execute_planner_request()`. It doesn't reimplement the pipeline. |
| Duplicate ForgeGate governance | ForgeGate runs inside ForgeWorks. Azul reads the results. |
| Reimplement FWResultGate logic | Extract from SAM as-is. Don't modify the severity/policy evaluation. |
| Build a general-purpose ticket system | Azul tickets are verification requests optimized for the verify→verdict flow. |
| Build a UI | v1.0 is programmatic (importlib + CLI). UI is future work. |

---

## Build Phases (Summary)

| Phase | What you build | Framework deps | Tests |
|---|---|---|---|
| **1. Ticket Lifecycle** | Entity, status machine, persistence, XP, training pairs | None | 20–25 |
| **2. Gate + Spec Builder** | FWResultGate extraction, planner spec construction | None (extracted code) | 15–20 |
| **3. Verification Engine** | Core verify() flow with all framework integrations | All (mocked) | 20–25 |
| **4. Entry Adapters** | 5 adapters for all use cases | None | 10–15 |
| **5. Daemon + Queue** | Long-running daemon, concurrent processing | All (mocked) | 10–15 |
| **6. Docker Packaging** | Dockerfile, integration tests, telemetry | All (real) | 5–10 |

**Total: 80–110 tests across 12–18 sessions.**

Phase 1 is pure logic — start there. Same principle as ForgeHarbor: build the ticket lifecycle and persistence layer with zero framework dependencies. That's your foundation.

---

## The Forge Family (Complete)

| Name | Layer | Role |
|---|---|---|
| **CONCORD** | Governance | Backend assessment & control specification |
| **ForgeGate** | Governance | Deterministic intent governance |
| **ForgeWorks** | Framework | T&E pipeline + domain onboarding |
| **ForgeScaffold** | Framework | Blueprint generation + governed change mgmt |
| **DAWN** | Execution | Deterministic auditable workflow network |
| **ForgeAtlas** | Service | Action discovery + semantic search |
| **ForgeHarbor** | Service | Warm-pool environment orchestrator |
| **Azul** | Application | Agentic change verification system |

Azul is the application layer. Everything below it is infrastructure. Azul is where the value becomes visible to users.

---

*End of briefing. Read the seven files listed above, then start with Phase 1: ticket lifecycle. Pure logic, no framework dependencies. The pattern is the same one that worked for ForgeHarbor — state machine first, integrations later.*
