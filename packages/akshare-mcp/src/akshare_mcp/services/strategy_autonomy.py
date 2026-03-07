"""策略自治生成：本地 LLM 代理 + 参数进化 + 实验闭环。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional
from uuid import uuid4

import pandas as pd

from .artifact_registry import register_experiment
from .llm_alpha import LLMAlphaMiner

logger = logging.getLogger(__name__)

DEFAULT_CODES = ['000300', '600519', '000858', '601318']


@dataclass
class StrategySpec:
    strategy_type: str
    params: dict[str, Any]
    name: str = ''
    description: str = ''
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_candidate(self, source: str, experiment_id: str) -> dict:
        return {
            'strategy_type': self.strategy_type,
            'params': self.params,
            'spawn_reason': self.description or self.name or f'{source}:{self.strategy_type}',
            'generation_reason': self.metadata.get('generation_reason') or {},
            'generator_type': self.metadata.get('generator_type') or source,
            'optimizer_type': self.metadata.get('optimizer_type'),
            'experiment_id': experiment_id,
            'tags': list(dict.fromkeys(['ai_generated', source, self.strategy_type, *(self.tags or [])])),
        }


class RuleStrategyGenerator:
    def generate(self, snapshot: dict, limit: int = 2) -> list[StrategySpec]:
        fg = int(snapshot.get('fear_greed_index') or 50)
        specs: list[StrategySpec] = []
        if fg >= 60:
            specs.append(StrategySpec(
                strategy_type='momentum',
                params={'lookback': 15, 'threshold': 0.018},
                name='AI 动量强化',
                description='高情绪阶段偏向动量追随。',
                tags=['rule'],
                metadata={'generator_type': 'rule', 'generation_reason': {'fg': fg, 'regime': 'greed'}},
            ))
            specs.append(StrategySpec(
                strategy_type='ma_cross',
                params={'short_period': 6, 'long_period': 24},
                name='AI 均线趋势',
                description='情绪偏强阶段用均线趋势过滤。',
                tags=['rule'],
                metadata={'generator_type': 'rule', 'generation_reason': {'fg': fg, 'regime': 'greed'}},
            ))
        else:
            specs.append(StrategySpec(
                strategy_type='rsi',
                params={'rsi_period': 14, 'oversold': 28, 'overbought': 72},
                name='AI RSI 反转',
                description='低情绪阶段偏向均值回归与超跌反弹。',
                tags=['rule'],
                metadata={'generator_type': 'rule', 'generation_reason': {'fg': fg, 'regime': 'fear_or_neutral'}},
            ))
            specs.append(StrategySpec(
                strategy_type='value_factor',
                params={'lookback': 60, 'buy_quantile': 0.8, 'sell_quantile': 0.2},
                name='AI 价值回归',
                description='低情绪阶段偏向价值/反转。',
                tags=['rule'],
                metadata={'generator_type': 'rule', 'generation_reason': {'fg': fg, 'regime': 'fear_or_neutral'}},
            ))
        return specs[: max(1, min(int(limit or 2), 10))]


class LLMProxyStrategyGenerator:
    def __init__(self):
        self.miner = LLMAlphaMiner()

    async def _build_market_frame(self, db) -> Optional[pd.DataFrame]:
        for code in DEFAULT_CODES:
            klines = await db.get_klines(code, limit=180)
            if not klines:
                continue
            frame = pd.DataFrame(klines)
            if not frame.empty and 'close' in frame.columns:
                return frame.tail(120).copy()
        return None

    @staticmethod
    def _candidate_to_spec(candidate: dict) -> Optional[StrategySpec]:
        category = str(candidate.get('category') or 'custom')
        mapping = {
            'momentum': ('momentum', {'lookback': 20, 'threshold': 0.02}),
            'trend': ('ma_cross', {'short_period': 5, 'long_period': 20}),
            'reversal': ('rsi', {'rsi_period': 14, 'oversold': 30, 'overbought': 70}),
            'value': ('value_factor', {'lookback': 60, 'buy_quantile': 0.8, 'sell_quantile': 0.2}),
            'quality': ('quality_factor', {'lookback': 50, 'buy_quantile': 0.75, 'sell_quantile': 0.25}),
            'growth': ('growth_factor', {'lookback': 40, 'buy_quantile': 0.75, 'sell_quantile': 0.25}),
            'volatility': ('ma_cross', {'short_period': 8, 'long_period': 34}),
            'risk_adjusted': ('quality_factor', {'lookback': 45, 'buy_quantile': 0.7, 'sell_quantile': 0.3}),
            'sentiment': ('momentum', {'lookback': 10, 'threshold': 0.015}),
            'event': ('momentum', {'lookback': 8, 'threshold': 0.012}),
        }
        target = mapping.get(category)
        if not target:
            return None
        strategy_type, params = target
        return StrategySpec(
            strategy_type=strategy_type,
            params=params,
            name=str(candidate.get('name') or 'AI 候选策略'),
            description=str(candidate.get('description') or candidate.get('rationale') or ''),
            tags=['llm_proxy', category],
            metadata={
                'generator_type': 'llm_proxy',
                'generation_reason': {
                    'category': category,
                    'formula': candidate.get('formula'),
                    'rationale': candidate.get('rationale'),
                },
                'source_candidate': candidate,
            },
        )

    async def generate(self, db, limit: int = 3) -> list[StrategySpec]:
        frame = await self._build_market_frame(db)
        if frame is None or frame.empty:
            return []
        raw = self.miner.generate_factor_candidates(frame, news_data=None, num_candidates=max(limit, 3))
        specs = []
        for candidate in raw:
            spec = self._candidate_to_spec(candidate)
            if spec is not None:
                specs.append(spec)
            if len(specs) >= limit:
                break
        return specs


class BanditParameterOptimizer:
    @staticmethod
    def _mutate_numeric(value: Any, scale: float) -> Any:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            mutated = max(1, int(round(value * scale)))
            return mutated
        if isinstance(value, float):
            return round(value * scale, 6)
        return value

    async def evolve(self, db, parent_strategy: dict, limit: int = 2) -> list[StrategySpec]:
        metrics = await db.get_strategy_metrics(parent_strategy['id'])
        stats = await db.get_signal_stats(parent_strategy['id'])
        base = dict(parent_strategy.get('params') or {})
        total_signals = int(stats.get('total_signals') or 0)
        hit_rate = float((stats.get('hit_rate') or {}).get(5, (stats.get('hit_rate') or {}).get('5', 0)) or 0)
        scales = [0.9, 1.1, 1.2, 0.8]
        specs: list[StrategySpec] = []
        for idx, scale in enumerate(scales[: max(1, min(limit, 4))], 1):
            mutated = {
                key: self._mutate_numeric(value, scale)
                if isinstance(value, (int, float)) else value
                for key, value in base.items()
            }
            specs.append(StrategySpec(
                strategy_type=parent_strategy.get('strategy_type') or 'momentum',
                params=mutated,
                name=f"RL 进化 {parent_strategy.get('name') or parent_strategy['id']} #{idx}",
                description='基于已有策略表现反馈进行参数扰动。',
                tags=['rl_evolved'],
                metadata={
                    'generator_type': 'rl_bandit',
                    'optimizer_type': 'epsilon_greedy',
                    'generation_reason': {
                        'parent_strategy_id': parent_strategy['id'],
                        'scale': scale,
                        'total_signals': total_signals,
                        'hit_rate_5d': hit_rate,
                        'metrics': metrics,
                    },
                    'parent_strategy_id': parent_strategy['id'],
                },
            ))
        return specs


class MultiAgentStrategyReviewer:
    SUPPORTED_TYPES = {'momentum', 'ma_cross', 'rsi', 'value_factor', 'quality_factor', 'growth_factor'}

    @staticmethod
    def _planner_score(spec: StrategySpec, snapshot: dict) -> float:
        fg = int(snapshot.get('fear_greed_index') or 50)
        stype = spec.strategy_type
        if fg >= 60 and stype in {'momentum', 'ma_cross'}:
            return 0.9
        if fg < 45 and stype in {'rsi', 'value_factor', 'quality_factor'}:
            return 0.85
        return 0.6

    @staticmethod
    def _risk_score(spec: StrategySpec) -> float:
        params = dict(spec.params or {})
        penalty = 0.0
        for key, value in params.items():
            if not isinstance(value, (int, float)):
                continue
            lowered = str(key).lower()
            if 'threshold' in lowered and float(value) > 0.05:
                penalty += 0.25
            if 'period' in lowered and float(value) < 3:
                penalty += 0.15
            if 'lookback' in lowered and float(value) < 5:
                penalty += 0.2
        return max(0.05, 1.0 - penalty)

    @staticmethod
    def _feasibility_score(spec: StrategySpec) -> float:
        return 1.0 if spec.strategy_type in MultiAgentStrategyReviewer.SUPPORTED_TYPES else 0.0

    @staticmethod
    def _novelty_score(spec: StrategySpec) -> float:
        tags = set(spec.tags or [])
        if 'rl_evolved' in tags:
            return 0.82
        if 'llm_proxy' in tags:
            return 0.76
        if 'rule' in tags:
            return 0.62
        return 0.55

    @staticmethod
    def _revise_params(params: dict[str, Any]) -> dict[str, Any]:
        revised: dict[str, Any] = {}
        for key, value in (params or {}).items():
            if isinstance(value, bool):
                revised[key] = value
                continue
            if isinstance(value, int):
                lowered = str(key).lower()
                if 'period' in lowered or 'lookback' in lowered:
                    revised[key] = max(3, min(value, 120))
                else:
                    revised[key] = value
                continue
            if isinstance(value, float):
                lowered = str(key).lower()
                if 'threshold' in lowered:
                    revised[key] = round(min(max(value, 0.003), 0.03), 6)
                else:
                    revised[key] = round(value, 6)
                continue
            revised[key] = value
        return revised

    def review(self, spec: StrategySpec, snapshot: dict) -> tuple[Optional[StrategySpec], dict[str, Any]]:
        planner = self._planner_score(spec, snapshot)
        risk = self._risk_score(spec)
        feasibility = self._feasibility_score(spec)
        novelty = self._novelty_score(spec)
        final_score = round(planner * 0.35 + risk * 0.25 + feasibility * 0.25 + novelty * 0.15, 4)
        decision = 'accept' if final_score >= 0.62 and feasibility > 0 else ('revise' if final_score >= 0.45 and feasibility > 0 else 'reject')
        suggestions: list[str] = []
        if feasibility <= 0:
            suggestions.append('策略类型未注册，拒绝进入自治工厂。')
        if risk < 0.7:
            suggestions.append('参数存在高风险取值，建议收敛阈值与周期。')
        if planner < 0.65:
            suggestions.append('策略与当前市场环境匹配度一般，建议进入观察或微调。')

        reviewed = spec
        if decision == 'revise':
            reviewed = StrategySpec(
                strategy_type=spec.strategy_type,
                params=self._revise_params(spec.params),
                name=spec.name,
                description=spec.description,
                tags=list(dict.fromkeys([*(spec.tags or []), 'committee_revised'])),
                metadata=dict(spec.metadata or {}),
            )
        review = {
            'planner_score': planner,
            'risk_score': risk,
            'feasibility_score': feasibility,
            'novelty_score': novelty,
            'final_score': final_score,
            'decision': decision,
            'suggestions': suggestions,
        }
        if decision == 'reject':
            return None, review
        reviewed.metadata = {
            **dict(reviewed.metadata or {}),
            'committee_review': review,
        }
        return reviewed, review


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
        return await db.save_strategy_generation_experiment({
            'experiment_id': experiment_id,
            'strategy_id': spec.metadata.get('parent_strategy_id'),
            'source': source,
            'generator_type': spec.metadata.get('generator_type') or source,
            'optimizer_type': spec.metadata.get('optimizer_type'),
            'status': 'generated',
            'hypothesis': hypothesis,
            'prompt': str(snapshot.get('date') or date.today()),
            'parameters': spec.params,
            'strategy_spec': {
                'strategy_type': spec.strategy_type,
                'name': spec.name,
                'description': spec.description,
                'tags': spec.tags,
            },
            'evaluation': {
                'source': source,
                'task_run_id': task_run.get('id'),
                'generation_reason': spec.metadata.get('generation_reason') or {},
                'committee_review': spec.metadata.get('committee_review') or {},
            },
            'result': {},
            'parent_experiment_id': None,
            'artifact_id': artifact.get('artifact_id'),
        })

    async def generate_factory_candidates(self, db, snapshot: dict, limit: int = 3) -> dict:
        cycle = await self.run_cycle(db, snapshot=snapshot, limit=limit, source='strategy_factory', auto_submit=False)
        return cycle

    async def run_cycle(
        self,
        db,
        snapshot: Optional[dict] = None,
        limit: int = 3,
        source: str = 'manual',
        parent_strategy_id: Optional[str] = None,
        auto_submit: bool = False,
    ) -> dict:
        snapshot = snapshot or (await db.get_daily_snapshot() if hasattr(db, 'get_daily_snapshot') else None) or {'date': str(date.today())}
        task_run = await db.save_strategy_task_run({
            'task_name': 'strategy_ai_cycle',
            'task_scope': source,
            'task_key': parent_strategy_id or str(snapshot.get('date') or date.today()),
            'status': 'running',
            'trace_id': uuid4().hex[:12],
            'payload': {
                'limit': limit,
                'parent_strategy_id': parent_strategy_id,
                'snapshot_date': snapshot.get('date'),
                'auto_submit': auto_submit,
            },
        })
        try:
            parents = await self._select_parents(db, parent_strategy_id=parent_strategy_id)
            rule_specs = self.rule_generator.generate(snapshot, limit=max(1, limit // 2 or 1))
            llm_specs = await self.llm_generator.generate(db, limit=max(1, limit))
            evolved_specs: list[StrategySpec] = []
            for parent in parents[:2]:
                evolved_specs.extend(await self.optimizer.evolve(db, parent, limit=2))

            merged: list[StrategySpec] = []
            seen = set()
            for spec in [*rule_specs, *llm_specs, *evolved_specs]:
                key = (spec.strategy_type, tuple(sorted((spec.params or {}).items())))
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
                reviewed_specs.append(reviewed_spec)

            experiments = []
            candidates = []
            for spec in reviewed_specs:
                experiment = await self._record_experiment(db, spec, source, snapshot, task_run)
                experiments.append(experiment)
                candidates.append(spec.to_candidate(source, experiment['experiment_id']))

            submit_result = None
            if auto_submit and candidates:
                from .strategy_factory import StrategySubmitter
                submit_result = await StrategySubmitter().submit(candidates, snapshot, db)
                by_experiment = {item.get('experiment_id'): item for item in submit_result.get('items', [])}
                for experiment in experiments:
                    item = by_experiment.get(experiment.get('experiment_id'))
                    await db.save_strategy_generation_experiment({
                        **experiment,
                        'strategy_id': (item or {}).get('strategy_id'),
                        'status': 'accepted' if (item or {}).get('passed') else 'rejected',
                        'result': item or {},
                    })

            result = {
                'task_run_id': task_run.get('id'),
                'snapshot_date': snapshot.get('date'),
                'generated_count': len(candidates),
                'reviewed_count': len(reviewed_specs),
                'rejected_count': rejected_count,
                'committee_reviews': committee_reviews,
                'candidates': candidates,
                'experiments': experiments,
                'submitted': submit_result,
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
