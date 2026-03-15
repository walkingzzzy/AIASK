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
