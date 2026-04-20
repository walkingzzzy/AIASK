from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
PYTHON_SRC_PATHS = [
    REPO_ROOT / "packages/strategy-factory/src",
    REPO_ROOT / "packages/akshare-mcp/src",
]

for src_path in PYTHON_SRC_PATHS:
    resolved = str(src_path)
    if resolved not in sys.path:
        sys.path.insert(0, resolved)
