from __future__ import annotations

import dataclasses
import json
from enum import Enum
from typing import Any


def _to_serializable(obj: Any) -> Any:
    """Recursively convert dataclasses and enums to JSON-safe primitives."""
    if obj is None:
        return None
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float, str)):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: _to_serializable(getattr(obj, f.name))
            for f in dataclasses.fields(obj)
        }
    if isinstance(obj, list):
        return [_to_serializable(i) for i in obj]
    if isinstance(obj, dict):
        return {str(k): _to_serializable(v) for k, v in obj.items()}
    return obj


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8 safe."""
    return json.dumps(
        _to_serializable(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
