"""
扩展因子计算器 - 技术因子、基本面因子、另类因子
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from numba import jit


class FactorCalculatorExtended:
    """扩展因子计算器"""
    
    # ========== 技术因子 ==========
    
    @staticmethod
    def calculate_momentum_factors(klines: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        动量因子
        - reversal: 反转因子（短期）
        - momentum: 动量因子（中期）
        - trend: 趋势因子（长期）
        """
        closes = np.array([k['close'] for k in klines])
        
        # 反转因子（5日）
        reversal_5d = (closes[-1] - closes[-5]) / closes[-5] if len(closes) >= 5 else 0
        
        # 动量因子（20日）
        momentum_20d = (closes[-1] - closes[-20]) / closes[-20] if len(closes) >= 20 else 0
        
        # 趋势因子（60日）
        trend_60d = (closes[-1] - closes[-60]) / closes[-60] if len(closes) >= 60 else 0
        
        return {
            'reversal_5d': float(reversal_5d),
            'momentum_20d': float(momentum_20d),
            'trend_60d': float(trend_60d),
        }
    
    @staticmethod
    def calculate_volume_factors(klines: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        成交量因子
        - volume_ratio: 量比
        - volume_trend: 成交量趋势
        - turnover_rate: 换手率
        """
        volumes = np.array([k.get('volume', 0) for k in klines])
        
        # 量比（今日/5日均量）
        volume_ratio = volumes[-1] / np.mean(volumes[-5:]) if len(volumes) >= 5 else 1.0
        
        # 成交量趋势（20日）
        if len(volumes) >= 20:
            volume_ma5 = np.convolve(volumes, np.ones(5)/5, mode='valid')
            volume_ma20 = np.convolve(volumes, np.ones(20)/20, mode='valid')
            volume_trend = (volume_ma5[-1] - volume_ma20[-1]) / volume_ma20[-1]
        else:
            volume_trend = 0.0
        
        # 换手率（简化计算）
        turnover_rate = volumes[-1] / 1e8 if len(volumes) > 0 else 0.0
        
        return {
            'volume_ratio': float(volume_ratio),
            'volume_trend': float(volume_trend),
            'turnover_rate': float(turnover_rate),
        }
    
    @staticmethod
    def calculate_price_factors(klines: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        价格因子
        - price_position: 价格位置（相对高低点）
        - amplitude: 振幅
        - gap: 跳空缺口
        """
        closes = np.array([k['close'] for k in klines])
        highs = np.array([k.get('high', k['close']) for k in klines])
        lows = np.array([k.get('low', k['close']) for k in klines])
        
        # 价格位置（60日）
        if len(closes) >= 60:
            high_60 = np.max(highs[-60:])
            low_60 = np.min(lows[-60:])
            price_position = (closes[-1] - low_60) / (high_60 - low_60) if high_60 > low_60 else 0.5
        else:
            price_position = 0.5
        
        # 振幅（20日平均）
        if len(highs) >= 20:
            amplitudes = (highs[-20:] - lows[-20:]) / closes[-20:]
            amplitude = np.mean(amplitudes)
        else:
            amplitude = 0.0
        
        # 跳空缺口
        gap = (closes[-1] - closes[-2]) / closes[-2] if len(closes) >= 2 else 0.0
        
        return {
            'price_position': float(price_position),
            'amplitude': float(amplitude),
            'gap': float(gap),
        }
    
    @staticmethod
    def calculate_volatility_factors(klines: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        波动率因子
        - volatility: 历史波动率
        - beta: 市场Beta
        - downside_risk: 下行风险
        """
        closes = np.array([k['close'] for k in klines])
        
        # 历史波动率（20日）
        if len(closes) >= 20:
            returns = np.diff(closes[-20:]) / closes[-20:-1]
            volatility = np.std(returns) * np.sqrt(252)
        else:
            volatility = 0.0
        
        # Beta（简化计算，假设市场收益率）
        if len(closes) >= 60:
            stock_returns = np.diff(closes[-60:]) / closes[-60:-1]
            market_returns = np.random.normal(0.001, 0.02, len(stock_returns))  # 模拟市场收益
            beta = np.cov(stock_returns, market_returns)[0, 1] / np.var(market_returns)
        else:
            beta = 1.0
        
        # 下行风险（负收益的标准差）
        if len(closes) >= 20:
            returns = np.diff(closes[-20:]) / closes[-20:-1]
            negative_returns = returns[returns < 0]
            downside_risk = np.std(negative_returns) if len(negative_returns) > 0 else 0.0
        else:
            downside_risk = 0.0
        
        return {
            'volatility': float(volatility),
            'beta': float(beta),
            'downside_risk': float(downside_risk),
        }
    
    # ========== 基本面因子 ==========
    
    @staticmethod
    def calculate_quality_factors(financials: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        质量因子
        - roe: 净资产收益率
        - roa: 总资产收益率
        - profit_margin: 净利润率
        """
        if not financials:
            return {'roe': 0.0, 'roa': 0.0, 'profit_margin': 0.0}
        
        latest = financials[0]
        
        roe = latest.get('roe', 0.0)
        
        # ROA（简化计算）
        net_profit = latest.get('net_profit', 0)
        revenue = latest.get('revenue', 1)
        roa = net_profit / revenue if revenue > 0 else 0.0
        
        # 净利润率
        profit_margin = net_profit / revenue if revenue > 0 else 0.0
        
        return {
            'roe': float(roe),
            'roa': float(roa),
            'profit_margin': float(profit_margin),
        }
    
    @staticmethod
    def calculate_growth_factors(financials: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        成长因子
        - revenue_growth: 营收增长率
        - profit_growth: 利润增长率
        - roe_growth: ROE增长率
        """
        if len(financials) < 2:
            return {'revenue_growth': 0.0, 'profit_growth': 0.0, 'roe_growth': 0.0}
        
        latest = financials[0]
        previous = financials[1]
        
        revenue_growth = latest.get('revenue_growth', 0.0)
        profit_growth = latest.get('profit_growth', 0.0)
        
        # ROE增长率
        roe_current = latest.get('roe', 0)
        roe_previous = previous.get('roe', 0)
        roe_growth = (roe_current - roe_previous) / roe_previous if roe_previous > 0 else 0.0
        
        return {
            'revenue_growth': float(revenue_growth),
            'profit_growth': float(profit_growth),
            'roe_growth': float(roe_growth),
        }
    
    @staticmethod
    def calculate_value_factors(stock_info: Dict[str, Any], financials: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        价值因子
        - pe: 市盈率
        - pb: 市净率
        - ps: 市销率
        """
        pe_ratio = stock_info.get('pe_ratio', 0.0)
        pb_ratio = stock_info.get('pb_ratio', 0.0)
        
        # 市销率（简化计算）
        market_cap = stock_info.get('market_cap', 0)
        revenue = financials[0].get('revenue', 1) if financials else 1
        ps_ratio = market_cap / revenue if revenue > 0 else 0.0
        
        return {
            'pe': float(pe_ratio),
            'pb': float(pb_ratio),
            'ps': float(ps_ratio),
        }
    
    @staticmethod
    def calculate_leverage_factors(financials: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        杠杆因子
        - debt_ratio: 资产负债率
        - debt_to_equity: 负债权益比
        - interest_coverage: 利息保障倍数
        """
        if not financials:
            return {'debt_ratio': 0.0, 'debt_to_equity': 0.0, 'interest_coverage': 0.0}
        
        latest = financials[0]
        
        debt_ratio = latest.get('debt_ratio', 0.0)
        
        # 负债权益比（简化）
        debt_to_equity = debt_ratio / (1 - debt_ratio) if debt_ratio < 1 else 0.0
        
        # 利息保障倍数（简化）
        interest_coverage = 5.0  # 默认值
        
        return {
            'debt_ratio': float(debt_ratio),
            'debt_to_equity': float(debt_to_equity),
            'interest_coverage': float(interest_coverage),
        }
    
    # ========== 综合因子计算 ==========
    
    @staticmethod
    def calculate_all_factors(
        klines: List[Dict[str, Any]],
        stock_info: Optional[Dict[str, Any]] = None,
        financials: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """计算所有因子"""
        
        factors = {}
        
        # 技术因子
        if klines:
            factors['momentum'] = FactorCalculatorExtended.calculate_momentum_factors(klines)
            factors['volume'] = FactorCalculatorExtended.calculate_volume_factors(klines)
            factors['price'] = FactorCalculatorExtended.calculate_price_factors(klines)
            factors['volatility'] = FactorCalculatorExtended.calculate_volatility_factors(klines)
        
        # 基本面因子
        if financials:
            factors['quality'] = FactorCalculatorExtended.calculate_quality_factors(financials)
            factors['growth'] = FactorCalculatorExtended.calculate_growth_factors(financials)
            factors['leverage'] = FactorCalculatorExtended.calculate_leverage_factors(financials)
        
        if stock_info and financials:
            factors['value'] = FactorCalculatorExtended.calculate_value_factors(stock_info, financials)
        
        return factors
    
    # ========== 因子标准化 ==========
    
    @staticmethod
    def normalize_factors(factors: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
        """因子标准化（Z-score）"""
        normalized = {}
        
        for category, factor_dict in factors.items():
            normalized[category] = {}
            for factor_name, value in factor_dict.items():
                # 简化的标准化（实际应使用全市场数据）
                normalized[category][factor_name] = float(value)
        
        return normalized
    
    # ========== 因子合成 ==========
    
    @staticmethod
    def composite_factor(
        factors: Dict[str, Dict[str, float]],
        weights: Optional[Dict[str, float]] = None
    ) -> float:
        """
        合成因子
        
        Args:
            factors: 各类因子字典
            weights: 权重字典
        
        Returns:
            合成因子得分
        """
        if weights is None:
            weights = {
                'momentum': 0.2,
                'volume': 0.1,
                'price': 0.1,
                'volatility': 0.1,
                'quality': 0.2,
                'growth': 0.15,
                'value': 0.1,
                'leverage': 0.05,
            }
        
        score = 0.0
        total_weight = 0.0
        
        for category, factor_dict in factors.items():
            if category in weights:
                category_score = np.mean(list(factor_dict.values()))
                score += category_score * weights[category]
                total_weight += weights[category]
        
        return score / total_weight if total_weight > 0 else 0.0


# 全局实例
factor_calculator_extended = FactorCalculatorExtended()
