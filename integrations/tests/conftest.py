import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FORGELEDGER = ROOT / "ForgeLedger"
FORGECOMPLIANCE = ROOT / "ForgeCompliance"
for path in (ROOT, FORGELEDGER, FORGECOMPLIANCE):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from forgeledger.jsonl_backend import JsonlBackend


@pytest.fixture
def backend(tmp_path):
    return JsonlBackend(tmp_path / "ledger.jsonl")


@pytest.fixture
def tenant_kwargs():
    return {
        "tenant_id": "tenant-001",
        "customer_boundary": "customer-a",
        "data_residency": "NZ",
    }
