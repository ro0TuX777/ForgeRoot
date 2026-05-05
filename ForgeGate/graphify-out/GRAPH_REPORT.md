# Graph Report - .  (2026-05-04)

## Corpus Check
- Corpus is ~1,813 words - fits in a single context window. You may not need a graph.

## Summary
- 50 nodes · 61 edges · 12 communities detected
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 6 edges (avg confidence: 0.82)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]

## God Nodes (most connected - your core abstractions)
1. `evaluate` - 10 edges
2. `_eval_expr` - 6 edges
3. `Deterministic Action-Governance Gate` - 6 edges
4. `DecisionRecord` - 6 edges
5. `Evaluation Pipeline` - 6 edges
6. `evaluate()` - 5 edges
7. `_eval_expr()` - 5 edges
8. `forgegate evaluate CLI Command` - 5 edges
9. `ForgeGateEvaluationError` - 4 edges
10. `_truthy()` - 3 edges

## Surprising Connections (you probably didn't know these)
- `Reference Gate` --semantically_similar_to--> `evaluate`  [INFERRED] [semantically similar]
  context.md → forgegate/core/evaluate.py
- `evaluate` --implements--> `DecisionRecord`  [INFERRED]
  forgegate/core/evaluate.py → context.md
- `forgegate evaluate CLI Command` --references--> `DecisionRecord`  [INFERRED]
  forgegate/cli/main.py → context.md
- `Evaluation Pipeline` --semantically_similar_to--> `Reference Gate`  [INFERRED] [semantically similar]
  ForgeGatewhitepaper.md → context.md
- `app()` --calls--> `evaluate()`  [INFERRED]
  cli\main.py → core\evaluate.py

## Hyperedges (group relationships)
- **Deterministic Gate Contract** — context_proposed_action, context_signals, context_budget_snapshot, context_decision_record, evaluate_evaluate [EXTRACTED 1.00]
- **Evaluation Pipeline Steps** — forgegatewhitepaper_constraints, forgegatewhitepaper_boundaries, forgegatewhitepaper_budgets, forgegatewhitepaper_tradeoffs, forgegatewhitepaper_shaping, context_decision_record [EXTRACTED 1.00]
- **CLI Reference Evaluation Flow** — main_app, main_evaluate_command, evaluate_evaluate, context_decision_record [INFERRED 0.84]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.24
Nodes (10): BudgetSnapshot, Phase 1 Gate Interface v0.1, Reference Gate, Scenario Test Harness, Signals, evaluate, _normalize_signals, Package evaluate Export (+2 more)

### Community 1 - "Community 1"
Cohesion: 0.33
Nodes (6): Deterministic Action-Governance Gate, ForgeGate, ProposedAction, LLM Policy Decider Risk, Policy as Code, Policy Enforcement Plane

### Community 2 - "Community 2"
Cohesion: 0.33
Nodes (6): Boundaries, Budgets, Constraints, Evaluation Pipeline, Shaping, Tradeoffs

### Community 3 - "Community 3"
Cohesion: 0.5
Nodes (2): Minimal deterministic ForgeGate evaluator compatibility layer.  This restores th, _resolve_var()

### Community 4 - "Community 4"
Cohesion: 0.67
Nodes (4): _eval_expr(), evaluate(), _normalize_signals(), _truthy()

### Community 5 - "Community 5"
Cohesion: 0.67
Nodes (4): _eval_expr, ForgeGateEvaluationError, _resolve_var, _truthy

### Community 6 - "Community 6"
Cohesion: 0.67
Nodes (4): Canonical Hashing, DAWN Optional Execution Substrate, DecisionRecord, Replay Safety

### Community 7 - "Community 7"
Cohesion: 0.67
Nodes (2): app(), Minimal ForgeGate CLI compatibility entry point.

### Community 8 - "Community 8"
Cohesion: 0.67
Nodes (3): ForgeGateEvaluationError, Raised when an intent spec cannot be evaluated deterministically., Exception

### Community 9 - "Community 9"
Cohesion: 1.0
Nodes (1): ForgeGate CLI package.

### Community 10 - "Community 10"
Cohesion: 1.0
Nodes (1): Core ForgeGate exports.

### Community 11 - "Community 11"
Cohesion: 1.0
Nodes (1): ForgeGate schema package placeholder.

## Knowledge Gaps
- **21 isolated node(s):** `Minimal ForgeGate CLI compatibility entry point.`, `ForgeGate CLI package.`, `Minimal deterministic ForgeGate evaluator compatibility layer.  This restores th`, `Raised when an intent spec cannot be evaluated deterministically.`, `Core ForgeGate exports.` (+16 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 3`** (4 nodes): `evaluate.py`, `Minimal deterministic ForgeGate evaluator compatibility layer.  This restores th`, `_resolve_var()`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 7`** (3 nodes): `app()`, `main.py`, `Minimal ForgeGate CLI compatibility entry point.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 9`** (2 nodes): `__init__.py`, `ForgeGate CLI package.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 10`** (2 nodes): `__init__.py`, `Core ForgeGate exports.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 11`** (2 nodes): `__init__.py`, `ForgeGate schema package placeholder.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `evaluate` connect `Community 0` to `Community 1`, `Community 5`, `Community 6`?**
  _High betweenness centrality (0.222) - this node is a cross-community bridge._
- **Why does `Reference Gate` connect `Community 0` to `Community 2`?**
  _High betweenness centrality (0.131) - this node is a cross-community bridge._
- **Why does `Evaluation Pipeline` connect `Community 2` to `Community 0`?**
  _High betweenness centrality (0.111) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `evaluate` (e.g. with `Reference Gate` and `DecisionRecord`) actually correct?**
  _`evaluate` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `DecisionRecord` (e.g. with `forgegate evaluate CLI Command` and `evaluate`) actually correct?**
  _`DecisionRecord` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Minimal ForgeGate CLI compatibility entry point.`, `ForgeGate CLI package.`, `Minimal deterministic ForgeGate evaluator compatibility layer.  This restores th` to the rest of the system?**
  _21 weakly-connected nodes found - possible documentation gaps or missing edges._