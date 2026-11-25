"""Makes the repo's shared modules (common/) importable from this service."""

import sys
from pathlib import Path

_COMMON = str(Path(__file__).resolve().parent.parent / "common")
if _COMMON not in sys.path:
    sys.path.insert(0, _COMMON)
