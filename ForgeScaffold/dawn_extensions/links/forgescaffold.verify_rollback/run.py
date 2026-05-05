import fnmatch
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _load_artifact(artifact_store, artifact_id: str) -> Dict[str, Any]:
    meta = artifact_store.get(artifact_id)
    if not meta:
        raise RuntimeError(f"Missing required artifact: {artifact_id}")
    with open(meta["path"], "r") as fh:
        return json.load(fh)


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _read_bytes(path: Path) -> Optional[bytes]:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _detect_newline_style(data: bytes) -> str:
    if b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b""):
        return "\r\n"
    return "\n"


def _normalize_newlines(text: str, newline: str) -> str:
    if newline == "\r\n":
        return text.replace("\r\n", "\n").replace("\n", "\r\n")
    return text.replace("\r\n", "\n")


def _split_lines(text: str) -> List[str]:
    return text.splitlines(keepends=True)


def _line_range_to_indices(text: str, token: str) -> Optional[Tuple[int, int]]:
    match = re.match(r"^L?(\d+)[-:](?:L)?(\d+)$", token.strip())
    if not match:
        return None
    start_line = int(match.group(1))
    end_line = int(match.group(2))
    if start_line <= 0 or end_line < start_line:
        return None
    lines = _split_lines(text)
    if not lines:
        return None
    if start_line > len(lines) or end_line > len(lines):
        return None
    start_idx = sum(len(line) for line in lines[: start_line - 1])
    end_idx = sum(len(line) for line in lines[:end_line])
    return start_idx, end_idx


def _find_anchor(text: str, anchor: Dict[str, Any]) -> List[Tuple[int, int]]:
    anchor_type = anchor.get("type")
    value = anchor.get("value", "")

    if anchor_type == "literal":
        matches = []
        start = 0
        while True:
            idx = text.find(value, start)
            if idx == -1:
                break
            matches.append((idx, idx + len(value)))
            start = idx + max(len(value), 1)
        return matches

    if anchor_type == "regex":
        return [(m.start(), m.end()) for m in re.finditer(value, text, flags=re.MULTILINE)]

    if anchor_type == "line_range":
        indices = _line_range_to_indices(text, value)
        return [indices] if indices else []

    return []


def _select_anchor(matches: List[Tuple[int, int]], occurrence: Optional[int]) -> Optional[Tuple[int, int]]:
    if not matches:
        return None
    if occurrence is None:
        if len(matches) == 1:
            return matches[0]
        return None
    if occurrence <= 0 or occurrence > len(matches):
        return None
    return matches[occurrence - 1]


def _apply_action(text: str, start: int, end: int, action: str, content: str) -> str:
    before = text[:start]
    target = text[start:end]
    after = text[end:]

    if action == "insert_before":
        return before + content + target + after
    if action == "insert_after":
        return before + target + content + after
    if action == "replace":
        return before + content + after
    if action == "delete":
        return before + after
    return text


def _scope_allowed(op: Dict[str, Any]) -> Tuple[bool, str]:
    path = op.get("path", "")
    old_path = op.get("old_path", "")
    tags = set(op.get("tags", []))

    deny_prefixes = ["dawn/", ".git/", ".github/workflows/"]
    for candidate in [path, old_path]:
        if any(candidate.startswith(prefix) for prefix in deny_prefixes):
            return False, f"Denied path: {candidate}"

    allow_prefixes = ["observability/", "tests/"]
    if path.startswith("src/"):
        if "observability" in tags:
            return True, "allowed"
        return False, "src writes require observability tag"

    if any(path.startswith(prefix) for prefix in allow_prefixes):
        return True, "allowed"

    return False, "path not in allowlist"


def _apply_operation(project_root: Path, op: Dict[str, Any]) -> Tuple[bool, str]:
    op_type = op["op"]
    path = project_root / op["path"]
    old_path = project_root / op.get("old_path", "") if op.get("old_path") else None

    if op_type == "add":
        if path.exists():
            return False, "target exists"
        content = op["content"].encode()
        if _sha256_bytes(content) != op["content_sha256"]:
            return False, "content hash mismatch"
        _write_bytes(path, content)
        return True, "applied"

    if op_type == "modify" and op.get("patch"):
        if not path.exists():
            return False, "target missing"
        data = _read_bytes(path) or b""
        newline = _detect_newline_style(data)
        had_final_newline = data.endswith(b"\n") or data.endswith(b"\r\n")
        text = data.decode(errors="replace")
        current = text

        for hunk in op.get("patch", []):
            matches = _find_anchor(current, hunk.get("anchor", {}))
            selected = _select_anchor(matches, hunk.get("anchor", {}).get("occurrence"))
            if not selected:
                return False, "rollback anchor not found"
            start, end = selected
            region = current[start:end]
            expected_before = hunk.get("expected_before_sha256")
            expected_after = hunk.get("expected_after_sha256")
            if expected_before and _sha256_text(region) != expected_before:
                return False, "rollback before hash mismatch"
            content = _normalize_newlines(hunk.get("content", ""), newline)
            next_text = _apply_action(current, start, end, hunk.get("action"), content)
            if expected_after:
                new_region = next_text[start : start + len(content)]
                if _sha256_text(new_region) != expected_after:
                    return False, "rollback after hash mismatch"
            current = next_text

        if newline == "\r\n":
            current = current.replace("\r\n", "\n").replace("\n", "\r\n")
        if had_final_newline and not current.endswith(newline):
            current += newline
        _write_bytes(path, current.encode())
        return True, "applied"

    if op_type == "modify":
        if not path.exists():
            return False, "target missing"
        content = op["content"].encode()
        if _sha256_bytes(content) != op["content_sha256"]:
            return False, "content hash mismatch"
        _write_bytes(path, content)
        return True, "applied"

    if op_type == "delete":
        if not path.exists():
            return True, "skipped_missing"
        path.unlink()
        return True, "applied"

    if op_type == "rename":
        if old_path is None or not old_path.exists():
            return False, "old_path missing"
        if path.exists():
            return False, "new path exists"
        path.parent.mkdir(parents=True, exist_ok=True)
        old_path.rename(path)
        return True, "applied"

    return False, "unsupported"


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    artifact_store = project_context.get("artifact_store")
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not artifact_store or not sandbox:
        raise RuntimeError("Sandbox or artifact store missing")

    rollback_patchset = _load_artifact(artifact_store, "forgescaffold.rollback_patchset.json")
    snapshot = _load_artifact(artifact_store, "forgescaffold.workspace_snapshot.json")

    operations = rollback_patchset.get("operations", [])
    for op in operations:
        ok, reason = _scope_allowed(op)
        if not ok:
            report = {"status": "FAIL", "reason": reason, "operations": []}
            report_path = sandbox.publish("forgescaffold.rollback_report.json", "rollback_report.json", report, schema="json")
            return {"status": "SUCCEEDED", "outputs": {"forgescaffold.rollback_report.json": {"path": report_path}}}

    results = []
    for op in operations:
        ok, reason = _apply_operation(project_root, op)
        results.append({"path": op.get("path"), "op": op.get("op"), "status": "APPLIED" if ok else "FAILED", "reason": reason})
        if not ok:
            break

    comparisons = []
    status = "PASS"
    for entry in snapshot.get("files", []):
        rel_path = entry.get("path")
        pre_hash = entry.get("pre_hash")
        file_path = project_root / rel_path
        if pre_hash is None:
            exists = file_path.exists()
            comparisons.append({"path": rel_path, "expected": None, "observed": None if not exists else _sha256_bytes(file_path.read_bytes())})
            if exists:
                status = "FAIL"
            continue
        observed = _sha256_bytes(file_path.read_bytes()) if file_path.exists() else None
        comparisons.append({"path": rel_path, "expected": pre_hash, "observed": observed})
        if observed != pre_hash:
            status = "FAIL"

    report = {
        "status": status,
        "operations": results,
        "comparisons": comparisons,
    }

    report_path = sandbox.publish(
        "forgescaffold.rollback_report.json",
        "rollback_report.json",
        report,
        schema="json",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {"forgescaffold.rollback_report.json": {"path": report_path}},
        "metrics": {"operations": len(operations)},
    }
