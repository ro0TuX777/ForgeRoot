# ForgeWorks — Architecture & Agent Framework

---

## 1. The Three-Layer Mental Model

```
╔══════════════════════════════════════════════════════════════════╗
║                       CALLER LAYER                              ║
║   CLI  ·  SAM orchestrator  ·  GitHub Actions CI/CD             ║
╠══════════════════════════════════════════════════════════════════╣
║                   FORGEWORKS LAYER                              ║
║  Ingest → Normalize → Validate → Run → Score → Report           ║
║                  (the portable T&E pipeline)                    ║
╠══════════════════════════════════════════════════════════════════╣
║        SAM RELAY RUNNER      │       FORGEGATE LAYER            ║
║  Scout→Legislator→Builder    │  evaluate_action()               ║
║  →Judge→Deployer             │  ALLOW / DENY / ESCALATE         ║
║  (the agentic workflow)      │  (the decision boundary)         ║
╠══════════════════════════════════════════════════════════════════╣
║                    CORE ENGINES LAYER                           ║
║  SmartModelSelector → Ollama → reasoning/code/general model     ║
╚══════════════════════════════════════════════════════════════════╝
```

> **SAM** = the agent team pattern
> **ForgeGate** = the intent/governance gate
> **ForgeWorks** = the portable domain pipeline + test harness

---

## 2. System Overview

```mermaid
graph TD
    subgraph EXT["External Callers"]
        CLI["🖥️ CLI\nforgeworks run"]
        SAM_EXT["🤖 SAM\nexternal orchestrator"]
        CI["⚙️ CI/CD\nGitHub Actions"]
    end

    subgraph FW["ForgeWorks — Portable Domain Pipeline + T&E Harness"]
        SW["service_wrapper.py\nexecute_planner_request()"]

        subgraph PIPE["Pipeline Stages"]
            ING["① INGEST\nraw domain data"]
            NRM["② NORMALIZE\ncanonical workcell"]
            VAL["③ VALIDATE\nschema + hash"]
            RUN["④ RUN\nSAM relay runner"]
            SCR["⑤ SCORE\noracle evaluation"]
            RPT["⑥ REPORT\nmarkdown + summary"]
        end

        subgraph ADP["Domain Adapters"]
            CI_ADP["ci_change_control\nadapter"]
            OPS_ADP["it_ops_runbook\nadapter"]
        end
    end

    subgraph RUNNER["SAM-Like Runner — 5-Phase Relay"]
        BATON["RelayBaton\ndisk-flushed state"]
        PH1["Phase 1\n🔍 Scout"]
        PH2["Phase 2\n📜 Legislator"]
        PH3["Phase 3\n🔨 Builder"]
        PH4["Phase 4\n⚖️ Judge"]
        PH5["Phase 5\n🚀 Deployer"]
        PTC["PhaseTransitionController\nVRAM lifecycle"]
        APPR["Approvals\ngated checkpoints"]
        LEDGER["TicketLedger\naudit trail"]
    end

    subgraph FG["ForgeGate — Governance Layer"]
        EVAL["evaluate_action()\nintent + signals → decision"]
        INTENT["Intent Bundles\nsam_sandbox / sam_deploy"]
        DEC["DecisionRecord\nALLOW / DENY / ESCALATE"]
    end

    subgraph CE["Core Engines — LLM Routing"]
        SMS["SmartModelSelector\nquery → model role"]
        MCM["ModelConfigManager\nmodels.conf"]
        OLMA["Ollama API\nhttp://localhost:11434"]
        R_MDL["reasoning_model\nDeepSeek-R1:32b"]
        C_MDL["code_model\nQwen2.5-coder:7b"]
        G_MDL["general_model\nLlama3.2:3b"]
    end

    EXT --> SW
    SW --> ING --> NRM --> VAL --> RUN --> SCR --> RPT
    NRM --> ADP
    RUN --> RUNNER
    RUNNER --> FG
    RUNNER --> CE

    PH1 --> BATON --> PH2 --> BATON
    BATON --> PH3 --> BATON --> PH4 --> BATON --> PH5
    PTC -.->|"unload/load\nper phase"| OLMA
    OLMA --> R_MDL & C_MDL & G_MDL
    SMS --> MCM --> OLMA
    EVAL --> INTENT --> DEC
    DEC -->|"ALLOW → proceed"| APPR
    DEC -->|"DENY → halt"| LEDGER
    DEC -->|"ESCALATE → human"| APPR
```

---

## 3. Full Pipeline Flow

```
  SAM / CLI
     │
     ▼
 execute_planner_request(planner_spec.json)
     │
     │  Gate 1: validate_planner_spec()      ──▶ FAIL → planner_receipt (failure)
     │  Gate 2: path alignment check         ──▶ FAIL → planner_receipt (failure)
     │  Gate 3: ingest()
     │            └─ domain adapter.ingest(raw_source → staged_raw/)
     │  Gate 4: normalize()
     │            └─ domain adapter.normalize(staged_raw → packs/{domain}/)
     │               ┌─ tickets.jsonl
     │               ├─ artifacts.jsonl
     │               └─ signals.jsonl
     │  Gate 5: validate()
     │            └─ jsonschema validation + SHA-256 hash computation
     │  Gate 6: run()
     │            └─ sam_like_runner.run_workcell()
     │               └─ [per ticket] → 5-Phase Relay (see §4)
     │  Gate 7: score()
     │            └─ oracle diff → penalty + total_score + pass/fail
     │  Gate 8: report()
     │            └─ report.md + run_summary.json
     │  Gate 9: build_planner_receipt()
     │
     ▼
  planner_receipt.json  (spec_id, gates_passed, metrics, artifacts)
```

Each gate produces a **structured error receipt** on failure so SAM can handle it programmatically.

---

## 4. The 5-Phase SAM Relay — Per Ticket

```
  ┌──────────────────────────────────────────────────────────────────┐
  │  RelayBaton (disk-flushed JSON — never held in RAM alone)        │
  │  { ticket_id, ticket_intent, current_phase,                      │
  │    hypothesis_path, spec_contract_path, builder_artifact_path,   │
  │    sandbox_directory, judge_verdict_path, phase_timing,          │
  │    retry_count, last_error_log }                                 │
  └──────────────────────────────────────────────────────────────────┘
         │           │           │           │           │
         ▼           ▼           ▼           ▼           ▼

  ╔═══════════╗ ╔═══════════╗ ╔═══════════╗ ╔═══════════╗ ╔═══════════╗
  ║  Phase 1  ║ ║  Phase 2  ║ ║  Phase 3  ║ ║  Phase 4  ║ ║  Phase 5  ║
  ║  SCOUT    ║ ║LEGISLATOR ║ ║  BUILDER  ║ ║   JUDGE   ║ ║ DEPLOYER  ║
  ║           ║ ║           ║ ║           ║ ║           ║ ║           ║
  ║ reasoning ║ ║ reasoning ║ ║   code    ║ ║  no LLM   ║ ║  no LLM   ║
  ║  model    ║ ║  model    ║ ║  model    ║ ║           ║ ║           ║
  ║           ║ ║           ║ ║           ║ ║           ║ ║           ║
  ║ Analyzes  ║ ║ Writes    ║ ║ Generates ║ ║ Runs test ║ ║ Copies    ║
  ║ ticket +  ║ ║ SpecContr ║ ║ artifact  ║ ║ script in ║ ║ verified  ║
  ║ proposes  ║ ║ act YAML  ║ ║ code per  ║ ║ sandbox   ║ ║ artifacts ║
  ║ Validated ║ ║ (rules +  ║ ║ the Spec  ║ ║ → verdict ║ ║ to target ║
  ║ Hypoth.   ║ ║ TDD plan) ║ ║ Contract  ║ ║           ║ ║           ║
  ╚═══════════╝ ╚═══════════╝ ╚═══════════╝ ╚═══════════╝ ╚═══════════╝
        │               │           │             │              │
   ForgeGate       ForgeGate   ForgeGate     ForgeGate      ForgeGate
   evaluate        evaluate    evaluate      sandbox        deploy
   phase.scout     phase.leg.  phase.build   intent         intent
```

**ForgeGate is called before every phase.** The runner only proceeds if the decision is `ALLOW` or
`ALLOW_WITH_MODS`. `DENY` halts the ticket. `ESCALATE` routes to the human approval gate.

---

## 5. 5-Phase Relay Sequence

```mermaid
sequenceDiagram
    participant R as sam_like_runner
    participant PTC as PhaseTransitionController
    participant FG as ForgeGate
    participant APPR as Approvals Gate
    participant BATON as RelayBaton (disk)
    participant LLM as Ollama LLM

    Note over R: Per-ticket loop begins
    R->>FG: evaluate_action(intent, phase.scout)
    FG-->>R: ALLOW / DENY / ESCALATE
    R->>APPR: resolve_approval(mode, policy)
    APPR-->>R: approval outcome

    R->>PTC: transition(None → Phase 1)
    PTC->>LLM: load reasoning_model (DeepSeek-R1)
    R->>LLM: Scout prompt → ValidatedHypothesis
    LLM-->>BATON: flush hypothesis.json
    PTC->>LLM: unload reasoning_model

    R->>FG: evaluate_action(intent, phase.legislator)
    FG-->>R: ALLOW
    R->>PTC: transition(Phase 1 → Phase 2)
    PTC->>LLM: load reasoning_model
    R->>LLM: Legislator prompt → SpecContract
    LLM-->>BATON: flush spec_contract.yaml
    PTC->>LLM: unload reasoning_model

    Note over R: Supervised mode: human gate before Builder
    R->>FG: evaluate_action(intent, phase.builder)
    FG-->>R: ALLOW
    R->>APPR: supervised gate checkpoint
    R->>PTC: transition(Phase 2 → Phase 3)
    PTC->>LLM: load code_model (Qwen2.5-coder)
    R->>LLM: Builder prompt → artifact code
    LLM-->>BATON: flush builder_artifact.py
    PTC->>LLM: unload code_model

    Note over R: Phase 4 & 5 — no LLM, subprocess + ForgeGate only
    R->>FG: evaluate_action(sam_sandbox_intent, sandbox_exec)
    FG-->>R: ALLOW / DENY
    R->>R: Judge: run test_script in sandbox
    BATON-->>R: load judge_verdict.json

    R->>FG: evaluate_action(sam_deploy_intent, deploy)
    FG-->>R: ALLOW / DENY
    R->>R: Deployer: copy artifacts to target
    BATON-->>R: mark ticket DONE

    Note over R: write_ledger / write_run_summary
```

---

## 6. PhaseTransitionController — VRAM Lifecycle

```
  ❌ WRONG (causes GPU stall):
  ┌────────────────────────────────────────────────┐
  │  Phase 1 loads DeepSeek-R1 (32B) ─── still in VRAM ──┐
  │  Phase 3 loads Qwen-coder (8B)  ─── also in VRAM   ──┤
  │                               both fight GPU → hangs  │
  └────────────────────────────────────────────────────────┘

  ✅ CORRECT (PhaseTransitionController enforces):
  ┌────────────────────────────────────────────────────────────────┐
  │  Phase 1 starts                                                │
  │    └─ load  DeepSeek-R1:32b          VRAM: [DeepSeek]         │
  │    └─ run_scout()                                              │
  │    └─ unload DeepSeek-R1             VRAM: []                  │
  │  Phase 2 starts                                                │
  │    └─ load  DeepSeek-R1:32b          VRAM: [DeepSeek]         │
  │    └─ run_legislator()                                         │
  │    └─ unload DeepSeek-R1             VRAM: []                  │
  │  Phase 3 starts                                                │
  │    └─ load  Qwen2.5-coder:7b         VRAM: [Qwen]             │
  │    └─ run_builder()                                            │
  │    └─ unload Qwen2.5-coder           VRAM: []                  │
  │  Phase 4: Judge   — no model needed  VRAM: []                  │
  │  Phase 5: Deployer — no model needed VRAM: []                  │
  └────────────────────────────────────────────────────────────────┘

  Phase → Model Role Mapping:
  ┌──────────┬──────────────────────┬──────────────────────────────┐
  │ Phase    │ Role                 │ Default Model                │
  ├──────────┼──────────────────────┼──────────────────────────────┤
  │ 1 Scout  │ reasoning            │ deepseek-r1:32b              │
  │ 2 Legis. │ reasoning            │ deepseek-r1:32b              │
  │ 3 Build. │ code                 │ qwen2.5-coder:7b             │
  │ 4 Judge  │ (none — subprocess)  │ —                            │
  │ 5 Deploy │ (none — ForgeGate)   │ —                            │
  └──────────┴──────────────────────┴──────────────────────────────┘
```

---

## 7. Approval & Run Modes

```
  ┌────────────────────────────────────────────────────────────────┐
  │                        DECISION FLOW                          │
  │                                                                │
  │  ForgeGate returns:                                            │
  │  ┌─────────────┬──────────────────────────────────────────┐   │
  │  │ ALLOW       │ proceed (approval may auto-pass by mode) │   │
  │  │ ALLOW_MODS  │ proceed with modifications noted         │   │
  │  │ ESCALATE    │ route to human approval gate             │   │
  │  │ DENY        │ halt ticket immediately, log to ledger   │   │
  │  └─────────────┴──────────────────────────────────────────┘   │
  │                                                                │
  │  Run modes affect approval policy:                             │
  │  ┌────────────┬───────────────────────────────────────────┐   │
  │  │ shadow     │ full run, NO side effects, decisions only  │   │
  │  │ supervised │ human gate required before Builder (write) │   │
  │  │ ramped     │ auto-allow low-risk; gate high-risk only   │   │
  │  └────────────┴───────────────────────────────────────────┘   │
  │                                                                │
  │  Hard-deny policies (always blocked regardless of mode):      │
  │    • approval_bypass                                           │
  │    • disable_tests                                             │
  └────────────────────────────────────────────────────────────────┘
```

---

## 8. Component & Module Map

```mermaid
graph LR
    subgraph CLI_SAM["Entry Points"]
        CLI2["forgeworks/cli.py"]
        SVC["forgeworks/sam/service_wrapper.py\nexecute_planner_request()"]
    end

    subgraph ADP2["forgeworks/adapters/"]
        BASE["base.py\nAdapterBase"]
        REG2["registry.py"]
        CI2["ci_change_control/\ningest · normalize · signals"]
        OPS2["it_ops_runbook/\ningest · normalize · signals"]
        BASE --> CI2 & OPS2
        REG2 --> CI2 & OPS2
    end

    subgraph CORE2["forgeworks/core/"]
        VAL2["validate.py"]
        HASH2["hashutil.py"]
        DRIFT2["drift_inject.py"]
        SCORE2["score.py"]
        RPT2["report_md.py"]
        REG3["regression.py"]
        PC["planner_contract.py"]
    end

    subgraph RUNNER2["forgeworks/runner/"]
        SAM_R["sam_like_runner.py\nrun_workcell()"]
        PH["phases/ phase1–5"]
        BATON2["tokio_baton.py\nRelayBaton"]
        TRANS["phase_transition.py\nVRAM lifecycle"]
        FGB["forgegate_bridge.py"]
        APPR2["approvals.py"]
        OUT["outcomes.py"]
        INTENTS["forgegate_intents/\nsam_sandbox · sam_deploy"]
    end

    subgraph CE2["forgeworks/core_engines/"]
        SEL["SmartModelSelector"]
        CFG["ModelConfigManager\nmodels.conf"]
        ENG["model_interface.py\n7 concrete engines"]
    end

    CLI2 & SVC --> ADP2
    SVC --> CORE2
    SVC --> RUNNER2
    SAM_R --> PH --> BATON2
    SAM_R --> TRANS --> CE2
    SAM_R --> FGB --> INTENTS
    SAM_R --> APPR2 & OUT
    SEL --> CFG --> ENG
```

---

## 9. Disk Artifacts Produced Per Run

```
  results/{run_id}/
  ├── decision_ledger.jsonl        ← every ForgeGate decision, hash-chained
  ├── approval_records.jsonl       ← every approval gate outcome
  ├── run_summary.json             ← aggregate metrics + ticket count
  ├── {ticket_id}/
  │   ├── ticket_outcome.json      ← per-ticket result
  │   ├── {ticket_id}_hypothesis.json       (Phase 1 output)
  │   ├── {ticket_id}_spec_contract.yaml    (Phase 2 output)
  │   ├── {ticket_id}_builder_artifact.*   (Phase 3 output)
  │   └── {ticket_id}_relay_baton.json     (live state)
  ├── score.json                   ← oracle diff, penalties, pass/fail
  └── report.md                    ← human-readable markdown report
```

---

## 10. Domain Adapter Pattern

```
  Raw domain data
       │
       ▼
  AdapterBase (forgeworks/adapters/base.py)
  ┌─────────────────────────────────────────────────┐
  │  .ingest(source_path, staged_path)              │
  │  .normalize(staged_path, out_path) → workcell   │
  └─────────────────────────────────────────────────┘
       │                          │
       ▼                          ▼
  ci_change_control/         it_ops_runbook/
  ├── ingest.py               ├── ingest.py
  ├── normalize.py            ├── normalize.py
  └── signals.py              └── signals.py
  (Engineering change         (IT runbook automation
   control / CI exceptions)    steps + signals)

  → Both produce the same canonical workcell schema:
    tickets.jsonl · artifacts.jsonl · signals.jsonl
```

---

## 11. Component Reference Table

| Concern | Owner | Key File |
|---|---|---|
| Entry point / service contract | `service_wrapper.py` | `forgeworks/sam/service_wrapper.py` |
| Domain data ingestion | Domain Adapters | `forgeworks/adapters/{domain}/` |
| Canonical workcell format | Core / validate | `forgeworks/core/validate.py` |
| 5-phase relay execution | SAM-Like Runner | `forgeworks/runner/sam_like_runner.py` |
| Phase state (disk) | RelayBaton | `forgeworks/runner/tokio_baton.py` |
| Phase agent logic | Phase modules | `forgeworks/runner/phases/phase1–5.py` |
| VRAM lifecycle | PhaseTransitionController | `forgeworks/runner/phase_transition.py` |
| Governance / policy | ForgeGate bridge | `forgeworks/runner/forgegate_bridge.py` |
| Approval gating | Approvals | `forgeworks/runner/approvals.py` |
| LLM routing | SmartModelSelector | `forgeworks/core_engines/selection/` |
| Scoring / evaluation | Score + Oracle | `forgeworks/core/score.py` |
| Determinism / audit | Hashutil + Ledger | `forgeworks/core/hashutil.py` |
| Drift / adversarial | Drift inject | `forgeworks/core/drift_inject.py` |

