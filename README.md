<p align="center">
  <img src="https://img.shields.io/badge/ForgeRoot-Governance%20Architecture-0d1117?style=for-the-badge&labelColor=161b22&color=58a6ff" alt="ForgeRoot" />
</p>

<h1 align="center">ForgeRoot</h1>
<h3 align="center">Governance & Assurance Architecture for Agentic Harnesses</h3>

<p align="center">
  <img src="https://img.shields.io/badge/status-Phase%202%20Prototyping-blue?style=flat-square" />
  <img src="https://img.shields.io/badge/license-Proprietary-red?style=flat-square" />
  <img src="https://img.shields.io/badge/architecture-Full--Stack%20Assurance-green?style=flat-square" />
  <img src="https://img.shields.io/badge/governance-Deterministic-purple?style=flat-square" />
</p>

---

## Overview

As AI systems evolve from advisory copilots into **autonomous engineering participants**, the central challenge is no longer capability alone — it is **control**.

**ForgeRoot** is the umbrella governance and assurance architecture for agentic harnesses. It unifies a set of specialized frameworks into one coordinated lifecycle that governs autonomous engineering action from intent admission to final verdict.

Rather than trusting a single model prompt, monolithic orchestrator, or informal approval process, ForgeRoot decomposes the problem into **hardened control layers**:

> *Intent Admission → Governed Discovery → Deterministic Policy → Sterile Execution → Structural Governance → Behavioral Verification*

The result is a framework for building AI-driven harnesses that are not merely powerful, but **operationally credible** — suitable for enterprise, defense, regulated, and mission-critical environments.

---

## The Problem

Organizations adopting AI-assisted development face six coupled failure modes:

| # | Risk Category | Description |
|---|---|---|
| 1 | **Unbounded Admission** | Agents requesting actions beyond their authorized trust tier, budget, or capability scope |
| 2 | **Discovery Surface** | Low-trust or compromised agents gaining knowledge of sensitive actions they should never discover |
| 3 | **Nondeterministic Governance** | LLMs acting as both proposer and judge — making governance probabilistic and prompt-fragile |
| 4 | **Execution Integrity** | Shared sandboxes creating contamination; cold-start overhead collapsing useful parallelism |
| 5 | **Structural Change** | AI-generated changes creating hidden regressions, ownership ambiguity, or broken dataflow |
| 6 | **Behavioral Verification** | Code that compiles and passes tests but violates performance budgets or security invariants |

Solving only one layer does not produce a trustworthy agentic system. What is required is a **full-stack assurance architecture**.

---

## Core Control Layers

ForgeRoot coordinates six specialized subsystems, each responsible for enforcing one control boundary in the autonomous action lifecycle.

### 1. CONCORD — Admission Pipeline

```
       [Agent Request]
              │
              ▼
  ┌───────────────────────┐  fail
  │ ① Session Validation  ├────────► DENY
  │ ② Action Resolution   │
  │ ③ Trust Gating        ├────────► DENY
  │ ④ Budget Check        │
  │ ⑤ Guard Evaluation    ├────────► DENY
  │ ⑥ Schema Validation   │
  │ ⑦ Idempotency Check   ├────────► DENY
  │ ⑧ Intent Creation     │
  └───────────┬───────────┘
              │ pass
              ▼
   [Intent Admitted to Pipeline]
```

The foundational admission boundary. Maps agent identity to explicit trust tiers, capability scopes, and budget constraints through a **rigid 11-stage fail-fast sequence** with sub-second revocation capabilities.

> *Should this agent, under this identity and budget, be allowed to request this class of action at all?*

### 2. ForgeAtlas — Semantic Capability Discovery

```
    [Agent Task Description]
              │
              ▼
  ┌───────────────────────┐
  │   Semantic Ranking    │   ◄── Embeddings search against catalog
  └───────────┬───────────┘
              │
  ┌───────────▼───────────┐
  │ Trust & Scope Filter  │   ◄── Removes actions above agent's TrustTier
  └───────────┬───────────┘
              │
              ▼
   [Allowed Action Summaries]
```

Governed discovery plane. Agents query capabilities semantically in natural language while a **strict trust invariant** ensures they cannot discover actions they cannot admit — mitigating prompt and action injection attacks.

> *Which actions should this agent even be allowed to know about for this task?*

### 3. ForgeGate — Deterministic Intent Governance

```
  [Proposed Action] + [Signals] + [Budget state]
                        │
                        ▼
            ┌───────────────────────┐
            │ 1. Constraints Check  │
            │ 2. Autonomy Boundaries│
            │ 3. Budget Limits      │
            │ 4. Tradeoff Selection │
            │ 5. Action Shaping     │
            └───────────┬───────────┘
                        │
                        ▼
                [Decision Record]
       (ALLOW | DENY | ESCALATE | MODIFY)
```

The final policy enforcement plane before execution. The model's output is treated as a **proposal only** — evaluated through deterministic constraints, boundaries, and shaping rules to produce a cryptographically identifiable `DecisionRecord`.

> *Given this specific proposed action under current conditions, may execution proceed — and if so, in what form?*

### 4. ForgeHarbor — Warm-Pool Execution Orchestrator

```
        [Pool Target: N Containers]
                     │
  [COLD] ──► [WARMING] ──► [READY] ──► [ASSIGNED] ──► [TERMINATED]
                               │            │
                               └────────────┤
                                            ▼
                                   (Heartbeat Monitor)
                                   Detects crash -> Recycles
```

Runtime substrate for approved agent work. Uses a **warm-pool execution model** with an abstract `EnvironmentProvider` interface — supporting Docker containers, MicroVMs (Firecracker), or Trusted Execution Environments (TEEs) without changes to the orchestrator layer.

> *Where can this action execute quickly, safely, and without contaminating future runs?*

### 5. ForgeScaffold — Structural Change Governance

```
               [Target Codebase]
                       │
         ┌─────────────▼─────────────┐
         │     System Blueprint      │
         │ - Unit/Service Catalog    │
         │ - Dataflow & Maps        │
         │ - Success Contracts       │
         │ - Dark Code Scope (Lyr 2) │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │ Governed Apply Pipeline   │
         │ - Patchset & HITL Review  │
         │ - Sandbox Verification    │
         │ - Immutable Evidence Index│
         └───────────────────────────┘
```

Maps target systems into standardized artifacts — unit inventory, dataflow maps, observability contracts, and success contract matrices — then governs structural changes through an **evidence-bound apply pipeline** with human-in-the-loop approval.

> *How do we mutate this system safely, traceably, and without untracked structural regressions?*

### 6. Azul — Agentic Change Verification

```
                   [Proposed Change]
                           │
       ┌───────────────────▼───────────────────────┐
       │ 1. ANALYZING   (ForgeScaffold scopes)     │
       │ 2. PROVISIONING(ForgeHarbor sandbox)      │
       │ 3. EVALUATING  (ForgeWorks pipelines)     │
       │ 4. COMPREHENSION (Dark Code Layer 3 Gate) │
       │ 5. GATING      (ForgeGate policy)         │
       └───────────────────┬───────────────────────┘
                           │
           [Verdict: PASS / FAIL / WARN_DARK_CODE]
                           │
             Awards XP & Emits Training Pair
```

Top-level verification layer. Forces agents to output a **structured explanation** (`ComprehensionReview`) that must match the codebase mapping from ForgeScaffold — yielding a `WARN_DARK_CODE` verdict if tests pass but human-comprehensible structural intent is absent.

> *Did this proposed change actually preserve safe behavior under controlled evaluation?*

---

## Operational Lifecycle

```
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ Phase 1  │───►│ Phase 2  │───►│ Phase 3  │───►│ Phase 4  │───►│ Phase 5  │───►│ Phase 6  │
  │ Admit    │    │ Discover │    │ Decide   │    │ Execute  │    │ Govern   │    │ Verify   │
  │ CONCORD  │    │ Atlas    │    │ Gate     │    │ Harbor   │    │ Scaffold │    │ Azul     │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

No autonomous action passes directly from model output to production consequence. Every meaningful transition is filtered through an explicit control plane.

| Phase | System | Purpose |
|-------|--------|---------|
| 1. Intent Admission | CONCORD | Validate identity, trust tier, budget, capability scope, schema compliance |
| 2. Governed Discovery | ForgeAtlas | Semantically rank and trust-filter available action options |
| 3. Policy Decision | ForgeGate | Evaluate constraints, autonomy boundaries, budgets — produce deterministic decision |
| 4. Sterile Runtime | ForgeHarbor | Bind task to pre-warmed isolated environment for immediate execution |
| 5. Structural Governance | ForgeScaffold | Analyze blast radius, enforce success contracts, record evidence trail |
| 6. Behavioral Verdict | Azul | Execute change in isolation, evaluate against policy, return formal verdict |

---

## Architecture Doctrines

| Principle | Description |
|-----------|-------------|
| **Governance ≠ Cognition** | LLMs propose; deterministic software governs. Admission, enforcement, and verification are never delegated to language models. |
| **Discovery Is a Security Surface** | An action that cannot be admitted should not be discoverable. Discovery is governed search, not flat metadata lookup. |
| **Execution Is Sterile by Default** | Each task runs in an isolated environment with bounded lifecycle control. Cross-run contamination is an assurance failure. |
| **Mutation Requires Evidence** | Structural changes must be attached to deterministic analysis, review context, and post-apply verification. |
| **Safety Must Be Proven** | Compilation or test passage is insufficient. Safe change requires evaluation against behavioral expectations and operational invariants. |
| **Decisions Must Be Replayable** | Admission receipts, decision records, and evidence indexes make every critical decision auditable and traceable. |

---

## Project Structure

```
ForgeRoot/
├── CONCORD/              # Admission pipeline & governance specification
├── ForgeAtlas/           # Semantic capability discovery engine
├── ForgeGate/            # Deterministic intent governance
├── ForgeHarbor/          # Warm-pool execution environment orchestrator
├── ForgeScaffold/        # Codebase mapping & governed refactoring
├── ForgeCompliance/      # Compliance verification tooling
├── ForgeLedger/          # Governance-native evidence infrastructure
├── Azul/                 # Agentic change verification system
├── DAWN/                 # Execution container runtime
├── LoopLogic/            # Feedback loop & training pair generation
├── Phase9/               # Phase 9 experimental features
├── action_catalogs/      # Tool & action catalog definitions
├── cockpit/              # Operational dashboard & monitoring
├── demo/                 # Demonstration scenarios
├── docs/                 # Extended documentation
├── integrations/         # Third-party integration adapters
├── scripts/              # Utility & setup scripts
├── warden/               # System guardian & remediation agent
└── forge_root_whitepaper_draft.md  # Full architectural whitepaper
```

---

## Use Cases

- **AI-Assisted Refactoring** — Governed review and application of large structural code changes
- **Autonomous Patch Validation** — Safe evaluation of dependency updates, security fixes, and maintenance patches
- **Mission-Critical Change Control** — Deterministic gating and evidence trails for high-assurance environments
- **Enterprise Agent Platforms** — Safe scaling of agents across large action catalogs and sensitive operational surfaces
- **Regulated AI Engineering** — Auditable control layers for privacy, sovereignty, and compliance requirements

---

## Phase 2 Prototyping

ForgeRoot is currently in **Phase 2 Controlled Prototyping**, validating the architecture through four rigorous milestone tests:

| Milestone | Test | Objective |
|-----------|------|-----------|
| **M1** | Kill-Switch Test | Sub-second revocation of a compromised agent via CONCORD mid-task |
| **M2** | Injection Test | ForgeAtlas semantic security against unauthorized discovery via prompt injection |
| **M3** | Comprehension Test | Azul detection of functionally correct but structurally opaque "Dark Code" |
| **M4** | Legacy Shadow Protocol | Auto-Scaffold-Before-Mutate for unmapped legacy codebase resources |

See the [full whitepaper](forge_root_whitepaper_draft.md) for detailed test scenarios and validation criteria.

---

## Documentation

| Document | Description |
|----------|-------------|
| [Whitepaper](forge_root_whitepaper_draft.md) | Full architectural specification with addendums |
| [Frameworks Overview](Forge_Frameworks_Overview.md) | High-level summary of all ForgeRoot frameworks |
| [Master Integration](forge_root_master_integration.md) | Integration guide for deploying ForgeRoot |
| [Control Plane Hardening](Control_Plane_Security_Hardening.md) | Security hardening plan for the orchestration layer |
| [Phase 2 Roadmap](Phase_2_Prototyping_Roadmap.md) | Controlled prototyping milestones and SLAs |
| [Compliance](compliance.md) | Compliance mapping and regulatory alignment |

---

<p align="center">
  <sub>ForgeRoot — Deterministic governance for autonomous engineering action.</sub>
</p>
