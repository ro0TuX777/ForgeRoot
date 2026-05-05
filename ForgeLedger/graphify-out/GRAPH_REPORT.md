# Graph Report - .  (2026-05-04)

## Corpus Check
- Corpus is ~23,410 words - fits in a single context window. You may not need a graph.

## Summary
- 703 nodes · 2440 edges · 18 communities detected
- Extraction: 44% EXTRACTED · 56% INFERRED · 0% AMBIGUOUS · INFERRED: 1370 edges (avg confidence: 0.61)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Backend Legal Hold|Backend Legal Hold]]
- [[_COMMUNITY_Event Schema Emission|Event Schema Emission]]
- [[_COMMUNITY_Checkpoint Anchoring|Checkpoint Anchoring]]
- [[_COMMUNITY_Canonical Signing|Canonical Signing]]
- [[_COMMUNITY_WORM Object Storage|WORM Object Storage]]
- [[_COMMUNITY_Public API Surface|Public API Surface]]
- [[_COMMUNITY_Hash Chain Validation|Hash Chain Validation]]
- [[_COMMUNITY_Key Management|Key Management]]
- [[_COMMUNITY_Ecosystem Evidence Docs|Ecosystem Evidence Docs]]
- [[_COMMUNITY_Adapter Validation|Adapter Validation]]
- [[_COMMUNITY_Read Access Auditing|Read Access Auditing]]
- [[_COMMUNITY_Retention Lifecycle|Retention Lifecycle]]
- [[_COMMUNITY_Durable Replay Guard|Durable Replay Guard]]
- [[_COMMUNITY_Ingest Redaction|Ingest Redaction]]
- [[_COMMUNITY_Retention Policy Rules|Retention Policy Rules]]
- [[_COMMUNITY_Checkpoint Audit Tests|Checkpoint Audit Tests]]
- [[_COMMUNITY_Test Import Setup|Test Import Setup]]
- [[_COMMUNITY_Export Selector|Export Selector]]

## God Nodes (most connected - your core abstractions)
1. `LedgerEvent` - 98 edges
2. `EventType` - 73 edges
3. `Actor` - 73 edges
4. `Tenant` - 70 edges
5. `SystemContext` - 70 edges
6. `Decision` - 70 edges
7. `Evidence` - 70 edges
8. `Integrity` - 65 edges
9. `LedgerQuery` - 64 edges
10. `Policy` - 64 edges

## Surprising Connections (you probably didn't know these)
- `Read Access Auditing` --semantically_similar_to--> `ForgeLedger Evidence Substrate`  [INFERRED] [semantically similar]
  tests/test_read_auditing.py → forgeledger_whitepaper_draft.md
- `Ingest-Time Redaction` --semantically_similar_to--> `ForgeLedger Evidence Substrate`  [INFERRED] [semantically similar]
  tests/test_redaction.py → forgeledger_whitepaper_draft.md
- `test_read_empty_ledger()` --calls--> `LedgerQuery`  [INFERRED]
  tests\test_jsonl_backend.py → forgeledger\backend.py
- `Import events from an export_slice result into this backend.          The slice'` --uses--> `LedgerEvent`  [INFERRED]
  forgeledger\backend.py → forgeledger\schema.py
- `test_replay_protector_raises_on_duplicate()` --calls--> `ReplayProtector`  [INFERRED]
  tests\test_sdk.py → forgeledger\replay_protection.py

## Hyperedges (group relationships)
- **Event Emission Pipeline** — emitter_ledger_emitter, redaction_ingest_redactor, retention_classify_event, hash_chain_attach_integrity, signing_sign_event, backend_ledger_backend [EXTRACTED 1.00]
- **Checkpoint Anchor Integrity Flow** — checkpoint_checkpoint_manager, checkpoint_chain_checkpoint, anchoring_local_anchor_backend, anchoring_anchor_record, hash_chain_verify_chain [EXTRACTED 1.00]
- **Retention Lifecycle Governance Flow** — retention_lifecycle_retention_lifecycle_manager, retention_get_retention_policy, backend_ledger_backend, audit_emit_audit_event, legal_hold_hold_registry [INFERRED 0.78]
- **Governance Evidence Flow** — test_adapters_concord_adapter_mapping, test_adapters_forgegate_adapter_mapping, forgeledger_whitepaper_forge_root_ecosystem, forgeledger_whitepaper_evidence_substrate [EXTRACTED 1.00]
- **Production Trust Boundary Hardening** — test_redaction_ingest_time_redaction, test_checkpoint_authenticated_checkpoints, test_durable_replay_durable_replay_protection, test_anchoring_local_anchor_backend, test_key_management_key_provider_abstraction, test_worm_object_backend_worm_object_backend [EXTRACTED 1.00]
- **Retention And Access Governance** — test_retention_retention_classification, test_retention_lifecycle_retention_lifecycle, test_legal_hold_hold_registry, test_read_auditing_read_access_auditing, retention_policies_retention_policy_config [INFERRED 0.88]

## Communities

### Community 0 - "Backend Legal Hold"
Cohesion: 0.05
Nodes (51): Wrapper that adds opt-in read-access audit events.      It deliberately audits o, append_event(), AppendResult, ExportSelector, HoldResult, HoldSelector, LedgerBackend, Import events from an export_slice result into this backend.          The slice' (+43 more)

### Community 1 - "Event Schema Emission"
Cohesion: 0.19
Nodes (68): Enum, emit_audit_event(), Emit a governance meta-event if an audit emitter is configured., LedgerEmitter, Raised when the ledger backend rejects an append.      Callers must treat this a, Thin emission helper.  Pipeline (in order):          build event         → Inges, In-memory replay guard.      Tracks processed event_ids; raises ReplayDetectedEr, ReplayProtector (+60 more)

### Community 2 - "Checkpoint Anchoring"
Cohesion: 0.06
Nodes (54): ABC, AnchorBackend, AnchorRecord, AnchorVerificationReport, CloudImmutableAnchorBackend, LocalAnchorBackend, Placeholder for future externally controlled immutable anchor targets., Append-only local anchor JSONL backend.      This is a local trust-target simula (+46 more)

### Community 3 - "Canonical Signing"
Cohesion: 0.08
Nodes (47): canonical_json(), Recursively convert dataclasses and enums to JSON-safe primitives., Deterministic JSON: sorted keys, no whitespace, UTF-8 safe., _to_serializable(), Event signing for Phase 5 — HMAC-SHA256 over canonical JSON.  The signature cove, Return a new event with integrity.signature set to HMAC-SHA256(canonical_json)., Verify the event's HMAC-SHA256 signature.     Returns False if the signature fie, _secret_bytes() (+39 more)

### Community 4 - "WORM Object Storage"
Cohesion: 0.07
Nodes (28): WormViolationError, AzureImmutableBlobBackend, LocalWormObjectBackend, Production WORM placeholder for S3 Object Lock., Production WORM placeholder for Azure Immutable Blob., Production WORM placeholder for Wasabi WORM buckets., Local write-once object simulation with manifest-based tamper detection.      Th, S3ObjectLockBackend (+20 more)

### Community 5 - "Public API Surface"
Cohesion: 0.07
Nodes (46): ForgeLedger Public API Surface, AnchorBackend, AnchorRecord, LocalAnchorBackend, emit_audit_event, AuditedLedgerBackend, HoldSelector, LedgerBackend.import_slice (+38 more)

### Community 6 - "Hash Chain Validation"
Cohesion: 0.1
Nodes (33): ChainValidationReport, attach_integrity(), compute_event_hash(), Compute sha256 over the canonical JSON of the event with integrity.event_hash cl, Return a new event with integrity.previous_hash set and integrity.event_hash com, Verify the integrity of an ordered event sequence.      Fails if any event_hash, verify_chain(), _make_chain() (+25 more)

### Community 7 - "Key Management"
Cohesion: 0.1
Nodes (29): EnvironmentKeyProvider, FileKeyProvider, KeyMaterial, Static test/dev provider. Do not use for production secret storage., Loads HMAC-SHA256 signing material from an environment variable., Loads HMAC-SHA256 signing material from a local file., StaticKeyProvider, _actor() (+21 more)

### Community 8 - "Ecosystem Evidence Docs"
Cohesion: 0.07
Nodes (37): Test Import Path Setup, Control Mapping Governance, Evidence Package Generation, ForgeLedger Evidence Substrate, ForgeRoot Ecosystem, Pilot Readiness Boundary, Retention Policy Config, Chainable Adapter Events (+29 more)

### Community 9 - "Adapter Validation"
Cohesion: 0.08
Nodes (17): _is_valid_iso8601(), validate_event(), Phase 1 tests 9–10: 9.  CONCORD event adapter emits a valid ledger event. 10. Fo, Events from both adapters can be chained together correctly., test_adapters_produce_chainable_events(), test_concord_adapter_emits_valid_ledger_event(), test_forgegate_adapter_emits_valid_ledger_event(), _sensitive_payload() (+9 more)

### Community 10 - "Read Access Auditing"
Cohesion: 0.2
Nodes (22): AuditedLedgerBackend, _infer_source_ledger_id(), _query_payload(), LedgerQuery, _audit_emitter(), _audit_events(), _primary_backend(), _reader() (+14 more)

### Community 11 - "Retention Lifecycle"
Cohesion: 0.16
Nodes (27): _action_counts(), _as_aware_utc(), _metadata_only_record(), _parse_event_time(), _read_all_backend_events(), _retention_value(), RetentionAction, RetentionApplyResult (+19 more)

### Community 12 - "Durable Replay Guard"
Cohesion: 0.11
Nodes (16): Exception, DurableReplayProtector, Append-only JSONL replay guard.      Existing event IDs are loaded on initializa, Replay protection for Phase 5.  Tracks seen event_ids and raises ReplayDetectedE, Raised when an event_id has already been processed., Register event_id or raise ReplayDetectedError if already seen., ReplayDetectedError, Phase 7b durable replay protection tests. (+8 more)

### Community 13 - "Ingest Redaction"
Cohesion: 0.2
Nodes (20): IngestRedactor, Ingest-time redaction for ForgeLedger.  Redaction runs BEFORE attach_integrity s, Return a new event with content-bearing payload fields replaced by         [REDA, RedactionPolicy, RedactionReceipt, _base_event(), _emit_sensitive_event(), _read_all() (+12 more)

### Community 14 - "Retention Policy Rules"
Cohesion: 0.21
Nodes (17): classify_event(), get_retention_policy(), is_deletion_eligible(), _load_config(), Force reload — used in tests to reset state., Determine the retention class for an event. legal_hold always wins., _reload_config(), _make_event() (+9 more)

### Community 15 - "Checkpoint Audit Tests"
Cohesion: 0.42
Nodes (13): _audit_emitter(), _emit_sensitive_event(), _make_chain(), _read_all(), test_checkpoint_audit_event_contains_checkpoint_id_and_hash(), test_checkpoint_audit_event_contains_latest_event_hash(), test_checkpoint_emits_ledger_checkpoint_created_event_to_audit_emitter(), test_no_audit_event_when_no_audit_emitter_provided() (+5 more)

### Community 16 - "Test Import Setup"
Cohesion: 1.0
Nodes (1): Add ForgeLedger and ForgedRoot root to sys.path so tests can import forgeledger.

### Community 19 - "Export Selector"
Cohesion: 1.0
Nodes (1): ExportSelector

## Knowledge Gaps
- **37 isolated node(s):** `Recursively convert dataclasses and enums to JSON-safe primitives.`, `Deterministic JSON: sorted keys, no whitespace, UTF-8 safe.`, `Static test/dev provider. Do not use for production secret storage.`, `Loads HMAC-SHA256 signing material from an environment variable.`, `Loads HMAC-SHA256 signing material from a local file.` (+32 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Test Import Setup`** (2 nodes): `conftest.py`, `Add ForgeLedger and ForgedRoot root to sys.path so tests can import forgeledger.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Export Selector`** (1 nodes): `ExportSelector`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ForgeLedger — immutable, tamper-evident audit event ledger for ForgeRoot.  Publi` connect `Checkpoint Anchoring` to `Backend Legal Hold`, `Event Schema Emission`, `WORM Object Storage`, `Hash Chain Validation`, `Key Management`, `Read Access Auditing`, `Retention Lifecycle`, `Durable Replay Guard`, `Ingest Redaction`?**
  _High betweenness centrality (0.210) - this node is a cross-community bridge._
- **Why does `LedgerEvent` connect `Event Schema Emission` to `Backend Legal Hold`, `Checkpoint Anchoring`, `Canonical Signing`, `Hash Chain Validation`, `Key Management`, `Read Access Auditing`, `Retention Lifecycle`, `Ingest Redaction`, `Retention Policy Rules`, `Checkpoint Audit Tests`?**
  _High betweenness centrality (0.103) - this node is a cross-community bridge._
- **Why does `LedgerQuery` connect `Read Access Auditing` to `Backend Legal Hold`, `Event Schema Emission`, `Checkpoint Anchoring`, `Canonical Signing`, `Hash Chain Validation`, `Key Management`, `Retention Lifecycle`, `Ingest Redaction`, `Checkpoint Audit Tests`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Are the 96 inferred relationships involving `LedgerEvent` (e.g. with `AuditedLedgerBackend` and `Wrapper that adds opt-in read-access audit events.      It deliberately audits o`) actually correct?**
  _`LedgerEvent` has 96 INFERRED edges - model-reasoned connections that need verification._
- **Are the 69 inferred relationships involving `EventType` (e.g. with `AnchorRecord` and `AnchorVerificationReport`) actually correct?**
  _`EventType` has 69 INFERRED edges - model-reasoned connections that need verification._
- **Are the 71 inferred relationships involving `Actor` (e.g. with `Emit a governance meta-event if an audit emitter is configured.` and `AuditedLedgerBackend`) actually correct?**
  _`Actor` has 71 INFERRED edges - model-reasoned connections that need verification._
- **Are the 68 inferred relationships involving `Tenant` (e.g. with `Emit a governance meta-event if an audit emitter is configured.` and `LedgerWriteFailedError`) actually correct?**
  _`Tenant` has 68 INFERRED edges - model-reasoned connections that need verification._