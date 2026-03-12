"""策略自治生成：本地 LLM 代理 + 参数进化 + 实验闭环。"""

from __future__ import annotations

import json
import logging
import time
from datetime import date
from typing import Any, Optional
from uuid import uuid4

from .artifact_registry import register_experiment
from .strategy_factory.utils import _extract_event_context

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


class StrategyAutonomyService:
    def __init__(self):
        self.rule_generator = RuleStrategyGenerator()
        self.llm_generator = LLMProxyStrategyGenerator()
        self.optimizer = BanditParameterOptimizer()
        self.reviewer = MultiAgentStrategyReviewer()

    async def _select_parents(self, db, parent_strategy_id: Optional[str] = None) -> list[dict]:
        if parent_strategy_id:
            strategy = await db.get_strategy(parent_strategy_id)
            return [strategy] if strategy else []
        parents = []
        for status in ('incubating', 'listed'):
            parents.extend(await db.list_strategies(status, limit=5))
        return parents[:3]

    @staticmethod
    def _attach_lineage(spec: StrategySpec, *, parent_strategy_id: Optional[str], task_run_id: Optional[int], review_rank: Optional[int] = None, is_champion: bool = False) -> StrategySpec:
        metadata = dict(spec.metadata or {})
        if parent_strategy_id and not metadata.get('parent_strategy_id'):
            metadata['parent_strategy_id'] = parent_strategy_id
        if task_run_id is not None:
            metadata['task_run_id'] = task_run_id
        committee_review = dict(metadata.get('committee_review') or {})
        if review_rank is not None:
            committee_review['rank'] = int(review_rank)
        if is_champion:
            committee_review['is_champion'] = True
        elif review_rank is not None:
            committee_review.setdefault('is_champion', False)
        if committee_review:
            metadata['committee_review'] = committee_review
        spec.metadata = metadata
        return spec

    @staticmethod
    def _review_score(spec: StrategySpec) -> float:
        review = dict((spec.metadata or {}).get('committee_review') or {})
        value = review.get('final_score')
        try:
            return float(value)
        except Exception:
            return 0.0

    async def _record_experiment(self, db, spec: StrategySpec, source: str, snapshot: dict, task_run: dict) -> dict:
        experiment_id = f"exp_{int(time.time())}_{uuid4().hex[:8]}"
        hypothesis = spec.description or f'{source}:{spec.strategy_type}'
        artifact = register_experiment({
            'experiment_id': experiment_id,
            'hypothesis': hypothesis,
            'method': spec.metadata.get('generator_type') or source,
            'parameters': spec.params,
            'status': 'running',
            'tags': spec.tags,
            'conclusion': '',
        })
        parent_strategy_id = spec.metadata.get('parent_strategy_id')
        prompt_payload = spec.metadata.get('llm_prompt')
        research_task = dict(spec.metadata.get('research_task') or {})
        event_context = dict(spec.metadata.get('event_context') or {}) or _extract_event_context(research_task)
        return await db.save_strategy_generation_experiment({
            'experiment_id': experiment_id,
            'strategy_id': parent_strategy_id,
            'parent_strategy_id': parent_strategy_id,
            'generated_strategy_id': spec.metadata.get('generated_strategy_id'),
            'task_run_id': task_run.get('id'),
            'source': source,
            'generator_type': spec.metadata.get('generator_type') or source,
            'optimizer_type': spec.metadata.get('optimizer_type'),
            'status': 'generated',
            'hypothesis': hypothesis,
            'prompt': (str(prompt_payload) if prompt_payload is not None else str(snapshot.get('date') or date.today())),
            'parameters': spec.params,
            'strategy_spec': {
                'strategy_type': spec.strategy_type,
                'name': spec.name,
                'description': spec.description,
                'tags': spec.tags,
                'params': spec.params,
                'target_symbols': spec.metadata.get('target_symbols') or [],
                'stock_pool': spec.metadata.get('stock_pool') or {},
                'selection_logic': spec.metadata.get('selection_logic') or [],
                'research_task': research_task,
                'event_context': event_context,
            },
            'evaluation': {
                'source': source,
                'task_run_id': task_run.get('id'),
                'generation_reason': spec.metadata.get('generation_reason') or {},
                'committee_review': spec.metadata.get('committee_review') or {},
                'llm_analysis': spec.metadata.get('llm_analysis') or {},
                'llm_research_context': spec.metadata.get('llm_research_context') or {},
                'llm_response': spec.metadata.get('llm_response') or {},
                'target_symbols': spec.metadata.get('target_symbols') or [],
                'stock_pool': spec.metadata.get('stock_pool') or {},
                'selection_logic': spec.metadata.get('selection_logic') or [],
                'research_scope': spec.metadata.get('research_scope') or {},
                'research_task': research_task,
                'event_context': event_context,
            },
            'result': {},
            'parent_experiment_id': None,
            'artifact_id': artifact.get('artifact_id'),
        })

    async def generate_factory_candidates(self, db, snapshot: dict, limit: int = 3, research_task: Optional[dict[str, Any]] = None, source: str = 'strategy_factory') -> dict:
        cycle = await self.run_cycle(db, snapshot=snapshot, limit=limit, source=source, auto_submit=False, research_task=research_task)
        return cycle

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
        snapshot = snapshot or (await db.get_daily_snapshot() if hasattr(db, 'get_daily_snapshot') else None) or {'date': str(date.today())}
        research_task = dict(research_task or {})
        event_context = _extract_event_context(research_task)
        task_run = await db.save_strategy_task_run({
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
        llm_report: dict[str, Any] = {}
        try:
            parents = await self._select_parents(db, parent_strategy_id=parent_strategy_id)
            task_preferences = list(research_task.get('strategy_preferences') or [])
            rule_limit = max(0, limit // 3) if research_task else max(1, limit // 2 or 1)
            rule_specs = self.rule_generator.generate(snapshot, limit=rule_limit) if rule_limit > 0 else []
            if task_preferences:
                rule_specs = [spec for spec in rule_specs if spec.strategy_type in set(task_preferences)] or rule_specs
            llm_specs = await self.llm_generator.generate(db, limit=max(1, limit), snapshot=snapshot, parent_strategies=parents, research_task=research_task)
            llm_report = self.llm_generator.get_last_report() if hasattr(self.llm_generator, 'get_last_report') else {}
            evolved_specs: list[StrategySpec] = []
            for parent in parents[:2]:
                evolved_specs.extend(await self.optimizer.evolve(db, parent, limit=2))

            merged: list[StrategySpec] = []
            seen = set()
            for spec in [*rule_specs, *llm_specs, *evolved_specs]:
                if research_task and not dict(spec.metadata or {}).get('research_task'):
                    spec.metadata = {**dict(spec.metadata or {}), 'research_task': research_task}
                key = (spec.strategy_type, json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(spec)
                if len(merged) >= max(1, min(int(limit or 3), 10)):
                    break

            reviewed_specs: list[StrategySpec] = []
            committee_reviews: list[dict[str, Any]] = []
            rejected_count = 0
            for spec in merged:
                reviewed_spec, review = self.reviewer.review(spec, snapshot)
                committee_reviews.append({
                    'strategy_type': spec.strategy_type,
                    'name': spec.name,
                    **review,
                })
                if reviewed_spec is None:
                    rejected_count += 1
                    continue
                reviewed_specs.append(self._attach_lineage(reviewed_spec, parent_strategy_id=parent_strategy_id, task_run_id=task_run.get('id')))

            reviewed_specs.sort(key=self._review_score, reverse=True)
            for rank, spec in enumerate(reviewed_specs, 1):
                self._attach_lineage(spec, parent_strategy_id=parent_strategy_id, task_run_id=task_run.get('id'), review_rank=rank, is_champion=rank == 1)

            experiments = []
            candidates = []
            champion = None
            for spec in reviewed_specs:
                experiment = await self._record_experiment(db, spec, source, snapshot, task_run)
                experiments.append(experiment)
                candidate = spec.to_candidate(source, experiment['experiment_id'])
                candidates.append(candidate)
                if champion is None:
                    committee_review = dict((experiment.get('evaluation') or {}).get('committee_review') or {})
                    champion = {
                        'experiment_id': experiment.get('experiment_id'),
                        'strategy_type': spec.strategy_type,
                        'name': spec.name,
                        'final_score': committee_review.get('final_score'),
                        'decision': committee_review.get('decision'),
                        'parent_strategy_id': experiment.get('parent_strategy_id') or experiment.get('strategy_id'),
                    }

            submit_result = None
            if auto_submit and candidates:
                from .strategy_factory import StrategySubmitter
                submit_result = await StrategySubmitter().submit(candidates, snapshot, db)
                by_experiment = {item.get('experiment_id'): item for item in submit_result.get('items', [])}
                updated_experiments = []
                for experiment in experiments:
                    item = by_experiment.get(experiment.get('experiment_id')) or {}
                    evaluation = dict(experiment.get('evaluation') or {})
                    evaluation['submission_result'] = item
                    updated = await db.save_strategy_generation_experiment({
                        **experiment,
                        'strategy_id': experiment.get('parent_strategy_id') or experiment.get('strategy_id'),
                        'generated_strategy_id': item.get('strategy_id') or experiment.get('generated_strategy_id'),
                        'status': 'accepted' if item.get('passed') else 'rejected',
                        'evaluation': evaluation,
                        'result': item,
                    })
                    updated_experiments.append(updated)
                experiments = updated_experiments
                if champion is not None:
                    champion_item = by_experiment.get(champion.get('experiment_id')) or {}
                    champion['generated_strategy_id'] = champion_item.get('strategy_id')
                    champion['status'] = 'accepted' if champion_item.get('passed') else 'rejected'

            result = {
                'task_run_id': task_run.get('id'),
                'snapshot_date': snapshot.get('date'),
                'research_task': research_task,
                'generated_count': len(candidates),
                'reviewed_count': len(reviewed_specs),
                'rejected_count': rejected_count,
                'committee_reviews': committee_reviews,
                'candidates': candidates,
                'experiments': experiments,
                'champion': champion,
                'submitted': submit_result,
                'llm_generation': llm_report,
                'event_context': event_context,
                'generation_stats': {
                    'rule_count': len(rule_specs),
                    'llm_count': len(llm_specs),
                    'evolved_count': len(evolved_specs),
                    'merged_count': len(merged),
                    'llm_generation': llm_report,
                    'research_task': research_task,
                    'event_context': event_context,
                },
            }
            if hasattr(db, 'save_strategy_domain_event'):
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
                    },
                })
            await db.update_strategy_task_run(task_run['id'], status='completed', result=result)
            return result
        except Exception as exc:
            logger.error('StrategyAutonomyService.run_cycle failed: %s', exc, exc_info=True)
            await db.update_strategy_task_run(task_run['id'], status='failed', error=str(exc), result={'snapshot_date': snapshot.get('date')})
            raise


_strategy_autonomy_service: Optional[StrategyAutonomyService] = None


def get_strategy_autonomy_service() -> StrategyAutonomyService:
    global _strategy_autonomy_service
    if _strategy_autonomy_service is None:
        _strategy_autonomy_service = StrategyAutonomyService()
    return _strategy_autonomy_service
