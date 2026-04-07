from __future__ import annotations

from contextlib import asynccontextmanager

import pandas as pd
import pytest

import akshare_mcp.tools.factor_profile as factor_profile_mod
import akshare_mcp.tools.managers.industry_chain_manager as industry_chain_manager_mod
import akshare_mcp.tools.managers.sector_manager as sector_manager_mod
import akshare_mcp.tools.managers.sentiment_manager as sentiment_manager_mod
import akshare_mcp.tools.news.research as research_mod
import akshare_mcp.tools.portfolio as portfolio_mod


class _DummyMCP:
    def tool(self, **_kwargs):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FactorConn:
    async def fetch(self, query, *args):
        if "WHERE industry = $1" in query:
            return [{"code": "000002"}, {"code": "000003"}]
        return [{"code": "000002"}, {"code": "000003"}, {"code": "000004"}]


class _FactorDB:
    def __init__(self):
        self._conn = _FactorConn()

    @asynccontextmanager
    async def acquire(self):
        yield self._conn

    async def get_stock_info(self, code):
        return {"industry": "白酒", "name": "测试股"}

    async def get_klines(self, code, limit=None):
        def _series(base: float, delta: float):
            values = []
            for idx in range(260):
                close = base + idx * 0.1 + delta
                values.append(
                    {
                        "date": f"2025-01-{(idx % 28) + 1:02d}",
                        "open": close - 0.3,
                        "high": close + 0.5,
                        "low": close - 0.6,
                        "close": close,
                        "volume": 1000 + idx,
                    }
                )
            return values[:limit]

        mapping = {
            "000001": _series(10.0, 0.0),
            "000002": _series(9.5, 1.0),
            "000003": _series(9.0, -0.5),
            "000004": _series(11.0, 0.8),
        }
        return mapping[code]


class _SentimentDB:
    async def get_klines(self, code, limit=20):
        values = []
        for idx in range(limit):
            close = 100 + idx
            values.append(
                {
                    "open": close - (0.5 if idx % 3 else -0.5),
                    "close": close,
                    "volume": 1000 + idx * 10,
                }
            )
        return values


def test_get_analyst_ranking_accepts_int_year(monkeypatch):
    class _TSPro:
        def report_rc(self, start_date, end_date, fields):
            assert start_date == "20250101"
            assert end_date == "20251231"
            return pd.DataFrame(
                [
                    {"author_name": "分析师A", "org_name": "机构甲", "report_date": "2025-01-03"},
                    {"author_name": "分析师A", "org_name": "机构甲", "report_date": "2025-02-07"},
                    {"author_name": "分析师B", "org_name": "机构乙", "report_date": "2025-03-11"},
                ]
            )

    monkeypatch.setattr(research_mod.data_source, "get_tushare_pro", lambda: _TSPro())

    result = research_mod.get_analyst_ranking(2025)

    assert result["success"] is True
    assert result["data"]["requested_year"] == "2025"
    assert result["data"]["analysts"][0]["name"] == "分析师A"


@pytest.mark.asyncio
async def test_get_factor_profile_accepts_factor_list(monkeypatch):
    monkeypatch.setattr(factor_profile_mod, "get_db", lambda: _FactorDB())
    mcp = _DummyMCP()
    factor_profile_mod.register(mcp)

    result = await mcp.get_factor_profile(code="000001", factors=["rsi", "macd"])

    assert result["success"] is True
    assert set(result["data"]["factors"].keys()) == {"rsi", "macd"}


@pytest.mark.asyncio
async def test_stress_test_portfolio_accepts_comma_separated_scenarios(monkeypatch):
    monkeypatch.setattr(
        portfolio_mod.risk_model,
        "stress_test",
        lambda holdings, scenario: {"scenario": scenario, "impact": -0.1},
    )
    mcp = _DummyMCP()
    portfolio_mod.register(mcp)

    result = await mcp.stress_test_portfolio(
        holdings=[{"code": "600519", "weight": 0.5}],
        scenarios="market_crash, black_swan",
    )

    assert result["success"] is True
    assert result["data"]["scenarios"] == ["market_crash", "black_swan"]
    assert set(result["data"]["stress_tests"].keys()) == {"market_crash", "black_swan"}


@pytest.mark.asyncio
async def test_industry_chain_manager_accepts_structured_params_keyword(monkeypatch):
    mcp = _DummyMCP()
    industry_chain_manager_mod.register_industry_chain_manager(mcp)
    monkeypatch.setattr(industry_chain_manager_mod, "get_db", lambda: object())

    result = await mcp.industry_chain_manager(
        action="get_chain",
        params={"keyword": "白酒"},
    )

    assert result["success"] is True
    assert result["data"]["industry"] == "白酒"
    assert result["data"]["source"] == "preset"


@pytest.mark.asyncio
async def test_sentiment_manager_accepts_top_level_code(monkeypatch):
    mcp = _DummyMCP()
    sentiment_manager_mod.register_sentiment_manager(mcp)
    monkeypatch.setattr(sentiment_manager_mod, "get_db", lambda: _SentimentDB())

    result = await mcp.sentiment_manager(
        action="stock_sentiment",
        code="000858",
    )

    assert result["success"] is True
    assert result["data"]["code"] == "000858"
    assert result["data"]["score"] > 0


@pytest.mark.asyncio
async def test_sector_manager_sector_rotation_prefers_market_blocks_fast_path(monkeypatch):
    mcp = _DummyMCP()
    sector_manager_mod.register_sector_manager(mcp)
    monkeypatch.setattr(sector_manager_mod, "get_db", lambda: object())

    async def _fake_get_market_blocks(block_type="industry", limit=20):
        assert block_type == "industry"
        return {
            "success": True,
            "data": {
                "blocks": [
                    {"blockCode": "BK001", "blockName": "半导体", "avgChangePct": 4.2, "stockCount": 18},
                    {"blockCode": "BK002", "blockName": "白酒", "avgChangePct": -1.5, "stockCount": 12},
                    {"blockCode": "BK003", "blockName": "券商", "avgChangePct": 1.1, "stockCount": 22},
                ]
            },
        }

    monkeypatch.setattr("akshare_mcp.tools.market_blocks.get_market_blocks", _fake_get_market_blocks)

    result = await mcp.sector_manager(action="sector_rotation", days=20)

    assert result["success"] is True
    assert result["data"]["source"] == "market_blocks"
    assert result["data"]["strong_sectors"][0]["blockName"] == "半导体"
    assert result["data"]["weak_sectors"][-1]["blockName"] == "白酒"
