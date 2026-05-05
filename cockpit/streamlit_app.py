"""Streamlit cockpit for federation status, approvals, and verdict visibility."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib import error, request

import streamlit as st
import yaml

from warden.daemon import (
    approve_stub_file,
    default_project_id,
    load_runtime_status,
    start_daemon_process,
    stop_daemon_process,
)
from warden.llm_gateway import GatewayError, LLMGateway
from warden.remediation_agent import DraftArtifact, RemediationAgent


OLLAMA_SCAN_DEFAULT = "llama4:17b-scout-16e-instruct-q4_K_M"
OLLAMA_REASONING_DEFAULT = "hf.co/unsloth/DeepSeek-R1-Distill-Qwen-32B-GGUF:Q4_K_M"
OLLAMA_VERDICT_DEFAULT = "hf.co/unsloth/Qwen3-Coder-Next-GGUF:UD-Q4_K_M"
OLLAMA_EMBEDDING_DEFAULT = "nomic-embed-text:latest"
OLLAMA_OCR_DEFAULT = "glm-ocr:latest"
DEFAULT_VERIFY_SUMMARY = "Manual verification request from cockpit"
SNAPSHOT_MAX_FILE_BYTES = 512 * 1024
SNAPSHOT_INCLUDE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".java",
    ".rb",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".sh",
    ".md",
    ".txt",
}
SNAPSHOT_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
}


def _forge_root() -> Path:
    return Path(os.environ.get("FORGE_ROOT", Path(__file__).resolve().parents[1])).resolve()


def _azul_data_dir(root: Path) -> Path:
    return Path(os.environ.get("AZUL_DATA_DIR", str(root / "azul_data"))).resolve()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dot(status: str) -> str:
    color = {
        "running": "#2bb673",
        "configured": "#2bb673",
        "stopped": "#f2b63d",
        "error": "#e4514f",
    }.get(status, "#a3a7ad")
    return f"<span style='display:inline-block;width:10px;height:10px;border-radius:50%;background:{color};margin-right:8px;'></span>"


def _apply_style() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap');
        html, body, [class*="css"] { font-family: "Space Grotesk", sans-serif; }
        .stApp { background: radial-gradient(circle at 10% 10%, #f2f4ef 0%, #e6ece0 48%, #dde7d5 100%); }
        .cockpit-card {
          background: #f8fbf6;
          border: 1px solid #c7d8bc;
          border-radius: 12px;
          padding: 0.75rem 1rem;
          margin-bottom: 0.65rem;
        }
        .ribbon {
          display:flex; gap:8px; flex-wrap:wrap; margin: 0.2rem 0 1rem 0;
        }
        .ribbon-pill {
          padding: 0.35rem 0.6rem;
          border-radius: 999px;
          background: #dde7d5;
          color: #2f4934;
          border: 1px solid #b7c9a9;
          font-size: 0.85rem;
        }
        .ribbon-pill.active {
          background: #2f6f47;
          border-color: #2f6f47;
          color: #f6fff5;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _framework_states(root: Path, gateway_health: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    return {
        "DAWN": {
            "status": "running" if (root / "DAWN").exists() else "error",
            "detail": "Runtime and pipelines available",
        },
        "CONCORD": {
            "status": "running" if (root / "CONCORD").exists() else "error",
            "detail": "Governance kernels available",
        },
        "ForgeAtlas": {
            "status": "running" if (root / "ForgeAtlas").exists() else "error",
            "detail": "Catalog discovery service available",
        },
        "ForgeScaffold": {
            "status": "running" if (root / "scripts" / "forge-scan").exists() else "error",
            "detail": "Scanner wrapper callable",
        },
        "ForgeGate": {
            "status": "running" if (root / "ForgeGate").exists() else "error",
            "detail": "Decision controls available",
        },
        "ForgeHarbor": {
            "status": "running" if (root / "ForgeHarbor" / "daemon.py").exists() else "error",
            "detail": "Environment daemon available",
        },
        "Azul": {
            "status": "running" if (root / "Azul" / "azul").exists() else "error",
            "detail": "Verification layer available",
        },
        "Local/vLLM": gateway_health["vllm"],
        "Local/Ollama": gateway_health["ollama"],
        "Frontier": gateway_health["frontier"],
    }


def _load_system_catalog(root: Path, project_id: str, status: Dict[str, Any]) -> Dict[str, Any]:
    if status.get("last_system_catalog"):
        return _load_json(Path(status["last_system_catalog"]))
    path = (
        root
        / "DAWN"
        / "projects"
        / project_id
        / "artifacts"
        / "forgescaffold.system_catalog"
        / "system_catalog.json"
    )
    return _load_json(path)


def _system_catalog_path(root: Path, project_id: str, status: Dict[str, Any]) -> Path:
    if status.get("last_system_catalog"):
        return Path(status["last_system_catalog"])
    return (
        root
        / "DAWN"
        / "projects"
        / project_id
        / "artifacts"
        / "forgescaffold.system_catalog"
        / "system_catalog.json"
    )


def _load_danger_map(root: Path, project_id: str, status: Dict[str, Any]) -> Dict[str, Any]:
    if status.get("last_danger_map"):
        return _load_json(Path(status["last_danger_map"]))
    path = (
        root
        / "DAWN"
        / "projects"
        / project_id
        / "artifacts"
        / "concord.danger_map"
        / "danger_map.json"
    )
    return _load_json(path)


def _load_completed_tickets(root: Path) -> List[Dict[str, Any]]:
    tickets_dir = _azul_data_dir(root) / "tickets" / "completed"
    out: List[Dict[str, Any]] = []
    if not tickets_dir.exists():
        return out
    for path in sorted(tickets_dir.glob("azul-*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = _load_json(path)
        if data:
            out.append(data)
    return out


def _load_xp_ledger(root: Path) -> List[Dict[str, Any]]:
    ledger = _azul_data_dir(root) / "xp_ledger.jsonl"
    out: List[Dict[str, Any]] = []
    if not ledger.exists():
        return out
    for line in ledger.read_text(encoding="utf-8").splitlines()[-200:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    out.reverse()
    return out


def _load_remediation_queue(root: Path) -> List[Dict[str, Any]]:
    pending_dir = _azul_data_dir(root) / "remediation_desk" / "pending"
    out: List[Dict[str, Any]] = []
    if not pending_dir.exists():
        return out
    for path in sorted(pending_dir.glob("remediation-*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = _load_json(path)
        if not data:
            continue
        data["_record_path"] = str(path)
        out.append(data)
    return out


def _mark_remediation_reviewed(root: Path, item_id: str) -> Dict[str, Any]:
    pending_dir = _azul_data_dir(root) / "remediation_desk" / "pending"
    reviewed_dir = _azul_data_dir(root) / "remediation_desk" / "reviewed"
    src = pending_dir / f"{item_id}.json"
    if not src.exists():
        return {"ok": False, "message": f"Remediation item not found: {src}"}
    reviewed_dir.mkdir(parents=True, exist_ok=True)
    dst = reviewed_dir / src.name
    data = _load_json(src)
    if not data:
        return {"ok": False, "message": f"Invalid remediation item: {src}"}
    data["status"] = "reviewed"
    data["reviewed_at"] = _now_iso()
    dst.write_text(json.dumps(data, indent=2), encoding="utf-8")
    src.unlink(missing_ok=True)
    return {"ok": True, "path": str(dst)}


def _list_ollama_models(endpoint: str) -> List[str]:
    url = f"{endpoint.rstrip('/')}/api/tags"
    req = request.Request(url=url, method="GET")
    try:
        with request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, error.HTTPError, json.JSONDecodeError):
        return []

    names: List[str] = []
    for item in payload.get("models", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _extract_ticket_id(output: str) -> str:
    match = re.search(r"Ticket:\s*(azul-[a-z0-9]+)", output, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _load_ticket_by_id(root: Path, ticket_id: str) -> tuple[Dict[str, Any], str]:
    if not ticket_id:
        return {}, ""
    base = _azul_data_dir(root) / "tickets"
    for folder in ("completed", "active"):
        path = base / folder / f"{ticket_id}.json"
        if path.exists():
            return _load_json(path), str(path)
    return {}, ""


def _load_latest_ticket(root: Path) -> tuple[Dict[str, Any], str]:
    completed = _azul_data_dir(root) / "tickets" / "completed"
    if not completed.exists():
        return {}, ""
    files = sorted(completed.glob("azul-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return {}, ""
    return _load_json(files[0]), str(files[0])


def _run_reasoning_trace(
    gateway: LLMGateway,
    *,
    diff_text: str,
    summary: str,
    domain: str,
) -> Dict[str, Any]:
    prompt = (
        "You are the federation judgment model. Provide a concise verification rationale.\n"
        f"Domain: {domain}\n"
        f"Summary: {summary}\n"
        "Focus on security/governance risks, likely guard predicate impact, and confidence.\n"
        "Diff follows:\n"
        f"{diff_text[:12000]}"
    )
    try:
        result = gateway.complete(
            task_tier="TIER_REASONING",
            prompt=prompt,
            system_prompt="Return concise governance reasoning for operator display.",
            reasoning_steps=[
                "Mapped diff to governance context",
                "Checked for high-risk operation patterns",
                "Produced lead-facing rationale",
            ],
            metadata={"source": "cockpit_verify", "domain": domain},
        )
        return {
            "ok": True,
            "text": result.text,
            "trace": {
                "model_used": result.trace.model_used,
                "task_tier": result.trace.task_tier,
                "reasoning_steps": result.trace.reasoning_steps,
                "confidence_score": result.trace.confidence_score,
                "raw_response_path": result.trace.raw_response_path,
            },
        }
    except GatewayError as exc:
        trace_dir = Path(
            os.environ.get("FORGE_TRACE_DIR", str(_forge_root() / "forge_output" / "traces"))
        ).resolve()
        trace_dir.mkdir(parents=True, exist_ok=True)
        fallback_path = trace_dir / f"{int(datetime.now(timezone.utc).timestamp())}-{uuid.uuid4().hex[:8]}-fallback.txt"

        heuristic_steps = [
            "Primary reasoning providers unavailable",
            "Generated deterministic fallback reasoning from diff heuristics",
        ]
        if "subprocess" in diff_text:
            heuristic_steps.append("Detected subprocess pattern in diff")
        if "shell=True" in diff_text:
            heuristic_steps.append("Detected shell=True injection risk pattern")

        fallback_reasoning = (
            "Fallback reasoning: model providers were unavailable, so deterministic "
            "risk heuristics were applied for operator visibility."
        )
        fallback_path.write_text(
            json.dumps(
                {
                    "error": str(exc),
                    "summary": summary,
                    "domain": domain,
                    "heuristic_steps": heuristic_steps,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "ok": True,
            "error": str(exc),
            "text": fallback_reasoning,
            "trace": {
                "model_used": "gateway/fallback",
                "task_tier": "TIER_REASONING",
                "reasoning_steps": heuristic_steps,
                "confidence_score": 0.35,
                "raw_response_path": str(fallback_path),
            },
        }


def _run_azul_verify(
    root: Path,
    *,
    diff_text: str,
    summary: str,
    domain: str,
) -> Dict[str, Any]:
    verify_dir = root / "forge_output" / "verify_inputs"
    verify_dir.mkdir(parents=True, exist_ok=True)
    diff_path = verify_dir / f"verify-{uuid.uuid4().hex[:12]}.patch"
    diff_path.write_text(diff_text, encoding="utf-8")

    cmd = [
        str(root / "scripts" / "azul-verify"),
        "--domain",
        domain,
        "--diff",
        str(diff_path),
        "--summary",
        summary,
    ]
    env = os.environ.copy()
    env["FORGE_ROOT"] = str(root)
    proc = subprocess.run(
        cmd,
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    ticket_id = _extract_ticket_id(output)
    ticket, ticket_path = _load_ticket_by_id(root, ticket_id)
    if not ticket:
        ticket, ticket_path = _load_latest_ticket(root)
        if ticket and not ticket_id:
            ticket_id = str(ticket.get("ticket_id", ""))

    return {
        "returncode": proc.returncode,
        "ticket_id": ticket_id,
        "ticket": ticket,
        "ticket_path": ticket_path,
        "output": output.strip(),
        "command": " ".join(cmd),
        "diff_path": str(diff_path),
    }


def _run_git_command(project_root: Path, args: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        check=False,
    )


def _snapshot_workspace(forge_root: Path, project_root: Path) -> Dict[str, Path]:
    slug = re.sub(r"[^a-z0-9]+", "_", project_root.name.lower()).strip("_") or "project"
    digest = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:12]
    root = forge_root / "forge_output" / "snapshot_diff" / f"{slug}-{digest}"
    return {
        "root": root,
        "manifest": root / "manifest.json",
        "files": root / "files",
    }


def _is_text_candidate(path: Path) -> bool:
    if path.suffix.lower() in SNAPSHOT_INCLUDE_EXTENSIONS:
        return True
    return path.suffix == ""


def _read_text_file(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) > SNAPSHOT_MAX_FILE_BYTES:
        return None
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _collect_snapshot_texts(project_root: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in SNAPSHOT_EXCLUDE_DIRS]
        root_path = Path(root)
        for filename in files:
            full = root_path / filename
            if not _is_text_candidate(full):
                continue
            text = _read_text_file(full)
            if text is None:
                continue
            rel = full.relative_to(project_root).as_posix()
            out[rel] = text
    return out


def _snapshot_manifest_data(texts: Dict[str, str], project_root: Path) -> Dict[str, Any]:
    files: Dict[str, Dict[str, Any]] = {}
    for rel, text in texts.items():
        encoded = text.encode("utf-8")
        files[rel] = {
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "bytes": len(encoded),
        }
    now = _now_iso()
    return {
        "project_root": str(project_root),
        "created_at": now,
        "updated_at": now,
        "files": files,
    }


def _write_snapshot_baseline(forge_root: Path, project_root: Path) -> Dict[str, Any]:
    try:
        ws = _snapshot_workspace(forge_root, project_root)
        ws["root"].mkdir(parents=True, exist_ok=True)
        if ws["files"].exists():
            shutil.rmtree(ws["files"])
        ws["files"].mkdir(parents=True, exist_ok=True)

        texts = _collect_snapshot_texts(project_root)
        for rel, text in texts.items():
            dest = ws["files"] / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")

        manifest = _snapshot_manifest_data(texts, project_root)
        ws["manifest"].write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return {
            "ok": True,
            "mode": "snapshot",
            "summary": f"Snapshot baseline refreshed for {project_root.name} ({len(texts)} files).",
            "file_count": len(texts),
            "workspace": str(ws["root"]),
        }
    except Exception as exc:
        return {
            "ok": False,
            "mode": "snapshot",
            "error": f"Failed to refresh snapshot baseline: {exc}",
        }


def _build_patch_from_snapshot(forge_root: Path, project_root: Path) -> Dict[str, Any]:
    ws = _snapshot_workspace(forge_root, project_root)
    manifest_path = ws["manifest"]
    files_root = ws["files"]

    if not manifest_path.exists():
        init = _write_snapshot_baseline(forge_root, project_root)
        return {
            "ok": True,
            "mode": "snapshot",
            "diff_text": "",
            "changed_files": [],
            "summary": (
                "Snapshot baseline initialized. Make changes in PROJECT_ROOT, "
                "then run verify again."
            ),
            "status_preview": init["summary"],
        }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        init = _write_snapshot_baseline(forge_root, project_root)
        return {
            "ok": True,
            "mode": "snapshot",
            "diff_text": "",
            "changed_files": [],
            "summary": "Snapshot manifest was invalid and has been reset. Re-run verify.",
            "status_preview": init["summary"],
        }

    baseline_files = manifest.get("files") if isinstance(manifest, dict) else {}
    if not isinstance(baseline_files, dict):
        baseline_files = {}

    current_texts = _collect_snapshot_texts(project_root)
    candidate_paths = sorted(set(baseline_files.keys()) | set(current_texts.keys()))

    patch_parts: List[str] = []
    changed_files: List[str] = []
    for rel in candidate_paths:
        old_path = files_root / rel
        old_exists = rel in baseline_files and old_path.exists()
        new_exists = rel in current_texts

        try:
            old_text = old_path.read_text(encoding="utf-8") if old_exists else ""
        except OSError:
            old_text = ""
        new_text = current_texts.get(rel, "")
        if old_exists and new_exists and old_text == new_text:
            continue

        if old_exists and not new_exists:
            from_file = f"a/{rel}"
            to_file = "/dev/null"
        elif new_exists and not old_exists:
            from_file = "/dev/null"
            to_file = f"b/{rel}"
        else:
            from_file = f"a/{rel}"
            to_file = f"b/{rel}"

        diff_lines = list(
            difflib.unified_diff(
                old_text.splitlines(),
                new_text.splitlines(),
                fromfile=from_file,
                tofile=to_file,
                lineterm="",
            )
        )
        if diff_lines:
            patch_parts.append("\n".join(diff_lines))
            if new_exists:
                changed_files.append(rel)

    if not patch_parts:
        return {
            "ok": True,
            "mode": "snapshot",
            "diff_text": "",
            "summary": f"No snapshot changes detected in {project_root.name}.",
            "changed_files": [],
            "status_preview": f"Baseline file count: {len(baseline_files)}",
        }

    return {
        "ok": True,
        "mode": "snapshot",
        "diff_text": "\n\n".join(patch_parts).strip() + "\n",
        "summary": f"Snapshot auto verify: {len(changed_files)} changed file(s) in {project_root.name}",
        "changed_files": changed_files,
        "status_preview": f"Baseline file count: {len(baseline_files)}",
    }


def _build_patch_from_project_root(project_root: Path, *, forge_root: Path) -> Dict[str, Any]:
    if not project_root.exists():
        return {"ok": False, "error": f"PROJECT_ROOT does not exist: {project_root}"}
    if not project_root.is_dir():
        return {"ok": False, "error": f"PROJECT_ROOT is not a directory: {project_root}"}

    probe = _run_git_command(project_root, ["rev-parse", "--is-inside-work-tree"])
    if probe.returncode != 0 or probe.stdout.strip().lower() != "true":
        return _build_patch_from_snapshot(forge_root, project_root)

    status_proc = _run_git_command(project_root, ["status", "--short"])
    if status_proc.returncode != 0:
        return {
            "ok": False,
            "error": f"Unable to read git status: {(status_proc.stderr or '').strip()}",
        }

    staged = _run_git_command(project_root, ["diff", "--binary", "--no-color", "--cached"])
    unstaged = _run_git_command(project_root, ["diff", "--binary", "--no-color"])
    for proc in (staged, unstaged):
        if proc.returncode not in (0, 1):
            return {
                "ok": False,
                "error": f"Failed to build git patch: {(proc.stderr or proc.stdout).strip()}",
            }

    untracked_proc = _run_git_command(
        project_root,
        ["ls-files", "--others", "--exclude-standard"],
    )
    if untracked_proc.returncode != 0:
        return {
            "ok": False,
            "error": f"Unable to list untracked files: {(untracked_proc.stderr or '').strip()}",
        }

    patch_parts: List[str] = []
    if staged.stdout.strip():
        patch_parts.append(staged.stdout.rstrip())
    if unstaged.stdout.strip():
        patch_parts.append(unstaged.stdout.rstrip())

    untracked_files = [line.strip() for line in untracked_proc.stdout.splitlines() if line.strip()]
    for rel_path in untracked_files[:200]:
        created = _run_git_command(
            project_root,
            ["diff", "--binary", "--no-color", "--no-index", "--", "/dev/null", rel_path],
        )
        if created.returncode not in (0, 1):
            continue
        if created.stdout.strip():
            patch_parts.append(created.stdout.rstrip())

    if not patch_parts:
        return {
            "ok": True,
            "mode": "git",
            "diff_text": "",
            "summary": f"Auto verify: no local git changes in {project_root.name}",
            "changed_files": [],
            "status_preview": status_proc.stdout.strip(),
        }

    diff_text = "\n\n".join(patch_parts).strip() + "\n"
    changed_files: List[str] = []
    for line in diff_text.splitlines():
        if not line.startswith("+++ b/"):
            continue
        candidate = line[6:].strip()
        if not candidate or candidate == "/dev/null":
            continue
        if candidate not in changed_files:
            changed_files.append(candidate)

    summary = f"Auto verify: {len(changed_files)} changed file(s) in {project_root.name}"
    return {
        "ok": True,
        "mode": "git",
        "diff_text": diff_text,
        "summary": summary,
        "changed_files": changed_files,
        "status_preview": status_proc.stdout.strip(),
    }


def _execute_verify_flow(
    *,
    root: Path,
    gateway: LLMGateway,
    diff_text: str,
    summary: str,
    domain: str,
    source: str,
) -> Dict[str, Any]:
    reasoning = _run_reasoning_trace(
        gateway,
        diff_text=diff_text,
        summary=summary,
        domain=domain,
    )
    azul = _run_azul_verify(
        root,
        diff_text=diff_text,
        summary=summary,
        domain=domain,
    )
    ticket = azul.get("ticket") or {}
    result = {
        "created_at": _now_iso(),
        "summary": summary,
        "domain": domain,
        "source": source,
        "reasoning": reasoning,
        "azul": azul,
    }
    celebration = None
    if ticket.get("status") == "COMPLETED":
        celebration = {
            "ticket_id": ticket.get("ticket_id", ""),
            "xp_awarded": ticket.get("xp_awarded", 0),
        }
    return {"last_verification": result, "xp_celebration": celebration}


def _draft_to_state_dict(draft: DraftArtifact) -> Dict[str, Any]:
    return {
        "plan_text": draft.plan_text,
        "patch_text": draft.patch_text,
        "plan_trace": draft.plan_trace,
        "patch_trace": draft.patch_trace,
        "impact_map": draft.impact_map,
    }


def _run_drafting_desk_audit(
    *,
    root: Path,
    gateway: LLMGateway,
    agent: RemediationAgent,
    intent: str,
    domain: str,
    patch_text: str,
    summary: str,
    system_catalog: Dict[str, Any],
    danger_map: Dict[str, Any],
    auto_remediate: bool,
    max_attempts: int,
) -> Dict[str, Any]:
    first = _execute_verify_flow(
        root=root,
        gateway=gateway,
        diff_text=patch_text,
        summary=summary,
        domain=domain,
        source="drafting_desk",
    )
    first_ticket = ((first.get("last_verification") or {}).get("azul") or {}).get("ticket") or {}
    attempts: List[Dict[str, Any]] = [
        {
            "attempt": 1,
            "status": first_ticket.get("status", ""),
            "verdict": first_ticket.get("verdict", ""),
            "verdict_reason": first_ticket.get("verdict_reason", ""),
            "summary": summary,
            "ticket_id": first_ticket.get("ticket_id", ""),
        }
    ]

    remediation: Dict[str, Any] = {}
    final_last_verification = first["last_verification"]
    final_xp_celebration = first["xp_celebration"]

    if auto_remediate and first_ticket.get("status") == "REJECTED":
        def _verify_fn(diff_text: str, attempt_summary: str, attempt_no: int) -> Dict[str, Any]:
            return _run_azul_verify(
                root,
                diff_text=diff_text,
                summary=attempt_summary,
                domain=domain,
            )

        remediation = agent.remediate_reject_loop(
            intent=intent,
            domain=domain,
            initial_patch=patch_text,
            system_catalog=system_catalog,
            danger_map=danger_map,
            verify_fn=_verify_fn,
            max_attempts=max_attempts,
            summary_prefix="Drafting Desk remediation",
        )
        for row in remediation.get("attempts") or []:
            verify_payload = row.get("verify") or {}
            ticket = verify_payload.get("ticket") or {}
            attempts.append(
                {
                    "attempt": row.get("attempt", ""),
                    "status": ticket.get("status", ""),
                    "verdict": ticket.get("verdict", ""),
                    "verdict_reason": ticket.get("verdict_reason", ""),
                    "summary": row.get("summary", ""),
                    "ticket_id": ticket.get("ticket_id", ""),
                }
            )

        final_verify = remediation.get("final_verify") or {}
        final_ticket = final_verify.get("ticket") or {}
        if final_ticket:
            final_patch = remediation.get("final_patch") or patch_text
            reasoning = _run_reasoning_trace(
                gateway,
                diff_text=str(final_patch),
                summary="Drafting Desk remediation final attempt",
                domain=domain,
            )
            final_last_verification = {
                "created_at": _now_iso(),
                "summary": "Drafting Desk remediation final attempt",
                "domain": domain,
                "source": "drafting_desk_remediation",
                "reasoning": reasoning,
                "azul": final_verify,
            }
            if final_ticket.get("status") == "COMPLETED":
                final_xp_celebration = {
                    "ticket_id": final_ticket.get("ticket_id", ""),
                    "xp_awarded": final_ticket.get("xp_awarded", 0),
                }

    dedup_attempts: List[Dict[str, Any]] = []
    seen = set()
    for row in attempts:
        key = (row.get("attempt"), row.get("ticket_id"))
        if key in seen:
            continue
        seen.add(key)
        dedup_attempts.append(row)

    return {
        "last_verification": final_last_verification,
        "xp_celebration": final_xp_celebration,
        "attempt_rows": dedup_attempts,
        "remediation": remediation,
    }


def _render_reasoning_sidebar() -> None:
    last = st.session_state.get("last_verification") or {}
    st.subheader("Reasoning Sidebar")
    if not last:
        st.caption("No verification run in this session yet.")
        return

    reasoning = last.get("reasoning") or {}
    azul = last.get("azul") or {}
    ticket = azul.get("ticket") or {}

    st.markdown("**Gateway Trace**")
    if reasoning.get("ok"):
        trace = reasoning.get("trace") or {}
        st.write(f"Model: `{trace.get('model_used', '')}`")
        st.write(f"Tier: `{trace.get('task_tier', '')}`")
        st.write(f"Confidence: `{trace.get('confidence_score', 0):.2f}`")
        if reasoning.get("error"):
            st.warning(f"Gateway degraded to fallback trace: {reasoning.get('error')}")
        steps = trace.get("reasoning_steps") or []
        if steps:
            st.write("Steps:")
            for step in steps:
                st.write(f"- {step}")
        st.caption(f"Raw trace: {trace.get('raw_response_path', '')}")
        with st.expander("Gateway Reasoning Text"):
            st.write(reasoning.get("text", ""))
    else:
        st.warning(f"Gateway trace unavailable: {reasoning.get('error', 'Unknown error')}")

    st.markdown("**Azul Verdict Reason**")
    if ticket:
        st.write(f"Ticket: `{ticket.get('ticket_id', '')}`")
        st.write(f"Status: `{ticket.get('status', '')}`")
        st.write(f"Verdict: `{ticket.get('verdict', '')}`")
        st.write(ticket.get("verdict_reason", "No verdict reason available"))
        metadata = ticket.get("metadata") if isinstance(ticket.get("metadata"), dict) else {}
        if metadata.get("manual_review_required"):
            st.error("Manual Review Required: operational fail-closed path triggered.")
            st.caption(str(metadata.get("operational_friction", "")))
    else:
        st.warning("Ticket result not found. Check command output.")

    with st.expander("Wrapper Output"):
        st.code(azul.get("output", ""), language="text")


def _active_ribbon(status: Dict[str, Any]) -> str:
    scan_ok = int((status.get("last_scan") or {}).get("returncode", 1)) == 0
    assess_ok = int((status.get("last_assess") or {}).get("returncode", 1)) == 0
    contract_ready = int(status.get("uncovered_unit_count", 0)) == 0
    phase = [
        ("Scan", scan_ok),
        ("Assess", assess_ok),
        ("Contract", contract_ready),
        ("Verify", True),
    ]
    pills = []
    for label, active in phase:
        cls = "ribbon-pill active" if active else "ribbon-pill"
        pills.append(f"<span class='{cls}'>{label}</span>")
    return "<div class='ribbon'>" + "".join(pills) + "</div>"


def _render_heatmap(units: List[Dict[str, Any]]) -> None:
    if not units:
        st.info("No risk-tagged units discovered yet.")
        return
    rows = []
    all_tags = set()
    for unit in units:
        all_tags.update(unit.get("risk_tags") or [])
    ordered_tags = sorted(all_tags)
    for unit in units:
        row = {"unit_id": unit.get("id", ""), "path": unit.get("path", "")}
        unit_tags = set(unit.get("risk_tags") or [])
        for tag in ordered_tags:
            row[tag] = 1 if tag in unit_tags else 0
        rows.append(row)
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _ingest_architecture_screenshot(
    *,
    root: Path,
    project_id: str,
    status: Dict[str, Any],
    gateway: LLMGateway,
    upload_name: str,
    image_bytes: bytes,
) -> Dict[str, Any]:
    try:
        ocr = gateway.ocr_image(
            image_bytes=image_bytes,
            prompt=(
                "Extract architecture components, edges, protocols, and any risk-relevant "
                "constraints. Return concise plaintext suitable for system catalog ingestion."
            ),
            system_prompt="Focus on code units, dataflow boundaries, and governance-relevant details.",
            metadata={"source": "cockpit_ocr_ingest", "upload_name": upload_name},
        )
    except GatewayError as exc:
        return {"ok": False, "error": str(exc)}

    catalog_path = _system_catalog_path(root, project_id, status)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog = _load_json(catalog_path) if catalog_path.exists() else {}
    if not isinstance(catalog, dict):
        catalog = {}

    entries = catalog.get("diagram_ingests")
    if not isinstance(entries, list):
        entries = []
    entries.append(
        {
            "ingested_at": _now_iso(),
            "source_file": upload_name,
            "model_used": ocr.trace.model_used,
            "raw_response_path": ocr.trace.raw_response_path,
            "summary_text": ocr.text,
        }
    )
    catalog["diagram_ingests"] = entries[-50:]
    catalog_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "catalog_path": str(catalog_path),
        "trace_path": ocr.trace.raw_response_path,
        "model_used": ocr.trace.model_used,
        "summary_text": ocr.text,
    }


def _render_stub_approvals(root: Path) -> None:
    stubs_dir = root / "action_catalogs" / "stubs"
    stubs_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(stubs_dir.glob("*.yaml"))
    if not files:
        st.info("No pending stubs.")
        return

    for path in files:
        with st.expander(path.name, expanded=False):
            st.code(path.read_text(encoding="utf-8"), language="yaml")
            if st.button(f"Vibe Check: activate {path.name}", key=f"approve-{path.name}"):
                result = approve_stub_file(forge_root=root, filename=path.name)
                if result["status"] == "ok":
                    st.success(f"Moved to active: {result['path']}")
                    st.rerun()
                else:
                    st.error(result["message"])


def _render_scoreboard(root: Path) -> None:
    tickets = _load_completed_tickets(root)
    xp = _load_xp_ledger(root)
    rejects = [t for t in tickets if t.get("status") == "REJECTED"]
    failed = [t for t in tickets if t.get("status") == "FAILED"]
    failed_manual_review = [
        t
        for t in failed
        if isinstance(t.get("metadata"), dict) and t.get("metadata", {}).get("manual_review_required")
    ]
    passes = [t for t in tickets if t.get("verdict") == "pass"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Security Catastrophes Blocked", len(rejects))
    c2.metric("Passing Verifications", len(passes))
    c3.metric("Failed Runs", len(failed))
    c4.metric("Manual Review Required", len(failed_manual_review))

    celebration = st.session_state.get("xp_celebration")
    if celebration:
        st.balloons()
        st.success(
            f"XP awarded on {celebration.get('ticket_id', '')}: +{celebration.get('xp_awarded', 0)}"
        )
        st.session_state.xp_celebration = None

    st.subheader("Verdict Feed")
    feed_rows = []
    for t in tickets[:80]:
        feed_rows.append(
            {
                "ticket_id": t.get("ticket_id", ""),
                "status": t.get("status", ""),
                "verdict": t.get("verdict", ""),
                "updated_at": t.get("updated_at", ""),
                "verdict_reason": t.get("verdict_reason", ""),
            }
        )
    st.dataframe(feed_rows, use_container_width=True, hide_index=True)

    st.subheader("XP Ledger")
    st.dataframe(xp[:80], use_container_width=True, hide_index=True)

    st.subheader("Hang-up Monitoring")
    if not failed:
        st.success("No FAILED shadow-runs detected.")
        return
    if failed_manual_review:
        st.warning(
            "Fail-closed operational tickets detected. Human review is required before proceeding."
        )
    for failure in failed[:10]:
        with st.container():
            st.markdown("<div class='cockpit-card'>", unsafe_allow_html=True)
            st.markdown(f"**{failure.get('ticket_id')}**")
            st.write(failure.get("verdict_reason", "No reason provided"))
            trace = (
                (failure.get("metadata") or {}).get("traceback")
                or (failure.get("review_bundle") or {}).get("failure_reason")
                or "Traceback unavailable."
            )
            st.code(str(trace), language="text")
            st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(
        page_title="Forge Federation Cockpit",
        page_icon="🛡️",
        layout="wide",
    )
    _apply_style()

    root = _forge_root()
    default_root = str(root)
    default_project_root = os.environ.get("PROJECT_ROOT", default_root)

    if "project_root" not in st.session_state:
        st.session_state.project_root = default_project_root
    if "project_id" not in st.session_state:
        st.session_state.project_id = default_project_id(Path(st.session_state.project_root))
    if "local_engine" not in st.session_state:
        st.session_state.local_engine = "ollama"
    if "frontier_engine" not in st.session_state:
        st.session_state.frontier_engine = os.environ.get("FRONTIER_PROVIDER", "anthropic")
    if "local_only_mode" not in st.session_state:
        st.session_state.local_only_mode = (
            os.environ.get("FORGE_LOCAL_ONLY", "true").strip().lower() == "true"
        )
    if "ollama_model" not in st.session_state:
        st.session_state.ollama_model = os.environ.get(
            "OLLAMA_SCAN_MODEL",
            os.environ.get("OLLAMA_MODEL", OLLAMA_SCAN_DEFAULT),
        )
    if "last_verification" not in st.session_state:
        st.session_state.last_verification = {}
    if "xp_celebration" not in st.session_state:
        st.session_state.xp_celebration = None
    if "drafting_intent" not in st.session_state:
        st.session_state.drafting_intent = ""
    if "drafting_domain" not in st.session_state:
        st.session_state.drafting_domain = "system_operations"
    if "drafting_draft" not in st.session_state:
        st.session_state.drafting_draft = {}
    if "drafting_patch_text" not in st.session_state:
        st.session_state.drafting_patch_text = ""
    if "drafting_attempt_rows" not in st.session_state:
        st.session_state.drafting_attempt_rows = []
    if "drafting_remediation" not in st.session_state:
        st.session_state.drafting_remediation = {}

    st.title("Forge Federation Cockpit")
    st.caption("Glass Box + Ignition System for governed AI delivery.")

    with st.sidebar:
        st.header("Ignition")
        st.session_state.project_root = st.text_input("PROJECT_ROOT", st.session_state.project_root)
        st.session_state.project_id = st.text_input("Project ID", st.session_state.project_id)
        st.session_state.local_engine = st.selectbox(
            "Local Engine",
            options=["vllm", "ollama"],
            index=0 if st.session_state.local_engine == "vllm" else 1,
        )
        st.session_state.frontier_engine = st.selectbox(
            "Frontier Engine",
            options=["openai", "anthropic"],
            index=0 if st.session_state.frontier_engine == "openai" else 1,
        )
        st.session_state.local_only_mode = st.toggle(
            "Local-Only Smoke Mode",
            value=st.session_state.local_only_mode,
            help="Use local providers only for all LLM tiers (no frontier fallback).",
        )

        ollama_endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
        if st.session_state.local_engine == "ollama":
            ollama_models = _list_ollama_models(ollama_endpoint)
            if ollama_models:
                if st.session_state.ollama_model not in ollama_models:
                    st.session_state.ollama_model = ollama_models[0]
                st.session_state.ollama_model = st.selectbox(
                    "Ollama Model",
                    options=ollama_models,
                    index=ollama_models.index(st.session_state.ollama_model),
                    key="ollama_model_selectbox",
                )
            else:
                st.session_state.ollama_model = st.text_input(
                    "Ollama Model",
                    value=st.session_state.ollama_model,
                    key="ollama_model_input",
                )

        local_primary = st.session_state.local_engine
        local_alt = "ollama" if local_primary == "vllm" else "vllm"
        if st.session_state.local_only_mode:
            routing_order = f"{local_primary},{local_alt}"
            os.environ["FORGE_LOCAL_ONLY"] = "true"
        else:
            routing_order = f"{local_primary},frontier,{local_alt}"
            os.environ["FORGE_LOCAL_ONLY"] = "false"
        os.environ["FRONTIER_PROVIDER"] = st.session_state.frontier_engine
        os.environ["LLM_SCAN_ORDER"] = routing_order
        os.environ["LLM_REASONING_ORDER"] = routing_order
        os.environ["LLM_VERDICT_ORDER"] = routing_order
        os.environ["LLM_LOCAL_ORDER"] = routing_order
        os.environ["LLM_OCR_ORDER"] = "ollama"
        os.environ["OLLAMA_SCAN_MODEL"] = st.session_state.ollama_model
        os.environ["OLLAMA_MODEL"] = st.session_state.ollama_model
        os.environ.setdefault("OLLAMA_REASONING_MODEL", OLLAMA_REASONING_DEFAULT)
        os.environ.setdefault("OLLAMA_VERDICT_MODEL", OLLAMA_VERDICT_DEFAULT)
        os.environ.setdefault("OLLAMA_EMBEDDING_MODEL", OLLAMA_EMBEDDING_DEFAULT)
        os.environ.setdefault("OLLAMA_OCR_MODEL", OLLAMA_OCR_DEFAULT)
        os.environ.setdefault("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")

        gateway = LLMGateway()
        agent = RemediationAgent(
            gateway=gateway,
            forge_root=root,
            project_root=Path(st.session_state.project_root).expanduser(),
        )
        gateway_health = gateway.health()
        frameworks = _framework_states(root, gateway_health)
        daemon_status = load_runtime_status(forge_root=root)
        frameworks["Warden"] = {
            "status": "running" if daemon_status.get("running") else "stopped",
            "detail": daemon_status.get("phase", "stopped"),
        }

        for name, state in frameworks.items():
            st.markdown(
                f"{_dot(state['status'])}<strong>{name}</strong><br><small>{state['detail']}</small>",
                unsafe_allow_html=True,
            )

        if (
            gateway_health["vllm"]["status"] != "running"
            and gateway_health["ollama"]["status"] == "running"
            and st.session_state.local_engine != "ollama"
        ):
            st.warning("vLLM is down. Fallback is available.")
            if st.button("Fallback to Ollama"):
                st.session_state.local_engine = "ollama"
                st.rerun()

        st.divider()
        if daemon_status.get("running"):
            if st.button("Stop Warden", type="primary"):
                result = stop_daemon_process(forge_root=root)
                if result["status"] == "ok":
                    st.success(result["message"])
                    st.rerun()
                st.error(result["message"])
        else:
            if st.button("Start Warden", type="primary"):
                result = start_daemon_process(
                    forge_root=root,
                    project_root=Path(st.session_state.project_root),
                    project_id=st.session_state.project_id,
                    env_overrides={
                        "FRONTIER_PROVIDER": st.session_state.frontier_engine,
                        "LLM_SCAN_ORDER": routing_order,
                        "LLM_REASONING_ORDER": routing_order,
                        "LLM_VERDICT_ORDER": routing_order,
                        "LLM_LOCAL_ORDER": routing_order,
                        "LLM_OCR_ORDER": "ollama",
                        "FORGE_LOCAL_ONLY": "true" if st.session_state.local_only_mode else "false",
                        "OLLAMA_SCAN_MODEL": st.session_state.ollama_model,
                        "OLLAMA_REASONING_MODEL": os.environ.get(
                            "OLLAMA_REASONING_MODEL", OLLAMA_REASONING_DEFAULT
                        ),
                        "OLLAMA_VERDICT_MODEL": os.environ.get(
                            "OLLAMA_VERDICT_MODEL", OLLAMA_VERDICT_DEFAULT
                        ),
                        "OLLAMA_EMBEDDING_MODEL": os.environ.get(
                            "OLLAMA_EMBEDDING_MODEL", OLLAMA_EMBEDDING_DEFAULT
                        ),
                        "OLLAMA_OCR_MODEL": os.environ.get(
                            "OLLAMA_OCR_MODEL", OLLAMA_OCR_DEFAULT
                        ),
                        "ANTHROPIC_MODEL": os.environ.get(
                            "ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"
                        ),
                        "OLLAMA_MODEL": st.session_state.ollama_model,
                    },
                )
                if result["status"] == "ok":
                    st.success(f"Warden started (pid={result.get('pid', 'n/a')})")
                    st.rerun()
                st.error(result["message"])

        st.divider()
        _render_reasoning_sidebar()

    daemon_status = load_runtime_status(forge_root=root)
    project_id = st.session_state.project_id
    danger_map = _load_danger_map(root, project_id, daemon_status)
    system_catalog = _load_system_catalog(root, project_id, daemon_status)
    units = system_catalog.get("units", [])
    risk_units = [u for u in units if u.get("risk_tags")]

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["Tactical Map", "Warden Desk", "Drafting Desk", "XP Scoreboard", "Verify Action"]
    )

    with tab1:
        st.markdown(_active_ribbon(daemon_status), unsafe_allow_html=True)

        st.subheader("Risk Heatmap")
        _render_heatmap(risk_units)

        st.subheader("Architecture OCR Ingest")
        image_upload = st.file_uploader(
            "Upload architecture screenshot",
            type=["png", "jpg", "jpeg", "webp"],
            key="architecture_ocr_upload",
        )
        if image_upload is not None:
            st.caption(f"Ready to ingest `{image_upload.name}` with `{OLLAMA_OCR_DEFAULT}`.")
            if st.button("Ingest into System Catalog", key="architecture_ocr_ingest"):
                with st.spinner("Running glm-ocr and updating system catalog..."):
                    ingest = _ingest_architecture_screenshot(
                        root=root,
                        project_id=project_id,
                        status=daemon_status,
                        gateway=gateway,
                        upload_name=image_upload.name,
                        image_bytes=image_upload.getvalue(),
                    )
                if ingest.get("ok"):
                    st.success(f"OCR ingested into {ingest['catalog_path']}")
                    with st.expander("OCR Summary"):
                        st.write(ingest.get("summary_text", ""))
                        st.caption(f"Model: {ingest.get('model_used', '')}")
                        st.caption(f"Trace: {ingest.get('trace_path', '')}")
                    st.rerun()
                else:
                    st.error(f"OCR ingest failed: {ingest.get('error', 'unknown error')}")

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Latest Danger Map")
            st.json(danger_map or {"status": "missing"})
        with c2:
            st.subheader("Warden Runtime")
            st.json(daemon_status)

    with tab2:
        st.subheader("Pending Contract Stubs")
        _render_stub_approvals(root)

        st.subheader("Active Contracts")
        active_dir = root / "action_catalogs" / "active"
        active_dir.mkdir(parents=True, exist_ok=True)
        active_files = sorted(active_dir.glob("*.yaml"))
        if not active_files:
            st.info("No active contracts yet.")
        else:
            for path in active_files:
                with st.expander(path.name, expanded=False):
                    data = yaml.safe_load(path.read_text(encoding="utf-8"))
                    st.json(data)

        st.subheader("Remediation Desk (Ready for Human Final Review)")
        st.caption(
            "Daemon-posted fixes that passed Azul after auto-remediation. "
            "Review before any manual application to PROJECT_ROOT."
        )
        remediation_items = _load_remediation_queue(root)
        if not remediation_items:
            st.info("No pending remediation items.")
        else:
            for item in remediation_items:
                item_id = str(item.get("id", "unknown"))
                label = (
                    f"{item_id} | status={item.get('status', '')} | "
                    f"final_ticket={item.get('final_ticket_id', '')}"
                )
                with st.expander(label, expanded=False):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Status", str(item.get("status", "")))
                    c2.metric("Attempts", int(item.get("attempt_count", 0) or 0))
                    c3.metric("Domain", str(item.get("domain", "")))
                    st.write(f"Initial Ticket: `{item.get('initial_ticket_id', '')}`")
                    st.write(f"Final Ticket: `{item.get('final_ticket_id', '')}`")
                    st.write(f"Cycle: `{item.get('cycle_id', '')}` ({item.get('cycle_reason', '')})")
                    st.write(f"Changed Files: `{len(item.get('changed_files') or [])}`")
                    st.write(
                        f"Auto Apply Performed: `{item.get('auto_apply_performed', False)}` "
                        "(expected `False`)"
                    )
                    patch_path = Path(str(item.get("patch_path", "")))
                    if patch_path.exists():
                        with st.expander("Remediation Patch"):
                            st.code(patch_path.read_text(encoding="utf-8"), language="diff")
                    else:
                        st.warning(f"Patch missing: {patch_path}")

                    if st.button("Mark as Reviewed", key=f"review-remediation-{item_id}"):
                        result = _mark_remediation_reviewed(root, item_id=item_id)
                        if result.get("ok"):
                            st.success(f"Moved to reviewed: {result.get('path', '')}")
                            st.rerun()
                        st.error(result.get("message", "Unable to mark remediation as reviewed."))

    with tab3:
        st.subheader("Drafting Desk")
        st.caption(
            "Planner-Worker-Judge flow: Intent -> Blueprint + Patch -> Azul auto-audit."
        )
        drafting_domain_options = [
            "ci_change_control",
            "it_ops_runbook",
            "system_operations",
        ]
        if st.session_state.drafting_domain not in drafting_domain_options:
            st.session_state.drafting_domain = drafting_domain_options[0]

        st.session_state.drafting_intent = st.text_area(
            "Natural Language Intent",
            value=st.session_state.drafting_intent,
            key="drafting_intent_input",
            height=130,
            placeholder=(
                "Example: Replace unsafe subprocess invocation in src/app/__init__.py "
                "with an allow-listed command and shell=False."
            ),
        )
        st.session_state.drafting_domain = st.selectbox(
            "Draft Domain",
            options=drafting_domain_options,
            index=drafting_domain_options.index(st.session_state.drafting_domain),
            key="drafting_domain_select",
        )

        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("Generate Blueprint + Patch", type="primary"):
                if not st.session_state.drafting_intent.strip():
                    st.error("Provide an intent first.")
                else:
                    try:
                        with st.spinner("Generating implementation plan and patch..."):
                            draft = agent.generate_draft(
                                intent=st.session_state.drafting_intent.strip(),
                                domain=st.session_state.drafting_domain,
                                system_catalog=system_catalog,
                                danger_map=danger_map,
                            )
                        st.session_state.drafting_draft = _draft_to_state_dict(draft)
                        st.session_state.drafting_patch_text = draft.patch_text
                        st.session_state.drafting_attempt_rows = []
                        st.session_state.drafting_remediation = {}
                    except GatewayError as exc:
                        st.error(f"Draft generation failed: {exc}")
        with c2:
            st.caption(
                "Drafts use `TIER_SCAN` for impact mapping, `TIER_REASONING` for the plan, "
                "and `TIER_VERDICT` for patch synthesis."
            )

        draft_state = st.session_state.get("drafting_draft") or {}
        if draft_state:
            plan_col, patch_col = st.columns(2)
            with plan_col:
                st.markdown("**Implementation Plan**")
                st.code(draft_state.get("plan_text", ""), language="markdown")
                with st.expander("Impact Map"):
                    st.code(draft_state.get("impact_map", ""), language="text")
                with st.expander("Plan Trace"):
                    st.json(draft_state.get("plan_trace", {}))
            with patch_col:
                st.markdown("**Proposed Patch**")
                st.session_state.drafting_patch_text = st.text_area(
                    "Unified Diff (editable before audit)",
                    value=st.session_state.drafting_patch_text,
                    key="drafting_patch_text_area",
                    height=320,
                )
                with st.expander("Patch Trace"):
                    st.json(draft_state.get("patch_trace", {}))

            st.divider()
            auto_remediate = st.toggle(
                "Auto-remediate on REJECT (max 3 attempts)",
                value=True,
                key="drafting_auto_remediate",
            )
            max_attempts = st.slider(
                "Remediation Attempt Limit",
                min_value=1,
                max_value=3,
                value=3,
                key="drafting_max_attempts",
            )
            if st.button("Run Draft Auto-Audit (via scripts/azul-verify)", key="drafting_auto_audit"):
                patch_text = st.session_state.drafting_patch_text.strip()
                if not patch_text:
                    st.error("Generated patch is empty. Regenerate or edit the patch first.")
                else:
                    summary = f"Drafting Desk: {st.session_state.drafting_intent[:120]}"
                    try:
                        with st.spinner("Running Azul audit and remediation loop..."):
                            result = _run_drafting_desk_audit(
                                root=root,
                                gateway=gateway,
                                agent=agent,
                                intent=st.session_state.drafting_intent.strip(),
                                domain=st.session_state.drafting_domain,
                                patch_text=patch_text,
                                summary=summary,
                                system_catalog=system_catalog,
                                danger_map=danger_map,
                                auto_remediate=auto_remediate,
                                max_attempts=max_attempts,
                            )
                        st.session_state.last_verification = result["last_verification"]
                        if result["xp_celebration"]:
                            st.session_state.xp_celebration = result["xp_celebration"]
                        st.session_state.drafting_attempt_rows = result.get("attempt_rows", [])
                        st.session_state.drafting_remediation = result.get("remediation", {})
                        final_patch = str(
                            (st.session_state.drafting_remediation.get("final_patch") or "")
                        ).strip()
                        if final_patch:
                            st.session_state.drafting_patch_text = final_patch
                        st.rerun()
                    except GatewayError as exc:
                        st.error(f"Remediation loop failed: {exc}")

        attempt_rows = st.session_state.get("drafting_attempt_rows") or []
        if attempt_rows:
            st.subheader("Auto-Audit Attempts")
            st.dataframe(attempt_rows, use_container_width=True, hide_index=True)
            remediation = st.session_state.get("drafting_remediation") or {}
            if remediation:
                with st.expander("Remediation Details"):
                    st.json(remediation)

    with tab4:
        _render_scoreboard(root)

    with tab5:
        st.subheader("Draft Input")
        verify_summary = st.text_input(
            "Change Summary",
            value=DEFAULT_VERIFY_SUMMARY,
            key="verify_summary",
        )
        verify_domain = st.selectbox(
            "Verification Domain",
            options=["ci_change_control", "it_ops_runbook", "system_operations"],
            index=0,
            key="verify_domain",
        )
        upload = st.file_uploader(
            "Upload Patch (.patch/.diff)",
            type=["patch", "diff", "txt"],
            key="verify_upload",
        )
        draft_diff = st.text_area(
            "Or paste diff draft",
            height=260,
            key="verify_diff_text",
            placeholder="--- a/src/file.py\n+++ b/src/file.py\n@@ ...",
        )
        upload_text = ""
        if upload is not None:
            upload_text = upload.getvalue().decode("utf-8", errors="replace")
            st.info(f"Using uploaded patch `{upload.name}` ({len(upload_text)} chars)")

        diff_text = upload_text.strip() if upload_text.strip() else draft_diff.strip()
        if st.button("Run Verify via scripts/azul-verify", type="primary"):
            effective_diff = diff_text
            effective_summary = verify_summary
            source_mode = "manual"

            if not effective_diff:
                project_root = Path(st.session_state.project_root).expanduser().resolve()
                auto_patch = _build_patch_from_project_root(project_root, forge_root=root)
                if not auto_patch.get("ok"):
                    st.error(
                        "No draft/upload was provided, and auto diff fallback failed: "
                        f"{auto_patch.get('error', 'unknown error')}"
                    )
                elif not auto_patch.get("diff_text"):
                    st.error(
                        "No draft/upload was provided, and no local git changes were found in PROJECT_ROOT."
                    )
                else:
                    effective_diff = str(auto_patch["diff_text"])
                    source_mode = "auto_git_fallback"
                    if (
                        not effective_summary.strip()
                        or effective_summary == DEFAULT_VERIFY_SUMMARY
                    ):
                        effective_summary = str(
                            auto_patch.get("summary", DEFAULT_VERIFY_SUMMARY)
                        )
                    mode = str(auto_patch.get("mode", "auto"))
                    st.info(
                        "No manual diff provided. Using PROJECT_ROOT auto diff fallback "
                        f"[mode={mode}] ({len(auto_patch.get('changed_files') or [])} file(s))."
                    )

            if effective_diff:
                with st.spinner("Running gateway reasoning + Azul verify wrapper..."):
                    executed = _execute_verify_flow(
                        root=root,
                        gateway=gateway,
                        diff_text=effective_diff,
                        summary=effective_summary,
                        domain=verify_domain,
                        source=source_mode,
                    )
                    st.session_state.last_verification = executed["last_verification"]
                    if executed["xp_celebration"]:
                        st.session_state.xp_celebration = executed["xp_celebration"]
                st.rerun()

        st.divider()
        st.subheader("Auto Verify")
        st.caption(
            "No upload required. Builds a patch from PROJECT_ROOT via git diff or snapshot diff."
        )
        st.code(st.session_state.project_root, language="text")

        if st.button("Run Auto Verify from PROJECT_ROOT (git/snapshot diff)"):
            project_root = Path(st.session_state.project_root).expanduser().resolve()
            auto_patch = _build_patch_from_project_root(project_root, forge_root=root)
            if not auto_patch.get("ok"):
                st.error(auto_patch.get("error", "Failed to build patch from PROJECT_ROOT changes."))
            elif not auto_patch.get("diff_text"):
                st.info(auto_patch.get("summary", "No local changes detected in PROJECT_ROOT."))
            else:
                changed_files = auto_patch.get("changed_files") or []
                mode = str(auto_patch.get("mode", "auto"))
                st.info(
                    "Generated patch with "
                    f"{len(changed_files)} changed file(s) from {project_root} [mode={mode}]."
                )
                auto_summary = verify_summary.strip()
                if not auto_summary or auto_summary == DEFAULT_VERIFY_SUMMARY:
                    auto_summary = auto_patch.get("summary", DEFAULT_VERIFY_SUMMARY)
                with st.spinner("Running auto verify from git diff..."):
                    executed = _execute_verify_flow(
                        root=root,
                        gateway=gateway,
                        diff_text=str(auto_patch["diff_text"]),
                        summary=auto_summary,
                        domain=verify_domain,
                        source="auto_git_diff",
                    )
                    st.session_state.last_verification = executed["last_verification"]
                    if executed["xp_celebration"]:
                        st.session_state.xp_celebration = executed["xp_celebration"]
                st.rerun()

        if st.button("Refresh Snapshot Baseline"):
            project_root = Path(st.session_state.project_root).expanduser().resolve()
            refreshed = _write_snapshot_baseline(root, project_root)
            if refreshed.get("ok"):
                st.success(refreshed.get("summary", "Snapshot baseline refreshed."))
            else:
                st.error(refreshed.get("error", "Unable to refresh snapshot baseline."))

        last = st.session_state.get("last_verification") or {}
        if last:
            azul = last.get("azul") or {}
            ticket = azul.get("ticket") or {}
            c1, c2, c3 = st.columns(3)
            c1.metric("Last Ticket", ticket.get("ticket_id", "n/a"))
            c2.metric("Status", ticket.get("status", "unknown"))
            c3.metric("XP Awarded", ticket.get("xp_awarded", 0))
            st.markdown("**Verdict Reason**")
            st.write(ticket.get("verdict_reason", "No verdict reason available."))
            with st.expander("Command Output"):
                st.code(azul.get("output", ""), language="text")


if __name__ == "__main__":
    main()
