"""策略模拟盘孵化：账户绑定、信号下发、指标沉淀。"""

from __future__ import annotations

import inspect
import json
import logging
from datetime import date, datetime, timezone
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


def _safe_rules_dict(value) -> dict:
    """将 risk_rules 字段安全地转换为 dict，防止反复 json.dumps 造成多层嵌套。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}

DEFAULT_INCUBATION_CAPITAL = 100000.0
DEFAULT_INCUBATION_RULES = {
    'max_position_pct': 25.0,
    'max_drawdown_pct': 18.0,
    'stop_loss_pct': 8.0,
}


def _get_async_db_method(db, name: str):
    """Only treat explicitly provided async methods as adapter overrides.

    ``MagicMock``/``Mock`` synthesizes arbitrary attributes on access, so
    ``hasattr`` is too permissive here and can leak un-awaited child mocks
    into fallback branches during tests.
    """
    method = getattr(db, name, None)
    if method is None or not callable(method):
        return None
    if inspect.iscoroutinefunction(method):
        return method
    if hasattr(method, "await_count"):
        return method
    return None


def _get_db_acquire(db):
    """Return a real acquire() hook, not a lazily synthesized mock child."""
    acquire = getattr(db, "acquire", None)
    if not callable(acquire):
        return None

    raw = getattr(db, "raw", None)
    target = getattr(raw, "acquire", None) if raw is not None else acquire
    if target is None or not callable(target):
        return None
    if type(target).__module__.startswith("unittest.mock"):
        return None
    return acquire


class StrategyIncubationService:
    async def _get_strategy_account(self, db, strategy_id: str) -> Optional[dict]:
        method = _get_async_db_method(db, 'get_paper_account_by_strategy')
        if method is not None:
            return await method(strategy_id)
        acquire = _get_db_acquire(db)
        if acquire is None:
            return None
        async with acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM paper_accounts WHERE strategy_id=$1 ORDER BY created_at LIMIT 1",
                strategy_id,
            )
        return dict(row) if row else None

    async def _save_strategy_account(self, db, account: dict) -> dict:
        method = _get_async_db_method(db, 'save_paper_account')
        if method is not None:
            return await method(account)
        acquire = _get_db_acquire(db)
        if acquire is None:
            return dict(account)
        async with acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_accounts
                    (id, user_id, name, initial_capital, current_capital, total_value, risk_rules,
                     strategy_id, account_type, incubation_stage, promotion_candidate, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11, $12, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    risk_rules = EXCLUDED.risk_rules,
                    strategy_id = EXCLUDED.strategy_id,
                    account_type = EXCLUDED.account_type,
                    incubation_stage = EXCLUDED.incubation_stage,
                    promotion_candidate = EXCLUDED.promotion_candidate,
                    status = EXCLUDED.status,
                    total_value = EXCLUDED.total_value,
                    current_capital = EXCLUDED.current_capital
                RETURNING *
                """,
                account['id'],
                account.get('user_id') or 'strategy_factory',
                account['name'],
                float(account.get('initial_capital') or DEFAULT_INCUBATION_CAPITAL),
                float(account.get('current_capital') or DEFAULT_INCUBATION_CAPITAL),
                float(account.get('total_value') or DEFAULT_INCUBATION_CAPITAL),
                json.dumps(_safe_rules_dict(account.get('risk_rules')) or DEFAULT_INCUBATION_RULES),
                account.get('strategy_id'),
                account.get('account_type') or 'incubation',
                account.get('incubation_stage') or 'warmup',
                bool(account.get('promotion_candidate')),
                account.get('status') or 'active',
            )
        return dict(row)

    async def _record_domain_event(self, db, strategy_id: Optional[str], event_type: str, payload: dict, *, source: str = 'incubation', severity: str = 'info', correlation_id: Optional[str] = None):
        method = _get_async_db_method(db, 'save_strategy_domain_event')
        if method is not None:
            await method({
                'strategy_id': strategy_id,
                'aggregate_type': 'strategy',
                'aggregate_id': strategy_id,
                'event_type': event_type,
                'source': source,
                'severity': severity,
                'correlation_id': correlation_id,
                'payload': payload,
            })

    async def ensure_account(self, db, strategy: dict, stage: str = 'warmup', source_run_id: Optional[str] = None) -> dict:
        strategy_id = strategy['id']
        binding_method = _get_async_db_method(db, 'get_strategy_incubation_account')
        binding = await binding_method(strategy_id) if binding_method is not None else None
        account = None
        created = False
        if binding:
            account = await self._get_strategy_account(db, strategy_id)
        if not account:
            account = await self._get_strategy_account(db, strategy_id)
        if not account:
            account = await self._save_strategy_account(db, {
                'id': f'inc_{uuid4().hex[:8]}',
                'user_id': 'strategy_factory',
                'name': f"孵化_{str(strategy.get('name') or strategy_id)[:24]}",
                'initial_capital': DEFAULT_INCUBATION_CAPITAL,
                'current_capital': DEFAULT_INCUBATION_CAPITAL,
                'total_value': DEFAULT_INCUBATION_CAPITAL,
                'risk_rules': DEFAULT_INCUBATION_RULES,
                'strategy_id': strategy_id,
                'account_type': 'incubation',
                'incubation_stage': stage,
                'promotion_candidate': False,
                'status': 'active',
            })
            created = True

        bind = await db.save_strategy_incubation_account(
            strategy_id,
            account['id'],
            stage=stage,
            status='active',
            source_run_id=source_run_id,
            metadata={
                'strategy_name': strategy.get('name'),
                'strategy_type': strategy.get('strategy_type'),
            },
        )
        await self._record_domain_event(
            db,
            strategy_id,
            'incubation.account_bound',
            {
                'account_id': account['id'],
                'stage': stage,
                'created': created,
                'source_run_id': source_run_id,
            },
            correlation_id=source_run_id,
        )
        return {'created': created, 'account': account, 'binding': bind}

    async def _latest_price(self, db, code: str) -> Optional[float]:
        try:
            klines = await db.get_klines(code, limit=1)
            if klines:
                return float(klines[-1].get('close') or 0) or None
        except Exception:
            return None
        return None

    async def _list_positions(self, db, account_id: str) -> list[dict]:
        method = _get_async_db_method(db, 'list_paper_positions')
        if method is not None:
            return await method(account_id)
        async with db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM paper_positions WHERE account_id = $1 ORDER BY stock_code",
                account_id,
            )
        return [dict(row) for row in rows]

    async def _save_position(self, db, position: dict) -> dict:
        method = _get_async_db_method(db, 'save_paper_position')
        if method is not None:
            return await method(position)
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_positions
                    (account_id, stock_code, stock_name, quantity, cost_price, current_price, market_value, profit_rate, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
                ON CONFLICT (account_id, stock_code) DO UPDATE SET
                    stock_name = EXCLUDED.stock_name,
                    quantity = EXCLUDED.quantity,
                    cost_price = EXCLUDED.cost_price,
                    current_price = EXCLUDED.current_price,
                    market_value = EXCLUDED.market_value,
                    profit_rate = EXCLUDED.profit_rate,
                    updated_at = NOW()
                RETURNING *
                """,
                position.get('account_id'),
                position.get('stock_code'),
                position.get('stock_name') or position.get('stock_code') or '',
                int(position.get('quantity') or 0),
                float(position.get('cost_price') or 0.0),
                position.get('current_price'),
                position.get('market_value'),
                position.get('profit_rate'),
            )
        return dict(row)

    async def _save_trade(self, db, trade: dict) -> dict:
        method = _get_async_db_method(db, 'save_paper_trade')
        if method is not None:
            return await method(trade)
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_trades
                    (id, account_id, stock_code, stock_name, trade_type, price, quantity, amount, commission, trade_time, reason, strategy_id, source_order_id, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
                RETURNING *
                """,
                trade.get('id'),
                trade.get('account_id'),
                trade.get('stock_code'),
                trade.get('stock_name') or trade.get('stock_code') or '',
                trade.get('trade_type'),
                float(trade.get('price') or 0.0),
                int(trade.get('quantity') or 0),
                float(trade.get('amount') or 0.0),
                float(trade.get('commission') or 0.0),
                trade.get('trade_time'),
                trade.get('reason'),
                trade.get('strategy_id'),
                trade.get('source_order_id'),
            )
        return dict(row)

    async def _update_order(self, db, order_id: int, updates: dict) -> Optional[dict]:
        method = _get_async_db_method(db, 'update_paper_order')
        if method is not None:
            return await method(order_id, updates)
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE paper_orders
                SET price = COALESCE($2, price),
                    shares = COALESCE($3, shares),
                    status = COALESCE($4, status),
                    commission = COALESCE($5, commission),
                    reason = COALESCE($6, reason),
                    filled_at = COALESCE($7, filled_at),
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                int(order_id),
                updates.get('price'),
                updates.get('shares'),
                updates.get('status'),
                updates.get('commission'),
                updates.get('reason'),
                updates.get('filled_at'),
            )
        return dict(row) if row else None

    async def _save_nav_snapshot(self, db, account: dict, nav_date: date, cash: float, market_value: float) -> dict:
        account_id = account['id']
        total_value = round(cash + market_value, 4)
        nav_rows_method = _get_async_db_method(db, 'get_paper_nav_rows')
        rows = await nav_rows_method(account_id, limit=2) if nav_rows_method is not None else []
        prev = next((row for row in rows if str(row.get('nav_date')) != str(nav_date)), None)
        prev_total = float((prev or {}).get('total_value') or account.get('initial_capital') or total_value or DEFAULT_INCUBATION_CAPITAL)
        daily_return = ((total_value - prev_total) / prev_total) if prev_total > 0 else 0.0
        snapshot = {
            'account_id': account_id,
            'nav_date': nav_date,
            'total_value': total_value,
            'cash': round(cash, 4),
            'market_value': round(market_value, 4),
            'daily_return': round(daily_return, 6),
        }
        save_nav_method = _get_async_db_method(db, 'save_paper_nav')
        if save_nav_method is not None:
            await save_nav_method(snapshot)
        else:
            async with db.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO paper_nav (account_id, nav_date, total_value, cash, market_value, daily_return, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, NOW())
                    ON CONFLICT (account_id, nav_date) DO UPDATE
                    SET total_value=$3, cash=$4, market_value=$5, daily_return=$6
                    """,
                    snapshot['account_id'], snapshot['nav_date'], snapshot['total_value'], snapshot['cash'], snapshot['market_value'], snapshot['daily_return'],
                )
        updated_account = await self._save_strategy_account(db, {
            **account,
            'current_capital': round(cash, 4),
            'total_value': total_value,
        })
        return {'snapshot': snapshot, 'account': updated_account}

    async def settle_orders(self, db, strategy: dict, signal_date: Optional[date] = None) -> dict:
        signal_date = signal_date or date.today()
        ensure = await self.ensure_account(db, strategy)
        account = ensure['account']
        account_id = account['id']
        list_orders_method = _get_async_db_method(db, 'list_strategy_paper_orders')
        orders = await list_orders_method(strategy['id'], signal_date) if list_orders_method is not None else []
        executable = [item for item in orders if str(item.get('status') or 'pending') in {'pending', 'submitted'}]
        positions = {str(item.get('stock_code') or ''): dict(item) for item in await self._list_positions(db, account_id)}
        cash = float(account.get('current_capital') or account.get('initial_capital') or DEFAULT_INCUBATION_CAPITAL)
        filled = []
        rejected = []
        now = datetime.now(timezone.utc)

        for order in executable:
            code = str(order.get('code') or '').strip()
            direction = str(order.get('direction') or '').strip().lower()
            shares = int(order.get('shares') or 0)
            if not code or shares <= 0 or direction not in {'buy', 'sell'}:
                rejected.append(await self._update_order(db, order['id'], {'status': 'rejected', 'reason': 'invalid_order'}))
                continue
            exec_price = await self._latest_price(db, code) or float(order.get('price') or 0)
            if exec_price <= 0:
                rejected.append(await self._update_order(db, order['id'], {'status': 'rejected', 'reason': 'price_unavailable'}))
                continue
            commission = round(exec_price * shares * 0.0003, 4)
            position = dict(positions.get(code) or {})
            current_qty = int(position.get('quantity') or 0)
            if direction == 'buy':
                amount = round(exec_price * shares, 4)
                total_cost = amount + commission
                if cash + 1e-9 < total_cost:
                    rejected.append(await self._update_order(db, order['id'], {'status': 'rejected', 'reason': 'insufficient_cash', 'price': round(exec_price, 4), 'commission': commission}))
                    continue
                cash = round(cash - total_cost, 4)
                new_qty = current_qty + shares
                avg_cost = float(position.get('cost_price') or 0.0)
                new_cost = ((avg_cost * current_qty) + amount) / max(new_qty, 1)
                latest_price = await self._latest_price(db, code) or exec_price
                market_value = round(latest_price * new_qty, 4)
                positions[code] = await self._save_position(db, {
                    'account_id': account_id,
                    'stock_code': code,
                    'stock_name': position.get('stock_name') or code,
                    'quantity': new_qty,
                    'cost_price': round(new_cost, 6),
                    'current_price': round(latest_price, 4),
                    'market_value': market_value,
                    'profit_rate': round(((latest_price - new_cost) / new_cost), 6) if new_cost > 0 else 0.0,
                })
            else:
                if current_qty < shares:
                    rejected.append(await self._update_order(db, order['id'], {'status': 'rejected', 'reason': 'insufficient_position', 'price': round(exec_price, 4)}))
                    continue
                amount = round(exec_price * shares, 4)
                cash = round(cash + amount - commission, 4)
                new_qty = current_qty - shares
                avg_cost = float(position.get('cost_price') or 0.0)
                latest_price = await self._latest_price(db, code) or exec_price
                market_value = round(latest_price * new_qty, 4)
                positions[code] = await self._save_position(db, {
                    'account_id': account_id,
                    'stock_code': code,
                    'stock_name': position.get('stock_name') or code,
                    'quantity': new_qty,
                    'cost_price': round(avg_cost, 6),
                    'current_price': round(latest_price, 4),
                    'market_value': market_value,
                    'profit_rate': round(((latest_price - avg_cost) / avg_cost), 6) if avg_cost > 0 else 0.0,
                })
            trade = await self._save_trade(db, {
                'id': f"ptr_{uuid4().hex[:10]}",
                'account_id': account_id,
                'stock_code': code,
                'stock_name': (positions.get(code) or {}).get('stock_name') or code,
                'trade_type': direction,
                'price': round(exec_price, 4),
                'quantity': shares,
                'amount': amount,
                'commission': commission,
                'trade_time': now,
                'reason': order.get('reason') or order.get('source') or 'strategy_signal',
                'strategy_id': strategy['id'],
                'source_order_id': str(order.get('id')),
            })
            updated_order = await self._update_order(db, order['id'], {
                'status': 'filled',
                'price': round(exec_price, 4),
                'commission': commission,
                'filled_at': now,
            })
            filled.append({'order': updated_order, 'trade': trade})

        market_value = 0.0
        for code, position in list(positions.items()):
            qty = int(position.get('quantity') or 0)
            if qty <= 0:
                continue
            latest_price = await self._latest_price(db, code) or float(position.get('current_price') or position.get('cost_price') or 0.0)
            avg_cost = float(position.get('cost_price') or 0.0)
            market_value += latest_price * qty
            positions[code] = await self._save_position(db, {
                **position,
                'account_id': account_id,
                'stock_code': code,
                'current_price': round(latest_price, 4),
                'market_value': round(latest_price * qty, 4),
                'profit_rate': round(((latest_price - avg_cost) / avg_cost), 6) if avg_cost > 0 else 0.0,
            })

        nav_result = await self._save_nav_snapshot(db, account, signal_date, cash, market_value)
        if filled or rejected:
            await self._record_domain_event(
                db,
                strategy['id'],
                'incubation.orders_settled',
                {
                    'account_id': account_id,
                    'signal_date': str(signal_date),
                    'filled_count': len(filled),
                    'rejected_count': len([item for item in rejected if item]),
                    'nav': nav_result['snapshot'],
                },
                correlation_id=str(signal_date),
                severity='warning' if rejected else 'info',
            )
        await self._record_domain_event(
            db,
            strategy['id'],
            'incubation.nav_recorded',
            {
                'account_id': account_id,
                'signal_date': str(signal_date),
                'nav': nav_result['snapshot'],
            },
            correlation_id=str(signal_date),
        )
        return {
            'strategy_id': strategy['id'],
            'account_id': account_id,
            'filled_count': len(filled),
            'rejected_count': len([item for item in rejected if item]),
            'nav_snapshot': nav_result['snapshot'],
            'cash': nav_result['snapshot']['cash'],
            'market_value': nav_result['snapshot']['market_value'],
        }

    async def sync_signals_to_orders(self, db, strategy: dict, signal_date: date) -> dict:
        ensure = await self.ensure_account(db, strategy)
        account = ensure['account']
        account_id = account['id']
        signals = await db.get_signals(strategy['id'], start_date=signal_date, end_date=signal_date, limit=200)
        list_orders_method = _get_async_db_method(db, 'list_strategy_paper_orders')
        if list_orders_method is not None:
            existing_orders = await list_orders_method(strategy['id'], signal_date)
        else:
            async with db.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM paper_orders WHERE strategy_id=$1 AND signal_date=$2",
                    strategy['id'], signal_date,
                )
            existing_orders = [dict(row) for row in rows]
        existing_keys = {(row.get('code'), row.get('direction')) for row in existing_orders}
        created = []
        skipped = 0

        current_capital = float(account.get('current_capital') or account.get('initial_capital') or DEFAULT_INCUBATION_CAPITAL)
        budget_per_trade = max(current_capital * 0.12, 5000.0)

        for signal in signals:
            code = str(signal.get('code') or '').strip()
            latest_signal = int(signal.get('signal') or 0)
            if not code or latest_signal == 0:
                continue
            direction = 'buy' if latest_signal > 0 else 'sell'
            if (code, direction) in existing_keys:
                skipped += 1
                continue
            price = await self._latest_price(db, code)
            if price is None or price <= 0:
                skipped += 1
                continue
            if direction == 'buy':
                shares = int(budget_per_trade / price / 100) * 100
                if shares < 100:
                    skipped += 1
                    continue
            else:
                # Fix #8: 卖出时使用实际持仓数量，而非硬编码 100 股
                position_shares = 0
                positions_method = _get_async_db_method(db, 'get_paper_positions')
                if positions_method is not None:
                    positions = await positions_method(account_id)
                    for pos in (positions or []):
                        if str(pos.get('code') or '') == str(code):
                            position_shares = int(pos.get('shares') or 0)
                            break
                shares = position_shares if position_shares > 0 else 100
            order = {
                'account_id': account_id,
                'strategy_id': strategy['id'],
                'signal_date': signal_date,
                'source': 'strategy_signal',
                'code': code,
                'direction': direction,
                'shares': shares,
                'price': round(float(price), 4),
                'order_type': 'limit',
                'status': 'pending',
            }
            save_order_method = _get_async_db_method(db, 'save_paper_order')
            if save_order_method is not None:
                created.append(await save_order_method(order))
            else:
                async with db.acquire() as conn:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO paper_orders
                            (account_id, strategy_id, signal_date, source, code, direction, shares, price, order_type, status, created_at, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NOW())
                        RETURNING *
                        """,
                        account_id,
                        strategy['id'],
                        signal_date,
                        'strategy_signal',
                        code,
                        direction,
                        shares,
                        round(float(price), 4),
                        'limit',
                        'pending',
                    )
                created.append(dict(row))
            existing_keys.add((code, direction))

        if created or skipped:
            await self._record_domain_event(
                db,
                strategy['id'],
                'incubation.orders_synced',
                {
                    'account_id': account_id,
                    'signal_date': str(signal_date),
                    'created_count': len(created),
                    'skipped_count': skipped,
                    'codes': [item.get('code') for item in created if item.get('code')],
                },
                correlation_id=str(signal_date),
            )

        return {
            'strategy_id': strategy['id'],
            'account_id': account_id,
            'created_count': len(created),
            'skipped_count': skipped,
            'orders': created,
        }

    # Fix #12: 6 阶段孵化映射
    @staticmethod
    def _derive_incubation_stage(overview: dict, nav_days: int) -> str:
        """根据孵化概览和交易天数推导当前阶段。

        6 stages: warmup → observe → candidate → graduation_ready → promoted / failed
        """
        if overview.get('promotion_ready'):
            return 'graduation_ready'
        if overview.get('deprecation_risk'):
            return 'failed'

        blockers = overview.get('blockers') or []
        risk_flags = overview.get('risk_flags') or []

        # warmup: 交易天数不足或有严重阻塞项
        if nav_days < 5 or any('min_' in str(b) for b in blockers):
            return 'warmup'

        # candidate: 无阻塞项且交易天数充足
        if not blockers and not risk_flags and nav_days >= 15:
            return 'candidate'

        # observe: 中间状态
        return 'observe'

    async def record_metrics(self, db, strategy: dict, metric_date: Optional[date] = None) -> Optional[dict]:
        metric_date = metric_date or date.today()
        binding = await self.ensure_account(db, strategy)
        account = binding['account']
        account_id = account['id']

        nav_rows_method = _get_async_db_method(db, 'get_paper_nav_rows')
        if nav_rows_method is not None:
            nav_rows = await nav_rows_method(account_id, limit=60)
            order_summary = await db.get_paper_order_summary(account_id)
        else:
            async with db.acquire() as conn:
                nav_rows = [dict(row) for row in await conn.fetch(
                    "SELECT * FROM paper_nav WHERE account_id=$1 ORDER BY nav_date DESC LIMIT 60",
                    account_id,
                )]
                summary = await conn.fetchrow(
                    """
                    SELECT
                        COALESCE(COUNT(*) FILTER (WHERE status IN ('pending','submitted')), 0)::int AS total_orders,
                        COALESCE(COUNT(*) FILTER (WHERE status = 'filled'), 0)::int AS filled_orders
                    FROM paper_orders
                    WHERE account_id=$1
                    """,
                    account_id,
                )
                trade_summary = await conn.fetchrow(
                    "SELECT COALESCE(COUNT(*), 0)::int AS total_trades, COALESCE(SUM(amount), 0)::float AS trade_amount FROM paper_trades WHERE account_id=$1",
                    account_id,
                )
                order_summary = {
                    'total_orders': int((summary or {}).get('total_orders') or 0),
                    'total_trades': int((trade_summary or {}).get('total_trades') or 0),
                    'trade_amount': float((trade_summary or {}).get('trade_amount') or 0.0),
                }

        latest_nav = nav_rows[0] if nav_rows else None
        total_value = float((latest_nav or {}).get('total_value') or account.get('total_value') or account.get('initial_capital') or DEFAULT_INCUBATION_CAPITAL)
        cash = float((latest_nav or {}).get('cash') or account.get('current_capital') or 0.0)
        market_value = float((latest_nav or {}).get('market_value') or max(total_value - cash, 0.0))
        daily_return = float((latest_nav or {}).get('daily_return') or 0.0)

        nav_values = [float(row.get('total_value') or 0) for row in reversed(nav_rows)]
        peak = nav_values[0] if nav_values else total_value
        max_drawdown = 0.0
        for value in nav_values:
            peak = max(peak, value)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - value) / peak)

        returns = [float(row.get('daily_return') or 0) for row in nav_rows if row.get('daily_return') is not None]
        # Fix #9: 至少需要 20 个数据点才能计算有统计意义的 Sharpe
        if len(returns) >= 20:
            mean_r = sum(returns) / len(returns)
            variance = sum((item - mean_r) ** 2 for item in returns) / max(len(returns) - 1, 1)
            std_r = variance ** 0.5
            sharpe_ratio = (mean_r / std_r) * (252 ** 0.5) if std_r > 0 else 0.0
        else:
            sharpe_ratio = 0.0

        signal_stats = await db.get_signal_stats(strategy['id'])
        hit_rate_5d = float((signal_stats.get('hit_rate') or {}).get(5, (signal_stats.get('hit_rate') or {}).get('5', 0)) or 0)
        forward_ic_5d = float((signal_stats.get('forward_ic') or {}).get(5, (signal_stats.get('forward_ic') or {}).get('5', 0)) or 0)
        forward_sharpe_5d = float((signal_stats.get('forward_sharpe') or {}).get(5, (signal_stats.get('forward_sharpe') or {}).get('5', 0)) or 0)
        total_signals = int(signal_stats.get('total_signals') or 0)

        metrics = await db.get_strategy_metrics(strategy['id'])
        backtest = next((item for item in metrics if item.get('period') in ('all', 'backtest')), {})
        baseline_sharpe = float(backtest.get('sharpe_ratio') or 0)
        baseline_mdd = abs(float(backtest.get('max_drawdown') or 0))
        alpha_decay = max(0.0, baseline_sharpe - max(forward_sharpe_5d, 0.0))
        drift_score = (abs(max_drawdown - baseline_mdd) + abs(baseline_sharpe - forward_sharpe_5d)) / 2 if baseline_sharpe or baseline_mdd else 0.0
        exposure_rate = (market_value / total_value) if total_value > 0 else 0.0
        turnover_rate = float(order_summary.get('trade_amount') or 0.0) / total_value if total_value > 0 else 0.0

        from .strategy_lifecycle_shared import build_incubation_overview as _build_incubation_overview
        overview = await _build_incubation_overview(db, strategy)
        decision = 'promote' if overview.get('promotion_ready') else ('observe' if not overview.get('deprecation_risk') else 'halt')

        metric = await db.save_strategy_incubation_metric(strategy['id'], metric_date, {
            'account_id': account_id,
            # Fix #12: 使用完整的 6 阶段映射替代二元分类
            'stage': self._derive_incubation_stage(overview, len(nav_rows)),
            'total_value': round(total_value, 4),
            'cash': round(cash, 4),
            'market_value': round(market_value, 4),
            'nav': round(total_value / max(float(account.get('initial_capital') or DEFAULT_INCUBATION_CAPITAL), 1.0), 6),
            'daily_return': round(daily_return, 6),
            'max_drawdown': round(max_drawdown, 6),
            'sharpe_ratio': round(sharpe_ratio, 6),
            'hit_rate_5d': round(hit_rate_5d, 6),
            'forward_ic_5d': round(forward_ic_5d, 6),
            'forward_sharpe_5d': round(forward_sharpe_5d, 6),
            'total_signals': total_signals,
            'total_orders': int(order_summary.get('total_orders') or 0),
            'total_trades': int(order_summary.get('total_trades') or 0),
            'turnover_rate': round(turnover_rate, 6),
            'exposure_rate': round(exposure_rate, 6),
            'alpha_decay': round(alpha_decay, 6),
            'drift_score': round(drift_score, 6),
            'blockers': overview.get('blockers') or [],
            'risk_flags': overview.get('risk_flags') or [],
            'decision': decision,
            'metadata': {
                'overview': overview,
                'binding_created': bool(binding.get('created')),
            },
        })
        update_account_status_method = _get_async_db_method(db, 'update_paper_account_status')
        if update_account_status_method is not None:
            await update_account_status_method(
                account_id,
                'active',
                stage=metric.get('stage') or 'warmup',
                promotion_candidate=bool(overview.get('promotion_ready')),
            )
        await self._record_domain_event(
            db,
            strategy['id'],
            'incubation.metric_recorded',
            {
                'account_id': account_id,
                'metric_date': str(metric_date),
                'decision': metric.get('decision'),
                'stage': metric.get('stage'),
                'nav': metric.get('nav'),
                'promotion_candidate': bool(overview.get('promotion_ready')),
            },
            correlation_id=str(metric_date),
        )
        return metric

    async def process_strategies(self, db, strategies: list[dict], signal_date: Optional[date] = None) -> dict:
        signal_date = signal_date or date.today()
        accounts_bound = 0
        orders_created = 0
        orders_filled = 0
        rejected_orders = 0
        nav_snapshots = 0
        metrics_recorded = 0
        items = []
        for strategy in strategies:
            try:
                ensure = await self.ensure_account(db, strategy)
                accounts_bound += 1 if ensure.get('created') else 0
                sync_result = await self.sync_signals_to_orders(db, strategy, signal_date)
                settle_result = await self.settle_orders(db, strategy, signal_date)
                metric = await self.record_metrics(db, strategy, signal_date)
                orders_created += int(sync_result.get('created_count') or 0)
                orders_filled += int(settle_result.get('filled_count') or 0)
                rejected_orders += int(settle_result.get('rejected_count') or 0)
                nav_snapshots += 1 if settle_result.get('nav_snapshot') else 0
                metrics_recorded += 1 if metric else 0
                items.append({
                    'strategy_id': strategy.get('id'),
                    'account_id': (ensure.get('account') or {}).get('id'),
                    'orders_created': sync_result.get('created_count', 0),
                    'orders_filled': settle_result.get('filled_count', 0),
                    'rejected_orders': settle_result.get('rejected_count', 0),
                    'nav': (settle_result.get('nav_snapshot') or {}).get('total_value'),
                    'decision': (metric or {}).get('decision'),
                })
            except Exception as exc:
                logger.warning('StrategyIncubationService.process_strategies failed for %s: %s', strategy.get('id'), exc)
                items.append({'strategy_id': strategy.get('id'), 'error': str(exc)})
        return {
            'count': len(strategies),
            'accounts_bound': accounts_bound,
            'orders_created': orders_created,
            'orders_filled': orders_filled,
            'rejected_orders': rejected_orders,
            'nav_snapshots': nav_snapshots,
            'metrics_recorded': metrics_recorded,
            'items': items,
        }


_incubation_service: Optional[StrategyIncubationService] = None


def get_strategy_incubation_service() -> StrategyIncubationService:
    global _incubation_service
    if _incubation_service is None:
        _incubation_service = StrategyIncubationService()
    return _incubation_service
