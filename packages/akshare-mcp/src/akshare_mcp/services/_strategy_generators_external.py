"""Strategy generators: rule-based and LLM-proxy strategy candidate generation."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional

import pandas as pd
def _get_strategy_factory_imports():
    from strategy_factory import (
        CATEGORY_MINIMUMS,
        LLM_FAN_OUT_COUNT,
        PIPELINE_MODE,
        PIPELINE_STAGE_TIMEOUTS,
        PIPELINE_STAGE_TIMEOUT_SEC,
        extract_event_context as _extract_event_context,
        preferred_strategy_types_for_factor,
    )
    from strategy_factory.domain.targets import _apply_target_symbol_policy, _normalize_research_task_contract
    return {
        "CATEGORY_MINIMUMS": CATEGORY_MINIMUMS,
        "LLM_FAN_OUT_COUNT": LLM_FAN_OUT_COUNT,
        "PIPELINE_MODE": PIPELINE_MODE,
        "PIPELINE_STAGE_TIMEOUTS": PIPELINE_STAGE_TIMEOUTS,
        "PIPELINE_STAGE_TIMEOUT_SEC": PIPELINE_STAGE_TIMEOUT_SEC,
        "extract_event_context": _extract_event_context,
        "preferred_strategy_types_for_factor": preferred_strategy_types_for_factor,
        "apply_target_symbol_policy": _apply_target_symbol_policy,
        "normalize_research_task_contract": _normalize_research_task_contract,
    }


import functools as _functools


@_functools.lru_cache(maxsize=1)
def _sf():
    return _get_strategy_factory_imports()


class _LazyProxy:
    """Module-level proxy to defer strategy_factory imports until first access."""
    def __getattr__(self, name):
        return _sf()[name]

_lazy = _LazyProxy()


def __getattr__(name):
    _map = {
        "CATEGORY_MINIMUMS": "CATEGORY_MINIMUMS",
        "LLM_FAN_OUT_COUNT": "LLM_FAN_OUT_COUNT",
        "PIPELINE_MODE": "PIPELINE_MODE",
        "_extract_event_context": "extract_event_context",
        "preferred_strategy_types_for_factor": "preferred_strategy_types_for_factor",
        "_apply_target_symbol_policy": "apply_target_symbol_policy",
        "_normalize_research_task_contract": "normalize_research_task_contract",
    }
    if name in _map:
        return _sf()[_map[name]]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


CATEGORY_MINIMUMS = _sf()["CATEGORY_MINIMUMS"]
LLM_FAN_OUT_COUNT = _sf()["LLM_FAN_OUT_COUNT"]
PIPELINE_MODE = _sf()["PIPELINE_MODE"]
_extract_event_context = _sf()["extract_event_context"]
preferred_strategy_types_for_factor = _sf()["preferred_strategy_types_for_factor"]
_apply_target_symbol_policy = _sf()["apply_target_symbol_policy"]
_normalize_research_task_contract = _sf()["normalize_research_task_contract"]

from .llm_alpha import LLMAlphaMiner
from .data_pipeline import normalize_klines
from .strategy_dsl import compile_strategy_blueprint
from .strategy_llm_provider import StrategyLLMProvider, get_strategy_llm_provider
from .strategy_pipeline import get_strategy_pipeline
from .strategy_spec import (
    DEFAULT_CODES,
    RESEARCH_CANDIDATE_POOL_LIMIT,
    RESEARCH_FINANCIAL_DETAIL_LIMIT,
    RESEARCH_KLINE_SCAN_LIMIT,
    RESEARCH_SYMBOL_DETAIL_LIMIT,
    RESEARCH_UNIVERSE_PAGE_SIZE,
    RESEARCH_UNIVERSE_SCAN_LIMIT,
    StrategySpec,
)

logger = logging.getLogger(__name__)


def _resolve_strategy_generators_imports() -> dict[str, Any]:
    try:
        from . import strategy_generators as public_module

        sf_fn = getattr(public_module, "_sf", _sf)
        return dict(sf_fn() or {})
    except Exception:
        return dict(_sf() or {})


class RuleStrategyGenerator:
    @staticmethod
    def _factor_research_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
        factor_research = dict(snapshot.get('factor_research') or {})
        summary = dict(factor_research.get('summary') or {})
        return {
            'top_factor_names': list(summary.get('top_factor_names') or factor_research.get('active_factors') or [])[:3],
            'preferred_strategy_types': [
                str(item).strip()
                for item in list(factor_research.get('preferred_strategy_types') or [])
                if str(item).strip()
            ][:4],
            'degraded': bool(factor_research.get('degraded')),
        }

    @classmethod
    def _build_rule_spec(
        cls,
        strategy_type: str,
        *,
        fg: int,
        regime: str,
        source: str,
        factor_summary: dict[str, Any],
    ) -> Optional[StrategySpec]:
        templates: dict[str, dict[str, Any]] = {
            'momentum': {
                'params': {'lookback': 15, 'threshold': 0.018},
                'name': 'AI 动量强化',
                'description': '高情绪或因子偏强阶段偏向动量追随。',
            },
            'ma_cross': {
                'params': {'short_period': 6, 'long_period': 24},
                'name': 'AI 均线趋势',
                'description': '趋势确认阶段用均线结构过滤噪音。',
            },
            'rsi': {
                'params': {'rsi_period': 14, 'oversold': 28, 'overbought': 72},
                'name': 'AI RSI 反转',
                'description': '低情绪或反转因子活跃阶段偏向均值回归。',
            },
            'value_factor': {
                'params': {'lookback': 60, 'buy_quantile': 0.8, 'sell_quantile': 0.2},
                'name': 'AI 价值回归',
                'description': '估值修复阶段偏向价值/反转组合。',
            },
            'quality_factor': {
                'params': {'lookback': 50, 'buy_quantile': 0.75, 'sell_quantile': 0.25},
                'name': 'AI 质量精选',
                'description': '质量因子占优阶段偏向盈利能力与稳健性筛选。',
            },
            'growth_factor': {
                'params': {'lookback': 40, 'buy_quantile': 0.78, 'sell_quantile': 0.22},
                'name': 'AI 成长加速',
                'description': '成长因子活跃阶段偏向高景气扩张。',
            },
            'multi_factor': {
                'params': {'factor_weights': {'value': 0.4, 'quality': 0.35, 'momentum': 0.25}},
                'name': 'AI 多因子平衡',
                'description': '因子共振时优先使用多因子组合。',
            },
            'macro_timing': {
                'params': {'risk_on_threshold': 0.55, 'rebalance_days': 10},
                'name': 'AI 宏观择时',
                'description': '波动与风险偏好分化阶段偏向宏观择时。',
            },
        }
        template = templates.get(strategy_type)
        if template is None:
            return None
        return StrategySpec(
            strategy_type=strategy_type,
            params=dict(template['params']),
            name=str(template['name']),
            description=str(template['description']),
            tags=['rule', 'factor_research' if source == 'factor_research' else 'fear_greed'],
            metadata={
                'generator_type': 'rule',
                'generation_reason': {
                    'source': source,
                    'fg': fg,
                    'regime': regime,
                    'factor_research': factor_summary,
                },
            },
        )

    def generate(
        self,
        snapshot: dict,
        limit: int = 2,
        *,
        preferred_types: Optional[list[str]] = None,
    ) -> list[StrategySpec]:
        fg = int(snapshot.get('fear_greed_index') or 50)
        regime = 'greed' if fg >= 60 else ('fear' if fg < 45 else 'neutral')
        factor_summary = self._factor_research_summary(snapshot)
        factor_preferred_types = [
            item for item in factor_summary.get('preferred_strategy_types') or []
            if item in CATEGORY_MINIMUMS
        ]
        requested_types = [
            str(item).strip()
            for item in list(preferred_types or [])
            if str(item).strip() in CATEGORY_MINIMUMS
        ]
        if not factor_preferred_types:
            for factor_name in list(factor_summary.get('top_factor_names') or []):
                for strategy_type in preferred_strategy_types_for_factor(factor_name):
                    if strategy_type in CATEGORY_MINIMUMS and strategy_type not in factor_preferred_types:
                        factor_preferred_types.append(strategy_type)
        regime_defaults = (
            ['momentum', 'ma_cross', 'quality_factor']
            if regime == 'greed'
            else ['value_factor', 'quality_factor', 'rsi']
        )
        preferred_anchor = requested_types or factor_preferred_types
        strategy_order = list(dict.fromkeys([*requested_types, *factor_preferred_types, *regime_defaults]))
        specs: list[StrategySpec] = []
        for index, strategy_type in enumerate(strategy_order):
            source = 'factor_research' if index < len(preferred_anchor) and preferred_anchor else 'fear_greed'
            spec = self._build_rule_spec(
                strategy_type,
                fg=fg,
                regime=regime,
                source=source,
                factor_summary=factor_summary,
            )
            if spec is not None:
                specs.append(spec)
        return specs[: max(1, min(int(limit or 2), 10))]


class _LLMProxyStrategyGeneratorExternalMixin:
        @staticmethod
        def _dedupe_specs(specs: list[StrategySpec]) -> list[StrategySpec]:
            unique: list[StrategySpec] = []
            seen: set[tuple[str, str]] = set()
            for spec in list(specs or []):
                key = (
                    str(spec.strategy_type or ''),
                    json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str),
                )
                if key in seen:
                    continue
                seen.add(key)
                unique.append(spec)
            return unique

        @staticmethod
        def _pipeline_run_timeout_sec() -> float:
            configured = os.getenv('STRATEGY_LLM_PIPELINE_RUN_TIMEOUT_SEC')
            if configured is not None:
                try:
                    value = float(configured or 20)
                except Exception:
                    value = 20.0
                return max(5.0, min(value, 600.0))

            stage_default = 10.0
            stage_timeouts: dict[str, Any] = {}
            try:
                strategy_generator_imports = _resolve_strategy_generators_imports()
                stage_default = float(strategy_generator_imports.get('PIPELINE_STAGE_TIMEOUT_SEC') or 10.0)
                stage_timeouts = dict(strategy_generator_imports.get('PIPELINE_STAGE_TIMEOUTS') or {})
            except Exception:
                stage_default = 10.0
                stage_timeouts = {}

            total_stage_budget = 0.0
            for timeout in stage_timeouts.values():
                try:
                    total_stage_budget += max(1.0, float(timeout or 0.0))
                except Exception:
                    total_stage_budget += max(1.0, stage_default)
            if total_stage_budget <= 0.0:
                total_stage_budget = max(5.0, stage_default * 5.0)

            buffer_sec = max(5.0, min(60.0, total_stage_budget * 0.2))
            return max(5.0, min(total_stage_budget + buffer_sec, 600.0))

        async def _run_external_provider_request(
            self,
            *,
            snapshot: dict[str, Any],
            frame,
            frame_cache: dict[str, pd.DataFrame],
            research_context: dict[str, Any],
            parent_strategies: list[dict[str, Any]],
            history_summary: list[dict[str, Any]],
            research_task: Optional[dict[str, Any]],
            request_limit: int,
            request_index: int,
        ) -> dict[str, Any]:
            try:
                provider_payload = await self.external_provider.generate_candidates(
                    snapshot=snapshot or {},
                    market_frame=frame,
                    research_context=research_context,
                    parent_strategies=list(parent_strategies or []),
                    history_summary=history_summary,
                    research_task=research_task,
                    limit=request_limit,
                )
                request_metrics = dict((provider_payload or {}).get('request_metrics') or {})
                analysis = dict((provider_payload or {}).get('analysis') or {})
                returned_candidates = list((provider_payload or {}).get('candidates') or [])
                all_specs: list[StrategySpec] = []
                viable_specs: list[StrategySpec] = []
                for candidate in returned_candidates:
                    spec = self._build_external_candidate_spec(
                        candidate,
                        provider_payload or {},
                        frame_cache,
                        frame,
                        research_task=research_task,
                    )
                    if spec is None:
                        continue
                    all_specs.append(spec)
                    if self._is_viable_external_spec(spec):
                        viable_specs.append(spec)
                viable_specs.sort(key=self._spec_preflight_score, reverse=True)
                all_specs.sort(key=self._spec_preflight_score, reverse=True)
                non_executable_candidate_count = max(0, len(returned_candidates) - len(all_specs))
                return {
                    'status': 'succeeded',
                    'request_index': request_index,
                    'analysis': analysis,
                    'request_report': {
                        'request_index': request_index,
                        'request_limit': request_limit,
                        'status': 'succeeded',
                        'returned_candidate_count': len(returned_candidates),
                        'compiled_candidate_count': len(all_specs),
                        'non_executable_candidate_count': non_executable_candidate_count,
                        'viable_candidate_count': len(viable_specs),
                        'candidate_names': [str((item or {}).get('name') or '') for item in returned_candidates[:4]],
                        'candidate_preflight': [
                            {
                                'name': spec.name,
                                'score': self._spec_preflight_score(spec),
                                'entry_count': int(dict(spec.metadata.get('dsl_activity') or {}).get('entry_count') or 0),
                                'exit_count': int(dict(spec.metadata.get('dsl_activity') or {}).get('exit_count') or 0),
                                'target_symbols': list(spec.metadata.get('target_symbols') or []),
                                'preflight_symbol': spec.metadata.get('preflight_symbol'),
                            }
                            for spec in all_specs[:4]
                        ],
                        'analysis': analysis,
                        'request_metrics': request_metrics,
                    },
                    'successful_without_specs': bool(returned_candidates) and not all_specs,
                    'all_specs': all_specs,
                    'viable_specs': viable_specs,
                    'exception': None,
                }
            except Exception as exc:
                metrics = dict(getattr(exc, 'metrics', {}) or {})
                logger.warning(
                    'LLMProxyStrategyGenerator external provider failed at request_index=%s limit=%s, retrying/fallback: %r',
                    request_index,
                    request_limit,
                    exc,
                )
                return {
                    'status': 'failed',
                    'request_index': request_index,
                    'analysis': {},
                    'request_report': {
                        'request_index': request_index,
                        'request_limit': request_limit,
                        'status': 'failed',
                        'error_type': metrics.get('last_error_type') or exc.__class__.__name__,
                        'error': metrics.get('last_error') or str(exc) or exc.__class__.__name__,
                        'request_metrics': metrics,
                    },
                    'successful_without_specs': False,
                    'all_specs': [],
                    'viable_specs': [],
                    'exception': exc,
                }

        async def _frame_from_codes(self, db, codes: list[str], limit: int = 180) -> Optional[pd.DataFrame]:
            for code in list(dict.fromkeys([str(item or '').strip() for item in list(codes or []) if str(item or '').strip()])):
                try:
                    klines = await db.get_klines(code, limit=limit)
                except Exception:
                    klines = []
                if not klines:
                    continue
                frame = pd.DataFrame(normalize_klines(klines))
                if not frame.empty and 'close' in frame.columns:
                    return frame.tail(120).copy()
            return None

        @staticmethod
        def _build_synthetic_market_frame(research_context: Optional[dict[str, Any]] = None) -> Optional[pd.DataFrame]:
            context = dict(research_context or {})
            sources = list(context.get('symbol_insights') or []) + list(context.get('candidate_universe') or [])
            close_values = []
            volume_values = []
            for item in sources:
                try:
                    close = float((item or {}).get('close') or 0.0)
                except Exception:
                    close = 0.0
                if close <= 0:
                    continue
                close_values.append(close)
                try:
                    volume = float((item or {}).get('volume') or (item or {}).get('market_cap') or 0.0)
                except Exception:
                    volume = 0.0
                volume_values.append(max(volume, 1.0))
                if len(close_values) >= 12:
                    break
            if not close_values:
                return None
            rows = max(24, len(close_values) * 4)
            closes = []
            volumes = []
            for idx in range(rows):
                base_close = close_values[idx % len(close_values)]
                drift = 1.0 + ((idx % 6) - 2) * 0.0025
                closes.append(round(base_close * drift, 6))
                base_volume = volume_values[idx % len(volume_values)] if volume_values else 1.0
                volumes.append(float(max(base_volume * (1.0 + ((idx % 5) - 2) * 0.03), 1.0)))
            return pd.DataFrame({
                'open': closes,
                'high': [value * 1.003 for value in closes],
                'low': [value * 0.997 for value in closes],
                'close': closes,
                'volume': volumes,
            })

        async def _build_market_frame(self, db, research_task: Optional[dict[str, Any]] = None) -> Optional[pd.DataFrame]:
            research_task = dict(research_task or {})
            target_codes = self._normalize_code_list(research_task.get('target_symbols'))
            target_frame = await self._frame_from_codes(db, target_codes, limit=180)
            if target_frame is not None:
                return target_frame

            primary_codes: list[str] = []
            if hasattr(db, 'list_stock_universe'):
                try:
                    rows = await db.list_stock_universe(limit=3, offset=0)
                    primary_codes = [str((row or {}).get('code') or '').strip() for row in rows if str((row or {}).get('code') or '').strip()]
                except Exception:
                    primary_codes = []
            return await self._frame_from_codes(db, [*primary_codes, *DEFAULT_CODES], limit=180)

        async def _build_symbol_frame_cache(self, db, research_context: Optional[dict[str, Any]] = None, research_task: Optional[dict[str, Any]] = None) -> dict[str, pd.DataFrame]:
            cache: dict[str, pd.DataFrame] = {}
            research_context = dict(research_context or {})
            research_task = dict(research_task or {})
            codes = self._normalize_code_list([
                research_task.get('target_symbols'),
                [item.get('code') for item in list(research_context.get('candidate_universe') or [])],
                [item.get('code') for item in list(research_context.get('symbol_insights') or [])],
            ], limit=10)
            for code in codes:
                frame = await self._frame_from_codes(db, [code], limit=180)
                if frame is not None:
                    cache[code] = frame
            return cache

        def _candidate_frame_codes(
            self,
            candidate: dict[str, Any],
            research_task: Optional[dict[str, Any]] = None,
        ) -> list[str]:
            research_task = dict(research_task or {})
            return self._normalize_code_list([
                candidate.get('target_symbols'),
                candidate.get('stock_pool'),
                ((candidate.get('dsl') or {}).get('metadata') or {}).get('target_symbols'),
                research_task.get('target_symbols'),
            ], limit=10)

        def _build_external_candidate_spec(
            self,
            candidate: dict[str, Any],
            provider_payload: dict[str, Any],
            frame_cache: dict[str, pd.DataFrame],
            default_frame: Optional[pd.DataFrame],
            research_task: Optional[dict[str, Any]] = None,
        ) -> Optional[StrategySpec]:
            frame_candidates: list[tuple[str, pd.DataFrame]] = []
            for code in self._candidate_frame_codes(candidate, research_task=research_task):
                frame = frame_cache.get(code)
                if frame is not None and not frame.empty:
                    frame_candidates.append((code, frame))
            if not frame_candidates and default_frame is not None and not default_frame.empty:
                frame_candidates.append(('__default__', default_frame))

            best_spec: Optional[StrategySpec] = None
            best_rank: Optional[tuple[float, int, int]] = None
            for code, frame in frame_candidates:
                spec = self._external_candidate_to_spec(candidate, provider_payload or {}, market_frame=frame)
                if spec is None:
                    continue
                metadata = dict(spec.metadata or {})
                metadata['preflight_symbol'] = None if code == '__default__' else code
                spec.metadata = metadata
                activity = dict(metadata.get('dsl_activity') or {})
                rank = (
                    self._spec_preflight_score(spec),
                    int(min(activity.get('entry_count') or 0, activity.get('exit_count') or 0)),
                    int(activity.get('active_days') or 0),
                )
                if best_rank is None or rank > best_rank:
                    best_spec = spec
                    best_rank = rank
            return best_spec
