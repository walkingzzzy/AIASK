"""策略自治生成：本地 LLM 代理 + 参数进化 + 实验闭环。"""

from __future__ import annotations

from collections import Counter
import logging
from datetime import date
from typing import Any, Optional
from uuid import uuid4

from .strategy_factory.utils import _extract_event_context
from .strategy_autonomy_components import (  # noqa: F401
    CandidateGenerationService,
    CommitteeReviewService,
    ExperimentRecorder,
)
from .strategy_autonomy_lifecycle import AutonomyLifecycleTracker

# --- Sub-module re-exports (backward compatibility) ---
from .strategy_spec import (  # noqa: F401
    DEFAULT_CODES,
    RESEARCH_CANDIDATE_POOL_LIMIT,
    RESEARCH_FINANCIAL_DETAIL_LIMIT,
    RESEARCH_KLINE_SCAN_LIMIT,
    RESEARCH_SYMBOL_DETAIL_LIMIT,
    RESEARCH_UNIVERSE_PAGE_SIZE,
    RESEARCH_UNIVERSE_SCAN_LIMIT,
    StrategySpec,
)
from .strategy_generators import RuleStrategyGenerator, LLMProxyStrategyGenerator  # noqa: F401
from .strategy_optimizer import BanditParameterOptimizer  # noqa: F401
from .strategy_reviewer import MultiAgentStrategyReviewer  # noqa: F401

logger = logging.getLogger(__name__)


class AutonomyCycleOrchestrator:
    @staticmethod
    def _submission_metrics(submit_result: Optional[dict]) -> dict:
        payload = dict(submit_result or {})
        items = list(payload.get('items') or payload.get('strategies') or [])
        submitted_count = int(payload.get('submitted', len(items)))
        passed_count = int(
            payload.get(
                'gate_3_passed',
                payload.get(
                    'passed_quality_gate',
                    len([item for item in items if item.get('passed')]),
                ),
            )
        )
        failed_count = int(payload.get('gate_3_failed', max(submitted_count - passed_count, 0)))
        return {
            'submitted_count': submitted_count,
            'passed_count': passed_count,
            'failed_count': failed_count,
        }

    def __init__(self):
        self.generation_service = CandidateGenerationService(
            rule_generator=RuleStrategyGenerator(),
            llm_generator=LLMProxyStrategyGenerator(),
            optimizer=BanditParameterOptimizer(),
        )
        self.review_service = CommitteeReviewService(reviewer=MultiAgentStrategyReviewer())
        self.experiment_recorder = ExperimentRecorder()
        self.rule_generator = self.generation_service.rule_generator
        self.llm_generator = self.generation_service.llm_generator
        self.optimizer = self.generation_service.optimizer
        self.reviewer = self.review_service.reviewer

    async def _select_parents(self, db, parent_strategy_id: Optional[str] = None) -> list[dict]:
        return await self.generation_service.select_parents(db, parent_strategy_id=parent_strategy_id)

    @staticmethod
    def _attach_lineage(spec: StrategySpec, *, parent_strategy_id: Optional[str], task_run_id: Optional[int], review_rank: Optional[int] = None, is_champion: bool = False) -> StrategySpec:
        return CommitteeReviewService.attach_lineage(
            spec,
            parent_strategy_id=parent_strategy_id,
            task_run_id=task_run_id,
            review_rank=review_rank,
            is_champion=is_champion,
        )

    @staticmethod
    def _review_score(spec: StrategySpec) -> float:
        return CommitteeReviewService.review_score(spec)

    async def _record_experiment(self, db, spec: StrategySpec, source: str, snapshot: dict, task_run: dict) -> dict:
        return await self.experiment_recorder.record_experiment(db, spec, source, snapshot, task_run)

    async def generate_factory_candidates(self, db, snapshot: dict, limit: int = 3, research_task: Optional[dict[str, Any]] = None, source: str = 'strategy_factory') -> dict:
        cycle = await self.run_cycle(db, snapshot=snapshot, limit=limit, source=source, auto_submit=False, research_task=research_task)
        return cycle

    @staticmethod
    def _build_generation_result(candidates: list[dict], generation_stats: dict, llm_report: dict[str, Any]) -> dict:
        return {
            'count': len(candidates),
            'stats': generation_stats,
            'llm_generation': llm_report,
            'candidates': candidates,
        }

    @staticmethod
    def _build_review_result(reviewed_specs: list[StrategySpec], rejected_count: int, committee_reviews: list[dict[str, Any]], champion: Optional[dict[str, Any]]) -> dict:
        return {
            'reviewed_count': len(reviewed_specs),
            'rejected_count': rejected_count,
            'committee_reviews': committee_reviews,
            'champion': champion,
        }

    @staticmethod
    def _build_experiments_result(experiments: list[dict]) -> dict:
        status_counts = Counter(
            str((item or {}).get('status') or 'unknown')
            for item in list(experiments or [])
        )
        return {
            'count': len(experiments),
            'items': experiments,
            'status_counts': dict(status_counts),
        }

    @staticmethod
    def _build_submission_result(auto_submit: bool, submit_result: Optional[dict], candidates: list[dict]) -> dict:
        payload = dict(submit_result or {})
        items = list(payload.get('items') or payload.get('strategies') or [])
        submitted_count = int(payload.get('submitted', len(items) if auto_submit and items else 0))
        inferred_passed_count = len([item for item in items if item.get('passed')])
        passed_count = int(payload.get('gate_3_passed', payload.get('passed_quality_gate', inferred_passed_count)))
        failed_count = int(payload.get('gate_3_failed', max(submitted_count - passed_count, 0)))
        return {
            'auto_submit': auto_submit,
            'attempted': bool(auto_submit and candidates),
            'submitted_count': submitted_count,
            'passed_count': passed_count,
            'failed_count': failed_count,
            'provisional_passed_count': int(payload.get('gate_3_provisional_passed', 0)),
            'failure_reason_topn': list(payload.get('gate_3_failure_reason_topn') or []),
            'items': items,
            'result': payload or None,
        }

    @staticmethod
    def _build_task_run_result(task_run: dict, *, source: str, snapshot_date: Any, research_task: dict, event_context: dict) -> dict:
        return {
            'id': task_run.get('id'),
            'trace_id': task_run.get('trace_id'),
            'status': 'completed',
            'source': source,
            'snapshot_date': snapshot_date,
            'research_task': research_task,
            'event_context': event_context,
        }

    @staticmethod
    def _build_cycle_result(
        *,
        task_run_result: dict,
        generation_result: dict,
        review_result: dict,
        experiments_result: dict,
        submission_result: dict,
        snapshot_date: Any,
        research_task: dict,
        factor_research: dict,
        event_context: dict,
        lifecycle: dict,
    ) -> dict:
        experiment_items = list(experiments_result.get('items') or [])
        return {
            'task_run': task_run_result,
            'generation': generation_result,
            'review': review_result,
            'experiments': experiments_result,
            'submission': submission_result,
            'lifecycle': lifecycle,
            'task_run_id': task_run_result.get('id'),
            'snapshot_date': snapshot_date,
            'research_task': research_task,
            'factor_research': factor_research,
            'generated_count': generation_result.get('count', 0),
            'reviewed_count': review_result.get('reviewed_count', 0),
            'rejected_count': review_result.get('rejected_count', 0),
            'committee_reviews': list(review_result.get('committee_reviews') or []),
            'candidates': list(generation_result.get('candidates') or []),
            'experiment_records': experiment_items,
            'champion': review_result.get('champion'),
            'submitted': submission_result.get('result'),
            'llm_generation': generation_result.get('llm_generation') or {},
            'event_context': event_context,
            'generation_stats': generation_result.get('stats') or {},
            'artifacts': {
                'experiments': experiment_items,
            },
        }


    async def _prepare_cycle_context(
        self,
        db,
        *,
        snapshot: Optional[dict],
        research_task: Optional[dict[str, Any]],
    ) -> tuple[dict, dict, dict, dict]:
        resolved_snapshot = snapshot or (
            await db.get_daily_snapshot() if hasattr(db, 'get_daily_snapshot') else None
        ) or {'date': str(date.today())}
        resolved_task = dict(research_task or {})
        factor_research = dict(resolved_snapshot.get('factor_research') or {})
        task_metadata = dict(resolved_task.get('metadata') or {})
        if factor_research and not task_metadata.get('factor_research'):
            task_metadata['factor_research'] = factor_research
        if task_metadata:
            resolved_task = {**resolved_task, 'metadata': task_metadata}
        event_context = _extract_event_context(resolved_task)
        return resolved_snapshot, resolved_task, factor_research, event_context

    async def _create_cycle_task_run(
        self,
        db,
        *,
        parent_strategy_id: Optional[str],
        source: str,
        limit: int,
        snapshot: dict,
        research_task: dict,
        event_context: dict,
        auto_submit: bool,
    ) -> dict:
        return await db.save_strategy_task_run({
            'strategy_id': parent_strategy_id,
            'task_name': 'strategy_ai_cycle',
            'task_scope': source,
            'task_key': research_task.get('task_key') or parent_strategy_id or str(snapshot.get('date') or date.today()),
            'status': 'running',
            'trace_id': uuid4().hex[:12],
            'payload': {
                'limit': limit,
                'parent_strategy_id': parent_strategy_id,
                'snapshot_date': snapshot.get('date'),
                'research_task': research_task,
                'event_context': event_context,
                'auto_submit': auto_submit,
            },
        })

    async def _run_cycle_pipeline(
        self,
        db,
        *,
        snapshot: dict,
        limit: int,
        source: str,
        parent_strategy_id: Optional[str],
        research_task: dict,
        task_run: dict,
        auto_submit: bool,
        lifecycle: AutonomyLifecycleTracker,
    ) -> dict:
        lifecycle.enter_phase('generating', detail={
            'source': source,
            'limit': int(limit or 0),
            'parent_strategy_id': parent_strategy_id,
        })
        generation_batch = await self.generation_service.generate(
            db,
            snapshot=snapshot,
            limit=limit,
            research_task=research_task,
            parent_strategy_id=parent_strategy_id,
        )
        llm_report = dict(generation_batch.get('llm_report') or {})
        rule_specs = list(generation_batch.get('rule_specs') or [])
        llm_specs = list(generation_batch.get('llm_specs') or [])
        evolved_specs = list(generation_batch.get('evolved_specs') or [])
        merged_specs = list(generation_batch.get('merged_specs') or [])
        lifecycle.complete_phase('generating', metrics={
            'rule_count': len(rule_specs),
            'llm_count': len(llm_specs),
            'evolved_count': len(evolved_specs),
            'merged_count': len(merged_specs),
        })

        lifecycle.enter_phase('reviewing', detail={'candidate_count': len(merged_specs)})
        review_batch = self.review_service.review_candidates(
            merged_specs,
            snapshot=snapshot,
            parent_strategy_id=parent_strategy_id,
            task_run_id=task_run.get('id'),
        )
        reviewed_specs = list(review_batch.get('reviewed_specs') or [])
        committee_reviews = list(review_batch.get('committee_reviews') or [])
        rejected_count = int(review_batch.get('rejected_count') or 0)
        lifecycle.complete_phase('reviewing', metrics={
            'reviewed_count': len(reviewed_specs),
            'rejected_count': rejected_count,
            'committee_review_count': len(committee_reviews),
        })

        lifecycle.enter_phase('recording', detail={'reviewed_count': len(reviewed_specs)})
        experiment_batch = await self.experiment_recorder.record_candidates(
            db,
            reviewed_specs,
            source=source,
            snapshot=snapshot,
            task_run=task_run,
        )
        experiments = list(experiment_batch.get('experiments') or [])
        candidates = list(experiment_batch.get('candidates') or [])
        champion = dict(experiment_batch.get('champion') or {}) or None
        lifecycle.complete_phase('recording', metrics={
            'experiment_count': len(experiments),
            'candidate_count': len(candidates),
            'champion_present': champion is not None,
        })

        submit_result = None
        if auto_submit and candidates:
            lifecycle.enter_phase('submitting', detail={'candidate_count': len(candidates)})
            from .strategy_factory import StrategySubmitter
            submit_result = await StrategySubmitter().submit(candidates, snapshot, db)
            submission_batch = await self.experiment_recorder.apply_submission_results(db, experiments, submit_result)
            experiments = list(submission_batch.get('experiments') or [])
            by_experiment = dict(submission_batch.get('items_by_experiment') or {})
            if champion is not None:
                champion_item = by_experiment.get(champion.get('experiment_id')) or {}
                champion['generated_strategy_id'] = champion_item.get('strategy_id')
                champion['status'] = 'accepted' if champion_item.get('passed') else 'rejected'
            lifecycle.complete_phase('submitting', metrics=self._submission_metrics(submit_result))
        elif auto_submit:
            lifecycle.skip_phase('submitting', reason='no_candidates')
        else:
            lifecycle.skip_phase('submitting', reason='auto_submit_disabled')

        return {
            'llm_report': llm_report,
            'rule_specs': rule_specs,
            'llm_specs': llm_specs,
            'evolved_specs': evolved_specs,
            'merged_specs': merged_specs,
            'reviewed_specs': reviewed_specs,
            'committee_reviews': committee_reviews,
            'rejected_count': rejected_count,
            'experiments': experiments,
            'candidates': candidates,
            'champion': champion,
            'submit_result': submit_result,
        }

    async def _save_cycle_completed_event(
        self,
        db,
        *,
        parent_strategy_id: Optional[str],
        task_run: dict,
        snapshot: dict,
        source: str,
        candidates: list[dict],
        reviewed_specs: list[StrategySpec],
        rejected_count: int,
        champion: Optional[dict[str, Any]],
        research_task: dict,
        event_context: dict,
        factor_research: dict,
        lifecycle: dict,
    ) -> None:
        if not hasattr(db, 'save_strategy_domain_event'):
            return
        await db.save_strategy_domain_event({
            'strategy_id': parent_strategy_id,
            'aggregate_type': 'strategy_ai_cycle',
            'aggregate_id': str(task_run.get('id') or snapshot.get('date') or date.today()),
            'event_type': 'strategy_ai_cycle.completed',
            'source': source,
            'severity': 'info',
            'correlation_id': task_run.get('trace_id'),
            'payload': {
                'generated_count': len(candidates),
                'reviewed_count': len(reviewed_specs),
                'rejected_count': rejected_count,
                'task_run_id': task_run.get('id'),
                'champion_experiment_id': (champion or {}).get('experiment_id'),
                'research_task': research_task,
                'event_context': event_context,
                'factor_research': factor_research,
                'lifecycle': lifecycle,
            },
        })

    async def _save_cycle_failed_event(
        self,
        db,
        *,
        parent_strategy_id: Optional[str],
        task_run: dict,
        snapshot: dict,
        source: str,
        research_task: dict,
        event_context: dict,
        factor_research: dict,
        lifecycle: dict,
        error: str,
    ) -> None:
        if not hasattr(db, 'save_strategy_domain_event'):
            return
        await db.save_strategy_domain_event({
            'strategy_id': parent_strategy_id,
            'aggregate_type': 'strategy_ai_cycle',
            'aggregate_id': str(task_run.get('id') or snapshot.get('date') or date.today()),
            'event_type': 'strategy_ai_cycle.failed',
            'source': source,
            'severity': 'error',
            'correlation_id': task_run.get('trace_id'),
            'payload': {
                'task_run_id': task_run.get('id'),
                'snapshot_date': snapshot.get('date'),
                'research_task': research_task,
                'event_context': event_context,
                'factor_research': factor_research,
                'lifecycle': lifecycle,
                'error': error,
            },
        })


    async def run_cycle(
        self,
        db,
        snapshot: Optional[dict] = None,
        limit: int = 3,
        source: str = 'manual',
        parent_strategy_id: Optional[str] = None,
        auto_submit: bool = False,
        research_task: Optional[dict[str, Any]] = None,
    ) -> dict:
        snapshot, research_task, factor_research, event_context = await self._prepare_cycle_context(
            db,
            snapshot=snapshot,
            research_task=research_task,
        )
        lifecycle = AutonomyLifecycleTracker(auto_submit=auto_submit)
        task_run = {'id': None, 'trace_id': None}
        try:
            lifecycle.enter_phase('prepared', detail={
                'source': source,
                'snapshot_date': snapshot.get('date'),
                'task_source': research_task.get('task_source'),
            })
            task_run = await self._create_cycle_task_run(
                db,
                parent_strategy_id=parent_strategy_id,
                source=source,
                limit=limit,
                snapshot=snapshot,
                research_task=research_task,
                event_context=event_context,
                auto_submit=auto_submit,
            )
            lifecycle.complete_phase('prepared', metrics={
                'task_run_id': task_run.get('id'),
                'snapshot_date': snapshot.get('date'),
                'auto_submit': bool(auto_submit),
            })
            pipeline = await self._run_cycle_pipeline(
                db,
                snapshot=snapshot,
                limit=limit,
                source=source,
                parent_strategy_id=parent_strategy_id,
                research_task=research_task,
                task_run=task_run,
                auto_submit=auto_submit,
                lifecycle=lifecycle,
            )
            llm_report = dict(pipeline.get('llm_report') or {})
            rule_specs = list(pipeline.get('rule_specs') or [])
            llm_specs = list(pipeline.get('llm_specs') or [])
            evolved_specs = list(pipeline.get('evolved_specs') or [])
            merged_specs = list(pipeline.get('merged_specs') or [])
            reviewed_specs = list(pipeline.get('reviewed_specs') or [])
            committee_reviews = list(pipeline.get('committee_reviews') or [])
            rejected_count = int(pipeline.get('rejected_count') or 0)
            experiments = list(pipeline.get('experiments') or [])
            candidates = list(pipeline.get('candidates') or [])
            champion = dict(pipeline.get('champion') or {}) or None
            submit_result = pipeline.get('submit_result')
            lifecycle.enter_phase('completed', detail={
                'generated_count': len(candidates),
                'experiment_count': len(experiments),
            })

            generation_stats = {
                'rule_count': len(rule_specs),
                'llm_count': len(llm_specs),
                'evolved_count': len(evolved_specs),
                'merged_count': len(merged_specs),
                'llm_generation': llm_report,
                'research_task': research_task,
                'event_context': event_context,
                'factor_research': factor_research,
            }
            lifecycle.complete_phase('completed', metrics={
                'generated_count': len(candidates),
                'reviewed_count': len(reviewed_specs),
                'experiment_count': len(experiments),
                **self._submission_metrics(submit_result),
            })
            lifecycle_result = lifecycle.snapshot()
            task_run_result = self._build_task_run_result(
                task_run,
                source=source,
                snapshot_date=snapshot.get('date'),
                research_task=research_task,
                event_context=event_context,
            )
            task_run_result['lifecycle'] = lifecycle_result
            generation_result = self._build_generation_result(candidates, generation_stats, llm_report)
            review_result = self._build_review_result(reviewed_specs, rejected_count, committee_reviews, champion)
            experiments_result = self._build_experiments_result(experiments)
            submission_result = self._build_submission_result(auto_submit, submit_result, candidates)
            result = self._build_cycle_result(
                task_run_result=task_run_result,
                generation_result=generation_result,
                review_result=review_result,
                experiments_result=experiments_result,
                submission_result=submission_result,
                snapshot_date=snapshot.get('date'),
                research_task=research_task,
                factor_research=factor_research,
                event_context=event_context,
                lifecycle=lifecycle_result,
            )
            await self._save_cycle_completed_event(
                db,
                parent_strategy_id=parent_strategy_id,
                task_run=task_run,
                snapshot=snapshot,
                source=source,
                candidates=candidates,
                reviewed_specs=reviewed_specs,
                rejected_count=rejected_count,
                champion=champion,
                research_task=research_task,
                event_context=event_context,
                factor_research=factor_research,
                lifecycle=lifecycle_result,
            )
            if task_run.get('id') is not None:
                await db.update_strategy_task_run(task_run['id'], status='completed', result=result)
            return result
        except Exception as exc:
            lifecycle.fail_phase(error=exc)
            lifecycle_result = lifecycle.snapshot()
            logger.error('StrategyAutonomyService.run_cycle failed: %s', exc, exc_info=True)
            if task_run.get('id') is not None:
                await db.update_strategy_task_run(
                    task_run['id'],
                    status='failed',
                    error=str(exc),
                    result={
                        'snapshot_date': snapshot.get('date'),
                        'research_task': research_task,
                        'event_context': event_context,
                        'factor_research': factor_research,
                        'lifecycle': lifecycle_result,
                    },
                )
            await self._save_cycle_failed_event(
                db,
                parent_strategy_id=parent_strategy_id,
                task_run=task_run,
                snapshot=snapshot,
                source=source,
                research_task=research_task,
                event_context=event_context,
                factor_research=factor_research,
                lifecycle=lifecycle_result,
                error=str(exc),
            )
            setattr(exc, 'autonomy_lifecycle', lifecycle_result)
            setattr(exc, 'autonomy_task_run_id', task_run.get('id'))
            raise


class StrategyAutonomyService(AutonomyCycleOrchestrator):
    """Backward-compatible public entry point for autonomy orchestration."""


_strategy_autonomy_service: Optional[StrategyAutonomyService] = None


def get_strategy_autonomy_service() -> StrategyAutonomyService:
    global _strategy_autonomy_service
    if _strategy_autonomy_service is None:
        _strategy_autonomy_service = StrategyAutonomyService()
    return _strategy_autonomy_service
