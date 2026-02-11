"""风险管理器 - VaR、压力测试、风险敞口"""

import json
from typing import Optional
from ...storage import get_db
from ...utils import ok, fail
import numpy as np


def _normalize_kwargs(kwargs: dict) -> dict:
    """统一解析 kwargs 参数（兼容 JSON 字符串和 dict）"""
    raw = kwargs.get("kwargs")
    if isinstance(raw, dict):
        kwargs = {**kwargs, **raw}
    elif isinstance(raw, str):
        try:
            extra = json.loads(raw or "{}")
            if isinstance(extra, dict):
                kwargs = {**kwargs, **extra}
        except Exception:
            pass
    return kwargs


def _safe_portfolio_id(val):
    """将 portfolio_id 转为 int（DB schema 为 SERIAL）"""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return val


def register_risk_manager(mcp):
    """注册风险管理器工具"""
    
    @mcp.tool()
    async def risk_manager(action: str, **kwargs):
        """风险管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/list/calculate_var/stress_test/risk_exposure
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - list: 无需额外参数（列出风险指标）
                - calculate_var: codes(list[str]), weights(list[float]), confidence(float, optional, 默认0.95), lookback_days(int, optional)
                - stress_test: codes(list[str]), weights(list[float]), scenarios(list[str], optional, 如 "market_crash")
                - risk_exposure: codes(list[str]), weights(list[float])

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            risk_manager(action="help", kwargs="{}")
            # 计算VaR
            risk_manager(action="calculate_var", kwargs='{"codes":["600519","000858"],"weights":[0.6,0.4],"confidence":0.95}')
            # 压力测试
            risk_manager(action="stress_test", kwargs='{"codes":["600519","000858"],"weights":[0.6,0.4],"scenarios":["market_crash"]}')
            # 风险敞口
            risk_manager(action="risk_exposure", kwargs='{"codes":["600519","000858"],"weights":[0.6,0.4]}')
        """
        try:
            db = get_db()
            kwargs = _normalize_kwargs(dict(kwargs))
            
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'list': '列出支持的操作和参数说明',
                        'calculate_var': '计算组合 VaR/CVaR（需要 portfolio_id）',
                        'stress_test': '压力测试（需要 portfolio_id, scenario）',
                        'risk_exposure': '组合风险敞口与集中度（需要 portfolio_id）',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'list':
                return ok({
                    'actions': [
                        {'action': 'calculate_var', 'description': '计算组合 VaR/CVaR', 'kwargs': 'portfolio_id, confidence(0.95), method(historical|parametric|monte_carlo)'},
                        {'action': 'stress_test', 'description': '压力测试', 'kwargs': 'portfolio_id, scenario(market_crash|black_swan|interest_rate_hike|sector_rotation|liquidity_crisis)'},
                        {'action': 'risk_exposure', 'description': '组合风险敞口与集中度', 'kwargs': 'portfolio_id'},
                    ],
                    'count': 3,
                })
            
            elif action == 'calculate_var':
                portfolio_id = _safe_portfolio_id(kwargs.get('portfolio_id'))
                confidence = kwargs.get('confidence', 0.95)
                method = kwargs.get('method', 'historical')
                
                async with db.acquire() as conn:
                    holdings = await conn.fetch(
                        "SELECT * FROM holdings WHERE portfolio_id = $1",
                        portfolio_id
                    )
                    
                    if not holdings:
                        return ok({
                            'message': '当前组合无持仓，请先添加持仓后再操作',
                            'quick_start': {
                                'step1': 'portfolio_manager(action="add_holding", portfolio_id="xxx", code="600519", shares=100)',
                                'step2': 'risk_manager(action="calculate_var", portfolio_id="xxx")'
                            }
                        })
                
                returns_data = []
                total_value = 0
                
                for holding in holdings:
                    code = holding['code']
                    shares = holding['shares']
                    
                    klines = await db.get_klines(code, limit=252)
                    if len(klines) < 2:
                        continue
                    
                    prices = [k['close'] for k in klines]
                    returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
                    
                    current_value = shares * prices[-1]
                    total_value += current_value
                    
                    returns_data.append({
                        'code': code,
                        'returns': returns,
                        'weight': 0,
                        'current_value': current_value
                    })
                
                for item in returns_data:
                    item['weight'] = item['current_value'] / total_value if total_value > 0 else 0
                
                min_length = min(len(item['returns']) for item in returns_data)
                portfolio_returns = []
                
                for i in range(min_length):
                    daily_return = sum(item['returns'][i] * item['weight'] for item in returns_data)
                    portfolio_returns.append(daily_return)
                
                portfolio_returns = np.array(portfolio_returns)
                
                if method == 'historical':
                    var = np.percentile(portfolio_returns, (1 - confidence) * 100)
                    var_amount = abs(var * total_value)
                    
                elif method == 'parametric':
                    from scipy import stats
                    mean = np.mean(portfolio_returns)
                    std = np.std(portfolio_returns)
                    var = stats.norm.ppf(1 - confidence, mean, std)
                    var_amount = abs(var * total_value)
                    
                else:
                    mean = np.mean(portfolio_returns)
                    std = np.std(portfolio_returns)
                    simulations = np.random.normal(mean, std, 10000)
                    var = np.percentile(simulations, (1 - confidence) * 100)
                    var_amount = abs(var * total_value)
                
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
                portfolio_id = _safe_portfolio_id(kwargs.get('portfolio_id'))
                scenario = kwargs.get('scenario', 'market_crash')
                
                async with db.acquire() as conn:
                    holdings = await conn.fetch(
                        "SELECT * FROM holdings WHERE portfolio_id = $1",
                        portfolio_id
                    )
                    
                    if not holdings:
                        return ok({
                            'message': '当前组合无持仓，请先添加持仓后再操作',
                            'quick_start': {
                                'step1': 'portfolio_manager(action="add_holding", portfolio_id="xxx", code="600519", shares=100)',
                                'step2': 'risk_manager(action="stress_test", portfolio_id="xxx", scenario="market_crash")'
                            }
                        })
                
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
                
                total_value = 0
                stressed_value = 0
                
                for holding in holdings:
                    code = holding['code']
                    shares = holding['shares']
                    
                    klines = await db.get_klines(code, limit=1)
                    if not klines:
                        continue
                    
                    current_price = klines[0]['close']
                    current_value = shares * current_price
                    total_value += current_value
                    
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
                portfolio_id = _safe_portfolio_id(kwargs.get('portfolio_id'))
                
                async with db.acquire() as conn:
                    holdings = await conn.fetch(
                        "SELECT * FROM holdings WHERE portfolio_id = $1",
                        portfolio_id
                    )
                    
                    if not holdings:
                        return ok({
                            'message': '当前组合无持仓，请先添加持仓后再操作',
                            'quick_start': {
                                'step1': 'portfolio_manager(action="add_holding", portfolio_id="xxx", code="600519", shares=100)',
                                'step2': 'risk_manager(action="risk_exposure", portfolio_id="xxx")'
                            }
                        })
                
                total_value = 0
                sector_exposure = {}
                stock_exposure = []
                
                for holding in holdings:
                    code = holding['code']
                    shares = holding['shares']
                    
                    stock_info = await db.get_stock_info(code)
                    klines = await db.get_klines(code, limit=1)
                    
                    if not klines:
                        continue
                    
                    current_price = klines[0]['close']
                    current_value = shares * current_price
                    total_value += current_value
                    
                    sector = stock_info.get('industry', '未知') if stock_info else '未知'
                    
                    if sector not in sector_exposure:
                        sector_exposure[sector] = 0
                    sector_exposure[sector] += current_value
                    
                    stock_exposure.append({
                        'code': code,
                        'name': stock_info.get('stock_name', code) if stock_info else code,
                        'value': float(current_value),
                        'weight': 0,
                        'sector': sector
                    })
                
                for item in stock_exposure:
                    item['weight'] = f"{(item['value'] / total_value * 100):.2f}%" if total_value > 0 else "0%"
                
                for sector in sector_exposure:
                    sector_exposure[sector] = f"{(sector_exposure[sector] / total_value * 100):.2f}%" if total_value > 0 else "0%"
                
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
                
                stock_exposure.sort(key=lambda x: x['value'], reverse=True)
                
                return ok({
                    'portfolio_id': portfolio_id,
                    'total_value': float(total_value),
                    'stock_exposure': stock_exposure[:10],
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
                return fail(f'Unknown action: {action}. Supported: help, list, calculate_var, stress_test, risk_exposure')
        except Exception as e:
            return fail(str(e))
