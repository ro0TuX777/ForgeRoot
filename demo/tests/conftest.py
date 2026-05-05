"""
Add ForgedRoot root to sys.path so tests can import demo.governed_agent_demo
and the forgeledger/forgecompliance packages (installed as editable installs).
"""
import sys
from pathlib import Path

_DEMO_ROOT    = Path(__file__).parent.parent        # i:\ForgedRoot\demo
_FORGEROOT    = _DEMO_ROOT.parent                   # i:\ForgedRoot

for _p in (_DEMO_ROOT, _FORGEROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)
