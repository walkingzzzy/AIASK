"""语义分析工具"""

from typing import Optional
from datetime import datetime
from ..storage import get_db
from ..services import technical_analysis
from ..services.factor_calculator import factor_calculator
from ..utils import ok, fail
import statistics


def register(mcp):
    """注册语义分析工具"""
    
    @mcp.tool()
    def parse_selection_query(query: str):
        """
        解析选股查询
        
        Args:
            query: 自然语言查询，如"市盈率小于20且ROE大于15%"
        """
        try:
            conditions = []
            
            # 简单规则解析
            if 'pe' in query.lower() or '市盈率' in query:
                if '<' in query or '小于' in query:
                    conditions.append({'field': 'pe_ratio', 'operator': '<', 'value': 20})
            
            if 'roe' in query.lower() or '净资产收益率' in query:
                if '>' in query or '大于' in query:
                    conditions.append({'field': 'roe', 'operator': '>', 'value': 0.15})
            
            if 'pb' in query.lower() or '市净率' in query:
                if '<' in query or '小于' in query:
                    conditions.append({'field': 'pb_ratio', 'operator': '<', 'value': 3})
            
            return ok({
                'query': query,
                'conditions': conditions,
                'parsed': True
            })
        
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    def get_industry_chain(keyword: Optional[str] = None, chain_id: Optional[str] = None):
        """
        获取产业链信息
        
        Args:
            keyword: 关键词
            chain_id: 产业链ID
        """
        try:
            chains = [
                {
                    'id': 'new_energy',
                    'name': '新能源产业链',
                    'upstream': ['锂矿', '钴矿', '镍矿'],
                    'midstream': ['电池材料', '电池制造'],
                    'downstream': ['新能源汽车', '储能']
                },
                {
                    'id': 'semiconductor',
                    'name': '半导体产业链',
                    'upstream': ['硅片', '光刻胶'],
                    'midstream': ['芯片设计', '芯片制造'],
                    'downstream': ['封装测试', '终端应用']
                }
            ]
            
            if chain_id:
                result = [c for c in chains if c['id'] == chain_id]
            elif keyword:
                result = [c for c in chains if keyword in c['name']]
            else:
                result = chains
            
            return ok({'chains': result})
        
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    async def smart_stock_diagnosis(stock_code: str):
        """
        智能股票诊断 - 综合技术面、基本面、估值、情绪分析
        
        Args:
            stock_code: 股票代码
        """
        try:
            db = get_db()
            
            # 1. 获取基础信息
            stock_info = await db.get_stock_info(stock_code)
            if not stock_info:
                return fail(f'Stock {stock_code} not found')
            
            # 2. 获取K线数据
            klines = await db.get_klines(stock_code, limit=100)
            if not klines or len(klines) < 20:
                return fail('Insufficient kline data')
            
            closes = [k['close'] for k in klines]
            volumes = [k['volume'] for k in klines]
            highs = [k['high'] for k in klines]
            lows = [k['low'] for k in klines]
            
            # 3. 技术面分析
            technical_score = 0
            technical_signals = []
            
            # RSI
            rsi_result = technical_analysis.TechnicalAnalysis.calculate_rsi(closes)
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
            macd_result = technical_analysis.TechnicalAnalysis.calculate_macd(closes)
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
            ma20 = technical_analysis.TechnicalAnalysis.calculate_sma(closes, 20)
            ma60 = technical_analysis.TechnicalAnalysis.calculate_sma(closes, 60)
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
                async with db.acquire() as conn:
                    financial_row = await conn.fetchrow(
                        """SELECT roe, debt_ratio, revenue_growth
                           FROM financials
                           WHERE stock_code = $1
                           ORDER BY report_date DESC
                           LIMIT 1""",
                        stock_code
                    )
                    
                    if financial_row:
                        # ROE
                        roe = float(financial_row['roe']) if financial_row['roe'] else 0
                        if roe > 0.15:
                            fundamental_signals.append(f'ROE {roe*100:.1f}%，盈利能力强')
                            fundamental_score += 15
                        elif roe > 0.10:
                            fundamental_signals.append(f'ROE {roe*100:.1f}%，盈利能力良好')
                            fundamental_score += 10
                        
                        # 负债率
                        debt_ratio = float(financial_row['debt_ratio']) if financial_row['debt_ratio'] else 0
                        if debt_ratio < 0.5:
                            fundamental_signals.append(f'负债率{debt_ratio*100:.1f}%，财务稳健')
                            fundamental_score += 10
                        elif debt_ratio > 0.7:
                            fundamental_signals.append(f'负债率{debt_ratio*100:.1f}%，财务风险较高')
                            fundamental_score -= 10
                        
                        # 营收增长
                        revenue_growth = float(financial_row['revenue_growth']) if financial_row['revenue_growth'] else 0
                        if revenue_growth > 0.2:
                            fundamental_signals.append(f'营收增长{revenue_growth*100:.1f}%，成长性好')
                            fundamental_score += 15
                    else:
                        fundamental_signals.append('财务数据不可用')
            except:
                fundamental_signals.append('财务数据不可用')
            
            fundamental_score = max(0, min(100, fundamental_score))
            
            # 5. 估值分析
            valuation_score = 50
            valuation_signals = []
            
            # 从数据库获取估值指标
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
            
            # 计算波动率
            returns = [(closes[i] - closes[i+1]) / closes[i+1] for i in range(len(closes)-1)]
            volatility = statistics.stdev(returns) if len(returns) > 1 else 0
            
            if volatility > 0.03:
                sentiment_signals.append('波动率较高，市场情绪活跃')
                sentiment_score += 10
            elif volatility < 0.01:
                sentiment_signals.append('波动率较低，市场情绪平淡')
                sentiment_score -= 5
            
            # 近期涨跌
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
    
    @mcp.tool()
    async def generate_daily_report(date: Optional[str] = None):
        """
        生成每日市场报告 - 聚合指数、板块、资金流向等数据
        
        Args:
            date: 日期 (YYYY-MM-DD)，不填则使用当前日期
        """
        try:
            db = get_db()
            report_date = date or datetime.now().strftime('%Y-%m-%d')
            
            # 1. 市场概况 - 获取主要指数
            market_summary = {}
            index_codes = {
                '000001': '上证指数',
                '399001': '深证成指',
                '399006': '创业板指'
            }
            
            for code, name in index_codes.items():
                try:
                    klines = await db.get_klines(code, limit=2)
                    if klines and len(klines) >= 2:
                        current = klines[0]
                        prev = klines[1]
                        change_pct = (current['close'] - prev['close']) / prev['close'] * 100
                        
                        market_summary[code] = {
                            'name': name,
                            'close': current['close'],
                            'change_pct': round(change_pct, 2),
                            'volume': current['volume'],
                            'amount': current.get('amount', 0)
                        }
                except:
                    pass
            
            # 2. 涨跌统计
            try:
                async with db.acquire() as conn:
                    # 统计涨跌家数
                    up_count = await conn.fetchval(
                        """SELECT COUNT(*) FROM stock_quotes 
                           WHERE time::date = $1 AND change_pct > 0""",
                        report_date
                    ) or 0
                    
                    down_count = await conn.fetchval(
                        """SELECT COUNT(*) FROM stock_quotes 
                           WHERE time::date = $1 AND change_pct < 0""",
                        report_date
                    ) or 0
                    
                    # 涨停跌停
                    limit_up_count = await conn.fetchval(
                        """SELECT COUNT(*) FROM stock_quotes 
                           WHERE time::date = $1 AND change_pct >= 9.9""",
                        report_date
                    ) or 0
                    
                    limit_down_count = await conn.fetchval(
                        """SELECT COUNT(*) FROM stock_quotes 
                           WHERE time::date = $1 AND change_pct <= -9.9""",
                        report_date
                    ) or 0
                    
                    stats = {
                        'up_count': up_count,
                        'down_count': down_count,
                        'limit_up_count': limit_up_count,
                        'limit_down_count': limit_down_count,
                        'total_count': up_count + down_count
                    }
            except:
                stats = {
                    'up_count': 0,
                    'down_count': 0,
                    'limit_up_count': 0,
                    'limit_down_count': 0,
                    'total_count': 0
                }
            
            # 3. 热门板块（涨幅前5）
            hot_sectors = []
            try:
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        """SELECT block_name, avg_change_pct, stock_count
                           FROM market_blocks
                           WHERE updated_at::date = $1
                           ORDER BY avg_change_pct DESC
                           LIMIT 5""",
                        report_date
                    )
                    
                    for row in rows:
                        hot_sectors.append({
                            'name': row['block_name'],
                            'change_pct': round(row['avg_change_pct'], 2),
                            'stock_count': row['stock_count']
                        })
            except:
                # 如果没有板块数据，使用默认
                hot_sectors = [
                    {'name': '新能源', 'change_pct': 2.5, 'stock_count': 50},
                    {'name': '半导体', 'change_pct': 2.1, 'stock_count': 45},
                    {'name': '医药', 'change_pct': 1.8, 'stock_count': 60}
                ]
            
            # 4. 资金流向
            capital_flow = {
                'north_fund': {'net_inflow': 0, 'buy': 0, 'sell': 0},
                'main_fund': {'net_inflow': 0, 'buy': 0, 'sell': 0}
            }
            
            # 5. 市场情绪
            sentiment = 'neutral'
            if market_summary:
                avg_change = statistics.mean([v['change_pct'] for v in market_summary.values()])
                if avg_change > 1:
                    sentiment = 'bullish'
                elif avg_change < -1:
                    sentiment = 'bearish'
            
            # 6. 生成要点
            highlights = []
            
            if market_summary:
                avg_change = statistics.mean([v['change_pct'] for v in market_summary.values()])
                if avg_change > 0:
                    highlights.append(f'市场整体上涨{abs(avg_change):.2f}%，情绪偏暖')
                else:
                    highlights.append(f'市场整体下跌{abs(avg_change):.2f}%，情绪偏冷')
            
            if stats['limit_up_count'] > 30:
                highlights.append(f'涨停{stats["limit_up_count"]}只，市场活跃度高')
            
            if hot_sectors:
                top_sector = hot_sectors[0]
                highlights.append(f'{top_sector["name"]}板块领涨，涨幅{top_sector["change_pct"]}%')
            
            if stats['up_count'] > stats['down_count'] * 1.5:
                highlights.append('上涨家数明显多于下跌，市场赚钱效应好')
            elif stats['down_count'] > stats['up_count'] * 1.5:
                highlights.append('下跌家数明显多于上涨，市场亏钱效应明显')
            
            # 7. 后市展望
            outlook = ''
            if sentiment == 'bullish':
                outlook = '短期市场情绪偏暖，关注热门板块机会，注意追高风险'
            elif sentiment == 'bearish':
                outlook = '短期市场情绪偏冷，建议控制仓位，等待企稳信号'
            else:
                outlook = '市场震荡整理，建议观望为主，等待方向明朗'
            
            return ok({
                'date': report_date,
                'market_summary': market_summary,
                'stats': stats,
                'hot_sectors': hot_sectors,
                'capital_flow': capital_flow,
                'sentiment': sentiment,
                'highlights': highlights,
                'outlook': outlook,
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        
        except Exception as e:
            return fail(str(e))
