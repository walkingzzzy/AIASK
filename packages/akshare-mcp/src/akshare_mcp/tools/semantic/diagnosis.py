"""智能股票诊断 — smart_stock_diagnosis"""

import statistics
from datetime import datetime
from ...storage import get_db
from ...services import technical_analysis
from ...utils import ok, fail, normalize_code
from ...data_source import data_source
from ..market import get_kline


async def smart_stock_diagnosis(stock_code: str):
    """
    智能股票诊断 - 综合技术面、基本面、估值、情绪四维分析并给出投资建议

    数据源优先级: TimescaleDB → TDX → AkShare/Tushare（降级）

    Args:
        stock_code (str, required): 股票代码，6位数字，如 "600519"

    Returns:
        dict: {"success": bool, "data": {
            "code": str, "name": str,
            "overall_score": float,                # 综合评分 0-100
            "recommendation": str,                 # "buy"|"hold"|"wait"|"sell"
            "recommendation_text": str,            # 中文建议
            "scores": {"technical": float, "fundamental": float, "valuation": float, "sentiment": float},
            "analysis": {"technical": list[str], "fundamental": list[str], "valuation": list[str], "sentiment": list[str]},
            "risks": list[str],                    # 风险提示
            "current_price": float,
            "analysis_date": str
        }}

    Errors:
        - 股票代码不存在时返回 "Stock {code} not found"
        - K线数据不足20条时返回 "Insufficient kline data"

    Examples:
        smart_stock_diagnosis("600519")
        smart_stock_diagnosis("000001")
    """
    try:
        db = get_db()
        code = normalize_code(stock_code)

        # 1. 获取基础信息
        stock_info = await db.get_stock_info(code)
        if not stock_info:
            stock_info = data_source.get_stock_info_priority_tdx(code)
        if not stock_info:
            return fail(f'Stock {stock_code} not found')

        # 2. 获取K线数据
        klines = await db.get_klines(code, limit=100)
        if not klines or len(klines) < 20:
            res = get_kline(code, 'daily', 100)
            if res.get('success') and res.get('data'):
                klines = res['data']
        if not klines or len(klines) < 20:
            return fail('Insufficient kline data')
        klines = sorted(klines, key=lambda x: x.get('date') or '')
        closes = [k['close'] for k in klines]
        volumes = [k['volume'] for k in klines]

        # 3. 技术面分析
        technical_score = 0
        technical_signals = []

        # RSI
        rsi_result = technical_analysis.calculate_rsi(closes)
        if rsi_result:
            rsi_value = rsi_result[-1] if isinstance(rsi_result, list) else rsi_result.get('value', 50)
            if rsi_value < 30:
                technical_signals.append('RSI超卖，可能反弹')
                technical_score += 20
            elif rsi_value > 70:
                technical_signals.append('RSI超买，注意回调风险')
                technical_score -= 10
            else:
                technical_signals.append('RSI正常区间')
                technical_score += 10

        # MACD
        macd_result = technical_analysis.calculate_macd(closes)
        if macd_result and 'histogram' in macd_result:
            hist = macd_result['histogram']
            if len(hist) >= 2:
                if hist[-2] < 0 and hist[-1] > 0:
                    technical_signals.append('MACD金叉，买入信号')
                    technical_score += 20
                elif hist[-2] > 0 and hist[-1] < 0:
                    technical_signals.append('MACD死叉，卖出信号')
                    technical_score -= 20

        # 均线
        ma20 = technical_analysis.calculate_sma(closes, 20)
        ma60 = technical_analysis.calculate_sma(closes, 60)
        if ma20 and ma60 and len(ma20) > 0 and len(ma60) > 0:
            if closes[-1] > ma20[-1] > ma60[-1]:
                technical_signals.append('多头排列，趋势向上')
                technical_score += 15
            elif closes[-1] < ma20[-1] < ma60[-1]:
                technical_signals.append('空头排列，趋势向下')
                technical_score -= 15

        # 成交量
        recent_vol = statistics.mean(volumes[:5])
        avg_vol = statistics.mean(volumes)
        if recent_vol > avg_vol * 1.5:
            technical_signals.append('成交量放大')
            technical_score += 10

        technical_score = max(0, min(100, 50 + technical_score))

        # 4. 基本面分析
        fundamental_score = 50
        fundamental_signals = []

        try:
            fin_list = await db.get_financials(code, limit=1)
            financial_row = fin_list[0] if fin_list else None
            if not financial_row:
                try:
                    from ..finance import _get_financials_akshare
                    fin = _get_financials_akshare(code)
                    if fin:
                        financial_row = fin
                except Exception:
                    pass
            if financial_row:
                roe = float(financial_row.get('roe') or 0)
                if abs(roe) > 1:
                    roe = roe / 100.0
                if roe > 0.15:
                    fundamental_signals.append(f'ROE {roe*100:.1f}%，盈利能力强')
                    fundamental_score += 15
                elif roe > 0.10:
                    fundamental_signals.append(f'ROE {roe*100:.1f}%，盈利能力良好')
                    fundamental_score += 10

                debt_ratio = float(financial_row.get('debt_ratio') or 0)
                if debt_ratio > 1:
                    debt_ratio = debt_ratio / 100.0
                if debt_ratio < 0.5:
                    fundamental_signals.append(f'负债率{debt_ratio*100:.1f}%，财务稳健')
                    fundamental_score += 10
                elif debt_ratio > 0.7:
                    fundamental_signals.append(f'负债率{debt_ratio*100:.1f}%，财务风险较高')
                    fundamental_score -= 10

                revenue_growth = float(financial_row.get('revenue_growth') or 0)
                if abs(revenue_growth) > 1:
                    revenue_growth = revenue_growth / 100.0
                if revenue_growth > 0.2:
                    fundamental_signals.append(f'营收增长{revenue_growth*100:.1f}%，成长性好')
                    fundamental_score += 15
            else:
                fundamental_signals.append('财务数据不可用')
        except Exception:
            fundamental_signals.append('财务数据不可用')

        fundamental_score = max(0, min(100, fundamental_score))

        # 5. 估值分析
        valuation_score = 50
        valuation_signals = []

        async with db.acquire() as conn:
            valuation_row = await conn.fetchrow(
                """SELECT pe_ratio, pb_ratio FROM stocks WHERE stock_code = $1""",
                stock_code
            )
            pe = float(valuation_row['pe_ratio']) if valuation_row and valuation_row['pe_ratio'] else 0
            pb = float(valuation_row['pb_ratio']) if valuation_row and valuation_row['pb_ratio'] else 0

        if pe and 0 < pe < 15:
            valuation_signals.append(f'PE {pe:.1f}，估值偏低')
            valuation_score += 20
        elif pe and pe > 50:
            valuation_signals.append(f'PE {pe:.1f}，估值偏高')
            valuation_score -= 20
        elif pe:
            valuation_signals.append(f'PE {pe:.1f}，估值合理')
            valuation_score += 10

        if pb and 0 < pb < 2:
            valuation_signals.append(f'PB {pb:.1f}，估值偏低')
            valuation_score += 15
        elif pb and pb > 5:
            valuation_signals.append(f'PB {pb:.1f}，估值偏高')
            valuation_score -= 15

        valuation_score = max(0, min(100, valuation_score))

        # 6. 情绪分析（基于价格波动）
        sentiment_score = 50
        sentiment_signals = []

        returns = [(closes[i] - closes[i+1]) / closes[i+1] for i in range(len(closes)-1)]
        volatility = statistics.stdev(returns) if len(returns) > 1 else 0

        if volatility > 0.03:
            sentiment_signals.append('波动率较高，市场情绪活跃')
            sentiment_score += 10
        elif volatility < 0.01:
            sentiment_signals.append('波动率较低，市场情绪平淡')
            sentiment_score -= 5

        recent_change = (closes[0] - closes[4]) / closes[4] if len(closes) > 4 else 0
        if recent_change > 0.1:
            sentiment_signals.append('近期大涨，市场情绪乐观')
            sentiment_score += 15
        elif recent_change < -0.1:
            sentiment_signals.append('近期大跌，市场情绪悲观')
            sentiment_score -= 15

        sentiment_score = max(0, min(100, sentiment_score))

        # 7. 综合评分
        overall_score = (
            technical_score * 0.3 +
            fundamental_score * 0.3 +
            valuation_score * 0.25 +
            sentiment_score * 0.15
        )

        # 8. 投资建议
        if overall_score >= 75:
            recommendation = 'buy'
            recommendation_text = '强烈推荐买入'
        elif overall_score >= 60:
            recommendation = 'hold'
            recommendation_text = '可以持有或适量买入'
        elif overall_score >= 45:
            recommendation = 'wait'
            recommendation_text = '观望为主'
        else:
            recommendation = 'sell'
            recommendation_text = '建议卖出或回避'

        # 9. 风险提示
        risks = []
        if technical_score < 40:
            risks.append('技术面偏弱')
        if fundamental_score < 40:
            risks.append('基本面欠佳')
        if valuation_score < 40:
            risks.append('估值偏高')
        if volatility > 0.04:
            risks.append('波动风险较大')

        return ok({
            'code': stock_code,
            'name': stock_info.get('name', ''),
            'overall_score': round(overall_score, 1),
            'recommendation': recommendation,
            'recommendation_text': recommendation_text,
            'scores': {
                'technical': round(technical_score, 1),
                'fundamental': round(fundamental_score, 1),
                'valuation': round(valuation_score, 1),
                'sentiment': round(sentiment_score, 1)
            },
            'analysis': {
                'technical': technical_signals,
                'fundamental': fundamental_signals,
                'valuation': valuation_signals,
                'sentiment': sentiment_signals
            },
            'risks': risks,
            'current_price': closes[0],
            'analysis_date': datetime.now().strftime('%Y-%m-%d')
        })

    except Exception as e:
        return fail(str(e))
