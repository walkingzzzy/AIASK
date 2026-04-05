import pytest

import akshare_mcp.tools.formula_fallback as formula_fallback_mod
import akshare_mcp.tools.managers.screener_manager as screener_manager_mod
from akshare_mcp.services import screen_conditions as _screen_conditions  # noqa: F401


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


def _make_upn_klines(n_up: int = 5) -> list[dict]:
    closes = [10.0]
    for _ in range(n_up):
        closes.append(round(closes[-1] * 1.03, 2))
    rows = []
    for idx, close in enumerate(closes):
        rows.append(
            {
                "date": f"2025-01-{idx + 1:02d}",
                "open": round(close * 0.99, 2),
                "high": round(close * 1.01, 2),
                "low": round(close * 0.98, 2),
                "close": close,
                "volume": 1_000_000,
                "amount": close * 1_000_000,
            }
        )
    return rows


def _make_flat_klines(days: int = 6) -> list[dict]:
    return [
        {
            "date": f"2025-01-{idx + 1:02d}",
            "open": 10.0,
            "high": 10.1,
            "low": 9.9,
            "close": 10.0,
            "volume": 1_000_000,
            "amount": 10_000_000,
        }
        for idx in range(days)
    ]


def test_formula_fallback_should_fall_back_to_akshare_when_legacy_chain_is_empty(monkeypatch):
    class _FakeDF:
        empty = False

        def tail(self, count):
            assert count == 2
            return self

        def iterrows(self):
            rows = [
                {"日期": "2025-01-01", "开盘": 10.0, "收盘": 10.1, "最高": 10.2, "最低": 9.9, "成交量": 100},
                {"日期": "2025-01-02", "开盘": 10.1, "收盘": 10.3, "最高": 10.4, "最低": 10.0, "成交量": 120},
            ]
            for idx, row in enumerate(rows):
                yield idx, row

    class _FakeAk:
        @staticmethod
        def stock_zh_a_hist(symbol: str, period: str = "daily", adjust: str = "qfq"):
            assert symbol == "600519"
            assert period == "daily"
            assert adjust == "qfq"
            return _FakeDF()

    monkeypatch.setattr(formula_fallback_mod.data_source, "get_kline", lambda *args, **kwargs: [])
    monkeypatch.setattr(formula_fallback_mod, "ak", _FakeAk())

    rows = formula_fallback_mod.get_kline_for_formula_fallback("600519", "daily", 2)

    assert len(rows) == 2
    assert rows[-1]["close"] == 10.3


@pytest.mark.asyncio
async def test_technical_screen_should_execute_and_honor_limit(monkeypatch):
    mcp = _DummyMCP()
    screener_manager_mod.register_screener_manager(mcp)

    async def _fake_pool(*args, **kwargs):
        return {
            "stocks": [
                {"code": "600519", "name": "贵州茅台", "klines": _make_upn_klines(5)},
                {"code": "000001", "name": "平安银行", "klines": _make_upn_klines(4)},
            ],
            "diagnostics": {
                "pool_size": 2,
                "pool_truncated": False,
                "original_pool_size": 2,
                "success_count": 2,
                "timeout_count": 0,
                "error_count": 0,
                "elapsed_ms": 12,
            },
        }

    monkeypatch.setattr(screener_manager_mod, "_get_stock_pool_with_klines", _fake_pool)

    result = await mcp.screener_manager(
        action="technical_screen",
        kwargs='{"conditions":["upn"],"logic":"AND","params":{"n":3},"limit":1}',
    )

    assert result["success"] is True
    assert result["data"]["conditions"] == ["upn"]
    assert result["data"]["matched_count"] == 1
    assert len(result["data"]["matched"]) == 1
    assert result["data"]["matched"][0]["code"] == "600519"


class _ScreenConn:
    async def fetch(self, query, *args):
        return [
            {
                "code": "600519",
                "stock_name": "贵州茅台",
                "market_cap": 1_000_000_000.0,
                "pe_ratio": 18.0,
                "pb_ratio": 3.0,
                "roe": 20.0,
                "revenue_growth": 10.0,
                "debt_ratio": 20.0,
                "industry": "白酒",
            },
            {
                "code": "000001",
                "stock_name": "平安银行",
                "market_cap": 800_000_000.0,
                "pe_ratio": 10.0,
                "pb_ratio": 1.0,
                "roe": 18.0,
                "revenue_growth": 8.0,
                "debt_ratio": 30.0,
                "industry": "银行",
            },
        ]


class _ScreenDB:
    def acquire(self):
        return _Acquire(_ScreenConn())

    async def _financials_code_column(self, conn):
        return "stock_code"


@pytest.mark.asyncio
async def test_combined_screen_should_preserve_technical_conditions_and_fill_name(monkeypatch):
    mcp = _DummyMCP()
    screener_manager_mod.register_screener_manager(mcp)
    monkeypatch.setattr(screener_manager_mod, "get_db", lambda: _ScreenDB())

    async def _fake_pool(stock_codes, *args, **kwargs):
        assert "600519" in stock_codes
        return {
            "stocks": [
                {"code": "600519", "name": "", "klines": _make_upn_klines(5)},
                {"code": "000001", "name": "", "klines": _make_flat_klines()},
            ],
            "diagnostics": {
                "pool_size": len(stock_codes),
                "pool_truncated": False,
                "original_pool_size": len(stock_codes),
                "success_count": 2,
                "timeout_count": 0,
                "error_count": 0,
                "elapsed_ms": 8,
            },
        }

    monkeypatch.setattr(screener_manager_mod, "_get_stock_pool_with_klines", _fake_pool)

    result = await mcp.screener_manager(
        action="combined_screen",
        kwargs='{"fundamental_criteria":{"max_pe":20.0,"min_roe":0.15},"technical_conditions":["upn"],"logic":"AND","params":{"n":3},"limit":1}',
    )

    assert result["success"] is True
    assert result["data"]["tech_conditions"] == ["upn"]
    assert result["data"]["technical_conditions"] == ["upn"]
    assert result["data"]["matched_count"] == 1
    assert result["data"]["matched"][0]["code"] == "600519"
    assert result["data"]["matched"][0]["name"] == "贵州茅台"
    assert result["data"]["matched"][0]["matched_conditions"] == ["upn", "fundamental_criteria"]
