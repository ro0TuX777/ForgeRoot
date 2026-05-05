# ForgeWorks Verification Checklist Template (Milestone Deliveries)

Use this template for every milestone. It is designed to be auditable and non-ambiguous. Narrative summaries are not accepted without the artifacts below.

Mandatory for every milestone delivery:
- Completed checklist (this file)
- Full verification packet (docs/VERIFICATION_PACKET_TEMPLATE.md)
- Regression proof if any frozen batch is touched
- Lifecycle artifact examples if SAM integration is touched
- Explicit readiness judgment (PASS/FAIL) with rationale

---

## A) Scope Completed

- Ticket IDs:
  - 
- Files changed (exact list):
  - 
- Config/schema changes (exact list):
  - 
- Contract/interface changes (exact list):
  - 

---

## B) Acceptance Criteria → Evidence Mapping

Provide a table mapping each acceptance criterion to a concrete artifact or command output.

| Acceptance criterion | Evidence (path / output) |
|---|---|
|  |  |
|  |  |

---

## C) Commands Executed (verbatim)

List every command in the exact order run, and include raw terminal output.

```
<command>
<terminal output>
```

---

## D) Artifacts Produced (required set)

At minimum, include the following (or explicitly state why not applicable):

- workcell_path
- workcell_hash
- decision_ledger.jsonl
- approval_records.jsonl (if supervised/ramped)
- run_summary.json
- score.json (if scored)
- report.md (if generated)
- summary.md (if cross-run)
- expected-vs-actual matrix
- penalty summary
- drift events applied
- failure summary for negative tests

Provide exact paths and short descriptions.

---

## E) Determinism Proof

Provide at least one repeated-run comparison per frozen batch:

- ledger hash comparison
- approval-record hash comparison
- score hash comparison
- repeat-run output (verbatim or hash)

---

## F) Contract Proof (SAM integration changes)

Include all required envelopes when contract changes are involved:

- sample request envelope
- sample response envelope
- sample error envelope
- sample run_summary.json payload
- sample persisted SAM job record

---

## G) Negative Tests

Provide at least one failure-mode proof (malformed input, missing signals, policy violation, etc.).

Include:

- exact input used
- exact command
- exact error output
- error code classification

---

## H) Remaining Gaps / Risks

Be explicit and short:

- 
- 

---

## I) Verification Packet Attached

Attach the verification packet folder described in docs/VERIFICATION_PACKET_TEMPLATE.md

---

# J) Readiness Judgment

Provide an explicit readiness decision for this milestone:

- Readiness: PASS / FAIL
- Rationale (short, evidence-based):
  - 

---

# SAM Dev Checklist Addendum

Required for SAM-side milestones:

- Wrapper/API proof: function signatures or routes for ingest/normalize/validate/run/score/report/summary
- Sample request/response pairs for each operation
- Failure example for at least 2 error types
- SAM job persistence example (payload with artifact paths and status)
- Ticket lifecycle proof (ExecutionReceipt + VerifiedEvidence)
