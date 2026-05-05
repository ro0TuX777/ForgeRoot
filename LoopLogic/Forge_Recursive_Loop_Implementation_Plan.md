# Forge Recursive Improvement Loop — Implementation Plan

**Status:** Draft v0.1 — 2026-03-08
**Prerequisite:** Recursive Loop Core Specification v0.1
**Target:** AI Dev (extension to Azul)
**Location:** `azul/loop/` subdirectory within the Azul codebase

---

## Overview

The Recursive Improvement Loop adds five components to Azul. Unlike ForgeAtlas and ForgeHarbor (standalone services), the loop lives inside Azul — it consumes Azul's ticket store, XP ledger, and ReviewBundles directly.

This plan builds the loop in four phases. Phase 1 is pure data analysis (no external effects). Phase 2 adds the recommendation engine. Phase 3 adds drift detection and gold labels. Phase 4 wires it into Azul's daemon as a background process.

### Existing assets the loop consumes

| Asset | Location | Status |
|---|---|---|
| Ticket store (JSON files) | `azul_data/tickets/` | ✅ Built in Azul Phase 1 |
| XP ledger (JSONL) | `azul_data/xp_ledger.jsonl` | ✅ Built in Azul Phase 1 |
| Training pairs | `azul_data/training_pairs/` | ✅ Built in Azul Phase 1 |
| ReviewBundles (inside tickets) | `ticket.review_bundle` field | ✅ Built in ForgeWorks + Azul Phase 3 |
| Gate results (inside tickets) | `ticket.gate_result` field | ✅ Built in Azul Phase 2 |
| ActionContract YAML manifests | `action_catalogs/` | ✅ Built in ForgeAtlas Phase 1 |
| Gate policy YAML files | `config/gate_policies/` | ✅ Built in Azul Phase 2 |

### What does NOT exist (building this)

| Component | Purpose |
|---|---|
| Pattern Analyzer | Compute metrics from verification evidence |
| Gold Label Store | Capture human edits vs AI originals |
| Drift Scanner | Compare originals vs approved on schedule |
| Improvement Recommender | Generate actionable recommendations |
| Loop Orchestrator | Trigger analysis on thresholds and schedule |

---

## Phase 1 — Pattern Analyzer (Pure Data, No Side Effects)

**Goal:** Read Azul's existing data stores and compute all metrics from the spec. No writes, no recommendations, no triggers.

**Duration estimate:** 2–3 sessions

### Deliverables

1. **`loop/pattern_analyzer.py`**: Core analysis engine.
   - `analyze(ticket_store, xp_ledger, window)` → `AnalysisReport`
   - Computes: reject_rate (by ticket_type), deny_rate (by ForgeGate phase), oracle_mismatch_frequency, score_distribution, score_trend, failure_mode_clustering, xp_velocity, distillation_yield, dev_performance_ranking

2. **`loop/types.py`**: Data types for the loop.
   - `AnalysisReport` — structured container for all computed metrics
   - `MetricTrend` — value + direction (rising/falling/flat) + window
   - `FailureCluster` — grouped failure modes with count and common cause
   - `ThresholdFlag` — which thresholds were crossed, with severity

3. **`loop/config.py`**: Threshold and schedule configuration. Reads from environment variables with defaults matching the spec.

4. **Tests**: Analyzer produces correct metrics from synthetic ticket data. Reject rate computed correctly across ticket types. Score trend detects rising/falling/flat. Failure clustering groups by error code. Empty ticket store produces valid (zeroed) report.

### Validation criteria

```python
# Synthetic data: 50 tickets, 40 COMPLETED, 5 REJECTED, 5 FAILED
store = create_synthetic_store(completed=40, rejected=5, failed=5)
report = analyze(store, xp_ledger, window=50)

assert report.reject_rate["ci_gate"] == 5/50  # or per-type calculation
assert report.score_trend.direction in ("rising", "falling", "flat")
assert len(report.failure_clusters) > 0
assert report.xp_velocity > 0
```

### Files created

| File | Purpose |
|---|---|
| `loop/__init__.py` | Package init |
| `loop/types.py` | AnalysisReport, MetricTrend, FailureCluster, ThresholdFlag |
| `loop/config.py` | Threshold + schedule configuration |
| `loop/pattern_analyzer.py` | Core analysis engine |
| `tests/test_pattern_analyzer.py` | Analyzer tests with synthetic data |

---

## Phase 2 — Gold Label Store + Drift Scanner

**Goal:** Capture human-vs-AI diffs (gold labels) and detect slow drift on a scheduled cadence.

**Duration estimate:** 2–3 sessions

### Deliverables

1. **`loop/gold_labels.py`**: Gold Label Store.
   - `record_label(artifact_type, original, approved, reviewer_id)` → `GoldLabel`
   - Computes diff between original and approved
   - Appends to `azul_data/gold_labels/gold_labels.jsonl`
   - `get_labels(artifact_type, since)` → query stored labels
   - `compute_agreement_rate(artifact_type, window)` → float (agreements / total reviews)

2. **`loop/drift_scanner.py`**: Scheduled drift detection.
   - `scan_drift(catalog_dir, policy_dir, gold_label_store, since)` → `DriftReport`
   - Compares original AI-generated stubs against current approved contracts
   - Computes agreement rate trend over time
   - Identifies systematic drift patterns (which fields change most, which direction)

3. **`DriftReport` type**: Added to `loop/types.py`.
   - contracts_compared, contracts_drifted, drift_direction, gold_labels_since, agreement_rate_trend, recommendations

4. **Tests**: Gold label records correctly from original/approved pairs. Agreement rate computes correctly. Drift scanner detects changed contracts. Drift direction correctly classified as improvement vs regression.

### Validation criteria

```python
# Record a gold label (human edited a guard predicate)
label = record_label(
    artifact_type="action_contract_stub",
    original={"guard_predicates": [{"name": "state_is_draft"}]},
    approved={"guard_predicates": [{"name": "state_is_draft"}, {"name": "balance_sufficient"}]},
    reviewer_id="vin",
)
assert label.diff == {"guard_predicates": {"added": [{"name": "balance_sufficient"}]}}

# Agreement rate
rate = compute_agreement_rate("action_contract_stub", window=20)
assert 0.0 <= rate <= 1.0

# Drift scan
drift = scan_drift(catalog_dir, policy_dir, gold_label_store, since=last_week)
assert drift.contracts_compared > 0
assert drift.drift_direction in ("improvement", "regression", "stable")
```

### Files created

| File | Purpose |
|---|---|
| `loop/gold_labels.py` | Gold Label Store + agreement rate |
| `loop/drift_scanner.py` | Scheduled drift detection |
| `tests/test_gold_labels.py` | Gold label recording + agreement rate tests |
| `tests/test_drift_scanner.py` | Drift detection tests |

---

## Phase 3 — Improvement Recommender

**Goal:** Take analysis reports and generate specific, actionable recommendations at all four improvement levels.

**Duration estimate:** 2–3 sessions

### Deliverables

1. **`loop/recommender.py`**: Improvement recommendation engine.
   - `recommend(report, gold_labels, current_contracts, current_policies)` → `ImprovementPlan`
   - Level 1 (prompts): When reject_rate > threshold or agreement_rate < threshold, generate prompt diffs with before/after examples drawn from ReviewBundles and gold labels
   - Level 2 (contracts): When oracle_mismatch repeats 3+ times, propose contract patches with specific field changes and rationale
   - Level 3 (policies): When gate overrides repeat 5+ times for same reason, propose policy threshold adjustments
   - Level 4 (distillation): When training pairs exceed batch_size, prepare distillation batch manifest

2. **`ImprovementPlan` type**: Added to `loop/types.py`.
   - prompt_diffs: list of PromptDiff (target_file, additions, removals, examples, rationale)
   - contract_patches: list of ContractPatch (contract_name, field_changes, rationale)
   - policy_adjustments: list of PolicyAdjustment (domain, threshold_changes, rationale, expected_impact)
   - distillation_batch: DistillationBatch | None (pair_count, avg_score, domains, manifest_path)
   - requires_human_review: True (always)

3. **Tests**: Recommender generates Level 1 recommendations when reject rate high. Generates Level 2 when oracle mismatch repeats. Generates Level 3 when overrides repeat. Generates Level 4 when pairs exceed batch. Generates empty plan when no thresholds crossed. Every recommendation includes rationale.

### Validation criteria

```python
# High reject rate → Level 1 recommendation
report = AnalysisReport(reject_rate={"ci_gate": 0.35}, ...)
plan = recommend(report, gold_labels, contracts, policies)
assert len(plan.prompt_diffs) > 0
assert plan.prompt_diffs[0].rationale is not None

# Recurring oracle mismatch → Level 2 recommendation
report = AnalysisReport(oracle_mismatch_frequency={"process_payment": 4}, ...)
plan = recommend(report, gold_labels, contracts, policies)
assert len(plan.contract_patches) > 0

# No thresholds crossed → empty plan
report = AnalysisReport(reject_rate={"ci_gate": 0.10}, ...)
plan = recommend(report, gold_labels, contracts, policies)
assert len(plan.prompt_diffs) == 0
assert len(plan.contract_patches) == 0
assert plan.requires_human_review == True  # always
```

### Files created

| File | Purpose |
|---|---|
| `loop/recommender.py` | Improvement recommendation engine |
| `tests/test_recommender.py` | Recommendation tests across all 4 levels |

---

## Phase 4 — Loop Orchestrator + Integration

**Goal:** Wire the loop into Azul's daemon as a background process with both threshold triggers and scheduled scans.

**Duration estimate:** 2–3 sessions

### Deliverables

1. **`loop/orchestrator.py`**: Loop orchestration engine.
   - `on_ticket_complete(ticket)` — called by Azul after every verdict. Increments counters. When counter hits threshold_window, runs pattern analyzer and checks thresholds.
   - `run_scheduled_scan()` — periodic: drift scan + full analysis + improvement report. Writes report to `azul_data/improvement_reports/`.
   - `run_distillation_batch()` — periodic: collect verified pairs above score threshold, prepare batch manifest in `azul_data/distillation_batches/`.

2. **Integration with Azul daemon**: Hook `on_ticket_complete` into Azul's verification engine return path. Add scheduled scan to Azul's background loop alongside queue reconciliation.

3. **Report output**: Improvement reports written as JSON to `azul_data/improvement_reports/`. Each report contains the AnalysisReport, DriftReport (if scheduled), and ImprovementPlan.

4. **CLI commands**: 
   - `azul loop status` — current metrics snapshot
   - `azul loop report` — latest improvement report
   - `azul loop agreement-rate` — current Lead Agreement Rate
   - `azul loop drift` — latest drift report

5. **Tests**: Orchestrator triggers analysis after N tickets. Scheduled scan produces report. Distillation batch collects pairs above threshold. CLI commands return expected shapes. Integration with Azul daemon doesn't break existing tests.

### Validation criteria

```python
# Threshold trigger
orchestrator = LoopOrchestrator(threshold_window=5)
for ticket in completed_tickets[:5]:
    orchestrator.on_ticket_complete(ticket)
# After 5th ticket, analysis should have run
assert orchestrator.last_analysis is not None

# Scheduled scan
report = orchestrator.run_scheduled_scan()
assert report.analysis is not None
assert report.drift is not None
assert report.improvement_plan is not None

# Distillation batch
batch = orchestrator.run_distillation_batch()
assert batch.pair_count > 0
assert all(p["verification_score"] >= 90.0 for p in batch.pairs)
```

### Files created

| File | Purpose |
|---|---|
| `loop/orchestrator.py` | Loop orchestration + Azul integration |
| `tests/test_orchestrator.py` | Orchestration + trigger tests |
| `tests/test_loop_integration.py` | Integration with Azul daemon |

---

## Phase Summary

| Phase | Builds | Dependencies | Test count target |
|---|---|---|---|
| Phase 1: Pattern Analyzer | Metrics computation from existing data | Azul ticket store + XP ledger | 15–20 |
| Phase 2: Gold Labels + Drift | Human-vs-AI tracking + scheduled drift detection | Phase 1 + action_catalogs + gate_policies | 15–20 |
| Phase 3: Recommender | Actionable improvement recommendations at 4 levels | Phases 1–2 | 12–18 |
| Phase 4: Orchestrator | Threshold triggers + scheduled scans + Azul integration | Phases 1–3 + Azul daemon | 10–15 |

**Total estimated test count: 52–73**
**Total estimated duration: 8–12 sessions**

---

## Files the Dev Must Read Before Starting

| # | File | Why |
|---|---|---|
| 1 | `azul/ticket_store.py` | The data source — how tickets are stored and queried |
| 2 | `azul/xp_ledger.py` | XP data — how rewards are tracked |
| 3 | `azul/training_pairs.py` | Training pair emission — what the distillation level consumes |
| 4 | `azul/gate.py` | Gate evaluation — how verdicts are computed |
| 5 | `azul/daemon.py` | Where the orchestrator hooks in |
| 6 | Recursive Loop Core Specification | The full design this plan implements |

---

*End of implementation plan. Four phases. Phase 1 is pure data analysis. Phases 2–3 add gold labels, drift detection, and recommendations. Phase 4 wires it into Azul. 52–73 tests across 8–12 sessions.*
