"""
回测可视化报告生成器
基于score_backtest.py的回测结果生成可视化报告
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class BacktestVisualizationConfig:
    """可视化配置"""
    figsize: tuple = (12, 8)
    dpi: int = 100
    style: str = 'seaborn-v0_8-darkgrid'
    color_palette: List[str] = None

    def __post_init__(self):
        if self.color_palette is None:
            self.color_palette = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']


class BacktestVisualizer:
    """
    回测可视化器

    功能：
    1. 评分分布图
    2. 各评分区间收益曲线
    3. 阈值优化热力图
    4. 滚动验证时序图
    5. 综合报告生成
    """

    def __init__(self, config: Optional[BacktestVisualizationConfig] = None):
        self.config = config or BacktestVisualizationConfig()
        self._init_plotting()

    def _init_plotting(self):
        """初始化绘图库"""
        try:
            import matplotlib
            matplotlib.use('Agg')  # 非交互式后端
            import matplotlib.pyplot as plt
            import seaborn as sns

            self.plt = plt
            self.sns = sns

            # 设置样式
            try:
                plt.style.use(self.config.style)
            except:
                logger.warning(f"样式 {self.config.style} 不可用，使用默认样式")

            # 设置中文字体
            plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
            plt.rcParams['axes.unicode_minus'] = False

            self.available = True
            logger.info("可视化库初始化成功")

        except ImportError as e:
            logger.warning(f"可视化库导入失败: {e}")
            self.available = False

    def plot_score_distribution(self, score_data: pd.DataFrame, save_path: str = None) -> Optional[str]:
        """
        绘制评分分布图

        Args:
            score_data: 评分数据 (columns: ai_score)
            save_path: 保存路径

        Returns:
            图片路径
        """
        if not self.available:
            logger.warning("可视化库不可用")
            return None

        fig, axes = self.plt.subplots(1, 2, figsize=self.config.figsize)

        # 直方图
        axes[0].hist(score_data['ai_score'], bins=50, color=self.config.color_palette[0], alpha=0.7)
        axes[0].set_xlabel('AI评分')
        axes[0].set_ylabel('频数')
        axes[0].set_title('AI评分分布直方图')
        axes[0].grid(True, alpha=0.3)

        # 箱线图
        axes[1].boxplot(score_data['ai_score'], vert=True)
        axes[1].set_ylabel('AI评分')
        axes[1].set_title('AI评分箱线图')
        axes[1].grid(True, alpha=0.3)

        self.plt.tight_layout()

        if save_path:
            self.plt.savefig(save_path, dpi=self.config.dpi, bbox_inches='tight')
            logger.info(f"评分分布图已保存: {save_path}")
            self.plt.close()
            return save_path

        return None

    def plot_score_returns_curve(self, backtest_results: List, save_path: str = None) -> Optional[str]:
        """
        绘制各评分区间收益曲线

        Args:
            backtest_results: 回测结果列表 (List[ScoreBacktestResult])
            save_path: 保存路径

        Returns:
            图片路径
        """
        if not self.available or not backtest_results:
            return None

        fig, axes = self.plt.subplots(2, 2, figsize=(14, 10))

        # 提取数据
        score_ranges = [r.score_range for r in backtest_results]
        avg_returns = [r.avg_return * 100 for r in backtest_results]
        win_rates = [r.win_rate * 100 for r in backtest_results]
        sharpe_ratios = [r.sharpe_ratio for r in backtest_results]
        max_drawdowns = [abs(r.max_drawdown) * 100 for r in backtest_results]

        # 1. 平均收益率
        axes[0, 0].bar(score_ranges, avg_returns, color=self.config.color_palette[0], alpha=0.7)
        axes[0, 0].set_xlabel('评分区间')
        axes[0, 0].set_ylabel('平均收益率 (%)')
        axes[0, 0].set_title('各评分区间平均收益率')
        axes[0, 0].axhline(y=0, color='red', linestyle='--', alpha=0.5)
        axes[0, 0].grid(True, alpha=0.3)
        axes[0, 0].tick_params(axis='x', rotation=45)

        # 2. 胜率
        axes[0, 1].bar(score_ranges, win_rates, color=self.config.color_palette[1], alpha=0.7)
        axes[0, 1].set_xlabel('评分区间')
        axes[0, 1].set_ylabel('胜率 (%)')
        axes[0, 1].set_title('各评分区间胜率')
        axes[0, 1].axhline(y=50, color='red', linestyle='--', alpha=0.5)
        axes[0, 1].grid(True, alpha=0.3)
        axes[0, 1].tick_params(axis='x', rotation=45)

        # 3. 夏普比率
        axes[1, 0].bar(score_ranges, sharpe_ratios, color=self.config.color_palette[2], alpha=0.7)
        axes[1, 0].set_xlabel('评分区间')
        axes[1, 0].set_ylabel('夏普比率')
        axes[1, 0].set_title('各评分区间夏普比率')
        axes[1, 0].axhline(y=0, color='red', linestyle='--', alpha=0.5)
        axes[1, 0].grid(True, alpha=0.3)
        axes[1, 0].tick_params(axis='x', rotation=45)

        # 4. 最大回撤
        axes[1, 1].bar(score_ranges, max_drawdowns, color=self.config.color_palette[3], alpha=0.7)
        axes[1, 1].set_xlabel('评分区间')
        axes[1, 1].set_ylabel('最大回撤 (%)')
        axes[1, 1].set_title('各评分区间最大回撤')
        axes[1, 1].grid(True, alpha=0.3)
        axes[1, 1].tick_params(axis='x', rotation=45)

        self.plt.tight_layout()

        if save_path:
            self.plt.savefig(save_path, dpi=self.config.dpi, bbox_inches='tight')
            logger.info(f"收益曲线图已保存: {save_path}")
            self.plt.close()
            return save_path

        return None

    def plot_threshold_heatmap(self, threshold_results: pd.DataFrame, save_path: str = None) -> Optional[str]:
        """
        绘制阈值优化热力图

        Args:
            threshold_results: 阈值优化结果 (columns: threshold, metric, value)
            save_path: 保存路径

        Returns:
            图片路径
        """
        if not self.available or threshold_results is None or len(threshold_results) == 0:
            return None

        # 透视表
        pivot_data = threshold_results.pivot(index='threshold', columns='metric', values='value')

        fig, ax = self.plt.subplots(figsize=self.config.figsize)

        # 绘制热力图
        im = self.sns.heatmap(pivot_data, annot=True, fmt='.2f', cmap='RdYlGn',
                              center=0, ax=ax, cbar_kws={'label': '指标值'})

        ax.set_xlabel('评估指标')
        ax.set_ylabel('评分阈值')
        ax.set_title('阈值优化热力图')

        self.plt.tight_layout()

        if save_path:
            self.plt.savefig(save_path, dpi=self.config.dpi, bbox_inches='tight')
            logger.info(f"阈值热力图已保存: {save_path}")
            self.plt.close()
            return save_path

        return None

    def plot_rolling_validation(self, rolling_results: List[Dict], save_path: str = None) -> Optional[str]:
        """
        绘制滚动验证时序图

        Args:
            rolling_results: 滚动验证结果
            save_path: 保存路径

        Returns:
            图片路径
        """
        if not self.available or not rolling_results:
            return None

        fig, axes = self.plt.subplots(2, 1, figsize=(14, 8))

        # 提取数据
        periods = [r['period'] for r in rolling_results]
        returns = [r['return'] * 100 for r in rolling_results]
        sharpe = [r['sharpe'] for r in rolling_results]

        # 1. 收益率时序
        axes[0].plot(periods, returns, marker='o', color=self.config.color_palette[0], linewidth=2)
        axes[0].set_xlabel('时间窗口')
        axes[0].set_ylabel('收益率 (%)')
        axes[0].set_title('滚动验证收益率')
        axes[0].axhline(y=0, color='red', linestyle='--', alpha=0.5)
        axes[0].grid(True, alpha=0.3)
        axes[0].tick_params(axis='x', rotation=45)

        # 2. 夏普比率时序
        axes[1].plot(periods, sharpe, marker='s', color=self.config.color_palette[1], linewidth=2)
        axes[1].set_xlabel('时间窗口')
        axes[1].set_ylabel('夏普比率')
        axes[1].set_title('滚动验证夏普比率')
        axes[1].axhline(y=0, color='red', linestyle='--', alpha=0.5)
        axes[1].grid(True, alpha=0.3)
        axes[1].tick_params(axis='x', rotation=45)

        self.plt.tight_layout()

        if save_path:
            self.plt.savefig(save_path, dpi=self.config.dpi, bbox_inches='tight')
            logger.info(f"滚动验证图已保存: {save_path}")
            self.plt.close()
            return save_path

        return None

    def generate_comprehensive_report(self, backtest_results: List, output_dir: str) -> Dict[str, str]:
        """
        生成综合回测报告

        Args:
            backtest_results: 回测结果
            output_dir: 输出目录

        Returns:
            生成的图片路径字典
        """
        import os
        os.makedirs(output_dir, exist_ok=True)

        report_paths = {}

        # 1. 评分分布图
        # 需要score_data，这里简化处理
        logger.info("生成评分分布图...")

        # 2. 收益曲线图
        returns_path = os.path.join(output_dir, 'score_returns_curve.png')
        self.plot_score_returns_curve(backtest_results, returns_path)
        report_paths['returns_curve'] = returns_path

        logger.info(f"综合报告已生成: {output_dir}")
        return report_paths

