from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from akshare_mcp.tools.semantic import daily_report as daily_report_mod


class _DailyReportDb:
    def __init__(self):
        self.get_north_fund_history = AsyncMock(
            return_value=[
                {
                    "trade_date": date(2026, 3, 20),
                    "north_money": 123.45,
                    "hgt": 70.0,
                    "sgt": 53.45,
                    "source": "north_fund_flow",
                }
            ]
        )


@pytest.mark.asyncio
async def test_generate_daily_report_prefers_db_north_fund(monkeypatch):
    db = _DailyReportDb()
    monkeypatch.setattr(daily_report_mod, "get_db", lambda: db)
    monkeypatch.setattr(
        daily_report_mod,
        "_fetch_index_quotes",
        lambda: {
            "000001": {
                "name": "上证指数",
                "close": 3100.0,
                "change_pct": 1.23,
                "volume": 100,
                "amount": 200,
            }
        },
    )

    async def _fake_stats(_db, _report_date):
        return {
            "up_count": 3000,
            "down_count": 1200,
            "limit_up_count": 66,
            "limit_down_count": 4,
            "total_count": 4200,
        }

    async def _fake_hot_sectors(_db):
        return [{"name": "半导体", "change_pct": 3.21, "stock_count": 48}]

    monkeypatch.setattr(daily_report_mod, "_fetch_stats", _fake_stats)
    monkeypatch.setattr(daily_report_mod, "_fetch_hot_sectors", _fake_hot_sectors)
    monkeypatch.setattr(
        daily_report_mod.data_source,
        "get_tushare_pro",
        lambda: (_ for _ in ()).throw(AssertionError("tushare fallback should not run")),
    )

    result = await daily_report_mod.generate_daily_report(date="2026-03-22")

    assert result["success"] is True
    data = result["data"]
    north = data["capital_flow"]["north_fund"]
    main_fund = data["capital_flow"]["main_fund"]
    assert north["net_inflow"] == 123.45
    assert north["sh_connect"] == 70.0
    assert north["sz_connect"] == 53.45
    assert north["source"] == "north_fund_flow"
    assert main_fund["source"] == "north_fund_flow"
    assert "DB北向资金净流入代理主力资金" in main_fund["note"]
    db.get_north_fund_history.assert_awaited_once_with(days=3, end_date=date(2026, 3, 22))

