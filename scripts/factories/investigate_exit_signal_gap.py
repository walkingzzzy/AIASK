#!/usr/bin/env python3
"""Exit signal gap investigation — thin wrapper over FactoryDiagnosticsService (P1-A3)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "akshare-mcp" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "strategy-factory" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "aiask-quant-core" / "src"))


def main() -> int:
    try:
        from akshare_mcp.storage.sqlite import get_db
        from akshare_mcp.services.factory_diagnostics import investigate_exit_signal_gap
    except Exception as exc:
        print(f"import failed: {exc}")
        return 2

    db = get_db()
    asyncio.run(db.initialize())
    payload = investigate_exit_signal_gap(db, sample_limit=10)
    gap = payload.get("exit_gap") or {}

    print("=" * 80)
    print("Exit Signal Gap Investigation (service-backed)")
    print("=" * 80)
    print(f"exit_signals:                 {gap.get('exit_signals')}")
    print(f"strategies_no_exit_order:     {gap.get('strategies_with_exit_signal_no_order')}")
    print(f"exit_signals_in_universe:     {gap.get('exit_signals_in_execution_universe')}")
    print(f"execution_universe_size:      {gap.get('execution_universe_size')}")
    print("-" * 80)
    print("exit_funnel:")
    print(json.dumps(payload.get("exit_funnel") or {}, ensure_ascii=False, indent=2))
    print("-" * 80)
    print("sample_strategies:")
    for item in gap.get("sample_strategies") or []:
        print(
            f"  - {str(item.get('strategy_id') or '')[:12]}... "
            f"status={item.get('status')} incubating={item.get('incubating')} "
            f"exit_signals={item.get('exit_signal_count')} open={item.get('open_positions')}"
        )
    print("-" * 80)
    print("likely_causes:")
    for cause in gap.get("likely_causes") or []:
        print(f"  - {cause}")
    print("-" * 80)
    print("recommendations:")
    for rec in gap.get("recommendations") or []:
        print(f"  - {rec}")
    if payload.get("error"):
        print(f"ERROR: {payload['error']}")
        return 1
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
