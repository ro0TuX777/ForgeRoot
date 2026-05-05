from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from warden.llm_gateway import GatewayResponse, ReasoningTrace
from warden.remediation_agent import RemediationAgent


class FakeGateway:
    def __init__(self, responses: List[Dict[str, str]]):
        self.responses = list(responses)
        self.calls: List[str] = []

    def complete(self, *, task_tier: str, prompt: str, **_: Any) -> GatewayResponse:
        self.calls.append(task_tier)
        if not self.responses:
            raise RuntimeError("no fake responses remaining")
        item = self.responses.pop(0)
        text = item["text"]
        trace = ReasoningTrace(
            model_used=item.get("model", f"fake/{task_tier.lower()}"),
            task_tier=task_tier,
            reasoning_steps=["fake"],
            confidence_score=0.9,
            raw_response_path=f"/tmp/{task_tier.lower()}.json",
        )
        return GatewayResponse(text=text, trace=trace, provider_payload={"fake": True})


def test_generate_draft_uses_planner_then_worker():
    gateway = FakeGateway(
        responses=[
            {"text": "- unit: external.subprocess"},  # TIER_SCAN impact map
            {"text": "1) Goal\n2) Target files\n3) Guard checks"},  # TIER_REASONING plan
            {
                "text": "```diff\n--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-print('x')\n+print('y')\n```"
            },  # TIER_VERDICT patch
        ]
    )
    agent = RemediationAgent(gateway=gateway)

    draft = agent.generate_draft(
        intent="update print",
        domain="ci_change_control",
        system_catalog={"units": [{"id": "external.subprocess"}]},
        danger_map={"risks": []},
    )

    assert gateway.calls == ["TIER_SCAN", "TIER_REASONING", "TIER_VERDICT"]
    assert "Goal" in draft.plan_text
    assert draft.patch_text.startswith("--- a/src/app.py")


def test_reject_loop_attempts_fix_until_pass():
    gateway = FakeGateway(
        responses=[
            {"text": "- impacted: src/app/__init__.py"},
            {"text": "Plan: replace unsafe subprocess usage."},
            {
                "text": "```patch\n--- a/src/app/__init__.py\n+++ b/src/app/__init__.py\n@@ -1,4 +1,4 @@\n-subprocess.check_call(['rm','-rf','/'], shell=True)\n+subprocess.check_call(['git status'], shell=False)\n```"
            },
        ]
    )
    agent = RemediationAgent(gateway=gateway)

    def verify_fn(diff_text: str, summary: str, attempt: int) -> Dict[str, Any]:
        if attempt == 1:
            return {
                "ticket": {
                    "status": "REJECTED",
                    "verdict": "reject",
                    "verdict_reason": "Guard Predicate Violation: rm and shell=True",
                },
                "output": "reject",
            }
        return {
            "ticket": {
                "status": "COMPLETED",
                "verdict": "pass",
                "verdict_reason": "",
            },
            "output": "pass",
        }

    result = agent.remediate_reject_loop(
        intent="Fix subprocess policy violation",
        domain="system_operations",
        initial_patch="--- a/src/app/__init__.py\n+++ b/src/app/__init__.py\n@@\n- bad\n+ bad\n",
        system_catalog={"units": [{"id": "external.subprocess"}]},
        danger_map={"risks": ["subprocess"]},
        verify_fn=verify_fn,
        max_attempts=3,
        summary_prefix="remediate",
    )

    assert result["resolved"] is True
    assert len(result["attempts"]) == 2
    assert result["attempts"][0]["status"] == "REJECTED"
    assert result["attempts"][1]["status"] == "COMPLETED"
    assert "shell=False" in result["final_patch"]


def test_reject_loop_can_start_from_known_reject_without_duplicate_verify():
    gateway = FakeGateway(
        responses=[
            {"text": "- impacted: src/app/__init__.py"},
            {"text": "Plan: replace unsafe subprocess usage."},
            {
                "text": "```patch\n--- a/src/app/__init__.py\n+++ b/src/app/__init__.py\n@@ -1,4 +1,4 @@\n-subprocess.check_call(['rm','-rf','/'], shell=True)\n+subprocess.check_call(['git status'], shell=False)\n```"
            },
        ]
    )
    agent = RemediationAgent(gateway=gateway)

    attempts_seen: list[int] = []

    def verify_fn(diff_text: str, summary: str, attempt: int) -> Dict[str, Any]:
        attempts_seen.append(attempt)
        return {
            "ticket": {
                "status": "COMPLETED",
                "verdict": "pass",
                "verdict_reason": "",
            },
            "output": "pass",
        }

    result = agent.remediate_reject_loop(
        intent="Fix subprocess policy violation",
        domain="system_operations",
        initial_patch="--- a/src/app/__init__.py\n+++ b/src/app/__init__.py\n@@\n- bad\n+ bad\n",
        system_catalog={"units": [{"id": "external.subprocess"}]},
        danger_map={"risks": ["subprocess"]},
        verify_fn=verify_fn,
        max_attempts=3,
        summary_prefix="remediate",
        start_from_reject=True,
        initial_verdict_reason="Guard Predicate Violation: rm and shell=True",
    )

    assert result["resolved"] is True
    assert attempts_seen == [1]
    assert result["attempts"][0]["attempt"] == 0
    assert result["attempts"][0]["status"] == "REJECTED"
    assert result["attempts"][1]["status"] == "COMPLETED"
