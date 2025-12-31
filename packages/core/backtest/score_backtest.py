"""
AI评分策略回测模块
基于AI评分的分层回测和验证
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import pandas as pd
import numpy as np


@dataclass
class ScoreBacktestResult:
    """评分回测结果"""
    score_range: str  # 评分区间
    total_stocks: int  # 股票数量
    avg_return: float  # 平均收益率
    win_rate: float  # 胜率
    sharpe_ratio: float  # 夏普比率
    max_drawdown: float  # 最大回撤
    beat_market_rate: float  # 跑赢市场比例


class AIScoreBacktester:
    """AI评分回测器"""

    def __init__(self):
        self.score_ranges = [
            (9.0, 10.0, "9-10分"),
            (8.0, 9.0, "8-9分"),
            (7.0, 8.0, "7-8分"),
            (6.0, 7.0, "6-7分"),
            (5.0, 6.0, "5-6分"),
            (0.0, 5.0, "5分以下")
        ]

    def stratified_backtest(
        self,
        score_data: pd.DataFrame,
        price_data: pd.DataFrame,
        holding_days: int = 20
    ) -> List[ScoreBacktestResult]:
        """
        分层回测 - 按评分区间分组回测

        Args:
            score_data: 评分数据 (columns: date, stock_code, ai_score)
            price_data: 价格数据 (columns: date, stock_code, close)
            holding_days: 持有天数

        Returns:
            各评分区间的回测结果
        """
        results = []

        for min_score, max_score, range_name in self.score_ranges:
            # 筛选评分区间内的股票
            filtered_scores = score_data[
                (score_data['ai_score'] >= min_score) &
                (score_data['ai_score'] < max_score)
            ]

            if len(filtered_scores) == 0:
                continue

            # 计算收益率
            returns = self._calculate_returns(
                filtered_scores,
                price_data,
                holding_days
            )

            if len(returns) == 0:
                continue

            # 计算指标
            result = ScoreBacktestResult(
                score_range=range_name,
                total_stocks=len(filtered_scores),
                avg_return=returns.mean(),
                win_rate=(returns > 0).sum() / len(returns),
                sharpe_ratio=self._calculate_sharpe(returns),
                max_drawdown=self._calculate_max_drawdown(returns),
                beat_market_rate=self._calculate_beat_market_rate(
                    returns, price_data, holding_days
                )
            )

            results.append(result)

        return results

    def _calculate_returns(
        self,
        score_data: pd.DataFrame,
        price_data: pd.DataFrame,
        holding_days: int
    ) -> pd.Series:
        """计算收益率"""
        returns = []

        for _, row in score_data.iterrows():
            stock_code = row['stock_code']
            date = row['date']

            # 获取买入价格
            buy_price_data = price_data[
                (price_data['stock_code'] == stock_code) &
                (price_data['date'] == date)
            ]

            if len(buy_price_data) == 0:
                continue

            buy_price = buy_price_data.iloc[0]['close']

            # 获取卖出价格 (holding_days后)
            sell_date = pd.to_datetime(date) + timedelta(days=holding_days)
            sell_price_data = price_data[
                (price_data['stock_code'] == stock_code) &
                (price_data['date'] >= sell_date)
            ].head(1)

            if len(sell_price_data) == 0:
                continue

            sell_price = sell_price_data.iloc[0]['close']

            # 计算收益率
            ret = (sell_price - buy_price) / buy_price
            returns.append(ret)

        return pd.Series(returns)

    def _calculate_sharpe(self, returns: pd.Series, risk_free_rate: float = 0.03) -> float:
        """计算夏普比率"""
        if len(returns) == 0 or returns.std() == 0:
            return 0.0

        excess_return = returns.mean() - risk_free_rate / 252
        return excess_return / returns.std() * np.sqrt(252)

    def _calculate_max_drawdown(self, returns: pd.Series) -> float:
        """计算最大回撤"""
        if len(returns) == 0:
            return 0.0

        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max

        return drawdown.min()

    def _calculate_beat_market_rate(
        self,
        returns: pd.Series,
        price_data: pd.DataFrame,
        holding_days: int
    ) -> float:
        """计算跑赢市场比例"""
        # 简化版：假设市场平均收益为0
        # 实际应该使用沪深300或中证500作为基准
        market_return = 0.0
        beat_count = (returns > market_return).sum()
        return beat_count / len(returns) if len(returns) > 0 else 0.0


class ScoreCorrelationAnalyzer:
    """评分相关性分析器"""

    def analyze_score_return_correlation(
        self,
        score_data: pd.DataFrame,
        return_data: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        分析评分与收益率的相关性

        Args:
            score_data: 评分数据
            return_data: 收益率数据

        Returns:
            相关性分析结果
        """
        # 合并数据
        merged = pd.merge(
            score_data,
            return_data,
            on=['date', 'stock_code'],
            how='inner'
        )

        # 计算相关系数
        correlation = merged['ai_score'].corr(merged['return'])

        # 分组统计
        score_bins = [0, 5, 6, 7, 8, 9, 10]
        merged['score_group'] = pd.cut(merged['ai_score'], bins=score_bins)
        group_stats = merged.groupby('score_group')['return'].agg(['mean', 'std', 'count'])

        return {
            'correlation': correlation,
            'group_statistics': group_stats.to_dict(),
            'total_samples': len(merged)
        }