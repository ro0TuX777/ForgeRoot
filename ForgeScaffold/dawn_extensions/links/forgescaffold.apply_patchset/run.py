import fnmatch
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

COMMON_DIR = Path(__file__).resolve().parents[1] / "forgescaffold_common"
sys.path.append(str(COMMON_DIR))

from lock_utils import acquire_lock, load_policy  # noqa: E402

def _load_artifact(artifact_store, artifact_id: str) -> Dict[str, Any]:
    meta = artifact_store.get(artifact_id)
    if not meta:
        raise RuntimeError(f"Missing required artifact: {artifact_id}")
    with open(meta["path"], "r") as fh:
        return json.load(fh)


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _read_bytes(path: Path) -> Optional[bytes]:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _compute_inputs_fingerprint(project_root: Path, extra_excludes: Optional[List[str]] = None) -> str:
    inputs_dir = project_root / "inputs"
    if not inputs_dir.exists():
        return ""

    default_excludes = [
        "hitl_*.json",
        ".dawn_*",
        ".DS_Store",
        "Thumbs.db",
        "._*",
        "*.tmp",
        "*.swp",
    ]
    excludes = default_excludes + (extra_excludes or [])

    files = []
    for file_path in sorted(inputs_dir.rglob("*")):
        if not file_path.is_file():
            continue
        rel_path = file_path.relative_to(inputs_dir).as_posix()
        if any(fnmatch.fnmatch(file_path.name, pat) or fnmatch.fnmatch(rel_path, pat) for pat in excludes):
            continue
        data = file_path.read_bytes()
        files.append(f"{rel_path}:{_sha256_bytes(data)}:{len(data)}")

    canonical = "\n".join(files)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


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


def _find_anchor(text: str, anchor: Dict[str, Any]) -> Tuple[List[Tuple[int, int]], str]:
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
        return matches, "literal"

    if anchor_type == "regex":
        matches = [(m.start(), m.end()) for m in re.finditer(value, text, flags=re.MULTILINE)]
        return matches, "regex"

    if anchor_type == "line_range":
        indices = _line_range_to_indices(text, value)
        return [indices] if indices else [], "line_range"

    return [], "unknown"


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


def _apply_action(text: str, start: int, end: int, action: str, content: str) -> Tuple[str, int, int]:
    before = text[:start]
    target = text[start:end]
    after = text[end:]

    if action == "insert_before":
        new_text = before + content + target + after
        return new_text, start, start + len(content) + len(target)
    if action == "insert_after":
        new_text = before + target + content + after
        return new_text, start, end + len(content)
    if action == "replace":
        new_text = before + content + after
        return new_text, start, start + len(content)
    if action == "delete":
        new_text = before + after
        return new_text, start, start
    return text, start, end


def _index_to_line(text: str, idx: int) -> int:
    if idx <= 0:
        return 1
    lines = _split_lines(text)
    total = 0
    for i, line in enumerate(lines, start=1):
        total += len(line)
        if idx < total:
            return i
    return max(len(lines), 1)


def _build_rollback_hunk(post_text: str, new_start: int, new_end: int, original_region: str) -> Dict[str, Any]:
    if new_start == new_end:
        if post_text:
            line = _index_to_line(post_text, new_start)
            return {
                "anchor": {"type": "line_range", "value": f"L{line}-L{line}"},
                "action": "insert_before",
                "content": original_region,
                "expected_before_sha256": _sha256_text(post_text[new_start:new_end]),
                "expected_after_sha256": _sha256_text(original_region),
            }
        return {
            "anchor": {"type": "line_range", "value": "L1-L1"},
            "action": "insert_before",
            "content": original_region,
            "expected_before_sha256": _sha256_text(""),
            "expected_after_sha256": _sha256_text(original_region),
        }

    line_start = _index_to_line(post_text, new_start)
    line_end = _index_to_line(post_text, max(new_end - 1, new_start))
    return {
        "anchor": {"type": "line_range", "value": f"L{line_start}-L{line_end}"},
        "action": "replace",
        "content": original_region,
        "expected_before_sha256": _sha256_text(post_text[new_start:new_end]),
        "expected_after_sha256": _sha256_text(original_region),
    }


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


def _validate_operation(op: Dict[str, Any]) -> Tuple[bool, str]:
    op_type = op.get("op")
    if op_type not in {"add", "modify", "delete", "rename"}:
        return False, f"Unsupported op: {op_type}"

    if op_type == "add":
        if "content" not in op or "content_sha256" not in op:
            return False, "Missing content for add"
        return True, "ok"

    if op_type == "modify" and op.get("patch"):
        for hunk in op.get("patch", []):
            anchor = hunk.get("anchor", {})
            if "type" not in anchor or "value" not in anchor:
                return False, "Hunk missing anchor.type or anchor.value"
            if hunk.get("action") not in {"insert_before", "insert_after", "replace", "delete"}:
                return False, "Unsupported hunk action"
            if hunk.get("action") in {"insert_before", "insert_after", "replace"} and "content" not in hunk:
                return False, "Hunk missing content for insert/replace"
        return True, "ok"

    if op_type in {"modify"}:
        if "content" not in op or "content_sha256" not in op:
            return False, f"Missing content for op {op_type}"

    if op_type == "rename" and not op.get("old_path"):
        return False, "Missing old_path for rename"

    return True, "ok"


def _apply_operation(project_root: Path, op: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    op_type = op["op"]
    path = project_root / op["path"]
    old_path = project_root / op.get("old_path", "") if op.get("old_path") else None

    pre_bytes = _read_bytes(path)
    pre_hash = _sha256_bytes(pre_bytes) if pre_bytes is not None else None

    detail = {
        "path": op.get("path"),
        "op": op_type,
        "pre_hash": pre_hash,
        "post_hash": None,
    }

    if op_type == "add":
        if path.exists():
            content = op["content"].encode()
            if _sha256_bytes(content) == _sha256_bytes(pre_bytes or b""):
                detail["post_hash"] = detail["pre_hash"]
                return True, "skipped_existing", detail
            return False, "target exists", detail
        content = op["content"].encode()
        if _sha256_bytes(content) != op["content_sha256"]:
            return False, "content hash mismatch", detail
        _write_bytes(path, content)
        detail["post_hash"] = _sha256_bytes(content)
        return True, "applied", detail

    if op_type == "modify" and op.get("patch"):
        if not path.exists():
            return False, "target missing", detail
        data = pre_bytes or b""
        newline = _detect_newline_style(data)
        had_final_newline = data.endswith(b"\n") or data.endswith(b"\r\n")
        text = data.decode(errors="replace")

        hunks = []
        rollback_hunks = []
        current = text

        for hunk in op.get("patch", []):
            anchor = hunk.get("anchor", {})
            matches, anchor_kind = _find_anchor(current, anchor)
            occurrence = anchor.get("occurrence")
            selected = _select_anchor(matches, occurrence)
            if not matches:
                hunks.append({
                    "status": "CONFLICT_ANCHOR_NOT_FOUND",
                    "anchor_type": anchor_kind,
                })
                return False, "CONFLICT_ANCHOR_NOT_FOUND", {**detail, "hunks": hunks}
            if selected is None:
                hunks.append({
                    "status": "CONFLICT_ANCHOR_AMBIGUOUS",
                    "anchor_type": anchor_kind,
                    "matches": len(matches),
                })
                return False, "CONFLICT_ANCHOR_AMBIGUOUS", {**detail, "hunks": hunks}

            start, end = selected
            region = current[start:end]
            before_hash = _sha256_text(region)
            expected_before = hunk.get("expected_before_sha256")
            expected_after = hunk.get("expected_after_sha256")

            if expected_before and expected_before != before_hash:
                already_applied = False
                if expected_after and expected_after == before_hash:
                    already_applied = True
                else:
                    content = _normalize_newlines(hunk.get("content", ""), newline)
                    candidate, _, _ = _apply_action(current, start, end, hunk.get("action"), content)
                    if candidate == current:
                        already_applied = True
                if already_applied:
                    hunks.append({
                        "status": "SKIPPED_ALREADY_APPLIED",
                        "anchor_type": anchor_kind,
                    })
                    continue
                hunks.append({
                    "status": "CONFLICT_BEFORE_HASH_MISMATCH",
                    "anchor_type": anchor_kind,
                    "expected_before": expected_before,
                    "observed_before": before_hash,
                })
                return False, "CONFLICT_BEFORE_HASH_MISMATCH", {**detail, "hunks": hunks}

            content = _normalize_newlines(hunk.get("content", ""), newline)
            next_text, new_start, new_end = _apply_action(current, start, end, hunk.get("action"), content)
            if next_text == current:
                hunks.append({
                    "status": "SKIPPED_ALREADY_APPLIED",
                    "anchor_type": anchor_kind,
                })
                continue

            if expected_after:
                after_region = next_text[new_start:new_end]
                after_hash = _sha256_text(after_region)
                if expected_after != after_hash:
                    hunks.append({
                        "status": "CONFLICT_AFTER_HASH_MISMATCH",
                        "anchor_type": anchor_kind,
                        "expected_after": expected_after,
                        "observed_after": after_hash,
                    })
                    return False, "CONFLICT_AFTER_HASH_MISMATCH", {**detail, "hunks": hunks}

            rollback_hunks.append(_build_rollback_hunk(next_text, new_start, new_end, region))
            hunks.append({
                "status": "APPLIED",
                "anchor_type": anchor_kind,
            })
            current = next_text

        if current == text:
            detail["post_hash"] = detail["pre_hash"]
            detail["hunks"] = hunks
            detail["rollback_hunks"] = rollback_hunks
            return True, "skipped_no_change", detail

        if newline == "\r\n":
            current = current.replace("\r\n", "\n").replace("\n", "\r\n")
        if had_final_newline and not current.endswith(newline):
            current += newline

        _write_bytes(path, current.encode())
        detail["post_hash"] = _sha256_bytes(current.encode())
        detail["hunks"] = hunks
        detail["rollback_hunks"] = rollback_hunks
        return True, "applied", detail

    if op_type == "modify":
        if not path.exists():
            return False, "target missing", detail
        content = op["content"].encode()
        if _sha256_bytes(content) != op["content_sha256"]:
            return False, "content hash mismatch", detail
        if _sha256_bytes(content) == _sha256_bytes(pre_bytes or b""):
            detail["post_hash"] = detail["pre_hash"]
            return True, "skipped_no_change", detail
        _write_bytes(path, content)
        detail["post_hash"] = _sha256_bytes(content)
        return True, "applied", detail

    if op_type == "delete":
        if not path.exists():
            return True, "skipped_missing", detail
        path.unlink()
        detail["post_hash"] = None
        return True, "applied", detail

    if op_type == "rename":
        if old_path is None or not old_path.exists():
            return False, "old_path missing", detail
        if path.exists():
            return False, "new path exists", detail
        path.parent.mkdir(parents=True, exist_ok=True)
        old_path.rename(path)
        post_bytes = _read_bytes(path)
        detail["post_hash"] = _sha256_bytes(post_bytes) if post_bytes is not None else None
        return True, "applied", detail

    return False, "unsupported", detail


def _build_rollback(op: Dict[str, Any], pre_bytes: Optional[bytes]) -> Dict[str, Any]:
    op_type = op["op"]
    if op_type == "add":
        return {"op": "delete", "path": op["path"], "reason": "rollback add"}
    if op_type == "delete":
        content = pre_bytes.decode() if pre_bytes is not None else ""
        return {
            "op": "add",
            "path": op["path"],
            "reason": "rollback delete",
            "content": content,
            "content_sha256": _sha256_bytes(pre_bytes or b""),
        }
    if op_type == "modify":
        content = pre_bytes.decode() if pre_bytes is not None else ""
        return {
            "op": "modify",
            "path": op["path"],
            "reason": "rollback modify",
            "content": content,
            "content_sha256": _sha256_bytes(pre_bytes or b""),
        }
    if op_type == "rename":
        return {
            "op": "rename",
            "path": op.get("old_path"),
            "old_path": op.get("path"),
            "reason": "rollback rename",
        }
    return {"op": "noop", "path": op.get("path"), "reason": "rollback unsupported"}


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    artifact_store = project_context.get("artifact_store")
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not artifact_store or not sandbox:
        raise RuntimeError("Sandbox or artifact store missing")

    patchset = _load_artifact(artifact_store, "forgescaffold.instrumentation.patchset.json")
    bundle = _load_artifact(artifact_store, "dawn.project.bundle")

    expected_fingerprint = patchset.get("target", {}).get("bundle_content_sha256") or ""
    observed_fingerprint = _compute_inputs_fingerprint(project_root)

    if not expected_fingerprint:
        report = {
            "status": "REFUSED_DRIFT",
            "reason": "missing expected bundle_content_sha256",
            "bundle_content_sha256_expected": expected_fingerprint,
            "bundle_content_sha256_observed": observed_fingerprint,
            "applied_ops": 0,
            "skipped_ops": len(patchset.get("operations", [])),
            "failed_ops": len(patchset.get("operations", [])),
            "operations": [],
        }
        report_path = sandbox.publish("forgescaffold.apply_report.json", "apply_report.json", report, schema="json")
        rollback_path = sandbox.publish("forgescaffold.rollback_patchset.json", "rollback_patchset.json", {"operations": []}, schema="json")
        snapshot_path = sandbox.publish("forgescaffold.workspace_snapshot.json", "workspace_snapshot.json", {"files": []}, schema="json")
        return {
            "status": "SUCCEEDED",
            "outputs": {
                "forgescaffold.apply_report.json": {"path": report_path},
                "forgescaffold.rollback_patchset.json": {"path": rollback_path},
                "forgescaffold.workspace_snapshot.json": {"path": snapshot_path},
            },
            "metrics": {"refused": True},
        }

    if expected_fingerprint != observed_fingerprint:
        report = {
            "status": "REFUSED_DRIFT",
            "reason": "bundle_content_sha256 mismatch",
            "bundle_content_sha256_expected": expected_fingerprint,
            "bundle_content_sha256_observed": observed_fingerprint,
            "applied_ops": 0,
            "skipped_ops": len(patchset.get("operations", [])),
            "failed_ops": len(patchset.get("operations", [])),
            "operations": [],
        }
        report_path = sandbox.publish("forgescaffold.apply_report.json", "apply_report.json", report, schema="json")
        rollback_path = sandbox.publish("forgescaffold.rollback_patchset.json", "rollback_patchset.json", {"operations": []}, schema="json")
        snapshot_path = sandbox.publish("forgescaffold.workspace_snapshot.json", "workspace_snapshot.json", {"files": []}, schema="json")
        return {
            "status": "SUCCEEDED",
            "outputs": {
                "forgescaffold.apply_report.json": {"path": report_path},
                "forgescaffold.rollback_patchset.json": {"path": rollback_path},
                "forgescaffold.workspace_snapshot.json": {"path": snapshot_path},
            },
            "metrics": {"refused": True},
        }

    operations = patchset.get("operations", [])
    scope_violations = []
    for op in operations:
        ok, reason = _scope_allowed(op)
        if not ok:
            scope_violations.append({"path": op.get("path"), "reason": reason})

    if scope_violations:
        report = {
            "status": "REFUSED_SCOPE",
            "reason": "scope violations",
            "violations": scope_violations,
            "bundle_content_sha256_expected": expected_fingerprint,
            "bundle_content_sha256_observed": observed_fingerprint,
            "applied_ops": 0,
            "skipped_ops": len(operations),
            "failed_ops": len(operations),
            "operations": [],
        }
        report_path = sandbox.publish("forgescaffold.apply_report.json", "apply_report.json", report, schema="json")
        rollback_path = sandbox.publish("forgescaffold.rollback_patchset.json", "rollback_patchset.json", {"operations": []}, schema="json")
        snapshot_path = sandbox.publish("forgescaffold.workspace_snapshot.json", "workspace_snapshot.json", {"files": []}, schema="json")
        return {
            "status": "SUCCEEDED",
            "outputs": {
                "forgescaffold.apply_report.json": {"path": report_path},
                "forgescaffold.rollback_patchset.json": {"path": rollback_path},
                "forgescaffold.workspace_snapshot.json": {"path": snapshot_path},
            },
            "metrics": {"refused": True},
        }

    applied = []
    skipped = []
    failed = []
    workspace_snapshot = []
    rollback_ops = []
    best_effort = bool(link_config.get("config", {}).get("best_effort", False))
    force_lock = bool(link_config.get("config", {}).get("force_lock", False))

    policy = load_policy(project_root)
    lock_ttl_minutes = int(policy.get("forgescaffold", {}).get("lock_ttl_minutes", 30))
    acquired, lock_info = acquire_lock(
        project_root,
        project_context.get("pipeline_id", ""),
        patchset.get("patchset_id"),
        lock_ttl_minutes,
        force=force_lock,
    )
    if not acquired:
        status = "REFUSED_LOCK_HELD" if lock_info.get("reason") == "LOCK_HELD" else "REFUSED_LOCK_STALE"
        report = {
            "status": status,
            "reason": lock_info.get("reason"),
            "bundle_content_sha256_expected": expected_fingerprint,
            "bundle_content_sha256_observed": observed_fingerprint,
            "applied_ops": 0,
            "skipped_ops": len(operations),
            "failed_ops": len(operations),
            "operations": [],
            "lock_forced": False,
            "lock_ttl_minutes": lock_ttl_minutes,
            "lock_info": lock_info,
        }
        report_path = sandbox.publish("forgescaffold.apply_report.json", "apply_report.json", report, schema="json")
        rollback_path = sandbox.publish(
            "forgescaffold.rollback_patchset.json",
            "rollback_patchset.json",
            {"operations": []},
            schema="json",
        )
        snapshot_path = sandbox.publish(
            "forgescaffold.workspace_snapshot.json",
            "workspace_snapshot.json",
            {"files": []},
            schema="json",
        )
        return {
            "status": "SUCCEEDED",
            "outputs": {
                "forgescaffold.apply_report.json": {"path": report_path},
                "forgescaffold.rollback_patchset.json": {"path": rollback_path},
                "forgescaffold.workspace_snapshot.json": {"path": snapshot_path},
            },
            "metrics": {"refused": True, "lock": lock_info.get("reason")},
        }

    for op in operations:
        valid, reason = _validate_operation(op)
        if not valid:
            failed.append({"path": op.get("path"), "op": op.get("op"), "reason": reason})
            if not best_effort:
                break
            continue

        target_path = project_root / op["path"]
        pre_bytes = _read_bytes(target_path)
        ok, result, detail = _apply_operation(project_root, op)
        if ok:
            if result.startswith("skipped"):
                skipped_entry = {
                    "path": op.get("path"),
                    "op": op.get("op"),
                    "reason": result,
                    "pre_hash": detail.get("pre_hash"),
                    "post_hash": detail.get("post_hash"),
                }
                if detail.get("hunks"):
                    skipped_entry["hunks"] = detail.get("hunks")
                skipped.append(skipped_entry)
            else:
                applied.append(detail)
                if detail.get("rollback_hunks"):
                    rollback_entry = {
                        "op": "modify",
                        "path": op.get("path"),
                        "reason": "rollback hunks",
                        "patch": detail.get("rollback_hunks"),
                    }
                    if op.get("tags"):
                        rollback_entry["tags"] = op.get("tags")
                    rollback_ops.append(rollback_entry)
                else:
                    rollback_entry = _build_rollback(op, pre_bytes)
                    if op.get("tags"):
                        rollback_entry["tags"] = op.get("tags")
                    rollback_ops.append(rollback_entry)
                workspace_snapshot.append({
                    "path": op.get("path"),
                    "pre_hash": detail.get("pre_hash"),
                    "post_hash": detail.get("post_hash"),
                })
        else:
            failed_entry = {"path": op.get("path"), "op": op.get("op"), "reason": result}
            if detail.get("hunks"):
                failed_entry["hunks"] = detail.get("hunks")
            failed.append(failed_entry)
            if not best_effort:
                break

    if failed and not best_effort:
        # rollback applied ops in reverse order
        for rollback in reversed(rollback_ops):
            _apply_operation(project_root, rollback)
        status = "FAILED"
    else:
        status = "APPLIED" if applied else "SKIPPED"

    report = {
        "status": status,
        "bundle_content_sha256_expected": expected_fingerprint,
        "bundle_content_sha256_observed": observed_fingerprint,
        "applied_ops": len(applied),
        "skipped_ops": len(skipped),
        "failed_ops": len(failed),
        "operations": {
            "applied": applied,
            "skipped": skipped,
            "failed": failed,
        },
        "lock_forced": lock_info.get("lock_forced", False),
        "lock_ttl_minutes": lock_ttl_minutes,
    }

    rollback_patchset = {
        "schema_version": "1.0.1",
        "patchset_id": hashlib.sha256(json.dumps(rollback_ops, sort_keys=True).encode()).hexdigest(),
        "generator": {
            "name": "forgescaffold.apply_patchset.rollback",
            "version": "1.0.0",
        },
        "target": {
            "project_id": project_context.get("project_id"),
            "bundle_content_sha256": observed_fingerprint,
        },
        "operations": rollback_ops,
    }

    report_path = sandbox.publish("forgescaffold.apply_report.json", "apply_report.json", report, schema="json")
    rollback_path = sandbox.publish("forgescaffold.rollback_patchset.json", "rollback_patchset.json", rollback_patchset, schema="json")
    snapshot_path = sandbox.publish("forgescaffold.workspace_snapshot.json", "workspace_snapshot.json", {"files": workspace_snapshot}, schema="json")

    return {
        "status": "SUCCEEDED",
        "outputs": {
            "forgescaffold.apply_report.json": {"path": report_path},
            "forgescaffold.rollback_patchset.json": {"path": rollback_path},
            "forgescaffold.workspace_snapshot.json": {"path": snapshot_path},
        },
        "metrics": {"applied_ops": len(applied), "failed_ops": len(failed)},
    }
