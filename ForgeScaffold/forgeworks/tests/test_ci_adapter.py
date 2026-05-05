from pathlib import Path
import shutil

from forgeworks.adapters.registry import register_builtin_adapters
from forgeworks.adapters.base import get_adapter
from forgeworks.core.validate import validate_workcell


def _sample_raw() -> Path:
    return Path(__file__).resolve().parents[1] / "ingest" / "ci_change_control" / "sample_raw"


def test_ci_adapter_normalize(tmp_path: Path):
    register_builtin_adapters()
    adapter = get_adapter("ci_change_control")

    raw_out = tmp_path / "raw"
    adapter.ingest(str(_sample_raw()), str(raw_out))

    out = tmp_path / "workcell"
    result = adapter.normalize(str(raw_out), str(out))
    assert result["tickets"] > 0
    assert result["signals"] > 0

    validated = validate_workcell(str(out))
    assert validated["status"] == "OK"

    signals = (out / "signals.jsonl").read_text()
    assert "queue.pressure" in signals
    assert "change.touches_ci_config" in signals
