# Forge Recursive Improvement Loop — AI Developer Briefing

**Feature:** Recursive Improvement Loop
**Date:** March 2026
**Audience:** AI Developer assigned to build the loop (Azul codebase extension)
**Companion documents:** Recursive Loop Core Specification, Implementation Plan, Punch List

---

## What You're Building

The Recursive Improvement Loop makes the Forge ecosystem self-improving. Right now, Azul verifies changes and produces verdicts. The loop analyzes those verdicts for patterns, detects what's going wrong, recommends fixes, and feeds the improvements back into the next cycle.

Without the loop, the system does the same quality of work forever. With the loop, every cycle makes the next one better — prompts get sharper, contracts get tighter, policies get calibrated, and models get trained on verified examples.

---

## Why This Exists

Azul already produces three things the loop needs:

1. **ReviewBundles** — structured evidence of every verification (scores, ForgeGate decisions, oracle matches, deny counts)
2. **XP Ledger** — tracking verification throughput and quality over time
3. **Training Pairs** — verified input-output examples for model fine-tuning

These exist as raw data. The loop turns that raw data into actionable intelligence: "reject rate for refactors is 35% — here's why, and here's a specific prompt change that should reduce it."

---

## The Loop in One Diagram

```
EXECUTE ──▶ VERIFY ──▶ LEARN ──▶ IMPROVE ──▶ (back to EXECUTE)
  │            │          │          │
  │            │          │          ├── Level 1: Update prompts
  AI Devs      Azul       Pattern    ├── Level 2: Refine contracts
  propose      evaluates  Analyzer   ├── Level 3: Tune gate policies
  changes      + scores   computes   └── Level 4: Distillation training
                          metrics
```

Every improvement requires human approval. The loop accelerates human judgment — it does not replace it.

---

## What You're Building (Five Components)

All five live in `azul/loop/` as an extension to the existing Azul codebase.

### 1. Pattern Analyzer (`pattern_analyzer.py`)

Reads Azul's ticket store, XP ledger, and ReviewBundles. Computes 10 metrics:

| Metric | What it tells you |
|---|---|
| Lead Agreement Rate | How often humans approve AI output unmodified (top-line metric) |
| Reject rate (by ticket_type) | Which work types the Devs struggle with |
| Deny rate (by ForgeGate phase) | Which governance rules Devs don't understand |
| Oracle mismatch frequency | Behavioral expectations that need clearer specification |
| Score distribution | Histogram of verification scores |
| Score trend | Moving average — is quality rising or falling? |
| Failure mode clustering | FAILED tickets grouped by error code |
| XP velocity | Throughput of verified work |
| Distillation yield | Training pairs emitted per total tickets |
| Dev performance ranking | Which agent configurations produce the best work |

This is a pure data component. It reads everything, writes nothing, has no side effects.

### 2. Gold Label Store (`gold_labels.py`)

Captures the difference between what AI generated and what a human approved. Every time a human edits an AI-generated artifact (contract stub, gate policy, briefing) before approving it, the diff is a "gold label" — it shows exactly what the system got wrong.

Gold labels are the highest-value signal in the entire loop. A ReviewBundle tells you pass/fail. A gold label tells you *what to fix*.

Stored as append-only JSONL. Queryable by artifact type and time range. Computes the Lead Agreement Rate (agreements / total reviews).

### 3. Drift Scanner (`drift_scanner.py`)

Runs on a scheduled cadence (weekly by default). Compares the original AI-generated versions of contracts and policies against the current approved versions. Detects slow drift that never crosses an acute threshold but accumulates.

The drift scan answers: "Are our contracts getting tighter (improvement) or looser (regression) over time?"

### 4. Improvement Recommender (`recommender.py`)

Takes an AnalysisReport and generates specific, actionable recommendations at four levels:

| Level | Trigger | What it recommends |
|---|---|---|
| 1: Prompts | Reject rate > 30% or agreement rate < 70% | Specific additions to Dev briefings with examples from ReviewBundles |
| 2: Contracts | Same oracle mismatch 3+ times | Specific field changes to ActionContract YAML with rationale |
| 3: Policies | Same gate override 5+ times | Specific threshold adjustments to gate policy YAML with expected impact |
| 4: Distillation | Training pairs > batch_size (100) | Batch manifest of verified pairs above score threshold (90) |

Every recommendation includes a rationale. Every ImprovementPlan has `requires_human_review = True` — always, no exceptions, no code path sets it to False.

### 5. Loop Orchestrator (`orchestrator.py`)

Wires everything together. Two trigger mechanisms:

**Threshold triggers (acute):** After every ticket completes, the orchestrator increments a counter. When the counter hits the threshold window (default 50 tickets), it runs the Pattern Analyzer and checks whether any threshold was crossed. If so, it runs the Recommender and produces an improvement report.

**Scheduled scans (drift):** On a weekly cadence, the orchestrator runs the Drift Scanner, the full Pattern Analyzer, and the Recommender regardless of whether thresholds were crossed. This catches slow degradation.

The orchestrator hooks into Azul's daemon — `on_ticket_complete()` is called from the verification engine's return path.

---

## The One Metric That Matters Most

**Lead Agreement Rate** — how often a human approves AI output without editing it.

If this number is climbing, the loop is working. If it's flat, something in the LEARN → IMPROVE chain is broken. Every other metric is diagnostic; this one is the headline.

Target trajectory: 60% → 95% over 30 days of active use.

---

## Where It Lives in the Codebase

```
azul/
├── loop/
│   ├── __init__.py
│   ├── types.py              ← AnalysisReport, MetricTrend, GoldLabel, DriftReport, ImprovementPlan
│   ├── config.py             ← threshold + schedule configuration from env vars
│   ├── pattern_analyzer.py   ← compute all metrics from Azul data
│   ├── gold_labels.py        ← record human-vs-AI diffs, compute agreement rate
│   ├── drift_scanner.py      ← weekly comparison of originals vs approved
│   ├── recommender.py        ← generate improvement recommendations (4 levels)
│   └── orchestrator.py       ← threshold triggers + scheduled scans + Azul integration
├── tests/
│   ├── test_pattern_analyzer.py
│   ├── test_gold_labels.py
│   ├── test_drift_scanner.py
│   ├── test_recommender.py
│   ├── test_orchestrator.py
│   └── test_loop_integration.py
```

You're extending Azul, not building a separate service. The loop reads directly from Azul's ticket store, XP ledger, and training pairs — no network calls, no separate containers.

---

## What Already Exists (You're Consuming, Not Rebuilding)

| Data source | Location | What you read from it |
|---|---|---|
| Ticket store | `azul_data/tickets/` | Status, verdict, gate_result, review_bundle, ticket_type |
| XP ledger | `azul_data/xp_ledger.jsonl` | XP per ticket, domain, type, timestamps |
| Training pairs | `azul_data/training_pairs/` | Verification score, domain, verified_at |
| Action catalogs | `action_catalogs/` | Current contract definitions (for drift comparison) |
| Gate policies | `config/gate_policies/` | Current policy thresholds (for drift comparison) |

Do not modify any of these stores from the loop code. The loop reads evidence and writes its own outputs (gold labels, improvement reports, drift reports, distillation batches) to separate locations.

---

## Files You Must Read Before Writing Code

| # | File | Why |
|---|---|---|
| 1 | `azul/ticket_store.py` | How tickets are stored and queried — your primary data source |
| 2 | `azul/xp_ledger.py` | XP tracking — how rewards are recorded |
| 3 | `azul/training_pairs.py` | Training pair emission — what Level 4 distillation consumes |
| 4 | `azul/gate.py` | Gate evaluation — how verdicts and severity are computed |
| 5 | `azul/daemon.py` | Where the orchestrator hooks in (background loop + on_ticket_complete) |
| 6 | Recursive Loop Core Specification | The full design you're implementing |

---

## What Success Looks Like

```bash
# After 50 tickets have been processed
$ azul loop status

Lead Agreement Rate:  78% (↑ from 65% last week)
Reject Rate:          ci_gate: 12%  refactor: 28%  security_patch: 8%
Score Trend:          rising (avg 84.2, +3.1 from last window)
XP Velocity:          340 XP / week
Distillation Yield:   62% of tickets produce training pairs
Thresholds Crossed:   refactor reject_rate approaching 30% (currently 28%)

$ azul loop report

Improvement Report — 2026-03-15
  Level 1 (Prompts):     1 recommendation
    → refactor briefing: add guard_predicate examples from gold labels
      Rationale: 4 of 5 recent refactor rejects were missing balance_sufficient guard
  Level 2 (Contracts):   0 recommendations
  Level 3 (Policies):    0 recommendations
  Level 4 (Distillation): batch ready (112 pairs, avg score 93.2)
  
  Human review required: YES

$ azul loop agreement-rate

Lead Agreement Rate: 78%
  action_contract_stubs:  82% (41/50)
  gate_policy_reviews:    71% (17/24)
  verdict_acceptances:    85% (68/80)
  Trend: rising (+13% over 30 days)
```

---

## What You Must NOT Build

| Out of scope | Why |
|---|---|
| Auto-apply prompt updates | Prompts shape agent behavior. Human reviews every change. |
| Auto-modify gate policies | Governance decisions require human judgment. |
| Auto-merge contract changes | Contracts define behavioral expectations. Domain knowledge required. |
| Train models without human approval | Fine-tuning is irreversible in practice. Architect approves each batch. |
| Override past Azul verdicts | The loop improves the future. It doesn't change the past. |
| Modify Azul's existing ticket store | The loop reads evidence. It writes to its own stores only. |

---

## Build Phases (Summary)

| Phase | What you build | Tests |
|---|---|---|
| **1. Pattern Analyzer** | Metrics computation from existing Azul data | 15–20 |
| **2. Gold Labels + Drift** | Human-vs-AI tracking + scheduled drift detection | 15–20 |
| **3. Recommender** | Actionable recommendations at 4 levels | 12–18 |
| **4. Orchestrator** | Threshold triggers + scheduled scans + Azul integration | 10–15 |

**Total: 52–73 tests across 8–12 sessions.**

Phase 1 is pure data analysis — no side effects, no writes, no triggers. Start there. Same foundation-first pattern that worked for every previous build.

---

*End of briefing. Read the six files listed above, then start with Phase 1: pattern analyzer. Pure data in, structured metrics out. The analyzer is the foundation — everything else builds on its output.*
