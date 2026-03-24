from types import SimpleNamespace

import pytest

import akshare_mcp.tools.vector as vector_mod
from akshare_mcp.tools.managers.vector_search_manager import register_vector_search_manager


class _DummyMCP:
    def __init__(self):
        self._tool_manager = SimpleNamespace(_tools={})

    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _Acquire:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def fetch(self, _query, *_args):
        return self._rows


class _VectorDb:
    def __init__(self):
        self._rows = [{"code": "000001", "stock_name": "平安银行"}]

    async def get_klines(self, code, limit=0):
        del limit
        return [
            {"close": 10.0, "volume": 100.0},
            {"close": 10.5, "volume": 120.0},
            {"close": 11.0, "volume": 130.0},
        ] if code in {"600519", "000001"} else []

    async def get_stock_info(self, code):
        if code == "600519":
            return {"industry": "白酒", "name": "贵州茅台"}
        return None

    def acquire(self):
        return _Acquire(self._rows)


@pytest.mark.asyncio
async def test_search_by_kline_returns_normalized_fallback_meta(monkeypatch):
    mcp = _DummyMCP()
    vector_mod.register(mcp)
    monkeypatch.setattr(vector_mod, "get_db", lambda: _VectorDb())

    def _fake_find_similar_patterns(**_kwargs):
        vector_mod.vector_search_engine.last_backend_used = "python_fallback"
        vector_mod.vector_search_engine.last_meta = {
            "backend_requested": "index",
            "backend_used": "python_fallback",
            "fallback_used": True,
            "fallback_reason": "index_empty_result",
            "latency_ms": 12.3,
        }
        return [{"code": "000001", "similarity": 0.91, "source": "python_fallback"}]

    monkeypatch.setattr(vector_mod.vector_search_engine, "find_similar_patterns", _fake_find_similar_patterns)

    result = await mcp.search_by_kline(code="600519", days=3, top_n=1, search_backend="index")

    assert result["success"] is True
    data = result["data"]
    assert data["backend_requested"] == "index"
    assert data["backend_used"] == "python_fallback"
    assert data["fallback_used"] is True
    assert data["fallback_reason"] == "index_empty_result"
    assert data["latency_ms"] == 12.3
    assert data["results"][0]["source"] == "python_fallback"


@pytest.mark.asyncio
async def test_vector_search_manager_preserves_normalized_fallback_meta():
    mcp = _DummyMCP()

    class _Tool:
        async def run(self, args):
            assert args["code"] == "600519"
            return {
                "success": True,
                "data": {
                    "results": [{"code": "000001", "similarity": 0.91, "source": "python_fallback"}],
                    "search_backend": "index",
                    "actual_backend": "python_fallback",
                    "backend_requested": "index",
                    "backend_used": "python_fallback",
                    "fallback_used": True,
                    "fallback_reason": "index_empty_result",
                    "latency_ms": 18.5,
                },
            }

    mcp._tool_manager._tools["search_by_kline"] = _Tool()
    register_vector_search_manager(mcp)

    result = await mcp.vector_search_manager(action="similar_patterns", code="600519", days=3, top_n=1)

    assert result["success"] is True
    data = result["data"]
    assert data["backend_requested"] == "index"
    assert data["backend_used"] == "python_fallback"
    assert data["fallback_used"] is True
    assert data["fallback_reason"] == "index_empty_result"
    assert data["latency_ms"] == 18.5


@pytest.mark.asyncio
async def test_vector_search_manager_market_docs_uses_hybrid_doc_search(monkeypatch):
    mcp = _DummyMCP()

    class _DocDb:
        async def search_market_doc_chunks(self, **kwargs):
            assert kwargs["stock_code"] == "600519"
            assert kwargs["query_text"] == "高增长"
            assert kwargs["doc_types"] == ["news"]
            return [
                {
                    "entity_id": "doc_1:0",
                    "title": "茅台业绩高增长点评",
                    "dense_score": 0.71,
                    "lexical_score": 1.0,
                    "hybrid_score": 0.8115,
                }
            ]

    monkeypatch.setattr(
        "akshare_mcp.tools.managers.vector_search_manager.get_db",
        lambda: _DocDb(),
    )
    register_vector_search_manager(mcp)

    result = await mcp.vector_search_manager(
        action="market_docs",
        code="600519",
        kwargs='{"query":"高增长","doc_types":["news"],"limit":5}',
    )

    assert result["success"] is True
    data = result["data"]
    assert data["retrieval_mode"] == "hybrid"
    assert data["count"] == 1
    assert data["results"][0]["entity_id"] == "doc_1:0"


@pytest.mark.asyncio
async def test_search_by_kline_supports_db_backend(monkeypatch):
    mcp = _DummyMCP()
    vector_mod.register(mcp)

    class _Db:
        async def get_klines(self, code, limit=0):
            return [
                {"date": f"2026-03-{idx:02d}", "close": 10 + idx, "open": 9.5 + idx, "high": 10.5 + idx, "low": 9.0 + idx, "volume": 1000 + idx}
                for idx in range(1, max(limit, 20) + 1)
            ]

        async def get_stock_info(self, code):
            return {"industry": "白酒", "name": "贵州茅台"} if code == "600519" else {"name": "平安银行"}

        async def list_stock_universe(self, *, limit=200, offset=0, min_market_cap=None, industry=None, market=None):
            del offset, min_market_cap, market
            rows = [
                {"code": "000001", "name": "平安银行", "industry": industry or "白酒"},
                {"code": "000002", "name": "万科A", "industry": industry or "白酒"},
            ]
            return rows[:limit]

        async def search_kline_pattern_windows(self, **kwargs):
            assert kwargs["window_size"] == 5
            assert kwargs["stock_codes"] == ["000001", "000002"]
            return [
                {
                    "stock_code": "000001",
                    "stock_name": "平安银行",
                    "similarity": 0.88,
                    "end_date": "2026-03-20",
                    "start_date": "2026-03-16",
                    "forward_return_5d": 0.05,
                    "forward_return_10d": 0.08,
                    "forward_return_20d": 0.12,
                }
            ]

    monkeypatch.setattr(vector_mod, "get_db", lambda: _Db())

    result = await mcp.search_by_kline(code="600519", days=5, top_n=1, search_backend="db")

    assert result["success"] is True
    data = result["data"]
    assert data["backend_requested"] == "db"
    assert data["backend_used"] == "db"
    assert data["fallback_used"] is False
    assert data["results"][0]["source"] == "db"
    assert data["results"][0]["forward_return_5d"] == 0.05


@pytest.mark.asyncio
async def test_search_by_kline_db_backend_falls_back_to_python(monkeypatch):
    mcp = _DummyMCP()
    vector_mod.register(mcp)

    class _Db:
        async def get_klines(self, code, limit=0):
            base = 10 if code == "600519" else 20
            return [
                {"date": f"2026-03-{idx:02d}", "close": base + idx, "open": base - 0.5 + idx, "high": base + 0.5 + idx, "low": base - 1.0 + idx, "volume": 1000 + idx}
                for idx in range(1, max(limit, 20) + 1)
            ]

        async def get_stock_info(self, code):
            return {"industry": "白酒", "name": "贵州茅台"} if code == "600519" else None

        async def list_stock_universe(self, *, limit=200, offset=0, min_market_cap=None, industry=None, market=None):
            del offset, min_market_cap, market
            return [
                {"code": "000001", "name": "平安银行", "industry": industry or "白酒"},
            ][:limit]

        async def search_kline_pattern_windows(self, **kwargs):
            assert kwargs["window_size"] == 5
            return []

        def acquire(self):
            class _Acquire:
                async def __aenter__(self_inner):
                    class _Conn:
                        async def fetch(self_conn, _query, *_args):
                            return []

                    return _Conn()

                async def __aexit__(self_inner, exc_type, exc, tb):
                    return False

            return _Acquire()

    monkeypatch.setattr(vector_mod, "get_db", lambda: _Db())

    def _fake_find_similar_patterns(**_kwargs):
        vector_mod.vector_search_engine.last_backend_used = "python_fallback"
        vector_mod.vector_search_engine.last_meta = {
            "backend_requested": "python",
            "backend_used": "python_fallback",
            "fallback_used": True,
            "fallback_reason": "index_empty_result",
            "latency_ms": 5.0,
        }
        return [{"code": "000001", "similarity": 0.77, "source": "python_fallback"}]

    monkeypatch.setattr(vector_mod.vector_search_engine, "find_similar_patterns", _fake_find_similar_patterns)

    result = await mcp.search_by_kline(code="600519", days=5, top_n=1, search_backend="db", allow_fallback=True)

    assert result["success"] is True
    data = result["data"]
    assert data["backend_requested"] == "db"
    assert data["backend_used"] == "python_fallback"
    assert data["fallback_used"] is True
    assert data["fallback_reason"] == "db_empty_result"
