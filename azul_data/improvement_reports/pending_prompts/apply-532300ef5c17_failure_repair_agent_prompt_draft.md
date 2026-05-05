# Prompt Draft: sam/agents/failure_repair_agent.py

**Run ID:** apply-532300ef5c17
**Target file:** `sam/agents/failure_repair_agent.py`
**Rationale:** FailureRepairAgent proposed over-scoped patches in 4 of last 10 cycles, causing unnecessary blast radius. Lead Agreement Rate for repair proposals dropped to 0.58 (threshold: 0.70).

## Proposed Additions

- Before proposing a patch, state the blast radius: which units are directly affected and how many transitive dependents exist.
- Limit patch scope to the minimal set of files required. State explicitly if the repair cannot be contained to a single file.

## Supporting Examples

```
GOOD: 'Patch limited to sam/core/memory.py (1 direct unit, 3 transitive). No external dependency changes required.'
```
```
BAD: 'Refactored memory module and updated all callers.' (over-scoped, blast radius unquantified)
```

---
_Review this draft and apply changes manually to the target file._
_Delete this file once applied or rejected._