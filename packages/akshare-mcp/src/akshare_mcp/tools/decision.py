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
from ..services.decision_contracts import (
    get_unified_decision_details_payload,
    get_unified_decision_summary_payload,
)
from ..services.decision_context_builder import (
    build_stock_context as _build_stock_context,
    build_user_context as _build_user_context,
)
from ..services.decision_quant_builder import build_quant_context as _build_quant_context
from ..services.decision_event_builder import build_event_context as _build_event_context
from ..services.decision_rule_gate import build_rule_gates as _build_rule_gates
from ..services.decision_fusion import fuse_unified_decision as _fuse_unified_decision
from ..services.factor_calculator import factor_calculator
from ..utils import ok, fail, resolve_security_code
import asyncio
import statistics
import time

from .decision_helpers import (
    _maybe_float,
    _clamp,
    _estimate_volatility,
    _calibrate_buy_probability,
    _estimate_target_price,
    _build_threshold_backtest,
    _build_probability_quality,
    _build_prediction_interval,
    _context_section,
    _derive_contextual_decision,
    _filter_klines_by_as_of,
)
from . import investment_analysis as investment_analysis_mod
from .investment_analysis import get_investment_analysis as _raw_get_investment_analysis


_monkey_patch_lock = asyncio.Lock()


async def get_investment_analysis(
    code: str | None = None,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
) -> dict:
    """兼容导出：默认将 decision.get_db 透传到 investment_analysis 模块。"""
    code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
    if not code:
        return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
    async with _monkey_patch_lock:
        original_get_db = getattr(investment_analysis_mod, 'get_db', None)
        investment_analysis_mod.get_db = get_db
        try:
            return await _raw_get_investment_analysis(code)
        finally:
            if original_get_db is not None:
                investment_analysis_mod.get_db = original_get_db


def register(mcp):
    """注册决策工具"""

    @mcp.tool()
    async def should_i_buy(
        code: str | None = None,
        investment_style: str = 'balanced',
        as_of: str = '',
        adjust: str = '',
        price_source_policy: str = 'auto',
        explain: bool = True,
        strict_mode: bool = False,
        stock_code: str | None = None,
        symbol: str | None = None,
        ticker: str | None = None,
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
        code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
        if not code:
            return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
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
            klines, pit_guard = _filter_klines_by_as_of(klines, as_of)
            if not klines or len(klines) < 20:
                return _fail('Insufficient kline data')

            closes = [k['close'] for k in klines]
            volumes = [k['volume'] for k in klines]
            latest_kline = max(
                klines,
                key=lambda item: str(item.get('date') or item.get('trade_date') or item.get('timestamp') or ''),
            )
            analysis_date = (
                latest_kline.get('date')
                or latest_kline.get('trade_date')
                or latest_kline.get('timestamp')
                or ''
            )
            current_price = float(latest_kline.get('close') or closes[-1])
            time_precision = 'historical_eod_close_as_of' if pit_guard.get('active') else 'historical_eod_close'

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
            recent_vol = statistics.mean(volumes[-5:])
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

            if context_decision and recommendation in {'hold', 'wait'}:
                recommendation = context_decision["recommendation"]
                action_text = context_decision["action_text"]
                for item in context_decision["positives"]:
                    if item not in reasons:
                        reasons.append(item)
                for item in context_decision["negatives"]:
                    if item not in risks:
                        risks.append(item)

            # 9. 目标价位（优先行业中位数PE估值法）
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
                closes=closes,
                thresholds=[40, 60, 80],
                horizon=10,
            )
            prediction_quality = _build_probability_quality(
                current_score=float(score),
                buy_probability=float(buy_probability),
                selected_threshold=int(threshold['buy']),
                threshold_backtest=threshold_backtest,
            )
            prediction_interval = _build_prediction_interval(
                closes=closes,
                current_score=float(score),
                thresholds=[40, 60, 80],
                horizon=10,
                confidence=0.8,
            )

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
                'time_precision': time_precision,
                'price_basis': 'kline_latest_close',
                'pit_guard': pit_guard,
                'failed_modules': ([f"investment_analysis:{context_error}"] if context_error else []),
                'decision_probability': {
                    'buy_probability': round(float(buy_probability), 4),
                    'buy_probability_pct': f"{buy_probability * 100:.2f}%",
                    'band': probability_band,
                    'method': 'logit(score,confidence,volatility)',
                },
                'prediction_quality': prediction_quality,
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
            if prediction_interval is not None:
                payload['prediction_interval'] = prediction_interval

            # 离线决策评估基线（benchmark_delta = hit_rate - historical_avg）
            empirical_hit_rate = prediction_quality.get('empirical_hit_rate')
            historical_positive_rate = 0.45  # A 股经验基准：约 45% 的情况下 5d 收益 > 0
            benchmark_delta = (
                round(float(empirical_hit_rate) - historical_positive_rate, 4)
                if empirical_hit_rate is not None else None
            )
            payload['offline_decision_baseline'] = {
                'recommendation': recommendation,
                'hit_rate': empirical_hit_rate,
                'benchmark_delta': benchmark_delta,
                'historical_positive_rate': historical_positive_rate,
                'method': 'decision_threshold_bucket_backtest_proxy',
                'support_samples': prediction_quality.get('support_samples', 0),
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
            result['meta']['time_precision'] = time_precision
            result['meta']['price_basis'] = 'kline_latest_close'
            result['meta']['pit_guard'] = pit_guard
            result['meta']['evidence_chain_saved'] = bool(payload.get('evidence_trace_id'))
            return result

        except Exception as e:
            return _fail(str(e))

    @mcp.tool()
    async def should_i_sell(
        code: str | None = None,
        buy_price: float = 0.0,
        holding_days: int = 0,
        stock_code: str | None = None,
        symbol: str | None = None,
        ticker: str | None = None,
    ):
        """
        卖出建议 - 综合止盈止损、技术信号、持仓时间分析

        Args:
            code: 股票代码
            buy_price: 买入价格
            holding_days: 持有天数
        """
        try:
            code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
            if not code:
                return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
            # buy_price <= 0 视为「未提供买入价」，降级为纯技术分析，不再直接拒绝
            has_buy_price = buy_price > 0
            db = get_db()

            # 1. 获取基础信息
            stock_info = await db.get_stock_info(code)
            if not stock_info:
                return fail(f'Stock {code} not found')

            # 2. 获取K线数据
            klines = await db.get_klines(code, limit=100)
            if not klines:
                return fail('No kline data')

            current_price = klines[-1]['close']
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

            # 3. 计算盈亏（仅在提供买入价时）
            if has_buy_price:
                profit_pct = (current_price - buy_price) / buy_price * 100
                profit_amount = current_price - buy_price
            else:
                profit_pct = 0.0
                profit_amount = 0.0

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

            # 4. 止盈止损分析（仅在提供买入价时）
            if has_buy_price:
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
                    if not has_buy_price or profit_pct < 5:
                        _apply_sell_signal('holding', f'持仓{holding_days}天收益不佳，考虑换股', 15, source='direct_holding')

            # 7. 波动风险
            volatility = _maybe_float(risk_ctx.get('volatility_20d'))
            if volatility is None:
                recent_window = closes[-21:] if len(closes) >= 21 else closes
                returns = [
                    (recent_window[i + 1] - recent_window[i]) / recent_window[i]
                    for i in range(max(len(recent_window) - 1, 0))
                    if recent_window[i] > 0
                ]
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
                if not has_buy_price or profit_pct > 0:
                    target_sell_price = current_price
                else:
                    target_sell_price = buy_price * 0.95  # 回本95%

            payload = {
                'code': code,
                'name': stock_info.get('name', ''),
                'recommendation': recommendation,
                'decision_mode': 'hybrid_score_plus_context',
                'action_text': action_text,
                'score': score,
                'current_price': current_price,
                'buy_price': buy_price if has_buy_price else None,
                'profit_pct': round(profit_pct, 2) if has_buy_price else None,
                'profit_amount': round(profit_amount, 2) if has_buy_price else None,
                'holding_days': holding_days if holding_days > 0 else None,
                'target_sell_price': round(target_sell_price, 2) if target_sell_price else None,
                'reasons': reasons,
                'risks': risks,
                'score_breakdown': {k: round(float(v), 2) for k, v in score_breakdown.items()},
                'signal_breakdown': signal_breakdown,
                'analysis_date': klines[-1].get('date', ''),
                'failed_modules': ([f"investment_analysis:{context_error}"] if context_error else []),
                'analysis_mode': 'technical_only' if not has_buy_price else 'full',
            }

            if analysis_context:
                payload['analysis_context'] = analysis_context

            return ok(payload)

        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def build_stock_context(
        code: str | None = None,
        stock_code: str | None = None,
        symbol: str | None = None,
        ticker: str | None = None,
    ):
        """构建股票上下文：基础骨架 + 行情快照 + 资金流 + 产业链。"""
        try:
            code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
            if not code:
                return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
            return ok(await _build_stock_context(code))
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def build_quant_context(
        code: str | None = None,
        stock_code: str | None = None,
        symbol: str | None = None,
        ticker: str | None = None,
    ):
        """构建量化上下文：因子画像 + 条件收益 + 相似形态 + OOS 验证。"""
        try:
            code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
            if not code:
                return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
            return ok(await _build_quant_context(code))
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def build_event_context(
        code: str | None = None,
        stock_code: str | None = None,
        symbol: str | None = None,
        ticker: str | None = None,
        news_limit: int = 12,
        notice_days: int = 30,
        report_limit: int = 6,
    ):
        """构建事件上下文：新闻/公告/研报聚合、事件分类与 veto 候选。"""
        try:
            code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
            if not code:
                return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
            return ok(
                await _build_event_context(
                    code,
                    news_limit=news_limit,
                    notice_days=notice_days,
                    report_limit=report_limit,
                )
            )
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def run_decision_gate(
        code: str | None = None,
        investment_style: str = 'balanced',
        user_id: str | None = None,
        stock_context: dict | None = None,
        quant_context: dict | None = None,
        event_context: dict | None = None,
        user_context: dict | None = None,
        stock_code: str | None = None,
        symbol: str | None = None,
        ticker: str | None = None,
    ):
        """运行统一决策规则闸门，可传入现成上下文，也可按代码自动构建。"""
        try:
            code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
            if not code:
                return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
            built_stock = stock_context if isinstance(stock_context, dict) else await _build_stock_context(code)
            built_quant = quant_context if isinstance(quant_context, dict) else await _build_quant_context(code)
            built_event = event_context if isinstance(event_context, dict) else await _build_event_context(code)
            built_user = user_context if isinstance(user_context, dict) else await _build_user_context(user_id)
            gate = _build_rule_gates(
                code=code,
                investment_style=investment_style,
                stock_context=built_stock,
                quant_context=built_quant,
                event_context=built_event,
                user_context=built_user,
            )
            return ok(gate)
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def fuse_decision_payload(
        code: str | None = None,
        investment_style: str = 'balanced',
        user_id: str | None = None,
        stock_context: dict | None = None,
        quant_context: dict | None = None,
        event_context: dict | None = None,
        user_context: dict | None = None,
        gate: dict | None = None,
        stock_code: str | None = None,
        symbol: str | None = None,
        ticker: str | None = None,
    ):
        """融合统一决策上下文，输出 action/summary/weights/raw_ai_output。"""
        try:
            code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
            if not code:
                return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
            built_stock = stock_context if isinstance(stock_context, dict) else await _build_stock_context(code)
            built_quant = quant_context if isinstance(quant_context, dict) else await _build_quant_context(code)
            built_event = event_context if isinstance(event_context, dict) else await _build_event_context(code)
            built_user = user_context if isinstance(user_context, dict) else await _build_user_context(user_id)
            built_gate = gate if isinstance(gate, dict) else _build_rule_gates(
                code=code,
                investment_style=investment_style,
                stock_context=built_stock,
                quant_context=built_quant,
                event_context=built_event,
                user_context=built_user,
            )
            return ok(
                _fuse_unified_decision(
                    stock_context=built_stock,
                    quant_context=built_quant,
                    event_context=built_event,
                    user_context=built_user,
                    gate=built_gate,
                )
            )
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def get_unified_decision_summary(
        code: str | None = None,
        investment_style: str = 'balanced',
        user_id: str | None = None,
        stock_code: str | None = None,
        symbol: str | None = None,
        ticker: str | None = None,
    ):
        """统一决策摘要：输出前端友好的 summary 卡片。"""
        try:
            code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
            if not code:
                return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
            payload = await get_unified_decision_summary_payload(
                code=code,
                investment_style=investment_style,
                user_id=user_id,
            )
            return ok(payload)
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def get_unified_decision_details(
        code: str | None = None,
        investment_style: str = 'balanced',
        user_id: str | None = None,
        stock_code: str | None = None,
        symbol: str | None = None,
        ticker: str | None = None,
    ):
        """统一决策详情：输出 summary + 全量 details 证据。"""
        try:
            code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
            if not code:
                return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
            payload = await get_unified_decision_details_payload(
                code=code,
                investment_style=investment_style,
                user_id=user_id,
            )
            return ok(payload)
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def get_unified_decision(
        code: str | None = None,
        detail_level: str = 'summary',
        investment_style: str = 'balanced',
        user_id: str | None = None,
        stock_code: str | None = None,
        symbol: str | None = None,
        ticker: str | None = None,
    ):
        """统一决策兼容包装器：按 detail_level 返回 summary 或 details。"""
        try:
            code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
            if not code:
                return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
            if str(detail_level or 'summary').strip().lower() == 'details':
                payload = await get_unified_decision_details_payload(
                    code=code,
                    investment_style=investment_style,
                    user_id=user_id,
                )
            else:
                payload = await get_unified_decision_summary_payload(
                    code=code,
                    investment_style=investment_style,
                    user_id=user_id,
                )
            return ok(payload)
        except Exception as e:
            return fail(str(e))

    # Phase 2：显式暴露纯数据汇聚工具，避免只有硬编码评分入口。
    mcp.tool()(get_investment_analysis)
