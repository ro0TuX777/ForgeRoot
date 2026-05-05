"""
Phase 1 test 7: Legal hold blocks deletion/purge.
"""
from forgeledger.backend import HoldSelector
from forgeledger.legal_hold import HoldRegistry


# ---------------------------------------------------------------------------
# Test 7: Legal hold blocks deletion
# ---------------------------------------------------------------------------

def test_legal_hold_blocks_event_ids():
    registry = HoldRegistry()
    event_ids = ["evt-001", "evt-002", "evt-003"]

    result = registry.apply(
        HoldSelector(tenant_id="tenant-001", reason="regulatory_investigation"),
        event_ids=event_ids,
    )

    assert result.applied_count == 3
    assert result.error is None
    assert registry.is_on_hold("evt-001")
    assert registry.is_on_hold("evt-002")
    assert registry.is_on_hold("evt-003")
    assert not registry.is_on_hold("evt-999")


def test_hold_release_removes_block():
    registry = HoldRegistry()
    result = registry.apply(
        HoldSelector(tenant_id="tenant-001", reason="audit_hold"),
        event_ids=["evt-001"],
    )
    assert registry.is_on_hold("evt-001")

    release = registry.release(result.hold_id, reason="investigation_closed")
    assert release.error is None
    assert not registry.is_on_hold("evt-001")


def test_release_nonexistent_hold_returns_error():
    registry = HoldRegistry()
    result = registry.release("nonexistent-hold-id", reason="oops")
    assert result.error is not None
    assert result.applied_count == 0


def test_active_holds_excludes_released():
    registry = HoldRegistry()
    r1 = registry.apply(HoldSelector(tenant_id="t1", reason="r1"), ["e1", "e2"])
    r2 = registry.apply(HoldSelector(tenant_id="t2", reason="r2"), ["e3"])

    registry.release(r1.hold_id, reason="done")

    active = registry.get_active_holds()
    assert len(active) == 1
    assert active[0].hold_id == r2.hold_id


def test_get_held_event_ids_returns_only_active():
    registry = HoldRegistry()
    r1 = registry.apply(HoldSelector(tenant_id="t1", reason="r1"), ["e1", "e2"])
    r2 = registry.apply(HoldSelector(tenant_id="t2", reason="r2"), ["e3"])
    registry.release(r1.hold_id, reason="released")

    held = registry.get_held_event_ids()
    assert "e3" in held
    assert "e1" not in held
    assert "e2" not in held


def test_multiple_holds_on_same_event():
    registry = HoldRegistry()
    r1 = registry.apply(HoldSelector(tenant_id="t1", reason="hold-1"), ["evt-001"])
    r2 = registry.apply(HoldSelector(tenant_id="t1", reason="hold-2"), ["evt-001"])

    registry.release(r1.hold_id, reason="done")
    # evt-001 is still held by r2
    assert registry.is_on_hold("evt-001")

    registry.release(r2.hold_id, reason="done")
    assert not registry.is_on_hold("evt-001")
