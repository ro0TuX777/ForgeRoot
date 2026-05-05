# ForgeGate Integration Feedback — SAM v2 Relay Architecture

**Submitter:** SAM (Small Agent Model) v2 integration team  
**ForgeGate version tested:** 0.4.0  
**Integration pattern:** Multi-agent, disk-relay pipeline with subprocess and file-write side-effect boundaries  
**Date:** 2026-03-02

---

## Integration Context

SAM v2 uses a 5-phase "Relay" pipeline where LLM agents pass state via serialized JSON/YAML files on disk (to avoid RAM contention between models). ForgeGate was integrated at two critical side-effect boundaries:

1. **Phase 4 — Sandbox Execution**: Governs whether a generated Python test script is permitted to run via `subprocess.run`.
2. **Phase 5 — Deployment**: Governs whether verified sandbox artifacts are permitted to be copied into the main codebase via `shutil.copy2`.

ForgeGate's deterministic, offline-first design made it an excellent fit. The core `evaluate()` API worked cleanly once we understood the intended schema. The friction points below are offered as constructive improvement requests.

---

## Friction Point 1: No DSL — Raw AST JSON is Error-Prone

### What We Expected
Based on the `AI_AGENT_INTEGRATION.md` guide, we initially wrote constraint conditions as natural-language-style strings:

```json
"when": "signal('is_verified') == false"
```

```json
"when": "has_substr(signal('target_directory'), 'sam/core')"
```

### What Actually Happened
The expression evaluator (`expr.py`) only accepts a structured JSON AST dict. The string form is silently treated as a truthy literal, meaning the constraint fires on **every** action regardless of signal values. This caused a `DENY` on all actions including valid ones, with no error or warning in the output.

### Suggested Fix
One or both of the following:

**Option A — Schema validation warning:** If the `when` field is a string and no DSL is supported, `evaluate()` should raise a warning or validation error rather than silently mis-evaluating.

**Option B — Minimal DSL layer:** Even a thin parser that maps `signal('x') == false` → `{"op": "eq", "left": {"var": "signals.x"}, "right": false}` would dramatically reduce integration errors and improve readability of intent files.

---

## Friction Point 2: Missing `contains` / `has_substr` Operator

### What We Needed
We needed to check whether a file path string contained a protected substring (e.g., block deployment into `sam/orchestration`):

```
if target_directory contains "sam/orchestration" → ESCALATE
```

### What Actually Happened
There is no `contains` or `has_substr` operator in `expr.py`. The workaround was to reverse the `in` operator:

```json
{
  "op": "in",
  "left": "sam/orchestration",
  "right": {"var": "signals.target_directory"}
}
```

This works, but is semantically counter-intuitive (`"X" in Y_string` vs `Y_string.contains("X")`), and is easy to get backwards, which produces a silent wrong result rather than an error.

### Suggested Fix
Add a `contains` operator (or alias `has_substr`) to `expr.py`:

```python
if op == "contains":
    return right in left  # left.contains(right)
```

This is the most natural direction for path and string checks, which are very common in governance policies.

---

## Friction Point 3: Unknown Top-Level Key `rules` is Silently Ignored

### What We Did
We initially structured the intent spec using a `"rules"` top-level key (based on reading the `AI_AGENT_INTEGRATION.md` which references "rules" conceptually), instead of the correct `"constraints"` key:

```json
{
  "rules": [
    { "id": "require_verification", "when": "...", "effect": "DENY" }
  ]
}
```

### What Actually Happened
ForgeGate did not raise any error. It evaluated the intent spec, found no `constraints`, `boundaries`, or `budgets`, and returned `ALLOW` by default — silently passing every action including ones that should have been blocked.

### Suggested Fix
Add an **unknown top-level key warning** in `evaluate()` or a `validate_intent_spec()` utility:

```python
KNOWN_KEYS = {"constraints", "boundaries", "budgets", "tradeoffs", "shaping", "actions", ...}
unknown = set(intent_spec.keys()) - KNOWN_KEYS
if unknown:
    warnings.warn(f"Unknown intent_spec keys (will be ignored): {unknown}")
```

This would have surfaced the mistake immediately and saved significant debugging time.

---

## Positive Observations

- The **fail-closed default** (missing signal → `ESCALATE`) is exactly right and worked as documented.
- **Deterministic hashing** (`input_hash`, `decision_id`) in the `DecisionRecord` is a strong feature for our audit ledger use case.
- The **`IntentBundle` structure** is clean and decouples policy from code effectively.
- Offline-first design with no network dependency is a hard requirement for our environment and was satisfied completely.
- The `ToolRouter` adapter pattern is well-conceived; we did not use it in this integration but see clear value for a higher-level abstraction layer in future phases.

---

## Summary Table

| # | Issue | Severity | Suggested Fix |
|---|-------|----------|---------------|
| 1 | String `when` conditions silently mis-evaluate | **High** | Validation warning + optional DSL parser |
| 2 | No `contains`/`has_substr` string operator | **Medium** | Add `contains` op to `expr.py` |
| 3 | Unknown top-level keys silently ignored | **Medium** | Unknown key warning in `evaluate()` |

---

*This feedback is based solely on framework-level integration experience. No proprietary SAM internals are included. Happy to provide reproducible minimal examples for any of the above if useful.*
