"""Strategy generators: rule-based and LLM-proxy strategy candidate generation."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from copy import deepcopy
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


def _rule_template_contract(strategy_type: str) -> dict[str, Any]:
    contracts: dict[str, dict[str, Any]] = {
        'volatility_breakout': {
            'template_generation_profile': 'conservative_breakout',
            'holding_horizon': {'min_days': 3, 'max_days': 15},
            'trade_plan': {'entry_bias': 'breakout_confirmation', 'exit_bias': 'trailing_stop_or_time_stop'},
            'risk_rules': {'stop_loss_pct': 0.07, 'take_profit_pct': 0.16, 'max_holding_days': 15, 'max_position_pct': 0.18},
            'position_sizing': {'mode': 'equal_weight', 'position_assumption': 'equal_weight_proxy'},
            'rebalance_rule': {'mode': 'signal_rebalance', 'frequency_days': 3},
            'portfolio_spec': {
                'position_assumption': 'equal_weight_proxy',
                'target_weight_scheme': 'equal_weight',
                'weight_method': 'volatility_budget',
                'max_position_pct': 0.18,
            },
            'execution_assumptions': {
                'commission_rate': 0.00025,
                'slippage_bps': 6,
                'tradability_filter': True,
                'slippage_model': 'fixed',
                'market_ruleset': 'cn_equity',
            },
            'validation_profile': {
                'profile': 'trade_rule_validation',
                'validation_focus': 'target_plus_representative',
                'primary_validation_layer': 'target',
            },
            'targeting_policy': {
                'target_symbol_policy': 'dynamic_signal_universe',
                'universe_scope': 'liquid_large_mid',
                'universe_expansion_policy': 'trend_leaders_only',
            },
            'rule_template_contract': {
                'template_generation_profile': 'conservative_breakout',
                'applicable_universe': {
                    'market_cap': 'mid_large',
                    'liquidity': 'high',
                    'style_bias': 'trend_expansion',
                },
                'target_layer': 'target',
                'default_risk_constraints': {
                    'stop_loss_pct': 0.07,
                    'take_profit_pct': 0.16,
                    'max_holding_days': 15,
                    'max_position_pct': 0.18,
                },
                'portfolio_weight_method': 'volatility_budget',
            },
        },
        'gap_fill': {
            'template_generation_profile': 'conservative_mean_reversion',
            'holding_horizon': {'min_days': 1, 'max_days': 8},
            'trade_plan': {'entry_bias': 'gap_repair_confirmation', 'exit_bias': 'mean_reversion_completion'},
            'risk_rules': {'stop_loss_pct': 0.05, 'take_profit_pct': 0.12, 'max_holding_days': 8, 'max_position_pct': 0.14},
            'position_sizing': {'mode': 'equal_weight', 'position_assumption': 'equal_weight_proxy'},
            'rebalance_rule': {'mode': 'signal_rebalance', 'frequency_days': 2},
            'portfolio_spec': {
                'position_assumption': 'equal_weight_proxy',
                'target_weight_scheme': 'equal_weight',
                'weight_method': 'repair_equal_weight',
                'max_position_pct': 0.14,
            },
            'execution_assumptions': {
                'commission_rate': 0.00025,
                'slippage_bps': 5,
                'tradability_filter': True,
                'slippage_model': 'fixed',
                'market_ruleset': 'cn_equity',
            },
            'validation_profile': {
                'profile': 'trade_rule_validation',
                'validation_focus': 'target_plus_representative',
                'primary_validation_layer': 'target',
            },
            'targeting_policy': {
                'target_symbol_policy': 'dynamic_signal_universe',
                'universe_scope': 'liquid_repair_candidates',
                'universe_expansion_policy': 'oversold_repair_only',
            },
            'rule_template_contract': {
                'template_generation_profile': 'conservative_mean_reversion',
                'applicable_universe': {
                    'market_cap': 'all_liquid',
                    'liquidity': 'medium_high',
                    'style_bias': 'oversold_repair',
                },
                'target_layer': 'target',
                'default_risk_constraints': {
                    'stop_loss_pct': 0.05,
                    'take_profit_pct': 0.12,
                    'max_holding_days': 8,
                    'max_position_pct': 0.14,
                },
                'portfolio_weight_method': 'repair_equal_weight',
            },
        },
        'mean_reversion_short': {
            'template_generation_profile': 'conservative_mean_reversion',
            'holding_horizon': {'min_days': 1, 'max_days': 7},
            'trade_plan': {'entry_bias': 'short_horizon_reversal', 'exit_bias': 'time_stop_or_signal_reset'},
            'risk_rules': {'stop_loss_pct': 0.05, 'take_profit_pct': 0.1, 'max_holding_days': 7, 'max_position_pct': 0.12},
            'position_sizing': {'mode': 'equal_weight', 'position_assumption': 'equal_weight_proxy'},
            'rebalance_rule': {'mode': 'signal_rebalance', 'frequency_days': 2},
            'portfolio_spec': {
                'position_assumption': 'equal_weight_proxy',
                'target_weight_scheme': 'equal_weight',
                'weight_method': 'short_horizon_equal_weight',
                'max_position_pct': 0.12,
            },
            'execution_assumptions': {
                'commission_rate': 0.00025,
                'slippage_bps': 5,
                'tradability_filter': True,
                'slippage_model': 'fixed',
                'market_ruleset': 'cn_equity',
            },
            'validation_profile': {
                'profile': 'trade_rule_validation',
                'validation_focus': 'target_plus_representative',
                'primary_validation_layer': 'target',
            },
            'targeting_policy': {
                'target_symbol_policy': 'dynamic_signal_universe',
                'universe_scope': 'liquid_defensive_reversion',
                'universe_expansion_policy': 'short_horizon_only',
            },
            'rule_template_contract': {
                'template_generation_profile': 'conservative_mean_reversion',
                'applicable_universe': {
                    'market_cap': 'all_liquid',
                    'liquidity': 'high',
                    'style_bias': 'defensive_mean_reversion',
                },
                'target_layer': 'target',
                'default_risk_constraints': {
                    'stop_loss_pct': 0.05,
                    'take_profit_pct': 0.1,
                    'max_holding_days': 7,
                    'max_position_pct': 0.12,
                },
                'portfolio_weight_method': 'short_horizon_equal_weight',
            },
        },
        'sector_rotation': {
            'template_generation_profile': 'conservative_rotation',
            'holding_horizon': {'min_days': 5, 'max_days': 20},
            'trade_plan': {'entry_bias': 'relative_strength_rotation', 'exit_bias': 'leadership_decay_or_time_stop'},
            'risk_rules': {'stop_loss_pct': 0.08, 'take_profit_pct': 0.18, 'max_holding_days': 20, 'max_position_pct': 0.15},
            'position_sizing': {'mode': 'equal_weight', 'position_assumption': 'equal_weight_proxy'},
            'rebalance_rule': {'mode': 'periodic_rebalance', 'frequency_days': 5},
            'portfolio_spec': {
                'position_assumption': 'equal_weight_proxy',
                'target_weight_scheme': 'equal_weight',
                'weight_method': 'sector_score_tilt',
                'max_position_pct': 0.15,
            },
            'execution_assumptions': {
                'commission_rate': 0.00025,
                'slippage_bps': 6,
                'tradability_filter': True,
                'slippage_model': 'fixed',
                'market_ruleset': 'cn_equity',
            },
            'validation_profile': {
                'profile': 'trade_rule_validation',
                'validation_focus': 'target_plus_representative',
                'primary_validation_layer': 'combined',
            },
            'targeting_policy': {
                'target_symbol_policy': 'sector_leader_rotation',
                'universe_scope': 'liquid_sector_leaders',
                'universe_expansion_policy': 'sector_relative_strength',
            },
            'rule_template_contract': {
                'template_generation_profile': 'conservative_rotation',
                'applicable_universe': {
                    'market_cap': 'mid_large',
                    'liquidity': 'high',
                    'style_bias': 'sector_leadership',
                },
                'target_layer': 'combined',
                'default_risk_constraints': {
                    'stop_loss_pct': 0.08,
                    'take_profit_pct': 0.18,
                    'max_holding_days': 20,
                    'max_position_pct': 0.15,
                },
                'portfolio_weight_method': 'sector_score_tilt',
            },
        },
        'north_capital_track': {
            'template_generation_profile': 'conservative_flow',
            'holding_horizon': {'min_days': 4, 'max_days': 12},
            'trade_plan': {'entry_bias': 'capital_flow_confirmation', 'exit_bias': 'flow_reversal_or_time_stop'},
            'risk_rules': {'stop_loss_pct': 0.07, 'take_profit_pct': 0.16, 'max_holding_days': 12, 'max_position_pct': 0.16},
            'position_sizing': {'mode': 'equal_weight', 'position_assumption': 'equal_weight_proxy'},
            'rebalance_rule': {'mode': 'periodic_rebalance', 'frequency_days': 3},
            'portfolio_spec': {
                'position_assumption': 'equal_weight_proxy',
                'target_weight_scheme': 'equal_weight',
                'weight_method': 'flow_score_tilt',
                'max_position_pct': 0.16,
            },
            'execution_assumptions': {
                'commission_rate': 0.00025,
                'slippage_bps': 6,
                'tradability_filter': True,
                'slippage_model': 'fixed',
                'market_ruleset': 'cn_equity',
            },
            'validation_profile': {
                'profile': 'trade_rule_validation',
                'validation_focus': 'target_plus_representative',
                'primary_validation_layer': 'combined',
            },
            'targeting_policy': {
                'target_symbol_policy': 'northbound_eligible_focus',
                'universe_scope': 'northbound_liquid_core',
                'universe_expansion_policy': 'flow_leaders_only',
            },
            'rule_template_contract': {
                'template_generation_profile': 'conservative_flow',
                'applicable_universe': {
                    'northbound_eligible': True,
                    'liquidity': 'high',
                    'style_bias': 'capital_flow_leaders',
                },
                'target_layer': 'combined',
                'default_risk_constraints': {
                    'stop_loss_pct': 0.07,
                    'take_profit_pct': 0.16,
                    'max_holding_days': 12,
                    'max_position_pct': 0.16,
                },
                'portfolio_weight_method': 'flow_score_tilt',
            },
        },
        'margin_divergence': {
            'template_generation_profile': 'conservative_flow',
            'holding_horizon': {'min_days': 3, 'max_days': 10},
            'trade_plan': {'entry_bias': 'divergence_repair_confirmation', 'exit_bias': 'divergence_resolution'},
            'risk_rules': {'stop_loss_pct': 0.06, 'take_profit_pct': 0.14, 'max_holding_days': 10, 'max_position_pct': 0.14},
            'position_sizing': {'mode': 'equal_weight', 'position_assumption': 'equal_weight_proxy'},
            'rebalance_rule': {'mode': 'signal_rebalance', 'frequency_days': 3},
            'portfolio_spec': {
                'position_assumption': 'equal_weight_proxy',
                'target_weight_scheme': 'equal_weight',
                'weight_method': 'divergence_tilt',
                'max_position_pct': 0.14,
            },
            'execution_assumptions': {
                'commission_rate': 0.00025,
                'slippage_bps': 6,
                'tradability_filter': True,
                'slippage_model': 'fixed',
                'market_ruleset': 'cn_equity',
            },
            'validation_profile': {
                'profile': 'trade_rule_validation',
                'validation_focus': 'target_plus_representative',
                'primary_validation_layer': 'target',
            },
            'targeting_policy': {
                'target_symbol_policy': 'margin_activity_focus',
                'universe_scope': 'liquid_margin_active',
                'universe_expansion_policy': 'divergence_repair_only',
            },
            'rule_template_contract': {
                'template_generation_profile': 'conservative_flow',
                'applicable_universe': {
                    'margin_active': True,
                    'liquidity': 'high',
                    'style_bias': 'capital_divergence',
                },
                'target_layer': 'target',
                'default_risk_constraints': {
                    'stop_loss_pct': 0.06,
                    'take_profit_pct': 0.14,
                    'max_holding_days': 10,
                    'max_position_pct': 0.14,
                },
                'portfolio_weight_method': 'divergence_tilt',
            },
        },
    }
    return deepcopy(contracts.get(str(strategy_type or '').strip().lower()) or {})


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
            'volatility_breakout': {
                'params': {'lookback': 20, 'threshold': 0.025},
                'name': 'AI 波动突破',
                'description': '趋势扩张与波动放大阶段偏向波动率突破。',
            },
            'gap_fill': {
                'params': {'gap_threshold': 0.02, 'rsi_period': 5, 'oversold': 24, 'overbought': 58},
                'name': 'AI 跳空回补',
                'description': '情绪错杀或事件冲击后偏向短线回补机会。',
            },
            'mean_reversion_short': {
                'params': {'rsi_period': 6, 'oversold': 26, 'overbought': 62},
                'name': 'AI 短线回归',
                'description': '震荡与防御环境下偏向短周期均值回归。',
            },
            'sector_rotation': {
                'params': {'lookback': 20, 'factor_weights': {'momentum': 0.45, 'quality': 0.30, 'value': 0.25}},
                'name': 'AI 行业轮动',
                'description': '主题扩散与风格切换阶段偏向行业轮动打分。',
            },
            'north_capital_track': {
                'params': {'lookback': 15, 'threshold': 0.015},
                'name': 'AI 北向跟踪',
                'description': '资金偏好明确时偏向价量共振的北向跟踪。',
            },
            'margin_divergence': {
                'params': {'fear_threshold': 40, 'greed_threshold': 60, 'lookback': 15},
                'name': 'AI 融资背离',
                'description': '价格与量能出现背离时偏向融资分歧修复。',
            },
        }
        template = templates.get(strategy_type)
        if template is None:
            return None
        template_contract = _rule_template_contract(strategy_type)
        metadata = {
            'generator_type': 'rule',
            'generation_reason': {
                'source': source,
                'fg': fg,
                'regime': regime,
                'factor_research': factor_summary,
                'template_generation_profile': template_contract.get('template_generation_profile'),
                'rule_template_contract': dict(template_contract.get('rule_template_contract') or {}),
            },
        }
        for key in (
            'holding_horizon',
            'trade_plan',
            'risk_rules',
            'position_sizing',
            'rebalance_rule',
            'portfolio_spec',
            'execution_assumptions',
            'validation_profile',
            'targeting_policy',
            'rule_template_contract',
        ):
            value = template_contract.get(key)
            if value:
                metadata[key] = deepcopy(value)
        return StrategySpec(
            strategy_type=strategy_type,
            params=dict(template['params']),
            name=str(template['name']),
            description=str(template['description']),
            tags=['rule', 'factor_research' if source == 'factor_research' else 'fear_greed'],
            metadata=metadata,
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
            ['momentum', 'volatility_breakout', 'north_capital_track', 'ma_cross', 'quality_factor']
            if regime == 'greed'
            else ['value_factor', 'quality_factor', 'mean_reversion_short', 'gap_fill', 'rsi']
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

from ._strategy_generators_external import _LLMProxyStrategyGeneratorExternalMixin
from ._strategy_generators_context import _LLMProxyStrategyGeneratorContextMixin
from ._strategy_generators_specs import _LLMProxyStrategyGeneratorSpecsMixin
from ._strategy_generators_generate import _LLMProxyStrategyGeneratorGenerateMixin


class LLMProxyStrategyGenerator(_LLMProxyStrategyGeneratorExternalMixin, _LLMProxyStrategyGeneratorContextMixin, _LLMProxyStrategyGeneratorSpecsMixin, _LLMProxyStrategyGeneratorGenerateMixin):
        def __init__(self):
            self.miner = LLMAlphaMiner()
            self.external_provider = get_strategy_llm_provider()
            self.last_report: dict[str, Any] = {}

        def get_last_report(self) -> dict[str, Any]:
            return dict(self.last_report)
