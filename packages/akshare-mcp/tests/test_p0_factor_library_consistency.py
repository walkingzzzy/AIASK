import math

import pytest

import akshare_mcp.tools.quant as quant_mod


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _FakeDB:
    def __init__(self, *, financial_row=None, stock_info=None):
        self._financial_row = financial_row
        self._stock_info = stock_info if stock_info is not None else {"market_cap": 2_000_000_000}

    async def get_klines(self, code, limit=100):
        bars = max(60, int(limit))
        return [{"close": 10.0 + i * 0.08} for i in range(bars)]

    async def get_financials(self, code, limit=1):
        if self._financial_row is None:
            return [
                {
                    "pe_ratio": 15.0,
                    "pb_ratio": 2.2,
                    "ps_ratio": 3.1,
                    "roe": 0.18,
                    "debt_ratio": 0.42,
                    "revenue_growth_yoy": 0.21,
                    "net_profit_growth": 0.25,
                }
            ]
        return [self._financial_row]

    async def get_stock_info(self, code):
        return self._stock_info


@pytest.mark.asyncio
async def test_factor_library_declared_factors_are_calculable(monkeypatch):
    mcp = _DummyMCP()
    quant_mod.register(mcp)
    monkeypatch.setattr(quant_mod, "get_db", lambda: _FakeDB())

    library = mcp.get_factor_library()
    assert library["success"] is True
    supported_factors = library["data"]["supported_factors"]
    assert len(supported_factors) == 8

    for factor in supported_factors:
        result = await mcp.calculate_factor(code="600519", factor=factor)
        assert result["success"] is True, f"{factor} failed: {result}"
        assert result["data"]["factor"] == factor
        assert math.isfinite(float(result["data"]["value"]))


@pytest.mark.asyncio
async def test_growth_factor_returns_clear_missing_field_error(monkeypatch):
    mcp = _DummyMCP()
    quant_mod.register(mcp)
    monkeypatch.setattr(
        quant_mod,
        "get_db",
        lambda: _FakeDB(financial_row={"pe_ratio": 12.0, "pb_ratio": 1.6, "roe": 0.17, "debt_ratio": 0.45}),
    )

    result = await mcp.calculate_factor(code="600519", factor="growth")
    assert result["success"] is False
    assert "missing growth fields" in (result["error"] or "")


@pytest.mark.asyncio
async def test_size_factor_returns_clear_missing_market_cap_error(monkeypatch):
    mcp = _DummyMCP()
    quant_mod.register(mcp)
    monkeypatch.setattr(quant_mod, "get_db", lambda: _FakeDB(stock_info={}))

    result = await mcp.calculate_factor(code="600519", factor="size")
    assert result["success"] is False
    assert "missing market cap" in (result["error"] or "")
