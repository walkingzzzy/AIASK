import pytest
from datetime import datetime

import akshare
import akshare_mcp.baostock_api as bs_api_mod
import akshare_mcp.data_source as ds_mod
import akshare_mcp.tools.finance as finance_mod
import akshare_mcp.tools.market.quote as quote_mod
import akshare_mcp.tools.managers.paper_trading_manager as ptm
import akshare_mcp.tools.managers.portfolio_manager as pm
import akshare_mcp.tools.options as options_mod
import akshare_mcp.tools.tdx_trading_data as tdx_trade_mod
import akshare_mcp.tools.valuation as valuation_mod


class _DummyMCP:
    def tool(self):
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


class _PortfolioConn:
    def __init__(self, exists=True):
        self.row = {'id': 1, 'name': 'old', 'description': 'd', 'current_value': 100.0} if exists else None
        self.updated = None

    async def fetchrow(self, query, *args):
        if 'FROM portfolios WHERE id = $1' in query:
            return self.row
        return None

    async def execute(self, query, *args):
        if query.startswith('UPDATE portfolios SET name = $1'):
            self.updated = args


class _PaperConn:
    def __init__(self):
        self.accounts = {'acc1': {'id': 'acc1', 'current_capital': 100000.0, 'total_value': 100000.0}}
        self.positions = {}
        self.trades = []

    async def fetchrow(self, query, *args):
        if 'FROM paper_accounts WHERE id = $1' in query:
            return self.accounts.get(args[0])
        if 'FROM paper_positions WHERE account_id = $1 AND stock_code = $2' in query:
            return self.positions.get((args[0], args[1]))
        return None

    async def fetch(self, query, *args):
        if 'FROM paper_positions WHERE account_id = $1' in query:
            aid = args[0]
            return [v for (k, _), v in self.positions.items() if k == aid]
        return []

    async def fetchval(self, query, *args):
        if 'SUM(market_value)' in query:
            aid = args[0]
            return sum(float(v.get('market_value') or 0) for (k, _), v in self.positions.items() if k == aid)
        return 0

    async def execute(self, query, *args):
        if 'INSERT INTO paper_trades' in query:
            self.trades.append({'id': args[0], 'account_id': args[1], 'stock_code': args[2], 'trade_type': args[4], 'price': args[5], 'quantity': args[6], 'amount': args[7]})
        elif 'UPDATE paper_positions' in query and 'cost_price = $2' in query:
            qty, cost, cp, mv, pr, aid, code = args
            self.positions[(aid, code)] = {'account_id': aid, 'stock_code': code, 'quantity': qty, 'cost_price': cost, 'current_price': cp, 'market_value': mv, 'profit_rate': pr}
        elif 'INSERT INTO paper_positions' in query:
            aid, code, _name, qty, cost, cp, mv, pr = args
            self.positions[(aid, code)] = {'account_id': aid, 'stock_code': code, 'quantity': qty, 'cost_price': cost, 'current_price': cp, 'market_value': mv, 'profit_rate': pr}
        elif 'UPDATE paper_positions' in query and 'cost_price = $2' not in query:
            qty, cp, mv, pr, aid, code = args
            old = self.positions[(aid, code)]
            self.positions[(aid, code)] = {**old, 'quantity': qty, 'current_price': cp, 'market_value': mv, 'profit_rate': pr}
        elif 'DELETE FROM paper_positions' in query:
            self.positions.pop((args[0], args[1]), None)
        elif 'UPDATE paper_accounts SET current_capital = $1' in query:
            cap, total, aid = args
            self.accounts[aid]['current_capital'] = cap
            self.accounts[aid]['total_value'] = total


class _FakeDB:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


@pytest.mark.asyncio
async def test_p0_1_portfolio_update_fill_required_fields(monkeypatch):
    mcp = _DummyMCP()
    pm.register_portfolio_manager(mcp)
    conn = _PortfolioConn(exists=True)
    monkeypatch.setattr(pm, 'get_db', lambda: _FakeDB(conn))

    r = await mcp.portfolio_manager(action='update', portfolio_id=1, updates={'name': 'new'})
    assert r['success'] is True
    assert conn.updated[0] == 'new'
    assert conn.updated[2] == 100.0


@pytest.mark.asyncio
async def test_p0_1_portfolio_update_not_found(monkeypatch):
    mcp = _DummyMCP()
    pm.register_portfolio_manager(mcp)
    monkeypatch.setattr(pm, 'get_db', lambda: _FakeDB(_PortfolioConn(exists=False)))
    r = await mcp.portfolio_manager(action='update', portfolio_id=999, updates={'name': 'x'})
    assert r['success'] is False


def test_p0_2_batch_quotes_compat_structure(monkeypatch):
    monkeypatch.setattr(quote_mod, 'get_batch_quotes', lambda _c: {'success': True, 'data': [{'code': '000001'}], 'cached': True})
    assert isinstance(quote_mod.get_batch_quotes_compat(['000001'])['data'], list)
    monkeypatch.setattr(quote_mod, 'get_batch_quotes', lambda _c: {'success': True, 'data': {'quotes': [{'code': '000002'}]}})
    assert quote_mod.get_batch_quotes_compat(['000002'])['data'][0]['code'] == '000002'


@pytest.mark.asyncio
async def test_p0_3_paper_trading_bookkeeping_consistency(monkeypatch):
    mcp = _DummyMCP()
    ptm.register_paper_trading_manager(mcp)
    conn = _PaperConn()
    monkeypatch.setattr(ptm, 'get_db', lambda: _FakeDB(conn))

    b = await mcp.paper_trading_manager(action='place_order', account_id='acc1', code='600519', direction='buy', quantity=100, price=10)
    assert b['success'] is True
    s = await mcp.paper_trading_manager(action='place_order', account_id='acc1', code='600519', direction='sell', quantity=40, price=12)
    assert s['success'] is True

    p = await mcp.paper_trading_manager(action='positions', account_id='acc1')
    assert p['data']['positions'][0]['quantity'] == 60
    summary = await mcp.paper_trading_manager(action='summary', account_id='acc1')
    assert summary['data']['total_value'] == pytest.approx(100200.0)

    bad = await mcp.paper_trading_manager(action='place_order', account_id='acc1', code='600519', direction='sell', quantity=1000, price=12)
    assert bad['success'] is False




def test_p0_4_get_option_chain_none_months_should_degrade_gracefully(monkeypatch):
    monkeypatch.setattr(options_mod.ak, "option_sse_list_sina", lambda symbol: None)
    monkeypatch.setattr(
        options_mod.ak,
        "option_sse_codes_sina",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("codes unavailable")),
    )

    r = options_mod.get_option_chain("510050")
    assert r["success"] is True
    data = r["data"]
    assert data["degraded"] is True
    assert isinstance(data.get("expiryMonths"), list)
    assert len(data.get("expiryMonths", [])) >= 1
    assert any("回退" in msg for msg in data.get("fallback_reason", []))


def test_p0_5_tdx_financial_snapshot_fallback_from_empty_tdx(monkeypatch):
    class _FakeTQ:
        def get_gp_one_data(self, stock_code=None):
            return {}

    monkeypatch.setattr(finance_mod.data_source, "is_tdx_available", lambda: True)
    monkeypatch.setattr(finance_mod.data_source, "get_tdxquant", lambda: _FakeTQ())
    monkeypatch.setattr(finance_mod.data_source, "_convert_to_tdx_code", lambda c: c)
    monkeypatch.setattr(
        finance_mod,
        "get_financials",
        lambda code: {"success": True, "data": {"reportDate": "2024-12-31", "source": "tushare_pro"}},
    )

    r = finance_mod.tdx_get_financial_snapshot("600519")
    assert r["success"] is True
    data = r["data"]
    assert "source_chain" in data
    assert "tdxquant.get_gp_one_data" in data["source_chain"]
    assert "finance.get_financials" in data["source_chain"]
    assert any("TDX返回空结果" in msg for msg in data.get("fallback_reason", []))



def test_p0_5b_tdx_financial_history_should_decode_mixed_bytes(monkeypatch):
    class _FakeTQ:
        def get_financial_data_by_date(self, stock_list, field_list, year, mmdd):
            return {
                b"code": stock_list[0],
                "rows": [
                    {b"name": b"\xc8\xd5\xc6\xda", b"value": b"20241231"},  # 日期(GBK)
                    {"field": "ROE", "value": b"12.5"},
                ],
            }

    monkeypatch.setattr(finance_mod.data_source, "is_tdx_available", lambda: True)
    monkeypatch.setattr(finance_mod.data_source, "get_tdxquant", lambda: _FakeTQ())
    monkeypatch.setattr(finance_mod.data_source, "_convert_to_tdx_code", lambda c: c)

    r = finance_mod.tdx_get_financial_history(["600519"], ["ROE"], "20241231")
    assert r["success"] is True
    data = r["data"]
    assert data["degraded"] is True
    assert any("编码异常" in msg for msg in data.get("fallback_reason", []))
    payload = data["data"]
    assert "code" in payload
    assert "rows" in payload


def test_p0_5c_tdx_stock_trading_data_unsupported_fields_and_placeholder(monkeypatch):
    class _FakeTQ:
        def get_gpjy_value_by_date(self, stock_list, field_list, year, mmdd):
            return {"600519": {"GP1": ["--", "--"]}}

    monkeypatch.setattr(tdx_trade_mod.data_source, "is_tdx_available", lambda: True)
    monkeypatch.setattr(tdx_trade_mod.data_source, "get_tdxquant", lambda: _FakeTQ())
    monkeypatch.setattr(tdx_trade_mod.data_source, "_convert_to_tdx_code", lambda c: c)

    r = tdx_trade_mod.tdx_get_stock_trading_data(["600519"], ["1", "GP999"])
    assert r["success"] is True
    assert r["degraded"] is True
    assert any("字段不支持" in msg for msg in r.get("fallback_reason", []))
    assert any("盘后数据未就绪" in msg for msg in r.get("fallback_reason", []))
    assert r["data_quality"]["placeholder_values"] > 0


def test_p0_5d_tdx_sector_trading_data_partial_placeholder(monkeypatch):
    class _FakeTQ:
        def get_bkjy_value_by_date(self, stock_list, field_list, year, mmdd):
            return {"880660.SH": {"BK5": ["10.2", "--"]}}

    monkeypatch.setattr(tdx_trade_mod.data_source, "is_tdx_available", lambda: True)
    monkeypatch.setattr(tdx_trade_mod.data_source, "get_tdxquant", lambda: _FakeTQ())

    r = tdx_trade_mod.tdx_get_sector_trading_data(["880660.SH"], ["BK5"])
    assert r["success"] is True
    assert r["degraded"] is True
    assert any("部分字段" in msg for msg in r.get("fallback_reason", []))


def test_p0_5e_tdx_market_trading_data_should_validate_end_date_dependency():
    r = tdx_trade_mod.tdx_get_market_trading_data(["SC1"], end_date="20250131")
    assert r["success"] is False
    assert "仅传 end_date 无效" in (r.get("error") or "")


def test_p0_5f_tdx_market_trading_data_unsupported_and_partial_placeholder(monkeypatch):
    class _FakeTQ:
        def get_scjy_value(self, field_list, start_time, end_time):
            return {"SC1": ["100", "--"]}

    monkeypatch.setattr(tdx_trade_mod.data_source, "is_tdx_available", lambda: True)
    monkeypatch.setattr(tdx_trade_mod.data_source, "get_tdxquant", lambda: _FakeTQ())

    r = tdx_trade_mod.tdx_get_market_trading_data(["1", "SC999"], start_date="20250101", end_date="20250131")
    assert r["success"] is True
    assert r["degraded"] is True
    assert any("字段不支持" in msg for msg in r.get("fallback_reason", []))
    assert any("部分字段" in msg for msg in r.get("fallback_reason", []))
    assert r["data_quality"]["placeholder_values"] == 1




@pytest.mark.asyncio
async def test_p0_6_historical_valuation_dedup_and_data_quality(monkeypatch):
    class _ValuationConn:
        async def fetch(self, query, code, days):
            return [
                {
                    "time": datetime(2026, 2, 1),
                    "pe": 20.0,
                    "pb": 3.0,
                    "mkt_cap": None,
                    "price": 100.0,
                },
                {
                    "time": datetime(2026, 2, 1),
                    "pe": 20.0,
                    "pb": 3.0,
                    "mkt_cap": 1000.0,
                    "price": 100.0,
                },
                {
                    "time": datetime(2026, 1, 31),
                    "pe": 19.0,
                    "pb": None,
                    "mkt_cap": 980.0,
                    "price": 98.0,
                },
            ]

    class _ValuationDB:
        def acquire(self):
            return _Acquire(_ValuationConn())

        async def get_stock_info(self, code):
            return None

    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, "get_db", lambda: _ValuationDB())

    r = await mcp.get_historical_valuation("600519", days=30)
    assert r["success"] is True
    data = r["data"]
    assert data["count"] == 2
    assert "data_quality" in data
    assert data["data_quality"]["raw_count"] == 3
    assert data["data_quality"]["deduplicated_count"] == 2
    assert data["data_quality"]["duplicate_removed"] == 1
    assert "source_chain" in data and data["source_chain"][0] == "db.stock_quotes"
    assert "fallback_reason" in data
    assert data["history"][0]["market_cap"] is not None
    assert data["history"][0]["date"] == "2026-02-01"
    assert data["history"][1]["date"] == "2026-01-31"


@pytest.mark.asyncio
async def test_p0_7_historical_valuation_fallback_chain_visible(monkeypatch):
    class _EmptyConn:
        async def fetch(self, query, code, days):
            return []

    class _EmptyDB:
        def acquire(self):
            return _Acquire(_EmptyConn())

        async def get_stock_info(self, code):
            return {"pe_ratio": 22.0, "pb_ratio": 4.0, "market_cap": 1200.0}

    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, "get_db", lambda: _EmptyDB())

    class _NoPro:
        def daily_basic(self, **kwargs):
            return None

    monkeypatch.setattr(ds_mod.data_source, "get_tushare_pro", lambda: _NoPro())

    class _DummyAK:
        @staticmethod
        def stock_a_indicator_lg(symbol):
            raise RuntimeError("ak not available")

    monkeypatch.setattr(akshare, "stock_a_indicator_lg", _DummyAK.stock_a_indicator_lg, raising=False)

    class _DummyBS:
        @staticmethod
        def query_history_k_data_plus(*args, **kwargs):
            raise RuntimeError("bs not available")

    monkeypatch.setattr(bs_api_mod, "baostock_client", _DummyBS)

    r = await mcp.get_historical_valuation("600519", days=5)
    assert r["success"] is True
    data = r["data"]
    assert data["source"] == "fallback"
    assert "db.stock_quotes" in data["source_chain"]
    assert "tushare.daily_basic" in data["source_chain"]
    assert "akshare.stock_a_indicator_lg" in data["source_chain"]
    assert "baostock.history_k_data_plus" in data["source_chain"]
    assert "db.get_stock_info" in data["source_chain"]
    assert data["count"] == 1
    assert data["history"][0]["pe_ratio"] == 22.0
    assert any("降级" in msg for msg in data.get("fallback_reason", []))
