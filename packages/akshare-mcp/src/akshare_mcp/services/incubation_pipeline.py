"""策略模拟盘孵化编排：阶段推进、自动评审和快照留痕。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class StrategyIncubationPipelineService:
    @staticmethod
    def _consecutive(metrics: list[dict], predicate) -> int:
        streak = 0
        for item in metrics:
            if predicate(item):
                streak += 1
            else:
                break
        return streak

    @staticmethod
    def _readiness_score(*, latest_metric: Optional[dict], overview: dict, open_risk_count: int, runtime_control: Optional[dict], observed_days: int, promote_streak: int, trade_days: int) -> float:
        score = 0.2
        if latest_metric:
            score += min(max(float(latest_metric.get('nav') or 1.0) - 1.0, -0.1), 0.2) * 1.5
            score += min(max(float(latest_metric.get('sharpe_ratio') or 0.0), -1.0), 2.0) * 0.12
            score += min(max(float(latest_metric.get('forward_sharpe_5d') or 0.0), -1.0), 1.5) * 0.12
            score += min(max(float(latest_metric.get('hit_rate_5d') or 0.0), 0.0), 1.0) * 0.18
            score -= min(max(float(latest_metric.get('max_drawdown') or 0.0), 0.0), 0.5) * 0.4
        score += min(observed_days, 20) * 0.0075  # scale to 20 days (was 10*0.015)
        score += min(promote_streak, 5) * 0.04
        score += min(trade_days, 10) * 0.015
        if overview.get('promotion_ready'):
            score += 0.15
        if overview.get('deprecation_risk'):
            score -= 0.2
        score -= min(len(overview.get('blockers') or []), 5) * 0.06
        score -= min(len(overview.get('risk_flags') or []), 5) * 0.05
        score -= min(open_risk_count, 3) * 0.08
        control_mode = str((runtime_control or {}).get('control_mode') or 'active')
        if control_mode not in {'active', 'throttled'}:
            score -= 0.18
        return round(max(0.0, min(score, 1.0)), 4)

    async def _record_domain_event(self, db, *, strategy_id: str, event_type: str, payload: dict, source: str, correlation_id: Optional[str] = None, severity: str = 'info'):
        if hasattr(db, 'save_strategy_domain_event'):
            await db.save_strategy_domain_event({
                'strategy_id': strategy_id,
                'aggregate_type': 'strategy_incubation_pipeline',
                'aggregate_id': strategy_id,
                'event_type': event_type,
                'source': source,
                'severity': severity,
                'correlation_id': correlation_id,
                'payload': payload,
            })

    async def _derive_snapshot(self, db, strategy: dict, *, task_run_id: Optional[int], source: str, auto_apply_review: bool) -> dict:
        # Fix #10: 从 strategy_lifecycle_shared 导入，避免循环依赖
        from .strategy_lifecycle_shared import build_incubation_overview as _build_incubation_overview

        sid = str(strategy['id'])
        overview = await _build_incubation_overview(db, strategy)
        account = await db.get_strategy_incubation_account(sid) if hasattr(db, 'get_strategy_incubation_account') else None
        if not account and str(strategy.get('status') or '') in {'incubating', 'listed'}:
            try:
                from .incubation import get_strategy_incubation_service
                ensured = await get_strategy_incubation_service().ensure_account(db, strategy, stage='warmup', source_run_id=source)
                account = ensured.get('binding') or await db.get_strategy_incubation_account(sid)
            except Exception as exc:
                logger.warning('StrategyIncubationPipelineService.ensure_account failed for %s: %s', sid, exc)
        latest_metric = await db.get_latest_strategy_incubation_metric(sid) if hasattr(db, 'get_latest_strategy_incubation_metric') else None
        metrics = await db.list_strategy_incubation_metrics(sid, limit=30) if hasattr(db, 'list_strategy_incubation_metrics') else ([] if latest_metric is None else [latest_metric])
        runtime_control = await db.get_strategy_runtime_control(sid) if hasattr(db, 'get_strategy_runtime_control') else None
        open_risks = await db.list_strategy_runtime_risk_events(strategy_id=sid, status='open', limit=20) if hasattr(db, 'list_strategy_runtime_risk_events') else []

        observed_days = len(metrics)
        trade_days = len([item for item in metrics if int(item.get('total_orders') or 0) > 0 or int(item.get('total_trades') or 0) > 0])
        promote_streak = self._consecutive(metrics, lambda row: str(row.get('decision') or '') == 'promote')
        observe_streak = self._consecutive(metrics, lambda row: str(row.get('decision') or '') in {'observe', 'promote'})
        halt_streak = self._consecutive(metrics, lambda row: str(row.get('decision') or '') == 'halt')
        open_risk_count = len(open_risks)
        control_mode = str((runtime_control or {}).get('control_mode') or 'active')
        is_control_blocking = control_mode not in {'active', 'throttled'}
        latest_decision = str((latest_metric or {}).get('decision') or 'observe')

        if str(strategy.get('status') or '') == 'listed':
            pipeline_stage = 'promoted'
            pipeline_status = 'listed'
            next_action = 'listed_monitoring'
        elif halt_streak >= 2 or (overview.get('deprecation_risk') and open_risk_count > 0):
            pipeline_stage = 'failed'
            pipeline_status = 'blocked'
            next_action = 'manual_intervention'
        elif observed_days < 7 or trade_days == 0:
            pipeline_stage = 'warmup'
            pipeline_status = 'collecting'
            next_action = 'collect_more_samples'
        elif overview.get('promotion_ready') and promote_streak >= 3 and observed_days >= 20 and open_risk_count == 0 and not is_control_blocking:
            pipeline_stage = 'graduation_ready'
            pipeline_status = 'ready_for_review'
            next_action = 'run_promotion_review'
        elif overview.get('promotion_ready') or latest_decision == 'promote':
            pipeline_stage = 'candidate'
            pipeline_status = 'candidate'
            next_action = 'accumulate_confirmation'
        else:
            pipeline_stage = 'observe'
            pipeline_status = 'observing'
            next_action = 'continue_observation'

        readiness_score = self._readiness_score(
            latest_metric=latest_metric,
            overview=overview,
            open_risk_count=open_risk_count,
            runtime_control=runtime_control,
            observed_days=observed_days,
            promote_streak=promote_streak,
            trade_days=trade_days,
        )

        snapshot = {
            'strategy_id': sid,
            'account_id': (account or {}).get('account_id'),
            'pipeline_stage': pipeline_stage,
            'pipeline_status': pipeline_status,
            'observed_days': observed_days,
            'promote_streak': promote_streak,
            'halt_streak': halt_streak,
            'latest_decision': latest_decision,
            'readiness_score': readiness_score,
            'next_action': next_action,
            'auto_review': bool(auto_apply_review and pipeline_stage == 'graduation_ready'),
            'auto_promoted': False,
            'blockers': list(overview.get('blockers') or []),
            'risk_flags': list(overview.get('risk_flags') or []),
            'summary': {
                'strategy_status': strategy.get('status'),
                'promotion_ready': bool(overview.get('promotion_ready')),
                'deprecation_risk': bool(overview.get('deprecation_risk')),
                'observed_forward_days': overview.get('observed_forward_days') or [],
                'missing_forward_days': overview.get('missing_forward_days') or [],
                'total_signals': overview.get('total_signals'),
                'trade_days': trade_days,
                'observe_streak': observe_streak,
                'open_risk_count': open_risk_count,
                'runtime_control_mode': control_mode,
            },
            'metadata': {
                'latest_metric': latest_metric or {},
                'overview': overview,
                'runtime_control': runtime_control or {},
                'open_risk_ids': [item.get('id') for item in open_risks if item.get('id') is not None],
            },
            'task_run_id': task_run_id,
            'source': source,
            'evaluated_at': datetime.now(timezone.utc).isoformat(),
        }
        return snapshot

    async def _apply_account_state(self, db, snapshot: dict, account: Optional[dict]):
        if not account:
            return
        account_id = account.get('account_id')
        strategy_id = snapshot.get('strategy_id')
        stage = snapshot.get('pipeline_stage') or 'warmup'
        status = 'active'
        if stage == 'graduation_ready':
            status = 'ready'
        elif stage == 'promoted':
            status = 'promoted'
        elif stage == 'failed':
            status = 'retired'
        if hasattr(db, 'save_strategy_incubation_account'):
            await db.save_strategy_incubation_account(
                strategy_id,
                account_id,
                stage=stage,
                status=status,
                source_run_id=str(snapshot.get('task_run_id') or ''),
                metadata={
                    **dict((account or {}).get('metadata') or {}),
                    'pipeline_status': snapshot.get('pipeline_status'),
                    'readiness_score': snapshot.get('readiness_score'),
                    'next_action': snapshot.get('next_action'),
                },
            )
        if hasattr(db, 'update_paper_account_status') and account_id:
            await db.update_paper_account_status(
                account_id,
                'active' if status in {'active', 'ready', 'promoted'} else 'archived',
                stage=stage,
                promotion_candidate=bool(stage in {'candidate', 'graduation_ready', 'promoted'}),
            )

    async def run_strategy(
        self,
        db,
        strategy: dict,
        *,
        source: str = 'manual',
        auto_apply_review: bool = False,
        task_run_id: Optional[int] = None,
    ) -> dict:
        correlation_id = uuid4().hex[:12]
        owns_task_run = task_run_id is None and hasattr(db, 'save_strategy_task_run')
        task_run = {'id': task_run_id, 'trace_id': correlation_id}
        if owns_task_run:
            task_run = await db.save_strategy_task_run({
                'strategy_id': strategy.get('id'),
                'task_name': 'strategy_incubation_pipeline',
                'task_scope': source,
                'task_key': str(strategy.get('id')),
                'status': 'running',
                'trace_id': correlation_id,
                'payload': {
                    'source': source,
                    'auto_apply_review': bool(auto_apply_review),
                },
            })

        try:
            snapshot = await self._derive_snapshot(
                db,
                strategy,
                task_run_id=task_run.get('id'),
                source=source,
                auto_apply_review=auto_apply_review,
            )
            latest_before = await db.get_latest_strategy_incubation_pipeline_snapshot(strategy['id']) if hasattr(db, 'get_latest_strategy_incubation_pipeline_snapshot') else None
            account = await db.get_strategy_incubation_account(strategy['id']) if hasattr(db, 'get_strategy_incubation_account') else None
            await self._apply_account_state(db, snapshot, account)
            persisted = await db.save_strategy_incubation_pipeline_snapshot(snapshot) if hasattr(db, 'save_strategy_incubation_pipeline_snapshot') else snapshot

            applied_review = None
            if auto_apply_review and snapshot.get('pipeline_stage') == 'graduation_ready':
                from .promotion_pipeline import get_strategy_promotion_pipeline_service
                applied_review = await get_strategy_promotion_pipeline_service().review(
                    db,
                    strategy,
                    source=f'{source}_incubation_pipeline',
                    auto_apply=True,
                )
                if applied_review.get('applied_transition'):
                    persisted = await db.save_strategy_incubation_pipeline_snapshot({
                        **persisted,
                        'pipeline_stage': 'promoted',
                        'pipeline_status': 'promoted',
                        'next_action': 'listed_monitoring',
                        'auto_promoted': True,
                        'metadata': {
                            **dict(persisted.get('metadata') or {}),
                            'promotion_review': applied_review.get('review') or {},
                            'applied_transition': applied_review.get('applied_transition') or {},
                        },
                        'summary': {
                            **dict(persisted.get('summary') or {}),
                            'strategy_status': 'listed',
                        },
                    }) if hasattr(db, 'save_strategy_incubation_pipeline_snapshot') else {**persisted, 'auto_promoted': True}
                    snapshot = {**snapshot, 'pipeline_stage': 'promoted', 'pipeline_status': 'promoted', 'auto_promoted': True}

            if latest_before and latest_before.get('pipeline_stage') != persisted.get('pipeline_stage'):
                await self._record_domain_event(
                    db,
                    strategy_id=str(strategy['id']),
                    event_type='incubation.stage_transitioned',
                    payload={
                        'from_stage': latest_before.get('pipeline_stage'),
                        'to_stage': persisted.get('pipeline_stage'),
                        'pipeline_status': persisted.get('pipeline_status'),
                    },
                    source=source,
                    correlation_id=task_run.get('trace_id'),
                )

            await self._record_domain_event(
                db,
                strategy_id=str(strategy['id']),
                event_type='incubation.pipeline_evaluated',
                payload={
                    'pipeline_stage': persisted.get('pipeline_stage'),
                    'pipeline_status': persisted.get('pipeline_status'),
                    'readiness_score': persisted.get('readiness_score'),
                    'next_action': persisted.get('next_action'),
                    'auto_review': persisted.get('auto_review'),
                    'auto_promoted': persisted.get('auto_promoted'),
                },
                source=source,
                correlation_id=task_run.get('trace_id'),
                severity='warning' if persisted.get('pipeline_stage') == 'failed' else 'info',
            )

            result = {
                'strategy_id': strategy.get('id'),
                'snapshot': persisted,
                'promotion_review': applied_review,
                'auto_promoted': bool((persisted or {}).get('auto_promoted')),
                'task_run_id': task_run.get('id'),
            }
            if owns_task_run and hasattr(db, 'update_strategy_task_run'):
                await db.update_strategy_task_run(task_run['id'], status='completed', result=result, completed_at=datetime.now(timezone.utc).isoformat())
            return result
        except Exception as exc:
            logger.warning('StrategyIncubationPipelineService.run_strategy failed for %s: %s', strategy.get('id'), exc)
            if owns_task_run and task_run.get('id') is not None and hasattr(db, 'update_strategy_task_run'):
                await db.update_strategy_task_run(task_run['id'], status='failed', error=str(exc), completed_at=datetime.now(timezone.utc).isoformat())
            raise

    async def run_batch(
        self,
        db,
        *,
        statuses: Optional[list[str]] = None,
        limit: int = 200,
        source: str = 'runtime_cycle',
        auto_apply_review: bool = True,
    ) -> dict:
        statuses = list(statuses or ['incubating'])
        correlation_id = uuid4().hex[:12]
        batch_run = await db.save_strategy_task_run({
            'strategy_id': None,
            'task_name': 'strategy_incubation_pipeline_batch',
            'task_scope': source,
            'task_key': correlation_id,
            'status': 'running',
            'trace_id': correlation_id,
            'payload': {
                'statuses': statuses,
                'limit': limit,
                'auto_apply_review': bool(auto_apply_review),
            },
        }) if hasattr(db, 'save_strategy_task_run') else {'id': None, 'trace_id': correlation_id}

        try:
            seen = set()
            strategies = []
            for status in statuses:
                rows = await db.list_strategies(status, limit=max(1, min(int(limit or 200), 1000)))
                for row in rows:
                    sid = row.get('id')
                    if sid and sid not in seen:
                        seen.add(sid)
                        strategies.append(row)
            items = []
            auto_promoted = 0
            stage_counts: dict[str, int] = {}
            for strategy in strategies:
                item = await self.run_strategy(
                    db,
                    strategy,
                    source=source,
                    auto_apply_review=auto_apply_review,
                    task_run_id=batch_run.get('id'),
                )
                items.append(item)
                stage = str(((item.get('snapshot') or {}).get('pipeline_stage') or 'unknown'))
                stage_counts[stage] = stage_counts.get(stage, 0) + 1
                auto_promoted += 1 if item.get('auto_promoted') else 0
            result = {
                'task_run_id': batch_run.get('id'),
                'count': len(items),
                'auto_promoted': auto_promoted,
                'stage_counts': stage_counts,
                'items': items,
            }
            if batch_run.get('id') is not None and hasattr(db, 'update_strategy_task_run'):
                await db.update_strategy_task_run(batch_run['id'], status='completed', result=result, completed_at=datetime.now(timezone.utc).isoformat())
            if hasattr(db, 'save_strategy_domain_event'):
                await db.save_strategy_domain_event({
                    'strategy_id': None,
                    'aggregate_type': 'incubation_pipeline',
                    'aggregate_id': str(batch_run.get('id') or correlation_id),
                    'event_type': 'incubation.pipeline_batch_completed',
                    'source': source,
                    'severity': 'info',
                    'correlation_id': batch_run.get('trace_id'),
                    'payload': result,
                })
            return result
        except Exception as exc:
            logger.warning('StrategyIncubationPipelineService.run_batch failed: %s', exc)
            if batch_run.get('id') is not None and hasattr(db, 'update_strategy_task_run'):
                await db.update_strategy_task_run(batch_run['id'], status='failed', error=str(exc), completed_at=datetime.now(timezone.utc).isoformat())
            raise


_incubation_pipeline_service: Optional[StrategyIncubationPipelineService] = None


def get_strategy_incubation_pipeline_service() -> StrategyIncubationPipelineService:
    global _incubation_pipeline_service
    if _incubation_pipeline_service is None:
        _incubation_pipeline_service = StrategyIncubationPipelineService()
    return _incubation_pipeline_service
