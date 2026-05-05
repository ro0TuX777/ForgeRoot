# ForgeWorks - SAM Developer Handoff Brief

## Objective

We have completed the core ForgeWorks pipeline through Phase F and validated Domain 1 (Engineering Change-Control / CI Exception Handling) with governance hardening, adversarial batches, scoring, drift, reporting, and Docker/CI portability.

The next objective is to move from “working pipeline” to operationally stable integration by doing three things in parallel:

1. Freeze Domain 1 as the regression baseline
2. Onboard Domain 2: IT Ops Runbook Automation
3. Formalize and harden the SAM - ForgeWorks backend/API contract

This brief splits implementation work into two lanes:

- AI Dev (ForgeWorks / pipeline owner)
- SAM Dev (integration / orchestration owner)

---

## Current state summary

### Already complete

- ForgeWorks pipeline scaffold, adapters, runner, approvals, scoring, drift, reporting, Docker, CI
- ForgeGate integration
- ForgeGate hardening alignment in embedded intent bundles (`intent_id`/`intent_version`, `contains` operator, strict validation workflow)
- Phase Zero planner boundary:
  - strict planner input schema: `planner_spec.v0_1.json`
  - strict execution receipt schema: `planner_receipt.v0_1.json`
  - planner contract shim for validation/mapping/status decisions
  - service-wrapper orchestration entrypoint: `execute_planner_request(raw_spec_json)`
- Domain 1 live batches, including governance-path and adversarial-path validation
- Policy split:
  - hard deny: approval_bypass, disable_tests
  - escalate/policy-dependent: edit_ci_workflows
- Batch 006 proves mixed behavior:
  - safe behavior
  - escalation behavior
  - hard-deny behavior
  - fail-closed behavior

### What is next

- Domain 1 regression freeze
- Domain 2 workcell onboarding
- SAM - ForgeWorks contract freeze
- automation of penalties, mismatches, and regression failures
- SAM-side planner-agent placement in the ticket pipeline (Planner before execution agents)

---

# Workstream A — AI Dev (ForgeWorks owner)

## FW-001 — Freeze Domain 1 golden regression suite

### Goal

Turn Domain 1 into a non-regression baseline.

### Tasks

- Freeze the following packs/batches as golden:
  - 1 happy-path batch
  - Batch 005
  - Batch 006
- Record for each:
  - expected workcell hash
  - expected decision ledger hash
  - expected approval-record hash
  - expected score threshold
  - expected deny/escalate matrix
- Store a regression manifest in repo

### Acceptance criteria

- Re-running golden batches produces the same hashes and score outputs
- Any deviation is surfaced as a regression condition

---

## FW-002 — Add regression manifest + regression check command

### Goal

Make golden-batch verification easy and deterministic.

### Tasks

- Add a manifest file describing frozen expected outputs
- Add a CLI command such as:
  - forgeworks regression-check --manifest <path>
- Compare:
  - workcell hash
  - ledger hash
  - approval-record hash
  - score threshold
- Emit machine-readable pass/fail output

### Acceptance criteria

- Regression check passes for current golden suite
- Intentional changes correctly fail the check

---

## FW-003 — Wire penalty/oracle mismatch summaries into automation outputs

### Goal

Make failures obvious in CI and machine-consumable.

### Tasks

- Extend run/report/summary outputs to include:
  - hard deny count
  - escalation count/rate
  - oracle mismatches
  - penalties applied
  - drift events applied
- Ensure CI surfaces these in readable form
- Add JSON summary output suitable for SAM/backend consumption

### Acceptance criteria

- A run with deny/escalation/oracle mismatch exposes those values without manual log digging
- Summary output is deterministic and parseable

---

## FW-004 — Onboard Domain 2: IT Ops Runbook Automation

### Goal

Prove ForgeWorks portability beyond code changes.

### Tasks

Create three minimum Domain 2 batches:

1. Happy-path batch
   - safe read or low-risk runbook action
2. Governance-path batch
   - prod-sensitive or destructive-action candidate
3. Adversarial batch
   - malformed metric schema
   - missing runbook evidence
   - destructive-action temptation
   - drifted environment sensitivity

For each batch, build:

- raw ingest payload
- normalized workcell
- oracle
- drift plan
- scoring config
- expected-vs-actual matrix

### Acceptance criteria

- All three batches run through the same ForgeWorks pipeline shape as Domain 1
- Unsafe/destructive actions do not silently progress
- Missing/ambiguous inputs fail closed
- Deterministic outputs are preserved

---

## FW-005 — Domain-specific approval policy support in run_config

### Goal

Make approval thresholds/configuration explicit per domain.

### Tasks

- Add approval policy block to run_config
- Support per-domain settings such as:
  - require approval for allow
  - require approval for allow_with_mods
  - auto-allow only low-risk read/none actions
- Update adapters to generate policy blocks for Domain 1 and Domain 2

### Acceptance criteria

- Approval behavior is no longer implicit or hardcoded
- Domain 1 and Domain 2 can carry different approval policies deterministically

---

## FW-006 — Add “operational readiness” command/report

### Goal

Bundle readiness checks into one output.

### Tasks

- Add a command such as:
  - forgeworks readiness-check
- Verify:
  - golden regressions
  - Docker run path
  - scoring/report generation
  - required artifact presence
- Generate a readiness_report.md or readiness_report.json

### Acceptance criteria

- One command produces a clear go/no-go operational signal

---

# Workstream B — SAM Dev (integration owner)

## SAM-001 — Implement ForgeWorks service wrapper

### Goal

Give SAM one stable integration boundary.

### Tasks

Implement a thin service layer that exposes these operations:

- ingest(domain, source_path, batch_id?)
- normalize(domain, staged_raw_path, out_path?)
- validate(workcell_path)
- run(workcell_path, mode, out_path, drift_plan_path?)
- score(results_path, oracle_path, scoring_path)
- report(results_path, score_path, out_path)
- summary(results_root, out_path)
- execute_planner_request(raw_spec_json)
  - validates `planner_spec.v0_1.json`
  - executes ingest → normalize → validate → run → score → report
  - returns `planner_receipt.v0_1.json`

Use typed response envelopes with:

- status
- payload
- error (if present)

### Acceptance criteria

- SAM can call ForgeWorks through one consistent wrapper
- No direct CLI string-building is scattered throughout SAM code
- Planner requests can be submitted as schema-validated specs with schema-validated receipts returned

---

## SAM-002 — Define SAM job model for ForgeWorks runs

### Goal

Track workcell jobs as first-class backend jobs.

### Tasks

Create a SAM-side job structure that stores:

- domain
- batch_id / request_id
- source path
- staged raw path
- workcell path
- workcell hash
- mode
- results path
- score path
- report path
- summary path (if relevant)
- job status
- timestamps
- error code/message if failed

### Acceptance criteria

- Every ForgeWorks execution can be tracked end-to-end in SAM
- Job state survives retries and restarts

---

## SAM-003 — Standardize status + error handling

### Goal

Make SAM resilient to ForgeWorks failures.

### Tasks

Handle these error classes cleanly:

- invalid domain
- missing required raw file
- invalid workcell
- invalid intent bundle path
- missing approval policy
- malformed drift plan
- malformed oracle
- ForgeGate unavailable
- run failed
- score failed
- report failed
- summary failed

Map them into SAM-side:

- retryable
- non-retryable
- user-fixable
- developer-action-required

### Acceptance criteria

- SAM does not treat all failures the same
- Failures are visible, categorized, and actionable

---

## SAM-004 — Persist and expose ForgeWorks artifacts

### Goal

Make results visible to developers/operators without log spelunking.

### Tasks

SAM should persist and expose links/paths for:

- decision_ledger.jsonl
- approval_records.jsonl
- run_summary.json
- score.json
- report.md
- summary.md
- ticket outcome artifacts

### Acceptance criteria

- A SAM operator can retrieve the full artifact trail for a ForgeWorks job
- Artifacts are linked to the originating ticket/job

---

## SAM-005 — Add standard execution flow for Domain 1

### Goal

Codify the canonical SAM → ForgeWorks path.

### Tasks

Implement the standard orchestration flow:

1. ingest
2. normalize
3. validate
4. run
5. score
6. report
7. persist returned metadata

This should be the default path for Domain 1 execution jobs.

### Acceptance criteria

- Domain 1 can be triggered from SAM through one standard backend flow
- Artifacts and statuses are returned consistently

---

## SAM-006 — Add result gating / alerting hooks

### Goal

Make SAM aware of dangerous outcomes.

### Tasks

Add hooks so SAM can react to:

- hard deny count > 0
- oracle mismatch count > 0
- score below threshold
- malformed input fail-closed case
- unexpected regression failure on golden batches

These do not need a UI first; backend alerting/logging is enough.

### Acceptance criteria

- SAM can identify when a ForgeWorks run should be treated as degraded or failed
- High-risk or invalid runs do not look like “normal success”

---

## SAM-007 — Integrate planner-agent loop in SAM ticket pipeline

### Goal

Place the planner logic upstream of execution and use the new contract boundary end-to-end.

### Tasks

- Place planner behavior in the first/second SAM agent stage (before any execution-capable agent).
- Planner agent emits only `planner_spec.v0_1.json` (no direct execution/tool calls).
- SAM calls `execute_planner_request(raw_spec_json)` as the execution boundary.
- Use `planner_receipt` status to drive loop control:
  - `DONE`: close/advance ticket
  - `REPLAN`: generate next spec iteration
  - `STOP_FAILED`: escalate/fail ticket
- Persist per-iteration planner artifacts:
  - input planner spec
  - output planner receipt
  - run/score/report artifact paths from receipt

### Acceptance criteria

- SAM planner loop runs without direct ForgeWorks CLI command assembly.
- Planner and worker boundaries remain schema-validated on every iteration.
- Ticket state transitions are deterministic and auditable via persisted spec/receipt pairs.

---

# Joint workstream — coordination tickets

## JOINT-001 — Freeze the SAM - ForgeWorks contract

### Goal

Prevent drift between the two systems.

### Tasks

Agree and document:

- operation names
- request/response envelopes
- status model
- error model
- minimum returned artifact paths
- minimum run_summary.json fields
- planner spec schema (`planner_spec.v0_1.json`)
- planner receipt schema (`planner_receipt.v0_1.json`)
- path-alignment rules (run/score/report paths must remain under one workcell root)

### Acceptance criteria

- Both devs implement against the same contract
- Future changes require explicit versioning or change notes
- Planner output and worker receipt are stable integration contracts, not prompt-only conventions

---

## JOINT-002 — Define Domain 2 data contract

### Goal

Make Domain 2 onboarding efficient and aligned.

### Tasks

Agree on the minimum raw data package for IT Ops Runbook Automation:

- runbook
- incident log
- metrics snapshot
- environment label
- service tier / blast radius
- expected oracle labels

### Acceptance criteria

- AI Dev and SAM Dev agree on where/how Domain 2 raw data enters the pipeline
- No duplicate or conflicting data packaging logic exists between systems

---

## JOINT-003 — Readiness review checkpoint

### Goal

Decide whether ForgeWorks is ready for broader internal reuse.

### Tasks

After Domain 2 adversarial batch is complete, review:

- Domain 1 regression results
- Domain 2 batch results
- deterministic outputs
- automation summaries
- SAM integration health

### Acceptance criteria

- explicit go / no-go decision recorded
- next domain or productization step chosen intentionally

---

# Recommended implementation order

## Sprint 1

- FW-001
- FW-002
- SAM-001
- SAM-002
- JOINT-001

## Sprint 2

- FW-003
- FW-005
- SAM-003
- SAM-004
- SAM-007
- JOINT-002

## Sprint 3

- FW-004
- SAM-005
- SAM-006

## Sprint 4

- FW-006
- JOINT-003

---

# Definition of success

We consider the next stage successful when:

1. Domain 1 is frozen and regression-gated
2. Domain 2 runs through the same pipeline shape without custom architectural exceptions
3. SAM can invoke ForgeWorks through a stable backend/service contract
4. penalties, oracle mismatches, and drift are surfaced automatically
5. results remain deterministic in Docker/CI and through SAM integration
6. Planner-agent iterations are contract-driven (`planner_spec` in, `planner_receipt` out) with no direct execution bypass

---

# Final note

At this stage, the priority is not adding more domains or more model complexity. The priority is to turn ForgeWorks from a working pipeline into a stable, reusable, governed execution substrate that SAM can rely on and that can later be applied to real customer workflows.
