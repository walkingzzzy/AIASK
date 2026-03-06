"""模拟交易管理器 — P3 订单生命周期 + 佣金 + 风控"""

import json
import uuid
import logging
from datetime import datetime
from ...storage import get_db
from ...utils import ok, fail
from ...services.cost_model import build_cost_model

logger = logging.getLogger(__name__)

# 默认风控规则
DEFAULT_RISK_RULES = {
    "max_position_pct": 30.0,   # 单股最大仓位占比 %
    "max_drawdown_pct": 20.0,   # 最大回撤阈值 %
    "stop_loss_pct": 10.0,      # 个股止损线 %
}


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
    if "code" not in kwargs:
        kwargs["code"] = kwargs.get("stock_code") or kwargs.get("symbol")
    return kwargs


def _safe_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _canonical_stock_code(code: str | None) -> str:
    text = str(code or '').strip()
    digits = ''.join(ch for ch in text if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else text


def _price_limit_pct(code: str, stock_name: str | None = None) -> float:
    normalized = _canonical_stock_code(code)
    name = str(stock_name or '').upper()
    if 'ST' in name:
        return 0.05
    if normalized.startswith('688'):
        return 0.20
    if normalized.startswith('300'):
        return 0.20
    if normalized.startswith(('8', '4')):
        return 0.30
    return 0.10


async def _get_quote_snapshot(code: str) -> dict:
    try:
        from ..market import get_realtime_quote
        from ...utils import normalize_code
        res = get_realtime_quote(normalize_code(code))
        if res and res.get('success') and isinstance(res.get('data'), dict):
            return res['data']
    except Exception as e:
        logger.debug('[PaperTrading] 获取行情快照失败: %s', e)
    return {}


async def _get_previous_close(code: str, db, quote: dict | None = None) -> float | None:
    quote = quote or {}
    for key in ('preClose', 'pre_close', 'prev_close'):
        prev_close = _safe_float(quote.get(key))
        if prev_close is not None and prev_close > 0:
            return prev_close
    try:
        klines = await db.get_klines(code, limit=2)
        if klines:
            if len(klines) >= 2:
                prev_close = _safe_float(klines[-2].get('close'))
            else:
                prev_close = _safe_float(klines[-1].get('close'))
            if prev_close is not None and prev_close > 0:
                return prev_close
    except Exception:
        pass
    return None


async def _validate_price_limit(code: str, price: float | None, db) -> str | None:
    if price is None:
        return None
    quote = await _get_quote_snapshot(code)
    prev_close = await _get_previous_close(code, db, quote)
    if prev_close is None or prev_close <= 0:
        return None
    limit_pct = _price_limit_pct(code, quote.get('name'))
    lower = round(prev_close * (1 - limit_pct), 2)
    upper = round(prev_close * (1 + limit_pct), 2)
    normalized_price = round(float(price), 2)
    if normalized_price < lower - 0.01 or normalized_price > upper + 0.01:
        return f'涨跌停限制：价格 {normalized_price:.2f} 超出允许范围 [{lower:.2f}, {upper:.2f}]'
    return None


async def _get_sellable_quantity(conn, account_id: str, code: str) -> int:
    sellable = await conn.fetchval(
        """SELECT COALESCE(SUM(
               CASE WHEN trade_type='buy' AND DATE(trade_time) < CURRENT_DATE THEN quantity
                    WHEN trade_type='sell' THEN -quantity
                    ELSE 0 END
           ), 0)
           FROM paper_trades
           WHERE account_id=$1 AND stock_code=$2""",
        account_id, code
    )
    try:
        return max(int(sellable or 0), 0)
    except Exception:
        return 0


async def _validate_sell_request(conn, account_id: str, code: str, shares: int) -> str | None:
    existing_pos = await conn.fetchrow(
        "SELECT * FROM paper_positions WHERE account_id = $1 AND stock_code = $2",
        account_id, code
    )
    position_qty = int(existing_pos.get('quantity') or 0) if existing_pos else 0
    if position_qty < shares:
        return '持仓不足，无法卖出'
    sellable = await _get_sellable_quantity(conn, account_id, code)
    if shares > sellable:
        return f'T+1限制：可卖 {sellable} 股，请求卖出 {shares} 股'
    return None


async def _refresh_account_prices(db, account_id: str) -> list[dict]:
    async with db.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM paper_positions WHERE account_id=$1", account_id)
        account = await conn.fetchrow("SELECT * FROM paper_accounts WHERE id = $1", account_id)

    positions = [dict(row) for row in rows]
    if not positions:
        if account:
            cash = float(account.get('current_capital') or 0)
            async with db.acquire() as conn:
                await conn.execute(
                    "UPDATE paper_accounts SET current_capital=$1, total_value=$2, updated_at=NOW() WHERE id=$3",
                    cash, cash, account_id
                )
        return []

    try:
        from ..market.quote import get_batch_quotes_compat
        quote_result = get_batch_quotes_compat([row.get('stock_code') for row in positions if row.get('stock_code')])
        quotes = quote_result.get('data') if isinstance(quote_result, dict) else []
    except Exception as e:
        logger.warning('[PaperTrading] 批量刷新持仓价格失败: %s', e)
        quotes = []

    quote_map = {
        _canonical_stock_code(item.get('code')): item
        for item in quotes
        if isinstance(item, dict) and item.get('code')
    }

    market_value_sum = 0.0
    refreshed_positions: list[dict] = []
    async with db.acquire() as conn:
        for row in positions:
            price = None
            quote = quote_map.get(_canonical_stock_code(row.get('stock_code')))
            if quote:
                price = _safe_float(quote.get('price'))

            if price is None or price <= 0:
                refreshed_positions.append(row)
                market_value_sum += float(row.get('market_value') or 0)
                continue

            quantity = int(row.get('quantity') or 0)
            cost_price = float(row.get('cost_price') or 0)
            market_value = price * quantity
            profit_rate = ((price - cost_price) / cost_price) if cost_price else 0.0
            await conn.execute(
                """UPDATE paper_positions
                   SET quantity=$1, current_price=$2, market_value=$3, profit_rate=$4, updated_at=NOW()
                   WHERE account_id=$5 AND stock_code=$6""",
                quantity, price, market_value, profit_rate, account_id, row.get('stock_code')
            )
            refreshed = {
                **row,
                'current_price': price,
                'market_value': market_value,
                'profit_rate': profit_rate,
            }
            refreshed_positions.append(refreshed)
            market_value_sum += market_value

        current_capital = float(account.get('current_capital') or 0) if account else 0.0
        await conn.execute(
            "UPDATE paper_accounts SET current_capital=$1, total_value=$2, updated_at=NOW() WHERE id=$3",
            current_capital, current_capital + market_value_sum, account_id
        )

    return refreshed_positions


async def _ensure_account(user_id: str, db) -> str:
    """确保用户有默认账户，没有则自动创建"""
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
        return account_id


async def _fill_order(conn, account_id: str, code: str, trade_type: str,
                      shares: int, price: float, order_id: str = None):
    """统一成交记账：写 trade → 更新 position → 更新 account。返回 (trade_id, commission)。"""
    amount = price * shares
    cost = build_cost_model({}, notional=amount, default_mode="execution")
    commission = cost["estimated"]["commission"]

    trade_id = order_id or str(uuid.uuid4())[:8]

    account = await conn.fetchrow("SELECT * FROM paper_accounts WHERE id = $1", account_id)
    if not account:
        raise ValueError("账户不存在")

    if trade_type == 'sell':
        reject = await _validate_sell_request(conn, account_id, code, shares)
        if reject:
            raise ValueError(reject)

    existing_pos = await conn.fetchrow(
        "SELECT * FROM paper_positions WHERE account_id = $1 AND stock_code = $2",
        account_id, code
    )

    await conn.execute(
        """INSERT INTO paper_trades
           (id, account_id, stock_code, stock_name, trade_type, price, quantity, amount, commission, trade_time, created_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())""",
        trade_id, account_id, code, code, trade_type, price, shares, amount, commission
    )

    if trade_type == 'buy':
        if existing_pos:
            old_qty = int(existing_pos.get('quantity') or 0)
            old_cost = float(existing_pos.get('cost_price') or 0)
            new_qty = old_qty + shares
            new_cost = ((old_cost * old_qty) + amount) / new_qty if new_qty > 0 else price
            market_value = price * new_qty
            profit_rate = ((price - new_cost) / new_cost) if new_cost else 0.0
            await conn.execute(
                """UPDATE paper_positions
                   SET quantity=$1, cost_price=$2, current_price=$3,
                       market_value=$4, profit_rate=$5, updated_at=NOW()
                   WHERE account_id=$6 AND stock_code=$7""",
                new_qty, new_cost, price, market_value, profit_rate, account_id, code
            )
        else:
            await conn.execute(
                """INSERT INTO paper_positions
                   (account_id, stock_code, stock_name, quantity, cost_price, current_price, market_value, profit_rate, created_at, updated_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW(),NOW())""",
                account_id, code, code, shares, price, price, amount, 0.0
            )
        capital_delta = -(amount + commission)
    else:
        old_qty = int(existing_pos.get('quantity') or 0)
        old_cost = float(existing_pos.get('cost_price') or 0)
        new_qty = old_qty - shares
        if new_qty > 0:
            market_value = price * new_qty
            profit_rate = ((price - old_cost) / old_cost) if old_cost else 0.0
            await conn.execute(
                """UPDATE paper_positions
                   SET quantity=$1, current_price=$2, market_value=$3, profit_rate=$4, updated_at=NOW()
                   WHERE account_id=$5 AND stock_code=$6""",
                new_qty, price, market_value, profit_rate, account_id, code
            )
        else:
            await conn.execute(
                "DELETE FROM paper_positions WHERE account_id=$1 AND stock_code=$2",
                account_id, code
            )
        capital_delta = amount - commission

    old_capital = float(account.get('current_capital') or 0)
    new_capital = old_capital + capital_delta
    mv_sum = await conn.fetchval(
        "SELECT COALESCE(SUM(market_value),0) FROM paper_positions WHERE account_id=$1", account_id
    )
    total_value = float(new_capital) + float(mv_sum or 0)
    await conn.execute(
        "UPDATE paper_accounts SET current_capital=$1, total_value=$2, updated_at=NOW() WHERE id=$3",
        new_capital, total_value, account_id
    )
    return trade_id, commission


async def _check_risk_before_buy(conn, account_id: str, code: str, amount: float) -> str | None:
    """买入前风控检查，返回拒绝原因或 None（通过）。"""
    account = await conn.fetchrow("SELECT * FROM paper_accounts WHERE id = $1", account_id)
    if not account:
        return "账户不存在"
    rules = account.get('risk_rules') or {}
    if isinstance(rules, str):
        try:
            rules = json.loads(rules)
        except Exception:
            rules = {}
    max_pos_pct = float(rules.get('max_position_pct', DEFAULT_RISK_RULES['max_position_pct']))
    max_dd_pct = float(rules.get('max_drawdown_pct', DEFAULT_RISK_RULES['max_drawdown_pct']))

    total_value = float(account.get('total_value') or 0)
    if total_value > 0 and (amount / total_value * 100) > max_pos_pct:
        return f"单股仓位超限: 买入金额占总资产 {amount/total_value*100:.1f}% > {max_pos_pct}%"

    initial = float(account.get('initial_capital') or 0)
    if initial > 0:
        drawdown = (initial - total_value) / initial * 100
        if drawdown > max_dd_pct:
            return f"账户回撤超限: {drawdown:.1f}% > {max_dd_pct}%，禁止新买入"
    return None


async def _get_price(code: str, db):
    """获取股票当前价格"""
    snapshot = await _get_quote_snapshot(code)
    price = _safe_float(snapshot.get('price')) if snapshot else None
    if price is not None and price > 0:
        return price
    try:
        klines = await db.get_klines(code, limit=1)
        if klines:
            return klines[0].get('close')
    except Exception as e:
        logger.warning("[PaperTrading] 获取实时价格失败: %s", e)
        pass
    return None


async def _record_order_event(conn, order_id: str, event_type: str,
                              account_id: str | None = None, code: str | None = None,
                              payload: dict | None = None):
    """订单事件审计（容错写入，不影响主流程）"""
    try:
        await conn.execute(
            """INSERT INTO order_events (order_id, account_id, code, event_type, payload, created_at)
               VALUES ($1, $2, $3, $4, $5::jsonb, NOW())""",
            str(order_id), account_id, code, event_type, json.dumps(payload or {})
        )
    except Exception as e:
        logger.debug("[PaperTrading] 记录 order_events 失败: %s", e)


def register_paper_trading_manager(mcp):
    """注册模拟交易管理器工具"""

    @mcp.tool()
    async def paper_trading_manager(action: str, **kwargs):
        """模拟交易管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型
            kwargs: JSON 字符串或关键字参数

        Supported actions:
            help, create_account, place_order, cancel_order, pending_orders,
            get_positions/list/positions, orders, order_events, summary, list_accounts/accounts,
            nav_history, set_risk_rules, matching_status, nav_status, update_prices
        """
        try:
            db = get_db()
            kwargs = _normalize_kwargs(dict(kwargs))
            user_id = kwargs.get('user_id', 'default')

            SUPPORTED_ACTIONS = {
                'create_account': '创建模拟账户',
                'place_order': '下单（market/limit/stop）',
                'cancel_order': '撤销挂单',
                'pending_orders': '查看挂单列表',
                'get_positions': '获取持仓', 'list': '获取持仓', 'positions': '获取持仓',
                'orders': '获取成交记录',
                'order_events': '查询订单事件',
                'summary': '账户摘要',
                'list_accounts': '列出所有账户',
                'accounts': '列出所有账户',
                'nav_history': '查看NAV历史',
                'set_risk_rules': '设置风控规则',
                'matching_status': '撮合引擎状态',
                'nav_status': 'NAV引擎状态',
                'update_prices': '批量刷新持仓现价/市值/盈亏',
                'help': '显示帮助',
            }

            if action == 'help':
                return ok({'supported_actions': SUPPORTED_ACTIONS})

            # --- create_account ---
            elif action == 'create_account':
                initial_capital = kwargs.get('initial_capital', 100000)
                name = kwargs.get('name', f'模拟账户_{user_id}')
                account_id = str(uuid.uuid4())[:8]
                async with db.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO paper_accounts (id,user_id,name,initial_capital,current_capital,total_value,created_at)
                           VALUES ($1,$2,$3,$4,$4,$4,NOW())""",
                        account_id, user_id, name, initial_capital
                    )
                return ok({'account_id': account_id})

            # --- place_order (market/limit/stop) ---
            elif action == 'place_order':
                account_id = kwargs.get('account_id')
                if not account_id:
                    account_id = await _ensure_account(user_id, db)

                code = kwargs.get('code')
                direction = kwargs.get('direction', 'buy')
                shares = kwargs.get('shares') or kwargs.get('quantity')
                price = kwargs.get('price')
                order_type = kwargs.get('order_type', 'market')
                stop_price = kwargs.get('stop_price')

                if not code:
                    return fail('需要提供 code 参数')
                if shares is None:
                    return fail('需要提供 shares 参数')
                try:
                    shares = int(shares)
                except Exception:
                    return fail('shares 必须是整数')
                if shares <= 0:
                    return fail('shares 必须大于 0')

                trade_type = 'buy' if direction in ('buy', 'long') else 'sell'
                if trade_type == 'buy' and shares % 100 != 0:
                    return fail('买入数量必须为100的整数倍（1手=100股）')

                # --- limit / stop 挂单 ---
                if order_type in ('limit', 'stop'):
                    if order_type == 'limit' and price is None:
                        return fail('限价单需要提供 price')
                    if order_type == 'stop' and stop_price is None:
                        return fail('止损单需要提供 stop_price')
                    try:
                        if price is not None:
                            price = float(price)
                        if stop_price is not None:
                            stop_price = float(stop_price)
                    except Exception:
                        return fail('price/stop_price 必须是数字')

                    rule_price = price if order_type == 'limit' else stop_price
                    price_limit_error = await _validate_price_limit(code, rule_price, db)
                    if price_limit_error:
                        return fail(price_limit_error)

                    order_id = str(uuid.uuid4())[:8]
                    async with db.acquire() as conn:
                        if trade_type == 'sell':
                            reject = await _validate_sell_request(conn, account_id, code, shares)
                            if reject:
                                return fail(reject)
                        row = await conn.fetchrow(
                            """INSERT INTO paper_orders
                               (account_id,code,direction,shares,price,order_type,stop_price,status,created_at,updated_at)
                               VALUES ($1,$2,$3,$4,$5,$6,$7,'pending',NOW(),NOW())
                               RETURNING id""",
                            account_id, code, trade_type, shares, price, order_type, stop_price
                        )
                        db_order_id = row['id'] if row else order_id
                        await _record_order_event(
                            conn,
                            str(db_order_id),
                            'created',
                            account_id=account_id,
                            code=code,
                            payload={
                                'order_type': order_type,
                                'direction': trade_type,
                                'shares': shares,
                                'price': price,
                                'stop_price': stop_price,
                            }
                        )
                    return ok({
                        'order_id': str(db_order_id), 'status': 'pending', 'order_type': order_type,
                        'account_id': account_id, 'code': code, 'direction': trade_type,
                        'shares': shares, 'price': price, 'stop_price': stop_price,
                    })

                # --- market 即时成交 ---
                if price is None:
                    price = await _get_price(code, db)
                if price is None:
                    return fail('市价单无法获取当前价格，请手动指定 price')
                try:
                    price = float(price)
                except Exception:
                    return fail('price 必须是数字')
                if price <= 0:
                    return fail('price 必须大于 0')

                price_limit_error = await _validate_price_limit(code, price, db)
                if price_limit_error:
                    return fail(price_limit_error)

                amount = price * shares
                async with db.acquire() as conn:
                    if trade_type == 'sell':
                        reject = await _validate_sell_request(conn, account_id, code, shares)
                        if reject:
                            return fail(reject)
                    # 买入前风控检查
                    if trade_type == 'buy':
                        reject = await _check_risk_before_buy(conn, account_id, code, amount)
                        if reject:
                            await _record_order_event(
                                conn,
                                f"risk-reject-{uuid.uuid4().hex[:8]}",
                                'risk_rejected',
                                account_id=account_id,
                                code=code,
                                payload={
                                    'order_type': 'market',
                                    'direction': trade_type,
                                    'shares': shares,
                                    'price': price,
                                    'reason': reject,
                                }
                            )
                            return fail(f'风控拒绝: {reject}')

                    trade_id, commission = await _fill_order(
                        conn, account_id, code, trade_type, shares, price
                    )
                    await _record_order_event(
                        conn,
                        str(trade_id),
                        'filled',
                        account_id=account_id,
                        code=code,
                        payload={
                            'order_type': 'market',
                            'direction': trade_type,
                            'shares': shares,
                            'price': price,
                            'amount': amount,
                            'commission': round(commission, 4),
                        }
                    )

                return ok({
                    'order_id': trade_id, 'status': 'filled', 'order_type': 'market',
                    'account_id': account_id, 'trade_type': trade_type,
                    'price': price, 'quantity': shares, 'amount': amount,
                    'commission': round(commission, 4),
                })

            # --- cancel_order ---
            elif action == 'cancel_order':
                order_id = kwargs.get('order_id')
                if not order_id:
                    return fail('需要提供 order_id')
                async with db.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT * FROM paper_orders WHERE id=$1 AND status='pending'", int(order_id)
                    )
                    if not row:
                        return fail('未找到该挂单或已非 pending 状态')
                    await conn.execute(
                        "UPDATE paper_orders SET status='cancelled', updated_at=NOW() WHERE id=$1",
                        int(order_id)
                    )
                    await _record_order_event(
                        conn,
                        str(order_id),
                        'cancelled',
                        account_id=row.get('account_id'),
                        code=row.get('code'),
                        payload={'from_status': 'pending'}
                    )
                return ok({'order_id': order_id, 'status': 'cancelled'})

            # --- pending_orders ---
            elif action == 'pending_orders':
                account_id = kwargs.get('account_id')
                if not account_id:
                    account_id = await _ensure_account(user_id, db)
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM paper_orders WHERE account_id=$1 AND status='pending' ORDER BY created_at DESC",
                        account_id
                    )
                return ok({'account_id': account_id, 'orders': [dict(r) for r in rows], 'count': len(rows)})

            # --- positions ---
            elif action in ('get_positions', 'list', 'positions'):
                account_id = kwargs.get('account_id')
                if not account_id:
                    account_id = await _ensure_account(user_id, db)
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM paper_positions WHERE account_id=$1", account_id
                    )
                    positions = []
                    for row in rows:
                        item = dict(row)
                        sellable = await _get_sellable_quantity(conn, account_id, item.get('stock_code'))
                        quantity = int(item.get('quantity') or 0)
                        item['sellable'] = max(0, min(quantity, sellable))
                        positions.append(item)
                return ok({'account_id': account_id, 'positions': positions, 'count': len(positions)})

            # --- orders (trades) ---
            elif action == 'orders':
                account_id = kwargs.get('account_id')
                if not account_id:
                    account_id = await _ensure_account(user_id, db)
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM paper_trades WHERE account_id=$1 ORDER BY created_at DESC LIMIT 50",
                        account_id
                    )
                return ok({'account_id': account_id, 'orders': [dict(r) for r in rows], 'count': len(rows)})

            # --- order_events ---
            elif action == 'order_events':
                order_id = kwargs.get('order_id')
                account_id = kwargs.get('account_id')
                if not account_id:
                    account_id = await _ensure_account(user_id, db)

                try:
                    limit = int(kwargs.get('limit', 100))
                except Exception:
                    limit = 100
                limit = max(1, min(limit, 500))

                async with db.acquire() as conn:
                    if order_id:
                        rows = await conn.fetch(
                            "SELECT * FROM order_events WHERE order_id=$1 ORDER BY created_at DESC LIMIT $2",
                            str(order_id), limit
                        )
                    else:
                        rows = await conn.fetch(
                            "SELECT * FROM order_events WHERE account_id=$1 ORDER BY created_at DESC LIMIT $2",
                            account_id, limit
                        )
                return ok({
                    'order_id': str(order_id) if order_id else None,
                    'account_id': account_id,
                    'events': [dict(r) for r in rows],
                    'count': len(rows),
                })

            # --- summary ---
            elif action == 'summary':
                account_id = kwargs.get('account_id')
                if not account_id:
                    account_id = await _ensure_account(user_id, db)
                async with db.acquire() as conn:
                    account = await conn.fetchrow("SELECT * FROM paper_accounts WHERE id=$1", account_id)
                    if not account:
                        return fail('账户不存在')
                    positions = await conn.fetch(
                        "SELECT * FROM paper_positions WHERE account_id=$1", account_id
                    )
                    pending = await conn.fetchval(
                        "SELECT COUNT(*) FROM paper_orders WHERE account_id=$1 AND status='pending'", account_id
                    )
                acct = dict(account)
                initial = float(acct.get('initial_capital') or 0)
                total = float(acct.get('total_value') or 0)
                return ok({
                    'account_id': account_id,
                    'account': acct,
                    'positions_count': len(positions),
                    'pending_orders_count': int(pending or 0),
                    'total_value': total,
                    'total_return_pct': round((total - initial) / initial * 100, 2) if initial > 0 else 0,
                })

            # --- list_accounts ---
            elif action in ('list_accounts', 'accounts'):
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM paper_accounts WHERE user_id=$1 ORDER BY created_at", user_id
                    )
                return ok({'accounts': [dict(r) for r in rows], 'count': len(rows)})

            # --- update_prices ---
            elif action == 'update_prices':
                account_id = kwargs.get('account_id')
                if not account_id:
                    account_id = await _ensure_account(user_id, db)
                positions = await _refresh_account_prices(db, account_id)
                async with db.acquire() as conn:
                    enriched_positions = []
                    for row in positions:
                        item = dict(row)
                        sellable = await _get_sellable_quantity(conn, account_id, item.get('stock_code'))
                        quantity = int(item.get('quantity') or 0)
                        item['sellable'] = max(0, min(quantity, sellable))
                        enriched_positions.append(item)
                    account = await conn.fetchrow("SELECT * FROM paper_accounts WHERE id=$1", account_id)
                return ok({
                    'account_id': account_id,
                    'positions': enriched_positions,
                    'count': len(enriched_positions),
                    'account': dict(account) if account else None,
                })

            # --- nav_history ---
            elif action == 'nav_history':
                account_id = kwargs.get('account_id')
                if not account_id:
                    account_id = await _ensure_account(user_id, db)
                limit = int(kwargs.get('limit', 90))
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM paper_nav WHERE account_id=$1 ORDER BY nav_date DESC LIMIT $2",
                        account_id, limit
                    )
                return ok({'account_id': account_id, 'nav': [dict(r) for r in reversed(list(rows))]})

            # --- set_risk_rules ---
            elif action == 'set_risk_rules':
                account_id = kwargs.get('account_id')
                if not account_id:
                    account_id = await _ensure_account(user_id, db)
                rules = {
                    'max_position_pct': float(kwargs.get('max_position_pct', DEFAULT_RISK_RULES['max_position_pct'])),
                    'max_drawdown_pct': float(kwargs.get('max_drawdown_pct', DEFAULT_RISK_RULES['max_drawdown_pct'])),
                    'stop_loss_pct': float(kwargs.get('stop_loss_pct', DEFAULT_RISK_RULES['stop_loss_pct'])),
                }
                async with db.acquire() as conn:
                    await conn.execute(
                        "UPDATE paper_accounts SET risk_rules=$1::jsonb, updated_at=NOW() WHERE id=$2",
                        json.dumps(rules), account_id
                    )
                return ok({'account_id': account_id, 'risk_rules': rules})

            # --- matching_status ---
            elif action == 'matching_status':
                try:
                    from ...services.matching_engine import get_matching_engine
                    engine = get_matching_engine()
                    return ok(engine.status())
                except Exception as e:
                    return ok({'running': False, 'error': str(e)})

            # --- nav_status ---
            elif action == 'nav_status':
                try:
                    from ...services.nav_engine import get_nav_engine
                    engine = get_nav_engine()
                    return ok(engine.status())
                except Exception as e:
                    return ok({'running': False, 'error': str(e)})

            else:
                return fail(f'Unknown action: {action}. Supported: {", ".join(SUPPORTED_ACTIONS.keys())}')
        except Exception as e:
            logger.error("[PaperTrading] %s error: %s", action, e, exc_info=True)
            return fail(str(e))


