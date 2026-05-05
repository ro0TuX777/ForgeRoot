from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from forgeledger.replay_protection import ReplayDetectedError


class DurableReplayProtector:
    """
    Append-only JSONL replay guard.

    Existing event IDs are loaded on initialization. New IDs are written and
    flushed to disk before being added to the in-memory seen set.
    """

    def __init__(self, store_path: Path) -> None:
        self._path = store_path
        self._seen: set[str] = set()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.touch()
        self._load_existing()

    def check_and_register(self, event_id: str) -> None:
        if event_id in self._seen:
            raise ReplayDetectedError(event_id)

        record = {
            "event_id": event_id,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._seen.add(event_id)

    def is_seen(self, event_id: str) -> bool:
        return event_id in self._seen

    def _load_existing(self) -> None:
        with open(self._path, "r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    raw = json.loads(stripped)
                    event_id = raw["event_id"]
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise ValueError(f"Invalid durable replay JSONL at line {line_number}: {exc}") from exc
                if not isinstance(event_id, str) or not event_id:
                    raise ValueError(f"Invalid durable replay event_id at line {line_number}")
                self._seen.add(event_id)
