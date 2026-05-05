"""
Add ForgeLedger and ForgedRoot root to sys.path so tests can import
forgeledger.* and integrations.* without installing the packages.
"""
import sys
from pathlib import Path

_FORGELEDGER_ROOT = Path(__file__).parent.parent        # i:\ForgedRoot\ForgeLedger
_FORGEROOT_ROOT   = _FORGELEDGER_ROOT.parent            # i:\ForgedRoot

for _p in (_FORGELEDGER_ROOT, _FORGEROOT_ROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)
