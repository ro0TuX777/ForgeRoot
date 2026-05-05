# Phase 9 Infrastructure Decisions

## Decision 1 - External Anchor Target

| Option | Pros | Cons | Pilot Suitability | Production Suitability | Recommendation |
|---|---|---|---|---|---|
| Local JSONL anchor only | Simple, testable, already implemented | Same host trust domain; not externally immutable | Good | Poor | Pilot default only |
| S3 Object Lock bucket | Strong cloud immutability, common operational model | Requires AWS setup and policy hardening | Good if AWS available | Strong | Preferred production option on AWS |
| Azure Immutable Blob | Strong cloud immutability, Azure-native | Requires Azure setup and policy hardening | Good if Azure available | Strong | Preferred production option on Azure |
| RFC 3161 timestamp authority | Independent timestamp proof | Does not store full operational context | Good supplemental option | Good supplemental option | Consider as secondary anchor |
| Git commit signing / transparency repository | Human-readable history, easy review | Operational discipline required; repo permissions matter | Good pilot candidate | Medium | Useful interim external anchor |
| Append-only transparency log | Strong public/internal append-only semantics | Requires service selection or build | Medium | Strong | Long-term candidate |

Selected pilot default: local JSONL anchor plus documented limitation.

Production recommendation: S3 Object Lock, Azure Immutable Blob, or append-only transparency log.

Open questions:
- Which cloud provider is preferred for pilot?
- Is external timestamping required by customer policy?

## Decision 2 - WORM / Object-Lock Storage

| Option | Pros | Cons | Pilot Suitability | Production Suitability |
|---|---|---|---|---|
| Local WORM simulation | Easy local validation; manifest tamper detection | Not infrastructure immutability | Good | Poor |
| S3 Object Lock | Mature WORM control | AWS configuration required | Good if AWS available | Strong |
| Azure Immutable Blob | Azure-native WORM | Azure configuration required | Good if Azure available | Strong |
| Wasabi WORM | Cost-effective object-lock style storage | Provider-specific review required | Medium | Medium/Strong |
| Other object-lock storage | Flexible | Requires formal assessment | Unknown | Unknown |

Selected pilot default: local WORM simulation.

Production recommendation: object-lock storage with compliance-mode retention where appropriate.

## Decision 3 - Key Management

| Option | Pros | Cons | Pilot Suitability | Production Suitability |
|---|---|---|---|---|
| Static test provider | Simple tests | Not operationally safe | Tests only | Poor |
| Environment provider | Simple deployment integration | Secret exposure risk through environment management | Acceptable pilot | Medium |
| File provider | Easy local control | File permission risk | Acceptable pilot | Medium |
| AWS KMS | Managed keys and auditability | AWS dependency | Good if AWS available | Strong |
| Azure Key Vault / Managed HSM | Managed keys and auditability | Azure dependency | Good if Azure available | Strong |
| HashiCorp Vault | Cloud-neutral secret management | Requires Vault ops maturity | Medium | Strong |
| Hardware HSM | Strong key protection | Cost and operational complexity | Low | Strong |

Selected pilot default: environment or file provider.

Production recommendation: cloud KMS, Vault, or HSM depending on deployment environment.

## Decision 4 - Evidence Package Encryption

| Option | Pros | Cons | Pilot Suitability | Production Suitability |
|---|---|---|---|---|
| Local AES-256-GCM key | Already implemented; simple | Key custody is manual | Good | Medium |
| KMS-wrapped data key | Better custody and auditability | Requires KMS integration | Medium | Strong |
| Customer-provided key | Strong customer control | Operational coordination required | Medium | Strong |

Selected pilot default: AES-256-GCM with controlled pilot key.

Production recommendation: KMS-wrapped data key or customer-provided key.

## Decision 5 - Audit Log Storage

| Option | Pros | Cons | Pilot Suitability | Production Suitability |
|---|---|---|---|---|
| Same host separate file | Simple | Same host compromise risk | Good pilot default | Poor |
| Separate mounted volume | Better separation | Mount/security config required | Good | Medium |
| Object-lock target | Strong retention | Requires cloud/object-lock setup | Medium | Strong |
| SIEM forwarding | Operational monitoring | Requires integration and parsing | Medium | Strong |

Selected pilot default: separate local audit ledger.

Production recommendation: object-lock storage and/or SIEM forwarding.

## Decision 6 - Retention Operation

| Option | Pros | Cons | Pilot Suitability | Production Suitability |
|---|---|---|---|---|
| Manual dry-run scan | Safe and reviewable | Manual effort | Strong pilot default | Medium |
| Scheduled dry-run | Better operational rhythm | Scheduler required | Good | Strong |
| Scheduled apply with approval | Enforces lifecycle | Requires approvals and rollback planning | Medium | Strong |
| External records management system | Mature governance | Integration required | Medium | Strong |

Selected pilot default: manual dry-run scan.

Production recommendation: scheduled dry-run and approved apply workflow.
