"""
行业对比分析模块
"""
from typing import Dict, Any, List
from dataclasses import dataclass
import pandas as pd


@dataclass
class IndustryRanking:
    """行业排名结果"""
    stock_code: str
    stock_name: str
    rank: int
    total_stocks: int
    percentile: float
    score: float
    metrics: Dict[str, Any]


class IndustryComparison:
    """行业对比分析"""

    def __init__(self):
        self.metrics = [
            'roe', 'pe', 'pb', 'revenue_growth',
            'profit_growth', 'gross_margin', 'net_margin'
        ]

    def get_industry_ranking(
        self,
        stock_code: str,
        industry_stocks: List[Dict[str, Any]]
    ) -> IndustryRanking:
        """
        获取个股在行业中的排名

        Args:
            stock_code: 股票代码
            industry_stocks: 行业内所有股票数据

        Returns:
            行业排名结果
        """
        # 找到目标股票
        target_stock = next(
            (s for s in industry_stocks if s['stock_code'] == stock_code),
            None
        )

        if not target_stock:
            raise ValueError(f"Stock {stock_code} not found in industry")

        # 计算综合得分
        scores = []
        for stock in industry_stocks:
            score = self._calculate_composite_score(stock)
            scores.append({
                'stock_code': stock['stock_code'],
                'stock_name': stock.get('stock_name', ''),
                'score': score,
                'metrics': stock
            })

        # 排序
        scores.sort(key=lambda x: x['score'], reverse=True)

        # 找到目标股票排名
        rank = next(
            (i + 1 for i, s in enumerate(scores) if s['stock_code'] == stock_code),
            len(scores)
        )

        percentile = (len(scores) - rank + 1) / len(scores) * 100

        return IndustryRanking(
            stock_code=stock_code,
            stock_name=target_stock.get('stock_name', ''),
            rank=rank,
            total_stocks=len(scores),
            percentile=percentile,
            score=scores[rank - 1]['score'],
            metrics=target_stock
        )

    def compare_with_peers(
        self,
        stock_data: Dict[str, Any],
        peer_stocks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        与同行业公司对比

        Args:
            stock_data: 目标股票数据
            peer_stocks: 同行业股票列表

        Returns:
            对比结果
        """
        comparisons = {}

        for metric in self.metrics:
            stock_value = stock_data.get(metric, 0)
            peer_values = [s.get(metric, 0) for s in peer_stocks if s.get(metric) is not None]

            if not peer_values:
                continue

            avg_value = sum(peer_values) / len(peer_values)
            median_value = sorted(peer_values)[len(peer_values) // 2]
            percentile = sum(1 for v in peer_values if v <= stock_value) / len(peer_values) * 100

            comparisons[metric] = {
                'value': stock_value,
                'industry_avg': avg_value,
                'industry_median': median_value,
                'percentile': percentile,
                'vs_avg': (stock_value - avg_value) / avg_value * 100 if avg_value != 0 else 0,
                'rank_signal': self._get_rank_signal(metric, percentile)
            }

        return comparisons

    def _calculate_composite_score(self, stock: Dict[str, Any]) -> float:
        """计算综合得分"""
        score = 0
        weights = {
            'roe': 0.25,
            'revenue_growth': 0.20,
            'profit_growth': 0.20,
            'gross_margin': 0.15,
            'net_margin': 0.10,
            'pe': 0.05,  # 反向指标
            'pb': 0.05   # 反向指标
        }

        for metric, weight in weights.items():
            value = stock.get(metric, 0)

            # 归一化到0-10分
            if metric == 'roe':
                normalized = min(value / 2, 10)  # ROE 20%为满分
            elif metric in ['revenue_growth', 'profit_growth']:
                normalized = min((value + 10) / 5, 10)  # -10%到40%映射到0-10
            elif metric in ['gross_margin', 'net_margin']:
                normalized = min(value / 10, 10)  # 100%为满分
            elif metric in ['pe', 'pb']:
                # 反向指标，越低越好
                normalized = max(10 - value / 5, 0)
            else:
                normalized = 5

            score += normalized * weight

        return score

    def _get_rank_signal(self, metric: str, percentile: float) -> str:
        """获取排名信号"""
        # 对于反向指标（PE, PB），低百分位更好
        if metric in ['pe', 'pb']:
            if percentile < 30:
                return 'excellent'
            elif percentile < 50:
                return 'good'
            elif percentile < 70:
                return 'average'
            else:
                return 'poor'
        else:
            # 正向指标
            if percentile > 70:
                return 'excellent'
            elif percentile > 50:
                return 'good'
            elif percentile > 30:
                return 'average'
            else:
                return 'poor'


class SectorRotation:
    """板块轮动分析"""

    def analyze_sector_strength(
        self,
        sector_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        分析板块强度

        Args:
            sector_data: 板块数据列表

        Returns:
            板块强度排名
        """
        results = []

        for sector in sector_data:
            # 计算板块综合强度
            strength_score = self._calculate_sector_strength(sector)

            results.append({
                'sector_name': sector.get('name', ''),
                'strength_score': strength_score,
                'avg_change': sector.get('avg_change', 0),
                'fund_flow': sector.get('fund_flow', 0),
                'leading_stocks': sector.get('leading_stocks', []),
                'signal': self._get_sector_signal(strength_score)
            })

        # 按强度排序
        results.sort(key=lambda x: x['strength_score'], reverse=True)

        return results

    def _calculate_sector_strength(self, sector: Dict[str, Any]) -> float:
        """计算板块强度"""
        score = 0

        # 涨跌幅权重40%
        avg_change = sector.get('avg_change', 0)
        score += min(max(avg_change * 2, 0), 4)

        # 资金流向权重40%
        fund_flow = sector.get('fund_flow', 0)
        if fund_flow > 0:
            score += min(fund_flow / 1000000000 * 2, 4)  # 每10亿加2分

        # 上涨股票占比权重20%
        up_ratio = sector.get('up_ratio', 0.5)
        score += up_ratio * 2

        return min(score, 10)

    def _get_sector_signal(self, strength_score: float) -> str:
        """获取板块信号"""
        if strength_score >= 7:
            return 'strong'
        elif strength_score >= 5:
            return 'moderate'
        else:
            return 'weak'