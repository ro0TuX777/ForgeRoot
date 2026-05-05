We want to add a new compliance evidence harness to ForgeRoot.

Please implement this as two related modules:

1. **ForgeLedger** — immutable, tamper-evident event ledger.
2. **ForgeCompliance** — control mapping, retention validation, evidence package generation, and compliance gap analysis.

The product claim is not “ForgeRoot makes customers compliant.” The claim is: **ForgeRoot produces control-aligned evidence for governed AI systems.**

## Architectural direction

Build v0.1 as internal-first, but design the schemas so the system can become embeddable later.

Use a shared library/direct-call pattern first. Do not introduce an event bus yet. However, all events must use a bus-compatible canonical event envelope so migration to an event bus is straightforward later.

Use a plugin architecture for sector/framework differences. Do not create one monolithic YAML file.

Use a `LedgerBackend` abstraction from day one. v0.1 backend should be local JSONL hash-chain. WORM-capable backends should be Phase 4.

## Phase 1: ForgeLedger v0.1

Implement:

* `LedgerEvent` schema
* canonical JSON serializer
* append-only JSONL backend
* hash-chain event integrity
* chain validation
* retention classification
* legal hold flag
* basic event export
* adapters for CONCORD and ForgeGate events

Initial event types:

* `concord.admission_decision`
* `forgegate.decision_record`
* `forgegate.policy_evaluation`
* `azul.verdict_summary`
* `warden.llm_call_metadata`
* `agent.tool_call`
* `agent.human_review_required`
* `human.approval_decision`
* `retention.legal_hold_applied`

Each event must include:

* `event_id`
* `ledger_version`
* `event_type`
* `event_time`
* `actor`
* `tenant`
* `system_context`
* `decision`
* `evidence`
* `policy`
* `control_tags`
* `integrity.previous_hash`
* `integrity.event_hash`

Retention classes:

* `ephemeral`
* `operational_30d`
* `support_1y`
* `audit_7y`
* `health_10y`
* `legal_hold`
* `customer_defined`

## Phase 1 tests

Create tests proving:

1. Appending an event creates a deterministic event hash.
2. A valid hash chain passes validation.
3. Editing an event causes chain validation failure.
4. Deleting an event causes chain validation failure.
5. Reordering events causes chain validation failure.
6. Every event gets a retention class.
7. Legal hold blocks deletion/purge.
8. Every policy decision records a policy hash.
9. CONCORD event adapter emits a valid ledger event.
10. ForgeGate DecisionRecord adapter emits a valid ledger event.

## Phase 2: ForgeCompliance v0.2

Implement:

* control registry
* mapping YAML schema
* framework mapper
* evidence gap analyzer
* plugin interface
* initial mappings for:

  * NZISM
  * HIPC 2020 / NZ Health
  * RBNZ BS11
  * SOC 2
  * ISO 27001
  * NIST CSF 2.0
  * Essential Eight
  * APRA CPS 234

Every mapping must include:

* framework
* control ID
* control objective
* required event types
* required fields
* evidence artifacts
* retention expectation
* claim boundary
* mapping confidence

The claim boundary must say: **“Evidence support only. Not a compliance certification.”**

## Phase 2 tests

Create tests proving:

1. All mapping YAML files validate against schema.
2. Event types map to expected control IDs.
3. Missing required fields are detected.
4. Missing event types produce control evidence gaps.
5. Sector plugins can override default retention.
6. Every mapping includes a claim boundary.
7. Coverage report is deterministic/reproducible.

## Phase 3: Evidence package generation

Implement an evidence package exporter that creates:

* `manifest.json`
* `package_hash.txt`
* `ledger_slice.jsonl`
* `chain_validation_report.json`
* `control_coverage_report.json`
* `retention_policy_report.json`
* `legal_hold_report.json`
* `event_type_summary.csv`
* `evidence_gap_report.json`
* `human_review_decisions.json`
* `model_provider_boundary_report.json`
* `README_AUDITOR.md`

The package must avoid compliance overclaiming and must include the claim boundary.

## Phase 3 tests

Create tests proving:

1. Package manifest is generated.
2. Package hash detects tampering.
3. Package contains chain validation report.
4. Package contains control coverage report.
5. Package contains evidence gap report.
6. Sensitive prompts/responses are redacted or hashed when policy requires.
7. Auditor README includes claim boundary.

## Phase 4: Backend abstraction and WORM readiness

Implement or stub:

* `LedgerBackend`
* JSONL backend
* WORM-compatible backend interface
* backend health event
* write-failure behavior
* export/import preserving hash chain

Tests:

1. Backend interface contract.
2. Write failure fails closed or emits critical event.
3. Export/import preserves chain integrity.
4. WORM backend rejects mutation where supported.

## Phase 5: Embeddable SDK / event bus compatibility

Do not implement fully in v0.1, but design schema for this path.

Future requirements:

* lightweight event emitter SDK
* event signing
* replay protection
* tenant boundary enforcement
* HTTP/queue ingest endpoint
* bus payload matches direct-call payload

## Phase 6: Demo integration

Integrate ForgeLedger and ForgeCompliance into the ForgeRoot Governed Agent Demo.

The demo must show:

* structured answer
* evidence citations
* assertion classes
* evidence gaps
* human-review trigger
* policy decision
* ledger event timeline
* hash-chain validation
* control coverage map
* retention class
* exportable evidence package

## Required output before coding

Please return:

1. Final proposed file tree.
2. Final event schema.
3. LedgerBackend interface.
4. Retention policy YAML.
5. First three mapping examples:

   * NZISM
   * SOC 2
   * HIPC 2020
6. Test matrix.
7. Build sequence by phase.
8. Any coupling risks with CONCORD, ForgeGate, Azul, or Warden.
9. Any security risks in storing prompts/responses.
10. Any recommendation to narrow Phase 1 further.


Yes — your AI Dev’s response is directionally right. I would formalize this as a new ForgeRoot compliance evidence harness, but I would slightly refine the naming and scope:

ForgeLedger should be the immutable evidence ledger.
ForgeCompliance should be the harness layer that validates, maps, exports, and tests compliance evidence.

That separation matters. A ledger stores facts. A compliance harness proves that those facts satisfy defined evidence expectations.

The complete solution should look like this:

ForgeRoot
├── CONCORD        → admission / authorization decisions
├── ForgeGate      → policy and action decision records
├── Azul           → safety verdicts and evidence trails
├── Warden         → LLM gateway call records
├── ForgeLedger    → immutable audit/event ledger
└── ForgeCompliance → control mapping, retention validation, evidence packages, gap analysis, tests
1. Strategic framing

The product claim should be:

ForgeRoot produces compliance-aligned evidence for governed AI systems by recording agent actions, policy decisions, evidence usage, model interactions, human approvals, retention classifications, and control mappings in a tamper-evident ledger.

The product should not claim:

“ForgeRoot makes you SOC 2 / ISO / NZISM / APRA compliant.”

That would be too strong. SOC 2, for example, concerns controls at service organizations relevant to security, availability, processing integrity, confidentiality, and privacy. ISO/IEC 27001 is an information security management system standard. NIST CSF 2.0 organizes cybersecurity outcomes around governance and operational security functions. ForgeRoot can support those control programs, but it does not replace auditors, risk owners, or formal certification.

The right phrase is:

Control-aligned evidence generation for AI governance.

That is defensible and valuable.

2. Core architectural decision: internal-only vs embeddable

Your AI Dev correctly identified the most important question: is this for ForgeRoot’s own internal actions only, or is it embeddable by downstream systems?

My recommendation:

Build v0.1 as internal-first, schema-designed for embeddability.

Do not try to solve downstream embedding immediately. But design the event schema, API, and backend interface so embeddability is a clean v0.3/v0.4 extension.

Option	Recommendation	Reason
Internal-only forever	No	Too limiting commercially.
Fully embeddable from day one	No	Too much deployment/API/security complexity.
Internal-first, embeddable schema	Yes	Fast, useful, commercially extensible.

The v0.1 implementation should ingest events from CONCORD, ForgeGate, Azul, and Warden through a shared library. But every event should use a stable envelope that could later be emitted over an event bus.

3. Proposed solution: ForgeLedger + ForgeCompliance
A. ForgeLedger

ForgeLedger is the immutable audit system.

Responsibilities
Record structured events.
Hash-chain entries.
Preserve event provenance.
Attach policy/version hashes.
Attach tenant/system boundaries.
Apply retention classification.
Support legal hold.
Support WORM backend abstraction.
Export event slices for compliance evidence packages.
Event sources
Source	Event examples
CONCORD	admission allowed/denied, identity checks, role checks, session boundary decisions
ForgeGate	action allowed/denied/review, policy decision, risk score, approval requirement
Azul	safety verdict, evidence bundle, pass/fail/warn result, reviewer notes
Warden	LLM call metadata, model provider, prompt class, response class, redaction status
ForgeRoot agents	tool calls, retrieval events, assertion classes, evidence gaps, escalation events
Human reviewers	approval, rejection, override, legal hold, risk acceptance
Ledger event envelope

Every event should follow a canonical schema:

{
  "event_id": "uuid",
  "ledger_version": "0.1",
  "event_type": "forgegate.decision_record",
  "event_time": "2026-04-28T00:00:00Z",
  "actor": {
    "actor_type": "agent|human|system",
    "actor_id": "agent.solution_designer",
    "role": "solution_engineer"
  },
  "tenant": {
    "tenant_id": "demo_msp_001",
    "customer_boundary": "synthetic_customer_a",
    "data_residency": "NZ"
  },
  "system_context": {
    "source_module": "ForgeGate",
    "environment": "local|private_cloud|cloud",
    "deployment_id": "forgeroot-demo"
  },
  "decision": {
    "decision_type": "allow|deny|review|escalate",
    "reason": "high_impact_recommendation_requires_review",
    "risk_level": "medium|high|critical"
  },
  "evidence": {
    "evidence_refs": ["doc:veeam_integration#chunk-4"],
    "evidence_gaps": [
      {
        "gap_type": "missing_bom_pricing",
        "blocking": true
      }
    ],
    "assertion_classes": ["FACT", "RECOMMENDATION", "APPROVAL_REQUIRED"]
  },
  "policy": {
    "policy_id": "forgeroot_policy_nz_msp_v0.1",
    "policy_hash": "sha256...",
    "retention_class": "audit_7y",
    "legal_hold": false
  },
  "control_tags": [
    "NZISM.LOGGING",
    "NIST_CSF.GV",
    "SOC2.SECURITY",
    "ISO27001.ANNEX_A_LOGGING"
  ],
  "integrity": {
    "previous_hash": "sha256...",
    "event_hash": "sha256...",
    "signature": null
  }
}
Hash-chain rule

Each entry should include:

event_hash = sha256(canonical_json(event_without_event_hash) + previous_hash)

Validation should fail if:

an event is missing,
an event is edited,
event order is changed,
the previous hash does not match,
the stored event hash does not recompute.
B. ForgeCompliance

ForgeCompliance is the compliance evidence harness.

Responsibilities
Map ledger event types to control frameworks.
Validate that required evidence exists.
Detect control evidence gaps.
Generate audit packages.
Validate retention policies.
Test legal hold behavior.
Produce framework-specific coverage reports.
Produce auditor-friendly evidence bundles.
Supported framework profiles

Start with these, in priority order:

Priority	Framework / profile	Why
1	NZISM	New Zealand government information security context. NZISM is the New Zealand Government’s manual for information assurance and information systems security.
2	NZ Privacy Act / HIPC profile	Relevant to health and personal information. HIPC covers identifiable health information handled by health agencies.
3	RBNZ BS11	Relevant to outsourcing risk for NZ banks. RBNZ describes BS11 as its outsourcing policy for banks.
4	Essential Eight	Widely recognized Australian baseline mitigation maturity model and relevant for NZ-aligned conversations. ASD says it supports implementation of the Essential Eight and progressive maturity levels.
5	ISO/IEC 27001/27002	Globally understood ISMS/control language.
6	SOC 2	Useful for service-provider assurance conversations.
7	NIST CSF / NIST 800-53 AU family	Useful for international mapping and audit/accountability vocabulary.
8	APRA CPS 234	Useful for Australian and finance-adjacent assurance. CPS 234 aims to ensure APRA-regulated entities are resilient against information security incidents.

For the demo, do not attempt full authoritative mappings. Use control-alignment mappings with claim boundaries.

Each mapping file should contain:

framework: NZISM
profile_version: "0.1"
claim_boundary: "Evidence support only. Not a compliance certification."
controls:
  - control_id: "NZISM.LOGGING.EVENT_CAPTURE"
    objective: "Security-relevant events are captured and retained."
    required_event_types:
      - "concord.admission_decision"
      - "forgegate.decision_record"
      - "warden.llm_call_metadata"
    required_fields:
      - "event_id"
      - "event_time"
      - "actor.actor_id"
      - "decision.decision_type"
      - "integrity.event_hash"
    evidence_artifacts:
      - "ledger_slice.jsonl"
      - "chain_validation_report.json"
      - "retention_policy_report.json"
4. Storage backend design

Your AI Dev is right: use a backend interface from day one.

v0.1 backends
Backend	Use
Local JSONL hash-chain	Dev and demo
SQLite ledger index	Search and test convenience
Filesystem evidence package export	Auditor bundle
v0.2/v0.3 backends
Backend	Use
S3 Object Lock / compatible WORM	Production immutability
Azure Immutable Blob	NZ/AU enterprise deployments
PostgreSQL append-only table	Operational querying
External SIEM export	Enterprise monitoring

The interface:

class LedgerBackend:
    def append_event(self, event: LedgerEvent) -> AppendResult: ...
    def read_events(self, query: LedgerQuery) -> list[LedgerEvent]: ...
    def get_latest_hash(self) -> str | None: ...
    def verify_chain(self) -> ChainValidationReport: ...
    def apply_legal_hold(self, selector: HoldSelector) -> HoldResult: ...
    def export_slice(self, selector: ExportSelector) -> EvidencePackage: ...
5. Retention Policy Engine

This should be a first-class subsystem, not a note in the schema.

Retention classes
retention_classes:
  ephemeral:
    retain_for_days: 0
    preserve_metadata_only: true
  operational_30d:
    retain_for_days: 30
  support_1y:
    retain_for_days: 365
  audit_7y:
    retain_for_days: 2555
  health_10y:
    retain_for_days: 3650
  legal_hold:
    retain_until: manual_release
    deletion_allowed: false

Health is worth special handling. The New Zealand Privacy Commissioner’s HIPC retention factsheet says Health Act regulations require health information held by providers to be retained for 10 years from the last encounter with the patient, unless transferred to another doctor or to the patient.

Retention engine responsibilities

For each event, determine:

retention class,
retention basis,
minimum retention period,
deletion eligibility,
legal hold status,
whether raw prompt/response can be retained,
whether metadata-only retention is required,
whether evidence snapshots can be retained,
whether cross-border export is permitted.
Key retention logic
if legal_hold = true:
    deletion_allowed = false
elif event.data_sensitivity = health_identifiable:
    retention_class = health_10y
elif event.control_tags includes finance_outsourcing:
    retention_class = audit_7y
elif event.event_type startswith warden.llm_call:
    retain prompt only if allowed by data_sensitivity policy
else:
    retention_class = operational_30d
6. Sector plugin pattern

Your AI Dev’s plugin instinct is correct.

Recommended structure:

forgeroot/
  forgeledger/
    schema.py
    backend.py
    jsonl_backend.py
    hash_chain.py
    retention.py
    legal_hold.py
    event_emitters.py
  forgecompliance/
    control_registry.py
    mapper.py
    gap_analyzer.py
    evidence_package.py
    validators.py
    reports.py
    plugins/
      base.py
      nz_government.py
      nz_health.py
      nz_finance.py
      au_finance.py
      generic_soc2.py
      generic_iso27001.py
      generic_nist.py
    mappings/
      nzism.yaml
      hipc_2020.yaml
      rbnz_bs11.yaml
      essential_eight.yaml
      apra_cps_234.yaml
      iso27001_2022.yaml
      soc2_tsc.yaml
      nist_csf_2_0.yaml
Plugin responsibilities

Each plugin should define:

class CompliancePlugin:
    profile_id: str
    jurisdiction: str
    sector: str
    framework_mappings: list[ControlMapping]

    def classify_event(self, event: LedgerEvent) -> list[str]: ...
    def retention_policy_for(self, event: LedgerEvent) -> RetentionDecision: ...
    def required_evidence(self, control_id: str) -> EvidenceRequirement: ...
    def validate_package(self, package: EvidencePackage) -> ValidationReport: ...

This makes NZ Health different from NZ Finance without turning one YAML into a swamp.

7. Phased implementation plan
Phase 0 — Design freeze and control boundaries

Goal: Resolve architecture and claim boundaries before code.

Deliverables
ForgeLedger concept spec.
ForgeCompliance concept spec.
Internal-first / embeddable-later decision.
Event envelope schema.
Claim boundary statement.
Initial framework list and priority.
v0.1 event types.
Test strategy.
Key decisions
Decision	Recommendation
Internal-only or embeddable?	Internal-first, embeddable schema.
Library or bus?	Shared library first, bus-compatible event schema.
Monolith or plugins?	ComplianceCore + sector plugins.
Backend?	JSONL hash-chain first, backend interface from day one.
First frameworks?	NZISM, HIPC/NZ Privacy, RBNZ BS11, Essential Eight, SOC 2, ISO 27001, NIST, APRA CPS 234.
Phase 0 acceptance criteria
Architecture doc approved.
Event schema approved.
Claim boundary approved.
v0.1 event list approved.
Test matrix approved.
Phase 1 — ForgeLedger v0.1: immutable audit trail and retention core

Goal: Create the append-only, tamper-evident ledger with retention classification.

Scope

Build:

LedgerEvent schema.
JSONL backend.
Hash-chain generation.
Chain verification.
Retention policy engine.
Legal hold flag.
Event emitters for CONCORD and ForgeGate.
Basic query/export by time, actor, module, event type.
Unit tests.
Event types in v0.1
concord.admission_decision
forgegate.decision_record
forgegate.policy_evaluation
azul.verdict_summary
warden.llm_call_metadata
agent.tool_call
agent.human_review_required
human.approval_decision
retention.legal_hold_applied
Testing validation
Test	Purpose
test_append_event_creates_hash	Event hash is created deterministically.
test_hash_chain_validates	Valid chain passes.
test_tampered_event_fails_chain_validation	Edited event fails verification.
test_deleted_event_fails_chain_validation	Missing event is detected.
test_reordered_events_fail_validation	Reordered events break chain.
test_retention_class_assigned	Events receive correct retention class.
test_legal_hold_blocks_deletion	Legal hold prevents deletion/export purge.
test_policy_hash_recorded	Policy hash is stored on each decision event.
test_concord_event_ingested	CONCORD emits valid event.
test_forgegate_decision_ingested	ForgeGate DecisionRecord maps into ledger schema.
Phase 1 acceptance criteria
All ledger events are append-only.
Hash-chain validation works.
Tampering is detected.
CONCORD and ForgeGate can emit events.
Every event receives a retention class.
Legal hold can be applied.
Basic evidence slice export works.
Phase 2 — ForgeCompliance v0.2: control mapping and evidence gap analysis

Goal: Map ledger events to control-aligned evidence requirements.

Scope

Build:

Control registry.
Framework mapping YAMLs.
Mapping validator.
Gap analyzer.
Evidence coverage report.
Initial plugins:
nz_government.py
nz_health.py
nz_finance.py
generic_soc2.py
generic_iso27001.py
generic_nist.py
Framework mapping principle

Each mapping should include:

control objective,
required event types,
required fields,
recommended evidence artifacts,
retention expectation,
claim boundary,
confidence level of mapping.
Testing validation
Test	Purpose
test_mapping_yaml_schema_valid	All mappings conform to schema.
test_event_type_maps_to_controls	Ledger event receives expected control tags.
test_required_fields_present	Missing required audit fields detected.
test_gap_report_detects_missing_event_type	Missing evidence produces gap.
test_gap_report_detects_missing_required_field	Missing actor/policy/hash detected.
test_plugin_retention_overrides_core_policy	Sector plugin overrides default retention correctly.
test_claim_boundary_present	Every mapping includes “not certification” boundary.
Phase 2 acceptance criteria
Ledger events can be mapped to control IDs.
Missing control evidence is detected.
Control coverage report is generated.
At least three framework profiles work end-to-end:
NZISM,
HIPC/NZ Health,
SOC 2 or ISO 27001.
Phase 3 — Evidence package generation

Goal: Generate auditor-consumable evidence bundles.

Evidence package contents
evidence_package/
  manifest.json
  package_hash.txt
  ledger_slice.jsonl
  chain_validation_report.json
  control_coverage_report.json
  retention_policy_report.json
  legal_hold_report.json
  event_type_summary.csv
  evidence_gap_report.json
  human_review_decisions.json
  model_provider_boundary_report.json
  README_AUDITOR.md
Evidence package manifest
{
  "package_id": "uuid",
  "created_at": "2026-04-28T00:00:00Z",
  "framework_profiles": ["NZISM", "SOC2", "ISO27001"],
  "time_range": {
    "from": "2026-04-01T00:00:00Z",
    "to": "2026-04-28T00:00:00Z"
  },
  "event_count": 1432,
  "chain_valid": true,
  "retention_policy_valid": true,
  "open_gaps": 3,
  "claim_boundary": "This package provides control-aligned evidence support and is not a certification of compliance."
}
Testing validation
Test	Purpose
test_package_manifest_created	Package has required manifest.
test_package_hash_verifies	Package hash detects tampering.
test_package_contains_chain_report	Chain validation included.
test_package_contains_gap_report	Gaps included.
test_package_redacts_sensitive_prompts	Sensitive prompts removed or hashed.
test_package_exports_control_coverage	Control coverage summary generated.
test_package_readme_contains_claim_boundary	Auditor README avoids compliance overclaiming.
Phase 3 acceptance criteria
Evidence package can be generated for one time window.
Package includes chain validation.
Package includes framework coverage.
Package includes gaps.
Package redacts or hashes sensitive fields according to policy.
Package is suitable for review by a non-developer auditor/risk owner.
Phase 4 — WORM backend and production storage abstraction

Goal: Support production-grade immutable storage patterns.

Scope
LedgerBackend interface finalized.
Local JSONL backend remains default.
Add S3-compatible Object Lock backend or Azure Immutable Blob backend.
Add backend health checks.
Add write-failure handling.
Add local fallback policy.
Add backend migration/export tool.
Testing validation
Test	Purpose
test_backend_interface_contract	All backends satisfy interface.
test_backend_append_idempotency	Duplicate event handling defined.
test_backend_write_failure_fails_closed	Ledger failure does not silently continue.
test_worm_backend_rejects_mutation	Immutability enforced where supported.
test_backend_health_report	Backend health emits audit event.
test_export_import_preserves_hash_chain	Migration preserves event integrity.
Phase 4 acceptance criteria
Backend interface stable.
At least one WORM-capable backend implemented or stubbed.
Ledger write failure policy is explicit.
Chain integrity survives export/import.
Production deployment profile documented.
Phase 5 — Embeddable SDK and event bus compatibility

Goal: Allow downstream systems to emit ForgeLedger events without importing full ForgeRoot.

Scope
Lightweight SDK.
Event signing option.
HTTP/gRPC ingest endpoint or queue-compatible envelope.
Replay protection.
Tenant API keys or mTLS boundary.
Event bus compatibility with the same schema.
API examples
client.emit_event(
    event_type="downstream.agent.recommendation",
    actor_id="partner_agent_001",
    tenant_id="msp_customer_a",
    decision_type="review",
    evidence_refs=["doc:policy#7"],
    control_tags=["SOC2.SECURITY", "NZISM.LOGGING"]
)
Testing validation
Test	Purpose
test_sdk_emits_valid_event	SDK event validates against schema.
test_invalid_event_rejected	Bad schema rejected.
test_replay_event_rejected	Replay protection works.
test_signature_validation	Signed events verified.
test_tenant_boundary_enforced	Tenant cannot write to another tenant namespace.
test_bus_payload_matches_library_payload	Bus and direct-call schemas match.
Phase 5 acceptance criteria
Downstream systems can emit events.
Events preserve tenant boundary.
Replay and signature controls exist.
SDK does not expose full ForgeRoot internals.
Event bus migration path is proven.
Phase 6 — Demo integration with ForgeRoot Governed Agent Demo

Goal: Show the compliance harness working inside the client-facing demo.

Demo scenario

User asks:

“Design a 2PB local backup environment for a regulated customer with ransomware resilience, Veeam compatibility, local jurisdiction control, and a path to 10PB.”

The agent produces:

answer,
evidence citations,
assumptions,
evidence gaps,
human-review trigger,
policy decision,
governance receipt,
ledger entries,
control mapping,
compliance evidence package.
Demo UI panels
Agent response.
Evidence used.
Assertion classes.
Evidence gaps.
Policy decision.
Ledger event timeline.
Hash-chain validation status.
Control coverage map.
Retention class.
Export evidence package.
Testing validation
Test	Purpose
test_demo_query_generates_ledger_events	Demo emits expected event sequence.
test_high_risk_design_requires_review	High-impact recommendation escalates.
test_control_coverage_generated	Framework tags produced.
test_evidence_package_exported_from_demo	Export works from UI/backend.
test_no_raw_sensitive_prompt_in_package_when_policy_blocks	Redaction works.
Phase 6 acceptance criteria
Demo shows business value clearly.
Non-technical viewer can understand audit trail.
Technical viewer can inspect JSON evidence.
Compliance/risk viewer sees control coverage and gaps.
The system avoids compliance overclaiming.
8. Validation strategy: what must be proven

The harness should prove five classes of properties.

A. Integrity properties
Property	Validation
Append-only behavior	Attempt update/delete and verify failure or detection.
Tamper evidence	Modify event and verify chain invalid.
Event ordering	Reorder events and verify chain invalid.
Policy version traceability	Every policy decision includes policy hash.
Package integrity	Evidence package hash validates contents.
B. Governance properties
Property	Validation
Every agent action has an event	Event sequence completeness test.
Every decision has a reason	Schema required field.
High-risk action triggers review	Policy test.
Human approval is recorded	Approval event required.
Denied action cannot proceed silently	Fail-closed test.
C. Evidence properties
Property	Validation
Evidence references are present	Receipt validation.
Unsupported claims create gaps	Sparse corpus test.
Assertion classes are recorded	FACT/DERIVED/RECOMMENDATION etc.
Evidence gaps affect confidence	Confidence degradation test.
Evidence package contains source traceability	Export validation.
D. Retention properties
Property	Validation
Retention class assigned	Required field.
Sector plugin can override retention	Plugin test.
Legal hold blocks deletion	Legal hold test.
Expired operational records can be purged	Retention purge test.
Sensitive content can be hashed/redacted	Privacy retention test.
E. Compliance-mapping properties
Property	Validation
Events map to control IDs	Mapping test.
Missing control evidence is detected	Gap analyzer test.
Framework mappings are schema-valid	YAML schema test.
Claim boundary is present	Text/metadata test.
Coverage report is reproducible	Snapshot test.
9. Minimal v0.1 file structure
forgeroot/
  forgeledger/
    __init__.py
    schema.py
    canonical_json.py
    hash_chain.py
    backend.py
    jsonl_backend.py
    retention.py
    legal_hold.py
    emitter.py
    validators.py
    export.py
    config/
      retention_policies.yaml
    tests/
      test_schema.py
      test_hash_chain.py
      test_jsonl_backend.py
      test_retention.py
      test_legal_hold.py

  forgecompliance/
    __init__.py
    control_registry.py
    mapping_schema.py
    mapper.py
    gap_analyzer.py
    evidence_package.py
    reports.py
    plugins/
      base.py
      nz_government.py
      nz_health.py
      nz_finance.py
      generic_soc2.py
      generic_iso27001.py
      generic_nist.py
    mappings/
      nzism.yaml
      hipc_2020.yaml
      rbnz_bs11.yaml
      soc2_tsc.yaml
      iso27001_2022.yaml
      nist_csf_2_0.yaml
    tests/
      test_mapping_schema.py
      test_mapper.py
      test_gap_analyzer.py
      test_evidence_package.py
      test_plugins.py

  integrations/
    concord_ledger_adapter.py
    forgegate_ledger_adapter.py
    azul_ledger_adapter.py
    warden_ledger_adapter.py