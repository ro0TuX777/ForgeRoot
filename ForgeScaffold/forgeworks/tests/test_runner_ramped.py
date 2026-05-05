from pathlib import Path
import hashlib

import pytest

from forgeworks.runner.sam_like_runner import run_workcell


def _workcell_path() -> Path:
    return Path(__file__).resolve().parents[1] / "packs" / "it_ops_runbook" / "0.1.0"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_ramped_run_creates_approvals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("forgegate")
    monkeypatch.setenv("FORGEWORKS_PHASE_STUBS", "1")
    out = tmp_path / "ramped"
    summary = run_workcell(str(_workcell_path()), str(out), mode="ramped")
    assert summary["approval_count"] > 0
    assert (out / "approval_records.jsonl").exists()


def test_ramped_run_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("forgegate")
    monkeypatch.setenv("FORGEWORKS_PHASE_STUBS", "1")
    out1 = tmp_path / "r1"
    out2 = tmp_path / "r2"
    run_workcell(str(_workcell_path()), str(out1), mode="ramped")
    run_workcell(str(_workcell_path()), str(out2), mode="ramped")
    h1 = _hash_file(out1 / "approval_records.jsonl")
    h2 = _hash_file(out2 / "approval_records.jsonl")
    assert h1 == h2
