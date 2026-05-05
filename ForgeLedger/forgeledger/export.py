from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from forgeledger.backend import ExportSelector, LedgerQuery

if TYPE_CHECKING:
    from forgeledger.backend import LedgerBackend


def export_slice_to_file(
    backend: "LedgerBackend",
    selector: ExportSelector,
    output_path: Path,
) -> dict:
    """
    Write a filtered JSONL slice of ledger events to output_path.
    Returns a summary dict (used as the basis for the Phase 3 evidence package manifest).
    """
    from forgeledger.canonical_json import canonical_json

    events = backend.read_events(LedgerQuery(
        from_time=selector.from_time,
        to_time=selector.to_time,
        tenant_id=selector.tenant_id,
        max_results=100_000,
    ))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for event in events:
            f.write(canonical_json(event) + "\n")

    chain_report = backend.verify_chain()

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "event_count": len(events),
        "output_path": str(output_path),
        "chain_valid": chain_report.valid,
        "framework_profiles": selector.framework_profiles or [],
        "selector": {
            "from_time": selector.from_time,
            "to_time": selector.to_time,
            "tenant_id": selector.tenant_id,
        },
    }
