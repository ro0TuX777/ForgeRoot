# Graph Report - .  (2026-05-04)

## Corpus Check
- Corpus is ~9,987 words - fits in a single context window. You may not need a graph.

## Summary
- 374 nodes · 725 edges · 12 communities detected
- Extraction: 68% EXTRACTED · 32% INFERRED · 0% AMBIGUOUS · INFERRED: 233 edges (avg confidence: 0.66)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 14|Community 14]]

## God Nodes (most connected - your core abstractions)
1. `ControlRegistry` - 74 edges
2. `GapAnalyzer` - 36 edges
3. `EvidencePackageBuilder` - 34 edges
4. `CompliancePlugin` - 25 edges
5. `FrameworkMapper` - 15 edges
6. `_mapping()` - 14 edges
7. `generate_coverage_report()` - 13 edges
8. `_make_event()` - 13 edges
9. `load_framework_profile()` - 12 edges
10. `ForgeCompliance — control mapping, retention validation, evidence gap analysis,` - 12 edges

## Surprising Connections (you probably didn't know these)
- `registry()` --calls--> `ControlRegistry`  [INFERRED]
  tests\test_evidence_package.py → forgecompliance\control_registry.py
- `Event-to-control mapper tests` --references--> `control_coverage_report.json`  [EXTRACTED]
  tests/test_mapper.py → forgecompliance/mappings/nzism.yaml
- `EvidencePackageBuilder` --uses--> `ControlRegistry`  [INFERRED]
  forgecompliance\evidence_package.py → forgecompliance\control_registry.py
- `EvidencePackageBuilder — Phase 3 implementation.  Assembles an auditor-consumabl` --uses--> `ControlRegistry`  [INFERRED]
  forgecompliance\evidence_package.py → forgecompliance\control_registry.py
- `Serialize event to dict, applying retention-driven redaction:     - EPHEMERAL ev` --uses--> `ControlRegistry`  [INFERRED]
  forgecompliance\evidence_package.py → forgecompliance\control_registry.py

## Hyperedges (group relationships)
- **Evidence Package Export Flow** — evidence_package_builder, reports_coverage_report, reports_retention_report, reports_event_type_summary, gap_analyzer_gapanalyzer, evidence_package_manifest, evidence_package_audit_export_event [EXTRACTED 1.00]
- **Framework Mapping Analysis Flow** — mapping_schema_frameworkprofile, mapping_schema_controlmapping, control_registry_controlregistry, mapper_frameworkmapper, gap_analyzer_gapanalyzer, reports_coverage_report [INFERRED 0.86]
- **Sector Retention Plugins** — plugins_complianceplugin, plugins_nz_government, plugins_nz_health, plugins_nz_finance, plugins_au_finance, plugins_generic_soc2, plugins_generic_iso27001, plugins_generic_nist [EXTRACTED 1.00]
- **Shared Non-Certification Claim Boundary** — nzism_framework, apra_cps_234_framework, essential_eight_framework, hipc_2020_framework, iso27001_2022_framework, nist_csf_2_0_framework, rbnz_bs11_framework, soc2_tsc_framework, mappings_claim_boundary [EXTRACTED 1.00]
- **Human Review Evidence Pattern** — mappings_event_agent_human_review_required, mappings_event_human_approval_decision, nzism_human_approval, soc2_tsc_change_management, essential_eight_mfa_human_gate, mappings_human_review_decisions [INFERRED 0.86]
- **Provider Boundary Evidence Pattern** — mappings_event_warden_llm_call_metadata, mappings_model_provider_boundary_report, hipc_2020_storage_security, nist_csf_2_0_provider_monitoring, rbnz_bs11_service_agreement [EXTRACTED 1.00]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (41): _decrypt_bytes(), decrypt_evidence_package(), _derive_aes256_key(), _encrypt_bytes(), EvidencePackageBuilder, EvidencePackageBuilder — Phase 3 implementation.  Assembles an auditor-consumabl, Builds a complete evidence package directory from a set of LedgerEvents.      Us, Write all 12 evidence package files to output_dir.         Returns the manifest (+33 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (49): ControlRegistry, ControlRegistry — loads all framework mapping YAMLs and indexes them for lookup., Return every (framework_id, control) pair across all loaded profiles., Validate every loaded profile. Returns {framework_id: [errors]}., In-memory index of all loaded FrameworkProfiles.      Profiles are keyed by prof, Return all (framework_id, control) pairs that require this event type., ControlCoverage, _field_present() (+41 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (41): ABC, CompliancePlugin, AUFinancePlugin, APRA CPS 234 plugin — Australian finance sector (APRA-regulated entities)., APRA CPS 234: information security capability evidence → audit_7y.         Appli, CompliancePlugin, CompliancePlugin — abstract base for sector/framework-specific behaviour.  Each, Return additional control tags to attach to this event. Default: none. (+33 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (53): CPS234.P15.CAPABILITY, APRA CPS 234 framework profile, CPS234.P24.INCIDENT, CPS234.P18.POLICY, CPS234.P26.TESTING, E8.ADMIN_PRIVILEGES.RESTRICT, E8.APPLICATION_CONTROL, E8.BACKUPS.AUDIT_LOG_INTEGRITY (+45 more)

### Community 4 - "Community 4"
Cohesion: 0.11
Nodes (29): ControlRegistry, ControlRegistry Mapping Provenance Lookup, Ledger Evidence Package Exported Audit Event, EvidencePackageBuilder, Evidence Package AES-256-GCM Encryption, Evidence Package Manifest, Evidence Package Redaction Policy, ControlCoverage (+21 more)

### Community 5 - "Community 5"
Cohesion: 0.21
Nodes (19): active_mappings(), apply_customer_overlay(), generate_mapping_governance_report(), MappingGovernanceReport, Return an overlaid provenance record without mutating the base mapping., validate_mapping_provenance(), _mapping(), test_approved_mapping_requires_reviewer_and_approver() (+11 more)

### Community 6 - "Community 6"
Cohesion: 0.2
Nodes (19): GapAnalyzer, _make_event(), _make_event_missing_field(), Phase 2 tests 3, 4: 3. Missing required fields are detected. 4. Missing event ty, NZISM.LOGGING.EVENT_CAPTURE requires three event types.     Supplying only one →, If events of the required type are present but a required field is empty,     th, Build an event with a top-level field cleared to empty string., NZISM.ACCESS.AUTHORISATION requires concord.admission_decision.     If only forg (+11 more)

### Community 7 - "Community 7"
Cohesion: 0.16
Nodes (14): load_framework_profile(), Load and parse a framework mapping YAML into a FrameworkProfile., Phase 2 tests 1 & 6: 1. All mapping YAML files validate against schema. 6. Every, Every mapping YAML must load cleanly and pass structural validation., Verify all 8 Phase 2 frameworks are present., claim_boundary must be present and must contain the required text., All mappings use exactly the same claim boundary text., test_all_controls_have_required_event_types() (+6 more)

### Community 8 - "Community 8"
Cohesion: 0.32
Nodes (14): CPS234.P28.AUDIT, chain_validation_report.json, ALL_PLUGINS, ALL_PLUGINS registry, AUFinancePlugin, CompliancePlugin, GenericISO27001Plugin, GenericNISTPlugin (+6 more)

### Community 9 - "Community 9"
Cohesion: 0.25
Nodes (8): ISO27001.A5.25.SECURITY_EVENT_ASSESSMENT, ISO 27001:2022 framework profile, ISO27001.A8.15.LOGGING, ISO27001.A8.16.MONITORING, ISO27001.A8.25.SECURE_DEVELOPMENT, ISO27001.A5.3.SEGREGATION_OF_DUTIES, evidence_gap_report.json, ledger_slice.jsonl

### Community 10 - "Community 10"
Cohesion: 1.0
Nodes (1): Return an override RetentionClass for this event, or None to use the         For

### Community 14 - "Community 14"
Cohesion: 1.0
Nodes (1): retention_policy_report.json

## Knowledge Gaps
- **45 isolated node(s):** `Return an overlaid provenance record without mutating the base mapping.`, `Schema for framework mapping YAML files.  Each YAML file describes one complianc`, `Load and parse a framework mapping YAML into a FrameworkProfile.`, `Validate a FrameworkProfile for structural correctness.     Returns a list of er`, `CompliancePlugin — abstract base for sector/framework-specific behaviour.  Each` (+40 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 10`** (1 nodes): `Return an override RetentionClass for this event, or None to use the         For`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 14`** (1 nodes): `retention_policy_report.json`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ControlRegistry` connect `Community 1` to `Community 0`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.279) - this node is a cross-community bridge._
- **Why does `CompliancePlugin` connect `Community 2` to `Community 1`?**
  _High betweenness centrality (0.200) - this node is a cross-community bridge._
- **Why does `ForgeCompliance — control mapping, retention validation, evidence gap analysis,` connect `Community 1` to `Community 2`, `Community 5`, `Community 6`?**
  _High betweenness centrality (0.194) - this node is a cross-community bridge._
- **Are the 62 inferred relationships involving `ControlRegistry` (e.g. with `ControlMapping` and `FrameworkProfile`) actually correct?**
  _`ControlRegistry` has 62 INFERRED edges - model-reasoned connections that need verification._
- **Are the 32 inferred relationships involving `GapAnalyzer` (e.g. with `EvidencePackageBuilder` and `EvidencePackageBuilder — Phase 3 implementation.  Assembles an auditor-consumabl`) actually correct?**
  _`GapAnalyzer` has 32 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `EvidencePackageBuilder` (e.g. with `ControlRegistry` and `GapAnalyzer`) actually correct?**
  _`EvidencePackageBuilder` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `CompliancePlugin` (e.g. with `ForgeCompliance — control mapping, retention validation, evidence gap analysis,` and `AUFinancePlugin`) actually correct?**
  _`CompliancePlugin` has 21 INFERRED edges - model-reasoned connections that need verification._