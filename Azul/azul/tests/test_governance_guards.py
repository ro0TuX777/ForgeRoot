import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from azul.governance_guards import evaluate_diff_against_subprocess_guards
from azul.governance_guards import evaluate_no_destructive_remediation


_GUARD_YAML = """\
domain: "system_operations"
unit_id: "external.subprocess"
actions:
  - id: "check_call"
    description: "Execute a system command"
    guard_predicates:
      - "args[0] in ['ls', 'git status', 'whoami']"
      - "kwargs.get('shell') == False"
    risk_tier: 3
    consistency_profile: "atomic"
"""


def _write_guard(catalog_root: Path) -> None:
    catalog_root.mkdir(parents=True, exist_ok=True)
    (catalog_root / "subprocess_guard.yaml").write_text(_GUARD_YAML, encoding="utf-8")


def test_flags_rm_and_shell_true(tmp_path: Path):
    catalog_root = tmp_path / "catalog"
    _write_guard(catalog_root)

    diff_text = """\
--- a/src/app/__init__.py
+++ b/src/app/__init__.py
@@ -1,1 +1,2 @@
+import subprocess
+    subprocess.check_call(['rm', '-rf', '/'], shell=True)
"""

    violations = evaluate_diff_against_subprocess_guards(
        diff_text,
        catalog_root=catalog_root,
    )

    assert len(violations) == 1
    assert "Guard Predicate Violation" in violations[0]
    assert "args[0] 'rm' not in ['ls', 'git status', 'whoami']" in violations[0]
    assert "kwargs.get('shell') expected False but got True" in violations[0]


def test_allows_ls_with_shell_false(tmp_path: Path):
    catalog_root = tmp_path / "catalog"
    _write_guard(catalog_root)

    diff_text = """\
--- a/src/app/__init__.py
+++ b/src/app/__init__.py
@@ -1,1 +1,2 @@
+import subprocess
+    subprocess.check_call(['ls'], shell=False)
"""

    violations = evaluate_diff_against_subprocess_guards(
        diff_text,
        catalog_root=catalog_root,
    )

    assert violations == []


def test_flags_destructive_line_ratio():
    diff_text = """\
--- a/src/service.py
+++ b/src/service.py
@@ -1,10 +1,1 @@
-line1
-line2
-line3
-line4
-line5
-line6
-line7
-line8
-line9
-line10
+line1
"""
    violations = evaluate_no_destructive_remediation(
        diff_text,
        deletion_ratio_threshold=2.0,
        min_deleted_lines=5,
    )
    assert len(violations) == 1
    assert "No-Destructive-Remediation Violation" in violations[0]
    assert "deleted_lines=10" in violations[0]


def test_flags_removed_export_without_replacement():
    diff_text = """\
--- a/src/app.py
+++ b/src/app.py
@@ -1,5 +1,2 @@
-def start_app():
-    return True
-
 def helper():
     return False
"""
    violations = evaluate_no_destructive_remediation(diff_text)
    assert len(violations) == 1
    assert "core export(s) removed without replacement" in violations[0]
    assert "start_app" in violations[0]
