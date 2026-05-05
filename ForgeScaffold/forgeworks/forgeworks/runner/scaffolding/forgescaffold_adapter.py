"""
ForgeScaffold Adapter for SAM
==============================

Bridges SAM's EvolutionaryController output (Coder LLM code proposals) into
ForgeScaffold-compatible patchset artifacts for the gated apply pipeline.

Pipeline flow:
  SAM Coder LLM output
      → create_patchset()       → instrumentation.patchset.json
      → run_apply_pipeline()    → apply_report.json + rollback_patchset.json
      → stamp_ticket_event()    → ticket_events.jsonl (hash-chained)
      → package_evidence()      → signed evidence pack per ticket
"""

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ─── Paths ────────────────────────────────────────────────────────────────────
FORGEWORKS_ROOT = Path(__file__).resolve().parents[3]  # forgeworks repo root
FORGESCAFFOLD_ROOT = Path(__file__).parents[4]  # resolves to ForgeScaffold root
FS_CLI = FORGESCAFFOLD_ROOT / "scripts" / "forgescaffold_cli.py"
FS_PROJECT = FORGESCAFFOLD_ROOT / "projects" / "forgeworks_pipeline"
FS_PROJECT_ID = "forgeworks_pipeline"


def _ensure_project_dir() -> Path:
    """Ensure the ForgeScaffold DAWN project directory exists."""
    workspace = FS_PROJECT / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    
    # Write a minimal dawn.project.bundle.json if missing
    bundle = FS_PROJECT / "dawn.project.bundle.json"
    if not bundle.exists():
        payload = {
            "schema_version": "1.0.0",
            "project_id": FS_PROJECT_ID,
            "project_root": str(FORGEWORKS_ROOT),
            "description": "ForgeWorks Pipeline — ForgeScaffold evidence tracking",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        bundle.write_text(json.dumps(payload, indent=2))
        logger.info(f"🏗️ Created ForgeScaffold project bundle: {bundle}")
    
    return workspace


def create_patchset(
    target_file: str,
    original_content: str,
    optimized_content: str,
    ticket_id: str,
    hypothesis: str,
) -> Optional[Path]:
    """
    Convert a SAM Coder LLM output into a ForgeScaffold patchset artifact.
    
    Returns path to the written patchset JSON, or None on failure.
    """
    try:
        workspace = _ensure_project_dir()
        
        # Build a unified diff
        import difflib
        original_lines = original_content.splitlines(keepends=True)
        optimized_lines = optimized_content.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            original_lines,
            optimized_lines,
            fromfile=f"a/{target_file}",
            tofile=f"b/{target_file}",
        ))
        unified_diff = "".join(diff_lines)
        
        # ForgeScaffold patchset schema
        patchset = {
            "schema_version": "1.0.0",
            "patchset_id": f"sam_{ticket_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}",
            "ticket_id": ticket_id,
            "hypothesis": hypothesis,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "patches": [
                {
                    "patch_id": f"patch_001_{ticket_id}",
                    "target_file": target_file,
                    "operation": "replace",
                    "original_content": original_content,
                    "proposed_content": optimized_content,
                    "unified_diff": unified_diff,
                    "risk_level": "medium",
                    "reversible": True,
                }
            ],
        }
        
        patchset_path = workspace / "instrumentation.patchset.json"
        patchset_path.write_text(json.dumps(patchset, indent=2))
        logger.info(f"✅ ForgeScaffold patchset created: {patchset_path}")
        return patchset_path
        
    except Exception as e:
        logger.error(f"❌ Failed to create ForgeScaffold patchset: {e}")
        return None


def run_apply_pipeline(ticket_id: str, approved_by: str = "SAM_AUTO") -> Dict[str, Any]:
    """
    Run the ForgeScaffold gated apply pipeline via the CLI.
    
    Returns the apply report dict, or an error dict on failure.
    """
    if not FS_CLI.exists():
        logger.warning(f"ForgeScaffold CLI not found at {FS_CLI}. Skipping.")
        return {"status": "SKIPPED", "reason": "ForgeScaffold CLI not installed."}
    
    try:
        workspace = _ensure_project_dir()
        
        cmd = [
            sys.executable, str(FS_CLI),
            "approve",
            "--project", FS_PROJECT_ID,
            "--actor", approved_by,
            "--json",
        ]
        
        result = subprocess.run(
            cmd,
            cwd=str(FORGESCAFFOLD_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        if result.returncode != 0:
            logger.error(f"ForgeScaffold apply failed: {result.stderr}")
            return {"status": "FAILED", "reason": result.stderr}
        
        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError:
            output = {"raw": result.stdout}
        
        logger.info(f"✅ ForgeScaffold apply pipeline completed for ticket {ticket_id}")
        return {"status": "SUCCEEDED", "output": output}
        
    except subprocess.TimeoutExpired:
        return {"status": "FAILED", "reason": "ForgeScaffold apply pipeline timed out."}
    except Exception as e:
        logger.error(f"❌ ForgeScaffold apply pipeline error: {e}")
        return {"status": "FAILED", "reason": str(e)}


def stamp_ticket_event(
    ticket_id: str,
    event_type: str,
    actor: str = "SAM",
    payload: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Append an event to the ForgeScaffold ticket_events.jsonl ledger for a SAM ticket.
    This provides a hash-chained, immutable audit trail per ticket.
    """
    try:
        _ensure_project_dir()
        tickets_dir = FS_PROJECT / "tickets"
        tickets_dir.mkdir(parents=True, exist_ok=True)
        events_path = tickets_dir / "ticket_events.jsonl"
        
        # Load previous event hash for chaining
        prev_hash = None
        if events_path.exists():
            lines = [l.strip() for l in events_path.read_text().splitlines() if l.strip()]
            if lines:
                try:
                    last = json.loads(lines[-1])
                    prev_hash = last.get("event_hash")
                except Exception:
                    pass
        
        import hashlib
        ts = datetime.now(timezone.utc).isoformat()
        event_id = f"{ticket_id}_{event_type}_{ts}"
        raw = json.dumps({"event_id": event_id, "ticket_id": ticket_id,
                          "event_type": event_type, "actor": actor,
                          "payload": payload or {}, "timestamp": ts,
                          "prev_event_hash": prev_hash}, sort_keys=True)
        event_hash = hashlib.sha256(raw.encode()).hexdigest()
        
        event = {
            "event_id": event_id,
            "ticket_id": ticket_id,
            "event_type": event_type,
            "actor": actor,
            "payload": payload or {},
            "timestamp": ts,
            "prev_event_hash": prev_hash,
            "event_hash": event_hash,
        }
        
        with open(events_path, "a") as f:
            f.write(json.dumps(event) + "\n")
        
        logger.info(f"⛓️ Ticket event stamped: {event_type} for {ticket_id} (hash: {event_hash[:12]}...)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to stamp ticket event: {e}")
        return False


def get_ticket_evidence(ticket_id: str) -> Dict[str, Any]:
    """
    Read all ForgeScaffold evidence for a given SAM ticket ID.
    Used by the UI to populate the Evidence tab.
    """
    evidence = {
        "ticket_id": ticket_id,
        "events": [],
        "patchset": None,
        "apply_report": None,
        "rollback_available": False,
    }
    
    try:
        # Read ticket events
        events_path = FS_PROJECT / "tickets" / "ticket_events.jsonl"
        if events_path.exists():
            for line in events_path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    if event.get("ticket_id") == ticket_id:
                        evidence["events"].append(event)
                except Exception:
                    continue
        
        # Read patchset if it references this ticket
        workspace = FS_PROJECT / "workspace"
        patchset_path = workspace / "instrumentation.patchset.json"
        if patchset_path.exists():
            patchset = json.loads(patchset_path.read_text())
            if patchset.get("ticket_id") == ticket_id:
                evidence["patchset"] = patchset
        
        # Read apply report
        apply_report_path = workspace / "apply_report.json"
        if apply_report_path.exists():
            evidence["apply_report"] = json.loads(apply_report_path.read_text())
        
        # Check rollback
        rollback_path = workspace / "rollback_patchset.json"
        evidence["rollback_available"] = rollback_path.exists()
        
    except Exception as e:
        logger.error(f"Failed to retrieve ForgeScaffold evidence for {ticket_id}: {e}")
    
    return evidence
