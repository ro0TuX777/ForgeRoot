ForgeWorks Phase D: Extraction Walkthrough
What Was Done
SAM's core LLM-execution infrastructure was extracted and transplanted into ForgeWorks. ForgeWorks can now run real LLM-driven phases (Scout → Legislator → Builder → Judge → Deployer) instead of simulated stubs.

What Was Copied
Tier 1 — Core Engines (forgeworks/core_engines/)
Full copy of SAM's CoreEngines/ model-switching framework. Provides:

SmartModelSelector — auto-routes queries to the right model role (reasoning_model for Scout/Legislator, code_model for Builder)
ModelConfigManager — reads 
models.conf
, talks to Ollama, manages load/unload/switch
ModelManagerIntegration
 — singleton bridge with observer pattern + perf monitoring
Engine implementations: DeepSeek, Qwen, Llama, GLM, Jamba
Import surgery performed: Rerouted all internal sam.core.* cross-references to forgeworks.core_engines.*. SAM-specific optional imports (embedding manager, DPO manager, hybrid model) were commented out as they are not needed in ForgeWorks.

Tier 2 — Relay State Machine + 5 Phases
File	Location
tokio_baton.py
forgeworks/runner/tokio_baton.py
phase1_scout.py
forgeworks/runner/phases/phase1_scout.py
phase2_legislator.py
forgeworks/runner/phases/phase2_legislator.py
phase3_builder.py
forgeworks/runner/phases/phase3_builder.py
phase4_judge.py
forgeworks/runner/phases/phase4_judge.py
phase5_deployer.py
forgeworks/runner/phases/phase5_deployer.py
Import surgery performed:

sam.orchestration.tokio_baton → forgeworks.runner.tokio_baton
sam.core.model_manager_integration → forgeworks.core_engines
Phase 4 hardcoded intent path → Path(__file__).parents[1] / "forgegate_intents/sam_sandbox_intent/..."
Phase 5 hardcoded intent path → Path(__file__).parents[1] / "forgegate_intents/sam_deploy_intent/..."
Phase 5 deploy target → forgeworks/results/<ticket_id>/ (was deployments/<ticket_id>/)
Tier 3 — ForgeGate Intent Bundles
Template bundles integrated from SAM and then aligned to ForgeGate hardening:

forgeworks/runner/forgegate_intents/sam_sandbox_intent/ — 2 constraints: workspace jail + Python-only extension
forgeworks/runner/forgegate_intents/sam_deploy_intent/ — 2 constraints: require verification + protect core paths

Hardening updates applied:
- intent root keys standardized to `intent_id` + `intent_version`
- substring checks migrated to `contains` (instead of reversed string `in`)
- legacy keys removed to avoid silent policy drift
Tier 4 — ForgeScaffold Helpers (forgeworks/runner/scaffolding/)
File	Changes
forgescaffold_test_validator.py
Zero changes (no SAM imports)
forgescaffold_coding_context.py
Hardcoded absolute workspace path → relative Path(__file__).parents[4]; SAM_ROOT → FORGEWORKS_ROOT; project_id "sam" → "forgeworks"
forgescaffold_adapter.py	Same path fixes; project "sam_evolution" → "forgeworks_pipeline"
Verification Results
Import Smoke Test ✅
[OK] tokio_baton imports
[OK] All 5 phases import
[OK] core_engines imports
[OK] forgescaffold_test_validator imports
[OK] forgescaffold_coding_context imports
[OK] forgescaffold_adapter imports
All imports OK
Pytest Suite ✅
.............................  [100%]
29 passed
All 14 pre-existing ForgeWorks tests pass unchanged.

Intent Bundle Check ✅
[OK] sam_sandbox_intent (2 constraints)
[OK] sam_deploy_intent (2 constraints)
Intent bundles OK
Final ForgeWorks Structure
forgeworks/forgeworks/
├── core_engines/              ← NEW: full model-switching framework
│   ├── config/
│   │   ├── model_config_manager.py
│   │   └── models.conf
│   ├── engines/model_interface.py
│   ├── integration/
│   │   ├── model_manager_integration.py
│   │   └── model_library_manager.py
│   ├── monitoring/model_performance_monitor.py
│   ├── migration/migration_controller.py
│   ├── selection/smart_model_selector.py
│   ├── validation/model_validator.py
│   └── __init__.py
├── runner/
│   ├── tokio_baton.py          ← NEW: relay state machine
│   ├── phases/                 ← NEW: 5-phase LLM pipeline
│   │   ├── phase1_scout.py
│   │   ├── phase2_legislator.py
│   │   ├── phase3_builder.py
│   │   ├── phase4_judge.py
│   │   └── phase5_deployer.py
│   ├── forgegate_intents/      ← NEW: governance bundles
│   │   ├── sam_sandbox_intent/
│   │   └── sam_deploy_intent/
│   ├── scaffolding/            ← NEW: TDD coding context helpers
│   │   ├── forgescaffold_adapter.py
│   │   ├── forgescaffold_coding_context.py
│   │   └── forgescaffold_test_validator.py
│   ├── sam_like_runner.py      (existing)
│   ├── forgegate_bridge.py     (existing)
│   ├── approvals.py            (existing)
│   └── outcomes.py             (existing)
├── core/                       (existing)
├── adapters/                   (existing)
└── schemas/                    (existing)
Next Steps
Configure models.conf in core_engines/config/ with your local Ollama model names
Wire the phases into sam_like_runner.py — call run_scout, run_legislator, etc. per ticket instead of the simulated ForgeGate stubs
Adapt intent bundles for your two domains (CI change-control and IT Ops) by creating domain-specific bundles alongside the template ones

Claim Lock Integration (Mechanism 1)
The SQLite ticket claim lock is now wired into the runner to enforce one-ticket-at-a-time execution:

- Claims are acquired per ticket with `TicketLedger.try_claim()`
- Stale claims are reaped at run start
- Run lifecycle is persisted with `start_run/complete_run/fail_run`
- Claims are always released in a `finally` block

File: `forgeworks/runner/ticket_ledger.py`  
Wired in: `forgeworks/runner/sam_like_runner.py`
