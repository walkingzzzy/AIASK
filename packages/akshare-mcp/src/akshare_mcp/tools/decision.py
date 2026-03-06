"""决策工具"""

from ..storage import get_db
from ..services import technical_analysis
from ..services import (
    add_evidence,
    create_chain,
    make_evidence,
    save_chain,
    set_conclusion,
    summarize_chain,
)
from ..services.factor_calculator import factor_calculator
from ..utils import ok, fail
import math
import statistics
import time


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


def register(mcp):
    """注册决策工具"""

    @mcp.tool()
    async def should_i_buy(
        code: str,
        investment_style: str = 'balanced',
        as_of: str = '',
        adjust: str = '',
        price_source_policy: str = 'auto',
        explain: bool = True,
        strict_mode: bool = False
    ):
        """
        买入建议 - 综合估值、技术、基本面、因子分析

        Args:
            code: 股票代码
            investment_style: 投资风格 ('aggressive'激进, 'balanced'平衡, 'conservative'保守)
            as_of: 分析时点（可选）
            adjust: 复权口径（可选）
            price_source_policy: 价格源策略（可选）
            explain: 是否返回证据链
            strict_mode: 严格模式（空值严格处理）
        """
        start_time = time.perf_counter()
        trace_id = f"should_i_buy:{code}:{int(time.time() * 1000)}"
        evidence_chain = None
        try:
            evidence_chain = create_chain(
                trace_id=trace_id,
                code=code,
                action="should_i_buy",
                tool_version="v1.1.0",
                extra={
                    "investment_style": investment_style,
                    "as_of": as_of,
                    "adjust": adjust,
                    "price_source_policy": price_source_policy,
                    "strict_mode": strict_mode,
                },
            )
        except Exception:
            evidence_chain = None

        def _record_evidence(
            evidence_type: str,
            metric_name: str,
            raw_value,
            delta_score: float,
            *,
            confidence_hint: float | None = None,
            detail: dict | None = None,
        ) -> None:
            nonlocal evidence_chain
            if evidence_chain is None:
                return
            try:
                ev = make_evidence(
                    evidence_type=evidence_type,
                    source_module="decision.should_i_buy",
                    metric_name=metric_name,
                    raw_value=raw_value,
                    score=float(max(0.0, min(100.0, 50.0 + delta_score))),
                    weight=1.0,
                    score_contribution=float(delta_score),
                    confidence=confidence_hint,
                    detail=detail or {},
                )
                evidence_chain = add_evidence(evidence_chain, ev)
            except Exception:
                pass

        def _with_meta(resp: dict, source_chain: list | None = None) -> dict:
            resp['meta'] = {
                'trace_id': trace_id,
                'tool_version': 'v1.1.0',
                'data_timestamp': None,
                'source_chain': source_chain or ['db', 'technical_analysis', 'factor_calculator'],
                'cached': bool(resp.get('cached', False)),
                'latency_ms': int((time.perf_counter() - start_time) * 1000),
                'as_of': as_of,
                'adjust': adjust,
                'price_source_policy': price_source_policy,
                'strict_mode': strict_mode,
            }
            return resp

        def _ok(data: dict, source_chain: list | None = None) -> dict:
            return _with_meta(ok(data), source_chain)

        def _fail(message: str, source_chain: list | None = None) -> dict:
            return _with_meta(fail(message), source_chain)

        try:
            db = get_db()

            # 1. 获取基础信息
            stock_info = await db.get_stock_info(code)
            if not stock_info:
                return _fail(f'Stock {code} not found')

            # 2. 获取K线数据
            klines = await db.get_klines(code, limit=100)
            if not klines or len(klines) < 20:
                return _fail('Insufficient kline data')

            closes = [k['close'] for k in klines]
            volumes = [k['volume'] for k in klines]

            analysis_context = {}
            context_error = None
            try:
                context_result = await get_investment_analysis(code)
                if context_result.get('success'):
                    analysis_context = context_result.get('data', {}) or {}
                else:
                    context_error = context_result.get('error', 'unknown')
            except Exception as ctx_exc:
                context_error = str(ctx_exc)

            valuation_ctx = _context_section(analysis_context, 'valuation')
            fundamentals_ctx = _context_section(analysis_context, 'fundamentals')
            technical_ctx = _context_section(analysis_context, 'technical')
            momentum_ctx = _context_section(analysis_context, 'momentum')

            reasons = []
            risks = []
            score = 0
            confidence = 0
            score_breakdown = {
                'valuation': 0.0,
                'technical': 0.0,
                'fundamental': 0.0,
                'factor': 0.0,
            }
            signal_breakdown = []

            def _apply_signal(
                category: str,
                text: str,
                delta_score: float,
                *,
                confidence_delta: float = 0.0,
                source: str = 'fallback',
                metric_name: str | None = None,
                raw_value=None,
                evidence_type: str | None = None,
                confidence_hint: float | None = None,
                detail: dict | None = None,
            ) -> None:
                nonlocal score, confidence
                if delta_score >= 0:
                    reasons.append(text)
                else:
                    risks.append(text)
                score += float(delta_score)
                confidence += float(confidence_delta)
                score_breakdown[category] = float(score_breakdown.get(category, 0.0)) + float(delta_score)
                signal_breakdown.append({
                    'category': category,
                    'text': text,
                    'delta_score': float(delta_score),
                    'confidence_delta': float(confidence_delta),
                    'source': source,
                })
                if evidence_type and metric_name is not None:
                    _record_evidence(
                        evidence_type,
                        metric_name,
                        raw_value,
                        float(delta_score),
                        confidence_hint=confidence_hint,
                        detail=detail,
                    )

            # 3. 估值分析（从数据库直接查询）
            pe = _maybe_float(valuation_ctx.get('pe'))
            pb = _maybe_float(valuation_ctx.get('pb'))
            valuation_source = 'analysis_context' if (pe is not None or pb is not None) else 'fallback'
            if pe is None or pb is None:
                try:
                    async with db.acquire() as conn:
                        valuation_row = await conn.fetchrow(
                            """SELECT pe_ratio, pb_ratio FROM stocks WHERE code = $1""",
                            code
                        )
                        if pe is None:
                            pe = _maybe_float(valuation_row['pe_ratio']) if valuation_row else None
                        if pb is None:
                            pb = _maybe_float(valuation_row['pb_ratio']) if valuation_row else None
                except Exception:
                    pass

            if pe and 0 < pe < 15:
                _apply_signal(
                    'valuation',
                    f'估值偏低(PE={pe:.1f})',
                    25,
                    confidence_delta=15,
                    source=valuation_source,
                    metric_name='pe_ratio',
                    raw_value=pe,
                    evidence_type='valuation',
                    confidence_hint=0.75,
                )
            elif pe and 15 <= pe < 30:
                _apply_signal(
                    'valuation',
                    f'估值合理(PE={pe:.1f})',
                    15,
                    confidence_delta=10,
                    source=valuation_source,
                    metric_name='pe_ratio',
                    raw_value=pe,
                    evidence_type='valuation',
                    confidence_hint=0.65,
                )
            elif pe and pe >= 50:
                _apply_signal(
                    'valuation',
                    f'估值偏高(PE={pe:.1f})',
                    -15,
                    source=valuation_source,
                    metric_name='pe_ratio',
                    raw_value=pe,
                    evidence_type='valuation',
                    confidence_hint=0.70,
                )

            if pb and 0 < pb < 2:
                _apply_signal(
                    'valuation',
                    f'市净率偏低(PB={pb:.1f})',
                    20,
                    confidence_delta=10,
                    source=valuation_source,
                    metric_name='pb_ratio',
                    raw_value=pb,
                    evidence_type='valuation',
                    confidence_hint=0.7,
                )
            elif pb and pb > 5:
                _apply_signal(
                    'valuation',
                    f'市净率偏高(PB={pb:.1f})',
                    -10,
                    source=valuation_source,
                    metric_name='pb_ratio',
                    raw_value=pb,
                    evidence_type='valuation',
                    confidence_hint=0.65,
                )

            # 4. 技术分析
            # RSI
            rsi_value = _maybe_float(technical_ctx.get('rsi_14'))
            rsi_source = 'analysis_context' if rsi_value is not None else 'fallback'
            if rsi_value is None:
                rsi_result = technical_analysis.calculate_rsi(closes)
                if rsi_result:
                    rsi_value = rsi_result[-1] if isinstance(rsi_result, list) else rsi_result.get('value', 50)
            if rsi_value is not None:
                if rsi_value < 30:
                    _apply_signal(
                        'technical',
                        f'RSI超卖({rsi_value:.1f})，可能反弹',
                        20,
                        confidence_delta=15,
                        source=rsi_source,
                        metric_name='rsi',
                        raw_value=float(rsi_value),
                        evidence_type='technical',
                        confidence_hint=0.75,
                    )
                elif rsi_value > 70:
                    _apply_signal(
                        'technical',
                        f'RSI超买({rsi_value:.1f})，短期风险',
                        -15,
                        source=rsi_source,
                        metric_name='rsi',
                        raw_value=float(rsi_value),
                        evidence_type='technical',
                        confidence_hint=0.70,
                    )

            # MACD
            macd_result = technical_analysis.calculate_macd(closes)
            if macd_result and 'histogram' in macd_result:
                hist = macd_result['histogram']
                if len(hist) >= 2:
                    if hist[-2] < 0 and hist[-1] > 0:
                        _apply_signal(
                            'technical',
                            'MACD金叉，买入信号',
                            25,
                            confidence_delta=20,
                            source='fallback',
                            metric_name='macd_histogram',
                            raw_value=float(hist[-1]),
                            evidence_type='technical',
                            confidence_hint=0.8,
                        )
                    elif hist[-2] > 0 and hist[-1] < 0:
                        _apply_signal(
                            'technical',
                            'MACD死叉，卖出信号',
                            -20,
                            source='fallback',
                            metric_name='macd_histogram',
                            raw_value=float(hist[-1]),
                            evidence_type='technical',
                            confidence_hint=0.78,
                        )

            # 均线趋势
            ma_data = technical_ctx.get('moving_averages', {}) if isinstance(technical_ctx.get('moving_averages'), dict) else {}
            ma20_last = _maybe_float(ma_data.get('ma20'))
            ma60_last = _maybe_float(ma_data.get('ma60'))
            if ma20_last is None or ma60_last is None:
                ma20 = technical_analysis.calculate_sma(closes, 20)
                ma60 = technical_analysis.calculate_sma(closes, 60)
                if ma20 and ma60 and len(ma20) > 0 and len(ma60) > 0:
                    ma20_last = _maybe_float(ma20[-1])
                    ma60_last = _maybe_float(ma60[-1])
            if ma20_last is not None and ma60_last is not None:
                latest_close = float(closes[-1])
                ma_source = 'analysis_context' if isinstance(technical_ctx.get('moving_averages'), dict) else 'fallback'
                if latest_close > ma20_last > ma60_last:
                    _apply_signal(
                        'technical',
                        '多头排列，趋势向上',
                        20,
                        confidence_delta=15,
                        source=ma_source,
                        metric_name='ma_trend',
                        raw_value={"close": latest_close, "ma20": float(ma20_last), "ma60": float(ma60_last)},
                        evidence_type='technical',
                        confidence_hint=0.75,
                    )
                elif latest_close < ma20_last < ma60_last:
                    _apply_signal(
                        'technical',
                        '空头排列，趋势向下',
                        -20,
                        source=ma_source,
                        metric_name='ma_trend',
                        raw_value={"close": latest_close, "ma20": float(ma20_last), "ma60": float(ma60_last)},
                        evidence_type='technical',
                        confidence_hint=0.75,
                    )

            # 成交量
            recent_vol = statistics.mean(volumes[:5])
            avg_vol = statistics.mean(volumes)
            if recent_vol > avg_vol * 1.5:
                _apply_signal(
                    'technical',
                    '成交量放大，资金关注',
                    15,
                    confidence_delta=10,
                    source='fallback',
                    metric_name='volume_ratio',
                    raw_value=float(recent_vol / avg_vol) if avg_vol else 0.0,
                    evidence_type='technical',
                    confidence_hint=0.6,
                )

            # 5. 基本面分析
            roe = _maybe_float(fundamentals_ctx.get('roe'))
            debt_ratio = _maybe_float(fundamentals_ctx.get('debt_ratio'))
            revenue_growth = _maybe_float(fundamentals_ctx.get('revenue_yoy'))
            if roe is None and debt_ratio is None and revenue_growth is None:
                try:
                    async with db.acquire() as conn:
                        f_code_col = await db._financials_code_column(conn)
                        financial_row = await conn.fetchrow(
                            f"""SELECT roe, debt_ratio, revenue_growth
                               FROM financials
                               WHERE {f_code_col} = $1
                               ORDER BY report_date DESC
                               LIMIT 1""",
                            code
                        )
                        if financial_row:
                            roe = _maybe_float(financial_row['roe'])
                            debt_ratio = _maybe_float(financial_row['debt_ratio'])
                            revenue_growth = _maybe_float(financial_row['revenue_growth'])
                except Exception:
                    pass

            if roe and roe > 15:
                _apply_signal(
                    'fundamental',
                    f'ROE优秀({roe:.1f}%)',
                    20,
                    confidence_delta=10,
                    source='analysis_context' if fundamentals_ctx else 'fallback',
                    metric_name='roe',
                    raw_value=roe,
                    evidence_type='fundamental',
                    confidence_hint=0.72,
                )
            elif roe and roe > 10:
                _apply_signal(
                    'fundamental',
                    f'ROE良好({roe:.1f}%)',
                    10,
                    source='analysis_context' if fundamentals_ctx else 'fallback',
                    metric_name='roe',
                    raw_value=roe,
                    evidence_type='fundamental',
                    confidence_hint=0.65,
                )

            if debt_ratio and debt_ratio > 70:
                _apply_signal(
                    'fundamental',
                    f'负债率较高({debt_ratio:.1f}%)',
                    -10,
                    source='analysis_context' if fundamentals_ctx else 'fallback',
                    metric_name='debt_ratio',
                    raw_value=debt_ratio,
                    evidence_type='fundamental',
                    confidence_hint=0.68,
                )

            if revenue_growth and revenue_growth > 20:
                _apply_signal(
                    'fundamental',
                    f'营收高增长({revenue_growth:.1f}%)',
                    20,
                    confidence_delta=15,
                    source='analysis_context' if fundamentals_ctx else 'fallback',
                    metric_name='revenue_growth',
                    raw_value=revenue_growth,
                    evidence_type='fundamental',
                    confidence_hint=0.75,
                )

            # 6. 因子分析
            momentum = _maybe_float(momentum_ctx.get('mom_20d'))
            if momentum is None:
                momentum = _maybe_float(momentum_ctx.get('mom_10d'))
            if momentum is None:
                try:
                    momentum = factor_calculator.calculate_momentum(closes)
                except Exception:
                    momentum = None
            if momentum is not None:
                if momentum > 0.1:
                    _apply_signal(
                        'factor',
                        '动量因子强势',
                        15,
                        source='analysis_context' if momentum_ctx else 'fallback',
                        metric_name='momentum',
                        raw_value=float(momentum),
                        evidence_type='factor',
                        confidence_hint=0.62,
                    )
                elif momentum < -0.1:
                    _apply_signal(
                        'factor',
                        '动量因子弱势',
                        -10,
                        source='analysis_context' if momentum_ctx else 'fallback',
                        metric_name='momentum',
                        raw_value=float(momentum),
                        evidence_type='factor',
                        confidence_hint=0.62,
                    )

            confidence = _clamp(confidence, 0.0, 100.0)

            # 7. 根据投资风格调整
            style_thresholds = {
                'aggressive': {'buy': 40, 'confidence': 50},
                'balanced': {'buy': 60, 'confidence': 60},
                'conservative': {'buy': 80, 'confidence': 70}
            }

            threshold = style_thresholds.get(investment_style, style_thresholds['balanced'])

            context_decision = _derive_contextual_decision(analysis_context) if analysis_context else None

            # 8. 生成建议
            if score >= threshold['buy'] and confidence >= threshold['confidence']:
                recommendation = 'buy'
                action_text = '建议买入'
            elif score >= threshold['buy'] * 0.7:
                recommendation = 'hold'
                action_text = '可以持有或小仓位试探'
            elif score >= 0:
                recommendation = 'wait'
                action_text = '建议观望'
            else:
                recommendation = 'avoid'
                action_text = '建议回避'

            if context_decision:
                recommendation = context_decision["recommendation"]
                action_text = context_decision["action_text"]
                for item in context_decision["positives"]:
                    if item not in reasons:
                        reasons.append(item)
                for item in context_decision["negatives"]:
                    if item not in risks:
                        risks.append(item)

            # 9. 目标价位（优先行业中位数PE估值法）
            current_price = closes[0]
            industry_peer_pes: list[float] = []
            industry_name = stock_info.get('industry') or stock_info.get('industry_name') or ''
            if industry_name:
                try:
                    async with db.acquire() as conn:
                        peer_rows = await conn.fetch(
                            """SELECT pe_ratio FROM stocks
                               WHERE industry = $1
                                 AND code <> $2
                                 AND pe_ratio IS NOT NULL""",
                            industry_name,
                            code,
                        )
                    industry_peer_pes = [float(r['pe_ratio']) for r in peer_rows if r.get('pe_ratio')]
                except Exception:
                    industry_peer_pes = []

            target_price, valuation_method, industry_median_pe = _estimate_target_price(
                recommendation=recommendation,
                current_price=float(current_price),
                pe=float(pe) if pe else 0.0,
                score=float(score),
                industry_peer_pes=industry_peer_pes,
            )

            confidence = max(0, min(100, confidence))
            volatility_20d = _estimate_volatility(closes, window=20)
            buy_probability = _calibrate_buy_probability(
                score=float(score),
                confidence=float(confidence),
                style=investment_style,
                volatility=float(volatility_20d),
            )
            probability_band = (
                "high" if buy_probability >= 0.7 else ("medium" if buy_probability >= 0.45 else "low")
            )

            threshold_backtest = _build_threshold_backtest(
                closes_desc=closes,
                thresholds=[40, 60, 80],
                horizon=10,
            )

            analysis_date = klines[0].get('date', '')
            payload = {
                'code': code,
                'name': stock_info.get('name', ''),
                'recommendation': recommendation,
                'decision_mode': 'context_guided_hybrid' if analysis_context else 'hybrid_score_plus_context',
                'action_text': action_text,
                'score': score,
                'confidence': round(confidence, 1),
                'current_price': current_price,
                'target_price': round(target_price, 2) if target_price else None,
                'valuation_method': valuation_method,
                'industry_median_pe': round(industry_median_pe, 2) if industry_median_pe else None,
                'reasons': reasons,
                'risks': risks,
                'score_breakdown': {k: round(float(v), 2) for k, v in score_breakdown.items()},
                'signal_breakdown': signal_breakdown,
                'investment_style': investment_style,
                'analysis_date': analysis_date,
                'failed_modules': ([f"investment_analysis:{context_error}"] if context_error else []),
                'decision_probability': {
                    'buy_probability': round(float(buy_probability), 4),
                    'buy_probability_pct': f"{buy_probability * 100:.2f}%",
                    'band': probability_band,
                    'method': 'logit(score,confidence,volatility)',
                },
                'probability_calibration': {
                    'thresholds': style_thresholds,
                    'selected_style_threshold': threshold,
                    'volatility_20d': round(float(volatility_20d), 6),
                    'threshold_backtest': {
                        'horizon_days': 10,
                        'records': threshold_backtest,
                    },
                },
            }

            if analysis_context:
                payload['analysis_context'] = analysis_context

            if evidence_chain is not None:
                try:
                    confidence_ratio = (
                        buy_probability if recommendation in {'buy', 'hold'} else (1.0 - buy_probability)
                    )
                    confidence_ratio = max(0.0, min(1.0, confidence_ratio))
                    evidence_chain = set_conclusion(
                        evidence_chain,
                        recommendation=recommendation,
                        total_score=float(score),
                        raw_total_score=float(score),
                        reason=action_text,
                        confidence=confidence_ratio,
                        data_quality={
                            "kline_size": len(closes),
                            "has_financial_row": bool('financial_row' in locals() and financial_row),
                            "strict_mode": bool(strict_mode),
                        },
                    )
                    saved_chain = save_chain(evidence_chain)
                    payload['evidence_trace_id'] = saved_chain.get('trace_id')
                    if explain:
                        payload['evidence_summary'] = summarize_chain(saved_chain)
                except Exception as chain_exc:
                    payload['failed_modules'].append(f"evidence_chain:{chain_exc}")

            if explain:
                payload['diagnostic'] = {
                    'trace': [
                        'valuation',
                        'technical:rsi/macd/ma',
                        'fundamental',
                        'factor:momentum',
                        f'style:{investment_style}',
                    ]
                }
            result = _ok(payload)
            result['meta']['data_timestamp'] = analysis_date
            result['meta']['evidence_chain_saved'] = bool(payload.get('evidence_trace_id'))
            return result

        except Exception as e:
            return _fail(str(e))

    @mcp.tool()
    async def should_i_sell(
        code: str,
        buy_price: float,
        holding_days: int = 0
    ):
        """
        卖出建议 - 综合止盈止损、技术信号、持仓时间分析

        Args:
            code: 股票代码
            buy_price: 买入价格
            holding_days: 持有天数
        """
        try:
            db = get_db()

            # 1. 获取基础信息
            stock_info = await db.get_stock_info(code)
            if not stock_info:
                return fail(f'Stock {code} not found')

            # 2. 获取K线数据
            klines = await db.get_klines(code, limit=100)
            if not klines:
                return fail('No kline data')

            current_price = klines[0]['close']
            closes = [k['close'] for k in klines]

            analysis_context = {}
            context_error = None
            try:
                context_result = await get_investment_analysis(code)
                if context_result.get('success'):
                    analysis_context = context_result.get('data', {}) or {}
                else:
                    context_error = context_result.get('error', 'unknown')
            except Exception as ctx_exc:
                context_error = str(ctx_exc)

            technical_ctx = _context_section(analysis_context, 'technical')
            risk_ctx = _context_section(analysis_context, 'risk')

            # 3. 计算盈亏
            profit_pct = (current_price - buy_price) / buy_price * 100
            profit_amount = current_price - buy_price

            reasons = []
            risks = []
            score = 0  # 正分倾向卖出，负分倾向持有
            score_breakdown = {
                'profit_loss': 0.0,
                'technical': 0.0,
                'holding': 0.0,
                'risk': 0.0,
            }
            signal_breakdown = []

            def _apply_sell_signal(category: str, text: str, delta_score: float, *, source: str = 'fallback') -> None:
                nonlocal score
                if delta_score >= 0:
                    reasons.append(text)
                else:
                    risks.append(text)
                score += float(delta_score)
                score_breakdown[category] = float(score_breakdown.get(category, 0.0)) + float(delta_score)
                signal_breakdown.append({
                    'category': category,
                    'text': text,
                    'delta_score': float(delta_score),
                    'source': source,
                })

            # 4. 止盈止损分析
            if profit_pct >= 30:
                _apply_sell_signal('profit_loss', f'盈利{profit_pct:.1f}%，建议止盈', 40, source='direct_profit_loss')
            elif profit_pct >= 20:
                _apply_sell_signal('profit_loss', f'盈利{profit_pct:.1f}%，可考虑部分止盈', 25, source='direct_profit_loss')
            elif profit_pct >= 10:
                _apply_sell_signal('profit_loss', f'盈利{profit_pct:.1f}%，持有为主', 5, source='direct_profit_loss')
            elif profit_pct <= -15:
                _apply_sell_signal('profit_loss', f'亏损{abs(profit_pct):.1f}%，建议止损', 35, source='direct_profit_loss')
            elif profit_pct <= -10:
                _apply_sell_signal('profit_loss', f'亏损{abs(profit_pct):.1f}%，考虑止损', 20, source='direct_profit_loss')
            elif profit_pct <= -5:
                _apply_sell_signal('profit_loss', f'亏损{abs(profit_pct):.1f}%，注意风险', 10, source='direct_profit_loss')

            # 5. 技术分析
            # RSI
            rsi_value = _maybe_float(technical_ctx.get('rsi_14'))
            rsi_source = 'analysis_context' if rsi_value is not None else 'fallback'
            if rsi_value is None:
                rsi_result = technical_analysis.calculate_rsi(closes)
                if rsi_result:
                    rsi_value = rsi_result[-1] if isinstance(rsi_result, list) else rsi_result.get('value', 50)
            if rsi_value is not None:
                if rsi_value > 80:
                    _apply_sell_signal('technical', f'RSI严重超买({rsi_value:.1f})，建议卖出', 25, source=rsi_source)
                elif rsi_value > 70:
                    _apply_sell_signal('technical', f'RSI超买({rsi_value:.1f})，考虑减仓', 15, source=rsi_source)
                elif rsi_value < 30:
                    _apply_sell_signal('technical', f'RSI超卖({rsi_value:.1f})，可能反弹', -15, source=rsi_source)

            # MACD
            macd_result = technical_analysis.calculate_macd(closes)
            if macd_result and 'histogram' in macd_result:
                hist = macd_result['histogram']
                if len(hist) >= 2:
                    if hist[-2] > 0 and hist[-1] < 0:
                        _apply_sell_signal('technical', 'MACD死叉，卖出信号', 20, source='fallback')
                    elif hist[-2] < 0 and hist[-1] > 0:
                        _apply_sell_signal('technical', 'MACD金叉，买入信号', -20, source='fallback')

            # 均线
            ma_data = technical_ctx.get('moving_averages', {}) if isinstance(technical_ctx.get('moving_averages'), dict) else {}
            ma20_last = _maybe_float(ma_data.get('ma20'))
            ma60_last = _maybe_float(ma_data.get('ma60'))
            if ma20_last is None or ma60_last is None:
                ma20 = technical_analysis.calculate_sma(closes, 20)
                ma60 = technical_analysis.calculate_sma(closes, 60)
                if ma20 and ma60 and len(ma20) > 0 and len(ma60) > 0:
                    ma20_last = _maybe_float(ma20[-1])
                    ma60_last = _maybe_float(ma60[-1])
            if ma20_last is not None and ma60_last is not None:
                latest_close = float(closes[-1])
                ma_source = 'analysis_context' if isinstance(technical_ctx.get('moving_averages'), dict) else 'fallback'
                if latest_close < ma20_last < ma60_last:
                    _apply_sell_signal('technical', '跌破均线，趋势转弱', 20, source=ma_source)
                elif latest_close > ma20_last > ma60_last:
                    _apply_sell_signal('technical', '多头排列，趋势向上', -15, source=ma_source)

            # 6. 持仓时间分析
            if holding_days > 0:
                if holding_days < 7:
                    _apply_sell_signal('holding', f'持仓仅{holding_days}天，建议再观察', -10, source='direct_holding')
                elif holding_days > 180:
                    if profit_pct < 5:
                        _apply_sell_signal('holding', f'持仓{holding_days}天收益不佳，考虑换股', 15, source='direct_holding')

            # 7. 波动风险
            volatility = _maybe_float(risk_ctx.get('volatility_20d'))
            if volatility is None:
                returns = [(closes[i] - closes[i+1]) / closes[i+1] for i in range(min(20, len(closes)-1))]
                if len(returns) > 1:
                    volatility = statistics.stdev(returns)
            if volatility is not None and volatility > 0.04:
                _apply_sell_signal('risk', '近期波动较大，注意风险', 10, source='analysis_context' if risk_ctx else 'fallback')

            # 8. 生成建议
            if score >= 40:
                recommendation = 'sell'
                action_text = '强烈建议卖出'
            elif score >= 25:
                recommendation = 'reduce'
                action_text = '建议减仓'
            elif score >= 10:
                recommendation = 'consider_sell'
                action_text = '可考虑卖出'
            elif score >= -10:
                recommendation = 'hold'
                action_text = '继续持有'
            else:
                recommendation = 'strong_hold'
                action_text = '坚定持有'

            # 9. 目标卖出价（如果建议卖出）
            target_sell_price = None
            if recommendation in ['sell', 'reduce']:
                if profit_pct > 0:
                    # 盈利状态，当前价即可
                    target_sell_price = current_price
                else:
                    # 亏损状态，等待反弹
                    target_sell_price = buy_price * 0.95  # 回本95%

            payload = {
                'code': code,
                'name': stock_info.get('name', ''),
                'recommendation': recommendation,
                'decision_mode': 'hybrid_score_plus_context',
                'action_text': action_text,
                'score': score,
                'current_price': current_price,
                'buy_price': buy_price,
                'profit_pct': round(profit_pct, 2),
                'profit_amount': round(profit_amount, 2),
                'holding_days': holding_days,
                'target_sell_price': round(target_sell_price, 2) if target_sell_price else None,
                'reasons': reasons,
                'risks': risks,
                'score_breakdown': {k: round(float(v), 2) for k, v in score_breakdown.items()},
                'signal_breakdown': signal_breakdown,
                'analysis_date': klines[0].get('date', ''),
                'failed_modules': ([f"investment_analysis:{context_error}"] if context_error else []),
            }

            if analysis_context:
                payload['analysis_context'] = analysis_context

            return ok(payload)

        except Exception as e:
            return fail(str(e))

    # Phase 2：显式暴露纯数据汇聚工具，避免只有硬编码评分入口。
    mcp.tool()(get_investment_analysis)


# ═══════════════════════════════════════════════════════════════════
#  Phase 2: 纯数据汇聚工具 — AI 自行推理，MCP 只提供数据原材料
# ═══════════════════════════════════════════════════════════════════

async def get_investment_analysis(code: str) -> dict:
    """
    投资分析数据汇聚（纯数据模式，不做评分/推荐）。

    返回结构化的多维度数据，供 AI 自行分析判断：
    - 价格上下文（当前价、多周期涨跌幅、52周高低点位置）
    - 估值数据（PE/PB 及历史分位）
    - 基本面指标（ROE/负债率/增速）
    - 技术面指标（RSI/MACD/均线排列/支撑阻力）
    - 动量因子
    - 风险指标（波动率/最大回撤）
    """
    try:
        db = get_db()
        result = {}
        info = None

        # ── 1. K 线与价格上下文 ──
        klines = await db.get_klines(code, limit=250)
        if not klines:
            return fail("无 K 线数据")

        closes = [float(k.get('close', 0)) for k in klines]
        highs = [float(k.get('high', 0)) for k in klines]
        lows = [float(k.get('low', 0)) for k in klines]
        volumes = [float(k.get('volume', 0)) for k in klines]
        current_price = closes[0] if closes else 0

        def _pct_change(data, days):
            if len(data) <= days:
                return None
            old = float(data[days])
            return round((float(data[0]) - old) / old * 100, 2) if old > 0 else None

        high_52w = max(highs[:min(250, len(highs))]) if highs else 0
        low_52w = min(lows[:min(250, len(lows))]) if lows else 0
        position_52w = None
        if high_52w > low_52w > 0:
            position_52w = round((current_price - low_52w) / (high_52w - low_52w) * 100, 1)

        result["price_context"] = {
            "current_price": current_price,
            "change_1d_pct": _pct_change(closes, 1),
            "change_5d_pct": _pct_change(closes, 5),
            "change_20d_pct": _pct_change(closes, 20),
            "change_60d_pct": _pct_change(closes, 60),
            "high_52w": high_52w,
            "low_52w": low_52w,
            "position_in_52w_range_pct": position_52w,
            "analysis_date": klines[0].get('date', '') if klines else '',
        }

        # ── 2. 估值数据 ──
        valuation = {}
        try:
            info = await db.get_stock_info(code)
            if info:
                for key in ['pe', 'pb', 'ps', 'total_mv', 'circ_mv', 'pe_ratio', 'pb_ratio', 'market_cap']:
                    val = info.get(key)
                    if val is not None:
                        try:
                            normalized_key = {
                                'pe_ratio': 'pe',
                                'pb_ratio': 'pb',
                                'market_cap': 'total_mv',
                            }.get(key, key)
                            valuation[normalized_key] = round(float(val), 2)
                        except (ValueError, TypeError):
                            pass
        except Exception:
            pass
        result["basic_info"] = {
            "code": code,
            "name": (info or {}).get("name") or (info or {}).get("stock_name", ""),
            "industry": (info or {}).get("industry", ""),
            "market_cap": valuation.get("total_mv"),
            "list_date": (info or {}).get("list_date"),
        }
        if (info or {}).get("industry") and hasattr(db, 'acquire'):
            try:
                async with db.acquire() as conn:
                    peer_rows = await conn.fetch(
                        """SELECT pe_ratio, pb_ratio FROM stocks WHERE industry = $1 AND code <> $2 AND pe_ratio IS NOT NULL""",
                        info["industry"],
                        code,
                    )
                peer_pes = [float(row['pe_ratio']) for row in peer_rows if row.get('pe_ratio')]
                peer_pbs = [float(row['pb_ratio']) for row in peer_rows if row.get('pb_ratio')]
                if peer_pes:
                    valuation["industry_median_pe"] = round(float(statistics.median(peer_pes)), 2)
                    if valuation.get("pe"):
                        valuation["industry_relative_pe"] = round(float(valuation["pe"]) / float(valuation["industry_median_pe"]), 4)
                if peer_pbs:
                    valuation["industry_median_pb"] = round(float(statistics.median(peer_pbs)), 2)
            except Exception:
                pass
        result["valuation"] = valuation

        # ── 3. 基本面指标 ──
        fundamentals = {}
        try:
            fin = None
            fin_rows = []
            if hasattr(db, 'get_financial_data'):
                fin = await db.get_financial_data(code)
            if not fin and hasattr(db, 'get_financials'):
                fin_rows = await db.get_financials(code)
                fin = fin_rows[0] if fin_rows else None
            if fin:
                aliases = {
                    'roe': ['roe'],
                    'roa': ['roa'],
                    'debt_ratio': ['debt_ratio'],
                    'gross_margin': ['gross_margin'],
                    'revenue_yoy': ['revenue_yoy', 'revenue_growth'],
                    'profit_yoy': ['profit_yoy', 'profit_growth'],
                    'eps': ['eps'],
                    'bps': ['bps', 'bvps'],
                }
                for key, candidates in aliases.items():
                    val = next((fin.get(name) for name in candidates if fin.get(name) is not None), None)
                    if val is not None:
                        try:
                            fundamentals[key] = round(float(val), 2)
                        except (ValueError, TypeError):
                            pass
                fundamentals["report_count"] = len(fin_rows) if isinstance(fin_rows, list) else 1
        except Exception:
            pass
        result["fundamentals"] = fundamentals

        # ── 4. 技术面指标（计算值，无评分） ──
        technical = {}
        if len(closes) >= 15:
            try:
                technical["rsi_14"] = round(factor_calculator.calculate_rsi(closes, 14), 2)
            except Exception:
                pass
            try:
                technical["rsi_6"] = round(factor_calculator.calculate_rsi(closes, 6), 2)
            except Exception:
                pass
        if len(closes) >= 26:
            try:
                technical["macd"] = round(factor_calculator.calculate_macd(closes), 4)
            except Exception:
                pass
            try:
                technical["macd_signal"] = round(factor_calculator.calculate_macd_signal(closes), 4)
            except Exception:
                pass
            try:
                technical["macd_hist"] = round(factor_calculator.calculate_macd_hist(closes), 4)
            except Exception:
                pass

        # 均线排列
        ma_data = {}
        for period in [5, 10, 20, 60, 120]:
            if len(closes) >= period:
                import numpy as np
                ma_data[f"ma{period}"] = round(float(np.mean(closes[:period])), 2)
        technical["moving_averages"] = ma_data
        if ma_data.get("ma20") and ma_data.get("ma60"):
            if current_price > ma_data["ma20"] > ma_data["ma60"]:
                technical["ma_alignment"] = "bullish"
            elif current_price < ma_data["ma20"] < ma_data["ma60"]:
                technical["ma_alignment"] = "bearish"
            else:
                technical["ma_alignment"] = "mixed"

        # 支撑/阻力（近 60 日高低点）
        if len(highs) >= 60 and len(lows) >= 60:
            technical["resistance_60d"] = max(highs[:60])
            technical["support_60d"] = min(lows[:60])

        result["technical"] = technical

        # ── 5. 动量因子 ──
        momentum = {}
        for days, label in [(5, "5d"), (10, "10d"), (20, "20d"), (60, "60d")]:
            if len(closes) > days:
                try:
                    momentum[f"mom_{label}"] = round(
                        factor_calculator.calculate_momentum(closes, days), 4
                    )
                except Exception:
                    pass
        market_regime = "neutral"
        if momentum.get("mom_20d") is not None:
            if momentum["mom_20d"] >= 0.05:
                market_regime = "bullish"
            elif momentum["mom_20d"] <= -0.05:
                market_regime = "bearish"
        momentum["market_regime"] = market_regime
        result["momentum"] = momentum

        # ── 6. 风险指标 ──
        risk = {}
        if len(closes) >= 21:
            try:
                risk["volatility_20d"] = round(
                    factor_calculator.calculate_volatility(closes, 20), 4
                )
            except Exception:
                pass
        if len(closes) >= 61:
            try:
                risk["volatility_60d"] = round(
                    factor_calculator.calculate_volatility(closes, 60), 4
                )
            except Exception:
                pass
        # 最大回撤（近 250 日）
        if len(closes) >= 20:
            import numpy as np
            cum_prices = np.array(closes[:min(250, len(closes))])
            # 注意：klines 是倒序（最近在前），需要反转
            cum_prices = cum_prices[::-1]
            peak = np.maximum.accumulate(cum_prices)
            dd = (peak - cum_prices) / peak
            risk["max_drawdown_250d"] = round(float(np.max(dd)), 4)
        if len(closes) >= 21:
            rets = np.diff(np.array(closes[:21][::-1])) / np.maximum(np.array(closes[:21][::-1])[:-1], 1e-12)
            neg_rets = rets[rets < 0]
            if len(neg_rets) > 0:
                risk["downside_volatility_20d"] = round(float(np.std(neg_rets)), 4)

        result["risk"] = risk

        return ok(result)

    except Exception as e:
        return fail(str(e))

