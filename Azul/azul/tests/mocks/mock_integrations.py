"""
mocks/mock_integrations.py — Fake implementations of all 3 integrations
========================================================================
Replaces real framework calls during testing.  Injected via monkeypatch.

All mocks are configurable:
    mock_harbor.should_fail = True     → returns _error
    mock_forge_works.score = 72.0      → sets review_bundle total_score
    mock_forge_scaffold.fail = True    → returns _error
"""

from __future__ import annotations

from typing import Any, Dict, Optional


# ── Shared envelope helpers ───────────────────────────────────────────────────

def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "ok", "payload": payload}


def _error(code: str, message: str) -> Dict[str, Any]:
    return {"status": "error", "error": {"code": code, "message": message, "details": {}}}


# ── MockForgeHarbor ───────────────────────────────────────────────────────────

class MockForgeHarbor:
    def __init__(self):
        self.should_fail            = False
        self.release_should_fail    = False
        self.env_id                 = "env-mock-001"
        self.requests_made          = []
        self.releases_made          = []

    def request_environment(self, ticket_id: str) -> Dict[str, Any]:
        self.requests_made.append(ticket_id)
        if self.should_fail:
            return _error("ENVIRONMENT_UNAVAILABLE", "No environments available")
        return _ok({"environment_id": self.env_id})

    def release_environment(self, environment_id: str) -> Dict[str, Any]:
        self.releases_made.append(environment_id)
        if self.release_should_fail:
            return _error("RELEASE_ERROR", "Release failed")
        return _ok({"released": True, "environment_id": environment_id})

    def reset(self):
        self.should_fail = False
        self.release_should_fail = False
        self.requests_made.clear()
        self.releases_made.clear()


# ── MockForgeScaffold ─────────────────────────────────────────────────────────

class MockForgeScaffold:
    def __init__(self):
        self.should_fail     = False
        self.unit_count      = 3
        self.calls_made      = []

    def analyze_blast_radius(self, target_files, project_root=None) -> Dict[str, Any]:
        self.calls_made.append(target_files)
        if self.should_fail:
            return _error("FORGE_SCAFFOLD_ERROR", "ForgeScaffold failure")
        mock_units = [
            {"id": f"unit.{i}", "path": f"module_{i}.py", "type": "module"}
            for i in range(self.unit_count)
        ]
        return _ok({
            "blast_radius": {
                "units":          mock_units,
                "affected_files": target_files,
                "total_units":    self.unit_count,
                "affected_count": min(self.unit_count, len(target_files)),
            }
        })

    def reset(self):
        self.should_fail = False
        self.calls_made.clear()


# ── MockForgeWorks ────────────────────────────────────────────────────────────

class MockForgeWorks:
    def __init__(self):
        self.should_fail         = False
        self.score               = 91.5
        self.pass_fail           = True
        self.deny_count          = 0
        self.oracle_mismatch     = 0
        self.escalation_count    = 0
        self.calls_made          = []

    def execute_verification(self, planner_spec: Dict[str, Any]) -> Dict[str, Any]:
        self.calls_made.append(planner_spec.get("spec_id"))
        if self.should_fail:
            return _error("FORGE_WORKS_ERROR", "ForgeWorks pipeline error")

        review_bundle = {
            "bundle_id":   "brv-mock-001",
            "summary":     {
                "domain":   planner_spec.get("domain", "ci_change_control"),
                "mode":     planner_spec.get("mode", "shadow"),
                "pass_fail": self.pass_fail,
                "total_score": self.score,
                "one_line": f"mock run: score {self.score:.1f}",
            },
            "gates_passed": 9,
            "failure_gate": None,
            "failure_reason": None,
            "metrics": {
                "total_score":          self.score,
                "pass_fail":            self.pass_fail,
                "deny_count":           self.deny_count,
                "oracle_mismatch_count": self.oracle_mismatch,
                "escalation_count":     self.escalation_count,
            },
            "artifacts": {},
            "risk_assessment": {
                "highest_risk_level": "med",
                "deny_count": self.deny_count,
                "oracle_mismatch_count": self.oracle_mismatch,
                "escalation_count": self.escalation_count,
            },
        }

        receipt = {
            "status":        "SUCCEEDED",
            "gates_passed":  9,
            "metrics":       review_bundle["metrics"],
            "review_bundle": review_bundle,
        }

        return _ok({"receipt": receipt, "review_bundle": review_bundle})

    def reset(self):
        self.should_fail = False
        self.score = 91.5
        self.pass_fail = True
        self.deny_count = 0
        self.oracle_mismatch = 0
        self.escalation_count = 0
        self.calls_made.clear()
