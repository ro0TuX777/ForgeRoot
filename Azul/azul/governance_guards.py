"""
governance_guards.py — catalog-driven guard checks for risky diff patterns.

This module wires simple YAML guard contracts into Azul verdicting.
Current focus:
  - unit_id: external.subprocess
  - action id: subprocess call name (e.g., check_call)
  - guard_predicates:
      * args[0] in [...]
      * kwargs.get('shell') == False/True

If a diff introduces a subprocess call that violates these predicates,
Azul should reject with a specific "Guard Predicate Violation" reason.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_ARGS_IN_RE = re.compile(r"^args\[(\d+)\]\s+in\s+(.+)$")
_KW_EQ_RE = re.compile(
    r"""^kwargs\.get\((['"])(?P<key>[^'"]+)\1\)\s*==\s*(?P<value>.+)$"""
)
_PY_DEF_RE = re.compile(r"^\s*def\s+([A-Za-z_]\w*)\s*\(")
_PY_CLASS_RE = re.compile(r"^\s*class\s+([A-Za-z_]\w*)\s*(?:\(|:)")
_JS_EXPORT_FN_RE = re.compile(r"^\s*export\s+(?:async\s+)?function\s+([A-Za-z_]\w*)\s*\(")
_JS_EXPORT_CONST_RE = re.compile(r"^\s*export\s+(?:const|let|var)\s+([A-Za-z_]\w*)\s*=")
_JS_MODULE_EXPORT_RE = re.compile(r"^\s*module\.exports\.([A-Za-z_]\w*)\s*=")


@dataclass
class SubprocessGuardRule:
    action_id: str
    allowed_args0: Optional[List[str]] = None
    required_kwargs: Dict[str, Any] = field(default_factory=dict)
    source_file: str = ""


@dataclass
class SubprocessInvocation:
    action_id: str
    file_path: str
    line_no: Optional[int]
    command_candidates: List[str]
    kwargs: Dict[str, Any]

    def location(self) -> str:
        if self.file_path and self.line_no:
            return f"{self.file_path}:{self.line_no}"
        if self.file_path:
            return self.file_path
        return "<diff>"


def _default_catalog_root() -> Path:
    root = os.environ.get("FORGE_ATLAS_CATALOG_PATH")
    if root:
        return Path(root).resolve()
    return (Path(__file__).resolve().parents[2] / "action_catalogs").resolve()


def _load_yaml(path: Path) -> Optional[Dict[str, Any]]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _parse_predicates(
    predicates: List[str],
) -> tuple[Optional[List[str]], Dict[str, Any]]:
    allowed_args0: Optional[List[str]] = None
    required_kwargs: Dict[str, Any] = {}

    for predicate in predicates:
        if not isinstance(predicate, str):
            continue
        text = predicate.strip()

        args_match = _ARGS_IN_RE.match(text)
        if args_match:
            arg_index = int(args_match.group(1))
            rhs = args_match.group(2).strip()
            if arg_index == 0:
                try:
                    values = ast.literal_eval(rhs)
                    if isinstance(values, list):
                        allowed_args0 = [str(v) for v in values]
                except Exception:
                    pass
            continue

        kw_match = _KW_EQ_RE.match(text)
        if kw_match:
            key = kw_match.group("key")
            raw_value = kw_match.group("value").strip()
            if raw_value in ("True", "False"):
                required_kwargs[key] = (raw_value == "True")
            else:
                try:
                    required_kwargs[key] = ast.literal_eval(raw_value)
                except Exception:
                    required_kwargs[key] = raw_value

    return allowed_args0, required_kwargs


def load_subprocess_rules(catalog_root: Optional[str | Path] = None) -> List[SubprocessGuardRule]:
    root = Path(catalog_root).resolve() if catalog_root is not None else _default_catalog_root()
    if not root.exists():
        return []

    rules: List[SubprocessGuardRule] = []
    for path in sorted(root.rglob("*.yaml")):
        data = _load_yaml(path)
        if not data:
            continue

        if data.get("unit_id") != "external.subprocess":
            continue

        actions = data.get("actions")
        if not isinstance(actions, list):
            continue

        for action in actions:
            if not isinstance(action, dict):
                continue
            action_id = action.get("id")
            if not action_id:
                continue
            predicates = action.get("guard_predicates", [])
            if not isinstance(predicates, list):
                predicates = []
            allowed_args0, required_kwargs = _parse_predicates(predicates)
            rules.append(
                SubprocessGuardRule(
                    action_id=str(action_id),
                    allowed_args0=allowed_args0,
                    required_kwargs=required_kwargs,
                    source_file=str(path),
                )
            )

    return rules


def _extract_command_candidates(node: ast.AST) -> List[str]:
    # subprocess.check_call(['git', 'status']) -> candidates include "git" and "git status"
    if isinstance(node, (ast.List, ast.Tuple)):
        values: List[str] = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                values.append(elt.value.strip())
            else:
                break
        if not values:
            return []
        candidates = [values[0]]
        if len(values) >= 2:
            candidates.append(f"{values[0]} {values[1]}")
        return [c for c in candidates if c]

    # subprocess.check_call("git status", shell=True) -> candidates include full and first token
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        text = node.value.strip()
        if not text:
            return []
        first = text.split()[0]
        return [text, first] if text != first else [first]

    return []


def _literal_or_unknown(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    return "<dynamic>"


def _parse_subprocess_invocations(diff_text: str) -> List[SubprocessInvocation]:
    invocations: List[SubprocessInvocation] = []
    file_path = ""
    line_no: Optional[int] = None

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ b/"):
            file_path = raw_line[6:].strip()
            line_no = None
            continue

        if raw_line.startswith("@@"):
            match = _HUNK_RE.match(raw_line)
            if match:
                line_no = int(match.group(1)) - 1
            continue

        if line_no is None:
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            line_no += 1
            code = raw_line[1:]
            if "subprocess." not in code:
                continue

            try:
                tree = ast.parse(code.lstrip())
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                ):
                    continue

                kwargs: Dict[str, Any] = {}
                for kw in node.keywords:
                    if kw.arg is None:
                        continue
                    kwargs[kw.arg] = _literal_or_unknown(kw.value)

                arg0_candidates: List[str] = []
                if node.args:
                    arg0_candidates = _extract_command_candidates(node.args[0])

                invocations.append(
                    SubprocessInvocation(
                        action_id=node.func.attr,
                        file_path=file_path,
                        line_no=line_no,
                        command_candidates=arg0_candidates,
                        kwargs=kwargs,
                    )
                )
            continue

        if raw_line.startswith("-") and not raw_line.startswith("---"):
            continue
        if raw_line.startswith("\\ No newline at end of file"):
            continue

        line_no += 1

    return invocations


def evaluate_diff_against_subprocess_guards(
    diff_text: str,
    *,
    catalog_root: Optional[str | Path] = None,
) -> List[str]:
    """Return human-readable guard violations for subprocess calls in a diff."""
    if not diff_text.strip():
        return []

    rules = load_subprocess_rules(catalog_root=catalog_root)
    if not rules:
        return []

    violations: List[str] = []
    seen: set[str] = set()
    invocations = _parse_subprocess_invocations(diff_text)
    if not invocations:
        return []

    rules_by_action: Dict[str, List[SubprocessGuardRule]] = {}
    for rule in rules:
        rules_by_action.setdefault(rule.action_id, []).append(rule)

    for invocation in invocations:
        action_rules = rules_by_action.get(invocation.action_id, [])
        for rule in action_rules:
            checks: List[str] = []

            if rule.allowed_args0 is not None:
                allowed = set(rule.allowed_args0)
                if not any(candidate in allowed for candidate in invocation.command_candidates):
                    actual = invocation.command_candidates[0] if invocation.command_candidates else "<dynamic>"
                    checks.append(f"args[0] '{actual}' not in {rule.allowed_args0}")

            for key, expected in rule.required_kwargs.items():
                actual = invocation.kwargs.get(key, "<missing>")
                if actual != expected:
                    checks.append(f"kwargs.get('{key}') expected {expected} but got {actual}")

            if checks:
                detail = "; ".join(checks)
                violation = (
                    "Guard Predicate Violation: "
                    f"external.subprocess.{invocation.action_id} at {invocation.location()} -> {detail}"
                )
                if violation in seen:
                    continue
                seen.add(violation)
                violations.append(violation)

    return violations


def _extract_core_export_name(line: str) -> str:
    for pattern in (
        _PY_DEF_RE,
        _PY_CLASS_RE,
        _JS_EXPORT_FN_RE,
        _JS_EXPORT_CONST_RE,
        _JS_MODULE_EXPORT_RE,
    ):
        match = pattern.match(line)
        if match:
            return str(match.group(1))
    return ""


def evaluate_no_destructive_remediation(
    diff_text: str,
    *,
    deletion_ratio_threshold: float = 2.0,
    min_deleted_lines: int = 12,
) -> List[str]:
    """
    Reject highly destructive remediation patches.

    Rules:
      1) Reject if deleted lines are much higher than added lines.
      2) Reject if core exported symbols are removed without replacement.
    """
    if not diff_text.strip():
        return []

    added = 0
    deleted = 0
    removed_exports: set[str] = set()
    added_exports: set[str] = set()

    for raw in diff_text.splitlines():
        if raw.startswith(("+++", "---", "@@")):
            continue
        if raw.startswith("-"):
            deleted += 1
            export_name = _extract_core_export_name(raw[1:])
            if export_name:
                removed_exports.add(export_name)
            continue
        if raw.startswith("+"):
            added += 1
            export_name = _extract_core_export_name(raw[1:])
            if export_name:
                added_exports.add(export_name)

    violations: List[str] = []
    effective_added = max(added, 1)
    ratio = deleted / float(effective_added)
    if deleted >= min_deleted_lines and ratio >= deletion_ratio_threshold:
        violations.append(
            "No-Destructive-Remediation Violation: "
            f"deleted_lines={deleted}, added_lines={added}, ratio={ratio:.2f} "
            f"(threshold={deletion_ratio_threshold:.2f})"
        )

    removed_without_replacement = sorted(name for name in removed_exports if name not in added_exports)
    if removed_without_replacement:
        violations.append(
            "No-Destructive-Remediation Violation: core export(s) removed without replacement -> "
            + ", ".join(removed_without_replacement)
        )

    return violations
