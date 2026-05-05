# Verification Packet Template

Each milestone delivery must include a verification packet folder. This packet is the authoritative evidence bundle.
Mandatory for every delivery:
- checklist completed
- full verification packet
- regression proof if a frozen batch is touched
- lifecycle artifact examples if SAM integration is touched
- explicit PASS/FAIL readiness judgment

## Folder structure (required)

verification_packet/
  README.md
  scope/
    files_changed.txt
    configs_touched.txt
    contracts_touched.txt
  commands/
    commands.txt
    terminal_output.txt
  artifacts/
    workcell_hash.txt
    decision_ledger.jsonl
    approval_records.jsonl
    run_summary.json
    score.json
    report.md
    summary.md
    expected_vs_actual.md
    expected_vs_actual.json
    penalty_trigger_summary.md
    penalty_trigger_summary.json
    drift_events.json
    failure_summary.json
  determinism/
    ledger_hash.txt
    approval_hash.txt
    score_hash.txt
    repeat_run_comparison.txt
    regression_proof.txt
  contract/
    sample_request.json
    sample_response.json
    sample_error.json
    sample_run_summary.json
    sam_job_record.json
    lifecycle_artifacts.json
  notes/
    remaining_gaps.md

## Required filenames and contents

- scope/files_changed.txt: exact file list changed in the milestone
- scope/configs_touched.txt: list of schema/config updates
- scope/contracts_touched.txt: list of API/contract changes
- commands/commands.txt: exact commands in order
- commands/terminal_output.txt: raw output (no edits)
- artifacts/workcell_hash.txt: workcell path + hash
- artifacts/decision_ledger.jsonl: raw ledger (or path if large)
- artifacts/approval_records.jsonl: approvals if applicable (or path if large)
- artifacts/run_summary.json: run summary
- artifacts/score.json: scoring output if applicable
- artifacts/report.md: report if generated
- artifacts/summary.md: cross-run summary if generated
- artifacts/expected_vs_actual.*: expected vs actual matrix
- artifacts/penalty_trigger_summary.*: penalty summary
- artifacts/drift_events.json: drift events applied
- artifacts/failure_summary.json: negative test outputs
- determinism/*.txt: hash comparisons and repeat-run evidence
- determinism/regression_proof.txt: only required when a frozen batch is touched (include manifest, hashes, and pass/fail)
- contract/*: sample envelopes and SAM persistence record
- contract/lifecycle_artifacts.json: required when SAM integration is touched (ExecutionReceipt, VerifiedEvidence, ticket linkage)
- notes/remaining_gaps.md: short, honest list of gaps

## Minimal README.md contents

- milestone name
- date
- owner
- short description of what changed
- pointer to verification checklist used

## Notes

- Use stable ordering and deterministic serialization when applicable.
- If a file is not applicable, include it with a short note explaining why (do not omit silently).
- Keep file contents short and direct; prefer paths if a file is too large.
