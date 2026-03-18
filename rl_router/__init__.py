import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for subpkg in ["core", "memory", "skills", "rl_router", "gateway"]:
    _p = os.path.join(_ROOT, subpkg)
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
