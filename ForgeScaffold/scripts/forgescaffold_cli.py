#!/usr/bin/env python3
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


CLI_VERSION = "1.0"

EXIT_SUCCESS = 0
EXIT_SUCCESS_WARN = 10
EXIT_USER_INPUT = 20
EXIT_POLICY_BLOCKED = 30
EXIT_APPROVAL_REQUIRED = 31
EXIT_LOCK_HELD = 32
EXIT_PIPELINE_FAILED = 40
EXIT_INTEGRITY_FAILED = 50
EXIT_INTERNAL_ERROR = 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _project_root(project: str) -> Path:
    return _repo_root() / "projects" / project


def _load_policy(project_root: Path) -> Dict[str, Any]:
    repo_root = _repo_root()
    policy_path = repo_root / "dawn" / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        policy_path = project_root / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        return {}
    return yaml.safe_load(policy_path.read_text()) or {}


def _cli_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    return (policy.get("forgescaffold") or {}).get("cli") or {}


def _profile_name(args: argparse.Namespace, policy: Dict[str, Any]) -> str:
    if args.profile:
        return args.profile
    return policy.get("default_profile") or "normal"


def _mode_name(args: argparse.Namespace, policy: Dict[str, Any]) -> str:
    if args.mode:
        return args.mode
    cli_policy = _cli_policy(policy)
    return cli_policy.get("default_mode") or "runnable_only"


def _default_pipeline(mode: str) -> str:
    repo_root = _repo_root()
    if mode == "strict":
        return str(repo_root / "dawn" / "pipelines" / "forgescaffold_apply_v9_cache.yaml")
    return str(repo_root / "dawn" / "pipelines" / "forgescaffold_apply_v9_cache_runnable.yaml")


def _redact_path(path: str, policy: Dict[str, Any], project_root: Path) -> str:
    cli_policy = _cli_policy(policy)
    if not cli_policy.get("redact_paths_in_human_output", True):
        return path
    try:
        repo_root = _repo_root()
        rel = Path(path).resolve().relative_to(repo_root)
        return str(rel)
    except Exception:
        try:
            rel = Path(path).resolve().relative_to(project_root)
            return str(rel)
        except Exception:
            return Path(path).name


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(payload, fh, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r") as fh:
        return json.load(fh)


def _artifact_dir(project_root: Path) -> Path:
    return project_root / "artifacts" / "forgescaffold.cli"


def _artifact_path(project_root: Path, name: str, out_override: Optional[str]) -> Path:
    if out_override:
        return Path(out_override)
    return _artifact_dir(project_root) / name


def _print_lines(lines: List[str], quiet: bool) -> None:
    if quiet:
        if lines:
            print(lines[-1])
        return
    for line in lines:
        print(line)


def _human_output(
    project: str,
    mode: str,
    profile: str,
    command: str,
    pipeline: Optional[str],
    status: str,
    code: str,
    details: str,
    artifacts: Dict[str, str],
    next_steps: Optional[List[str]],
    verbose_lines: Optional[List[str]],
    policy: Dict[str, Any],
    project_root: Path,
    quiet: bool,
    suppress: bool,
) -> None:
    if suppress:
        return
    lines = []
    lines.append(f"ForgeScaffold CLI v{CLI_VERSION}  project={project}  mode={mode}  profile={profile}")
    lines.append(f"Action: {command}  pipeline={pipeline or 'N/A'}")
    lines.append(f"Result: {status}  code={code}  details=\"{details}\"")
    if next_steps:
        for step in next_steps:
            lines.append(f"Next: {step}")
    if artifacts:
        lines.append("Artifacts:")
        for key, value in artifacts.items():
            lines.append(f"  {key}: {_redact_path(value, policy, project_root)}")
    if verbose_lines:
        lines.extend(verbose_lines)
    _print_lines(lines, quiet)


def _common_fields(
    project: str,
    command: str,
    mode: str,
    profile: str,
    pipeline_name: Optional[str],
    status: str,
    primary_code: str,
    error_codes: List[str],
) -> Dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "project": project,
        "command": command,
        "mode": mode,
        "profile": profile,
        "pipeline_name": pipeline_name,
        "status": status,
        "primary_code": primary_code,
        "error_codes": error_codes,
        "created_at": _now_iso(),
    }


def _exit_code(status: str, code: str, mode: str) -> int:
    if status == "PASS":
        return EXIT_SUCCESS
    if status == "WARN":
        return EXIT_SUCCESS_WARN
    if status == "BLOCKED":
        if code in {"LOCK_HELD", "LOCK_INVALID"}:
            return EXIT_LOCK_HELD
        if code in {"APPROVAL_REQUIRED", "APPROVAL_INVALID", "RISK_ACK_REQUIRED", "APPROVAL_COUNT_INSUFFICIENT", "APPROVAL_REPLAY_DETECTED"}:
            return EXIT_APPROVAL_REQUIRED
        if code in {"TICKET_REQUIRED", "TICKET_ID_INVALID", "HIGH_RISK_BLOCKED"}:
            return EXIT_POLICY_BLOCKED
        return EXIT_POLICY_BLOCKED
    if status == "FAIL":
        if code in {"INDEX_INTEGRITY_FAIL", "ENTRY_HASH_MISMATCH", "SIGNATURE_INVALID", "TRUST_SCOPE_VIOLATION", "CACHE_INTEGRITY_FAIL", "CHECKPOINT_VERIFY_FAIL"}:
            return EXIT_INTEGRITY_FAILED
        if code in {"PIPELINE_FAILED", "STATUS_LINK_FAIL", "QUERY_FAILED"}:
            return EXIT_PIPELINE_FAILED
        if code in {"USER_INPUT_ERROR", "POLICY_PARSE_FAIL"}:
            return EXIT_USER_INPUT
        return EXIT_INTERNAL_ERROR
    return EXIT_INTERNAL_ERROR


def _run_orchestrator(project: str, pipeline_path: str, profile: Optional[str], suppress_output: bool = False) -> None:
    repo_root = _repo_root()
    sys.path.insert(0, str(repo_root))
    from dawn.runtime.orchestrator import Orchestrator

    links_dirs = [str(repo_root / "dawn" / "links")]
    orchestrator = Orchestrator(links_dirs, str(repo_root / "projects"))
    if suppress_output:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            orchestrator.run_pipeline(project, pipeline_path, profile=profile)
    else:
        orchestrator.run_pipeline(project, pipeline_path, profile=profile)


def _run_single_link(
    project: str,
    link_id: str,
    config: Optional[Dict[str, Any]],
    profile: Optional[str],
    suppress_output: bool = False,
) -> None:
    nonce = _now_iso().replace(":", "").replace("-", "")
    pipeline = {
        "pipelineId": f"cli_{link_id.replace('.', '_')}_{nonce}",
        "links": [{"id": link_id, "config": config or {}}],
    }
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as fh:
        yaml.safe_dump(pipeline, fh)
        path = fh.name
    _run_orchestrator(project, path, profile, suppress_output=suppress_output)


def _read_artifact_index(project_root: Path) -> Dict[str, Any]:
    index_path = project_root / "artifact_index.json"
    if not index_path.exists():
        return {}
    return _load_json(index_path)


def _artifact_path_from_index(project_root: Path, artifact_id: str) -> Optional[str]:
    index = _read_artifact_index(project_root)
    entry = index.get(artifact_id)
    if not entry:
        return None
    return entry.get("path")


def _load_artifact(project_root: Path, artifact_id: str) -> Optional[Dict[str, Any]]:
    path = _artifact_path_from_index(project_root, artifact_id)
    if not path:
        return None
    try:
        return _load_json(Path(path))
    except Exception:
        return None


def _cache_backend(project_root: Path) -> Tuple[str, Optional[str]]:
    index_path = project_root / "evidence" / "evidence_index.jsonl"
    cache_path = project_root / "evidence" / "cache" / "evidence_index_cache.sqlite"
    if not cache_path.exists():
        return "scan_jsonl", None
    try:
        import sqlite3

        conn = sqlite3.connect(str(cache_path))
        try:
            cur = conn.execute(
                "SELECT source_index_sha256, source_entry_count, source_last_entry_hash FROM cache_meta LIMIT 1"
            )
            row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return "scan_jsonl", None
        index_bytes = index_path.read_bytes() if index_path.exists() else b""
        import hashlib

        index_sha = hashlib.sha256(index_bytes).hexdigest()
        entries = index_path.read_text().splitlines() if index_path.exists() else []
        entry_count = len([line for line in entries if line.strip()])
        last_hash = None
        for line in reversed(entries):
            if line.strip():
                try:
                    last_hash = json.loads(line).get("entry_hash")
                except Exception:
                    last_hash = None
                break
        meta = {
            "source_index_sha256": row[0],
            "source_entry_count": row[1],
            "source_last_entry_hash": row[2],
        }
        if meta == {"source_index_sha256": index_sha, "source_entry_count": entry_count, "source_last_entry_hash": last_hash}:
            return "cache_sqlite", str(cache_path)
    except Exception:
        return "scan_jsonl", None
    return "scan_jsonl", None


def _latest_checkpoint(project_root: Path, policy: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    index_policy = (policy.get("forgescaffold") or {}).get("index_integrity") or {}
    if not index_policy.get("checkpoint_enabled", False):
        return None
    checkpoints_dir = project_root / index_policy.get("checkpoint_write_root", "evidence/checkpoints")
    if not checkpoints_dir.is_absolute() and str(index_policy.get("checkpoint_write_root", "")).startswith("projects/"):
        checkpoints_dir = _repo_root() / index_policy.get("checkpoint_write_root")
    if not checkpoints_dir.exists():
        return None
    files = [p for p in checkpoints_dir.glob("checkpoint_*.json") if not p.name.endswith(".signature.json")]
    if not files:
        return None
    latest = sorted(files)[-1]
    try:
        payload = _load_json(latest)
    except Exception:
        return None
    payload["_path"] = str(latest)
    return payload


def _ensure_dir(path: Path) -> Tuple[bool, Optional[str]]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        test = path / ".cli_write_test"
        test.write_text("ok")
        test.unlink()
        return True, None
    except Exception as exc:
        return False, str(exc)


def _pipeline_has_link(pipeline_path: str, link_id: str) -> bool:
    try:
        data = yaml.safe_load(Path(pipeline_path).read_text())
    except Exception:
        return False
    for link in data.get("links", []):
        if link.get("id") == link_id:
            return True
    return False


def _generate_approval_template(project: str, profile: str, suppress_output: bool = False) -> Optional[str]:
    repo_root = _repo_root()
    pipeline = {
        "pipelineId": f"cli_generate_approval_{datetime.now().timestamp()}",
        "links": [
            {"id": "ingest.project_bundle"},
            {"id": "forgescaffold.system_catalog"},
            {"id": "forgescaffold.map_dataflow"},
            {"id": "forgescaffold.obs_define_schema"},
            {"id": "forgescaffold.obs_instrument_patchset"},
            {"id": "forgescaffold.test_matrix"},
            {"id": "forgescaffold.generate_review_packet"},
            {"id": "forgescaffold.generate_approval_template"},
        ],
    }
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as fh:
        yaml.safe_dump(pipeline, fh)
        temp_path = fh.name
    _run_orchestrator(project, temp_path, profile, suppress_output=suppress_output)
    project_root = _project_root(project)
    return _artifact_path_from_index(project_root, "forgescaffold.approval_template.json")


def _write_apply_summary(project_root: Path, payload: Dict[str, Any], out_path: Path) -> None:
    _write_json(out_path, payload)


def cmd_status(args: argparse.Namespace) -> int:
    project = args.project
    project_root = _project_root(project)
    policy = _load_policy(project_root)
    profile = _profile_name(args, policy)
    mode = _mode_name(args, policy)
    cli_policy = _cli_policy(policy)
    limit = args.limit if args.limit is not None else int(cli_policy.get("status_default_limit", 10))

    try:
        _run_single_link(project, "forgescaffold.status", {"limit": limit}, profile, suppress_output=args.quiet or args.json)
        status_path = _artifact_path_from_index(project_root, "forgescaffold.status.json")
        if not status_path:
            raise RuntimeError("status artifact missing")
        status_payload = _load_json(Path(status_path))
    except Exception:
        status = "FAIL"
        code = "STATUS_LINK_FAIL"
        payload = _common_fields(project, "status", mode, profile, None, status, code, [code])
        out_path = _artifact_path(project_root, "status_cli.json", args.out)
        payload["status_path"] = None
        _write_json(out_path, payload)
        _human_output(
            project,
            mode,
            profile,
            "status",
            None,
            status,
            code,
            "Status link failed",
            {"status_cli": str(out_path)},
            None,
            None,
            policy,
            project_root,
            args.quiet, args.json,
        )
        if args.json:
            print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return _exit_code(status, code, mode)

    cache_backend, _ = _cache_backend(project_root)
    lock = status_payload.get("lock") or {}
    lock_present = lock.get("present")
    detail = "Lock present" if lock_present else "Lock clear"
    detail = f"{detail}; backend={cache_backend}"

    status = "PASS"
    code = "OK"
    payload = _common_fields(project, "status", mode, profile, None, status, code, [])
    payload["status_path"] = status_path
    payload["cache_backend"] = cache_backend
    out_path = _artifact_path(project_root, "status_cli.json", args.out)
    _write_json(out_path, payload)

    artifacts = {"status": status_path, "status_cli": str(out_path)}
    verbose_lines = None
    if args.verbose:
        verbose_lines = [
            f"timestamp={_now_iso()}",
            f"cache_backend={cache_backend}",
        ]
    _human_output(
        project,
        mode,
        profile,
        "status",
        None,
        status,
        code,
        detail,
        artifacts,
        None,
        verbose_lines,
        policy,
        project_root,
        args.quiet, args.json,
    )

    if args.json:
        print(Path(status_path).read_text())

    return _exit_code(status, code, mode)


def cmd_query(args: argparse.Namespace) -> int:
    project = args.project
    project_root = _project_root(project)
    policy = _load_policy(project_root)
    profile = _profile_name(args, policy)
    mode = _mode_name(args, policy)

    config = {
        "limit": args.limit,
        "patchset_id": args.patchset,
        "ticket_id": args.ticket,
        "status": args.status,
    }

    try:
        _run_single_link(project, "forgescaffold.query_evidence_index", config, profile, suppress_output=args.quiet or args.json)
        result_path = _artifact_path_from_index(project_root, "forgescaffold.evidence_query_results.json")
        if not result_path:
            raise RuntimeError("query results missing")
        results_payload = _load_json(Path(result_path))
    except Exception:
        status = "FAIL"
        code = "QUERY_FAILED"
        payload = _common_fields(project, "query", mode, profile, None, status, code, [code])
        out_path = _artifact_path(project_root, "query_results.json", args.out)
        payload["query_backend"] = None
        _write_json(out_path, payload)
        _human_output(
            project,
            mode,
            profile,
            "query",
            None,
            status,
            code,
            "Query failed",
            {"query_results": str(out_path)},
            None,
            None,
            policy,
            project_root,
            args.quiet, args.json,
        )
        if args.json:
            print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return _exit_code(status, code, mode)

    status = "PASS"
    code = "OK"
    payload = _common_fields(project, "query", mode, profile, None, status, code, [])
    payload.update(
        {
            "query_backend": results_payload.get("query_backend"),
            "filters": results_payload.get("filters"),
            "count": results_payload.get("count"),
            "results": results_payload.get("results"),
        }
    )
    out_path = _artifact_path(project_root, "query_results.json", args.out)
    _write_json(out_path, payload)

    artifacts = {"query_results": str(out_path)}
    detail = f"{payload.get('count', 0)} results backend={payload.get('query_backend')}"
    verbose_lines = None
    if args.verbose:
        verbose_lines = [
            f"timestamp={_now_iso()}",
            f"backend={payload.get('query_backend')}",
        ]
    _human_output(
        project,
        mode,
        profile,
        "query",
        None,
        status,
        code,
        detail,
        artifacts,
        None,
        verbose_lines,
        policy,
        project_root,
        args.quiet, args.json,
    )
    if args.json:
        print(Path(out_path).read_text())
    return _exit_code(status, code, mode)


def cmd_apply(args: argparse.Namespace) -> int:
    project = args.project
    project_root = _project_root(project)
    policy = _load_policy(project_root)
    profile = _profile_name(args, policy)
    mode = _mode_name(args, policy)

    cli_policy = _cli_policy(policy)
    allow_force = bool(cli_policy.get("allow_force_lock", False))
    require_yes = bool(cli_policy.get("require_yes_for_force", True))

    pipeline_path = args.pipeline or _default_pipeline(mode)
    pipeline_name = Path(pipeline_path).name

    lock_path = project_root / ".locks" / "forgescaffold_apply.lock"
    lock_payload = None
    lock_age = None
    if lock_path.exists():
        try:
            lock_payload = json.loads(lock_path.read_text())
        except Exception:
            lock_payload = None
        if lock_payload and lock_payload.get("started_at"):
            try:
                started = datetime.fromisoformat(lock_payload["started_at"].replace("Z", "+00:00"))
                lock_age = (datetime.now(timezone.utc) - started).total_seconds() / 60.0
            except Exception:
                lock_age = None
        lock_detail = f"Apply lock present age={int(lock_age)}m" if lock_age is not None else "Apply lock present"
        if not args.force:
            status = "BLOCKED"
            code = "LOCK_HELD"
            payload = _common_fields(project, "apply", mode, profile, pipeline_name, status, code, [code])
            out_path = _artifact_path(project_root, "apply_summary.json", args.out)
            payload["details"] = lock_detail
            _write_apply_summary(project_root, payload, out_path)
            next_steps = [f"python3 scripts/forgescaffold_cli.py explain --project {project} --last"]
            verbose_lines = None
            if args.verbose:
                verbose_lines = [f"timestamp={_now_iso()}"]
            _human_output(
                project,
                mode,
                profile,
                "apply",
                pipeline_name,
                status,
                code,
                lock_detail,
                {"apply_summary": str(out_path)},
                next_steps,
                verbose_lines,
                policy,
                project_root,
                args.quiet, args.json,
            )
            if args.json:
                print(Path(out_path).read_text())
            return _exit_code(status, code, mode)
        if args.force:
            if not allow_force:
                status = "BLOCKED"
                code = "POLICY_BLOCKED"
                payload = _common_fields(project, "apply", mode, profile, pipeline_name, status, code, [code])
                out_path = _artifact_path(project_root, "apply_summary.json", args.out)
                payload["details"] = "Force lock not allowed by policy"
                _write_apply_summary(project_root, payload, out_path)
                verbose_lines = None
                if args.verbose:
                    verbose_lines = [f"timestamp={_now_iso()}"]
                _human_output(
                    project,
                    mode,
                    profile,
                    "apply",
                    pipeline_name,
                    status,
                    code,
                    "Force lock not allowed by policy",
                    {"apply_summary": str(out_path)},
                    None,
                    verbose_lines,
                    policy,
                    project_root,
                    args.quiet, args.json,
                )
                return _exit_code(status, code, mode)
            if require_yes and not args.yes:
                status = "BLOCKED"
                code = "USER_INPUT_ERROR"
                payload = _common_fields(project, "apply", mode, profile, pipeline_name, status, code, [code])
                out_path = _artifact_path(project_root, "apply_summary.json", args.out)
                payload["details"] = "--yes required for force"
                _write_apply_summary(project_root, payload, out_path)
                verbose_lines = None
                if args.verbose:
                    verbose_lines = [f"timestamp={_now_iso()}"]
                _human_output(
                    project,
                    mode,
                    profile,
                    "apply",
                    pipeline_name,
                    status,
                    code,
                    "--yes required for force",
                    {"apply_summary": str(out_path)},
                    None,
                    verbose_lines,
                    policy,
                    project_root,
                    args.quiet, args.json,
                )
                return _exit_code(status, code, mode)

    approval_path = project_root / "approvals" / "patchset_approval.json"
    if not approval_path.exists():
        template_path = _generate_approval_template(project, profile, suppress_output=args.quiet or args.json)
        if template_path and args.ticket:
            try:
                template_payload = _load_json(Path(template_path))
                template_payload["ticket_id"] = args.ticket
                _write_json(Path(template_path), template_payload)
            except Exception:
                pass
        status = "BLOCKED"
        code = "APPROVAL_REQUIRED"
        payload = _common_fields(project, "apply", mode, profile, pipeline_name, status, code, [code])
        out_path = _artifact_path(project_root, "apply_summary.json", args.out)
        payload["approval_template"] = template_path
        _write_apply_summary(project_root, payload, out_path)
        approve_cmd = (
            f"python3 scripts/forgescaffold_cli.py approve --project {project} --approval {template_path} "
            f"--approver \"<name>\" --reason \"<text>\" --yes"
        )
        verbose_lines = None
        if args.verbose:
            verbose_lines = [f"timestamp={_now_iso()}"]
        _human_output(
            project,
            mode,
            profile,
            "apply",
            pipeline_name,
            status,
            code,
            "HITL gate active; approval receipt missing",
            {"approval_template": template_path or ""},
            [approve_cmd],
            verbose_lines,
            policy,
            project_root,
            args.quiet, args.json,
        )
        if args.json:
            print(Path(out_path).read_text())
        return _exit_code(status, code, mode)

    try:
        pipeline_to_run = pipeline_path
        if args.force or args.mode:
            data = yaml.safe_load(Path(pipeline_path).read_text())
            for link in data.get("links", []):
                if link.get("id") == "forgescaffold.apply_patchset" and args.force:
                    link.setdefault("config", {})
                    link["config"]["force_lock"] = True
                if link.get("id") == "forgescaffold.verify_post_apply" and args.mode:
                    link.setdefault("config", {})
                    link["config"]["mode"] = args.mode
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as fh:
                yaml.safe_dump(data, fh)
                pipeline_to_run = fh.name

        _run_orchestrator(project, pipeline_to_run, profile, suppress_output=args.quiet or args.json)
    except Exception:
        status = "FAIL"
        code = "PIPELINE_FAILED"
        payload = _common_fields(project, "apply", mode, profile, pipeline_name, status, code, [code])
        out_path = _artifact_path(project_root, "apply_summary.json", args.out)
        _write_apply_summary(project_root, payload, out_path)
        verbose_lines = None
        if args.verbose:
            verbose_lines = [f"timestamp={_now_iso()}"]
        _human_output(
            project,
            mode,
            profile,
            "apply",
            pipeline_name,
            status,
            code,
            "Pipeline failed",
            {"apply_summary": str(out_path)},
            None,
            verbose_lines,
            policy,
            project_root,
            args.quiet, args.json,
        )
        if args.json:
            print(Path(out_path).read_text())
        return _exit_code(status, code, mode)

    verify_report = _load_artifact(project_root, "forgescaffold.verification_report.json")
    evidence_verification = _load_artifact(project_root, "forgescaffold.evidence_verification_report.json")
    status_value = "PASS"
    if verify_report and verify_report.get("status") == "WARN":
        status_value = "WARN"
    if evidence_verification and evidence_verification.get("status") != "PASS":
        status_value = "FAIL"

    index_path = project_root / "evidence" / "evidence_index.jsonl"
    last_entry = None
    if index_path.exists():
        lines = [line for line in index_path.read_text().splitlines() if line.strip()]
        if lines:
            try:
                last_entry = json.loads(lines[-1])
            except Exception:
                last_entry = None

    checkpoint = _latest_checkpoint(project_root, policy)
    cache_backend, _ = _cache_backend(project_root)

    apply_summary = _common_fields(project, "apply", mode, profile, pipeline_name, status_value, "OK" if status_value != "FAIL" else "PIPELINE_FAILED", [])
    apply_summary.update(
        {
            "evidence_pack_path": (last_entry or {}).get("evidence_pack_path"),
            "entry_hash": (last_entry or {}).get("entry_hash"),
            "last_checkpoint_hash": (checkpoint or {}).get("last_entry_hash"),
            "ticket_id": (last_entry or {}).get("ticket_id"),
            "ticket_id_status": (last_entry or {}).get("ticket_id_status"),
            "query_backend": cache_backend,
        }
    )

    out_path = _artifact_path(project_root, "apply_summary.json", args.out)
    _write_apply_summary(project_root, apply_summary, out_path)

    detail = "Evidence signed; index appended; checkpoint cadence respected"
    if status_value == "WARN":
        detail = "Runnable-only: deps missing were skipped; no runnable failures"
    if status_value == "FAIL":
        detail = "Apply pipeline failed"

    verbose_lines = None
    if args.verbose:
        verbose_lines = [
            f"timestamp={_now_iso()}",
            f"cache_backend={cache_backend}",
        ]
    _human_output(
        project,
        mode,
        profile,
        "apply",
        pipeline_name,
        status_value,
        "OK" if status_value != "FAIL" else "PIPELINE_FAILED",
        detail,
        {"apply_summary": str(out_path)},
        None,
        verbose_lines,
        policy,
        project_root,
        args.quiet, args.json,
    )

    if args.json:
        print(Path(out_path).read_text())

    return _exit_code(status_value, "OK" if status_value != "FAIL" else "PIPELINE_FAILED", mode)


def cmd_approve(args: argparse.Namespace) -> int:
    project = args.project
    project_root = _project_root(project)
    policy = _load_policy(project_root)
    profile = _profile_name(args, policy)
    mode = _mode_name(args, policy)

    approval_path = Path(args.approval)
    if not approval_path.exists():
        status = "FAIL"
        code = "APPROVAL_INVALID"
        payload = _common_fields(project, "approve", mode, profile, None, status, code, [code])
        out_path = _artifact_path(project_root, "approve_summary.json", args.out)
        _write_json(out_path, payload)
        verbose_lines = None
        if args.verbose:
            verbose_lines = [f"timestamp={_now_iso()}"]
        _human_output(
            project,
            mode,
            profile,
            "approve",
            None,
            status,
            code,
            "Approval template not found",
            {"approve_summary": str(out_path)},
            None,
            verbose_lines,
            policy,
            project_root,
            args.quiet, args.json,
        )
        return _exit_code(status, code, mode)

    template = _load_json(approval_path)
    approval_id = template.get("approval_id")
    if not approval_id:
        status = "FAIL"
        code = "APPROVAL_INVALID"
        payload = _common_fields(project, "approve", mode, profile, None, status, code, [code])
        out_path = _artifact_path(project_root, "approve_summary.json", args.out)
        _write_json(out_path, payload)
        verbose_lines = None
        if args.verbose:
            verbose_lines = [f"timestamp={_now_iso()}"]
        _human_output(
            project,
            mode,
            profile,
            "approve",
            None,
            status,
            code,
            "approval_id missing",
            {"approve_summary": str(out_path)},
            None,
            verbose_lines,
            policy,
            project_root,
            args.quiet, args.json,
        )
        return _exit_code(status, code, mode)

    used_path = project_root / "approvals" / "used_approvals.jsonl"
    if used_path.exists():
        for line in used_path.read_text().splitlines():
            if line.strip():
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if entry.get("approval_id") == approval_id:
                    status = "BLOCKED"
                    code = "APPROVAL_REPLAY_DETECTED"
                    payload = _common_fields(project, "approve", mode, profile, None, status, code, [code])
                    out_path = _artifact_path(project_root, "approve_summary.json", args.out)
                    _write_json(out_path, payload)
                    verbose_lines = None
                    if args.verbose:
                        verbose_lines = [f"timestamp={_now_iso()}"]
                    _human_output(
                        project,
                        mode,
                        profile,
                        "approve",
                        None,
                        status,
                        code,
                        "Approval replay detected",
                        {"approve_summary": str(out_path)},
                        None,
                        verbose_lines,
                        policy,
                        project_root,
                        args.quiet, args.json,
                    )
                    return _exit_code(status, code, mode)

    required_approvals = int(template.get("required_approvals") or 1)
    if required_approvals > 1 and not args.co_approver:
        status = "BLOCKED"
        code = "APPROVAL_COUNT_INSUFFICIENT"
        payload = _common_fields(project, "approve", mode, profile, None, status, code, [code])
        out_path = _artifact_path(project_root, "approve_summary.json", args.out)
        _write_json(out_path, payload)
        verbose_lines = None
        if args.verbose:
            verbose_lines = [f"timestamp={_now_iso()}"]
        _human_output(
            project,
            mode,
            profile,
            "approve",
            None,
            status,
            code,
            "Two approvers required",
            {"approve_summary": str(out_path)},
            None,
            verbose_lines,
            policy,
            project_root,
            args.quiet, args.json,
        )
        return _exit_code(status, code, mode)

    if template.get("required_risk_ack") and not args.risk_ack:
        status = "BLOCKED"
        code = "RISK_ACK_REQUIRED"
        payload = _common_fields(project, "approve", mode, profile, None, status, code, [code])
        out_path = _artifact_path(project_root, "approve_summary.json", args.out)
        _write_json(out_path, payload)
        verbose_lines = None
        if args.verbose:
            verbose_lines = [f"timestamp={_now_iso()}"]
        _human_output(
            project,
            mode,
            profile,
            "approve",
            None,
            status,
            code,
            "Risk acknowledgment required",
            {"approve_summary": str(out_path)},
            None,
            verbose_lines,
            policy,
            project_root,
            args.quiet, args.json,
        )
        return _exit_code(status, code, mode)

    approvers = [
        {
            "name": args.approver,
            "approved_at": _now_iso(),
            "nonce": args.nonce or "cli-approval-nonce-1234567890",
            "approval_reason": args.reason,
        }
    ]
    if args.co_approver:
        approvers.append(
            {
                "name": args.co_approver,
                "approved_at": _now_iso(),
                "nonce": args.co_nonce or "cli-approval-nonce-abcdef1234",
                "approval_reason": args.reason,
            }
        )

    approval_payload = {
        "schema_version": template.get("schema_version", "1.0.0"),
        "approval_id": approval_id,
        "patchset_id": template.get("patchset_id"),
        "bundle_content_sha256": template.get("bundle_content_sha256"),
        "review_packet_sha256": template.get("review_packet_sha256"),
        "approvers": approvers,
        "approval_reason": args.reason,
        "risk_ack": bool(args.risk_ack),
        "risk_override": bool(args.risk_override),
        "ticket_id": template.get("ticket_id") or template.get("ticket"),
    }

    approvals_dir = project_root / "approvals"
    approvals_dir.mkdir(parents=True, exist_ok=True)
    approval_file = approvals_dir / "patchset_approval.json"
    _write_json(approval_file, approval_payload)

    if args.sign:
        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519
            from cryptography.hazmat.primitives import serialization
            import base64
        except Exception as exc:
            status = "FAIL"
            code = "APPROVAL_INVALID"
            payload = _common_fields(project, "approve", mode, profile, None, status, code, [code])
            out_path = _artifact_path(project_root, "approve_summary.json", args.out)
            _write_json(out_path, payload)
            verbose_lines = None
            if args.verbose:
                verbose_lines = [f"timestamp={_now_iso()}"]
            _human_output(
                project,
                mode,
                profile,
                "approve",
                None,
                status,
                code,
                "Signing deps missing",
                {"approve_summary": str(out_path)},
                None,
                verbose_lines,
                policy,
                project_root,
                args.quiet, args.json,
            )
            return _exit_code(status, code, mode)

        key_text = os.environ.get("FORGESCAFFOLD_SIGNING_KEY")
        if key_text:
            if key_text.startswith("base64:"):
                raw = base64.b64decode(key_text.split(":", 1)[1])
            else:
                raw = base64.b64decode(key_text)
            if len(raw) == 64:
                raw = raw[:32]
            private_key = ed25519.Ed25519PrivateKey.from_private_bytes(raw)
            signature = private_key.sign(json.dumps(approval_payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            signature_path = approvals_dir / "patchset_approval.signature"
            signature_path.write_bytes(signature)

    status = "PASS"
    code = "OK"
    summary = _common_fields(project, "approve", mode, profile, None, status, code, [])
    summary["approval_receipt_path"] = str(approval_file)
    out_path = _artifact_path(project_root, "approve_summary.json", args.out)
    _write_json(out_path, summary)

    next_cmd = f"python3 scripts/forgescaffold_cli.py apply --project {project} --mode {mode} --yes"
    verbose_lines = None
    if args.verbose:
        verbose_lines = [f"timestamp={_now_iso()}"]
    _human_output(
        project,
        mode,
        profile,
        "approve",
        None,
        status,
        code,
        f"Approval recorded approval_id={approval_id}",
        {"approval_receipt": str(approval_file), "approve_summary": str(out_path)},
        [next_cmd],
        verbose_lines,
        policy,
        project_root,
        args.quiet, args.json,
    )

    if args.json:
        print(Path(out_path).read_text())

    return _exit_code(status, code, mode)


def _find_latest_cli_failure(project_root: Path) -> Optional[Dict[str, Any]]:
    cli_dir = _artifact_dir(project_root)
    if not cli_dir.exists():
        return None
    candidates = []
    for path in cli_dir.glob("*.json"):
        try:
            payload = _load_json(path)
        except Exception:
            continue
        status = payload.get("status")
        if status in {"FAIL", "BLOCKED"}:
            candidates.append((path.stat().st_mtime, payload, path))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return {"payload": candidates[0][1], "path": str(candidates[0][2])}


def _explain_for_code(code: str, project: str, mode: str) -> Dict[str, Any]:
    default = {
        "cause": "No explanation available",
        "evidence": [],
        "next_steps": [f"python3 scripts/forgescaffold_cli.py doctor --project {project} --mode {mode} --json"],
    }
    mapping = {
        "LOCK_HELD": {
            "cause": "Apply lock exists; another run is in progress or stale.",
            "evidence": ["Lock file present"],
            "next_steps": [
                f"python3 scripts/forgescaffold_cli.py apply --project {project} --mode {mode} --yes",
                f"python3 scripts/forgescaffold_cli.py explain --project {project} --last",
            ],
        },
        "APPROVAL_REQUIRED": {
            "cause": "HITL approval missing.",
            "evidence": ["approval_receipt.json not found"],
            "next_steps": [
                f"python3 scripts/forgescaffold_cli.py approve --project {project} --approval <template_path> --approver \"<name>\" --reason \"<text>\" --yes",
                f"python3 scripts/forgescaffold_cli.py apply --project {project} --mode {mode} --yes",
            ],
        },
        "TICKET_REQUIRED": {
            "cause": "Ticket binding required by policy.",
            "evidence": ["ticket_id missing"],
            "next_steps": [
                f"python3 scripts/forgescaffold_cli.py apply --project {project} --mode {mode} --ticket FC-<id> --yes",
            ],
        },
        "TICKET_ID_INVALID": {
            "cause": "Ticket ID failed normalization/validation.",
            "evidence": ["ticket_id invalid"],
            "next_steps": [
                f"python3 scripts/forgescaffold_cli.py apply --project {project} --mode {mode} --ticket FC-<digits> --yes",
            ],
        },
        "RISK_ACK_REQUIRED": {
            "cause": "High-risk approval requires risk acknowledgment.",
            "evidence": ["risk_ack missing"],
            "next_steps": [
                f"python3 scripts/forgescaffold_cli.py approve --project {project} --approval <template_path> --approver \"<name>\" --reason \"<text>\" --risk-ack --yes",
            ],
        },
        "SIGNATURE_INVALID": {
            "cause": "Evidence signature verification failed.",
            "evidence": ["signature invalid or missing"],
            "next_steps": [
                f"python3 scripts/forgescaffold_cli.py doctor --project {project} --mode {mode} --json",
            ],
        },
        "TRUST_SCOPE_VIOLATION": {
            "cause": "Signer scope does not permit this project/pipeline.",
            "evidence": ["signer scope violation"],
            "next_steps": [
                f"python3 scripts/forgescaffold_cli.py doctor --project {project} --mode {mode} --json",
            ],
        },
        "INDEX_INTEGRITY_FAIL": {
            "cause": "Evidence index integrity check failed.",
            "evidence": ["index integrity report failed"],
            "next_steps": [
                f"python3 scripts/forgescaffold_cli.py doctor --project {project} --mode {mode} --json",
            ],
        },
        "ENTRY_HASH_MISMATCH": {
            "cause": "Evidence index hash chain mismatch.",
            "evidence": ["entry hash mismatch"],
            "next_steps": [
                f"python3 scripts/forgescaffold_cli.py doctor --project {project} --mode {mode} --json",
            ],
        },
    }
    for key, value in mapping.items():
        if code == key or code.startswith("CONFLICT_"):
            if code.startswith("CONFLICT_"):
                return {
                    "cause": "Patch application conflict.",
                    "evidence": [code],
                    "next_steps": [
                        f"python3 scripts/forgescaffold_cli.py apply --project {project} --mode {mode} --yes",
                    ],
                }
            return value
    return default


def cmd_explain(args: argparse.Namespace) -> int:
    project = args.project
    project_root = _project_root(project)
    policy = _load_policy(project_root)
    profile = _profile_name(args, policy)
    mode = _mode_name(args, policy)

    code = args.error_code
    references = []
    if args.last:
        last = _find_latest_cli_failure(project_root)
        if not last:
            status = "FAIL"
            code = "EXPLAIN_NO_CONTEXT"
            payload = _common_fields(project, "explain", mode, profile, None, status, code, [code])
            out_path = _artifact_path(project_root, "explain.json", args.out)
            payload.update({"code": code, "cause": "No prior CLI failure found", "evidence": [], "next_steps": []})
            _write_json(out_path, payload)
            verbose_lines = None
            if args.verbose:
                verbose_lines = [f"timestamp={_now_iso()}"]
            _human_output(
                project,
                mode,
                profile,
                "explain",
                None,
                status,
                code,
                "No prior CLI failure found",
                {"explain": str(out_path)},
                None,
                verbose_lines,
                policy,
                project_root,
                args.quiet, args.json,
            )
            return _exit_code(status, code, mode)
        code = last["payload"].get("primary_code")
        references.append(last["path"])

    explanation = _explain_for_code(code, project, mode)

    status = "PASS"
    primary_code = "OK"
    payload = _common_fields(project, "explain", mode, profile, None, status, primary_code, [])
    payload.update(
        {
            "code": code,
            "cause": explanation.get("cause"),
            "evidence": explanation.get("evidence"),
            "next_steps": explanation.get("next_steps"),
            "references": references,
        }
    )

    out_path = _artifact_path(project_root, "explain.json", args.out)
    _write_json(out_path, payload)

    lines = [
        f"Cause: {explanation.get('cause')}",
        f"Evidence: {', '.join(explanation.get('evidence') or [])}",
    ]
    next_steps = explanation.get("next_steps") or []

    verbose_lines = None
    if args.verbose:
        verbose_lines = [f"timestamp={_now_iso()}"]
    _human_output(
        project,
        mode,
        profile,
        "explain",
        None,
        status,
        primary_code,
        f"Explanation generated for {code}",
        {"explain": str(out_path)},
        next_steps,
        lines + (verbose_lines or []),
        policy,
        project_root,
        args.quiet, args.json,
    )

    if args.json:
        print(Path(out_path).read_text())

    return _exit_code(status, primary_code, mode)


def cmd_doctor(args: argparse.Namespace) -> int:
    project = args.project
    project_root = _project_root(project)
    policy = _load_policy(project_root)
    profile = _profile_name(args, policy)
    mode = _mode_name(args, policy)

    errors: List[str] = []
    warnings: List[str] = []

    if not policy:
        errors.append("POLICY_PARSE_FAIL")

    profile_cfg = (policy.get("profiles") or {}).get(profile, {})
    allowed_roots = set(profile_cfg.get("allowed_write_roots") or [])
    for required in ["artifacts", "approvals", ".locks"]:
        if required not in allowed_roots:
            errors.append("WRITE_ROOT_BLOCKED")
            break

    ok, reason = _ensure_dir(project_root / ".locks")
    if not ok:
        errors.append("WRITE_ROOT_BLOCKED")
        warnings.append(reason or "lock dir not writable")

    index_path = project_root / "evidence" / "evidence_index.jsonl"
    if not index_path.exists():
        warnings.append("INDEX_READ_FAIL")

    cache_path = project_root / "evidence" / "cache" / "evidence_index_cache.sqlite"
    if cache_path.exists():
        try:
            _run_single_link(project, "forgescaffold.verify_cache_integrity", {}, profile, suppress_output=True)
            report_path = _artifact_path_from_index(project_root, "forgescaffold.cache_integrity_report.json")
            if report_path:
                report = _load_json(Path(report_path))
                if report.get("status") != "PASS":
                    warnings.append("CACHE_INTEGRITY_FAIL")
        except Exception:
            warnings.append("CACHE_INTEGRITY_FAIL")

    index_policy = (policy.get("forgescaffold") or {}).get("index_integrity") or {}
    if index_policy.get("checkpoint_enabled", False):
        try:
            _run_single_link(project, "forgescaffold.verify_index_integrity", {}, profile, suppress_output=True)
            report_path = _artifact_path_from_index(project_root, "forgescaffold.index_integrity_report.json")
            if report_path:
                report = _load_json(Path(report_path))
                if report.get("status") != "PASS":
                    warnings.append("CHECKPOINT_VERIFY_FAIL")
        except Exception:
            warnings.append("CHECKPOINT_VERIFY_FAIL")

    pipeline_path = _default_pipeline(mode)
    signing_required = _pipeline_has_link(pipeline_path, "forgescaffold.sign_evidence")
    if signing_required:
        try:
            import cryptography  # noqa: F401
        except Exception:
            warnings.append("SIGNING_DEPS_MISSING")

    status = "PASS"
    primary_code = "OK"
    if errors:
        status = "FAIL"
        primary_code = errors[0]
    elif warnings:
        status = "WARN"
        primary_code = "OK_WARN"

    payload = _common_fields(project, "doctor", mode, profile, None, status, primary_code, errors + warnings)
    payload.update({"warnings": warnings, "errors": errors})

    out_path = _artifact_path(project_root, "doctor_report.json", args.out)
    _write_json(out_path, payload)

    detail = "Diagnostics complete"
    if status == "WARN":
        detail = "Warnings detected"
    if status == "FAIL":
        detail = "Blocking issues detected"

    verbose_lines = None
    if args.verbose:
        verbose_lines = [f"timestamp={_now_iso()}"]
    _human_output(
        project,
        mode,
        profile,
        "doctor",
        None,
        status,
        primary_code,
        detail,
        {"doctor_report": str(out_path)},
        None,
        verbose_lines,
        policy,
        project_root,
        args.quiet, args.json,
    )

    if args.json:
        print(Path(out_path).read_text())

    return _exit_code(status, primary_code, mode)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forgescaffold_cli.py", add_help=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--project", required=True)
    parent.add_argument("--profile")
    parent.add_argument("--mode", choices=["strict", "runnable_only"])
    parent.add_argument("--pipeline")
    parent.add_argument("--json", action="store_true")
    parent.add_argument("--out")
    parent.add_argument("--limit", type=int)
    parent.add_argument("--verbose", action="store_true")
    parent.add_argument("--quiet", action="store_true")
    parent.add_argument("--yes", action="store_true")
    parent.add_argument("--bootstrap", action="store_true")

    status = subparsers.add_parser("status", parents=[parent], help="Show project operational status")
    status.set_defaults(func=cmd_status)

    apply_cmd = subparsers.add_parser("apply", parents=[parent], help="Run ForgeScaffold apply pipeline")
    apply_cmd.add_argument("--ticket")
    apply_cmd.add_argument("--force", action="store_true")
    apply_cmd.set_defaults(func=cmd_apply)

    approve = subparsers.add_parser("approve", parents=[parent], help="Record an approval receipt")
    approve.add_argument("--approval", required=True)
    approve.add_argument("--approver", required=True)
    approve.add_argument("--co-approver")
    approve.add_argument("--reason", required=True)
    approve.add_argument("--risk-ack", action="store_true")
    approve.add_argument("--risk-override", action="store_true")
    approve.add_argument("--sign", action="store_true")
    approve.add_argument("--nonce")
    approve.add_argument("--co-nonce")
    approve.set_defaults(func=cmd_approve)

    query = subparsers.add_parser("query", parents=[parent], help="Query evidence index")
    query.add_argument("--ticket")
    query.add_argument("--patchset")
    query.add_argument("--status", choices=["PASS", "WARN", "FAIL"])
    query.set_defaults(func=cmd_query)

    explain = subparsers.add_parser("explain", parents=[parent], help="Explain last failure")
    explain_group = explain.add_mutually_exclusive_group(required=True)
    explain_group.add_argument("--last", action="store_true")
    explain_group.add_argument("--error-code")
    explain.set_defaults(func=cmd_explain)

    doctor = subparsers.add_parser("doctor", parents=[parent], help="Preflight diagnostics")
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception:
        return EXIT_INTERNAL_ERROR


if __name__ == "__main__":
    sys.exit(main())
