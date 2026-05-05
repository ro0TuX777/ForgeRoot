from dataclasses import dataclass
from typing import Callable, Dict


class AdapterError(Exception):
    pass


@dataclass(frozen=True)
class DomainAdapter:
    domain: str
    ingest: Callable[[str, str], None]
    normalize: Callable[[str, str], Dict]
    extract_signals: Callable[[str, str], None]


_REGISTRY: Dict[str, DomainAdapter] = {}


def register_adapter(adapter: DomainAdapter) -> None:
    _REGISTRY[adapter.domain] = adapter


def get_adapter(domain: str) -> DomainAdapter:
    adapter = _REGISTRY.get(domain)
    if not adapter:
        raise AdapterError(f"unsupported domain: {domain}")
    return adapter
