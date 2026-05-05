from pathlib import Path

from azul.loop.drift_scanner import DriftScanner


def test_snapshot_on_first_scan_then_detect_drift(tmp_path, monkeypatch):
    data_dir = tmp_path / "azul_data"
    catalogs = tmp_path / "action_catalogs" / "active"
    policies = tmp_path / "gate_policies"
    catalogs.mkdir(parents=True)
    policies.mkdir(parents=True)

    contract = catalogs / "external_subprocess.yaml"
    policy = policies / "default.yaml"

    contract.write_text(
        "unit_id: external.subprocess\nactions:\n  - id: check_call\n    guard_predicates: ['safe']\n    risk_tier: 2\n",
        encoding="utf-8",
    )
    policy.write_text(
        "min_score: 70\nwarn_score: 80\nmax_deny_count: 2\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("AZUL_DATA_DIR", str(data_dir))
    monkeypatch.setenv("FORGE_ATLAS_CATALOG_PATH", str(tmp_path / "action_catalogs"))
    monkeypatch.setenv("AZUL_GATE_POLICIES_DIR", str(policies))

    scanner = DriftScanner()
    first = scanner.scan_drift()
    assert first.baseline_new_count >= 2
    assert first.contracts_drifted == 0
    assert first.policies_drifted == 0

    contract.write_text(
        "unit_id: external.subprocess\nactions:\n  - id: check_call\n    guard_predicates: ['safe','no_shell']\n    risk_tier: 3\n",
        encoding="utf-8",
    )

    second = scanner.scan_drift()
    assert second.contracts_compared >= 1
    assert second.contracts_drifted >= 1
    assert any(item.artifact_type == "contract" and item.status == "drifted" for item in second.items)
