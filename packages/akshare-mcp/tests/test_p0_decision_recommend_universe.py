import pytest

import akshare_mcp.tools.managers.decision_manager as dm


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _FakeDecisionDB:
    def __init__(self):
        self.search_called = 0

    async def search_stocks(self, keyword: str, limit: int = 20):
        self.search_called += 1
        return [
            {"code": "600001", "name": "A", "industry": "银行", "market_cap": 120_000_000_000},
            {"code": "600002", "name": "B", "industry": "科技", "market_cap": 90_000_000_000},
            {"code": "600003", "name": "C", "industry": "银行", "market_cap": 80_000_000_000},
        ][: int(limit)]

    async def get_klines(self, code, limit=100):
        bars = max(80, int(limit))
        return [
            {
                "date": f"2025-01-{(i % 28) + 1:02d}",
                "close": 10.0 + i * 0.1,
                "volume": 100000 + i * 10,
            }
            for i in range(bars)
        ]

    async def save_klines(self, code, klines):
        return None

    async def get_financials(self, code, limit=1):
        return [{"roe": 0.22, "pe_ratio": 12.0, "debt_ratio": 0.35, "pb_ratio": 1.6}]


@pytest.mark.asyncio
async def test_recommend_uses_dynamic_universe_with_filters(monkeypatch):
    mcp = _DummyMCP()
    dm.register_decision_manager(mcp)
    fake_db = _FakeDecisionDB()
    monkeypatch.setattr(dm, "get_db", lambda: fake_db)

    result = await mcp.decision_manager(
        action="recommend",
        limit=5,
        universe_limit=50,
        criteria={
            "min_score": 0,
            "sectors": ["银行"],
            "liquidity_filter": {"min_market_cap": 100_000_000_000},
        },
    )

    assert result["success"] is True
    data = result["data"]
    assert data["message"] == ""
    assert data["universe"]["fallback_used"] is False
    assert data["universe"]["no_candidates"] is False
    assert data["universe"]["candidate_count"] == 1
    assert data["universe"]["scanned_count"] == 1
    assert fake_db.search_called == 1
    assert len(data["recommendations"]) == 1
    assert data["recommendations"][0]["code"] == "600001"


@pytest.mark.asyncio
async def test_recommend_prefers_explicit_codes_over_search(monkeypatch):
    mcp = _DummyMCP()
    dm.register_decision_manager(mcp)
    fake_db = _FakeDecisionDB()
    monkeypatch.setattr(dm, "get_db", lambda: fake_db)

    result = await mcp.decision_manager(
        action="recommend",
        limit=2,
        codes=["000001", "000002"],
        criteria={"min_score": 0},
    )

    assert result["success"] is True
    data = result["data"]
    assert fake_db.search_called == 0
    assert data["universe"]["fallback_used"] is False
    assert data["universe"]["no_candidates"] is False
    assert data["universe"]["candidate_count"] == 2
    assert data["recommendations"][0]["code"] in {"000001", "000002"}


@pytest.mark.asyncio
async def test_recommend_returns_empty_when_filters_exhaust_candidates(monkeypatch):
    mcp = _DummyMCP()
    dm.register_decision_manager(mcp)
    fake_db = _FakeDecisionDB()
    monkeypatch.setattr(dm, "get_db", lambda: fake_db)

    result = await mcp.decision_manager(
        action="recommend",
        limit=5,
        universe_limit=50,
        criteria={
            "min_score": 0,
            "sectors": ["银行"],
            "liquidity_filter": {"min_market_cap": 1_000_000_000_000},
        },
    )

    assert result["success"] is True
    data = result["data"]
    assert fake_db.search_called == 1
    assert data["recommendations"] == []
    assert data["count"] == 0
    assert data["message"] == "未找到符合条件的候选股票"
    assert data["universe"]["fallback_used"] is False
    assert data["universe"]["no_candidates"] is True
    assert data["universe"]["candidate_count"] == 0
    assert data["universe"]["scanned_count"] == 0
