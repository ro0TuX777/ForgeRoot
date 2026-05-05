"""ForgeAtlas — environment variable configuration.

All settings have in-code defaults so the service runs without any
environment variables set (useful for tests and local dev).
"""

from __future__ import annotations

import os
import pathlib

# Repository root (ForgedRoot) — used to locate the default action catalog.
_FORGE_ROOT = pathlib.Path(
    os.environ.get(
        "FORGE_ROOT",
        str(pathlib.Path(__file__).resolve().parents[2]),
    )
)

_DAWN_CATALOG_PATH = _FORGE_ROOT / "DAWN" / "action_catalogs"
_ROOT_CATALOG_PATH = _FORGE_ROOT / "action_catalogs"
_DEFAULT_CATALOG_PATH = (
    _DAWN_CATALOG_PATH
    if _DAWN_CATALOG_PATH.exists()
    else _ROOT_CATALOG_PATH
)

# Path to the action_catalogs/ directory.
# Override via FORGE_ATLAS_CATALOG_PATH.
CATALOG_PATH: str = os.environ.get(
    "FORGE_ATLAS_CATALOG_PATH",
    str(_DEFAULT_CATALOG_PATH),
)

# Session ID used when no session_id is supplied in the query.
DEFAULT_SESSION_ID: str = os.environ.get(
    "FORGE_ATLAS_DEFAULT_SESSION_ID",
    "forge-atlas-anonymous",
)

# Default maximum results per query.
DEFAULT_MAX_RESULTS: int = int(
    os.environ.get("FORGE_ATLAS_DEFAULT_MAX_RESULTS", "10")
)

# Cosine similarity threshold for semantic search (Phase 3).
SIMILARITY_THRESHOLD: float = float(
    os.environ.get("ACTION_DISCOVERY_SIMILARITY_THRESHOLD", "0.3")
)

# Embedding model name (Phase 3).
EMBEDDING_MODEL: str = os.environ.get(
    "FORGE_ATLAS_EMBEDDING_MODEL",
    "all-MiniLM-L6-v2",
)
