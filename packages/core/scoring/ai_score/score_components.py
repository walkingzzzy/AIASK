"""
AI评分组件
技术面、基本面、资金面、情绪面、风险评分
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import pandas as pd
import numpy as np


@dataclass
class ScoreResult:
    """评分结果"""
    score: float           # 0-10分
    weight: float          # 权重
    factors: List[Dict]    # 影响因子
    details: Dict[str, Any]  # 详细数据


class BaseScoreComponent(ABC):
    """评分组件基类"""
    
    def __init__(self, name: str, weight: float):
        self.name = name
        self.weight = weight
    
    @abstractmethod
    def calculate(self, data: Dict[str, Any]) -> ScoreResult:
        """计算评分"""
        pass
    
    @staticmethod
    def normalize_score(value: float, min_val: float, max_val: float) -> float:
        """将值归一化到0-10分"""
        if max_val == min_val:
            return 5.0
        score = (value - min_val) / (max_val - min_val) * 10
        return max(0, min(10, score))
    
    @staticmethod
    def percentile_score(value: float, values: List[float]) -> float:
        """基于百分位计算评分"""
        if not values:
            return 5.0
        percentile = sum(1 for v in values if v <= value) / len(values) * 100
        return percentile / 10  # 转换为0-10分


class TechnicalScore(BaseScoreComponent):
    """
    技术面评分 (权重25%)
    
    评分维度：
    - 趋势强度（均线系统）
    - 动量指标（RSI、MACD）
    - 形态识别
    """
    
    def __init__(self, weight: float = 0.25):
        super().__init__("technical", weight)
    
    def calculate(self, data: Dict[str, Any]) -> ScoreResult:
        factors = []
        scores = []
        
        # 1. 均线趋势评分 (0-10)
        ma_score = self._score_ma_trend(data)
        scores.append(ma_score * 0.3)
        if ma_score > 7:
            factors.append({"factor": "均线多头排列", "impact": f"+{(ma_score-5)*0.2:.1f}", "category": "trend"})
        elif ma_score < 3:
            factors.append({"factor": "均线空头排列", "impact": f"{(ma_score-5)*0.2:.1f}", "category": "trend"})
        
        # 2. MACD评分 (0-10)
        macd_score = self._score_macd(data)
        scores.append(macd_score * 0.3)
        if macd_score > 7:
            factors.append({"factor": "MACD金叉/多头", "impact": f"+{(macd_score-5)*0.2:.1f}", "category": "momentum"})
        
        # 3. RSI评分 (0-10)
        rsi_score = self._score_rsi(data)
        scores.append(rsi_score * 0.2)
        if rsi_score > 7:
            factors.append({"factor": "RSI强势区域", "impact": f"+{(rsi_score-5)*0.1:.1f}", "category": "momentum"})
        elif rsi_score < 3:
            factors.append({"factor": "RSI超卖", "impact": f"+{(5-rsi_score)*0.1:.1f}", "category": "momentum"})
        
        # 4. 成交量评分 (0-10)
        volume_score = self._score_volume(data)
        scores.append(volume_score * 0.2)
        if volume_score > 7:
            factors.append({"factor": "放量上涨", "impact": f"+{(volume_score-5)*0.1:.1f}", "category": "volume"})
        
        total_score = sum(scores)
        
        return ScoreResult(
            score=total_score,
            weight=self.weight,
            factors=factors,
            details={
                "ma_score": ma_score,
                "macd_score": macd_score,
                "rsi_score": rsi_score,
                "volume_score": volume_score
            }
        )
    
    def _score_ma_trend(self, data: Dict) -> float:
        """均线趋势评分"""
        close = data.get('close', 0)
        ma5 = data.get('ma5', close)
        ma10 = data.get('ma10', close)
        ma20 = data.get('ma20', close)
        
        score = 5.0
        # 多头排列加分
        if close > ma5 > ma10 > ma20:
            score = 8.0
        elif close > ma5 > ma10:
            score = 7.0
        elif close > ma5:
            score = 6.0
        # 空头排列减分
        elif close < ma5 < ma10 < ma20:
            score = 2.0
        elif close < ma5 < ma10:
            score = 3.0
        elif close < ma5:
            score = 4.0
        
        return score
    
    def _score_macd(self, data: Dict) -> float:
        """MACD评分"""
        dif = data.get('macd_dif', 0)
        dea = data.get('macd_dea', 0)
        hist = data.get('macd_hist', 0)
        
        score = 5.0
        if dif > dea and hist > 0:
            score = 7.0 + min(hist / 0.5, 2)  # 最高9分
        elif dif > dea:
            score = 6.0
        elif dif < dea and hist < 0:
            score = 3.0 - min(abs(hist) / 0.5, 2)  # 最低1分
        elif dif < dea:
            score = 4.0
        
        return max(1, min(10, score))
    
    def _score_rsi(self, data: Dict) -> float:
        """RSI评分"""
        rsi = data.get('rsi', 50)
        
        if rsi > 70:
            return 4.0  # 超买，风险
        elif rsi > 60:
            return 7.0  # 强势
        elif rsi > 50:
            return 6.0  # 偏强
        elif rsi > 40:
            return 5.0  # 中性
        elif rsi > 30:
            return 6.0  # 偏弱但可能反弹
        else:
            return 7.0  # 超卖，可能反弹
    
    def _score_volume(self, data: Dict) -> float:
        """成交量评分"""
        volume_ratio = data.get('volume_ratio', 1.0)
        price_change = data.get('price_change', 0)
        
        score = 5.0
        if volume_ratio > 1.5 and price_change > 0:
            score = 8.0  # 放量上涨
        elif volume_ratio > 1.2 and price_change > 0:
            score = 7.0
        elif volume_ratio < 0.5 and price_change < 0:
            score = 6.0  # 缩量下跌，抛压减轻
        elif volume_ratio > 1.5 and price_change < 0:
            score = 3.0  # 放量下跌
        
        return score


class FundamentalScore(BaseScoreComponent):
    """
    基本面评分 (权重30%)
    
    评分维度：
    - 估值水平（PE、PB分位数）
    - 盈利能力（ROE、毛利率）
    - 成长能力（营收增速、利润增速）
    """
    
    def __init__(self, weight: float = 0.30):
        super().__init__("fundamental", weight)
    
    def calculate(self, data: Dict[str, Any]) -> ScoreResult:
        factors = []
        scores = []
        
        # 1. 估值评分 (0-10)
        valuation_score = self._score_valuation(data)
        scores.append(valuation_score * 0.35)
        if valuation_score > 7:
            factors.append({"factor": "估值处于历史低位", "impact": f"+{(valuation_score-5)*0.3:.1f}", "category": "valuation"})
        elif valuation_score < 3:
            factors.append({"factor": "估值处于历史高位", "impact": f"{(valuation_score-5)*0.3:.1f}", "category": "valuation"})
        
        # 2. 盈利能力评分 (0-10)
        profitability_score = self._score_profitability(data)
        scores.append(profitability_score * 0.35)
        if profitability_score > 7:
            factors.append({"factor": "ROE优秀", "impact": f"+{(profitability_score-5)*0.3:.1f}", "category": "profitability"})
        
        # 3. 成长能力评分 (0-10)
        growth_score = self._score_growth(data)
        scores.append(growth_score * 0.30)
        if growth_score > 7:
            factors.append({"factor": "业绩高增长", "impact": f"+{(growth_score-5)*0.2:.1f}", "category": "growth"})
        
        total_score = sum(scores)
        
        return ScoreResult(
            score=total_score,
            weight=self.weight,
            factors=factors,
            details={
                "valuation_score": valuation_score,
                "profitability_score": profitability_score,
                "growth_score": growth_score
            }
        )
    
    def _score_valuation(self, data: Dict) -> float:
        """估值评分（PE分位数越低越好）"""
        pe = data.get('pe', 20)
        pe_percentile = data.get('pe_percentile', 50)  # PE历史百分位
        
        # PE分位数越低，估值越便宜，得分越高
        score = 10 - pe_percentile / 10
        
        # 负PE（亏损）扣分
        if pe < 0:
            score = 2.0
        # PE过高扣分
        elif pe > 100:
            score = min(score, 3.0)
        
        return max(1, min(10, score))
    
    def _score_profitability(self, data: Dict) -> float:
        """盈利能力评分"""
        roe = data.get('roe', 10)
        gross_margin = data.get('gross_margin', 30)
        
        score = 5.0
        
        # ROE评分
        if roe > 20:
            score += 2.5
        elif roe > 15:
            score += 1.5
        elif roe > 10:
            score += 0.5
        elif roe < 5:
            score -= 2.0
        
        # 毛利率评分
        if gross_margin > 50:
            score += 1.5
        elif gross_margin > 30:
            score += 0.5
        elif gross_margin < 15:
            score -= 1.0
        
        return max(1, min(10, score))
    
    def _score_growth(self, data: Dict) -> float:
        """成长能力评分"""
        revenue_growth = data.get('revenue_growth', 0)
        profit_growth = data.get('profit_growth', 0)
        
        score = 5.0
        
        # 营收增速
        if revenue_growth > 30:
            score += 2.0
        elif revenue_growth > 15:
            score += 1.0
        elif revenue_growth < 0:
            score -= 1.5
        
        # 利润增速
        if profit_growth > 30:
            score += 2.0
        elif profit_growth > 15:
            score += 1.0
        elif profit_growth < 0:
            score -= 1.5
        
        return max(1, min(10, score))


class FundFlowScore(BaseScoreComponent):
    """
    资金面评分 (权重25%)
    
    评分维度：
    - 北向资金流向
    - 主力资金流向
    - 融资融券变化
    """
    
    def __init__(self, weight: float = 0.25):
        super().__init__("fund_flow", weight)
    
    def calculate(self, data: Dict[str, Any]) -> ScoreResult:
        factors = []
        scores = []
        
        # 1. 北向资金评分
        north_score = self._score_north_fund(data)
        scores.append(north_score * 0.4)
        if north_score > 7:
            factors.append({"factor": "北向资金持续流入", "impact": f"+{(north_score-5)*0.3:.1f}", "category": "north_fund"})
        
        # 2. 主力资金评分
        main_score = self._score_main_fund(data)
        scores.append(main_score * 0.4)
        if main_score > 7:
            factors.append({"factor": "主力资金净流入", "impact": f"+{(main_score-5)*0.3:.1f}", "category": "main_fund"})
        
        # 3. 融资融券评分
        margin_score = self._score_margin(data)
        scores.append(margin_score * 0.2)
        
        total_score = sum(scores)
        
        return ScoreResult(
            score=total_score,
            weight=self.weight,
            factors=factors,
            details={
                "north_score": north_score,
                "main_score": main_score,
                "margin_score": margin_score
            }
        )
    
    def _score_north_fund(self, data: Dict) -> float:
        """北向资金评分"""
        north_flow_5d = data.get('north_flow_5d', 0)  # 5日累计
        north_holding_change = data.get('north_holding_change', 0)  # 持仓变化
        
        score = 5.0
        
        if north_flow_5d > 0:
            score += min(north_flow_5d / 100000000, 3)  # 每亿加分，最多3分
        else:
            score += max(north_flow_5d / 100000000, -3)
        
        if north_holding_change > 0:
            score += 1.0
        elif north_holding_change < 0:
            score -= 1.0
        
        return max(1, min(10, score))
    
    def _score_main_fund(self, data: Dict) -> float:
        """主力资金评分"""
        main_flow = data.get('main_fund_flow', 0)
        volume_ratio = data.get('volume_ratio', 1.0)
        
        score = 5.0
        
        if main_flow > 0:
            score += min(main_flow / 50000000, 3)  # 每5000万加分
        else:
            score += max(main_flow / 50000000, -3)
        
        # 放量配合加分
        if main_flow > 0 and volume_ratio > 1.5:
            score += 1.0
        
        return max(1, min(10, score))
    
    def _score_margin(self, data: Dict) -> float:
        """融资融券评分"""
        margin_change = data.get('margin_change', 0)  # 融资余额变化
        
        score = 5.0
        if margin_change > 0:
            score += min(margin_change / 10000000, 2)
        else:
            score += max(margin_change / 10000000, -2)
        
        return max(1, min(10, score))


class SentimentScore(BaseScoreComponent):
    """
    情绪面评分 (权重10%)
    
    评分维度：
    - 新闻情绪
    - 研报评级
    - 市场热度
    """
    
    def __init__(self, weight: float = 0.10):
        super().__init__("sentiment", weight)
    
    def calculate(self, data: Dict[str, Any]) -> ScoreResult:
        factors = []
        
        # 简化版：基于市场广度和热度
        market_breadth = data.get('market_breadth', 0.5)  # 上涨股票占比
        news_sentiment = data.get('news_sentiment', 0)  # -1到1
        analyst_rating = data.get('analyst_rating', 3)  # 1-5
        
        score = 5.0
        
        # 市场广度
        score += (market_breadth - 0.5) * 4
        
        # 新闻情绪
        score += news_sentiment * 2
        
        # 分析师评级
        score += (analyst_rating - 3) * 1
        
        score = max(1, min(10, score))
        
        if score > 7:
            factors.append({"factor": "市场情绪偏多", "impact": f"+{(score-5)*0.1:.1f}", "category": "sentiment"})
        
        return ScoreResult(
            score=score,
            weight=self.weight,
            factors=factors,
            details={
                "market_breadth": market_breadth,
                "news_sentiment": news_sentiment,
                "analyst_rating": analyst_rating
            }
        )


class RiskScore(BaseScoreComponent):
    """
    风险评分 (权重10%)
    
    评分维度：
    - 波动率
    - Beta系数
    - 最大回撤
    
    注意：风险评分是反向的，风险越低得分越高
    """
    
    def __init__(self, weight: float = 0.10):
        super().__init__("risk", weight)
    
    def calculate(self, data: Dict[str, Any]) -> ScoreResult:
        factors = []
        
        volatility = data.get('volatility', 0.02)  # 日波动率
        beta = data.get('beta', 1.0)
        max_drawdown = data.get('max_drawdown', 0.1)  # 最大回撤
        
        score = 5.0
        
        # 波动率评分（低波动高分）
        if volatility < 0.015:
            score += 2.0
        elif volatility < 0.025:
            score += 1.0
        elif volatility > 0.04:
            score -= 2.0
        
        # Beta评分（接近1为好）
        if 0.8 <= beta <= 1.2:
            score += 1.0
        elif beta > 1.5:
            score -= 1.5
        
        # 最大回撤评分
        if max_drawdown < 0.1:
            score += 1.5
        elif max_drawdown > 0.3:
            score -= 2.0
        
        score = max(1, min(10, score))
        
        if score > 7:
            factors.append({"factor": "风险可控", "impact": f"+{(score-5)*0.1:.1f}", "category": "risk"})
        elif score < 4:
            factors.append({"factor": "波动风险较高", "impact": f"{(score-5)*0.1:.1f}", "category": "risk"})
        
        return ScoreResult(
            score=score,
            weight=self.weight,
            factors=factors,
            details={
                "volatility": volatility,
                "beta": beta,
                "max_drawdown": max_drawdown,
                "risk_level": "低" if score > 7 else "中" if score > 4 else "高"
            }
        )
