ForgeWorks — Developer Context & Domain Onboarding Draft
1. Executive summary

We originally built an agentic team inside SAM that works through a ticket lifecycle. That team proved useful as an internal workflow pattern, but it was too tightly coupled to one system and one use case.

To make the agentic team reusable across other companies and other domains, we needed a way to:

ingest domain-specific data,

normalize it into a consistent structure,

run the same governed workflow repeatedly,

evaluate it offline,

compare behavior across domains,

identify failure modes before production use.

That requirement became ForgeWorks.

ForgeWorks is a terminal-first, Dockerized Workcell T&E pipeline that ingests raw domain data, normalizes it into a canonical workcell format, runs a governed agent workflow through ForgeGate, and emits deterministic ledgers, scores, and reports.

It is not just a benchmark harness. It is also the reference onboarding pipeline for future customer environments.

2. Why we created ForgeWorks
The original problem

SAM’s internal ticket-driven agent team was promising, but there was a scaling problem:

it was designed around our own system,

our own data structures,

our own workflows,

and our own assumptions.

That is not enough if the goal is to reuse the same agentic-team pattern for:

engineering change-control,

IT runbooks,

support triage,

security patching,

procurement/finance exception handling,

or any future customer workflow.

The real blocker

An agent team is not reusable just because the models are reusable.

What actually has to be reusable is:

the data ingestion path,

the ticket/work unit structure,

the governance boundary,

the evaluation method,

and the failure analysis loop.

Without that, every new domain becomes a one-off integration project.

Why ForgeWorks exists

ForgeWorks was created to become:

the test harness for agentic workflows,

the normalization pipeline for domain data,

the offline T&E environment for 4–5 reusable work domains,

and the reference interface that SAM or another backend can call.

3. What a Workcell is

A Workcell is a structured, offline-testable unit of work for a specific domain.

A workcell contains:

tickets,

artifacts,

signals,

a governance policy bundle,

optional oracle expectations,

optional drift plan,

scoring configuration,

and run configuration.

A workcell is the thing ForgeWorks runs.

4. Why we created the Workcell Pack Specification

The Workcell Pack Specification exists because we needed a way to make different domains look structurally the same to the pipeline.

Without a pack specification

Every domain would have:

different raw inputs,

different naming,

different assumptions,

different validation rules,

different reporting shapes.

That would make the system fragile and non-reusable.

With a pack specification

Every domain is compiled into the same canonical shape:

tickets.jsonl

artifact_index.json

signals.jsonl

run_config.json

oracle/expectations.jsonl

drift/drift_plan.json

scoring/scoring.json

intent bundle / governance bundle

That means:

adapters can vary,

domains can vary,

but the execution and evaluation plane stays stable.

In practical terms

The Workcell Pack Specification is the contract between:

raw domain data,

normalized work units,

ForgeGate governance,

the runner,

the scoring engine,

and the report system.

It is what makes the agentic team portable.

5. Relationship between SAM, ForgeGate, and ForgeWorks
SAM

SAM is the agentic team / orchestration pattern:

Scout

Legislator

Builder

Judge

Deployer

It is the behavioral workflow.

ForgeGate

ForgeGate is the governance layer:

evaluates ProposedAction + Signals,

returns DecisionRecord,

enforces boundaries,

supports escalation and approval.

It is the decision boundary.

ForgeWorks

ForgeWorks is the pipeline and T&E harness:

ingests raw domain data,

builds workcells,

runs the workflow,

evaluates results,

injects drift,

produces reports.

It is the offline execution and evaluation environment.

Put simply

SAM = the agent team pattern

ForgeGate = the intent/governance gate

ForgeWorks = the portable domain pipeline + test harness

6. Why this matters for reuse across companies

A company will not care that we have an “agentic team framework.”
They will care that we can:

ingest their data,

map it into a stable work structure,

run a governed workflow,

show measurable outcomes,

and explain failure modes clearly.

ForgeWorks is the system that makes that possible.

It gives us:

a reproducible way to onboard a domain,

a repeatable way to test it offline,

and a safe way to improve it before touching live systems.

7. Recommended initial domains (4–5) that map cleanly to the wedge and are testable offline

The wedge is still strongest in engineering change-control / autonomous maintenance, but the test program should cover adjacent domains that stress different parts of the workflow.

Domain 1 — CI Change-Control / Autonomous Repo Maintenance

Why it fits

Closest to the commercial wedge

Rule-heavy

Clear success criteria

Easy to test offline

Typical tickets

failing tests

lint failures

dependency updates

flaky test quarantine

bounded refactor tickets

Domain 2 — Dependency & Security Patch Workflow

Why it fits

Adjacent to repo maintenance

High value

Strong governance needs

Good for testing risk escalation

Typical tickets

CVE remediation

version bump validation

lockfile updates

patch verification

Domain 3 — IT Ops Runbook Automation

Why it fits

Maps to real operations workflows

Strong branching logic

Good escalation and approval testing

Testable offline with logs/runbooks/metrics snapshots

Typical tickets

disk full

service down

queue lag

restart needed

health-check remediation

Domain 4 — Internal Support / Triage Workflow

Why it fits

Good for routing and escalation logic

Tests classification and “done” ambiguity

Safer if kept internal/offline with no real customer messaging

Typical tickets

classify request

route to correct owner

draft internal resolution note

escalate high-priority/internal risk cases

Domain 5 — Procurement / Finance Exception Handling

Why it fits

Strong decision-tree structure

Good for anomaly detection + routing

Good test bed for threshold, approval, and evidence requirements

Typical tickets

invoice mismatch

vendor mismatch

missing PO reference

threshold approval required

duplicate invoice suspicion

8. What data should we gather for these domains?

This is the critical next step.

Brutal truth: do not start by gathering “everything.”
Gather only what is needed to produce:

tickets,

artifacts,

signals,

and acceptance criteria.

Also, for T&E, each domain needs oracle-style expectations.

8A. Data to gather for CI Change-Control
Raw data

CI logs

test output logs

lint output logs

repo snapshot manifest

failing file/test references

dependency manifest / lockfile snapshots

policy metadata:

forbidden paths

allowed change classes

max file count / max diff size

Needed normalized outputs

tickets:

fix_ci_failure

lint_fix

dependency_patch

artifacts:

logs

repo snapshot refs

config refs

signals:

touches CI config?

touches core paths?

queue pressure

retry count

confidence / verification status

Oracle / expected labels

should escalate?

allowed actions

forbidden actions

must keep tests passing?

acceptable ticket terminal state?

8B. Data to gather for Dependency & Security Patch domain
Raw data

vulnerability advisory exports

dependency tree / lockfile

package version metadata

internal allowlist / denylist policies

test suite summary

repo manifest

Needed normalized outputs

tickets:

security_patch

dependency_upgrade_review

artifacts:

advisory record

lockfile snapshot

repo manifest

signals:

severity

package criticality

major/minor/patch bump class

touches auth/crypto/runtime-critical area?

Oracle / expected labels

allowed upgrade class

should escalate major bumps?

expected approval need

must keep compatibility / tests passing?

8C. Data to gather for IT Ops Runbook domain
Raw data

runbooks

incident logs

metrics snapshots

service inventory

environment classification (staging/prod)

action allowlists

known destructive actions list

Needed normalized outputs

tickets:

service_down

disk_full

queue_lag

latency_high

artifacts:

runbook file

incident log

metrics snapshot

signals:

env

blast radius

service tier

queue pressure

metric values

destructive action candidate?

Oracle / expected labels

should escalate?

safe action class?

disallowed action class?

should remain read-only in this case?

8D. Data to gather for Internal Support / Triage
Raw data

ticket exports

category taxonomy

routing rules

severity definitions

historical resolved examples (sanitized)

internal knowledge snippets / FAQs

policy rules for escalation

Needed normalized outputs

tickets:

classify_and_route

draft_internal_response

artifacts:

ticket text

metadata

routing table

signals:

severity

ambiguity level

missing required info?

priority

user tier (if relevant)

Oracle / expected labels

correct routing team

should escalate?

allowed response class

forbidden response behavior (hallucinated facts, closure without route)

8E. Data to gather for Procurement / Finance Exceptions
Raw data

invoice CSV or JSON exports

PO records

vendor records

approval thresholds

anomaly flags / heuristics

policy rules (e.g. no auto-approval over threshold)

Needed normalized outputs

tickets:

invoice_mismatch

vendor_mismatch

threshold_approval_required

artifacts:

invoice record

PO record

vendor reference

signals:

amount

threshold exceeded?

missing PO?

duplicate suspicion?

known vendor mismatch?

Oracle / expected labels

route only?

escalate?

never auto-approve?

evidence required before closure?

9. Where this data enters ForgeWorks

The pipeline should be documented as:

Step 1 — Raw data arrives

Placed into:

ingest/<domain>/sample_raw/

or in production:

ingest/<domain>/<customer_or_batch_id>/
Step 2 — Ingest

Command:

forgeworks ingest --domain <domain> --source <raw_source> --out <staged_raw>
Step 3 — Normalize

Command:

forgeworks normalize --domain <domain> --raw <staged_raw> --out <workcell_dir>

This creates the canonical workcell pack:

tickets

artifacts

signals

run_config

oracle/drift/scoring refs

Step 4 — Run

Command:

forgeworks run --workcell <workcell_dir> --mode <shadow|supervised|ramped> --out <results_dir>
Step 5 — Score

Command:

forgeworks score --results <results_dir> --oracle <oracle_path> --scoring <scoring_path>
Step 6 — Report

Command:

forgeworks report --results <results_dir> --score <score_json> --out <report_md>
Step 7 — Summary

Command:

forgeworks summary --results-root <dir> --out <summary_md>

This should go into the documentation explicitly because this is the future onboarding path for new domains.