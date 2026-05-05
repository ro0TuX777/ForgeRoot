import sys
from pathlib import Path

_FORGECOMP_ROOT = Path(__file__).parent.parent   # i:\ForgedRoot\ForgeCompliance
_FORGEROOT_ROOT = _FORGECOMP_ROOT.parent         # i:\ForgedRoot
_FORGELEDGER_ROOT = _FORGEROOT_ROOT / "ForgeLedger"

for _p in (_FORGECOMP_ROOT, _FORGEROOT_ROOT, _FORGELEDGER_ROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)
