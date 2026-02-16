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


def _calibrate_buy_probability(score: float, confidence: float, style: str, volatility: float) -> float:
    style_threshold = {
        "aggressive": 40.0,
        "balanced": 60.0,
        "conservative": 80.0,
    }.get(str(style or "balanced").lower(), 60.0)

    score_term = (float(score) - style_threshold) / 15.0
    confidence_term = (float(confidence) - 60.0) / 25.0
    vol_penalty = max(0.0, float(volatility) - 0.03) * 8.0
    logit = score_term + confidence_term - vol_penalty
    probability = 1.0 / (1.0 + math.exp(-logit))
    return float(_clamp(probability, 0.01, 0.99))


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
            
            reasons = []
            risks = []
            score = 0
            confidence = 0
            
            # 3. 估值分析（从数据库直接查询）
            async with db.acquire() as conn:
                valuation_row = await conn.fetchrow(
                    """SELECT pe_ratio, pb_ratio FROM stocks WHERE stock_code = $1""",
                    code
                )
                pe = float(valuation_row['pe_ratio']) if valuation_row and valuation_row['pe_ratio'] else 0
                pb = float(valuation_row['pb_ratio']) if valuation_row and valuation_row['pb_ratio'] else 0
            
            if pe and 0 < pe < 15:
                reasons.append(f'估值偏低(PE={pe:.1f})')
                score += 25
                confidence += 15
                _record_evidence("valuation", "pe_ratio", pe, 25, confidence_hint=0.75)
            elif pe and 15 <= pe < 30:
                reasons.append(f'估值合理(PE={pe:.1f})')
                score += 15
                confidence += 10
                _record_evidence("valuation", "pe_ratio", pe, 15, confidence_hint=0.65)
            elif pe and pe >= 50:
                risks.append(f'估值偏高(PE={pe:.1f})')
                score -= 15
                _record_evidence("valuation", "pe_ratio", pe, -15, confidence_hint=0.70)
            
            if pb and 0 < pb < 2:
                reasons.append(f'市净率偏低(PB={pb:.1f})')
                score += 20
                confidence += 10
                _record_evidence("valuation", "pb_ratio", pb, 20, confidence_hint=0.7)
            elif pb and pb > 5:
                risks.append(f'市净率偏高(PB={pb:.1f})')
                score -= 10
                _record_evidence("valuation", "pb_ratio", pb, -10, confidence_hint=0.65)
            
            # 4. 技术分析
            # RSI
            rsi_result = technical_analysis.calculate_rsi(closes)
            if rsi_result:
                rsi_value = rsi_result[-1] if isinstance(rsi_result, list) else rsi_result.get('value', 50)
                if rsi_value < 30:
                    reasons.append(f'RSI超卖({rsi_value:.1f})，可能反弹')
                    score += 20
                    confidence += 15
                    _record_evidence("technical", "rsi", float(rsi_value), 20, confidence_hint=0.75)
                elif rsi_value > 70:
                    risks.append(f'RSI超买({rsi_value:.1f})，短期风险')
                    score -= 15
                    _record_evidence("technical", "rsi", float(rsi_value), -15, confidence_hint=0.70)
            
            # MACD
            macd_result = technical_analysis.calculate_macd(closes)
            if macd_result and 'histogram' in macd_result:
                hist = macd_result['histogram']
                if len(hist) >= 2:
                    if hist[-2] < 0 and hist[-1] > 0:
                        reasons.append('MACD金叉，买入信号')
                        score += 25
                        confidence += 20
                        _record_evidence("technical", "macd_histogram", float(hist[-1]), 25, confidence_hint=0.8)
                    elif hist[-2] > 0 and hist[-1] < 0:
                        risks.append('MACD死叉，卖出信号')
                        score -= 20
                        _record_evidence("technical", "macd_histogram", float(hist[-1]), -20, confidence_hint=0.78)
            
            # 均线趋势
            ma20 = technical_analysis.calculate_sma(closes, 20)
            ma60 = technical_analysis.calculate_sma(closes, 60)
            if ma20 and ma60 and len(ma20) > 0 and len(ma60) > 0:
                if closes[-1] > ma20[-1] > ma60[-1]:
                    reasons.append('多头排列，趋势向上')
                    score += 20
                    confidence += 15
                    _record_evidence(
                        "technical",
                        "ma_trend",
                        {"close": float(closes[-1]), "ma20": float(ma20[-1]), "ma60": float(ma60[-1])},
                        20,
                        confidence_hint=0.75,
                    )
                elif closes[-1] < ma20[-1] < ma60[-1]:
                    risks.append('空头排列，趋势向下')
                    score -= 20
                    _record_evidence(
                        "technical",
                        "ma_trend",
                        {"close": float(closes[-1]), "ma20": float(ma20[-1]), "ma60": float(ma60[-1])},
                        -20,
                        confidence_hint=0.75,
                    )
            
            # 成交量
            recent_vol = statistics.mean(volumes[:5])
            avg_vol = statistics.mean(volumes)
            if recent_vol > avg_vol * 1.5:
                reasons.append('成交量放大，资金关注')
                score += 15
                confidence += 10
                _record_evidence(
                    "technical",
                    "volume_ratio",
                    float(recent_vol / avg_vol) if avg_vol else 0.0,
                    15,
                    confidence_hint=0.6,
                )
            
            # 5. 基本面分析
            try:
                async with db.acquire() as conn:
                    financial_row = await conn.fetchrow(
                        """SELECT roe, debt_ratio, revenue_growth
                           FROM financials
                           WHERE stock_code = $1
                           ORDER BY report_date DESC
                           LIMIT 1""",
                        code
                    )
                    
                    if financial_row:
                        roe = float(financial_row['roe']) if financial_row['roe'] else 0
                        if roe > 0.15:
                            reasons.append(f'ROE优秀({roe*100:.1f}%)')
                            score += 20
                            confidence += 10
                            _record_evidence("fundamental", "roe", roe, 20, confidence_hint=0.72)
                        elif roe > 0.10:
                            reasons.append(f'ROE良好({roe*100:.1f}%)')
                            score += 10
                            _record_evidence("fundamental", "roe", roe, 10, confidence_hint=0.65)
                        
                        debt_ratio = float(financial_row['debt_ratio']) if financial_row['debt_ratio'] else 0
                        if debt_ratio > 0.7:
                            risks.append(f'负债率较高({debt_ratio*100:.1f}%)')
                            score -= 10
                            _record_evidence("fundamental", "debt_ratio", debt_ratio, -10, confidence_hint=0.68)
                        
                        revenue_growth = float(financial_row['revenue_growth']) if financial_row['revenue_growth'] else 0
                        if revenue_growth > 0.2:
                            reasons.append(f'营收高增长({revenue_growth*100:.1f}%)')
                            score += 20
                            confidence += 15
                            _record_evidence("fundamental", "revenue_growth", revenue_growth, 20, confidence_hint=0.75)
            except:
                pass
            
            # 6. 因子分析
            try:
                momentum = factor_calculator.calculate_momentum(closes)
                if momentum > 0.1:
                    reasons.append('动量因子强势')
                    score += 15
                    _record_evidence("factor", "momentum", float(momentum), 15, confidence_hint=0.62)
                elif momentum < -0.1:
                    risks.append('动量因子弱势')
                    score -= 10
                    _record_evidence("factor", "momentum", float(momentum), -10, confidence_hint=0.62)
            except:
                pass
            
            # 7. 根据投资风格调整
            style_thresholds = {
                'aggressive': {'buy': 40, 'confidence': 50},
                'balanced': {'buy': 60, 'confidence': 60},
                'conservative': {'buy': 80, 'confidence': 70}
            }
            
            threshold = style_thresholds.get(investment_style, style_thresholds['balanced'])
            
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
            
            # 9. 目标价位（简单估算）
            current_price = closes[0]
            target_price = None
            if recommendation == 'buy':
                # 基于PE估算目标价
                if pe and 0 < pe < 50:
                    industry_avg_pe = pe * 1.2  # 假设行业平均PE高20%
                    target_price = current_price * (industry_avg_pe / pe)
                else:
                    target_price = current_price * 1.15  # 默认15%涨幅
            
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
                'action_text': action_text,
                'score': score,
                'confidence': round(confidence, 1),
                'current_price': current_price,
                'target_price': round(target_price, 2) if target_price else None,
                'reasons': reasons,
                'risks': risks,
                'investment_style': investment_style,
                'analysis_date': analysis_date,
                'failed_modules': [],
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
            
            # 3. 计算盈亏
            profit_pct = (current_price - buy_price) / buy_price * 100
            profit_amount = current_price - buy_price
            
            reasons = []
            risks = []
            score = 0  # 正分倾向卖出，负分倾向持有
            
            # 4. 止盈止损分析
            if profit_pct >= 30:
                reasons.append(f'盈利{profit_pct:.1f}%，建议止盈')
                score += 40
            elif profit_pct >= 20:
                reasons.append(f'盈利{profit_pct:.1f}%，可考虑部分止盈')
                score += 25
            elif profit_pct >= 10:
                reasons.append(f'盈利{profit_pct:.1f}%，持有为主')
                score += 5
            elif profit_pct <= -15:
                reasons.append(f'亏损{abs(profit_pct):.1f}%，建议止损')
                score += 35
            elif profit_pct <= -10:
                reasons.append(f'亏损{abs(profit_pct):.1f}%，考虑止损')
                score += 20
            elif profit_pct <= -5:
                risks.append(f'亏损{abs(profit_pct):.1f}%，注意风险')
                score += 10
            
            # 5. 技术分析
            # RSI
            rsi_result = technical_analysis.calculate_rsi(closes)
            if rsi_result:
                rsi_value = rsi_result[-1] if isinstance(rsi_result, list) else rsi_result.get('value', 50)
                if rsi_value > 80:
                    reasons.append(f'RSI严重超买({rsi_value:.1f})，建议卖出')
                    score += 25
                elif rsi_value > 70:
                    reasons.append(f'RSI超买({rsi_value:.1f})，考虑减仓')
                    score += 15
                elif rsi_value < 30:
                    risks.append(f'RSI超卖({rsi_value:.1f})，可能反弹')
                    score -= 15

            # MACD
            macd_result = technical_analysis.calculate_macd(closes)
            if macd_result and 'histogram' in macd_result:
                hist = macd_result['histogram']
                if len(hist) >= 2:
                    if hist[-2] > 0 and hist[-1] < 0:
                        reasons.append('MACD死叉，卖出信号')
                        score += 20
                    elif hist[-2] < 0 and hist[-1] > 0:
                        risks.append('MACD金叉，买入信号')
                        score -= 20

            # 均线
            ma20 = technical_analysis.calculate_sma(closes, 20)
            ma60 = technical_analysis.calculate_sma(closes, 60)
            if ma20 and ma60 and len(ma20) > 0 and len(ma60) > 0:
                if closes[-1] < ma20[-1] < ma60[-1]:
                    reasons.append('跌破均线，趋势转弱')
                    score += 20
                elif closes[-1] > ma20[-1] > ma60[-1]:
                    risks.append('多头排列，趋势向上')
                    score -= 15
            
            # 6. 持仓时间分析
            if holding_days > 0:
                if holding_days < 7:
                    risks.append(f'持仓仅{holding_days}天，建议再观察')
                    score -= 10
                elif holding_days > 180:
                    if profit_pct < 5:
                        reasons.append(f'持仓{holding_days}天收益不佳，考虑换股')
                        score += 15
            
            # 7. 波动风险
            returns = [(closes[i] - closes[i+1]) / closes[i+1] for i in range(min(20, len(closes)-1))]
            if len(returns) > 1:
                volatility = statistics.stdev(returns)
                if volatility > 0.04:
                    risks.append('近期波动较大，注意风险')
                    score += 10
            
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
            
            return ok({
                'code': code,
                'name': stock_info.get('name', ''),
                'recommendation': recommendation,
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
                'analysis_date': klines[0].get('date', '')
            })
        
        except Exception as e:
            return fail(str(e))
