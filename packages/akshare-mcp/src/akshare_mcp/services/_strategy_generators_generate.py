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
    from strategy_factory.application.precompile_contract import validate_precompile_candidate_contract
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
        "validate_precompile_candidate_contract": validate_precompile_candidate_contract,
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
        "validate_precompile_candidate_contract": "validate_precompile_candidate_contract",
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
validate_precompile_candidate_contract = _sf()["validate_precompile_candidate_contract"]

from .llm_alpha import LLMAlphaMiner
from .data_pipeline import normalize_klines
from .strategy_dsl import compile_strategy_blueprint
from .strategy_llm_provider import StrategyLLMProvider, get_strategy_llm_provider
from .strategy_open_dsl import (
    is_open_dsl_spec_metadata,
    open_dsl_max_candidates_per_run,
)
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


_NON_REQUEST_SKIP_STATUSES = {"compatibility_skip", "cooldown_skip"}


def _normalize_external_request_status(status: Any) -> str:
    return str(status or "").strip().lower() or "unknown"


def _count_external_request_statuses(requests: Optional[list[dict[str, Any]]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in list(requests or []):
        status = _normalize_external_request_status(dict(item or {}).get("status"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _count_external_network_requests(requests: Optional[list[dict[str, Any]]]) -> int:
    total = 0
    for item in list(requests or []):
        payload = dict(item or {})
        status = _normalize_external_request_status(payload.get("status"))
        if status in _NON_REQUEST_SKIP_STATUSES:
            continue
        metrics = dict(payload.get("request_metrics") or {})
        try:
            attempt_count = int(metrics.get("attempt_count") or 0)
        except Exception:
            attempt_count = 0
        total += max(attempt_count, 1)
    return total


def _count_external_real_requests(requests: Optional[list[dict[str, Any]]]) -> int:
    total = 0
    for item in list(requests or []):
        status = _normalize_external_request_status(dict(item or {}).get("status"))
        if status in _NON_REQUEST_SKIP_STATUSES:
            continue
        total += 1
    return total


def _request_is_compatibility_failure(request: Optional[dict[str, Any]]) -> bool:
    payload = dict(request or {})
    status = _normalize_external_request_status(payload.get("status"))
    if status in _NON_REQUEST_SKIP_STATUSES:
        return False
    metrics = dict(payload.get("request_metrics") or {})
    metric_status = _normalize_external_request_status(metrics.get("status"))
    error_type = str(payload.get("error_type") or metrics.get("last_error_type") or "").strip().lower()
    error_text = str(payload.get("error") or metrics.get("last_error") or "").strip().lower()
    return (
        metric_status == "compatibility_failed"
        or error_type == "providercompatibilityerror"
        or "missing extractable content" in error_text
    )


def _request_is_empty_200_response(request: Optional[dict[str, Any]]) -> bool:
    payload = dict(request or {})
    status = _normalize_external_request_status(payload.get("status"))
    if status in _NON_REQUEST_SKIP_STATUSES:
        return False
    metrics = dict(payload.get("request_metrics") or {})
    if bool(metrics.get("empty_200_response")):
        return True
    if not _request_is_compatibility_failure(payload):
        return False
    error_text = str(payload.get("error") or metrics.get("last_error") or "").strip().lower()
    return "missing extractable content" in error_text


def _count_external_compatibility_failures(requests: Optional[list[dict[str, Any]]]) -> int:
    return sum(1 for item in list(requests or []) if _request_is_compatibility_failure(item))


def _count_external_effective_responses(requests: Optional[list[dict[str, Any]]]) -> int:
    total = 0
    for item in list(requests or []):
        if _normalize_external_request_status(dict(item or {}).get("status")) == "succeeded":
            total += 1
    return total


def _count_external_empty_200_responses(requests: Optional[list[dict[str, Any]]]) -> int:
    return sum(1 for item in list(requests or []) if _request_is_empty_200_response(item))


def _finalize_external_provider_report(external_provider: Optional[dict[str, Any]]) -> dict[str, Any]:
    summary = dict(external_provider or {})
    requests = list(summary.get("requests") or [])
    status_counts = dict(summary.get("request_status_counts") or {}) or _count_external_request_statuses(requests)
    stage_attempt_count = int(summary.get("stage_attempt_count") or len(requests))
    network_request_count = int(summary.get("network_request_count") or _count_external_network_requests(requests))
    real_request_count = int(summary.get("real_request_count") or _count_external_real_requests(requests))
    compatibility_failure_count = int(
        summary.get("compatibility_failure_count") or _count_external_compatibility_failures(requests)
    )
    effective_response_count = int(
        summary.get("effective_response_count") or _count_external_effective_responses(requests)
    )
    empty_200_response_count = int(
        summary.get("empty_200_response_count") or _count_external_empty_200_responses(requests)
    )

    summary["stage_attempt_count"] = stage_attempt_count
    summary["network_request_count"] = network_request_count
    summary["real_request_count"] = real_request_count
    summary["compatibility_skip_count"] = int(
        summary.get("compatibility_skip_count")
        or status_counts.get("compatibility_skip", 0)
    )
    summary["cooldown_skip_count"] = int(
        summary.get("cooldown_skip_count")
        or status_counts.get("cooldown_skip", 0)
    )
    summary["compatibility_failure_count"] = compatibility_failure_count
    summary["effective_response_count"] = effective_response_count
    summary["empty_200_response_count"] = empty_200_response_count
    summary["compatibility_failure_ratio"] = (
        round(compatibility_failure_count / real_request_count, 4) if real_request_count else 0.0
    )
    summary["effective_response_ratio"] = (
        round(effective_response_count / real_request_count, 4) if real_request_count else 0.0
    )
    if status_counts:
        summary["request_status_counts"] = status_counts
    requests = list(summary.get("requests") or [])
    if requests:
        summary["open_dsl_candidate_count"] = int(
            summary.get("open_dsl_candidate_count")
            or sum(int(dict(item or {}).get("open_dsl_candidate_count") or 0) for item in requests)
        )
        summary["open_dsl_compiled_candidate_count"] = int(
            summary.get("open_dsl_compiled_candidate_count")
            or sum(int(dict(item or {}).get("open_dsl_compiled_candidate_count") or 0) for item in requests)
        )
        summary["open_dsl_viable_candidate_count"] = int(
            summary.get("open_dsl_viable_candidate_count")
            or sum(int(dict(item or {}).get("open_dsl_viable_candidate_count") or 0) for item in requests)
        )
        summary["open_dsl_rejected_count"] = int(
            summary.get("open_dsl_rejected_count")
            or sum(int(dict(item or {}).get("open_dsl_rejected_count") or 0) for item in requests)
        )
    return summary


def _rule_template_contract(strategy_type: str) -> dict[str, Any]:
    contracts: dict[str, dict[str, Any]] = {
        'volatility_breakout': {
            'template_generation_profile': 'conservative_breakout',
            'holding_horizon': {'min_days': 3, 'max_days': 15},
            'trade_plan': {'entry_bias': 'breakout_confirmation', 'exit_bias': 'trailing_stop_or_time_stop'},
            'risk_rules': {'stop_loss_pct': 0.07, 'take_profit_pct': 0.16, 'max_holding_days': 15, 'max_position_pct': 0.18},
            'position_sizing': {'mode': 'equal_weight', 'position_assumption': 'equal_weight_proxy'},
            'rebalance_rule': {'mode': 'signal_rebalance', 'frequency_days': 3},
            'portfolio_spec': {'position_assumption': 'equal_weight_proxy', 'target_weight_scheme': 'equal_weight', 'weight_method': 'volatility_budget', 'max_position_pct': 0.18},
            'execution_assumptions': {'commission_rate': 0.00025, 'slippage_bps': 6, 'tradability_filter': True, 'slippage_model': 'fixed', 'market_ruleset': 'cn_equity'},
            'validation_profile': {'profile': 'trade_rule_validation', 'validation_focus': 'target_plus_representative', 'primary_validation_layer': 'target'},
            'targeting_policy': {'target_symbol_policy': 'dynamic_signal_universe', 'universe_scope': 'liquid_large_mid', 'universe_expansion_policy': 'trend_leaders_only'},
            'rule_template_contract': {'template_generation_profile': 'conservative_breakout', 'applicable_universe': {'market_cap': 'mid_large', 'liquidity': 'high', 'style_bias': 'trend_expansion'}, 'target_layer': 'target', 'default_risk_constraints': {'stop_loss_pct': 0.07, 'take_profit_pct': 0.16, 'max_holding_days': 15, 'max_position_pct': 0.18}, 'portfolio_weight_method': 'volatility_budget'},
        },
        'gap_fill': {
            'template_generation_profile': 'conservative_mean_reversion',
            'holding_horizon': {'min_days': 1, 'max_days': 8},
            'trade_plan': {'entry_bias': 'gap_repair_confirmation', 'exit_bias': 'mean_reversion_completion'},
            'risk_rules': {'stop_loss_pct': 0.05, 'take_profit_pct': 0.12, 'max_holding_days': 8, 'max_position_pct': 0.14},
            'position_sizing': {'mode': 'equal_weight', 'position_assumption': 'equal_weight_proxy'},
            'rebalance_rule': {'mode': 'signal_rebalance', 'frequency_days': 2},
            'portfolio_spec': {'position_assumption': 'equal_weight_proxy', 'target_weight_scheme': 'equal_weight', 'weight_method': 'repair_equal_weight', 'max_position_pct': 0.14},
            'execution_assumptions': {'commission_rate': 0.00025, 'slippage_bps': 5, 'tradability_filter': True, 'slippage_model': 'fixed', 'market_ruleset': 'cn_equity'},
            'validation_profile': {'profile': 'trade_rule_validation', 'validation_focus': 'target_plus_representative', 'primary_validation_layer': 'target'},
            'targeting_policy': {'target_symbol_policy': 'dynamic_signal_universe', 'universe_scope': 'liquid_repair_candidates', 'universe_expansion_policy': 'oversold_repair_only'},
            'rule_template_contract': {'template_generation_profile': 'conservative_mean_reversion', 'applicable_universe': {'market_cap': 'all_liquid', 'liquidity': 'medium_high', 'style_bias': 'oversold_repair'}, 'target_layer': 'target', 'default_risk_constraints': {'stop_loss_pct': 0.05, 'take_profit_pct': 0.12, 'max_holding_days': 8, 'max_position_pct': 0.14}, 'portfolio_weight_method': 'repair_equal_weight'},
        },
        'mean_reversion_short': {
            'template_generation_profile': 'conservative_mean_reversion',
            'holding_horizon': {'min_days': 1, 'max_days': 7},
            'trade_plan': {'entry_bias': 'short_horizon_reversal', 'exit_bias': 'time_stop_or_signal_reset'},
            'risk_rules': {'stop_loss_pct': 0.05, 'take_profit_pct': 0.1, 'max_holding_days': 7, 'max_position_pct': 0.12},
            'position_sizing': {'mode': 'equal_weight', 'position_assumption': 'equal_weight_proxy'},
            'rebalance_rule': {'mode': 'signal_rebalance', 'frequency_days': 2},
            'portfolio_spec': {'position_assumption': 'equal_weight_proxy', 'target_weight_scheme': 'equal_weight', 'weight_method': 'short_horizon_equal_weight', 'max_position_pct': 0.12},
            'execution_assumptions': {'commission_rate': 0.00025, 'slippage_bps': 5, 'tradability_filter': True, 'slippage_model': 'fixed', 'market_ruleset': 'cn_equity'},
            'validation_profile': {'profile': 'trade_rule_validation', 'validation_focus': 'target_plus_representative', 'primary_validation_layer': 'target'},
            'targeting_policy': {'target_symbol_policy': 'dynamic_signal_universe', 'universe_scope': 'liquid_defensive_reversion', 'universe_expansion_policy': 'short_horizon_only'},
            'rule_template_contract': {'template_generation_profile': 'conservative_mean_reversion', 'applicable_universe': {'market_cap': 'all_liquid', 'liquidity': 'high', 'style_bias': 'defensive_mean_reversion'}, 'target_layer': 'target', 'default_risk_constraints': {'stop_loss_pct': 0.05, 'take_profit_pct': 0.1, 'max_holding_days': 7, 'max_position_pct': 0.12}, 'portfolio_weight_method': 'short_horizon_equal_weight'},
        },
        'sector_rotation': {
            'template_generation_profile': 'conservative_rotation',
            'holding_horizon': {'min_days': 5, 'max_days': 20},
            'trade_plan': {'entry_bias': 'relative_strength_rotation', 'exit_bias': 'leadership_decay_or_time_stop'},
            'risk_rules': {'stop_loss_pct': 0.08, 'take_profit_pct': 0.18, 'max_holding_days': 20, 'max_position_pct': 0.15},
            'position_sizing': {'mode': 'equal_weight', 'position_assumption': 'equal_weight_proxy'},
            'rebalance_rule': {'mode': 'periodic_rebalance', 'frequency_days': 5},
            'portfolio_spec': {'position_assumption': 'equal_weight_proxy', 'target_weight_scheme': 'equal_weight', 'weight_method': 'sector_score_tilt', 'max_position_pct': 0.15},
            'execution_assumptions': {'commission_rate': 0.00025, 'slippage_bps': 6, 'tradability_filter': True, 'slippage_model': 'fixed', 'market_ruleset': 'cn_equity'},
            'validation_profile': {'profile': 'trade_rule_validation', 'validation_focus': 'target_plus_representative', 'primary_validation_layer': 'combined'},
            'targeting_policy': {'target_symbol_policy': 'sector_leader_rotation', 'universe_scope': 'liquid_sector_leaders', 'universe_expansion_policy': 'sector_relative_strength'},
            'rule_template_contract': {'template_generation_profile': 'conservative_rotation', 'applicable_universe': {'market_cap': 'mid_large', 'liquidity': 'high', 'style_bias': 'sector_leadership'}, 'target_layer': 'combined', 'default_risk_constraints': {'stop_loss_pct': 0.08, 'take_profit_pct': 0.18, 'max_holding_days': 20, 'max_position_pct': 0.15}, 'portfolio_weight_method': 'sector_score_tilt'},
        },
        'north_capital_track': {
            'template_generation_profile': 'conservative_flow',
            'holding_horizon': {'min_days': 4, 'max_days': 12},
            'trade_plan': {'entry_bias': 'capital_flow_confirmation', 'exit_bias': 'flow_reversal_or_time_stop'},
            'risk_rules': {'stop_loss_pct': 0.07, 'take_profit_pct': 0.16, 'max_holding_days': 12, 'max_position_pct': 0.16},
            'position_sizing': {'mode': 'equal_weight', 'position_assumption': 'equal_weight_proxy'},
            'rebalance_rule': {'mode': 'periodic_rebalance', 'frequency_days': 3},
            'portfolio_spec': {'position_assumption': 'equal_weight_proxy', 'target_weight_scheme': 'equal_weight', 'weight_method': 'flow_score_tilt', 'max_position_pct': 0.16},
            'execution_assumptions': {'commission_rate': 0.00025, 'slippage_bps': 6, 'tradability_filter': True, 'slippage_model': 'fixed', 'market_ruleset': 'cn_equity'},
            'validation_profile': {'profile': 'trade_rule_validation', 'validation_focus': 'target_plus_representative', 'primary_validation_layer': 'combined'},
            'targeting_policy': {'target_symbol_policy': 'northbound_eligible_focus', 'universe_scope': 'northbound_liquid_core', 'universe_expansion_policy': 'flow_leaders_only'},
            'rule_template_contract': {'template_generation_profile': 'conservative_flow', 'applicable_universe': {'northbound_eligible': True, 'liquidity': 'high', 'style_bias': 'capital_flow_leaders'}, 'target_layer': 'combined', 'default_risk_constraints': {'stop_loss_pct': 0.07, 'take_profit_pct': 0.16, 'max_holding_days': 12, 'max_position_pct': 0.16}, 'portfolio_weight_method': 'flow_score_tilt'},
        },
        'margin_divergence': {
            'template_generation_profile': 'conservative_flow',
            'holding_horizon': {'min_days': 3, 'max_days': 10},
            'trade_plan': {'entry_bias': 'divergence_repair_confirmation', 'exit_bias': 'divergence_resolution'},
            'risk_rules': {'stop_loss_pct': 0.06, 'take_profit_pct': 0.14, 'max_holding_days': 10, 'max_position_pct': 0.14},
            'position_sizing': {'mode': 'equal_weight', 'position_assumption': 'equal_weight_proxy'},
            'rebalance_rule': {'mode': 'signal_rebalance', 'frequency_days': 3},
            'portfolio_spec': {'position_assumption': 'equal_weight_proxy', 'target_weight_scheme': 'equal_weight', 'weight_method': 'divergence_tilt', 'max_position_pct': 0.14},
            'execution_assumptions': {'commission_rate': 0.00025, 'slippage_bps': 6, 'tradability_filter': True, 'slippage_model': 'fixed', 'market_ruleset': 'cn_equity'},
            'validation_profile': {'profile': 'trade_rule_validation', 'validation_focus': 'target_plus_representative', 'primary_validation_layer': 'target'},
            'targeting_policy': {'target_symbol_policy': 'margin_activity_focus', 'universe_scope': 'liquid_margin_active', 'universe_expansion_policy': 'divergence_repair_only'},
            'rule_template_contract': {'template_generation_profile': 'conservative_flow', 'applicable_universe': {'margin_active': True, 'liquidity': 'high', 'style_bias': 'capital_divergence'}, 'target_layer': 'target', 'default_risk_constraints': {'stop_loss_pct': 0.06, 'take_profit_pct': 0.14, 'max_holding_days': 10, 'max_position_pct': 0.14}, 'portfolio_weight_method': 'divergence_tilt'},
        },
    }
    return deepcopy(contracts.get(str(strategy_type or '').strip().lower()) or {})


def _collapsed_generation_hint(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
    )


def _snapshot_pipeline_contract(research_task: Optional[dict[str, Any]]) -> dict[str, Any]:
    task = dict(research_task or {})
    task_source = str(task.get("task_source") or "").strip().lower()
    opportunity_type = str(task.get("opportunity_type") or "").strip().lower()
    validation_focus = str(task.get("validation_focus") or "").strip().lower()
    template_profile = str(task.get("template_generation_profile") or "").strip().lower()
    allowed_strategy_types = [
        str(item).strip()
        for item in list(task.get("allowed_strategy_types") or [])
        if str(item).strip()
    ]
    collapsed = _collapsed_generation_hint(
        " ".join(
            str(item or "")
            for item in (
                task.get("candidate_family"),
                task.get("factor_name"),
                task.get("candidate_name"),
                task.get("preference_reason"),
                task.get("rationale"),
            )
            if str(item or "").strip()
        )
    )
    if not template_profile:
        if any(token in collapsed for token in ("closelocation", "intradayresilience", "trendefficiency", "pullback", "quality", "stability", "quiet", "repair", "reversion")):
            template_profile = "conservative_mean_reversion"
        elif any(token in collapsed for token in ("capitalflow", "northcapital", "northbound", "fundflow", "liquidity", "turnover")):
            template_profile = "conservative_flow"
        elif any(token in collapsed for token in ("rotation", "sector", "cycle", "divergence", "breadth")):
            template_profile = "conservative_rotation"
        elif any(token in collapsed for token in ("momentum", "macross", "cross", "trend", "breakout", "gapcontinuation", "expansion", "acceleration", "volatility")):
            template_profile = "conservative_breakout"

    conservative_snapshot_task = (
        task_source == "snapshot"
        and (
            template_profile.startswith("conservative_")
            or opportunity_type in {"candidate_family_activation", "candidate_factor_activation", "factor_acceleration"}
            or validation_focus == "candidate_target_only"
        )
    )
    return {
        "conservative_snapshot_task": conservative_snapshot_task,
        "template_generation_profile": template_profile,
        "allowed_strategy_types": allowed_strategy_types,
    }


def _conservative_ma_cross_dsl(target_symbols: list[str], stock_pool: dict[str, Any], *, short_period: int, long_period: int) -> dict[str, Any]:
    metadata = {
        "target_symbols": list(target_symbols),
        "stock_pool": dict(stock_pool),
        "generation_profile": "snapshot_family_conservative",
    }
    return {
        "version": "1.0",
        "timeframe": "daily",
        "entry": {
            "all": [
                {
                    "op": "cross_above",
                    "left": {"indicator": "sma", "field": "close", "window": short_period},
                    "right": {"indicator": "sma", "field": "close", "window": long_period},
                },
                {
                    "op": "gt",
                    "left": {"field": "close"},
                    "right": {"indicator": "sma", "field": "close", "window": 20},
                },
                {
                    "op": "gt",
                    "left": {"indicator": "roc", "field": "close", "window": 20},
                    "right": {"value": 0.01},
                },
                {
                    "op": "gt",
                    "left": {"indicator": "volume_ratio", "field": "volume", "window": 20},
                    "right": {"value": 1.0},
                },
            ],
        },
        "exit": {
            "any": [
                {
                    "op": "cross_below",
                    "left": {"indicator": "sma", "field": "close", "window": short_period},
                    "right": {"indicator": "sma", "field": "close", "window": long_period},
                },
                {
                    "op": "lt",
                    "left": {"field": "close"},
                    "right": {"indicator": "sma", "field": "close", "window": 20},
                },
                {
                    "op": "lt",
                    "left": {"indicator": "roc", "field": "close", "window": 10},
                    "right": {"value": -0.012},
                },
            ],
        },
        "metadata": metadata,
    }


def _normalize_snapshot_pipeline_candidate(candidate: dict[str, Any]) -> Optional[dict[str, Any]]:
    payload = deepcopy(candidate or {})
    contract = _snapshot_pipeline_contract(payload.get("research_task"))
    if not contract.get("conservative_snapshot_task"):
        return payload

    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    allowed_strategy_types = set(contract.get("allowed_strategy_types") or [])
    if allowed_strategy_types and strategy_type and strategy_type not in allowed_strategy_types:
        return None
    if strategy_type == "momentum":
        return None
    if strategy_type != "ma_cross":
        return payload

    params = dict(payload.get("params") or {})
    short_period = max(int(params.get("short_period") or 12), 12)
    long_period = max(int(params.get("long_period") or 48), 48)
    if long_period <= short_period:
        long_period = max(long_period, short_period * 4)
    target_symbols = [
        str(item).strip()
        for item in list(payload.get("target_symbols") or [])
        if str(item).strip()
    ]
    stock_pool = dict(payload.get("stock_pool") or {})
    if not stock_pool and target_symbols:
        stock_pool = {"selection_mode": "explicit", "symbols": list(target_symbols)}
    payload["params"] = {
        **params,
        "short_period": short_period,
        "long_period": long_period,
    }
    payload["dsl"] = _conservative_ma_cross_dsl(
        target_symbols,
        stock_pool,
        short_period=short_period,
        long_period=long_period,
    )
    payload["tags"] = list(
        dict.fromkeys(
            [
                *list(payload.get("tags") or []),
                "snapshot_family_conservative",
                "ma_cross_retuned",
            ]
        )
    )
    payload["description"] = str(
        payload.get("description")
        or "针对 snapshot family target pool 收紧后的长周期均线模板，优先过滤负 Sharpe 的高换手趋势信号。"
    )
    return payload


def _resolve_pipeline_runtime_symbols() -> tuple[str, Any]:
    try:
        from . import strategy_generators as public_module

        pipeline_mode = str(getattr(public_module, "PIPELINE_MODE", PIPELINE_MODE) or PIPELINE_MODE)
        pipeline_factory = getattr(public_module, "get_strategy_pipeline", get_strategy_pipeline)
        return pipeline_mode, pipeline_factory
    except Exception:
        return str(PIPELINE_MODE), get_strategy_pipeline


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
                'description': '趋势加速且波动扩张时，捕捉放量突破的延续段。',
            },
            'gap_fill': {
                'params': {'gap_threshold': 0.02, 'rsi_period': 5, 'oversold': 24, 'overbought': 58},
                'name': 'AI 跳空回补',
                'description': '利用超跌跳空后的回补行为，构建短线反转机会。',
            },
            'mean_reversion_short': {
                'params': {'rsi_period': 6, 'oversold': 26, 'overbought': 62},
                'name': 'AI 短反均值回归',
                'description': '短周期超跌/超涨后的价格修复，偏向高频次轻持仓。',
            },
            'sector_rotation': {
                'params': {'lookback': 20, 'factor_weights': {'momentum': 0.45, 'quality': 0.30, 'value': 0.25}},
                'name': 'AI 行业轮动',
                'description': '结合动量、稳定性与估值回归代理，优先轮动到更强板块。',
            },
            'north_capital_track': {
                'params': {'lookback': 15, 'threshold': 0.015},
                'name': 'AI 北向跟踪',
                'description': '用价量共振近似北向资金持续流入，捕捉机构偏好延续。',
            },
            'margin_divergence': {
                'params': {'fear_threshold': 40, 'greed_threshold': 60, 'lookback': 15},
                'name': 'AI 融资背离',
                'description': '价格回落但量能韧性仍在时布局，过热或背离恶化时退出。',
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


class _LLMProxyStrategyGeneratorGenerateMixin:
        @staticmethod
        def _l2_hypothesis_replay_enabled() -> bool:
            raw = os.getenv("STRATEGY_FACTORY_L2_HYPOTHESIS_REPLAY_ENABLED")
            if raw is None:
                raw = os.getenv("STRATEGY_FACTORY_L2_REPLAY_ENABLED")
            if raw is None:
                return True
            return str(raw).strip().lower() in {"1", "true", "yes", "on"}

        @classmethod
        def _replay_strategy_spec_from_experiment(
            cls,
            row: dict[str, Any],
            *,
            research_task: Optional[dict[str, Any]] = None,
        ) -> Optional[StrategySpec]:
            payload = dict(row or {})
            strategy_spec = dict(payload.get("strategy_spec") or {})
            evaluation = dict(payload.get("evaluation") or {})
            replay_contract = dict(strategy_spec.get("replay_contract") or {})
            contract = dict(replay_contract or strategy_spec)
            strategy_type = str(contract.get("strategy_type") or strategy_spec.get("strategy_type") or "").strip()
            if not strategy_type:
                return None
            params = dict(contract.get("params") or {})
            name = str(contract.get("name") or strategy_spec.get("name") or "").strip() or "历史回放候选"
            description = str(
                contract.get("description")
                or strategy_spec.get("description")
                or payload.get("hypothesis")
                or ""
            ).strip()
            target_symbols = cls._normalize_code_list(
                [
                    contract.get("target_symbols"),
                    strategy_spec.get("target_symbols"),
                    evaluation.get("target_symbols"),
                ]
            )
            normalized_task = _normalize_research_task_contract(research_task or {})
            requested_targets = set(cls._normalize_code_list(normalized_task.get("target_symbols")))
            if requested_targets and target_symbols and not requested_targets.intersection(target_symbols):
                return None
            allowed_strategy_types = {
                str(item or "").strip().lower()
                for item in list(normalized_task.get("allowed_strategy_types") or [])
                if str(item or "").strip()
            }
            if allowed_strategy_types and strategy_type.strip().lower() not in allowed_strategy_types:
                return None

            hypothesis_artifact = dict(
                contract.get("hypothesis_artifact")
                or strategy_spec.get("hypothesis_artifact")
                or evaluation.get("hypothesis_artifact")
                or {}
            )
            metadata = {
                "generator_type": "hypothesis_replay",
                "hypothesis": str(
                    hypothesis_artifact.get("alpha_hypothesis")
                    or payload.get("hypothesis")
                    or description
                    or name
                ).strip(),
                "holding_horizon": dict(contract.get("holding_horizon") or {}),
                "trade_plan": dict(contract.get("trade_plan") or {}),
                "risk_rules": dict(contract.get("risk_rules") or {}),
                "position_sizing": dict(contract.get("position_sizing") or {}),
                "execution_notes": contract.get("execution_notes"),
                "rebalance_rule": dict(contract.get("rebalance_rule") or {}),
                "portfolio_spec": dict(contract.get("portfolio_spec") or {}),
                "execution_assumptions": dict(contract.get("execution_assumptions") or {}),
                "validation_profile": dict(contract.get("validation_profile") or {}),
                "targeting_policy": dict(contract.get("targeting_policy") or {}),
                "constraint_check": dict(contract.get("constraint_check") or {}),
                "target_symbols": list(target_symbols),
                "stock_pool": dict(contract.get("stock_pool") or {}),
                "selection_logic": list(contract.get("selection_logic") or []),
                "research_task": dict(contract.get("research_task") or strategy_spec.get("research_task") or normalized_task),
                "event_context": dict(contract.get("event_context") or strategy_spec.get("event_context") or {}),
                "hypothesis_artifact": hypothesis_artifact,
                "hypothesis_lowering_audit": dict(
                    contract.get("hypothesis_lowering_audit")
                    or evaluation.get("hypothesis_lowering_audit")
                    or {}
                ),
                "holding_rationale": hypothesis_artifact.get("holding_rationale"),
                "alpha_half_life": hypothesis_artifact.get("alpha_half_life"),
                "cost_sensitivity_grid": hypothesis_artifact.get("cost_sensitivity_grid"),
                "position_model": hypothesis_artifact.get("position_model"),
                "capacity_assumption": hypothesis_artifact.get("capacity_assumption"),
                "market_regime_assumption": hypothesis_artifact.get("market_regime_assumption"),
                "economic_semantics_score": hypothesis_artifact.get("economic_semantics_score"),
                "economic_semantics_missing_fields": list(
                    hypothesis_artifact.get("economic_semantics_missing_fields") or []
                ),
                "validation_focus": (
                    hypothesis_artifact.get("validation_focus")
                    or dict(contract.get("validation_profile") or {}).get("validation_focus")
                ),
                "replay_source": {
                    "experiment_id": payload.get("experiment_id"),
                    "generator_type": payload.get("generator_type"),
                    "status": payload.get("status"),
                    "source": payload.get("source"),
                },
                "committee_review": dict(evaluation.get("committee_review") or {}),
                "llm_analysis": dict(evaluation.get("llm_analysis") or {}),
                "llm_research_context": dict(evaluation.get("llm_research_context") or {}),
                "source_candidate": {
                    "name": name,
                    "description": description,
                    "strategy_type": strategy_type,
                    "params": dict(params),
                    "target_symbols": list(target_symbols),
                    "stock_pool": dict(contract.get("stock_pool") or {}),
                    "selection_logic": list(contract.get("selection_logic") or []),
                    "research_task": dict(contract.get("research_task") or strategy_spec.get("research_task") or normalized_task),
                    "event_context": dict(contract.get("event_context") or strategy_spec.get("event_context") or {}),
                    "hypothesis_artifact": hypothesis_artifact,
                },
            }
            tags = list(
                dict.fromkeys(
                    [
                        "hypothesis_replay",
                        *(list(contract.get("tags") or strategy_spec.get("tags") or [])[:8]),
                    ]
                )
            )
            return StrategySpec(
                strategy_type=strategy_type,
                params=params,
                name=name,
                description=description,
                tags=tags,
                metadata=metadata,
            )

        async def replay_persisted_specs(
            self,
            db,
            *,
            limit: int = 3,
            snapshot: Optional[dict[str, Any]] = None,
            parent_strategies: Optional[list[dict[str, Any]]] = None,
            research_task: Optional[dict[str, Any]] = None,
            trigger_reason: str = "provider_health_blocked",
        ) -> dict[str, Any]:
            del snapshot
            if not self._l2_hypothesis_replay_enabled() or not hasattr(db, "list_strategy_generation_experiments"):
                return {
                    "specs": [],
                    "report": {
                        "status": "disabled",
                        "trigger_reason": trigger_reason,
                        "selected_count": 0,
                    },
                }

            requested_limit = max(1, min(int(limit or 3), 10))
            rows: list[dict[str, Any]] = []
            for parent in list(parent_strategies or [])[:3]:
                parent_id = str((parent or {}).get("id") or "").strip()
                if not parent_id:
                    continue
                try:
                    rows.extend(
                        await db.list_strategy_generation_experiments(
                            parent_strategy_id=parent_id,
                            limit=max(6, requested_limit * 4),
                        )
                    )
                except Exception as exc:
                    logger.warning(
                        "LLMProxyStrategyGenerator: replay experiment lookup failed for %s: %s",
                        parent_id,
                        exc,
                    )
            replay_specs: list[tuple[tuple[float, int, int], StrategySpec, dict[str, Any]]] = []
            seen_ids: set[str] = set()
            for row in rows:
                row_payload = dict(row or {})
                experiment_id = str(row_payload.get("experiment_id") or "").strip()
                if experiment_id and experiment_id in seen_ids:
                    continue
                if experiment_id:
                    seen_ids.add(experiment_id)
                spec = self._replay_strategy_spec_from_experiment(row_payload, research_task=research_task)
                if spec is None:
                    continue
                evaluation = dict(row_payload.get("evaluation") or {})
                review = dict(evaluation.get("committee_review") or {})
                decision = str(review.get("decision") or "").strip().lower()
                status = str(row_payload.get("status") or "").strip().lower()
                decision_rank = {
                    "accept": 4,
                    "accepted": 4,
                    "revise": 3,
                    "retry": 2,
                    "generated": 2,
                    "review": 1,
                    "reject": 0,
                    "rejected": 0,
                }.get(decision, 1 if status in {"generated", "accepted"} else 0)
                try:
                    score = float(review.get("final_score") or 0.0)
                except Exception:
                    score = 0.0
                target_symbols = set(self._normalize_code_list(spec.metadata.get("target_symbols")))
                requested_targets = set(
                    self._normalize_code_list((research_task or {}).get("target_symbols"))
                )
                overlap = len(target_symbols.intersection(requested_targets)) if requested_targets else 0
                replay_specs.append(((score, overlap, decision_rank), spec, row_payload))

            replay_specs.sort(key=lambda item: item[0], reverse=True)
            deduped_specs = self._dedupe_specs([item[1] for item in replay_specs])
            selected_specs = deduped_specs[:requested_limit]
            selected_ids: list[str] = []
            selected_status_counts: dict[str, int] = {}
            for _rank, _spec, row_payload in replay_specs:
                if len(selected_ids) >= len(selected_specs):
                    break
                candidate_key = (
                    str(_spec.strategy_type or ""),
                    json.dumps(_spec.params or {}, sort_keys=True, ensure_ascii=False, default=str),
                )
                if candidate_key not in {
                    (
                        str(spec.strategy_type or ""),
                        json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str),
                    )
                    for spec in selected_specs
                }:
                    continue
                experiment_id = str(row_payload.get("experiment_id") or "").strip()
                if experiment_id:
                    selected_ids.append(experiment_id)
                status = str(row_payload.get("status") or "unknown").strip().lower() or "unknown"
                selected_status_counts[status] = selected_status_counts.get(status, 0) + 1

            return {
                "specs": selected_specs,
                "report": {
                    "status": "succeeded" if selected_specs else "empty",
                    "trigger_reason": trigger_reason,
                    "available_count": len(replay_specs),
                    "selected_count": len(selected_specs),
                    "experiment_ids": selected_ids,
                    "status_counts": selected_status_counts,
                },
            }

        async def _generate_via_pipeline(
            self,
            db,
            limit: int = 3,
            snapshot: Optional[dict] = None,
            research_task: Optional[dict[str, Any]] = None,
            timeout_sec: Optional[float] = None,
        ) -> list[StrategySpec]:
            """使用多阶段 Pipeline 生成策略候选。"""
            _pipeline_mode, pipeline_factory = _resolve_pipeline_runtime_symbols()
            pipeline = pipeline_factory()
            pipeline_timeout_sec = float(timeout_sec or self._pipeline_run_timeout_sec())
            pipeline_result = await asyncio.wait_for(
                pipeline.run_pipeline(
                    db=db,
                    snapshot=snapshot or {},
                    research_task=research_task,
                ),
                timeout=pipeline_timeout_sec,
            )

            specs: list[StrategySpec] = []
            pipeline_precompile_rejections: list[dict[str, Any]] = []
            normalized_research_task = (
                _normalize_research_task_contract(research_task)
                if isinstance(research_task, dict) and research_task
                else {}
            )
            for candidate in pipeline_result.candidates[:limit]:
                candidate_payload = dict(candidate or {})
                if normalized_research_task and not candidate_payload.get("research_task"):
                    candidate_payload["research_task"] = dict(normalized_research_task)
                spec = self._pipeline_candidate_to_spec(candidate_payload, pipeline_result.provenance)
                if spec is not None:
                    specs.append(spec)
                elif candidate_payload.get("_generator_precompile_reject_reasons"):
                    pipeline_precompile_rejections.append(
                        {
                            "name": str(candidate_payload.get("name") or ""),
                            "strategy_type": str(candidate_payload.get("strategy_type") or ""),
                            "reject_reasons": list(candidate_payload.get("_generator_precompile_reject_reasons") or []),
                        }
                    )

            stage_requests: list[dict[str, Any]] = []
            llm_attempt_count = 0
            llm_success_count = 0
            llm_elapsed_seconds = 0.0
            last_error = None
            last_error_type = None
            for stage_id, stage_result in pipeline_result.stages.items():
                stage_error = getattr(stage_result, "llm_error", None) or stage_result.error
                stage_error_type = getattr(stage_result, "llm_error_type", None)
                stage_error_metrics = dict(getattr(stage_result, "llm_error_metrics", {}) or {})
                if stage_error and last_error is None:
                    last_error = stage_error
                    last_error_type = stage_error_type or (
                        stage_error.split(":", 1)[0] if ":" in stage_error else stage_error
                    )
                if not getattr(stage_result, "llm_attempted", False):
                    continue
                llm_attempt_count += 1
                llm_elapsed_seconds += float(stage_result.elapsed_sec or 0.0)
                if not stage_result.used_fallback:
                    llm_success_count += 1
                request_status = "succeeded"
                if stage_result.used_fallback:
                    metric_status = _normalize_external_request_status(stage_error_metrics.get("status"))
                    request_status = metric_status if metric_status in _NON_REQUEST_SKIP_STATUSES else "fallback"
                request_attempt_count = 0
                if request_status not in _NON_REQUEST_SKIP_STATUSES:
                    try:
                        request_attempt_count = int(stage_error_metrics.get("attempt_count") or 0)
                    except Exception:
                        request_attempt_count = 0
                    request_attempt_count = max(request_attempt_count, 1)
                stage_requests.append(
                    {
                        "stage_id": stage_id,
                        "status": request_status,
                        "used_fallback": bool(stage_result.used_fallback),
                        "elapsed_seconds": round(float(stage_result.elapsed_sec or 0.0), 4),
                        "prompt_chars": int(stage_result.prompt_chars or 0),
                        "response_chars": int(stage_result.response_chars or 0),
                        "error": stage_error,
                        "error_type": stage_error_type,
                        "request_metrics": {
                            "status": stage_error_metrics.get("status"),
                            "attempt_count": request_attempt_count,
                            "prompt_chars": int(stage_result.prompt_chars or 0),
                            "response_chars": int(stage_result.response_chars or 0),
                            "elapsed_seconds": round(float(stage_result.elapsed_sec or 0.0), 4),
                            "last_error_type": stage_error_type,
                            "last_error": stage_error,
                            "last_error_status_code": (
                                stage_error_metrics.get("last_error_status_code")
                                or stage_error_metrics.get("status_code")
                            ),
                            "empty_200_response": bool(stage_error_metrics.get("empty_200_response")),
                        },
                    }
                )

            if specs:
                external_status = "succeeded" if llm_success_count > 0 else "fallback_only"
            elif pipeline_result.error:
                external_status = "failed"
            elif llm_attempt_count > 0:
                external_status = "non_executable"
            else:
                external_status = "skipped"

            self.last_report = {
                'pipeline_mode': 'staged',
                'pipeline_provenance': pipeline_result.provenance,
                'pipeline_error': pipeline_result.error,
                'selected_count': len(specs),
                'selected_generators': {'pipeline_staged': len(specs)},
                'pipeline_precompile_rejected_count': len(pipeline_precompile_rejections),
                'pipeline_precompile_rejections': pipeline_precompile_rejections[:8],
                'external_provider': {
                    'enabled': True,
                    'provider': getattr(self.external_provider.config, 'provider', None),
                    'model': getattr(self.external_provider.config, 'model', None),
                    'status': external_status,
                    'requests': stage_requests,
                    'selected_count': len(specs),
                    'viable_selected_count': len(specs),
                    'fallback_count': len(specs) if external_status == 'fallback_only' else 0,
                    'elapsed_seconds': round(llm_elapsed_seconds, 4),
                    'last_error_type': last_error_type,
                    'last_error': last_error,
                },
            }
            self.last_report['external_provider'] = _finalize_external_provider_report(
                self.last_report.get('external_provider')
            )
            return specs

        @classmethod
        def _pipeline_candidate_to_spec(
            cls,
            candidate: dict[str, Any],
            provenance: dict[str, Any],
        ) -> Optional[StrategySpec]:
            """将 pipeline 产出的 candidate dict 转为 StrategySpec。"""
            if not candidate or not isinstance(candidate, dict):
                return None
            original_candidate = candidate
            candidate = _normalize_snapshot_pipeline_candidate(candidate)
            if candidate is None:
                return None
            research_task = _normalize_research_task_contract(candidate.get('research_task') or {})
            target_symbols = cls._normalize_code_list(candidate.get('target_symbols'))
            validation_focus = str((research_task.get('validation_focus') or 'target_plus_representative')).strip().lower()
            portfolio_spec = dict(candidate.get('portfolio_spec') or {
                'position_assumption': 'equal_weight_proxy' if len(target_symbols) > 1 else 'single_name_full_notional',
                'target_weight_scheme': 'equal_weight' if len(target_symbols) > 1 else 'single_name',
            })
            execution_assumptions = dict(candidate.get('execution_assumptions') or {
                'commission_rate': 0.00025,
                'slippage_bps': 5,
                'tradability_filter': True,
                'slippage_model': 'fixed',
            })
            validation_profile = dict(candidate.get('validation_profile') or {
                'profile': 'event_trade_validation' if validation_focus == 'event_target_only' else 'trade_rule_validation',
                'validation_focus': validation_focus,
                'primary_validation_layer': 'target' if validation_focus == 'event_target_only' else 'combined',
            })
            precompile_validation = validate_precompile_candidate_contract(
                {
                    **candidate,
                    'research_task': dict(research_task),
                    'strategy_type': str(candidate.get('strategy_type') or 'dsl_rule').strip() or 'dsl_rule',
                    'target_symbols': list(target_symbols),
                    'stock_pool': dict(
                        candidate.get('stock_pool')
                        or ({'selection_mode': 'explicit', 'symbols': list(target_symbols)} if target_symbols else {})
                    ),
                    'portfolio_spec': dict(portfolio_spec),
                    'execution_assumptions': dict(execution_assumptions),
                    'validation_profile': dict(validation_profile),
                    'constraint_check': dict(candidate.get('constraint_check') or {}),
                },
                research_task=research_task,
                source='pipeline_staged',
            )
            if not precompile_validation.accepted:
                original_candidate["_generator_precompile_reject_reasons"] = list(precompile_validation.reject_reasons)
                original_candidate["_generator_precompile_validation"] = precompile_validation.to_dict()
                candidate["_generator_precompile_reject_reasons"] = list(precompile_validation.reject_reasons)
                candidate["_generator_precompile_validation"] = precompile_validation.to_dict()
                return None
            target_symbols = list(precompile_validation.target_symbols)
            candidate = {
                **candidate,
                'research_task': dict(research_task),
                'target_symbols': list(target_symbols),
                'stock_pool': dict(precompile_validation.stock_pool),
                'constraint_check': dict(precompile_validation.constraint_check),
            }

            # 尝试通过 DSL 编译获得可执行策略
            compiled: Optional[dict] = None
            dsl = candidate.get('dsl')
            if dsl and isinstance(dsl, dict):
                try:
                    compiled = compile_strategy_blueprint(candidate, tune_for_factory=True)
                except Exception:
                    compiled = None

            if compiled:
                compiled_meta = dict(compiled.get('metadata') or {})
                params = dict(compiled.get('params') or {})
                strategy_type = str(compiled.get('strategy_type') or 'dsl_rule')
                name = str(compiled.get('name') or candidate.get('name') or 'AI Pipeline 策略')
                description = str(compiled.get('description') or candidate.get('description') or '')
            else:
                # DSL 编译失败时，尝试直接用 strategy_type + params
                strategy_type = str(candidate.get('strategy_type') or 'dsl_rule')
                params = dict(candidate.get('params') or {})
                if not params and dsl:
                    params = {'dsl': dsl}
                name = str(candidate.get('name') or 'AI Pipeline 策略')
                description = str(candidate.get('description') or '')
                compiled_meta = {}

            if target_symbols and strategy_type == 'dsl_rule':
                dsl_params = dict(params.get('dsl') or {})
                dsl_metadata = dict(dsl_params.get('metadata') or {})
                dsl_metadata['target_symbols'] = list(target_symbols)
                dsl_params['metadata'] = dsl_metadata
                params['dsl'] = dsl_params

            tags = ['pipeline_staged', *(compiled_meta.get('tags') or []), *(candidate.get('tags') or [])]
            if target_symbols:
                tags.append('targeted_universe')

            metadata = {
                **compiled_meta,
                'generator_type': 'pipeline_staged',
                'hypothesis': str(candidate.get('hypothesis') or candidate.get('description') or ''),
                'holding_horizon': dict(candidate.get('holding_horizon') or {}),
                'trade_plan': dict(candidate.get('trade_plan') or {}),
                'risk_rules': dict(candidate.get('risk_rules') or ((params.get('dsl') or {}).get('risk_rules') or {})),
                'position_sizing': dict(candidate.get('position_sizing') or {}),
                'execution_notes': candidate.get('execution_notes'),
                'rebalance_rule': dict(candidate.get('rebalance_rule') or {'mode': 'signal_rebalance'}),
                'portfolio_spec': dict(precompile_validation.portfolio_spec),
                'execution_assumptions': dict(precompile_validation.execution_assumptions),
                'validation_profile': dict(precompile_validation.validation_profile),
                'targeting_policy': dict(candidate.get('targeting_policy') or {}),
                'constraint_check': dict(precompile_validation.constraint_check),
                'market_regime_assumption': candidate.get('market_regime_assumption'),
                'position_sizing_rationale': candidate.get('position_sizing_rationale'),
                'capacity_bucket': candidate.get('capacity_bucket'),
                'turnover_cost_class': candidate.get('turnover_cost_class'),
                'expected_turnover_band': candidate.get('expected_turnover_band'),
                'economic_semantics_score': candidate.get('economic_semantics_score'),
                'economic_semantics_missing_fields': list(candidate.get('economic_semantics_missing_fields') or []),
                'target_symbols': list(target_symbols),
                'stock_pool': dict(
                    candidate.get('stock_pool')
                    or ((params.get('dsl') or {}).get('metadata') or {}).get('stock_pool')
                    or ({'selection_mode': 'explicit', 'symbols': list(target_symbols)} if target_symbols else {})
                ),
                'selection_logic': list(candidate.get('selection_logic') or []),
                'research_scope': dict(candidate.get('research_scope') or {}),
                'event_context': dict(candidate.get('event_context') or {}),
                'research_task': dict(candidate.get('research_task') or {}),
                'pipeline_provenance': provenance,
                'source_candidate': candidate,
            }

            return StrategySpec(
                strategy_type=strategy_type,
                params=params,
                name=name,
                description=description,
                tags=list(dict.fromkeys(tags)),
                metadata=metadata,
            )

        async def generate(self, db, limit: int = 3, snapshot: Optional[dict] = None, parent_strategies: Optional[list[dict]] = None, research_task: Optional[dict[str, Any]] = None) -> list[StrategySpec]:
            snapshot = snapshot or {}
            shared_generation_context = dict(snapshot.get('_shared_generation_context') or {})
            if parent_strategies is None and shared_generation_context.get('parent_strategies'):
                parent_strategies = [dict(item or {}) for item in list(shared_generation_context.get('parent_strategies') or [])]
            requested_limit = max(1, min(int(limit or 3), 10))
            history_summary = [
                dict(item or {})
                for item in list(shared_generation_context.get('history_summary') or [])
            ]
            if not history_summary:
                history_summary = await self._recent_experiments(db, parent_strategies=parent_strategies)
            research_context = await self._build_research_context(
                db,
                snapshot,
                parent_strategies=parent_strategies,
                history_summary=history_summary,
                research_task=research_task,
            )
            research_context_summary = self._summarize_research_context(research_context)
            task_target_context = dict(research_context.get('task_target_context') or {})
            target_context_blocked = bool(research_context.get('blocked_by_target_universe'))
            targeted_research = bool(
                task_target_context.get('targeted_task')
                or self._normalize_code_list((research_task or {}).get('target_symbols'))
            )
            allowed_strategy_types = {
                str(item).strip().lower()
                for item in list((research_task or {}).get('allowed_strategy_types') or [])
                if str(item).strip()
            }
            allow_target_context_recovery = bool(
                self.external_provider.is_enabled()
                and (
                    'dsl_rule' in allowed_strategy_types
                    or 'open_dsl' in allowed_strategy_types
                    or 'llm_defined' in allowed_strategy_types
                )
            )
            recovered_target_frame: Optional[pd.DataFrame] = None
            recovered_target_context = False
            # 多阶段 pipeline 路径
            _pipeline_fallback_reason: Optional[str] = None
            skip_monolithic_external_provider = False
            pipeline_run_timeout_sec: Optional[float] = None
            pipeline_mode, _pipeline_factory = _resolve_pipeline_runtime_symbols()
            pipeline_disabled_by_scheduler = bool((research_task or {}).get('disable_pipeline_staged'))
            pipeline_disable_reason = str(
                (research_task or {}).get('pipeline_staged_skip_reason') or 'generator_mode_cooldown'
            ).strip()
            if targeted_research and target_context_blocked and allow_target_context_recovery:
                recovered_target_frame = await self._build_market_frame(db, research_task=research_task)
                if recovered_target_frame is not None and not recovered_target_frame.empty:
                    recovered_target_context = True
                    target_context_blocked = False
                    task_target_context = {
                        **task_target_context,
                        'status': 'recovered_from_explicit_target_frame',
                        'blocked_by_target_universe': False,
                        'matched_target_symbols': list(
                            self._normalize_code_list((research_task or {}).get('target_symbols'))
                        ),
                        'candidate_universe_symbols': list(
                            self._normalize_code_list((research_task or {}).get('target_symbols'))
                        ),
                    }
                    research_context = {
                        **research_context,
                        'blocked_by_target_universe': False,
                        'target_context_status': 'recovered_from_explicit_target_frame',
                        'task_target_context': task_target_context,
                    }
                    research_context_summary = self._summarize_research_context(research_context)
                else:
                    recovered_target_frame = None
            if targeted_research and target_context_blocked:
                if pipeline_mode == 'staged':
                    _pipeline_fallback_reason = 'target_context_blocked'
                report: dict[str, Any] = {
                    'requested_limit': requested_limit,
                    'market_frame_ready': False,
                    'market_frame_rows': 0,
                    'market_frame_source': 'target_context_blocked',
                    'research_context': research_context,
                    'research_context_summary': research_context_summary,
                    'external_provider': {
                        'enabled': bool(self.external_provider.is_enabled()),
                        'provider': getattr(self.external_provider.config, 'provider', None),
                        'model': getattr(self.external_provider.config, 'model', None),
                        'status': 'skipped_target_context_blocked',
                        'request_limits': [],
                        'requests': [],
                        'selected_count': 0,
                        'viable_selected_count': 0,
                        'fallback_count': 0,
                        'analysis': {},
                    },
                    'local_generator': {
                        'status': 'skipped_target_context_blocked',
                        'precompile_rejected_count': 0,
                        'precompile_rejections': [],
                    },
                    'selected_count': 0,
                    'selected_generators': {},
                    'research_task': dict(research_task or {}),
                    'pipeline_run_timeout_sec': None,
                }
                if _pipeline_fallback_reason:
                    report['pipeline_staged_fallback_reason'] = _pipeline_fallback_reason
                report['external_provider'] = _finalize_external_provider_report(report.get('external_provider'))
                self.last_report = report
                return []
            if pipeline_disabled_by_scheduler and pipeline_mode == 'staged':
                _pipeline_fallback_reason = pipeline_disable_reason or 'generator_mode_cooldown'
            elif pipeline_mode == 'staged' and self.external_provider.is_enabled():
                pipeline_run_timeout_sec = self._pipeline_run_timeout_sec()
                try:
                    staged_specs = await self._generate_via_pipeline(
                        db=db,
                        limit=limit,
                        snapshot=snapshot,
                        research_task=research_task,
                        timeout_sec=pipeline_run_timeout_sec,
                    )
                    if staged_specs:
                        return staged_specs
                    _pipeline_fallback_reason = 'returned_empty'
                    logger.info('Pipeline staged mode returned no specs, falling back to monolithic')
                except asyncio.TimeoutError as exc:
                    _pipeline_fallback_reason = 'pipeline_timeout'
                    skip_monolithic_external_provider = True
                    logger.warning(
                        'Pipeline staged mode timed out after %.1fs, falling back to local-only path: %s',
                        float(pipeline_run_timeout_sec or 0.0),
                        exc,
                    )
                except Exception as exc:
                    _pipeline_fallback_reason = f'{type(exc).__name__}: {exc}'
                    logger.warning('Pipeline staged mode failed: %s, falling back to monolithic', exc)

            frame = recovered_target_frame
            frame_source = (
                'recovered_explicit_target_frame'
                if recovered_target_context and frame is not None and not frame.empty
                else 'none'
            )
            if frame is None or frame.empty:
                frame = await self._build_market_frame(db, research_task=research_task)
                frame_source = 'primary_market_frame' if frame is not None and not frame.empty else 'none'
            frame_cache = await self._build_symbol_frame_cache(db, research_context=research_context, research_task=research_task)
            if (frame is None or frame.empty) and frame_cache:
                for cached_frame in frame_cache.values():
                    if cached_frame is not None and not cached_frame.empty:
                        frame = cached_frame.tail(120).copy()
                        frame_source = 'research_context_frame_cache'
                        break
            if frame is None or frame.empty:
                synthetic_frame = self._build_synthetic_market_frame(research_context)
                if synthetic_frame is not None and not synthetic_frame.empty:
                    frame = synthetic_frame
                    frame_source = 'synthetic_research_context_frame'
            report: dict[str, Any] = {
                'requested_limit': requested_limit,
                'market_frame_ready': bool(frame is not None and not frame.empty),
                'market_frame_rows': int(len(frame)) if frame is not None and not frame.empty else 0,
                'market_frame_source': frame_source,
                'research_context': research_context,
                'research_context_summary': research_context_summary,
                'external_provider': {
                    'enabled': bool(self.external_provider.is_enabled()),
                    'provider': getattr(self.external_provider.config, 'provider', None),
                    'model': getattr(self.external_provider.config, 'model', None),
                    'status': 'skipped',
                    'request_limits': [],
                    'requests': [],
                    'selected_count': 0,
                    'viable_selected_count': 0,
                    'fallback_count': 0,
                    'analysis': {},
                },
                'local_generator': {
                    'status': 'pending',
                    'precompile_rejected_count': 0,
                    'precompile_rejections': [],
                },
                'selected_count': 0,
                'selected_generators': {},
                'research_task': dict(research_task or {}),
                'pipeline_run_timeout_sec': round(float(pipeline_run_timeout_sec or 0.0), 4) if pipeline_run_timeout_sec is not None else None,
            }
            external_specs: list[StrategySpec] = []
            fallback_external_specs: list[StrategySpec] = []
            if skip_monolithic_external_provider:
                report['external_provider']['status'] = 'skipped_after_pipeline_timeout'
                report['external_provider']['last_error_type'] = 'PipelineTimeout'
                report['external_provider']['last_error'] = 'staged pipeline timed out; monolithic external provider skipped for this task'
            elif frame is not None and not frame.empty and self.external_provider.is_enabled():
                base_request_limit = max(2, min(int(limit or 3), 3))
                request_limits = [base_request_limit for _ in range(max(1, min(int(LLM_FAN_OUT_COUNT or 1), 4)))]
                report['external_provider']['request_limits'] = list(request_limits)
                last_exc: Optional[Exception] = None
                successful_request_without_specs = False
                external_started_at = time.perf_counter()
                request_results = await asyncio.gather(*[
                    self._run_external_provider_request(
                        snapshot=snapshot,
                        frame=frame,
                        frame_cache=frame_cache,
                        research_context=research_context,
                        parent_strategies=list(parent_strategies or []),
                        history_summary=history_summary,
                        research_task=research_task,
                        request_limit=request_limit,
                        request_index=request_index,
                    )
                    for request_index, request_limit in enumerate(request_limits, 1)
                ])
                aggregated_viable_specs: list[StrategySpec] = []
                aggregated_all_specs: list[StrategySpec] = []
                for result in sorted(request_results, key=lambda item: int(item.get('request_index') or 0)):
                    report['external_provider']['requests'].append(dict(result.get('request_report') or {}))
                    successful_request_without_specs = successful_request_without_specs or bool(result.get('successful_without_specs'))
                    aggregated_viable_specs.extend(list(result.get('viable_specs') or []))
                    aggregated_all_specs.extend(list(result.get('all_specs') or []))
                    analysis = dict(result.get('analysis') or {})
                    if analysis and not report['external_provider']['analysis']:
                        report['external_provider']['analysis'] = analysis
                    if result.get('status') == 'failed' and result.get('exception') is not None:
                        last_exc = result.get('exception')
                aggregated_viable_specs = self._dedupe_specs(sorted(aggregated_viable_specs, key=self._spec_preflight_score, reverse=True))
                aggregated_all_specs = self._dedupe_specs(sorted(aggregated_all_specs, key=self._spec_preflight_score, reverse=True))
                open_dsl_cap = open_dsl_max_candidates_per_run()

                def _apply_open_dsl_cap(specs: list[StrategySpec]) -> tuple[list[StrategySpec], int, int]:
                    if open_dsl_cap < 0:
                        return list(specs), 0, 0
                    capped: list[StrategySpec] = []
                    selected_open_dsl = 0
                    overflow = 0
                    for spec in list(specs or []):
                        if is_open_dsl_spec_metadata(dict(spec.metadata or {})):
                            if selected_open_dsl >= open_dsl_cap:
                                overflow += 1
                                continue
                            selected_open_dsl += 1
                        capped.append(spec)
                    return capped, selected_open_dsl, overflow

                aggregated_viable_specs, open_dsl_viable_selected_count, open_dsl_viable_overflow_count = _apply_open_dsl_cap(
                    aggregated_viable_specs
                )
                aggregated_all_specs, _open_dsl_all_selected_count, open_dsl_all_overflow_count = _apply_open_dsl_cap(
                    aggregated_all_specs
                )
                if aggregated_viable_specs:
                    external_specs = aggregated_viable_specs[:limit]
                    selected_keys = {
                        (str(spec.strategy_type or ''), json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str))
                        for spec in external_specs
                    }
                    fallback_external_specs = [
                        spec for spec in aggregated_all_specs
                        if (
                            str(spec.strategy_type or ''),
                            json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str),
                        ) not in selected_keys
                    ]
                elif aggregated_all_specs:
                    fallback_external_specs = aggregated_all_specs[:limit]
                report['external_provider']['elapsed_seconds'] = round(time.perf_counter() - external_started_at, 4)
                report['external_provider']['viable_selected_count'] = len(external_specs)
                report['external_provider']['fallback_count'] = len(fallback_external_specs)
                report['external_provider']['open_dsl_max_candidates_per_run'] = open_dsl_cap
                report['external_provider']['open_dsl_viable_selected_count'] = open_dsl_viable_selected_count
                report['external_provider']['open_dsl_selected_count'] = sum(
                    1 for spec in [*external_specs, *fallback_external_specs]
                    if is_open_dsl_spec_metadata(dict(spec.metadata or {}))
                )
                report['external_provider']['open_dsl_overflow_count'] = max(
                    open_dsl_viable_overflow_count,
                    open_dsl_all_overflow_count,
                )
                if external_specs:
                    report['external_provider']['status'] = 'succeeded'
                elif fallback_external_specs:
                    report['external_provider']['status'] = 'fallback_only'
                elif successful_request_without_specs:
                    report['external_provider']['status'] = 'non_executable'
                    report['external_provider']['last_error_type'] = 'NoExecutableCandidates'
                    report['external_provider']['last_error'] = 'external llm returned candidates but none compiled into executable strategies'
                elif last_exc is not None:
                    report['external_provider']['status'] = 'failed'
                    last_metrics = dict(getattr(last_exc, 'metrics', {}) or {})
                    report['external_provider']['last_error_type'] = last_metrics.get('last_error_type') or last_exc.__class__.__name__
                    report['external_provider']['last_error'] = last_metrics.get('last_error') or str(last_exc) or last_exc.__class__.__name__
                if self.external_provider.config.strict and last_exc is not None and not external_specs and not fallback_external_specs:
                    self.last_report = report
                    raise last_exc

            if frame is None or frame.empty:
                selected = (external_specs or fallback_external_specs)[:limit]
                generator_counts: dict[str, int] = {}
                for spec in selected:
                    generator_type = str(spec.metadata.get('generator_type') or 'unknown')
                    generator_counts[generator_type] = generator_counts.get(generator_type, 0) + 1
                report['selected_count'] = len(selected)
                report['selected_generators'] = generator_counts
                report['external_provider']['selected_count'] = generator_counts.get('external_llm', 0)
                report['local_generator']['status'] = 'skipped_no_market_frame'
                report['external_provider'] = _finalize_external_provider_report(report.get('external_provider'))
                self.last_report = report
                return selected
            local_specs: list[StrategySpec] = []
            allow_local_specs = not targeted_research or (not external_specs and not fallback_external_specs)
            if allow_local_specs:
                report['local_generator']['status'] = 'running'
                local_limit = limit
                if targeted_research and str((research_task or {}).get('task_source') or '').strip().lower() == 'event_driven':
                    local_limit = 1
                raw = self.miner.generate_factor_candidates(frame, news_data=None, num_candidates=max(local_limit, 3))
                raw = sorted(
                    raw,
                    key=lambda item: self._local_category_rank(str((item or {}).get('category') or 'custom').strip().lower(), research_task=research_task),
                )
                for candidate in raw:
                    spec = self._local_candidate_to_spec(candidate, research_task=research_task)
                    if spec is not None:
                        local_specs.append(spec)
                    elif candidate.get("_generator_precompile_reject_reasons"):
                        report['local_generator']['precompile_rejected_count'] += 1
                        if len(report['local_generator']['precompile_rejections']) < 8:
                            report['local_generator']['precompile_rejections'].append(
                                {
                                    'name': str(candidate.get('name') or ''),
                                    'category': str(candidate.get('category') or ''),
                                    'reject_reasons': list(candidate.get("_generator_precompile_reject_reasons") or []),
                                }
                            )
                    if len(local_specs) >= local_limit:
                        break
                report['local_generator']['status'] = 'succeeded' if local_specs else 'empty'
            else:
                report['local_generator']['status'] = 'skipped_external_selected'
            if len(external_specs) >= limit:
                selected = external_specs[:limit]
                generator_counts: dict[str, int] = {}
                for spec in selected:
                    generator_type = str(spec.metadata.get('generator_type') or 'unknown')
                    generator_counts[generator_type] = generator_counts.get(generator_type, 0) + 1
                report['selected_count'] = len(selected)
                report['selected_generators'] = generator_counts
                report['external_provider']['selected_count'] = generator_counts.get('external_llm', 0)
                self.last_report = report
                return selected
            merged: list[StrategySpec] = []
            seen = set()
            if self.external_provider.config.strict:
                fallback_order = [*external_specs, *fallback_external_specs, *local_specs]
            else:
                preferred_external = fallback_external_specs[:1]
                remaining_external = fallback_external_specs[1:]
                fallback_order = [*external_specs, *preferred_external, *local_specs, *remaining_external]
            for spec in fallback_order:
                key = (spec.strategy_type, json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(spec)
                if len(merged) >= limit:
                    break
            generator_counts: dict[str, int] = {}
            for spec in merged:
                generator_type = str(spec.metadata.get('generator_type') or 'unknown')
                generator_counts[generator_type] = generator_counts.get(generator_type, 0) + 1
            report['selected_count'] = len(merged)
            report['selected_generators'] = generator_counts
            report['external_provider']['selected_count'] = generator_counts.get('external_llm', 0)
            if _pipeline_fallback_reason:
                report['pipeline_staged_fallback_reason'] = _pipeline_fallback_reason
                pipeline_report = getattr(self, 'last_report', None) or {}
                report['pipeline_staged_provenance'] = pipeline_report.get('pipeline_provenance')
                report['pipeline_staged_error'] = pipeline_report.get('pipeline_error')
            report['external_provider'] = _finalize_external_provider_report(report.get('external_provider'))
            self.last_report = report
            return merged
