import numpy as np
import pytest

import akshare_mcp.tools.quant as quant_mod


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _FakeBacktestDB:
    def __init__(self, n_codes: int = 12, n_bars: int = 160):
        self.n_bars = int(n_bars)
        self._codes = [f"600{100 + i:03d}" for i in range(n_codes)]

    async def get_klines(self, code, limit=200):
        bars = min(int(limit), self.n_bars)
        idx = int(str(code)[-2:]) % 20
        rows = []
        for i in range(self.n_bars):
            base = 10.0 + idx * 0.2
            # Stable upward trend + light oscillation to guarantee rolling windows.
            close = base + 0.03 * i + 0.6 * np.sin((i + idx) / 9.0)
            volume = 100000 + (i % 11) * 2000
            # Make some codes periodically untradable at rebalance points.
            if idx in {0, 5} and (i % 5 == 4):
                volume = 0
            rows.append({"close": float(close), "volume": float(volume)})
        # Mimic DB behavior: newest first.
        return list(reversed(rows[-bars:]))

    async def get_financials(self, code, limit=1):
        return [
            {
                "pe_ratio": 18.0,
                "pb_ratio": 2.0,
                "roe": 0.15,
                "debt_ratio": 0.4,
                "revenue_growth_yoy": 0.12,
                "net_profit_growth": 0.14,
            }
        ]

    async def get_stock_info(self, code):
        idx = int(str(code)[-2:]) % 20
        return {"market_cap": 1_000_000_000 + idx * 80_000_000}


def _max_drawdown_from_curve(curve):
    arr = np.array(curve, dtype=float)
    peak = np.maximum.accumulate(arr)
    dd = (peak - arr) / np.where(peak > 0, peak, 1.0)
    return float(np.max(dd)) if dd.size > 0 else 0.0


@pytest.mark.asyncio
async def test_factor_backtest_outputs_realized_equity_curve_and_drawdown(monkeypatch):
    mcp = _DummyMCP()
    quant_mod.register(mcp)
    monkeypatch.setattr(quant_mod, "get_db", lambda: _FakeBacktestDB())

    result = await mcp.backtest_factor(
        codes=[f"600{100 + i:03d}" for i in range(12)],
        factor="momentum",
        groups=3,
        holding_days=5,
        max_periods=12,
    )
    assert result["success"] is True
    data = result["data"]

    curve = data["equity_curve"]
    period_returns = data["period_long_short_returns"]
    assert isinstance(curve, list) and len(curve) >= 2
    assert len(curve) == len(period_returns) + 1
    assert data["period_group_results"]
    assert data["max_drawdown"] == pytest.approx(_max_drawdown_from_curve(curve), rel=1e-9, abs=1e-9)


@pytest.mark.asyncio
async def test_factor_backtest_cost_and_tradability_stats_are_populated(monkeypatch):
    mcp = _DummyMCP()
    quant_mod.register(mcp)
    monkeypatch.setattr(quant_mod, "get_db", lambda: _FakeBacktestDB())

    result = await mcp.backtest_factor(
        codes=[f"600{100 + i:03d}" for i in range(12)],
        factor="momentum",
        groups=3,
        holding_days=5,
        commission=0.0005,
        slippage_model="fixed",
        tradability_filter=True,
        max_periods=10,
    )
    assert result["success"] is True
    data = result["data"]

    assert data["costs"]["commission"] == pytest.approx(0.0005)
    assert data["costs"]["slippage_model"] == "fixed"
    assert data["costs"]["avg_impact_cost_rate"] > 0
    assert data["tradability"]["enabled"] is True
    assert data["tradability"]["candidate_signals"] >= data["tradability"]["filled_signals"]
    assert 0.0 <= data["tradability"]["fill_ratio"] <= 1.0
    assert data["tradability"]["untradable_ratio"] >= 0.0
