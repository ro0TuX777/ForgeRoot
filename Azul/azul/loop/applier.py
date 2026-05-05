"""IMPROVE stage applier — routes ImprovementPlan changes through ForgedRoot governance.

Every change produced here is human-reviewable before it takes effect:
  - PromptDiff    → draft file in improvement_reports/pending_prompts/
  - ContractPatch → stub YAML in action_catalogs/stubs/ (existing approval workflow)
  - PolicyAdjustment → pending YAML in config/gate_policies/pending/
  - DistillationBatch → signals batch readiness (no trainer in ForgedRoot; consumer responsibility)

Nothing is applied autonomously. requires_human_review is enforced.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config import LoopConfig, ensure_loop_dirs, load_loop_config
from .types import ContractPatch, DistillationBatch, ImprovementPlan, PolicyAdjustment, PromptDiff


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id() -> str:
    return f"apply-{uuid.uuid4().hex[:12]}"


class ApplyError(RuntimeError):
    """Raised when the applier cannot safely process a plan."""


class ImprovementApplier:
    """Routes an ImprovementPlan to the appropriate ForgedRoot governance queues.

    Design invariant: this class never modifies live files directly.
    All outputs go to human-review queues (stubs/, pending/) or draft directories.
    Human approval is required before anything becomes active.
    """

    def __init__(
        self,
        cfg: Optional[LoopConfig] = None,
        forge_root: Optional[Path] = None,
    ) -> None:
        self.cfg = cfg or load_loop_config()
        ensure_loop_dirs(self.cfg)
        self.forge_root = forge_root or Path(self.cfg.azul_data_dir).parent.parent

        # Output directories — all pending human review
        self._pending_prompts_dir = self.cfg.reports_dir / "pending_prompts"
        self._pending_policies_dir = self.cfg.policies_dir.parent / "pending"
        self._stubs_dir = self.forge_root / "action_catalogs" / "stubs"
        self._apply_ledger = self.cfg.azul_data_dir / "apply_ledger.jsonl"

        for directory in [
            self._pending_prompts_dir,
            self._pending_policies_dir,
            self._stubs_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    def apply(self, plan: ImprovementPlan) -> Dict[str, Any]:
        """Route all items in the plan to their appropriate review queues.

        Returns a summary of what was written. Nothing is applied live.
        Raises ApplyError if requires_human_review is False (safety invariant).
        """
        if not plan.requires_human_review:
            raise ApplyError(
                "ImprovementPlan.requires_human_review must be True. "
                "Autonomous self-modification is not permitted."
            )

        run_id = _run_id()
        results: Dict[str, Any] = {
            "run_id": run_id,
            "applied_at": _now_iso(),
            "prompt_drafts": [],
            "contract_stubs": [],
            "policy_pendings": [],
            "distillation_signal": None,
            "errors": [],
        }

        for diff in plan.prompt_diffs:
            try:
                path = self._write_prompt_draft(run_id=run_id, diff=diff)
                results["prompt_drafts"].append(str(path))
            except Exception as exc:
                results["errors"].append(f"prompt_diff({diff.target_file}): {exc}")

        for patch in plan.contract_patches:
            try:
                path = self._write_contract_stub(run_id=run_id, patch=patch)
                results["contract_stubs"].append(str(path))
            except Exception as exc:
                results["errors"].append(f"contract_patch({patch.contract_name}): {exc}")

        for adjustment in plan.policy_adjustments:
            try:
                path = self._write_policy_pending(run_id=run_id, adjustment=adjustment)
                results["policy_pendings"].append(str(path))
            except Exception as exc:
                results["errors"].append(f"policy_adjustment({adjustment.domain}): {exc}")

        if plan.distillation_batch:
            results["distillation_signal"] = self._signal_distillation(plan.distillation_batch)

        self._append_ledger(run_id=run_id, plan=plan, results=results)
        return results

    # ------------------------------------------------------------------
    # Private writers — each produces a human-reviewable artifact
    # ------------------------------------------------------------------

    def _write_prompt_draft(self, *, run_id: str, diff: PromptDiff) -> Path:
        """Write a human-readable prompt change proposal to the pending_prompts dir."""
        slug = Path(diff.target_file).stem.replace(" ", "_").lower()[:40]
        filename = f"{run_id}_{slug}_prompt_draft.md"
        path = self._pending_prompts_dir / filename

        lines = [
            f"# Prompt Draft: {diff.target_file}",
            f"",
            f"**Run ID:** {run_id}",
            f"**Target file:** `{diff.target_file}`",
            f"**Rationale:** {diff.rationale}",
            f"",
        ]
        if diff.additions:
            lines += ["## Proposed Additions", ""]
            for item in diff.additions:
                lines.append(f"- {item}")
            lines.append("")
        if diff.removals:
            lines += ["## Proposed Removals", ""]
            for item in diff.removals:
                lines.append(f"- {item}")
            lines.append("")
        if diff.examples:
            lines += ["## Supporting Examples", ""]
            for example in diff.examples:
                lines.append(f"```")
                lines.append(example)
                lines.append(f"```")
            lines.append("")
        lines += [
            "---",
            "_Review this draft and apply changes manually to the target file._",
            "_Delete this file once applied or rejected._",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def _write_contract_stub(self, *, run_id: str, patch: ContractPatch) -> Path:
        """Write a contract patch as a stub YAML for the existing stub approval workflow."""
        safe_name = patch.contract_name.replace(".yaml", "").replace(" ", "_")[:60]
        filename = f"{safe_name}.yaml"
        path = self._stubs_dir / filename

        existing: Dict[str, Any] = {}
        if path.exists():
            try:
                existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                pass

        stub: Dict[str, Any] = {
            **existing,
            **patch.field_changes,
            "_improvement_metadata": {
                "run_id": run_id,
                "rationale": patch.rationale,
                "generated_at": _now_iso(),
                "status": "pending_approval",
            },
        }

        path.write_text(yaml.safe_dump(stub, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return path

    def _write_policy_pending(self, *, run_id: str, adjustment: PolicyAdjustment) -> Path:
        """Write a policy adjustment to the pending/ dir — not loaded by ForgeGate until approved."""
        safe_domain = adjustment.domain.replace(".", "_").replace(" ", "_")[:50]
        filename = f"{run_id}_{safe_domain}_policy_pending.yaml"
        path = self._pending_policies_dir / filename

        payload: Dict[str, Any] = {
            "domain": adjustment.domain,
            "threshold_changes": adjustment.threshold_changes,
            "rationale": adjustment.rationale,
            "expected_impact": adjustment.expected_impact,
            "_improvement_metadata": {
                "run_id": run_id,
                "generated_at": _now_iso(),
                "status": "pending_approval",
                "instruction": (
                    "Review this adjustment. If approved, merge threshold_changes into "
                    "the active policy file for this domain in config/gate_policies/. "
                    "ForgeGate does not load files from this pending/ directory."
                ),
            },
        }
        path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return path

    def _signal_distillation(self, batch: DistillationBatch) -> Dict[str, Any]:
        """Record that a distillation batch is ready. No training is triggered here."""
        signal = {
            "signaled_at": _now_iso(),
            "pair_count": batch.pair_count,
            "avg_score": batch.avg_score,
            "domains": batch.domains,
            "manifest_path": batch.manifest_path,
            "note": (
                "Batch ready. ForgedRoot has no built-in trainer. "
                "An external consumer (e.g. SAM DistillationTrainer) should read "
                "manifest_path and execute training."
            ),
        }
        signal_path = self.cfg.distillation_batches_dir / "ready_signal.jsonl"
        with signal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(signal) + "\n")
        return signal

    def _append_ledger(
        self,
        *,
        run_id: str,
        plan: ImprovementPlan,
        results: Dict[str, Any],
    ) -> None:
        """Append an audit entry to the apply ledger (append-only)."""
        entry = {
            "run_id": run_id,
            "applied_at": results["applied_at"],
            "prompt_draft_count": len(results["prompt_drafts"]),
            "contract_stub_count": len(results["contract_stubs"]),
            "policy_pending_count": len(results["policy_pendings"]),
            "distillation_signaled": results["distillation_signal"] is not None,
            "error_count": len(results["errors"]),
            "errors": results["errors"],
        }
        with self._apply_ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")


def apply_plan_from_file(plan_path: Path, forge_root: Optional[Path] = None) -> Dict[str, Any]:
    """Convenience function: load an ImprovementPlan from a JSON file and apply it.

    The JSON file must conform to improvement_plan.schema.json.
    Returns the apply result summary.
    """
    raw = plan_path.read_text(encoding="utf-8")
    data = json.loads(raw)

    schema_version = data.get("schema_version")
    if schema_version != "1.0.0":
        raise ApplyError(
            f"Unsupported schema_version: '{schema_version}'. Expected '1.0.0'. "
            "Upgrade the plan format or pin to the correct schema version."
        )

    plan = ImprovementPlan(
        prompt_diffs=[PromptDiff(**d) for d in data.get("prompt_diffs", [])],
        contract_patches=[ContractPatch(**p) for p in data.get("contract_patches", [])],
        policy_adjustments=[PolicyAdjustment(**a) for a in data.get("policy_adjustments", [])],
        distillation_batch=(
            DistillationBatch(**data["distillation_batch"])
            if data.get("distillation_batch")
            else None
        ),
        requires_human_review=bool(data.get("requires_human_review", True)),
    )

    applier = ImprovementApplier(forge_root=forge_root)
    return applier.apply(plan)
