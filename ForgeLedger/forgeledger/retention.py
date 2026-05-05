from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from forgeledger.schema import LedgerEvent, RetentionClass

_CONFIG_PATH = Path(__file__).parent / "config" / "retention_policies.yaml"
_config: Optional[dict] = None


def _load_config() -> dict:
    global _config
    if _config is None:
        import yaml
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f)
    return _config  # type: ignore[return-value]


def _reload_config() -> None:
    """Force reload — used in tests to reset state."""
    global _config
    _config = None


def classify_event(event: "LedgerEvent") -> "RetentionClass":
    """Determine the retention class for an event. legal_hold always wins."""
    from forgeledger.schema import RetentionClass
    config = _load_config()

    if event.policy.legal_hold:
        return RetentionClass.LEGAL_HOLD

    # Payload sensitivity override
    if event.payload:
        sensitivity = event.payload.get("data_sensitivity", "")
        overrides = config.get("sensitivity_overrides", {})
        if sensitivity in overrides:
            rc_val = overrides[sensitivity].get("retention_class")
            if rc_val:
                return RetentionClass(rc_val)

    # Control tag override for finance outsourcing
    if any("finance_outsourcing" in tag.lower() for tag in event.control_tags):
        return RetentionClass.AUDIT_7Y

    # Event type default
    defaults = config.get("event_type_defaults", {})
    rc_val = defaults.get(event.event_type.value)
    if rc_val:
        return RetentionClass(rc_val)

    return RetentionClass(config.get("default_class", "operational_30d"))


def get_retention_policy(retention_class: "RetentionClass") -> dict:
    config = _load_config()
    return config["retention_classes"].get(retention_class.value, {})


def is_deletion_eligible(event: "LedgerEvent", held_event_ids: set[str]) -> bool:
    if event.event_id in held_event_ids:
        return False
    if event.policy.legal_hold:
        return False
    policy = get_retention_policy(event.policy.retention_class)
    return policy.get("deletion_allowed", True)
