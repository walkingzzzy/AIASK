"""
A股股票列表获取模块
支持从多个数据源获取股票列表
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class StockListProvider:
    """股票列表提供者"""

    # A股主要指数成分股（示例）
    INDEX_STOCKS = {
        "沪深300": [
            "600519", "600036", "601318", "600276", "000858",  # 白酒、金融
            "601166", "601288", "601398", "601939", "601988",  # 银行
            "600030", "601012", "600887", "600809", "002475",  # 保险、地产
            "000002", "000333", "000651", "002594", "300750",  # 地产、科技
        ],
        "上证50": [
            "600519", "600036", "601318", "600276", "601166",
            "601288", "601398", "601939", "601988", "600030",
        ],
        "创业板": [
            "300750", "300059", "300142", "300124", "300122",
            "300015", "300014", "300003", "300002", "300001",
        ]
    }

    # 行业龙头股票
    INDUSTRY_LEADERS = {
        "白酒": ["600519", "000858", "000568", "603369", "600809"],
        "银行": ["601398", "601939", "601288", "601166", "600036"],
        "保险": ["601318", "601601", "601336", "601628"],
        "地产": ["000002", "001979", "600048", "000001"],
        "医药": ["600276", "000661", "002007", "300015"],
        "科技": ["300750", "002415", "002594", "300059"],
        "新能源": ["300750", "002594", "300014", "002129"],
        "消费": ["600519", "000858", "603288", "002304"],
    }

    @staticmethod
    def get_hot_stocks() -> List[str]:
        """获取热门股票列表"""
        hot_stocks = set()

        # 添加沪深300成分股
        hot_stocks.update(StockListProvider.INDEX_STOCKS["沪深300"])

        # 添加行业龙头
        for stocks in StockListProvider.INDUSTRY_LEADERS.values():
            hot_stocks.update(stocks)

        return sorted(list(hot_stocks))

    @staticmethod
    def get_index_stocks(index_name: str) -> List[str]:
        """获取指定指数的成分股"""
        return StockListProvider.INDEX_STOCKS.get(index_name, [])

    @staticmethod
    def get_industry_stocks(industry: str) -> List[str]:
        """获取指定行业的股票"""
        return StockListProvider.INDUSTRY_LEADERS.get(industry, [])

    @staticmethod
    def get_all_a_stocks() -> List[str]:
        """
        获取全部A股列表

        注意：这里返回示例数据，实际应该从数据源获取
        """
        # 收集所有已知股票
        all_stocks = set()

        # 添加指数成分股
        for stocks in StockListProvider.INDEX_STOCKS.values():
            all_stocks.update(stocks)

        # 添加行业股票
        for stocks in StockListProvider.INDUSTRY_LEADERS.values():
            all_stocks.update(stocks)

        # 添加更多示例股票（实际应该从数据源获取完整列表）
        additional_stocks = [
            # 沪市主板
            "600000", "600004", "600005", "600006", "600007",
            "600008", "600009", "600010", "600011", "600012",
            # 深市主板
            "000001", "000002", "000003", "000004", "000005",
            "000006", "000007", "000008", "000009", "000010",
            # 创业板
            "300001", "300002", "300003", "300004", "300005",
            "300006", "300007", "300008", "300009", "300010",
        ]
        all_stocks.update(additional_stocks)

        return sorted(list(all_stocks))

    @staticmethod
    def get_stock_info(stock_code: str) -> Optional[Dict]:
        """
        获取股票基本信息

        注意：这里返回模拟数据，实际应该从数据源获取
        """
        # 股票名称映射（示例）
        stock_names = {
            "600519": "贵州茅台",
            "000858": "五粮液",
            "601318": "中国平安",
            "600036": "招商银行",
            "300750": "宁德时代",
            "002594": "比亚迪",
            "000651": "格力电器",
            "000333": "美的集团",
            "600276": "恒瑞医药",
            "603259": "药明康德",
        }

        # 行业映射（示例）
        stock_industries = {
            "600519": "白酒",
            "000858": "白酒",
            "601318": "保险",
            "600036": "银行",
            "300750": "新能源",
            "002594": "新能源",
            "000651": "家电",
            "000333": "家电",
            "600276": "医药",
            "603259": "医药",
        }

        name = stock_names.get(stock_code, f"股票{stock_code}")
        industry = stock_industries.get(stock_code, "其他")

        return {
            "code": stock_code,
            "name": name,
            "industry": industry,
            "market": "SH" if stock_code.startswith("6") else "SZ",
        }


def get_stock_list_provider() -> StockListProvider:
    """获取股票列表提供者"""
    return StockListProvider()
