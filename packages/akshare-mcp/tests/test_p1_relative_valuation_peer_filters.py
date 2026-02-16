import pytest

import akshare_mcp.tools.valuation as valuation_mod


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _FakeDB:
    def __init__(self, stock_info_map, financials_map):
        self._stock_info_map = stock_info_map
        self._financials_map = financials_map

    async def get_stock_info(self, code):
        return self._stock_info_map.get(code)

    async def get_financials(self, code, limit=1):
        rows = self._financials_map.get(code, [])
        return rows[:limit]


@pytest.mark.asyncio
async def test_p1_2_relative_valuation_growth_cashflow_filters_and_premium(monkeypatch):
    mcp = _DummyMCP()
    valuation_mod.register(mcp)

    stock_info = {
        "TGT": {"name": "目标公司", "industry": "测试行业", "market_cap": 100.0, "pe_ratio": 20.0, "pb_ratio": 3.0},
        "P1": {"name": "同业1", "market_cap": 80.0, "pe_ratio": 15.0, "pb_ratio": 2.0},
        "P2": {"name": "同业2", "market_cap": 90.0, "pe_ratio": 17.0, "pb_ratio": 2.3},
        "P3": {"name": "同业3", "market_cap": 110.0, "pe_ratio": 19.0, "pb_ratio": 2.6},
        "P4": {"name": "同业4", "market_cap": 120.0, "pe_ratio": 21.0, "pb_ratio": 2.8},
        "P5": {"name": "同业5", "market_cap": 130.0, "pe_ratio": 22.0, "pb_ratio": 3.1},
        "P6": {"name": "同业6", "market_cap": 140.0, "pe_ratio": 23.0, "pb_ratio": 3.2},
        "P7": {"name": "同业7", "market_cap": 100.0, "pe_ratio": 16.0, "pb_ratio": 2.1},
        "P8": {"name": "同业8", "market_cap": 95.0, "pe_ratio": 18.0, "pb_ratio": 2.4},
    }
    financials = {
        "TGT": [{"roe": 0.18, "debt_ratio": 0.45, "revenue_yoy": 0.20, "operating_cash_flow": 120.0, "net_profit": 100.0}],
        "P1": [{"roe": 0.12, "debt_ratio": 0.50, "revenue_yoy": 0.18, "operating_cash_flow": 110.0, "net_profit": 100.0}],
        "P2": [{"roe": 0.13, "debt_ratio": 0.52, "revenue_yoy": 0.15, "operating_cash_flow": 90.0, "net_profit": 100.0}],
        "P3": [{"roe": 0.14, "debt_ratio": 0.48, "revenue_yoy": 0.25, "operating_cash_flow": 130.0, "net_profit": 100.0}],
        "P4": [{"roe": 0.15, "debt_ratio": 0.46, "revenue_yoy": 0.22, "operating_cash_flow": 100.0, "net_profit": 100.0}],
        "P5": [{"roe": 0.11, "debt_ratio": 0.60, "revenue_yoy": 0.10, "operating_cash_flow": 105.0, "net_profit": 100.0}],
        "P6": [{"roe": 0.12, "debt_ratio": 0.53, "revenue_yoy": 0.21, "operating_cash_flow": 60.0, "net_profit": 100.0}],
        "P7": [{"roe": 0.13, "debt_ratio": 0.40, "revenue_yoy": -0.40, "operating_cash_flow": 100.0, "net_profit": 100.0}],
        "P8": [{"roe": 0.13, "debt_ratio": 0.55, "revenue_yoy": 0.20, "operating_cash_flow": 300.0, "net_profit": 100.0}],
    }

    monkeypatch.setattr(valuation_mod, "get_db", lambda: _FakeDB(stock_info, financials))

    result = await mcp.relative_valuation("TGT", metrics=["pe_ratio", "pb_ratio"], peers=["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"])
    assert result["success"] is True

    data = result["data"]
    build = data["peer_pool_build"]

    assert build["candidate_count"] == 8
    assert build["after_quality_filter"] == 8
    assert build["after_growth_filter"] == 7
    assert build["after_cashflow_filter"] == 6
    assert build["growth_filter_relaxed"] is False
    assert build["cashflow_filter_relaxed"] is False

    assert data["peer_count"] == 6
    assert "comparison" in data and "pe_ratio" in data["comparison"]
    assert "premium_to_median" in data["comparison"]["pe_ratio"]
    assert data["comparison"]["pe_ratio"]["premium_to_median"] is not None


@pytest.mark.asyncio
async def test_p1_2_relative_valuation_relaxation_reasons_for_missing_growth_cashflow(monkeypatch):
    mcp = _DummyMCP()
    valuation_mod.register(mcp)

    stock_info = {
        "TGT": {"name": "目标公司", "industry": "测试行业", "market_cap": 100.0, "pe_ratio": 20.0, "pb_ratio": 3.0},
        "A1": {"name": "同业A1", "market_cap": 100.0, "pe_ratio": 15.0, "pb_ratio": 2.0},
        "A2": {"name": "同业A2", "market_cap": 102.0, "pe_ratio": 16.0, "pb_ratio": 2.1},
        "A3": {"name": "同业A3", "market_cap": 98.0, "pe_ratio": 17.0, "pb_ratio": 2.2},
        "A4": {"name": "同业A4", "market_cap": 105.0, "pe_ratio": 18.0, "pb_ratio": 2.3},
        "A5": {"name": "同业A5", "market_cap": 95.0, "pe_ratio": 19.0, "pb_ratio": 2.4},
    }
    financials = {
        "TGT": [{"roe": 0.16, "debt_ratio": 0.40, "revenue_yoy": 0.12, "operating_cash_flow": 80.0, "net_profit": 100.0}],
        "A1": [{"roe": 0.12, "debt_ratio": 0.45}],
        "A2": [{"roe": 0.13, "debt_ratio": 0.46}],
        "A3": [{"roe": 0.14, "debt_ratio": 0.47}],
        "A4": [{"roe": 0.15, "debt_ratio": 0.44}],
        "A5": [{"roe": 0.11, "debt_ratio": 0.43}],
    }

    monkeypatch.setattr(valuation_mod, "get_db", lambda: _FakeDB(stock_info, financials))

    result = await mcp.relative_valuation("TGT", metrics=["pe_ratio", "pb_ratio"], peers=["A1", "A2", "A3", "A4", "A5"])
    assert result["success"] is True

    build = result["data"]["peer_pool_build"]
    assert build["growth_filter_relaxed"] is True
    assert build["cashflow_filter_relaxed"] is True
    assert "growth_filter_relaxed_due_to_missing_data" in build["relaxation_reasons"]
    assert "cashflow_filter_relaxed_due_to_missing_data" in build["relaxation_reasons"]

