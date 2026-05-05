# Phase 12 Example Artifacts (Global / Fleet Ops)

This folder is the canonical “fleet ops” pack for Phase 12. It shows how the global catalog, cross‑project query, and cache batch work together.

## How to reproduce

1) Enable global catalog policy and allowlist the projects used in the verifier:
```
# dawn/policy/runtime_policy.yaml
forgescaffold:
  global_catalog:
    enabled: true
    write_root: evidence/global
    projects_allowlist:
      - forgescaffold_phase12_a_ci
      - forgescaffold_phase12_b_ci
```

2) Run the Phase 12 verifier:
```
python3 scripts/verify_forgescaffold_phase12.py --project forgescaffold_phase12_ci --bootstrap \
  --profile forgescaffold_apply_lowrisk
```

## What each artifact means

- `catalog.json`: deterministic global catalog of per‑project evidence state.
- `evidence_global_query_results.json`: cross‑project query results with `query_backend_summary` showing cache vs scan.
- `cache_batch_report.json`: per‑project cache build summary (BUILT vs SKIPPED).
- `status.json` / `status.md`: operator view (cache coverage, stale caches, trust warnings, recent runs).

## Cache vs scan interpretation

`query_backend_summary` explicitly lists which projects were queried via SQLite cache vs JSONL scan. A mixed backend run (one cached, one scanning) is expected and demonstrated in this pack.
