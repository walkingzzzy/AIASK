"""期权管理器 - Black-Scholes定价和Greeks计算"""

from typing import Optional
import json
from ...utils import ok, fail


def _normalize_kwargs(kwargs: dict) -> dict:
    extra = kwargs.get("kwargs")
    if extra is not None:
        if isinstance(extra, str):
            try:
                extra = json.loads(extra or "{}")
            except Exception:
                extra = None
        if isinstance(extra, dict):
            kwargs = {**kwargs, **extra}
    if kwargs.get("option_price") is None:
        kwargs["option_price"] = kwargs.get("OptionPrice") or kwargs.get("price")
    # 参数别名统一
    if kwargs.get("expiry_date") is None:
        kwargs["expiry_date"] = kwargs.get("maturity") or kwargs.get("expiry") or kwargs.get("expire_date") or kwargs.get("expiration") or kwargs.get("expiry_date_str")
    if kwargs.get("time_to_maturity") is None:
        kwargs["time_to_maturity"] = kwargs.get("time") or kwargs.get("ttm") or kwargs.get("maturity_years") or kwargs.get("time_to_expiry") or kwargs.get("t") or kwargs.get("T") or kwargs.get("years") or kwargs.get("time_years")
    if kwargs.get("risk_free_rate") is None:
        kwargs["risk_free_rate"] = kwargs.get("rate") or kwargs.get("rf_rate") or kwargs.get("rf") or kwargs.get("r") or kwargs.get("risk_free") or kwargs.get("riskfree")
    if kwargs.get("volatility") is None:
        kwargs["volatility"] = kwargs.get("vol") or kwargs.get("sigma") or kwargs.get("iv") or kwargs.get("implied_vol")
    if kwargs.get("dividend_yield") is None:
        kwargs["dividend_yield"] = kwargs.get("div_yield") or kwargs.get("dividend") or kwargs.get("q") or kwargs.get("div")
    if kwargs.get("spot") is None:
        kwargs["spot"] = kwargs.get("S") or kwargs.get("s") or kwargs.get("spot_price") or kwargs.get("current_price") or kwargs.get("underlying_price")
    if kwargs.get("strike") is None:
        kwargs["strike"] = kwargs.get("K") or kwargs.get("k") or kwargs.get("strike_price") or kwargs.get("exercise_price")
    if kwargs.get("option_type") is None:
        kwargs["option_type"] = kwargs.get("type") or kwargs.get("cp") or kwargs.get("call_put")
    return kwargs


def register_options_manager(mcp):
    """注册期权管理器工具"""
    
    @mcp.tool()
    async def options_manager(action: str, **kwargs):
        """期权管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/list/calculate_greeks/calculate_price/implied_volatility
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - list: underlying(str, 如 "510050"), expiry_month(str, optional)
                - calculate_greeks: S(float, 标的价格), K(float, 行权价), T(float, 到期时间/年), r(float, 无风险利率), sigma(float, 波动率), option_type(str, "call"/"put")
                - calculate_price: 同 calculate_greeks
                - implied_volatility: S(float), K(float), T(float), r(float), market_price(float), option_type(str)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            options_manager(action="help", kwargs="{}")
            # 计算希腊字母
            options_manager(action="calculate_greeks", kwargs='{"S":3.5,"K":3.0,"T":0.25,"r":0.03,"sigma":0.2,"option_type":"call"}')
            # 计算隐含波动率
            options_manager(action="implied_volatility", kwargs='{"S":3.5,"K":3.0,"T":0.25,"r":0.03,"market_price":0.6,"option_type":"call"}')
        """
        try:
            kwargs = _normalize_kwargs(kwargs)
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'list': '列出期权合约',
                        'calculate_greeks': '计算希腊字母（需要 code/underlying）',
                        'calculate_price': 'Black-Scholes 定价（需要参数）',
                        'implied_volatility': '隐含波动率计算',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'list':
                underlying = kwargs.get('underlying') or kwargs.get('code') or '510050'
                expiry_month = kwargs.get('expiry_month') or kwargs.get('month') or ""
                limit = kwargs.get('limit', 200)
                try:
                    limit = int(limit)
                except Exception:
                    limit = 200

                from ..options import get_option_chain

                chain = get_option_chain(
                    underlying=str(underlying),
                    expiry_month=str(expiry_month),
                    limit=limit,
                )
                if not chain.get('success'):
                    return fail(chain.get('error') or '获取期权链失败')

                data = chain.get('data') or {}
                options = data.get('options') or []
                return ok({
                    'underlying': data.get('underlying', {}),
                    'expiryMonths': data.get('expiryMonths', []),
                    'selectedExpiry': data.get('selectedExpiry', []),
                    'options': options,
                    'count': len(options),
                    'truncated': bool(data.get('truncated', False)),
                })
            
            elif action == 'calculate_greeks':
                code = kwargs.get('code') or kwargs.get('underlying')
                spot = kwargs.get('spot')
                strike = kwargs.get('strike')
                time_to_maturity = kwargs.get('time_to_maturity')
                risk_free_rate = kwargs.get('risk_free_rate')
                volatility = kwargs.get('volatility')
                option_type = kwargs.get('option_type', 'call')
                dividend_yield = kwargs.get('dividend_yield')
                
                # 类型转换（参数可能以字符串形式传入）— 使用默认值
                if strike is not None:
                    strike = float(strike)
                if time_to_maturity is not None:
                    time_to_maturity = float(time_to_maturity)
                risk_free_rate = float(risk_free_rate) if risk_free_rate is not None else 0.03
                volatility = float(volatility) if volatility is not None else 0.25
                dividend_yield = float(dividend_yield) if dividend_yield is not None else 0.0
                
                # 如果提供了 code 但没有 spot，自动获取当前价格
                if code and spot is None:
                    try:
                        from ..market import get_kline
                        from ...utils import normalize_code
                        res = get_kline(normalize_code(code), 'daily', 1)
                        if res.get('success') and res.get('data'):
                            spot = float(res['data'][-1].get('close', 0) or 0)
                    except Exception:
                        pass
                if spot is not None:
                    spot = float(spot)
                else:
                    spot = 100.0
                
                # strike 默认等于 spot（平值期权）
                if strike is None:
                    strike = spot
                
                # 处理到期日期
                expiry_date = kwargs.get('expiry_date')
                if expiry_date:
                    from ...services.options_pricing import options_pricing
                    time_to_maturity = options_pricing.calculate_time_to_maturity(str(expiry_date))
                
                # time_to_maturity 默认 0.25 年（3个月）
                if time_to_maturity is None:
                    time_to_maturity = 0.25
                
                from ...services.options_pricing import options_pricing
                
                option_price = options_pricing.black_scholes(
                    spot=spot,
                    strike=strike,
                    time_to_maturity=time_to_maturity,
                    risk_free_rate=risk_free_rate,
                    volatility=volatility,
                    option_type=option_type,
                    dividend_yield=dividend_yield
                )
                
                greeks = options_pricing.calculate_greeks(
                    spot=spot,
                    strike=strike,
                    time_to_maturity=time_to_maturity,
                    risk_free_rate=risk_free_rate,
                    volatility=volatility,
                    option_type=option_type,
                    dividend_yield=dividend_yield
                )
                
                return ok({
                    'code': code,
                    'option_type': option_type,
                    'spot': spot,
                    'strike': strike,
                    'time_to_maturity': f"{time_to_maturity:.4f} years ({time_to_maturity*365:.0f} days)",
                    'volatility': f"{volatility*100:.2f}%",
                    'risk_free_rate': f"{risk_free_rate*100:.2f}%",
                    'option_price': f"{option_price:.4f}",
                    'greeks': {
                        'delta': f"{greeks['delta']:.4f}",
                        'gamma': f"{greeks['gamma']:.4f}",
                        'theta': f"{greeks['theta']:.4f} (per day)",
                        'vega': f"{greeks['vega']:.4f} (per 1% vol change)",
                        'rho': f"{greeks['rho']:.4f} (per 1% rate change)",
                    },
                    'interpretation': {
                        'delta': f"标的价格变动1元，期权价格变动{abs(greeks['delta']):.4f}元",
                        'gamma': f"Delta对标的价格的敏感度为{greeks['gamma']:.4f}",
                        'theta': f"每天时间价值衰减{abs(greeks['theta']):.4f}元",
                        'vega': f"波动率变动1%，期权价格变动{greeks['vega']:.4f}元",
                        'rho': f"利率变动1%，期权价格变动{greeks['rho']:.4f}元",
                    }
                })
            
            elif action == 'calculate_price':
                spot = float(kwargs.get('spot', 100.0) or 100.0)
                strike = float(kwargs.get('strike', 100.0) or 100.0)
                time_to_maturity = float(kwargs.get('time_to_maturity', 0.25) or 0.25)
                risk_free_rate = float(kwargs.get('risk_free_rate', 0.03) or 0.03)
                volatility = float(kwargs.get('volatility', 0.25) or 0.25)
                option_type = str(kwargs.get('option_type', 'call') or 'call')
                dividend_yield = float(kwargs.get('dividend_yield', 0.0) or 0.0)
                
                # 如果提供了 code 但没有显式 spot，自动获取当前价格
                code = kwargs.get('code') or kwargs.get('underlying')
                if code and kwargs.get('spot') is None:
                    try:
                        from ..market import get_kline
                        from ...utils import normalize_code
                        res = get_kline(normalize_code(code), 'daily', 1)
                        if res.get('success') and res.get('data'):
                            spot = float(res['data'][-1].get('close', 0) or 0)
                            if kwargs.get('strike') is None:
                                strike = spot  # 平值期权
                    except Exception:
                        pass
                
                expiry_date = kwargs.get('expiry_date')
                if expiry_date:
                    from ...services.options_pricing import options_pricing
                    time_to_maturity = options_pricing.calculate_time_to_maturity(str(expiry_date))
                
                from ...services.options_pricing import options_pricing
                
                option_price = options_pricing.black_scholes(
                    spot=spot,
                    strike=strike,
                    time_to_maturity=time_to_maturity,
                    risk_free_rate=risk_free_rate,
                    volatility=volatility,
                    option_type=option_type,
                    dividend_yield=dividend_yield
                )
                
                if option_type == 'call':
                    intrinsic_value = max(spot - strike, 0)
                else:
                    intrinsic_value = max(strike - spot, 0)
                
                time_value = option_price - intrinsic_value
                
                return ok({
                    'option_type': option_type,
                    'spot': spot,
                    'strike': strike,
                    'option_price': f"{option_price:.4f}",
                    'intrinsic_value': f"{intrinsic_value:.4f}",
                    'time_value': f"{time_value:.4f}",
                    'moneyness': 'ITM' if intrinsic_value > 0 else ('ATM' if abs(spot - strike) < 0.01 * spot else 'OTM'),
                })
            
            elif action == 'implied_volatility':
                option_price = kwargs.get('option_price')
                spot = float(kwargs.get('spot', 100.0) or 100.0)
                strike = float(kwargs.get('strike', 100.0) or 100.0)
                time_to_maturity = float(kwargs.get('time_to_maturity', 0.25) or 0.25)
                risk_free_rate = float(kwargs.get('risk_free_rate', 0.03) or 0.03)
                option_type = str(kwargs.get('option_type', 'call') or 'call')
                dividend_yield = float(kwargs.get('dividend_yield', 0.0) or 0.0)
                
                if not option_price:
                    return fail('需要提供option_price参数')
                
                expiry_date = kwargs.get('expiry_date')
                if expiry_date:
                    from ...services.options_pricing import options_pricing
                    time_to_maturity = options_pricing.calculate_time_to_maturity(str(expiry_date))
                
                from ...services.options_pricing import options_pricing
                
                iv = options_pricing.implied_volatility(
                    option_price=option_price,
                    spot=spot,
                    strike=strike,
                    time_to_maturity=time_to_maturity,
                    risk_free_rate=risk_free_rate,
                    option_type=option_type,
                    dividend_yield=dividend_yield
                )
                
                if iv is None:
                    return fail('隐含波动率计算未收敛')
                
                return ok({
                    'option_price': option_price,
                    'implied_volatility': f"{iv*100:.2f}%",
                    'iv_value': iv,
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, list, calculate_greeks, calculate_price, implied_volatility')
        except Exception as e:
            return fail(str(e))
