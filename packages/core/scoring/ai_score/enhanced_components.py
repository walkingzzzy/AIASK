"""
扩展评分组件
集成所有高级指标到评分系统
"""
from typing import Dict, Any, List
import pandas as pd
from .score_components import BaseScoreComponent, ScoreResult
from .advanced_indicators import AdvancedTechnicalIndicators
from .fundamental_indicators import AdvancedFundamentalIndicators
from .fund_flow_indicators import AdvancedFundFlowIndicators
from .sentiment_indicators import AdvancedSentimentIndicators
from .risk_indicators import AdvancedRiskIndicators


class EnhancedTechnicalScore(BaseScoreComponent):
    """
    增强技术面评分 (权重25%)

    新增指标：
    - RSI斜率
    - MACD背离
    - 布林带位置
    - KDJ交叉
    - ATR波动率
    - OBV趋势
    - 威廉指标
    """

    def __init__(self, weight: float = 0.25):
        super().__init__("enhanced_technical", weight)
        self.advanced = AdvancedTechnicalIndicators()

    def calculate(self, data: Dict[str, Any]) -> ScoreResult:
        factors = []
        scores = []

        # 基础技术指标 (权重40%)
        base_score = self._calculate_base_technical(data)
        scores.append(base_score * 0.4)

        # 高级技术指标 (权重60%)
        try:
            prices = pd.Series(data.get('price_history', []))

            # RSI斜率
            if len(prices) >= 20:
                rsi_result = self.advanced.calculate_rsi_slope(prices)
                if rsi_result.strength > 0.5:
                    factors.append({
                        "factor": rsi_result.description,
                        "impact": f"+{rsi_result.strength:.1f}",
                        "category": "momentum"
                    })
                    scores.append(self._signal_to_score(rsi_result.signal) * 0.1)

            # 布林带位置
            if len(prices) >= 20:
                bb_result = self.advanced.calculate_bollinger_position(prices)
                if bb_result.strength > 0.5:
                    factors.append({
                        "factor": bb_result.description,
                        "impact": f"{'+' if bb_result.signal == 'bullish' else ''}{bb_result.strength:.1f}",
                        "category": "volatility"
                    })
                    scores.append(self._signal_to_score(bb_result.signal) * 0.15)

            # OBV趋势
            volume = pd.Series(data.get('volume_history', []))
            if len(prices) >= 20 and len(volume) >= 20:
                obv_result = self.advanced.calculate_obv_trend(volume, prices)
                if obv_result.strength > 0.5:
                    factors.append({
                        "factor": obv_result.description,
                        "impact": f"+{obv_result.strength:.1f}",
                        "category": "volume"
                    })
                    scores.append(self._signal_to_score(obv_result.signal) * 0.15)

        except Exception as e:
            # 如果高级指标计算失败，使用基础分数
            scores.append(base_score * 0.6)

        total_score = sum(scores) if scores else base_score

        return ScoreResult(
            score=total_score,
            weight=self.weight,
            factors=factors,
            details={"base_score": base_score, "advanced_indicators": len(factors)}
        )

    def _calculate_base_technical(self, data: Dict) -> float:
        """计算基础技术评分"""
        score = 5.0
        close = data.get('close', 0)
        ma5 = data.get('ma5', close)
        ma20 = data.get('ma20', close)

        if close > ma5 > ma20:
            score = 7.5
        elif close > ma5:
            score = 6.5
        elif close < ma5 < ma20:
            score = 3.5

        return score

    def _signal_to_score(self, signal: str) -> float:
        """将信号转换为评分"""
        if signal == 'bullish':
            return 8.0
        elif signal == 'bearish':
            return 3.0
        else:
            return 5.0


class EnhancedFundamentalScore(BaseScoreComponent):
    """
    增强基本面评分 (权重30%)

    新增指标：
    - Piotroski F-Score
    - Altman Z-Score
    - 杜邦分析
    - 现金转换周期
    - 自由现金流收益率
    """

    def __init__(self, weight: float = 0.30):
        super().__init__("enhanced_fundamental", weight)
        self.advanced = AdvancedFundamentalIndicators()

    def calculate(self, data: Dict[str, Any]) -> ScoreResult:
        factors = []
        scores = []

        # 基础基本面评分 (权重50%)
        base_score = self._calculate_base_fundamental(data)
        scores.append(base_score * 0.5)

        # 高级基本面指标 (权重50%)
        try:
            financial_data = data.get('financial_data', {})

            # Piotroski F-Score
            if financial_data:
                f_score_result = self.advanced.calculate_piotroski_f_score(financial_data)
                if f_score_result.level in ['excellent', 'good']:
                    factors.append({
                        "factor": f_score_result.description,
                        "impact": f"+{(f_score_result.score - 5) * 0.2:.1f}",
                        "category": "quality"
                    })
                scores.append(f_score_result.score * 0.2)

            # 自由现金流收益率
            if financial_data:
                fcf_result = self.advanced.calculate_free_cash_flow_yield(financial_data)
                if fcf_result.level in ['excellent', 'good']:
                    factors.append({
                        "factor": fcf_result.description,
                        "impact": f"+{(fcf_result.score - 5) * 0.15:.1f}",
                        "category": "cash_flow"
                    })
                scores.append(fcf_result.score * 0.15)

            # 杜邦分析
            if financial_data:
                dupont_result = self.advanced.calculate_dupont_analysis(financial_data)
                scores.append(dupont_result.score * 0.15)

        except Exception:
            scores.append(base_score * 0.5)

        total_score = sum(scores) if scores else base_score

        return ScoreResult(
            score=total_score,
            weight=self.weight,
            factors=factors,
            details={"base_score": base_score, "advanced_indicators": len(factors)}
        )

    def _calculate_base_fundamental(self, data: Dict) -> float:
        """计算基础基本面评分"""
        score = 5.0
        roe = data.get('roe', 10)
        pe_percentile = data.get('pe_percentile', 50)

        if roe > 15:
            score += 2.0
        if pe_percentile < 30:
            score += 2.0

        return min(10.0, score)


class EnhancedFundFlowScore(BaseScoreComponent):
    """
    增强资金流向评分 (权重25%)

    新增指标：
    - ETF资金流向
    - QFII持仓变化
    - 融资融券趋势
    """

    def __init__(self, weight: float = 0.25):
        super().__init__("enhanced_fund_flow", weight)
        self.advanced = AdvancedFundFlowIndicators()

    def calculate(self, data: Dict[str, Any]) -> ScoreResult:
        factors = []
        scores = []

        # 基础资金流向评分 (权重60%)
        base_score = self._calculate_base_fund_flow(data)
        scores.append(base_score * 0.6)

        # 高级资金流向指标 (权重40%)
        try:
            # ETF资金流向
            etf_flows = data.get('etf_flows', {})
            if etf_flows:
                etf_result = self.advanced.calculate_etf_flow_impact(
                    data.get('stock_code', ''), etf_flows
                )
                if etf_result.strength > 0.5:
                    factors.append({
                        "factor": etf_result.description,
                        "impact": f"+{etf_result.strength:.1f}",
                        "category": "etf_flow"
                    })
                scores.append(self._signal_to_score(etf_result.signal) * 0.2)

            # 融资融券趋势
            margin_data = data.get('margin_balance_history')
            if margin_data and len(margin_data) >= 6:
                margin_series = pd.Series(margin_data)
                margin_result = self.advanced.calculate_margin_trading_trend(margin_series)
                if margin_result.strength > 0.5:
                    factors.append({
                        "factor": margin_result.description,
                        "impact": f"+{margin_result.strength:.1f}",
                        "category": "margin"
                    })
                scores.append(self._signal_to_score(margin_result.signal) * 0.2)

        except Exception:
            scores.append(base_score * 0.4)

        total_score = sum(scores) if scores else base_score

        return ScoreResult(
            score=total_score,
            weight=self.weight,
            factors=factors,
            details={"base_score": base_score}
        )

    def _calculate_base_fund_flow(self, data: Dict) -> float:
        """计算基础资金流向评分"""
        score = 5.0
        main_flow = data.get('main_fund_flow', 0)

        if main_flow > 50000000:
            score = 8.0
        elif main_flow > 0:
            score = 6.5
        elif main_flow < -50000000:
            score = 3.0

        return score

    def _signal_to_score(self, signal: str) -> float:
        """将信号转换为评分"""
        if signal == 'inflow':
            return 8.0
        elif signal == 'outflow':
            return 3.0
        else:
            return 5.0