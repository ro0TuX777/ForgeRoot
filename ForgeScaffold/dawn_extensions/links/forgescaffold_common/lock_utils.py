import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml


def load_policy(project_root: Path) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    policy_path = repo_root / "dawn" / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        policy_path = project_root / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        return {}
    return yaml.safe_load(policy_path.read_text()) or {}


def lock_path_for_project(project_root: Path) -> Path:
    return project_root / ".locks" / "forgescaffold_apply.lock"


def _parse_datetime(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_stale(lock_payload: Dict[str, Any], ttl_minutes: int) -> bool:
    started_at = _parse_datetime(str(lock_payload.get("started_at", "")))
    if not started_at:
        return True
    age_minutes = (_now() - started_at).total_seconds() / 60.0
    return age_minutes > ttl_minutes


def acquire_lock(
    project_root: Path,
    pipeline_name: str,
    patchset_id: Optional[str],
    ttl_minutes: int,
    force: bool = False,
) -> Tuple[bool, Dict[str, Any]]:
    lock_path = lock_path_for_project(project_root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if lock_path.exists():
        try:
            existing = json.loads(lock_path.read_text())
        except Exception:
            existing = {}
        if not _is_stale(existing, ttl_minutes):
            return False, {"reason": "LOCK_HELD", "existing": existing, "lock_path": str(lock_path)}
        if not force:
            return False, {"reason": "LOCK_STALE", "existing": existing, "lock_path": str(lock_path)}

    payload = {
        "pid": os.getpid(),
        "hostname": os.uname().nodename if hasattr(os, "uname") else None,
        "started_at": _now().isoformat().replace("+00:00", "Z"),
        "pipeline_name": pipeline_name,
        "patchset_id": patchset_id,
    }
    tmp_path = lock_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload))
    tmp_path.replace(lock_path)

    return True, {
        "reason": "LOCK_ACQUIRED",
        "lock_path": str(lock_path),
        "lock_forced": force,
        "payload": payload,
    }


def release_lock(project_root: Path) -> Dict[str, Any]:
    lock_path = lock_path_for_project(project_root)
    if not lock_path.exists():
        return {"released": False, "reason": "LOCK_MISSING", "lock_path": str(lock_path)}
    try:
        payload = json.loads(lock_path.read_text())
    except Exception:
        payload = None
    lock_path.unlink(missing_ok=True)
    return {"released": True, "lock_path": str(lock_path), "payload": payload}
