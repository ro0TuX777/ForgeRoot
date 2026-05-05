"""Improvement recommendation engine for recursive loop."""

from __future__ import annotations

from typing import Dict, Optional

from .config import LoopConfig, load_loop_config
from .types import (
    AnalysisReport,
    ContractPatch,
    DistillationBatch,
    ImprovementPlan,
    PolicyAdjustment,
    PromptDiff,
)


def _top_key(values: Dict[str, int]) -> tuple[str, int]:
    if not values:
        return "", 0
    key = max(values.items(), key=lambda item: item[1])[0]
    return key, int(values[key])


class ImprovementRecommender:
    def __init__(self, cfg: Optional[LoopConfig] = None) -> None:
        self.cfg = cfg or load_loop_config()

    def recommend(
        self,
        *,
        report: AnalysisReport,
        policy_edit_count: int,
        distillation_batch: Optional[DistillationBatch] = None,
    ) -> ImprovementPlan:
        plan = ImprovementPlan(requires_human_review=True)

        high_reject_types = [
            ticket_type
            for ticket_type, rate in report.reject_rate.items()
            if rate > self.cfg.reject_threshold
        ]
        low_agreement_types = [
            artifact_type
            for artifact_type, rate in report.agreement_rates.items()
            if rate < self.cfg.agreement_threshold
        ]

        if high_reject_types or low_agreement_types:
            summary = []
            if high_reject_types:
                summary.append(f"high reject_rate in {', '.join(high_reject_types)}")
            if low_agreement_types:
                summary.append(f"low agreement_rate in {', '.join(low_agreement_types)}")
            plan.prompt_diffs.append(
                PromptDiff(
                    target_file="docs/ONBOARDING_LEAD_MANUAL.md",
                    additions=[
                        "Add concrete guard predicate examples from recent rejected tickets.",
                        "Add one successful before/after contract correction example.",
                    ],
                    removals=[],
                    examples=[
                        "subprocess.check_call(['rm', '-rf', '/'], shell=True) -> reject",
                    ],
                    rationale="; ".join(summary),
                )
            )

        mismatch_key, mismatch_count = _top_key(report.oracle_mismatch_frequency)
        if mismatch_count >= self.cfg.mismatch_repeat:
            contract_name = mismatch_key.split(" ", 1)[0] if mismatch_key else "unknown_contract"
            plan.contract_patches.append(
                ContractPatch(
                    contract_name=contract_name,
                    field_changes={
                        "guard_predicates": {
                            "add": [
                                "input_sanitized == True",
                                "manual_override == False",
                            ]
                        }
                    },
                    rationale=(
                        f"Oracle mismatch repeated {mismatch_count} times for pattern: {mismatch_key[:120]}"
                    ),
                )
            )

        if policy_edit_count >= self.cfg.override_repeat:
            plan.policy_adjustments.append(
                PolicyAdjustment(
                    domain="ci_change_control",
                    threshold_changes={"min_score": "+2", "max_deny_count": "-1"},
                    rationale=(
                        f"Policy recommendation edits repeated {policy_edit_count} times; tune defaults to reduce manual overrides."
                    ),
                    expected_impact="Fewer manual policy edits and higher agreement rate.",
                )
            )

        if distillation_batch is not None:
            plan.distillation_batch = distillation_batch

        # Safety invariant: always human review.
        plan.requires_human_review = True
        return plan


__all__ = ["ImprovementRecommender"]
