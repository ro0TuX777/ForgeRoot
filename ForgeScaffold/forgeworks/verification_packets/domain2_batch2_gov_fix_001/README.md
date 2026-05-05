# Domain 2 Batch 2 — Governance Path Fix Packet

This packet closes the governance-path escalation mismatch by adding an explicit intent constraint and rerunning the batch.

## Root cause
See `root_cause.md` (intent/policy layer missing escalation rule).

## Diff proof
See `intent_spec.diff` (constraint added to intent spec).

## Key artifacts
- Ledger: artifacts/decision_ledger.jsonl
- Approvals: artifacts/approval_records.jsonl
- Run summary: artifacts/run_summary.json
- Score: artifacts/score.json
- Report: artifacts/report.md
- Expected vs actual: artifacts/expected_vs_actual.*
- Penalty/oracle/drift summary: artifacts/penalty_trigger_summary.*

## Determinism
See determinism/* (ledger/approval/score hashes; repeat run match).

## Regression checks
Domain 1 regression suite and Domain 2 batch 1 score pass are recorded in commands/terminal_output.txt.

## Readiness
Checklist marks PASS after fix.
