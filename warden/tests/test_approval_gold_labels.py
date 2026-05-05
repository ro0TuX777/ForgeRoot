import json
from pathlib import Path

from warden.daemon import approve_stub_file


def test_approve_stub_records_gold_label_and_baseline(tmp_path, monkeypatch):
    forge_root = tmp_path / "forge"
    stubs = forge_root / "action_catalogs" / "stubs"
    stubs.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("AZUL_DATA_DIR", str(tmp_path / "azul_data"))

    stub_name = "external_subprocess.yaml"
    stub_path = stubs / stub_name
    stub_path.write_text(
        "unit_id: external.subprocess\nactions:\n  - id: check_call\n    guard_predicates: ['safe']\n",
        encoding="utf-8",
    )

    result = approve_stub_file(forge_root=forge_root, filename=stub_name)
    assert result["status"] == "ok"

    active_path = forge_root / "action_catalogs" / "active" / stub_name
    assert active_path.exists()

    baseline = tmp_path / "azul_data" / "baselines" / "contracts" / "stubs" / stub_name
    assert baseline.exists()

    labels = tmp_path / "azul_data" / "gold_labels" / "gold_labels.jsonl"
    assert labels.exists()
    row = json.loads(labels.read_text(encoding="utf-8").splitlines()[0])
    assert row["artifact_type"] == "action_contract_stub"
