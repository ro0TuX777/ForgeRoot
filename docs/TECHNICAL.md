# ForgedRoot — Technical Reference

## Stack at a Glance

| Layer | Technology |
|-------|-----------|
| Core language | Python 3.10+ (3.11+ for ForgeGate) |
| Schema validation | Pydantic v2.6+ |
| CLI tooling | Typer + Rich |
| Operator UI | Streamlit |
| Workflow engine | DAWN (custom, FastAPI backend) |
| LLM inference | vLLM / Ollama (local) + OpenAI / Anthropic (frontier) |
| Containerization | Docker (ForgeHarbor environments) |
| Persistence | JSON / JSONL flat files |
| Testing | pytest |

---

## Component Architecture

### Warden (`warden/`)

The central background service. Three modules:

#### `daemon.py` (~1,559 lines)

Entry point: `FederationWarden.run_forever()`

Responsibilities:
- File system watcher with configurable debounce (avoids re-triggering on rapid saves)
- Orchestrates the three-phase scan loop:
  1. `forge-scan` — static analysis of changed files, produces risk JSON
  2. `forge-assess` — loads risk units into in-memory danger map
  3. Stub generation — for each uncovered risk, writes an action contract stub to `action_catalogs/stubs/`
- Manages daemon lifecycle: PID file, signal handling (`SIGTERM`/`SIGINT`), startup recovery from prior state
- Writes status JSON and appends to an event ledger on every cycle
- Calls `llm_gateway.py` for LLM-assisted assessment steps

Start the daemon:
```bash
python -m warden.daemon \
  --forge-root /path/to/ForgedRoot \
  --project-root /path/to/watched/project \
  --project-id my-project
```

State files written to `warden/state/`:
- `daemon.pid` — process ID
- `daemon_status.json` — current health snapshot
- `event_ledger.jsonl` — append-only event log

#### `llm_gateway.py` (~761 lines)

A hybrid LLM routing layer that abstracts local and frontier providers behind a unified interface.

**Task tiers** (each maps to a different model selection strategy):

| Tier | Constant | Use |
|------|----------|-----|
| Lightweight scan | `TIER_SCAN` | Pattern matching, quick triage |
| Governance verdict | `TIER_VERDICT` | Structured decision output |
| Deep reasoning | `TIER_REASONING` | Complex multi-step analysis |

**Provider fallback order** (configurable via env vars):
```
LLM_SCAN_ORDER=ollama,frontier,vllm
LLM_VERDICT_ORDER=frontier,ollama,vllm
LLM_REASONING_ORDER=frontier,vllm,ollama
```

Every response is wrapped in a `ReasoningTrace`:
```python
@dataclass
class ReasoningTrace:
    model: str
    task_tier: str
    reasoning_steps: list[str]
    confidence_score: float
    raw_response_path: str   # path to saved raw LLM output for audit
```

Additional capabilities: embedding generation, OCR tasks, provider health checks with automatic skip on timeout.

#### `remediation_agent.py` (~325 lines)

Generates remediation plans and patches in response to a REJECT verdict.

Flow:
```
Azul verdict (REJECT) → build impact map from catalogs + danger map
                       → prompt LLM for remediation plan
                       → extract patch from LLM response
                       → emit DraftArtifact
```

`DraftArtifact` schema:
```python
@dataclass
class DraftArtifact:
    plan: str           # Human-readable remediation steps
    patch: str          # Proposed code/config diff
    trace: ReasoningTrace
```

The agent iterates against Azul verdict feedback until confidence threshold is met or max iterations reached.

---

### ForgeGate (`ForgeGate/`)

**Package entry point:** `forgegate.cli.main:app`
**Python requirement:** >=3.11
**Key dependency:** Pydantic v2.6, jsonschema>=4.21

The deterministic governance engine. No LLM is involved in ForgeGate decisions — all evaluation is rule-based.

#### Input schemas

```
ProposedAction v0.1
├── action_id: str
├── domain: str
├── unit_id: str
├── args: list
├── kwargs: dict
└── metadata: dict

Signals v0.1
├── risk_tier: int (0–5)
├── blast_radius: str
├── dependency_count: int
└── prior_violations: list[str]

BudgetSnapshot (optional)
├── remaining_cost_units: float
└── ceiling: float
```

#### Evaluation pipeline (deterministic, ordered)

```
1. Constraints  → DENY or ESCALATE if any hard rule triggers
2. Boundaries   → ESCALATE if autonomy cap exceeded for this trust tier
3. Budgets      → ESCALATE or DENY if cost ceiling breached
4. Tradeoffs    → select branch when multiple valid paths exist
5. Shaping      → ALLOW_WITH_MODS if action is allowed with parameter changes
```

All five stages run in order; earlier stages can short-circuit.

#### Output: `DecisionRecord`

```python
@dataclass
class DecisionRecord:
    decision: Literal["ALLOW", "ALLOW_WITH_MODS", "ESCALATE", "DENY"]
    triggered_rules: list[str]   # audit trail of every rule that fired
    input_hash: str              # SHA-256 of serialized inputs
    decision_id: str             # UUID, stable for replay
    modifications: dict          # populated if ALLOW_WITH_MODS
```

`input_hash` + `decision_id` together guarantee replay safety: the same inputs always produce the same `DecisionRecord`.

#### CLI usage

```bash
forgegate evaluate \
  --intent intent.json \
  --action action.json \
  --signals signals.json \
  --output record.json
```

---

### Action Catalogs (`action_catalogs/`)

Guard predicates are written as YAML contract files.

**Stub** (auto-generated, pending approval):
```
action_catalogs/stubs/<domain>__<unit_id>.yaml
```

**Active** (human-approved, enforced by ForgeGate):
```
action_catalogs/active/<domain>__<unit_id>.yaml
```

**Contract schema:**
```yaml
domain: "system_operations"
unit_id: "external.subprocess"
version: "0.1"
actions:
  - id: "check_call"
    description: "Execute a system command via subprocess.check_call"
    guard_predicates:
      - "args[0] in ['ls', 'git status', 'whoami']"
      - "kwargs.get('shell') == False"
    risk_tier: 3
    escalation_threshold: 4
```

Guard predicates are evaluated as Python expressions with the action's `args` and `kwargs` in scope. ForgeGate loads active contracts at startup and re-loads them on SIGHUP.

---

### ForgeHarbor (`ForgeHarbor/`)

Manages a warm pool of isolated execution environments for shadow-running proposed changes.

Key modules:

| Module | Role |
|--------|------|
| `pool_manager.py` | Maintains N warm containers ready for immediate assignment |
| `lifecycle_engine.py` | Provisions (create → configure → assign) and tears down environments |
| `docker_provider.py` | Docker-specific implementation |
| `mock_provider.py` | In-process mock for testing |
| `heartbeat_monitor.py` | Polls container health, evicts dead environments from pool |

**Environment constraints applied at provision time:**
- CPU quota
- Memory limit
- Execution time ceiling
- Write access restricted to allowed paths only (sandbox)

---

### ForgeAtlas (`ForgeAtlas/`)

Discovers and catalogs actions available to agents.

Core service: `ActionDiscovery`

Flow:
1. Introspect tool modules (import + inspect signatures)
2. Extract schema for each callable action
3. Write catalog entries (one per action) for ForgeGate to load as governance targets

Used at startup to ensure the governance layer knows the full action surface before the first proposed change arrives.

---

### DAWN (`DAWN/`)

The workflow orchestration engine underpinning Azul's verification pipeline and the Warden's scan loop.

**Core abstractions:**

**Link** — A self-contained task unit.
```yaml
id: forge-scan
requires:
  - artifact: changed_files
    schema: file_list_v1
produces:
  - artifact: risk_units
    schema: risk_unit_list_v1
timeout_s: 120
sandbox:
  write_paths: [azul_data/]
```

**Pipeline** — An ordered sequence of Links defined in YAML:
```yaml
pipeline: verify-change
links:
  - forge-scaffold
  - forge-harbor-provision
  - forge-shadow-run
  - forge-gate-evaluate
  - forge-bundle
```

**Artifact** — A versioned, schema-validated output. Stored on disk. DAWN refuses to pass an artifact to a downstream Link if schema validation fails.

**Ledger** — Append-only JSONL file. Every Link execution writes one entry:
```json
{
  "ts": "2026-03-14T10:22:01Z",
  "link_id": "forge-scan",
  "pipeline_run": "run-abc123",
  "status": "SUCCESS",
  "artifact_ids": ["risk_units-v1-abc123"]
}
```

**Interfaces:**
- CLI: `python3 -m dawn.runtime.main --project <name> --pipeline <yaml>`
- WebUI: FastAPI backend served at `localhost:8001` (operator console)

---

### CONCORD (Trust & Coordination)

Specification-only (no runtime code); implemented as policy loaded by ForgeGate and the Warden.

**Trust tiers:**

| Tier | Label | Autonomy |
|------|-------|----------|
| T0 | Supervised | Every action requires human approval |
| T1 | Guided | Routine actions auto-approved; novel actions escalated |
| T2 | Collaborative | Escalate only on policy boundary crossings |
| T3 | Delegated | Human reviews outcomes, not individual actions |
| T4 | Autonomous | Operates within approved budgets without real-time oversight |

**BudgetProfile** — Each agent class has a cost ceiling in risk-weighted cost units. ForgeGate checks the `BudgetSnapshot` at evaluation time and escalates when remaining units drop below threshold.

**Saga model** — Long-running multi-step operations are modeled as sagas with:
- Timeout policies per step
- Compensation strategies (rollback actions) if a step fails mid-saga

---

## Data Directory Reference (`azul_data/`)

```
azul_data/
├── tickets/
│   ├── active/           # In-flight tickets (JSON, one file per ticket)
│   └── completed/        # Finished tickets
├── verdicts/             # DecisionRecord outputs per ticket
├── gold_labels/          # Human-curated ground truth labels
├── training_pairs/       # (input, expected_output) pairs for distillation
├── drift_reports/        # Alerts when model behavior drifts from baseline
├── improvement_reports/  # LoopLogic analyzer outputs
├── remediation_desk/
│   ├── pending/          # DraftArtifacts awaiting review
│   ├── reviewed/         # Human-approved remediation plans
│   └── patches/          # Applied patches
├── distillation_batches/ # Batched training data ready for fine-tuning
├── baselines/
│   ├── contracts/        # Baseline contract snapshots
│   └── policies/         # Baseline gate policy snapshots
├── config/
│   └── gate_policies/    # Active policy YAML files loaded by ForgeGate
├── xp_ledger.jsonl       # Append-only XP award log
└── loop_state.json       # Current stage and metadata for LoopLogic
```

---

## Ticket Lifecycle

```
CREATED → SCAFFOLDED → PROVISIONED → SHADOW_RUN → EVIDENCE_COLLECTED
                                                         │
                                             GATE_EVALUATING
                                                         │
                                 ┌───────────────────────┼───────────────────────┐
                             APPROVED                 REJECTED               ESCALATED
                                 │                       │                       │
                           XP awarded           Remediation desk          Human review
                           Training pair        DraftArtifact             queue
                           emitted              generated
```

Ticket JSON written to `azul_data/tickets/active/<ticket-id>.json` on creation, moved to `completed/` on terminal state.

---

## LLM Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `FORGE_ROOT` | Repository root | `/path/to/ForgedRoot` |
| `AZUL_DATA_DIR` | Persistent state root | `/path/to/ForgedRoot/azul_data` |
| `FRONTIER_PROVIDER` | Frontier API provider | `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | API key for Anthropic | `sk-ant-...` |
| `OPENAI_API_KEY` | API key for OpenAI | `sk-...` |
| `OLLAMA_ENDPOINT` | Local Ollama base URL | `http://localhost:11434` |
| `VLLM_ENDPOINT` | Local vLLM base URL | `http://localhost:8000` |
| `OLLAMA_SCAN_MODEL` | Model for TIER_SCAN | `llama3` |
| `OLLAMA_VERDICT_MODEL` | Model for TIER_VERDICT | `mistral` |
| `LLM_SCAN_ORDER` | Provider fallback order | `ollama,frontier,vllm` |
| `LLM_VERDICT_ORDER` | Provider fallback order | `frontier,ollama,vllm` |
| `LLM_REASONING_ORDER` | Provider fallback order | `frontier,vllm,ollama` |

---

## Testing

Test suites live alongside each component:

```
warden/tests/
├── test_daemon.py          # Lifecycle, file watching, state persistence
├── test_llm_gateway.py     # Provider routing, fallback, ReasoningTrace
└── test_remediation.py     # Plan/patch generation, DraftArtifact

ForgeGate/tests/
└── test_gate.py            # Determinism, constraint/boundary/budget evaluation

ForgeHarbor/tests/
└── test_lifecycle.py       # Provision, heartbeat, teardown
```

Run all tests:
```bash
pytest warden/tests/ ForgeGate/tests/ ForgeHarbor/tests/ -v
```

ForgeGate tests verify determinism explicitly: identical `(ProposedAction, Signals, BudgetSnapshot)` inputs must always produce identical `DecisionRecord` outputs across runs and restarts.

---

## Startup Ticket Reconciliation

When the Warden daemon restarts after an ungraceful shutdown (power loss, kill -9, crash), tickets may be stuck in intermediate states in `azul_data/tickets/active/`. Without reconciliation, these tickets remain stuck indefinitely — no verdict is ever issued and the change is never re-evaluated.

`FederationWarden._requeue_stuck_tickets_on_startup()` runs automatically on every daemon start, before the first watch cycle.

### What it detects

Tickets in `PROVISIONING` or `EVALUATING` status in `azul_data/tickets/active/`. These are states that require an active daemon to advance — if the daemon stopped mid-flight, they will never self-resolve.

### What it does

**If the stuck ticket has a `change_payload.diff`:**
1. Fail-closes the stuck ticket: status → `FAILED`, `verdict_reason` records the requeue event, `metadata.manual_review_required = true`
2. Moves the ticket to `azul_data/tickets/completed/`
3. Submits the original diff to `azul-verify` to create a fresh ticket — the change gets a full re-evaluation from scratch
4. Records the old ticket ID and new ticket ID in metadata (`metadata.requeued_ticket_id`) for audit chain continuity

**If the stuck ticket has no diff (data loss scenario):**
1. Fail-closes with `metadata.manual_review_reason = "startup_requeue_missing_diff"`
2. Sets `manual_review_required = true` — flags for human follow-up
3. Does not attempt requeue (nothing to re-evaluate)

### Audit trail

Every reconciliation event is appended to `warden/state/events.jsonl`:

```json
{
  "event": "startup_requeue",
  "message": "Startup reconciliation requeued stuck Azul tickets",
  "data": {
    "count": 2,
    "items": [
      {
        "ticket_id": "azul-abc123",
        "from_status": "EVALUATING",
        "requeued_ticket_id": "azul-def456",
        "requeue_returncode": 0
      }
    ]
  }
}
```

### Implementing the same pattern in another system

The pattern is straightforward to adapt. The three required pieces:

1. **On startup, before main loop:** scan the active ticket store for any ticket in a non-terminal intermediate state
2. **Fail-close the stuck ticket** with a clear audit reason — never leave stuck tickets in active status
3. **Re-submit the work** using the original payload, creating a new ticket with a fresh evaluation

Key design decisions:
- **Fail-close first, requeue second.** Never update a stuck ticket to `QUEUED` in place — this obscures the gap in its history. The old ticket should record that it was abandoned; the new ticket starts clean.
- **Fail-close is unconditional.** Do not try to resume from where the ticket left off. The intermediate state is untrustworthy after an ungraceful shutdown.
- **Missing payload = human review, not silent drop.** If the original work can't be recovered, flag it explicitly rather than discarding silently.

---

## Adding a New Action Contract

1. A stub is auto-generated by the Warden when a new risky pattern is detected. Review it at `action_catalogs/stubs/`.
2. Edit the stub to add or tighten `guard_predicates`.
3. Approve via Cockpit (Warden's Desk tab) or by moving the file manually to `action_catalogs/active/`.
4. Send `SIGHUP` to the Warden process to reload contracts without restart:
   ```bash
   kill -HUP $(cat warden/state/daemon.pid)
   ```

---

## Adding a New DAWN Link

1. Create a Python module implementing the Link interface (see `DAWN/` for examples).
2. Write a YAML descriptor specifying `requires`, `produces`, `timeout_s`, and `sandbox`.
3. Register the Link in the relevant pipeline YAML under `DAWN/pipelines/`.
4. Run the pipeline locally to validate artifact schemas before merging.

---

## SAM Integration: Pull-Sync Spec

ForgedRoot exposes two files for SAM's autonomous learning loop. Both should be synced on the same schedule (recommended: every cycle, or on a scheduled task).

### Gold Labels

| Item | Value |
|---|---|
| Source | `I:\ForgedRoot\azul_data\gold_labels\gold_labels.jsonl` |
| SAM target | `F:\SAM\SmallAgentModel-main\data\forgroot_gold_labels\gold_labels.jsonl` |
| Format | Append-only JSONL, one GoldLabel per line |
| Reader | `sam/evolution/distillation/gold_label_reader.py` |
| Cursor | `F:\SAM\SmallAgentModel-main\data\forgroot_gold_labels\.cursor` — **SAM-local, do not sync** |

Sync command:
```powershell
Copy-Item "I:\ForgedRoot\azul_data\gold_labels\gold_labels.jsonl" `
    "F:\SAM\SmallAgentModel-main\data\forgroot_gold_labels\gold_labels.jsonl"
```

SAM's byte-offset cursor handles incremental reads — copying the full file each sync cycle is safe and does not reset progress.

### Ticket Export (for `verdict_override` triple reconstruction)

ForgedRoot derives ticket summaries from `verdict_override` GoldLabel entries (no separate ticket store).

Generate the export:
```python
from azul.loop.gold_labels import GoldLabelStore
from pathlib import Path

store = GoldLabelStore()
count = store.export_ticket_summaries(
    Path("azul_data/ticket_export/ticket_export.jsonl")
)
```

| Item | Value |
|---|---|
| Source | `I:\ForgedRoot\azul_data\ticket_export\ticket_export.jsonl` |
| SAM target | `F:\SAM\SmallAgentModel-main\data\forgroot_gold_labels\ticket_export.jsonl` |
| Format | JSONL — `{"ticket_id": "...", "change_summary": "..."}` per line |
| Regeneration | Run `export_ticket_summaries()` before each sync cycle |

SAM wires the export into `GoldLabelReader` via:
```python
import json
from pathlib import Path

def _build_ticket_loader(export_path: Path):
    tickets = {}
    if export_path.exists():
        for line in export_path.read_text().splitlines():
            entry = json.loads(line)
            tickets[entry["ticket_id"]] = entry
    return lambda tid: tickets.get(tid)
```

The loader returns `{"ticket_id": "...", "change_summary": "..."}` or `None`. SAM reads `entry.get("change_summary", "")` as the `input_prompt` for distillation triples.

---

## Operational Notes

- **ForgeGate is always synchronous.** It must not call external services or LLMs. If you need LLM input before governance, do it upstream and pass the result in `Signals`.
- **The ledger is append-only.** Never delete or rewrite `event_ledger.jsonl` or `xp_ledger.jsonl`. Archive and rotate if disk space is a concern.
- **Stub approval is a security boundary.** Approving a stub grants agents permission to perform that action class. Review guard predicates carefully before moving to `active/`.
- **Training pairs are valuable.** Every verification cycle that produces a REJECT or ESCALATE with a human-corrected outcome is a free labeled training example. Do not prune `azul_data/training_pairs/` lightly.
