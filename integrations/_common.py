from __future__ import annotations

from forgeledger.backend import LedgerBackend, LedgerQuery
from forgeledger.schema import LedgerEvent
from integrations.types import (
    normalize_azul_output,
    normalize_concord_output,
    normalize_forgegate_output,
    normalize_warden_output,
)


def control_tags_from_frameworks(frameworks: list[str], defaults: list[str]) -> list[str]:
    tags = list(defaults)
    for framework in frameworks:
        if framework == "NZISM":
            tags.append("NZISM.LOGGING.EVENT_CAPTURE")
        elif framework == "SOC2":
            tags.append("SOC2.CC7.2")
        elif framework == "NIST_CSF_2_0":
            tags.append("NIST_CSF.GV")
        elif framework == "HIPC_2020":
            tags.append("HIPC_2020.GOVERNANCE")
    return sorted(set(tags))


def stored_event_by_id(backend: LedgerBackend, event_id: str) -> LedgerEvent:
    for event in backend.read_events(LedgerQuery(max_results=100_000)):
        if event.event_id == event_id:
            return event
    raise LookupError(f"Stored event not found: {event_id}")
