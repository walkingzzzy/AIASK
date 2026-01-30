"""决策工具"""

from ..storage import get_db
from ..services import technical_analysis
from ..services.factor_calculator import factor_calculator
from ..utils import ok, fail
import statistics


def register(mcp):
    """注册决策工具"""
    
    @mcp.tool()
    async def should_i_buy(
        code: str,
        investment_style: str = 'balanced'
    ):
        """
        买入建议 - 综合估值、技术、基本面、因子分析
        
        Args:
            code: 股票代码
            investment_style: 投资风格 ('aggressive'激进, 'balanced'平衡, 'conservative'保守)
        """
        try:
            db = get_db()
            
            # 1. 获取基础信息
            stock_info = await db.get_stock_info(code)
            if not stock_info:
                return fail(f'Stock {code} not found')
            
            # 2. 获取K线数据
            klines = await db.get_klines(code, limit=100)
            if not klines or len(klines) < 20:
                return fail('Insufficient kline data')
            
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
            elif pe and 15 <= pe < 30:
                reasons.append(f'估值合理(PE={pe:.1f})')
                score += 15
                confidence += 10
            elif pe and pe >= 50:
                risks.append(f'估值偏高(PE={pe:.1f})')
                score -= 15
            
            if pb and 0 < pb < 2:
                reasons.append(f'市净率偏低(PB={pb:.1f})')
                score += 20
                confidence += 10
            elif pb and pb > 5:
                risks.append(f'市净率偏高(PB={pb:.1f})')
                score -= 10
            
            # 4. 技术分析
            # RSI
            rsi_result = technical_analysis.TechnicalAnalysis.calculate_rsi(closes)
            if rsi_result:
                rsi_value = rsi_result[-1] if isinstance(rsi_result, list) else rsi_result.get('value', 50)
                if rsi_value < 30:
                    reasons.append(f'RSI超卖({rsi_value:.1f})，可能反弹')
                    score += 20
                    confidence += 15
                elif rsi_value > 70:
                    risks.append(f'RSI超买({rsi_value:.1f})，短期风险')
                    score -= 15
            
            # MACD
            macd_result = technical_analysis.TechnicalAnalysis.calculate_macd(closes)
            if macd_result and 'histogram' in macd_result:
                hist = macd_result['histogram']
                if len(hist) >= 2:
                    if hist[-2] < 0 and hist[-1] > 0:
                        reasons.append('MACD金叉，买入信号')
                        score += 25
                        confidence += 20
                    elif hist[-2] > 0 and hist[-1] < 0:
                        risks.append('MACD死叉，卖出信号')
                        score -= 20
            
            # 均线趋势
            ma20 = technical_analysis.TechnicalAnalysis.calculate_sma(closes, 20)
            ma60 = technical_analysis.TechnicalAnalysis.calculate_sma(closes, 60)
            if ma20 and ma60 and len(ma20) > 0 and len(ma60) > 0:
                if closes[-1] > ma20[-1] > ma60[-1]:
                    reasons.append('多头排列，趋势向上')
                    score += 20
                    confidence += 15
                elif closes[-1] < ma20[-1] < ma60[-1]:
                    risks.append('空头排列，趋势向下')
                    score -= 20
            
            # 成交量
            recent_vol = statistics.mean(volumes[:5])
            avg_vol = statistics.mean(volumes)
            if recent_vol > avg_vol * 1.5:
                reasons.append('成交量放大，资金关注')
                score += 15
                confidence += 10
            
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
                        elif roe > 0.10:
                            reasons.append(f'ROE良好({roe*100:.1f}%)')
                            score += 10
                        
                        debt_ratio = float(financial_row['debt_ratio']) if financial_row['debt_ratio'] else 0
                        if debt_ratio > 0.7:
                            risks.append(f'负债率较高({debt_ratio*100:.1f}%)')
                            score -= 10
                        
                        revenue_growth = float(financial_row['revenue_growth']) if financial_row['revenue_growth'] else 0
                        if revenue_growth > 0.2:
                            reasons.append(f'营收高增长({revenue_growth*100:.1f}%)')
                            score += 20
                            confidence += 15
            except:
                pass
            
            # 6. 因子分析
            try:
                momentum = factor_calculator.calculate_momentum(closes)
                if momentum > 0.1:
                    reasons.append('动量因子强势')
                    score += 15
                elif momentum < -0.1:
                    risks.append('动量因子弱势')
                    score -= 10
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
            
            return ok({
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
                'analysis_date': klines[0].get('date', '')
            })
        
        except Exception as e:
            return fail(str(e))
    
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
            rsi_result = technical_analysis.TechnicalAnalysis.calculate_rsi(closes)
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
            macd_result = technical_analysis.TechnicalAnalysis.calculate_macd(closes)
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
            ma20 = technical_analysis.TechnicalAnalysis.calculate_sma(closes, 20)
            ma60 = technical_analysis.TechnicalAnalysis.calculate_sma(closes, 60)
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
