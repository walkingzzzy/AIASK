import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from akshare_mcp.services.strategy_factory import BacktestFilter


def _make_klines(n=200, base=10.0):
    price = base
    rows = []
    for i in range(n):
        price *= 1.002
        rows.append(
            {
                "time": f"2024-01-{(i % 28) + 1:02d}",
                "open": round(price * 0.998, 2),
                "high": round(price * 1.01, 2),
                "low": round(price * 0.99, 2),
                "close": round(price, 2),
                "volume": 10000 + i,
            }
        )
    return rows


def _make_backtest_result(sharpe: float, mdd: float, trades: float, total_return: float = 0.12, win_rate: float = 0.55) -> dict:
    return {
        "success": True,
        "data": {
            "sharpe_ratio": sharpe,
            "total_return": total_return,
            "max_drawdown": mdd,
            "win_rate": win_rate,
            "trades_count": trades,
        },
    }


@pytest.mark.asyncio
async def test_filter_runs_candidate_codes_concurrently(monkeypatch):
    import akshare_mcp.services.strategy_factory.backtest_filter as backtest_filter_mod

    monkeypatch.setattr(backtest_filter_mod, "REPRESENTATIVE_STOCKS", [])
    monkeypatch.setattr(backtest_filter_mod, "BACKTEST_CODE_CONCURRENCY", 3)

    bt_filter = BacktestFilter()
    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519", "000858", "601318"],
        "stock_pool": {"selection_mode": "explicit", "symbols": ["600519", "000858", "601318"]},
    }
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=_make_klines())

    state = {"active": 0, "peak": 0}

    async def _fake_to_thread(*_args, **_kwargs):
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.01)
        state["active"] -= 1
        return _make_backtest_result(0.52, 0.12, 5)

    with patch("akshare_mcp.services.strategy_factory.asyncio.to_thread", new=_fake_to_thread):
        passed = await bt_filter.filter([candidate], db)

    assert len(passed) == 1
    assert state["peak"] > 1
    result = candidate["backtest_result"]
    assert result["evaluated_code_count"] == 3
    assert result["successful_code_count"] == 3
    assert result["backtest_run_ms"] > 0
    assert result["avg_code_ms"] > 0


@pytest.mark.asyncio
async def test_filter_reuses_preloaded_klines_without_duplicate_fetches(monkeypatch):
    import akshare_mcp.services.strategy_factory.backtest_filter as backtest_filter_mod

    monkeypatch.setattr(backtest_filter_mod, "REPRESENTATIVE_STOCKS", [])
    monkeypatch.setattr(backtest_filter_mod, "BACKTEST_CODE_CONCURRENCY", 2)

    bt_filter = BacktestFilter()
    candidates = [
        {
            "strategy_type": "momentum",
            "params": {"lookback": 20, "threshold": 0.02},
            "target_symbols": ["600519", "000858", "601318"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519", "000858", "601318"]},
        },
        {
            "strategy_type": "momentum",
            "params": {"lookback": 30, "threshold": 0.03},
            "target_symbols": ["600519", "000858", "601318"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519", "000858", "601318"]},
        },
    ]

    call_counts = {}

    async def _get_klines(code, limit=500):
        del limit
        call_counts[code] = call_counts.get(code, 0) + 1
        return _make_klines()

    db = MagicMock()
    db.get_klines = AsyncMock(side_effect=_get_klines)

    with patch(
        "akshare_mcp.services.strategy_factory.asyncio.to_thread",
        new=AsyncMock(return_value=_make_backtest_result(0.52, 0.12, 5)),
    ):
        passed = await bt_filter.filter(candidates, db)

    assert len(passed) == 2
    assert call_counts == {"600519": 1, "000858": 1, "601318": 1}
    for candidate in candidates:
        assert candidate["backtest_result"]["kline_cache_hit_count"] == 3
    report_summary = bt_filter.get_last_report()["summary"]
    assert report_summary["cache_hit_ratio"] == 1.0
    assert report_summary["avg_candidate_ms"] > 0
    assert report_summary["avg_code_ms"] >= 0


@pytest.mark.asyncio
async def test_filter_keeps_results_consistent_across_code_concurrency_levels(monkeypatch):
    import akshare_mcp.services.strategy_factory.backtest_filter as backtest_filter_mod

    monkeypatch.setattr(backtest_filter_mod, "REPRESENTATIVE_STOCKS", [])

    async def _fake_to_thread(_func, code, _klines, _strategy_type, _params):
        sharpe_by_code = {"600519": 0.61, "000858": 0.55, "601318": 0.58}
        return _make_backtest_result(sharpe_by_code[code], 0.12, 5)

    candidate_serial = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519", "000858", "601318"],
        "stock_pool": {"selection_mode": "explicit", "symbols": ["600519", "000858", "601318"]},
    }
    candidate_parallel = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519", "000858", "601318"],
        "stock_pool": {"selection_mode": "explicit", "symbols": ["600519", "000858", "601318"]},
    }

    monkeypatch.setattr(backtest_filter_mod, "BACKTEST_CODE_CONCURRENCY", 1)
    serial_filter = BacktestFilter()
    serial_db = MagicMock()
    serial_db.get_klines = AsyncMock(return_value=_make_klines())
    with patch("akshare_mcp.services.strategy_factory.asyncio.to_thread", new=_fake_to_thread):
        serial_passed = await serial_filter.filter([candidate_serial], serial_db)

    monkeypatch.setattr(backtest_filter_mod, "BACKTEST_CODE_CONCURRENCY", 3)
    parallel_filter = BacktestFilter()
    parallel_db = MagicMock()
    parallel_db.get_klines = AsyncMock(return_value=_make_klines())
    with patch("akshare_mcp.services.strategy_factory.asyncio.to_thread", new=_fake_to_thread):
        parallel_passed = await parallel_filter.filter([candidate_parallel], parallel_db)

    assert len(serial_passed) == len(parallel_passed) == 1
    serial_result = candidate_serial["backtest_result"]
    parallel_result = candidate_parallel["backtest_result"]
    assert serial_result["passed"] == parallel_result["passed"] is True
    assert serial_result["reason_code"] == parallel_result["reason_code"] == "passed"
    assert serial_result["metrics"] == parallel_result["metrics"]
    assert serial_result["successful_code_count"] == parallel_result["successful_code_count"] == 3
