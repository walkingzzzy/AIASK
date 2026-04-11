"""策略模拟盘晋级评审与自动应用流水线。"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class StrategyPromotionPipelineService:
    @staticmethod
    def _score(overview: dict, metric: Optional[dict]) -> float:
        score = 0.35
        if overview.get('promotion_ready'):
            score += 0.4
        if overview.get('deprecation_risk'):
            score -= 0.35
        if metric:
            sharpe = float(metric.get('sharpe_ratio') or 0)
            hit_rate = float(metric.get('hit_rate_5d') or 0)
            forward_sharpe = float(metric.get('forward_sharpe_5d') or 0)
            score += min(max(sharpe, -1.0), 2.0) * 0.08
            score += hit_rate * 0.12
            score += max(forward_sharpe, -1.0) * 0.08
        score -= min(len(overview.get('blockers') or []), 5) * 0.08
        score -= min(len(overview.get('risk_flags') or []), 5) * 0.05
        return round(max(0.0, min(score, 1.0)), 4)

    async def review(
        self,
        db,
        strategy: dict,
        *,
        source: str = 'manual',
        auto_apply: bool = False,
    ) -> dict:
        from .strategy_lifecycle_shared import (
            build_incubation_overview as _build_incubation_overview,
            update_status as _update_status,
            validate_transition as _validate_transition,
        )

        overview = await _build_incubation_overview(db, strategy)
        sid = strategy['id']
        metric = await db.get_latest_strategy_incubation_metric(sid) if hasattr(db, 'get_latest_strategy_incubation_metric') else None
        account = await db.get_strategy_incubation_account(sid) if hasattr(db, 'get_strategy_incubation_account') else None
        blockers = list(overview.get('blockers') or [])
        risk_flags = list(overview.get('risk_flags') or [])
        score = self._score(overview, metric)

        if overview.get('promotion_ready'):
            status = 'approved'
            recommendation = 'promote'
        elif overview.get('deprecation_risk'):
            status = 'rejected'
            recommendation = 'deprecate'
        else:
            status = 'watch'
            recommendation = 'observe'

        review = await db.save_strategy_promotion_review({
            'strategy_id': sid,
            'account_id': (account or {}).get('account_id'),
            'review_source': source,
            'stage': (metric or {}).get('stage') or (account or {}).get('stage') or 'incubating',
            'status': status,
            'recommendation': recommendation,
            'score': score,
            'blockers': blockers,
            'risk_flags': risk_flags,
            'summary': {
                'promotion_ready': bool(overview.get('promotion_ready')),
                'deprecation_risk': bool(overview.get('deprecation_risk')),
                'validation_grade': overview.get('validation_grade'),
                'strict_incubation_ready': overview.get('strict_incubation_ready'),
                'live_candidate_ready': overview.get('live_candidate_ready'),
                'strict_live_alignment_status': overview.get('strict_live_alignment_status'),
                'total_signals': overview.get('total_signals'),
                'observed_forward_days': overview.get('observed_forward_days') or [],
            },
            'metadata': {
                'overview': overview,
                'metric': metric or {},
            },
        }) if hasattr(db, 'save_strategy_promotion_review') else {
            'strategy_id': sid,
            'status': status,
            'recommendation': recommendation,
            'score': score,
            'blockers': blockers,
            'risk_flags': risk_flags,
            'summary': overview,
            'metadata': {'metric': metric or {}},
        }

        if hasattr(db, 'save_strategy_domain_event'):
            await db.save_strategy_domain_event({
                'strategy_id': sid,
                'aggregate_type': 'strategy_promotion_review',
                'aggregate_id': str(review.get('id') or sid),
                'event_type': 'promotion.reviewed',
                'source': source,
                'severity': 'warning' if status == 'rejected' else 'info',
                'correlation_id': (account or {}).get('account_id'),
                'payload': {
                    'status': status,
                    'recommendation': recommendation,
                    'score': score,
                    'blockers': blockers,
                    'risk_flags': risk_flags,
                },
            })

        applied_transition = None
        if auto_apply:
            current_status = str(strategy.get('status') or '')
            if recommendation == 'promote' and _validate_transition(current_status, 'listed'):
                await _update_status(
                    db,
                    sid,
                    'listed',
                    actor_id=source,
                    reason='promotion_pipeline_approved',
                    metadata={'promotion_review_id': review.get('id'), 'score': score},
                )
                applied_transition = {'from': current_status, 'to': 'listed'}
                if account and hasattr(db, 'save_strategy_incubation_account'):
                    await db.save_strategy_incubation_account(
                        sid,
                        account['account_id'],
                        stage='promoted',
                        status='active',
                        source_run_id=(account or {}).get('source_run_id'),
                        metadata={**dict((account or {}).get('metadata') or {}), 'promotion_review_id': review.get('id')},
                    )
            elif recommendation == 'deprecate' and _validate_transition(current_status, 'deprecated'):
                await _update_status(
                    db,
                    sid,
                    'deprecated',
                    actor_id=source,
                    reason='promotion_pipeline_rejected',
                    metadata={'promotion_review_id': review.get('id'), 'score': score},
                )
                applied_transition = {'from': current_status, 'to': 'deprecated'}
                if account and hasattr(db, 'save_strategy_incubation_account'):
                    await db.save_strategy_incubation_account(
                        sid,
                        account['account_id'],
                        stage='failed',
                        status='retired',
                        source_run_id=(account or {}).get('source_run_id'),
                        metadata={**dict((account or {}).get('metadata') or {}), 'promotion_review_id': review.get('id')},
                    )

        if applied_transition and hasattr(db, 'save_strategy_domain_event'):
            await db.save_strategy_domain_event({
                'strategy_id': sid,
                'aggregate_type': 'strategy_promotion_review',
                'aggregate_id': str(review.get('id') or sid),
                'event_type': 'promotion.applied',
                'source': source,
                'severity': 'info',
                'correlation_id': (account or {}).get('account_id'),
                'payload': {
                    'transition': applied_transition,
                    'status': status,
                    'recommendation': recommendation,
                    'score': score,
                },
            })

        return {
            'review': review,
            'overview': overview,
            'applied_transition': applied_transition,
        }


_promotion_pipeline_service: Optional[StrategyPromotionPipelineService] = None


def get_strategy_promotion_pipeline_service() -> StrategyPromotionPipelineService:
    global _promotion_pipeline_service
    if _promotion_pipeline_service is None:
        _promotion_pipeline_service = StrategyPromotionPipelineService()
    return _promotion_pipeline_service
