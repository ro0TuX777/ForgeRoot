# ForgeScaffold Phase 9 Examples (forgescaffold_phase9_ci)

This folder contains sample operational-hardening artifacts from a Phase 9 bootstrap project.

## Contents
- evidence_index.jsonl (v2 entries; multi-signature + lock/approval metadata)
- used_approvals.jsonl (append-only replay protection log)
- status.json + status.md (operator view)
- prune_report.json (dry-run retention report)

## How locks work
- Per-project lock lives at `projects/<project>/.locks/forgescaffold_apply.lock`.
- Lock is acquired before apply and held through verify/package/sign/verify/index.
- Stale locks can be overridden only with explicit force; `lock_forced` is recorded in the index.

## How replay guard works
- Approval templates include `approval_id` (UUIDv4/hex) and must be signed by approvers.
- Gate rejects any `approval_id` already present in `used_approvals.jsonl`.
- Used approvals are append-only with patchset + bundle + review hash for explainable audits.

## Query evidence index
Use the query link (configurable filters):
- patchset_id
- approver
- risk_level
- since / until (RFC3339)
- limit

The query link reads mixed v1/v2 entries and returns deterministic results.

## Retention (safe by default)
Retention is declared in policy but disabled by default:
- `forgescaffold.retention.enabled: false`
- `prune_mode: dry_run` when enabled

To actually delete evidence packs, explicitly set:
- enabled: true
- prune_mode: delete

