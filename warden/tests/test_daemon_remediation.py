from __future__ import annotations

import json
import tempfile
from pathlib import Path

from warden.daemon import (
    FederationWarden,
    WardenConfig,
    list_remediation_queue,
    review_remediation_item,
)
from warden.llm_gateway import GatewayConfig, LLMGateway


def _build_daemon(tmp_root: Path, project_root: Path) -> FederationWarden:
    cfg = WardenConfig(
        forge_root=tmp_root,
        project_root=project_root,
        project_id="helios_watch",
    )
    gw = LLMGateway(
        GatewayConfig(
            forge_root=tmp_root,
            trace_dir=(tmp_root / "traces"),
        )
    )
    return FederationWarden(config=cfg, gateway=gw)


def test_changed_file_patch_generation_uses_snapshot_baseline():
    root = Path(tempfile.mkdtemp())
    project_root = root / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    file_path = project_root / "app.py"
    file_path.write_text("print('old')\n", encoding="utf-8")

    daemon = _build_daemon(root, project_root)

    first = daemon._build_patch_from_changed_files([])
    assert first["ok"] is True
    assert first["diff_text"] == ""

    file_path.write_text("print('new')\n", encoding="utf-8")
    second = daemon._build_patch_from_changed_files(["app.py"])
    assert second["ok"] is True
    assert "--- a/app.py" in second["diff_text"]
    assert "+++ b/app.py" in second["diff_text"]
    assert second["changed_files"] == ["app.py"]


def test_enqueue_remediation_creates_human_review_record_without_apply():
    root = Path(tempfile.mkdtemp())
    project_root = root / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    target = project_root / "app.py"
    target.write_text("print('stable')\n", encoding="utf-8")

    daemon = _build_daemon(root, project_root)
    item = daemon._enqueue_remediation_for_human_review(
        cycle_id="c123",
        source_reason="file_change",
        initial_verify={"ticket": {"ticket_id": "azul-a1", "verdict_reason": "guard violation"}},
        remediation={
            "final_patch": "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-print('stable')\n+print('fixed')\n",
            "final_verify": {"ticket": {"ticket_id": "azul-b2", "status": "COMPLETED", "verdict": "pass"}},
            "attempts": [{}, {}],
        },
        domain="system_operations",
        changed_files=["app.py"],
    )

    assert item["status"] == "ready_for_human_review"
    record_path = Path(item["record_path"])
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["requires_human_final_review"] is True
    assert record["auto_apply_performed"] is False
    assert record["final_ticket_id"] == "azul-b2"
    assert Path(record["patch_path"]).exists()
    assert target.read_text(encoding="utf-8") == "print('stable')\n"


def test_remediation_status_and_review_flow():
    root = Path(tempfile.mkdtemp())
    project_root = root / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    daemon = _build_daemon(root, project_root)

    item = daemon._enqueue_remediation_for_human_review(
        cycle_id="c999",
        source_reason="file_change",
        initial_verify={"ticket": {"ticket_id": "azul-a9", "verdict_reason": "guard violation"}},
        remediation={
            "final_patch": "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-print('x')\n+print('y')\n",
            "final_verify": {"ticket": {"ticket_id": "azul-b9", "status": "COMPLETED", "verdict": "pass"}},
            "attempts": [{}],
        },
        domain="system_operations",
        changed_files=["a.py"],
    )
    item_id = item["id"]

    status_before = list_remediation_queue(forge_root=root)
    assert status_before["status"] == "ok"
    assert status_before["pending_count"] == 1
    assert status_before["pending"][0]["id"] == item_id

    reviewed = review_remediation_item(forge_root=root, item_id=item_id)
    assert reviewed["status"] == "ok"

    status_after = list_remediation_queue(forge_root=root, include_reviewed=True)
    assert status_after["pending_count"] == 0
    assert status_after["reviewed_count"] == 1
    assert status_after["reviewed"][0]["id"] == item_id


def test_startup_requeue_for_stuck_azul_tickets(monkeypatch):
    root = Path(tempfile.mkdtemp())
    project_root = root / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    daemon = _build_daemon(root, project_root)

    active_dir = root / "azul_data" / "tickets" / "active"
    active_dir.mkdir(parents=True, exist_ok=True)
    stuck = {
        "ticket_id": "azul-stuck-1",
        "status": "EVALUATING",
        "domain": "system_operations",
        "change_summary": "stuck test",
        "change_payload": {"diff": "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-print('x')\n+print('y')\n"},
        "metadata": {},
    }
    (active_dir / "azul-stuck-1.json").write_text(json.dumps(stuck, indent=2), encoding="utf-8")

    monkeypatch.setattr(
        daemon,
        "_run_azul_verify",
        lambda **kwargs: {"ticket": {"ticket_id": "azul-requeued-1"}, "returncode": 0},
    )

    result = daemon._requeue_stuck_tickets_on_startup()
    assert result["requeued_count"] == 1
    assert not (active_dir / "azul-stuck-1.json").exists()

    completed_path = root / "azul_data" / "tickets" / "completed" / "azul-stuck-1.json"
    assert completed_path.exists()
    completed = json.loads(completed_path.read_text(encoding="utf-8"))
    assert completed["status"] == "FAILED"
    assert completed["metadata"]["manual_review_required"] is True
    assert completed["metadata"]["requeued_ticket_id"] == "azul-requeued-1"
