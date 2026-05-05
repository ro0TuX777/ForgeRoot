import pytest

from forgeworks.runner.approvals import ApprovalPolicyError, requires_approval, resolve_approval


def _run_config():
    return {
        "approval_policy": {
            "ramped_auto_allow_risk_tiers": ["low"],
            "ramped_auto_allow_side_effects": ["none", "read"],
            "auto_reject_actions": [],
        }
    }


def _decision(decision: str):
    return {"decision": decision, "decision_id": "abc"}


def _action(risk: str, side_effect: str, action_id: str = "ticket.advance_phase"):
    return {"metadata": {"risk_tier": risk, "side_effect": side_effect}, "action_id": action_id}


def test_supervised_requires_approval_for_allow():
    assert requires_approval(_decision("ALLOW"), _action("low", "none"), "supervised", _run_config()) is True
    assert requires_approval(_decision("ALLOW_WITH_MODS"), _action("low", "none"), "supervised", _run_config()) is True


def test_ramped_skips_low_risk_none_read():
    assert requires_approval(_decision("ALLOW"), _action("low", "none"), "ramped", _run_config()) is False
    assert requires_approval(_decision("ALLOW"), _action("low", "read"), "ramped", _run_config()) is False


def test_ramped_requires_for_higher_risk():
    assert requires_approval(_decision("ALLOW"), _action("med", "read"), "ramped", _run_config()) is True
    assert requires_approval(_decision("ALLOW"), _action("high", "write"), "ramped", _run_config()) is True


def test_escalate_always_requires():
    assert requires_approval(_decision("ESCALATE"), _action("low", "none"), "ramped", _run_config()) is True


def test_approval_record_shape():
    record = resolve_approval("T1", "ticket.advance_phase", _decision("ALLOW"), _action("low", "none"), "ramped", _run_config())
    assert record["schema_version"] == "0.1"
    assert record["approval_outcome"] in {"APPROVED", "REJECTED", "NOT_REQUIRED"}


def test_missing_policy_fails():
    with pytest.raises(ApprovalPolicyError):
        requires_approval(_decision("ALLOW"), _action("low", "none"), "supervised", {})


def test_ramped_allow_with_mods_requires_approval():
    assert requires_approval(_decision("ALLOW_WITH_MODS"), _action("low", "none"), "ramped", _run_config()) is True


def test_ramped_auto_reject_action_requires_approval():
    config = _run_config()
    config["approval_policy"]["auto_reject_actions"] = ["ticket.advance_phase"]
    assert requires_approval(_decision("ALLOW"), _action("low", "none"), "ramped", config) is True


def test_resolve_approval_not_required_for_ramped_low_none():
    record = resolve_approval("T1", "ticket.advance_phase", _decision("ALLOW"), _action("low", "none"), "ramped", _run_config())
    assert record["approval_outcome"] == "NOT_REQUIRED"
    assert record["approval_required"] is False


def test_resolve_approval_supervised_allow_is_approved():
    record = resolve_approval("T1", "ticket.advance_phase", _decision("ALLOW"), _action("low", "none"), "supervised", _run_config())
    assert record["approval_outcome"] == "APPROVED"
    assert record["approval_required"] is True


def test_requires_approval_unknown_mode_defaults_true():
    assert requires_approval(_decision("ALLOW"), _action("low", "none"), "unknown-mode", _run_config()) is True
