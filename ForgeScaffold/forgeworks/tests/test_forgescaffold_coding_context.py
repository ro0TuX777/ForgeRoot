"""Tests for ForgeScaffold link resolution used by coding context."""

import importlib.util
from pathlib import Path

import pytest

_PKG_ROOT = Path(__file__).resolve().parents[1]
_CTX_PATH = _PKG_ROOT / "forgeworks" / "runner" / "scaffolding" / "forgescaffold_coding_context.py"


def _load_coding_context():
    """Load module without importing ``forgeworks.runner`` (avoids optional forgegate deps)."""
    spec = importlib.util.spec_from_file_location("forgescaffold_coding_context_under_test", _CTX_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ctx = _load_coding_context()
FS_LINKS = _ctx.FS_LINKS
_import_fs_module = _ctx._import_fs_module
_link_run_py = _ctx._link_run_py


def test_link_run_py_forgescaffold_prefix_maps_to_short_dir():
    p = _link_run_py("forgescaffold.system_catalog")
    assert p.is_file()
    assert p.parent.name == "system_catalog"
    assert p.name == "run.py"
    assert p.parent.parent == FS_LINKS


def test_link_run_py_plain_link_name():
    p = _link_run_py("map_dataflow")
    assert p.is_file()
    assert p.parent.name == "map_dataflow"


def test_link_run_py_prefers_dotted_directory_when_stripped_also_exists():
    """Full id must win so we load the canonical pipeline link, not a legacy alias."""
    p = _link_run_py("forgescaffold.apply_patchset")
    assert p.is_file()
    assert "forgescaffold.apply_patchset" in p.as_posix()


def test_link_run_py_missing_raises():
    with pytest.raises(ImportError, match="ForgeScaffold link not found"):
        _link_run_py("forgescaffold.__no_such_link__")


def test_import_fs_module_loads_run_py():
    mod = _import_fs_module("forgescaffold.system_catalog")
    assert hasattr(mod, "assemble_units")
