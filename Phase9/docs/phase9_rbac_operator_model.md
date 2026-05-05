# Phase 9 RBAC / Operator Model

## Roles

### Ledger Writer
Can append governed events through approved adapters and `LedgerEmitter`. Cannot read, export, decrypt, or alter ledgers by default.

### Compliance Analyst
Can perform audited reads and generate reports. Cannot rotate keys, delete ledgers, or modify mappings.

### Evidence Package Exporter
Can export encrypted evidence packages. Must provide reason and generate audit event.

### Evidence Package Recipient
Can decrypt evidence packages only when authorized. Has no ledger write authority.

### Ledger Administrator
Can configure paths, retention policy, backend providers, and deployment settings. Cannot silently bypass audit controls.

### Key Custodian
Can rotate and manage signing/encryption keys. Cannot alter ledger contents.

### Legal Hold Officer
Can place and release legal holds. Release requires reason and auditability.

### Control Mapping Reviewer
Can review, approve, and deprecate mappings. Cannot alter event history.

### Auditor / External Reviewer
Can receive evidence packages. No direct ledger access by default.

## Action Matrix

| Action | Ledger Writer | Compliance Analyst | Evidence Exporter | Evidence Recipient | Ledger Admin | Key Custodian | Legal Hold Officer | Mapping Reviewer | Auditor |
|---|---|---|---|---|---|---|---|---|---|
| Append event | Allowed, audit via ledger | Denied | Denied | Denied | Approval required | Denied | Denied | Denied | Denied |
| Read ledger | Denied | Allowed, audit required | Approval required, audit required | Denied | Approval required, audit required | Denied | Approval required | Denied | Denied |
| Read audit ledger | Denied | Allowed, audit required | Denied | Denied | Approval required | Denied | Approval required | Approval required | Denied |
| Export evidence package | Denied | Approval required | Allowed, audit required | Denied | Approval required | Denied | Denied | Denied | Denied |
| Decrypt evidence package | Denied | Approval required | Approval required | Allowed if authorized | Denied | Approval required | Denied | Denied | Allowed if authorized |
| Run retention scan | Denied | Allowed, audit required | Denied | Denied | Allowed, audit required | Denied | Allowed, audit required | Denied | Denied |
| Apply retention action | Denied | Denied | Denied | Denied | Approval required, audit required | Denied | Approval required, audit required | Denied | Denied |
| Place legal hold | Denied | Approval required | Denied | Denied | Approval required | Denied | Allowed, audit required | Denied | Denied |
| Release legal hold | Denied | Denied | Denied | Denied | Approval required | Denied | Approval required, audit required | Denied | Denied |
| Publish anchor | Denied | Denied | Denied | Denied | Allowed, audit required | Denied | Denied | Denied | Denied |
| Rotate keys | Denied | Denied | Denied | Denied | Approval required | Allowed, audit required | Denied | Denied | Denied |
| Approve control mapping | Denied | Denied | Denied | Denied | Denied | Denied | Denied | Allowed, audit/process record required | Denied |
| Modify deployment config | Denied | Denied | Denied | Denied | Approval required, audit required | Approval required for key settings | Denied | Denied | Denied |

Direct ledger file access is privileged break-glass access. It should be discouraged, logged externally where possible, and reviewed after use.
