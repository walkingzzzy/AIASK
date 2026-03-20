"""Quant context builder for unified decision."""

from __future__ import annotations

from typing import Any

from ..services.conditional_returns import calculate_conditional_returns
from ..services.data_pipeline import compute_signal_hit_rate, normalize_klines
from ..storage import get_db
from ..tools.factor_profile import (
    _FACTOR_REGISTRY,
    _OVERSOLD_SIGNAL_MAP,
    _build_factor_profile,
    _fetch_peer_codes,
)
from ..tools.quant import _build_similar_pattern_report
from ..tools.quant_analysis import run_factor_oos_validation
from ..utils import resolve_security_code
from .decision_pipeline_shared import build_context_meta, clamp, safe_float


def _pick_period_stat(container: dict[str, Any] | None, period: int) -> dict[str, Any]:
    if not isinstance(container, dict):
        return {}
    data = container.get(f"{period}d")
    return dict(data) if isinstance(data, dict) else {}


def _blended_probability(
    *,
    period: int,
    signal_stats: dict[str, Any] | None,
    conditional_returns: dict[str, Any] | None,
    similar_patterns: dict[str, Any] | None,
    rsi_current: float | None,
    macd_current: float | None,
    momentum_current: float | None,
) -> dict[str, Any]:
    signal = _pick_period_stat((signal_stats or {}).get("forward_returns", {}), period)
    conditional = _pick_period_stat((conditional_returns or {}).get("forward_returns", {}), period)
    similar = _pick_period_stat((similar_patterns or {}).get("aggregate_prediction", {}), period)

    components: list[tuple[str, float]] = []
    for label, payload in (
        ("signal", safe_float(signal.get("hit_rate"))),
        ("conditional", safe_float(conditional.get("win_rate"))),
        ("similar", safe_float(similar.get("hit_rate"))),
    ):
        if payload is not None:
            components.append((label, payload))

    heuristic = 0.5
    if rsi_current is not None:
        heuristic += 0.08 if rsi_current <= 32 else (-0.06 if rsi_current >= 72 else 0.0)
    if macd_current is not None:
        heuristic += 0.06 if macd_current > 0 else (-0.04 if macd_current < 0 else 0.0)
    if momentum_current is not None:
        heuristic += 0.08 if momentum_current > 0 else (-0.08 if momentum_current < 0 else 0.0)
    components.append(("heuristic", clamp(heuristic, 0.2, 0.8)))

    weights = {"signal": 0.35, "conditional": 0.30, "similar": 0.20, "heuristic": 0.15}
    numerator = sum(value * weights.get(label, 0.0) for label, value in components)
    denominator = sum(weights.get(label, 0.0) for label, _ in components)
    probability = clamp(numerator / denominator if denominator > 0 else 0.5, 0.05, 0.95)

    expected_return = safe_float(signal.get("avg_return"))
    if expected_return is None:
        expected_return = safe_float(conditional.get("mean"))
    if expected_return is None:
        expected_return = safe_float(similar.get("avg_return"))

    return {
        "up_probability": round(probability, 4),
        "expected_return": round(expected_return, 4) if expected_return is not None else None,
        "sources": [label for label, _ in components],
        "sample_hint": int(
            max(
                safe_float(signal.get("samples")) or 0,
                safe_float(conditional.get("count")) or 0,
                safe_float(similar.get("samples")) or 0,
            )
        ),
    }


def _quality_label(sample_size: int, stability_ratio: float | None, warnings: list[str]) -> str:
    if sample_size >= 100 and (stability_ratio or 0.0) >= 0.6 and not warnings:
        return "high"
    if sample_size >= 40 and (stability_ratio or 0.0) >= 0.35:
        return "medium"
    return "low"


async def build_quant_context(
    code: str,
    *,
    factors: tuple[str, ...] = ("rsi", "macd", "momentum"),
    lookback_days: int = 250,
) -> dict[str, Any]:
    """Build a quant evidence bundle used by the unified decision pipeline."""
    normalized_code = resolve_security_code(code)
    if not normalized_code:
        raise ValueError("需要提供股票代码")

    db = get_db()
    klines = await db.get_klines(normalized_code, limit=max(int(lookback_days), 260))
    if not klines or len(klines) < 30:
        raise RuntimeError("K 线数据不足，无法构建量化上下文")

    ordered = normalize_klines(klines)
    closes = [float(item.get("close", 0) or 0) for item in ordered if item.get("close") is not None]
    warnings: list[str] = []
    fallback_reasons: list[str] = []
    source_chain = [
        "decision_quant_builder",
        "db.get_klines",
        "factor_profile._FACTOR_REGISTRY",
        "data_pipeline.compute_signal_hit_rate",
    ]
    result_factors: dict[str, Any] = {}
    reasons: list[str] = []
    risks: list[str] = []
    score = 50.0

    for factor_name in factors:
        compute_fn = _FACTOR_REGISTRY.get(factor_name)
        if compute_fn is None:
            warnings.append(f"unsupported_factor:{factor_name}")
            continue
        try:
            series = compute_fn(closes)
            profile = _build_factor_profile(series, len(closes))
            result_factors[factor_name] = profile
        except Exception as exc:
            warnings.append(f"{factor_name}:{exc}")

    rsi_profile = result_factors.get("rsi", {})
    rsi_current = safe_float(rsi_profile.get("current"))
    if rsi_current is not None:
        if rsi_current <= 32:
            score += 8.0
            reasons.append(f"RSI 处于低位({rsi_current:.1f})，存在均值回归空间")
        elif rsi_current >= 72:
            score -= 8.0
            risks.append(f"RSI 偏高({rsi_current:.1f})，短线追高风险上升")

    macd_profile = result_factors.get("macd", {})
    macd_current = safe_float(macd_profile.get("current"))
    if macd_current is not None:
        if macd_current > 0:
            score += 10.0
            reasons.append("MACD 位于零轴上方，趋势延续信号偏正面")
        elif macd_current < 0:
            score -= 8.0
            risks.append("MACD 位于零轴下方，趋势确认仍偏弱")

    momentum_profile = result_factors.get("momentum", {})
    momentum_current = safe_float(momentum_profile.get("current"))
    if momentum_current is not None:
        if momentum_current > 0:
            score += 12.0
            reasons.append(f"20 日动量为正({momentum_current:.3f})")
        elif momentum_current < 0:
            score -= 12.0
            risks.append(f"20 日动量为负({momentum_current:.3f})")

    signal_stats = None
    signal_meta = _OVERSOLD_SIGNAL_MAP.get("rsi")
    if signal_meta:
        try:
            signal_stats = compute_signal_hit_rate(
                ordered,
                signal=signal_meta["signal"],
                forward_days=[5, 10, 20],
                signal_params=signal_meta["signal_params"],
            )
            result_factors.setdefault("rsi", {})["historical_oversold_recovery"] = signal_stats
            forward_10d = (signal_stats.get("forward_returns") or {}).get("10d", {})
            win_rate = safe_float(forward_10d.get("hit_rate"))
            mean_return = safe_float(forward_10d.get("avg_return"))
            if win_rate is not None:
                if win_rate >= 0.55:
                    score += 8.0
                    reasons.append(f"历史 RSI 超卖后 10 日胜率较高({win_rate:.0%})")
                elif win_rate <= 0.45:
                    score -= 8.0
                    risks.append(f"历史 RSI 超卖后 10 日胜率一般({win_rate:.0%})")
            if mean_return is not None and mean_return > 0:
                score += 4.0
        except Exception as exc:
            warnings.append(f"signal_hit_rate:{exc}")

    conditional_returns = None
    try:
        conditional_returns = calculate_conditional_returns(
            ordered,
            conditions=[
                {"field": "rsi_14", "op": "<=", "value": 35},
                {"field": "volume_ratio", "op": ">=", "value": 0.9},
            ],
            forward_days=[1, 3, 5, 10, 20],
            logic="AND",
        )
        source_chain.append("services.conditional_returns")
        forward_5d = (conditional_returns.get("forward_returns") or {}).get("5d", {})
        condition_win_rate = safe_float(forward_5d.get("win_rate"))
        if condition_win_rate is not None:
            if condition_win_rate >= 0.58:
                score += 5.0
                reasons.append(f"条件收益统计显示 5 日胜率偏高({condition_win_rate:.0%})")
            elif condition_win_rate <= 0.42:
                score -= 5.0
                risks.append(f"条件收益统计显示 5 日胜率偏低({condition_win_rate:.0%})")
    except Exception as exc:
        warnings.append(f"conditional_returns:{exc}")
        fallback_reasons.append(f"conditional_returns:{exc}")

    similar_patterns = None
    try:
        similar_patterns = _build_similar_pattern_report(
            ordered,
            window_days=20,
            top_n=6,
            forward_days=[5, 10, 20],
        )
        source_chain.append("quant._build_similar_pattern_report")
        similar_10d = (similar_patterns.get("aggregate_prediction") or {}).get("10d", {})
        similar_hit_rate = safe_float(similar_10d.get("hit_rate"))
        if similar_hit_rate is not None:
            if similar_hit_rate >= 0.60:
                score += 4.0
                reasons.append(f"历史相似形态 10 日命中率较高({similar_hit_rate:.0%})")
            elif similar_hit_rate <= 0.40:
                score -= 4.0
                risks.append(f"历史相似形态 10 日表现偏弱({similar_hit_rate:.0%})")
    except Exception as exc:
        warnings.append(f"similar_patterns:{exc}")
        fallback_reasons.append(f"similar_patterns:{exc}")

    oos_validation = None
    try:
        industry = ""
        stock_info = await db.get_stock_info(normalized_code)
        if isinstance(stock_info, dict):
            industry = str(stock_info.get("industry") or "")
        peer_codes, market_codes = await _fetch_peer_codes(db, normalized_code, industry)
        candidate_codes = [normalized_code, *peer_codes[:8], *market_codes[:4]]
        candidate_codes = list(dict.fromkeys(code for code in candidate_codes if code))
        if len(candidate_codes) >= 3:
            validation_resp = await run_factor_oos_validation(
                candidate_codes[:12],
                "momentum",
                factor_lookback=20,
                forward_period=10,
                panel_periods=120,
                wf_train_window=50,
                wf_test_window=20,
                bootstrap_n=300,
                bootstrap_confidence=0.9,
                validation_parallel=False,
                bootstrap_mode="fast",
                include_perf_breakdown=False,
            )
            if validation_resp.get("success"):
                oos_validation = dict(validation_resp.get("data") or {})
                source_chain.append("quant.run_factor_oos_validation")
            else:
                raise RuntimeError(str(validation_resp.get("error") or "oos_validation_failed"))
        else:
            fallback_reasons.append("oos_validation:peer_codes_insufficient")
            warnings.append("oos_validation:peer_codes_insufficient")
    except Exception as exc:
        warnings.append(f"oos_validation:{exc}")
        fallback_reasons.append(f"oos_validation:{exc}")

    probability_targets = {
        f"{period}d": _blended_probability(
            period=period,
            signal_stats=signal_stats,
            conditional_returns=conditional_returns,
            similar_patterns=similar_patterns,
            rsi_current=rsi_current,
            macd_current=macd_current,
            momentum_current=momentum_current,
        )
        for period in (1, 3, 5, 10, 20)
    }

    walk_forward = ((oos_validation or {}).get("validation_report") or {}).get("walk_forward", {})
    bootstrap_ci = ((oos_validation or {}).get("validation_report") or {}).get("bootstrap_ci", {})
    similar_match_count = len((similar_patterns or {}).get("matches") or [])
    sample_size = max(
        int((signal_stats or {}).get("sample_count") or 0),
        int((conditional_returns or {}).get("condition_matches") or 0),
        similar_match_count,
        int((bootstrap_ci or {}).get("sample_size") or 0),
    )
    stability_ratio = safe_float(walk_forward.get("stability_ratio"))
    confidence_meta = {
        "sample_size": sample_size,
        "stability_ratio": round(stability_ratio, 4) if stability_ratio is not None else None,
        "oos_rank_ic_mean": safe_float(walk_forward.get("oos_rank_ic_mean")),
        "ci_bounds": {
            "lower": safe_float(bootstrap_ci.get("ci_lower")),
            "upper": safe_float(bootstrap_ci.get("ci_upper")),
        },
        "quality": _quality_label(sample_size, stability_ratio, warnings),
        "warning_count": len(warnings),
    }

    score = round(clamp(score, 0.0, 100.0), 2)
    missing_fields = []
    if not conditional_returns:
        missing_fields.append("conditional_returns")
    if not similar_patterns:
        missing_fields.append("similar_patterns")
    if not oos_validation:
        missing_fields.append("oos_validation")

    meta = build_context_meta(
        source="quant_context",
        source_chain=source_chain,
        asof_value=(ordered[-1] or {}).get("date"),
        warnings=warnings,
        fallback_reason=fallback_reasons,
        missing_fields=missing_fields,
        degraded=bool(warnings or missing_fields),
        cached=False,
    )
    return {
        "code": normalized_code,
        "score": score,
        "factors": result_factors,
        "signal_stats": signal_stats,
        "conditional_returns": conditional_returns,
        "similar_patterns": similar_patterns,
        "oos_validation": oos_validation,
        "probability_targets": probability_targets,
        "confidence_meta": confidence_meta,
        "reasons": reasons,
        "risks": risks,
        **meta,
    }
