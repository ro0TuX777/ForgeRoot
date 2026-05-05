ForgeWorks — Phase D Complete

This is a living planning doc.

Phase A: Canonical workcell IR, validation CLI, deterministic hashing.
Phase B: Domain ingestion and normalization via adapters (ci_change_control, it_ops_runbook).
Phase C: Shadow-mode runner with ForgeGate bridge and deterministic decision ledgers.
Phase D: SAM Core Engines, relay state machine, and 5-phase LLM pipeline absorbed.

Phase D scope (complete)
- Core Engines (model switching, SmartModelSelector, ModelConfigManager, Ollama routing)
- tokio_baton.py (disk-flushed relay state: ValidatedHypothesis, SpecContract, RelayBaton)
- 5-phase pipeline: Scout → Legislator → Builder → Judge → Deployer
- ForgeGate intent bundles: sam_sandbox_intent, sam_deploy_intent (templates)
- ForgeScaffold scaffolding helpers: coding context, test matrix validator, patchset adapter

Next steps
- Configure models.conf with Ollama model assignments (reasoning, code, general)
- Wire phases into sam_like_runner.py per ticket
- Create domain-specific ForgeGate intent bundles for ci_change_control and it_ops_runbook
- Gather first real raw datasets for both domains
