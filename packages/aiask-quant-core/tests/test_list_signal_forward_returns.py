"""INVERT-DESIGN P3：list_signal_forward_returns 返回前向收益序列（供 PromotionGate/DSR）。"""

from __future__ import annotations

import asyncio
from datetime import date

from aiask_quant_core.storage import close_db, get_db


def test_list_signal_forward_returns_returns_series(tmp_path, monkeypatch):
    monkeypatch.setenv("AIASK_SQLITE_PATH", str(tmp_path / "fwd_series.sqlite3"))

    async def _run() -> None:
        db = get_db()
        try:
            await db.initialize()
            await db.save_strategy(
                {
                    "id": "strat-fwd",
                    "name": "Fwd Series",
                    "status": "incubating",
                    "strategy_type": "momentum",
                }
            )
            # 写 4 个信号（不同 code，避免 unique 冲突）+ 各自 3D 前向收益。
            sig_date = date(2026, 5, 20)
            codes = ["600519", "000001", "000651", "601318"]
            await db.save_signals(
                "strat-fwd",
                sig_date,
                [{"code": c, "signal": 1} for c in codes],
            )
            signals = await db.get_signals("strat-fwd", limit=10)
            assert len(signals) == 4
            returns = [0.01, -0.02, 0.03, 0.0]
            # 按 signal id 升序对齐 returns（list_signal_forward_returns 也按 id 升序）
            signals_sorted = sorted(signals, key=lambda s: int(s["id"]))
            for sig, r in zip(signals_sorted, returns):
                await db.save_forward_returns(int(sig["id"]), 3, r)
                # 写一个不同 horizon，验证过滤
                await db.save_forward_returns(int(sig["id"]), 5, 99.0)

            rows = await db.list_signal_forward_returns("strat-fwd", forward_days=3)
            vals = [float(r["actual_return"]) for r in rows]
            assert vals == returns  # 升序、仅 3D、值正确

            # horizon=5 只拿到占位 99.0，证明过滤生效
            rows5 = await db.list_signal_forward_returns("strat-fwd", forward_days=5)
            assert all(float(r["actual_return"]) == 99.0 for r in rows5)
            assert len(rows5) == 4

            # 不存在的 horizon → 空
            rows10 = await db.list_signal_forward_returns("strat-fwd", forward_days=10)
            assert rows10 == []
        finally:
            await close_db()

    asyncio.run(_run())
