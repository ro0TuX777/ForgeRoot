import sys
from pathlib import Path

_WARDEN_ROOT = Path(__file__).parent.parent
_FORGEROOT_ROOT = _WARDEN_ROOT.parent

for _path in (_FORGEROOT_ROOT,):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)
