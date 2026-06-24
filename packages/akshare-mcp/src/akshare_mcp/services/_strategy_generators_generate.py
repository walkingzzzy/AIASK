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
    from strategy_factory.api import (
        extract_event_context as _extract_event_context,
        preferred_strategy_types_for_factor,
    )
    from strategy_factory.api.constants import (
        CATEGORY_MINIMUMS,
        LLM_FAN_OUT_COUNT,
        PIPELINE_MODE,
        PIPELINE_STAGE_TIMEOUTS,
        PIPELINE_STAGE_TIMEOUT_SEC,
    )
    from strategy_factory.api.semantic_contract import (
        resolve_candidate_validation_profile,
        validate_precompile_candidate_contract,
    )
    from strategy_factory.api.semantic_contract import apply_target_symbol_policy, normalize_research_task_contract
    return {
        "CATEGORY_MINIMUMS": CATEGORY_MINIMUMS,
        "LLM_FAN_OUT_COUNT": LLM_FAN_OUT_COUNT,
        "PIPELINE_MODE": PIPELINE_MODE,
        "PIPELINE_STAGE_TIMEOUTS": PIPELINE_STAGE_TIMEOUTS,
        "PIPELINE_STAGE_TIMEOUT_SEC": PIPELINE_STAGE_TIMEOUT_SEC,
        "extract_event_context": _extract_event_context,
        "preferred_strategy_types_for_factor": preferred_strategy_types_for_factor,
        "apply_target_symbol_policy": apply_target_symbol_policy,
        "normalize_research_task_contract": normalize_research_task_contract,
        "resolve_candidate_validation_profile": resolve_candidate_validation_profile,
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
        "apply_target_symbol_policy": "apply_target_symbol_policy",
        "normalize_research_task_contract": "normalize_research_task_contract",
        "resolve_candidate_validation_profile": "resolve_candidate_validation_profile",
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
apply_target_symbol_policy = _sf()["apply_target_symbol_policy"]
normalize_research_task_contract = _sf()["normalize_research_task_contract"]
resolve_candidate_validation_profile = _sf()["resolve_candidate_validation_profile"]
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


def _pipeline_report_has_provider_output_format_failure(report: Optional[dict[str, Any]]) -> bool:
    payload = dict(report or {})
    provenance = dict(payload.get("pipeline_provenance") or {})
    stages = dict(provenance.get("stages") or {})
    for stage_payload in stages.values():
        stage = dict(stage_payload or {})
        metrics = dict(stage.get("llm_error_metrics") or {})
        if bool(metrics.get("local_fallback_suppressed")):
            return True
        if str(metrics.get("suppression_reason") or "").strip().lower() == "provider_output_format_failure":
            return True
    external_provider = dict(payload.get("external_provider") or {})
    for request in list(external_provider.get("requests") or []):
        request_payload = dict(request or {})
        metrics = dict(request_payload.get("request_metrics") or {})
        if bool(metrics.get("local_fallback_suppressed")):
            return True
        if str(metrics.get("suppression_reason") or "").strip().lower() == "provider_output_format_failure":
            return True
    return False


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
        'event_structure_breakout': {
            'template_generation_profile': 'high_precision_event_structure',
            'holding_horizon': {'min_days': 3, 'max_days': 12, 'expected_turnover_band': 'low'},
            'trade_plan': {'entry_bias': 'event_structure_breakout_confirmation', 'exit_bias': 'breakout_failure_or_time_stop'},
            'risk_rules': {'stop_loss_pct': 0.06, 'take_profit_pct': 0.16, 'max_holding_days': 12, 'max_position_pct': 0.14},
            'position_sizing': {'mode': 'equal_weight', 'position_assumption': 'equal_weight_proxy'},
            'rebalance_rule': {'mode': 'signal_rebalance', 'frequency_days': 4},
            'portfolio_spec': {'position_assumption': 'equal_weight_proxy', 'target_weight_scheme': 'equal_weight', 'weight_method': 'event_structure_breakout_weight', 'max_position_pct': 0.14},
            'execution_assumptions': {'commission_rate': 0.00025, 'slippage_bps': 5, 'tradability_filter': True, 'slippage_model': 'fixed', 'market_ruleset': 'cn_equity', 'market_impact_bps': 1.0, 'capacity_bucket': 'mid'},
            'validation_profile': {'profile': 'event_trade_validation', 'validation_focus': 'candidate_target_only', 'primary_validation_layer': 'target', 'objective_profile': 'high_precision', 'trade_density_preference': 'low', 'regime_required': True, 'cost_robust_required': True, 'entry_selectivity': 'strict_event_breakout', 'preferred_regime': 'event_follow_through_with_structure_confirmation', 'avoid_regime': 'false_breakout_or_post_event_mean_reversion'},
            'targeting_policy': {'target_symbol_policy': 'strict_intersection', 'universe_scope': 'liquid_event_breakout_leaders', 'universe_expansion_policy': 'forbid'},
            'rule_template_contract': {'template_generation_profile': 'high_precision_event_structure', 'applicable_universe': {'market_cap': 'mid_large', 'liquidity': 'high', 'style_bias': 'event_structure_follow_through'}, 'target_layer': 'target', 'default_risk_constraints': {'stop_loss_pct': 0.06, 'take_profit_pct': 0.16, 'max_holding_days': 12, 'max_position_pct': 0.14}, 'portfolio_weight_method': 'event_structure_breakout_weight'},
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


def _snapshot_pool_risk_contract(pool_profile: str, strategy_type: str) -> dict[str, Any]:
    profile = str(pool_profile or "").strip().lower()
    strategy_key = str(strategy_type or "").strip().lower()
    if profile == "high_vol_growth":
        if strategy_key in {"volatility_breakout", "event_structure_breakout", "momentum"}:
            return {
                "holding_horizon": {"min_days": 5, "max_days": 8},
                "trade_plan": {"exit_bias": "atr_trailing_or_time_stop"},
                "risk_rules": {
                    "stop_loss_mode": "atr_bucketed",
                    "atr_window": 14,
                    "atr_multiplier": 2.2,
                    "stop_floor_pct": 0.05,
                    "stop_loss_pct": 0.05,
                    "take_profit_pct": 0.10,
                    "time_stop_days": 8,
                    "max_holding_days": 8,
                    "position_cap_pct": 0.10,
                    "max_position_pct": 0.10,
                    "trailing_activation_r": 1.0,
                    "stop_rule_source": "atr_bucketed_high_vol_growth_breakout",
                },
            }
        return {
            "holding_horizon": {"min_days": 1, "max_days": 5},
            "trade_plan": {"exit_bias": "fast_reversion_or_time_stop"},
            "risk_rules": {
                "stop_loss_mode": "atr_bucketed",
                "atr_window": 14,
                "atr_multiplier": 1.8,
                "stop_floor_pct": 0.04,
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.08,
                "time_stop_days": 5,
                "max_holding_days": 5,
                "position_cap_pct": 0.10,
                "max_position_pct": 0.10,
                "trailing_activation_r": 1.0,
                "stop_rule_source": "atr_bucketed_high_vol_growth_reversion",
            },
        }
    if profile == "low_vol_defensive":
        return {
            "holding_horizon": {"min_days": 15, "max_days": 25},
            "trade_plan": {"exit_bias": "flow_decay_or_time_stop"},
            "risk_rules": {
                "stop_loss_mode": "atr_bucketed",
                "atr_window": 14,
                "atr_multiplier": 3.0,
                "stop_floor_pct": 0.06,
                "stop_loss_pct": 0.06,
                "take_profit_pct": 0.14,
                "time_stop_days": 25,
                "max_holding_days": 25,
                "position_cap_pct": 0.18,
                "max_position_pct": 0.18,
                "trailing_activation_r": 1.2,
                "stop_rule_source": "atr_bucketed_low_vol_defensive",
            },
        }
    if profile == "cycle_resource":
        return {
            "holding_horizon": {"min_days": 8, "max_days": 15},
            "trade_plan": {"exit_bias": "leadership_decay_or_time_stop"},
            "risk_rules": {
                "stop_loss_mode": "atr_bucketed",
                "atr_window": 14,
                "atr_multiplier": 2.5,
                "stop_floor_pct": 0.05,
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.16,
                "time_stop_days": 15,
                "max_holding_days": 15,
                "position_cap_pct": 0.14,
                "max_position_pct": 0.14,
                "trailing_activation_r": 1.1,
                "stop_rule_source": "atr_bucketed_cycle_resource",
            },
        }
    return {}


def _apply_snapshot_pool_contract(payload: dict[str, Any]) -> dict[str, Any]:
    task = normalize_research_task_contract(payload.get("research_task") or {})
    pool_profile = str(task.get("pool_profile") or payload.get("pool_profile") or "").strip().lower()
    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    if not pool_profile or not strategy_type:
        return payload
    if pool_profile == "high_vol_growth" and strategy_type == "ma_cross":
        return {}
    profile_contract = _snapshot_pool_risk_contract(pool_profile, strategy_type)
    if not profile_contract:
        return payload
    risk_rules = {
        **dict(payload.get("risk_rules") or {}),
        **dict(profile_contract.get("risk_rules") or {}),
    }
    trade_plan = {
        **dict(payload.get("trade_plan") or {}),
        **dict(profile_contract.get("trade_plan") or {}),
    }
    portfolio_spec = {
        **dict(payload.get("portfolio_spec") or {}),
        "max_position_pct": risk_rules.get("position_cap_pct") or risk_rules.get("max_position_pct"),
    }
    rule_template_contract = {
        **dict(payload.get("rule_template_contract") or {}),
        "default_risk_constraints": {
            **dict(dict(payload.get("rule_template_contract") or {}).get("default_risk_constraints") or {}),
            **dict(profile_contract.get("risk_rules") or {}),
        },
    }
    tags = list(
        dict.fromkeys(
            [
                *list(payload.get("tags") or []),
                f"pool_profile_{pool_profile}",
                "risk_contract_atr_bucketed",
            ]
        )
    )
    return {
        **payload,
        "pool_profile": pool_profile,
        "volatility_bucket": task.get("volatility_bucket") or payload.get("volatility_bucket"),
        "liquidity_bucket": task.get("liquidity_bucket") or payload.get("liquidity_bucket"),
        "family_mix_constraints": dict(task.get("family_mix_constraints") or payload.get("family_mix_constraints") or {}),
        "holding_horizon": {
            **dict(payload.get("holding_horizon") or {}),
            **dict(profile_contract.get("holding_horizon") or {}),
        },
        "trade_plan": trade_plan,
        "risk_rules": risk_rules,
        "portfolio_spec": portfolio_spec,
        "rule_template_contract": rule_template_contract,
        "position_sizing_rationale": "pool_profile_bucketed_risk",
        "market_regime_assumption": {
            "summary": f"{pool_profile} bucket uses ATR bucketed stops and horizon tuned for profile persistence.",
            "preferred_regime": pool_profile,
            "avoid_regime": "uniform_fixed_stop_loss",
        },
        "tags": tags,
    }


def _normalize_snapshot_pipeline_candidate(candidate: dict[str, Any]) -> Optional[dict[str, Any]]:
    """规整 snapshot pipeline 候选。返回 None 表示被清零。

    P0-C 可观测性:被清零时把原因写入 candidate["_generator_normalize_reject_reason"],
    供上游 _pipeline_candidate_to_spec 冒泡到 last_report(对齐 precompile reject 留底模式),
    消除"候选静默清零无痕迹"盲区。
    """
    payload = deepcopy(candidate or {})
    contract = _snapshot_pipeline_contract(payload.get("research_task"))
    payload = _apply_snapshot_pool_contract(payload)
    if not payload:
        candidate["_generator_normalize_reject_reason"] = "snapshot_pool_contract_empty"
        return None
    if not contract.get("conservative_snapshot_task"):
        return payload

    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    allowed_strategy_types = set(contract.get("allowed_strategy_types") or [])
    if allowed_strategy_types and strategy_type and strategy_type not in allowed_strategy_types:
        candidate["_generator_normalize_reject_reason"] = (
            f"strategy_type_not_in_conservative_allowlist:{strategy_type or 'unknown'}"
        )
        return None
    if strategy_type == "momentum":
        candidate["_generator_normalize_reject_reason"] = "momentum_dropped_in_conservative_snapshot_task"
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
                'params': {
                    'rsi_period': 12,
                    'oversold': 18,
                    'overbought': 64,
                    'regime_filter_enabled': True,
                    'allowed_entry_regimes': ['bear_calm', 'bear_volatile'],
                    'noise_filter_enabled': True,
                    'noise_window': 6,
                    'noise_ceiling': 6.0,
                    'regime_break_threshold': 0.015,
                    'mean_reversion_exit_min_hold_bars': 4,
                    'mean_reversion_exit_buffer': -0.002,
                    'max_hold_bars': 6,
                    'adverse_regime_exit_enabled': True,
                    'adverse_exit_regimes': ['range_volatile'],
                    'adverse_noise_ceiling': 6.0,
                },
                'name': 'AI RSI 反转',
                'description': '仅在超跌后出现止跌修复迹象时参与高精度反转。',
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
                'params': {'fear_threshold': 24, 'greed_threshold': 74, 'lookback': 36},
                'name': 'AI 宏观择时',
                'description': '只在恐慌修复与波动稳定共振时参与宏观择时。',
            },
            'volatility_breakout': {
                'params': {'lookback': 20, 'threshold': 0.025},
                'name': 'AI 波动突破',
                'description': '趋势加速且波动扩张时，捕捉放量突破的延续段。',
            },
            'event_structure_breakout': {
                'params': {'breakout_window': 12, 'breakout_buffer_pct': 0.002, 'contraction_window': 5, 'contraction_max_range_ratio': 0.06, 'volume_window': 8, 'breakout_volume_ratio_min': 1.0, 'structure_window': 4, 'structure_close_location_min': 0.62, 'structure_body_return_min': 0.003, 'event_impulse_window': 5, 'event_impulse_threshold': 0.015, 'max_hold_bars': 8, 'breakout_failure_close_buffer': -0.012, 'adverse_volume_ratio_max': 0.85},
                'name': 'AI 事件结构突破',
                'description': '催化后缩量整理并放量突破时，只捕捉结构延续的低频高把握段。',
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

from akshare_mcp._fragment_loader import exec_block as _exec_block


# P3 (R7.1): structured failure-reason taxonomy for the staged LLM
# pipeline. Each LLM stage that fails is classified into one of these
# enum-equivalent strings; the dashboard groups by (stage_id, reason).
class StagedPipelineReason:
    EMPTY_OUTPUT = "empty_output"
    SCHEMA_INVALID = "schema_invalid"
    NON_EXECUTABLE = "non_executable"
    TARGET_CONTEXT_BLOCKED = "target_context_blocked"
    PIPELINE_TIMEOUT = "pipeline_timeout"
    PROVIDER_FORMAT_FAILURE = "provider_output_format_failure"
    UNKNOWN = "unknown"


_STAGED_PIPELINE_REASON_KEYWORDS = (
    # ordered: most specific first
    ("target_context_blocked", StagedPipelineReason.TARGET_CONTEXT_BLOCKED),
    ("provider_output_format", StagedPipelineReason.PROVIDER_FORMAT_FAILURE),
    ("pipeline_timeout", StagedPipelineReason.PIPELINE_TIMEOUT),
    ("invalid_output", StagedPipelineReason.SCHEMA_INVALID),
    ("schema_invalid", StagedPipelineReason.SCHEMA_INVALID),
    ("non_executable", StagedPipelineReason.NON_EXECUTABLE),
    ("returned_empty", StagedPipelineReason.EMPTY_OUTPUT),
    ("no_executable_specs", StagedPipelineReason.EMPTY_OUTPUT),
    ("empty_output", StagedPipelineReason.EMPTY_OUTPUT),
)


def classify_staged_pipeline_reason(token: str) -> str:
    """Map an arbitrary stage_fallback reason string into a stable enum
    string. Unknown tokens fall back to ``StagedPipelineReason.UNKNOWN``."""
    text = str(token or "").strip().lower()
    if not text:
        return StagedPipelineReason.UNKNOWN
    for keyword, value in _STAGED_PIPELINE_REASON_KEYWORDS:
        if keyword in text:
            return value
    return StagedPipelineReason.UNKNOWN


def _build_pipeline_fallback_breakdown(
    stage_fallback_reasons: dict,
    *,
    invalid_output_stage_ids: list,
) -> dict:
    """Produce the ``pipeline_fallback_breakdown`` payload required by R7.2.

    Returns a dict with three sub-maps:
        - ``by_reason``: enum -> count
        - ``by_stage``: stage_id -> count (each stage counted once)
        - ``by_stage_reason``: ``"<stage_id>:<enum>"`` -> count

    The legacy ``pipeline_fallback_counts`` (free-form reason strings)
    stays for read-path compatibility.
    """
    by_reason: dict[str, int] = {}
    by_stage: dict[str, int] = {}
    by_stage_reason: dict[str, int] = {}
    for stage_id, raw_reason in (stage_fallback_reasons or {}).items():
        sid = str(stage_id or "unknown_stage")
        enum_reason = classify_staged_pipeline_reason(raw_reason)
        by_reason[enum_reason] = by_reason.get(enum_reason, 0) + 1
        by_stage[sid] = by_stage.get(sid, 0) + 1
        key = f"{sid}:{enum_reason}"
        by_stage_reason[key] = by_stage_reason.get(key, 0) + 1
    # invalid_output_stage_ids that didn't already show up in
    # stage_fallback_reasons get their own schema_invalid entry so
    # operators see them too.
    for sid in invalid_output_stage_ids or []:
        sid_text = str(sid or "")
        if not sid_text:
            continue
        key = f"{sid_text}:{StagedPipelineReason.SCHEMA_INVALID}"
        if key not in by_stage_reason:
            by_stage_reason[key] = 1
            by_stage[sid_text] = by_stage.get(sid_text, 0) + 1
            by_reason[StagedPipelineReason.SCHEMA_INVALID] = (
                by_reason.get(StagedPipelineReason.SCHEMA_INVALID, 0) + 1
            )
    return {
        "by_reason": by_reason,
        "by_stage": by_stage,
        "by_stage_reason": by_stage_reason,
    }


_exec_block(
    globals(),
    '_strategy_generators_generate_parts',
    'class _LLMProxyStrategyGeneratorGenerateMixin:\n        @staticmethod\n',
    ['context.py', 'specs.py', 'runtime.py'],
    future_annotations=True,
)
