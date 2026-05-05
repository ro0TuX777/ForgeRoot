# Phase 9 Pilot Readiness Checklist

Status values: PASS, WARN, FAIL, NOT APPLICABLE.

## 1. Ledger Controls

| Item | Status | Notes |
|---|---|---|
| Ingest-time redaction enabled | PASS | Proven in Phase 7/8 tests. |
| Event authentication enabled | PASS | HMAC-SHA256 supported with key IDs. |
| Checkpointing enabled | PASS | Authenticated checkpoints available. |
| Anchor publishing configured | WARN | Local anchor simulation exists; external target pending. |
| Replay protection enabled | PASS | Durable replay protection implemented. |

## 2. Storage Controls

| Item | Status | Notes |
|---|---|---|
| Primary ledger path selected | PASS | Pilot path documented. |
| Audit ledger path selected | PASS | Separate audit ledger documented. |
| WORM backend selected | WARN | Local simulation selected for pilot. |
| Object-lock decision recorded | PASS | Production decision options documented. |

## 3. Key Controls

| Item | Status | Notes |
|---|---|---|
| Key provider selected | WARN | Env/file acceptable for pilot; KMS/HSM pending. |
| Key ID recorded | PASS | Events/checkpoints support key IDs. |
| Key rotation owner assigned | WARN | Role defined, named owner pending. |
| No raw secret in artifacts | PASS | Tested for ledger/checkpoint artifacts. |

## 4. Access Controls

| Item | Status | Notes |
|---|---|---|
| RBAC model reviewed | WARN | Model documented; enforcement wrapper pending. |
| Evidence exporter assigned | WARN | Role defined, named owner pending. |
| Legal hold officer assigned | WARN | Role defined, named owner pending. |
| Key custodian assigned | WARN | Role defined, named owner pending. |

## 5. Compliance Controls

| Item | Status | Notes |
|---|---|---|
| Mapping governance reviewed | PASS | Governance metadata and reports implemented. |
| Claim boundary approved | WARN | Draft approved language exists; formal approval pending. |
| Deprecated mappings excluded | PASS | Implemented by default. |
| Customer overlays reviewed | WARN | Mechanism exists; customer process pending. |

## 6. Evidence Controls

| Item | Status | Notes |
|---|---|---|
| Evidence package generated | PASS | Phase 9 package generated. |
| Package encrypted | PASS | AES-256-GCM package generated. |
| Package hash verified | PASS | Package hash included. |
| Package decryption tested | PASS | Decryption utility tested in suite. |
| Read-access audit recorded | PASS | Read audit sample generated. |

## 7. Retention Controls

| Item | Status | Notes |
|---|---|---|
| Retention scan run | PASS | Phase 9 scan generated. |
| Legal holds reviewed | WARN | Mechanism exists; pilot owner pending. |
| Dry-run report reviewed | WARN | Report generated; review pending. |
| Apply mode disabled unless approved | PASS | Dry-run is default. |

## 8. Open Gaps

| Item | Status | Yes/No |
|---|---|---|
| External anchor production target implemented? | WARN | No |
| Infrastructure WORM implemented? | WARN | No |
| KMS/HSM implemented? | WARN | No |
| Real captured subsystem outputs available? | WARN | No |
| Formal compliance review complete? | WARN | No |
| Deployment threat model approved? | WARN | No |

## Checklist Result

Pilot readiness: PASS with WARN items.

Production deployment readiness: FAIL until external immutable anchoring, infrastructure WORM/object-lock storage, real key-management infrastructure, RBAC enforcement, formal review, and operational scheduler decisions are implemented.
