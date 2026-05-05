# ForgeScaffold: Technical Paper

**Version:** 12.0
**Date:** 2026-02-21
**Classification:** Internal Engineering Reference

---

## Abstract

ForgeScaffold is a deterministic, auditable blueprint-generation and change-management system built natively on the DAWN execution model. Given any target codebase — monolith, service mesh, or local agent graph — ForgeScaffold materializes three primary artifacts: a **System Catalog**, a **Dataflow Map**, and a **Test Matrix**. Changes derived from those artifacts travel through a governed apply pipeline that enforces human-in-the-loop approval, cryptographic evidence signing, multi-signature trust enforcement, hash-chained audit logs, and fleet-level status aggregation. This paper describes the system architecture, execution model, data contracts, security model, and the 12-phase development arc that produced the current implementation.

---

## Table of Contents

1. [Background: The DAWN Execution Model](#1-background-the-dawn-execution-model)
2. [System Overview](#2-system-overview)
3. [Blueprint Generation (Phase 1)](#3-blueprint-generation-phase-1)
   - 3.1 System Catalog Link
   - 3.2 Dataflow Map Link
   - 3.3 Test Matrix Link
4. [Artifact Schemas](#4-artifact-schemas)
5. [Apply Pipeline Evolution (Phases 2–9)](#5-apply-pipeline-evolution-phases-29)
   - 5.1 Pipeline v1–v2: Patchset Apply
   - 5.2 Pipeline v3: Human-in-the-Loop Gate
   - 5.3 Pipeline v4: Review Packet
   - 5.4 Pipeline v5: Risk Index
   - 5.5 Pipeline v6: Multi-Signature Evidence
   - 5.6 Pipeline v7: Operational Status
   - 5.7 Pipeline v8: Index Integrity
   - 5.8 Pipeline v9: SQLite Cache Layer
6. [Security Model](#6-security-model)
   - 6.1 Evidence Signing
   - 6.2 Trusted Signer Registry
   - 6.3 Multi-Signature Enforcement
   - 6.4 Replay Protection
   - 6.5 Hash-Chained Evidence Index
   - 6.6 Tamper Detection
7. [Shared Infrastructure (forgescaffold_common)](#7-shared-infrastructure-forgescaffold_common)
8. [Cache and Cadence Layer (Phase 11)](#8-cache-and-cadence-layer-phase-11)
9. [Fleet Operations (Phase 12)](#9-fleet-operations-phase-12)
10. [Verifier Scripts](#10-verifier-scripts)
11. [Link Catalog Reference](#11-link-catalog-reference)
12. [Operational Runbook](#12-operational-runbook)
13. [Design Principles and Constraints](#13-design-principles-and-constraints)
14. [Phase Summary](#14-phase-summary)

---

## 1. Background: The DAWN Execution Model

DAWN is a local pipeline orchestration framework. Its central concepts are:

| Concept | Description |
|---|---|
| **Pipeline** | A YAML file declaring an ordered list of links. |
| **Link** | An atomic unit of work with explicit `requires` and `produces` contracts. |
| **Artifact** | A named, versioned file (JSON, YAML, binary, or text) registered in `artifact_index.json`. |
| **Ledger** | An append-only `events.jsonl` file recording the start and completion of every link execution. |
| **Sandbox** | An isolated write space per link; artifacts are published via `sandbox.publish(...)` or `sandbox.publish_text(...)`. |
| **Artifact Store** | A queryable map from `artifactId` to on-disk path, shared across links within a pipeline run. |
| **Profile** | Runtime policy parameters (e.g., `forgescaffold_apply_lowrisk`) controlling budgets and isolation mode. |

The CLI invocation pattern is:

```
python3 -m dawn.runtime.main --project <project_id> --pipeline <pipeline.yaml> [--profile <profile>]
```

Projects live at `projects/<project_id>/`. The artifact index is at `projects/<project_id>/artifact_index.json`. The ledger is at `projects/<project_id>/ledger/events.jsonl`.

Every link declares its contract in a `link.yaml` file (`apiVersion: dawn.links/v1`) and implements a `run(project_context, link_config)` function in `run.py`. Links must be deterministic: given identical inputs, they must produce identical outputs.

---

## 2. System Overview

ForgeScaffold extends DAWN with two high-level responsibilities:

1. **Blueprint Generation** — Heuristic analysis of a project workspace to produce a System Catalog, Dataflow Map, and Test Matrix. These are read-only analysis artifacts; the source tree is never mutated.

2. **Governed Change Application** — A multi-stage pipeline that ingests a proposed patchset, instruments it, presents it for human review and cryptographic approval, applies it, packages and signs the evidence, verifies the evidence chain, and appends a tamper-evident entry to the evidence index.

The two responsibilities are wired into distinct pipelines that share a common DAWN project context. All produced artifacts are registered in `artifact_index.json` and auditable through the immutable ledger.

```
┌─────────────────────────────────────────────────────────────────┐
│                        DAWN Pipeline Runner                      │
│                                                                  │
│  forgescaffold_blueprint        forgescaffold_apply_v9_cache     │
│  ─────────────────────          ─────────────────────────────   │
│  ingest.project_bundle          ingest.project_bundle            │
│  forgescaffold.system_catalog   forgescaffold.system_catalog     │
│  forgescaffold.map_dataflow     forgescaffold.map_dataflow       │
│  forgescaffold.test_matrix      forgescaffold.obs_*              │
│                                 forgescaffold.test_matrix        │
│                                 forgescaffold.generate_review_*  │
│                                 forgescaffold.gate_patchset_*    │
│                                 forgescaffold.apply_patchset     │
│                                 forgescaffold.verify_post_apply  │
│                                 forgescaffold.verify_rollback    │
│                                 forgescaffold.package_evidence   │
│                                 forgescaffold.sign_evidence      │
│                                 forgescaffold.verify_evidence    │
│                                 forgescaffold.update_evidence_*  │
│                                 forgescaffold.build_index_cache  │
│                                 forgescaffold.verify_cache_*     │
│                                 forgescaffold.write_index_*      │
│                                 forgescaffold.verify_index_*     │
│                                 forgescaffold.status             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Blueprint Generation (Phase 1)

The blueprint pipeline (`forgescaffold_blueprint.yaml`) runs four links in order:

```yaml
pipelineId: "forgescaffold_blueprint"
links:
  - id: ingest.project_bundle
  - id: forgescaffold.system_catalog
  - id: forgescaffold.map_dataflow
  - id: forgescaffold.test_matrix
```

### 3.1 System Catalog Link

**Link ID:** `forgescaffold.system_catalog`
**File:** `dawn_extensions/links/system_catalog/run.py`
**Produces:** `system_catalog.json` (`artifactId: forgescaffold.system_catalog.json`)

The link walks the project workspace and assembles a flat list of `units` across five collectors that run in order, with later results merged (earlier keys preserved):

| Collector | Unit Type | Detection Heuristic |
|---|---|---|
| `collect_python_units` | `module` | Walk `src/` for `__init__.py` (packages) and standalone `.py` files; group by package namespace. |
| `collect_service_units` | `service` | Parse `docker-compose.yml`/`compose.yaml` for service blocks; parse `*.yaml`/`*.yml` for K8s `Deployment`, `StatefulSet`, or `Service` kinds. |
| `collect_agent_units` | `agent_step` | Scan well-known folders: `agents/`, `agent_steps/`, `workflows/`, `pipeline/`, `flows/`, `skills/`, `tools/` for `.yaml`, `.yml`, `.json`, `.py` files. |
| `collect_datastores` | `datastore` | Detect directories named `data/`, `storage/`, `databases/`, `db/`, `state/`, `cache/`; recurse for `.db`, `.sqlite`, `.json`, `.yaml` files. |
| `collect_external_deps` | `external_dependency` | Parse `requirements.txt`, `pyproject.toml` (Poetry), and `package.json`; also seed known runtime patterns (`requests`, `httpx`, `grpc`, `subprocess`, etc.). |

Each unit record carries:

```json
{
  "id": "<stable-dotted-id>",
  "type": "<module|service|agent_step|datastore|external_dependency>",
  "path": "<project-relative path>",
  "entrypoint": "<project-relative path or null>",
  "language": "<python|javascript|container|yaml|config|...>",
  "owner_tag": "<project_id or label override>",
  "risk_tags": ["<tag>", ...],
  "exports": [],
  "observability": { ... }
}
```

Unit IDs are stable: Python package IDs are derived from relative paths with `/` replaced by `.`; service IDs are prefixed `service.`; agent step IDs are `agent_step.<folder>.<stem>`; datastore IDs are `datastore.<dir>`; external dependency IDs are `external.<name>`.

The `assemble_units` function sorts by key before building the final list, ensuring deterministic order regardless of filesystem traversal order.

### 3.2 Dataflow Map Link

**Link ID:** `forgescaffold.map_dataflow`
**File:** `dawn_extensions/links/map_dataflow/run.py`
**Requires:** `forgescaffold.system_catalog.json`
**Produces:** `dataflow_map.json` (`artifactId: forgescaffold.dataflow_map.json`)

The link reads the System Catalog and builds a directed graph of edges. It segments catalog units by type, then runs per-source-file analysis on every Python module:

**Edge types and their detection strategies:**

| Edge Type | Detection Method |
|---|---|
| `imports` | Python AST (`ast.Import`, `ast.ImportFrom`) — matched against module unit IDs via longest-prefix match, then against external dependency names. |
| `http` | Keyword scan (lowercased file text) for `requests`, `httpx`, `urllib`, `fetch`, `axios` — edges point to matching service or external dependency. |
| `grpc` | Keyword scan for `grpc` — edge to matching external dependency. |
| `spawns` | Keyword scan for `subprocess`, `os.system`, `multiprocess` — edge to matching external dependency. |
| `retrieves` | Keyword scan for `vectorstore`, `pinecone`, `faiss`, `llama` — edge to matching external or self-referencing module. |
| `reads`/`writes` | Datastore path name appears in module source text; disambiguated by presence of the word `read`. |
| `event` | Agent step units are linked sequentially in alphabetical order. |

Deduplication is enforced by a `seen` set keyed on `(from, to, type, file, line)`. Evidence carries `{"file": ..., "line": ..., "note": ...}`.

The output payload is:

```json
{
  "project_id": "...",
  "nodes": [{"id": "...", "type": "...", "path": "...", "language": "..."}, ...],
  "edges": [{"from": "...", "to": "...", "type": "...", "evidence": [...]}, ...]
}
```

### 3.3 Test Matrix Link

**Link ID:** `forgescaffold.test_matrix`
**File:** `dawn_extensions/links/test_matrix/run.py`
**Requires:** `forgescaffold.system_catalog.json`, `forgescaffold.dataflow_map.json`
**Produces:** `test_matrix.yaml`, `test_harness/manifest.json`

For every unit in the catalog, the link generates four test entries spanning levels L0–L3:

| Level | Purpose | Command Strategy |
|---|---|---|
| `L0_contract` | Schema/interface importability | `pytest` smoke, `compileall`, or path-existence check depending on unit type. |
| `L1_slice` | Dependency-light integration slice | `pytest <path>` for modules; config existence checks for services. |
| `L2_smoke` | End-to-end minimal execution | `python3 <entrypoint>` for modules/agents; simulated HTTP calls for services. |
| `L3_nonfunctional` | Perf, security, reliability hooks | `echo` stubs with explicit TODO markers. |

Commands are generated by `build_command(unit, level)` using `shlex.quote` for safe path handling. The dominant language across the catalog determines the test harness format (Python `pytest` or Node `node --test`).

The link also writes a test harness scaffolding under `test_harness/` with a `README.md` and a minimal `test_l0_smoke.py` (or `.js`) placeholder.

YAML output uses `yaml.safe_dump(payload, sort_keys=False)` for determinism.

---

## 4. Artifact Schemas

All primary artifacts are validated against JSON Schema definitions in `dawn_extensions/schemas/`.

### system_catalog.schema.json

```
root: { project_id: string, units: array }
unit: {
  id: string (required),
  type: enum[module, service, agent_step, datastore, external_dependency] (required),
  path: string (required),
  entrypoint: string|null,
  language: string|null,
  owner_tag: string|null,
  risk_tags: string[],
  exports: string[],
  observability: { logs, tracing, metrics, ... }
}
```

### dataflow_map.schema.json

```
root: { project_id: string, nodes: array, edges: array }
node: { id: string (required), type: string (required), path, language }
edge: {
  from: string (required),
  to: string (required),
  type: enum[calls, imports, http, grpc, event, reads, writes, spawns, retrieves] (required),
  evidence: [{ file: string, note: string, line: integer|null }] (required)
}
```

### test_matrix.schema.json

```
root: { project_id: string, levels: string[], units: array }
unit_entry: {
  unit_id: string,
  type: string,
  path: string,
  success_criteria: string[],
  tests: [{ id, level, command, artifacts_expected }]
}
```

Schemas are self-registered into `dawn.runtime.schemas.SCHEMA_REGISTRY` at link startup via `register_schema()`, with a graceful no-op if the DAWN schema module is absent (useful for isolated testing).

---

## 5. Apply Pipeline Evolution (Phases 2–9)

### 5.1 Pipeline v1–v2: Patchset Apply

**Files:** `forgescaffold_apply_v1.yaml`, `forgescaffold_apply_v2_hunks.yaml`

The earliest apply pipelines add two links beyond the blueprint base:

- **`forgescaffold.apply_patchset`** — Applies a generated or supplied patchset to the project workspace within sandbox bounds.
- **`forgescaffold.package_evidence`** — Bundles all intermediate artifacts (catalog, dataflow, test matrix, patchset diff) into an evidence manifest.

v2 adds hunk-level granularity to the patchset representation.

### 5.2 Pipeline v3: Human-in-the-Loop Gate

**Files:** `forgescaffold_apply_v3_hitl.yaml`, `forgescaffold_apply_v3_hitl_runnable.yaml`

The HITL gate inserts three new links:

- **`forgescaffold.obs_define_schema`** — Declares the observability schema for the patchset (log envelope, instrumentation fields).
- **`forgescaffold.obs_instrument_patchset`** — Stamps the patchset with structured observability metadata (link IDs, trace context, risk fields).
- **`forgescaffold.gate_patchset_approval`** — Reads `instrumentation.patchset.json` (and optionally `review_packet.json`) and blocks pipeline execution until a valid `approval_receipt.json` is provided.

The approval receipt must contain a `patchset_id` and `bundle_content_sha256` that match the instrumented patchset. This receipt is later bound into the signed evidence chain.

The `_runnable` variants bypass waiting behavior for CI/automated testing.

### 5.3 Pipeline v4: Review Packet

**File:** `forgescaffold_apply_v4_review_hitl.yaml`

Adds:

- **`forgescaffold.generate_review_packet`** — Produces a human-readable `review_packet.json` surfacing risk summary, affected units from the catalog, dataflow impact, and test matrix obligations. This is the document a human reviewer reads before approving.
- **`forgescaffold.generate_approval_template`** — Emits a structured `approval_template.json` with a UUIDv4 `approval_id` field, which the approver fills in and signs.

### 5.4 Pipeline v5: Risk Index

**File:** `forgescaffold_apply_v5_risk_index.yaml`

Adds:

- **`forgescaffold.update_evidence_index`** — Appends a signed, hash-chained entry to `evidence_index.jsonl`, the append-only per-project evidence registry. Each entry captures `patchset_id`, `risk_level`, approval metadata, and digest hashes.

The evidence index is the authoritative post-apply audit trail.

### 5.5 Pipeline v6: Multi-Signature Evidence

**File:** `forgescaffold_apply_v6_multisig.yaml`

Adds:

- **`forgescaffold.sign_evidence`** — Signs the `evidence_manifest.json` and `approval_receipt.json` to produce `evidence_signature.json` and `evidence_receipt.json`. Supports multiple signers in a single receipt.
- **`forgescaffold.verify_evidence`** — Reads the manifest, signatures, receipt, instrumentation, and optional rollback report; runs the full trust/scope/expiry check and produces `evidence_verification_report.json`.

At this phase, the pipeline reaches its security-complete form: approve → sign → verify → index.

### 5.6 Pipeline v7: Operational Status

**File:** `forgescaffold_apply_v7_operational.yaml`

Adds:

- **`forgescaffold.status`** — Reads the evidence index, lock state, and signer registry to produce `status.json` and `status.md` (a human-readable operator dashboard).

The status link provides immediate visibility into: whether a project lock is held, how many recent runs exist, and how many trusted signers are registered.

### 5.7 Pipeline v8: Index Integrity

**File:** `forgescaffold_apply_v8_integrity.yaml`

Adds:

- **`forgescaffold.verify_index_integrity`** — Re-reads `evidence_index.jsonl` and walks the full hash chain, verifying `prev_entry_hash` linkage and per-entry SHA-256 hashes. Reports `CHAIN_BREAK` or `ENTRY_HASH_MISMATCH` on tampering.

This link closes the tamper-detection loop: even if an attacker modifies a past index entry, the chain verification will detect it.

### 5.8 Pipeline v9: SQLite Cache Layer

**File:** `forgescaffold_apply_v9_cache.yaml`

Adds three cache-related links completing the current single-project pipeline:

- **`forgescaffold.build_index_cache`** — Materializes a SQLite cache (`evidence_index_cache.sqlite`, optionally gzipped) from `evidence_index.jsonl`. The cache enables O(1) query lookups in large indexes.
- **`forgescaffold.verify_cache_integrity`** — Compares every SQLite row against the source JSONL, reporting `CACHE_ROW_MISMATCH` if divergence is found.
- **`forgescaffold.write_index_checkpoint`** — Writes a signed checkpoint JSON recording the current index file hash, for cadence-based cache refresh suppression.

The full Phase 9 link order:

```
ingest → system_catalog → map_dataflow → obs_define_schema →
obs_instrument_patchset → test_matrix → generate_review_packet →
generate_approval_template → gate_patchset_approval → apply_patchset →
verify_post_apply → verify_rollback → package_evidence → sign_evidence →
verify_evidence → update_evidence_index → build_index_cache →
verify_cache_integrity → write_index_checkpoint → verify_index_integrity →
status
```

---

## 6. Security Model

### 6.1 Evidence Signing

After a patchset is applied and packaged, `forgescaffold.sign_evidence` signs two artifacts:

1. **Evidence Manifest** (`evidence_manifest.json`) — A content-addressed bundle of all intermediate artifacts.
2. **Approval Receipt** (`approval_receipt.json`) — Binds the human approver's `approval_id` (UUIDv4) to the `patchset_id` and `bundle_content_sha256`.

The signing output (`evidence_signature.json`, `evidence_receipt.json`) includes the signer fingerprint(s) and cryptographic signatures.

### 6.2 Trusted Signer Registry

**File:** `dawn_extensions/policy.trusted_signers.yaml` (also mirrored as `trusted_signers.yaml`)

```yaml
trusted_signers:
  - fingerprint: "<sha256_hex>"
    label: "ci-signer"
    scopes:
      projects: ["project_id_1", ...]
      pipelines: ["pipeline_name_1", ...]
    expires_at: "2030-01-01T00:00:00Z"
    revoked: false
```

Each entry enforces:
- **Fingerprint trust** — Only known fingerprints are considered trusted.
- **Project scope** — A signer may only approve runs within listed projects.
- **Pipeline scope** — A signer may only approve named pipelines.
- **Expiry** — Signatures from expired signers are rejected.
- **Revocation** — `revoked: true` immediately disables a signer without removing their record.

### 6.3 Multi-Signature Enforcement

Policy (`runtime_policy.yaml`) can require a minimum number of valid signatures per risk level:

```yaml
forgescaffold:
  min_signatures_by_risk:
    low: 1
    medium: 2
    high: 3
```

`forgescaffold.verify_evidence` checks that `valid_signatures >= required_signatures` for the patchset's declared risk level. A FAIL result with `INSUFFICIENT_SIGNATURES` blocks index registration.

**Verification report — PASS:**

```json
{
  "status": "PASS",
  "manifest_hash_ok": true,
  "receipt_ok": true,
  "required_signatures": 2,
  "valid_signatures": 2,
  "signers": [
    {"fingerprint": "<fp1>", "trusted": true, "scope_ok": true, "expired": false, "sig_ok": true},
    {"fingerprint": "<fp2>", "trusted": true, "scope_ok": true, "expired": false, "sig_ok": true}
  ]
}
```

**Verification report — FAIL (tamper):**

```json
{
  "status": "FAIL",
  "errors": ["SIGNATURE_INVALID", "MANIFEST_HASH_MISMATCH", "RECEIPT_MANIFEST_MISMATCH"],
  "manifest": {"hash_match": false, "signature_valid": false},
  "receipt": {"manifest_match": false}
}
```

### 6.4 Replay Protection

Every approval template contains a `approval_id` (UUIDv4 or hex token). The gate link checks `used_approvals.jsonl` — an append-only log — and rejects any `approval_id` already present. On successful gate passage, the ID is written to `used_approvals.jsonl` with the associated `patchset_id`, `bundle_content_sha256`, and review hash. This prevents an approval from being replayed against a different patchset.

### 6.5 Hash-Chained Evidence Index

**File:** `dawn_extensions/links/forgescaffold_common/index_utils.py`

`evidence_index.jsonl` is an append-only JSONL file where each line is an independent JSON object. Every entry is chained to the previous via a SHA-256 hash:

```python
entry["prev_entry_hash"] = last_entry_hash(index_path) or "GENESIS"
entry_hash = sha256(canonical_json(entry_without_entry_hash))
entry["entry_hash"] = entry_hash
```

The first entry always sets `prev_entry_hash = "GENESIS"`. Canonical JSON is produced with `sort_keys=True` and compact separators (`(",", ":"`)), ensuring hash stability across Python versions and platforms.

Chain verification (`verify_index_chain`) walks every line in sequence, checking:
1. `prev_entry_hash` matches the computed hash of the prior entry.
2. `entry_hash` equals `sha256(canonical_json(entry without entry_hash))`.

Any deviation produces `CHAIN_BREAK` or `ENTRY_HASH_MISMATCH`.

### 6.6 Tamper Detection

The system detects tampering at four layers:

| Layer | Mechanism |
|---|---|
| Manifest hash | `MANIFEST_HASH_MISMATCH` when evidence manifest content hash mismatches the signature payload. |
| Signature validity | `SIGNATURE_INVALID` when the cryptographic signature does not verify against the manifest hash. |
| Receipt linkage | `RECEIPT_MANIFEST_MISMATCH` when the receipt's `bundle_content_sha256` mismatches the manifest. |
| Index chain | `CHAIN_BREAK` / `ENTRY_HASH_MISMATCH` when any past index entry is altered. |

---

## 7. Shared Infrastructure (forgescaffold_common)

`dawn_extensions/links/forgescaffold_common/` provides two utility modules shared by all advanced links via direct Python import:

### index_utils.py

| Function | Purpose |
|---|---|
| `canonical_json(payload)` | Deterministic JSON serialization (sorted keys, compact separators). |
| `sha256_text(text)` | UTF-8 SHA-256 hex digest. |
| `compute_entry_hash(entry)` | Hash of entry with `entry_hash` field stripped. |
| `load_index(path)` | Load JSONL lines into a list of dicts. |
| `last_entry_hash(path)` | Return the `entry_hash` of the final index entry. |
| `policy_snapshot_hash(policy)` | Deterministic hash of ForgeScaffold policy keys (used in index entries for auditability). |
| `index_file_sha256(path)` | SHA-256 of the raw JSONL bytes (used for cache integrity). |
| `append_index_entry(path, entry)` | Atomically append a chained entry. |
| `verify_index_chain(path)` | Full chain walk; returns `(ok, line_no, error_code)`. |

### lock_utils.py

Per-project apply lock lives at `projects/<project>/.locks/forgescaffold_apply.lock`. It is a JSON file containing PID, hostname, start timestamp, pipeline name, and patchset ID.

| Function | Purpose |
|---|---|
| `acquire_lock(project_root, pipeline, patchset_id, ttl_minutes, force)` | Atomic acquire via temp file rename. Returns `(acquired, detail)`. |
| `release_lock(project_root)` | Deletes lock file; returns previous payload. |
| `_is_stale(payload, ttl_minutes)` | True if lock age exceeds TTL. |

Lock acquisition is non-blocking: if a non-stale lock is held, it returns `LOCK_HELD` immediately. Stale locks can be force-overridden (recorded as `lock_forced: true` in the index entry for auditability). This prevents concurrent apply runs against the same project.

---

## 8. Cache and Cadence Layer (Phase 11)

For projects with large evidence indexes, JSONL scan performance degrades linearly. Phase 11 introduces a SQLite-backed cache layer.

### Build

`forgescaffold.build_index_cache` reads `evidence_index.jsonl` and inserts every entry into a SQLite table. The database is compressed with gzip and stored at `evidence/cache/evidence_index_cache.sqlite.gz`. A `cache_build_report.json` records the build timestamp, row count, and the SHA-256 of the source JSONL at build time.

### Integrity Verification

`forgescaffold.verify_cache_integrity` reads every SQLite row and compares it against the corresponding JSONL entry. Mismatches produce `CACHE_ROW_MISMATCH`. A PASS report confirms the cache is a faithful replica of the index.

Cache meta schema version 1.0.1 adds `checkpoint_path` and `checkpoint_timestamp` fields to the cache build report, linking the cache to the checkpoint that authorized its construction.

### Cadence (Checkpoint-Based Suppression)

`forgescaffold.write_index_checkpoint` writes a checkpoint JSON containing:
- The current `index_file_sha256`
- The emission timestamp
- An `emit_reason` explaining why the checkpoint was emitted or suppressed

Possible `emit_reason` values:

| Value | Meaning |
|---|---|
| `emitted_min_interval` | Checkpoint emitted because the minimum interval elapsed. |
| `emitted_every_n` | Checkpoint emitted due to N-run cadence. |
| `cadence_blocked` | Cadence rules blocked emission; no checkpoint written. |
| `disabled` | Checkpointing disabled by policy. |
| `skipped_not_pass` | Checkpoint skipped because preceding verify did not PASS. |

When the index JSONL hash matches the checkpoint hash, cache builds and verifications can be skipped, reducing redundant I/O on large deployments.

### Query Backend Selection

`forgescaffold.query_evidence_index` automatically selects the query backend:
- **`cache_sqlite`** — Used when a valid, integrity-passing SQLite cache exists.
- **JSONL scan** — Fallback when no cache is present or cache fails integrity check.

Query results include a `query_backend` field so operators can see which path was taken.

---

## 9. Fleet Operations (Phase 12)

Phase 12 promotes ForgeScaffold from a per-project tool to a fleet-level control plane.

**Pipeline:** `forgescaffold_global_ops_v10.yaml`

```yaml
pipelineId: "forgescaffold_global_ops_v10"
links:
  - id: forgescaffold.build_global_catalog
  - id: forgescaffold.build_all_caches
  - id: forgescaffold.status_global
  - id: forgescaffold.query_global_evidence
    config:
      limit: 10
```

### Policy Configuration

```yaml
forgescaffold:
  global_catalog:
    enabled: true
    write_root: evidence/global
    projects_allowlist:
      - project_a_ci
      - project_b_ci
```

Only projects explicitly allowlisted can be included in the global catalog. This prevents accidental cross-project data leakage.

### Global Catalog

`forgescaffold.build_global_catalog` scans all allowlisted projects, collects their most recent evidence index entries, and produces:

- `evidence/global/catalog.json` — A deterministic per-project evidence state snapshot.
- `evidence/global/catalog.signature.json` — Signature over the catalog hash (optional, when signing policy is enabled).

### Batch Cache Build

`forgescaffold.build_all_caches` runs cache build logic for every project in the allowlist and produces a `cache_batch_report.json` summarizing per-project outcomes:
- `BUILT` — Cache was successfully constructed or refreshed.
- `SKIPPED` — Cadence rules or a valid existing cache prevented a rebuild.

### Cross-Project Query

`forgescaffold.query_global_evidence` queries evidence across all allowlisted projects, using per-project cache backends where available. The result includes a `query_backend_summary` object listing which projects were served from SQLite cache vs JSONL scan.

Example:

```json
{
  "results": [...],
  "query_backend_summary": {
    "project_a_ci": "cache_sqlite",
    "project_b_ci": "jsonl_scan"
  }
}
```

### Global Status

`forgescaffold.status_global` aggregates status across all projects, reporting:
- Cache coverage (percentage of projects with valid caches)
- Stale caches
- Trust warnings (expiring or revoked signers)
- Recent run counts per project

---

## 10. Verifier Scripts

`scripts/verify_forgescaffold_phase<N>.py` scripts provide end-to-end acceptance tests for each phase. They share a common structure:

1. **Bootstrap** (optional, `--bootstrap` flag) — Runs the relevant pipeline against a CI test project to populate artifacts.
2. **Artifact assertions** — Verify that every expected artifact ID exists in `artifact_index.json` and that the on-disk file is present and parseable.
3. **Ledger assertions** — Verify that `events.jsonl` contains `SUCCEEDED` events for each expected link.
4. **Content assertions** — Inspect artifact content for structural correctness (e.g., non-empty units list, non-empty edges, correct PASS status on verification reports).
5. **Determinism assertions** — Re-run the pipeline and confirm artifacts are byte-identical (or that the DAWN runtime emits an idempotent skip).

The phase verifiers are additive: Phase 12's verifier imports and re-uses Phase 9's checks, layering fleet assertions on top.

---

## 11. Link Catalog Reference

| Link ID | Category | Produces |
|---|---|---|
| `forgescaffold.system_catalog` | Blueprint | `system_catalog.json` |
| `forgescaffold.map_dataflow` | Blueprint | `dataflow_map.json` |
| `forgescaffold.test_matrix` | Blueprint | `test_matrix.yaml`, `test_harness/manifest.json` |
| `forgescaffold.obs_define_schema` | Observability | Observability schema artifact |
| `forgescaffold.obs_instrument_patchset` | Observability | `instrumentation.patchset.json` |
| `forgescaffold.generate_review_packet` | Governance | `review_packet.json` |
| `forgescaffold.generate_approval_template` | Governance | `approval_template.json` (with `approval_id`) |
| `forgescaffold.gate_patchset_approval` | Governance | `approval_receipt.json` |
| `forgescaffold.apply_patchset` | Change | Applied workspace mutations |
| `forgescaffold.verify_post_apply` | Change | Post-apply verification report |
| `forgescaffold.verify_rollback` | Change | Rollback verification report |
| `forgescaffold.package_evidence` | Audit | `evidence_manifest.json` |
| `forgescaffold.sign_evidence` | Audit | `evidence_signature.json`, `evidence_receipt.json` |
| `forgescaffold.verify_evidence` | Audit | `evidence_verification_report.json` |
| `forgescaffold.update_evidence_index` | Audit | Append to `evidence_index.jsonl` |
| `forgescaffold.query_evidence_index` | Query | `evidence_query_results.json` |
| `forgescaffold.prune_evidence` | Retention | `prune_report.json` |
| `forgescaffold.build_index_cache` | Cache | `evidence_index_cache.sqlite(.gz)`, `cache_build_report.json` |
| `forgescaffold.verify_cache_integrity` | Cache | `cache_integrity_report.json` |
| `forgescaffold.write_index_checkpoint` | Cache | `index_checkpoint.json` |
| `forgescaffold.verify_index_integrity` | Audit | `index_integrity_report.json` |
| `forgescaffold.write_compaction_summary` | Maintenance | `compaction_summary.json` |
| `forgescaffold.status` | Operations | `status.json`, `status.md` |
| `forgescaffold.build_global_catalog` | Fleet | `evidence/global/catalog.json` |
| `forgescaffold.build_all_caches` | Fleet | `cache_batch_report.json` |
| `forgescaffold.status_global` | Fleet | Fleet status report |
| `forgescaffold.query_global_evidence` | Fleet | `evidence_global_query_results.json` |

---

## 12. Operational Runbook

### Running the Blueprint Pipeline

```bash
python3 -m dawn.runtime.main \
  --project <project_id> \
  --pipeline dawn/pipelines/forgescaffold_blueprint.yaml
```

Confirm artifacts in `projects/<project_id>/artifact_index.json`:
- `forgescaffold.system_catalog.json`
- `forgescaffold.dataflow_map.json`
- `forgescaffold.test_matrix.yaml`

### Running the Full Apply Pipeline (with caching)

```bash
python3 -m dawn.runtime.main \
  --project <project_id> \
  --pipeline dawn/pipelines/forgescaffold_apply_v9_cache.yaml \
  --profile forgescaffold_apply_lowrisk
```

Before execution, ensure:
- Approval receipt (`approval_receipt.json`) is present with a valid, unused `approval_id`.
- At least one trusted signer has signed the evidence manifest.

### Running Fleet Operations

1. Update `runtime_policy.yaml` with the projects allowlist.
2. Run:
```bash
python3 -m dawn.runtime.main \
  --project fleet_ops \
  --pipeline dawn/pipelines/forgescaffold_global_ops_v10.yaml \
  --profile forgescaffold_apply_lowrisk
```

### Registering a New Trusted Signer

Edit `dawn_extensions/policy.trusted_signers.yaml`:

```yaml
trusted_signers:
  - fingerprint: "<sha256_of_public_key>"
    label: "new-signer"
    scopes:
      projects: ["target_project"]
      pipelines: ["forgescaffold_apply_v9_cache"]
    expires_at: "2028-01-01T00:00:00Z"
    revoked: false
```

### Retention Policy

Evidence pruning is opt-in and disabled by default:

```yaml
forgescaffold:
  retention:
    enabled: false        # Set to true to activate
    prune_mode: dry_run   # Use 'delete' to actually remove entries
    max_age_days: 90
```

Always run a dry-run first to inspect `prune_report.json` before enabling delete mode.

---

## 13. Design Principles and Constraints

### Determinism

All links must produce byte-identical outputs for identical inputs. Practices enforced across the codebase:
- `sorted()` on all collections before serialization.
- `yaml.safe_dump(payload, sort_keys=False)` with stable field ordering.
- `json.dumps(payload, sort_keys=True, separators=(",", ":"))` for canonical hashes.
- No timestamps in artifact payloads (timestamps appear only in ledger/index metadata).
- Sorted file walks (`sorted(rglob(...))`) for filesystem independence.

### No External Network Calls

Links are explicitly prohibited from making network calls. All analysis is file-local. HTTP/gRPC edge types in the dataflow map are detected by keyword presence in source files, not by probing live endpoints.

### Source Tree Immutability

Blueprint links never mutate the source tree. The apply link operates within DAWN's sandbox scope and writes only to the artifact directory unless the runtime profile explicitly permits workspace mutations.

### Audit Completeness

Every meaningful runtime event is recorded in two places: the DAWN ledger (`events.jsonl`) and, for post-apply runs, the evidence index (`evidence_index.jsonl`). The two are independently verifiable.

### Defense in Depth

Security guarantees stack:
1. Human must approve (gate link, approval receipt).
2. Approval is unique (replay guard via `used_approvals.jsonl`).
3. Evidence is signed (cryptographic signature).
4. Signer must be trusted with correct scope and non-expired credential (signer registry).
5. Minimum N signatures required per risk level (multi-sig policy).
6. All past approvals are tamper-evident (hash-chained index).
7. Cache faithfully represents the index (cache integrity verification).

---

## 14. Phase Summary

| Phase | Pipeline Version | Key Additions |
|---|---|---|
| 1 | `forgescaffold_blueprint` | System Catalog, Dataflow Map, Test Matrix; base verifier. |
| 2 | `forgescaffold_apply_v1`, `v2_hunks` | Patchset apply; evidence packaging; hunk-level diffs. |
| 3 | `forgescaffold_apply_v3_hitl` | Observability instrumentation; HITL approval gate. |
| 4 | `forgescaffold_apply_v4_review_hitl` | Review packet; approval template with UUIDv4 approval_id. |
| 5 | `forgescaffold_apply_v5_risk_index` | Evidence index (`evidence_index.jsonl`); risk level tagging. |
| 6 | `forgescaffold_apply_v6_multisig` | Cryptographic signing; trusted signer registry; multi-signature enforcement; evidence verification. |
| 7 | `forgescaffold_apply_v7_operational` | Operational status dashboard; project lock management. |
| 8 | `forgescaffold_apply_v8_integrity` | Full index chain integrity verification; signer scopes and expiry; evidence query link. |
| 9 | `forgescaffold_apply_v9_cache` | SQLite cache; cache integrity; checkpointing; cadence suppression; replay guard. |
| 10 | `forgescaffold_apply_v9_cache` (same) | Compaction summary; write_index_checkpoint cadence improvements. |
| 11 | Cache meta schema 1.0.1 | Cache–checkpoint binding; `emit_reason` field; cache query backend selection. |
| 12 | `forgescaffold_global_ops_v10` | Global catalog; batch cache builds; cross-project evidence query; fleet status. |

---

*End of Technical Paper*
