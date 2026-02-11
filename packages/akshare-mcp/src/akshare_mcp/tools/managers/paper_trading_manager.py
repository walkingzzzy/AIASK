"""模拟交易管理器"""

import json
import uuid
import logging
from datetime import datetime
from ...storage import get_db
from ...utils import ok, fail

logger = logging.getLogger(__name__)


def _normalize_kwargs(kwargs: dict) -> dict:
    """统一解析 kwargs 参数（兼容 JSON 字符串和 dict）"""
    raw = kwargs.get("kwargs")
    if isinstance(raw, dict):
        kwargs = {**kwargs, **raw}
    elif isinstance(raw, str):
        try:
            extra = json.loads(raw or "{}")
            if isinstance(extra, dict):
                kwargs = {**kwargs, **extra}
        except Exception:
            pass
    # 兼容 code / stock_code / symbol
    if "code" not in kwargs:
        kwargs["code"] = kwargs.get("stock_code") or kwargs.get("symbol")
    return kwargs


async def _ensure_account(user_id: str, db) -> str:
    """确保用户有默认账户，没有则自动创建（行业标准：$100k初始资金）"""
    async with db.acquire() as conn:
        account = await conn.fetchrow(
            "SELECT id FROM paper_accounts WHERE user_id = $1 ORDER BY created_at LIMIT 1",
            user_id
        )
        if account:
            return account['id']

        account_id = str(uuid.uuid4())[:8]
        await conn.execute(
            """INSERT INTO paper_accounts (id, user_id, name, initial_capital, current_capital, total_value, created_at)
               VALUES ($1, $2, $3, $4, $4, $4, NOW())""",
            account_id, user_id, f'默认账户_{user_id}', 100000
        )
        logger.info(f"[PaperTrading] 自动创建默认账户: {account_id}, 初始资金: $100k")
        return account_id


def register_paper_trading_manager(mcp):
    """注册模拟交易管理器工具"""
    
    @mcp.tool()
    async def paper_trading_manager(action: str, **kwargs):
        """模拟交易管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/create_account/place_order/get_positions/list/positions/orders/summary
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - create_account: name(str, optional), initial_capital(float, optional)
                - place_order: account_id(str), code(str), direction(str, "buy"/"sell"), quantity(int), price(float, optional)
                - get_positions / positions: account_id(str)
                - list: 无需额外参数（列出所有模拟账户）
                - orders: account_id(str)
                - summary: account_id(str)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            paper_trading_manager(action="help", kwargs="{}")
            # 创建模拟账户
            paper_trading_manager(action="create_account", kwargs='{"name":"测试账户","initial_capital":200000}')
            # 模拟买入
            paper_trading_manager(action="place_order", kwargs='{"code":"600519","direction":"buy","quantity":100,"price":1800}')
            # 查看持仓
            paper_trading_manager(action="positions", kwargs="{}")
            # 账户摘要
            paper_trading_manager(action="summary", kwargs="{}")
        """
        try:
            db = get_db()
            kwargs = _normalize_kwargs(dict(kwargs))
            user_id = kwargs.get('user_id', 'default')
            
            SUPPORTED_ACTIONS = {
                'create_account': '创建模拟账户',
                'place_order': '下单交易',
                'get_positions': '获取持仓',
                'list': '获取持仓（别名）',
                'positions': '获取持仓（别名）',
                'orders': '获取订单列表',
                'summary': '获取账户摘要',
                'help': '显示帮助信息',
            }
            
            if action == 'help':
                return ok({'supported_actions': SUPPORTED_ACTIONS})
            
            elif action == 'create_account':
                initial_capital = kwargs.get('initial_capital', 100000)
                name = kwargs.get('name', f'模拟账户_{user_id}')
                account_id = str(uuid.uuid4())[:8]
                
                async with db.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO paper_accounts (id, user_id, name, initial_capital, current_capital, total_value, created_at)
                           VALUES ($1, $2, $3, $4, $4, $4, NOW())""",
                        account_id, user_id, name, initial_capital
                    )
                return ok({'account_id': account_id})
            
            elif action == 'place_order':
                account_id = kwargs.get('account_id')
                if not account_id:
                    account_id = await _ensure_account(user_id, db)
                
                code = kwargs.get('code')
                direction = kwargs.get('direction', 'buy')
                shares = kwargs.get('shares') or kwargs.get('quantity')
                price = kwargs.get('price')
                
                if not code:
                    return fail('需要提供 code 参数')
                if shares is None:
                    return fail('需要提供 shares 参数')
                
                # 市价单自动获取当前价格
                if price is None:
                    try:
                        from ..market import get_batch_quotes
                        from ...utils import normalize_code
                        quotes_res = get_batch_quotes([normalize_code(code)])
                        if quotes_res and quotes_res.get('success') and quotes_res.get('data'):
                            quote_list = quotes_res['data']
                            if isinstance(quote_list, list) and len(quote_list) > 0:
                                price = quote_list[0].get('price') or quote_list[0].get('close') or quote_list[0].get('now')
                            elif isinstance(quote_list, dict):
                                price = quote_list.get('price') or quote_list.get('close')
                    except Exception as e:
                        logger.warning(f"[PaperTrading] 获取实时价格失败: {e}")
                    
                    # 如果实时行情也拿不到，尝试从K线获取最新收盘价
                    if price is None:
                        try:
                            klines = await db.get_klines(code, limit=1)
                            if klines:
                                price = klines[0].get('close') or klines[-1].get('close')
                        except Exception:
                            pass
                    
                    if price is None:
                        return fail('市价单无法获取当前价格，请手动指定 price 参数')
                
                trade_id = str(uuid.uuid4())[:8]
                trade_type = 'buy' if direction in ('buy', 'long') else 'sell'
                amount = float(price) * int(shares)
                
                async with db.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO paper_trades 
                           (id, account_id, stock_code, stock_name, trade_type, price, quantity, amount, trade_time, created_at)
                           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())""",
                        trade_id, account_id, code, code, trade_type, price, int(shares), amount
                    )
                return ok({
                    'order_id': trade_id,
                    'status': 'filled',
                    'account_id': account_id,
                    'message': '已自动使用默认账户' if not kwargs.get('account_id') else None
                })
            
            elif action in ['get_positions', 'list', 'positions']:
                account_id = kwargs.get('account_id')
                if not account_id:
                    account_id = await _ensure_account(user_id, db)
                
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM paper_positions WHERE account_id = $1",
                        account_id
                    )
                    positions = [dict(row) for row in rows]
                
                return ok({
                    'account_id': account_id,
                    'positions': positions,
                    'count': len(positions),
                    'message': '已自动使用默认账户' if not kwargs.get('account_id') else None
                })
            
            elif action == 'orders':
                account_id = kwargs.get('account_id')
                if not account_id:
                    account_id = await _ensure_account(user_id, db)
                
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM paper_trades WHERE account_id = $1 ORDER BY created_at DESC LIMIT 50",
                        account_id
                    )
                    orders = [dict(row) for row in rows]
                
                return ok({
                    'account_id': account_id,
                    'orders': orders,
                    'count': len(orders),
                    'message': '已自动使用默认账户' if not kwargs.get('account_id') else None
                })
            
            elif action == 'summary':
                account_id = kwargs.get('account_id')
                if not account_id:
                    account_id = await _ensure_account(user_id, db)
                
                async with db.acquire() as conn:
                    account = await conn.fetchrow(
                        "SELECT * FROM paper_accounts WHERE id = $1",
                        account_id
                    )
                    if not account:
                        return fail('账户不存在')
                    
                    positions = await conn.fetch(
                        "SELECT * FROM paper_positions WHERE account_id = $1",
                        account_id
                    )
                    
                return ok({
                    'account_id': account_id,
                    'account': dict(account),
                    'positions_count': len(positions),
                    'total_value': account.get('total_value', 0),
                    'message': '已自动使用默认账户' if not kwargs.get('account_id') else None
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: {", ".join(SUPPORTED_ACTIONS.keys())}')
        except Exception as e:
            return fail(str(e))