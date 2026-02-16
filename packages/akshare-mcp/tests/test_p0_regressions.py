import pytest

import akshare_mcp.tools.market.quote as quote_mod
import akshare_mcp.tools.managers.paper_trading_manager as ptm
import akshare_mcp.tools.managers.portfolio_manager as pm


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

