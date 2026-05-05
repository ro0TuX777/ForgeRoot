from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from forgeledger.backend import (
    AppendResult,
    ChainValidationReport,
    ExportSelector,
    HoldResult,
    HoldSelector,
    LedgerBackend,
    LedgerQuery,
)
from forgeledger.canonical_json import canonical_json
from forgeledger.hash_chain import verify_chain as _verify_chain
from forgeledger.schema import LedgerEvent, event_from_dict


class JsonlBackend(LedgerBackend):
    """
    Append-only JSONL file backend for Phase 1.

    Events are stored one per line as canonical JSON. Legal holds are tracked in
    a sidecar file at <ledger_path>.holds.json. Neither file is ever mutated —
    holds are accumulated as a JSON object keyed by hold_id.
    """

    def __init__(self, ledger_path: Path) -> None:
        self._path = ledger_path
        self._holds_path = Path(str(ledger_path) + ".holds.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.touch()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_holds(self) -> dict:
        if not self._holds_path.exists():
            return {}
        with open(self._holds_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_holds(self, holds: dict) -> None:
        with open(self._holds_path, "w", encoding="utf-8") as f:
            json.dump(holds, f, indent=2)

    def _read_all(self) -> list[LedgerEvent]:
        events = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(event_from_dict(json.loads(line)))
        return events

    def _count_lines(self) -> int:
        count = 0
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count

    # ------------------------------------------------------------------
    # LedgerBackend implementation
    # ------------------------------------------------------------------

    def append_event(self, event: LedgerEvent) -> AppendResult:
        seq = self._count_lines()
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(canonical_json(event) + "\n")
        except OSError as exc:
            return AppendResult(
                success=False,
                event_id=event.event_id,
                event_hash=event.integrity.event_hash,
                sequence_number=seq,
                error=str(exc),
            )
        return AppendResult(
            success=True,
            event_id=event.event_id,
            event_hash=event.integrity.event_hash,
            sequence_number=seq,
        )

    def read_events(self, query: LedgerQuery) -> list[LedgerEvent]:
        result = []
        for event in self._read_all():
            if query.actor_id and event.actor.actor_id != query.actor_id:
                continue
            if query.source_module and event.system_context.source_module != query.source_module:
                continue
            if query.event_types and event.event_type.value not in query.event_types:
                continue
            if query.tenant_id and event.tenant.tenant_id != query.tenant_id:
                continue
            if query.from_time and event.event_time < query.from_time:
                continue
            if query.to_time and event.event_time > query.to_time:
                continue
            result.append(event)
            if len(result) >= query.max_results:
                break
        return result

    def get_latest_hash(self) -> Optional[str]:
        last_line: Optional[str] = None
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    last_line = stripped
        if last_line is None:
            return None
        return json.loads(last_line)["integrity"]["event_hash"]

    def verify_chain(self) -> ChainValidationReport:
        return _verify_chain(self._read_all())

    def apply_legal_hold(self, selector: HoldSelector) -> HoldResult:
        holds = self._load_holds()
        hold_id = str(uuid.uuid4())

        if selector.event_ids:
            held_ids = list(selector.event_ids)
        else:
            events = self.read_events(LedgerQuery(
                from_time=selector.from_time,
                to_time=selector.to_time,
                tenant_id=selector.tenant_id,
                max_results=100_000,
            ))
            held_ids = [e.event_id for e in events]

        holds[hold_id] = {
            "hold_id": hold_id,
            "tenant_id": selector.tenant_id,
            "reason": selector.reason,
            "event_ids": held_ids,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "released": False,
        }
        self._save_holds(holds)
        return HoldResult(applied_count=len(held_ids), hold_id=hold_id)

    def release_legal_hold(self, hold_id: str, reason: str) -> HoldResult:
        holds = self._load_holds()
        if hold_id not in holds:
            return HoldResult(applied_count=0, hold_id=hold_id, error="Hold not found")
        holds[hold_id]["released"] = True
        holds[hold_id]["release_reason"] = reason
        holds[hold_id]["released_at"] = datetime.now(timezone.utc).isoformat()
        self._save_holds(holds)
        return HoldResult(applied_count=len(holds[hold_id]["event_ids"]), hold_id=hold_id)

    def is_on_hold(self, event_id: str) -> bool:
        holds = self._load_holds()
        return any(
            not h["released"] and event_id in h["event_ids"]
            for h in holds.values()
        )

    def export_slice(self, selector: ExportSelector) -> dict:
        events = self.read_events(LedgerQuery(
            from_time=selector.from_time,
            to_time=selector.to_time,
            tenant_id=selector.tenant_id,
            max_results=100_000,
        ))
        chain_report = self.verify_chain()
        return {
            "events": [json.loads(canonical_json(e)) for e in events],
            "event_count": len(events),
            "chain_valid": chain_report.valid,
            "framework_profiles": selector.framework_profiles or [],
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

    def health_check(self) -> dict:
        try:
            ok = self._path.exists() and self._path.is_file()
            if not ok:
                return {"healthy": False, "backend_type": "jsonl", "path": str(self._path)}
            events = self._read_all()
            last_id = events[-1].event_id if events else None
            return {
                "healthy": True,
                "backend_type": "jsonl",
                "path": str(self._path),
                "event_count": len(events),
                "last_event_id": last_id,
            }
        except Exception as exc:
            return {"healthy": False, "backend_type": "jsonl", "error": str(exc)}
