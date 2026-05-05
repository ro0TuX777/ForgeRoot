"""
ForgeScaffold Coding Context
==============================

Provides every SAM Coder LLM with structured pre-flight context before coding:
  1. System Catalog  — what modules exist and their roles
  2. Dataflow Map    — what the target file connects to (impact radius)
  3. Test Matrix     — what success looks like before a single line is written

Calls ForgeScaffold's link run.py functions directly (no DAWN runtime needed),
making this a pure-Python integration compatible with the SAM ecosystem.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── ForgeScaffold source path ────────────────────────────────────────────────
FS_ROOT = Path(__file__).resolve().parents[4]  # ForgeScaffold repo root (contains dawn_extensions/)
FS_LINKS = FS_ROOT / "dawn_extensions" / "links"
FORGEWORKS_ROOT = Path(__file__).resolve().parents[3]  # forgeworks Python package root


def _link_run_py(link_name: str) -> Path:
    """Resolve link id (e.g. ``forgescaffold.system_catalog``) to a ``run.py`` path.

    Some links keep the full dotted id as their directory name
    (``forgescaffold.apply_patchset``); others omit the ``forgescaffold.`` prefix
    (``system_catalog``, ``map_dataflow``). Try full id first, then the suffix.
    """
    candidates = [FS_LINKS / link_name]
    if link_name.startswith("forgescaffold."):
        candidates.append(FS_LINKS / link_name[len("forgescaffold.") :])
    for base in candidates:
        run_py = base / "run.py"
        if run_py.is_file():
            return run_py
    tried = ", ".join(str(c / "run.py") for c in candidates)
    raise ImportError(f"ForgeScaffold link not found for {link_name!r} (tried {tried})")


def _import_fs_module(link_name: str):
    """Dynamically import a ForgeScaffold link's run.py as a module."""
    import importlib.util

    run_py = _link_run_py(link_name)
    safe = link_name.replace(".", "_")
    spec = importlib.util.spec_from_file_location(f"fs_{safe}", run_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ForgeScaffoldCodingContext:
    """
    Pre-flight coding context loader for SAM's Coder LLM.

    Usage:
        ctx = ForgeScaffoldCodingContext(project_root=SAM_ROOT)
        ctx.build(target_file="sam/evolution/evolutionary_controller.py")
        prompt_block = ctx.format_prompt_section()
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or FORGEWORKS_ROOT
        self.catalog: Dict[str, Any] = {}
        self.dataflow: Dict[str, Any] = {}
        self.relevant_units: List[Dict[str, Any]] = []
        self.impact_units: List[Dict[str, Any]] = []
        self._built = False

    def build(self, target_file: str) -> "ForgeScaffoldCodingContext":
        """
        Run catalog + dataflow extraction for the project and cache results.
        Safe to call multiple times — re-uses cache after first build.
        """
        try:
            self._build_catalog()
            self._build_dataflow()
            self._resolve_relevant_units(target_file)
            self._build_impact_radius(target_file)
            self._built = True
            logger.info(
                f"🔐 ForgeScaffold context built: {len(self.relevant_units)} relevant "
                f"units, {len(self.impact_units)} impacted modules"
            )
        except Exception as e:
            logger.warning(f"ForgeScaffold context build failed (non-fatal): {e}")
        return self

    def _build_catalog(self):
        """Run system_catalog extraction directly."""
        try:
            fs_catalog = _import_fs_module("forgescaffold.system_catalog")
            units = fs_catalog.assemble_units(self.project_root, "forgeworks")
            self.catalog = {"project_id": "forgeworks", "units": units}
        except Exception as e:
            logger.warning(f"Catalog extraction failed: {e}")
            self.catalog = {"project_id": "forgeworks", "units": []}

    def _build_dataflow(self):
        """Run dataflow map extraction directly (AST-based)."""
        try:
            fs_dataflow = _import_fs_module("forgescaffold.map_dataflow")

            units_by_id = {u["id"]: u for u in self.catalog.get("units", [])}
            module_units = {k: v for k, v in units_by_id.items() if v.get("type") == "module"}
            datastore_units = {k: v for k, v in units_by_id.items() if v.get("type") == "datastore"}
            service_units = {k: v for k, v in units_by_id.items() if v.get("type") == "service"}
            external_units = {k: v for k, v in units_by_id.items() if v.get("type") == "external_dependency"}

            external_index = fs_dataflow.build_external_index(external_units)
            module_sources = fs_dataflow.gather_module_sources(self.project_root, module_units)

            edges = []
            seen = set()
            module_ids = set(module_units.keys())

            for module_id, file_paths in module_sources.items():
                for src_file in file_paths:
                    imports = fs_dataflow.extract_imports_from_file(src_file)
                    for import_name, lineno in imports:
                        target = fs_dataflow.match_module(import_name, module_ids)
                        evidence = {
                            "file": fs_dataflow.readable_relpath(self.project_root, src_file),
                            "line": lineno,
                            "note": import_name,
                        }
                        if target:
                            fs_dataflow.add_edge(edges, seen, module_id, target, "imports", evidence)
                        else:
                            key = import_name.split(".")[0].lower()
                            ext_target = external_index.get(key)
                            if ext_target:
                                fs_dataflow.add_edge(edges, seen, module_id, ext_target, "imports", evidence)

            nodes = [
                {"id": uid, "type": u.get("type"), "path": u.get("path")}
                for uid, u in sorted(units_by_id.items())
            ]
            self.dataflow = {"edges": edges, "nodes": nodes}
        except Exception as e:
            logger.warning(f"Dataflow extraction failed: {e}")
            self.dataflow = {"edges": [], "nodes": []}

    def _resolve_relevant_units(self, target_file: str):
        """Find catalog units whose path contains the target file."""
        target_norm = target_file.replace("\\", "/").lower()
        self.relevant_units = [
            u for u in self.catalog.get("units", [])
            if target_norm in (u.get("path") or "").replace("\\", "/").lower()
            or (u.get("path") or "").replace("\\", "/").lower() in target_norm
        ]

    def _build_impact_radius(self, target_file: str):
        """Find all modules that import from (or are imported by) the target file."""
        if not self.relevant_units:
            return

        target_ids = {u["id"] for u in self.relevant_units}
        impacted_ids = set()
        for edge in self.dataflow.get("edges", []):
            if edge.get("from") in target_ids or edge.get("to") in target_ids:
                impacted_ids.add(edge.get("from"))
                impacted_ids.add(edge.get("to"))

        impacted_ids -= target_ids  # exclude the target itself
        units_by_id = {u["id"]: u for u in self.catalog.get("units", [])}
        self.impact_units = [units_by_id[uid] for uid in impacted_ids if uid in units_by_id]

    def format_prompt_section(self) -> str:
        """
        Returns a Markdown block ready to prepend to the Coder LLM prompt.
        Keeps output concise — LLM context budget matters.
        """
        if not self._built:
            return ""

        lines = ["## 🏗️ ForgeScaffold Pre-Flight Context\n"]

        # --- Relevant Units ---
        if self.relevant_units:
            lines.append("### Target Module(s)")
            for u in self.relevant_units[:5]:
                lines.append(f"- **{u['id']}** (`{u.get('path', '?')}`) — type: `{u.get('type', '?')}`")
            lines.append("")

        # --- Impact Radius ---
        if self.impact_units:
            lines.append(f"### Impact Radius ({len(self.impact_units)} dependent modules)")
            lines.append("> These modules import or are imported by your target. Changes here ripple outward.")
            for u in self.impact_units[:10]:
                lines.append(f"- `{u['id']}` (`{u.get('path', '?')}`)")
            lines.append("")

        # --- Catalog summary ---
        total_units = len(self.catalog.get("units", []))
        total_edges = len(self.dataflow.get("edges", []))
        lines.append(f"### Codebase Snapshot")
        lines.append(f"- Total modules catalogued: **{total_units}**")
        lines.append(f"- Total dataflow edges: **{total_edges}**")
        lines.append("")

        lines.append("---")
        lines.append(
            "> **ForgeScaffold Contract**: Your code proposal MUST include `success_criteria` — "
            "a list of statements that define what 'done' looks like before any file is written."
        )

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relevant_units": self.relevant_units,
            "impact_units": self.impact_units,
            "total_catalog_units": len(self.catalog.get("units", [])),
            "total_dataflow_edges": len(self.dataflow.get("edges", [])),
        }
