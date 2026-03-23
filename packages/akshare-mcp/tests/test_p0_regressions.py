import pytest
import numpy as np
import sys
from datetime import datetime

import akshare
import akshare_mcp.baostock_api as bs_api_mod
import akshare_mcp.data_source as ds_mod
import akshare_mcp.tools.backtest as backtest_mod
import akshare_mcp.tools.decision as decision_mod
import akshare_mcp.tools.data_warmup as data_warmup_mod
import akshare_mcp.tools.finance as finance_mod
import akshare_mcp.tools.fund_flow as fund_flow_mod
import akshare_mcp.tools.market.limit_up as limit_up_mod
import akshare_mcp.tools.market.quote as quote_mod
import akshare_mcp.tools.news as news_mod
import akshare_mcp.tools.portfolio as portfolio_mod
import akshare_mcp.tools.quant as quant_mod
import akshare_mcp.tools.search as search_mod
import akshare_mcp.tools.vector as vector_mod
import akshare_mcp.tools.alerts as alerts_tool_mod
import akshare_mcp.tools.managers.alerts_manager as alerts_manager_mod
import akshare_mcp.tools.managers.comprehensive_manager as comprehensive_manager_mod
import akshare_mcp.tools.managers.decision_manager as decision_manager_mod
import akshare_mcp.tools.managers.event_manager as event_manager_mod
import akshare_mcp.tools.managers.limit_up_manager as limit_up_manager_mod
import akshare_mcp.tools.managers.market_insight_manager as market_insight_manager_mod
import akshare_mcp.tools.market_blocks as market_blocks_mod
import akshare_mcp.tools.managers.paper_trading_manager as ptm
import akshare_mcp.tools.managers.portfolio_manager as pm
import akshare_mcp.tools.managers.research_manager as research_manager_mod
import akshare_mcp.tools.managers.sector_manager as sector_manager_mod
import akshare_mcp.tools.managers.trading_data_manager as trading_data_manager_mod
import akshare_mcp.tools.managers.watchlist_manager as watchlist_manager_mod
import akshare_mcp.tools.options as options_mod
import akshare_mcp.tools.valuation as valuation_mod
import akshare_mcp.services.portfolio_optimization as po_mod


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
        self.accounts = {
            'acc1': {
                'id': 'acc1',
                'user_id': 'default',
                'current_capital': 100000.0,
                'total_value': 100000.0,
            }
        }
        self.positions = {}
        self.trades = []

    async def fetchrow(self, query, *args):
        if 'FROM paper_accounts WHERE' in query:
            return self.accounts.get(args[0])
        if 'FROM paper_positions WHERE' in query and len(args) >= 2:
            return self.positions.get((args[0], args[1]))
        return None

    async def fetch(self, query, *args):
        if 'FROM paper_accounts WHERE user_id' in query:
            uid = args[0]
            return [v for v in self.accounts.values() if v.get('user_id') == uid]
        if 'FROM paper_positions WHERE account_id' in query:
            aid = args[0]
            return [v for (k, _), v in self.positions.items() if k == aid]
        if 'FROM paper_trades WHERE account_id' in query:
            aid = args[0]
            return [v for v in reversed(self.trades) if v.get('account_id') == aid]
        return []

    async def fetchval(self, query, *args):
        if 'FROM paper_trades' in query:
            aid, code = args
            today = datetime.now().date()
            sellable = 0
            for trade in self.trades:
                if trade.get('account_id') != aid or trade.get('stock_code') != code:
                    continue
                trade_time = trade.get('trade_time') or datetime.now()
                trade_date = trade_time.date() if hasattr(trade_time, 'date') else today
                if trade.get('trade_type') == 'buy' and trade_date < today:
                    sellable += int(trade.get('quantity') or 0)
                elif trade.get('trade_type') == 'sell':
                    sellable -= int(trade.get('quantity') or 0)
            return sellable
        if 'SUM(market_value)' in query:
            aid = args[0]
            return sum(float(v.get('market_value') or 0) for (k, _), v in self.positions.items() if k == aid)
        return 0

    async def execute(self, query, *args):
        if 'INSERT INTO paper_trades' in query:
            self.trades.append({
                'id': args[0],
                'account_id': args[1],
                'stock_code': args[2],
                'trade_type': args[4],
                'price': args[5],
                'quantity': args[6],
                'amount': args[7],
                'commission': args[8],
                'trade_time': datetime.now(),
            })
        elif 'UPDATE paper_positions' in query and 'cost_price=$2' in query:
            qty, cost, cp, mv, pr, aid, code = args
            self.positions[(aid, code)] = {'account_id': aid, 'stock_code': code, 'quantity': qty, 'cost_price': cost, 'current_price': cp, 'market_value': mv, 'profit_rate': pr}
        elif 'INSERT INTO paper_positions' in query:
            aid, code, _name, qty, cost, cp, mv, pr = args
            self.positions[(aid, code)] = {'account_id': aid, 'stock_code': code, 'quantity': qty, 'cost_price': cost, 'current_price': cp, 'market_value': mv, 'profit_rate': pr}
        elif 'UPDATE paper_positions' in query and 'cost_price=$2' not in query:
            qty, cp, mv, pr, aid, code = args
            old = self.positions[(aid, code)]
            self.positions[(aid, code)] = {**old, 'quantity': qty, 'current_price': cp, 'market_value': mv, 'profit_rate': pr}
        elif 'DELETE FROM paper_positions' in query:
            self.positions.pop((args[0], args[1]), None)
        elif 'UPDATE paper_accounts SET current_capital' in query:
            cap, total, aid = args
            self.accounts[aid]['current_capital'] = cap
            self.accounts[aid]['total_value'] = total


class _FakeDB:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


class _PaperFakeDB(_FakeDB):
    async def get_klines(self, code, limit=2):
        return []


class _BatchBacktestDB:
    async def get_klines(self, code, start_date=None, end_date=None):
        return [
            {
                'date': '2025-01-02',
                'open': 10.0,
                'close': 10.2,
                'high': 10.3,
                'low': 9.9,
                'volume': 1000,
            },
            {
                'date': '2025-01-03',
                'open': 10.2,
                'close': 10.1,
                'high': 10.4,
                'low': 10.0,
                'volume': 1100,
            },
        ]


class _EmptyFetchConn:
    async def fetch(self, query, *args):
        return []


class _TradingDataDB(_FakeDB):
    async def get_klines(self, code, limit=1):
        return []


@pytest.mark.asyncio
async def test_p0_08_run_batch_backtest_should_mark_all_failures_degraded(monkeypatch):
    monkeypatch.setattr(backtest_mod, 'get_db', lambda: _BatchBacktestDB())
    monkeypatch.setattr(
        backtest_mod.backtest_engine,
        'run_backtest',
        lambda code, klines, strategy, params: {'success': False, 'error': f'backtest failed for {code}'},
    )

    result = await backtest_mod.run_batch_backtest(['600519', '000858'], use_parallel=False)

    assert result['success'] is True
    data = result['data']
    assert data['successful_count'] == 0
    assert data['failed_count'] == 2
    assert data['degraded'] is True
    assert 'all_fetch_failed' in data['quality_flags']
    assert len(data['failure_reasons']) == 2
    assert data['failure_reasons'][0]['code'] == '600519'


@pytest.mark.asyncio
async def test_p0_08b_run_batch_backtest_tool_should_mark_all_failures_degraded(monkeypatch):
    monkeypatch.setattr(backtest_mod, 'get_db', lambda: _BatchBacktestDB())
    monkeypatch.setattr(
        backtest_mod.backtest_engine,
        'run_backtest',
        lambda code, klines, strategy, params: {'success': False, 'error': f'backtest failed for {code}'},
    )

    mcp = _DummyMCP()
    backtest_mod.register(mcp)

    result = await mcp.run_batch_backtest(['600519', '000858'], use_parallel=False)

    assert result['success'] is True
    data = result['data']
    assert data['successful_count'] == 0
    assert data['failed_count'] == 2
    assert data['degraded'] is True
    assert 'all_fetch_failed' in data['quality_flags']
    assert len(data['failure_reasons']) == 2


@pytest.mark.asyncio
async def test_p0_08c_trading_data_manager_should_fallback_to_tool_block_trades_with_quality_meta(monkeypatch):
    mcp = _DummyMCP()
    trading_data_manager_mod.register_trading_data_manager(mcp)

    monkeypatch.setattr(trading_data_manager_mod, 'get_db', lambda: _TradingDataDB(_EmptyFetchConn()))
    monkeypatch.setattr(
        fund_flow_mod,
        'get_block_trades',
        lambda date="", stock_code="", limit=500: {
            'success': True,
            'data': [
                {
                    'date': '2026-03-18',
                    'code': '600519',
                    'name': '贵州茅台',
                    'price': 1500.5,
                    'amount': 1500500.0,
                }
            ],
            'data_quality': {'name_backfilled_count': 1},
            'source_chain': ['eastmoney.block_trades'],
            'fallback_reason': ['db block_trades empty'],
            'degraded': False,
        },
    )

    result = await mcp.trading_data_manager(
        action='block_trades',
        kwargs='{"stock_code":"600519","limit":10,"date":"2026-03-18"}',
    )

    assert result['success'] is True
    data = result['data']
    assert data['code'] == '600519'
    assert len(data['trades']) == 1
    assert data['analysis']['totalTrades'] == 1
    assert data['analysis']['avgPrice'] == pytest.approx(1500.5)
    assert data['data_quality']['name_backfilled_count'] == 1
    assert data['source_chain'] == ['eastmoney.block_trades']
    assert data['fallback_reason'] == ['db block_trades empty']
    assert data['degraded'] is False


@pytest.mark.asyncio
async def test_p0_08d_limit_up_manager_should_propagate_quality_meta(monkeypatch):
    mcp = _DummyMCP()
    limit_up_manager_mod.register_limit_up_manager(mcp)

    monkeypatch.setattr(
        limit_up_mod,
        'get_limit_up_stocks',
        lambda date="": {
            'success': True,
            'data': [
                {
                    'code': '000001',
                    'name': '平安银行',
                    'price': 11.0,
                    'changePercent': 10.0,
                    'turnoverRate': None,
                    'industry': '银行',
                    'concept': '',
                    'firstLimitTime': '',
                    'lastLimitTime': '',
                    'continuousDays': 2,
                }
            ],
            'data_quality': {'missing_field_counts': {'openTimes': 1}},
            'source_chain': ['tushare.stk_limit', 'tushare.daily'],
            'fallback_reason': ['openTimes unavailable from source'],
            'degraded': True,
        },
    )

    result = await mcp.limit_up_manager(action='list', kwargs='{"date":"2026-03-18"}')

    assert result['success'] is True
    data = result['data']
    assert data['count'] == 1
    assert data['limit_up_stocks'][0]['code'] == '000001'
    assert data['data_quality']['missing_field_counts']['openTimes'] == 1
    assert data['source_chain'] == ['tushare.stk_limit', 'tushare.daily']
    assert data['fallback_reason'] == ['openTimes unavailable from source']
    assert data['degraded'] is True


class _WatchlistConn:
    def __init__(self):
        now = datetime.now()
        self.groups = {
            ("default", "default"): {
                "id": "default",
                "name": "我的自选",
                "user_id": "default",
                "color": "#6366f1",
                "sort_order": 0,
                "created_at": now,
            },
        }
        self.items = {}

    async def fetch(self, query, *args):
        if "FROM watchlist_groups" in query:
            user_id, default_group_id = args
            rows = [
                row for (gid, uid), row in self.groups.items()
                if uid == user_id or (uid == "default" and gid == default_group_id)
            ]
            return sorted(rows, key=lambda row: (int(row.get("sort_order") or 0), str(row.get("name") or "")))

        if "FROM watchlist" in query:
            user_id = args[0]
            rows = [row for (uid, _code), row in self.items.items() if uid == user_id]
            return sorted(rows, key=lambda row: (str(row.get("group_id") or ""), int(row.get("sort_order") or 0), str(row.get("code") or "")))

        return []

    async def fetchrow(self, query, *args):
        if "SELECT id FROM watchlist_groups" in query:
            user_id, name = args
            for (_gid, uid), row in self.groups.items():
                if uid == user_id and row.get("name") == name:
                    return {"id": row["id"]}
        return None

    async def execute(self, query, *args):
        if "INSERT INTO watchlist_groups" in query:
            group_id, name, user_id, color, default_color = args
            current = self.groups.get((group_id, user_id), {})
            self.groups[(group_id, user_id)] = {
                "id": group_id,
                "name": name or current.get("name") or group_id,
                "user_id": user_id,
                "color": color or current.get("color") or default_color,
                "sort_order": current.get("sort_order", 1),
                "created_at": current.get("created_at", datetime.now()),
            }
            return

        if "INSERT INTO watchlist (user_id, code, group_id, sort_order, note, added_at)" in query:
            user_id, code, group_id, sort_order, note = args
            current = self.items.get((user_id, code), {})
            self.items[(user_id, code)] = {
                "id": current.get("id", len(self.items) + 1),
                "user_id": user_id,
                "code": code,
                "name": current.get("name", code),
                "group_id": group_id,
                "sort_order": sort_order,
                "note": note,
                "added_at": current.get("added_at", datetime.now()),
            }
            return

        if "DELETE FROM watchlist WHERE user_id = $1 AND code = $2" in query:
            user_id, code = args
            self.items.pop((user_id, code), None)
            return

        if "UPDATE watchlist\n                            SET sort_order = $1" in query:
            sort_order, user_id, code, group_id = args
            row = self.items.get((user_id, code))
            if row and row.get("group_id") == group_id:
                row["sort_order"] = sort_order
            return

        if "UPDATE watchlist SET group_id = $1, sort_order = 0" in query:
            target_group_id, user_id, source_group_id = args
            for (uid, _code), row in list(self.items.items()):
                if uid == user_id and row.get("group_id") == source_group_id:
                    row["group_id"] = target_group_id
                    row["sort_order"] = 0
            return

        if "DELETE FROM watchlist_groups WHERE user_id = $1 AND id = $2" in query:
            user_id, group_id = args
            self.groups.pop((group_id, user_id), None)
            return


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
async def test_p0_1a_portfolio_manager_accepts_structured_params(monkeypatch):
    mcp = _DummyMCP()
    pm.register_portfolio_manager(mcp)

    class _PortfolioCreateConn(_PortfolioConn):
        async def fetchval(self, query, *args):
            if 'INSERT INTO portfolios' in query:
                self.created = args
                return 101
            return None

    conn = _PortfolioCreateConn(exists=True)
    monkeypatch.setattr(pm, 'get_db', lambda: _FakeDB(conn))

    created = await mcp.portfolio_manager(
        action='create',
        params={'name': '结构化组合', 'user_id': 'u1', 'initial_capital': 250000},
    )
    assert created['success'] is True
    assert created['data']['portfolio_id'] == 101


@pytest.mark.asyncio
async def test_p0_1_portfolio_update_not_found(monkeypatch):
    mcp = _DummyMCP()
    pm.register_portfolio_manager(mcp)
    monkeypatch.setattr(pm, 'get_db', lambda: _FakeDB(_PortfolioConn(exists=False)))
    r = await mcp.portfolio_manager(action='update', portfolio_id=999, updates={'name': 'x'})
    assert r['success'] is False


@pytest.mark.asyncio
async def test_p0_1b_watchlist_manager_group_crud_and_reorder(monkeypatch):
    mcp = _DummyMCP()
    watchlist_manager_mod.register_watchlist_manager(mcp)
    conn = _WatchlistConn()
    monkeypatch.setattr(watchlist_manager_mod, 'get_db', lambda: _FakeDB(conn))

    created = await mcp.watchlist_manager(
        action='create_group',
        params={'user_id': 'u1', 'group_id': 'group_growth', 'name': '成长组', 'color': '#00ff00'},
    )
    assert created['success'] is True
    assert created['data']['group_id'] == 'group_growth'

    added = await mcp.watchlist_manager(
        action='add_stocks',
        params={'user_id': 'u1', 'group_id': 'group_growth', 'group_name': '成长组', 'codes': ['600519', '000001']},
    )
    assert added['success'] is True
    assert added['data']['count'] == 2

    listed = await mcp.watchlist_manager(action='list', params={'user_id': 'u1'})
    assert listed['success'] is True
    groups = listed['data']['groups']
    growth = next(group for group in groups if group['id'] == 'group_growth')
    assert [item['code'] for item in growth['items']] == ['600519', '000001']
    assert growth['color'] == '#00ff00'

    reordered = await mcp.watchlist_manager(
        action='reorder',
        params={'user_id': 'u1', 'group_id': 'group_growth', 'codes': ['000001', '600519']},
    )
    assert reordered['success'] is True
    listed_after_reorder = await mcp.watchlist_manager(action='list', params={'user_id': 'u1'})
    growth_after = next(group for group in listed_after_reorder['data']['groups'] if group['id'] == 'group_growth')
    assert [item['code'] for item in growth_after['items']] == ['000001', '600519']

    removed = await mcp.watchlist_manager(action='remove_stock', params={'user_id': 'u1', 'code': '600519'})
    assert removed['success'] is True

    deleted = await mcp.watchlist_manager(action='delete_group', params={'user_id': 'u1', 'group_id': 'group_growth'})
    assert deleted['success'] is True

    final_list = await mcp.watchlist_manager(action='list', params={'user_id': 'u1'})
    final_groups = final_list['data']['groups']
    assert all(group['id'] != 'group_growth' for group in final_groups)
    default_group = next(group for group in final_groups if group['id'] == 'default')
    assert [item['code'] for item in default_group['items']] == ['000001']


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
    monkeypatch.setattr(ptm, 'get_db', lambda: _PaperFakeDB(conn))

    async def _fake_quote(_code):
        return {'name': '贵州茅台', 'preClose': 11.0, 'price': 11.0}

    async def _always_sellable(_conn, _account_id, _code):
        return 10_000

    monkeypatch.setattr(ptm, '_get_quote_snapshot', _fake_quote)
    monkeypatch.setattr(ptm, '_get_sellable_quantity', _always_sellable)

    b = await mcp.paper_trading_manager(action='place_order', account_id='acc1', code='600519', direction='buy', quantity=100, price=10)
    assert b['success'] is True
    s = await mcp.paper_trading_manager(action='place_order', account_id='acc1', code='600519', direction='sell', quantity=40, price=12)
    assert s['success'] is True

    p = await mcp.paper_trading_manager(action='positions', account_id='acc1')
    assert p['data']['positions'][0]['quantity'] == 60
    summary = await mcp.paper_trading_manager(action='summary', account_id='acc1')
    assert summary['data']['total_value'] == pytest.approx(100200.0, rel=0.01)

    bad = await mcp.paper_trading_manager(action='place_order', account_id='acc1', code='600519', direction='sell', quantity=1000, price=12)
    assert bad['success'] is False


@pytest.mark.asyncio
async def test_p0_3_paper_trading_accepts_structured_params(monkeypatch):
    mcp = _DummyMCP()
    ptm.register_paper_trading_manager(mcp)
    conn = _PaperConn()
    monkeypatch.setattr(ptm, 'get_db', lambda: _PaperFakeDB(conn))

    async def _fake_quote(_code):
        return {'name': '贵州茅台', 'preClose': 11.0, 'price': 11.0}

    monkeypatch.setattr(ptm, '_get_quote_snapshot', _fake_quote)

    buy = await mcp.paper_trading_manager(
        action='place_order',
        params={'account_id': 'acc1', 'code': '600519', 'direction': 'buy', 'quantity': 100, 'price': 10},
    )
    assert buy['success'] is True

    positions = await mcp.paper_trading_manager(action='positions', params={'account_id': 'acc1'})
    assert positions['success'] is True
    assert positions['data']['positions'][0]['quantity'] == 100


@pytest.mark.asyncio
async def test_p0_3_paper_trading_t_plus_one_and_sellable(monkeypatch):
    mcp = _DummyMCP()
    ptm.register_paper_trading_manager(mcp)
    conn = _PaperConn()
    monkeypatch.setattr(ptm, 'get_db', lambda: _PaperFakeDB(conn))

    async def _fake_quote(_code):
        return {'name': '贵州茅台', 'preClose': 11.0, 'price': 11.0}

    monkeypatch.setattr(ptm, '_get_quote_snapshot', _fake_quote)

    buy = await mcp.paper_trading_manager(action='place_order', account_id='acc1', code='600519', direction='buy', quantity=100, price=10)
    assert buy['success'] is True

    positions = await mcp.paper_trading_manager(action='positions', account_id='acc1')
    assert positions['success'] is True
    assert positions['data']['positions'][0]['sellable'] == 0

    same_day_sell = await mcp.paper_trading_manager(action='place_order', account_id='acc1', code='600519', direction='sell', quantity=100, price=10)
    assert same_day_sell['success'] is False
    assert 'T+1' in str(same_day_sell.get('error') or same_day_sell.get('message') or same_day_sell)


@pytest.mark.asyncio
async def test_p0_3_paper_trading_lot_size_and_price_limit(monkeypatch):
    mcp = _DummyMCP()
    ptm.register_paper_trading_manager(mcp)
    conn = _PaperConn()
    monkeypatch.setattr(ptm, 'get_db', lambda: _PaperFakeDB(conn))

    async def _fake_quote(_code):
        return {'name': '贵州茅台', 'preClose': 10.0, 'price': 10.0}

    monkeypatch.setattr(ptm, '_get_quote_snapshot', _fake_quote)

    bad_lot = await mcp.paper_trading_manager(action='place_order', account_id='acc1', code='600519', direction='buy', quantity=150, price=10)
    assert bad_lot['success'] is False
    assert '100' in str(bad_lot.get('error') or bad_lot.get('message') or bad_lot)

    bad_limit = await mcp.paper_trading_manager(action='place_order', account_id='acc1', code='600519', direction='buy', quantity=100, price=11.5)
    assert bad_limit['success'] is False
    assert '涨跌停限制' in str(bad_limit.get('error') or bad_limit.get('message') or bad_limit)


@pytest.mark.asyncio
async def test_p0_3_paper_trading_update_prices_and_accounts_alias(monkeypatch):
    mcp = _DummyMCP()
    ptm.register_paper_trading_manager(mcp)
    conn = _PaperConn()
    conn.positions[('acc1', '600519')] = {
        'account_id': 'acc1',
        'stock_code': '600519',
        'stock_name': '贵州茅台',
        'quantity': 100,
        'cost_price': 10.0,
        'current_price': 10.0,
        'market_value': 1000.0,
        'profit_rate': 0.0,
    }
    monkeypatch.setattr(ptm, 'get_db', lambda: _PaperFakeDB(conn))
    monkeypatch.setattr(quote_mod, 'get_batch_quotes_compat', lambda codes: {
        'success': True,
        'data': [{'code': codes[0], 'price': 12.0, 'name': '贵州茅台'}],
    })

    accounts = await mcp.paper_trading_manager(action='accounts', user_id='default')
    assert accounts['success'] is True
    assert accounts['data']['count'] == 1

    refreshed = await mcp.paper_trading_manager(action='update_prices', account_id='acc1')
    assert refreshed['success'] is True
    position = refreshed['data']['positions'][0]
    assert position['current_price'] == pytest.approx(12.0)
    assert position['market_value'] == pytest.approx(1200.0)
    assert position['profit_rate'] == pytest.approx(0.2)
    assert refreshed['data']['account']['total_value'] == pytest.approx(101200.0)


@pytest.mark.asyncio
async def test_p0_3b_paper_trading_update_prices_should_fill_default_error(monkeypatch):
    mcp = _DummyMCP()
    ptm.register_paper_trading_manager(mcp)
    monkeypatch.setattr(ptm, 'get_db', lambda: object())

    async def _raise_empty(_db, _account_id):
        raise RuntimeError('')

    monkeypatch.setattr(ptm, '_refresh_account_prices', _raise_empty)

    result = await mcp.paper_trading_manager(action='update_prices', account_id='acc1')
    assert result['success'] is False
    assert result['error'] == 'update_prices 执行失败'




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


@pytest.mark.asyncio
async def test_p0_7b_historical_valuation_should_fallback_when_db_query_breaks(monkeypatch):
    class _BrokenConn:
        async def fetch(self, query, code, days):
            raise RuntimeError('column "pe" does not exist')

    class _BrokenDB:
        def acquire(self):
            return _Acquire(_BrokenConn())

        async def get_stock_info(self, code):
            return {"pe_ratio": 18.0, "pb_ratio": 2.5, "market_cap": 900.0}

    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, 'get_db', lambda: _BrokenDB())

    class _NoPro:
        def daily_basic(self, **kwargs):
            return None

    monkeypatch.setattr(ds_mod.data_source, 'get_tushare_pro', lambda: _NoPro())
    monkeypatch.setattr(akshare, 'stock_a_indicator_lg', lambda symbol: (_ for _ in ()).throw(RuntimeError('ak not available')), raising=False)

    class _DummyBS:
        @staticmethod
        def query_history_k_data_plus(*args, **kwargs):
            raise RuntimeError('bs not available')

    monkeypatch.setattr(bs_api_mod, 'baostock_client', _DummyBS)

    result = await mcp.get_historical_valuation('600519', days=5)
    assert result['success'] is True
    data = result['data']
    assert data['source'] == 'fallback'
    assert data['history'][0]['pe_ratio'] == 18.0
    assert any('stock_quotes查询失败' in msg for msg in data.get('fallback_reason', []))



@pytest.mark.asyncio
async def test_p0_7c_historical_valuation_filters_non_positive_metrics(monkeypatch):
    class _ValuationConn:
        async def fetch(self, query, code, days):
            return [
                {
                    "time": datetime(2026, 2, 2),
                    "pe": 0.0,
                    "pb": -1.0,
                    "mkt_cap": 1200.0,
                    "price": 101.0,
                },
                {
                    "time": datetime(2026, 2, 1),
                    "pe": 18.0,
                    "pb": 2.5,
                    "mkt_cap": 1190.0,
                    "price": 99.0,
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

    result = await mcp.get_historical_valuation("600519", days=30)
    assert result["success"] is True
    data = result["data"]
    assert data["history"][0]["date"] == "2026-02-02"
    assert data["history"][0]["pe_ratio"] is None
    assert data["history"][0]["pb_ratio"] is None
    assert data["history"][1]["pe_ratio"] == 18.0
    assert data["stats"]["pe"]["current"] == 18.0
    assert data["data_quality"]["invalid_value_cells"] == 2
    assert data["data_quality"]["invalid_value_fields"]["pe_ratio"] == 1
    assert data["data_quality"]["invalid_value_fields"]["pb_ratio"] == 1


class _DecisionConn:
    async def fetchrow(self, query, *args):
        if "SELECT pe_ratio, pb_ratio FROM stocks" in query:
            return {"pe_ratio": 20.0, "pb_ratio": 1.5}
        if "FROM financials" in query:
            return {"roe": 16.0, "debt_ratio": 30.0, "revenue_growth": 25.0}
        return None

    async def fetch(self, query, *args):
        if "SELECT pe_ratio FROM stocks" in query:
            # 行业对标样本足够，触发 industry_median_pe
            return [{"pe_ratio": 18.0}, {"pe_ratio": 22.0}, {"pe_ratio": 20.0}, {"pe_ratio": 24.0}]
        return []


class _DecisionConnPeersInsufficient(_DecisionConn):
    async def fetch(self, query, *args):
        if "SELECT pe_ratio FROM stocks" in query:
            # 样本不足，触发回退路径
            return [{"pe_ratio": 18.0}, {"pe_ratio": 22.0}]
        return []


class _DecisionDB:
    def __init__(self, conn):
        self._conn = conn

    async def get_stock_info(self, code):
        return {"stock_code": code, "name": "测试股", "industry": "白酒"}

    async def get_klines(self, code, limit=100):
        return [
            {"close": 100.0, "volume": 1000.0, "date": "2026-02-01"},
            {"close": 99.0, "volume": 900.0, "date": "2026-01-31"},
            {"close": 98.0, "volume": 850.0, "date": "2026-01-30"},
            {"close": 97.0, "volume": 800.0, "date": "2026-01-29"},
            {"close": 96.0, "volume": 780.0, "date": "2026-01-28"},
            {"close": 95.0, "volume": 500.0, "date": "2026-01-27"},
            {"close": 94.0, "volume": 500.0, "date": "2026-01-26"},
            {"close": 93.0, "volume": 500.0, "date": "2026-01-25"},
            {"close": 92.0, "volume": 500.0, "date": "2026-01-24"},
            {"close": 91.0, "volume": 500.0, "date": "2026-01-23"},
            {"close": 90.0, "volume": 500.0, "date": "2026-01-22"},
            {"close": 89.0, "volume": 500.0, "date": "2026-01-21"},
            {"close": 88.0, "volume": 500.0, "date": "2026-01-20"},
            {"close": 87.0, "volume": 500.0, "date": "2026-01-19"},
            {"close": 86.0, "volume": 500.0, "date": "2026-01-18"},
            {"close": 85.0, "volume": 500.0, "date": "2026-01-17"},
            {"close": 84.0, "volume": 500.0, "date": "2026-01-16"},
            {"close": 83.0, "volume": 500.0, "date": "2026-01-15"},
            {"close": 82.0, "volume": 500.0, "date": "2026-01-14"},
            {"close": 81.0, "volume": 500.0, "date": "2026-01-13"},
        ]

    def acquire(self):
        return _Acquire(self._conn)

    async def _financials_code_column(self, conn):
        return "code"


@pytest.mark.asyncio
async def test_p0_8_should_i_buy_industry_median_pe_path(monkeypatch):
    mcp = _DummyMCP()
    decision_mod.register(mcp)
    monkeypatch.setattr(decision_mod, "get_db", lambda: _DecisionDB(_DecisionConn()))

    monkeypatch.setattr(decision_mod.technical_analysis, "calculate_rsi", lambda closes: [20.0])
    monkeypatch.setattr(decision_mod.technical_analysis, "calculate_macd", lambda closes: {"histogram": [-1.0, 1.0]})
    monkeypatch.setattr(decision_mod.technical_analysis, "calculate_sma", lambda closes, n: [90.0 if n == 20 else 80.0])
    monkeypatch.setattr(decision_mod.factor_calculator, "calculate_momentum", lambda closes: 0.0)

    r = await mcp.should_i_buy("600519", investment_style="balanced")
    assert r["success"] is True, r
    data = r["data"]
    assert data["recommendation"] == "buy"
    assert data["valuation_method"] == "industry_median_pe"
    assert data["industry_median_pe"] == pytest.approx(21.0)
    assert data["target_price"] is not None


@pytest.mark.asyncio
async def test_p0_8b_should_i_buy_pe_expansion_fallback_when_peers_insufficient(monkeypatch):
    mcp = _DummyMCP()
    decision_mod.register(mcp)
    monkeypatch.setattr(decision_mod, "get_db", lambda: _DecisionDB(_DecisionConnPeersInsufficient()))

    monkeypatch.setattr(decision_mod.technical_analysis, "calculate_rsi", lambda closes: [20.0])
    monkeypatch.setattr(decision_mod.technical_analysis, "calculate_macd", lambda closes: {"histogram": [-1.0, 1.0]})
    monkeypatch.setattr(decision_mod.technical_analysis, "calculate_sma", lambda closes, n: [90.0 if n == 20 else 80.0])
    monkeypatch.setattr(decision_mod.factor_calculator, "calculate_momentum", lambda closes: 0.0)

    r = await mcp.should_i_buy("600519", investment_style="balanced")
    assert r["success"] is True
    data = r["data"]
    assert data["recommendation"] == "buy"
    assert data["valuation_method"] == "pe_expansion_fallback"
    assert data["industry_median_pe"] is None


def test_p0_9_portfolio_optimizer_ledoit_and_degrade_paths(monkeypatch):
    expected = np.array([0.10, 0.12, 0.08], dtype=float)
    cov = np.array([[0.10, 0.02, 0.01], [0.03, 0.11, 0.02], [0.01, 0.02, 0.09]], dtype=float)
    returns = np.random.RandomState(42).randn(80, 3) * 0.01

    class _FakeLW:
        def fit(self, x):
            self.covariance_ = np.array([[0.09, 0.01, 0.0], [0.01, 0.10, 0.01], [0.0, 0.01, 0.08]], dtype=float)
            return self

    monkeypatch.setattr(po_mod, "LedoitWolf", _FakeLW)

    mv = po_mod.PortfolioOptimizer.mean_variance_optimization(
        expected, cov, returns_matrix=returns, use_ledoit_wolf=True
    )
    assert mv["success"] is True
    assert len(mv["weights"]) == 3

    rp = po_mod.PortfolioOptimizer.risk_parity(
        cov, returns_matrix=returns, use_ledoit_wolf=True
    )
    assert rp["success"] is True
    assert len(rp["weights"]) == 3

    ms = po_mod.PortfolioOptimizer.max_sharpe_ratio(
        expected, cov, returns_matrix=returns, use_ledoit_wolf=True
    )
    assert ms["success"] is True
    assert len(ms["weights"]) == 3

    minv = po_mod.PortfolioOptimizer.min_variance(
        cov, returns_matrix=returns, use_ledoit_wolf=True
    )
    assert minv["success"] is True
    assert len(minv["weights"]) == 3

    # sklearn 缺失时应平滑降级
    monkeypatch.setattr(po_mod, "LedoitWolf", None)
    degraded = po_mod.PortfolioOptimizer.max_sharpe_ratio(
        expected, cov, returns_matrix=returns, use_ledoit_wolf=True
    )
    assert degraded["success"] is True
    assert len(degraded["weights"]) == 3
    assert isinstance(degraded["sharpe_ratio"], float)


@pytest.mark.asyncio
async def test_p0_10_search_similar_stocks_should_fallback_to_market_candidates(monkeypatch):
    class _VectorConn:
        def __init__(self):
            self.calls = []

        async def fetch(self, query, *args):
            self.calls.append(query)
            if 'WHERE industry = $1' in query:
                return []
            if 'WHERE code != $1' in query:
                return [{'code': '000001', 'stock_name': '平安银行'}]
            return []

    class _VectorDB:
        def __init__(self, conn):
            self.conn = conn

        def acquire(self):
            return _Acquire(self.conn)

        async def get_stock_info(self, code):
            if code == '600519':
                return {'name': '贵州茅台', 'industry': '白酒', 'pe_ratio': 20.0, 'pb_ratio': 5.0}
            if code == '000001':
                return {'name': '平安银行', 'industry': '银行', 'pe_ratio': 6.0, 'pb_ratio': 0.8}
            return None

        async def get_financials(self, code, limit=1):
            return []

        async def get_klines(self, code, limit=60):
            return []

    conn = _VectorConn()
    mcp = _DummyMCP()
    vector_mod.register(mcp)
    monkeypatch.setattr(vector_mod, 'get_db', lambda: _VectorDB(conn))

    result = await mcp.search_similar_stocks('600519', top_n=5, similarity_type='fundamental')
    assert result['success'] is True
    data = result['data']
    assert data['candidate_scope'] == 'market'
    assert data['total_candidates'] == 1
    assert data['similar_stocks'][0]['code'] == '000001'
    assert any('WHERE industry = $1' in query for query in conn.calls)
    assert any('WHERE code != $1' in query for query in conn.calls)


@pytest.mark.asyncio
async def test_p0_11_calculate_factor_should_accept_aliases(monkeypatch):
    class _QuantDB:
        async def get_klines(self, code, limit=100):
            return [{'close': float(i)} for i in range(1, 80)]

        async def get_financials(self, code, limit=1):
            return [{'roe': 18.0, 'debt_ratio': 30.0, 'profit_growth': 10.0}]

        async def get_stock_info(self, code):
            return {'market_cap': 1000000000.0}

    mcp = _DummyMCP()
    quant_mod.register(mcp)
    monkeypatch.setattr(quant_mod, 'get_db', lambda: _QuantDB())

    rsi_res = await mcp.calculate_factor('600519', 'rsi')
    assert rsi_res['success'] is True
    assert rsi_res['data']['factor'] == 'rsi_14'

    mom_res = await mcp.calculate_factor('600519', 'momentum_20d')
    assert mom_res['success'] is True
    assert mom_res['data']['factor'] == 'momentum'


@pytest.mark.asyncio
async def test_p0_12_research_manager_should_normalize_limit(monkeypatch):
    captured = {}

    def _fake_get_stock_research(code, limit=10):
        captured['limit'] = limit
        return {
            'success': True,
            'data': {
                'reports': [{'title': 'r1'}, {'title': 'r2'}][:limit],
                'total': min(limit, 2),
            },
        }

    mcp = _DummyMCP()
    research_manager_mod.register_research_manager(mcp)
    monkeypatch.setattr(research_manager_mod, 'get_db', lambda: object())
    monkeypatch.setattr(news_mod, 'get_stock_research', _fake_get_stock_research)

    result = await mcp.research_manager(action='get_reports', code='600519', kwargs='{"limit": "2"}')
    assert result['success'] is True
    assert captured['limit'] == 2
    assert result['data']['count'] == 2


@pytest.mark.asyncio
async def test_p0_13_sector_manager_should_accept_days_alias(monkeypatch):
    class _SectorConn:
        async def fetch(self, query, *args):
            if 'FROM market_blocks WHERE block_type' in query:
                return [{'block_code': 'BK001', 'block_name': '半导体'}]
            if 'FROM block_stocks WHERE block_code' in query:
                return [{'stock_code': '600519'}]
            return []

    class _SectorDB:
        def acquire(self):
            return _Acquire(_SectorConn())

        async def get_klines(self, code, limit=31):
            return [{'close': 100.0}, {'close': 110.0}]

    mcp = _DummyMCP()
    sector_manager_mod.register_sector_manager(mcp)
    monkeypatch.setattr(sector_manager_mod, 'get_db', lambda: _SectorDB())

    result = await mcp.sector_manager(action='sector_rotation', kwargs='{"days": "30"}')
    assert result['success'] is True
    assert result['data']['period'] == 30


@pytest.mark.asyncio
async def test_p0_14_market_insight_sector_analysis_should_filter_requested_sector(monkeypatch):
    mcp = _DummyMCP()
    market_insight_manager_mod.register_market_insight_manager(mcp)

    monkeypatch.setattr(fund_flow_mod, 'get_sector_fund_flow', lambda top_n=10: {
        'success': True,
        'data': [
            {'name': '半导体', 'mainNetInflow': 12.3},
            {'name': '银行', 'mainNetInflow': -2.0},
        ],
    })
    monkeypatch.setattr(fund_flow_mod, 'get_concept_fund_flow', lambda top_n=5: {
        'success': True,
        'data': [
            {'name': 'AI芯片', 'mainNetInflow': 8.8},
            {'name': '白酒', 'mainNetInflow': -1.0},
        ],
    })

    result = await mcp.market_insight_manager(action='sector_analysis', kwargs='{"sector": "半导体"}')
    assert result['success'] is True
    data = result['data']
    assert data['requestedSector'] == '半导体'
    assert data['matchedCount'] == 1
    assert data['hotSectors'][0]['name'] == '半导体'


@pytest.mark.asyncio
async def test_p0_14b_data_warmup_should_accept_comma_separated_stock_string(monkeypatch):
    mcp = _DummyMCP()
    data_warmup_mod.register(mcp)

    captured = {}

    async def _fake_sync_stock_klines(*, codes, start_date, end_date, period):
        captured['codes'] = list(codes)
        captured['start_date'] = start_date
        captured['end_date'] = end_date
        captured['period'] = period
        return {'synced': len(codes), 'failed': 0, 'total': len(codes)}

    monkeypatch.setattr(data_warmup_mod.data_sync_service, 'sync_stock_klines', _fake_sync_stock_klines)

    result = await mcp.data_warmup(
        action='warmup',
        stocks='600519, 000001, 600519',
        lookback_days=30,
    )

    assert result['success'] is True
    assert result['data']['stocks_warmed'] == 2
    assert captured['codes'] == ['600519', '000001']
    assert captured['period'] == 'daily'


@pytest.mark.asyncio
async def test_p0_15_comprehensive_manager_quick_scan_should_honor_single_code(monkeypatch):
    class _ComprehensiveDB:
        async def get_klines(self, code, limit=1):
            if code == '600519':
                return [{'date': '2026-02-01', 'close': 100.0, 'change_pct': 1.2, 'volume': 12345}]
            return []

    mcp = _DummyMCP()
    comprehensive_manager_mod.register_comprehensive_manager(mcp)
    monkeypatch.setattr(comprehensive_manager_mod, 'get_db', lambda: _ComprehensiveDB())

    result = await mcp.comprehensive_manager(action='quick_scan', code='600519')
    assert result['success'] is True
    assert result['data']['scanned'] == 1
    assert result['data']['results'][0]['code'] == '600519'


@pytest.mark.asyncio
async def test_p0_16_alerts_manager_update_should_preserve_status_when_status_missing(monkeypatch):
    alerts_tool_mod._alerts_store.clear()
    mcp = _DummyMCP()
    alerts_manager_mod.register_alerts_manager(mcp)

    created = await mcp.alerts_manager(action='create', code='600519', indicator='price', condition='>', value=1800)
    assert created['success'] is True
    alert_id = created['data']['alert_id']

    updated = await mcp.alerts_manager(action='update', alert_id=alert_id, value=1900)
    assert updated['success'] is True
    assert updated['data']['status'] == 'active'
    assert updated['data']['alert']['value'] == pytest.approx(1900.0)
    assert alerts_tool_mod._alerts_store[alert_id]['active'] is True


@pytest.mark.asyncio
async def test_p0_16a_alerts_manager_accepts_structured_params(monkeypatch):
    alerts_tool_mod._alerts_store.clear()
    mcp = _DummyMCP()
    alerts_manager_mod.register_alerts_manager(mcp)

    created = await mcp.alerts_manager(
        action='create',
        params={'code': '600519', 'indicator': 'price', 'condition': '>', 'value': 1800},
    )
    assert created['success'] is True

    listed = await mcp.alerts_manager(action='list', params={'status': 'active'})
    assert listed['success'] is True
    assert listed['data']['count'] >= 1


@pytest.mark.asyncio
async def test_p0_17_search_stocks_should_match_industry_keyword(monkeypatch):
    class _SearchConn:
        async def fetch(self, query, *args):
            assert 'industry IS NOT NULL' in query
            return [
                {'code': '600519', 'stock_name': '贵州茅台', 'industry': '白酒', 'market_cap': 123.0}
            ]

    class _SearchDB:
        def acquire(self):
            return _Acquire(_SearchConn())

    mcp = _DummyMCP()
    search_mod.register(mcp)
    monkeypatch.setattr(search_mod, 'get_db', lambda: _SearchDB())

    result = await mcp.search_stocks(keyword='白酒', limit=5)
    assert result['success'] is True
    assert result['data']['count'] == 1
    assert result['data']['results'][0]['industry'] == '白酒'


def test_p0_18_search_stocks_tushare_fallback_should_match_industry_keyword(monkeypatch):
    class _SimpleDF:
        empty = False

        def iterrows(self):
            yield 0, {'ts_code': '600519.SH', 'symbol': '600519', 'name': '贵州茅台', 'industry': '白酒'}

    class _FakePro:
        def stock_basic(self, **kwargs):
            return _SimpleDF()

    monkeypatch.setattr(search_mod.data_source, 'get_tushare_pro', lambda: _FakePro())
    results = search_mod._search_stocks_tushare_fallback('白酒', 5)
    assert len(results) == 1
    assert results[0]['code'] == '600519'


@pytest.mark.asyncio
async def test_p0_19_semantic_stock_search_should_prioritize_industry_match(monkeypatch):
    class _VectorConn:
        async def fetch(self, query, *args):
            if 'WHERE industry IS NOT NULL AND LOWER(industry) LIKE $1' in query:
                assert args[0] == '%白酒%'
                return [
                    {'code': '600519', 'stock_name': '贵州茅台', 'industry': '白酒', 'market_cap': 100.0, 'pe_ratio': 30.0, 'pb_ratio': 8.0},
                    {'code': '000858', 'stock_name': '五粮液', 'industry': '白酒', 'market_cap': 90.0, 'pe_ratio': 25.0, 'pb_ratio': 6.0},
                ]
            return [
                {'code': '600630', 'stock_name': '龙头股份', 'industry': '纺织服饰', 'market_cap': 10.0, 'pe_ratio': 10.0, 'pb_ratio': 1.0},
            ]

    class _VectorDB:
        def acquire(self):
            return _Acquire(_VectorConn())

    mcp = _DummyMCP()
    vector_mod.register(mcp)
    monkeypatch.setattr(vector_mod, 'get_db', lambda: _VectorDB())

    result = await mcp.semantic_stock_search(query='白酒龙头', limit=3)
    assert result['success'] is True
    assert result['data']['results'][0]['code'] == '600519'
    assert result['data']['results'][0]['industry'] == '白酒'
    returned_codes = [item['code'] for item in result['data']['results']]
    assert '000858' in returned_codes
    if '600630' in returned_codes:
        leader = next(item for item in result['data']['results'] if item['code'] == '600630')
        assert leader['score'] < result['data']['results'][0]['score']


@pytest.mark.asyncio
async def test_p0_19b_semantic_stock_search_should_not_match_single_char_sector_fallback(monkeypatch):
    class _EmptyConn:
        async def fetch(self, query, *args):
            return []

    class _EmptyDB:
        def acquire(self):
            return _Acquire(_EmptyConn())

    class _Frame:
        def __init__(self, rows):
            self._rows = rows
            self.empty = not rows

        def iterrows(self):
            for idx, row in enumerate(self._rows):
                yield idx, row

        def head(self, count):
            return _Frame(self._rows[:count])

    def _stock_sector_detail(sector):
        if sector == 'new_whitewine':
            return _Frame([{'code': '600519', 'name': '贵州茅台'}])
        if sector == 'new_tourism':
            return _Frame([{'code': '600054', 'name': '黄山旅游'}])
        return _Frame([])

    monkeypatch.setattr(vector_mod, 'get_db', lambda: _EmptyDB())
    monkeypatch.setattr(
        akshare,
        'stock_sector_spot',
        lambda: _Frame([
            {'板块': '酒店旅游', 'label': 'new_tourism'},
            {'板块': '白酒概念', 'label': 'new_whitewine'},
        ]),
        raising=False,
    )
    monkeypatch.setattr(akshare, 'stock_board_industry_name_ths', lambda: _Frame([]), raising=False)
    monkeypatch.setattr(akshare, 'stock_sector_detail', _stock_sector_detail, raising=False)
    monkeypatch.setitem(sys.modules, 'akshare', akshare)

    mcp = _DummyMCP()
    vector_mod.register(mcp)

    result = await mcp.semantic_stock_search(query='白酒', limit=5)

    assert result['success'] is True
    returned_codes = [item['code'] for item in result['data']['results']]
    assert '600519' in returned_codes
    assert '600054' not in returned_codes
    assert result['data']['results'][0]['code'] == '600519'
    assert result['data']['results'][0]['match_type']


@pytest.mark.asyncio
async def test_p0_19c_semantic_stock_search_should_use_ths_concept_constituents(monkeypatch):
    class _EmptyConn:
        async def fetch(self, query, *args):
            return []

    class _EmptyDB:
        def acquire(self):
            return _Acquire(_EmptyConn())

    class _Frame:
        def __init__(self, rows):
            self._rows = rows
            self.empty = not rows

        def iterrows(self):
            for idx, row in enumerate(self._rows):
                yield idx, row

    def _concept_rows(block_code, block_name):
        assert block_code == '301496'
        assert block_name == '白酒概念'
        return [
            {'stock_code': '600519', 'stock_name': '贵州茅台'},
            {'stock_code': '000858', 'stock_name': '五粮液'},
        ]

    monkeypatch.setattr(vector_mod, 'get_db', lambda: _EmptyDB())
    monkeypatch.setattr(akshare, 'stock_sector_spot', lambda: _Frame([]), raising=False)
    monkeypatch.setattr(akshare, 'stock_board_industry_name_ths', lambda: _Frame([]), raising=False)
    monkeypatch.setattr(
        akshare,
        'stock_board_concept_name_ths',
        lambda: _Frame([{'name': '白酒概念', 'code': '301496'}]),
        raising=False,
    )
    monkeypatch.setattr(market_blocks_mod, '_fetch_concept_stocks_from_ths', _concept_rows)
    monkeypatch.setitem(sys.modules, 'akshare', akshare)

    mcp = _DummyMCP()
    vector_mod.register(mcp)

    result = await mcp.semantic_stock_search(query='白酒', limit=5)

    assert result['success'] is True
    returned_codes = [item['code'] for item in result['data']['results']]
    assert returned_codes[:2] == ['600519', '000858']
    assert all('industry' in item for item in result['data']['results'])
    assert result['data']['results'][0]['industry'] == '白酒概念'


@pytest.mark.asyncio
async def test_p0_19d_semantic_stock_search_should_not_leak_akshare_stdout(monkeypatch, capsys):
    class _EmptyConn:
        async def fetch(self, query, *args):
            return []

    class _EmptyDB:
        def acquire(self):
            return _Acquire(_EmptyConn())

    class _Frame:
        def __init__(self, rows):
            self._rows = rows
            self.empty = not rows

        def iterrows(self):
            for idx, row in enumerate(self._rows):
                yield idx, row

        def head(self, count):
            return _Frame(self._rows[:count])

    def _noisy_sector_spot():
        print("sector spot progress should not reach stdout")
        return _Frame([])

    def _noisy_industry_names():
        print("industry ths progress should not reach stdout")
        return _Frame([])

    def _noisy_concept_names():
        print("concept ths progress should not reach stdout")
        return _Frame([{'name': '白酒概念', 'code': '301496'}])

    def _concept_rows(block_code, block_name):
        return [{'stock_code': '600519', 'stock_name': '贵州茅台'}]

    monkeypatch.setattr(vector_mod, 'get_db', lambda: _EmptyDB())
    monkeypatch.setattr(akshare, 'stock_sector_spot', _noisy_sector_spot, raising=False)
    monkeypatch.setattr(akshare, 'stock_board_industry_name_ths', _noisy_industry_names, raising=False)
    monkeypatch.setattr(akshare, 'stock_board_concept_name_ths', _noisy_concept_names, raising=False)
    monkeypatch.setattr(market_blocks_mod, '_fetch_concept_stocks_from_ths', _concept_rows)
    monkeypatch.setitem(sys.modules, 'akshare', akshare)

    mcp = _DummyMCP()
    vector_mod.register(mcp)

    result = await mcp.semantic_stock_search(query='白酒', limit=5)
    captured = capsys.readouterr()

    assert result['success'] is True
    assert result['data']['results'][0]['code'] == '600519'
    assert captured.out == ''


def test_p0_19e_market_blocks_ths_should_not_leak_akshare_stdout(monkeypatch, capsys):
    class _Frame:
        def __init__(self, rows):
            self._rows = rows
            self.empty = not rows

        def iterrows(self):
            for idx, row in enumerate(self._rows):
                yield idx, row

    def _noisy_concept_names():
        print("market blocks concept progress should not reach stdout")
        return _Frame([{'name': '白酒概念', 'code': '301496'}])

    monkeypatch.setattr(market_blocks_mod.ak, 'stock_board_concept_name_ths', _noisy_concept_names, raising=False)

    result = market_blocks_mod._fetch_from_ths('concept')
    captured = capsys.readouterr()

    assert result
    assert result[0]['block_code'] == '301496'
    assert captured.out == ''


@pytest.mark.asyncio
async def test_p0_20_event_manager_should_fallback_to_content_sources(monkeypatch):
    class _EventConn:
        async def fetch(self, query, *args):
            return []

    class _EventDB:
        def acquire(self):
            return _Acquire(_EventConn())

    mcp = _DummyMCP()
    event_manager_mod.register_event_manager(mcp)
    monkeypatch.setattr(event_manager_mod, 'get_db', lambda: _EventDB())
    monkeypatch.setattr(event_manager_mod, 'get_stock_news', lambda code, limit=10: {
        'success': True,
        'data': [{'title': '宁德时代获机构关注', 'date': '2026-03-03', 'source': '新闻源'}],
    })
    monkeypatch.setattr(event_manager_mod, 'get_stock_notices', lambda **kwargs: {
        'success': True,
        'data': {'events': [{'title': '宁德时代年度报告', 'date': '2026-03-02', 'source': '公告'}]},
    })
    monkeypatch.setattr(event_manager_mod, 'get_stock_research', lambda code, limit=10: {
        'success': True,
        'data': {'reports': [{'title': '维持买入评级', 'date': '2026-03-01', 'institution': '机构A'}]},
    })
    monkeypatch.setattr(event_manager_mod, 'get_research_reports', lambda **kwargs: {'success': True, 'data': []})

    result = await mcp.event_manager(action='get_by_code', kwargs='{"code":"300750"}')
    assert result['success'] is True
    assert result['data']['source'] == 'aggregated_content'
    assert result['data']['fallback_used'] is True
    assert result['data']['count'] == 3
    assert {item['event_type'] for item in result['data']['events']} == {'news', 'notice', 'research'}


@pytest.mark.asyncio
async def test_p0_21_relative_valuation_should_fallback_to_market_peers_when_industry_missing(monkeypatch):
    class _ValuationConn:
        async def fetch(self, query, *args):
            if 'ORDER BY ABS(COALESCE(market_cap, 0) - $2) ASC' in query:
                return [
                    {'code': 'P1'}, {'code': 'P2'}, {'code': 'P3'}, {'code': 'P4'}, {'code': 'P5'}
                ]
            return []

    class _ValuationDB:
        def __init__(self):
            self.stock_info = {
                'TGT': {'name': '目标公司', 'industry': None, 'market_cap': 100.0, 'pe_ratio': 20.0, 'pb_ratio': 3.0},
                'P1': {'name': '同业1', 'market_cap': 95.0, 'pe_ratio': 15.0, 'pb_ratio': 2.0},
                'P2': {'name': '同业2', 'market_cap': 98.0, 'pe_ratio': 16.0, 'pb_ratio': 2.1},
                'P3': {'name': '同业3', 'market_cap': 102.0, 'pe_ratio': 17.0, 'pb_ratio': 2.2},
                'P4': {'name': '同业4', 'market_cap': 105.0, 'pe_ratio': 18.0, 'pb_ratio': 2.3},
                'P5': {'name': '同业5', 'market_cap': 110.0, 'pe_ratio': 19.0, 'pb_ratio': 2.4},
            }
            self.financials = {
                code: [{'roe': 0.15, 'debt_ratio': 0.4, 'revenue_yoy': 0.12, 'operating_cash_flow': 120.0, 'net_profit': 100.0}]
                for code in ['TGT', 'P1', 'P2', 'P3', 'P4', 'P5']
            }

        def acquire(self):
            return _Acquire(_ValuationConn())

        async def get_stock_info(self, code):
            return self.stock_info.get(code)

        async def get_financials(self, code, limit=1):
            rows = self.financials.get(code, [])
            return rows[:limit]

    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, 'get_db', lambda: _ValuationDB())

    result = await mcp.relative_valuation('TGT')
    assert result['success'] is True
    assert result['data']['peer_count'] == 5
    assert result['data']['peer_pool_build']['peer_source'] == 'market_cap_fallback'
    assert 'industry_missing' in result['data']['peer_pool_build']['fallback_reasons']


@pytest.mark.asyncio
async def test_p0_21b_relative_valuation_tracks_invalid_metrics_and_alias_financials(monkeypatch):
    class _ValuationConn:
        async def fetch(self, query, *args):
            if 'WHERE industry = $1 AND code != $2' in query:
                return [
                    {'code': 'P1'}, {'code': 'P2'}, {'code': 'P3'}, {'code': 'P4'}, {'code': 'P5'}
                ]
            return []

    class _ValuationDB:
        def __init__(self):
            self.stock_info = {
                'TGT': {'name': '目标公司', 'industry': '白酒', 'market_cap': 100.0, 'pe_ratio': 0.0, 'pb_ratio': 3.0, 'ps_ratio': -1.0},
                'P1': {'name': '同业1', 'market_cap': 95.0, 'pe_ratio': 15.0, 'pb_ratio': 2.0, 'ps_ratio': 1.0},
                'P2': {'name': '同业2', 'market_cap': 98.0, 'pe_ratio': 16.0, 'pb_ratio': 2.1, 'ps_ratio': 1.1},
                'P3': {'name': '同业3', 'market_cap': 102.0, 'pe_ratio': 17.0, 'pb_ratio': 2.2, 'ps_ratio': 1.2},
                'P4': {'name': '同业4', 'market_cap': 105.0, 'pe_ratio': 18.0, 'pb_ratio': 2.3, 'ps_ratio': 1.3},
                'P5': {'name': '同业5', 'market_cap': 110.0, 'pe_ratio': 19.0, 'pb_ratio': 0.0, 'ps_ratio': 1.4},
            }
            self.financials = {
                'TGT': [{'roe': 0.15, 'debtRatio': 0.40, 'revenueGrowth': 0.12, 'operatingCashFlow': 120.0, 'net_profit': 100.0}],
                'P1': [{'roe': 0.16, 'debt_ratio': 0.35, 'revenue_yoy': 0.11, 'operating_cash_flow': 130.0, 'netProfit': 100.0}],
                'P2': [{'roe': 0.15, 'debt_ratio': 0.36, 'revenue_yoy': 0.12, 'operating_cash_flow': 125.0, 'netProfit': 100.0}],
                'P3': [{'roe': 0.14, 'debtRatio': 0.38, 'revenueGrowth': 0.13, 'operatingCashFlow': 140.0, 'netProfit': 100.0}],
                'P4': [{'roe': 0.17, 'debt_ratio': 0.39, 'revenue_growth': 0.14, 'operating_cash_flow': 150.0, 'net_profit': 100.0}],
                'P5': [{'roe': 0.16, 'debt_ratio': 0.41, 'revenue_growth': 0.10, 'operating_cash_flow': 135.0, 'net_profit': 100.0}],
            }

        def acquire(self):
            return _Acquire(_ValuationConn())

        async def get_stock_info(self, code):
            return self.stock_info.get(code)

        async def get_financials(self, code, limit=1):
            rows = self.financials.get(code, [])
            return rows[:limit]

    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, 'get_db', lambda: _ValuationDB())

    result = await mcp.relative_valuation('TGT', metrics=['pe_ratio', 'pb_ratio', 'ps_ratio'])
    assert result['success'] is True
    assert result['data']['target_metrics'] == {'pb_ratio': 3.0}
    assert result['data']['invalid_target_metrics']['pe_ratio']['reason'] == 'non_positive'
    assert result['data']['invalid_target_metrics']['ps_ratio']['reason'] == 'non_positive'
    assert result['data']['invalid_peer_metrics']['pb_ratio']['non_positive'] == 1
    assert result['data']['peer_count'] == 5
    assert result['data']['peer_pool_build']['peer_source'] == 'industry'
    assert result['data']['peer_pool_build']['quality_thresholds']['debt_ratio_max'] == pytest.approx(0.65)


def test_p1_limit_up_statistics_should_handle_none_fields(monkeypatch):
    monkeypatch.setattr(
        limit_up_mod,
        'get_limit_up_stocks',
        lambda date='': {
            'success': True,
            'data': [
                {'tradeDate': '2026-01-15', 'continuousDays': None, 'openTimes': None},
                {'tradeDate': '2026-01-15', 'continuousDays': '2', 'openTimes': '1'},
                {'tradeDate': '2026-01-15', 'continuousDays': 4, 'openTimes': 0},
            ],
            'source': 'unit_test',
            'source_chain': ['unit_test'],
            'data_quality': {'missing_field_counts': {'openTimes': 1}},
        },
    )

    result = limit_up_mod.get_limit_up_statistics('2026-01-15')

    assert result['success'] is True
    assert result['data']['firstBoard'] == 0
    assert result['data']['secondBoard'] == 1
    assert result['data']['higherBoard'] == 1
    assert result['data']['failedBoard'] == 1


@pytest.mark.asyncio
async def test_p1_analyze_portfolio_risk_should_accept_codes_weights(monkeypatch):
    class _RiskDB:
        async def get_klines(self, code, limit=252):
            base = 10.0 if code == '600519' else 20.0
            return [
                {'close': base, 'volume': 1000},
                {'close': base * 1.02, 'volume': 1100},
                {'close': base * 1.03, 'volume': 1200},
            ]

    mcp = _DummyMCP()
    portfolio_mod.register(mcp)
    monkeypatch.setattr(portfolio_mod, 'get_db', lambda: _RiskDB())

    result = await mcp.analyze_portfolio_risk(codes=['600519', '000858'], weights=[0.6, 0.4])

    assert result['success'] is True
    assert result['data']['coverage']['requested'] == 2
    assert len(result['data']['analyzed_holdings']) == 2
    assert result['data']['portfolio_id'] is None


@pytest.mark.asyncio
async def test_p1_decision_manager_portfolio_advice_should_use_explicit_codes_weights(monkeypatch):
    class _DecisionDB:
        async def get_klines(self, code, limit=100):
            base = 10.0 if code == '600519' else 30.0
            return [
                {'close': base + i * 0.1, 'volume': 1000 + i * 10}
                for i in range(100)
            ]

        async def get_financials(self, code, limit=1):
            return [{
                'roe': 18.0,
                'pe_ratio': 20.0,
                'debt_ratio': 0.3,
                'pb_ratio': 2.0,
            }]

        async def save_klines(self, code, klines):
            return None

    mcp = _DummyMCP()
    decision_manager_mod.register_decision_manager(mcp)
    monkeypatch.setattr(decision_manager_mod, 'get_db', lambda: _DecisionDB())

    result = await mcp.decision_manager(
        action='portfolio_advice',
        codes=['600519', '000858'],
        weights=[0.4, 0.6],
    )

    assert result['success'] is True
    assert result['data']['codes'] == ['600519', '000858']
    assert len(result['data']['holdings_advice']) == 2
    assert result['data']['overall_score'] >= 0


@pytest.mark.asyncio
async def test_p1_scenario_dcf_should_auto_fill_base_revenue(monkeypatch):
    class _ScenarioDB:
        async def get_financials(self, code, limit=8):
            return [{
                'revenue': 5_000_000_000,
                'net_profit': 800_000_000,
            }]

    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, 'get_db', lambda: _ScenarioDB())

    result = await mcp.scenario_dcf_valuation(code='600519', industry='消费', years=3)

    assert result['success'] is True
    assert result['data']['base_revenue'] == pytest.approx(5_000_000_000.0)
    assert result['data']['base_revenue_source'] == 'financial_revenue'
    assert 'db.get_financials' in result['data']['source_chain']
