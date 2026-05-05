import pytest

from forgeworks.adapters.base import AdapterError, get_adapter
from forgeworks.adapters.registry import register_builtin_adapters


def test_adapter_lookup():
    register_builtin_adapters()
    adapter = get_adapter("ci_change_control")
    assert adapter.domain == "ci_change_control"


def test_unknown_domain_fails():
    register_builtin_adapters()
    with pytest.raises(AdapterError):
        get_adapter("unknown_domain")
