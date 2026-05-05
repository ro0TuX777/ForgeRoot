# Graph Report - .  (2026-05-04)

## Corpus Check
- Corpus is ~8,030 words - fits in a single context window. You may not need a graph.

## Summary
- 152 nodes · 354 edges · 12 communities detected
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 50 edges (avg confidence: 0.62)
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

## God Nodes (most connected - your core abstractions)
1. `LLMGateway` - 40 edges
2. `FederationWarden` - 34 edges
3. `RemediationAgent` - 21 edges
4. `GatewayError` - 19 edges
5. `main()` - 13 edges
6. `_azul_data_dir()` - 11 edges
7. `_now_iso()` - 10 edges
8. `GatewayResponse` - 10 edges
9. `_build_daemon()` - 9 edges
10. `FakeGateway` - 9 edges

## Surprising Connections (you probably didn't know these)
- `WardenConfig` --uses--> `GatewayError`  [INFERRED]
  daemon.py → llm_gateway.py
- `WardenConfig` --uses--> `LLMGateway`  [INFERRED]
  daemon.py → llm_gateway.py
- `WardenConfig` --uses--> `RemediationAgent`  [INFERRED]
  daemon.py → remediation_agent.py
- `FederationWarden` --uses--> `GatewayError`  [INFERRED]
  daemon.py → llm_gateway.py
- `FederationWarden` --uses--> `LLMGateway`  [INFERRED]
  daemon.py → llm_gateway.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.14
Nodes (11): Federation Warden daemon: watch code, trigger scan/assess, draft contract stubs., Ensure DAWN project inputs path exists and contains current watched files., Requeue tickets stuck in PROVISIONING/EVALUATING from previous runs.         Thi, GatewayError, LLMGateway, Raised when all provider attempts fail., Routes requests by task tier with deterministic fallback ordering., Return lightweight provider health for cockpit ignition checks. (+3 more)

### Community 1 - "Community 1"
Cohesion: 0.2
Nodes (3): FederationWarden, _load_json(), _now_iso()

### Community 2 - "Community 2"
Cohesion: 0.15
Nodes (14): RuntimeError, FakeGateway, test_generate_draft_uses_planner_then_worker(), test_reject_loop_attempts_fix_until_pass(), test_reject_loop_can_start_from_known_reject_without_duplicate_verify(), GatewayResponse, Model response plus audit trace., DraftArtifact (+6 more)

### Community 3 - "Community 3"
Cohesion: 0.13
Nodes (3): _detect_changes(), _extract_ticket_id(), _read_text_file()

### Community 4 - "Community 4"
Cohesion: 0.24
Nodes (10): _build_daemon(), test_changed_file_patch_generation_uses_snapshot_baseline(), test_enqueue_remediation_creates_human_review_record_without_apply(), test_remediation_status_and_review_flow(), test_startup_requeue_for_stuck_azul_tickets(), test_daemon_yaml_helpers(), test_gateway_provider_order(), WardenConfig (+2 more)

### Community 5 - "Community 5"
Cohesion: 0.2
Nodes (7): classify_intent(), _dedupe(), from_env(), Hybrid fuel LLM gateway with local/cloud routing and reasoning traces., Trace metadata returned for every gateway request., Generate text routed by intent description rather than explicit tier.          C, ReasoningTrace

### Community 6 - "Community 6"
Cohesion: 0.33
Nodes (9): _build_parser(), default_forge_root(), from_args(), load_runtime_status(), main(), _pid_is_running(), _print_json(), start_daemon_process() (+1 more)

### Community 7 - "Community 7"
Cohesion: 0.29
Nodes (4): default_project_id(), _extract_yaml_block(), _is_stub_valid(), _slug()

### Community 8 - "Community 8"
Cohesion: 0.33
Nodes (6): _azul_data_dir(), list_remediation_queue(), remediation_desk_patches_dir(), remediation_desk_pending_dir(), remediation_desk_reviewed_dir(), review_remediation_item()

### Community 9 - "Community 9"
Cohesion: 0.4
Nodes (4): test_approve_stub_records_gold_label_and_baseline(), approve_stub_file(), _contract_baseline_path(), _snapshot_contract_baseline()

### Community 10 - "Community 10"
Cohesion: 1.0
Nodes (1): Federation Warden package.

### Community 11 - "Community 11"
Cohesion: 1.0
Nodes (1): Map a natural language intent description to the best task tier.          Allows

## Knowledge Gaps
- **13 isolated node(s):** `Hybrid fuel LLM gateway with local/cloud routing and reasoning traces.`, `Raised when all provider attempts fail.`, `Trace metadata returned for every gateway request.`, `Model response plus audit trace.`, `Runtime config sourced from environment variables.` (+8 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 10`** (2 nodes): `__init__.py`, `Federation Warden package.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 11`** (1 nodes): `Map a natural language intent description to the best task tier.          Allows`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `FederationWarden` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 4`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.337) - this node is a cross-community bridge._
- **Why does `LLMGateway` connect `Community 0` to `Community 1`, `Community 2`, `Community 4`, `Community 5`?**
  _High betweenness centrality (0.325) - this node is a cross-community bridge._
- **Why does `RemediationAgent` connect `Community 2` to `Community 0`, `Community 1`, `Community 4`?**
  _High betweenness centrality (0.151) - this node is a cross-community bridge._
- **Are the 13 inferred relationships involving `LLMGateway` (e.g. with `WardenConfig` and `FederationWarden`) actually correct?**
  _`LLMGateway` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `FederationWarden` (e.g. with `GatewayError` and `LLMGateway`) actually correct?**
  _`FederationWarden` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `RemediationAgent` (e.g. with `WardenConfig` and `FederationWarden`) actually correct?**
  _`RemediationAgent` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `GatewayError` (e.g. with `WardenConfig` and `FederationWarden`) actually correct?**
  _`GatewayError` has 9 INFERRED edges - model-reasoned connections that need verification._