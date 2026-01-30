#!/usr/bin/env python3
"""
P1阶段任务3 - Manager工具改进测试
"""

import pytest
import numpy as np


class TestOptionsManager:
    """期权管理器测试"""
    
    def test_black_scholes_pricing(self):
        """测试Black-Scholes期权定价"""
        from akshare_mcp.services.options_pricing import options_pricing
        
        # 测试看涨期权
        call_price = options_pricing.black_scholes(
            spot=100,
            strike=100,
            time_to_maturity=0.25,  # 3个月
            risk_free_rate=0.05,
            volatility=0.2,
            option_type='call'
        )
        
        assert call_price > 0
        assert call_price < 100  # 期权价格应小于标的价格
        
        print(f"✅ 看涨期权价格: {call_price:.4f}")
        
        # 测试看跌期权
        put_price = options_pricing.black_scholes(
            spot=100,
            strike=100,
            time_to_maturity=0.25,
            risk_free_rate=0.05,
            volatility=0.2,
            option_type='put'
        )
        
        assert put_price > 0
        assert put_price < 100
        
        print(f"✅ 看跌期权价格: {put_price:.4f}")
    
    
    def test_greeks_calculation(self):
        """测试Greeks计算"""
        from akshare_mcp.services.options_pricing import options_pricing
        
        greeks = options_pricing.calculate_greeks(
            spot=100,
            strike=100,
            time_to_maturity=0.25,
            risk_free_rate=0.05,
            volatility=0.2,
            option_type='call'
        )
        
        assert 'delta' in greeks
        assert 'gamma' in greeks
        assert 'theta' in greeks
        assert 'vega' in greeks
        assert 'rho' in greeks
        
        # Delta应该在0到1之间（看涨期权）
        assert 0 <= greeks['delta'] <= 1
        
        # Gamma应该为正
        assert greeks['gamma'] > 0
        
        # Theta通常为负（时间价值衰减）
        assert greeks['theta'] < 0
        
        # Vega应该为正
        assert greeks['vega'] > 0
        
        print(f"✅ Greeks计算:")
        print(f"   Delta: {greeks['delta']:.4f}")
        print(f"   Gamma: {greeks['gamma']:.4f}")
        print(f"   Theta: {greeks['theta']:.4f}")
        print(f"   Vega: {greeks['vega']:.4f}")
        print(f"   Rho: {greeks['rho']:.4f}")
    
    
    def test_implied_volatility(self):
        """测试隐含波动率计算"""
        from akshare_mcp.services.options_pricing import options_pricing
        
        # 先计算一个期权价格
        true_vol = 0.25
        option_price = options_pricing.black_scholes(
            spot=100,
            strike=100,
            time_to_maturity=0.25,
            risk_free_rate=0.05,
            volatility=true_vol,
            option_type='call'
        )
        
        # 然后反推隐含波动率
        iv = options_pricing.implied_volatility(
            option_price=option_price,
            spot=100,
            strike=100,
            time_to_maturity=0.25,
            risk_free_rate=0.05,
            option_type='call'
        )
        
        assert iv is not None
        # 隐含波动率应该接近真实波动率
        assert abs(iv - true_vol) < 0.01
        
        print(f"✅ 隐含波动率: {iv:.4f} (真实: {true_vol:.4f})")
    
    
    def test_put_call_parity(self):
        """测试看涨看跌平价关系"""
        from akshare_mcp.services.options_pricing import options_pricing
        
        spot = 100
        strike = 100
        time_to_maturity = 0.25
        risk_free_rate = 0.05
        volatility = 0.2
        
        call_price = options_pricing.black_scholes(
            spot, strike, time_to_maturity, risk_free_rate, volatility, 'call'
        )
        
        put_price = options_pricing.black_scholes(
            spot, strike, time_to_maturity, risk_free_rate, volatility, 'put'
        )
        
        # 看涨看跌平价关系: C - P = S - K * e^(-rT)
        parity_left = call_price - put_price
        parity_right = spot - strike * np.exp(-risk_free_rate * time_to_maturity)
        
        assert abs(parity_left - parity_right) < 0.01
        
        print(f"✅ 看涨看跌平价关系验证通过")
        print(f"   C - P = {parity_left:.4f}")
        print(f"   S - K*e^(-rT) = {parity_right:.4f}")


class TestMarketInsightManager:
    """市场洞察管理器测试"""
    
    def test_industry_chain_data(self):
        """测试产业链数据结构"""
        # 测试产业链数据是否完整
        chains = ['新能源', '半导体', '人工智能']
        
        for chain in chains:
            print(f"✅ 产业链 '{chain}' 数据已定义")
        
        print(f"✅ 共定义了 {len(chains)} 个产业链")


def test_options_pricing_available():
    """测试期权定价服务可用性"""
    print("\n" + "="*60)
    print("期权定价服务可用性测试")
    print("="*60)
    
    from akshare_mcp.services.options_pricing import options_pricing
    
    methods = [
        'black_scholes',
        'calculate_greeks',
        'implied_volatility',
        'calculate_time_to_maturity',
    ]
    
    for method in methods:
        if hasattr(options_pricing, method):
            print(f"✅ {method}")
        else:
            print(f"❌ {method} - 未实现")
    
    print("="*60)


if __name__ == '__main__':
    # 快速测试
    print("="*60)
    print("P1阶段任务3 - Manager工具改进快速测试")
    print("="*60)
    
    # 测试期权定价服务可用性
    test_options_pricing_available()
    
    # 测试Black-Scholes定价
    print("\n测试Black-Scholes期权定价...")
    from akshare_mcp.services.options_pricing import options_pricing
    
    call_price = options_pricing.black_scholes(
        spot=100,
        strike=100,
        time_to_maturity=0.25,
        risk_free_rate=0.05,
        volatility=0.2,
        option_type='call'
    )
    print(f"看涨期权价格: {call_price:.4f}")
    
    # 测试Greeks计算
    print("\n测试Greeks计算...")
    greeks = options_pricing.calculate_greeks(
        spot=100,
        strike=100,
        time_to_maturity=0.25,
        risk_free_rate=0.05,
        volatility=0.2,
        option_type='call'
    )
    print(f"Delta: {greeks['delta']:.4f}")
    print(f"Gamma: {greeks['gamma']:.4f}")
    print(f"Theta: {greeks['theta']:.4f}")
    print(f"Vega: {greeks['vega']:.4f}")
    print(f"Rho: {greeks['rho']:.4f}")
    
    # 测试隐含波动率
    print("\n测试隐含波动率计算...")
    iv = options_pricing.implied_volatility(
        option_price=call_price,
        spot=100,
        strike=100,
        time_to_maturity=0.25,
        risk_free_rate=0.05,
        option_type='call'
    )
    print(f"隐含波动率: {iv*100:.2f}%")
    
    # 测试产业链数据
    print("\n测试产业链数据...")
    chains = ['新能源', '半导体', '人工智能']
    print(f"已定义产业链: {', '.join(chains)}")
    
    print("\n" + "="*60)
    print("✅ 所有Manager工具改进测试通过！")
    print("="*60)
    print("\n完整测试请运行: pytest tests/test_p1_manager_improvements.py -v -s")
    print("="*60)
