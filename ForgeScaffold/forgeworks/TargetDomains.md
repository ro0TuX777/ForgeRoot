goal is:

portable proof,

market relevance,

offline testability,

and clean product positioning,

then the best first two are:

Pairing A — strongest recommendation

Engineering Change-Control / CI Exception Handling

IT Ops Runbook Automation

This pairing is broad enough to matter and narrow enough to execute.

What this says to the market

With those two domains, your story becomes:

“We built a governed agentic workflow that can safely handle both engineering change-control and operational runbook work, offline and with deterministic approvals, scoring, and drift testing.”

---

# Domain Requirements (Minimum Viable Test Pack)

These are the **minimum inputs and normalized outputs** required to run a batch test through ForgeWorks end‑to‑end. Keep them small, deterministic, and adversarial.

## Engineering Change‑Control / CI Exception Handling

**Raw ingest (required)**
- `ci_log_01.txt`
- `failing_tests.json`
- `repo_snapshot_manifest.json`
- `policy.json`
- `metadata.json`

**Normalized workcell (required)**
- `tickets.jsonl` (1+ tickets)
- `artifact_index.json`
- `signals.jsonl`
- `run_config.json`
- `oracle/expectations.jsonl`
- `drift/drift_plan.json`
- `scoring/scoring.json`

**Signal keys (minimum)**
- `queue.pressure`
- `echo.fidelity`
- `retry.count`
- `change.touches_ci_config`
- `change.touches_core_paths`
- `spec.present`

**Oracle expectations (minimum)**
- `should_escalate`
- `allowed_action_classes`
- `forbidden_actions`
- `must_keep_tests_passing`

**Drift events (minimum)**
- `queue_pressure_spike`
- `policy_change`

**Adversarial cases to include**
- core path touch (should escalate / require approval)
- test‑disable temptation (should deny)
- CI workflow edit temptation (should deny or escalate)
- drift‑sensitive case (behavior changes under pressure)

## IT Ops Runbook Automation

**Raw ingest (required)**
- `runbook_service_down.md`
- `incident_log_01.txt`
- `metrics_snapshot.json`
- `metadata.json`

**Normalized workcell (required)**
- `tickets.jsonl` (1+ tickets)
- `artifact_index.json`
- `signals.jsonl`
- `run_config.json`
- `oracle/expectations.jsonl`
- `drift/drift_plan.json`
- `scoring/scoring.json`

**Signal keys (minimum)**
- `queue.pressure`
- `echo.fidelity`
- `retry.count`
- `env`
- `blast_radius`
- `service.tier`
- `runbook.present`

**Oracle expectations (minimum)**
- `should_escalate`
- `allowed_action_classes`
- `forbidden_actions`

**Drift events (minimum)**
- `metric_schema_change`
- `tool_version_bump`

**Adversarial cases to include**
- unsafe action temptation (should deny)
- high blast radius (should escalate)
- drifted metrics schema (should alter behavior deterministically)
