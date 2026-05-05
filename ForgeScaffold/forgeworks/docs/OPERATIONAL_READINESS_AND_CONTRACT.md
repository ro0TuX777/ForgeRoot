# ForgeWorks Operational Readiness Plan

## 1. Purpose

This plan defines what must be true before ForgeWorks is treated as an operationally ready component for multi-domain agentic workflow testing and future customer onboarding.

ForgeWorks is no longer just a prototype runner. It now includes:

- domain ingestion and normalization
- governed execution via ForgeGate
- supervised and ramped autonomy
- deterministic scoring
- drift injection
- markdown reporting
- Docker/CI portability
- live adversarial CI batches

The next goal is to move from “it works” to “it is stable, portable, measurable, and safe to reuse.”

## 2. Operational objective

ForgeWorks is considered operationally ready when it can:

- reliably execute a frozen regression suite for Domain 1,
- onboard and validate Domain 2 using the same pipeline contract,
- expose failures through deterministic ledgers, scores, and reports,
- integrate with SAM through a stable backend/API contract,
- fail closed when signals, artifacts, or policy context are incomplete.

## 3. Current status

### Current readiness decision (2026-02-28)

**GO for broader internal reuse.** ForgeWorks has completed regression gating across all accepted Domain 1 and Domain 2 batches, and the SAM wrapper integration path has been verified with truthful failure handling. This GO decision applies to the proven Engineering Change-Control / CI Exception Handling and IT Ops Runbook Automation workflows and their verified SAM-backed execution paths.

### Completed

- ForgeWorks pipeline implemented through Docker/CI
- Workcell Pack Specification established
- ForgeGate integrated into execution flow
- Domain 1 established: Engineering Change-Control / CI Exception Handling
- Governance hardening completed:
  - hard deny for approval_bypass
  - hard deny for disable_tests
  - escalate/policy-dependent for edit_ci_workflows
- Batch 005 validated governance path
- Batch 006 introduced adversarial depth
- scoring, drift, and reporting operational
- SAM wiring to ForgeWorks already exists

### Not yet complete

- External production rollout readiness (not validated)
- Domain 3 selection/onboarding
- Optional: expand regression gating to any future domains before GO

## 4. Readiness pillars

ForgeWorks readiness will be judged across five pillars.

### A. Reproducibility

The same workcell, seed, mode, and policy must produce:

- the same workcell hash
- the same decision ledger hash
- the same approval record hash
- the same score

### B. Governance integrity

Unsafe actions must:

- be denied or escalated correctly
- never silently progress
- be visible in the ledger and report
- influence score deterministically

### C. Domain portability

At least two distinct domains must run through the same pipeline shape:

- Engineering Change-Control / CI Exception Handling
- IT Ops Runbook Automation

### D. Operational integration

SAM must be able to call ForgeWorks through a stable, documented contract and receive:

- paths
- statuses
- summaries
- errors
- artifacts

### E. Failure visibility

ForgeWorks must surface:

- malformed input
- missing signals
- oracle mismatches
- drift effects
- penalty triggers
  without ambiguity.

## 5. Domain readiness strategy

### Domain 1 — Engineering Change-Control / CI Exception Handling

This is the primary wedge and must become the baseline regression domain.

#### Required readiness state

- golden regression batches frozen
- expected score thresholds defined
- expected deny/escalate behavior frozen
- CI/job automation surfaces:
  - hard deny counts
  - oracle mismatches
  - drift events
  - penalty summaries

#### Golden batch recommendation

Freeze at least:

- 1 happy-path batch
- Batch 005 governance-path batch
- Batch 006 adversarial batch

#### Domain 1 exit criteria

Domain 1 is operationally stable when:

- all golden batches are deterministic
- no unsafe allowed progression occurs
- malformed-input cases fail closed
- score regressions trigger automation failure

### Domain 2 — IT Ops Runbook Automation

This is the proof that ForgeWorks is not just for code.

#### Required batch set

Build three minimum workcells:

- happy-path batch
  - safe, read-oriented, low-risk runbook actions
- governance-path batch
  - prod-sensitive or destructive-action candidates requiring escalation
- adversarial batch
  - malformed metric schema
  - missing runbook evidence
  - destructive-action temptation
  - drifted environment sensitivity

#### Domain 2 exit criteria

Domain 2 is operationally stable when:

- the same pipeline contract works without domain-specific hacks
- escalation/approval behavior is deterministic
- destructive-action candidates never silently progress
- drift visibly changes behavior and score

## 6. Non-regression gate policy

ForgeWorks should fail operational validation if any of the following occur in golden batches:

- approval_bypass is allowed
- disable_tests is allowed
- malformed artifact/signal case does not fail closed
- expected escalation is missed
- score falls below domain threshold
- ledger or score becomes nondeterministic without intentional change
- drift event is applied silently or not reflected in reporting

## 7. Automation gating policy

The CI or automation layer should report and optionally fail on:

### Hard fail conditions

- hard-deny class allowed
- missing approval record where required
- oracle expectation missing for any ticket
- malformed workcell enters run instead of failing earlier
- run summary missing required artifact references
- deterministic regression hash unexpectedly changes on frozen golden batch

### Soft fail / warning conditions

- score drops below warning threshold
- escalation rate changes materially
- approval rate changes materially
- drift event count differs from expected
- report generation succeeds but omits required sections

## 8. Readiness milestones

### Milestone 1 — Domain 1 freeze

Deliverables:

- frozen golden batches
- expected hashes
- score thresholds
- automation fail conditions

### Milestone 2 — Domain 2 onboarding

Deliverables:

- three IT Ops batches
- oracle/drift/scoring defined
- deterministic supervised and ramped runs
- report and summary output

### Milestone 3 — Integration freeze

Deliverables:

- SAM ↔ ForgeWorks backend/API contract finalized
- status/error taxonomy frozen
- artifact paths standardized

### Milestone 4 — Portable proof achieved

Deliverables:

- two domains passing readiness criteria
- Docker/CI reproducibility established
- automation summaries wired
- handoff docs for human developer complete

## 9. Required artifacts for readiness review

For each readiness review, collect:

- workcell path
- workcell hash
- decision ledger
- approval records
- run summary
- score.json
- report.md
- summary.md
- expected-vs-actual matrix
- penalty summary
- drift events applied
- error summary for failed cases

## 10. Roles and ownership

### ForgeWorks owner

Responsible for:

- pipeline correctness
- scoring and reporting
- reproducibility
- Docker/CI path

### ForgeGate owner

Responsible for:

- decision semantics
- deny/escalate rules
- approval requirements
- signal/policy compatibility

### SAM owner

Responsible for:

- backend/API call correctness
- job orchestration
- state handling
- artifact path persistence
- upstream input packaging

### Human reviewer / tech lead

Responsible for:

- domain acceptance criteria
- oracle label sanity
- approval policy sanity
- go/no-go readiness decision

## 11. Immediate next actions

- Freeze Domain 1 golden batches
- Define and build Domain 2 minimum three-batch set
- Formalize SAM ↔ ForgeWorks contract
- Wire penalty/oracle mismatch summaries into automation
- Run readiness review after Domain 2 adversarial batch passes

## 12. Readiness decision rule

ForgeWorks should be considered operationally ready for broader internal reuse only when:

- Domain 1 is frozen and regression-gated
- Domain 2 is onboarded and adversarially validated
- the SAM ↔ ForgeWorks contract is documented and stable
- automation surfaces penalty/oracle/drift outcomes
- repeated containerized runs remain deterministic

---

# SAM ↔ ForgeWorks API / Backend Contract Spec

## 1. Purpose

This contract defines how SAM calls ForgeWorks as a backend workcell pipeline.

ForgeWorks should be treated as a separate execution subsystem that owns:

- ingest
- normalize
- validate
- run
- score
- report
- summary

SAM should not reimplement these responsibilities.

## 2. Architectural boundary

### SAM responsibilities

- accept user/system requests
- decide which domain workflow to invoke
- package or point to raw source data
- call ForgeWorks operations
- persist returned job/run metadata
- render or forward results to users/operators

### ForgeWorks responsibilities

- stage raw inputs
- normalize into workcells
- validate workcells
- execute governed runs
- score against oracle
- produce markdown reports and summaries
- return stable status and artifact paths

## 3. Integration style

Preferred order of implementation:

### Phase 1

In-process Python service layer

SAM imports a thin ForgeWorks service wrapper

easiest for local iteration

### Phase 2

Local worker/service boundary

subprocess or job queue invocation

clearer isolation

### Phase 3

HTTP or RPC service

only if needed later for scale/separation

The contract below should work regardless of transport.

## 4. Core operations

### 4.1 Ingest

Intent

Stage raw domain data into ForgeWorks-controlled raw input structure.

Request

{
  "domain": "ci_change_control",
  "source_path": "./ingest/ci_change_control/batch_001",
  "batch_id": "batch_001"
}

Response

{
  "status": "ok",
  "domain": "ci_change_control",
  "batch_id": "batch_001",
  "staged_raw_path": "./ingest/ci_change_control/staged_batch_001"
}

### 4.2 Normalize

Intent

Convert staged raw input into canonical workcell format.

Request

{
  "domain": "ci_change_control",
  "staged_raw_path": "./ingest/ci_change_control/staged_batch_001",
  "out_path": "./packs/ci_change_control/test_batch_001"
}

Response

{
  "status": "ok",
  "domain": "ci_change_control",
  "workcell_path": "./packs/ci_change_control/test_batch_001",
  "workcell_hash": "abc123...",
  "ticket_count": 5,
  "artifact_count": 8,
  "signal_count": 5
}

### 4.3 Validate

Intent

Confirm workcell structure is valid before execution.

Request

{
  "workcell_path": "./packs/ci_change_control/test_batch_001"
}

Response

{
  "status": "ok",
  "workcell_path": "./packs/ci_change_control/test_batch_001",
  "workcell_hash": "abc123...",
  "schemas_checked": ["ticket", "artifact_index", "signals", "run_config"]
}

### 4.4 Run

Intent

Execute the workcell through ForgeWorks runner and ForgeGate.

Request

{
  "workcell_path": "./packs/ci_change_control/test_batch_001",
  "mode": "supervised",
  "out_path": "./results/test_batch_001",
  "drift_plan_path": "./packs/ci_change_control/test_batch_001/drift/drift_plan.json"
}

Response

{
  "status": "ok",
  "workcell_path": "./packs/ci_change_control/test_batch_001",
  "mode": "supervised",
  "results_path": "./results/test_batch_001",
  "run_summary_path": "./results/test_batch_001/run_summary.json",
  "ledger_path": "./results/test_batch_001/decision_ledger.jsonl",
  "approval_records_path": "./results/test_batch_001/approval_records.jsonl",
  "ticket_count": 5,
  "decision_count": 17,
  "approval_count": 14,
  "workcell_hash": "abc123..."
}

### 4.5 Score

Intent

Evaluate run output against oracle and scoring config.

Request

{
  "results_path": "./results/test_batch_001",
  "oracle_path": "./packs/ci_change_control/test_batch_001/oracle/expectations.jsonl",
  "scoring_path": "./packs/ci_change_control/test_batch_001/scoring/scoring.json"
}

Response

{
  "status": "ok",
  "results_path": "./results/test_batch_001",
  "score_path": "./results/test_batch_001/score.json",
  "total_score": 87.5,
  "pass": true,
  "penalty_count": 1
}

### 4.6 Report

Intent

Generate single-run markdown report.

Request

{
  "results_path": "./results/test_batch_001",
  "score_path": "./results/test_batch_001/score.json",
  "out_path": "./results/test_batch_001/report.md"
}

Response

{
  "status": "ok",
  "report_path": "./results/test_batch_001/report.md"
}

### 4.7 Summary

Intent

Generate cross-run markdown summary.

Request

{
  "results_root": "./results",
  "out_path": "./results/summary.md"
}

Response

{
  "status": "ok",
  "summary_path": "./results/summary.md",
  "runs_summarized": 6
}

## 5. Standard status model

Every operation should return one of:

- ok
- failed
- warning

For machine handling, prefer:

- ok
- error

Warnings can be embedded in payloads rather than replacing status.

## 6. Standard error model

SAM must be able to interpret errors cleanly.

Error envelope

{
  "status": "error",
  "error": {
    "code": "MISSING_REQUIRED_RAW_FILE",
    "message": "missing required raw file: failing_tests.json",
    "stage": "normalize",
    "details": {
      "domain": "ci_change_control",
      "path": "/tmp/fw_bad_raw"
    }
  }
}

Recommended error codes

- INVALID_DOMAIN
- MISSING_REQUIRED_RAW_FILE
- INVALID_WORKCELL
- INVALID_INTENT_BUNDLE_PATH
- MISSING_APPROVAL_POLICY
- MALFORMED_DRIFT_PLAN
- MALFORMED_ORACLE
- FORGEGATE_UNAVAILABLE
- RUN_FAILED
- SCORE_FAILED
- REPORT_FAILED
- SUMMARY_FAILED

## 7. Idempotency expectations

### Ingest

Should be idempotent for the same source_path + batch_id unless explicitly overwritten.

### Normalize

Should produce the same workcell hash for the same raw input.

### Validate

Always deterministic.

### Run

Should be deterministic for same:

- workcell
- mode
- seed
- drift plan

### Score / Report / Summary

Should be deterministic given identical inputs.

## 8. Artifact contract

ForgeWorks must return stable artifact paths so SAM can store and display them.

Minimum artifact set after a run:

- decision_ledger.jsonl
- run_summary.json
- tickets/*.json

Additional for supervised/ramped:

- approval_records.jsonl

Additional after scoring/reporting:

- score.json
- report.md

Additional for summary:

- summary.md

## 9. Run summary schema expectations

SAM should assume run_summary.json includes at least:

- run_id
- workcell_path
- mode
- ticket_count
- decision_count
- approval_count
- escalation_count
- escalation_rate
- workcell_hash
- ledger_path
- approval_records_path if applicable
- score_path if scored
- drift_events_applied

## 10. Approval / governance expectations

SAM should not reinterpret ForgeGate results.

ForgeWorks owns:

- decision evaluation
- approval record creation
- deny/escalate semantics
- score penalties related to those outcomes

SAM should consume them as facts.

## 11. Recommended backend wrapper interface

If implemented as Python service methods:

ingest(domain: str, source_path: str, batch_id: str | None = None) -> dict
normalize(domain: str, staged_raw_path: str, out_path: str | None = None) -> dict
validate(workcell_path: str) -> dict
run(workcell_path: str, mode: str, out_path: str, drift_plan_path: str | None = None) -> dict
score(results_path: str, oracle_path: str, scoring_path: str) -> dict
report(results_path: str, score_path: str, out_path: str) -> dict
summary(results_root: str, out_path: str) -> dict

If implemented as HTTP later, preserve the same operation semantics.

## 12. SAM workflow example

Example flow

SAM receives a request to evaluate a CI exception batch.

SAM calls ingest.

SAM calls normalize.

SAM calls validate.

SAM calls run.

SAM calls score.

SAM calls report.

SAM stores or renders:

- report path
- score
- run summary
- artifact links

This is the cleanest reusable pattern.

## 13. Logging and observability expectations

Each ForgeWorks call should log:

- operation
- domain
- workcell path
- batch/run identifier
- status
- artifact outputs
- error code if failed

This is necessary for SAM-side observability and troubleshooting.

## 14. Contract freeze recommendation

Before broadening domains, freeze:

- operation names
- status model
- error model
- minimum artifact paths
- run summary minimum fields

That will prevent SAM and ForgeWorks from drifting apart as each evolves.

## 15. Immediate implementation recommendation

Next practical step:

- implement this contract as a local Python service wrapper
- add typed response envelopes
- run Domain 1 golden batches through it
- then use the same interface for Domain 2 onboarding

That is the safest path.
