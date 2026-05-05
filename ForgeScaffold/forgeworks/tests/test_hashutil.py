from pathlib import Path
import shutil

from forgeworks.core.hashutil import compute_workcell_hash


def _fixture_path() -> Path:
    return Path(__file__).resolve().parents[1] / "packs" / "hello_workcell" / "0.1.0"


def test_hash_deterministic(tmp_path: Path):
    workcell = tmp_path / "wc"
    shutil.copytree(_fixture_path(), workcell)
    h1 = compute_workcell_hash(str(workcell))
    h2 = compute_workcell_hash(str(workcell))
    assert h1 == h2


def test_hash_changes_on_edit(tmp_path: Path):
    workcell = tmp_path / "wc"
    shutil.copytree(_fixture_path(), workcell)
    h1 = compute_workcell_hash(str(workcell))
    ticket_path = workcell / "tickets.jsonl"
    ticket_path.write_text(ticket_path.read_text().replace("HELLO-001", "HELLO-002"))
    h2 = compute_workcell_hash(str(workcell))
    assert h1 != h2
