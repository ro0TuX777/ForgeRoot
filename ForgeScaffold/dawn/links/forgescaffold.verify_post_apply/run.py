import importlib
import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


def _load_artifact(artifact_store, artifact_id: str) -> Dict[str, Any]:
    meta = artifact_store.get(artifact_id)
    if not meta:
        raise RuntimeError(f"Missing required artifact: {artifact_id}")
    with open(meta["path"], "r") as fh:
        if meta["path"].endswith(".yaml") or meta["path"].endswith(".yml"):
            return yaml.safe_load(fh)
        return json.load(fh)


def _run_command(command: str, cwd: Path, timeout: int) -> Dict[str, Any]:
    result = subprocess.run(
        command,
        shell=True,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _python_importable(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except Exception:
        return False


def _extract_python_import(command: str) -> Optional[str]:
    try:
        args = shlex.split(command)
    except ValueError:
        return None
    if not args or args[0] != "python3" or "-c" not in args:
        return None
    idx = args.index("-c")
    if idx + 1 >= len(args):
        return None
    snippet = args[idx + 1].strip()
    if not snippet.startswith("import "):
        return None
    module = snippet.split()[1].split(";")[0]
    return module.strip()


def _extract_pytest_target(command: str) -> Optional[str]:
    try:
        args = shlex.split(command)
    except ValueError:
        return None
    if len(args) < 3 or args[0] != "python3" or args[1] != "-m" or args[2] != "pytest":
        return None
    for arg in args[3:]:
        if not arg.startswith("-"):
            return arg
    return None


def _preflight_check(command: str, project_root: Path) -> Tuple[Optional[str], List[str], Optional[str]]:
    missing = []
    skip_reason = None

    if command.strip().startswith("python3") and not shutil.which("python3"):
        return "SKIPPED_CMD_MISSING", ["python3"], "python3 not found"
    if command.strip().startswith("node") and not shutil.which("node"):
        return "SKIPPED_CMD_MISSING", ["node"], "node not found"

    import_module = _extract_python_import(command)
    if import_module:
        if not _python_importable(import_module):
            return "SKIPPED_DEP_MISSING", [import_module], f"missing python module: {import_module}"

    pytest_target = _extract_pytest_target(command)
    if pytest_target:
        if not _python_importable("pytest"):
            return "SKIPPED_DEP_MISSING", ["pytest"], "missing python module: pytest"
        target_path = project_root / pytest_target
        if not target_path.exists():
            return "SKIPPED_TARGET_MISSING", [], f"target missing: {pytest_target}"
        if target_path.is_file():
            try:
                content = target_path.read_text()
            except Exception:
                content = ""
            if "def test_" not in content and "class Test" not in content:
                return "SKIPPED_NO_TESTS", [], f"no tests detected in {pytest_target}"

    return skip_reason, missing, None


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    artifact_store = project_context.get("artifact_store")
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not artifact_store or not sandbox:
        raise RuntimeError("Sandbox or artifact store missing")

    test_matrix = _load_artifact(artifact_store, "forgescaffold.test_matrix.yaml")
    _load_artifact(artifact_store, "forgescaffold.test_harness.manifest.json")

    tests = []
    for unit in test_matrix.get("units", []):
        for test in unit.get("tests", []):
            if test.get("level") in {"L0_contract", "L1_slice"}:
                tests.append(test)

    commands = []
    for test in tests:
        cmd = test.get("command")
        if cmd and cmd not in commands:
            commands.append(cmd)

    results = []
    logs = []
    timeout_sec = int(link_config.get("config", {}).get("timeout_sec", 300))
    mode = link_config.get("config", {}).get("mode", "strict")
    runnable_only = mode == "runnable_only"

    for idx, command in enumerate(commands):
        if runnable_only:
            skip_status, missing_deps, reason = _preflight_check(command, project_root)
            if skip_status:
                log_path = Path("test_results") / f"command_{idx}.log"
                content = (
                    f"COMMAND: {command}\n"
                    f"STATUS: {skip_status}\n"
                    f"REASON: {reason}\n"
                    f"MISSING_DEPS: {', '.join(missing_deps) if missing_deps else 'none'}\n"
                )
                sandbox.write_text(str(log_path), content)
                logs.append({
                    "path": str(log_path),
                    "command": command,
                    "exit_code": None,
                    "status": skip_status,
                })
                results.append({
                    "command": command,
                    "exit_code": None,
                    "status": skip_status,
                    "reason": reason,
                    "missing_deps": missing_deps,
                })
                continue

        payload = _run_command(command, project_root, timeout_sec)
        log_path = Path("test_results") / f"command_{idx}.log"
        content = (
            f"COMMAND: {payload['command']}\n"
            f"EXIT_CODE: {payload['exit_code']}\n\n"
            f"STDOUT:\n{payload['stdout']}\n\nSTDERR:\n{payload['stderr']}\n"
        )
        sandbox.write_text(str(log_path), content)
        logs.append({"path": str(log_path), "command": payload["command"], "exit_code": payload["exit_code"]})
        results.append({
            "command": payload["command"],
            "exit_code": payload["exit_code"],
            "status": "PASS" if payload["exit_code"] == 0 else "FAIL",
        })

    failed = [r for r in results if r["status"] == "FAIL"]
    skipped = [r for r in results if r["status"].startswith("SKIPPED_")]
    if failed:
        overall = "FAIL"
    elif skipped:
        overall = "WARN"
    else:
        overall = "PASS"

    report = {
        "status": overall,
        "mode": mode,
        "results": results,
    }

    manifest = {
        "root": "test_results",
        "logs": logs,
    }

    report_path = sandbox.publish(
        "forgescaffold.verification_report.json",
        "verification_report.json",
        report,
        schema="json",
    )
    manifest_path = sandbox.publish(
        "forgescaffold.test_results.manifest.json",
        "test_results/manifest.json",
        manifest,
        schema="json",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {
            "forgescaffold.verification_report.json": {"path": report_path},
            "forgescaffold.test_results.manifest.json": {"path": manifest_path},
        },
        "metrics": {"commands": len(commands)},
    }
