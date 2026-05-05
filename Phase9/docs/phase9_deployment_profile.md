# Phase 9 Pilot Deployment Profile

## 1. Pilot Deployment Assumption

Recommended pilot profile:
- Private/local deployment
- Single tenant
- Filesystem-backed development ledger
- Separate audit ledger
- Local anchor simulation for pilot
- Local WORM simulation for pilot
- Environment or file key provider for pilot
- Encrypted evidence package output

This profile is deployable for a controlled pilot. It is not a production infrastructure profile.

## 2. Environment Layout

| Asset | Recommended Pilot Path |
|---|---|
| Primary ledger | `runtime/ledger/ledger.jsonl` |
| Audit ledger | `runtime/ledger/audit_ledger.jsonl` |
| Checkpoints | `runtime/ledger/checkpoints.jsonl` |
| Anchors | `runtime/ledger/anchors.jsonl` |
| WORM objects | `runtime/worm_objects/` |
| Evidence package output | `Phase9/pilot_evidence_package/` |
| Captured fixture path | `integrations/captured/` |
| Key source | Environment or file key provider |
| Retention config | `ForgeLedger/forgeledger/config/retention_policies.yaml` |

## 3. Data Flow

```text
subsystem output
  -> normalizer
  -> adapter
  -> LedgerEmitter
  -> ingest-time redaction
  -> hash/sign
  -> ledger append
  -> checkpoint
  -> anchor
  -> evidence package export
  -> encrypted package
```

## 4. Tenant Model

The pilot is single tenant by default. Multi-tenant operation is deferred.

Tenant fields remain required in events so that future tenant isolation and filtering can be enforced without changing the event model.

## 5. Storage Model

- Primary ledger: append-only JSONL ledger for governed events.
- Audit ledger: separate JSONL ledger for governance meta-events.
- Checkpoint file: append-only JSONL checkpoints over primary chain state.
- Anchor file: local JSONL anchor simulation for pilot.
- WORM object directory: local manifest-backed WORM simulation.
- Evidence package output: generated under `Phase9/pilot_evidence_package/`, encrypted when a key is supplied.

## 6. Key Model

Pilot key provider choices:
- Environment provider
- File provider
- Static provider for tests only

Current signature model:
- HMAC-SHA256 lowercase hex
- `key_id` recorded where signatures are produced
- Raw signing secret must not appear in ledgers, checkpoints, anchors, WORM manifests, or evidence packages

Future production model:
- KMS or HSM-backed key provider
- Formal key rotation and custody workflow

## 7. Pilot Limitations

- No real object-lock infrastructure unless configured externally.
- No real external immutable anchor unless selected.
- No production RBAC unless implemented by the deployment wrapper.
- No compliance certification claim.
- Representative fixtures remain separate from real captured subsystem outputs.
