"""Root conftest — ensures 'backend/' is on sys.path so ``app.*`` imports resolve."""

import sys
from pathlib import Path

_backend_dir = str(Path(__file__).resolve().parent / "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
