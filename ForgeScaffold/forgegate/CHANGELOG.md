# Changelog

## ForgeGate v0.4.1 (Hardening)
- Intent preflight validation in `evaluate()` with fail-closed `ESCALATE` for invalid intent specs.
- Expression evaluator now supports `contains` and `has_substr`.
- Added strict lint/validation mode: `lint-intent --strict` and `validate-bundle --strict`.
- Lint now checks intent structure (unknown keys, invalid expression types, empty policy specs).

## ForgeGate v0.4.0 (Phase 4)
- Bundle and ledger signing with verification and checkpoints.
- Replay and diff reports for intent changes.
- Policy linting with signal/action reference checks.
- Rule-scoped missing-signal behavior and typed signal enforcement.
- Tool router profiles and safety hardening (redaction + payload limits).

## ForgeGate v0.3.0 (Phase 3)
- Intent registry with promote/rollback/approve.
- Tool router adapter and runnable demo.
- Drift policy thresholds and triage runbook.
- Budget snapshot schema and evaluation.
- Bundle validation improvements and adoption scaffolding.

## ForgeGate v0.2.0 (Phase 2)
- IntentBundle packaging, drift report, adapters docs, and examples.

## ForgeGate v0.1.0 (Phase 1)
- Initial deterministic gate evaluator, schemas, CLI, and scenario test harness.
