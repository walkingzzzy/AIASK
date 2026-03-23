from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import akshare_mcp.tools.vector as vector_mod


class _DummyMCP:
    def __init__(self):
        self._tool_manager = SimpleNamespace(_tools={})

    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FundamentalConn:
    def __init__(self):
        self.calls: list[str] = []

    async def fetch(self, query, *args):
        normalized = " ".join(str(query).split())
        self.calls.append(normalized)
        if "information_schema.columns" in normalized:
            return [{"column_name": "stock_code"}]
        if "FROM financials" in normalized:
            return [
                {"code": "000001", "roe": 14.0, "debt_ratio": 0.42, "revenue_growth": 0.09},
                {"code": "000002", "roe": 11.0, "debt_ratio": 0.48, "revenue_growth": 0.06},
            ]
        return []


class _FundamentalDb:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)

    async def get_stock_info(self, code):
        if code == "600519":
            return {"name": "贵州茅台", "industry": "白酒", "pe_ratio": 20.0, "pb_ratio": 5.0}
        raise AssertionError(f"candidate get_stock_info should not be called: {code}")

    async def get_financials(self, code, limit=1):
        del limit
        if code == "600519":
            return [{"roe": 18.0, "debt_ratio": 0.35, "revenue_growth": 0.12}]
        raise AssertionError(f"candidate get_financials should not be called: {code}")

    async def get_klines(self, code, limit=60):
        del code, limit
        return []

    async def list_stock_universe(self, *, limit=200, offset=0, min_market_cap=None, industry=None, market=None):
        del offset, min_market_cap, market
        rows = [
            {"code": "000001", "name": "平安银行", "industry": "白酒", "pe_ratio": 18.0, "pb_ratio": 4.7},
            {"code": "000002", "name": "万科A", "industry": "白酒", "pe_ratio": 22.0, "pb_ratio": 5.3},
        ]
        return rows[:limit] if industry else rows[:limit]


class _KlineConn:
    def __init__(self):
        self.calls: list[str] = []

    async def fetch(self, query, *args):
        normalized = " ".join(str(query).split())
        self.calls.append(normalized)
        if "FROM (" in normalized and "kline_1d" in normalized:
            codes = list(args[0])
            limit = int(args[1])
            now = datetime(2026, 3, 20)
            rows = []
            for idx, code in enumerate(codes):
                for offset in range(limit):
                    close = 10.0 + idx + offset * 0.1
                    rows.append(
                        {
                            "code": code,
                            "time": now - timedelta(days=limit - offset),
                            "open": close - 0.05,
                            "high": close + 0.08,
                            "low": close - 0.08,
                            "close": close,
                            "volume": 1000 + offset,
                            "amount": 10000.0 + offset,
                            "turnover": None,
                            "change_pct": None,
                        }
                    )
            return rows
        return []


class _KlineDb:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)

    async def get_stock_info(self, code):
        if code == "600519":
            return {"industry": "白酒", "name": "贵州茅台"}
        return None

    async def get_klines(self, code, limit=0):
        if code != "600519":
            raise AssertionError(f"candidate get_klines should not be called: {code}")
        return [
            {"close": 10.0 + i * 0.1, "open": 10.0 + i * 0.1 - 0.05, "high": 10.0 + i * 0.1 + 0.08, "low": 10.0 + i * 0.1 - 0.08, "volume": 1000 + i}
            for i in range(limit)
        ]

    async def list_stock_universe(self, *, limit=200, offset=0, min_market_cap=None, industry=None, market=None):
        del offset, min_market_cap, market
        rows = [
            {"code": "000001", "name": "平安银行", "industry": "白酒"},
            {"code": "000002", "name": "万科A", "industry": "白酒"},
        ]
        return rows[:limit] if industry else rows[:limit]


@pytest.mark.asyncio
async def test_search_similar_stocks_batches_candidate_financial_fetch(monkeypatch):
    mcp = _DummyMCP()
    vector_mod.register(mcp)
    conn = _FundamentalConn()
    monkeypatch.setattr(vector_mod, "get_db", lambda: _FundamentalDb(conn))

    result = await mcp.search_similar_stocks("600519", top_n=2, similarity_type="fundamental")

    assert result["success"] is True
    assert result["data"]["calculated"] == 2
    assert any("FROM financials" in query for query in conn.calls)


@pytest.mark.asyncio
async def test_search_by_kline_batches_candidate_kline_fetch(monkeypatch):
    mcp = _DummyMCP()
    vector_mod.register(mcp)
    conn = _KlineConn()
    monkeypatch.setattr(vector_mod, "get_db", lambda: _KlineDb(conn))

    captured = {}

    def _fake_find_similar_patterns(**kwargs):
        captured["candidate_codes"] = sorted(kwargs["candidate_klines_dict"].keys())
        vector_mod.vector_search_engine.last_backend_used = "python"
        vector_mod.vector_search_engine.last_meta = {
            "backend_requested": "python",
            "backend_used": "python",
            "fallback_used": False,
            "fallback_reason": None,
            "latency_ms": 4.2,
        }
        return [{"code": "000001", "similarity": 0.9, "source": "python"}]

    monkeypatch.setattr(vector_mod.vector_search_engine, "find_similar_patterns", _fake_find_similar_patterns)

    result = await mcp.search_by_kline("600519", days=5, top_n=1, search_backend="python")

    assert result["success"] is True
    assert captured["candidate_codes"] == ["000001", "000002"]
    assert any("kline_1d" in query for query in conn.calls)
