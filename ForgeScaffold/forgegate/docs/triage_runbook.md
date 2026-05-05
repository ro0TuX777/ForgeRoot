# ForgeGate Drift Triage Runbook

## Missing signal rate high
- Check signal extraction in adapters.
- Ensure required signals are populated in Signals.values.
- If missing is expected, explicitly allow via intent_spec.allow_missing_signals.

## Deny rate spikes
- Review constraints and boundary thresholds.
- Validate adapter mapping (risk tiers / action ids).
- Confirm proposed_action fields are correct.

## Escalation spikes
- Add more discriminative signals or adjust boundaries.
- Reduce ambiguity in intent_spec (tradeoffs, constraints).
- Confirm tools are mapped to correct side_effect/risk_tier.

## Payload limit violations
- Reduce payload size or raise limits in intent_spec.payload_limits.
- Avoid passing large blobs into params/signals.

## Decision distribution drift
- Compare current report to last baseline.
- If shifts are intent-driven, update intent_spec and re-run scenarios.
