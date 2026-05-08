from __future__ import annotations

import asyncio
from datetime import date

from akshare_mcp.services.incubation import StrategyIncubationService


class _HistoricalPriceDb:
    def __init__(self):
        self.calls: list[tuple[str, str | None, int | None]] = []

    async def get_klines(self, code: str, start_date=None, end_date=None, limit=None):
        self.calls.append((code, end_date, limit))
        if end_date == "2026-04-17":
            return [{"date": "2026-04-17", "close": 11.2}]
        return [{"date": "2026-04-18", "close": 13.4}]


class _ReplayDb:
    def __init__(self):
        self.signal_rows = [
            {"strategy_id": "strategy-replay", "code": "600000", "signal_date": date(2026, 4, 17), "signal": 1},
            {"strategy_id": "strategy-replay", "code": "600000", "signal_date": date(2026, 4, 21), "signal": -1},
        ]

    async def get_signals(self, strategy_id: str, start_date=None, end_date=None, limit: int = 100):
        rows = [dict(item) for item in self.signal_rows if item["strategy_id"] == strategy_id]
        if start_date is not None:
            rows = [item for item in rows if item["signal_date"] >= start_date]
        if end_date is not None:
            rows = [item for item in rows if item["signal_date"] <= end_date]
        rows.sort(key=lambda item: item["signal_date"], reverse=True)
        return rows[:limit]

    async def get_klines(self, code: str, start_date=None, end_date=None, limit=None):
        assert code == "600000"
        rows = [
            {"date": "2026-04-17", "close": 10.0},
            {"date": "2026-04-18", "close": 10.5},
            {"date": "2026-04-21", "close": 10.8},
        ]
        if start_date:
            rows = [row for row in rows if row["date"] >= str(start_date)]
        if end_date:
            rows = [row for row in rows if row["date"] <= str(end_date)]
        if limit is not None:
            rows = rows[-int(limit):]
        return rows


class _MultiCodeReplayDb:
    async def get_signals(self, strategy_id: str, start_date=None, end_date=None, limit: int = 100):
        return []

    async def get_klines(self, code: str, start_date=None, end_date=None, limit=None):
        rows_by_code = {
            "600000": [
                {"date": "2026-04-17", "close": 10.0},
                {"date": "2026-04-18", "close": 10.5},
            ],
            "600519": [
                {"date": "2026-04-20", "close": 1200.0},
                {"date": "2026-04-21", "close": 1210.0},
            ],
        }
        return rows_by_code.get(code, [])


class _RecordingReplayService(StrategyIncubationService):
    def __init__(self):
        super().__init__()
        self.replayed_dates: list[date] = []
        self.force_close_calls: list[date] = []

    async def process_strategies(self, db, strategies: list[dict], signal_date=None):
        self.replayed_dates.append(signal_date)
        return {
            "count": len(strategies),
            "accounts_bound": 0,
            "orders_created": 1,
            "orders_filled": 1,
            "rejected_orders": 0,
            "nav_snapshots": 1,
            "metrics_recorded": 1,
            "items": [{"strategy_id": strategies[0]["id"], "signal_date": str(signal_date)}],
        }

    async def force_close_open_positions(self, db, strategy: dict, signal_date: date, **kwargs):
        self.force_close_calls.append(signal_date)
        return {
            "strategy_id": strategy["id"],
            "account_id": "inc-test",
            "created_count": 1,
            "skipped_count": 0,
            "orders": [{"id": 1, "code": "600000"}],
            "reason": kwargs.get("reason") or "replay_window_end_forced_exit",
        }

    async def settle_orders(self, db, strategy: dict, signal_date=None):
        return {
            "strategy_id": strategy["id"],
            "account_id": "inc-test",
            "filled_count": 1,
            "rejected_count": 0,
            "nav_snapshot": {"total_value": 100000.0},
        }

    async def record_metrics(self, db, strategy: dict, metric_date=None):
        return {"strategy_id": strategy["id"], "metric_date": str(metric_date)}


def test_price_on_or_before_uses_historical_close_before_falling_back():
    service = StrategyIncubationService()
    db = _HistoricalPriceDb()

    historical_price = asyncio.run(
        service._price_on_or_before(db, "600000", date(2026, 4, 17))
    )
    latest_price = asyncio.run(service._price_on_or_before(db, "600000", None))

    assert historical_price == 11.2
    assert latest_price == 13.4
    assert db.calls[0] == ("600000", "2026-04-17", 1)


def test_replay_strategy_history_replays_market_days_in_chronological_order():
    service = _RecordingReplayService()
    db = _ReplayDb()
    strategy = {
        "id": "strategy-replay",
        "target_symbols": ["600000"],
    }

    result = asyncio.run(
        service.replay_strategy_history(
            db,
            strategy,
            start_date=date(2026, 4, 17),
            end_date=date(2026, 4, 21),
            include_market_days=True,
            run_acceptance=False,
        )
    )

    assert service.replayed_dates == [
        date(2026, 4, 17),
        date(2026, 4, 18),
        date(2026, 4, 21),
    ]
    assert result["replayed_days"] == 3
    assert result["non_empty_days"] == 3
    assert result["orders_filled"] == 3
    assert result["start_date"] == "2026-04-17"
    assert result["end_date"] == "2026-04-21"


def test_replay_strategy_history_unions_market_days_from_multiple_target_codes():
    service = _RecordingReplayService()
    db = _MultiCodeReplayDb()
    strategy = {
        "id": "strategy-replay",
        "target_symbols": ["600000", "600519"],
    }

    result = asyncio.run(
        service.replay_strategy_history(
            db,
            strategy,
            start_date=date(2026, 4, 17),
            end_date=date(2026, 4, 21),
            include_market_days=True,
            run_acceptance=False,
        )
    )

    assert service.replayed_dates == [
        date(2026, 4, 17),
        date(2026, 4, 18),
        date(2026, 4, 20),
        date(2026, 4, 21),
    ]
    assert result["replayed_days"] == 4


def test_replay_strategy_history_can_force_close_open_positions_at_window_end():
    service = _RecordingReplayService()
    db = _ReplayDb()
    strategy = {
        "id": "strategy-replay",
        "target_symbols": ["600000"],
    }

    result = asyncio.run(
        service.replay_strategy_history(
            db,
            strategy,
            start_date=date(2026, 4, 17),
            end_date=date(2026, 4, 21),
            include_market_days=True,
            force_close_open_positions=True,
            run_acceptance=False,
        )
    )

    assert service.force_close_calls == [date(2026, 4, 21)]
    assert result["orders_created"] == 4
    assert result["orders_filled"] == 4
    assert result["metrics_recorded"] == 4
    assert result["daily_results"][-1]["window_force_close"] is True
