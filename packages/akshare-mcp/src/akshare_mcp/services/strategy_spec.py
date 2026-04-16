"""StrategySpec data class and configuration constants."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4

from strategy_factory.application.market_evidence import (
    build_market_fact_gate_audit,
    normalize_market_evidence_facts,
)
from strategy_factory.application.research_protocol_contract import (
    CANDIDATE_CONTRACT_V2,
    build_research_validation_contract,
    normalize_field_provenance_token,
    normalize_prediction_trace_id,
)


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
_TREND_EXECUTABLE_DSL_TYPES = {"ma_cross", "momentum", "volatility_breakout"}
_PROXY_RUNTIME_FACTOR_TYPES = {"quality_factor", "value_factor", "growth_factor"}
_HIGH_VOL_BOARD_BUCKETS = {"star", "chinext", "beijing"}
_EMPTY_VALUES = (None, "", [], {})
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


def _clip_float(value: Any, minimum: float, maximum: float, default: float) -> float:
    resolved = _safe_float(value, default)
    return max(float(minimum), min(float(maximum), resolved))


def _resolve_profile_metric(
    *,
    profile: Optional[dict[str, Any]],
    summary: Optional[dict[str, Any]],
    measured_keys: tuple[str, ...],
    legacy_keys: tuple[str, ...],
    minimum: float,
    maximum: float,
    default: float,
) -> tuple[float, str]:
    for source_label, source in (("profile", dict(profile or {})), ("summary", dict(summary or {}))):
        for key in (*measured_keys, *legacy_keys):
            value = source.get(key)
            if value not in _EMPTY_VALUES:
                return round(_clip_float(value, minimum, maximum, default), 4), f"{source_label}:{key}"
    return round(float(default), 4), "default"


def _instrument_profile_metric(
    profile: Optional[dict[str, Any]],
    *keys: str,
    default: float,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    payload = dict(profile or {})
    for key in keys:
        value = payload.get(key)
        if value not in _EMPTY_VALUES:
            resolved = _safe_float(value, default)
            if minimum is not None:
                resolved = max(float(minimum), resolved)
            if maximum is not None:
                resolved = min(float(maximum), resolved)
            return float(resolved)
    resolved = float(default)
    if minimum is not None:
        resolved = max(float(minimum), resolved)
    if maximum is not None:
        resolved = min(float(maximum), resolved)
    return resolved


def _primary_target_code(target_symbols: list[str]) -> str:
    return str((list(target_symbols or []) or [""])[0] or "").strip()


def _normalize_board_bucket(value: Any, *, code: str = "") -> str:
    token = str(value or "").strip().lower()
    aliases = {
        "futures": "futures",
        "commodity_futures": "futures",
        "star": "star",
        "star_market": "star",
        "科创板": "star",
        "chinext": "chinext",
        "创业板": "chinext",
        "growth_enterprise_market": "chinext",
        "beijing": "beijing",
        "bj": "beijing",
        "北交所": "beijing",
        "main_board": "main_board",
        "main": "main_board",
        "主板": "main_board",
    }
    if token in aliases:
        return aliases[token]
    normalized_code = str(code or "").split(".")[0].strip()
    if normalized_code.isalpha():
        return "futures"
    if normalized_code.startswith("688"):
        return "star"
    if normalized_code.startswith(("300", "301")):
        return "chinext"
    if normalized_code.startswith(("8", "4", "92")):
        return "beijing"
    if normalized_code:
        return "main_board"
    return "unknown"


def _default_instrument_profile(
    *,
    target_symbols: list[str],
    source_symbol_summary: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    code = _primary_target_code(target_symbols)
    summary = dict(source_symbol_summary or {})
    board_bucket = _normalize_board_bucket(
        summary.get("board_bucket") or summary.get("market"),
        code=code,
    )
    defaults_by_board = {
        "star": {
            "annual_volatility": 0.47,
            "atr14_pct": 0.044,
            "gap_p95": 0.051,
            "trend_efficiency_60d": 0.24,
            "turnover_median": 1.8,
        },
        "chinext": {
            "annual_volatility": 0.42,
            "atr14_pct": 0.039,
            "gap_p95": 0.045,
            "trend_efficiency_60d": 0.26,
            "turnover_median": 1.6,
        },
        "beijing": {
            "annual_volatility": 0.55,
            "atr14_pct": 0.060,
            "gap_p95": 0.070,
            "trend_efficiency_60d": 0.18,
            "turnover_median": 2.2,
        },
        "main_board": {
            "annual_volatility": 0.30,
            "atr14_pct": 0.026,
            "gap_p95": 0.028,
            "trend_efficiency_60d": 0.33,
            "turnover_median": 1.1,
        },
    }
    defaults = dict(defaults_by_board.get(board_bucket) or {
        "annual_volatility": 0.34,
        "atr14_pct": 0.030,
        "gap_p95": 0.032,
        "trend_efficiency_60d": 0.30,
        "turnover_median": 1.2,
    })
    market_cap = _safe_float(summary.get("market_cap"), 0.0)
    if market_cap >= 150_000_000_000.0:
        defaults["annual_volatility"] = max(0.18, defaults["annual_volatility"] - 0.06)
        defaults["atr14_pct"] = max(0.018, defaults["atr14_pct"] - 0.006)
        defaults["gap_p95"] = max(0.018, defaults["gap_p95"] - 0.006)
        defaults["trend_efficiency_60d"] = min(0.55, defaults["trend_efficiency_60d"] + 0.05)
        defaults["turnover_median"] = max(0.7, defaults["turnover_median"] - 0.15)
    elif 0 < market_cap <= 15_000_000_000.0:
        defaults["annual_volatility"] = min(0.62, defaults["annual_volatility"] + 0.05)
        defaults["atr14_pct"] = min(0.080, defaults["atr14_pct"] + 0.008)
        defaults["gap_p95"] = min(0.090, defaults["gap_p95"] + 0.008)
        defaults["trend_efficiency_60d"] = max(0.14, defaults["trend_efficiency_60d"] - 0.04)
        defaults["turnover_median"] = min(3.0, defaults["turnover_median"] + 0.2)
    intraday_range_p90 = round(max(defaults["atr14_pct"] * 1.55, defaults["gap_p95"] * 1.25), 4)
    volume_ratio_p80 = round(max(1.02, min(1.20, 1.0 + defaults["atr14_pct"] * 2.0)), 4)
    volume_ratio_p90 = round(max(volume_ratio_p80 + 0.04, min(1.45, volume_ratio_p80 + 0.12)), 4)
    turnover_rate_p80 = round(max(0.9, defaults["turnover_median"] * 0.95), 4)
    turnover_rate_p90 = round(max(turnover_rate_p80 + 0.15, min(6.0, defaults["turnover_median"] * 1.2)), 4)
    return {
        "annual_volatility_realized_252d": round(defaults["annual_volatility"], 4),
        "annual_volatility": round(defaults["annual_volatility"], 4),
        "atr14_pct_realized": round(defaults["atr14_pct"], 4),
        "atr14_pct": round(defaults["atr14_pct"], 4),
        "gap_p95_realized": round(defaults["gap_p95"], 4),
        "gap_p95": round(defaults["gap_p95"], 4),
        "intraday_range_p90": intraday_range_p90,
        "trend_efficiency_60d_realized": round(defaults["trend_efficiency_60d"], 4),
        "trend_efficiency_60d": round(defaults["trend_efficiency_60d"], 4),
        "turnover_median": round(defaults["turnover_median"], 4),
        "volume_ratio_p80": volume_ratio_p80,
        "volume_ratio_p90": volume_ratio_p90,
        "turnover_rate_p80": turnover_rate_p80,
        "turnover_rate_p90": turnover_rate_p90,
        "measurement_source": "default_board_profile",
        "measurement_sources": {
            "annual_volatility_realized_252d": "default",
            "atr14_pct_realized": "default",
            "gap_p95_realized": "default",
            "intraday_range_p90": "default",
            "trend_efficiency_60d_realized": "default",
            "volume_ratio_p80": "default",
            "volume_ratio_p90": "default",
            "turnover_rate_p80": "default",
            "turnover_rate_p90": "default",
        },
        "measured_profile_complete": False,
        "board_bucket": board_bucket,
        "market_cap": round(market_cap, 2) if market_cap > 0 else None,
        "symbol": code or None,
    }


def _normalize_instrument_profile(
    profile: Optional[dict[str, Any]],
    *,
    target_symbols: list[str],
    source_symbol_summary: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    defaults = _default_instrument_profile(
        target_symbols=target_symbols,
        source_symbol_summary=source_symbol_summary,
    )
    payload = dict(profile or {})
    summary = dict(source_symbol_summary or {})
    code = _primary_target_code(target_symbols)
    board_bucket = _normalize_board_bucket(
        payload.get("board_bucket") or defaults.get("board_bucket"),
        code=code,
    )
    annual_volatility_realized_252d, annual_volatility_source = _resolve_profile_metric(
        profile=payload,
        summary=summary,
        measured_keys=("annual_volatility_realized_252d", "annual_volatility_realized", "realized_annual_volatility"),
        legacy_keys=("annual_volatility",),
        minimum=0.12,
        maximum=0.80,
        default=_safe_float(defaults["annual_volatility"], defaults["annual_volatility"]),
    )
    atr14_pct_realized, atr14_pct_source = _resolve_profile_metric(
        profile=payload,
        summary=summary,
        measured_keys=("atr14_pct_realized", "atr14_pct_14d_realized", "realized_atr14_pct"),
        legacy_keys=("atr14_pct",),
        minimum=0.01,
        maximum=0.12,
        default=_safe_float(defaults["atr14_pct"], defaults["atr14_pct"]),
    )
    gap_p95_realized, gap_p95_source = _resolve_profile_metric(
        profile=payload,
        summary=summary,
        measured_keys=("gap_p95_realized", "gap_p95", "open_gap_p95"),
        legacy_keys=("gap_p95",),
        minimum=0.005,
        maximum=0.15,
        default=_safe_float(defaults["gap_p95"], defaults["gap_p95"]),
    )
    intraday_range_p90, intraday_range_source = _resolve_profile_metric(
        profile=payload,
        summary=summary,
        measured_keys=("intraday_range_p90", "intraday_range_p90_realized"),
        legacy_keys=(),
        minimum=0.01,
        maximum=0.20,
        default=_safe_float(defaults["intraday_range_p90"], defaults["intraday_range_p90"]),
    )
    trend_efficiency_60d_realized, trend_efficiency_source = _resolve_profile_metric(
        profile=payload,
        summary=summary,
        measured_keys=("trend_efficiency_60d_realized",),
        legacy_keys=("trend_efficiency_60d",),
        minimum=0.0,
        maximum=0.9,
        default=_safe_float(defaults["trend_efficiency_60d"], defaults["trend_efficiency_60d"]),
    )
    turnover_median, turnover_median_source = _resolve_profile_metric(
        profile=payload,
        summary=summary,
        measured_keys=("turnover_median_realized",),
        legacy_keys=("turnover_median",),
        minimum=0.1,
        maximum=8.0,
        default=_safe_float(defaults["turnover_median"], defaults["turnover_median"]),
    )
    volume_ratio_p80, volume_ratio_p80_source = _resolve_profile_metric(
        profile=payload,
        summary=summary,
        measured_keys=("volume_ratio_p80",),
        legacy_keys=(),
        minimum=1.0,
        maximum=2.5,
        default=_safe_float(defaults["volume_ratio_p80"], defaults["volume_ratio_p80"]),
    )
    volume_ratio_p90, volume_ratio_p90_source = _resolve_profile_metric(
        profile=payload,
        summary=summary,
        measured_keys=("volume_ratio_p90",),
        legacy_keys=(),
        minimum=1.02,
        maximum=3.0,
        default=_safe_float(defaults["volume_ratio_p90"], defaults["volume_ratio_p90"]),
    )
    turnover_rate_p80, turnover_rate_p80_source = _resolve_profile_metric(
        profile=payload,
        summary=summary,
        measured_keys=("turnover_rate_p80",),
        legacy_keys=(),
        minimum=0.1,
        maximum=8.0,
        default=_safe_float(defaults["turnover_rate_p80"], defaults["turnover_rate_p80"]),
    )
    turnover_rate_p90, turnover_rate_p90_source = _resolve_profile_metric(
        profile=payload,
        summary=summary,
        measured_keys=("turnover_rate_p90",),
        legacy_keys=(),
        minimum=0.1,
        maximum=10.0,
        default=_safe_float(defaults["turnover_rate_p90"], defaults["turnover_rate_p90"]),
    )
    measured_sources = {
        "annual_volatility_realized_252d": annual_volatility_source,
        "atr14_pct_realized": atr14_pct_source,
        "gap_p95_realized": gap_p95_source,
        "intraday_range_p90": intraday_range_source,
        "trend_efficiency_60d_realized": trend_efficiency_source,
        "turnover_median": turnover_median_source,
        "volume_ratio_p80": volume_ratio_p80_source,
        "volume_ratio_p90": volume_ratio_p90_source,
        "turnover_rate_p80": turnover_rate_p80_source,
        "turnover_rate_p90": turnover_rate_p90_source,
    }
    measured_profile_complete = all(
        measured_sources[key] != "default"
        for key in (
            "annual_volatility_realized_252d",
            "atr14_pct_realized",
            "gap_p95_realized",
            "intraday_range_p90",
            "trend_efficiency_60d_realized",
            "volume_ratio_p80",
            "volume_ratio_p90",
            "turnover_rate_p80",
            "turnover_rate_p90",
        )
    )
    measurement_source = "measured" if measured_profile_complete else (
        "partial_measured"
        if any(source != "default" for source in measured_sources.values())
        else "default_board_profile"
    )
    normalized = {
        "annual_volatility_realized_252d": annual_volatility_realized_252d,
        "annual_volatility": annual_volatility_realized_252d,
        "atr14_pct_realized": atr14_pct_realized,
        "atr14_pct": atr14_pct_realized,
        "gap_p95_realized": gap_p95_realized,
        "gap_p95": gap_p95_realized,
        "intraday_range_p90": intraday_range_p90,
        "trend_efficiency_60d_realized": trend_efficiency_60d_realized,
        "trend_efficiency_60d": trend_efficiency_60d_realized,
        "turnover_median": turnover_median,
        "volume_ratio_p80": volume_ratio_p80,
        "volume_ratio_p90": volume_ratio_p90,
        "turnover_rate_p80": turnover_rate_p80,
        "turnover_rate_p90": turnover_rate_p90,
        "measurement_source": measurement_source,
        "measurement_sources": measured_sources,
        "measured_profile_complete": measured_profile_complete,
        "board_bucket": board_bucket,
        "market_cap": round(
            _safe_float(
                payload.get("market_cap"),
                defaults.get("market_cap") or 0.0,
            ),
            2,
        ) if _safe_float(payload.get("market_cap"), defaults.get("market_cap") or 0.0) > 0 else defaults.get("market_cap"),
        "symbol": code or payload.get("symbol") or defaults.get("symbol"),
    }
    for extra_key in (
        "asset_class",
        "underlying",
        "curve_legs",
        "roll_rule",
    ):
        value = payload.get(extra_key)
        if value not in _EMPTY_VALUES:
            normalized[extra_key] = value
    if str(normalized.get("asset_class") or "").strip().lower() == "futures":
        normalized["board_bucket"] = "futures"
    return normalized


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


def _runtime_playbook_family(strategy_type: str) -> str:
    family = str(strategy_type or "").strip().lower()
    if family in {"momentum", "ma_cross", "volatility_breakout"}:
        return "trend"
    if family in {"quality_factor", "value_factor"}:
        return "slow_factor"
    return "default"


def _trend_strategy_requires_compiled_dsl(strategy_type: str, target_symbols: list[str]) -> bool:
    return str(strategy_type or "").strip().lower() in _TREND_EXECUTABLE_DSL_TYPES and len(list(target_symbols or [])) == 1


def _has_nonempty_mapping(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def _semantic_contract_missing_fields(
    strategy_type: str,
    *,
    evidence_chain: Optional[dict[str, Any]],
    prediction_contract: Optional[dict[str, Any]],
    confidence_contract: Optional[dict[str, Any]],
) -> list[str]:
    normalized_strategy_type = str(strategy_type or "").strip().lower()
    if normalized_strategy_type not in (_TREND_EXECUTABLE_DSL_TYPES | _PROXY_RUNTIME_FACTOR_TYPES):
        return []
    missing: list[str] = []
    if not _has_nonempty_mapping(evidence_chain):
        missing.append("evidence_chain")
    if not _has_nonempty_mapping(prediction_contract):
        missing.append("prediction_contract")
    if not _has_nonempty_mapping(confidence_contract):
        missing.append("confidence_contract")
    return missing


def _has_true_fundamental_runtime(
    strategy_type: str,
    *,
    params: Optional[dict[str, Any]] = None,
    runtime_playbook: Optional[dict[str, Any]] = None,
) -> bool:
    normalized_strategy_type = str(strategy_type or "").strip().lower()
    if normalized_strategy_type not in _PROXY_RUNTIME_FACTOR_TYPES:
        return False
    payload = dict(params or {})
    playbook = dict(runtime_playbook or {})
    explicit_mode = str(
        payload.get("runtime_family_data_source")
        or playbook.get("runtime_family_data_source")
        or payload.get("factor_runtime_mode")
        or ""
    ).strip().lower()
    if explicit_mode in {"fundamental_runtime", "fundamental_cached_runtime", "fundamental"}:
        return True
    factor_runtime_contract = dict(
        payload.get("fundamental_runtime_contract")
        or payload.get("factor_runtime_contract")
        or {}
    )
    return bool(factor_runtime_contract)


def _resolve_runtime_semantic_diagnostics(
    *,
    strategy_type: str,
    params: Optional[dict[str, Any]],
    target_symbols: list[str],
    instrument_profile: Optional[dict[str, Any]],
    runtime_playbook: Optional[dict[str, Any]],
    evidence_chain: Optional[dict[str, Any]],
    prediction_contract: Optional[dict[str, Any]],
    confidence_contract: Optional[dict[str, Any]],
    execution_semantic_contract: Optional[dict[str, Any]],
) -> dict[str, Any]:
    normalized_strategy_type = str(strategy_type or "").strip().lower()
    profile = dict(instrument_profile or {})
    playbook = dict(runtime_playbook or {})
    execution_contract = dict(execution_semantic_contract or {})
    single_name_trend = _trend_strategy_requires_compiled_dsl(strategy_type, target_symbols)
    semantic_contract_missing_fields = _semantic_contract_missing_fields(
        normalized_strategy_type,
        evidence_chain=evidence_chain,
        prediction_contract=prediction_contract,
        confidence_contract=confidence_contract,
    )
    measurement_source = str(profile.get("measurement_source") or "default_board_profile").strip().lower() or "default_board_profile"
    measured_profile_complete = bool(profile.get("measured_profile_complete"))
    execution_semantic_mode = str(
        execution_contract.get("execution_semantic_mode")
        or dict(params or {}).get("execution_semantic_mode")
        or ""
    ).strip().lower()
    dsl_compiled = bool(
        execution_contract.get("dsl_compiled")
        or dict(params or {}).get("dsl_compiled")
        or dict(params or {}).get("dsl")
    )
    proxy_runtime_used = False
    runtime_family_data_source = "market_data_runtime"
    if normalized_strategy_type in _PROXY_RUNTIME_FACTOR_TYPES:
        runtime_family_data_source = (
            "fundamental_runtime"
            if _has_true_fundamental_runtime(
                normalized_strategy_type,
                params=params,
                runtime_playbook=playbook,
            )
            else "price_proxy_runtime"
        )
        proxy_runtime_used = runtime_family_data_source != "fundamental_runtime"

    semantic_runtime_match = True
    if normalized_strategy_type in _PROXY_RUNTIME_FACTOR_TYPES and proxy_runtime_used:
        semantic_runtime_match = False
    elif single_name_trend and (execution_semantic_mode != "compiled_dsl" or not dsl_compiled):
        semantic_runtime_match = False

    execution_semantic_gap_reasons = [
        str(item).strip()
        for item in list(execution_contract.get("execution_semantic_gap_reasons") or [])
        if str(item).strip()
    ]
    diagnostic_reasons: list[str] = []
    if semantic_contract_missing_fields:
        diagnostic_reasons.append("final_strategy_missing_semantic_contract")
    if normalized_strategy_type in _PROXY_RUNTIME_FACTOR_TYPES and proxy_runtime_used:
        diagnostic_reasons.extend(
            [
                "runtime_family_semantic_mismatch",
                "proxy_runtime_not_allowed_for_formal_incubation",
            ]
        )
    if single_name_trend and measurement_source == "default_board_profile":
        diagnostic_reasons.append("default_profile_not_allowed_for_single_name_runtime")
    elif single_name_trend and not measured_profile_complete:
        diagnostic_reasons.append("measured_profile_incomplete")

    merged_gap_reasons = list(dict.fromkeys([*execution_semantic_gap_reasons, *diagnostic_reasons]))
    diagnostic_only = bool(
        merged_gap_reasons
        or not semantic_runtime_match
    )
    if single_name_trend and (execution_semantic_mode != "compiled_dsl" or not dsl_compiled):
        execution_readiness_tier = "missing_executable_contract"
    elif diagnostic_only:
        execution_readiness_tier = "observe_diagnostic_only"
    else:
        execution_readiness_tier = "formal_runtime_ready"
    return {
        "semantic_runtime_match": semantic_runtime_match,
        "runtime_family_data_source": runtime_family_data_source,
        "proxy_runtime_used": proxy_runtime_used,
        "diagnostic_only": diagnostic_only,
        "execution_readiness_tier": execution_readiness_tier,
        "semantic_contract_missing_fields": semantic_contract_missing_fields,
        "execution_semantic_gap_reasons": merged_gap_reasons,
    }


def _ensure_trade_plan_execution_nodes(strategy_type: str, trade_plan: dict[str, Any]) -> dict[str, Any]:
    payload = dict(trade_plan or {})
    entry_bias = str(payload.get("entry_bias") or "").strip()
    exit_bias = str(payload.get("exit_bias") or "").strip()
    if not entry_bias or not exit_bias:
        defaults = _default_trade_plan(str(strategy_type or "").strip().lower(), "snapshot")
        entry_bias = entry_bias or str(defaults.get("entry_bias") or "").strip()
        exit_bias = exit_bias or str(defaults.get("exit_bias") or "").strip()
    entry_node = dict(payload.get("entry") or {})
    exit_node = dict(payload.get("exit") or {})
    entry_node.setdefault("node_id", "entry_step_1")
    entry_node.setdefault("phase", "entry")
    entry_node.setdefault("entry_bias", entry_bias or None)
    exit_node.setdefault("node_id", "exit_step_1")
    exit_node.setdefault("phase", "exit")
    exit_node.setdefault("exit_bias", exit_bias or None)
    payload["entry_bias"] = entry_bias or None
    payload["exit_bias"] = exit_bias or None
    payload["entry"] = entry_node
    payload["exit"] = exit_node
    return payload


def _trend_runtime_warmup_policy(
    *,
    holding_horizon: dict[str, Any],
    backtest_metrics: Optional[dict[str, Any]],
) -> dict[str, Any]:
    metrics = dict(backtest_metrics or {})
    observed_trade_count = max(
        _safe_float(metrics.get("trade_count"), 0.0),
        _safe_float(metrics.get("trades_count"), 0.0),
        _safe_float(metrics.get("total_trades"), 0.0),
    )
    max_days = max(8, _safe_int(dict(holding_horizon or {}).get("max_days"), 20) or 20)
    expected_trade_count = observed_trade_count if observed_trade_count > 0 else max(4.0, min(12.0, 252.0 / float(max_days)))
    warmup_target_signals = max(4, min(8, int(round(expected_trade_count / 2.5)) or 4))
    warmup_soft_timeout_days = max(5, min(18, int(round(max(5, warmup_target_signals * 2.0)))))
    warmup_hard_timeout_days = max(20, min(45, int(round(max(20, warmup_target_signals * 5.0)))))
    warmup_max_days = max(30, min(60, int(round(max(warmup_hard_timeout_days + 10, warmup_soft_timeout_days + 15)))))
    return {
        "warmup_target_signals": warmup_target_signals,
        "warmup_soft_timeout_days": warmup_soft_timeout_days,
        "warmup_hard_timeout_days": warmup_hard_timeout_days,
        "warmup_max_days": warmup_max_days,
    }


def _build_single_name_trend_dsl(
    strategy_type: str,
    *,
    params: dict[str, Any],
    trade_plan: dict[str, Any],
    holding_horizon: dict[str, Any],
    instrument_profile: dict[str, Any],
    risk_rules: dict[str, Any],
) -> dict[str, Any]:
    family = str(strategy_type or "").strip().lower()
    entry_node_id = str(dict(trade_plan.get("entry") or {}).get("node_id") or "entry_step_1").strip() or "entry_step_1"
    exit_node_id = str(dict(trade_plan.get("exit") or {}).get("node_id") or "exit_step_1").strip() or "exit_step_1"
    atr14_pct = _instrument_profile_metric(
        instrument_profile,
        "atr14_pct_realized",
        "atr14_pct",
        default=0.03,
        minimum=0.01,
        maximum=0.12,
    )
    trend_efficiency = _instrument_profile_metric(
        instrument_profile,
        "trend_efficiency_60d_realized",
        "trend_efficiency_60d",
        default=0.3,
        minimum=0.0,
        maximum=0.9,
    )
    gap_p95 = _instrument_profile_metric(
        instrument_profile,
        "gap_p95_realized",
        "gap_p95",
        default=0.03,
        minimum=0.005,
        maximum=0.15,
    )
    intraday_range_p90 = _instrument_profile_metric(
        instrument_profile,
        "intraday_range_p90",
        default=max(atr14_pct * 1.5, gap_p95),
        minimum=0.01,
        maximum=0.20,
    )
    volume_ratio_floor = round(
        max(
            1.05,
            min(
                1.8,
                _instrument_profile_metric(
                    instrument_profile,
                    "volume_ratio_p80",
                    "volume_ratio_p90",
                    default=1.0 + atr14_pct * 4.5,
                    minimum=1.0,
                    maximum=2.5,
                ),
            ),
        ),
        4,
    )
    turnover_rate_floor = round(
        max(
            1.02,
            min(
                1.7,
                _instrument_profile_metric(
                    instrument_profile,
                    "turnover_rate_p80",
                    "turnover_rate_p90",
                    default=1.0 + gap_p95 * 3.0,
                    minimum=0.5,
                    maximum=4.0,
                ),
            ),
        ),
        4,
    )
    adx_floor = round(max(16.0, min(30.0, 18.0 + max(0.0, (trend_efficiency - 0.2) * 25.0))), 4)
    upper_shadow_ratio_max = round(
        max(
            0.22,
            min(
                0.48,
                0.42 - max(0.0, trend_efficiency - 0.2) * 0.2 + max(0.0, intraday_range_p90 - atr14_pct) * 0.2,
            ),
        ),
        4,
    )
    anti_chop_count_threshold = 3.0
    long_shadow_window = 5
    max_days = max(5, _safe_int(holding_horizon.get("max_days"), 20) or 20)
    metadata = {
        "strategy_profile": {
            "family": family,
            "execution_semantic_mode": "compiled_dsl",
        },
        "target_symbols": list(params.get("target_symbols") or []),
        "holding_horizon": dict(holding_horizon or {}),
        "holding_horizon_days": max_days,
        "instrument_profile": dict(instrument_profile or {}),
    }

    def _tag(condition: dict[str, Any], node_id: str) -> dict[str, Any]:
        return {**condition, "trade_plan_node_id": node_id}

    if family == "ma_cross":
        short_period = max(3, _safe_int(params.get("short_period"), 5) or 5)
        long_period = max(short_period + 2, _safe_int(params.get("long_period"), 20) or 20)
        slope_lookback = max(3, min(10, long_period // 4 or 3))
        anti_chop_window = max(8, min(15, long_period // 2 or 8))
        entry = {
            "all": [
                _tag(
                    {
                        "op": "cross_above",
                        "left": {"indicator": "sma", "field": "close", "window": short_period},
                        "right": {"indicator": "sma", "field": "close", "window": long_period},
                    },
                    entry_node_id,
                ),
                _tag(
                    {
                        "op": "gt",
                        "left": {"indicator": "slope", "field": "close", "window": long_period, "lookback": slope_lookback},
                        "right": {"value": 0.0},
                    },
                    entry_node_id,
                ),
                _tag(
                    {
                        "op": "gte",
                        "left": {"indicator": "adx", "window": max(7, min(20, long_period // 2 or 7))},
                        "right": {"value": adx_floor},
                    },
                    entry_node_id,
                ),
                {
                    "any": [
                        _tag(
                            {
                                "op": "gte",
                                "left": {"indicator": "volume_ratio", "window": 20},
                                "right": {"value": volume_ratio_floor},
                            },
                            entry_node_id,
                        ),
                        _tag(
                            {
                                "op": "gte",
                                "left": {"indicator": "turnover_rate", "window": 20},
                                "right": {"value": turnover_rate_floor},
                            },
                            entry_node_id,
                        ),
                    ]
                },
                {
                    "not": _tag(
                        {
                            "op": "gte",
                            "left": {
                                "indicator": "rolling_count",
                                "window": long_shadow_window,
                                "condition": {
                                    "all": [
                                        {
                                            "op": "gte",
                                            "left": {"indicator": "upper_shadow_ratio"},
                                            "right": {"value": upper_shadow_ratio_max},
                                        },
                                        {
                                            "op": "gte",
                                            "left": {"indicator": "volume_ratio", "window": 20},
                                            "right": {"value": max(1.0, round(volume_ratio_floor - 0.1, 4))},
                                        },
                                    ]
                                },
                            },
                            "right": {"value": 1.0},
                        },
                        entry_node_id,
                    )
                },
                {
                    "not": _tag(
                        {
                            "op": "gte",
                            "left": {
                                "indicator": "rolling_count",
                                "window": anti_chop_window,
                                "condition": {
                                    "any": [
                                        {
                                            "op": "cross_above",
                                            "left": {"indicator": "sma", "field": "close", "window": short_period},
                                            "right": {"indicator": "sma", "field": "close", "window": long_period},
                                        },
                                        {
                                            "op": "cross_below",
                                            "left": {"indicator": "sma", "field": "close", "window": short_period},
                                            "right": {"indicator": "sma", "field": "close", "window": long_period},
                                        },
                                    ]
                                },
                            },
                            "right": {"value": anti_chop_count_threshold},
                        },
                        entry_node_id,
                    )
                },
            ]
        }
        exit_rule = {
            "any": [
                _tag(
                    {
                        "op": "cross_below",
                        "left": {"indicator": "sma", "field": "close", "window": short_period},
                        "right": {"indicator": "sma", "field": "close", "window": long_period},
                    },
                    exit_node_id,
                ),
                _tag(
                    {
                        "op": "lte",
                        "left": {"indicator": "slope", "field": "close", "window": long_period, "lookback": slope_lookback},
                        "right": {"value": 0.0},
                    },
                    exit_node_id,
                ),
                _tag(
                    {
                        "op": "lt",
                        "left": {"indicator": "roc", "field": "close", "window": max(3, short_period)},
                        "right": {"value": -round(max(0.02, min(0.12, atr14_pct * 1.2)), 4)},
                    },
                    exit_node_id,
                ),
            ]
        }
    elif family == "momentum":
        lookback = max(3, _safe_int(params.get("lookback") or params.get("period"), 8) or 8)
        threshold = round(max(0.01, min(0.15, abs(_safe_float(params.get("threshold"), 0.02)))), 4)
        trend_window = max(10, min(30, lookback * 2))
        entry = {
            "all": [
                _tag(
                    {
                        "op": "gt",
                        "left": {"indicator": "roc", "field": "close", "window": lookback},
                        "right": {"value": threshold},
                    },
                    entry_node_id,
                ),
                _tag(
                    {
                        "op": "gt",
                        "left": {"field": "close"},
                        "right": {"indicator": "sma", "field": "close", "window": trend_window},
                    },
                    entry_node_id,
                ),
                _tag(
                    {
                        "op": "gte",
                        "left": {"indicator": "adx", "window": max(7, min(20, trend_window // 2))},
                        "right": {"value": adx_floor},
                    },
                    entry_node_id,
                ),
                _tag(
                    {
                        "op": "gte",
                        "left": {"indicator": "volume_ratio", "window": 20},
                        "right": {"value": max(1.0, round(volume_ratio_floor - 0.05, 4))},
                    },
                    entry_node_id,
                ),
            ]
        }
        exit_rule = {
            "any": [
                _tag(
                    {
                        "op": "lt",
                        "left": {"indicator": "roc", "field": "close", "window": lookback},
                        "right": {"value": round(-threshold * 0.25, 4)},
                    },
                    exit_node_id,
                ),
                _tag(
                    {
                        "op": "lt",
                        "left": {"field": "close"},
                        "right": {"indicator": "sma", "field": "close", "window": trend_window},
                    },
                    exit_node_id,
                ),
                _tag(
                    {
                        "op": "lte",
                        "left": {"indicator": "slope", "field": "close", "window": trend_window, "lookback": max(3, lookback // 2)},
                        "right": {"value": 0.0},
                    },
                    exit_node_id,
                ),
            ]
        }
    else:
        breakout_window = max(10, _safe_int(params.get("breakout_window"), 20) or 20)
        trend_window = max(10, min(30, breakout_window))
        atr_multiple = round(max(0.5, min(2.0, 1.0 + atr14_pct * 10.0)), 4)
        entry = {
            "all": [
                _tag(
                    {
                        "op": "gte",
                        "left": {"field": "close"},
                        "right": {
                            "binary": {
                                "op": "sub",
                                "left": {"indicator": "highest", "field": "high", "window": breakout_window},
                                "right": {
                                    "binary": {
                                        "op": "mul",
                                        "left": {"indicator": "atr", "window": 14},
                                        "right": {"value": atr_multiple},
                                    }
                                },
                            }
                        },
                    },
                    entry_node_id,
                ),
                _tag(
                    {
                        "op": "gte",
                        "left": {"indicator": "adx", "window": max(7, min(20, breakout_window // 2))},
                        "right": {"value": adx_floor},
                    },
                    entry_node_id,
                ),
                _tag(
                    {
                        "op": "gte",
                        "left": {"indicator": "volume_ratio", "window": 20},
                        "right": {"value": volume_ratio_floor},
                    },
                    entry_node_id,
                ),
            ]
        }
        exit_rule = {
            "any": [
                _tag(
                    {
                        "op": "lt",
                        "left": {"field": "close"},
                        "right": {"indicator": "lowest", "field": "low", "window": max(5, breakout_window // 2)},
                    },
                    exit_node_id,
                ),
                _tag(
                    {
                        "op": "lt",
                        "left": {"field": "close"},
                        "right": {"indicator": "sma", "field": "close", "window": trend_window},
                    },
                    exit_node_id,
                ),
                _tag(
                    {
                        "op": "lte",
                        "left": {"indicator": "slope", "field": "close", "window": trend_window, "lookback": max(3, trend_window // 4)},
                        "right": {"value": 0.0},
                    },
                    exit_node_id,
                ),
            ]
        }
    return {
        "version": "1.0",
        "timeframe": "daily",
        "entry": entry,
        "exit": exit_rule,
        "metadata": metadata,
        "risk_rules": dict(risk_rules or {}),
    }


def _resolve_execution_semantic_contract(
    *,
    strategy_type: str,
    params: dict[str, Any],
    target_symbols: list[str],
    trade_plan: dict[str, Any],
    holding_horizon: dict[str, Any],
    risk_rules: dict[str, Any],
    position_sizing: dict[str, Any],
    stock_pool: dict[str, Any],
    prediction_contract: dict[str, Any],
    instrument_profile: dict[str, Any],
    explicit_dsl: dict[str, Any],
    existing_claim_to_trade_plan_map: dict[str, Any],
    existing_trade_plan_to_dsl_map: dict[str, Any],
    existing_dsl_support_audit: dict[str, Any],
) -> dict[str, Any]:
    requires_dsl = _trend_strategy_requires_compiled_dsl(strategy_type, target_symbols)
    dsl_payload = dict(explicit_dsl or {})
    compile_failure_reasons: list[str] = []
    if not dsl_payload and requires_dsl:
        dsl_payload = _build_single_name_trend_dsl(
            strategy_type,
            params=params,
            trade_plan=trade_plan,
            holding_horizon=holding_horizon,
            instrument_profile=instrument_profile,
            risk_rules=risk_rules,
        )
        if not dsl_payload:
            compile_failure_reasons.append("trend_family_dsl_synthesis_failed")

    compiled_dsl: dict[str, Any] = {}
    dsl_support_audit = dict(existing_dsl_support_audit or {})
    claim_to_trade_plan_map = dict(existing_claim_to_trade_plan_map or {})
    trade_plan_to_dsl_map = dict(existing_trade_plan_to_dsl_map or {})

    if dsl_payload:
        try:
            from .strategy_dsl import compile_strategy_blueprint

            compiled = compile_strategy_blueprint(
                {
                    "name": f"{strategy_type}_compiled_execution_contract",
                    "strategy_type": strategy_type,
                    "target_symbols": list(target_symbols),
                    "stock_pool": dict(stock_pool or {}),
                    "holding_horizon": dict(holding_horizon or {}),
                    "trade_plan": dict(trade_plan or {}),
                    "prediction_contract": dict(prediction_contract or {}),
                    "position_sizing": dict(position_sizing or {}),
                    "risk_rules": dict(risk_rules or {}),
                    "dsl": dict(dsl_payload or {}),
                },
                tune_for_factory=False,
            )
            compiled_dsl = dict((compiled.get("params") or {}).get("dsl") or {})
            compiled_meta = dict(compiled.get("metadata") or {})
            if not dsl_support_audit:
                dsl_support_audit = dict(compiled_meta.get("dsl_support_audit") or {})
            if not claim_to_trade_plan_map or not dict(claim_to_trade_plan_map).get("claim_to_trade_step_ids"):
                claim_to_trade_plan_map = dict(compiled_meta.get("claim_to_trade_plan_map") or {})
            if not trade_plan_to_dsl_map or int(dict(trade_plan_to_dsl_map).get("mapped_trade_step_count") or 0) <= 0:
                trade_plan_to_dsl_map = dict(compiled_meta.get("trade_plan_to_dsl_map") or {})
        except Exception as exc:
            compile_failure_reasons.append(f"dsl_compile_failed:{type(exc).__name__}")

    dsl_compiled = bool(compiled_dsl)
    mapped_trade_step_count = int(dict(trade_plan_to_dsl_map or {}).get("mapped_trade_step_count") or 0)
    execution_semantic_gap_reasons: list[str] = []
    if requires_dsl and not dsl_compiled:
        execution_semantic_gap_reasons.append("compiled_dsl_missing_for_single_name_trend_strategy")
    if requires_dsl and mapped_trade_step_count <= 0:
        execution_semantic_gap_reasons.append("trade_plan_to_dsl_map_missing_for_single_name_trend_strategy")
    execution_semantic_gap_reasons.extend(
        reason for reason in compile_failure_reasons if reason not in execution_semantic_gap_reasons
    )
    execution_semantic_mode = (
        "compiled_dsl"
        if dsl_compiled
        else "missing_executable_contract"
        if requires_dsl
        else "builtin_legacy"
    )
    return {
        "dsl": compiled_dsl,
        "dsl_support_audit": dsl_support_audit,
        "claim_to_trade_plan_map": claim_to_trade_plan_map,
        "trade_plan_to_dsl_map": trade_plan_to_dsl_map,
        "dsl_required": requires_dsl,
        "dsl_compiled": dsl_compiled,
        "execution_semantic_mode": execution_semantic_mode,
        "execution_semantic_gap": bool(execution_semantic_gap_reasons),
        "execution_semantic_gap_reasons": execution_semantic_gap_reasons,
        "dsl_compile_failure_reasons": compile_failure_reasons,
    }


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


def _build_parameter_coherence_audit(
    strategy_type: str,
    *,
    holding_horizon: Optional[dict[str, Any]],
    rebalance_rule: Optional[dict[str, Any]],
    runtime_playbook: Optional[dict[str, Any]],
    instrument_profile: Optional[dict[str, Any]],
    backtest_metrics: Optional[dict[str, Any]],
) -> dict[str, Any]:
    holding = dict(holding_horizon or {})
    rebalance = dict(rebalance_rule or {})
    playbook = dict(runtime_playbook or {})
    entry_policy = dict(playbook.get("entry_policy") or {})
    exit_policy = dict(playbook.get("exit_policy") or {})
    reentry_policy = dict(playbook.get("reentry_policy") or {})
    incubation_policy = dict(playbook.get("incubation_policy") or {})
    profile = dict(instrument_profile or {})
    metrics = dict(backtest_metrics or {})
    issues: list[dict[str, Any]] = []

    atr14_pct = _instrument_profile_metric(
        profile,
        "atr14_pct_realized",
        "atr14_pct",
        default=0.03,
        minimum=0.01,
        maximum=0.12,
    )
    initial_stop = abs(_safe_float(exit_policy.get("initial_stop_loss_pct"), 0.0))
    if initial_stop > 0:
        stop_vs_atr = round(initial_stop / max(atr14_pct, 1e-6), 4)
        if stop_vs_atr < 1.2:
            issues.append(
                {
                    "code": "stop_vs_atr_too_tight",
                    "severity": "blocker",
                    "message": "initial stop loss is tighter than 1.2x ATR for the measured instrument profile",
                    "metric": "stop_vs_atr",
                    "value": stop_vs_atr,
                }
            )
        elif stop_vs_atr > 4.5:
            issues.append(
                {
                    "code": "stop_vs_atr_too_loose",
                    "severity": "warning",
                    "message": "initial stop loss is looser than 4.5x ATR and may dilute thesis invalidation timing",
                    "metric": "stop_vs_atr",
                    "value": stop_vs_atr,
                }
            )

    max_holding_days = max(
        _safe_int(holding.get("max_days"), 0),
        _safe_int(exit_policy.get("time_stop_days"), 0),
    )
    rebalance_interval_days = _safe_int(
        rebalance.get("frequency_days") or rebalance.get("rebalance_interval_days"),
        0,
    )
    if rebalance_interval_days > 0 and max_holding_days > 0 and rebalance_interval_days > max_holding_days:
        issues.append(
            {
                "code": "holding_horizon_shorter_than_rebalance_interval",
                "severity": "blocker",
                "message": "rebalance interval exceeds maximum holding horizon",
                "metric": "rebalance_interval_days",
                "value": rebalance_interval_days,
            }
        )

    observed_trade_count = max(
        _safe_float(metrics.get("trade_count"), 0.0),
        _safe_float(metrics.get("trades_count"), 0.0),
        _safe_float(metrics.get("total_trades"), 0.0),
    )
    expected_trade_interval_days = (
        round(252.0 / observed_trade_count, 2)
        if observed_trade_count > 0
        else float(max(6, max_holding_days or 20))
    )
    cooldown_days = _safe_int(reentry_policy.get("cooldown_days"), 0)
    if cooldown_days > 0 and expected_trade_interval_days > 0 and cooldown_days > expected_trade_interval_days * 1.5:
        issues.append(
            {
                "code": "cooldown_exceeds_expected_trade_interval",
                "severity": "warning",
                "message": "cooldown is materially longer than expected trade interval and may suppress re-entry evidence accumulation",
                "metric": "cooldown_days",
                "value": cooldown_days,
            }
        )

    warmup_target_signals = _safe_int(incubation_policy.get("warmup_target_signals"), 0)
    expected_annual_signals = max(1.0, observed_trade_count or round(252.0 / max(expected_trade_interval_days, 1.0), 2))
    if warmup_target_signals > max(8, expected_annual_signals * 1.25):
        issues.append(
            {
                "code": "warmup_target_exceeds_signal_density",
                "severity": "blocker" if strategy_type in _TREND_EXECUTABLE_DSL_TYPES else "warning",
                "message": "warmup target signals exceeds expected annual signal density and may deadlock incubation",
                "metric": "warmup_target_signals",
                "value": warmup_target_signals,
            }
        )

    volume_confirmation = dict(entry_policy.get("volume_confirmation") or {})
    volume_ratio_floor = _safe_float(volume_confirmation.get("volume_ratio_floor"), 0.0)
    volume_ratio_p90 = _instrument_profile_metric(
        profile,
        "volume_ratio_p90",
        default=1.18,
        minimum=1.0,
        maximum=3.0,
    )
    if volume_ratio_floor > 0 and volume_ratio_floor > volume_ratio_p90 + 0.05:
        issues.append(
            {
                "code": "volume_filter_exceeds_observed_distribution",
                "severity": "warning",
                "message": "volume confirmation floor is above observed p90 and may create signal vacuum",
                "metric": "volume_ratio_floor",
                "value": volume_ratio_floor,
            }
        )

    trade_density = _safe_float(metrics.get("trade_density"), 0.0)
    implementation_shortfall_proxy = _safe_float(metrics.get("implementation_shortfall_proxy"), 0.0)
    if trade_density > 0 and implementation_shortfall_proxy > 0 and trade_density * implementation_shortfall_proxy > 0.12:
        issues.append(
            {
                "code": "trade_density_cost_pressure_high",
                "severity": "warning",
                "message": "expected trade density and implementation shortfall imply elevated round-trip cost drag",
                "metric": "trade_density_cost_pressure",
                "value": round(trade_density * implementation_shortfall_proxy, 4),
            }
        )

    blockers = [issue["code"] for issue in issues if issue.get("severity") == "blocker"]
    warnings = [issue["code"] for issue in issues if issue.get("severity") == "warning"]
    return {
        "status": "failed" if blockers else "passed_with_warnings" if warnings else "passed",
        "issues": issues,
        "blockers": blockers,
        "warnings": warnings,
        "metrics": {
            "stop_vs_atr": round(initial_stop / max(atr14_pct, 1e-6), 4) if initial_stop > 0 else None,
            "expected_trade_interval_days": expected_trade_interval_days,
            "warmup_target_signals": warmup_target_signals or None,
            "expected_annual_signals": round(expected_annual_signals, 2),
            "volume_ratio_floor": round(volume_ratio_floor, 4) if volume_ratio_floor > 0 else None,
            "volume_ratio_p90": round(volume_ratio_p90, 4),
        },
    }


def _resolve_source_label(*labeled_values: tuple[str, Any]) -> str:
    for label, value in labeled_values:
        if isinstance(value, dict) and value:
            return label
        if isinstance(value, (list, tuple, set)) and value:
            return label
        if value not in (None, "", [], {}):
            return label
    return "default"


def _default_research_validation_contract_payload() -> dict[str, Any]:
    try:
        from .research_510300_v3 import build_default_research_validation_contract

        return dict(build_default_research_validation_contract() or {})
    except Exception:
        return {
            "contract_version": "strategy_factory.research_protocol.v2",
            "walk_forward_config": {"train_months": 60, "test_months": 12, "step_months": 12},
            "baseline_reference": {
                "name": "510300_baseline_reference",
                "baseline_slippage_bps": 5.0,
                "stress_slippage_bps": 10.0,
            },
            "cash_sleeve_policy": {
                "enabled": False,
                "schedule_clock": "prev_close_signal_next_open_execute_same_close_cash_rebuild",
            },
            "cost_sensitivity_grid": {"base_slippage_bps": 5.0, "stress_slippage_bps": 10.0},
            "capacity_execution": {"schedule_clock": "prev_close_signal_next_open_execute_same_close_cash_rebuild"},
            "multiple_testing": {
                "mode": "formal_runtime",
                "white_reality_check_enabled": True,
                "hansen_spa_enabled": True,
                "pbo_enabled": True,
            },
            "admission_thresholds": {
                "validation_profile": {
                    "profile": "trade_rule_validation",
                    "validation_focus": "target_plus_representative",
                    "primary_validation_layer": "target",
                }
            },
            "family_holding_bucket": {"family": "default", "holding_bucket": "medium"},
        }


def _classify_holding_bucket(holding_horizon: dict[str, Any]) -> str:
    max_days = _safe_int(dict(holding_horizon or {}).get("max_days"), 0)
    if max_days <= 5:
        return "short"
    if max_days <= 15:
        return "medium"
    return "long"


def _trade_plan_nodes_for_provenance(trade_plan: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def _append(node: Any, *, phase: str, index: int = 0) -> None:
        if not isinstance(node, dict):
            return
        node_id = str(
            node.get("node_id")
            or node.get("plan_node_id")
            or node.get("trade_plan_node_id")
            or node.get("trade_plan_step_id")
            or node.get("id")
            or f"{phase}_{index}"
        ).strip()
        claim_ids = [
            str(item).strip()
            for item in list(node.get("claim_ids") or [])
            if str(item).strip()
        ]
        nodes.append(
            {
                **node,
                "node_id": node_id,
                "phase": phase,
                "claim_ids": list(dict.fromkeys(claim_ids)),
            }
        )

    payload = dict(trade_plan or {})
    if isinstance(payload.get("entry"), dict):
        _append(payload.get("entry"), phase="entry")
    if isinstance(payload.get("exit"), dict):
        _append(payload.get("exit"), phase="exit")
    for phase_name in ("entries", "exits", "nodes", "steps"):
        for index, item in enumerate(list(payload.get(phase_name) or [])):
            resolved_phase = "entry" if phase_name == "entries" else "exit" if phase_name == "exits" else phase_name
            _append(item, phase=resolved_phase, index=index)
    if not nodes and payload:
        _append(payload, phase="node")
    return nodes


def _claim_ids_from_prediction_contract(prediction_contract: dict[str, Any]) -> list[str]:
    claim_ids: list[str] = []
    for item in list(dict(prediction_contract or {}).get("claims") or []):
        if not isinstance(item, dict):
            continue
        claim_id = str(item.get("claim_id") or item.get("id") or "").strip()
        if claim_id:
            claim_ids.append(claim_id)
    return list(dict.fromkeys(claim_ids))


def _trade_step_ids_from_trade_plan_to_dsl_map(trade_plan_to_dsl_map: dict[str, Any]) -> list[str]:
    step_ids: list[str] = []
    for key in (
        "trade_step_to_dsl_sections",
        "trade_step_to_claim_ids",
    ):
        payload = dict(trade_plan_to_dsl_map.get(key) or {})
        step_ids.extend(str(item).strip() for item in payload.keys() if str(item).strip())
    return list(dict.fromkeys(step_ids))


def _claim_ids_from_claim_map(claim_to_trade_plan_map: dict[str, Any]) -> list[str]:
    payload = dict(claim_to_trade_plan_map.get("claim_to_trade_step_ids") or {})
    return list(dict.fromkeys(str(item).strip() for item in payload.keys() if str(item).strip()))


def _enrich_runtime_playbook_provenance(
    runtime_playbook: dict[str, Any],
    *,
    strategy_type: str,
    prediction_contract: dict[str, Any],
    trade_plan: dict[str, Any],
    claim_to_trade_plan_map: dict[str, Any],
    trade_plan_to_dsl_map: dict[str, Any],
    source_priority: dict[str, str],
    runtime_playbook_source: str,
) -> dict[str, Any]:
    playbook = dict(runtime_playbook or {})
    existing_provenance = dict(playbook.get("_provenance") or {})
    trade_plan_nodes = _trade_plan_nodes_for_provenance(trade_plan)
    derived_claim_ids = list(
        dict.fromkeys(
            [
                *_claim_ids_from_prediction_contract(prediction_contract),
                *_claim_ids_from_claim_map(claim_to_trade_plan_map),
                *[
                    str(claim_id).strip()
                    for node in trade_plan_nodes
                    for claim_id in list(node.get("claim_ids") or [])
                    if str(claim_id).strip()
                ],
            ]
        )
    )
    derived_trade_step_ids = list(
        dict.fromkeys(
            [
                *[
                    str(node.get("node_id") or "").strip()
                    for node in trade_plan_nodes
                    if str(node.get("node_id") or "").strip()
                ],
                *_trade_step_ids_from_trade_plan_to_dsl_map(trade_plan_to_dsl_map),
            ]
        )
    )
    source_claim_ids = list(
        dict.fromkeys(
            [
                *[
                    str(item).strip()
                    for item in list(playbook.get("source_claim_ids") or [])
                    if str(item).strip()
                ],
                *[
                    str(item).strip()
                    for item in list(existing_provenance.get("source_claim_ids") or [])
                    if str(item).strip()
                ],
                *derived_claim_ids,
            ]
        )
    )
    source_trade_step_ids = list(
        dict.fromkeys(
            [
                *[
                    str(item).strip()
                    for item in list(playbook.get("source_trade_step_ids") or [])
                    if str(item).strip()
                ],
                *[
                    str(item).strip()
                    for item in list(existing_provenance.get("source_trade_step_ids") or [])
                    if str(item).strip()
                ],
                *derived_trade_step_ids,
            ]
        )
    )
    derived_from_defaults = bool(
        existing_provenance.get("derived_from_defaults")
        if existing_provenance.get("derived_from_defaults") is not None
        else playbook.get("derived_from_defaults")
        if playbook.get("derived_from_defaults") is not None
        else runtime_playbook_source == "default"
    )
    family_label = _runtime_playbook_family(strategy_type)
    derivation_labels = list(
        dict.fromkeys(
            [
                *[
                    str(item).strip()
                    for item in list(playbook.get("derivation_labels") or [])
                    if str(item).strip()
                ],
                *[
                    str(item).strip()
                    for item in list(existing_provenance.get("derivation_labels") or [])
                    if str(item).strip()
                ],
                "default_runtime_playbook" if derived_from_defaults else "runtime_playbook_provided",
                "trade_plan_driven" if source_trade_step_ids else "trade_plan_missing",
                "claim_linked" if source_claim_ids else "claim_mapping_missing",
                f"family_template:{family_label}",
            ]
        )
    )
    provenance = {
        **existing_provenance,
        "source_claim_ids": source_claim_ids,
        "source_trade_step_ids": source_trade_step_ids,
        "derived_from_defaults": derived_from_defaults,
        "derivation_labels": derivation_labels,
        "source_priority": dict(source_priority),
        "runtime_playbook_source": runtime_playbook_source,
    }
    return {
        **playbook,
        "source_claim_ids": source_claim_ids,
        "source_trade_step_ids": source_trade_step_ids,
        "derived_from_defaults": derived_from_defaults,
        "derivation_labels": derivation_labels,
        "_provenance": provenance,
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
        source_symbol_summary = _dict_value(
            metadata.get("source_symbol_summary"),
            source_candidate.get("source_symbol_summary"),
            research_task.get("source_symbol_summary"),
        )
        backtest_metrics = _dict_value(
            metadata.get("backtest_metrics"),
            source_candidate.get("backtest_metrics"),
            dict(self.params or {}).get("backtest_metrics"),
            source_candidate_params.get("backtest_metrics"),
        )
        task_source = _task_source(research_task, event_context)
        prediction_trace_id = normalize_prediction_trace_id(
            _scalar_value(
                metadata.get("prediction_trace_id"),
                source_candidate.get("prediction_trace_id"),
                dict(self.params or {}).get("prediction_trace_id"),
                source_candidate_params.get("prediction_trace_id"),
            ),
            _scalar_value(
                metadata.get("trace_id"),
                source_candidate.get("trace_id"),
                dict(self.params or {}).get("trace_id"),
                source_candidate_params.get("trace_id"),
            ),
            fallback=f"pred_{uuid4().hex[:12]}",
        )
        explicit_research_validation_contract = _dict_value(
            metadata.get("research_validation_contract"),
            source_candidate.get("research_validation_contract"),
            dict(self.params or {}).get("research_validation_contract"),
            source_candidate_params.get("research_validation_contract"),
        )
        research_validation_contract_source = _resolve_source_label(
            ("metadata", metadata.get("research_validation_contract")),
            ("source_candidate", source_candidate.get("research_validation_contract")),
            ("params", dict(self.params or {}).get("research_validation_contract")),
            ("source_candidate_params", source_candidate_params.get("research_validation_contract")),
        )
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
        evidence_chain = _dict_value(
            metadata.get("evidence_chain"),
            source_candidate.get("evidence_chain"),
            dict(self.params or {}).get("evidence_chain"),
            source_candidate_params.get("evidence_chain"),
        )
        prediction_contract = _dict_value(
            metadata.get("prediction_contract"),
            source_candidate.get("prediction_contract"),
            dict(self.params or {}).get("prediction_contract"),
            source_candidate_params.get("prediction_contract"),
        )
        confidence_contract = _dict_value(
            metadata.get("confidence_contract"),
            source_candidate.get("confidence_contract"),
            dict(self.params or {}).get("confidence_contract"),
            source_candidate_params.get("confidence_contract"),
        )
        evidence_alignment_audit = _dict_value(
            metadata.get("evidence_alignment_audit"),
            source_candidate.get("evidence_alignment_audit"),
            dict(self.params or {}).get("evidence_alignment_audit"),
            source_candidate_params.get("evidence_alignment_audit"),
        )
        market_facts = normalize_market_evidence_facts(
            metadata.get("market_facts"),
            source_candidate.get("market_facts"),
            dict(self.params or {}).get("market_facts"),
            source_candidate_params.get("market_facts"),
            evidence_chain.get("market_facts") if isinstance(evidence_chain, dict) else None,
        )
        if market_facts:
            evidence_chain = dict(evidence_chain or {})
            evidence_chain["market_facts"] = list(market_facts)
            evidence_alignment_audit = {
                **dict(evidence_alignment_audit or {}),
                **_build_market_fact_gate_audit(market_facts),
            }
        dsl_support_audit = _dict_value(
            metadata.get("dsl_support_audit"),
            source_candidate.get("dsl_support_audit"),
            dict(self.params or {}).get("dsl_support_audit"),
            source_candidate_params.get("dsl_support_audit"),
        )
        claim_to_trade_plan_map = _dict_value(
            metadata.get("claim_to_trade_plan_map"),
            source_candidate.get("claim_to_trade_plan_map"),
            dict(self.params or {}).get("claim_to_trade_plan_map"),
            source_candidate_params.get("claim_to_trade_plan_map"),
        )
        trade_plan_to_dsl_map = _dict_value(
            metadata.get("trade_plan_to_dsl_map"),
            source_candidate.get("trade_plan_to_dsl_map"),
            dict(self.params or {}).get("trade_plan_to_dsl_map"),
            source_candidate_params.get("trade_plan_to_dsl_map"),
        )
        explicit_dsl = _dict_value(
            metadata.get("dsl"),
            source_candidate.get("dsl"),
            dict(self.params or {}).get("dsl"),
            source_candidate_params.get("dsl"),
        )
        holding_horizon_source = _resolve_source_label(
            ("metadata", metadata.get("holding_horizon")),
            ("source_candidate", source_candidate.get("holding_horizon")),
            ("params", dict(self.params or {}).get("holding_horizon")),
            ("source_candidate_params", source_candidate_params.get("holding_horizon")),
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
        trade_plan_source = _resolve_source_label(
            ("metadata", metadata.get("trade_plan")),
            ("source_candidate", source_candidate.get("trade_plan")),
            ("params", dict(self.params or {}).get("trade_plan")),
            ("source_candidate_params", source_candidate_params.get("trade_plan")),
        )
        trade_plan = _dict_value(
            metadata.get("trade_plan"),
            source_candidate.get("trade_plan"),
            dict(self.params or {}).get("trade_plan"),
            source_candidate_params.get("trade_plan"),
        )
        if not trade_plan:
            trade_plan = _default_trade_plan(self.strategy_type, task_source)
        trade_plan = _ensure_trade_plan_execution_nodes(self.strategy_type, trade_plan)
        risk_rules_source = _resolve_source_label(
            ("metadata", metadata.get("risk_rules")),
            ("source_candidate", source_candidate.get("risk_rules")),
            ("params", dict(self.params or {}).get("risk_rules")),
            ("source_candidate_params", source_candidate_params.get("risk_rules")),
        )
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
        execution_assumptions_source = _resolve_source_label(
            ("metadata", metadata.get("execution_assumptions")),
            ("source_candidate", source_candidate.get("execution_assumptions")),
            ("params", dict(self.params or {}).get("execution_assumptions")),
            ("source_candidate_params", source_candidate_params.get("execution_assumptions")),
        )
        execution_assumptions = _dict_value(
            metadata.get("execution_assumptions"),
            source_candidate.get("execution_assumptions"),
            dict(self.params or {}).get("execution_assumptions"),
            source_candidate_params.get("execution_assumptions"),
        )
        if not execution_assumptions:
            execution_assumptions = _default_execution_assumptions(task_source)
        runtime_playbook_source = _resolve_source_label(
            ("metadata", metadata.get("runtime_playbook")),
            ("source_candidate", source_candidate.get("runtime_playbook")),
            ("params", dict(self.params or {}).get("runtime_playbook")),
            ("source_candidate_params", source_candidate_params.get("runtime_playbook")),
        )
        runtime_playbook = _dict_value(
            metadata.get("runtime_playbook"),
            source_candidate.get("runtime_playbook"),
            dict(self.params or {}).get("runtime_playbook"),
            source_candidate_params.get("runtime_playbook"),
        )
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
        capacity_assumption_source = _resolve_source_label(
            ("metadata", metadata.get("capacity_assumption")),
            ("source_candidate", source_candidate.get("capacity_assumption")),
            ("hypothesis_artifact", hypothesis_artifact.get("capacity_assumption")),
        )
        cost_sensitivity_grid = _dict_value(
            metadata.get("cost_sensitivity_grid"),
            source_candidate.get("cost_sensitivity_grid"),
            hypothesis_artifact.get("cost_sensitivity_grid"),
        )
        cost_sensitivity_grid_source = _resolve_source_label(
            ("metadata", metadata.get("cost_sensitivity_grid")),
            ("source_candidate", source_candidate.get("cost_sensitivity_grid")),
            ("hypothesis_artifact", hypothesis_artifact.get("cost_sensitivity_grid")),
        )
        instrument_profile = _normalize_instrument_profile(
            _dict_value(
                metadata.get("instrument_profile"),
                source_candidate.get("instrument_profile"),
                dict(self.params or {}).get("instrument_profile"),
                source_candidate_params.get("instrument_profile"),
                research_task.get("instrument_profile"),
            ),
            target_symbols=list(target_symbols),
            source_symbol_summary=source_symbol_summary,
        )
        execution_semantic_contract = _resolve_execution_semantic_contract(
            strategy_type=self.strategy_type,
            params={**dict(self.params or {}), "target_symbols": list(target_symbols)},
            target_symbols=list(target_symbols),
            trade_plan=trade_plan,
            holding_horizon=holding_horizon,
            risk_rules=risk_rules,
            position_sizing=position_sizing,
            stock_pool=stock_pool,
            prediction_contract=prediction_contract,
            instrument_profile=instrument_profile,
            explicit_dsl=explicit_dsl,
            existing_claim_to_trade_plan_map=claim_to_trade_plan_map,
            existing_trade_plan_to_dsl_map=trade_plan_to_dsl_map,
            existing_dsl_support_audit=dsl_support_audit,
        )
        if execution_semantic_contract.get("dsl_support_audit"):
            dsl_support_audit = dict(execution_semantic_contract.get("dsl_support_audit") or {})
        if execution_semantic_contract.get("claim_to_trade_plan_map"):
            claim_to_trade_plan_map = dict(execution_semantic_contract.get("claim_to_trade_plan_map") or {})
        if execution_semantic_contract.get("trade_plan_to_dsl_map"):
            trade_plan_to_dsl_map = dict(execution_semantic_contract.get("trade_plan_to_dsl_map") or {})
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
        if not runtime_playbook:
            runtime_playbook = _default_runtime_playbook(
                self.strategy_type,
                holding_horizon=holding_horizon,
                trade_plan=trade_plan,
                risk_rules=risk_rules,
                portfolio_spec=portfolio_spec,
                execution_assumptions=execution_assumptions,
                instrument_profile=instrument_profile,
                backtest_metrics=backtest_metrics,
            )
        runtime_playbook = _enrich_runtime_playbook_provenance(
            runtime_playbook,
            strategy_type=self.strategy_type,
            prediction_contract=prediction_contract,
            trade_plan=trade_plan,
            claim_to_trade_plan_map=claim_to_trade_plan_map,
            trade_plan_to_dsl_map=trade_plan_to_dsl_map,
            source_priority={
                "holding_horizon": holding_horizon_source,
                "trade_plan": trade_plan_source,
                "risk_rules": risk_rules_source,
                "execution_assumptions": execution_assumptions_source,
                "runtime_playbook": runtime_playbook_source,
            },
            runtime_playbook_source=runtime_playbook_source,
        )
        regime_filter_contract = _dict_value(
            metadata.get("regime_filter_contract"),
            source_candidate.get("regime_filter_contract"),
            dict(self.params or {}).get("regime_filter_contract"),
            source_candidate_params.get("regime_filter_contract"),
        )
        if not regime_filter_contract:
            regime_filter_contract = _build_regime_filter_contract(
                self.strategy_type,
                market_regime_assumption=market_regime_assumption,
                instrument_profile=instrument_profile,
                runtime_playbook=runtime_playbook,
            )
        drawdown_invalidation_contract = _dict_value(
            metadata.get("drawdown_invalidation_contract"),
            source_candidate.get("drawdown_invalidation_contract"),
            dict(self.params or {}).get("drawdown_invalidation_contract"),
            source_candidate_params.get("drawdown_invalidation_contract"),
        )
        if not drawdown_invalidation_contract:
            drawdown_invalidation_contract = _build_drawdown_invalidation_contract(
                self.strategy_type,
                instrument_profile=instrument_profile,
                runtime_playbook=runtime_playbook,
                target_symbols=list(target_symbols),
            )
        thesis_invalidation_contract = _dict_value(
            metadata.get("thesis_invalidation_contract"),
            source_candidate.get("thesis_invalidation_contract"),
            dict(self.params or {}).get("thesis_invalidation_contract"),
            source_candidate_params.get("thesis_invalidation_contract"),
        )
        if not thesis_invalidation_contract:
            thesis_invalidation_contract = _build_thesis_invalidation_contract(
                self.strategy_type,
                trade_plan=trade_plan,
                runtime_playbook=runtime_playbook,
                instrument_profile=instrument_profile,
                drawdown_invalidation_contract=drawdown_invalidation_contract,
            )
        parameter_coherence_audit = _dict_value(
            metadata.get("parameter_coherence_audit"),
            source_candidate.get("parameter_coherence_audit"),
            dict(self.params or {}).get("parameter_coherence_audit"),
            source_candidate_params.get("parameter_coherence_audit"),
        )
        if not parameter_coherence_audit:
            parameter_coherence_audit = _build_parameter_coherence_audit(
                self.strategy_type,
                holding_horizon=holding_horizon,
                rebalance_rule=rebalance_rule,
                runtime_playbook=runtime_playbook,
                instrument_profile=instrument_profile,
                backtest_metrics=backtest_metrics,
            )
        runtime_semantic_diagnostics = _resolve_runtime_semantic_diagnostics(
            strategy_type=self.strategy_type,
            params={**dict(self.params or {}), "runtime_playbook": runtime_playbook},
            target_symbols=list(target_symbols),
            instrument_profile=instrument_profile,
            runtime_playbook=runtime_playbook,
            evidence_chain=evidence_chain,
            prediction_contract=prediction_contract,
            confidence_contract=confidence_contract,
            execution_semantic_contract=execution_semantic_contract,
        )
        execution_semantic_gap_reasons = list(
            dict.fromkeys(
                [
                    *list(execution_semantic_contract.get("execution_semantic_gap_reasons") or []),
                    *list(runtime_semantic_diagnostics.get("execution_semantic_gap_reasons") or []),
                ]
            )
        )
        default_research_validation_contract = _default_research_validation_contract_payload()
        holding_bucket = _classify_holding_bucket(holding_horizon)
        capacity_execution_contract = (
            explicit_research_validation_contract.get("capacity_execution")
            or {
                **dict(capacity_assumption or {}),
                "capacity_bucket": capacity_bucket,
                "position_model": position_model,
                "max_position_pct": portfolio_spec.get("max_position_pct"),
                "market_impact_bps": execution_assumptions.get("market_impact_bps"),
                "slippage_bps": execution_assumptions.get("slippage_bps"),
                "commission_rate": execution_assumptions.get("commission_rate"),
                "tradability_filter": execution_assumptions.get("tradability_filter"),
            }
        )
        family_holding_bucket_contract = (
            explicit_research_validation_contract.get("family_holding_bucket")
            or {
                "family": family_specialization.get("family")
                or family_specialization.get("family_id")
                or self.strategy_type,
                "holding_bucket": holding_bucket,
                "expected_turnover_band": expected_turnover_band,
            }
        )
        effective_research_sections = {
            "walk_forward_config": dict(explicit_research_validation_contract.get("walk_forward_config") or {}),
            "baseline_reference": dict(explicit_research_validation_contract.get("baseline_reference") or {}),
            "cash_sleeve_policy": dict(explicit_research_validation_contract.get("cash_sleeve_policy") or {}),
            "cost_sensitivity_grid": dict(
                explicit_research_validation_contract.get("cost_sensitivity_grid")
                or dict(cost_sensitivity_grid)
                or {}
            ),
            "capacity_execution": dict(capacity_execution_contract or {}),
            "multiple_testing": dict(explicit_research_validation_contract.get("multiple_testing") or {}),
            "admission_thresholds": dict(explicit_research_validation_contract.get("admission_thresholds") or {}),
            "family_holding_bucket": dict(family_holding_bucket_contract or {}),
        }
        research_field_provenance = {
            "walk_forward_config": normalize_field_provenance_token(
                research_validation_contract_source
                if effective_research_sections["walk_forward_config"]
                else "missing"
            ),
            "baseline_reference": normalize_field_provenance_token(
                research_validation_contract_source
                if effective_research_sections["baseline_reference"]
                else "missing"
            ),
            "cash_sleeve_policy": normalize_field_provenance_token(
                research_validation_contract_source
                if effective_research_sections["cash_sleeve_policy"]
                else "missing"
            ),
            "cost_sensitivity_grid": normalize_field_provenance_token(
                research_validation_contract_source
                if explicit_research_validation_contract.get("cost_sensitivity_grid")
                else cost_sensitivity_grid_source
                if effective_research_sections["cost_sensitivity_grid"]
                else "missing"
            ),
            "capacity_execution": normalize_field_provenance_token(
                research_validation_contract_source
                if explicit_research_validation_contract.get("capacity_execution")
                else capacity_assumption_source
                if effective_research_sections["capacity_execution"]
                else "missing"
            ),
            "multiple_testing": normalize_field_provenance_token(
                research_validation_contract_source
                if effective_research_sections["multiple_testing"]
                else "missing"
            ),
            "admission_thresholds": normalize_field_provenance_token(
                research_validation_contract_source
                if effective_research_sections["admission_thresholds"]
                else "missing"
            ),
            "family_holding_bucket": normalize_field_provenance_token(
                research_validation_contract_source
                if explicit_research_validation_contract.get("family_holding_bucket")
                else "derived"
                if effective_research_sections["family_holding_bucket"]
                else "missing"
            ),
        }
        recommended_defaults = {
            field_name: dict(default_research_validation_contract.get(field_name) or {})
            for field_name in effective_research_sections
            if not effective_research_sections.get(field_name)
            and dict(default_research_validation_contract.get(field_name) or {})
        }
        research_contract_hard_failures: list[dict[str, Any]] = []
        for field_name in list(runtime_semantic_diagnostics.get("semantic_contract_missing_fields") or []):
            token = str(field_name or "").strip()
            if token:
                research_contract_hard_failures.append(
                    {
                        "field": token,
                        "issue": "semantic_contract_missing_field",
                        "reason_code": f"semantic_contract_missing:{token}",
                        "detail": "runtime semantic contract is not executable without this field",
                    }
                )
        for reason_code in execution_semantic_gap_reasons:
            token = str(reason_code or "").strip()
            if token:
                research_contract_hard_failures.append(
                    {
                        "issue": "execution_semantic_gap",
                        "reason_code": token,
                    }
                )
        research_validation_contract = build_research_validation_contract(
            walk_forward_config=effective_research_sections.get("walk_forward_config"),
            baseline_reference=effective_research_sections.get("baseline_reference"),
            cash_sleeve_policy=effective_research_sections.get("cash_sleeve_policy"),
            cost_sensitivity_grid=effective_research_sections.get("cost_sensitivity_grid"),
            capacity_execution=effective_research_sections.get("capacity_execution"),
            multiple_testing=effective_research_sections.get("multiple_testing"),
            admission_thresholds=effective_research_sections.get("admission_thresholds"),
            family_holding_bucket=effective_research_sections.get("family_holding_bucket"),
            field_provenance=research_field_provenance,
            recommended_defaults=recommended_defaults,
            hard_failures=research_contract_hard_failures,
        )
        research_protocol_version = str(
            research_validation_contract.get("contract_version")
            or default_research_validation_contract.get("contract_version")
            or "strategy_factory.research_protocol.v2"
        ).strip() or "strategy_factory.research_protocol.v2"
        candidate_contract_version = CANDIDATE_CONTRACT_V2
        field_provenance = dict(research_validation_contract.get("field_provenance") or {})
        field_provenance_summary = dict(research_validation_contract.get("field_provenance_summary") or {})
        spec_completeness = str(research_validation_contract.get("spec_completeness") or "complete").strip() or "complete"
        completion_issues = list(research_validation_contract.get("completion_issues") or [])
        research_hard_failures = list(research_validation_contract.get("hard_failures") or [])
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
            "runtime_playbook": dict(runtime_playbook),
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
            "instrument_profile": dict(instrument_profile),
            "regime_filter_contract": dict(regime_filter_contract),
            "parameter_coherence_audit": dict(parameter_coherence_audit),
            "thesis_invalidation_contract": dict(thesis_invalidation_contract),
            "drawdown_invalidation_contract": dict(drawdown_invalidation_contract),
            "position_sizing_rationale": position_sizing_rationale,
            "capacity_bucket": capacity_bucket,
            "turnover_cost_class": execution_assumptions.get("turnover_cost_class"),
            "expected_turnover_band": expected_turnover_band,
            "family_specialization": dict(family_specialization),
            "execution_semantic_mode": execution_semantic_contract.get("execution_semantic_mode"),
            "execution_semantic_gap": bool(execution_semantic_contract.get("execution_semantic_gap") or execution_semantic_gap_reasons),
            "execution_semantic_gap_reasons": execution_semantic_gap_reasons,
            "dsl_required": bool(execution_semantic_contract.get("dsl_required")),
            "dsl_compiled": bool(execution_semantic_contract.get("dsl_compiled")),
            "dsl_compile_failure_reasons": list(execution_semantic_contract.get("dsl_compile_failure_reasons") or []),
            "semantic_runtime_match": bool(runtime_semantic_diagnostics.get("semantic_runtime_match")),
            "runtime_family_data_source": runtime_semantic_diagnostics.get("runtime_family_data_source"),
            "proxy_runtime_used": bool(runtime_semantic_diagnostics.get("proxy_runtime_used")),
            "diagnostic_only": bool(runtime_semantic_diagnostics.get("diagnostic_only")),
            "execution_readiness_tier": runtime_semantic_diagnostics.get("execution_readiness_tier"),
            "semantic_contract_missing_fields": list(runtime_semantic_diagnostics.get("semantic_contract_missing_fields") or []),
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
            "prediction_trace_id": prediction_trace_id,
            "trace_id": prediction_trace_id,
            "research_validation_contract": dict(research_validation_contract),
            "research_protocol_version": research_protocol_version,
            "candidate_contract_version": candidate_contract_version,
            "field_provenance": dict(field_provenance),
            "field_provenance_summary": dict(field_provenance_summary),
            "spec_completeness": spec_completeness,
            "completion_issues": list(completion_issues),
            "hard_failures": list(research_hard_failures),
        }
        if market_facts:
            candidate_params["market_facts"] = list(market_facts)
        if backtest_metrics:
            candidate_params["backtest_metrics"] = dict(backtest_metrics)
        if source_symbol_summary:
            candidate_params["source_symbol_summary"] = dict(source_symbol_summary)
        if execution_semantic_contract.get("dsl"):
            candidate_params["dsl"] = dict(execution_semantic_contract.get("dsl") or {})
        for field_name, field_value in (
            ("evidence_chain", evidence_chain),
            ("prediction_contract", prediction_contract),
            ("confidence_contract", confidence_contract),
            ("evidence_alignment_audit", evidence_alignment_audit),
            ("dsl_support_audit", dsl_support_audit),
            ("claim_to_trade_plan_map", claim_to_trade_plan_map),
            ("trade_plan_to_dsl_map", trade_plan_to_dsl_map),
        ):
            if field_value:
                candidate_params[field_name] = dict(field_value)
        for field_name in ("legacy_semantic_contract", "contradiction_count", "proxy_dependency_score"):
            field_value = _scalar_value(
                metadata.get(field_name),
                source_candidate.get(field_name),
                dict(self.params or {}).get(field_name),
                source_candidate_params.get(field_name),
            )
            if field_value not in (None, "", [], {}):
                candidate_params[field_name] = field_value
        candidate_payload = {
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
            'runtime_playbook': dict(runtime_playbook),
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
            'instrument_profile': dict(instrument_profile),
            'regime_filter_contract': dict(regime_filter_contract),
            'parameter_coherence_audit': dict(parameter_coherence_audit),
            'thesis_invalidation_contract': dict(thesis_invalidation_contract),
            'drawdown_invalidation_contract': dict(drawdown_invalidation_contract),
            'position_sizing_rationale': position_sizing_rationale,
            'capacity_bucket': capacity_bucket,
            'turnover_cost_class': execution_assumptions.get('turnover_cost_class'),
            'expected_turnover_band': expected_turnover_band,
            'family_specialization': dict(family_specialization),
            'execution_semantic_mode': execution_semantic_contract.get('execution_semantic_mode'),
            'execution_semantic_gap': bool(execution_semantic_contract.get('execution_semantic_gap') or execution_semantic_gap_reasons),
            'execution_semantic_gap_reasons': execution_semantic_gap_reasons,
            'dsl_required': bool(execution_semantic_contract.get('dsl_required')),
            'dsl_compiled': bool(execution_semantic_contract.get('dsl_compiled')),
            'dsl_compile_failure_reasons': list(execution_semantic_contract.get('dsl_compile_failure_reasons') or []),
            'semantic_runtime_match': bool(runtime_semantic_diagnostics.get('semantic_runtime_match')),
            'runtime_family_data_source': runtime_semantic_diagnostics.get('runtime_family_data_source'),
            'proxy_runtime_used': bool(runtime_semantic_diagnostics.get('proxy_runtime_used')),
            'diagnostic_only': bool(runtime_semantic_diagnostics.get('diagnostic_only')),
            'execution_readiness_tier': runtime_semantic_diagnostics.get('execution_readiness_tier'),
            'semantic_contract_missing_fields': list(runtime_semantic_diagnostics.get('semantic_contract_missing_fields') or []),
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
            'source_symbol_summary': dict(source_symbol_summary),
            'task_run_id': _scalar_value(metadata.get('task_run_id'), source_candidate.get('task_run_id')),
            'parent_strategy_id': _scalar_value(metadata.get('parent_strategy_id'), source_candidate.get('parent_strategy_id')),
            'pipeline_provenance': _dict_value(metadata.get('pipeline_provenance')),
            'experiment_id': experiment_id,
            'prediction_trace_id': prediction_trace_id,
            'trace_id': prediction_trace_id,
            'research_validation_contract': dict(research_validation_contract),
            'research_protocol_version': research_protocol_version,
            'candidate_contract_version': candidate_contract_version,
            'field_provenance': dict(field_provenance),
            'field_provenance_summary': dict(field_provenance_summary),
            'spec_completeness': spec_completeness,
            'completion_issues': list(completion_issues),
            'hard_failures': list(research_hard_failures),
            'tags': list(dict.fromkeys(['ai_generated', source, self.strategy_type, *(self.tags or [])])),
        }
        if backtest_metrics:
            candidate_payload['backtest_metrics'] = dict(backtest_metrics)
        if execution_semantic_contract.get("dsl"):
            candidate_payload["dsl"] = dict(execution_semantic_contract.get("dsl") or {})
        for field_name in (
            "evidence_chain",
            "prediction_contract",
            "confidence_contract",
            "evidence_alignment_audit",
            "dsl_support_audit",
            "claim_to_trade_plan_map",
            "trade_plan_to_dsl_map",
        ):
            if isinstance(candidate_params.get(field_name), dict) and candidate_params.get(field_name):
                candidate_payload[field_name] = dict(candidate_params.get(field_name) or {})
        for field_name in ("legacy_semantic_contract", "contradiction_count", "proxy_dependency_score"):
            if candidate_params.get(field_name) not in (None, "", [], {}):
                candidate_payload[field_name] = candidate_params.get(field_name)
        return candidate_payload
