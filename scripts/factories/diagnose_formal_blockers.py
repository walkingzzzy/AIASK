#!/usr/bin/env python3
"""Formal blockers diagnose script — thin wrapper over FactoryDiagnosticsService (P0-C)."""

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
        from akshare_mcp.services.factory_diagnostics import get_factory_diagnostics_service
    except Exception as exc:
        print(f"import failed: {exc}")
        return 2

    db = get_db()
    asyncio.run(db.initialize())
    payload = get_factory_diagnostics_service().collect(db, top_n=20)

    print("=" * 80)
    print("Factory Formal Diagnostics (service-backed)")
    print("=" * 80)
    print(f"formal_count:   {payload.get('formal_count')}")
    print(f"observe_count:  {payload.get('observe_count')}")
    print(f"incubating:     {payload.get('incubating_count')}")
    print(f"signal_id_cov:  {payload.get('signal_id_coverage')}")
    print(f"orders:         {payload.get('orders_with_signal_id')}/{payload.get('orders_total')}")
    print("-" * 80)
    print("status_histogram:")
    for k, v in (payload.get("status_histogram") or {}).items():
        print(f"  {k}: {v}")
    print("-" * 80)
    print("hard_gate_histogram:")
    for k, v in (payload.get("hard_gate_histogram") or {}).items():
        print(f"  {k}: {v}")
    print("-" * 80)
    print("top_blockers:")
    for item in payload.get("top_blockers") or []:
        print(f"  [{item.get('count')}] {item.get('code')}")
    print("-" * 80)
    print("exit_funnel:")
    print(json.dumps(payload.get("exit_funnel") or {}, ensure_ascii=False, indent=2))
    print("-" * 80)
    print("evidence_gaps:")
    print(json.dumps(payload.get("evidence_gaps") or [], ensure_ascii=False, indent=2))
    print("-" * 80)
    print("next_actions:")
    for item in payload.get("next_actions") or []:
        print(f"  - {item.get('code')}: {item.get('detail')}")
    if payload.get("error"):
        print(f"ERROR: {payload['error']}")
        return 1
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
