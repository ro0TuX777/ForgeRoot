# Phase 9 Pilot Threat Model

## 1. Scope

This threat model covers a ForgeLedger pilot deployment used to collect governance evidence from CONCORD, ForgeGate, Warden, Azul, and related governed-agent workflows.

In scope:
- Ledger event ingestion, hashing, signing, redaction, checkpoints, anchors, read auditing, retention scans, evidence package generation, and mapping governance.
- Local pilot storage paths and local simulation controls used for pilot validation.
- Operator and reviewer behavior needed to run a responsible pilot.

Out of scope:
- Formal production certification.
- Cloud account hardening, network segmentation, endpoint security, and full enterprise IAM.
- Final legal interpretation of framework compliance.
- Full live subsystem coverage unless captured outputs are later added and reviewed.

This is not a production certification threat model.

## 2. Assets

- Primary ledger
- Audit ledger
- Checkpoints
- Anchors
- WORM object manifests
- Evidence packages
- Evidence package encryption keys
- HMAC signing keys
- Redaction receipts
- Control mappings
- Subsystem adapter inputs
- Captured fixtures
- Retention scan outputs

## 3. Trust Boundaries

- Agent subsystem boundary: governed agents and subsystem outputs enter the assurance path.
- Adapter boundary: normalized subsystem outputs are converted into ledger emissions.
- Ledger write boundary: `LedgerEmitter` applies redaction, retention classification, hashing, signing, and append.
- Audit ledger boundary: governance meta-events are written separately from primary evidence events.
- Evidence export boundary: ledger slices and reports leave the ledger environment.
- Encryption/decryption boundary: evidence packages become accessible to recipients with keys.
- External anchor boundary: checkpoint records leave the primary ledger trust domain.
- WORM storage boundary: object immutability depends on the selected backend.
- Operator/admin boundary: privileged users configure storage, keys, retention, and exports.
- Compliance reviewer boundary: humans approve mappings and claim language.

## 4. Adversaries / Failure Actors

- Accidental operator misuse
- Malicious insider
- Compromised agent
- Compromised filesystem access
- Compromised signing key
- Compromised read/export operator
- Schema drift from subsystem outputs
- Overenthusiastic sales/compliance overclaiming
- External infrastructure misconfiguration

## 5. Threat Scenarios

| Scenario | Risk |
|---|---|
| Ledger tail truncation | Recent events are removed while remaining chain still verifies locally. |
| Chain recomputation after tampering | Event contents are changed and later hashes are recomputed. |
| Event replay | Previously emitted event IDs are resubmitted. |
| Direct file tampering | Local ledger or artifact files are edited outside approved APIs. |
| WORM object tampering | Stored objects are changed after manifest creation. |
| Anchor tampering | Anchor records are modified, omitted, or forged. |
| Key compromise | HMAC or encryption keys are exposed or reused improperly. |
| Read access abuse | Operators read ledger data without justification. |
| Evidence package exfiltration | Exported packages are copied outside approved handling. |
| Package decryption misuse | Authorized key holder decrypts package for an unauthorized purpose. |
| Retention misuse | Records are deleted, archived, or preserved incorrectly. |
| Legal hold bypass | Held records are processed as deletion/archive candidates. |
| Adapter schema drift | Real subsystem output no longer matches adapter assumptions. |
| Raw sensitive prompt leakage | Prompt/response content reaches persistent ledger storage. |
| Redaction receipt misuse | Receipts are treated as authorization to recover raw content. |
| Control mapping overclaim | Evidence mapping is described as certification. |
| Representative fixture mistaken for live integration | Hand-authored fixtures are presented as captured subsystem proof. |

## 6. Existing Mitigations

- Ingest-time redaction before hashing/signing/appending
- Redaction receipts with hashes of original values
- HMAC-SHA256 event authentication
- Authenticated checkpoints
- Local anchor abstraction
- Durable replay protection
- WORM object manifest verification
- Read-access auditing
- Retention lifecycle dry-run and legal-hold checks
- Mapping governance metadata and reports
- AES-256-GCM evidence package encryption
- Explicit claim boundary

## 7. Residual Risks

- Local anchor is not external immutable infrastructure.
- Local WORM simulation is not production object lock.
- HMAC is shared-secret authentication, not asymmetric non-repudiation.
- KMS/HSM providers are stubs, not real integrations.
- Representative fixtures are not live subsystem output.
- RBAC is documented but not fully enforced unless implemented by deployment wrapper.
- Formal compliance review is still required.
- External immutable anchor target has not been selected for production.
- Infrastructure WORM backend has not been deployed.
- Operational retention scheduler has not been implemented.

## 8. Pilot Acceptance Posture

| Risk | Pilot Posture |
|---|---|
| Local anchor simulation | Acceptable for pilot with compensating documentation; requires infrastructure decision for production. |
| Local WORM simulation | Acceptable for pilot; not acceptable as production WORM. |
| HMAC shared-secret model | Acceptable for pilot with protected key handling; requires KMS/HSM decision for production. |
| Representative fixtures | Acceptable for pilot demo planning; real capture required before stronger integration claims. |
| RBAC documented only | Acceptable with manual operator controls; production requires enforcement. |
| Formal mapping review pending | Acceptable with evidence-support claim boundary; certification claims are not allowed. |
| Retention scheduler absent | Acceptable for pilot with manual dry-run; production requires scheduler and approval workflow. |
