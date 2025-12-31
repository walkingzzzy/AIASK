"""
AI评分系统测试
"""
import pytest

from packages.core.scoring.ai_score.score_components import (
    TechnicalScore,
    FundamentalScore,
    FundFlowScore,
    SentimentScore,
    RiskScore,
    ScoreResult,
)
from packages.core.scoring.ai_score.score_calculator import AIScoreCalculator, AIScoreResult
from packages.core.scoring.explainer.score_explainer import ScoreExplainer, ExplanationResult


class TestScoreComponents:
    """测试评分组件"""

    @pytest.fixture
    def sample_data(self):
        """生成测试数据"""
        return {
            # 技术面数据
            "close": 100.0,
            "ma5": 99.0,
            "ma10": 98.0,
            "ma20": 97.0,
            "macd_dif": 0.5,
            "macd_dea": 0.3,
            "macd_hist": 0.2,
            "rsi": 55,
            "volume_ratio": 1.2,
            "price_change": 0.02,
            # 基本面数据
            "pe": 20,
            "pe_percentile": 40,
            "roe": 18,
            "gross_margin": 35,
            "revenue_growth": 20,
            "profit_growth": 25,
            # 资金面数据
            "north_flow_5d": 200000000,
            "north_holding_change": 100000,
            "main_fund_flow": 50000000,
            "margin_change": 5000000,
            # 情绪面数据
            "market_breadth": 0.6,
            "news_sentiment": 0.3,
            "analyst_rating": 4,
            # 风险数据
            "volatility": 0.02,
            "beta": 1.0,
            "max_drawdown": 0.1,
        }

    def test_technical_score(self, sample_data):
        """测试技术面评分"""
        component = TechnicalScore()
        result = component.calculate(sample_data)

        assert isinstance(result, ScoreResult)
        assert 0 <= result.score <= 10
        assert result.weight == 0.25
        assert "ma_score" in result.details

    def test_fundamental_score(self, sample_data):
        """测试基本面评分"""
        component = FundamentalScore()
        result = component.calculate(sample_data)

        assert isinstance(result, ScoreResult)
        assert 0 <= result.score <= 10
        assert result.weight == 0.30
        assert "valuation_score" in result.details

    def test_fund_flow_score(self, sample_data):
        """测试资金面评分"""
        component = FundFlowScore()
        result = component.calculate(sample_data)

        assert isinstance(result, ScoreResult)
        assert 0 <= result.score <= 10
        assert result.weight == 0.25

    def test_sentiment_score(self, sample_data):
        """测试情绪面评分"""
        component = SentimentScore()
        result = component.calculate(sample_data)

        assert isinstance(result, ScoreResult)
        assert 0 <= result.score <= 10
        assert result.weight == 0.10

    def test_risk_score(self, sample_data):
        """测试风险评分"""
        component = RiskScore()
        result = component.calculate(sample_data)

        assert isinstance(result, ScoreResult)
        assert 0 <= result.score <= 10
        assert result.weight == 0.10
        assert "risk_level" in result.details


class TestAIScoreCalculator:
    """测试AI评分计算器"""

    @pytest.fixture
    def calculator(self):
        return AIScoreCalculator()

    @pytest.fixture
    def sample_data(self):
        return {
            "close": 100.0,
            "ma5": 99.0,
            "ma10": 98.0,
            "ma20": 97.0,
            "macd_dif": 0.5,
            "macd_dea": 0.3,
            "macd_hist": 0.2,
            "rsi": 55,
            "volume_ratio": 1.2,
            "price_change": 0.02,
            "pe": 20,
            "pe_percentile": 40,
            "roe": 18,
            "gross_margin": 35,
            "revenue_growth": 20,
            "profit_growth": 25,
            "north_flow_5d": 200000000,
            "main_fund_flow": 50000000,
            "market_breadth": 0.6,
            "volatility": 0.02,
            "beta": 1.0,
            "max_drawdown": 0.1,
        }

    def test_calculate_score(self, calculator, sample_data):
        """测试评分计算"""
        result = calculator.calculate("600519", "贵州茅台", sample_data)

        assert isinstance(result, AIScoreResult)
        assert 1 <= result.ai_score <= 10
        assert result.stock_code == "600519"
        assert result.stock_name == "贵州茅台"

    def test_signal_generation(self, calculator, sample_data):
        """测试信号生成"""
        result = calculator.calculate("600519", "贵州茅台", sample_data)

        valid_signals = ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]
        assert result.signal in valid_signals

    def test_beat_probability(self, calculator, sample_data):
        """测试跑赢概率"""
        result = calculator.calculate("600519", "贵州茅台", sample_data)

        assert 0 <= result.beat_market_probability <= 1

    def test_subscores(self, calculator, sample_data):
        """测试分项评分"""
        result = calculator.calculate("600519", "贵州茅台", sample_data)

        assert "technical" in result.subscores
        assert "fundamental" in result.subscores
        assert "fund_flow" in result.subscores
        assert "sentiment" in result.subscores
        assert "risk" in result.subscores

    def test_to_dict(self, calculator, sample_data):
        """测试转换为字典"""
        result = calculator.calculate("600519", "贵州茅台", sample_data)
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "ai_score" in result_dict
        assert "signal" in result_dict


class TestScoreExplainer:
    """测试评分解释器"""

    @pytest.fixture
    def explainer(self):
        return ScoreExplainer()

    @pytest.fixture
    def score_result(self):
        """模拟评分结果"""
        return {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "ai_score": 7.5,
            "signal": "Buy",
            "subscores": {
                "technical": {"score": 7.0, "weight": 0.25, "details": {"ma_score": 7.5}},
                "fundamental": {
                    "score": 8.0,
                    "weight": 0.30,
                    "details": {"valuation_score": 8.0},
                },
                "fund_flow": {"score": 7.5, "weight": 0.25, "details": {"north_score": 7.5}},
                "sentiment": {"score": 6.5, "weight": 0.10, "details": {}},
                "risk": {
                    "score": 7.0,
                    "weight": 0.10,
                    "details": {"risk_level": "中"},
                },
            },
            "risks": ["估值处于历史高位"],
        }

    def test_explain(self, explainer, score_result):
        """测试生成解释"""
        result = explainer.explain(score_result)

        assert isinstance(result, ExplanationResult)
        assert result.stock_code == "600519"
        assert result.ai_score == 7.5

    def test_score_breakdown(self, explainer, score_result):
        """测试评分分解"""
        result = explainer.explain(score_result)

        assert isinstance(result.score_breakdown, dict)
        assert len(result.score_breakdown) > 0

    def test_summary_generation(self, explainer, score_result):
        """测试摘要生成"""
        result = explainer.explain(score_result)

        assert isinstance(result.summary, str)
        assert len(result.summary) > 0
        assert "贵州茅台" in result.summary

    def test_suggestions(self, explainer, score_result):
        """测试建议生成"""
        result = explainer.explain(score_result)

        assert isinstance(result.suggestions, list)
        assert len(result.suggestions) > 0

    def test_to_dict(self, explainer, score_result):
        """测试转换为字典"""
        result = explainer.explain(score_result)
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "summary" in result_dict
        assert "suggestions" in result_dict


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
