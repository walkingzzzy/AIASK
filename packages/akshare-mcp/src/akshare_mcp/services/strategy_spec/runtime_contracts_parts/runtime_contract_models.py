
from __future__ import annotations

from typing import Any

from strategy_factory.application.research_protocol_contract import CANDIDATE_CONTRACT_V2

from .constants import *  # noqa: F401,F403
from .defaults import *  # noqa: F401,F403
from .dsl_builder import *  # noqa: F401,F403
from .normalizers import *  # noqa: F401,F403

def _default_runtime_playbook(
    strategy_type: str,
    *,
    holding_horizon: Optional[dict[str, Any]] = None,
    trade_plan: Optional[dict[str, Any]] = None,
    risk_rules: Optional[dict[str, Any]] = None,
    portfolio_spec: Optional[dict[str, Any]] = None,
    execution_assumptions: Optional[dict[str, Any]] = None,
    instrument_profile: Optional[dict[str, Any]] = None,
    backtest_metrics: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    holding = dict(holding_horizon or {})
    plan = dict(trade_plan or {})
    rules = dict(risk_rules or {})
    portfolio = dict(portfolio_spec or {})
    execution = dict(execution_assumptions or {})
    family = _runtime_playbook_family(strategy_type)
    profile = dict(instrument_profile or {})
    stop_loss_mode = str(rules.get("stop_loss_mode") or "fixed_pct").strip().lower() or "fixed_pct"
    atr_window = max(5, _safe_int(rules.get("atr_window"), 14))
    atr_multiplier = max(0.5, _safe_float(rules.get("atr_multiplier"), 2.0))
    stop_floor_pct = max(
        0.02,
        abs(
            _safe_float(
                rules.get("stop_floor_pct")
                or rules.get("stop_loss_pct")
                or rules.get("stop_loss")
                or 0.08,
                0.08,
            )
        ),
    )
    trailing_activation_r = max(0.5, _safe_float(rules.get("trailing_activation_r"), 1.0))
    stop_rule_source = str(rules.get("stop_rule_source") or stop_loss_mode or "fixed_pct").strip().lower() or "fixed_pct"

    initial_stop_loss_pct = max(
        0.02,
        abs(_safe_float(rules.get("stop_loss_pct") or rules.get("stop_loss") or 0.08, 0.08)),
    )
    take_profit_pct = max(
        initial_stop_loss_pct,
        abs(_safe_float(rules.get("take_profit_pct") or rules.get("take_profit") or initial_stop_loss_pct * 2.0, initial_stop_loss_pct * 2.0)),
    )
    time_stop_days = max(1, _safe_int(rules.get("max_holding_days") or holding.get("max_days") or 20, 20))
    cooldown_days = max(
        1,
        _safe_int(
            rules.get("cooldown_days")
            or rules.get("cooldown_window_days")
            or plan.get("cooldown_window_days")
            or holding.get("cooldown_window_days")
            or 5,
            5,
        ),
    )
    max_position_pct = min(
        0.35,
        max(
            0.02,
            _safe_float(
                portfolio.get("max_position_pct")
                or rules.get("position_cap_pct")
                or rules.get("max_position_pct")
                or 0.18,
                0.18,
            ),
        ),
    )
    max_slippage_bps = max(
        1.0,
        _safe_float(execution.get("max_slippage_bps") or execution.get("slippage_bps") or 5.0, 5.0),
    )
    if family == "trend" and profile:
        atr14_pct = _instrument_profile_metric(
            profile,
            "atr14_pct_realized",
            "atr14_pct",
            default=(initial_stop_loss_pct / 2.0 if initial_stop_loss_pct > 0 else 0.03),
            minimum=0.01,
            maximum=0.12,
        )
        if stop_loss_mode == "atr_bucketed":
            initial_stop_loss_pct = _clip_float(
                max(stop_floor_pct, atr14_pct * atr_multiplier),
                stop_floor_pct,
                0.22,
                initial_stop_loss_pct,
            )
        else:
            initial_stop_loss_pct = _clip_float(1.8 * atr14_pct, 0.06, 0.18, initial_stop_loss_pct)
        take_profit_pct = _clip_float(max(2.0 * initial_stop_loss_pct, 0.12), 0.12, 0.35, take_profit_pct)
    elif stop_loss_mode == "atr_bucketed":
        initial_stop_loss_pct = max(stop_floor_pct, initial_stop_loss_pct)
    trailing_stop_pct = round(
        max(
            0.03,
            min(
                (
                    _clip_float(
                        1.2
                        * _instrument_profile_metric(
                            profile,
                            "atr14_pct_realized",
                            "atr14_pct",
                            default=0.03,
                            minimum=0.01,
                            maximum=0.12,
                        ),
                        0.05,
                        0.15,
                        0.08,
                    )
                    if family == "trend" and profile
                    else initial_stop_loss_pct * (0.8 if family == "trend" else 1.0)
                ),
                0.15 if family == "trend" else 0.12,
            ),
        ),
        4,
    )
    trailing_activation_profit_pct = round(max(initial_stop_loss_pct * trailing_activation_r, 0.05), 4)
    failure_exit_rule = "signal_or_time_stop"
    if family == "trend":
        failure_exit_rule = "opposite_signal_or_breakout_failure"
    elif family == "slow_factor":
        failure_exit_rule = "quality_drift_or_rank_decay"

    loss_bands = [
        {
            "threshold_pct": round(initial_stop_loss_pct * 0.5, 4),
            "action": "hold",
            "label": "soft_drawdown_watch",
        },
        {
            "threshold_pct": round(initial_stop_loss_pct, 4),
            "action": "reduce" if family == "slow_factor" else "exit",
            "label": "primary_stop_band",
        },
        {
            "threshold_pct": round(initial_stop_loss_pct * 1.2, 4),
            "action": "freeze_reentry",
            "label": "hard_stop_band",
        },
    ]

    position_policy = {
        "budget_mode": "fixed_fraction",
        "base_budget_pct": 0.04,
        "max_position_pct": round(max_position_pct, 4),
        "max_concurrent_positions": 2 if family in {"trend", "slow_factor"} else 1,
        "scale_in": {"enabled": False, "mode": "forbid"},
        "scale_out": {
            "enabled": family == "slow_factor",
            "mode": "reduce_then_exit" if family == "slow_factor" else "take_profit_or_trailing",
        },
    }

    if family == "slow_factor":
        time_stop_days = max(time_stop_days, 42)
        position_policy["base_budget_pct"] = 0.05
    elif family == "trend" and profile:
        annual_volatility = _instrument_profile_metric(
            profile,
            "annual_volatility_realized_252d",
            "annual_volatility",
            default=0.3,
            minimum=0.12,
            maximum=0.8,
        )
        gap_p95 = _instrument_profile_metric(
            profile,
            "gap_p95_realized",
            "gap_p95",
            default=0.03,
            minimum=0.005,
            maximum=0.15,
        )
        if annual_volatility >= 0.4 or gap_p95 >= 0.045:
            position_policy["max_position_pct"] = round(min(float(position_policy["max_position_pct"]), 0.22), 4)
        position_policy["base_budget_pct"] = round(min(max(float(position_policy.get("base_budget_pct") or 0.04), 0.04), 0.06), 4)

    incubation_policy = {
        "warmup_target_signals": 20,
        "warmup_soft_timeout_days": 5,
        "warmup_hard_timeout_days": 20,
        "warmup_max_days": 30,
    }
    if family == "trend":
        incubation_policy = _trend_runtime_warmup_policy(
            holding_horizon=holding,
            backtest_metrics=backtest_metrics,
        )
    return {
        "entry_policy": {
            "order_style": "marketable_limit",
            "signal_validity_days": max(1, min(5, max(1, time_stop_days // 5))),
            "max_slippage_bps": round(max_slippage_bps, 4),
            "tradability_guard": bool(
                execution.get("tradability_filter")
                if execution.get("tradability_filter") is not None
                else True
            ),
            "volume_confirmation": (
                {
                    "mode": "profile_percentile_or_scaled",
                    "volume_ratio_floor": round(
                        max(
                            1.05,
                            min(
                                1.8,
                                _instrument_profile_metric(
                                    profile,
                                    "volume_ratio_p80",
                                    "volume_ratio_p90",
                                    default=1.0
                                    + _instrument_profile_metric(
                                        profile,
                                        "atr14_pct_realized",
                                        "atr14_pct",
                                        default=0.03,
                                        minimum=0.01,
                                        maximum=0.12,
                                    )
                                    * 4.5,
                                    minimum=1.0,
                                    maximum=2.5,
                                ),
                            ),
                        ),
                        4,
                    ),
                    "turnover_rate_floor": round(
                        max(
                            1.02,
                            min(
                                1.7,
                                _instrument_profile_metric(
                                    profile,
                                    "turnover_rate_p80",
                                    "turnover_rate_p90",
                                    default=1.0
                                    + _instrument_profile_metric(
                                        profile,
                                        "gap_p95_realized",
                                        "gap_p95",
                                        default=0.03,
                                        minimum=0.005,
                                        maximum=0.15,
                                    )
                                    * 3.0,
                                    minimum=0.5,
                                    maximum=4.0,
                                ),
                            ),
                        ),
                        4,
                    ),
                }
                if family == "trend" and profile
                else None
            ),
        },
        "exit_policy": {
            "initial_stop_loss_pct": round(initial_stop_loss_pct, 4),
            "stop_loss_mode": stop_loss_mode,
            "atr_window": atr_window,
            "atr_multiplier": round(atr_multiplier, 4),
            "stop_floor_pct": round(stop_floor_pct, 4),
            "stop_rule_source": stop_rule_source,
            "take_profit_pct": round(take_profit_pct, 4),
            "trailing_stop_pct": trailing_stop_pct,
            "trailing_activation_profit_pct": trailing_activation_profit_pct,
            "time_stop_days": time_stop_days,
            "failure_exit_rule": failure_exit_rule,
        },
        "adverse_move_policy": {
            "loss_bands": loss_bands,
            "average_down": "forbid",
            "freeze_after_stop": True,
            "reduce_on_drawdown": family == "slow_factor",
        },
        "reentry_policy": {
            "cooldown_days": cooldown_days,
            "reclaim_condition": (
                "reclaim_fast_ma_and_break_recent_high"
                if family == "trend"
                else "recover_rank_and_trend_alignment"
                if family == "slow_factor"
                else "signal_reconfirm_after_cooldown"
            ),
            "max_retries_per_20d": 1 if family == "slow_factor" else 2,
        },
        "cooldown_by_exit_reason": {
            "time_stop": max(1, cooldown_days // 2),
            "dsl_exit": max(1, cooldown_days // 2),
            "signal_failure_exit": cooldown_days,
            "stop_loss": cooldown_days,
            "trailing_stop": max(1, cooldown_days // 2),
            "take_profit": max(1, cooldown_days // 3),
            "freeze_reentry": max(cooldown_days, cooldown_days + 2),
            "shock_exit": max(cooldown_days, cooldown_days + 4),
            "gap_through_stop": max(cooldown_days, cooldown_days + 4),
        },
        "stop_execution_mode": "gap_aware_ohlc" if family == "trend" else "close_confirmed_only",
        "position_policy": position_policy,
        "incubation_policy": incubation_policy,
    }


def _build_regime_filter_contract(
    strategy_type: str,
    *,
    market_regime_assumption: Optional[dict[str, Any]],
    instrument_profile: Optional[dict[str, Any]],
    runtime_playbook: Optional[dict[str, Any]],
) -> dict[str, Any]:
    strategy_family = _runtime_playbook_family(strategy_type)
    regime_payload = dict(market_regime_assumption or {})
    profile = dict(instrument_profile or {})
    entry_policy = dict(dict(runtime_playbook or {}).get("entry_policy") or {})
    filters: list[dict[str, Any]] = []
    trend_efficiency_floor = round(
        max(
            0.18,
            min(
                0.45,
                _instrument_profile_metric(
                    profile,
                    "trend_efficiency_60d_realized",
                    "trend_efficiency_60d",
                    default=0.28,
                    minimum=0.0,
                    maximum=0.9,
                ) * 0.9,
            ),
        ),
        4,
    )
    if strategy_family == "trend":
        filters.append(
            {
                "metric": "trend_efficiency_60d_realized",
                "op": "gte",
                "value": trend_efficiency_floor,
                "reason": "trend_family_requires_persistent_directionality",
            }
        )
        volume_confirmation = dict(entry_policy.get("volume_confirmation") or {})
        if volume_confirmation:
            if volume_confirmation.get("volume_ratio_floor") not in _EMPTY_VALUES:
                filters.append(
                    {
                        "metric": "volume_ratio",
                        "op": "gte",
                        "value": round(_safe_float(volume_confirmation.get("volume_ratio_floor"), 1.05), 4),
                        "reason": "entry_requires_participation_confirmation",
                    }
                )
            if volume_confirmation.get("turnover_rate_floor") not in _EMPTY_VALUES:
                filters.append(
                    {
                        "metric": "turnover_rate",
                        "op": "gte",
                        "value": round(_safe_float(volume_confirmation.get("turnover_rate_floor"), 1.02), 4),
                        "reason": "entry_requires_turnover_confirmation",
                    }
                )
        filters.append(
            {
                "metric": "anti_chop_cross_count_12d",
                "op": "lt",
                "value": 3,
                "reason": "avoid_repeated_short_long_cross_chop",
            }
        )
    return {
        "family": strategy_family,
        "preferred_regime": str(regime_payload.get("preferred_regime") or "").strip() or None,
        "avoid_regime": str(regime_payload.get("avoid_regime") or "").strip() or None,
        "summary": str(regime_payload.get("summary") or "").strip() or None,
        "quantified": bool(filters),
        "filters": filters,
        "measurement_source": str(profile.get("measurement_source") or "default_board_profile"),
    }


def _build_drawdown_invalidation_contract(
    strategy_type: str,
    *,
    instrument_profile: Optional[dict[str, Any]],
    runtime_playbook: Optional[dict[str, Any]],
    target_symbols: list[str],
) -> dict[str, Any]:
    profile = dict(instrument_profile or {})
    exit_policy = dict(dict(runtime_playbook or {}).get("exit_policy") or {})
    annual_volatility = _instrument_profile_metric(
        profile,
        "annual_volatility_realized_252d",
        "annual_volatility",
        default=0.3,
        minimum=0.12,
        maximum=0.8,
    )
    initial_stop = abs(_safe_float(exit_policy.get("initial_stop_loss_pct"), 0.08))
    review_threshold = round(max(0.10, min(0.22, max(initial_stop * 2.0, annual_volatility * 0.38))), 4)
    kill_threshold = round(max(review_threshold + 0.04, min(0.32, max(initial_stop * 2.8, annual_volatility * 0.55))), 4)
    applies_as_hard_gate = strategy_type in _TREND_EXECUTABLE_DSL_TYPES and len(target_symbols or []) <= 1
    return {
        "review_drawdown_pct": review_threshold,
        "kill_drawdown_pct": kill_threshold,
        "apply_as_hard_gate": applies_as_hard_gate,
        "stage_action": {
            "review_threshold": "forced_review",
            "kill_threshold": "kill_switch",
        },
        "measurement_source": str(profile.get("measurement_source") or "default_board_profile"),
    }


def _build_thesis_invalidation_contract(
    strategy_type: str,
    *,
    trade_plan: Optional[dict[str, Any]],
    runtime_playbook: Optional[dict[str, Any]],
    instrument_profile: Optional[dict[str, Any]],
    drawdown_invalidation_contract: Optional[dict[str, Any]],
) -> dict[str, Any]:
    playbook = dict(runtime_playbook or {})
    exit_policy = dict(playbook.get("exit_policy") or {})
    adverse_move_policy = dict(playbook.get("adverse_move_policy") or {})
    profile = dict(instrument_profile or {})
    invalidates_when: list[dict[str, Any]] = []
    invalidates_when.append(
        {
            "reason": "signal_failure_exit",
            "trigger": str(exit_policy.get("failure_exit_rule") or "signal_or_time_stop"),
            "source": "runtime_playbook.exit_policy.failure_exit_rule",
        }
    )
    if adverse_move_policy.get("freeze_after_stop") is not None:
        invalidates_when.append(
            {
                "reason": "adverse_move_exit",
                "trigger": "freeze_after_stop" if adverse_move_policy.get("freeze_after_stop") else "adverse_move_exit",
                "source": "runtime_playbook.adverse_move_policy.freeze_after_stop",
            }
        )
    if strategy_type in _TREND_EXECUTABLE_DSL_TYPES:
        invalidates_when.append(
            {
                "reason": "trend_efficiency_break",
                "metric": "trend_efficiency_60d_realized",
                "op": "lt",
                "value": round(
                    max(
                        0.12,
                        min(
                            0.28,
                            _instrument_profile_metric(
                                profile,
                                "trend_efficiency_60d_realized",
                                "trend_efficiency_60d",
                                default=0.24,
                                minimum=0.0,
                                maximum=0.9,
                            ) * 0.75,
                        ),
                    ),
                    4,
                ),
                "source": "instrument_profile",
            }
        )
    return {
        "strategy_family": _runtime_playbook_family(strategy_type),
        "trade_plan_entry": dict((trade_plan or {}).get("entry") or {}),
        "invalidates_when": invalidates_when,
        "drawdown_linked": dict(drawdown_invalidation_contract or {}),
    }
