from pathlib import Path
import hashlib

import pytest

from forgeworks.runner.sam_like_runner import run_workcell


def _workcell_path() -> Path:
    return Path(__file__).resolve().parents[1] / "packs" / "ci_change_control" / "0.1.0"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_supervised_run_creates_approvals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("forgegate")
    monkeypatch.setenv("FORGEWORKS_PHASE_STUBS", "1")
    out = tmp_path / "supervised"
    summary = run_workcell(str(_workcell_path()), str(out), mode="supervised")
    assert summary["approval_count"] == summary["decision_count"]
    assert (out / "approval_records.jsonl").exists()


def test_supervised_run_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("forgegate")
    monkeypatch.setenv("FORGEWORKS_PHASE_STUBS", "1")
    out1 = tmp_path / "s1"
    out2 = tmp_path / "s2"
    run_workcell(str(_workcell_path()), str(out1), mode="supervised")
    run_workcell(str(_workcell_path()), str(out2), mode="supervised")
    h1 = _hash_file(out1 / "approval_records.jsonl")
    h2 = _hash_file(out2 / "approval_records.jsonl")
    assert h1 == h2
