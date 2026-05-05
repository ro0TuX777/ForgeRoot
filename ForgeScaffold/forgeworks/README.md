# ForgeWorks (Phase A)

ForgeWorks is a terminal/Docker workcell T&E pipeline. Phase A establishes the canonical workcell IR, validation, and deterministic hashing.

## Quickstart

```bash
cd forgeworks
pip install -e '.[dev]'
forgeworks validate --workcell ./packs/hello_workcell/0.1.0
```

## Docker (build context + start commands)

ForgeWorks’ Docker image is built from the **repo root** so both ForgeWorks and ForgeGate are included.
Build from your workspace repo root (for example `~/ForgeScaffold`), not from the `forgeworks/` subdir.

```bash
# from repo root
docker build -t forgeworks:local -f forgeworks/docker/Dockerfile .
```

Start the container and run the CLI (results volume mounted):

```bash
cd forgeworks
docker run --rm -v "$PWD/results:/app/forgeworks/results" forgeworks:local \
  forgeworks validate --workcell ./packs/ci_change_control/0.1.0
```

Example supervised run inside the container:

```bash
docker run --rm -v "$PWD/results:/app/forgeworks/results" forgeworks:local \
  forgeworks run --workcell ./packs/ci_change_control/0.1.0 --mode supervised --out ./results/ci_supervised_container
```

What the container includes:
- ForgeWorks (installed editable)
- ForgeGate (installed editable; required for `forgeworks run`)
- Runtime deps (jsonschema, pyyaml, etc.)

## Scripts (one-command pack execution)

These are thin wrappers around the CLI with a deterministic command order.

```bash
# validate → run → score → report
./scripts/run_pack.sh ci_change_control 0.1.0 supervised ./results/ci_supervised_script

# demo across two packs + summary
./scripts/run_demo.sh ./results/demo
```

## Batch template generator (CI change-control)

Generate a minimal raw ingest batch in one command:

```bash
./scripts/generate_ci_batch.py --out ./ingest/ci_change_control/batch_002 --count 5
```

Then run ingest/normalize against it:

```bash
forgeworks ingest --domain ci_change_control --source ./ingest/ci_change_control/batch_002 --out ./ingest/ci_change_control/staged_batch_002
forgeworks normalize --domain ci_change_control --raw ./ingest/ci_change_control/staged_batch_002 --out ./packs/ci_change_control/test_batch_002
```

## Batch template generator (IT ops runbook)

Generate a minimal IT ops batch in one command:

```bash
./scripts/generate_it_ops_batch.py --out ./ingest/it_ops_runbook/batch_001
```

Then run ingest/normalize against it:

```bash
forgeworks ingest --domain it_ops_runbook --source ./ingest/it_ops_runbook/batch_001 --out ./ingest/it_ops_runbook/staged_batch_001
forgeworks normalize --domain it_ops_runbook --raw ./ingest/it_ops_runbook/staged_batch_001 --out ./packs/it_ops_runbook/test_batch_001
```

## CLI

### Validate a workcell

```bash
forgeworks validate --workcell ./packs/hello_workcell/0.1.0
```

On success, prints the deterministic `workcell_hash`. On failure, prints a clear error and exits non-zero.

## ForgeGate Governance Hardening (March 2026)

ForgeWorks ships embedded ForgeGate intent bundles for Phase 4 (`Judge`) and Phase 5 (`Deployer`):

- `forgeworks/runner/forgegate_intents/sam_sandbox_intent/intent/intent_spec.json`
- `forgeworks/runner/forgegate_intents/sam_deploy_intent/intent/intent_spec.json`

These bundles were updated to align with ForgeGate hardening:

- schema-compliant root fields: `intent_id`, `intent_version`
- substring checks use ForgeGate `contains` operator
- policy files avoid legacy keys that can be ignored by mistake

Recommended validation flow when editing governance bundles:

```bash
# from the ForgeGate project root
forgegate lint-intent /path/to/IntentBundle --strict
forgegate validate-bundle /path/to/IntentBundle --strict
```

Why this matters:
- invalid `when` expression types fail closed instead of silently mis-evaluating
- unknown top-level intent keys are surfaced by strict lint/validation
- intent-policy regressions are easier to catch before live runs

## Schemas

Workcell IR schemas live in `forgeworks/schemas/`:
- ticket.v0_1.json
- artifact_index.v0_1.json
- signals.v0_1.json
- run_config.v0_1.json
- results.v0_1.json
- drift_plan.v0_1.json
- scoring.v0_1.json

## Fixture

A minimal valid fixture exists at:
`packs/hello_workcell/0.1.0/`

## Additional docs

- `docs/FORGEGATE_HARDENING.md`
- `docs/SAM_FORGEWORKS_HANDOFF.md`
