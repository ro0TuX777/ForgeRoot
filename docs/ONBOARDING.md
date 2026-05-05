# ForgedRoot — Onboarding Guide

## What Is ForgedRoot?

ForgedRoot is an **agentic change verification and governance framework**. It answers one question before any change reaches production:

> **"Is this change safe?"**

The system is designed for environments where AI agents (or human developers) propose changes to code, operational procedures, or training data. Rather than relying on trust or manual review alone, ForgedRoot runs every proposed change through a deterministic, multi-gate verification pipeline — then records the verdict, awards XP, and emits training data to make the next cycle smarter.

---

## Why It Exists

As AI agents become capable of writing and deploying code autonomously, the risk surface grows proportionally. ForgedRoot was built to:

1. **Enforce governance deterministically** — no LLM makes final security decisions; a rule-based gate engine does.
2. **Scale human oversight** — humans review strategy and policy, not individual change diffs.
3. **Close the improvement loop** — every verification cycle produces evidence that feeds back into better prompts, contracts, policies, and training data.

---

## The Seven Components

| Component | Role |
|-----------|------|
| **Azul** | The primary application. Accepts a proposed change, creates a ticket, runs the full verification pipeline, and returns a verdict. |
| **Warden** | A background daemon that watches a project directory, detects file changes, and continuously triggers scan → assess → stub generation cycles. |
| **Cockpit** | A Streamlit web UI for human operators. Start/stop the Warden, approve stubs, monitor XP, and review decisions. |
| **ForgeGate** | The deterministic governance engine. Evaluates proposed actions against constraints, boundaries, budgets, and tradeoffs. Returns `ALLOW`, `ALLOW_WITH_MODS`, `ESCALATE`, or `DENY`. |
| **ForgeHarbor** | Provisions isolated execution environments (Docker containers or mocks) for shadow-running proposed changes safely. |
| **ForgeAtlas** | Discovers and catalogs available tools and actions that agents can propose, so the governance layer knows what it is governing. |
| **DAWN** | The workflow orchestration engine. Executes deterministic pipelines of self-contained tasks (Links) with contract enforcement and an immutable audit ledger. |

Two additional cross-cutting frameworks:

| Framework | Role |
|-----------|------|
| **CONCORD** | Defines trust tiers (T0–T4), capability sets, budget profiles, and coordination protocols across agents. |
| **LoopLogic** | Specifies the four-stage recursive improvement loop: Execute → Verify → Learn → Improve. |

---

## How a Change Gets Verified

```
Developer / AI Agent proposes a change
           │
           ▼
    Azul creates a Ticket
           │
           ▼
  ForgeScaffold maps blast radius
  (which files, services, and dependencies are affected)
           │
           ▼
  ForgeAtlas discovers available actions
           │
           ▼
  ForgeHarbor provisions a shadow environment
           │
           ▼
  Change runs inside the shadow environment
           │
           ▼
  Evidence collected (logs, behavior traces, test results)
           │
           ▼
  ForgeGate evaluates 5 governance gates:
    1. Constraints (hard deny rules)
    2. Boundaries  (autonomy caps)
    3. Budgets     (resource / risk limits)
    4. Tradeoffs   (branch selection)
    5. Shaping     (allowed-with-modifications)
           │
           ▼
  Verdict: APPROVED / REJECTED / ESCALATED
           │
           ▼
  XP awarded, ReviewBundle saved, Training Pairs emitted
```

---

## How the Warden Fits In

The Warden runs as a background daemon alongside active development. It does not wait for a developer to submit a ticket — it watches the file system and reacts automatically:

```
Watch project directory
       │
       ▼ (file change detected + debounced)
   forge-scan   → identifies risky patterns
   forge-assess → loads risk units into memory
       │
       ▼
  Generate Action Catalog stubs for uncovered risks
       │
       ▼
  Move approved stubs to active/ catalog
       │
       ▼ (repeat forever)
```

Operators approve or reject stubs via the Cockpit UI.

---

## The Improvement Loop

Every verification cycle feeds a four-stage loop:

1. **EXECUTE** — AI Devs or human developers produce work. Each change becomes an Azul ticket.
2. **VERIFY** — Azul runs the full Forge stack and emits: verdicts, ReviewBundles, XP, training pairs.
3. **LEARN** — A Pattern Analyzer reads accumulated evidence and computes metrics:
   - Lead Agreement Rate (approvals without human modification)
   - Reject/Deny rates by type
   - Score distribution trends
   - Failure mode clustering
4. **IMPROVE** — The system updates at four levels: prompts, contracts, policies, training data.

The loop is self-reinforcing: a system that verifies more accurately produces better training data, which produces better models, which verify more accurately.

---

## Key Concepts to Understand First

**Guard Predicate** — A declarative rule attached to an action contract. Example: `args[0] in ['ls', 'git status', 'whoami']`. If a proposed action violates a guard predicate, ForgeGate returns DENY. The rule is the rule.

**Action Catalog** — The set of approved action contracts (under `action_catalogs/active/`). Stubs for newly detected risky patterns land in `action_catalogs/stubs/` until a human approves them.

**DecisionRecord** — The deterministic output of ForgeGate. Includes the decision, all triggered rules, and hashes of the input and decision for replay safety.

**ReviewBundle** — The evidence package produced by a verification run: test results, behavior traces, gate decisions. Stored under `azul_data/`.

**XP** — A quantified score awarded on verified, approved changes. Tracked per developer/agent in `azul_data/xp_ledger.jsonl`.

**ReasoningTrace** — Metadata attached to every LLM response: model used, task tier, reasoning steps, confidence score, raw response path. Enables full audit of AI-assisted decisions.

**Trust Tiers (T0–T4)** — CONCORD's framework for grading agent autonomy. T0 agents require human approval for every action; T4 agents operate fully autonomously within approved budgets.

---

## Where Things Live

```
ForgedRoot/
├── Azul/              # Change verification app (specs + implementation)
├── warden/            # Background daemon (Python)
│   ├── daemon.py      # Main watcher and orchestrator
│   ├── llm_gateway.py # Hybrid LLM routing (local + frontier)
│   └── remediation_agent.py
├── cockpit/           # Streamlit operator UI
├── ForgeGate/         # Deterministic governance engine (Python package)
├── ForgeHarbor/       # Environment provisioning
├── ForgeAtlas/        # Action discovery
├── DAWN/              # Workflow orchestration engine
├── CONCORD/           # Trust and coordination specs
├── LoopLogic/         # Recursive improvement loop specs
├── action_catalogs/
│   ├── active/        # Production guard predicates
│   └── stubs/         # Pending human approval
├── azul_data/
│   ├── tickets/       # Active and completed tickets
│   ├── verdicts/      # Gate evaluation results
│   ├── training_pairs/ # Distillation data
│   └── xp_ledger.jsonl
├── docs/
│   ├── specs/         # Detailed component specifications
│   └── ONBOARDING_LEAD_MANUAL.md  # Operational runbook for verification leads
└── scripts/           # Setup and verification helpers
```

---

## Getting Started

### 1. Set up the environment

```bash
cd /path/to/ForgedRoot
source scripts/setup_env.sh
```

Key environment variables:
- `FORGE_ROOT` — Repository root
- `AZUL_DATA_DIR` — Persistent state directory
- `FRONTIER_PROVIDER` — `anthropic` or `openai`
- `OLLAMA_ENDPOINT` / `VLLM_ENDPOINT` — Local model endpoints (optional)

### 2. Start the Cockpit

```bash
streamlit run cockpit/streamlit_app.py
```

From here you can ignite the Warden, select models, and monitor live state.

### 3. Run a verification manually

```bash
./scripts/azul-verify --diff your.patch --summary "Description of change"
```

### 4. Evaluate a governance decision directly

```bash
forgegate evaluate \
  --intent intent.json \
  --action action.json \
  --signals signals.json
```

---

## Next Steps

- Read `docs/ONBOARDING_LEAD_MANUAL.md` for the operational runbook used by verification leads.
- Read `docs/specs/` for deep dives into each component.
- Read `docs/TECHNICAL.md` for architecture, data flows, and developer reference.
