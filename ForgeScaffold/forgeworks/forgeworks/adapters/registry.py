from .base import DomainAdapter, register_adapter
from .ci_change_control import ingest as ci_ingest
from .ci_change_control import normalize as ci_normalize
from .ci_change_control import extract_signals as ci_signals
from .it_ops_runbook import ingest as ops_ingest
from .it_ops_runbook import normalize as ops_normalize
from .it_ops_runbook import extract_signals as ops_signals


def register_builtin_adapters() -> None:
    register_adapter(
        DomainAdapter(
            domain="ci_change_control",
            ingest=ci_ingest,
            normalize=ci_normalize,
            extract_signals=ci_signals,
        )
    )
    register_adapter(
        DomainAdapter(
            domain="it_ops_runbook",
            ingest=ops_ingest,
            normalize=ops_normalize,
            extract_signals=ops_signals,
        )
    )
