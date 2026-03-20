"""Quant context builder for unified decision."""

from __future__ import annotations

from typing import Any

from ..storage import get_db
from ..tools.factor_profile import _FACTOR_REGISTRY, _OVERSOLD_SIGNAL_MAP, _build_factor_profile
from ..services.data_pipeline import compute_signal_hit_rate, normalize_klines
from ..utils import now_iso, resolve_security_code


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


async def build_quant_context(
    code: str,
    *,
    factors: tuple[str, ...] = ("rsi", "macd", "momentum"),
    lookback_days: int = 250,
) -> dict[str, Any]:
    """Build a compact quant-evidence bundle used by the unified decision pipeline."""
    normalized_code = resolve_security_code(code)
    if not normalized_code:
        raise ValueError("需要提供股票代码")

    db = get_db()
    klines = await db.get_klines(normalized_code, limit=max(int(lookback_days), 250))
    if not klines or len(klines) < 30:
        raise RuntimeError("K 线数据不足，无法构建量化上下文")

    ordered = normalize_klines(klines)
    closes = [float(item.get("close", 0) or 0) for item in ordered if item.get("close") is not None]
    warnings: list[str] = []
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
    rsi_current = _safe_float(rsi_profile.get("current"))
    if rsi_current is not None:
        if rsi_current <= 32:
            score += 8.0
            reasons.append(f"RSI 处于低位({rsi_current:.1f})，存在均值回归空间")
        elif rsi_current >= 72:
            score -= 8.0
            risks.append(f"RSI 偏高({rsi_current:.1f})，短线追高风险上升")

    macd_profile = result_factors.get("macd", {})
    macd_current = _safe_float(macd_profile.get("current"))
    if macd_current is not None:
        if macd_current > 0:
            score += 10.0
            reasons.append("MACD 位于零轴上方，趋势延续信号偏正面")
        elif macd_current < 0:
            score -= 8.0
            risks.append("MACD 位于零轴下方，趋势确认仍偏弱")

    momentum_profile = result_factors.get("momentum", {})
    momentum_current = _safe_float(momentum_profile.get("current"))
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
            win_rate = _safe_float(forward_10d.get("win_rate"))
            mean_return = _safe_float(forward_10d.get("mean"))
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

    score = round(_clamp(score, 0.0, 100.0), 2)
    return {
        "code": normalized_code,
        "score": score,
        "factors": result_factors,
        "signal_stats": signal_stats,
        "reasons": reasons,
        "risks": risks,
        "warnings": warnings,
        "source_chain": [
            "decision_quant_builder",
            "db.get_klines",
            "factor_profile._FACTOR_REGISTRY",
            "data_pipeline.compute_signal_hit_rate",
        ],
        "timestamp": now_iso(),
    }
