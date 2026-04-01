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

__all__ = [name for name in globals() if name not in {"__builtins__", "__all__"}]
