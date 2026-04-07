import asyncio

import pytest


class _DummyMCP:
    def tool(self, **_kwargs):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _DecisionDB:
    async def get_stock_info(self, code):
        return {"name": "测试股份", "industry": "消费"}

    async def get_klines(self, code, limit=None):
        rows = []
        for i in range(120):
            rows.append(
                {
                    "date": f"2026-03-{(i % 28) + 1:02d}",
                    "open": float(10 + i * 0.1),
                    "high": float(10.2 + i * 0.1),
                    "low": float(9.8 + i * 0.1),
                    "close": float(10 + i * 0.1),
                    "volume": 1000 + i * 5,
                }
            )
        return rows


async def _fake_analysis_context(_code):
    return {
        "success": True,
        "data": {
            "valuation": {"pe": 12.0, "pb": 1.5},
            "fundamentals": {"roe": 16.0, "debt_ratio": 30.0, "revenue_yoy": 12.0},
            "technical": {"rsi_14": 48.0, "moving_averages": {"ma20": 18.0, "ma60": 16.0}},
            "momentum": {"mom_20d": 0.08},
            "risk": {"volatility_20d": 0.02},
        },
    }


@pytest.mark.asyncio
async def test_should_i_buy_does_not_deadlock_when_analysis_context_uses_default_wrapper(monkeypatch):
    from akshare_mcp.tools import decision as decision_mod

    monkeypatch.setattr(decision_mod, "get_db", lambda: _DecisionDB())
    monkeypatch.setattr(decision_mod._decision_common_mod, "_raw_get_investment_analysis", _fake_analysis_context)
    monkeypatch.setattr(decision_mod.technical_analysis, "calculate_macd", lambda closes: {"histogram": [0.1, 0.2]})

    mcp = _DummyMCP()
    decision_mod.register(mcp)

    result = await asyncio.wait_for(mcp.should_i_buy("000001", investment_style="balanced"), timeout=1.0)

    assert result["success"] is True
    assert result["data"]["analysis_context"]["valuation"]["pe"] == 12.0


@pytest.mark.asyncio
async def test_should_i_sell_does_not_deadlock_when_analysis_context_uses_default_wrapper(monkeypatch):
    from akshare_mcp.tools import decision as decision_mod

    monkeypatch.setattr(decision_mod, "get_db", lambda: _DecisionDB())
    monkeypatch.setattr(decision_mod._decision_common_mod, "_raw_get_investment_analysis", _fake_analysis_context)
    monkeypatch.setattr(decision_mod.technical_analysis, "calculate_rsi", lambda closes: [72.0])
    monkeypatch.setattr(decision_mod.technical_analysis, "calculate_macd", lambda closes: {"histogram": [0.2, -0.1]})
    monkeypatch.setattr(
        decision_mod.technical_analysis,
        "calculate_sma",
        lambda closes, period: [sum(closes[-period:]) / period],
    )

    mcp = _DummyMCP()
    decision_mod.register(mcp)

    result = await asyncio.wait_for(mcp.should_i_sell("000001", buy_price=9.0, holding_days=30), timeout=1.0)

    assert result["success"] is True
    assert result["data"]["analysis_context"]["valuation"]["pe"] == 12.0
