"""P1 方案C/D 回归测试。"""

import asyncio
import json
import os
import sys
import threading

import pytest

# 兼容未安装 editable package 的本地测试场景
CURRENT_DIR = os.path.dirname(__file__)
SRC_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from akshare_mcp.cache import SimpleCache
from akshare_mcp.services import data_sync as data_sync_module
from akshare_mcp.services.data_sync import DataSyncService
from akshare_mcp.services.factor_calculator_extended import FactorCalculatorExtended
from akshare_mcp.tools import backtest as backtest_tool
from akshare_mcp.tools import data_sync as data_sync_tool


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator


def test_batch_backtest_has_concurrent_fetch_and_timings(monkeypatch):
    """验证批量回测包含并发取数与分阶段耗时字段。"""

    class FakeDB:
        async def get_klines(self, code, start_date, end_date):
            await asyncio.sleep(0.01)
            return [{"date": "2025-01-01", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]

    class FakeEngine:
        @staticmethod
        def batch_backtest_sequential(codes, klines_dict, strategy, params):
            results = [
                {
                    "code": c,
                    "success": True,
                    "total_return": 0.1,
                    "sharpe_ratio": 1.2,
                    "max_drawdown": 0.05,
                }
                for c in codes
            ]
            return {"success": True, "data": {"results": results, "count": len(results)}}

    monkeypatch.setattr(backtest_tool, "get_db", lambda: FakeDB())
    monkeypatch.setattr(backtest_tool, "ParallelBacktestEngine", FakeEngine, raising=False)
    monkeypatch.setattr(backtest_tool, "RAY_AVAILABLE", False)

    mcp = FakeMCP()
    backtest_tool.register(mcp)
    result = asyncio.run(
        mcp.tools["run_batch_backtest"](
            codes=["000001", "600519", "000858"],
            use_parallel=False,
            fetch_concurrency=5,
        )
    )

    assert result["success"] is True
    data = result["data"]
    assert "timings" in data
    assert set(data["timings"].keys()) == {
        "io_fetch_seconds",
        "compute_seconds",
        "aggregation_seconds",
        "total_seconds",
    }
    assert data["fetch_concurrency"] == 5
    assert data["source_stats"]["timescaledb"] == 3


def test_batch_backtest_fetch_concurrency_limit(monkeypatch):
    """验证限流参数生效（观测最大并发不超过阈值）。"""

    class State:
        active = 0
        max_active = 0

    class FakeDB:
        async def get_klines(self, code, start_date, end_date):
            State.active += 1
            State.max_active = max(State.max_active, State.active)
            await asyncio.sleep(0.02)
            State.active -= 1
            return [{"date": "2025-01-01", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]

    class FakeEngine:
        @staticmethod
        def batch_backtest_sequential(codes, klines_dict, strategy, params):
            return {"success": True, "data": {"results": [{"success": True} for _ in codes]}}

    monkeypatch.setattr(backtest_tool, "get_db", lambda: FakeDB())
    monkeypatch.setattr(backtest_tool, "ParallelBacktestEngine", FakeEngine, raising=False)
    monkeypatch.setattr(backtest_tool, "RAY_AVAILABLE", False)

    mcp = FakeMCP()
    backtest_tool.register(mcp)
    asyncio.run(
        mcp.tools["run_batch_backtest"](
            codes=[f"6000{i:02d}" for i in range(10)], use_parallel=False, fetch_concurrency=3
        )
    )

    assert State.max_active <= 3


def test_simple_cache_stats_and_thread_safety(tmp_path):
    """验证缓存命中率、总请求数、并发写入稳定性。"""
    cache = SimpleCache(cache_dir=str(tmp_path / "cache"), memory_maxsize=8)
    cache.set("k1", {"v": 1})

    assert cache.get("k1", ttl_seconds=60) == {"v": 1}
    assert cache.get("k1", ttl_seconds=60) == {"v": 1}

    errors = []

    def writer(i):
        try:
            cache.set("shared", {"i": i})
            _ = cache.get("shared", ttl_seconds=60)
        except Exception as e:  # pragma: no cover
            errors.append(str(e))

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2)

    stats = cache.get_cache_stats()
    assert not errors
    assert stats["total_requests"] >= 2
    assert stats["hits"] >= 2
    assert 0 <= stats["hit_rate"] <= 1
    assert 0 <= stats["miss_rate"] <= 1



def test_batch_backtest_prefers_db_batch_path(monkeypatch):
    """验证优先走 get_klines_batch 路径。"""

    class FakeDB:
        async def get_klines_batch(self, codes, start_date, end_date, limit):
            return {
                c: [{"date": "2025-01-01", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]
                for c in codes
            }

        async def get_klines(self, code, start_date, end_date):  # 不应被调用
            raise AssertionError("should not fallback to get_klines")

    class FakeEngine:
        @staticmethod
        def batch_backtest_sequential(codes, klines_dict, strategy, params):
            return {"success": True, "data": {"results": [{"success": True} for _ in codes]}}

    monkeypatch.setattr(backtest_tool, "get_db", lambda: FakeDB())
    monkeypatch.setattr(backtest_tool, "ParallelBacktestEngine", FakeEngine, raising=False)
    monkeypatch.setattr(backtest_tool, "RAY_AVAILABLE", False)

    mcp = FakeMCP()
    backtest_tool.register(mcp)
    result = asyncio.run(
        mcp.tools["run_batch_backtest"](
            codes=["000001", "600519", "000858"],
            use_parallel=False,
            fetch_concurrency=4,
        )
    )

    assert result["success"] is True
    stats = result["data"]["source_stats"]
    assert stats["timescaledb_batch"] == 3
    assert stats["timescaledb"] == 0


def test_batch_backtest_batch_failure_falls_back_to_single_fetch(monkeypatch):
    """验证批量接口失败后会自动回退逐只查询。"""

    class FakeDB:
        async def get_klines_batch(self, codes, start_date, end_date, limit):
            raise RuntimeError("batch broken")

        async def get_klines(self, code, start_date, end_date):
            return [{"date": "2025-01-01", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]

    class FakeEngine:
        @staticmethod
        def batch_backtest_sequential(codes, klines_dict, strategy, params):
            return {"success": True, "data": {"results": [{"success": True} for _ in codes]}}

    monkeypatch.setattr(backtest_tool, "get_db", lambda: FakeDB())
    monkeypatch.setattr(backtest_tool, "ParallelBacktestEngine", FakeEngine, raising=False)
    monkeypatch.setattr(backtest_tool, "RAY_AVAILABLE", False)

    mcp = FakeMCP()
    backtest_tool.register(mcp)
    result = asyncio.run(
        mcp.tools["run_batch_backtest"](
            codes=["000001", "600519"],
            use_parallel=False,
            fetch_concurrency=2,
        )
    )

    assert result["success"] is True
    stats = result["data"]["source_stats"]
    assert stats["timescaledb_batch"] == 0
    assert stats["timescaledb"] == 2


def test_batch_backtest_warmup_before_fetch(monkeypatch):
    """验证 warmup_before_fetch 会触发 data_sync 预热并写入返回。"""

    class FakeSyncService:
        def __init__(self):
            self.called = False

        async def sync_stock_klines(self, codes, start_date, end_date, period):
            self.called = True
            return {"success": True, "data": {"success": len(codes), "failed": 0}}

    class FakeDB:
        async def get_klines(self, code, start_date, end_date):
            return [{"date": "2025-01-01", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]

    class FakeEngine:
        @staticmethod
        def batch_backtest_sequential(codes, klines_dict, strategy, params):
            return {"success": True, "data": {"results": [{"success": True} for _ in codes]}}

    fake_sync = FakeSyncService()
    monkeypatch.setattr(backtest_tool, "data_sync_service", fake_sync)
    monkeypatch.setattr(backtest_tool, "get_db", lambda: FakeDB())
    monkeypatch.setattr(backtest_tool, "ParallelBacktestEngine", FakeEngine, raising=False)
    monkeypatch.setattr(backtest_tool, "RAY_AVAILABLE", False)

    mcp = FakeMCP()
    backtest_tool.register(mcp)
    result = asyncio.run(
        mcp.tools["run_batch_backtest"](
            codes=["000001", "600519"],
            use_parallel=False,
            warmup_before_fetch=True,
        )
    )

    assert result["success"] is True
    assert fake_sync.called is True
    assert result["data"]["warmup_enabled"] is True
    assert result["data"]["warmup"]["success"] is True


def test_data_sync_cache_key_v2_legacy_compat(monkeypatch):
    """验证缓存 key v2 读取优先级与 legacy 命中回填。"""

    class FakeCache:
        def __init__(self):
            self.store = {}
            self.set_calls = []

        def get(self, key, ttl_seconds):
            return self.store.get(key)

        def set(self, key, value):
            self.store[key] = value
            self.set_calls.append(key)

    fake_cache = FakeCache()
    monkeypatch.setattr(data_sync_module, "cache", fake_cache)

    service = DataSyncService()
    legacy_key = service._build_kline_cache_key_legacy("000001", "daily", "2024-01-01", "2024-12-31", 100)
    v2_key = service._build_kline_cache_key_v2("000001", "daily", "2024-01-01", "2024-12-31", 100)
    fake_cache.store[legacy_key] = [{"date": "2024-01-02", "close": 10, "open": 9, "high": 11, "low": 8, "volume": 1}]

    result = asyncio.run(
        service.get_kline_with_cache(
            stock_code="000001",
            period="daily",
            start_date="2024-01-01",
            end_date="2024-12-31",
            limit=100,
            use_cache=True,
        )
    )

    assert result["success"] is True
    assert result["source"] == "simple_cache"
    assert v2_key in fake_cache.store
    assert v2_key in fake_cache.set_calls
    assert result["data"][0]["change_pct"] == 0



def test_data_warmup_tool_warmup_status_clear(monkeypatch):
    """验证 data_warmup 工具三种 action 行为。"""
    from akshare_mcp.tools import data_warmup as data_warmup_tool

    class FakeSyncService:
        async def sync_stock_klines(self, codes, start_date, end_date, period):
            return {"success": True, "data": {"success": len(codes), "failed": 0}}

        def get_sync_metrics(self):
            return {"pending": 0, "success": 2, "fail": 0, "retry": 0, "lag": 0.0}

    class FakeCache:
        def __init__(self):
            self.cleared = 0

        def clear(self):
            self.cleared += 1
            return 3

        def get_cache_stats(self):
            return {"hit_rate": 0.5, "total_requests": 10}

    monkeypatch.setattr(data_warmup_tool, "data_sync_service", FakeSyncService())
    monkeypatch.setattr(data_warmup_tool, "cache", FakeCache())

    mcp = FakeMCP()
    data_warmup_tool.register(mcp)

    warmup_result = asyncio.run(
        mcp.tools["data_warmup"](
            action="warmup",
            stocks=["1", "600519"],
            lookback_days=30,
            force_update=True,
        )
    )
    assert warmup_result["success"] is True
    assert warmup_result["data"]["stocks_warmed"] == 2

    status_result = asyncio.run(mcp.tools["data_warmup"](action="status"))
    assert status_result["success"] is True
    assert "sync_metrics" in status_result["data"]
    assert "cache_stats" in status_result["data"]

    clear_result = asyncio.run(mcp.tools["data_warmup"](action="clear"))
    assert clear_result["success"] is True
    assert clear_result["data"]["cache_files_removed"] == 3

    bad_result = asyncio.run(mcp.tools["data_warmup"](action="unknown"))
    assert bad_result["success"] is False
    assert "Unknown action" in bad_result["error"]



def test_run_batch_backtest_contains_warmup_flag_by_default(monkeypatch):
    """验证未开启 warmup 时返回 warmup_enabled=False。"""

    class FakeDB:
        async def get_klines(self, code, start_date, end_date):
            return [{"date": "2025-01-01", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]

    class FakeEngine:
        @staticmethod
        def batch_backtest_sequential(codes, klines_dict, strategy, params):
            return {"success": True, "data": {"results": [{"success": True} for _ in codes]}}

    monkeypatch.setattr(backtest_tool, "get_db", lambda: FakeDB())
    monkeypatch.setattr(backtest_tool, "ParallelBacktestEngine", FakeEngine, raising=False)
    monkeypatch.setattr(backtest_tool, "RAY_AVAILABLE", False)

    mcp = FakeMCP()
    backtest_tool.register(mcp)
    result = asyncio.run(mcp.tools["run_batch_backtest"](codes=["000001"], use_parallel=False))

    assert result["success"] is True
    assert result["data"]["warmup_enabled"] is False
    assert "warmup" not in result["data"]




def test_data_sync_dead_letter_persistence_and_metrics(tmp_path, monkeypatch):
    """验证最终失败会写入 dead-letter，且指标/读取/清理可用。"""

    class FakeCache:
        def __init__(self, cache_dir):
            self.cache_dir = str(cache_dir)

        def get(self, key, ttl_seconds):
            return None

        def set(self, key, value):
            return None

    monkeypatch.setattr(data_sync_module, "cache", FakeCache(tmp_path / "cache"))
    service = DataSyncService(dead_letter_dir=str(tmp_path / "dlq"))
    service._max_retry = 0

    async def always_fail_save(stock_code, klines):
        raise RuntimeError("db down")

    monkeypatch.setattr(service, "_save_klines_to_db", always_fail_save)

    item = {
        "stock_code": "000001",
        "klines": [{"date": "2025-01-02", "close": 10.0}],
        "retry": 0,
        "enqueued_at": 123.45,
    }
    asyncio.run(service._save_klines_with_retry(item))

    dlq = service.get_dead_letters(limit=10)
    assert dlq["success"] is True
    assert dlq["count"] == 1
    assert dlq["records"][0]["stock_code"] == "000001"
    assert "db down" in dlq["records"][0]["error"]

    metrics = service.get_sync_metrics()
    assert metrics["fail"] == 1
    assert metrics["dead_letter"] == 1
    assert metrics["dead_letter_path"].endswith("kline_save_failures.jsonl")

    cleared = service.clear_dead_letters()
    assert cleared["success"] is True
    assert cleared["removed"] in (0, 1)
    assert service.get_dead_letters(limit=10)["count"] == 0


def test_data_sync_tools_expose_dead_letter_status(monkeypatch):
    """验证 MCP 工具层暴露 get_sync_status/get_dead_letters/clear_dead_letters。"""

    class FakeSyncService:
        def get_sync_metrics(self):
            return {"pending": 0, "success": 3, "fail": 1, "retry": 2, "lag": 0.1, "dead_letter": 1}

        def get_dead_letters(self, limit=20):
            return {
                "success": True,
                "path": "/tmp/dlq.jsonl",
                "count": 1,
                "records": [{"stock_code": "000001", "error": "x"}],
            }

        def clear_dead_letters(self):
            return {"success": True, "removed": 1, "path": "/tmp/dlq.jsonl"}

    monkeypatch.setattr(data_sync_tool, "data_sync_service", FakeSyncService())

    mcp = FakeMCP()
    data_sync_tool.register(mcp)

    status = mcp.tools["get_sync_status"]()
    assert status["success"] is True
    assert status["dead_letters"]["count"] == 1

    records = mcp.tools["get_dead_letters"](limit=5)
    assert records["success"] is True
    assert records["count"] == 1

    cleared = mcp.tools["clear_dead_letters"]()
    assert cleared["success"] is True
    assert cleared["removed"] == 1


def test_vector_search_index_backend_and_fallback(monkeypatch):
    """验证 index 主路径命中，以及异常时 python_fallback。"""
    pytest.importorskip("sklearn")
    from akshare_mcp.services.vector_search import VectorSearchEngine

    engine = VectorSearchEngine()

    query = [
        {"close": 10.0, "volume": 100},
        {"close": 10.3, "volume": 101},
        {"close": 10.1, "volume": 102},
        {"close": 10.4, "volume": 103},
        {"close": 10.2, "volume": 104},
    ]
    candidates = {
        "AAA": [
            {"close": 8.0, "volume": 90},
            {"close": 8.2, "volume": 91},
            {"close": 8.1, "volume": 92},
            {"close": 8.3, "volume": 93},
            {"close": 8.25, "volume": 94},
        ],
        "BBB": [
            {"close": 6.0, "volume": 80},
            {"close": 6.1, "volume": 81},
            {"close": 6.2, "volume": 82},
            {"close": 6.3, "volume": 83},
            {"close": 6.4, "volume": 84},
        ],
    }

    hit = engine.find_similar_patterns(
        query_klines=query,
        candidate_klines_dict=candidates,
        top_k=2,
        method="returns",
        metric="correlation",
        backend="index",
        allow_fallback=True,
    )
    assert len(hit) >= 1
    assert engine.last_backend_used == "index"
    assert all(item["source"] == "index" for item in hit)

    def broken_search_index(query_vector, top_k=10, metric="cosine"):
        raise RuntimeError("index broken")

    monkeypatch.setattr(engine, "search_index", broken_search_index)
    fallback = engine.find_similar_patterns(
        query_klines=query,
        candidate_klines_dict=candidates,
        top_k=2,
        method="returns",
        metric="correlation",
        backend="index",
        allow_fallback=True,
    )
    assert len(fallback) >= 1
    assert engine.last_backend_used == "python_fallback"
    assert all(item["source"] == "python_fallback" for item in fallback)


def test_factor_market_returns_pass_through_affects_beta():
    """验证 market_returns 贯通后，beta 不再固定为默认值。"""

    market_returns = [0.01, -0.004, 0.008, -0.003, 0.006] * 12  # 60 points
    stock_returns = [2 * r for r in market_returns]

    close = 100.0
    klines = []
    for i, r in enumerate(stock_returns):
        close = close * (1 + r)
        klines.append({"date": f"2025-01-{i+1:02d}", "close": close, "volume": 1000 + i})

    factors_with_market = FactorCalculatorExtended.calculate_all_factors(
        klines=klines,
        market_returns=market_returns,
    )
    beta_with_market = factors_with_market["volatility"]["beta"]

    factors_without_market = FactorCalculatorExtended.calculate_all_factors(
        klines=klines,
        market_returns=None,
    )
    beta_without_market = factors_without_market["volatility"]["beta"]

    assert beta_with_market > 1.5
    assert beta_without_market == 1.0
    assert beta_with_market != beta_without_market
