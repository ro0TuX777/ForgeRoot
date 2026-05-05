# Azul — Core Specification

**Status:** Draft v0.1 — 2026-03-08
**Type:** Application (first Forge-family product)
**Role:** Agentic change verification system
**Depends on:** ForgeWorks, ForgeGate, ForgeScaffold, ForgeAtlas, ForgeHarbor, DAWN, CONCORD
**Deployment:** Docker container (long-running daemon with ticket lifecycle)

---

## 1 — Purpose

Azul is an agentic change verification system. It answers one question: **"Is this change safe?"** before the change takes effect.

A change can be code (PR, refactor, dependency bump), an operational procedure (runbook update), or training data (distillation pairs). Azul takes the proposed change, runs it through a governed behavioral evaluation, and returns a structured verdict with evidence.

Azul is the first application built on top of the Forge framework ecosystem. It orchestrates all seven frameworks/services into a single verification workflow:

| Framework/Service | Role in Azul |
|---|---|
| ForgeScaffold | Maps the structural impact of the change (blast radius, dependencies) |
| ForgeAtlas | Discovers available actions for the verification task |
| ForgeHarbor | Provisions an isolated environment for the shadow run |
| ForgeWorks | Executes the governed behavioral evaluation pipeline |
| ForgeGate | Governs each phase of the pipeline (5 gates per ticket) |
| CONCORD | Coordinates trust, budgets, consistency, and admission |
| DAWN | Executes links inside the ForgeHarbor-provisioned environment |

---

## 2 — Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                              AZUL                                     │
│                  Agentic Change Verification System                    │
│                                                                       │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │  Entry       │  │  Ticket      │  │  Verification │  │  Verdict   │ │
│  │  Adapters    │  │  Lifecycle   │  │  Engine       │  │  & Reward  │ │
│  │              │  │              │  │               │  │            │ │
│  │  CI webhook  │  │  Create      │  │  Spec build   │  │  Gate eval │ │
│  │  CLI         │  │  Track       │  │  Shadow run   │  │  XP award  │ │
│  │  API         │  │  Status      │  │  Evidence     │  │  Training  │ │
│  │  Event       │  │  XP/Reward   │  │  collection   │  │  pair emit │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬────────┘  └─────┬─────┘ │
│         │                 │                  │                  │      │
│         └────────┬────────┘                  │                  │      │
│                  ▼                           ▼                  │      │
│         ┌────────────────┐         ┌─────────────────┐         │      │
│         │ Ticket Store   │         │ Framework        │         │      │
│         │ (persistent)   │         │ Orchestrator     │─────────┘      │
│         └────────────────┘         └────────┬────────┘                │
│                                             │                         │
└─────────────────────────────────────────────┼─────────────────────────┘
                                              │
                              ┌───────────────┼───────────────┐
                              ▼               ▼               ▼
                        ForgeScaffold   ForgeHarbor     ForgeAtlas
                        (blast radius)  (environment)   (tool discovery)
                              │               │               │
                              └───────┬───────┘               │
                                      ▼                       │
                                ForgeWorks                    │
                                (shadow pipeline)             │
                                      │                       │
                                ForgeGate ◀───────────────────┘
                                (phase governance)
                                      │
                                DAWN (execution)
                                      │
                                CONCORD (coordination)
```

Four components inside Azul:

| Component | Responsibility |
|---|---|
| Entry Adapters | Normalize change requests from CI webhooks, CLI, API, or event triggers into Azul tickets |
| Ticket Lifecycle | Persistent ticket tracking with statuses, metadata, and XP reward system |
| Verification Engine | Orchestrates the framework calls: build spec, run shadow pipeline, collect evidence |
| Verdict & Reward | Evaluates gate policy, awards XP, emits training pairs for distillation |

---

## 3 — Use Cases (v1.0)

### 3.1 CI Pipeline Gate

**Trigger:** CI webhook sends a diff/PR reference.
**Flow:** Azul creates a ticket → ForgeScaffold maps blast radius → ForgeHarbor provisions environment → ForgeWorks shadow-runs the change → ReviewBundle returned → gate policy evaluated → CI receives pass/reject with evidence link.
**Domain:** `ci_change_control`
**Mode:** `shadow`

### 3.2 Agent-Proposed Refactors

**Trigger:** Drift scanner or autonomous agent proposes a code fix.
**Flow:** Agent submits diff + target files → Azul creates a ticket → ForgeScaffold identifies dependencies → ForgeWorks evaluates behavioral preservation → ReviewBundle → gate evaluation → if pass, change is applied; if fail, change is rejected with explanation.
**Domain:** `ci_change_control`
**Mode:** `shadow` (v1.0), `supervised` (future for high-risk refactors)

### 3.3 Dependency/Security Patch Verification

**Trigger:** Security advisory or lockfile diff submitted.
**Flow:** Azul creates a ticket with dependency context → ForgeScaffold maps which modules import the affected dependency (blast radius) → ForgeHarbor provisions environment with updated dependency → ForgeWorks runs behavioral tests → ReviewBundle confirms both the security fix and behavioral preservation.
**Domain:** `ci_change_control` (with security-specific oracle)
**Mode:** `shadow`

### 3.4 Domain Policy Compliance

**Trigger:** Operational procedure update submitted (runbook change, deployment checklist revision).
**Flow:** Azul creates a ticket → ForgeWorks ingests the updated procedure as domain work data → governs each step through ForgeGate against policy oracle → ReviewBundle documents compliance status.
**Domain:** `it_ops_runbook`
**Mode:** `shadow` or `supervised`

### 3.5 Distillation Training Gate

**Trigger:** Agent execution produces candidate training pairs.
**Flow:** Each training pair becomes a ticket → ForgeWorks shadow-runs the proposed behavior against oracle expectations → pairs that pass earn XP and enter the training set → pairs that fail are filtered out. ReviewBundle is the provenance record for each training datum.
**Domain:** Configurable per source agent
**Mode:** `shadow`

---

## 4 — Ticket Lifecycle

### 4.1 Ticket entity

```
AzulTicket:
    ticket_id:          str         Unique identifier
    ticket_type:        enum        ci_gate | refactor | security_patch |
                                    policy_compliance | distillation_pair
    status:             enum        See §4.2
    priority:           enum        low | normal | high | critical
    domain:             str         ForgeWorks domain (ci_change_control | it_ops_runbook | ...)
    mode:               str         shadow | supervised | ramped
    
    # Change description
    change_summary:     str         Human-readable description of what's being verified
    change_payload:     dict        Domain-specific: diff, lockfile delta, procedure update, training pair
    source:             dict        Where the change came from (CI, agent, scanner, user)
    target_files:       list        Files/resources affected (if applicable)
    
    # Verification context
    blast_radius:       dict | None ForgeScaffold analysis (populated during verification)
    environment_id:     str | None  ForgeHarbor-assigned environment
    planner_spec:       dict | None Constructed planner spec for ForgeWorks
    
    # Results
    review_bundle:      dict | None ForgeWorks ReviewBundle
    comprehension_review: dict | None Dark Code Layer 3 response (Architectural context)
    gate_result:        dict | None FWResultGate evaluation
    verdict:            str | None  pass | reject | warn
    verdict_reason:     str | None  Human-readable explanation
    
    # Reward
    xp_awarded:         int         XP earned (0 until verdict)
    training_pair:      dict | None Emitted training pair (for distillation use case)
    
    # Metadata
    gate_policy:        dict | None Per-ticket gate policy override
    created_at:         str         ISO-8601
    updated_at:         str         ISO-8601
    completed_at:       str | None  ISO-8601
    metadata:           dict        Extensible key-value store
```

### 4.2 Status machine

```
SUBMITTED ──→ ANALYZING ──→ PROVISIONING ──→ EVALUATING ──→ COMPREHENSION_GATE ──→ GATING ──→ COMPLETED
                                                                                          ──→ REJECTED
                                                                                          ──→ WARNED
                                                                                          ──→ WARNED_DARK_CODE
    │              │              │               │            │
    └──────────────┴──────────────┴───────────────┴────────────┘
                              │
                           FAILED (any stage can fail)
```

| Status | What's happening | Framework active |
|---|---|---|
| SUBMITTED | Ticket created, queued for processing | None |
| ANALYZING | ForgeScaffold mapping blast radius (codebase domains only) | ForgeScaffold |
| PROVISIONING | ForgeHarbor assigning a warm environment | ForgeHarbor |
| EVALUATING | ForgeWorks shadow pipeline running inside the environment | ForgeWorks, ForgeGate, DAWN |
| COMPREHENSION_GATE | Layer 3 check: agent emits structured explanation of state, architecture, & dependency | LLM/Oracle |
| GATING | FWResultGate evaluating the ReviewBundle and ComprehensionReview | Gate logic |
| COMPLETED | Verdict = pass. Change is safe and comprehensible. XP awarded. | None |
| REJECTED | Verdict = reject. Change failed behavioral verification. | None |
| WARNED | Verdict = pass with warnings. Change is safe but flagged. | None |
| WARNED_DARK_CODE | Verdict = pass. Tests perfectly but lacks human comprehension (hidden state, logic leaks). | None |
| FAILED | Pipeline error at any stage. Not a behavioral rejection — an operational failure. | None |

### 4.3 Status transitions

| From | To | Trigger |
|---|---|---|
| SUBMITTED | ANALYZING | Ticket dequeued for processing (codebase domains) |
| SUBMITTED | PROVISIONING | Ticket dequeued (non-codebase domains skip analysis) |
| ANALYZING | PROVISIONING | ForgeScaffold analysis complete |
| ANALYZING | FAILED | ForgeScaffold error |
| PROVISIONING | EVALUATING | ForgeHarbor environment assigned |
| PROVISIONING | FAILED | ForgeHarbor ENVIRONMENT_UNAVAILABLE (after retries) |
| EVALUATING | COMPREHENSION_GATE | ForgeWorks pipeline complete, ReviewBundle returned |
| EVALUATING | FAILED | ForgeWorks pipeline error (not a behavioral rejection) |
| COMPREHENSION_GATE | GATING | ComprehensionReview generated |
| GATING | COMPLETED | Gate verdict = pass |
| GATING | REJECTED | Gate verdict = reject (behavioral failure) |
| GATING | WARNED | Gate verdict = pass with warnings |
| GATING | WARNED_DARK_CODE | Tests pass but Comprehension Gate fails |
| Any | FAILED | Unrecoverable error |

---

## 5 — Verification Engine

The core of Azul — orchestrates the framework calls for each ticket.

### 5.1 Verification flow

```python
def verify(ticket: AzulTicket) -> AzulTicket:
    """
    Full verification pipeline for one ticket.
    Updates ticket status as it progresses.
    """
    
    # 1. ANALYZING — blast radius (codebase domains only)
    if ticket.domain in CODEBASE_DOMAINS:
        ticket.status = ANALYZING
        ticket.blast_radius = forge_scaffold_analyze(ticket.target_files)
    
    # 2. PROVISIONING — get an execution environment
    ticket.status = PROVISIONING
    env = forge_harbor_request(ticket.ticket_id)
    ticket.environment_id = env.environment_id
    
    # 3. Build planner spec (follows _build_planner_spec pattern from SAM)
    ticket.planner_spec = build_verification_spec(ticket)
    
    # 4. EVALUATING — run ForgeWorks shadow pipeline
    ticket.status = EVALUATING
    receipt = execute_planner_request(ticket.planner_spec)
    ticket.review_bundle = receipt.get("review_bundle")
    
    # 5. Release environment
    forge_harbor_release(ticket.environment_id)
    
    # 6. COMPREHENSION GATE (Dark Code Layer 3)
    ticket.status = COMPREHENSION_GATE
    ticket.comprehension_review = evaluate_comprehension(ticket.planner_spec, ticket.review_bundle)
    
    # 7. GATING — evaluate against gate policy
    ticket.status = GATING
    gate_result = fw_result_gate.evaluate(
        ticket.review_bundle, 
        ticket.comprehension_review,
        policy=ticket.gate_policy or DEFAULT_GATE_POLICY
    )
    ticket.gate_result = gate_result
    
    # 8. Verdict
    if gate_result.severity == "critical":
        ticket.status = REJECTED
        ticket.verdict = "reject"
    elif gate_result.severity == "dark_code":
        ticket.status = WARNED_DARK_CODE
        ticket.verdict = "pass"
    elif gate_result.severity == "warn":
        ticket.status = WARNED
        ticket.verdict = "pass"
    else:
        ticket.status = COMPLETED
        ticket.verdict = "pass"
    
    # 9. Reward
    if ticket.verdict == "pass":
        ticket.xp_awarded = calculate_xp(ticket)
        if ticket.ticket_type == "distillation_pair":
            ticket.training_pair = emit_training_pair(ticket)
    
    ticket.completed_at = now()
    return ticket
```

### 5.2 Spec builder

Follows the `_build_planner_spec()` pattern extracted from SAM's `forge_planner_agent.py`:

```python
def build_verification_spec(ticket: AzulTicket) -> dict:
    return {
        "schema_version": "0.1",
        "spec_id": f"azul-{ticket.ticket_id}-v1",
        "request_id": ticket.ticket_id,
        "goal": ticket.change_summary,
        "domain": ticket.domain,
        "mode": ticket.mode,
        "source": build_source_block(ticket),
        "workcell": {"out_path": f"results/azul/{ticket.ticket_id}/workcell"},
        "run": {"out_path": f"results/azul/{ticket.ticket_id}/run"},
        "score": {
            "oracle_path": resolve_oracle_path(ticket.domain),
            "scoring_path": resolve_scoring_path(ticket.domain),
        },
        "report": {"out_path": f"results/azul/{ticket.ticket_id}/report"},
        "loop_policy": ticket.metadata.get("loop_policy", DEFAULT_LOOP_POLICY),
    }
```

### 5.3 Gate policy (extracted from SAM's FWResultGate)

```python
DEFAULT_GATE_POLICY = {
    "min_score":            70.0,   # CRITICAL if below
    "warn_score":           80.0,   # WARN if below (but >= min_score)
    "max_deny_count":       0,      # WARN if > 0
    "max_oracle_mismatch":  0,      # WARN if > 0
    "max_escalation_count": 2,      # WARN if > 2
    "require_pass_fail":    True,   # CRITICAL if pass_fail=False
}
```

Gate policy is overridable per-ticket via `ticket.gate_policy` and per-domain via configuration.

---

## 6 — XP and Reward System

### 6.1 XP calculation

XP is awarded when a ticket reaches COMPLETED or WARNED status. The base calculation:

```python
def calculate_xp(ticket: AzulTicket) -> int:
    base_xp = XP_BY_TYPE[ticket.ticket_type]     # e.g., ci_gate=10, refactor=15, distillation=5
    score_bonus = int(ticket.review_bundle["metrics"]["total_score"] / 10)
    risk_multiplier = RISK_MULTIPLIERS[ticket.priority]  # low=1.0, normal=1.0, high=1.5, critical=2.0
    return int(base_xp * risk_multiplier + score_bonus)
```

### 6.2 Training pair emission (distillation use case)

When a distillation_pair ticket passes verification:

```python
def emit_training_pair(ticket: AzulTicket) -> dict:
    return {
        "pair_id": f"tp-{ticket.ticket_id}",
        "input": ticket.change_payload["input"],
        "output": ticket.change_payload["output"],
        "verification_score": ticket.review_bundle["metrics"]["total_score"],
        "verification_bundle_id": ticket.review_bundle["bundle_id"],
        "xp_awarded": ticket.xp_awarded,
        "domain": ticket.domain,
        "verified_at": ticket.completed_at,
    }
```

Training pairs that fail verification (ticket REJECTED) are not emitted. The ReviewBundle documents why they failed, creating a negative-example record for future training improvement.

---

## 7 — Entry Adapters

Each use case has an entry adapter that normalizes its trigger into an AzulTicket.

### 7.1 CI Webhook Adapter

```
Input:  POST payload with repo, branch, diff_url, commit_sha
Output: AzulTicket(ticket_type="ci_gate", domain="ci_change_control", 
        change_payload={"diff": fetched_diff, "commit": sha}, 
        target_files=files_changed)
```

### 7.2 CLI Adapter

```
Input:  azul verify --diff path/to/patch.diff --domain ci_change_control
Output: AzulTicket(ticket_type="refactor", domain=specified, 
        change_payload={"diff": file_contents},
        target_files=extracted_from_diff)
```

### 7.3 Agent/API Adapter

```
Input:  JSON payload via importlib call (Pattern 1) or API
Output: AzulTicket(ticket_type=specified, domain=specified, 
        change_payload=provided, target_files=provided)
```

### 7.4 Event/Scanner Adapter

```
Input:  Drift scanner or security advisory event
Output: AzulTicket(ticket_type="refactor" or "security_patch", 
        domain="ci_change_control",
        change_payload={"advisory": advisory_data, "proposed_fix": diff},
        target_files=affected_files)
```

### 7.5 Distillation Adapter

```
Input:  Training pair candidate from agent execution
Output: AzulTicket(ticket_type="distillation_pair", domain=source_domain,
        change_payload={"input": prompt, "output": completion},
        target_files=[])
```

---

## 8 — Persistent Storage

### 8.1 Ticket store

Azul stores tickets as JSON files in a persistent directory:

```
azul_data/
├── tickets/
│   ├── active/
│   │   └── <ticket_id>.json
│   └── completed/
│       └── <ticket_id>.json
├── verdicts/
│   └── <ticket_id>_verdict.json     (gate result + ReviewBundle reference)
├── training_pairs/
│   └── <pair_id>.json               (verified distillation pairs)
├── xp_ledger.jsonl                  (append-only XP awards)
└── config/
    ├── gate_policies/
    │   ├── default.yaml
    │   ├── ci_change_control.yaml
    │   └── it_ops_runbook.yaml
    └── domain_config.yaml           (oracle paths, scoring paths, mode defaults)
```

### 8.2 XP ledger

Append-only JSONL file recording every XP award:

```json
{"ticket_id": "azul-001", "xp": 25, "ticket_type": "ci_gate", "domain": "ci_change_control", "score": 91.5, "timestamp": "2026-03-08T10:00:00Z"}
```

---

## 9 — Service Interface

Azul is a long-running daemon (like ForgeHarbor) with caller-facing functions:

```python
def submit(change: dict) -> dict:
    """Submit a change for verification. Returns ticket_id."""

def get_ticket(ticket_id: str) -> dict:
    """Query ticket status and results."""

def get_verdict(ticket_id: str) -> dict:
    """Get the verification verdict with ReviewBundle reference."""

def list_tickets(status: str | None = None, ticket_type: str | None = None) -> dict:
    """List tickets with optional filters."""

def get_xp_summary() -> dict:
    """XP totals by domain, ticket type, and time window."""

def get_training_pairs(domain: str | None = None, min_score: float | None = None) -> dict:
    """Retrieve verified training pairs for distillation."""

def health() -> dict:
    """Service health: ticket queue depth, framework connectivity, uptime."""
```

All functions return `_ok/_error` envelopes.

---

## 10 — Framework Integration Points

| Integration | Call pattern | When |
|---|---|---|
| ForgeScaffold | importlib (Pattern 1) | ANALYZING stage — blast radius analysis |
| ForgeHarbor | daemon function call | PROVISIONING stage — request/release environment |
| ForgeAtlas | importlib (Pattern 1) | EVALUATING stage — discover available actions for the verification task |
| ForgeWorks | importlib (Pattern 1) via `execute_planner_request()` | EVALUATING stage — full shadow pipeline |
| ForgeGate | Called internally by ForgeWorks (5x per ticket) | During ForgeWorks pipeline execution |
| CONCORD | Admission and coordination layer | Throughout — trust, budgets, session management |
| DAWN | Execution engine inside ForgeHarbor container | During ForgeWorks pipeline execution |
| FWResultGate | Direct function call (extracted from SAM) | GATING stage — verdict evaluation |

---

## 11 — What Azul Must NOT Do

| Out of scope | Reason |
|---|---|
| Apply changes to production | Azul verifies changes. Applying them is the caller's responsibility based on the verdict. |
| Manage source code repositories | Azul receives diffs/payloads. It doesn't clone repos or manage branches. |
| Replace ForgeWorks | Azul orchestrates ForgeWorks. It doesn't duplicate the pipeline. |
| Replace ForgeGate | Governance happens inside ForgeWorks. Azul reads the results. |
| Replace CONCORD | Azul uses CONCORD for coordination. It doesn't reimplementadmission. |
| Serve as a general-purpose ticket system | Azul tickets are verification requests, not work items. The ticket lifecycle is optimized for the verify→verdict flow. |

---

## 12 — Configuration

### 12.1 Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `AZUL_DATA_DIR` | `./azul_data` | Persistent storage root |
| `AZUL_DEFAULT_MODE` | `shadow` | Default ForgeWorks run mode |
| `AZUL_DEFAULT_DOMAIN` | `ci_change_control` | Default domain for unspecified tickets |
| `AZUL_QUEUE_WORKERS` | `3` | Concurrent verification workers |
| `AZUL_FORGEWORKS_TIMEOUT_MS` | `300000` | Max time for ForgeWorks pipeline per ticket |
| `AZUL_FORGE_HARBOR_ENABLED` | `true` | Whether to provision environments (false = use local execution) |
| `AZUL_FORGE_SCAFFOLD_ENABLED` | `true` | Whether to run blast radius analysis |
| `AZUL_TRAINING_PAIR_EMISSION` | `true` | Whether to emit verified training pairs |
| `LOG_LEVEL` | `INFO` | Service log level |

---

*End of core specification. Azul is the first Forge-family application — an agentic change verification system that orchestrates all seven frameworks into a submit→verify→verdict workflow with XP rewards and training pair emission.*
