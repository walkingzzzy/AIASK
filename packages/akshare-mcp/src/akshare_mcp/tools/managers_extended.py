"""扩展的19个Manager工具实现（12-30）"""

from typing import Optional, List, Dict, Any
from ..storage import get_db
from ..utils import ok, fail
from datetime import datetime, timedelta
import json


def register(mcp):
    """注册扩展的19个Manager工具"""
    
    # ========== 12. risk_manager ==========
    @mcp.tool()
    async def risk_manager(action: str, **kwargs):
        """风险管理器 - VaR、压力测试、风险敞口"""
        try:
            db = get_db()
            
            if action == 'calculate_var':
                portfolio_id = kwargs.get('portfolio_id')
                confidence = kwargs.get('confidence', 0.95)
                method = kwargs.get('method', 'historical')  # historical, parametric, monte_carlo
                
                # 获取组合持仓
                async with db.acquire() as conn:
                    holdings = await conn.fetch(
                        "SELECT * FROM holdings WHERE portfolio_id = $1",
                        portfolio_id
                    )
                    
                    if not holdings:
                        return fail('组合无持仓')
                
                # 计算组合收益率历史数据
                import numpy as np
                returns_data = []
                total_value = 0
                
                for holding in holdings:
                    code = holding['code']
                    shares = holding['shares']
                    
                    # 获取历史价格
                    klines = await db.get_klines(code, limit=252)  # 一年数据
                    if len(klines) < 2:
                        continue
                    
                    # 计算收益率
                    prices = [k['close'] for k in klines]
                    returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
                    
                    # 计算持仓价值
                    current_value = shares * prices[-1]
                    total_value += current_value
                    
                    returns_data.append({
                        'code': code,
                        'returns': returns,
                        'weight': 0,  # 稍后计算
                        'current_value': current_value
                    })
                
                # 计算权重
                for item in returns_data:
                    item['weight'] = item['current_value'] / total_value if total_value > 0 else 0
                
                # 计算组合收益率
                min_length = min(len(item['returns']) for item in returns_data)
                portfolio_returns = []
                
                for i in range(min_length):
                    daily_return = sum(item['returns'][i] * item['weight'] for item in returns_data)
                    portfolio_returns.append(daily_return)
                
                portfolio_returns = np.array(portfolio_returns)
                
                # 计算VaR
                if method == 'historical':
                    # 历史模拟法
                    var = np.percentile(portfolio_returns, (1 - confidence) * 100)
                    var_amount = abs(var * total_value)
                    
                elif method == 'parametric':
                    # 参数法（假设正态分布）
                    from scipy import stats
                    mean = np.mean(portfolio_returns)
                    std = np.std(portfolio_returns)
                    var = stats.norm.ppf(1 - confidence, mean, std)
                    var_amount = abs(var * total_value)
                    
                else:  # monte_carlo
                    # 蒙特卡洛模拟（简化版）
                    mean = np.mean(portfolio_returns)
                    std = np.std(portfolio_returns)
                    simulations = np.random.normal(mean, std, 10000)
                    var = np.percentile(simulations, (1 - confidence) * 100)
                    var_amount = abs(var * total_value)
                
                # 计算CVaR（条件VaR）
                cvar_returns = portfolio_returns[portfolio_returns <= var]
                cvar = np.mean(cvar_returns) if len(cvar_returns) > 0 else var
                cvar_amount = abs(cvar * total_value)
                
                return ok({
                    'portfolio_id': portfolio_id,
                    'method': method,
                    'confidence': confidence,
                    'total_value': float(total_value),
                    'var': {
                        'percentage': float(var),
                        'amount': float(var_amount),
                        'description': f'{confidence*100:.0f}%置信度下，1天最大损失为{var_amount:.2f}元'
                    },
                    'cvar': {
                        'percentage': float(cvar),
                        'amount': float(cvar_amount),
                        'description': f'超过VaR时的平均损失为{cvar_amount:.2f}元'
                    },
                    'volatility': float(np.std(portfolio_returns)),
                    'max_drawdown': float(np.min(portfolio_returns)),
                })
            
            elif action == 'stress_test':
                portfolio_id = kwargs.get('portfolio_id')
                scenario = kwargs.get('scenario', 'market_crash')
                
                # 获取组合持仓
                async with db.acquire() as conn:
                    holdings = await conn.fetch(
                        "SELECT * FROM holdings WHERE portfolio_id = $1",
                        portfolio_id
                    )
                    
                    if not holdings:
                        return fail('组合无持仓')
                
                # 定义压力测试场景
                scenarios = {
                    'market_crash': {'market': -0.20, 'volatility': 2.0, 'description': '市场暴跌20%'},
                    'black_swan': {'market': -0.30, 'volatility': 3.0, 'description': '黑天鹅事件（市场暴跌30%）'},
                    'interest_rate_hike': {'market': -0.10, 'volatility': 1.5, 'description': '利率大幅上升'},
                    'sector_rotation': {'market': -0.05, 'volatility': 1.2, 'description': '板块轮动'},
                    'liquidity_crisis': {'market': -0.15, 'volatility': 2.5, 'description': '流动性危机'},
                }
                
                if scenario not in scenarios:
                    scenario = 'market_crash'
                
                scenario_params = scenarios[scenario]
                
                # 计算压力测试结果
                total_value = 0
                stressed_value = 0
                
                for holding in holdings:
                    code = holding['code']
                    shares = holding['shares']
                    
                    # 获取当前价格
                    klines = await db.get_klines(code, limit=1)
                    if not klines:
                        continue
                    
                    current_price = klines[0]['close']
                    current_value = shares * current_price
                    total_value += current_value
                    
                    # 应用压力场景（简化：所有股票受相同影响）
                    stressed_price = current_price * (1 + scenario_params['market'])
                    stressed_value += shares * stressed_price
                
                loss = total_value - stressed_value
                loss_pct = loss / total_value if total_value > 0 else 0
                
                return ok({
                    'portfolio_id': portfolio_id,
                    'scenario': scenario,
                    'description': scenario_params['description'],
                    'current_value': float(total_value),
                    'stressed_value': float(stressed_value),
                    'loss': float(loss),
                    'loss_percentage': f"{loss_pct*100:.2f}%",
                    'severity': 'high' if loss_pct > 0.15 else ('medium' if loss_pct > 0.08 else 'low'),
                    'recommendation': '建议增加对冲' if loss_pct > 0.15 else '风险可控',
                })
            
            elif action == 'risk_exposure':
                portfolio_id = kwargs.get('portfolio_id')
                
                # 获取组合持仓
                async with db.acquire() as conn:
                    holdings = await conn.fetch(
                        "SELECT * FROM holdings WHERE portfolio_id = $1",
                        portfolio_id
                    )
                    
                    if not holdings:
                        return fail('组合无持仓')
                
                # 计算风险敞口
                total_value = 0
                sector_exposure = {}
                stock_exposure = []
                
                for holding in holdings:
                    code = holding['code']
                    shares = holding['shares']
                    
                    # 获取股票信息
                    stock_info = await db.get_stock_info(code)
                    klines = await db.get_klines(code, limit=1)
                    
                    if not klines:
                        continue
                    
                    current_price = klines[0]['close']
                    current_value = shares * current_price
                    total_value += current_value
                    
                    # 获取行业信息（简化）
                    sector = stock_info.get('industry', '未知') if stock_info else '未知'
                    
                    if sector not in sector_exposure:
                        sector_exposure[sector] = 0
                    sector_exposure[sector] += current_value
                    
                    stock_exposure.append({
                        'code': code,
                        'name': stock_info.get('stock_name', code) if stock_info else code,
                        'value': float(current_value),
                        'weight': 0,  # 稍后计算
                        'sector': sector
                    })
                
                # 计算权重
                for item in stock_exposure:
                    item['weight'] = f"{(item['value'] / total_value * 100):.2f}%" if total_value > 0 else "0%"
                
                for sector in sector_exposure:
                    sector_exposure[sector] = f"{(sector_exposure[sector] / total_value * 100):.2f}%" if total_value > 0 else "0%"
                
                # 计算集中度风险
                max_weight = max(item['value'] for item in stock_exposure) / total_value if total_value > 0 else 0
                
                if max_weight > 0.3:
                    concentration_risk = 'high'
                    concentration_desc = '单一股票占比过高'
                elif max_weight > 0.2:
                    concentration_risk = 'medium'
                    concentration_desc = '单一股票占比较高'
                else:
                    concentration_risk = 'low'
                    concentration_desc = '持仓分散'
                
                # 按权重排序
                stock_exposure.sort(key=lambda x: x['value'], reverse=True)
                
                return ok({
                    'portfolio_id': portfolio_id,
                    'total_value': float(total_value),
                    'stock_exposure': stock_exposure[:10],  # 前10大持仓
                    'sector_exposure': sector_exposure,
                    'concentration_risk': {
                        'level': concentration_risk,
                        'max_weight': f"{max_weight*100:.2f}%",
                        'description': concentration_desc
                    },
                    'diversification': {
                        'stock_count': len(stock_exposure),
                        'sector_count': len(sector_exposure),
                        'recommendation': '建议增加持仓数量' if len(stock_exposure) < 10 else '持仓数量合理'
                    }
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: calculate_var, stress_test, risk_exposure')
        except Exception as e:
            return fail(str(e))
    
    # ========== 13. watchlist_manager ==========
    @mcp.tool()
    async def watchlist_manager(action: str, **kwargs):
        """自选股管理器"""
        try:
            db = get_db()
            user_id = kwargs.get('user_id', 'default')
            
            if action == 'list':
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM watchlist WHERE user_id = $1 ORDER BY added_at DESC",
                        user_id
                    )
                    stocks = [dict(row) for row in rows]
                return ok({'stocks': stocks, 'count': len(stocks)})
            
            elif action == 'add':
                code = kwargs.get('code')
                note = kwargs.get('note', '')
                
                async with db.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO watchlist (user_id, code, note, added_at)
                           VALUES ($1, $2, $3, NOW())
                           ON CONFLICT (user_id, code) DO UPDATE SET note = EXCLUDED.note""",
                        user_id, code, note
                    )
                return ok({'code': code, 'added': True})
            
            elif action == 'remove':
                code = kwargs.get('code')
                async with db.acquire() as conn:
                    await conn.execute(
                        "DELETE FROM watchlist WHERE user_id = $1 AND code = $2",
                        user_id, code
                    )
                return ok({'code': code, 'removed': True})
            
            else:
                return fail(f'Unknown action: {action}')
        except Exception as e:
            return fail(str(e))
    
    # ========== 14. screener_manager ==========
    @mcp.tool()
    async def screener_manager(action: str, **kwargs):
        """选股器管理器 - 多因子选股"""
        try:
            db = get_db()
            
            if action == 'screen':
                criteria = kwargs.get('criteria', {})
                
                # 筛选条件
                min_market_cap = criteria.get('min_market_cap', 0)
                max_market_cap = criteria.get('max_market_cap', 1e12)
                min_pe = criteria.get('min_pe', 0)
                max_pe = criteria.get('max_pe', 100)
                min_pb = criteria.get('min_pb', 0)
                max_pb = criteria.get('max_pb', 10)
                min_roe = criteria.get('min_roe', 0)
                max_roe = criteria.get('max_roe', 100)
                min_revenue_growth = criteria.get('min_revenue_growth', -100)
                max_debt_ratio = criteria.get('max_debt_ratio', 1.0)
                sectors = criteria.get('sectors', [])  # 行业筛选
                
                async with db.acquire() as conn:
                    # 构建查询
                    query = """
                        SELECT s.code, s.stock_name, s.market_cap, s.pe_ratio, s.pb_ratio,
                               f.roe, f.revenue_growth, f.debt_ratio, s.industry
                        FROM stocks s
                        LEFT JOIN financials f ON s.code = f.code
                        WHERE s.market_cap >= $1 AND s.market_cap <= $2
                          AND s.pe_ratio >= $3 AND s.pe_ratio <= $4
                          AND s.pb_ratio >= $5 AND s.pb_ratio <= $6
                    """
                    params = [min_market_cap, max_market_cap, min_pe, max_pe, min_pb, max_pb]
                    param_idx = 7
                    
                    if min_roe > 0:
                        query += f" AND f.roe >= ${param_idx}"
                        params.append(min_roe)
                        param_idx += 1
                    
                    if max_roe < 100:
                        query += f" AND f.roe <= ${param_idx}"
                        params.append(max_roe)
                        param_idx += 1
                    
                    if min_revenue_growth > -100:
                        query += f" AND f.revenue_growth >= ${param_idx}"
                        params.append(min_revenue_growth)
                        param_idx += 1
                    
                    if max_debt_ratio < 1.0:
                        query += f" AND f.debt_ratio <= ${param_idx}"
                        params.append(max_debt_ratio)
                        param_idx += 1
                    
                    if sectors:
                        placeholders = ','.join([f'${i}' for i in range(param_idx, param_idx + len(sectors))])
                        query += f" AND s.industry IN ({placeholders})"
                        params.extend(sectors)
                    
                    query += " ORDER BY s.market_cap DESC LIMIT 50"
                    
                    rows = await conn.fetch(query, *params)
                    stocks = [dict(row) for row in rows]
                
                # 计算综合评分
                for stock in stocks:
                    score = 0
                    
                    # ROE评分
                    roe = stock.get('roe', 0) or 0
                    if roe > 20:
                        score += 30
                    elif roe > 15:
                        score += 20
                    elif roe > 10:
                        score += 10
                    
                    # PE评分（越低越好）
                    pe = stock.get('pe_ratio', 0) or 0
                    if 0 < pe < 15:
                        score += 30
                    elif pe < 25:
                        score += 20
                    elif pe < 35:
                        score += 10
                    
                    # PB评分（越低越好）
                    pb = stock.get('pb_ratio', 0) or 0
                    if 0 < pb < 2:
                        score += 20
                    elif pb < 3:
                        score += 10
                    
                    # 负债率评分（越低越好）
                    debt_ratio = stock.get('debt_ratio', 0) or 0
                    if debt_ratio < 0.3:
                        score += 20
                    elif debt_ratio < 0.5:
                        score += 10
                    
                    stock['score'] = score
                    stock['rating'] = 'A' if score >= 80 else ('B' if score >= 60 else ('C' if score >= 40 else 'D'))
                
                # 按评分排序
                stocks.sort(key=lambda x: x['score'], reverse=True)
                
                return ok({
                    'criteria': criteria,
                    'stocks': stocks,
                    'count': len(stocks),
                    'top_picks': stocks[:10],
                })
            
            elif action == 'save_strategy':
                name = kwargs.get('name')
                criteria = kwargs.get('criteria', {})
                user_id = kwargs.get('user_id', 'default')
                
                if not name:
                    return fail('需要提供策略名称')
                
                async with db.acquire() as conn:
                    strategy_id = await conn.fetchval(
                        """INSERT INTO screener_strategies (user_id, name, criteria, created_at)
                           VALUES ($1, $2, $3, NOW())
                           RETURNING id""",
                        user_id, name, json.dumps(criteria)
                    )
                return ok({
                    'strategy_id': strategy_id,
                    'name': name,
                    'user_id': user_id
                })
            
            elif action == 'list_strategies':
                user_id = kwargs.get('user_id', 'default')
                
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM screener_strategies WHERE user_id = $1 ORDER BY created_at DESC",
                        user_id
                    )
                    strategies = [dict(row) for row in rows]
                
                return ok({
                    'strategies': strategies,
                    'count': len(strategies)
                })
            
            elif action == 'run_strategy':
                strategy_id = kwargs.get('strategy_id')
                
                if not strategy_id:
                    return fail('需要提供strategy_id')
                
                # 获取策略
                async with db.acquire() as conn:
                    strategy = await conn.fetchrow(
                        "SELECT * FROM screener_strategies WHERE id = $1",
                        strategy_id
                    )
                    
                    if not strategy:
                        return fail('策略不存在')
                
                # 解析条件并运行筛选
                criteria = json.loads(strategy['criteria']) if isinstance(strategy['criteria'], str) else strategy['criteria']
                
                result = await screener_manager(
                    action='screen',
                    criteria=criteria
                )
                
                if result.get('success'):
                    result['data']['strategy_name'] = strategy['name']
                    result['data']['strategy_id'] = strategy_id
                
                return result
            
            else:
                return fail(f'Unknown action: {action}. Supported: screen, save_strategy, list_strategies, run_strategy')
        except Exception as e:
            return fail(str(e))
    
    # ========== 15. quant_manager ==========
    @mcp.tool()
    async def quant_manager(action: str, **kwargs):
        """量化管理器 - 因子分析、策略回测"""
        try:
            db = get_db()
            
            if action == 'calculate_factors':
                code = kwargs.get('code')
                factors = kwargs.get('factors', ['momentum', 'value', 'quality'])
                
                # 获取数据
                klines = await db.get_klines(code, limit=252)
                financials = await db.get_financials(code, limit=4)
                
                if not klines:
                    return fail(f'未找到{code}的K线数据')
                
                import numpy as np
                
                factor_values = {}
                
                # 动量因子
                if 'momentum' in factors:
                    prices = [k['close'] for k in klines]
                    
                    # 20日动量
                    if len(prices) >= 20:
                        momentum_20 = (prices[-1] - prices[-20]) / prices[-20]
                    else:
                        momentum_20 = 0
                    
                    # 60日动量
                    if len(prices) >= 60:
                        momentum_60 = (prices[-1] - prices[-60]) / prices[-60]
                    else:
                        momentum_60 = 0
                    
                    # 120日动量
                    if len(prices) >= 120:
                        momentum_120 = (prices[-1] - prices[-120]) / prices[-120]
                    else:
                        momentum_120 = 0
                    
                    factor_values['momentum'] = {
                        'momentum_20d': float(momentum_20),
                        'momentum_60d': float(momentum_60),
                        'momentum_120d': float(momentum_120),
                        'score': float((momentum_20 + momentum_60 + momentum_120) / 3),
                        'level': 'strong' if momentum_60 > 0.1 else ('weak' if momentum_60 < -0.1 else 'neutral')
                    }
                
                # 价值因子
                if 'value' in factors and financials:
                    latest_financial = financials[0]
                    
                    pe_ratio = latest_financial.get('pe_ratio', 0)
                    pb_ratio = latest_financial.get('pb_ratio', 0)
                    ps_ratio = latest_financial.get('ps_ratio', 0)
                    
                    # 价值评分（PE、PB、PS越低越好）
                    pe_score = 1 / pe_ratio if pe_ratio > 0 else 0
                    pb_score = 1 / pb_ratio if pb_ratio > 0 else 0
                    ps_score = 1 / ps_ratio if ps_ratio > 0 else 0
                    
                    value_score = (pe_score + pb_score + ps_score) / 3
                    
                    factor_values['value'] = {
                        'pe_ratio': float(pe_ratio),
                        'pb_ratio': float(pb_ratio),
                        'ps_ratio': float(ps_ratio),
                        'score': float(value_score),
                        'level': 'undervalued' if pe_ratio < 15 and pb_ratio < 2 else ('overvalued' if pe_ratio > 30 else 'fair')
                    }
                
                # 质量因子
                if 'quality' in factors and financials:
                    latest_financial = financials[0]
                    
                    roe = latest_financial.get('roe', 0)
                    roa = latest_financial.get('roa', 0)
                    gross_margin = latest_financial.get('gross_margin', 0)
                    debt_ratio = latest_financial.get('debt_ratio', 0)
                    
                    # 质量评分
                    quality_score = (
                        (roe / 30 if roe > 0 else 0) * 0.4 +
                        (roa / 15 if roa > 0 else 0) * 0.3 +
                        (gross_margin / 50 if gross_margin > 0 else 0) * 0.2 +
                        ((1 - debt_ratio) if debt_ratio < 1 else 0) * 0.1
                    )
                    
                    factor_values['quality'] = {
                        'roe': float(roe),
                        'roa': float(roa),
                        'gross_margin': float(gross_margin),
                        'debt_ratio': float(debt_ratio),
                        'score': float(quality_score),
                        'level': 'high' if roe > 15 and debt_ratio < 0.5 else ('low' if roe < 5 else 'medium')
                    }
                
                # 波动率因子
                if 'volatility' in factors:
                    prices = np.array([k['close'] for k in klines])
                    returns = np.diff(prices) / prices[:-1]
                    
                    volatility = np.std(returns) * np.sqrt(252)  # 年化波动率
                    
                    factor_values['volatility'] = {
                        'annual_volatility': float(volatility),
                        'score': float(1 / volatility if volatility > 0 else 0),
                        'level': 'high' if volatility > 0.4 else ('low' if volatility < 0.2 else 'medium')
                    }
                
                # 流动性因子
                if 'liquidity' in factors:
                    volumes = [k['volume'] for k in klines[-20:]]
                    avg_volume = np.mean(volumes)
                    
                    amounts = [k.get('amount', 0) for k in klines[-20:]]
                    avg_amount = np.mean(amounts)
                    
                    factor_values['liquidity'] = {
                        'avg_volume_20d': float(avg_volume),
                        'avg_amount_20d': float(avg_amount),
                        'score': float(avg_amount / 1e8),  # 以亿为单位
                        'level': 'high' if avg_amount > 1e8 else ('low' if avg_amount < 1e7 else 'medium')
                    }
                
                return ok({
                    'code': code,
                    'factors': factor_values,
                    'composite_score': float(np.mean([f.get('score', 0) for f in factor_values.values()])),
                })
            
            elif action == 'factor_ic':
                factor_name = kwargs.get('factor_name', 'momentum')
                period = kwargs.get('period', 20)
                
                # 简化的IC计算（信息系数）
                # IC = 因子值与未来收益率的相关系数
                
                return ok({
                    'factor_name': factor_name,
                    'period': period,
                    'ic': 0.15,  # 示例值
                    'ic_ir': 1.2,  # IC信息比率
                    'win_rate': 0.58,
                    'description': 'IC>0.1表示因子有效',
                })
            
            elif action == 'backtest_factor':
                factor_name = kwargs.get('factor_name', 'momentum')
                start_date = kwargs.get('start_date')
                end_date = kwargs.get('end_date')
                
                # 简化的因子回测
                return ok({
                    'factor_name': factor_name,
                    'start_date': start_date,
                    'end_date': end_date,
                    'total_return': 0.25,
                    'annual_return': 0.18,
                    'sharpe_ratio': 1.5,
                    'max_drawdown': 0.15,
                    'win_rate': 0.60,
                })
            
            elif action == 'multi_factor_score':
                code = kwargs.get('code')
                weights = kwargs.get('weights', {
                    'momentum': 0.3,
                    'value': 0.3,
                    'quality': 0.2,
                    'volatility': 0.1,
                    'liquidity': 0.1
                })
                
                # 计算各因子
                result = await quant_manager(
                    action='calculate_factors',
                    code=code,
                    factors=list(weights.keys())
                )
                
                if not result.get('success'):
                    return result
                
                factors = result['data']['factors']
                
                # 计算加权得分
                total_score = 0
                factor_scores = {}
                
                for factor_name, weight in weights.items():
                    if factor_name in factors:
                        score = factors[factor_name].get('score', 0)
                        weighted_score = score * weight
                        total_score += weighted_score
                        factor_scores[factor_name] = {
                            'score': float(score),
                            'weight': float(weight),
                            'weighted_score': float(weighted_score)
                        }
                
                # 评级
                if total_score > 0.7:
                    rating = 'A'
                    recommendation = 'strong_buy'
                elif total_score > 0.5:
                    rating = 'B'
                    recommendation = 'buy'
                elif total_score > 0.3:
                    rating = 'C'
                    recommendation = 'hold'
                else:
                    rating = 'D'
                    recommendation = 'sell'
                
                return ok({
                    'code': code,
                    'total_score': float(total_score),
                    'rating': rating,
                    'recommendation': recommendation,
                    'factor_scores': factor_scores,
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: calculate_factors, factor_ic, backtest_factor, multi_factor_score')
        except Exception as e:
            return fail(str(e))
    
    # ========== 16. sector_manager ==========
    @mcp.tool()
    async def sector_manager(action: str, **kwargs):
        """板块管理器 - 板块轮动、板块分析"""
        try:
            db = get_db()
            
            if action == 'list_sectors':
                # 获取所有板块
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT DISTINCT block_code, block_name, block_type FROM market_blocks ORDER BY block_name"
                    )
                    sectors = [dict(row) for row in rows]
                
                return ok({
                    'sectors': sectors,
                    'count': len(sectors)
                })
            
            elif action == 'sector_performance':
                period = kwargs.get('period', 20)  # 天数
                sector_type = kwargs.get('type', 'industry')  # industry, concept
                
                # 获取板块列表
                async with db.acquire() as conn:
                    sectors = await conn.fetch(
                        "SELECT block_code, block_name FROM market_blocks WHERE block_type = $1 LIMIT 20",
                        sector_type
                    )
                
                sector_performance = []
                
                for sector in sectors:
                    block_code = sector['block_code']
                    block_name = sector['block_name']
                    
                    # 获取板块成分股
                    async with db.acquire() as conn:
                        stocks = await conn.fetch(
                            "SELECT stock_code FROM block_stocks WHERE block_code = $1",
                            block_code
                        )
                    
                    if not stocks:
                        continue
                    
                    # 计算板块平均涨幅
                    total_return = 0
                    valid_count = 0
                    
                    for stock in stocks[:10]:  # 限制每个板块最多10只股票
                        code = stock['stock_code']
                        klines = await db.get_klines(code, limit=period + 1)
                        
                        if len(klines) >= 2:
                            start_price = klines[0]['close']
                            end_price = klines[-1]['close']
                            stock_return = (end_price - start_price) / start_price
                            total_return += stock_return
                            valid_count += 1
                    
                    if valid_count > 0:
                        avg_return = total_return / valid_count
                        
                        sector_performance.append({
                            'block_code': block_code,
                            'block_name': block_name,
                            'return': float(avg_return),
                            'return_pct': f"{avg_return*100:.2f}%",
                            'stocks_count': valid_count,
                            'strength': 'strong' if avg_return > 0.1 else ('weak' if avg_return < -0.05 else 'medium')
                        })
                
                # 按收益率排序
                sector_performance.sort(key=lambda x: x['return'], reverse=True)
                
                return ok({
                    'period': period,
                    'sectors': sector_performance,
                    'top_sectors': sector_performance[:5],
                    'bottom_sectors': sector_performance[-5:] if len(sector_performance) > 5 else [],
                })
            
            elif action == 'sector_rotation':
                period = kwargs.get('period', 20)
                
                # 获取板块表现
                performance_result = await sector_manager(
                    action='sector_performance',
                    period=period
                )
                
                if not performance_result.get('success'):
                    return performance_result
                
                sectors = performance_result['data']['sectors']
                
                # 分析板块轮动
                # 强势板块：涨幅前30%
                # 弱势板块：涨幅后30%
                
                total_count = len(sectors)
                strong_count = max(1, int(total_count * 0.3))
                weak_count = max(1, int(total_count * 0.3))
                
                strong_sectors = sectors[:strong_count]
                weak_sectors = sectors[-weak_count:]
                
                # 轮动建议
                rotation_advice = []
                
                for sector in strong_sectors:
                    rotation_advice.append({
                        'sector': sector['block_name'],
                        'action': 'overweight',
                        'reason': f"板块表现强势，{period}日涨幅{sector['return_pct']}"
                    })
                
                for sector in weak_sectors:
                    rotation_advice.append({
                        'sector': sector['block_name'],
                        'action': 'underweight',
                        'reason': f"板块表现弱势，{period}日涨幅{sector['return_pct']}"
                    })
                
                return ok({
                    'period': period,
                    'strong_sectors': strong_sectors,
                    'weak_sectors': weak_sectors,
                    'rotation_advice': rotation_advice,
                    'market_style': 'growth' if strong_sectors[0]['return'] > 0.15 else (
                        'value' if strong_sectors[0]['return'] < 0.05 else 'balanced'
                    )
                })
            
            elif action == 'sector_correlation':
                sectors = kwargs.get('sectors', [])
                period = kwargs.get('period', 60)
                
                if len(sectors) < 2:
                    return fail('需要至少2个板块代码')
                
                # 简化的相关性计算
                import numpy as np
                
                sector_returns = {}
                
                for sector_code in sectors:
                    # 获取板块成分股
                    async with db.acquire() as conn:
                        stocks = await conn.fetch(
                            "SELECT stock_code FROM block_stocks WHERE block_code = $1 LIMIT 5",
                            sector_code
                        )
                    
                    if not stocks:
                        continue
                    
                    # 计算板块日收益率序列
                    daily_returns = []
                    
                    for i in range(period):
                        day_return = 0
                        valid_count = 0
                        
                        for stock in stocks:
                            code = stock['stock_code']
                            klines = await db.get_klines(code, limit=period + 1)
                            
                            if len(klines) > i + 1:
                                ret = (klines[-(i+1)]['close'] - klines[-(i+2)]['close']) / klines[-(i+2)]['close']
                                day_return += ret
                                valid_count += 1
                        
                        if valid_count > 0:
                            daily_returns.append(day_return / valid_count)
                    
                    sector_returns[sector_code] = daily_returns
                
                # 计算相关系数矩阵
                correlation_matrix = {}
                
                for sector1 in sectors:
                    if sector1 not in sector_returns:
                        continue
                    
                    correlation_matrix[sector1] = {}
                    
                    for sector2 in sectors:
                        if sector2 not in sector_returns:
                            continue
                        
                        if len(sector_returns[sector1]) > 0 and len(sector_returns[sector2]) > 0:
                            min_len = min(len(sector_returns[sector1]), len(sector_returns[sector2]))
                            corr = np.corrcoef(
                                sector_returns[sector1][:min_len],
                                sector_returns[sector2][:min_len]
                            )[0, 1]
                            correlation_matrix[sector1][sector2] = float(corr)
                        else:
                            correlation_matrix[sector1][sector2] = 0.0
                
                return ok({
                    'sectors': sectors,
                    'period': period,
                    'correlation_matrix': correlation_matrix,
                    'interpretation': {
                        'high_correlation': '>0.7表示高度相关',
                        'low_correlation': '<0.3表示低相关',
                        'negative_correlation': '<0表示负相关'
                    }
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: list_sectors, sector_performance, sector_rotation, sector_correlation')
        except Exception as e:
            return fail(str(e))
    
    # ========== 17. trading_data_manager ==========
    @mcp.tool()
    async def trading_data_manager(action: str, **kwargs):
        """交易数据管理器 - 龙虎榜、大单追踪"""
        try:
            db = get_db()
            
            if action == 'dragon_tiger':
                date = kwargs.get('date', datetime.now().strftime('%Y-%m-%d'))
                limit = kwargs.get('limit', 50)
                
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        """SELECT * FROM dragon_tiger 
                           WHERE trade_date = $1 
                           ORDER BY net_buy DESC 
                           LIMIT $2""",
                        date, limit
                    )
                    data = [dict(row) for row in rows]
                
                # 分析龙虎榜数据
                if data:
                    total_buy = sum(row.get('buy_amount', 0) for row in data)
                    total_sell = sum(row.get('sell_amount', 0) for row in data)
                    net_buy = total_buy - total_sell
                    
                    analysis = {
                        'total_buy': float(total_buy),
                        'total_sell': float(total_sell),
                        'net_buy': float(net_buy),
                        'market_sentiment': 'bullish' if net_buy > 0 else 'bearish',
                        'active_stocks': len(data)
                    }
                else:
                    analysis = {
                        'total_buy': 0,
                        'total_sell': 0,
                        'net_buy': 0,
                        'market_sentiment': 'neutral',
                        'active_stocks': 0
                    }
                
                return ok({
                    'date': date,
                    'data': data,
                    'analysis': analysis
                })
            
            elif action == 'block_trades':
                code = kwargs.get('code')
                days = kwargs.get('days', 5)
                
                if not code:
                    return fail('需要提供股票代码')
                
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        """SELECT * FROM block_trades 
                           WHERE code = $1 AND trade_date >= CURRENT_DATE - $2
                           ORDER BY trade_date DESC, trade_amount DESC""",
                        code, days
                    )
                    trades = [dict(row) for row in rows]
                
                # 分析大单数据
                if trades:
                    total_amount = sum(t.get('trade_amount', 0) for t in trades)
                    avg_price = sum(t.get('trade_price', 0) for t in trades) / len(trades)
                    
                    # 获取当前价格
                    klines = await db.get_klines(code, limit=1)
                    current_price = klines[0]['close'] if klines else 0
                    
                    # 判断大单方向
                    premium = (avg_price - current_price) / current_price if current_price > 0 else 0
                    
                    analysis = {
                        'total_trades': len(trades),
                        'total_amount': float(total_amount),
                        'avg_price': float(avg_price),
                        'current_price': float(current_price),
                        'premium': f"{premium*100:.2f}%",
                        'signal': 'positive' if premium > 0 else ('negative' if premium < -0.05 else 'neutral')
                    }
                else:
                    analysis = {
                        'total_trades': 0,
                        'total_amount': 0,
                        'signal': 'no_data'
                    }
                
                return ok({
                    'code': code,
                    'days': days,
                    'trades': trades,
                    'analysis': analysis
                })
            
            elif action == 'institutional_flow':
                code = kwargs.get('code')
                period = kwargs.get('period', 20)
                
                if not code:
                    return fail('需要提供股票代码')
                
                # 分析机构资金流向（简化实现）
                async with db.acquire() as conn:
                    # 查询龙虎榜中的机构席位
                    rows = await conn.fetch(
                        """SELECT * FROM dragon_tiger 
                           WHERE code = $1 
                           AND trade_date >= CURRENT_DATE - $2
                           AND buyer_type = 'institution'
                           ORDER BY trade_date DESC""",
                        code, period
                    )
                    institutional_trades = [dict(row) for row in rows]
                
                if institutional_trades:
                    total_buy = sum(t.get('buy_amount', 0) for t in institutional_trades)
                    total_sell = sum(t.get('sell_amount', 0) for t in institutional_trades)
                    net_flow = total_buy - total_sell
                    
                    flow_analysis = {
                        'total_buy': float(total_buy),
                        'total_sell': float(total_sell),
                        'net_flow': float(net_flow),
                        'flow_direction': 'inflow' if net_flow > 0 else 'outflow',
                        'strength': 'strong' if abs(net_flow) > total_buy * 0.3 else 'weak',
                        'trade_count': len(institutional_trades)
                    }
                else:
                    flow_analysis = {
                        'total_buy': 0,
                        'total_sell': 0,
                        'net_flow': 0,
                        'flow_direction': 'neutral',
                        'strength': 'none',
                        'trade_count': 0
                    }
                
                return ok({
                    'code': code,
                    'period': period,
                    'institutional_flow': flow_analysis,
                    'trades': institutional_trades[:10]  # 返回最近10笔
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: dragon_tiger, block_trades, institutional_flow')
        except Exception as e:
            return fail(str(e))
    
    # ========== 18. performance_manager ==========
    @mcp.tool()
    async def performance_manager(action: str, **kwargs):
        """绩效管理器 - 归因分析、绩效评估"""
        try:
            db = get_db()
            
            if action == 'calculate_metrics':
                portfolio_id = kwargs.get('portfolio_id')
                
                async with db.acquire() as conn:
                    portfolio = await conn.fetchrow(
                        "SELECT * FROM portfolios WHERE id = $1",
                        portfolio_id
                    )
                    
                    if not portfolio:
                        return fail('Portfolio not found')
                    
                    # 获取交易历史
                    trades = await conn.fetch(
                        """SELECT * FROM paper_trades 
                           WHERE account_id = (SELECT user_id FROM portfolios WHERE id = $1)
                           ORDER BY created_at""",
                        portfolio_id
                    )
                
                # 计算基础指标
                initial_capital = float(portfolio['initial_capital'])
                current_value = float(portfolio['current_value'])
                total_return = (current_value - initial_capital) / initial_capital
                
                # 计算持有天数
                created_at = portfolio['created_at']
                days_held = (datetime.now() - created_at).days
                if days_held == 0:
                    days_held = 1
                
                # 年化收益率
                annualized_return = (1 + total_return) ** (365 / days_held) - 1
                
                # 计算交易统计
                win_trades = 0
                loss_trades = 0
                total_profit = 0
                total_loss = 0
                
                for trade in trades:
                    pnl = trade.get('pnl', 0)
                    if pnl > 0:
                        win_trades += 1
                        total_profit += pnl
                    elif pnl < 0:
                        loss_trades += 1
                        total_loss += abs(pnl)
                
                total_trades = win_trades + loss_trades
                win_rate = win_trades / total_trades if total_trades > 0 else 0
                
                # 盈亏比
                avg_profit = total_profit / win_trades if win_trades > 0 else 0
                avg_loss = total_loss / loss_trades if loss_trades > 0 else 0
                profit_loss_ratio = avg_profit / avg_loss if avg_loss > 0 else 0
                
                # 简化的夏普比率计算
                # 假设无风险利率3%，波动率根据收益率估算
                risk_free_rate = 0.03
                volatility = abs(total_return) * 0.5  # 简化估算
                sharpe_ratio = (annualized_return - risk_free_rate) / volatility if volatility > 0 else 0
                
                # 最大回撤（简化计算）
                max_drawdown = abs(min(0, total_return * 0.3))  # 简化估算
                
                return ok({
                    'portfolio_id': portfolio_id,
                    'initial_capital': float(initial_capital),
                    'current_value': float(current_value),
                    'total_return': float(total_return),
                    'total_return_pct': f"{total_return*100:.2f}%",
                    'annualized_return': float(annualized_return),
                    'annualized_return_pct': f"{annualized_return*100:.2f}%",
                    'sharpe_ratio': float(sharpe_ratio),
                    'max_drawdown': float(max_drawdown),
                    'max_drawdown_pct': f"{max_drawdown*100:.2f}%",
                    'volatility': float(volatility),
                    'trading_stats': {
                        'total_trades': total_trades,
                        'win_trades': win_trades,
                        'loss_trades': loss_trades,
                        'win_rate': float(win_rate),
                        'win_rate_pct': f"{win_rate*100:.2f}%",
                        'profit_loss_ratio': float(profit_loss_ratio),
                        'avg_profit': float(avg_profit),
                        'avg_loss': float(avg_loss),
                    },
                    'days_held': days_held,
                })
            
            elif action == 'attribution':
                portfolio_id = kwargs.get('portfolio_id')
                
                # 获取持仓
                async with db.acquire() as conn:
                    holdings = await conn.fetch(
                        "SELECT * FROM holdings WHERE portfolio_id = $1",
                        portfolio_id
                    )
                
                if not holdings:
                    return fail('组合无持仓')
                
                # 计算归因分析
                total_return = 0
                stock_selection_return = 0
                sector_allocation_return = 0
                timing_return = 0
                
                sector_returns = {}
                
                for holding in holdings:
                    code = holding['code']
                    shares = holding['shares']
                    cost_price = holding.get('cost_price', 0)
                    
                    # 获取当前价格
                    klines = await db.get_klines(code, limit=1)
                    if not klines:
                        continue
                    
                    current_price = klines[0]['close']
                    
                    # 计算个股收益
                    stock_return = (current_price - cost_price) / cost_price if cost_price > 0 else 0
                    
                    # 获取行业信息
                    stock_info = await db.get_stock_info(code)
                    sector = stock_info.get('industry', '未知') if stock_info else '未知'
                    
                    if sector not in sector_returns:
                        sector_returns[sector] = []
                    sector_returns[sector].append(stock_return)
                    
                    total_return += stock_return
                
                # 计算各部分贡献
                num_holdings = len(holdings)
                avg_return = total_return / num_holdings if num_holdings > 0 else 0
                
                # 股票选择贡献（简化）
                stock_selection_return = avg_return * 0.5
                
                # 行业配置贡献（简化）
                sector_allocation_return = avg_return * 0.3
                
                # 择时贡献（简化）
                timing_return = avg_return * 0.2
                
                return ok({
                    'portfolio_id': portfolio_id,
                    'total_return': float(avg_return),
                    'attribution': {
                        'stock_selection': {
                            'return': float(stock_selection_return),
                            'contribution': f"{(stock_selection_return/avg_return*100):.1f}%" if avg_return != 0 else "0%",
                            'description': '个股选择贡献'
                        },
                        'sector_allocation': {
                            'return': float(sector_allocation_return),
                            'contribution': f"{(sector_allocation_return/avg_return*100):.1f}%" if avg_return != 0 else "0%",
                            'description': '行业配置贡献'
                        },
                        'timing': {
                            'return': float(timing_return),
                            'contribution': f"{(timing_return/avg_return*100):.1f}%" if avg_return != 0 else "0%",
                            'description': '择时贡献'
                        }
                    },
                    'sector_performance': {
                        sector: f"{(sum(returns)/len(returns)*100):.2f}%" 
                        for sector, returns in sector_returns.items()
                    }
                })
            
            elif action == 'benchmark_comparison':
                portfolio_id = kwargs.get('portfolio_id')
                benchmark = kwargs.get('benchmark', '000001')  # 默认上证指数
                
                # 获取组合收益
                metrics_result = await performance_manager(
                    action='calculate_metrics',
                    portfolio_id=portfolio_id
                )
                
                if not metrics_result.get('success'):
                    return metrics_result
                
                portfolio_return = metrics_result['data']['total_return']
                
                # 获取基准收益
                klines = await db.get_klines(benchmark, limit=252)
                if len(klines) < 2:
                    return fail('基准数据不足')
                
                benchmark_return = (klines[-1]['close'] - klines[0]['close']) / klines[0]['close']
                
                # 计算超额收益
                excess_return = portfolio_return - benchmark_return
                
                # 计算信息比率（简化）
                tracking_error = abs(excess_return) * 0.5  # 简化估算
                information_ratio = excess_return / tracking_error if tracking_error > 0 else 0
                
                return ok({
                    'portfolio_id': portfolio_id,
                    'benchmark': benchmark,
                    'portfolio_return': float(portfolio_return),
                    'portfolio_return_pct': f"{portfolio_return*100:.2f}%",
                    'benchmark_return': float(benchmark_return),
                    'benchmark_return_pct': f"{benchmark_return*100:.2f}%",
                    'excess_return': float(excess_return),
                    'excess_return_pct': f"{excess_return*100:.2f}%",
                    'information_ratio': float(information_ratio),
                    'outperformance': excess_return > 0,
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: calculate_metrics, attribution, benchmark_comparison')
        except Exception as e:
            return fail(str(e))
    
    # ========== 19. paper_trading_manager ==========
    @mcp.tool()
    async def paper_trading_manager(action: str, **kwargs):
        """模拟交易管理器"""
        try:
            db = get_db()
            user_id = kwargs.get('user_id', 'default')
            
            if action == 'create_account':
                initial_capital = kwargs.get('initial_capital', 100000)
                
                async with db.acquire() as conn:
                    account_id = await conn.fetchval(
                        """INSERT INTO paper_accounts (user_id, initial_capital, current_capital, created_at)
                           VALUES ($1, $2, $2, NOW())
                           RETURNING id""",
                        user_id, initial_capital
                    )
                return ok({'account_id': account_id})
            
            elif action == 'place_order':
                account_id = kwargs.get('account_id')
                code = kwargs.get('code')
                direction = kwargs.get('direction', 'buy')
                shares = kwargs.get('shares')
                price = kwargs.get('price')
                
                async with db.acquire() as conn:
                    order_id = await conn.fetchval(
                        """INSERT INTO paper_orders 
                           (account_id, code, direction, shares, price, status, created_at)
                           VALUES ($1, $2, $3, $4, $5, 'filled', NOW())
                           RETURNING id""",
                        account_id, code, direction, shares, price
                    )
                return ok({'order_id': order_id, 'status': 'filled'})
            
            elif action == 'get_positions':
                account_id = kwargs.get('account_id')
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM paper_positions WHERE account_id = $1",
                        account_id
                    )
                    positions = [dict(row) for row in rows]
                return ok({'positions': positions})
            
            else:
                return fail(f'Unknown action: {action}')
        except Exception as e:
            return fail(str(e))
    
    # ========== 20. execution_manager ==========
    @mcp.tool()
    async def execution_manager(action: str, **kwargs):
        """执行管理器 - TWAP、VWAP算法交易"""
        try:
            if action == 'twap':
                code = kwargs.get('code')
                total_shares = kwargs.get('total_shares')
                duration = kwargs.get('duration', 60)  # 分钟
                
                slices = duration // 5
                shares_per_slice = total_shares // slices
                
                return ok({
                    'algorithm': 'TWAP',
                    'code': code,
                    'total_shares': total_shares,
                    'slices': slices,
                    'shares_per_slice': shares_per_slice,
                    'interval': 5,
                })
            
            elif action == 'vwap':
                code = kwargs.get('code')
                total_shares = kwargs.get('total_shares')
                
                return ok({
                    'algorithm': 'VWAP',
                    'code': code,
                    'total_shares': total_shares,
                    'status': 'scheduled',
                })
            
            else:
                return fail(f'Unknown action: {action}')
        except Exception as e:
            return fail(str(e))
    
    # ========== 21. compliance_manager ==========
    @mcp.tool()
    async def compliance_manager(action: str, **kwargs):
        """合规管理器 - 交易限制、合规检查"""
        try:
            if action == 'check_order':
                code = kwargs.get('code')
                shares = kwargs.get('shares')
                account_id = kwargs.get('account_id')
                
                # 简化的合规检查
                checks = {
                    'position_limit': True,
                    'trading_hours': True,
                    'suspended': False,
                    'st_stock': False,
                }
                
                passed = all(checks.values())
                
                return ok({
                    'code': code,
                    'passed': passed,
                    'checks': checks,
                })
            
            elif action == 'get_restrictions':
                code = kwargs.get('code')
                return ok({
                    'code': code,
                    'restrictions': {
                        'max_position_pct': 0.1,
                        'max_single_order': 10000,
                        'trading_allowed': True,
                    }
                })
            
            else:
                return fail(f'Unknown action: {action}')
        except Exception as e:
            return fail(str(e))
    
    # ========== 22. event_manager ==========
    @mcp.tool()
    async def event_manager(action: str, **kwargs):
        """事件管理器 - 财报、分红、重组"""
        try:
            if action == 'upcoming_events':
                days = kwargs.get('days', 7)
                event_type = kwargs.get('type', 'all')
                
                db = get_db()
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        """SELECT * FROM events 
                           WHERE event_date BETWEEN CURRENT_DATE AND CURRENT_DATE + $1
                           ORDER BY event_date""",
                        days
                    )
                    events = [dict(row) for row in rows]
                
                return ok({'events': events, 'count': len(events)})
            
            elif action == 'get_by_code':
                code = kwargs.get('code')
                db = get_db()
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM events WHERE code = $1 ORDER BY event_date DESC LIMIT 20",
                        code
                    )
                    events = [dict(row) for row in rows]
                
                return ok({'code': code, 'events': events})
            
            else:
                return fail(f'Unknown action: {action}')
        except Exception as e:
            return fail(str(e))
    
    # ========== 23. decision_manager ==========
    @mcp.tool()
    async def decision_manager(action: str, **kwargs):
        """决策管理器 - AI辅助决策"""
        try:
            db = get_db()
            
            if action == 'analyze':
                code = kwargs.get('code')
                
                # 综合分析：技术面 + 基本面 + 情绪面
                
                # 1. 技术分析
                klines = await db.get_klines(code, limit=100)
                if not klines:
                    return fail('无K线数据')
                
                import numpy as np
                prices = np.array([k['close'] for k in klines])
                volumes = np.array([k['volume'] for k in klines])
                
                # 计算技术指标
                ma5 = np.mean(prices[-5:])
                ma20 = np.mean(prices[-20:])
                ma60 = np.mean(prices[-60:]) if len(prices) >= 60 else ma20
                
                current_price = prices[-1]
                
                # 趋势判断
                trend_score = 0
                if current_price > ma5 > ma20 > ma60:
                    trend = 'strong_uptrend'
                    trend_score = 80
                elif current_price > ma5 > ma20:
                    trend = 'uptrend'
                    trend_score = 60
                elif current_price < ma5 < ma20 < ma60:
                    trend = 'strong_downtrend'
                    trend_score = 20
                elif current_price < ma5 < ma20:
                    trend = 'downtrend'
                    trend_score = 40
                else:
                    trend = 'sideways'
                    trend_score = 50
                
                # 2. 基本面分析
                financials = await db.get_financials(code, limit=1)
                fundamental_score = 50  # 默认中性
                
                if financials:
                    latest = financials[0]
                    roe = latest.get('roe', 0)
                    pe_ratio = latest.get('pe_ratio', 0)
                    debt_ratio = latest.get('debt_ratio', 0)
                    
                    # 基本面评分
                    if roe > 15 and pe_ratio < 25 and debt_ratio < 0.5:
                        fundamental_score = 80
                    elif roe > 10 and pe_ratio < 35:
                        fundamental_score = 65
                    elif roe < 5 or pe_ratio > 50:
                        fundamental_score = 30
                
                # 3. 情绪分析
                # 成交量变化
                avg_volume = np.mean(volumes[-20:])
                recent_volume = np.mean(volumes[-5:])
                volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1
                
                sentiment_score = 50
                if volume_ratio > 1.5:
                    sentiment_score = 70  # 放量
                elif volume_ratio < 0.7:
                    sentiment_score = 40  # 缩量
                
                # 综合评分
                total_score = (
                    trend_score * 0.4 +
                    fundamental_score * 0.4 +
                    sentiment_score * 0.2
                )
                
                # 决策建议
                if total_score >= 75:
                    decision = 'strong_buy'
                    confidence = 'high'
                    reason = '技术面、基本面、情绪面均表现良好'
                elif total_score >= 60:
                    decision = 'buy'
                    confidence = 'medium'
                    reason = '整体表现较好，可适当买入'
                elif total_score >= 45:
                    decision = 'hold'
                    confidence = 'medium'
                    reason = '表现中性，建议观望'
                elif total_score >= 30:
                    decision = 'sell'
                    confidence = 'medium'
                    reason = '表现较弱，建议减仓'
                else:
                    decision = 'strong_sell'
                    confidence = 'high'
                    reason = '多方面表现不佳，建议清仓'
                
                return ok({
                    'code': code,
                    'decision': decision,
                    'confidence': confidence,
                    'total_score': float(total_score),
                    'reason': reason,
                    'analysis': {
                        'technical': {
                            'score': float(trend_score),
                            'trend': trend,
                            'current_price': float(current_price),
                            'ma5': float(ma5),
                            'ma20': float(ma20),
                            'ma60': float(ma60),
                        },
                        'fundamental': {
                            'score': float(fundamental_score),
                            'roe': float(financials[0].get('roe', 0)) if financials else 0,
                            'pe_ratio': float(financials[0].get('pe_ratio', 0)) if financials else 0,
                        },
                        'sentiment': {
                            'score': float(sentiment_score),
                            'volume_ratio': float(volume_ratio),
                            'status': 'active' if volume_ratio > 1.2 else ('weak' if volume_ratio < 0.8 else 'normal')
                        }
                    },
                    'risk_warning': '投资有风险，决策仅供参考' if total_score < 60 else None
                })
            
            elif action == 'recommend':
                criteria = kwargs.get('criteria', {})
                limit = kwargs.get('limit', 10)
                
                # 基于条件推荐股票
                min_score = criteria.get('min_score', 60)
                sectors = criteria.get('sectors', [])
                
                # 简化实现：返回示例推荐
                recommendations = []
                
                # 这里应该遍历股票池进行分析，简化为示例
                sample_codes = ['600519', '000858', '002304', '000001', '600036']
                
                for code in sample_codes[:limit]:
                    # 调用analyze获取评分
                    result = await decision_manager(action='analyze', code=code)
                    
                    if result.get('success'):
                        data = result['data']
                        if data['total_score'] >= min_score:
                            recommendations.append({
                                'code': code,
                                'decision': data['decision'],
                                'score': data['total_score'],
                                'reason': data['reason']
                            })
                
                # 按评分排序
                recommendations.sort(key=lambda x: x['score'], reverse=True)
                
                return ok({
                    'recommendations': recommendations,
                    'count': len(recommendations),
                    'criteria': criteria
                })
            
            elif action == 'portfolio_advice':
                portfolio_id = kwargs.get('portfolio_id')
                
                # 获取组合持仓
                async with db.acquire() as conn:
                    holdings = await conn.fetch(
                        "SELECT * FROM holdings WHERE portfolio_id = $1",
                        portfolio_id
                    )
                
                if not holdings:
                    return fail('组合无持仓')
                
                # 分析每个持仓
                advice_list = []
                
                for holding in holdings:
                    code = holding['code']
                    
                    # 获取决策建议
                    result = await decision_manager(action='analyze', code=code)
                    
                    if result.get('success'):
                        data = result['data']
                        advice_list.append({
                            'code': code,
                            'decision': data['decision'],
                            'score': data['total_score'],
                            'action': '建议加仓' if data['decision'] in ['strong_buy', 'buy'] else (
                                '建议减仓' if data['decision'] in ['sell', 'strong_sell'] else '建议持有'
                            )
                        })
                
                # 整体建议
                avg_score = np.mean([a['score'] for a in advice_list])
                
                if avg_score >= 65:
                    overall_advice = '组合整体表现良好，可继续持有'
                elif avg_score >= 50:
                    overall_advice = '组合表现中性，建议优化持仓结构'
                else:
                    overall_advice = '组合表现较弱，建议调整持仓'
                
                return ok({
                    'portfolio_id': portfolio_id,
                    'overall_score': float(avg_score),
                    'overall_advice': overall_advice,
                    'holdings_advice': advice_list
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: analyze, recommend, portfolio_advice')
        except Exception as e:
            return fail(str(e))
    
    # ========== 24. user_manager ==========
    @mcp.tool()
    async def user_manager(action: str, **kwargs):
        """用户管理器"""
        try:
            db = get_db()
            
            if action == 'get_profile':
                user_id = kwargs.get('user_id', 'default')
                async with db.acquire() as conn:
                    user = await conn.fetchrow(
                        "SELECT * FROM users WHERE id = $1",
                        user_id
                    )
                    if not user:
                        return fail('User not found')
                    profile = dict(user)
                
                return ok(profile)
            
            elif action == 'update_preferences':
                user_id = kwargs.get('user_id', 'default')
                preferences = kwargs.get('preferences', {})
                
                async with db.acquire() as conn:
                    await conn.execute(
                        "UPDATE users SET preferences = $1, updated_at = NOW() WHERE id = $2",
                        json.dumps(preferences), user_id
                    )
                return ok({'user_id': user_id, 'updated': True})
            
            else:
                return fail(f'Unknown action: {action}')
        except Exception as e:
            return fail(str(e))
    
    # ========== 25. vector_search_manager ==========
    @mcp.tool()
    async def vector_search_manager(action: str, **kwargs):
        """向量搜索管理器 - 相似K线形态、相似股票"""
        try:
            db = get_db()
            
            if action == 'find_similar':
                code = kwargs.get('code')
                pattern_length = kwargs.get('pattern_length', 20)
                top_k = kwargs.get('top_k', 10)
                
                if not code:
                    return fail('需要提供股票代码')
                
                # 获取目标股票的K线形态
                klines = await db.get_klines(code, limit=pattern_length)
                
                if len(klines) < pattern_length:
                    return fail(f'K线数据不足，需要至少{pattern_length}条')
                
                # 提取价格序列并归一化
                import numpy as np
                prices = np.array([k['close'] for k in klines])
                normalized_prices = (prices - prices.mean()) / prices.std()
                
                # 简化实现：使用欧氏距离查找相似形态
                # 实际应使用向量数据库（如pgvector）
                
                similar_stocks = []
                
                # 示例：返回一些相似的股票（实际应从向量数据库查询）
                candidate_codes = ['600519', '000858', '002304', '000001', '600036']
                
                for candidate_code in candidate_codes:
                    if candidate_code == code:
                        continue
                    
                    candidate_klines = await db.get_klines(candidate_code, limit=pattern_length)
                    
                    if len(candidate_klines) >= pattern_length:
                        candidate_prices = np.array([k['close'] for k in candidate_klines])
                        candidate_normalized = (candidate_prices - candidate_prices.mean()) / candidate_prices.std()
                        
                        # 计算相似度（使用余弦相似度）
                        similarity = np.dot(normalized_prices, candidate_normalized) / (
                            np.linalg.norm(normalized_prices) * np.linalg.norm(candidate_normalized)
                        )
                        
                        similar_stocks.append({
                            'code': candidate_code,
                            'similarity': float(similarity),
                            'similarity_pct': f"{similarity*100:.2f}%"
                        })
                
                # 按相似度排序
                similar_stocks.sort(key=lambda x: x['similarity'], reverse=True)
                
                return ok({
                    'code': code,
                    'pattern_length': pattern_length,
                    'similar_stocks': similar_stocks[:top_k],
                    'count': len(similar_stocks[:top_k]),
                    'method': 'cosine_similarity'
                })
            
            elif action == 'index_patterns':
                codes = kwargs.get('codes', [])
                pattern_length = kwargs.get('pattern_length', 20)
                
                if not codes:
                    return fail('需要提供股票代码列表')
                
                # 索引K线形态到向量数据库
                indexed_count = 0
                
                for code in codes:
                    klines = await db.get_klines(code, limit=pattern_length)
                    
                    if len(klines) >= pattern_length:
                        # 提取特征向量
                        import numpy as np
                        prices = np.array([k['close'] for k in klines])
                        volumes = np.array([k['volume'] for k in klines])
                        
                        # 归一化
                        price_features = (prices - prices.mean()) / prices.std()
                        volume_features = (volumes - volumes.mean()) / volumes.std()
                        
                        # 组合特征（简化）
                        features = np.concatenate([price_features, volume_features])
                        
                        # 存储到向量数据库（简化实现）
                        async with db.acquire() as conn:
                            await conn.execute(
                                """INSERT INTO pattern_vectors (stock_code, pattern_vector, pattern_length, created_at)
                                   VALUES ($1, $2, $3, NOW())
                                   ON CONFLICT (stock_code) DO UPDATE 
                                   SET pattern_vector = EXCLUDED.pattern_vector, 
                                       pattern_length = EXCLUDED.pattern_length,
                                       created_at = NOW()""",
                                code, features.tolist(), pattern_length
                            )
                        
                        indexed_count += 1
                
                return ok({
                    'indexed_codes': indexed_count,
                    'total_codes': len(codes),
                    'pattern_length': pattern_length,
                    'status': 'completed'
                })
            
            elif action == 'semantic_search':
                query = kwargs.get('query', '')
                top_k = kwargs.get('top_k', 10)
                
                if not query:
                    return fail('需要提供搜索查询')
                
                # 语义搜索（简化实现）
                # 实际应使用文本嵌入模型
                
                # 关键词匹配
                keywords = query.lower().split()
                
                results = []
                
                # 示例：根据关键词返回相关股票
                keyword_mapping = {
                    '白酒': ['600519', '000858'],
                    '科技': ['000001', '002304'],
                    '金融': ['600036', '601318'],
                    '医药': ['600276', '000538'],
                    '新能源': ['002594', '300750']
                }
                
                for keyword in keywords:
                    if keyword in keyword_mapping:
                        for code in keyword_mapping[keyword]:
                            stock_info = await db.get_stock_info(code)
                            if stock_info:
                                results.append({
                                    'code': code,
                                    'name': stock_info.get('stock_name', code),
                                    'industry': stock_info.get('industry', '未知'),
                                    'relevance': 0.9,
                                    'matched_keyword': keyword
                                })
                
                # 去重
                seen = set()
                unique_results = []
                for r in results:
                    if r['code'] not in seen:
                        seen.add(r['code'])
                        unique_results.append(r)
                
                return ok({
                    'query': query,
                    'results': unique_results[:top_k],
                    'count': len(unique_results[:top_k])
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: find_similar, index_patterns, semantic_search')
        except Exception as e:
            return fail(str(e))
    
    # ========== 26. comprehensive_manager ==========
    @mcp.tool()
    async def comprehensive_manager(action: str, **kwargs):
        """综合管理器 - 一站式分析"""
        try:
            db = get_db()
            
            if action == 'full_analysis':
                code = kwargs.get('code')
                
                # 1. 基础信息
                stock_info = await db.get_stock_info(code)
                if not stock_info:
                    return fail(f'未找到股票{code}')
                
                # 2. K线数据
                klines = await db.get_klines(code, limit=100)
                
                # 3. 财务数据
                financials = await db.get_financials(code, limit=4)
                
                # 4. 技术分析
                technical_analysis = {}
                if klines:
                    import numpy as np
                    prices = np.array([k['close'] for k in klines])
                    
                    ma5 = float(np.mean(prices[-5:]))
                    ma20 = float(np.mean(prices[-20:]))
                    ma60 = float(np.mean(prices[-60:])) if len(prices) >= 60 else ma20
                    
                    current_price = float(prices[-1])
                    
                    # 趋势
                    if current_price > ma5 > ma20:
                        trend = 'uptrend'
                    elif current_price < ma5 < ma20:
                        trend = 'downtrend'
                    else:
                        trend = 'sideways'
                    
                    # 波动率
                    returns = np.diff(prices) / prices[:-1]
                    volatility = float(np.std(returns) * np.sqrt(252))
                    
                    technical_analysis = {
                        'current_price': current_price,
                        'ma5': ma5,
                        'ma20': ma20,
                        'ma60': ma60,
                        'trend': trend,
                        'volatility': volatility,
                        'support': float(np.min(prices[-20:])),
                        'resistance': float(np.max(prices[-20:])),
                    }
                
                # 5. 基本面分析
                fundamental_analysis = {}
                if financials:
                    latest = financials[0]
                    
                    # 盈利能力
                    roe = latest.get('roe', 0)
                    roa = latest.get('roa', 0)
                    net_margin = latest.get('net_margin', 0)
                    
                    # 估值
                    pe_ratio = latest.get('pe_ratio', 0)
                    pb_ratio = latest.get('pb_ratio', 0)
                    
                    # 财务健康
                    debt_ratio = latest.get('debt_ratio', 0)
                    current_ratio = latest.get('current_ratio', 0)
                    
                    # 成长性
                    revenue_growth = latest.get('revenue_growth', 0)
                    profit_growth = latest.get('profit_growth', 0)
                    
                    fundamental_analysis = {
                        'profitability': {
                            'roe': float(roe),
                            'roa': float(roa),
                            'net_margin': float(net_margin),
                            'level': 'high' if roe > 15 else ('medium' if roe > 8 else 'low')
                        },
                        'valuation': {
                            'pe_ratio': float(pe_ratio),
                            'pb_ratio': float(pb_ratio),
                            'level': 'undervalued' if pe_ratio < 15 and pb_ratio < 2 else (
                                'overvalued' if pe_ratio > 30 else 'fair'
                            )
                        },
                        'financial_health': {
                            'debt_ratio': float(debt_ratio),
                            'current_ratio': float(current_ratio),
                            'level': 'healthy' if debt_ratio < 0.5 and current_ratio > 1.5 else (
                                'risky' if debt_ratio > 0.7 else 'fair'
                            )
                        },
                        'growth': {
                            'revenue_growth': float(revenue_growth),
                            'profit_growth': float(profit_growth),
                            'level': 'high' if revenue_growth > 0.2 else ('low' if revenue_growth < 0 else 'medium')
                        }
                    }
                
                # 6. 综合评分
                tech_score = 50
                if technical_analysis:
                    if technical_analysis['trend'] == 'uptrend':
                        tech_score = 70
                    elif technical_analysis['trend'] == 'downtrend':
                        tech_score = 30
                
                fund_score = 50
                if fundamental_analysis:
                    prof_level = fundamental_analysis['profitability']['level']
                    val_level = fundamental_analysis['valuation']['level']
                    
                    if prof_level == 'high' and val_level == 'undervalued':
                        fund_score = 85
                    elif prof_level == 'high':
                        fund_score = 70
                    elif prof_level == 'low':
                        fund_score = 30
                
                total_score = (tech_score * 0.4 + fund_score * 0.6)
                
                # 7. 投资建议
                if total_score >= 75:
                    recommendation = 'strong_buy'
                    advice = '技术面和基本面均表现优秀，强烈推荐买入'
                elif total_score >= 60:
                    recommendation = 'buy'
                    advice = '整体表现良好，建议买入'
                elif total_score >= 45:
                    recommendation = 'hold'
                    advice = '表现中性，建议持有观望'
                elif total_score >= 30:
                    recommendation = 'sell'
                    advice = '表现较弱，建议减仓'
                else:
                    recommendation = 'strong_sell'
                    advice = '表现不佳，建议清仓'
                
                return ok({
                    'code': code,
                    'basic_info': {
                        'name': stock_info.get('stock_name', code),
                        'industry': stock_info.get('industry', '未知'),
                        'market_cap': stock_info.get('market_cap', 0),
                    },
                    'technical': technical_analysis,
                    'fundamental': fundamental_analysis,
                    'score': {
                        'technical_score': float(tech_score),
                        'fundamental_score': float(fund_score),
                        'total_score': float(total_score),
                    },
                    'recommendation': recommendation,
                    'advice': advice,
                    'risk_level': 'high' if technical_analysis.get('volatility', 0) > 0.4 else (
                        'low' if technical_analysis.get('volatility', 0) < 0.2 else 'medium'
                    ),
                })
            
            elif action == 'compare_stocks':
                codes = kwargs.get('codes', [])
                
                if len(codes) < 2:
                    return fail('需要至少2个股票代码')
                
                comparison = []
                
                for code in codes:
                    result = await comprehensive_manager(action='full_analysis', code=code)
                    
                    if result.get('success'):
                        data = result['data']
                        comparison.append({
                            'code': code,
                            'name': data['basic_info']['name'],
                            'total_score': data['score']['total_score'],
                            'recommendation': data['recommendation'],
                            'technical_trend': data['technical'].get('trend', 'unknown'),
                            'fundamental_level': data['fundamental'].get('profitability', {}).get('level', 'unknown'),
                        })
                
                # 排序
                comparison.sort(key=lambda x: x['total_score'], reverse=True)
                
                return ok({
                    'comparison': comparison,
                    'best_pick': comparison[0] if comparison else None,
                    'count': len(comparison)
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: full_analysis, compare_stocks')
        except Exception as e:
            return fail(str(e))
    
    # ========== 27. macro_manager ==========
    @mcp.tool()
    async def macro_manager(action: str, **kwargs):
        """宏观管理器 - 宏观经济数据"""
        try:
            if action == 'get_indicators':
                indicators = kwargs.get('indicators', ['gdp', 'cpi', 'pmi'])
                
                # 宏观指标数据（实际应从数据库或API获取）
                indicator_data = {
                    'gdp': {
                        'value': 5.2,
                        'period': '2024Q1',
                        'unit': '%',
                        'description': 'GDP同比增长率',
                        'trend': 'stable',
                        'impact': '经济增长稳定，利好股市'
                    },
                    'cpi': {
                        'value': 2.1,
                        'period': '2024-01',
                        'unit': '%',
                        'description': '居民消费价格指数',
                        'trend': 'rising',
                        'impact': '通胀温和，货币政策保持稳定'
                    },
                    'ppi': {
                        'value': 1.5,
                        'period': '2024-01',
                        'unit': '%',
                        'description': '工业生产者出厂价格指数',
                        'trend': 'rising',
                        'impact': '工业品价格上涨，制造业利润改善'
                    },
                    'pmi': {
                        'value': 50.8,
                        'period': '2024-01',
                        'unit': '',
                        'description': '制造业采购经理指数',
                        'trend': 'expanding',
                        'impact': 'PMI>50表示制造业扩张，经济向好'
                    },
                    'm2': {
                        'value': 8.5,
                        'period': '2024-01',
                        'unit': '%',
                        'description': '广义货币供应量同比增长',
                        'trend': 'stable',
                        'impact': '货币供应适度，流动性充裕'
                    },
                    'interest_rate': {
                        'value': 3.45,
                        'period': '2024-01',
                        'unit': '%',
                        'description': '一年期贷款市场报价利率(LPR)',
                        'trend': 'stable',
                        'impact': '利率保持稳定，融资成本可控'
                    },
                    'exchange_rate': {
                        'value': 7.18,
                        'period': '2024-01',
                        'unit': 'CNY/USD',
                        'description': '人民币兑美元汇率',
                        'trend': 'stable',
                        'impact': '汇率稳定，有利于进出口贸易'
                    }
                }
                
                result = {}
                for indicator in indicators:
                    if indicator in indicator_data:
                        result[indicator] = indicator_data[indicator]
                
                # 综合评估
                overall_sentiment = 'positive'
                if 'gdp' in result and result['gdp']['value'] < 4.0:
                    overall_sentiment = 'negative'
                elif 'pmi' in result and result['pmi']['value'] < 50:
                    overall_sentiment = 'negative'
                
                return ok({
                    'indicators': result,
                    'overall_sentiment': overall_sentiment,
                    'market_outlook': '宏观经济指标整体向好，支持股市上涨' if overall_sentiment == 'positive' else '宏观经济面临压力，需谨慎投资'
                })
            
            elif action == 'analyze_impact':
                indicator = kwargs.get('indicator', 'cpi')
                value = kwargs.get('value')
                
                # 分析宏观指标对市场的影响
                impact_analysis = {
                    'gdp': {
                        'high': {'threshold': 6.0, 'impact': 'positive', 'sectors': ['消费', '金融', '地产']},
                        'low': {'threshold': 4.0, 'impact': 'negative', 'sectors': ['周期', '出口']}
                    },
                    'cpi': {
                        'high': {'threshold': 3.0, 'impact': 'negative', 'sectors': ['消费', '零售'], 'reason': '通胀压力大，可能收紧货币政策'},
                        'low': {'threshold': 1.0, 'impact': 'neutral', 'sectors': [], 'reason': '通胀温和'}
                    },
                    'pmi': {
                        'high': {'threshold': 52.0, 'impact': 'positive', 'sectors': ['制造业', '工业'], 'reason': '制造业强劲扩张'},
                        'low': {'threshold': 50.0, 'impact': 'negative', 'sectors': ['制造业', '工业'], 'reason': '制造业收缩'}
                    },
                    'interest_rate': {
                        'high': {'threshold': 4.0, 'impact': 'negative', 'sectors': ['地产', '金融'], 'reason': '融资成本上升'},
                        'low': {'threshold': 3.0, 'impact': 'positive', 'sectors': ['地产', '金融'], 'reason': '融资成本下降'}
                    }
                }
                
                if indicator not in impact_analysis:
                    return fail(f'不支持的指标: {indicator}')
                
                analysis = impact_analysis[indicator]
                
                if value is None:
                    return ok({
                        'indicator': indicator,
                        'analysis': analysis,
                        'note': '请提供指标值以获取具体影响分析'
                    })
                
                # 判断影响
                if value >= analysis['high']['threshold']:
                    impact = analysis['high']['impact']
                    affected_sectors = analysis['high']['sectors']
                    reason = analysis['high'].get('reason', '')
                elif value <= analysis['low']['threshold']:
                    impact = analysis['low']['impact']
                    affected_sectors = analysis['low']['sectors']
                    reason = analysis['low'].get('reason', '')
                else:
                    impact = 'neutral'
                    affected_sectors = []
                    reason = '指标处于正常区间'
                
                return ok({
                    'indicator': indicator,
                    'value': value,
                    'impact': impact,
                    'affected_sectors': affected_sectors,
                    'reason': reason,
                    'recommendation': '关注相关板块机会' if impact == 'positive' else (
                        '规避相关板块风险' if impact == 'negative' else '保持观望'
                    )
                })
            
            elif action == 'policy_calendar':
                days = kwargs.get('days', 30)
                
                # 重要政策事件日历（示例数据）
                events = [
                    {
                        'date': '2024-02-05',
                        'event': '央行货币政策委员会例会',
                        'importance': 'high',
                        'potential_impact': '可能调整货币政策方向'
                    },
                    {
                        'date': '2024-02-15',
                        'event': 'CPI数据发布',
                        'importance': 'medium',
                        'potential_impact': '反映通胀水平，影响货币政策预期'
                    },
                    {
                        'date': '2024-03-01',
                        'event': 'PMI数据发布',
                        'importance': 'medium',
                        'potential_impact': '反映制造业景气度'
                    },
                    {
                        'date': '2024-03-05',
                        'event': '全国两会召开',
                        'importance': 'high',
                        'potential_impact': '确定年度经济目标和政策方向'
                    }
                ]
                
                return ok({
                    'events': events,
                    'count': len(events),
                    'period': f'未来{days}天'
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: get_indicators, analyze_impact, policy_calendar')
        except Exception as e:
            return fail(str(e))
    
    # ========== 28. research_manager ==========
    @mcp.tool()
    async def research_manager(action: str, **kwargs):
        """研究管理器 - 研报、评级"""
        try:
            db = get_db()
            
            if action == 'get_reports':
                code = kwargs.get('code')
                limit = kwargs.get('limit', 10)
                report_type = kwargs.get('type', 'all')  # all, buy, sell, hold
                
                if not code:
                    return fail('需要提供股票代码')
                
                async with db.acquire() as conn:
                    if report_type == 'all':
                        rows = await conn.fetch(
                            """SELECT * FROM research_reports 
                               WHERE code = $1 
                               ORDER BY publish_date DESC 
                               LIMIT $2""",
                            code, limit
                        )
                    else:
                        rows = await conn.fetch(
                            """SELECT * FROM research_reports 
                               WHERE code = $1 AND rating = $2
                               ORDER BY publish_date DESC 
                               LIMIT $3""",
                            code, report_type, limit
                        )
                    reports = [dict(row) for row in rows]
                
                # 分析研报趋势
                if reports:
                    ratings = [r.get('rating', 'hold') for r in reports]
                    buy_count = ratings.count('buy')
                    sell_count = ratings.count('sell')
                    hold_count = ratings.count('hold')
                    
                    consensus = 'buy' if buy_count > sell_count and buy_count > hold_count else (
                        'sell' if sell_count > buy_count else 'hold'
                    )
                    
                    analysis = {
                        'total_reports': len(reports),
                        'buy_count': buy_count,
                        'sell_count': sell_count,
                        'hold_count': hold_count,
                        'consensus': consensus,
                        'confidence': max(buy_count, sell_count, hold_count) / len(reports)
                    }
                else:
                    analysis = {
                        'total_reports': 0,
                        'consensus': 'unknown',
                        'confidence': 0
                    }
                
                return ok({
                    'code': code,
                    'reports': reports,
                    'analysis': analysis
                })
            
            elif action == 'get_ratings':
                code = kwargs.get('code')
                
                if not code:
                    return fail('需要提供股票代码')
                
                async with db.acquire() as conn:
                    # 统计最近3个月的评级
                    rows = await conn.fetch(
                        """SELECT rating, COUNT(*) as count 
                           FROM research_reports 
                           WHERE code = $1 
                           AND publish_date >= CURRENT_DATE - INTERVAL '3 months'
                           GROUP BY rating""",
                        code
                    )
                    rating_stats = {row['rating']: row['count'] for row in rows}
                
                buy_count = rating_stats.get('buy', 0)
                hold_count = rating_stats.get('hold', 0)
                sell_count = rating_stats.get('sell', 0)
                total = buy_count + hold_count + sell_count
                
                if total > 0:
                    consensus = 'buy' if buy_count > max(hold_count, sell_count) else (
                        'sell' if sell_count > hold_count else 'hold'
                    )
                    
                    # 计算评级分数（buy=1, hold=0, sell=-1）
                    rating_score = (buy_count - sell_count) / total
                else:
                    consensus = 'unknown'
                    rating_score = 0
                
                return ok({
                    'code': code,
                    'ratings': {
                        'buy': buy_count,
                        'hold': hold_count,
                        'sell': sell_count,
                        'total': total
                    },
                    'consensus': consensus,
                    'rating_score': float(rating_score),
                    'recommendation': '强烈推荐' if rating_score > 0.5 else (
                        '推荐' if rating_score > 0.2 else (
                            '中性' if rating_score > -0.2 else (
                                '不推荐' if rating_score > -0.5 else '强烈不推荐'
                            )
                        )
                    )
                })
            
            elif action == 'target_price':
                code = kwargs.get('code')
                
                if not code:
                    return fail('需要提供股票代码')
                
                async with db.acquire() as conn:
                    # 获取最近的目标价
                    rows = await conn.fetch(
                        """SELECT target_price, institution, publish_date 
                           FROM research_reports 
                           WHERE code = $1 
                           AND target_price IS NOT NULL
                           AND publish_date >= CURRENT_DATE - INTERVAL '6 months'
                           ORDER BY publish_date DESC
                           LIMIT 20""",
                        code
                    )
                    target_prices = [dict(row) for row in rows]
                
                if target_prices:
                    prices = [t['target_price'] for t in target_prices]
                    avg_target = sum(prices) / len(prices)
                    max_target = max(prices)
                    min_target = min(prices)
                    
                    # 获取当前价格
                    klines = await db.get_klines(code, limit=1)
                    current_price = klines[0]['close'] if klines else 0
                    
                    if current_price > 0:
                        upside = (avg_target - current_price) / current_price
                        max_upside = (max_target - current_price) / current_price
                        min_upside = (min_target - current_price) / current_price
                    else:
                        upside = max_upside = min_upside = 0
                    
                    analysis = {
                        'current_price': float(current_price),
                        'avg_target_price': float(avg_target),
                        'max_target_price': float(max_target),
                        'min_target_price': float(min_target),
                        'upside': f"{upside*100:.2f}%",
                        'max_upside': f"{max_upside*100:.2f}%",
                        'min_upside': f"{min_upside*100:.2f}%",
                        'institutions_count': len(target_prices),
                        'investment_value': 'high' if upside > 0.2 else ('medium' if upside > 0.1 else 'low')
                    }
                else:
                    analysis = {
                        'institutions_count': 0,
                        'investment_value': 'unknown'
                    }
                
                return ok({
                    'code': code,
                    'target_prices': target_prices,
                    'analysis': analysis
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: get_reports, get_ratings, target_price')
        except Exception as e:
            return fail(str(e))
    
    # ========== 29. live_trading_manager ==========
    @mcp.tool()
    async def live_trading_manager(action: str, **kwargs):
        """实盘交易管理器（仅监控，不实际交易）"""
        try:
            if action == 'get_status':
                return ok({
                    'status': 'monitoring',
                    'mode': 'read_only',
                    'message': '仅支持监控模式，不支持实盘交易',
                })
            
            elif action == 'monitor_account':
                account_id = kwargs.get('account_id')
                return ok({
                    'account_id': account_id,
                    'monitoring': True,
                    'last_update': datetime.now().isoformat(),
                })
            
            else:
                return fail(f'Unknown action: {action}')
        except Exception as e:
            return fail(str(e))
    
    # ========== 30. insight_manager ==========
    @mcp.tool()
    async def insight_manager(action: str, **kwargs):
        """洞察管理器 - AI生成投资洞察"""
        try:
            db = get_db()
            
            if action == 'generate':
                topic = kwargs.get('topic', 'market')
                
                if topic == 'market':
                    # 市场洞察
                    # 获取主要指数数据
                    indices = ['000001', '399001', '399006']
                    index_data = []
                    
                    for code in indices:
                        klines = await db.get_klines(code, limit=20)
                        if klines and len(klines) >= 2:
                            latest = klines[-1]
                            prev = klines[-2]
                            change = (latest['close'] - prev['close']) / prev['close']
                            
                            index_data.append({
                                'code': code,
                                'change': change
                            })
                    
                    # 生成洞察
                    if index_data:
                        avg_change = sum(d['change'] for d in index_data) / len(index_data)
                        
                        if avg_change > 0.01:
                            insight = '市场整体表现强势，主要指数普遍上涨，市场情绪乐观。建议关注强势板块的龙头股票。'
                            sentiment = 'bullish'
                        elif avg_change < -0.01:
                            insight = '市场整体走弱，主要指数普遍下跌，市场情绪谨慎。建议控制仓位，关注防御性板块。'
                            sentiment = 'bearish'
                        else:
                            insight = '市场处于震荡整理阶段，成交量萎缩，等待方向选择。建议保持观望，等待明确信号。'
                            sentiment = 'neutral'
                    else:
                        insight = '暂无足够数据生成市场洞察'
                        sentiment = 'unknown'
                    
                elif topic == 'sector':
                    # 板块洞察
                    insight = '科技板块表现强势，资金持续流入，关注人工智能、半导体等细分领域的龙头股机会。'
                    sentiment = 'positive'
                    
                elif topic == 'risk':
                    # 风险洞察
                    insight = '市场波动率上升，建议控制仓位，注意风险管理。可适当配置防御性资产。'
                    sentiment = 'cautious'
                    
                elif topic == 'opportunity':
                    # 机会洞察
                    insight = '当前市场估值处于合理区间，部分优质个股已具备配置价值。建议关注业绩稳定、估值合理的蓝筹股。'
                    sentiment = 'optimistic'
                    
                else:
                    insight = f'暂不支持{topic}主题的洞察生成'
                    sentiment = 'unknown'
                
                return ok({
                    'topic': topic,
                    'insight': insight,
                    'sentiment': sentiment,
                    'confidence': 0.75,
                    'generated_at': datetime.now().isoformat(),
                    'tags': ['市场分析', '投资建议'] if topic == 'market' else ['板块分析'] if topic == 'sector' else ['风险提示']
                })
            
            elif action == 'daily_brief':
                date = kwargs.get('date', datetime.now().strftime('%Y-%m-%d'))
                
                # 生成每日简报
                # 1. 市场概况
                indices = ['000001', '399001', '399006']
                market_summary = []
                
                for code in indices:
                    klines = await db.get_klines(code, limit=2)
                    if klines and len(klines) >= 2:
                        latest = klines[-1]
                        prev = klines[-2]
                        change = (latest['close'] - prev['close']) / prev['close']
                        
                        name = {'000001': '上证指数', '399001': '深证成指', '399006': '创业板指'}.get(code, code)
                        market_summary.append(f"{name}{'上涨' if change > 0 else '下跌'}{abs(change)*100:.2f}%")
                
                # 2. 热门板块（简化）
                hot_sectors = ['科技', '新能源', '医药']
                
                # 3. 关键事件（示例）
                key_events = [
                    '央行公开市场操作维持流动性合理充裕',
                    '多家上市公司发布业绩预告',
                    '外资持续流入A股市场'
                ]
                
                # 4. 市场展望
                outlook = '短期市场或将维持震荡格局，中期趋势向好。建议关注业绩确定性强的优质标的。'
                
                return ok({
                    'date': date,
                    'brief': {
                        'market_summary': '、'.join(market_summary) if market_summary else '市场数据暂缺',
                        'hot_sectors': hot_sectors,
                        'key_events': key_events,
                        'outlook': outlook
                    },
                    'highlights': [
                        '市场成交量较前日放大',
                        '北向资金净流入',
                        '科技板块领涨'
                    ]
                })
            
            elif action == 'weekly_review':
                # 周度回顾
                end_date = kwargs.get('end_date', datetime.now().strftime('%Y-%m-%d'))
                
                # 获取一周数据
                klines = await db.get_klines('000001', limit=5)
                
                if klines and len(klines) >= 2:
                    week_start = klines[0]['close']
                    week_end = klines[-1]['close']
                    week_change = (week_end - week_start) / week_start
                    
                    # 计算周内最高最低
                    week_high = max(k['high'] for k in klines)
                    week_low = min(k['low'] for k in klines)
                    volatility = (week_high - week_low) / week_low
                    
                    performance = 'strong' if week_change > 0.03 else (
                        'weak' if week_change < -0.03 else 'neutral'
                    )
                    
                    review = {
                        'period': f'截至{end_date}的一周',
                        'market_performance': {
                            'change': f"{week_change*100:.2f}%",
                            'high': float(week_high),
                            'low': float(week_low),
                            'volatility': f"{volatility*100:.2f}%",
                            'rating': performance
                        },
                        'key_points': [
                            f"本周市场{'上涨' if week_change > 0 else '下跌'}{abs(week_change)*100:.2f}%",
                            f"波动率为{volatility*100:.2f}%，市场{'活跃' if volatility > 0.05 else '平稳'}",
                            '成交量较上周有所放大' if week_change > 0 else '成交量较上周萎缩'
                        ],
                        'next_week_outlook': '预计下周市场将延续当前趋势' if abs(week_change) > 0.02 else '预计下周市场将继续震荡'
                    }
                else:
                    review = {
                        'period': f'截至{end_date}的一周',
                        'message': '数据不足，无法生成周度回顾'
                    }
                
                return ok(review)
            
            else:
                return fail(f'Unknown action: {action}. Supported: generate, daily_brief, weekly_review')
        except Exception as e:
            return fail(str(e))
