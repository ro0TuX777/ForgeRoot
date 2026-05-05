# Forge Recursive Improvement Loop — Punch List

**Status:** Draft v0.1 — 2026-03-08
**Companion to:** Core Specification v0.1, Implementation Plan v0.1
**Convention:** P0 = blocks all downstream work. P1 = blocks release. P2 = should ship. P3 = nice to have.

---

## P0 — Blocks Everything

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P0-1 | `AnalysisReport` + `MetricTrend` + `FailureCluster` + `ThresholdFlag` types | 1 | All dataclasses defined with correct fields. MetricTrend includes value + direction + window. |
| P0-2 | `analyze()` computes reject_rate by ticket_type | 1 | Correct rate from synthetic data. Handles zero tickets gracefully. Groups by all 5 ticket types. |
| P0-3 | `analyze()` computes score_distribution and score_trend | 1 | Histogram correct. Trend direction (rising/falling/flat) matches synthetic data slope. |
| P0-4 | `analyze()` computes failure_mode_clustering | 1 | FAILED tickets grouped by error code. Cluster count and dominant cause correct. |
| P0-5 | `GoldLabel` type + `record_label()` + append-only JSONL store | 2 | Diff computed between original and approved. Stored to `gold_labels.jsonl`. Queryable by artifact_type and time range. |
| P0-6 | `compute_agreement_rate()` | 2 | Agreements / total reviews. Correct for 100% agreement, 0% agreement, and mixed data. |
| P0-7 | `recommend()` generates Level 1 recommendation when reject_rate > threshold | 3 | Prompt diff includes rationale, affected ticket_type, and example ReviewBundles. |

---

## P1 — Blocks Release

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P1-1 | `analyze()` computes deny_rate by ForgeGate phase | 1 | Correct deny count per phase (Scout, Legislator, Builder, Judge, Deployer). Handles tickets with no ForgeGate data. |
| P1-2 | `analyze()` computes oracle_mismatch_frequency | 1 | Recurring mismatches identified with count per action/resource. |
| P1-3 | `analyze()` computes xp_velocity and distillation_yield | 1 | XP per time window correct. Yield = training pairs / total tickets. |
| P1-4 | `analyze()` computes dev_performance_ranking | 1 | Devs ranked by average score. Handles single-Dev data. |
| P1-5 | Threshold configuration from environment variables | 1 | All 11 variables from spec §11.1 read with correct defaults. |
| P1-6 | `scan_drift()` compares originals vs approved contracts | 2 | Detects changed fields. Classifies drift direction (improvement/regression/stable). Reports agreement_rate_trend. |
| P1-7 | `DriftReport` includes recommendations | 2 | At least one recommendation per drifted contract. Recommendations reference specific fields. |
| P1-8 | `recommend()` generates Level 2 when oracle_mismatch repeats 3+ times | 3 | Contract patch includes specific field changes, affected contract name, and rationale. |
| P1-9 | `recommend()` generates Level 3 when policy override repeats 5+ times | 3 | Policy adjustment includes threshold change, domain, rationale, and expected impact. |
| P1-10 | `recommend()` generates Level 4 when training pairs > batch_size | 3 | Distillation batch manifest lists pairs above min_score. Includes pair_count, avg_score, domains. |
| P1-11 | `ImprovementPlan.requires_human_review` always True | 3 | No code path sets this to False. Tested explicitly. |
| P1-12 | `on_ticket_complete()` hook in orchestrator | 4 | Increments counter. Runs analysis when counter hits threshold_window. Resets counter after analysis. |
| P1-13 | `run_scheduled_scan()` produces improvement report | 4 | Report written to `azul_data/improvement_reports/` as JSON. Contains analysis + drift + improvement plan. |
| P1-14 | Integration with Azul daemon | 4 | `on_ticket_complete` called from verification engine return path. Scheduled scan in background loop. No regression in existing 214 Azul tests. |

---

## P2 — Should Ship

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P2-1 | `analyze()` handles empty ticket store | 1 | Returns valid AnalysisReport with zeroed metrics. Does not crash. |
| P2-2 | Gold label diff handles nested dict changes | 2 | Correctly diffs nested objects (e.g., guard_predicates list changes, budget_cost_units number changes). |
| P2-3 | Drift scanner handles new contracts (present in catalog, no original to compare) | 2 | Reports as "new, no drift baseline" rather than erroring. |
| P2-4 | Recommender generates empty plan when no thresholds crossed | 3 | All recommendation lists empty. requires_human_review still True. |
| P2-5 | `run_distillation_batch()` prepares batch manifest | 4 | Manifest JSON in `azul_data/distillation_batches/`. Pairs above min_score only. |
| P2-6 | CLI: `azul loop status` | 4 | Returns current metrics snapshot as formatted output. |
| P2-7 | CLI: `azul loop report` | 4 | Returns latest improvement report. |
| P2-8 | CLI: `azul loop agreement-rate` | 4 | Returns current Lead Agreement Rate with trend. |

---

## P3 — Nice to Have (Not Required for v1.0)

| # | Item | Phase | Acceptance criteria |
|---|---|---|---|
| P3-1 | Score trend visualization data (time-series export) | 1+ | Score trend exportable as CSV or JSON time-series for external charting. |
| P3-2 | Gold label diff visualization (human-readable format) | 2+ | Pretty-printed diff showing what was added/removed/changed per field. |
| P3-3 | Recommender confidence scoring | 3+ | Each recommendation carries a confidence level (high/medium/low) based on evidence strength. |
| P3-4 | Cross-domain comparison in analysis | 1+ | Reject rates and scores compared across domains. Anomalous domains flagged. |
| P3-5 | Historical agreement rate chart data | 2+ | Agreement rate over time exportable for trend visualization. |
| P3-6 | Distillation batch preview (dry-run) | 4+ | Show what pairs would be in the next batch without actually preparing it. |

---

## Dependency Map

```
P0-1 (types) ──→ P0-2 (reject_rate) ──→ P0-3 (score_trend) ──→ P0-4 (failure_clusters)
                      │
                      ▼
              P1-1 (deny_rate) + P1-2 (oracle_mismatch) + P1-3 (xp/yield) + P1-4 (dev ranking)
                      │
                      ▼
              P0-5 (gold labels) ──→ P0-6 (agreement_rate) ──→ P1-6 (drift scanner)
                      │                                               │
                      └───────────────────┬───────────────────────────┘
                                          ▼
                                  P0-7 (recommender Level 1)
                                          │
                              ┌───────────┼───────────┐
                              ▼           ▼           ▼
                      P1-8 (Level 2)  P1-9 (Level 3) P1-10 (Level 4)
                              │           │           │
                              └───────────┼───────────┘
                                          ▼
                                  P1-12 (orchestrator hook)
                                          │
                                          ▼
                                  P1-13 (scheduled scan) ──→ P1-14 (Azul integration)
```

---

## Test Coverage Summary

| Phase | Test files | Target count |
|---|---|---|
| 1 | test_pattern_analyzer.py | 15–20 |
| 2 | test_gold_labels.py, test_drift_scanner.py | 15–20 |
| 3 | test_recommender.py | 12–18 |
| 4 | test_orchestrator.py, test_loop_integration.py | 10–15 |
| **Total** | | **52–73** |

---

## Definition of Done

The Recursive Improvement Loop is complete when:

1. All P0 and P1 items pass their acceptance criteria
2. All P2 items pass or have documented deferral reasons
3. Test count ≥ 52 with zero failures
4. Pattern Analyzer produces correct metrics from Azul's real ticket store
5. Gold Label Store records diffs and computes agreement rate
6. Drift Scanner detects contract changes between scans
7. Recommender produces actionable recommendations at all 4 levels (when thresholds are crossed)
8. Recommender produces empty plan when no thresholds are crossed
9. `requires_human_review` is True on every ImprovementPlan (no exceptions)
10. Loop orchestrator integrates with Azul daemon without regressing existing tests
11. Improvement reports are persisted as JSON and queryable via CLI
12. Lead Agreement Rate is computable and the top-line metric is surfaced in `azul loop status`

---

*End of punch list. 7 P0s, 14 P1s, 8 P2s, 6 P3s. Critical path: P0-1 → P0-2 → P0-5 → P0-6 → P0-7 → P1-12 → P1-14.*
