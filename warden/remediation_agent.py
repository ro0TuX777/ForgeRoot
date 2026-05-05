"""Planner-Worker remediator for patch drafting and auto-remediation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .llm_gateway import GatewayError, GatewayResponse, LLMGateway


@dataclass(frozen=True)
class DraftArtifact:
    plan_text: str
    patch_text: str
    plan_trace: Dict[str, Any]
    patch_trace: Dict[str, Any]
    impact_map: str


class RemediationAgent:
    """Generates plans/patches and iterates against Azul verdict feedback."""

    def __init__(
        self,
        *,
        gateway: Optional[LLMGateway] = None,
        forge_root: Optional[Path] = None,
        project_root: Optional[Path] = None,
    ) -> None:
        self.gateway = gateway or LLMGateway()
        self.forge_root = forge_root or Path.cwd()
        self.project_root = project_root or self.forge_root

    @staticmethod
    def _json_preview(payload: Dict[str, Any], limit_chars: int = 12000) -> str:
        try:
            text = json.dumps(payload, indent=2)
        except Exception:
            text = str(payload)
        return text[:limit_chars]

    @staticmethod
    def _extract_patch_block(text: str) -> str:
        stripped = text.strip()
        if not stripped:
            return ""

        fence = re.findall(r"```(?:diff|patch)?\n([\s\S]*?)```", stripped, flags=re.IGNORECASE)
        for candidate in fence:
            candidate = candidate.strip()
            if candidate.startswith("--- ") or candidate.startswith("diff --git"):
                return candidate + "\n"

        if "--- " in stripped and "+++ " in stripped:
            start = stripped.find("--- ")
            return stripped[start:].strip() + "\n"
        return stripped + "\n"

    @staticmethod
    def _trace_meta(response: GatewayResponse) -> Dict[str, Any]:
        return {
            "model_used": response.trace.model_used,
            "task_tier": response.trace.task_tier,
            "reasoning_steps": response.trace.reasoning_steps,
            "confidence_score": response.trace.confidence_score,
            "raw_response_path": response.trace.raw_response_path,
        }

    def _build_impact_map(
        self,
        *,
        intent: str,
        domain: str,
        system_catalog: Dict[str, Any],
        danger_map: Dict[str, Any],
    ) -> tuple[str, Dict[str, Any]]:
        prompt = (
            "You are the Planner (Scout). Identify likely impacted units and risk surfaces.\n"
            f"Domain: {domain}\n"
            f"Intent: {intent}\n"
            "Return concise bullets only.\n\n"
            "System catalog excerpt:\n"
            f"{self._json_preview(system_catalog, limit_chars=7000)}\n\n"
            "Danger map excerpt:\n"
            f"{self._json_preview(danger_map, limit_chars=3000)}"
        )
        result = self.gateway.complete(
            task_tier="TIER_SCAN",
            prompt=prompt,
            system_prompt="Output 4-8 bullets with unit ids, files, and risks.",
            reasoning_steps=[
                "Mapped intent to catalog units",
                "Highlighted high-risk governance surfaces",
            ],
            metadata={"source": "remediation_agent.impact_map", "domain": domain},
        )
        return result.text.strip(), self._trace_meta(result)

    def build_plan(
        self,
        *,
        intent: str,
        domain: str,
        system_catalog: Dict[str, Any],
        danger_map: Dict[str, Any],
        previous_verdict_reason: str = "",
        attempt: int = 1,
    ) -> tuple[str, Dict[str, Any], str, Dict[str, Any]]:
        impact_map, impact_trace = self._build_impact_map(
            intent=intent,
            domain=domain,
            system_catalog=system_catalog,
            danger_map=danger_map,
        )
        prompt = (
            "You are the Blueprint Generator (Deep reasoning).\n"
            f"Attempt: {attempt}\n"
            f"Domain: {domain}\n"
            f"Intent: {intent}\n"
            f"Previous verdict reason: {previous_verdict_reason or 'none'}\n\n"
            "Impacted units:\n"
            f"{impact_map}\n\n"
            "Generate a short implementation plan with sections:\n"
            "1) Goal\n2) Target files\n3) Required code changes\n"
            "4) Guard/compliance checks to satisfy\n5) Test notes."
        )
        result = self.gateway.complete(
            task_tier="TIER_REASONING",
            prompt=prompt,
            system_prompt="Be explicit, deterministic, and governance-first.",
            reasoning_steps=[
                "Converted intent into verifiable sub-tasks",
                "Embedded governance constraints from danger map",
            ],
            metadata={"source": "remediation_agent.plan", "domain": domain, "attempt": attempt},
        )
        return result.text.strip(), self._trace_meta(result), impact_map, impact_trace

    def build_patch(
        self,
        *,
        intent: str,
        domain: str,
        plan_text: str,
        previous_patch: str = "",
        previous_verdict_reason: str = "",
        attempt: int = 1,
    ) -> tuple[str, Dict[str, Any]]:
        prompt = (
            "You are the Worker (Patch Engine). Produce a unified diff only.\n"
            f"Attempt: {attempt}\n"
            f"Domain: {domain}\n"
            f"Intent: {intent}\n"
            f"Previous verdict reason: {previous_verdict_reason or 'none'}\n\n"
            "Implementation plan:\n"
            f"{plan_text[:9000]}\n\n"
            "Previous patch (if any):\n"
            f"{previous_patch[:6000] if previous_patch else 'none'}\n\n"
            "Rules:\n"
            "- Output MUST be a unified diff patch.\n"
            "- Do not include markdown commentary.\n"
            "- If verdict mentions guard predicate violation, fix the violating call accordingly.\n"
            "- Keep patch minimal and compilable."
        )
        result = self.gateway.complete(
            task_tier="TIER_VERDICT",
            prompt=prompt,
            system_prompt="Return only unified diff text beginning with --- a/...",
            reasoning_steps=[
                "Translated plan into code edit operations",
                "Applied governance feedback from prior verdict",
            ],
            metadata={"source": "remediation_agent.patch", "domain": domain, "attempt": attempt},
        )
        patch = self._extract_patch_block(result.text)
        return patch, self._trace_meta(result)

    def generate_draft(
        self,
        *,
        intent: str,
        domain: str,
        system_catalog: Dict[str, Any],
        danger_map: Dict[str, Any],
    ) -> DraftArtifact:
        plan, plan_trace, impact_map, impact_trace = self.build_plan(
            intent=intent,
            domain=domain,
            system_catalog=system_catalog,
            danger_map=danger_map,
        )
        patch, patch_trace = self.build_patch(
            intent=intent,
            domain=domain,
            plan_text=plan,
            attempt=1,
        )
        merged_plan_trace = dict(plan_trace)
        merged_plan_trace["impact_map_trace"] = impact_trace
        return DraftArtifact(
            plan_text=plan,
            patch_text=patch,
            plan_trace=merged_plan_trace,
            patch_trace=patch_trace,
            impact_map=impact_map,
        )

    def remediate_reject_loop(
        self,
        *,
        intent: str,
        domain: str,
        initial_patch: str,
        system_catalog: Dict[str, Any],
        danger_map: Dict[str, Any],
        verify_fn: Callable[[str, str, int], Dict[str, Any]],
        max_attempts: int = 3,
        summary_prefix: str = "Auto-remediation",
        start_from_reject: bool = False,
        initial_verdict_reason: str = "",
    ) -> Dict[str, Any]:
        attempts: List[Dict[str, Any]] = []
        patch = initial_patch
        verdict_reason = initial_verdict_reason or ""

        if start_from_reject:
            # Skip re-verifying a patch that is already known REJECTED and generate
            # the first corrective attempt immediately from the supplied verdict reason.
            plan, plan_trace, impact_map, impact_trace = self.build_plan(
                intent=intent,
                domain=domain,
                system_catalog=system_catalog,
                danger_map=danger_map,
                previous_verdict_reason=verdict_reason,
                attempt=1,
            )
            patch, patch_trace = self.build_patch(
                intent=intent,
                domain=domain,
                plan_text=plan,
                previous_patch=patch,
                previous_verdict_reason=verdict_reason,
                attempt=1,
            )
            attempts.append(
                {
                    "attempt": 0,
                    "summary": f"{summary_prefix} seed rejection",
                    "patch": initial_patch,
                    "status": "REJECTED",
                    "verdict": "reject",
                    "verdict_reason": verdict_reason,
                    "remediation_plan": plan,
                    "remediation_impact_map": impact_map,
                    "plan_trace": {**plan_trace, "impact_map_trace": impact_trace},
                    "patch_trace": patch_trace,
                }
            )

        for attempt in range(1, max_attempts + 1):
            summary = f"{summary_prefix} attempt {attempt}: {intent[:120]}"
            verify_result = verify_fn(patch, summary, attempt)
            ticket = verify_result.get("ticket") or {}
            status = str(ticket.get("status") or "")
            verdict = str(ticket.get("verdict") or "")
            verdict_reason = str(ticket.get("verdict_reason") or "")

            attempt_record = {
                "attempt": attempt,
                "summary": summary,
                "patch": patch,
                "verify": verify_result,
                "status": status,
                "verdict": verdict,
                "verdict_reason": verdict_reason,
            }
            attempts.append(attempt_record)

            if status in {"COMPLETED", "WARNED"} and verdict == "pass":
                return {
                    "status": "ok",
                    "resolved": True,
                    "attempts": attempts,
                    "final_patch": patch,
                    "final_verify": verify_result,
                }

            if status != "REJECTED" or attempt >= max_attempts:
                break

            plan, plan_trace, impact_map, impact_trace = self.build_plan(
                intent=intent,
                domain=domain,
                system_catalog=system_catalog,
                danger_map=danger_map,
                previous_verdict_reason=verdict_reason,
                attempt=attempt + 1,
            )
            patch, patch_trace = self.build_patch(
                intent=intent,
                domain=domain,
                plan_text=plan,
                previous_patch=patch,
                previous_verdict_reason=verdict_reason,
                attempt=attempt + 1,
            )
            attempts[-1]["remediation_plan"] = plan
            attempts[-1]["remediation_impact_map"] = impact_map
            attempts[-1]["plan_trace"] = {**plan_trace, "impact_map_trace": impact_trace}
            attempts[-1]["patch_trace"] = patch_trace

        return {
            "status": "ok",
            "resolved": False,
            "attempts": attempts,
            "final_patch": patch,
            "final_verify": attempts[-1].get("verify") if attempts else {},
            "final_verdict_reason": verdict_reason,
        }


__all__ = ["DraftArtifact", "RemediationAgent", "GatewayError"]
