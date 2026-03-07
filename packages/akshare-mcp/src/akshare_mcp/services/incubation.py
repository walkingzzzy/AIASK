"""策略模拟盘孵化：账户绑定、信号下发、指标沉淀。"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

DEFAULT_INCUBATION_CAPITAL = 100000.0
DEFAULT_INCUBATION_RULES = {
    'max_position_pct': 25.0,
    'max_drawdown_pct': 18.0,
    'stop_loss_pct': 8.0,
}


class StrategyIncubationService:
    async def _get_strategy_account(self, db, strategy_id: str) -> Optional[dict]:
        if hasattr(db, 'get_paper_account_by_strategy'):
            return await db.get_paper_account_by_strategy(strategy_id)
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM paper_accounts WHERE strategy_id=$1 ORDER BY created_at LIMIT 1",
                strategy_id,
            )
        return dict(row) if row else None

    async def _save_strategy_account(self, db, account: dict) -> dict:
        if hasattr(db, 'save_paper_account'):
            return await db.save_paper_account(account)
        async with db.acquire() as conn:
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
                __import__('json').dumps(account.get('risk_rules') or DEFAULT_INCUBATION_RULES),
                account.get('strategy_id'),
                account.get('account_type') or 'incubation',
                account.get('incubation_stage') or 'warmup',
                bool(account.get('promotion_candidate')),
                account.get('status') or 'active',
            )
        return dict(row)

    async def _record_domain_event(self, db, strategy_id: Optional[str], event_type: str, payload: dict, *, source: str = 'incubation', severity: str = 'info', correlation_id: Optional[str] = None):
        if hasattr(db, 'save_strategy_domain_event'):
            await db.save_strategy_domain_event({
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
        binding = await db.get_strategy_incubation_account(strategy_id) if hasattr(db, 'get_strategy_incubation_account') else None
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

    async def sync_signals_to_orders(self, db, strategy: dict, signal_date: date) -> dict:
        ensure = await self.ensure_account(db, strategy)
        account = ensure['account']
        account_id = account['id']
        signals = await db.get_signals(strategy['id'], start_date=signal_date, end_date=signal_date, limit=200)
        if hasattr(db, 'list_strategy_paper_orders'):
            existing_orders = await db.list_strategy_paper_orders(strategy['id'], signal_date)
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
                shares = 100
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
            if hasattr(db, 'save_paper_order'):
                created.append(await db.save_paper_order(order))
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

    async def record_metrics(self, db, strategy: dict, metric_date: Optional[date] = None) -> Optional[dict]:
        metric_date = metric_date or date.today()
        binding = await self.ensure_account(db, strategy)
        account = binding['account']
        account_id = account['id']

        if hasattr(db, 'get_paper_nav_rows'):
            nav_rows = await db.get_paper_nav_rows(account_id, limit=60)
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
        if len(returns) >= 2:
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

        from ..tools.managers.strategy_manager import _build_incubation_overview
        overview = await _build_incubation_overview(db, strategy)
        decision = 'promote' if overview.get('promotion_ready') else ('observe' if not overview.get('deprecation_risk') else 'halt')

        metric = await db.save_strategy_incubation_metric(strategy['id'], metric_date, {
            'account_id': account_id,
            'stage': 'candidate' if overview.get('promotion_ready') else 'warmup',
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
        if hasattr(db, 'update_paper_account_status'):
            await db.update_paper_account_status(
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
        metrics_recorded = 0
        items = []
        for strategy in strategies:
            try:
                ensure = await self.ensure_account(db, strategy)
                accounts_bound += 1 if ensure.get('created') else 0
                sync_result = await self.sync_signals_to_orders(db, strategy, signal_date)
                metric = await self.record_metrics(db, strategy, signal_date)
                orders_created += int(sync_result.get('created_count') or 0)
                metrics_recorded += 1 if metric else 0
                items.append({
                    'strategy_id': strategy.get('id'),
                    'account_id': (ensure.get('account') or {}).get('id'),
                    'orders_created': sync_result.get('created_count', 0),
                    'decision': (metric or {}).get('decision'),
                })
            except Exception as exc:
                logger.warning('StrategyIncubationService.process_strategies failed for %s: %s', strategy.get('id'), exc)
                items.append({'strategy_id': strategy.get('id'), 'error': str(exc)})
        return {
            'count': len(strategies),
            'accounts_bound': accounts_bound,
            'orders_created': orders_created,
            'metrics_recorded': metrics_recorded,
            'items': items,
        }


_incubation_service: Optional[StrategyIncubationService] = None


def get_strategy_incubation_service() -> StrategyIncubationService:
    global _incubation_service
    if _incubation_service is None:
        _incubation_service = StrategyIncubationService()
    return _incubation_service
