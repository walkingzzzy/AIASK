from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_script_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts" / "audit_sync_core_market_data.py"
    spec = importlib.util.spec_from_file_location("audit_sync_core_market_data_test_mod", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeConn:
    async def execute(self, *args, **kwargs):
        del args, kwargs
        return None

    async def executemany(self, *args, **kwargs):
        del args, kwargs
        return None


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


class _FakeDb:
    def __init__(self):
        self.conn = _FakeConn()

    def acquire(self):
        return _AcquireCtx(self.conn)


@pytest.mark.asyncio
async def test_sync_north_fund_skips_ip_limit_error(monkeypatch):
    mod = _load_script_module()

    class _FakePro:
        def moneyflow_hsgt(self, **kwargs):
            del kwargs
            raise RuntimeError("您的IP数量超限，最大数量为2个！")

    monkeypatch.setattr(mod.data_source, "get_tushare_pro", lambda: _FakePro())

    result = await mod._sync_north_fund(_FakeDb(), days=30)

    assert result["skipped"] is True
    assert "IP数量超限" in result["skip_reason"]
    assert result["rows"] == 0


@pytest.mark.asyncio
async def test_sync_margin_skips_ip_limit_error(monkeypatch):
    mod = _load_script_module()

    class _FakePro:
        def margin(self, **kwargs):
            del kwargs
            raise RuntimeError("您的IP数量超限，最大数量为2个！")

        def margin_detail(self, **kwargs):
            del kwargs
            raise AssertionError("margin_detail should not run after IP limit")

    monkeypatch.setattr(mod.data_source, "get_tushare_pro", lambda: _FakePro())
    monkeypatch.setattr(mod.data_source, "get_trading_dates", lambda **kwargs: {"data": ["20260320", "20260321"]})

    result = await mod._sync_margin(_FakeDb(), days=10)

    assert result["skipped"] is True
    assert "IP数量超限" in result["skip_reason"]
    assert result["market_rows"] == 0
    assert result["detail_rows"] == 0
    assert result["failed_dates"] == []


@pytest.mark.asyncio
async def test_main_keeps_success_exit_code_when_aux_syncs_are_skipped(monkeypatch):
    mod = _load_script_module()
    sections: dict[str, dict] = {}
    fake_db = object()

    monkeypatch.setattr(mod, "load_mcp_env", lambda override=False: None)
    monkeypatch.setattr(mod, "get_db", lambda: fake_db)
    monkeypatch.setattr(mod, "_print_section", lambda title, payload: sections.setdefault(title, payload))

    async def _fake_ensure_aux_market_tables(db):
        assert db is fake_db

    async def _fake_audit_codes(db, codes):
        assert db is fake_db
        return [{"code": code, "count": 0, "min_date": None, "max_date": None} for code in codes]

    async def _fake_audit_market_aux(db):
        assert db is fake_db
        return {}

    async def _fake_sync_trading_calendar(db, *, years):
        assert db is fake_db
        return {"years": years}

    async def _fake_sync_indices(db, *, start_date, end_date):
        assert db is fake_db
        return {"codes": [], "saved_rows": 12, "fetched_rows": 12, "failed": []}

    async def _fake_sync_stocks(db, *, stock_codes, start_date, end_date):
        assert db is fake_db
        return {"codes": [], "saved_rows": 8, "fetched_rows": 8, "failed": []}

    async def _fake_sync_north_fund(db, *, days):
        assert db is fake_db
        return {
            "days": days,
            "rows": 0,
            "start_date": "20260101",
            "end_date": "20260131",
            "skipped": True,
            "skip_reason": "您的IP数量超限，最大数量为2个！",
        }

    async def _fake_sync_margin(db, *, days):
        assert db is fake_db
        return {
            "days": days,
            "trade_dates": 0,
            "market_rows": 0,
            "detail_rows": 0,
            "failed_dates": [],
            "start_date": "20260101",
            "end_date": "20260131",
            "skipped": True,
            "skip_reason": "您的IP数量超限，最大数量为2个！",
        }

    monkeypatch.setattr(mod, "_ensure_aux_market_tables", _fake_ensure_aux_market_tables)
    monkeypatch.setattr(mod, "_audit_codes", _fake_audit_codes)
    monkeypatch.setattr(mod, "_audit_market_aux", _fake_audit_market_aux)
    monkeypatch.setattr(mod, "_sync_trading_calendar", _fake_sync_trading_calendar)
    monkeypatch.setattr(mod, "_sync_indices", _fake_sync_indices)
    monkeypatch.setattr(mod, "_sync_stocks", _fake_sync_stocks)
    monkeypatch.setattr(mod, "_sync_north_fund", _fake_sync_north_fund)
    monkeypatch.setattr(mod, "_sync_margin", _fake_sync_margin)

    args = SimpleNamespace(
        years=1,
        stock_codes="600519,000858",
        calendar_year=2026,
        north_days=30,
        margin_days=15,
    )

    exit_code = await mod._main(args)

    assert exit_code == 0
    assert sections["summary"]["north_fund_skipped"] is True
    assert sections["summary"]["margin_skipped"] is True
    assert "IP数量超限" in sections["summary"]["north_fund_skip_reason"]
    assert "IP数量超限" in sections["summary"]["margin_skip_reason"]


@pytest.mark.asyncio
async def test_main_treats_existing_index_and_stock_data_as_degraded_skip_on_ip_limit(monkeypatch):
    mod = _load_script_module()
    sections: dict[str, dict] = {}
    fake_db = object()

    monkeypatch.setattr(mod, "load_mcp_env", lambda override=False: None)
    monkeypatch.setattr(mod, "get_db", lambda: fake_db)
    monkeypatch.setattr(mod, "_print_section", lambda title, payload: sections.setdefault(title, payload))

    async def _fake_ensure_aux_market_tables(db):
        assert db is fake_db

    async def _fake_audit_codes(db, codes):
        assert db is fake_db
        return [
            {"code": str(code), "count": 1200, "min_date": "2021-03-22", "max_date": "2026-04-09"}
            for code in codes
        ]

    async def _fake_audit_market_aux(db):
        assert db is fake_db
        return {}

    async def _fake_sync_trading_calendar(db, *, years):
        assert db is fake_db
        return {"years": years}

    async def _fake_sync_indices(db, *, start_date, end_date):
        del start_date, end_date
        assert db is fake_db
        return {
            "codes": [],
            "saved_rows": 0,
            "fetched_rows": 0,
            "failed": [
                {"code": "sh000001", "ts_code": "000001.SH", "error": "您的IP数量超限，最大数量为2个！"},
                {"code": "sh000300", "ts_code": "000300.SH", "error": "您的IP数量超限，最大数量为2个！"},
            ],
        }

    async def _fake_sync_stocks(db, *, stock_codes, start_date, end_date):
        del start_date, end_date
        assert db is fake_db
        return {
            "codes": [],
            "saved_rows": 0,
            "fetched_rows": 0,
            "failed": [
                {"code": str(code), "ts_code": f"{code}.SH", "error": "您的IP数量超限，最大数量为2个！"}
                for code in stock_codes
            ],
        }

    async def _fake_sync_north_fund(db, *, days):
        assert db is fake_db
        return {
            "days": days,
            "rows": 0,
            "start_date": "20260101",
            "end_date": "20260131",
            "skipped": True,
            "skip_reason": "您的IP数量超限，最大数量为2个！",
        }

    async def _fake_sync_margin(db, *, days):
        assert db is fake_db
        return {
            "days": days,
            "trade_dates": 0,
            "market_rows": 0,
            "detail_rows": 0,
            "failed_dates": [],
            "start_date": "20260101",
            "end_date": "20260131",
            "skipped": True,
            "skip_reason": "您的IP数量超限，最大数量为2个！",
        }

    monkeypatch.setattr(mod, "_ensure_aux_market_tables", _fake_ensure_aux_market_tables)
    monkeypatch.setattr(mod, "_audit_codes", _fake_audit_codes)
    monkeypatch.setattr(mod, "_audit_market_aux", _fake_audit_market_aux)
    monkeypatch.setattr(mod, "_sync_trading_calendar", _fake_sync_trading_calendar)
    monkeypatch.setattr(mod, "_sync_indices", _fake_sync_indices)
    monkeypatch.setattr(mod, "_sync_stocks", _fake_sync_stocks)
    monkeypatch.setattr(mod, "_sync_north_fund", _fake_sync_north_fund)
    monkeypatch.setattr(mod, "_sync_margin", _fake_sync_margin)

    args = SimpleNamespace(
        years=1,
        stock_codes="600519,000858",
        calendar_year=2026,
        north_days=30,
        margin_days=15,
    )

    exit_code = await mod._main(args)

    assert exit_code == 0
    assert sections["summary"]["index_skipped"] is True
    assert sections["summary"]["stock_skipped"] is True
    assert "IP数量超限" in sections["summary"]["index_skip_reason"]
    assert "IP数量超限" in sections["summary"]["stock_skip_reason"]
