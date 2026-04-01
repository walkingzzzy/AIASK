from ._test_p0_regressions_support import *


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

__all__ = [name for name in globals() if name.startswith("test_")]
