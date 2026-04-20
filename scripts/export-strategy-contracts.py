#!/usr/bin/env python3
"""Export Python strategy contract surfaces for shared-type generation."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "packages/akshare-mcp/src"))

    from akshare_mcp.contracts.strategy_manager_contract import (  # noqa: PLC0415
        export_strategy_manager_contract_surface,
    )

    payload = {
        "strategy_manager": export_strategy_manager_contract_surface(),
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
