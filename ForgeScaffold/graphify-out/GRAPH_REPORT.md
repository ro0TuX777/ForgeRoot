# Graph Report - .  (2026-05-04)

## Corpus Check
- 96 files · ~31,759 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 671 nodes · 993 edges · 86 communities detected
- Extraction: 88% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 37 edges (avg confidence: 0.79)
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
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]

## God Nodes (most connected - your core abstractions)
1. `forgescaffold.package_evidence` - 22 edges
2. `forgescaffold.test_matrix` - 17 edges
3. `forgescaffold.obs_instrument_patchset` - 16 edges
4. `forgescaffold.verify_post_apply` - 16 edges
5. `forgescaffold_apply_v5_risk_index` - 16 edges
6. `forgescaffold_apply_v5_risk_index_runnable` - 16 edges
7. `forgescaffold_apply_v4_review_hitl` - 14 edges
8. `forgescaffold_apply_v4_review_hitl_runnable` - 14 edges
9. `forgescaffold.verify_evidence` - 13 edges
10. `forgescaffold.map_dataflow` - 13 edges

## Surprising Connections (you probably didn't know these)
- `ingest.project_bundle (DAWN stock link)` --semantically_similar_to--> `ingest.project_bundle`  [INFERRED] [semantically similar]
  docs/ARCHITECTURE.md → dawn_extensions/pipelines/forgescaffold_blueprint.yaml
- `forgescaffold.system_catalog` --semantically_similar_to--> `forgescaffold.system_catalog`  [INFERRED] [semantically similar]
  docs/ARCHITECTURE.md → dawn_extensions/pipelines/forgescaffold_blueprint.yaml
- `Cross-project evidence query` --semantically_similar_to--> `forgescaffold.query_global_evidence`  [INFERRED] [semantically similar]
  docs/examples/forgescaffold_phase12_ci/README_PHASE12.md → dawn_extensions/pipelines/forgescaffold_global_ops_v10.yaml
- `run()` --calls--> `load_policy()`  [INFERRED]
  dawn_extensions\links\forgescaffold.apply_patchset\run.py → dawn_extensions\links\forgescaffold_common\lock_utils.py
- `_trusted_policy_hash()` --calls--> `policy_snapshot_hash()`  [INFERRED]
  dawn_extensions\links\forgescaffold.build_global_catalog\run.py → dawn_extensions\links\forgescaffold_common\index_utils.py

## Hyperedges (group relationships)
- **SQLite evidence index cache build and verify** — forgescaffold_build_all_caches_run, forgescaffold_build_index_cache_run, forgescaffold_query_evidence_index_run, forgescaffold_verify_cache_integrity_run, artifact_evidence_cache_sqlite [0.82]
- **Hash-chained index with optional signed checkpoints** — forgescaffold_update_evidence_index_run, index_utils_append_index_entry, index_utils_verify_index_chain, forgescaffold_verify_index_integrity_run, forgescaffold_write_index_checkpoint_run [0.9]
- **Global catalog aggregates per-project indices** — forgescaffold_build_global_catalog_run, forgescaffold_query_global_evidence_run, forgescaffold_status_global_run [0.84]
- **obs_define_schema_publish_pair** — obs_define_schema_run, art_log_envelope_schema, art_obs_recommendations [0.95]
- **instrumentation_patchset_data_sources** — obs_instrument_patchset_run, art_system_catalog, bund_dawn_project, art_instr_patchset [0.94]
- **test_matrix_feeds_verify_post_apply** — test_matrix_run, verify_post_apply_run, art_test_matrix_yaml, art_verify_report [0.93]
- **runner_scaffolding_exports** — scaffolding_init, class_ForgeScaffoldCodingContext, fn_generate_test_matrix, fn_validate_code_proposal, fn_create_patchset, fn_stamp_ticket_event, fn_get_ticket_evidence [0.97]
- **Catalog to instrumentation patchset chain** — lnk_forgescaffold_system_catalog, lnk_forgescaffold_map_dataflow, lnk_forgescaffold_obs_define_schema, lnk_forgescaffold_obs_instrument_patchset [EXTRACTED 1.00]
- **Evidence index cache and checkpoint writers** — lnk_forgescaffold_verify_cache_integrity, lnk_forgescaffold_verify_index_integrity, lnk_forgescaffold_write_compaction_summary, lnk_forgescaffold_write_index_checkpoint [INFERRED 0.72]
- **Test matrix drives post-apply verification** — lnk_forgescaffold_test_matrix, lnk_forgescaffold_verify_post_apply, art_forgescaffold_verification_report_json [EXTRACTED 1.00]
- **Blueprint Phase 1 link chain** — forgescaffold_blueprint_ingest_project_bundle, forgescaffold_blueprint_forgescaffold_system_catalog, forgescaffold_blueprint_forgescaffold_map_dataflow, forgescaffold_blueprint_forgescaffold_test_matrix [EXTRACTED 1.00]
- **Apply v9 cache pipeline tail (cache, checkpoint, integrity, status)** — forgescaffold_apply_v9_cache_forgescaffold_build_index_cache, forgescaffold_apply_v9_cache_forgescaffold_verify_cache_integrity, forgescaffold_apply_v9_cache_forgescaffold_write_index_checkpoint, forgescaffold_apply_v9_cache_forgescaffold_verify_index_integrity, forgescaffold_apply_v9_cache_forgescaffold_status [EXTRACTED 1.00]
- **Phase 12 fleet ops artifact family** — phase12_global_catalog, phase12_query_global_evidence, phase12_status_markdown, forgescaffold_global_ops_v10_forgescaffold_build_global_catalog [INFERRED 0.68]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (45): _build_db(), _cache_meta(), _latest_checkpoint(), _load_policy(), run(), _build_db(), _cache_meta_from_db(), _latest_checkpoint() (+37 more)

### Community 1 - "Community 1"
Cohesion: 0.17
Nodes (46): dawn.project.bundle, forgescaffold.apply_report.json, forgescaffold.approval_receipt.json, forgescaffold.dataflow_map.json, forgescaffold.evidence_manifest.json, forgescaffold.evidence_pack.manifest.json, forgescaffold.evidence_receipt.json, forgescaffold.evidence_signature.json (+38 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (36): forgescaffold.apply_patchset, forgescaffold.gate_patchset_approval, forgescaffold.generate_approval_template, forgescaffold.generate_review_packet, forgescaffold.map_dataflow, forgescaffold.obs_define_schema, forgescaffold.obs_instrument_patchset, forgescaffold.package_evidence (+28 more)

### Community 3 - "Community 3"
Cohesion: 0.12
Nodes (30): _apply_action(), _apply_operation(), _build_rollback(), _build_rollback_hunk(), _compute_inputs_fingerprint(), _detect_newline_style(), _find_anchor(), _index_to_line() (+22 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (19): ForgeScaffoldCodingContext, _import_fs_module(), ForgeScaffold Coding Context ==============================  Provides every SAM, Find catalog units whose path contains the target file., Find all modules that import from (or are imported by) the target file., Returns a Markdown block ready to prepend to the Coder LLM prompt.         Keeps, Dynamically import a ForgeScaffold run.py as a module., Pre-flight coding context loader for SAM's Coder LLM.      Usage:         ctx = (+11 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (27): forgescaffold.instrumentation.patchset.json, forgescaffold.log_envelope.schema.json, forgescaffold.observability_recommendations.md, forgescaffold.system_catalog.json, forgescaffold.test_harness.manifest.json, forgescaffold.test_matrix.yaml, forgescaffold.test_results.manifest.json, forgescaffold.verification_report.json (+19 more)

### Community 6 - "Community 6"
Cohesion: 0.08
Nodes (25): forgescaffold.apply_patchset, forgescaffold.build_index_cache, forgescaffold.gate_patchset_approval, forgescaffold.generate_approval_template, forgescaffold.generate_review_packet, forgescaffold.map_dataflow, forgescaffold.obs_define_schema, forgescaffold.obs_instrument_patchset (+17 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (22): forgescaffold.apply_patchset, forgescaffold.build_index_cache, forgescaffold.gate_patchset_approval, forgescaffold.generate_approval_template, forgescaffold.generate_review_packet, forgescaffold.map_dataflow, forgescaffold.obs_define_schema, forgescaffold.obs_instrument_patchset (+14 more)

### Community 8 - "Community 8"
Cohesion: 0.21
Nodes (20): _apply_action(), _apply_operation(), _build_rollback(), _build_rollback_hunk(), _compute_inputs_fingerprint(), _detect_newline_style(), _find_anchor(), _index_to_line() (+12 more)

### Community 9 - "Community 9"
Cohesion: 0.18
Nodes (20): evidence_index_cache.sqlite, evidence_index.jsonl, forgescaffold.build_all_caches.run, forgescaffold.build_global_catalog.run, forgescaffold.build_index_cache.run, forgescaffold.update_evidence_index.run, forgescaffold.verify_cache_integrity.run, forgescaffold.verify_index_integrity.run (+12 more)

### Community 10 - "Community 10"
Cohesion: 0.1
Nodes (20): forgescaffold.apply_patchset, forgescaffold.gate_patchset_approval, forgescaffold.generate_approval_template, forgescaffold.generate_review_packet, forgescaffold.map_dataflow, forgescaffold.obs_define_schema, forgescaffold.obs_instrument_patchset, forgescaffold.package_evidence (+12 more)

### Community 11 - "Community 11"
Cohesion: 0.1
Nodes (20): forgescaffold.apply_patchset, forgescaffold.gate_patchset_approval, forgescaffold.generate_approval_template, forgescaffold.generate_review_packet, forgescaffold.map_dataflow, forgescaffold.obs_define_schema, forgescaffold.obs_instrument_patchset, forgescaffold.package_evidence (+12 more)

### Community 12 - "Community 12"
Cohesion: 0.11
Nodes (18): forgescaffold.apply_patchset, forgescaffold.gate_patchset_approval, forgescaffold.generate_approval_template, forgescaffold.generate_review_packet, forgescaffold.map_dataflow, forgescaffold.obs_define_schema, forgescaffold.obs_instrument_patchset, forgescaffold.package_evidence (+10 more)

### Community 13 - "Community 13"
Cohesion: 0.11
Nodes (18): forgescaffold.apply_patchset, forgescaffold.gate_patchset_approval, forgescaffold.generate_approval_template, forgescaffold.generate_review_packet, forgescaffold.map_dataflow, forgescaffold.obs_define_schema, forgescaffold.obs_instrument_patchset, forgescaffold.package_evidence (+10 more)

### Community 14 - "Community 14"
Cohesion: 0.25
Nodes (15): _apply_action(), _apply_operation(), _detect_newline_style(), _find_anchor(), _line_range_to_indices(), _load_artifact(), _normalize_newlines(), _read_bytes() (+7 more)

### Community 15 - "Community 15"
Cohesion: 0.35
Nodes (11): _canonical_json(), _latest_checkpoint(), _load_index_lines(), _load_policy(), _load_private_key_from_text(), _load_private_keys(), _policy_snapshot_hash(), _resolve_checkpoint_dir() (+3 more)

### Community 16 - "Community 16"
Cohesion: 0.21
Nodes (11): create_patchset(), _ensure_project_dir(), get_ticket_evidence(), ForgeScaffold Adapter for SAM ==============================  Bridges SAM's Evol, Run the ForgeScaffold gated apply pipeline via the CLI.          Returns the app, Append an event to the ForgeScaffold ticket_events.jsonl ledger for a SAM ticket, Read all ForgeScaffold evidence for a given SAM ticket ID.     Used by the UI to, Ensure the ForgeScaffold DAWN project directory exists. (+3 more)

### Community 17 - "Community 17"
Cohesion: 0.35
Nodes (10): _canonical_json(), _is_trusted(), _load_artifact(), _load_policy(), _load_trusted_signers(), _parse_datetime(), _required_signatures(), run() (+2 more)

### Community 18 - "Community 18"
Cohesion: 0.35
Nodes (10): add_edge(), build_external_index(), extract_imports_from_file(), gather_module_sources(), load_catalog(), load_text(), match_module(), readable_relpath() (+2 more)

### Community 19 - "Community 19"
Cohesion: 0.38
Nodes (9): _cache_meta(), _latest_checkpoint(), _load_policy(), _load_private_keys(), _load_trusted_signers(), _parse_datetime(), run(), _sha256_bytes() (+1 more)

### Community 20 - "Community 20"
Cohesion: 0.4
Nodes (9): _cache_meta(), _cache_up_to_date(), _index_meta(), _load_index(), _matches(), _parse_datetime(), _query_cache(), _render_md() (+1 more)

### Community 21 - "Community 21"
Cohesion: 0.33
Nodes (8): assemble_units(), collect_agent_units(), collect_datastores(), collect_external_deps(), collect_service_units(), readable_relpath(), register_schema(), run()

### Community 22 - "Community 22"
Cohesion: 0.44
Nodes (8): _load_artifact(), _load_policy(), _normalize_approvers(), _overall_risk(), _parse_datetime(), _risk_defaults(), run(), _validate_approval()

### Community 23 - "Community 23"
Cohesion: 0.42
Nodes (8): _diff_preview(), _load_artifact(), _load_policy(), _overall_risk(), _required_signatures(), _risk_for_path(), run(), _sha256_text()

### Community 24 - "Community 24"
Cohesion: 0.39
Nodes (7): _build_modify_op(), _detect_entrypoint_patch(), _load_artifact(), _logger_wrapper_content(), register_schema(), run(), _sha256_text()

### Community 25 - "Community 25"
Cohesion: 0.22
Nodes (9): map_dataflow.add_edge, map_dataflow.build_external_index, map_dataflow.extract_imports_from_file, map_dataflow.gather_module_sources, map_dataflow.load_catalog, map_dataflow.load_text, map_dataflow.match_module, map_dataflow.register_schema (+1 more)

### Community 26 - "Community 26"
Cohesion: 0.22
Nodes (9): ingest.project_bundle (DAWN stock link), forgescaffold.system_catalog, forgescaffold.system_catalog.json, forgescaffold.map_dataflow, forgescaffold.system_catalog, forgescaffold.test_matrix, ingest.project_bundle, forgescaffold blueprint (+1 more)

### Community 27 - "Community 27"
Cohesion: 0.46
Nodes (7): _load_catalog(), _load_index(), _load_policy(), _load_trusted_signers(), _parse_datetime(), _render_md(), run()

### Community 28 - "Community 28"
Cohesion: 0.46
Nodes (7): _extract_pytest_target(), _extract_python_import(), _load_artifact(), _preflight_check(), _python_importable(), run(), _run_command()

### Community 29 - "Community 29"
Cohesion: 0.29
Nodes (8): apply_patchset.run, forgescaffold.instrumentation.patchset.json, forgescaffold.apply_patchset.run, forgescaffold.gate_patchset_approval.run, forgescaffold.verify_rollback.run, lock_utils.acquire_lock, lock_utils.load_policy, lock_utils.lock_path_for_project

### Community 30 - "Community 30"
Cohesion: 0.52
Nodes (6): _load_artifact(), _load_policy(), _required_from_risk(), _required_signatures(), _risk_defaults(), run()

### Community 31 - "Community 31"
Cohesion: 0.52
Nodes (6): _load_catalog(), _load_index(), _matches(), _parse_datetime(), _query_cache(), run()

### Community 32 - "Community 32"
Cohesion: 0.52
Nodes (6): _canonical_json(), _load_artifact(), _load_private_key_from_text(), _load_private_keys(), run(), _sha256_bytes()

### Community 33 - "Community 33"
Cohesion: 0.52
Nodes (6): build_command(), escape_literal(), load_artifact(), register_schema(), run(), write_harness()

### Community 34 - "Community 34"
Cohesion: 0.29
Nodes (7): forgescaffold.map_dataflow, forgescaffold.obs_define_schema, forgescaffold.obs_instrument_patchset, forgescaffold.system_catalog, forgescaffold.test_matrix, ingest.project_bundle, forgescaffold blueprint v2

### Community 35 - "Community 35"
Cohesion: 0.6
Nodes (5): _load_index(), _load_policy(), _load_trusted_signers(), _parse_datetime(), run()

### Community 36 - "Community 36"
Cohesion: 0.33
Nodes (6): forgescaffold.build_all_caches, forgescaffold.build_global_catalog, forgescaffold.query_global_evidence, forgescaffold.status_global, forgescaffold global ops v10, Cross-project evidence query

### Community 37 - "Community 37"
Cohesion: 0.7
Nodes (4): _load_index(), _load_policy(), _parse_datetime(), run()

### Community 38 - "Community 38"
Cohesion: 0.83
Nodes (3): build_recommendations(), register_schema(), run()

### Community 39 - "Community 39"
Cohesion: 0.67
Nodes (2): _copy_file(), run()

### Community 40 - "Community 40"
Cohesion: 0.67
Nodes (4): sig1, sig2, policy.trusted.signers, trusted.signers.yaml

### Community 41 - "Community 41"
Cohesion: 0.5
Nodes (4): forgescaffold.cache_integrity_report.json, forgescaffold.index_integrity_report.json, forgescaffold.verify_cache_integrity, forgescaffold.verify_index_integrity

### Community 42 - "Community 42"
Cohesion: 0.67
Nodes (3): forgescaffold.status_global.json, forgescaffold.status_global.md, forgescaffold.status_global

### Community 43 - "Community 43"
Cohesion: 0.67
Nodes (3): forgescaffold.compaction_summary.json, forgescaffold.compaction_summary.signature.json, forgescaffold.write_compaction_summary

### Community 44 - "Community 44"
Cohesion: 0.67
Nodes (3): forgescaffold.index_checkpoint.json, forgescaffold.index_checkpoint.signature.json, forgescaffold.write_index_checkpoint

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (2): forgescaffold.evidence_manifest.json, forgescaffold.sign_evidence

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (2): forgescaffold.evidence_pack.manifest.json, package.evidence.run

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (2): forgescaffold.map_dataflow, forgescaffold.dataflow_map.json

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (2): Deterministic outputs policy, scripts/verify_forgescaffold_phase1.py

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (2): forgescaffold.query_evidence_index, Configurable evidence index query

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): forgescaffold.generate_approval_template.run

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): forgescaffold.generate_review_packet.run

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): forgescaffold.prune_evidence.run

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): forgescaffold.query_evidence_index.run

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): forgescaffold.query_global_evidence.run

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (1): forgescaffold.sign_evidence.run

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (1): forgescaffold.status.run

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (1): forgescaffold.status_global.run

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (1): forgescaffold.verify_evidence.run

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (1): forgescaffold.adapter

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (1): apply.patchset.link.yaml

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (1): forgescaffold.build_all_caches

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (1): forgescaffold.build_global_catalog

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (1): forgescaffold.build_index_cache

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (1): forgescaffold.generate_approval_template

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (1): forgescaffold.prune_evidence

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (1): forgescaffold.query_evidence_index

### Community 67 - "Community 67"
Cohesion: 1.0
Nodes (1): forgescaffold.query_global_evidence

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (1): forgescaffold.status

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (1): run_apply_pipeline

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (1): ForgeScaffold as DAWN-native blueprint runner

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (1): forgescaffold.test_matrix (L0-L3 checklist)

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (1): forgescaffold.test_matrix.yaml

### Community 73 - "Community 73"
Cohesion: 1.0
Nodes (1): artifact_index.json registration

### Community 74 - "Community 74"
Cohesion: 1.0
Nodes (1): Units abstraction (monolith/mesh/agent)

### Community 75 - "Community 75"
Cohesion: 1.0
Nodes (1): Dark Code Layer 2 catalog semantics

### Community 76 - "Community 76"
Cohesion: 1.0
Nodes (1): DAWN Link contract

### Community 77 - "Community 77"
Cohesion: 1.0
Nodes (1): DAWN Ledger (events.jsonl)

### Community 78 - "Community 78"
Cohesion: 1.0
Nodes (1): Blueprint generation Phase 1

### Community 79 - "Community 79"
Cohesion: 1.0
Nodes (1): verify_cache_integrity reports

### Community 80 - "Community 80"
Cohesion: 1.0
Nodes (1): Global / fleet catalog

### Community 81 - "Community 81"
Cohesion: 1.0
Nodes (1): Operator status view (Phase 12)

### Community 82 - "Community 82"
Cohesion: 1.0
Nodes (1): Per-project apply lock

### Community 83 - "Community 83"
Cohesion: 1.0
Nodes (1): used_approvals.jsonl replay guard

### Community 84 - "Community 84"
Cohesion: 1.0
Nodes (1): Phase 9 status snapshot

### Community 85 - "Community 85"
Cohesion: 1.0
Nodes (1): dawn/policy/trusted_signers.yaml scopes

## Knowledge Gaps
- **81 isolated node(s):** `ForgeScaffold Adapter for SAM ==============================  Bridges SAM's Evol`, `Ensure the ForgeScaffold DAWN project directory exists.`, `Convert a SAM Coder LLM output into a ForgeScaffold patchset artifact.`, `Run the ForgeScaffold gated apply pipeline via the CLI.          Returns the app`, `Append an event to the ForgeScaffold ticket_events.jsonl ledger for a SAM ticket` (+76 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 39`** (4 nodes): `run.py`, `_copy_file()`, `_load_artifact()`, `run()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (2 nodes): `forgescaffold.evidence_manifest.json`, `forgescaffold.sign_evidence`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (2 nodes): `forgescaffold.evidence_pack.manifest.json`, `package.evidence.run`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (2 nodes): `forgescaffold.map_dataflow`, `forgescaffold.dataflow_map.json`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (2 nodes): `Deterministic outputs policy`, `scripts/verify_forgescaffold_phase1.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (2 nodes): `forgescaffold.query_evidence_index`, `Configurable evidence index query`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `forgescaffold.generate_approval_template.run`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `forgescaffold.generate_review_packet.run`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `forgescaffold.prune_evidence.run`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `forgescaffold.query_evidence_index.run`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `forgescaffold.query_global_evidence.run`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `forgescaffold.sign_evidence.run`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `forgescaffold.status.run`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `forgescaffold.status_global.run`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `forgescaffold.verify_evidence.run`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `forgescaffold.adapter`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (1 nodes): `apply.patchset.link.yaml`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (1 nodes): `forgescaffold.build_all_caches`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (1 nodes): `forgescaffold.build_global_catalog`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (1 nodes): `forgescaffold.build_index_cache`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (1 nodes): `forgescaffold.generate_approval_template`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (1 nodes): `forgescaffold.prune_evidence`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (1 nodes): `forgescaffold.query_evidence_index`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (1 nodes): `forgescaffold.query_global_evidence`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (1 nodes): `forgescaffold.status`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (1 nodes): `run_apply_pipeline`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (1 nodes): `ForgeScaffold as DAWN-native blueprint runner`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (1 nodes): `forgescaffold.test_matrix (L0-L3 checklist)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (1 nodes): `forgescaffold.test_matrix.yaml`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (1 nodes): `artifact_index.json registration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (1 nodes): `Units abstraction (monolith/mesh/agent)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (1 nodes): `Dark Code Layer 2 catalog semantics`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (1 nodes): `DAWN Link contract`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 77`** (1 nodes): `DAWN Ledger (events.jsonl)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 78`** (1 nodes): `Blueprint generation Phase 1`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 79`** (1 nodes): `verify_cache_integrity reports`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 80`** (1 nodes): `Global / fleet catalog`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 81`** (1 nodes): `Operator status view (Phase 12)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 82`** (1 nodes): `Per-project apply lock`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 83`** (1 nodes): `used_approvals.jsonl replay guard`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 84`** (1 nodes): `Phase 9 status snapshot`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 85`** (1 nodes): `dawn/policy/trusted_signers.yaml scopes`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run()` connect `Community 3` to `Community 0`?**
  _High betweenness centrality (0.009) - this node is a cross-community bridge._
- **Why does `append_index_entry()` connect `Community 0` to `Community 3`?**
  _High betweenness centrality (0.009) - this node is a cross-community bridge._
- **What connects `ForgeScaffold Adapter for SAM ==============================  Bridges SAM's Evol`, `Ensure the ForgeScaffold DAWN project directory exists.`, `Convert a SAM Coder LLM output into a ForgeScaffold patchset artifact.` to the rest of the system?**
  _81 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.08 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.06 - nodes in this community are weakly interconnected._
- **Should `Community 3` be split into smaller, more focused modules?**
  _Cohesion score 0.12 - nodes in this community are weakly interconnected._
- **Should `Community 4` be split into smaller, more focused modules?**
  _Cohesion score 0.08 - nodes in this community are weakly interconnected._