from pathlib import Path

from forgeworks.adapters.registry import register_builtin_adapters
from forgeworks.adapters.base import get_adapter
from forgeworks.core.validate import validate_workcell


def _sample_raw() -> Path:
    return Path(__file__).resolve().parents[1] / "ingest" / "it_ops_runbook" / "sample_raw"


def test_it_ops_adapter_normalize(tmp_path: Path):
    register_builtin_adapters()
    adapter = get_adapter("it_ops_runbook")

    raw_out = tmp_path / "raw"
    adapter.ingest(str(_sample_raw()), str(raw_out))

    out = tmp_path / "workcell"
    result = adapter.normalize(str(raw_out), str(out))
    assert result["tickets"] > 0
    assert result["signals"] > 0

    validated = validate_workcell(str(out))
    assert validated["status"] == "OK"

    signals = (out / "signals.jsonl").read_text()
    assert "runbook.present" in signals
    assert "blast_radius" in signals
