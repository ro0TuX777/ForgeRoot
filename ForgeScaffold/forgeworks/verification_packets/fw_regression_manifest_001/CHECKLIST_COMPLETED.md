# Verification Checklist — Completed

## A) Scope Completed

- Ticket IDs:
  - FW-001, FW-002 (Domain 1 regression manifest + regression-check)
- Files changed (exact list):
  - forgeworks/cli.py
  - forgeworks/core/regression.py
  - forgeworks/runner/sam_like_runner.py
  - forgeworks/core/score.py
  - forgeworks/core/report_md.py
  - forgeworks/core/summary.py
  - forgeworks/schemas/run_config.v0_1.json
  - forgeworks/adapters/ci_change_control/normalize.py
  - forgeworks/adapters/it_ops_runbook/normalize.py
  - forgeworks/adapters/it_ops_runbook/signals.py
  - docs/OPERATIONAL_READINESS_AND_CONTRACT.md
  - docs/VERIFICATION_CHECKLIST_TEMPLATE.md
  - docs/VERIFICATION_PACKET_TEMPLATE.md
  - regression/manifest.json
- Config/schema changes (exact list):
  - forgeworks/schemas/run_config.v0_1.json
  - regression/manifest.json
- Contract/interface changes (exact list):
  - None (no SAM contract changes)

## B) Acceptance Criteria → Evidence Mapping

| Acceptance criterion | Evidence (path / output) |
|---|---|
| Regression manifest exists | regression/manifest.json |
| Regression check command works | commands/terminal_output.txt (regression-check section) |
| Frozen hashes captured | determinism/ledger_hash.txt, determinism/approval_hash.txt |
| Score threshold captured | determinism/score_hash.txt |

## C) Commands Executed (verbatim)

See commands/commands.txt and commands/terminal_output.txt

## D) Artifacts Produced (required set)

- workcell_hash: artifacts/workcell_hash.txt
- decision_ledger.jsonl: artifacts/test_batch_001/decision_ledger.jsonl, artifacts/test_batch_005/decision_ledger.jsonl, artifacts/test_batch_006/decision_ledger.jsonl
- approval_records.jsonl: artifacts/*/approval_records.jsonl
- run_summary.json: artifacts/*/run_summary.json
- score.json: artifacts/*/score.json
- report.md: artifacts/test_batch_001/report.md, artifacts/test_batch_006/report.md
- expected-vs-actual matrix: artifacts/test_batch_006/expected_vs_actual.md + .json
- penalty summary: artifacts/test_batch_005/penalty_trigger_summary.* and artifacts/test_batch_006/penalty_trigger_summary.*
- drift events applied: artifacts/drift_events.json
- failure summary: artifacts/failure_summary.json

## E) Determinism Proof

- ledger hashes: determinism/ledger_hash.txt
- approval hashes: determinism/approval_hash.txt
- score thresholds: determinism/score_hash.txt
- repeat-run reference: determinism/repeat_run_comparison.txt
- regression proof: determinism/regression_proof.txt

## F) Contract Proof (SAM integration changes)

Not applicable in this milestone. Placeholders:
- contract/*.json

## G) Negative Tests

Not executed in this milestone. Placeholder:
- artifacts/failure_summary.json

## H) Remaining Gaps / Risks

- Regression check not yet wired into CI.
- Domain 2 batches not yet created.

## I) Verification Packet Attached

verification_packets/fw_regression_manifest_001

## J) Readiness Judgment

- Readiness: PASS (for regression manifest + regression-check milestone)
- Rationale:
  - Regression manifest created and validated with regression-check output.
  - Frozen hashes and score thresholds captured.
  - Determinism evidence present in packet.

# SAM Dev Checklist Addendum

Not applicable (no SAM integration changes in this milestone).
