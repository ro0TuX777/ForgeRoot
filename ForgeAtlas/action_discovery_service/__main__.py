"""ForgeAtlas — Docker entrypoint (P1-7).

Validates service health at startup, logs the catalog summary, and exits.

Usage (Docker CMD):
    python -m action_discovery_service

Exit codes:
    0 — healthy or degraded (service usable)
    1 — unhealthy (no contracts loaded or catalog missing)

Logs (written to stdout for Docker log capture):
    ActionDiscovery startup: N contracts loaded, M failed, semantic search enabled/disabled
    Catalog version: sha256:...
    Service ready.   (status: healthy | degraded)

  or on failure:
    Service UNHEALTHY: ...
"""

from __future__ import annotations

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)

# Importing the service module executes the module-level startup
# (catalog load + semantic embed + startup log).
from action_discovery_service.run import health  # noqa: E402

h = health()

if h["status"] == "unhealthy":
    logging.error(
        "Service UNHEALTHY — %d contracts registered, %d failures. "
        "Check catalog path and YAML manifests.",
        h["contracts_registered"],
        h["contracts_failed"],
    )
    sys.exit(1)

logging.info(
    "Service ready.  status=%s  contracts=%d  semantic=%s  version=%.16s",
    h["status"],
    h["contracts_registered"],
    "enabled" if h["semantic_search_enabled"] else "disabled",
    h["catalog_version"],
)
