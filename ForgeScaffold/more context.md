ForgeScaffold Phase 1 — Agent Context Packet (copy/paste)
Role

You are a senior engineer implementing ForgeScaffold as a DAWN-native blueprint generator. Treat the codebase as a deterministic supply chain: strict contracts, frozen inputs, auditable outputs, and idempotent reruns.

Background: DAWN execution model (you must conform)

DAWN runs pipelines (YAML) composed of links (units of work) with explicit requires / produces contracts.

DAWN tracks outputs in projects/<project>/artifact_index.json and writes an immutable event trail to projects/<project>/ledger/events.jsonl.

Links are created via the factory and live under dawn/links/<link_id>/ with link.yaml + run.py.

CLI usage pattern: python3 -m dawn.runtime.main --project <id> --pipeline dawn/pipelines/<x>.yaml.

Mission (Phase 1)

Build a blueprint runner that can map a target codebase into:

a System Catalog (what exists)

a Dataflow Map (how it connects)

a Test Matrix (how we prove each module/service/agent-step works)

This blueprint must be portable across three architecture types:

Monolith (modules/packages)

Service mesh (services + APIs/events)

Local agent codebase (agent steps/tools/workflow nodes)

Phase 1 Deliverables (Definition of Done)

Implement 3 new DAWN links + 1 pipeline + 1 verifier script.

Links (new)

Create these link IDs (namespacing matters):

forgescaffold.system_catalog

forgescaffold.map_dataflow

forgescaffold.test_matrix

Each link must:

enforce requires / produces in link.yaml (contracts)

write outputs via DAWN mechanisms (artifact_store / sandbox)

emit logs suitable for DAWN streaming + ledger traceability

be deterministic (same snapshot → same artifacts)

be safe (no network calls; only local file reads under project workspace unless explicitly approved)

Reference patterns:

Link YAML structure uses apiVersion: dawn.links/v1, kind: Link, metadata.name, spec.requires, spec.produces, and a standard step chain.

Link run.py signature commonly looks like run(project_context, link_config) and writes artifacts with artifact_store.write_artifact(...) or context["sandbox"].write_json(...).

Pipeline (new)

Add: dawn/pipelines/forgescaffold_blueprint.yaml

Format must match existing pipelines:

pipelineId: "forgescaffold_blueprint"

links: - id: ... list in order
(See existing pipeline structure in default.yaml / app_mvp.yaml.)

Recommended link order:

forgescaffold.system_catalog

forgescaffold.map_dataflow

forgescaffold.test_matrix

Verifier script (new)

Add: scripts/verify_forgescaffold_phase1.py

It must assert:

artifacts exist in artifact_index.json

output files exist on disk and are parseable (JSON/YAML)

ledger contains SUCCEEDED events for all three links

rerun on unchanged inputs yields identical content (or idempotent “skip” behavior if DAWN supports it in runtime)

Canonical output artifacts (strict)

All outputs must live in the DAWN project workspace and be registered in the artifact index.

Output 1: System Catalog (JSON)

Artifact ID: forgescaffold.system_catalog.json
File: system_catalog.json

Purpose: enumerate “units”:

module (monolith)

service (service mesh)

agent_step (local agent graph)

datastore

external_dependency

Minimum fields per unit:

id (stable)

type (enum above)

path or entrypoint

language (if known)

owner_tag (optional)

risk_tags (optional)

exports (optional)

observability (logger name/category suggestions)

Output 2: Dataflow Map (JSON)

Artifact ID: forgescaffold.dataflow_map.json
File: dataflow_map.json

Edges must support:

calls (in-process call)

imports (static dependency)

http, grpc

event (pub/sub)

reads, writes

spawns (subprocess)

retrieves (RAG / vectorstore lookup)

Minimum fields per edge:

from, to, type

evidence (file + line or config key, best-effort)

Output 3: Test Matrix (YAML)

Artifact ID: forgescaffold.test_matrix.yaml
File: test_matrix.yaml

Levels:

L0_contract (schema/contract tests per module boundary)

L1_slice (dependency-light integration slice)

L2_smoke (end-to-end “does it run”)

L3_nonfunctional (perf, security, reliability hooks)

Per unit:

success_criteria (bullet list)

tests (list with id, level, command, artifacts_expected)

How to implement (Phase 1 heuristic approach)

You do NOT need perfect static analysis yet—Phase 1 should be useful with pragmatic heuristics:

System Catalog extraction

Monolith: walk projects/<project>/src/ (or equivalent), group by package/module folders.

Service mesh: detect docker-compose.yml, k8s/*.yaml, helm, skaffold, terraform—derive service names + ports.

Local agent: detect workflow/graph configs (YAML/JSON), or common folders like agents/, tools/, skills/, pipelines/.

Dataflow map extraction

Python: parse imports quickly via AST when possible; fallback to regex.

TS/JS: parse import statements; scan for fetch/axios/grpc patterns.

Service mesh: map services via compose/k8s service definitions + known routes (best-effort).

Agent: edges from workflow definitions (node → node) + tool invocations.

Test matrix generation

For each unit, generate:

1x L0 contract test (importability / schema / interface)

1x L1 slice (unit + 1 dependency)

1x L2 smoke (minimal boot/run if applicable)

placeholders for L3 hooks

Commands should be concrete but safe (no network). If uncertain, emit TODO with clear next-step.

Logging & audit expectations

Use DAWN’s existing ledger + artifact index model; logs should be meaningful for “Operator Console” streaming and post-run audit. DAWN explicitly supports live log streaming, artifact browsing, and immutable ledger events.

When in doubt: write more structured logs (JSON lines) to stdout and rely on DAWN’s ledger to record success/fail at the link boundary.

Constraints (non-negotiable)

Deterministic: identical inputs → identical outputs.

No external network calls.

Do not mutate source tree unless the runtime policy/profile allows it; prefer writing only artifacts. (DAWN supports profiles like normal vs isolation and budgets in runtime_policy.yaml.)

All produced files must be registered as artifacts in the artifact index.

Implementation notes (DAWN-specific)

Use the link factory to scaffold each link: python3 -m dawn.factory.generate_link <link_id> then fill in link.yaml + run.py.

Follow existing link contract shape (example: service.catalog/link.yaml).

Follow existing run patterns (example: service.catalog/run.py, impl.generate_patchset/run.py).

Acceptance tests you must run before reporting “done”

Create a test DAWN project and run:
python3 -m dawn.runtime.main --project <proj> --pipeline dawn/pipelines/forgescaffold_blueprint.yaml

Confirm these exist:

projects/<proj>/artifact_index.json contains the 3 ForgeScaffold artifacts

projects/<proj>/ledger/events.jsonl shows all 3 links SUCCEEDED

Rerun the pipeline with no changes and confirm artifacts are byte-identical (or skipped idempotently).

What you should return to the Project Lead (me) after Phase 1

list of files added/changed

the three artifact formats (sample outputs)

any runtime/policy gotchas discovered

one short recommendation for Phase 2 (where accuracy improvements matter most)