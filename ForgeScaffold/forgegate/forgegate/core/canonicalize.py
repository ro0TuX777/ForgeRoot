import json
from typing import Any, Dict, Iterable, List


VOLATILE_FIELDS = {"nonce", "timestamp", "run_id", "request_id"}


def strip_volatile(data: Dict[str, Any], volatile_fields: Iterable[str] = VOLATILE_FIELDS) -> Dict[str, Any]:
    cleaned = {}
    for key, value in data.items():
        if key in volatile_fields:
            continue
        if isinstance(value, dict):
            cleaned[key] = strip_volatile(value, volatile_fields)
        elif isinstance(value, list):
            cleaned[key] = [strip_volatile(v, volatile_fields) if isinstance(v, dict) else v for v in value]
        else:
            cleaned[key] = value
    return cleaned


def _looks_like_context_ref_list(items: List[Any]) -> bool:
    if not items:
        return False
    if not all(isinstance(x, dict) for x in items):
        return False
    for item in items:
        if "ref_type" not in item or "ref_id" not in item:
            return False
    return True


def _sort_context_refs(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def keyfn(item: Dict[str, Any]):
        span = item.get("span") or {}
        return (str(item.get("ref_type")), str(item.get("ref_id")), int(span.get("start", -1)), int(span.get("end", -1)))

    return sorted(items, key=keyfn)


def normalize_for_canonicalization(data: Any) -> Any:
    if isinstance(data, dict):
        return {key: normalize_for_canonicalization(value) for key, value in data.items()}
    if isinstance(data, list):
        normalized = [normalize_for_canonicalization(value) for value in data]
        if _looks_like_context_ref_list(normalized):
            return _sort_context_refs(normalized)  # type: ignore[arg-type]
        return normalized
    return data


def canonical_json(data: Any) -> str:
    normalized = normalize_for_canonicalization(data)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
