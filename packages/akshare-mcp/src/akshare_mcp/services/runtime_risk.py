"""策略运行时风控：告警、熔断、恢复。"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class StrategyRuntimeRiskService:
    def __init__(self):
        self.critical_drawdown = 0.30
        self.recovery_drawdown = 0.18
        self.daily_loss_limit = -0.08
        self.over_exposure_limit = 0.95
        self.alpha_decay_limit = 0.35
        self.drift_limit = 0.45

    async def _set_account_status(self, db, account_id: str, status: str, promotion_candidate: Optional[bool] = None):
        if hasattr(db, 'update_paper_account_status'):
            await db.update_paper_account_status(account_id, status, promotion_candidate=promotion_candidate)
            return
        async with db.acquire() as conn:
            if promotion_candidate is None:
                await conn.execute(
                    "UPDATE paper_accounts SET status=$1, updated_at=NOW() WHERE id=$2",
                    status,
                    account_id,
                )
            else:
                await conn.execute(
                    "UPDATE paper_accounts SET status=$1, promotion_candidate=$2, updated_at=NOW() WHERE id=$3",
                    status,
                    bool(promotion_candidate),
                    account_id,
                )

    async def _latest_suspend_source(self, db, strategy_id: str) -> Optional[str]:
        if not hasattr(db, 'list_strategy_status_events'):
            return None
        rows = await db.list_strategy_status_events(strategy_id, to_status='suspended', limit=1)
        if not rows:
            return None
        return rows[0].get('from_status') or None

    async def _suspend_strategy(self, db, strategy: dict, metric: dict):
        from ..tools.managers.strategy_manager import _update_status, _validate_transition

        current = str(strategy.get('status') or '')
        if _validate_transition(current, 'suspended'):
            await _update_status(
                db,
                strategy['id'],
                'suspended',
                actor_id='runtime_risk',
                reason='runtime_circuit_breaker',
                metadata={'metric': metric},
            )

    async def _recover_strategy(self, db, strategy: dict, metric: dict):
        from ..tools.managers.strategy_manager import _update_status, _validate_transition

        recover_to = await self._latest_suspend_source(db, strategy['id']) or 'listed'
        current = str(strategy.get('status') or '')
        if _validate_transition(current, recover_to):
            await _update_status(
                db,
                strategy['id'],
                recover_to,
                actor_id='runtime_risk',
                reason='runtime_recovered',
                metadata={'metric': metric},
            )
            return recover_to
        return None

    async def _record_domain_event(self, db, strategy_id: Optional[str], event_type: str, payload: dict, *, source: str = 'runtime_risk', severity: str = 'info', correlation_id: Optional[str] = None):
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

    async def _execute_risk_actions(self, db, strategy_id: str, account_id: Optional[str], trigger: str, metric: dict) -> list[dict]:
        if not account_id:
            return []
        try:
            from .risk_executor import get_risk_executor
            actions = await get_risk_executor().enforce(account_id)
        except Exception as exc:
            logger.warning('StrategyRuntimeRiskService._execute_risk_actions failed for %s/%s: %s', strategy_id, account_id, exc)
            return []
        action_rows = [item.to_dict() for item in actions]
        if action_rows:
            await self._record_domain_event(
                db,
                strategy_id,
                'runtime_risk.actions_executed',
                {
                    'account_id': account_id,
                    'trigger': trigger,
                    'metric': metric,
                    'actions': action_rows,
                },
                severity='warning',
                correlation_id=account_id,
            )
        return action_rows

    async def scan(self, db, strategies: Optional[list[dict]] = None, enforce_actions: bool = True) -> dict:
        if strategies is None:
            strategies = []
            for status in ('incubating', 'listed', 'suspended'):
                rows = await db.list_strategies(status, limit=200)
                strategies.extend(rows)

        emitted = []
        suspended = []
        recovered = []
        action_items = []
        executed_accounts: set[str] = set()

        for strategy in strategies:
            sid = strategy.get('id')
            metric = await db.get_latest_strategy_incubation_metric(sid) if hasattr(db, 'get_latest_strategy_incubation_metric') else None
            if not metric:
                continue
            account = await db.get_strategy_incubation_account(sid) if hasattr(db, 'get_strategy_incubation_account') else None
            account_id = (account or {}).get('account_id')
            open_events = await db.list_strategy_runtime_risk_events(strategy_id=sid, status='open', limit=100) if hasattr(db, 'list_strategy_runtime_risk_events') else []
            open_types = {item.get('event_type') for item in open_events}

            daily_return = float(metric.get('daily_return') or 0)
            max_drawdown = abs(float(metric.get('max_drawdown') or 0))
            exposure_rate = float(metric.get('exposure_rate') or 0)
            alpha_decay = float(metric.get('alpha_decay') or 0)
            drift_score = float(metric.get('drift_score') or 0)

            def needs_emit(event_type: str) -> bool:
                return event_type not in open_types

            if max_drawdown >= self.critical_drawdown and needs_emit('drawdown_breach'):
                event = await db.save_strategy_runtime_risk_event({
                    'strategy_id': sid,
                    'account_id': account_id,
                    'severity': 'critical',
                    'event_type': 'drawdown_breach',
                    'action': 'suspend_strategy',
                    'title': '策略回撤触发熔断',
                    'reason': f'最大回撤 {max_drawdown:.1%} ≥ {self.critical_drawdown:.0%}',
                    'payload': {'metric': metric},
                })
                emitted.append(event)
                if account_id:
                    await self._set_account_status(db, account_id, 'frozen', promotion_candidate=False)
                await self._suspend_strategy(db, strategy, metric)
                suspended.append({'strategy_id': sid, 'reason': event.get('reason')})
                await self._record_domain_event(db, sid, 'runtime_risk.drawdown_breach', {'account_id': account_id, 'reason': event.get('reason'), 'metric': metric}, severity='critical', correlation_id=account_id)
                if enforce_actions and account_id not in executed_accounts:
                    action_items.extend(await self._execute_risk_actions(db, sid, account_id, 'drawdown_breach', metric))
                    executed_accounts.add(account_id)

            if daily_return <= self.daily_loss_limit and needs_emit('daily_loss_spike'):
                emitted.append(await db.save_strategy_runtime_risk_event({
                    'strategy_id': sid,
                    'account_id': account_id,
                    'severity': 'high',
                    'event_type': 'daily_loss_spike',
                    'action': 'freeze_account',
                    'title': '单日大幅亏损',
                    'reason': f'日收益 {daily_return:.1%} ≤ {self.daily_loss_limit:.1%}',
                    'payload': {'metric': metric},
                }))
                if account_id:
                    await self._set_account_status(db, account_id, 'frozen', promotion_candidate=False)
                await self._record_domain_event(db, sid, 'runtime_risk.daily_loss_spike', {'account_id': account_id, 'metric': metric}, severity='warning', correlation_id=account_id)
                if enforce_actions and account_id not in executed_accounts:
                    action_items.extend(await self._execute_risk_actions(db, sid, account_id, 'daily_loss_spike', metric))
                    executed_accounts.add(account_id)

            if exposure_rate >= self.over_exposure_limit and needs_emit('over_exposure'):
                emitted.append(await db.save_strategy_runtime_risk_event({
                    'strategy_id': sid,
                    'account_id': account_id,
                    'severity': 'medium',
                    'event_type': 'over_exposure',
                    'action': 'reduce_position',
                    'title': '仓位暴露过高',
                    'reason': f'暴露率 {exposure_rate:.1%} ≥ {self.over_exposure_limit:.0%}',
                    'payload': {'metric': metric},
                }))
                await self._record_domain_event(db, sid, 'runtime_risk.over_exposure', {'account_id': account_id, 'metric': metric}, severity='warning', correlation_id=account_id)
                if enforce_actions and account_id not in executed_accounts:
                    action_items.extend(await self._execute_risk_actions(db, sid, account_id, 'over_exposure', metric))
                    executed_accounts.add(account_id)

            if alpha_decay >= self.alpha_decay_limit and needs_emit('alpha_decay'):
                emitted.append(await db.save_strategy_runtime_risk_event({
                    'strategy_id': sid,
                    'account_id': account_id,
                    'severity': 'medium',
                    'event_type': 'alpha_decay',
                    'action': 'review_required',
                    'title': 'Alpha 衰减告警',
                    'reason': f'alpha_decay {alpha_decay:.2f} ≥ {self.alpha_decay_limit:.2f}',
                    'payload': {'metric': metric},
                }))
                await self._record_domain_event(db, sid, 'runtime_risk.alpha_decay', {'account_id': account_id, 'metric': metric}, severity='info', correlation_id=account_id)

            if drift_score >= self.drift_limit and needs_emit('behavior_drift'):
                emitted.append(await db.save_strategy_runtime_risk_event({
                    'strategy_id': sid,
                    'account_id': account_id,
                    'severity': 'medium',
                    'event_type': 'behavior_drift',
                    'action': 'review_required',
                    'title': '策略行为漂移',
                    'reason': f'drift_score {drift_score:.2f} ≥ {self.drift_limit:.2f}',
                    'payload': {'metric': metric},
                }))
                await self._record_domain_event(db, sid, 'runtime_risk.behavior_drift', {'account_id': account_id, 'metric': metric}, severity='info', correlation_id=account_id)

            if str(strategy.get('status')) == 'suspended' and max_drawdown < self.recovery_drawdown and daily_return > -0.03 and drift_score < 0.25:
                recovered_to = await self._recover_strategy(db, strategy, metric)
                if recovered_to:
                    if account_id:
                        await self._set_account_status(db, account_id, 'active', promotion_candidate=bool(metric.get('decision') == 'promote'))
                    for item in open_events:
                        if item.get('severity') == 'critical' and hasattr(db, 'resolve_strategy_runtime_risk_event'):
                            await db.resolve_strategy_runtime_risk_event(item['id'], {
                                'resolution': 'auto_recovered',
                                'recovered_to': recovered_to,
                            })
                    recovered.append({'strategy_id': sid, 'to_status': recovered_to})
                    await self._record_domain_event(db, sid, 'runtime_risk.recovered', {'account_id': account_id, 'to_status': recovered_to, 'metric': metric}, severity='info', correlation_id=account_id)

        return {
            'scanned': len(strategies),
            'events': emitted,
            'event_count': len(emitted),
            'actions': action_items,
            'action_count': len(action_items),
            'suspended': suspended,
            'recovered': recovered,
        }


_runtime_risk_service: Optional[StrategyRuntimeRiskService] = None


def get_strategy_runtime_risk_service() -> StrategyRuntimeRiskService:
    global _runtime_risk_service
    if _runtime_risk_service is None:
        _runtime_risk_service = StrategyRuntimeRiskService()
    return _runtime_risk_service
