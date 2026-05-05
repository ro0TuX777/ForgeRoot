from pathlib import Path
import hashlib

import pytest

from forgeworks.runner.sam_like_runner import run_workcell, run_shadow


def _workcell_path() -> Path:
    return Path(__file__).resolve().parents[1] / "packs" / "ci_change_control" / "0.1.0"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_shadow_run_creates_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("forgegate")
    monkeypatch.setenv("FORGEWORKS_PHASE_STUBS", "1")
    out = tmp_path / "results"
    summary = run_shadow(str(_workcell_path()), str(out))
    assert summary["ticket_count"] > 0
    ledger = out / "decision_ledger.jsonl"
    assert ledger.exists()
    ticket_dir = out / "tickets"
    assert any(ticket_dir.iterdir())


def test_shadow_run_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("forgegate")
    monkeypatch.setenv("FORGEWORKS_PHASE_STUBS", "1")
    out1 = tmp_path / "r1"
    out2 = tmp_path / "r2"
    run_workcell(str(_workcell_path()), str(out1), mode="shadow")
    run_workcell(str(_workcell_path()), str(out2), mode="shadow")
    h1 = _hash_file(out1 / "decision_ledger.jsonl")
    h2 = _hash_file(out2 / "decision_ledger.jsonl")
    assert h1 == h2
