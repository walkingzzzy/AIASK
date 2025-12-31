"""
集合竞价分析器
分析9:15-9:25竞价数据，识别异动股票
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

try:
    import akshare as ak
    import pandas as pd
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    ak = None
    pd = None

logger = logging.getLogger(__name__)


@dataclass
class AuctionStock:
    """竞价股票数据"""
    stock_code: str
    stock_name: str
    auction_price: float          # 竞价价格
    auction_change: float         # 竞价涨幅
    auction_volume: float         # 竞价成交量
    volume_ratio: float           # 量比
    buy_volume: float            # 买入量
    sell_volume: float           # 卖出量
    net_inflow: float            # 净流入
    is_abnormal: bool            # 是否异动
    abnormal_reason: List[str]   # 异动原因


class CallAuctionAnalyzer:
    """集合竞价分析器"""

    def __init__(self):
        if not HAS_AKSHARE:
            raise ImportError("akshare is required for CallAuctionAnalyzer")

        # 异动阈值配置
        self.config = {
            'high_change_threshold': 6.0,      # 高涨幅阈值
            'volume_ratio_threshold': 2.0,     # 量比阈值
            'big_order_threshold': 1000000,    # 大单阈值(元)
        }

    def get_auction_data(self) -> List[AuctionStock]:
        """
        获取集合竞价数据

        Returns:
            竞价股票列表
        """
        try:
            # 获取实时行情数据
            df = ak.stock_zh_a_spot_em()

            stocks = []
            for _, row in df.iterrows():
                stock = AuctionStock(
                    stock_code=row['代码'],
                    stock_name=row['名称'],
                    auction_price=float(row.get('最新价', 0)),
                    auction_change=float(row.get('涨跌幅', 0)),
                    auction_volume=float(row.get('成交量', 0)),
                    volume_ratio=float(row.get('量比', 1.0)),
                    buy_volume=float(row.get('买入量', 0)),
                    sell_volume=float(row.get('卖出量', 0)),
                    net_inflow=float(row.get('净流入', 0)),
                    is_abnormal=False,
                    abnormal_reason=[]
                )

                # 判断是否异动
                stock.is_abnormal, stock.abnormal_reason = self._check_abnormal(stock)

                stocks.append(stock)

            return stocks

        except Exception as e:
            logger.error(f"获取竞价数据失败: {e}")
            return []

    def _check_abnormal(self, stock: AuctionStock) -> tuple:
        """
        检查是否异动

        Args:
            stock: 股票数据

        Returns:
            (是否异动, 异动原因列表)
        """
        reasons = []

        # 高涨幅异动
        if stock.auction_change >= self.config['high_change_threshold']:
            reasons.append(f"竞价涨幅{stock.auction_change:.2f}%")

        # 量比异动
        if stock.volume_ratio >= self.config['volume_ratio_threshold']:
            reasons.append(f"量比{stock.volume_ratio:.2f}倍")

        # 大单净流入
        if stock.net_inflow >= self.config['big_order_threshold']:
            reasons.append(f"大单净流入{stock.net_inflow/10000:.0f}万")

        return len(reasons) > 0, reasons

    def get_auction_ranking(self, top_n: int = 50) -> Dict[str, List[AuctionStock]]:
        """
        获取竞价排行榜

        Args:
            top_n: 返回前N名

        Returns:
            排行榜字典
        """
        stocks = self.get_auction_data()

        return {
            'change_ranking': sorted(stocks, key=lambda x: x.auction_change, reverse=True)[:top_n],
            'volume_ranking': sorted(stocks, key=lambda x: x.auction_volume, reverse=True)[:top_n],
            'ratio_ranking': sorted(stocks, key=lambda x: x.volume_ratio, reverse=True)[:top_n],
            'abnormal_stocks': [s for s in stocks if s.is_abnormal][:top_n]
        }

    def analyze_auction_stock(self, stock_code: str) -> Dict[str, Any]:
        """
        分析单只股票的竞价情况

        Args:
            stock_code: 股票代码

        Returns:
            分析结果
        """
        stocks = self.get_auction_data()
        target = next((s for s in stocks if s.stock_code == stock_code), None)

        if not target:
            return {'error': '未找到股票'}

        # 生成分析报告
        analysis = {
            'stock_info': {
                'code': target.stock_code,
                'name': target.stock_name,
                'auction_price': target.auction_price,
                'auction_change': target.auction_change,
            },
            'auction_metrics': {
                'volume': target.auction_volume,
                'volume_ratio': target.volume_ratio,
                'net_inflow': target.net_inflow,
            },
            'is_abnormal': target.is_abnormal,
            'abnormal_reasons': target.abnormal_reason,
            'open_prediction': self._predict_open(target),
            'operation_advice': self._generate_advice(target),
        }

        return analysis

    def _predict_open(self, stock: AuctionStock) -> str:
        """预测开盘走势"""
        if stock.auction_change > 7 and stock.volume_ratio > 3:
            return "强势高开，可能冲击涨停"
        elif stock.auction_change > 3 and stock.net_inflow > 0:
            return "高开，关注能否站稳"
        elif stock.auction_change < -3:
            return "低开，注意风险"
        else:
            return "平开，观望为主"

    def _generate_advice(self, stock: AuctionStock) -> str:
        """生成操作建议"""
        if stock.is_abnormal and stock.auction_change > 6:
            return "竞价异动明显，开盘可关注，但需警惕冲高回落"
        elif stock.volume_ratio > 3 and stock.net_inflow > 0:
            return "量价配合良好，可适量参与"
        elif stock.auction_change > 9:
            return "涨幅过大，追高风险高，建议观望"
        else:
            return "竞价表现一般，观望为主"
