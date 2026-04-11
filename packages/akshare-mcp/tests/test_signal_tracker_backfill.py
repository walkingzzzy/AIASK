from __future__ import annotations

from datetime import date

import pytest

from akshare_mcp.services.signal_tracker import SignalTracker


class _BackfillDB:
    def __init__(self):
        self.pending_calls = 0
        self.kline_calls: list[dict] = []
        self.saved_batches: list[list[dict]] = []

    async def get_pending_forward_returns(
        self,
        forward_days: int,
        limit: int = 500,
        after_signal_date=None,
        after_id=None,
    ):
        self.pending_calls += 1
        if self.pending_calls > 1:
            return []
        assert forward_days == 1
        assert limit == 50
        assert after_signal_date is None
        assert after_id in (None, 0)
        return [
            {
                "id": 11,
                "strategy_id": "sid_a",
                "signal_date": date(2026, 4, 2),
                "code": "600519",
                "signal": 1,
            },
            {
                "id": 12,
                "strategy_id": "sid_b",
                "signal_date": date(2026, 4, 3),
                "code": "600519",
                "signal": -1,
            },
        ]

    async def get_klines(self, code: str, start_date=None, end_date=None, limit=None):
        self.kline_calls.append(
            {
                "code": code,
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit,
            }
        )
        return [
            {"date": "2026-04-02", "close": 10.0, "volume": 1000},
            {"date": "2026-04-03", "close": 11.0, "volume": 1000},
            {"date": "2026-04-04", "close": 12.0, "volume": 1000},
        ]

    async def save_forward_returns_batch(self, rows):
        self.saved_batches.append(list(rows))
        return len(rows)


@pytest.mark.asyncio
async def test_signal_tracker_backfills_pending_forward_returns_from_historical_series():
    tracker = SignalTracker()
    db = _BackfillDB()

    result = await tracker.backfill_forward_returns(
        db,
        forward_days_list=[1],
        batch_limit=50,
        max_rounds=3,
    )

    assert result["computed"] == 2
    assert result["windows"]["1D"]["computed"] == 2
    assert result["windows"]["1D"]["stalled"] is False
    assert db.kline_calls == [
        {
            "code": "600519",
            "start_date": "2026-04-02",
            "end_date": None,
            "limit": None,
        }
    ]
    assert len(db.saved_batches) == 1
    assert db.saved_batches[0][0]["signal_id"] == 11
    assert db.saved_batches[0][0]["forward_days"] == 1
    assert db.saved_batches[0][0]["actual_return"] == pytest.approx(0.1)
    assert db.saved_batches[0][1]["signal_id"] == 12
    assert db.saved_batches[0][1]["actual_return"] == pytest.approx(12.0 / 11.0 - 1.0)
