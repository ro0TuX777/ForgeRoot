"""
integrations/forge_scaffold.py — ForgeScaffold blast-radius analysis
=====================================================================
Calls the ForgeScaffold ``forgescaffold.system_catalog`` DAWN link to map
the structural impact of a change on a codebase.

ForgeScaffold uses the DAWN link pattern: each link is a ``run.py`` that
takes ``(project_context: dict, link_config: dict) -> dict``.

For Azul's purposes, we run the system_catalog link against the caller's
project root to identify which modules are affected by the target_files.

Returns _ok({"blast_radius": dict}) or _error on failure.
Never raises.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Path resolution ─────────────────────────────────────────────────────────

_FORGE_SCAFFOLD_ROOT = os.environ.get(
    "FORGE_SCAFFOLD_ROOT",
    str(Path(os.environ.get("FORGE_ROOT", str(Path(__file__).resolve().parents[3]))) / "DAWN"),
)

_SYSTEM_CATALOG_LINK = os.environ.get(
    "FORGE_SCAFFOLD_SYSTEM_CATALOG_PATH",
    str(Path(_FORGE_SCAFFOLD_ROOT) / "dawn" / "links" / "forgescaffold.system_catalog" / "run.py"),
)

_DATAFLOW_LINK = os.environ.get(
    "FORGE_SCAFFOLD_DATAFLOW_PATH",
    str(Path(_FORGE_SCAFFOLD_ROOT) / "dawn" / "links" / "forgescaffold.map_dataflow" / "run.py"),
)


def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "ok", "payload": payload}


def _error(code: str, message: str, details: Optional[Dict] = None) -> Dict[str, Any]:
    return {"status": "error", "error": {"code": code, "message": message, "details": details or {}}}


# ── Public API ───────────────────────────────────────────────────────────────

def analyze_blast_radius(
    target_files: List[str],
    project_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Map the blast radius of the given target_files in the project.

    Args:
        target_files: List of file paths affected by the change.
        project_root: Root of the codebase to analyze. Defaults to cwd.

    Returns:
        _ok({"blast_radius": {"units": [...], "affected_files": [...]}})
        _error on failure.  Never raises.
    """
    if not target_files:
        return _ok({"blast_radius": {"units": [], "affected_files": []}})

    try:
        link_path = Path(_SYSTEM_CATALOG_LINK)
        if not link_path.exists():
            return _error(
                "FORGE_SCAFFOLD_UNAVAILABLE",
                f"ForgeScaffold system_catalog link not found at {link_path}",
            )

        spec = importlib.util.spec_from_file_location("forge_scaffold_catalog", link_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        root = project_root or str(Path.cwd())

        # ForgeScaffold system_catalog needs a sandbox and artifact_store for
        # publishing — we use the lightweight standalone path that just assembles
        # units without publishing (calling assemble_units directly).
        units = mod.assemble_units(
            project_root=Path(root),
            project_id="azul_target",
        )

        # Filter to units that overlap with the target files
        affected = _units_touching_files(units, target_files, root)

        return _ok({
            "blast_radius": {
                "units":          affected,
                "affected_files": target_files,
                "total_units":    len(units),
                "affected_count": len(affected),
                "project_root":   root,
            },
        })

    except Exception as exc:
        logger.error(f"[ForgeScaffold] analyze_blast_radius error: {exc}")
        return _error("FORGE_SCAFFOLD_ERROR", str(exc), {"target_files": target_files})


def compute_blast_radius_score(
    affected_unit_ids: List[str],
    all_edges: List[Dict[str, Any]],
    total_unit_count: int,
) -> Dict[str, Any]:
    """Compute a weighted blast radius score using BFS over the dataflow edge graph.

    Algorithm
    ---------
    1. Start from the directly affected unit IDs (depth 0).
    2. BFS outward through the edge graph — each hop increments depth.
    3. Weight each transitively reached unit by 1 / (depth + 1) so direct
       impact counts fully and transitive impact decays with distance.
    4. Sum the weights and normalise to [0.0, 1.0] against total_unit_count.
    5. Isolation score = 1.0 - blast_radius_score (how contained the change is).

    Returns a dict compatible with ForgeGate's Signals schema:
        {
            "blast_radius_score": float,   # 0.0–1.0
            "isolation_score":    float,   # 0.0–1.0 (1 - blast_radius_score)
            "direct_count":       int,
            "transitive_count":   int,
            "max_depth":          int,
            "weighted_reach":     float,
        }
    """
    if not affected_unit_ids or total_unit_count == 0:
        return {
            "blast_radius_score": 0.0,
            "isolation_score": 1.0,
            "direct_count": 0,
            "transitive_count": 0,
            "max_depth": 0,
            "weighted_reach": 0.0,
        }

    # Build adjacency: unit_id → set of units it affects (outgoing edges)
    adjacency: Dict[str, set] = {}
    for edge in all_edges:
        src = edge.get("from", "")
        dst = edge.get("to", "")
        if src and dst:
            adjacency.setdefault(src, set()).add(dst)
            # Treat imports/dependencies as bidirectional impact:
            # if A imports B and B changes, A is also affected
            adjacency.setdefault(dst, set()).add(src)

    visited: Dict[str, int] = {}  # unit_id → depth at which it was first reached
    queue: list = [(uid, 0) for uid in affected_unit_ids]
    for uid in affected_unit_ids:
        visited[uid] = 0

    while queue:
        current, depth = queue.pop(0)
        for neighbour in adjacency.get(current, set()):
            if neighbour not in visited:
                visited[neighbour] = depth + 1
                queue.append((neighbour, depth + 1))

    direct_count = len(affected_unit_ids)
    transitive_count = len(visited) - direct_count
    max_depth = max(visited.values(), default=0)

    # Weighted reach: direct units contribute 1.0 each, transitives decay by depth
    weighted_reach = sum(1.0 / (depth + 1) for depth in visited.values())

    # Normalise against total unit count (capped at 1.0)
    blast_radius_score = min(1.0, weighted_reach / total_unit_count)
    isolation_score = round(1.0 - blast_radius_score, 6)
    blast_radius_score = round(blast_radius_score, 6)

    return {
        "blast_radius_score": blast_radius_score,
        "isolation_score": isolation_score,
        "direct_count": direct_count,
        "transitive_count": transitive_count,
        "max_depth": max_depth,
        "weighted_reach": round(weighted_reach, 4),
    }


def _units_touching_files(
    units: List[Dict[str, Any]],
    target_files: List[str],
    project_root: str,
) -> List[Dict[str, Any]]:
    """Return units whose path overlaps with any target_file."""
    affected = []
    target_stems = {Path(f).stem for f in target_files}
    target_paths = {str(Path(f)) for f in target_files}

    for unit in units:
        unit_path = unit.get("path", "")
        if not unit_path:
            continue
        # Match by stem or path substring
        unit_stem = Path(unit_path).stem
        if unit_stem in target_stems or any(t in unit_path for t in target_paths):
            affected.append(unit)

    return affected
