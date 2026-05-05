"""Federation Warden daemon: watch code, trigger scan/assess, draft contract stubs."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import yaml

from .llm_gateway import GatewayError, LLMGateway
from .remediation_agent import RemediationAgent


_WATCH_EXTENSIONS = {
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
}

_SNAPSHOT_MAX_FILE_BYTES = 512 * 1024
_SNAPSHOT_INCLUDE_EXTENSIONS = {
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
_SNAPSHOT_EXCLUDE_DIRS = {
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _azul_data_dir(forge_root: Path) -> Path:
    default = forge_root / "azul_data"
    return Path(os.environ.get("AZUL_DATA_DIR", str(default))).resolve()


def _contract_baseline_path(*, forge_root: Path, contract_path: Path) -> Path:
    baseline_root = _azul_data_dir(forge_root) / "baselines" / "contracts"
    catalogs_root = (forge_root / "action_catalogs").resolve()
    try:
        rel = contract_path.resolve().relative_to(catalogs_root)
    except ValueError:
        rel = Path(contract_path.name)
    return baseline_root / rel


def _snapshot_contract_baseline(*, forge_root: Path, contract_path: Path) -> Path:
    baseline_path = _contract_baseline_path(forge_root=forge_root, contract_path=contract_path)
    if baseline_path.exists():
        return baseline_path
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(contract_path, baseline_path)
    return baseline_path


def default_forge_root() -> Path:
    return Path(os.environ.get("FORGE_ROOT", Path.cwd())).resolve()


def default_project_id(project_root: Path) -> str:
    return f"{_slug(project_root.name or 'project')}_watch"


@dataclass(frozen=True)
class WardenConfig:
    forge_root: Path
    project_root: Path
    project_id: str
    poll_interval_sec: float = 5.0
    debounce_sec: float = 2.0
    run_on_start: bool = True

    @property
    def scripts_dir(self) -> Path:
        return self.forge_root / "scripts"

    @property
    def state_dir(self) -> Path:
        return self.forge_root / "warden" / "state"

    @property
    def status_path(self) -> Path:
        return self.state_dir / "warden_status.json"

    @property
    def events_path(self) -> Path:
        return self.state_dir / "events.jsonl"

    @property
    def pid_path(self) -> Path:
        return self.state_dir / "warden.pid"

    @property
    def log_path(self) -> Path:
        return self.state_dir / "warden.log"

    @property
    def stubs_dir(self) -> Path:
        return self.forge_root / "action_catalogs" / "stubs"

    @property
    def active_dir(self) -> Path:
        return self.forge_root / "action_catalogs" / "active"

    @property
    def system_catalog_path(self) -> Path:
        return (
            self.forge_root
            / "DAWN"
            / "projects"
            / self.project_id
            / "artifacts"
            / "forgescaffold.system_catalog"
            / "system_catalog.json"
        )

    @property
    def danger_map_path(self) -> Path:
        return (
            self.forge_root
            / "DAWN"
            / "projects"
            / self.project_id
            / "artifacts"
            / "concord.danger_map"
            / "danger_map.json"
        )

    @property
    def verify_inputs_dir(self) -> Path:
        return self.forge_root / "forge_output" / "verify_inputs"

    @property
    def remediation_desk_pending_dir(self) -> Path:
        return _azul_data_dir(self.forge_root) / "remediation_desk" / "pending"

    @property
    def remediation_desk_reviewed_dir(self) -> Path:
        return _azul_data_dir(self.forge_root) / "remediation_desk" / "reviewed"

    @property
    def remediation_desk_patches_dir(self) -> Path:
        return _azul_data_dir(self.forge_root) / "remediation_desk" / "patches"

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "WardenConfig":
        forge_root = Path(args.forge_root or default_forge_root()).resolve()
        project_root = Path(args.project_root).resolve()
        project_id = args.project_id or default_project_id(project_root)
        return cls(
            forge_root=forge_root,
            project_root=project_root,
            project_id=project_id,
            poll_interval_sec=args.poll_interval,
            debounce_sec=args.debounce,
            run_on_start=not args.no_run_on_start,
        )


class FederationWarden:
    """Main daemon engine."""

    def __init__(self, config: WardenConfig, gateway: Optional[LLMGateway] = None):
        self.config = config
        self.gateway = gateway or LLMGateway()
        self.remediator = RemediationAgent(
            gateway=self.gateway,
            forge_root=self.config.forge_root,
            project_root=self.config.project_root,
        )
        self._status: Dict[str, Any] = {}
        self._last_cycle_at = 0.0

        self.config.state_dir.mkdir(parents=True, exist_ok=True)
        self.config.stubs_dir.mkdir(parents=True, exist_ok=True)
        self.config.active_dir.mkdir(parents=True, exist_ok=True)
        self.config.verify_inputs_dir.mkdir(parents=True, exist_ok=True)
        self.config.remediation_desk_pending_dir.mkdir(parents=True, exist_ok=True)
        self.config.remediation_desk_reviewed_dir.mkdir(parents=True, exist_ok=True)
        self.config.remediation_desk_patches_dir.mkdir(parents=True, exist_ok=True)

    def run_forever(self) -> int:
        stop = {"value": False}

        def _request_stop(_signum: int, _frame: Any) -> None:
            stop["value"] = True
            self._append_event("signal", "Shutdown signal received", {})

        signal.signal(signal.SIGTERM, _request_stop)
        signal.signal(signal.SIGINT, _request_stop)

        self._write_pid()
        self._update_status(
            running=True,
            phase="starting",
            last_heartbeat_at=_now_iso(),
            project_id=self.config.project_id,
            project_root=str(self.config.project_root),
            forge_root=str(self.config.forge_root),
        )
        self._append_event("daemon", "Warden daemon started", {"pid": os.getpid()})
        startup_requeue = self._requeue_stuck_tickets_on_startup()
        self._update_status(startup_requeue=startup_requeue)

        snapshot = self._collect_file_state()
        if self.config.run_on_start:
            self.run_cycle(reason="startup", changed_files=[])
            snapshot = self._collect_file_state()

        while not stop["value"]:
            time.sleep(self.config.poll_interval_sec)
            new_snapshot = self._collect_file_state()
            changed = self._detect_changes(snapshot, new_snapshot)
            snapshot = new_snapshot

            self._update_status(last_heartbeat_at=_now_iso(), phase="idle")
            if not changed:
                continue

            now = time.time()
            if now - self._last_cycle_at < self.config.debounce_sec:
                continue
            self._last_cycle_at = now
            self.run_cycle(reason="file_change", changed_files=changed)

        self._update_status(running=False, phase="stopped", last_heartbeat_at=_now_iso())
        self._append_event("daemon", "Warden daemon stopped", {})
        self._remove_pid()
        return 0

    def run_cycle(self, *, reason: str, changed_files: list[str]) -> None:
        cycle_id = uuid.uuid4().hex[:10]
        self._update_status(
            phase="running",
            cycle_id=cycle_id,
            cycle_reason=reason,
            changed_files=changed_files[:100],
            last_cycle_started_at=_now_iso(),
        )
        self._append_event(
            "cycle_start",
            "Cycle started",
            {"cycle_id": cycle_id, "reason": reason, "changed_files": changed_files},
        )

        self._stage_dawn_inputs(changed_files)
        scan_result = self._run_script("forge-scan", [self.config.project_id])
        if scan_result["returncode"] != 0:
            self._update_status(
                phase="error",
                last_error=f"forge-scan failed: {scan_result['stderr_tail']}",
                last_scan=scan_result,
                running=True,
            )
            self._append_event(
                "cycle_error",
                "forge-scan failed",
                {"cycle_id": cycle_id, "scan_result": scan_result},
            )
            return

        assess_result = self._run_script("forge-assess", [self.config.project_id])
        if assess_result["returncode"] != 0:
            self._update_status(
                phase="error",
                last_error=f"forge-assess failed: {assess_result['stderr_tail']}",
                last_scan=scan_result,
                last_assess=assess_result,
                running=True,
            )
            self._append_event(
                "cycle_error",
                "forge-assess failed",
                {"cycle_id": cycle_id, "assess_result": assess_result},
            )
            return

        risk_units = self._load_risk_units()
        active_units = self._load_active_unit_ids()
        uncovered = [u for u in risk_units if u["id"] not in active_units]
        generated = self._generate_stubs(uncovered)
        verification = self._run_auto_verify_and_remediate(
            cycle_id=cycle_id,
            reason=reason,
            changed_files=changed_files,
        )

        self._update_status(
            phase="idle",
            last_error="",
            running=True,
            last_cycle_completed_at=_now_iso(),
            last_scan=scan_result,
            last_assess=assess_result,
            last_system_catalog=str(self.config.system_catalog_path),
            last_danger_map=str(self.config.danger_map_path),
            uncovered_units=uncovered,
            generated_stubs=generated,
            risk_unit_count=len(risk_units),
            uncovered_unit_count=len(uncovered),
            last_verify=verification.get("verify", {}),
            last_remediation=verification.get("remediation", {}),
            remediation_queue_item=verification.get("queue_item", {}),
        )
        self._append_event(
            "cycle_done",
            "Cycle completed",
            {
                "cycle_id": cycle_id,
                "risk_unit_count": len(risk_units),
                "uncovered_unit_count": len(uncovered),
                "generated_count": len(generated),
                "verify_state": verification.get("state", ""),
            },
        )

    def _generate_stubs(self, uncovered_units: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        generated: list[Dict[str, Any]] = []
        for unit in uncovered_units:
            unit_id = str(unit["id"])
            stub_path = self.config.stubs_dir / f"{_slug(unit_id)}.yaml"
            if stub_path.exists():
                generated.append(
                    {
                        "unit_id": unit_id,
                        "path": str(stub_path),
                        "status": "exists",
                        "reasoning_trace_path": "",
                    }
                )
                continue

            stub_yaml, reasoning_trace_path = self._build_stub(unit)
            stub_path.write_text(stub_yaml, encoding="utf-8")
            _snapshot_contract_baseline(
                forge_root=self.config.forge_root,
                contract_path=stub_path,
            )
            generated.append(
                {
                    "unit_id": unit_id,
                    "path": str(stub_path),
                    "status": "generated",
                    "reasoning_trace_path": reasoning_trace_path,
                }
            )
        return generated

    def _build_stub(self, unit: Dict[str, Any]) -> tuple[str, str]:
        unit_id = str(unit.get("id", "unknown.unit"))
        risk_tags = unit.get("risk_tags", [])
        trace_path = ""
        prompt = (
            "Generate a YAML action contract stub for this risky unit.\n"
            f"unit_id: {unit_id}\n"
            f"risk_tags: {risk_tags}\n"
            "Output only YAML with keys: domain, unit_id, actions[]."
        )
        system = (
            "You are a governance contract assistant. "
            "Return valid YAML only. Keep guard predicates explicit and conservative."
        )

        try:
            response = self.gateway.complete(
                task_tier="TIER_REASONING",
                prompt=prompt,
                system_prompt=system,
                reasoning_steps=[
                    f"Inspecting risk tags for {unit_id}",
                    "Drafting conservative guard predicates",
                ],
                metadata={"unit_id": unit_id, "source": "warden_stub_generation"},
            )
            trace_path = response.trace.raw_response_path
            candidate = self._extract_yaml_block(response.text)
            if self._is_stub_valid(candidate, expected_unit_id=unit_id):
                return candidate, trace_path
        except GatewayError as exc:
            self._append_event(
                "llm_fallback",
                "LLM generation failed, using deterministic stub",
                {"unit_id": unit_id, "error": str(exc)},
            )

        return self._deterministic_stub(unit), trace_path

    def _deterministic_stub(self, unit: Dict[str, Any]) -> str:
        unit_id = str(unit.get("id", "unknown.unit"))
        risk_tags = list(unit.get("risk_tags") or [])
        risk_tier = 3 if any(tag in {"critical", "subprocess", "auth"} for tag in risk_tags) else 2
        action_id = "review_required"
        if "subprocess" in unit_id:
            action_id = "check_call"
        stub = {
            "domain": "generated_risk_controls",
            "unit_id": unit_id,
            "actions": [
                {
                    "id": action_id,
                    "description": f"Auto-generated contract candidate for {unit_id}",
                    "guard_predicates": [
                        "manual_review_required == True",
                        "change_risk_acknowledged == True",
                    ],
                    "risk_tier": risk_tier,
                    "consistency_profile": "eventual",
                }
            ],
        }
        return yaml.safe_dump(stub, sort_keys=False)

    @staticmethod
    def _extract_yaml_block(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            parts = stripped.split("```")
            for part in parts:
                clean = part.strip()
                if not clean:
                    continue
                if clean.startswith("yaml"):
                    clean = clean[4:].lstrip()
                if ":" in clean:
                    return clean
        return stripped

    @staticmethod
    def _is_stub_valid(content: str, *, expected_unit_id: str) -> bool:
        try:
            data = yaml.safe_load(content)
        except Exception:
            return False
        if not isinstance(data, dict):
            return False
        if str(data.get("unit_id", "")) != expected_unit_id:
            return False
        actions = data.get("actions")
        return isinstance(actions, list) and len(actions) > 0

    def _load_risk_units(self) -> list[Dict[str, Any]]:
        if not self.config.system_catalog_path.exists():
            return []
        catalog = json.loads(self.config.system_catalog_path.read_text(encoding="utf-8"))
        units = catalog.get("units", [])
        out = []
        for unit in units:
            risk_tags = unit.get("risk_tags") or []
            if risk_tags:
                out.append(
                    {
                        "id": str(unit.get("id", "")),
                        "path": str(unit.get("path", "")),
                        "risk_tags": list(risk_tags),
                        "type": str(unit.get("type", "")),
                    }
                )
        return out

    def _load_active_unit_ids(self) -> set[str]:
        unit_ids: set[str] = set()
        if not self.config.active_dir.exists():
            return unit_ids
        for yaml_path in self.config.active_dir.rglob("*.yaml"):
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict) and data.get("unit_id"):
                unit_ids.add(str(data["unit_id"]))
        return unit_ids

    def _run_script(self, script_name: str, args: list[str]) -> Dict[str, Any]:
        script_path = self.config.scripts_dir / script_name
        cmd = [str(script_path)] + args
        env = os.environ.copy()
        env["FORGE_ROOT"] = str(self.config.forge_root)
        env["FORGE_PROJECT_ROOT"] = str(self.config.project_root)
        started = time.time()
        proc = subprocess.run(
            cmd,
            cwd=str(self.config.forge_root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "script": script_name,
            "command": cmd,
            "returncode": proc.returncode,
            "duration_sec": round(time.time() - started, 3),
            "stdout_tail": "\n".join(proc.stdout.strip().splitlines()[-12:]),
            "stderr_tail": "\n".join(proc.stderr.strip().splitlines()[-12:]),
        }

    def _run_auto_verify_and_remediate(
        self,
        *,
        cycle_id: str,
        reason: str,
        changed_files: list[str],
    ) -> Dict[str, Any]:
        enabled = os.environ.get("FORGE_WARDEN_AUTO_VERIFY", "true").strip().lower() == "true"
        if not enabled:
            return {
                "state": "verify_disabled",
                "verify": {"status": "skipped", "reason": "FORGE_WARDEN_AUTO_VERIFY=false"},
                "remediation": {},
                "queue_item": {},
            }

        patch_result = self._build_patch_from_changed_files(changed_files)
        if not patch_result.get("ok"):
            return {
                "state": "verify_error",
                "verify": {
                    "status": "error",
                    "reason": patch_result.get("error", "Unable to build diff"),
                },
                "remediation": {},
                "queue_item": {},
            }

        diff_text = str(patch_result.get("diff_text", "")).strip()
        if not diff_text:
            return {
                "state": "verify_skipped_no_diff",
                "verify": {
                    "status": "skipped",
                    "reason": patch_result.get("summary", "No qualifying text diff detected."),
                    "changed_files": patch_result.get("changed_files", []),
                },
                "remediation": {},
                "queue_item": {},
            }

        domain = os.environ.get("FORGE_WARDEN_VERIFY_DOMAIN", "system_operations")
        summary = patch_result.get("summary") or (
            f"Warden auto verify ({reason}) [{len(patch_result.get('changed_files', []))} files]"
        )
        verify = self._run_azul_verify(diff_text=diff_text, summary=str(summary), domain=domain)
        ticket = verify.get("ticket") or {}
        status = str(ticket.get("status", "")).upper()
        verdict = str(ticket.get("verdict", "")).lower()
        state = "verify_done"
        remediation: Dict[str, Any] = {}
        queue_item: Dict[str, Any] = {}

        if status == "REJECTED":
            state = "remediation_started"
            self._append_event(
                "remediation_start",
                "Auto-remediation loop started after rejected verify",
                {
                    "cycle_id": cycle_id,
                    "ticket_id": ticket.get("ticket_id", ""),
                    "verdict_reason": ticket.get("verdict_reason", ""),
                },
            )
            remediation = self._run_remediation_loop(
                intent=f"Fix governance rejection for changed files: {', '.join(patch_result.get('changed_files', [])[:8])}",
                domain=domain,
                initial_patch=diff_text,
                initial_verdict_reason=str(ticket.get("verdict_reason", "")),
            )
            final_verify = remediation.get("final_verify") or {}
            final_ticket = final_verify.get("ticket") or {}
            final_status = str(final_ticket.get("status", "")).upper()
            final_verdict = str(final_ticket.get("verdict", "")).lower()
            if final_status in {"COMPLETED", "WARNED"} and final_verdict == "pass":
                queue_item = self._enqueue_remediation_for_human_review(
                    cycle_id=cycle_id,
                    source_reason=reason,
                    initial_verify=verify,
                    remediation=remediation,
                    domain=domain,
                    changed_files=patch_result.get("changed_files", []),
                )
                state = "remediation_ready_for_human_review"
                self._append_event(
                    "remediation_ready",
                    "Remediated patch passed Azul and is ready for human final review",
                    {"cycle_id": cycle_id, "queue_item_id": queue_item.get("id", "")},
                )
            else:
                state = "remediation_unresolved"
        elif status in {"COMPLETED", "WARNED"} and verdict == "pass":
            state = "verify_passed"

        return {
            "state": state,
            "verify": {
                **verify,
                "changed_files": patch_result.get("changed_files", []),
            },
            "remediation": remediation,
            "queue_item": queue_item,
        }

    def _run_remediation_loop(
        self,
        *,
        intent: str,
        domain: str,
        initial_patch: str,
        initial_verdict_reason: str,
    ) -> Dict[str, Any]:
        system_catalog = self._load_json(self.config.system_catalog_path)
        danger_map = self._load_json(self.config.danger_map_path)

        def _verify_fn(diff_text: str, attempt_summary: str, _attempt_no: int) -> Dict[str, Any]:
            return self._run_azul_verify(
                diff_text=diff_text,
                summary=attempt_summary,
                domain=domain,
            )

        max_attempts = int(os.environ.get("FORGE_WARDEN_REMEDIATE_MAX_ATTEMPTS", "3"))
        return self.remediator.remediate_reject_loop(
            intent=intent,
            domain=domain,
            initial_patch=initial_patch,
            system_catalog=system_catalog,
            danger_map=danger_map,
            verify_fn=_verify_fn,
            max_attempts=max(1, min(5, max_attempts)),
            summary_prefix="Warden remediation",
            start_from_reject=True,
            initial_verdict_reason=initial_verdict_reason,
        )

    def _run_azul_verify(self, *, diff_text: str, summary: str, domain: str) -> Dict[str, Any]:
        self.config.verify_inputs_dir.mkdir(parents=True, exist_ok=True)
        diff_path = self.config.verify_inputs_dir / f"warden-{uuid.uuid4().hex[:12]}.patch"
        diff_path.write_text(diff_text, encoding="utf-8")

        cmd = [
            str(self.config.scripts_dir / "azul-verify"),
            "--domain",
            domain,
            "--diff",
            str(diff_path),
            "--summary",
            summary,
        ]
        env = os.environ.copy()
        env["FORGE_ROOT"] = str(self.config.forge_root)
        started = time.time()
        proc = subprocess.run(
            cmd,
            cwd=str(self.config.forge_root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        duration = round(time.time() - started, 3)
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        ticket_id = self._extract_ticket_id(output)
        ticket, ticket_path = self._load_ticket_by_id(ticket_id)
        if not ticket:
            ticket, ticket_path = self._load_latest_ticket()

        return {
            "script": "azul-verify",
            "command": cmd,
            "returncode": proc.returncode,
            "duration_sec": duration,
            "ticket_id": ticket_id or str(ticket.get("ticket_id", "")),
            "ticket": ticket,
            "ticket_path": ticket_path,
            "output_tail": "\n".join(output.strip().splitlines()[-24:]),
            "diff_path": str(diff_path),
        }

    def _requeue_stuck_tickets_on_startup(self) -> Dict[str, Any]:
        """
        Requeue tickets stuck in PROVISIONING/EVALUATING from previous runs.
        This keeps verification durable across daemon restarts.
        """
        active_dir = _azul_data_dir(self.config.forge_root) / "tickets" / "active"
        completed_dir = _azul_data_dir(self.config.forge_root) / "tickets" / "completed"
        completed_dir.mkdir(parents=True, exist_ok=True)

        processed: list[Dict[str, Any]] = []
        if not active_dir.exists():
            return {"requeued_count": 0, "items": processed}

        for path in sorted(active_dir.glob("azul-*.json")):
            ticket = self._load_json(path)
            if not ticket:
                continue

            status = str(ticket.get("status", "")).upper()
            if status not in {"PROVISIONING", "EVALUATING"}:
                continue

            ticket_id = str(ticket.get("ticket_id", path.stem))
            payload = ticket.get("change_payload") if isinstance(ticket.get("change_payload"), dict) else {}
            diff_text = str(payload.get("diff", "")).strip()
            domain = str(ticket.get("domain", os.environ.get("FORGE_WARDEN_VERIFY_DOMAIN", "system_operations")))
            summary = str(ticket.get("change_summary", "") or f"Warden startup requeue for {ticket_id}")

            if not diff_text:
                ticket["status"] = "FAILED"
                ticket["verdict"] = None
                ticket["verdict_reason"] = (
                    "Fail-closed: startup reconciliation found stuck ticket with no diff payload."
                )
                ticket["completed_at"] = _now_iso()
                ticket["updated_at"] = _now_iso()
                metadata = ticket.get("metadata") if isinstance(ticket.get("metadata"), dict) else {}
                metadata["manual_review_required"] = True
                metadata["manual_review_reason"] = "startup_requeue_missing_diff"
                metadata["requeue_attempted_at"] = _now_iso()
                ticket["metadata"] = metadata
                (completed_dir / path.name).write_text(json.dumps(ticket, indent=2), encoding="utf-8")
                path.unlink(missing_ok=True)
                processed.append(
                    {
                        "ticket_id": ticket_id,
                        "from_status": status,
                        "action": "failed_closed_missing_diff",
                    }
                )
                continue

            verify = self._run_azul_verify(
                diff_text=diff_text,
                summary=f"{summary} [startup-requeue]",
                domain=domain,
            )
            new_ticket_id = str((verify.get("ticket") or {}).get("ticket_id", ""))

            ticket["status"] = "FAILED"
            ticket["verdict"] = None
            ticket["verdict_reason"] = (
                "Fail-closed: ticket was stuck in "
                f"{status}; requeued as {new_ticket_id or 'new ticket'} on daemon startup."
            )
            ticket["completed_at"] = _now_iso()
            ticket["updated_at"] = _now_iso()
            metadata = ticket.get("metadata") if isinstance(ticket.get("metadata"), dict) else {}
            metadata["manual_review_required"] = True
            metadata["manual_review_reason"] = "startup_requeue"
            metadata["requeue_attempted_at"] = _now_iso()
            metadata["requeued_ticket_id"] = new_ticket_id
            ticket["metadata"] = metadata

            (completed_dir / path.name).write_text(json.dumps(ticket, indent=2), encoding="utf-8")
            path.unlink(missing_ok=True)
            processed.append(
                {
                    "ticket_id": ticket_id,
                    "from_status": status,
                    "requeued_ticket_id": new_ticket_id,
                    "requeue_returncode": int(verify.get("returncode", 1)),
                }
            )

        if processed:
            self._append_event(
                "startup_requeue",
                "Startup reconciliation requeued stuck Azul tickets",
                {"count": len(processed), "items": processed},
            )

        return {"requeued_count": len(processed), "items": processed}

    @staticmethod
    def _extract_ticket_id(output: str) -> str:
        match = re.search(r"Ticket:\s*(azul-[a-z0-9]+)", output, flags=re.IGNORECASE)
        if not match:
            return ""
        return match.group(1)

    def _load_ticket_by_id(self, ticket_id: str) -> tuple[Dict[str, Any], str]:
        if not ticket_id:
            return {}, ""
        base = _azul_data_dir(self.config.forge_root) / "tickets"
        for folder in ("completed", "active"):
            path = base / folder / f"{ticket_id}.json"
            if path.exists():
                return self._load_json(path), str(path)
        return {}, ""

    def _load_latest_ticket(self) -> tuple[Dict[str, Any], str]:
        completed = _azul_data_dir(self.config.forge_root) / "tickets" / "completed"
        if not completed.exists():
            return {}, ""
        files = sorted(completed.glob("azul-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return {}, ""
        return self._load_json(files[0]), str(files[0])

    def _snapshot_workspace(self) -> Dict[str, Path]:
        slug = _slug(self.config.project_root.name or "project")
        digest = hashlib.sha256(str(self.config.project_root).encode("utf-8")).hexdigest()[:12]
        root = self.config.state_dir / "project_snapshots" / f"{slug}-{digest}"
        return {
            "root": root,
            "files": root / "files",
            "marker": root / ".initialized",
        }

    def _is_text_candidate(self, path: Path) -> bool:
        return path.suffix.lower() in _SNAPSHOT_INCLUDE_EXTENSIONS or path.suffix == ""

    @staticmethod
    def _read_text_file(path: Path) -> str | None:
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        if len(raw) > _SNAPSHOT_MAX_FILE_BYTES:
            return None
        if b"\x00" in raw:
            return None
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def _initialize_snapshot_baseline(self) -> None:
        ws = self._snapshot_workspace()
        ws["files"].mkdir(parents=True, exist_ok=True)
        if ws["marker"].exists():
            return
        for rel in sorted(self._collect_file_state().keys()):
            src = self.config.project_root / rel
            dest = ws["files"] / rel
            if not src.exists() or not src.is_file():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dest)
            except OSError:
                continue
        ws["marker"].write_text(_now_iso(), encoding="utf-8")

    def _sync_snapshot_files(self, rel_paths: list[str]) -> None:
        ws = self._snapshot_workspace()
        ws["files"].mkdir(parents=True, exist_ok=True)
        for rel in rel_paths:
            src = self.config.project_root / rel
            dest = ws["files"] / rel
            if src.exists() and src.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(src, dest)
                except OSError:
                    continue
            else:
                try:
                    dest.unlink()
                except FileNotFoundError:
                    pass

    def _build_patch_from_changed_files(self, changed_files: list[str]) -> Dict[str, Any]:
        self._initialize_snapshot_baseline()
        if not changed_files:
            return {
                "ok": True,
                "diff_text": "",
                "changed_files": [],
                "summary": "No changed files detected for auto-verify.",
            }

        ws = self._snapshot_workspace()
        files_root = ws["files"]
        changed = sorted(dict.fromkeys(changed_files))
        patch_parts: list[str] = []
        patched_files: list[str] = []

        for rel in changed:
            old_path = files_root / rel
            new_path = self.config.project_root / rel
            old_exists = old_path.exists() and old_path.is_file()
            new_exists = new_path.exists() and new_path.is_file()
            if not old_exists and not new_exists:
                continue

            use_text = False
            if old_exists and self._is_text_candidate(old_path):
                use_text = True
            if new_exists and self._is_text_candidate(new_path):
                use_text = True
            if not use_text:
                continue

            old_text = self._read_text_file(old_path) if old_exists else ""
            new_text = self._read_text_file(new_path) if new_exists else ""
            if old_text is None or new_text is None:
                continue
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
                    patched_files.append(rel)

        self._sync_snapshot_files(changed)

        if not patch_parts:
            return {
                "ok": True,
                "diff_text": "",
                "changed_files": patched_files,
                "summary": "Changed files detected, but no qualifying textual diff for verify.",
            }

        return {
            "ok": True,
            "diff_text": "\n\n".join(patch_parts).strip() + "\n",
            "changed_files": patched_files,
            "summary": (
                f"Warden auto verify: {len(patched_files)} changed file(s) in "
                f"{self.config.project_root.name}"
            ),
        }

    def _enqueue_remediation_for_human_review(
        self,
        *,
        cycle_id: str,
        source_reason: str,
        initial_verify: Dict[str, Any],
        remediation: Dict[str, Any],
        domain: str,
        changed_files: list[str],
    ) -> Dict[str, Any]:
        queue_id = f"remediation-{uuid.uuid4().hex[:10]}"
        patch_text = str(remediation.get("final_patch") or "").strip()
        if not patch_text:
            return {}

        patch_path = self.config.remediation_desk_patches_dir / f"{queue_id}.patch"
        patch_path.write_text(patch_text + "\n", encoding="utf-8")
        record = {
            "id": queue_id,
            "status": "ready_for_human_review",
            "created_at": _now_iso(),
            "project_id": self.config.project_id,
            "project_root": str(self.config.project_root),
            "cycle_id": cycle_id,
            "cycle_reason": source_reason,
            "domain": domain,
            "changed_files": changed_files[:100],
            "initial_ticket_id": str((initial_verify.get("ticket") or {}).get("ticket_id", "")),
            "initial_verdict_reason": str(
                (initial_verify.get("ticket") or {}).get("verdict_reason", "")
            ),
            "final_ticket_id": str(
                ((remediation.get("final_verify") or {}).get("ticket") or {}).get("ticket_id", "")
            ),
            "final_ticket_status": str(
                ((remediation.get("final_verify") or {}).get("ticket") or {}).get("status", "")
            ),
            "final_verdict": str(
                ((remediation.get("final_verify") or {}).get("ticket") or {}).get("verdict", "")
            ),
            "attempt_count": len(remediation.get("attempts") or []),
            "requires_human_final_review": True,
            "auto_apply_performed": False,
            "patch_path": str(patch_path),
            "metadata": {
                "source": "warden.auto_remediation",
                "note": (
                    "Remediation patch passed Azul gate and is queued for human final "
                    "review. The daemon never auto-applies fixes to PROJECT_ROOT."
                ),
            },
        }
        record_path = self.config.remediation_desk_pending_dir / f"{queue_id}.json"
        record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return {
            "id": queue_id,
            "status": record["status"],
            "record_path": str(record_path),
            "patch_path": str(patch_path),
            "attempt_count": record["attempt_count"],
            "final_ticket_id": record["final_ticket_id"],
        }

    @staticmethod
    def _load_json(path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        return data

    def _collect_file_state(self) -> Dict[str, tuple[int, int]]:
        ignore_roots = {
            str((self.config.project_root / ".git").resolve()),
            str((self.config.project_root / "__pycache__").resolve()),
            str((self.config.project_root / ".venv").resolve()),
            str(_azul_data_dir(self.config.forge_root)),
            str((self.config.forge_root / "DAWN" / "projects").resolve()),
            str((self.config.forge_root / "action_catalogs" / "stubs").resolve()),
            str((self.config.forge_root / "action_catalogs" / "active").resolve()),
            str((self.config.forge_root / "forge_output").resolve()),
            str(self.config.state_dir.resolve()),
        }

        snapshot: Dict[str, tuple[int, int]] = {}
        for path in self.config.project_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in _WATCH_EXTENSIONS:
                continue
            resolved = str(path.resolve())
            if any(resolved.startswith(prefix) for prefix in ignore_roots):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            snapshot[str(path.relative_to(self.config.project_root))] = (
                stat.st_mtime_ns,
                stat.st_size,
            )
        return snapshot

    @staticmethod
    def _detect_changes(
        old: Dict[str, tuple[int, int]],
        new: Dict[str, tuple[int, int]],
    ) -> list[str]:
        changed: list[str] = []
        all_keys = set(old) | set(new)
        for key in sorted(all_keys):
            if old.get(key) != new.get(key):
                changed.append(key)
        return changed

    def _stage_dawn_inputs(self, changed_files: list[str]) -> None:
        """Ensure DAWN project inputs path exists and contains current watched files."""
        inputs_dir = (
            self.config.forge_root / "DAWN" / "projects" / self.config.project_id / "inputs"
        )
        inputs_dir.mkdir(parents=True, exist_ok=True)

        marker = inputs_dir / ".warden_project_root"
        marker.write_text(str(self.config.project_root), encoding="utf-8")

        candidates = changed_files
        if not candidates:
            candidates = list(self._collect_file_state().keys())

        copied = 0
        for relative in candidates:
            src = self.config.project_root / relative
            if not src.exists() or not src.is_file():
                continue
            dest = inputs_dir / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dest)
                copied += 1
            except OSError:
                continue

        if copied == 0:
            placeholder = inputs_dir / "README.md"
            if not placeholder.exists():
                placeholder.write_text(
                    "Warden-managed DAWN input staging placeholder.\n",
                    encoding="utf-8",
                )

    def _update_status(self, **fields: Any) -> None:
        base = {
            "running": False,
            "phase": "idle",
            "pid": os.getpid(),
            "project_root": str(self.config.project_root),
            "project_id": self.config.project_id,
            "forge_root": str(self.config.forge_root),
            "updated_at": _now_iso(),
        }
        base.update(self._status)
        base.update(fields)
        base["updated_at"] = _now_iso()
        self._status = base
        self.config.status_path.write_text(json.dumps(base, indent=2), encoding="utf-8")

    def _append_event(self, event_type: str, message: str, details: Dict[str, Any]) -> None:
        event = {
            "ts": _now_iso(),
            "event_type": event_type,
            "message": message,
            "details": details,
        }
        with self.config.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

    def _write_pid(self) -> None:
        self.config.pid_path.write_text(str(os.getpid()), encoding="utf-8")

    def _remove_pid(self) -> None:
        try:
            self.config.pid_path.unlink()
        except FileNotFoundError:
            pass


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def load_runtime_status(forge_root: Optional[Path] = None) -> Dict[str, Any]:
    root = (forge_root or default_forge_root()).resolve()
    path = root / "warden" / "state" / "warden_status.json"
    if not path.exists():
        return {
            "running": False,
            "phase": "stopped",
            "project_root": "",
            "project_id": "",
            "updated_at": "",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"running": False, "phase": "error", "updated_at": _now_iso()}
    pid = int(data.get("pid", 0) or 0)
    if data.get("running") and pid and not _pid_is_running(pid):
        data["running"] = False
        data["phase"] = "stopped"
    return data


def start_daemon_process(
    *,
    forge_root: Path,
    project_root: Path,
    project_id: str,
    poll_interval: float = 5.0,
    debounce: float = 2.0,
    run_on_start: bool = True,
    env_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    status = load_runtime_status(forge_root=forge_root)
    if status.get("running"):
        return {"status": "ok", "message": "already running", "pid": status.get("pid")}

    state_dir = forge_root / "warden" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / "warden.log"
    log_handle = log_path.open("a", encoding="utf-8")

    env = os.environ.copy()
    env["FORGE_ROOT"] = str(forge_root)
    if env_overrides:
        env.update(env_overrides)

    cmd = [
        sys.executable,
        "-m",
        "warden.daemon",
        "run",
        "--forge-root",
        str(forge_root),
        "--project-root",
        str(project_root),
        "--project-id",
        project_id,
        "--poll-interval",
        str(poll_interval),
        "--debounce",
        str(debounce),
    ]
    if not run_on_start:
        cmd.append("--no-run-on-start")
    proc = subprocess.Popen(  # noqa: S603,S607 - internal command
        cmd,
        cwd=str(forge_root),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return {"status": "ok", "message": "started", "pid": proc.pid}


def stop_daemon_process(*, forge_root: Path) -> Dict[str, Any]:
    root = forge_root.resolve()
    pid_path = root / "warden" / "state" / "warden.pid"
    if not pid_path.exists():
        return {"status": "ok", "message": "not running"}
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except ValueError:
        pid_path.unlink(missing_ok=True)
        return {"status": "error", "message": "invalid pid file"}

    if not _pid_is_running(pid):
        pid_path.unlink(missing_ok=True)
        return {"status": "ok", "message": "not running"}

    os.kill(pid, signal.SIGTERM)
    for _ in range(40):
        if not _pid_is_running(pid):
            break
        time.sleep(0.1)
    if _pid_is_running(pid):
        os.kill(pid, signal.SIGKILL)
    pid_path.unlink(missing_ok=True)
    return {"status": "ok", "message": "stopped", "pid": pid}


def _print_json(data: Dict[str, Any]) -> None:
    print(json.dumps(data, indent=2))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Federation Warden daemon")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--forge-root", default=str(default_forge_root()))
        p.add_argument("--project-root", default=str(default_forge_root()))
        p.add_argument("--project-id", default="")
        p.add_argument("--poll-interval", type=float, default=5.0)
        p.add_argument("--debounce", type=float, default=2.0)
        p.add_argument("--no-run-on-start", action="store_true")

    p_run = sub.add_parser("run", help="Run daemon in foreground")
    add_common_flags(p_run)

    p_once = sub.add_parser("once", help="Run one scan/assess cycle")
    add_common_flags(p_once)

    p_start = sub.add_parser("start", help="Start daemon as background process")
    add_common_flags(p_start)

    p_stop = sub.add_parser("stop", help="Stop background daemon")
    p_stop.add_argument("--forge-root", default=str(default_forge_root()))

    p_status = sub.add_parser("status", help="Print daemon status")
    p_status.add_argument("--forge-root", default=str(default_forge_root()))

    p_rem_status = sub.add_parser(
        "remediation-status",
        help="List remediation desk queue items",
    )
    p_rem_status.add_argument("--forge-root", default=str(default_forge_root()))
    p_rem_status.add_argument("--include-reviewed", action="store_true")
    p_rem_status.add_argument("--limit", type=int, default=100)

    p_rem_review = sub.add_parser(
        "remediation-review",
        help="Mark a remediation desk item as reviewed",
    )
    p_rem_review.add_argument("item_id")
    p_rem_review.add_argument("--forge-root", default=str(default_forge_root()))

    p_approve = sub.add_parser("approve", help="Move stub to active by filename")
    p_approve.add_argument("filename")
    p_approve.add_argument("--forge-root", default=str(default_forge_root()))

    return parser


def approve_stub_file(*, forge_root: Path, filename: str) -> Dict[str, Any]:
    stubs_dir = forge_root / "action_catalogs" / "stubs"
    active_dir = forge_root / "action_catalogs" / "active"
    src = stubs_dir / filename
    dst = active_dir / filename
    if not src.exists():
        return {"status": "error", "message": f"stub not found: {src}"}
    active_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = _snapshot_contract_baseline(forge_root=forge_root, contract_path=src)
    shutil.move(str(src), str(dst))
    try:
        try:
            from azul.loop.gold_labels import GoldLabelStore
        except ModuleNotFoundError:
            candidates = [
                forge_root / "Azul",
                Path(__file__).resolve().parents[1] / "Azul",
            ]
            for azul_pkg_root in candidates:
                if not azul_pkg_root.exists():
                    continue
                if str(azul_pkg_root) not in sys.path:
                    sys.path.insert(0, str(azul_pkg_root))
            from azul.loop.gold_labels import GoldLabelStore

        reviewer = os.environ.get("FORGE_REVIEWER_ID", os.environ.get("USER", "lead_architect"))
        store = GoldLabelStore()
        store.record_contract_approval(
            baseline_contract_path=baseline_path,
            approved_contract_path=dst,
            reviewer_id=reviewer,
            metadata={"source": "warden.approve_stub_file"},
        )
    except Exception:
        # Approval path must not fail because loop logging failed.
        pass
    return {"status": "ok", "message": "approved", "path": str(dst)}


def list_remediation_queue(
    *,
    forge_root: Path,
    include_reviewed: bool = False,
    limit: int = 100,
) -> Dict[str, Any]:
    data_root = _azul_data_dir(forge_root) / "remediation_desk"
    pending_dir = data_root / "pending"
    reviewed_dir = data_root / "reviewed"

    pending: list[Dict[str, Any]] = []
    reviewed: list[Dict[str, Any]] = []
    if pending_dir.exists():
        for path in sorted(
            pending_dir.glob("remediation-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[: max(1, limit)]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {}
            pending.append(
                {
                    "id": str(data.get("id", path.stem)),
                    "status": str(data.get("status", "ready_for_human_review")),
                    "created_at": str(data.get("created_at", "")),
                    "project_id": str(data.get("project_id", "")),
                    "domain": str(data.get("domain", "")),
                    "attempt_count": int(data.get("attempt_count", 0) or 0),
                    "final_ticket_id": str(data.get("final_ticket_id", "")),
                    "record_path": str(path),
                    "patch_path": str(data.get("patch_path", "")),
                }
            )

    if include_reviewed and reviewed_dir.exists():
        for path in sorted(
            reviewed_dir.glob("remediation-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[: max(1, limit)]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {}
            reviewed.append(
                {
                    "id": str(data.get("id", path.stem)),
                    "status": str(data.get("status", "reviewed")),
                    "created_at": str(data.get("created_at", "")),
                    "reviewed_at": str(data.get("reviewed_at", "")),
                    "project_id": str(data.get("project_id", "")),
                    "domain": str(data.get("domain", "")),
                    "attempt_count": int(data.get("attempt_count", 0) or 0),
                    "final_ticket_id": str(data.get("final_ticket_id", "")),
                    "record_path": str(path),
                    "patch_path": str(data.get("patch_path", "")),
                }
            )

    return {
        "status": "ok",
        "forge_root": str(forge_root.resolve()),
        "data_root": str(data_root),
        "pending_count": len(pending),
        "reviewed_count": len(reviewed),
        "pending": pending,
        "reviewed": reviewed,
    }


def review_remediation_item(*, forge_root: Path, item_id: str) -> Dict[str, Any]:
    data_root = _azul_data_dir(forge_root) / "remediation_desk"
    pending_dir = data_root / "pending"
    reviewed_dir = data_root / "reviewed"
    clean_id = item_id.strip()
    clean_id = clean_id[:-5] if clean_id.endswith(".json") else clean_id

    src = pending_dir / f"{clean_id}.json"
    if not src.exists():
        return {"status": "error", "message": f"remediation item not found: {src}"}
    reviewed_dir.mkdir(parents=True, exist_ok=True)
    dst = reviewed_dir / src.name

    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}

    data["id"] = str(data.get("id", clean_id))
    data["status"] = "reviewed"
    data["reviewed_at"] = _now_iso()
    data["reviewer"] = os.environ.get("FORGE_REVIEWER_ID", os.environ.get("USER", "lead_architect"))

    dst.write_text(json.dumps(data, indent=2), encoding="utf-8")
    src.unlink(missing_ok=True)
    return {"status": "ok", "message": "reviewed", "path": str(dst), "id": data["id"]}


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "status":
        _print_json(load_runtime_status(forge_root=Path(args.forge_root)))
        return 0

    if args.command == "stop":
        _print_json(stop_daemon_process(forge_root=Path(args.forge_root)))
        return 0

    if args.command == "remediation-status":
        _print_json(
            list_remediation_queue(
                forge_root=Path(args.forge_root),
                include_reviewed=bool(args.include_reviewed),
                limit=int(args.limit),
            )
        )
        return 0

    if args.command == "remediation-review":
        _print_json(
            review_remediation_item(
                forge_root=Path(args.forge_root),
                item_id=str(args.item_id),
            )
        )
        return 0

    if args.command == "approve":
        _print_json(
            approve_stub_file(forge_root=Path(args.forge_root), filename=args.filename)
        )
        return 0

    config = WardenConfig.from_args(args)

    if args.command == "start":
        result = start_daemon_process(
            forge_root=config.forge_root,
            project_root=config.project_root,
            project_id=config.project_id,
            poll_interval=config.poll_interval_sec,
            debounce=config.debounce_sec,
            run_on_start=config.run_on_start,
        )
        _print_json(result)
        return 0

    daemon = FederationWarden(config=config)
    if args.command == "once":
        daemon.run_cycle(reason="manual_once", changed_files=[])
        _print_json(load_runtime_status(forge_root=config.forge_root))
        return 0
    return daemon.run_forever()


if __name__ == "__main__":
    raise SystemExit(main())
