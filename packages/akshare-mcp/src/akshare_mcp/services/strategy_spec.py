"""StrategySpec data class and configuration constants."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)) or default)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


DEFAULT_CODES = ['000300', '600519', '000858', '601318']
RESEARCH_UNIVERSE_PAGE_SIZE = _env_int('STRATEGY_LLM_RESEARCH_PAGE_SIZE', 120, minimum=20, maximum=500)
RESEARCH_UNIVERSE_SCAN_LIMIT = _env_int('STRATEGY_LLM_RESEARCH_SCAN_LIMIT', 300, minimum=20, maximum=2000)
RESEARCH_KLINE_SCAN_LIMIT = _env_int('STRATEGY_LLM_RESEARCH_KLINE_SCAN_LIMIT', 60, minimum=10, maximum=300)
RESEARCH_SYMBOL_DETAIL_LIMIT = _env_int('STRATEGY_LLM_RESEARCH_SYMBOL_DETAIL_LIMIT', 24, minimum=4, maximum=80)
RESEARCH_CANDIDATE_POOL_LIMIT = _env_int('STRATEGY_LLM_RESEARCH_CANDIDATE_POOL_LIMIT', 12, minimum=3, maximum=40)
RESEARCH_FINANCIAL_DETAIL_LIMIT = _env_int('STRATEGY_LLM_RESEARCH_FINANCIAL_DETAIL_LIMIT', 8, minimum=2, maximum=20)

_FACTOR_VALIDATION_TYPES = {"value_factor", "quality_factor", "growth_factor", "multi_factor"}


def _normalize_code_list(*values: Any, limit: int = 12) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()

    def visit(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for key in ("code", "symbol", "stock_code"):
                if value.get(key) is not None:
                    visit(value.get(key))
            for key in ("codes", "symbols", "stock_codes", "target_symbols"):
                if value.get(key) is not None:
                    visit(value.get(key))
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)
            return
        raw = str(value or "").strip()
        if not raw:
            return
        if any(sep in raw for sep in [",", ";", "|", "\n", "\t", " "]):
            normalized = (
                raw.replace(";", ",")
                .replace("|", ",")
                .replace("\n", ",")
                .replace("\t", ",")
                .replace(" ", ",")
            )
            for part in normalized.split(","):
                visit(part)
            return
        code = raw.split(".")[0].strip()
        if not code or code in seen:
            return
        seen.add(code)
        codes.append(code)

    for value in values:
        visit(value)
    return codes[: max(1, min(int(limit or 12), 40))]


def _safe_normalize_research_task(task: Any) -> dict[str, Any]:
    payload = dict(task or {})
    if not payload:
        return {}
    try:
        from strategy_factory.domain.targets import _normalize_research_task_contract

        return dict(_normalize_research_task_contract(payload))
    except Exception:
        task_source = str(payload.get("task_source") or "snapshot").strip().lower() or "snapshot"
        target_symbols = _normalize_code_list(
            [
                payload.get("target_symbols"),
                payload.get("stock_pool"),
                (payload.get("event_context") or {}).get("target_symbols"),
            ],
            limit=12,
        )
        stock_pool = dict(payload.get("stock_pool") or {})
        if target_symbols and not stock_pool:
            stock_pool = {"selection_mode": "explicit", "symbols": list(target_symbols)}
        holding_window = dict(payload.get("holding_window") or {})
        if not holding_window:
            holding_window = {"max_days": 10 if task_source == "event_driven" else 20}
        return {
            **payload,
            "task_source": task_source,
            "target_symbols": list(target_symbols),
            "stock_pool": stock_pool,
            "target_symbol_policy": str(
                payload.get("target_symbol_policy")
                or ("strict_intersection" if task_source == "event_driven" else "prefer_intersection")
            ).strip().lower(),
            "universe_expansion_policy": str(
                payload.get("universe_expansion_policy")
                or ("allow_same_theme_only" if task_source == "event_driven" else "allow_market_fallback")
            ).strip().lower(),
            "validation_focus": str(
                payload.get("validation_focus")
                or ("event_target_only" if task_source == "event_driven" else "target_plus_representative")
            ).strip().lower(),
            "holding_window": holding_window,
        }


def _task_source(research_task: dict[str, Any], event_context: dict[str, Any]) -> str:
    source = str(research_task.get("task_source") or "").strip().lower()
    if source:
        return source
    return "event_driven" if event_context else "snapshot"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _normalize_turnover_band(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token in {"very_high", "high", "medium", "low"}:
        return token
    return ""


def _derive_half_life_semantics(alpha_half_life: Any) -> dict[str, Any]:
    half_life = _safe_float(alpha_half_life, 0.0)
    if half_life <= 0:
        return {}
    if half_life <= 3:
        return {
            "min_days": 1,
            "max_days": max(2, _safe_int(round(half_life * 1.5), 2)),
            "rebalance_interval_days": 1,
            "cooldown_window_days": 1,
            "expected_turnover_band": "very_high",
        }
    if half_life <= 8:
        min_days = max(2, _safe_int(round(half_life * 0.75), 2))
        max_days = max(min_days + 1, _safe_int(round(half_life * 1.5), min_days + 1))
        return {
            "min_days": min_days,
            "max_days": max_days,
            "rebalance_interval_days": max(2, _safe_int(round(half_life / 2.0), 2)),
            "cooldown_window_days": max(1, _safe_int(round(half_life / 3.0), 1)),
            "expected_turnover_band": "high",
        }
    if half_life <= 16:
        min_days = max(3, _safe_int(round(half_life * 0.8), 3))
        max_days = max(min_days + 1, _safe_int(round(half_life * 1.8), min_days + 1))
        return {
            "min_days": min_days,
            "max_days": max_days,
            "rebalance_interval_days": max(3, _safe_int(round(half_life * 0.75), 3)),
            "cooldown_window_days": max(2, _safe_int(round(half_life / 2.0), 2)),
            "expected_turnover_band": "medium",
        }
    min_days = max(5, _safe_int(round(half_life), 5))
    max_days = max(min_days + 1, _safe_int(round(half_life * 2.2), min_days + 1))
    return {
        "min_days": min_days,
        "max_days": max_days,
        "rebalance_interval_days": max(5, _safe_int(round(half_life), 5)),
        "cooldown_window_days": max(3, _safe_int(round(half_life * 0.75), 3)),
        "expected_turnover_band": "low",
    }


def _merge_holding_semantics(
    holding_horizon: dict[str, Any],
    *,
    holding_rationale: Any = None,
    alpha_half_life: Any = None,
) -> dict[str, Any]:
    result = dict(holding_horizon or {})
    derived = _derive_half_life_semantics(alpha_half_life)
    if result.get("rationale") in (None, "", [], {}) and holding_rationale not in (None, "", [], {}):
        result["rationale"] = holding_rationale
    if result.get("alpha_half_life") in (None, "", [], {}) and alpha_half_life not in (None, "", [], {}):
        result["alpha_half_life"] = _safe_float(alpha_half_life)
    for key in ("min_days", "max_days", "cooldown_window_days", "expected_turnover_band"):
        if result.get(key) in (None, "", [], {}) and derived.get(key) not in (None, "", [], {}):
            result[key] = derived.get(key)
    return result


def _merge_rebalance_semantics(
    rebalance_rule: dict[str, Any],
    *,
    task_source: str,
    holding_horizon: dict[str, Any],
    alpha_half_life: Any = None,
) -> dict[str, Any]:
    result = dict(rebalance_rule or {})
    derived = _derive_half_life_semantics(alpha_half_life)
    max_days = _safe_int(holding_horizon.get("max_days"), 0)
    rebalance_interval_days = max(
        1,
        _safe_int(
            result.get("rebalance_interval_days") or derived.get("rebalance_interval_days"),
            max(1, min(max_days or 10, max(1, (max_days or 10) // 2))),
        ),
    )
    if result.get("mode") in (None, "", [], {}):
        result["mode"] = (
            "event_driven_hold"
            if task_source == "event_driven"
            else ("periodic_rebalance" if rebalance_interval_days >= 3 else "signal_rebalance")
        )
    if task_source != "event_driven":
        result.setdefault("frequency_days", max(1, min(max_days or rebalance_interval_days, rebalance_interval_days)))
    result.setdefault("rebalance_interval_days", rebalance_interval_days)
    if result.get("cooldown_window_days") in (None, "", [], {}):
        result["cooldown_window_days"] = _safe_int(
            holding_horizon.get("cooldown_window_days") or derived.get("cooldown_window_days"),
            0,
        )
    if result.get("expected_turnover_band") in (None, "", [], {}):
        result["expected_turnover_band"] = (
            _normalize_turnover_band(holding_horizon.get("expected_turnover_band"))
            or derived.get("expected_turnover_band")
        )
    return result


def _resolve_capacity_bucket(
    capacity_assumption: dict[str, Any],
    *,
    target_symbols: list[str],
    position_model: str,
) -> str:
    explicit = str(
        capacity_assumption.get("capacity_bucket")
        or capacity_assumption.get("bucket")
        or ""
    ).strip().lower()
    if explicit:
        return explicit
    max_position_pct = _safe_float(capacity_assumption.get("max_position_pct"), 0.0)
    participation = _safe_float(capacity_assumption.get("capacity_participation_rate"), 0.0)
    symbol_count = max(_safe_int(capacity_assumption.get("symbol_count"), 0), len(target_symbols))
    normalized_model = str(position_model or "").strip().lower()
    if symbol_count <= 1 or "single" in normalized_model or max_position_pct >= 0.3 or participation >= 0.15:
        return "small"
    if symbol_count >= 8 and max_position_pct <= 0.12 and participation <= 0.08:
        return "large"
    return "mid"


def _resolve_turnover_cost_class(
    *,
    execution_assumptions: dict[str, Any],
    expected_turnover_band: str,
    capacity_bucket: str,
) -> str:
    slippage_bps = _safe_float(execution_assumptions.get("slippage_bps"), 0.0)
    market_impact_bps = _safe_float(execution_assumptions.get("market_impact_bps"), 0.0)
    if expected_turnover_band == "very_high" or slippage_bps >= 10 or market_impact_bps >= 4:
        return "high_touch"
    if expected_turnover_band == "high" or slippage_bps >= 5 or capacity_bucket == "small":
        return "medium_touch"
    return "low_touch"


def _resolve_position_sizing_rationale(
    *,
    position_model: str,
    target_symbols: list[str],
    capacity_bucket: str,
    expected_turnover_band: str,
) -> str:
    normalized_model = str(position_model or "").strip().lower()
    if "volatility" in normalized_model:
        return "volatility_budgeted_across_target_basket"
    if "single" in normalized_model or len(target_symbols) <= 1:
        return (
            "single_name_conviction_capped_by_capacity"
            if capacity_bucket in {"small", "mid"}
            else "single_name_conviction_with_liquidity_buffer"
        )
    if expected_turnover_band in {"high", "very_high"}:
        return "equal_weight_diversified_basket_to_limit_turnover_drag"
    return "equal_weight_diversified_basket"


def _default_holding_horizon(
    strategy_type: str,
    research_task: dict[str, Any],
    task_source: str,
    *,
    alpha_half_life: Any = None,
) -> dict[str, Any]:
    holding_window = dict(research_task.get("holding_window") or {})
    if holding_window:
        return _merge_holding_semantics(
            holding_window,
            alpha_half_life=alpha_half_life,
        )
    derived = _derive_half_life_semantics(alpha_half_life)
    if derived:
        return _merge_holding_semantics(derived, alpha_half_life=alpha_half_life)
    if task_source == "event_driven":
        return {"max_days": 10}
    if strategy_type == "quality_factor":
        return {"min_days": 30, "max_days": 84}
    if strategy_type in _FACTOR_VALIDATION_TYPES or strategy_type in {"macro_timing", "sector_rotation"}:
        return {"min_days": 5, "max_days": 24}
    if task_source in {"snapshot", "bulk_stock_matrix"}:
        if strategy_type == "momentum":
            return {"min_days": 14, "max_days": 42}
        if strategy_type in {"ma_cross", "volatility_breakout", "north_capital_track", "margin_divergence"}:
            return {"min_days": 14, "max_days": 48}
        if strategy_type in {"gap_fill", "mean_reversion_short", "rsi"}:
            return {"min_days": 3, "max_days": 12}
        return {"min_days": 4, "max_days": 15}
    return {"max_days": 10}


def _default_trade_plan(strategy_type: str, task_source: str) -> dict[str, Any]:
    if task_source == "event_driven":
        return {
            "entry_bias": "event_follow_through",
            "exit_bias": "time_stop_or_signal_reversal",
        }
    if strategy_type in _FACTOR_VALIDATION_TYPES:
        return {
            "entry_bias": "cross_sectional_rank",
            "exit_bias": "rank_decay_or_periodic_rebalance",
        }
    if strategy_type == "momentum":
        return {
            "entry_bias": "trend_persistence_confirmation",
            "exit_bias": "false_breakout_or_momentum_decay",
        }
    if strategy_type == "quality_factor":
        return {
            "entry_bias": "quality_stability_with_trend_confirmation",
            "exit_bias": "quality_drift_or_rank_decay",
        }
    if strategy_type == "ma_cross":
        return {
            "entry_bias": "adaptive_cross_with_volume_confirmation",
            "exit_bias": "range_reentry_or_cross_failure",
        }
    if strategy_type == "macro_timing":
        return {
            "entry_bias": "regime_confirmed",
            "exit_bias": "regime_flip_or_time_stop",
        }
    return {
        "entry_bias": "signal_confirmed",
        "exit_bias": "signal_or_time_stop",
    }


def _default_market_regime_assumption(strategy_type: str, task_source: str) -> dict[str, Any]:
    if task_source == "event_driven":
        return {
            "summary": "事件催化后的短窗口延续阶段更有效。",
            "preferred_regime": "event_follow_through",
            "avoid_regime": "post_event_mean_reversion",
        }
    if strategy_type == "momentum":
        return {
            "summary": "趋势扩张且龙头相对强度保持的阶段更有效，需要避免无量假突破与快速反抽。",
            "preferred_regime": "trend_expansion_with_persistence",
            "avoid_regime": "false_breakout_range_reversion",
        }
    if strategy_type == "ma_cross":
        return {
            "summary": "需要均线张口扩大并伴随量能确认，横盘噪声区间的频繁穿越应过滤。",
            "preferred_regime": "trend_expansion_with_volume_confirmation",
            "avoid_regime": "range_bound_chop",
        }
    if strategy_type in {"volatility_breakout"}:
        return {
            "summary": "趋势扩张或强势股持续领跑阶段更有效。",
            "preferred_regime": "trend_expansion",
            "avoid_regime": "range_bound_chop",
        }
    if strategy_type == "quality_factor":
        return {
            "summary": "基本面稳定扩散并与中期价格趋势共振时更有效，风格急切换和质量漂移阶段要回避。",
            "preferred_regime": "quality_stability_with_trend_resonance",
            "avoid_regime": "quality_drift_high_noise_rotation",
        }
    if strategy_type in {"value_factor", "growth_factor", "multi_factor"}:
        return {
            "summary": "慢变量扩散、基本面驱动占优的稳定阶段更有效。",
            "preferred_regime": "slow_factor_diffusion",
            "avoid_regime": "high_noise_rotation",
        }
    return {
        "summary": "流动性正常、成本可控的中性市场环境更有效。",
        "preferred_regime": "neutral_liquid_cn_equity",
        "avoid_regime": "illiquid_stressed_market",
    }


def _default_risk_rules(task_source: str, holding_horizon: dict[str, Any]) -> dict[str, Any]:
    max_holding_days = int(holding_horizon.get("max_days") or 0)
    return {
        "stop_loss_pct": 0.08 if task_source == "event_driven" else 0.1,
        "take_profit_pct": 0.18 if task_source == "event_driven" else 0.2,
        "max_holding_days": max_holding_days or (10 if task_source == "event_driven" else 20),
    }


def _default_position_sizing(target_symbols: list[str]) -> dict[str, Any]:
    multiple_names = len(target_symbols) > 1
    return {
        "mode": "equal_weight" if multiple_names else "single_name",
        "position_assumption": "equal_weight_proxy" if multiple_names else "single_name_full_notional",
    }


def _default_rebalance_rule(
    strategy_type: str,
    task_source: str,
    *,
    holding_horizon: Optional[dict[str, Any]] = None,
    alpha_half_life: Any = None,
) -> dict[str, Any]:
    derived = _derive_half_life_semantics(alpha_half_life)
    if derived:
        return _merge_rebalance_semantics(
            {},
            task_source=task_source,
            holding_horizon=_merge_holding_semantics(dict(holding_horizon or {}), alpha_half_life=alpha_half_life),
            alpha_half_life=alpha_half_life,
        )
    if task_source == "event_driven":
        return {"mode": "event_driven_hold"}
    if strategy_type == "quality_factor":
        return {"mode": "periodic_rebalance", "frequency_days": 28}
    if strategy_type in _FACTOR_VALIDATION_TYPES or strategy_type == "sector_rotation":
        return {"mode": "periodic_rebalance", "frequency_days": 10}
    if strategy_type == "macro_timing":
        return {"mode": "regime_rebalance", "frequency_days": 10}
    if task_source in {"snapshot", "bulk_stock_matrix"}:
        if strategy_type == "momentum":
            return {"mode": "periodic_rebalance", "frequency_days": 14}
        if strategy_type in {"ma_cross", "volatility_breakout", "north_capital_track", "margin_divergence"}:
            return {"mode": "periodic_rebalance", "frequency_days": 12}
        if strategy_type in {"gap_fill", "mean_reversion_short", "rsi"}:
            return {"mode": "periodic_rebalance", "frequency_days": 4}
    return {"mode": "signal_rebalance"}


def _default_family_specialization(
    strategy_type: str,
    task_source: str,
    *,
    holding_horizon: Optional[dict[str, Any]] = None,
    rebalance_rule: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    family = str(strategy_type or "").strip().lower()
    holding = dict(holding_horizon or {})
    rebalance = dict(rebalance_rule or {})
    max_days = max(1, _safe_int(holding.get("max_days"), 0) or 1)
    frequency_days = max(1, _safe_int(rebalance.get("frequency_days"), 0) or max(1, max_days // 2))
    if family == "momentum":
        return {
            "trend_persistence_regime": "trend_expansion_with_relative_strength_persistence",
            "false_breakout_filter": "prefer_volume_confirmed_breakout_and_positive_trend_slope",
            "peer_selection_mode": "target_plus_dynamic_family_peer",
            "holding_bias": f"hold_for_{max_days}_days_or_until_momentum_decay",
            "rebalance_bias": f"periodic_rebalance_every_{frequency_days}_days",
        }
    if family == "quality_factor":
        return {
            "rebalance_bias": "low_frequency_quality_refresh",
            "quality_trend_resonance": "require_fundamental_stability_and_price_trend_alignment",
            "quality_drift_detection": "monitor_rank_margin_cashflow_stability_deterioration",
            "peer_selection_mode": "target_plus_dynamic_family_peer",
            "compounding_window": "prefer_slow_compounding_validation_window",
            "holding_bias": f"slow_factor_diffusion_hold_{max_days}_days",
            "task_source": task_source or None,
        }
    if family == "ma_cross":
        return {
            "adaptive_span_logic": "fast_slow_span_scaled_by_regime_and_noise_level",
            "range_filter": "avoid_crosses_when_long_ma_is_flat_and_price_is_range_bound",
            "volume_confirmation": "prefer_crosses_with_volume_ratio_confirmation",
            "holding_bias": f"trend_follow_hold_{max_days}_days",
            "rebalance_bias": f"periodic_rebalance_every_{frequency_days}_days",
        }
    return {}


def _default_portfolio_spec(target_symbols: list[str]) -> dict[str, Any]:
    multiple_names = len(target_symbols) > 1
    return {
        "position_assumption": "equal_weight_proxy" if multiple_names else "single_name_full_notional",
        "target_weight_scheme": "equal_weight" if multiple_names else "single_name",
    }


def _default_execution_assumptions(task_source: str) -> dict[str, Any]:
    return {
        "commission_rate": 0.00025,
        "slippage_bps": 8 if task_source == "event_driven" else 5,
        "tradability_filter": True,
        "slippage_model": "fixed",
    }


def _default_validation_profile(
    strategy_type: str,
    research_task: dict[str, Any],
    task_source: str,
) -> dict[str, Any]:
    default_focus = (
        "event_target_only"
        if task_source == "event_driven"
        else "candidate_target_only" if strategy_type == "quality_factor"
        else "target_plus_representative"
    )
    validation_focus = str(
        research_task.get("validation_focus") or default_focus
    ).strip().lower()
    if strategy_type == "quality_factor" and validation_focus in {
        "candidate_target_only",
        "target_only",
        "target_plus_family_peer",
    }:
        profile = "trade_rule_validation"
    elif strategy_type in _FACTOR_VALIDATION_TYPES:
        profile = "factor_rank_validation"
    elif strategy_type == "macro_timing":
        profile = "macro_regime_validation"
    elif task_source == "event_driven" or validation_focus == "event_target_only":
        profile = "event_trade_validation"
    else:
        profile = "trade_rule_validation"
    return {
        "profile": profile,
        "validation_focus": validation_focus,
        "primary_validation_layer": "target" if validation_focus == "event_target_only" else "combined",
    }


def _default_targeting_policy(research_task: dict[str, Any]) -> dict[str, Any]:
    if not research_task:
        return {}
    return {
        "target_symbol_policy": research_task.get("target_symbol_policy"),
        "universe_expansion_policy": research_task.get("universe_expansion_policy"),
        "validation_focus": research_task.get("validation_focus"),
    }


def _default_constraint_check(
    *,
    target_symbols: list[str],
    research_task: dict[str, Any],
    targeting_policy: dict[str, Any],
) -> dict[str, Any]:
    research_symbols = _normalize_code_list(
        [
            research_task.get("target_symbols"),
            research_task.get("stock_pool"),
        ],
        limit=12,
    )
    overlap_count = len(set(target_symbols).intersection(research_symbols))
    coverage_ratio = round(overlap_count / max(1, len(target_symbols)), 4) if target_symbols else 0.0
    intersection_ratio = round(overlap_count / max(1, len(research_symbols)), 4) if research_symbols else None
    violation = None
    if (
        str(targeting_policy.get("target_symbol_policy") or "").strip().lower() == "strict_intersection"
        and research_symbols
        and target_symbols
        and overlap_count == 0
    ):
        violation = "strict_intersection_empty"
    return {
        "target_symbols_before_normalize": list(target_symbols),
        "target_symbols_after_normalize": list(target_symbols),
        "research_target_symbols": list(research_symbols),
        "target_symbol_policy": targeting_policy.get("target_symbol_policy"),
        "universe_expansion_policy": targeting_policy.get("universe_expansion_policy"),
        "expansion_applied": False,
        "expansion_reason": None,
        "expansion_source": None,
        "constraint_violation": violation,
        "coverage_ratio": coverage_ratio,
        "intersection_ratio": intersection_ratio,
    }


@dataclass
class StrategySpec:
    strategy_type: str
    params: dict[str, Any]
    name: str = ''
    description: str = ''
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_candidate(self, source: str, experiment_id: str) -> dict:
        metadata = dict(self.metadata or {})
        source_candidate = dict(metadata.get("source_candidate") or {})
        source_candidate_params = dict(source_candidate.get("params") or {})

        def _list_value(*values: Any) -> list[Any]:
            for value in values:
                if isinstance(value, (list, tuple, set)) and value:
                    return list(value)
            return []

        def _dict_value(*values: Any) -> dict[str, Any]:
            for value in values:
                if isinstance(value, dict) and value:
                    return dict(value)
            return {}

        def _scalar_value(*values: Any) -> Any:
            for value in values:
                if value not in (None, "", [], {}):
                    return value
            return None

        target_symbols = _normalize_code_list(
            metadata.get("target_symbols"),
            source_candidate.get("target_symbols"),
            metadata.get("stock_pool"),
            source_candidate.get("stock_pool"),
            dict(self.params or {}).get("target_symbols"),
            source_candidate_params.get("target_symbols"),
            dict(self.params or {}).get("stock_pool"),
            source_candidate_params.get("stock_pool"),
        )
        stock_pool = _dict_value(
            metadata.get("stock_pool"),
            source_candidate.get("stock_pool"),
            dict(self.params or {}).get("stock_pool"),
            source_candidate_params.get("stock_pool"),
            {"selection_mode": "explicit", "symbols": list(target_symbols)} if target_symbols else {},
        )
        research_task = _safe_normalize_research_task(_dict_value(
            metadata.get("research_task"),
            source_candidate.get("research_task"),
            dict(self.params or {}).get("research_task"),
            source_candidate_params.get("research_task"),
        ))
        event_context = _dict_value(
            metadata.get("event_context"),
            source_candidate.get("event_context"),
            dict(self.params or {}).get("event_context"),
            source_candidate_params.get("event_context"),
        )
        selection_logic = _list_value(
            metadata.get("selection_logic"),
            source_candidate.get("selection_logic"),
        )
        research_scope = _dict_value(
            metadata.get("research_scope"),
            source_candidate.get("research_scope"),
        )
        hypothesis_artifact = _dict_value(
            metadata.get("hypothesis_artifact"),
            source_candidate.get("hypothesis_artifact"),
        )
        task_source = _task_source(research_task, event_context)
        holding_rationale = _scalar_value(
            metadata.get("holding_rationale"),
            source_candidate.get("holding_rationale"),
            hypothesis_artifact.get("holding_rationale"),
        )
        alpha_half_life = _scalar_value(
            metadata.get("alpha_half_life"),
            source_candidate.get("alpha_half_life"),
            hypothesis_artifact.get("alpha_half_life"),
        )
        market_regime_assumption = _scalar_value(
            metadata.get("market_regime_assumption"),
            source_candidate.get("market_regime_assumption"),
            hypothesis_artifact.get("market_regime_assumption"),
        )
        holding_horizon = _dict_value(
            metadata.get("holding_horizon"),
            source_candidate.get("holding_horizon"),
            dict(self.params or {}).get("holding_horizon"),
            source_candidate_params.get("holding_horizon"),
        )
        if not holding_horizon:
            holding_horizon = _default_holding_horizon(
                self.strategy_type,
                research_task,
                task_source,
                alpha_half_life=alpha_half_life,
            )
        if alpha_half_life in (None, "", [], {}):
            alpha_half_life = holding_horizon.get("alpha_half_life") or holding_horizon.get("max_days")
        if market_regime_assumption in (None, "", [], {}):
            market_regime_assumption = _default_market_regime_assumption(
                self.strategy_type,
                task_source,
            )
        holding_horizon = _merge_holding_semantics(
            holding_horizon,
            holding_rationale=holding_rationale,
            alpha_half_life=alpha_half_life,
        )
        trade_plan = _dict_value(
            metadata.get("trade_plan"),
            source_candidate.get("trade_plan"),
            dict(self.params or {}).get("trade_plan"),
            source_candidate_params.get("trade_plan"),
        )
        if not trade_plan:
            trade_plan = _default_trade_plan(self.strategy_type, task_source)
        risk_rules = _dict_value(
            metadata.get("risk_rules"),
            source_candidate.get("risk_rules"),
            dict(self.params or {}).get("risk_rules"),
            source_candidate_params.get("risk_rules"),
        )
        if not risk_rules:
            risk_rules = _default_risk_rules(task_source, holding_horizon)
        position_sizing = _dict_value(
            metadata.get("position_sizing"),
            source_candidate.get("position_sizing"),
            dict(self.params or {}).get("position_sizing"),
            source_candidate_params.get("position_sizing"),
        )
        if not position_sizing:
            position_sizing = _default_position_sizing(target_symbols)
        rebalance_rule = _dict_value(
            metadata.get("rebalance_rule"),
            source_candidate.get("rebalance_rule"),
            dict(self.params or {}).get("rebalance_rule"),
            source_candidate_params.get("rebalance_rule"),
        )
        if not rebalance_rule:
            rebalance_rule = _default_rebalance_rule(
                self.strategy_type,
                task_source,
                holding_horizon=holding_horizon,
                alpha_half_life=alpha_half_life,
            )
        rebalance_rule = _merge_rebalance_semantics(
            rebalance_rule,
            task_source=task_source,
            holding_horizon=holding_horizon,
            alpha_half_life=alpha_half_life,
        )
        portfolio_spec = _dict_value(
            metadata.get("portfolio_spec"),
            source_candidate.get("portfolio_spec"),
            dict(self.params or {}).get("portfolio_spec"),
            source_candidate_params.get("portfolio_spec"),
        )
        if not portfolio_spec:
            portfolio_spec = _default_portfolio_spec(target_symbols)
        execution_assumptions = _dict_value(
            metadata.get("execution_assumptions"),
            source_candidate.get("execution_assumptions"),
            dict(self.params or {}).get("execution_assumptions"),
            source_candidate_params.get("execution_assumptions"),
        )
        if not execution_assumptions:
            execution_assumptions = _default_execution_assumptions(task_source)
        validation_profile = _dict_value(
            metadata.get("validation_profile"),
            source_candidate.get("validation_profile"),
            dict(self.params or {}).get("validation_profile"),
            source_candidate_params.get("validation_profile"),
        )
        if not validation_profile:
            validation_profile = _default_validation_profile(self.strategy_type, research_task, task_source)
        targeting_policy = _dict_value(
            metadata.get("targeting_policy"),
            source_candidate.get("targeting_policy"),
            dict(self.params or {}).get("targeting_policy"),
            source_candidate_params.get("targeting_policy"),
        )
        if not targeting_policy:
            targeting_policy = _default_targeting_policy(research_task)
        constraint_check = _dict_value(
            metadata.get("constraint_check"),
            source_candidate.get("constraint_check"),
            dict(self.params or {}).get("constraint_check"),
            source_candidate_params.get("constraint_check"),
        )
        if not constraint_check:
            constraint_check = _default_constraint_check(
                target_symbols=list(target_symbols),
                research_task=research_task,
                targeting_policy=targeting_policy,
            )
        position_model = _scalar_value(
            metadata.get("position_model"),
            source_candidate.get("position_model"),
            hypothesis_artifact.get("position_model"),
            position_sizing.get("mode"),
            portfolio_spec.get("position_assumption"),
        )
        capacity_assumption = _dict_value(
            metadata.get("capacity_assumption"),
            source_candidate.get("capacity_assumption"),
            hypothesis_artifact.get("capacity_assumption"),
        )
        cost_sensitivity_grid = _dict_value(
            metadata.get("cost_sensitivity_grid"),
            source_candidate.get("cost_sensitivity_grid"),
            hypothesis_artifact.get("cost_sensitivity_grid"),
        )
        family_specialization = _default_family_specialization(
            self.strategy_type,
            task_source,
            holding_horizon=holding_horizon,
            rebalance_rule=rebalance_rule,
        )
        family_specialization.update(
            _dict_value(
                metadata.get("family_specialization"),
                source_candidate.get("family_specialization"),
                dict(self.params or {}).get("family_specialization"),
                source_candidate_params.get("family_specialization"),
                hypothesis_artifact.get("family_specific_hypothesis"),
            )
        )
        expected_turnover_band = (
            _normalize_turnover_band(
                holding_horizon.get("expected_turnover_band")
                or rebalance_rule.get("expected_turnover_band")
            )
            or _derive_half_life_semantics(alpha_half_life).get("expected_turnover_band")
        )
        capacity_bucket = _resolve_capacity_bucket(
            dict(capacity_assumption),
            target_symbols=list(target_symbols),
            position_model=str(position_model or ""),
        )
        if not capacity_assumption:
            capacity_assumption = {
                "max_position_pct": portfolio_spec.get("max_position_pct"),
                "symbol_count": len(target_symbols),
                "capacity_bucket": capacity_bucket,
            }
        if not cost_sensitivity_grid:
            cost_sensitivity_grid = {
                "base_case": {
                    "commission_rate": execution_assumptions.get("commission_rate"),
                    "slippage_bps": execution_assumptions.get("slippage_bps"),
                    "tradability_filter": execution_assumptions.get("tradability_filter"),
                    "slippage_model": execution_assumptions.get("slippage_model"),
                    "market_impact_bps": execution_assumptions.get("market_impact_bps"),
                },
                "source": "strategy_spec_execution_defaults",
            }
        position_sizing_rationale = _resolve_position_sizing_rationale(
            position_model=str(position_model or ""),
            target_symbols=list(target_symbols),
            capacity_bucket=capacity_bucket,
            expected_turnover_band=expected_turnover_band or "medium",
        )
        position_sizing.setdefault("capacity_bucket", capacity_bucket or None)
        position_sizing.setdefault("expected_turnover_band", expected_turnover_band or None)
        position_sizing.setdefault("position_sizing_rationale", position_sizing_rationale)
        portfolio_spec.setdefault("capacity_bucket", capacity_bucket or None)
        portfolio_spec.setdefault("expected_turnover_band", expected_turnover_band or None)
        portfolio_spec.setdefault("position_sizing_rationale", position_sizing_rationale)
        execution_assumptions.setdefault("capacity_bucket", capacity_bucket or None)
        execution_assumptions.setdefault(
            "turnover_cost_class",
            _resolve_turnover_cost_class(
                execution_assumptions=execution_assumptions,
                expected_turnover_band=expected_turnover_band or "medium",
                capacity_bucket=capacity_bucket,
            ),
        )
        execution_assumptions.setdefault("expected_turnover_band", expected_turnover_band or None)
        trade_plan.setdefault("cooldown_window_days", holding_horizon.get("cooldown_window_days"))
        trade_plan.setdefault("expected_turnover_band", expected_turnover_band or None)
        risk_rules.setdefault("cooldown_window_days", holding_horizon.get("cooldown_window_days"))
        candidate_params = {
            **dict(self.params or {}),
            "target_symbols": list(target_symbols),
            "stock_pool": dict(stock_pool),
            "research_task": dict(research_task),
            "event_context": dict(event_context),
            "holding_horizon": dict(holding_horizon),
            "trade_plan": dict(trade_plan),
            "risk_rules": dict(risk_rules),
            "position_sizing": dict(position_sizing),
            "rebalance_rule": dict(rebalance_rule),
            "portfolio_spec": dict(portfolio_spec),
            "execution_assumptions": dict(execution_assumptions),
            "validation_profile": dict(validation_profile),
            "targeting_policy": dict(targeting_policy),
            "constraint_check": dict(constraint_check),
            "hypothesis_artifact": dict(hypothesis_artifact),
            "holding_rationale": holding_rationale,
            "alpha_half_life": alpha_half_life,
            "cost_sensitivity_grid": dict(cost_sensitivity_grid),
            "position_model": position_model,
            "capacity_assumption": dict(capacity_assumption),
            "market_regime_assumption": market_regime_assumption,
            "position_sizing_rationale": position_sizing_rationale,
            "capacity_bucket": capacity_bucket,
            "turnover_cost_class": execution_assumptions.get("turnover_cost_class"),
            "expected_turnover_band": expected_turnover_band,
            "family_specialization": dict(family_specialization),
            "economic_semantics_score": _scalar_value(
                metadata.get("economic_semantics_score"),
                source_candidate.get("economic_semantics_score"),
                hypothesis_artifact.get("economic_semantics_score"),
            ),
            "economic_semantics_missing_fields": _list_value(
                metadata.get("economic_semantics_missing_fields"),
                source_candidate.get("economic_semantics_missing_fields"),
                hypothesis_artifact.get("economic_semantics_missing_fields"),
            ),
            "validation_focus": _scalar_value(
                metadata.get("validation_focus"),
                source_candidate.get("validation_focus"),
                hypothesis_artifact.get("validation_focus"),
                validation_profile.get("validation_focus"),
            ),
        }
        return {
            'name': self.name or str(source_candidate.get('name') or ''),
            'description': self.description or str(source_candidate.get('description') or ''),
            'strategy_type': self.strategy_type,
            'params': candidate_params,
            'spawn_reason': self.description or self.name or f'{source}:{self.strategy_type}',
            'hypothesis': _scalar_value(metadata.get('hypothesis'), source_candidate.get('hypothesis')),
            'holding_horizon': dict(holding_horizon),
            'trade_plan': dict(trade_plan),
            'risk_rules': dict(risk_rules),
            'position_sizing': dict(position_sizing),
            'execution_notes': _scalar_value(metadata.get('execution_notes'), source_candidate.get('execution_notes')),
            'rebalance_rule': dict(rebalance_rule),
            'portfolio_spec': dict(portfolio_spec),
            'execution_assumptions': dict(execution_assumptions),
            'validation_profile': dict(validation_profile),
            'targeting_policy': dict(targeting_policy),
            'constraint_check': dict(constraint_check),
            'hypothesis_artifact': dict(hypothesis_artifact),
            'hypothesis_artifact_id': _scalar_value(
                metadata.get('hypothesis_artifact_id'),
                source_candidate.get('hypothesis_artifact_id'),
                hypothesis_artifact.get('artifact_id'),
            ),
            'hypothesis_lowering_audit': _dict_value(
                metadata.get('hypothesis_lowering_audit'),
                source_candidate.get('hypothesis_lowering_audit'),
            ),
            'holding_rationale': holding_rationale,
            'alpha_half_life': alpha_half_life,
            'cost_sensitivity_grid': _dict_value(
                cost_sensitivity_grid,
            ),
            'position_model': position_model,
            'capacity_assumption': dict(capacity_assumption),
            'market_regime_assumption': market_regime_assumption,
            'position_sizing_rationale': position_sizing_rationale,
            'capacity_bucket': capacity_bucket,
            'turnover_cost_class': execution_assumptions.get('turnover_cost_class'),
            'expected_turnover_band': expected_turnover_band,
            'family_specialization': dict(family_specialization),
            'economic_semantics_score': _scalar_value(
                metadata.get('economic_semantics_score'),
                source_candidate.get('economic_semantics_score'),
                hypothesis_artifact.get('economic_semantics_score'),
            ),
            'economic_semantics_missing_fields': _list_value(
                metadata.get('economic_semantics_missing_fields'),
                source_candidate.get('economic_semantics_missing_fields'),
                hypothesis_artifact.get('economic_semantics_missing_fields'),
            ),
            'validation_focus': _scalar_value(
                metadata.get('validation_focus'),
                source_candidate.get('validation_focus'),
                hypothesis_artifact.get('validation_focus'),
                validation_profile.get('validation_focus'),
            ),
            'generation_reason': _dict_value(metadata.get('generation_reason'), source_candidate.get('generation_reason')),
            'committee_review': _dict_value(metadata.get('committee_review'), source_candidate.get('committee_review')),
            'generator_type': _scalar_value(metadata.get('generator_type'), source_candidate.get('generator_type'), source) or source,
            'optimizer_type': _scalar_value(metadata.get('optimizer_type'), source_candidate.get('optimizer_type')),
            'llm_prompt': _dict_value(metadata.get('llm_prompt'), source_candidate.get('llm_prompt')),
            'llm_response': _dict_value(metadata.get('llm_response'), source_candidate.get('llm_response')),
            'target_symbols': list(target_symbols),
            'stock_pool': dict(stock_pool),
            'selection_logic': list(selection_logic),
            'research_scope': dict(research_scope),
            'research_task': dict(research_task),
            'event_context': dict(event_context),
            'task_run_id': _scalar_value(metadata.get('task_run_id'), source_candidate.get('task_run_id')),
            'parent_strategy_id': _scalar_value(metadata.get('parent_strategy_id'), source_candidate.get('parent_strategy_id')),
            'pipeline_provenance': _dict_value(metadata.get('pipeline_provenance')),
            'experiment_id': experiment_id,
            'tags': list(dict.fromkeys(['ai_generated', source, self.strategy_type, *(self.tags or [])])),
        }
