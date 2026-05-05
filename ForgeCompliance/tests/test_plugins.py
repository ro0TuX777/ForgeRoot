"""
Phase 2 test 5: Sector plugins can override default retention.
"""
from forgeledger.hash_chain import attach_integrity
from forgeledger.schema import (
    LEDGER_VERSION,
    Actor,
    Decision,
    Evidence,
    EventType,
    Integrity,
    LedgerEvent,
    Policy,
    RetentionClass,
    SystemContext,
    Tenant,
)
from forgecompliance.plugins import ALL_PLUGINS
from forgecompliance.plugins.nz_health import NZHealthPlugin
from forgecompliance.plugins.nz_government import NZGovernmentPlugin
from forgecompliance.plugins.nz_finance import NZFinancePlugin
from forgecompliance.plugins.au_finance import AUFinancePlugin
from forgecompliance.plugins.generic_soc2 import GenericSOC2Plugin
from forgecompliance.plugins.generic_nist import GenericNISTPlugin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    event_type: EventType,
    data_residency: str = "NZ",
    retention_class: RetentionClass = RetentionClass.OPERATIONAL_30D,
    control_tags: list[str] | None = None,
    legal_hold: bool = False,
    data_sensitivity: str | None = None,
) -> LedgerEvent:
    payload = {"data_sensitivity": data_sensitivity} if data_sensitivity else None
    return attach_integrity(
        LedgerEvent(
            event_id="evt-plugin-001",
            ledger_version=LEDGER_VERSION,
            event_type=event_type,
            event_time="2026-04-28T10:00:00Z",
            actor=Actor(actor_type="agent", actor_id="test.agent", role="test"),
            tenant=Tenant(tenant_id="t-001", customer_boundary="b", data_residency=data_residency),
            system_context=SystemContext(source_module="CONCORD", environment="local", deployment_id="test"),
            decision=Decision(decision_type="allow", reason="test", risk_level="low"),
            evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=[]),
            policy=Policy(
                policy_id="p-001",
                policy_hash="abc",
                retention_class=retention_class,
                legal_hold=legal_hold,
            ),
            control_tags=control_tags or [],
            integrity=Integrity(previous_hash=None, event_hash=""),
            payload=payload,
        ),
        None,
    )


# ---------------------------------------------------------------------------
# Test 5: Sector plugins can override default retention
# ---------------------------------------------------------------------------

def test_nz_health_plugin_overrides_to_health_10y_for_health_identifiable():
    plugin = NZHealthPlugin()
    event = _make_event(
        EventType.AGENT_TOOL_CALL,
        data_sensitivity="health_identifiable",
        retention_class=RetentionClass.OPERATIONAL_30D,
    )
    override = plugin.retention_override(event)
    assert override == RetentionClass.HEALTH_10Y


def test_nz_health_plugin_overrides_via_control_tag():
    plugin = NZHealthPlugin()
    event = _make_event(
        EventType.FORGEGATE_DECISION_RECORD,
        retention_class=RetentionClass.SUPPORT_1Y,
        control_tags=["HIPC.RULE11.ACCESS_LOG"],
    )
    override = plugin.retention_override(event)
    assert override == RetentionClass.HEALTH_10Y


def test_nz_health_plugin_does_not_override_legal_hold():
    plugin = NZHealthPlugin()
    event = _make_event(
        EventType.AGENT_TOOL_CALL,
        data_sensitivity="health_identifiable",
        legal_hold=True,
    )
    override = plugin.retention_override(event)
    assert override is None  # legal_hold is handled by core, plugin defers


def test_nz_health_plugin_returns_none_for_non_health_event():
    plugin = NZHealthPlugin()
    event = _make_event(EventType.CONCORD_ADMISSION_DECISION)
    assert plugin.retention_override(event) is None


def test_nz_government_plugin_upgrades_operational_to_audit_7y():
    plugin = NZGovernmentPlugin()
    event = _make_event(
        EventType.CONCORD_ADMISSION_DECISION,
        data_residency="NZ",
        retention_class=RetentionClass.OPERATIONAL_30D,
    )
    override = plugin.retention_override(event)
    assert override == RetentionClass.AUDIT_7Y


def test_nz_government_plugin_does_not_downgrade_health_10y():
    plugin = NZGovernmentPlugin()
    event = _make_event(
        EventType.CONCORD_ADMISSION_DECISION,
        data_residency="NZ",
        retention_class=RetentionClass.HEALTH_10Y,
    )
    override = plugin.retention_override(event)
    # HEALTH_10Y is above AUDIT_7Y — plugin should not override it down
    assert override is None


def test_nz_finance_plugin_overrides_for_finance_outsourcing():
    plugin = NZFinancePlugin()
    event = _make_event(
        EventType.WARDEN_LLM_CALL_METADATA,
        retention_class=RetentionClass.SUPPORT_1Y,
        data_sensitivity="finance_outsourcing",
    )
    override = plugin.retention_override(event)
    assert override == RetentionClass.AUDIT_7Y


def test_au_finance_plugin_applies_to_nz_residency():
    plugin = AUFinancePlugin()
    event = _make_event(
        EventType.FORGEGATE_DECISION_RECORD,
        data_residency="NZ",
        control_tags=["CPS234.P28.AUDIT"],
    )
    override = plugin.retention_override(event)
    assert override == RetentionClass.AUDIT_7Y


def test_au_finance_plugin_ignores_non_au_nz_residency():
    plugin = AUFinancePlugin()
    event = _make_event(
        EventType.FORGEGATE_DECISION_RECORD,
        data_residency="US",
        control_tags=["CPS234.P28.AUDIT"],
    )
    assert plugin.retention_override(event) is None


def test_generic_soc2_plugin_upgrades_operational_events():
    plugin = GenericSOC2Plugin()
    event = _make_event(
        EventType.CONCORD_ADMISSION_DECISION,
        retention_class=RetentionClass.OPERATIONAL_30D,
    )
    override = plugin.retention_override(event)
    assert override == RetentionClass.SUPPORT_1Y


def test_nist_plugin_always_returns_none():
    plugin = GenericNISTPlugin()
    for et in EventType:
        event = _make_event(et)
        assert plugin.retention_override(event) is None


# ---------------------------------------------------------------------------
# Plugin registry sanity checks
# ---------------------------------------------------------------------------

def test_all_plugins_have_required_class_vars():
    for plugin in ALL_PLUGINS:
        assert hasattr(plugin, "profile_id"), f"{type(plugin).__name__} missing profile_id"
        assert hasattr(plugin, "jurisdiction"), f"{type(plugin).__name__} missing jurisdiction"
        assert hasattr(plugin, "sector"), f"{type(plugin).__name__} missing sector"
        assert plugin.profile_id, f"{type(plugin).__name__}.profile_id is empty"


def test_all_plugin_ids_are_unique():
    ids = [p.profile_id for p in ALL_PLUGINS]
    assert len(ids) == len(set(ids)), f"Duplicate plugin profile_ids: {ids}"


def test_all_plugins_validate_package_returns_list():
    for plugin in ALL_PLUGINS:
        result = plugin.validate_package({})
        assert isinstance(result, list), f"{type(plugin).__name__}.validate_package must return list"


def test_all_plugins_extra_control_tags_returns_list():
    event = _make_event(EventType.CONCORD_ADMISSION_DECISION)
    for plugin in ALL_PLUGINS:
        result = plugin.extra_control_tags(event)
        assert isinstance(result, list), f"{type(plugin).__name__}.extra_control_tags must return list"
