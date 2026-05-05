# ForgeWorks ForgeGate Hardening Notes

Date: 2026-03-02

This note records governance hardening updates applied to ForgeWorks after the first SAM integration.

## What changed

1. Embedded ForgeGate intent specs were normalized to schema-compliant root keys:
- `intent_id`
- `intent_version`

2. Substring/path guard conditions now use ForgeGate `contains`:
- deploy protection checks for `sam/orchestration` in target path
- sandbox checks for workspace path and `.py` entrypoint

3. Legacy/non-schema keys were removed from embedded specs to reduce policy drift risk.
4. Embedded action/signal catalogs were normalized to ForgeGate schema keys:
- `action_id` (not `id`)
- `signal_id` (not `id`)
- `schema_version` included in both catalogs

## Why this was done

- Prevent silent policy mistakes (for example, ignored keys or malformed `when` fields).
- Improve readability of path checks versus reversed string `in` expressions.
- Align ForgeWorks with stricter ForgeGate validation workflows used in CI/promotion.

## Recommended operator workflow

When changing bundle policy files:

```bash
forgegate lint-intent <IntentBundlePath> --strict
forgegate validate-bundle <IntentBundlePath> --strict
```

Treat strict lint/validation failures as release blockers for policy updates.
