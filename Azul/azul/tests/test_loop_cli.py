import json


def test_loop_status_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AZUL_DATA_DIR", str(tmp_path))
    import azul.adapters.cli as cli_mod

    code = cli_mod.run(["loop", "status"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "enabled" in payload
    assert "agreement_rates" in payload


def test_loop_report_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AZUL_DATA_DIR", str(tmp_path))
    import azul.adapters.cli as cli_mod

    code = cli_mod.run(["loop", "report"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "empty"


def test_loop_drift_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AZUL_DATA_DIR", str(tmp_path))
    import azul.adapters.cli as cli_mod

    code = cli_mod.run(["loop", "drift"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "empty"
