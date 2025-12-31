"""
AI评分阈值优化模块
通过回测优化买入/卖出阈值
"""
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np


@dataclass
class ThresholdOptimizationResult:
    """阈值优化结果"""
    buy_threshold: float  # 最优买入阈值
    sell_threshold: float  # 最优卖出阈值
    expected_return: float  # 期望收益率
    win_rate: float  # 胜率
    sharpe_ratio: float  # 夏普比率
    total_trades: int  # 交易次数


class ScoreThresholdOptimizer:
    """评分阈值优化器"""

    def __init__(self):
        self.buy_thresholds = [6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0]
        self.sell_thresholds = [4.0, 4.5, 5.0, 5.5, 6.0]

    def optimize_thresholds(
        self,
        score_data: pd.DataFrame,
        price_data: pd.DataFrame,
        holding_days: int = 20
    ) -> ThresholdOptimizationResult:
        """
        优化买入/卖出阈值

        Args:
            score_data: 评分数据
            price_data: 价格数据
            holding_days: 持有天数

        Returns:
            最优阈值结果
        """
        best_result = None
        best_sharpe = -np.inf

        for buy_threshold in self.buy_thresholds:
            for sell_threshold in self.sell_thresholds:
                if sell_threshold >= buy_threshold:
                    continue

                # 回测该阈值组合
                result = self._backtest_threshold(
                    score_data,
                    price_data,
                    buy_threshold,
                    sell_threshold,
                    holding_days
                )

                # 选择夏普比率最高的组合
                if result.sharpe_ratio > best_sharpe:
                    best_sharpe = result.sharpe_ratio
                    best_result = result

        return best_result

    def _backtest_threshold(
        self,
        score_data: pd.DataFrame,
        price_data: pd.DataFrame,
        buy_threshold: float,
        sell_threshold: float,
        holding_days: int
    ) -> ThresholdOptimizationResult:
        """回测特定阈值组合"""
        # 筛选买入信号
        buy_signals = score_data[score_data['ai_score'] >= buy_threshold]

        returns = []
        for _, row in buy_signals.iterrows():
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

            # 模拟持有期间，检查是否触发卖出信号
            sell_price = self._find_sell_price(
                score_data,
                price_data,
                stock_code,
                date,
                sell_threshold,
                holding_days
            )

            if sell_price is None:
                continue

            # 计算收益率
            ret = (sell_price - buy_price) / buy_price
            returns.append(ret)

        returns_series = pd.Series(returns)

        if len(returns_series) == 0:
            return ThresholdOptimizationResult(
                buy_threshold=buy_threshold,
                sell_threshold=sell_threshold,
                expected_return=0.0,
                win_rate=0.0,
                sharpe_ratio=0.0,
                total_trades=0
            )

        return ThresholdOptimizationResult(
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
            expected_return=returns_series.mean(),
            win_rate=(returns_series > 0).sum() / len(returns_series),
            sharpe_ratio=self._calculate_sharpe(returns_series),
            total_trades=len(returns_series)
        )

    def _find_sell_price(
        self,
        score_data: pd.DataFrame,
        price_data: pd.DataFrame,
        stock_code: str,
        buy_date: str,
        sell_threshold: float,
        max_holding_days: int
    ) -> float:
        """查找卖出价格"""
        # 获取买入后的评分数据
        future_scores = score_data[
            (score_data['stock_code'] == stock_code) &
            (score_data['date'] > buy_date)
        ].head(max_holding_days)

        # 检查是否触发卖出信号
        for _, score_row in future_scores.iterrows():
            if score_row['ai_score'] < sell_threshold:
                # 触发卖出，获取当日价格
                sell_price_data = price_data[
                    (price_data['stock_code'] == stock_code) &
                    (price_data['date'] == score_row['date'])
                ]

                if len(sell_price_data) > 0:
                    return sell_price_data.iloc[0]['close']

        # 未触发卖出信号，持有到期
        end_date = pd.to_datetime(buy_date) + pd.Timedelta(days=max_holding_days)
        end_price_data = price_data[
            (price_data['stock_code'] == stock_code) &
            (price_data['date'] >= end_date)
        ].head(1)

        if len(end_price_data) > 0:
            return end_price_data.iloc[0]['close']

        return None

    def _calculate_sharpe(self, returns: pd.Series, risk_free_rate: float = 0.03) -> float:
        """计算夏普比率"""
        if len(returns) == 0 or returns.std() == 0:
            return 0.0

        excess_return = returns.mean() - risk_free_rate / 252
        return excess_return / returns.std() * np.sqrt(252)


class RollingValidation:
    """滚动验证"""

    def rolling_backtest(
        self,
        score_data: pd.DataFrame,
        price_data: pd.DataFrame,
        train_window: int = 252,  # 训练窗口1年
        test_window: int = 63,    # 测试窗口3个月
        step: int = 21            # 步长1个月
    ) -> List[Dict[str, Any]]:
        """
        滚动回测验证

        Args:
            score_data: 评分数据
            price_data: 价格数据
            train_window: 训练窗口天数
            test_window: 测试窗口天数
            step: 滚动步长

        Returns:
            滚动验证结果列表
        """
        results = []
        optimizer = ScoreThresholdOptimizer()

        dates = sorted(score_data['date'].unique())
        total_days = len(dates)

        for i in range(0, total_days - train_window - test_window, step):
            # 训练期
            train_start = dates[i]
            train_end = dates[i + train_window]

            train_scores = score_data[
                (score_data['date'] >= train_start) &
                (score_data['date'] < train_end)
            ]

            train_prices = price_data[
                (price_data['date'] >= train_start) &
                (price_data['date'] < train_end)
            ]

            # 优化阈值
            optimal = optimizer.optimize_thresholds(
                train_scores,
                train_prices,
                holding_days=20
            )

            # 测试期
            test_start = train_end
            test_end = dates[min(i + train_window + test_window, total_days - 1)]

            test_scores = score_data[
                (score_data['date'] >= test_start) &
                (score_data['date'] < test_end)
            ]

            test_prices = price_data[
                (price_data['date'] >= test_start) &
                (price_data['date'] < test_end)
            ]

            # 测试阈值
            test_result = optimizer._backtest_threshold(
                test_scores,
                test_prices,
                optimal.buy_threshold,
                optimal.sell_threshold,
                holding_days=20
            )

            results.append({
                'train_period': f"{train_start} to {train_end}",
                'test_period': f"{test_start} to {test_end}",
                'optimal_buy_threshold': optimal.buy_threshold,
                'optimal_sell_threshold': optimal.sell_threshold,
                'train_sharpe': optimal.sharpe_ratio,
                'test_sharpe': test_result.sharpe_ratio,
                'test_return': test_result.expected_return,
                'test_win_rate': test_result.win_rate
            })

        return results