from pathlib import Path
import shutil

import pytest

from forgeworks.core.validate import WorkcellValidationError, validate_workcell


def _fixture_path() -> Path:
    return Path(__file__).resolve().parents[1] / "packs" / "hello_workcell" / "0.1.0"


def test_valid_workcell_passes():
    result = validate_workcell(str(_fixture_path()))
    assert result["status"] == "OK"
    assert result["workcell_hash"]


def test_missing_required_file_fails(tmp_path: Path):
    workcell = tmp_path / "wc"
    shutil.copytree(_fixture_path(), workcell)
    (workcell / "run_config.json").unlink()
    with pytest.raises(WorkcellValidationError) as exc:
        validate_workcell(str(workcell))
    assert "run_config.json" in str(exc.value.errors[0]["error"]) or "missing file" in str(exc.value.errors[0]["error"]).lower()


def test_broken_schema_fails(tmp_path: Path):
    workcell = tmp_path / "wc"
    shutil.copytree(_fixture_path(), workcell)
    (workcell / "run_config.json").write_text('{"schema_version":"0.1","domain":"hello","seed":123,"intent_bundle_path":"./intent_bundle"}')
    with pytest.raises(WorkcellValidationError) as exc:
        validate_workcell(str(workcell))
    assert "run_config.json" in exc.value.errors[0]["file"]
    assert "mode" in exc.value.errors[0]["error"]
