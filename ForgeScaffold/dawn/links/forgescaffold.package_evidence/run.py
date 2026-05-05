import json
import shutil
from pathlib import Path
from typing import Any, Dict


def _load_artifact(artifact_store, artifact_id: str) -> Dict[str, Any]:
    meta = artifact_store.get(artifact_id)
    if not meta:
        raise RuntimeError(f"Missing required artifact: {artifact_id}")
    with open(meta["path"], "r") as fh:
        return json.load(fh)


def _copy_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    artifact_store = project_context.get("artifact_store")
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not artifact_store or not sandbox:
        raise RuntimeError("Sandbox or artifact store missing")

    evidence_root = Path("evidence_pack")
    evidence_abs = Path(sandbox.sandbox_root)

    artifact_ids = [
        "forgescaffold.instrumentation.patchset.json",
        "forgescaffold.apply_report.json",
        "forgescaffold.rollback_patchset.json",
        "forgescaffold.workspace_snapshot.json",
        "forgescaffold.verification_report.json",
        "forgescaffold.test_results.manifest.json",
        "forgescaffold.approval_receipt.json",
        "forgescaffold.ticket_event_receipt.json",
        "forgescaffold.rollback_report.json",
    ]

    manifest_entries = []
    for artifact_id in artifact_ids:
        meta = artifact_store.get(artifact_id)
        if not meta:
            continue
        src = Path(meta["path"])
        dest = evidence_root / src.name
        _copy_file(src, evidence_abs / dest)
        manifest_entries.append({"artifact_id": artifact_id, "path": str(dest)})

    ledger_path = project_root / "ledger" / "events.jsonl"
    if ledger_path.exists():
        dest = evidence_root / "ledger_events.jsonl"
        _copy_file(ledger_path, evidence_abs / dest)
        manifest_entries.append({"artifact_id": "ledger.events", "path": str(dest)})

    manifest = {
        "root": "evidence_pack",
        "entries": manifest_entries,
    }

    manifest_path = sandbox.publish(
        "forgescaffold.evidence_pack.manifest.json",
        "evidence_pack/manifest.json",
        manifest,
        schema="json",
    )
    alias_path = sandbox.publish(
        "forgescaffold.evidence_manifest.json",
        "evidence_pack/manifest.json",
        manifest,
        schema="json",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {
            "forgescaffold.evidence_pack.manifest.json": {"path": manifest_path},
            "forgescaffold.evidence_manifest.json": {"path": alias_path},
        },
        "metrics": {"entries": len(manifest_entries)},
    }
