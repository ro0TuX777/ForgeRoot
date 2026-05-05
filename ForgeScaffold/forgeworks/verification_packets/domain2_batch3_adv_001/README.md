# Domain 2 Batch 3 — Adversarial (IT Ops Runbook)

This packet captures the adversarial onboarding proof for Domain 2 with deterministic supervised execution.

## What this proves
- Adversarial IT Ops batch runs end-to-end in supervised mode.
- Approval behavior is exercised and recorded.
- Negative/adversarial case fails closed (missing runbook).
- Deterministic outputs across repeated runs.

## Key outputs
- Run summary: artifacts/run_summary.json
- Ledger: artifacts/decision_ledger.jsonl
- Approvals: artifacts/approval_records.jsonl
- Score: artifacts/score.json
- Report: artifacts/report.md
- Expected vs actual: artifacts/expected_vs_actual.*
- Penalty/oracle/drift summary: artifacts/penalty_trigger_summary.*

## Determinism
See determinism/* and determinism/hashes.txt for matching ledger/approval hashes between run and repeat run.

## Negative case
Normalization fails when runbook_service_down.md is missing (artifacts/failure_summary.json + terminal output).

## Readiness
Readiness judgment is recorded in CHECKLIST_COMPLETED.md (PASS).
