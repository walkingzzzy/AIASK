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


class _LLMProxyStrategyGeneratorSpecsMixin:
        def _fallback_variant_seed(task: dict[str, Any], target_symbols: list[str], candidate: dict[str, Any]) -> int:
            seed_text = "|".join([
                str(task.get('task_id') or ''),
                str(task.get('theme') or ''),
                str(task.get('opportunity_type') or ''),
                str(candidate.get('category') or ''),
                *[str(code) for code in list(target_symbols or [])[:6]],
            ])
            return sum(ord(ch) for ch in seed_text if ch)

        def _adapt_local_fallback_params(
            cls,
            strategy_type: str,
            params: dict[str, Any],
            task: dict[str, Any],
            candidate: dict[str, Any],
            target_symbols: list[str],
        ) -> tuple[dict[str, Any], dict[str, Any]]:
            adapted = dict(params or {})
            if not task:
                return adapted, {
                    'variant_seed': 0,
                    'profile': 'default',
                    'task_opportunity_type': None,
                }
            opportunity_type = str(task.get('opportunity_type') or 'default').strip().lower() or 'default'
            variant_seed = cls._fallback_variant_seed(task, target_symbols, candidate)
            bucket = variant_seed % 5
            symbol_count = max(1, len(target_symbols or []))

            if strategy_type == 'momentum':
                lookback_map = {
                    'sector_breakout': [8, 10, 12, 15, 18],
                    'rotation_balanced': [14, 18, 20, 24, 30],
                    'industry_leadership': [10, 12, 16, 20, 24],
                    'factor_acceleration': [6, 8, 10, 12, 15],
                    'default': [10, 14, 18, 20, 24],
                }
                threshold_map = {
                    'sector_breakout': [0.008, 0.01, 0.012, 0.015, 0.018],
                    'rotation_balanced': [0.006, 0.008, 0.01, 0.012, 0.015],
                    'industry_leadership': [0.007, 0.009, 0.011, 0.013, 0.016],
                    'factor_acceleration': [0.005, 0.007, 0.009, 0.011, 0.013],
                    'default': [0.008, 0.01, 0.012, 0.015, 0.018],
                }
                lookbacks = lookback_map.get(opportunity_type, lookback_map['default'])
                thresholds = threshold_map.get(opportunity_type, threshold_map['default'])
                adapted['lookback'] = int(lookbacks[bucket])
                adapted['threshold'] = round(float(thresholds[(bucket + symbol_count) % len(thresholds)]), 4)
            elif strategy_type == 'ma_cross':
                short_map = {
                    'sector_breakout': [4, 5, 6, 8, 10],
                    'rotation_balanced': [5, 6, 8, 10, 12],
                    'industry_leadership': [4, 6, 7, 9, 11],
                    'default': [5, 6, 8, 10, 12],
                }
                long_map = {
                    'sector_breakout': [18, 20, 24, 30, 34],
                    'rotation_balanced': [24, 30, 36, 40, 48],
                    'industry_leadership': [20, 24, 28, 32, 40],
                    'default': [20, 24, 30, 36, 40],
                }
                shorts = short_map.get(opportunity_type, short_map['default'])
                longs = long_map.get(opportunity_type, long_map['default'])
                adapted['short_period'] = int(shorts[bucket])
                adapted['long_period'] = int(max(longs[(bucket + 1) % len(longs)], adapted['short_period'] + 6))
            elif strategy_type == 'rsi':
                adapted['rsi_period'] = int([6, 8, 10, 12, 14][bucket])
                adapted['oversold'] = int([24, 26, 28, 30, 32][bucket])
                adapted['overbought'] = int([68, 70, 72, 74, 76][bucket])
            elif strategy_type in {'quality_factor', 'value_factor', 'growth_factor'}:
                lookbacks = [24, 30, 36, 45, 60] if opportunity_type == 'sector_breakout' else [30, 40, 50, 60, 72]
                buy_quantiles = [0.58, 0.62, 0.66, 0.7, 0.75]
                sell_quantiles = [0.22, 0.26, 0.3, 0.34, 0.38]
                adapted['lookback'] = int(lookbacks[bucket])
                adapted['buy_quantile'] = round(float(buy_quantiles[bucket]), 4)
                adapted['sell_quantile'] = round(float(sell_quantiles[(bucket + 2) % len(sell_quantiles)]), 4)

            profile = {
                'variant_seed': variant_seed,
                'variant_bucket': bucket,
                'profile': opportunity_type,
                'task_opportunity_type': opportunity_type,
                'symbol_count': symbol_count,
            }
            return adapted, profile

        def _local_category_rank(category: str, research_task: Optional[dict[str, Any]] = None) -> tuple[int, int]:
            task = _normalize_research_task_contract(research_task)
            opportunity_type = str(task.get('opportunity_type') or '').strip().lower()
            task_source = str(task.get('task_source') or '').strip().lower()
            strategy_preferences = [str(item).strip().lower() for item in list(task.get('preferred_strategy_types') or task.get('strategy_preferences') or []) if str(item).strip()]

            category_to_types = {
                'momentum': ('momentum',),
                'event': ('momentum',),
                'sentiment': ('momentum',),
                'trend': ('ma_cross',),
                'volatility': ('ma_cross',),
                'reversal': ('rsi',),
                'quality': ('quality_factor',),
                'risk_adjusted': ('quality_factor',),
                'value': ('value_factor',),
                'growth': ('growth_factor',),
                'liquidity': ('growth_factor', 'momentum'),
            }
            if opportunity_type in {'sector_breakout', 'trend_expansion', 'industry_leadership'} or task_source == 'event_driven':
                preferred_categories = ['event', 'momentum', 'trend', 'growth', 'liquidity', 'sentiment', 'quality', 'risk_adjusted', 'volatility', 'value', 'reversal']
            elif opportunity_type == 'oversold_repair':
                preferred_categories = ['reversal', 'value', 'quality', 'risk_adjusted', 'trend', 'momentum', 'event', 'sentiment', 'growth', 'liquidity', 'volatility']
            elif opportunity_type == 'factor_acceleration':
                preferred_categories = ['quality', 'growth', 'value', 'momentum', 'trend', 'risk_adjusted', 'event', 'sentiment', 'liquidity', 'volatility', 'reversal']
            else:
                preferred_categories = ['momentum', 'trend', 'quality', 'value', 'growth', 'event', 'sentiment', 'risk_adjusted', 'liquidity', 'volatility', 'reversal']

            prioritize_opportunity = task_source == 'event_driven' and opportunity_type in {'sector_breakout', 'trend_expansion', 'industry_leadership'}
            if strategy_preferences and not prioritize_opportunity:
                matched_index = len(strategy_preferences)
                for idx, strategy_type in enumerate(category_to_types.get(category, ())):
                    if strategy_type in strategy_preferences:
                        matched_index = min(matched_index, strategy_preferences.index(strategy_type))
                if matched_index < len(strategy_preferences):
                    return (matched_index, preferred_categories.index(category) if category in preferred_categories else len(preferred_categories))

            return (
                len(strategy_preferences) + 1,
                preferred_categories.index(category) if category in preferred_categories else len(preferred_categories),
            )

        def _local_candidate_to_spec(cls, candidate: dict, research_task: Optional[dict[str, Any]] = None) -> Optional[StrategySpec]:
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
            task = _normalize_research_task_contract(research_task)
            event_context = _extract_event_context(task)
            task_source = str(task.get('task_source') or '').strip().lower()
            target_resolution = _apply_target_symbol_policy([
                candidate.get('target_symbols'),
                candidate.get('stock_pool'),
            ], task, fallback_symbols=[task.get('target_symbols'), task.get('stock_pool')], limit=8)
            target_symbols = list(target_resolution.get('target_symbols') or [])
            stock_pool = cls._normalize_stock_pool(candidate.get('stock_pool'), target_symbols)
            strategy_type, params = target
            params, fallback_profile = cls._adapt_local_fallback_params(strategy_type, params, task, candidate, target_symbols)
            validation_profile = {
                'profile': 'event_trade_validation' if task.get('validation_focus') == 'event_target_only' else 'trade_rule_validation',
                'validation_focus': task.get('validation_focus'),
                'primary_validation_layer': 'target' if task.get('validation_focus') == 'event_target_only' else 'combined',
            }
            holding_horizon = dict(task.get('holding_window') or {})
            risk_rules = {
                'stop_loss_pct': 0.08 if task_source == 'event_driven' else 0.1,
                'take_profit_pct': 0.18 if task_source == 'event_driven' else 0.2,
                'max_holding_days': int(holding_horizon.get('max_days') or 20),
            }
            tags = ['local_rule_v1', 'llm_proxy_fallback', category]
            if target_symbols:
                tags.append('targeted_universe')
            return StrategySpec(
                strategy_type=strategy_type,
                params=params,
                name=str(candidate.get('name') or 'AI 候选策略'),
                description=str(candidate.get('description') or candidate.get('rationale') or ''),
                tags=list(dict.fromkeys(tags)),
                metadata={
                    'generator_type': str(candidate.get('_engine') or candidate.get('engine') or 'local_rule_v1'),
                    'generation_reason': {
                        'source': 'event_driven_local_fallback' if task_source == 'event_driven' else 'llm_proxy_local_fallback',
                        'category': category,
                        'formula': candidate.get('formula'),
                        'rationale': candidate.get('rationale'),
                        'engine': candidate.get('_engine') or candidate.get('engine') or 'local_rule_v1',
                        'fallback_reason': 'external_llm_unavailable',
                        'target_symbols': list(target_symbols),
                        'stock_pool': stock_pool,
                        'fallback_profile': fallback_profile,
                    },
                    'target_symbols': list(target_symbols),
                    'stock_pool': stock_pool,
                    'selection_logic': list(task.get('selection_logic') or []),
                    'research_scope': dict(task.get('analysis_scope') or {}),
                    'research_task': task,
                    'event_context': event_context,
                    'hypothesis': str(candidate.get('rationale') or candidate.get('description') or task.get('rationale') or ''),
                    'holding_horizon': holding_horizon,
                    'trade_plan': {
                        'entry_bias': 'event_follow_through' if task_source == 'event_driven' else 'signal_confirmed',
                        'exit_bias': 'time_stop_or_signal_reversal',
                    },
                    'risk_rules': risk_rules,
                    'position_sizing': {
                        'mode': 'equal_weight' if len(target_symbols) > 1 else 'single_name',
                        'position_assumption': 'equal_weight_proxy' if len(target_symbols) > 1 else 'single_name_full_notional',
                    },
                    'execution_notes': 'use liquid names and respect tradability filter',
                    'rebalance_rule': {'mode': 'event_driven_hold' if task_source == 'event_driven' else 'signal_rebalance'},
                    'portfolio_spec': {
                        'position_assumption': 'equal_weight_proxy' if len(target_symbols) > 1 else 'single_name_full_notional',
                        'target_weight_scheme': 'equal_weight' if len(target_symbols) > 1 else 'single_name',
                    },
                    'execution_assumptions': {
                        'commission_rate': 0.00025,
                        'slippage_bps': 8 if task_source == 'event_driven' else 5,
                        'tradability_filter': True,
                        'slippage_model': 'fixed',
                    },
                    'validation_profile': validation_profile,
                    'targeting_policy': {
                        'target_symbol_policy': task.get('target_symbol_policy'),
                        'universe_expansion_policy': task.get('universe_expansion_policy'),
                        'validation_focus': task.get('validation_focus'),
                    },
                    'constraint_check': dict(target_resolution.get('constraint_check') or {}),
                    'fallback_profile': fallback_profile,
                    'source_candidate': candidate,
                },
            )

        def _normalize_stock_pool(cls, payload: Any, target_symbols: list[str]) -> dict[str, Any]:
            if isinstance(payload, dict):
                symbols = cls._normalize_code_list(payload.get('symbols') or payload.get('codes') or payload.get('stock_codes') or target_symbols)
                return {
                    'selection_mode': str(payload.get('selection_mode') or payload.get('mode') or ('explicit' if symbols else 'screened')).strip() or 'screened',
                    'symbols': symbols,
                    'filters': dict(payload.get('filters') or {}),
                    'rationale': payload.get('rationale'),
                }
            return {
                'selection_mode': 'explicit' if target_symbols else 'screened',
                'symbols': list(target_symbols),
                'filters': {},
                'rationale': None,
            }

        def _external_candidate_to_spec(cls, candidate: dict, provider_payload: dict, market_frame: Optional[pd.DataFrame] = None) -> Optional[StrategySpec]:
            normalized_candidate = StrategyLLMProvider._normalize_candidate_payload(
                candidate,
                research_task=provider_payload.get('research_task') or {},
            )
            if normalized_candidate:
                candidate = {
                    **candidate,
                    **normalized_candidate,
                    'dsl': normalized_candidate.get('dsl') or candidate.get('dsl'),
                }
            try:
                compiled = compile_strategy_blueprint(candidate, market_frame=market_frame, tune_for_factory=True)
            except Exception:
                return None
            compiled_meta = dict(compiled.get('metadata') or {})
            activity = dict(compiled_meta.get('dsl_activity') or {})
            analysis = dict(provider_payload.get('analysis') or {})
            research_context = dict(provider_payload.get('research_context') or {})
            research_task = _normalize_research_task_contract(provider_payload.get('research_task') or {})
            target_resolution = _apply_target_symbol_policy([
                candidate.get('target_symbols'),
                candidate.get('stock_pool'),
                ((candidate.get('dsl') or {}).get('metadata') or {}).get('target_symbols'),
                ((candidate.get('dsl') or {}).get('metadata') or {}).get('stock_pool'),
            ], research_task, fallback_symbols=[
                ((provider_payload.get('research_context') or {}).get('candidate_universe_symbols') if isinstance(provider_payload.get('research_context'), dict) else None),
                research_task.get('target_symbols'),
            ], limit=8)
            target_symbols = list(target_resolution.get('target_symbols') or [])
            stock_pool = cls._normalize_stock_pool(candidate.get('stock_pool'), target_symbols)
            selection_logic = candidate.get('selection_logic') or analysis.get('selection_notes') or []
            if isinstance(selection_logic, str):
                selection_logic = [selection_logic]
            elif not isinstance(selection_logic, list):
                selection_logic = [selection_logic] if selection_logic else []
            params = dict(compiled.get('params') or {})
            if target_symbols and str(compiled.get('strategy_type') or 'dsl_rule') == 'dsl_rule':
                dsl = dict(params.get('dsl') or {})
                dsl_metadata = dict(dsl.get('metadata') or {})
                dsl_metadata['target_symbols'] = list(target_symbols)
                dsl_metadata['stock_pool'] = stock_pool
                dsl['metadata'] = dsl_metadata
                params['dsl'] = dsl
            metadata = {
                **compiled_meta,
                'generator_type': 'external_llm',
                'hypothesis': str(candidate.get('hypothesis') or candidate.get('rationale') or candidate.get('description') or ''),
                'holding_horizon': dict(candidate.get('holding_horizon') or research_task.get('holding_window') or {}),
                'trade_plan': dict(candidate.get('trade_plan') or {}),
                'risk_rules': dict(candidate.get('risk_rules') or ((params.get('dsl') or {}).get('risk_rules') or {})),
                'position_sizing': dict(candidate.get('position_sizing') or {}),
                'execution_notes': candidate.get('execution_notes'),
                'rebalance_rule': dict(candidate.get('rebalance_rule') or {'mode': 'event_driven_hold' if research_task.get('task_source') == 'event_driven' else 'signal_rebalance'}),
                'portfolio_spec': dict(candidate.get('portfolio_spec') or {
                    'position_assumption': 'equal_weight_proxy' if len(target_symbols) > 1 else 'single_name_full_notional',
                    'target_weight_scheme': 'equal_weight' if len(target_symbols) > 1 else 'single_name',
                }),
                'execution_assumptions': dict(candidate.get('execution_assumptions') or {
                    'commission_rate': 0.00025,
                    'slippage_bps': 8 if research_task.get('task_source') == 'event_driven' else 5,
                    'tradability_filter': True,
                    'slippage_model': 'fixed',
                }),
                'validation_profile': dict(candidate.get('validation_profile') or {
                    'profile': 'event_trade_validation' if research_task.get('validation_focus') == 'event_target_only' else 'trade_rule_validation',
                    'validation_focus': research_task.get('validation_focus'),
                    'primary_validation_layer': 'target' if research_task.get('validation_focus') == 'event_target_only' else 'combined',
                }),
                'targeting_policy': dict(candidate.get('targeting_policy') or {
                    'target_symbol_policy': research_task.get('target_symbol_policy'),
                    'universe_expansion_policy': research_task.get('universe_expansion_policy'),
                    'validation_focus': research_task.get('validation_focus'),
                }),
                'constraint_check': dict(candidate.get('constraint_check') or target_resolution.get('constraint_check') or {}),
                'generation_reason': {
                    'provider': provider_payload.get('provider'),
                    'model': provider_payload.get('model'),
                    'rationale': candidate.get('rationale'),
                    'analysis': analysis,
                    'research_context': research_context,
                    'constraint_check': dict(candidate.get('constraint_check') or target_resolution.get('constraint_check') or {}),
                    'target_symbols': list(target_symbols),
                    'stock_pool': stock_pool,
                    'selection_logic': list(selection_logic),
                    'dsl_summary': (params or {}).get('dsl') or {},
                    'dsl_activity': activity,
                    'dsl_tuning': compiled_meta.get('dsl_tuning') or {},
                },
                'llm_prompt': provider_payload.get('prompt') or {},
                'llm_analysis': analysis,
                'llm_research_context': research_context,
                'llm_response': {
                    'provider': provider_payload.get('provider'),
                    'model': provider_payload.get('model'),
                    'analysis': analysis,
                    'research_context': research_context,
                    'research_task': provider_payload.get('research_task') or {},
                    'candidate': candidate,
                    'content': provider_payload.get('content'),
                    'request_metrics': provider_payload.get('request_metrics') or {},
                },
                'target_symbols': list(target_symbols),
                'stock_pool': stock_pool,
                'selection_logic': list(selection_logic),
                'research_scope': dict(research_context.get('analysis_scope') or {}),
                'research_task': research_task,
                'source_candidate': candidate,
            }
            tags = ['external_llm', *(compiled.get('tags') or []), *(candidate.get('tags') or [])]
            if target_symbols:
                tags.append('targeted_universe')
            return StrategySpec(
                strategy_type=str(compiled.get('strategy_type') or 'dsl_rule'),
                params=params,
                name=str(compiled.get('name') or candidate.get('name') or '外部 AI 策略'),
                description=str(compiled.get('description') or candidate.get('description') or candidate.get('rationale') or ''),
                tags=list(dict.fromkeys(tags)),
                metadata=metadata,
            )

        def _spec_preflight_score(spec: StrategySpec) -> float:
            activity = dict(spec.metadata.get('dsl_activity') or {})
            score = float(activity.get('score') or 0.0)
            tuning = dict(spec.metadata.get('dsl_tuning') or {})
            if tuning.get('applied'):
                score += 0.1
            return score

        def _is_viable_external_spec(cls, spec: StrategySpec) -> bool:
            activity = dict(spec.metadata.get('dsl_activity') or {})
            if not activity:
                return True
            entry_count = int(activity.get('entry_count') or 0)
            exit_count = int(activity.get('exit_count') or 0)
            return entry_count > 0 and exit_count > 0 and cls._spec_preflight_score(spec) >= 0.8

        async def _recent_experiments(self, db, parent_strategies: Optional[list[dict]] = None) -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for parent in list(parent_strategies or [])[:3]:
                parent_id = str((parent or {}).get('id') or '').strip()
                if not parent_id or not hasattr(db, 'list_strategy_generation_experiments'):
                    continue
                rows.extend(await db.list_strategy_generation_experiments(parent_strategy_id=parent_id, limit=5))
            summary = []
            for row in rows[:12]:
                evaluation = dict(row.get('evaluation') or {})
                committee_review = dict(evaluation.get('committee_review') or {})
                summary.append({
                    'parent_strategy_id': row.get('parent_strategy_id') or row.get('strategy_id'),
                    'generator_type': row.get('generator_type'),
                    'status': row.get('status'),
                    'final_score': committee_review.get('final_score'),
                    'decision': committee_review.get('decision'),
                    'parameters': row.get('parameters') or {},
                })
            return summary
