"""策略工厂命名工具。"""

from __future__ import annotations


def _auto_name(stype: str, params: dict) -> str:
    """从策略类型+参数生成中文名。"""
    if stype == "ma_cross":
        return f"均线交叉·快{params.get('short_period', 5)}慢{params.get('long_period', 20)}"
    if stype == "momentum":
        return f"动量突破·{params.get('lookback', 20)}日{params.get('threshold', 0.02):.0%}"
    if stype == "rsi":
        return f"RSI反转·{params.get('rsi_period', 14)}日({params.get('oversold', 30)}/{params.get('overbought', 70)})"
    if stype == "volatility_breakout":
        return f"波动突破·{params.get('lookback', 20)}日{params.get('threshold', 0.025):.0%}"
    if stype == "gap_fill":
        return f"缺口回补·{params.get('rsi_period', 5)}日回归"
    if stype == "mean_reversion_short":
        return f"短反转·{params.get('rsi_period', 6)}日RSI"
    if stype == "value_factor":
        return f"价值精选·前{int(params.get('buy_quantile', 0.8) * 100)}%"
    if stype == "quality_factor":
        return f"质量优选·前{int(params.get('buy_quantile', 0.8) * 100)}%"
    if stype == "growth_factor":
        return f"成长优选·前{int(params.get('buy_quantile', 0.8) * 100)}%"
    if stype == "multi_factor":
        factor_weights = params.get("factor_weights", {})
        top = max(factor_weights, key=factor_weights.get, default="均衡") if factor_weights else "均衡"
        return f"多因子·{top}主导"
    if stype == "macro_timing":
        return f"宏观择时·恐贪({params.get('fear_threshold', 35)}/{params.get('greed_threshold', 65)})"
    if stype == "sector_rotation":
        return f"板块轮动·{params.get('lookback', 20)}日观察"
    if stype == "north_capital_track":
        return f"北向跟踪·{params.get('lookback', 15)}日动量"
    if stype == "margin_divergence":
        return f"两融背离·{params.get('lookback', 12)}日节奏"
    return f"{stype}策略"
