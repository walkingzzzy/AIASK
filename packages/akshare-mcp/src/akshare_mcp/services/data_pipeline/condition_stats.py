"""条件统计与信号命中率助手。"""

from typing import Any, Iterable

import numpy as np

from ..factor_calculator import factor_calculator


def normalize_klines(klines: Iterable[dict]) -> list[dict]:
    rows = list(klines or [])
    if len(rows) >= 2:
        first = str(rows[0].get("date") or rows[0].get("time") or "")
        last = str(rows[-1].get("date") or rows[-1].get("time") or "")
        if first > last:
            rows.reverse()
    return rows


def _signal_indices(closes: np.ndarray, signal: str, signal_params: dict[str, Any] | None) -> list[int]:
    params = signal_params or {}
    if signal == "rsi_oversold":
        period = int(params.get("period", 14))
        threshold = float(params.get("threshold", 30))
        series = factor_calculator.calculate_rsi(closes.tolist(), period=period, as_series=True)
        offset = max(0, len(closes) - len(series))
        return [offset + i for i, value in enumerate(series) if np.isfinite(value) and float(value) <= threshold]
    if signal == "macd_golden_cross":
        series = factor_calculator.calculate_macd(closes.tolist(), as_series=True)
        return [i for i in range(1, len(series)) if np.isfinite(series[i - 1]) and np.isfinite(series[i]) and series[i - 1] <= 0 < series[i]]
    if signal == "ma_bullish_alignment":
        return [i for i in range(59, len(closes)) if closes[i] > np.mean(closes[i - 19:i + 1]) > np.mean(closes[i - 59:i + 1])]
    return []


def compute_signal_hit_rate(klines: Iterable[dict], signal: str, forward_days: list[int], signal_params: dict[str, Any] | None = None) -> dict:
    ordered = normalize_klines(klines)
    closes = np.array([float(row.get("close", 0) or 0) for row in ordered], dtype=np.float64)
    if len(closes) < 30:
        return {"signal": signal, "sample_count": 0, "forward_returns": {}, "by_regime": {}}
    indices = _signal_indices(closes, signal, signal_params)
    overall = {int(fd): [] for fd in forward_days}
    by_regime = {name: {int(fd): [] for fd in forward_days} for name in ("bullish", "neutral", "bearish")}
    for idx in indices:
        if idx < 20:
            continue
        regime_ret = (closes[idx] - closes[idx - 20]) / closes[idx - 20] if closes[idx - 20] > 0 else 0.0
        regime = "bullish" if regime_ret >= 0.05 else ("bearish" if regime_ret <= -0.05 else "neutral")
        for fd in forward_days:
            future_idx = idx + int(fd)
            if future_idx >= len(closes) or closes[idx] <= 0:
                continue
            fwd_ret = float((closes[future_idx] - closes[idx]) / closes[idx])
            overall[int(fd)].append(fwd_ret)
            by_regime[regime][int(fd)].append(fwd_ret)
    summarize = lambda values: {"samples": len(values), "hit_rate": round(float(np.mean(np.array(values) > 0)), 4) if values else None, "avg_return": round(float(np.mean(values)), 4) if values else None}
    return {
        "signal": signal,
        "sample_count": len(indices),
        "forward_returns": {f"{fd}d": summarize(values) for fd, values in overall.items()},
        "by_regime": {regime: {f"{fd}d": summarize(values) for fd, values in buckets.items()} for regime, buckets in by_regime.items()},
    }