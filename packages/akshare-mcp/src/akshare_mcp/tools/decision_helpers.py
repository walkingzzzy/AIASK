"""决策工具 — 纯数学/概率/技术辅助函数。"""

import math
import statistics


def _maybe_float(value):
    try:
        if value is None or value == '':
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _estimate_volatility(closes: list[float], window: int = 20) -> float:
    if not closes or len(closes) < 3:
        return 0.0
    n = min(window, len(closes) - 1)
    rets = []
    for i in range(n):
        prev = float(closes[i + 1])
        curr = float(closes[i])
        if prev > 0:
            rets.append((curr - prev) / prev)
    if len(rets) < 2:
        return 0.0
    return float(statistics.pstdev(rets))


def _calibrate_buy_probability(
    score: float,
    confidence: float,
    style: str,
    volatility: float,
) -> float:
    """将 score/confidence/波动率压缩为 [0,1] 的买入概率。"""
    style_bias = {
        "aggressive": 0.15,
        "balanced": 0.0,
        "conservative": -0.15,
    }.get(style, 0.0)

    # 以 60 分为中性点；置信度作为辅助项；波动率越大概率越低
    score_term = (float(score) - 60.0) / 12.0
    confidence_term = (float(confidence) - 60.0) / 25.0
    vol_term = float(volatility) * 18.0
    logit = score_term + 0.7 * confidence_term - vol_term + style_bias

    # 数值稳定：避免 exp 溢出
    logit = _clamp(logit, -30.0, 30.0)
    prob = 1.0 / (1.0 + math.exp(-logit))
    return float(_clamp(prob, 0.0, 1.0))



def _estimate_target_price(
    recommendation: str,
    current_price: float,
    pe: float,
    score: float,
    industry_peer_pes: list[float] | None = None,
) -> tuple[float | None, str, float | None]:
    """目标价估算：优先行业中位数 PE 法，缺失时回退旧口径。"""
    if recommendation != 'buy':
        return None, 'none', None

    if not pe or pe <= 0:
        return float(current_price) * 1.15, 'fixed_gain_fallback', None

    eps = float(current_price) / float(pe)
    peers = [float(x) for x in (industry_peer_pes or []) if x and 0 < float(x) < 80]
    if len(peers) >= 3:
        industry_median_pe = float(statistics.median(peers))
        # 给行业估值法留 10% 上行空间，避免过于保守
        target_price = eps * industry_median_pe * 1.10
        return float(target_price), 'industry_median_pe', industry_median_pe

    pe_expansion = 1.0 + min(float(score), 100.0) / 500.0
    return float(eps * float(pe) * pe_expansion), 'pe_expansion_fallback', None




def _compute_rsi_from_window(window_prices: list[float]) -> float:
    if len(window_prices) < 2:
        return 50.0
    gains = 0.0
    losses = 0.0
    for i in range(1, len(window_prices)):
        change = float(window_prices[i] - window_prices[i - 1])
        if change > 0:
            gains += change
        else:
            losses -= change
    period = max(1, len(window_prices) - 1)
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss <= 1e-12:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def _build_threshold_backtest(
    closes_desc: list[float],
    thresholds: list[int],
    horizon: int = 10,
) -> list[dict]:
    if not closes_desc or len(closes_desc) < 80:
        return []

    closes = list(reversed([float(c) for c in closes_desc]))  # oldest -> newest
    points: list[tuple[float, float]] = []
    start_idx = 30
    end_idx = len(closes) - int(horizon) - 1
    if end_idx <= start_idx:
        return []

    for idx in range(start_idx, end_idx + 1):
        price_now = closes[idx]
        if price_now <= 0:
            continue

        ma10 = sum(closes[idx - 9: idx + 1]) / 10.0
        ma30 = sum(closes[idx - 29: idx + 1]) / 30.0
        base10 = closes[idx - 10]
        momentum10 = ((price_now - base10) / base10) if base10 > 0 else 0.0
        rsi14 = _compute_rsi_from_window(closes[idx - 14: idx + 1])

        score = 50.0
        if momentum10 > 0.05:
            score += 15.0
        elif momentum10 < -0.05:
            score -= 15.0

        if price_now > ma10 > ma30:
            score += 20.0
        elif price_now < ma10 < ma30:
            score -= 20.0

        if rsi14 < 30.0:
            score += 15.0
        elif rsi14 > 70.0:
            score -= 15.0

        score = _clamp(score, 0.0, 100.0)
        price_future = closes[idx + horizon]
        forward_return = ((price_future - price_now) / price_now) if price_now > 0 else 0.0
        points.append((float(score), float(forward_return)))

    if not points:
        return []

    reports: list[dict] = []
    for threshold in thresholds:
        subset = [p for p in points if p[0] >= float(threshold)]
        sample_count = len(subset)
        if sample_count == 0:
            reports.append(
                {
                    "threshold": int(threshold),
                    "sample_count": 0,
                    "hit_rate": None,
                    "avg_forward_return": None,
                }
            )
            continue
        win_count = sum(1 for _, r in subset if r > 0)
        avg_ret = sum(r for _, r in subset) / sample_count
        reports.append(
            {
                "threshold": int(threshold),
                "sample_count": int(sample_count),
                "hit_rate": float(win_count / sample_count),
                "avg_forward_return": float(avg_ret),
            }
        )
    return reports


def _context_section(analysis_context: dict | None, name: str) -> dict:
    if not isinstance(analysis_context, dict):
        return {}
    value = analysis_context.get(name, {})
    return value if isinstance(value, dict) else {}


def _derive_contextual_decision(analysis_context: dict | None) -> dict:
    valuation = _context_section(analysis_context, "valuation")
    fundamentals = _context_section(analysis_context, "fundamentals")
    technical = _context_section(analysis_context, "technical")
    momentum = _context_section(analysis_context, "momentum")
    risk = _context_section(analysis_context, "risk")

    positives: list[str] = []
    negatives: list[str] = []
    pe = _maybe_float(valuation.get("pe"))
    industry_gap = _maybe_float(valuation.get("industry_relative_pe"))
    if pe is not None and 0 < pe < 20:
        positives.append(f"估值处于可接受区间(PE={pe:.1f})")
    if industry_gap is not None and industry_gap < 0.9:
        positives.append("相对行业估值偏低")
    elif industry_gap is not None and industry_gap > 1.2:
        negatives.append("相对行业估值偏高")

    roe = _maybe_float(fundamentals.get("roe"))
    revenue_yoy = _maybe_float(fundamentals.get("revenue_yoy"))
    debt_ratio = _maybe_float(fundamentals.get("debt_ratio"))
    if roe is not None and roe >= 12:
        positives.append(f"盈利能力良好(ROE={roe:.1f})")
    if revenue_yoy is not None and revenue_yoy >= 10:
        positives.append(f"营收保持增长({revenue_yoy:.1f}%)")
    if debt_ratio is not None and debt_ratio >= 70:
        negatives.append(f"负债率偏高({debt_ratio:.1f}%)")

    rsi = _maybe_float(technical.get("rsi_14"))
    ma_alignment = technical.get("ma_alignment")
    macd_hist = _maybe_float(technical.get("macd_hist"))
    if rsi is not None and rsi < 35:
        positives.append(f"RSI接近超卖({rsi:.1f})")
    elif rsi is not None and rsi > 75:
        negatives.append(f"RSI偏热({rsi:.1f})")
    if ma_alignment == "bullish":
        positives.append("均线呈多头排列")
    elif ma_alignment == "bearish":
        negatives.append("均线呈空头排列")
    if macd_hist is not None and macd_hist < 0:
        negatives.append("MACD柱线仍在零轴下方")

    mom_20d = _maybe_float(momentum.get("mom_20d"))
    market_regime = momentum.get("market_regime")
    if mom_20d is not None and mom_20d > 0.05:
        positives.append("20日动量为正")
    elif mom_20d is not None and mom_20d < -0.05:
        negatives.append("20日动量偏弱")
    if market_regime == "bearish":
        negatives.append("当前处于偏弱市场环境")

    volatility = _maybe_float(risk.get("volatility_20d"))
    drawdown = _maybe_float(risk.get("max_drawdown_250d"))
    if volatility is not None and volatility > 0.04:
        negatives.append("短期波动率较高")
    if drawdown is not None and drawdown > 0.30:
        negatives.append("历史回撤偏大")

    if len(positives) >= 4 and len(negatives) <= 1:
        recommendation, action_text = "buy", "建议买入"
    elif len(negatives) >= 4:
        recommendation, action_text = "avoid", "建议回避"
    elif len(positives) >= len(negatives) and positives:
        recommendation, action_text = "hold", "可持有或逢低布局"
    else:
        recommendation, action_text = "wait", "建议继续观望"
    return {
        "recommendation": recommendation,
        "action_text": action_text,
        "positives": positives,
        "negatives": negatives,
    }
