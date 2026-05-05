# Phase 11 Example Artifacts (Cache + Cadence)

This folder contains a minimal reference pack for Phase 11 cache + cadence:
- `evidence_index.jsonl` with 2+ entries
- `evidence_index_cache.sqlite.gz` (SQLite cache, gzipped)
- PASS/FAIL cache integrity reports
- evidence query results showing `query_backend: cache_sqlite`
- a checkpoint JSON + signature (from cadence-enabled run)

## How to reproduce

1) Run the Phase 11 verifier (bootstrap):
```
python3 scripts/verify_forgescaffold_phase11.py --project forgescaffold_phase11_ci --bootstrap \
  --profile forgescaffold_apply_lowrisk
```

2) Build cache (if you want to regenerate the cache file):
```
python3 -m dawn.runtime.main --project forgescaffold_phase11_ci \
  --pipeline /tmp/forgescaffold_build_cache.yaml --profile forgescaffold_apply_lowrisk
```

3) Query with cache backend:
```
python3 -m dawn.runtime.main --project forgescaffold_phase11_ci \
  --pipeline /tmp/forgescaffold_query_cache.yaml --profile forgescaffold_apply_lowrisk
```

## What to look for

- `cache_integrity_report_pass.json` shows `status: PASS`.
- `cache_integrity_report_fail.json` shows `CACHE_ROW_MISMATCH` after tampering.
- `evidence_query_results.json` includes `query_backend: "cache_sqlite"`.
- Checkpoint files show cadence behavior (min_interval suppressed extra runs).

## Notes for operators

- Cache meta schema 1.0.1: adds `checkpoint_path` and `checkpoint_timestamp` to show exactly which checkpoint (if any) the cache was validated against.
- Checkpoint `emit_reason`: explains why a checkpoint was emitted or suppressed (e.g., `emitted_min_interval`, `emitted_every_n`, `cadence_blocked`, `disabled`, `skipped_not_pass`).

## Inflate cache (optional)

```
gzip -d evidence_index_cache.sqlite.gz
```
