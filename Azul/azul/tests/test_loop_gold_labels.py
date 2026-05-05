import json
from pathlib import Path

from azul.loop.gold_labels import GoldLabelStore


def test_record_label_and_agreement_rate(tmp_path, monkeypatch):
    monkeypatch.setenv("AZUL_DATA_DIR", str(tmp_path))
    store = GoldLabelStore()

    store.record_label(
        artifact_type="action_contract_stub",
        original={"a": 1},
        approved={"a": 2},
        reviewer_id="vin",
    )
    store.record_label(
        artifact_type="action_contract_stub",
        original={"a": 1},
        approved={"a": 1},
        reviewer_id="vin",
    )

    labels = store.get_labels("action_contract_stub")
    assert len(labels) == 2
    assert labels[0].artifact_type == "action_contract_stub"
    assert store.compute_agreement_rate("action_contract_stub", window=2) == 0.5


def test_record_contract_approval_uses_baseline(tmp_path, monkeypatch):
    monkeypatch.setenv("AZUL_DATA_DIR", str(tmp_path))
    baseline = tmp_path / "baseline.yaml"
    approved = tmp_path / "approved.yaml"
    baseline.write_text(
        "unit_id: external.subprocess\nactions:\n  - id: check_call\n    guard_predicates: ['x']\n",
        encoding="utf-8",
    )
    approved.write_text(
        "unit_id: external.subprocess\nactions:\n  - id: check_call\n    guard_predicates: ['x','y']\n",
        encoding="utf-8",
    )

    store = GoldLabelStore()
    label = store.record_contract_approval(
        baseline_contract_path=baseline,
        approved_contract_path=approved,
        reviewer_id="lead",
    )

    assert label.artifact_type == "action_contract_stub"
    assert label.agreement is False

    rows = store.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    payload = json.loads(rows[0])
    assert payload["metadata"]["source"] == "contract_stub_approval"
