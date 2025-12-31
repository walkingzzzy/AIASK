"""
回测服务
集成AI评分回测和阈值优化
"""
from typing import Dict, Any, List
import pandas as pd
from ..backtest.score_backtest import AIScoreBacktester, ScoreCorrelationAnalyzer
from ..backtest.threshold_optimizer import ScoreThresholdOptimizer, RollingValidation


class BacktestService:
    """回测服务"""

    def __init__(self):
        self.backtester = AIScoreBacktester()
        self.correlation_analyzer = ScoreCorrelationAnalyzer()
        self.threshold_optimizer = ScoreThresholdOptimizer()
        self.rolling_validator = RollingValidation()

    def run_stratified_backtest(
        self,
        score_data: pd.DataFrame,
        price_data: pd.DataFrame,
        holding_days: int = 20
    ) -> List[Dict[str, Any]]:
        """
        运行分层回测

        Args:
            score_data: 评分数据
            price_data: 价格数据
            holding_days: 持有天数

        Returns:
            回测结果列表
        """
        results = self.backtester.stratified_backtest(
            score_data,
            price_data,
            holding_days
        )

        return [
            {
                "score_range": r.score_range,
                "total_stocks": r.total_stocks,
                "avg_return": r.avg_return,
                "win_rate": r.win_rate,
                "sharpe_ratio": r.sharpe_ratio,
                "max_drawdown": r.max_drawdown,
                "beat_market_rate": r.beat_market_rate
            }
            for r in results
        ]

    def optimize_thresholds(
        self,
        score_data: pd.DataFrame,
        price_data: pd.DataFrame,
        holding_days: int = 20
    ) -> Dict[str, Any]:
        """
        优化买入/卖出阈值

        Args:
            score_data: 评分数据
            price_data: 价格数据
            holding_days: 持有天数

        Returns:
            最优阈值结果
        """
        result = self.threshold_optimizer.optimize_thresholds(
            score_data,
            price_data,
            holding_days
        )

        return {
            "buy_threshold": result.buy_threshold,
            "sell_threshold": result.sell_threshold,
            "expected_return": result.expected_return,
            "win_rate": result.win_rate,
            "sharpe_ratio": result.sharpe_ratio,
            "total_trades": result.total_trades
        }

    def analyze_correlation(
        self,
        score_data: pd.DataFrame,
        return_data: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        分析评分与收益率相关性

        Args:
            score_data: 评分数据
            return_data: 收益率数据

        Returns:
            相关性分析结果
        """
        return self.correlation_analyzer.analyze_score_return_correlation(
            score_data,
            return_data
        )

    def run_rolling_validation(
        self,
        score_data: pd.DataFrame,
        price_data: pd.DataFrame,
        train_window: int = 252,
        test_window: int = 63,
        step: int = 21
    ) -> List[Dict[str, Any]]:
        """
        运行滚动验证

        Args:
            score_data: 评分数据
            price_data: 价格数据
            train_window: 训练窗口
            test_window: 测试窗口
            step: 滚动步长

        Returns:
            滚动验证结果
        """
        return self.rolling_validator.rolling_backtest(
            score_data,
            price_data,
            train_window,
            test_window,
            step
        )