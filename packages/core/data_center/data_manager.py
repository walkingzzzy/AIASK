"""
数据管理器
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .models import DataCategory, DataQuery, DataStatistics

logger = logging.getLogger(__name__)


class DataManager:
    """数据管理器"""

    def __init__(self):
        self.cache = {}
        self.data_service = None
        self._init_data_service()

    def _init_data_service(self):
        """初始化数据服务"""
        try:
            from services.stock_data_service import get_stock_service
            self.data_service = get_stock_service()
        except Exception as e:
            logger.warning(f"数据服务初始化失败: {e}")

    def query_data(self, query: DataQuery) -> List[Dict[str, Any]]:
        """
        查询数据

        Args:
            query: 数据查询请求

        Returns:
            数据列表
        """
        if not self.data_service:
            return []

        try:
            if query.category == DataCategory.MARKET:
                return self._query_market_data(query)
            elif query.category == DataCategory.FINANCIAL:
                return self._query_financial_data(query)
            elif query.category == DataCategory.FUND_FLOW:
                return self._query_fund_flow_data(query)
            elif query.category == DataCategory.TECHNICAL:
                return self._query_technical_data(query)
            else:
                return []
        except Exception as e:
            logger.error(f"查询数据失败: {e}")
            return []

    def _query_market_data(self, query: DataQuery) -> List[Dict[str, Any]]:
        """查询市场数据"""
        results = []
        try:
            if query.stock_code:
                # 获取K线数据
                df = self.data_service.get_kline_data(
                    query.stock_code,
                    start_date=query.start_date.strftime('%Y%m%d') if query.start_date else None,
                    end_date=query.end_date.strftime('%Y%m%d') if query.end_date else None
                )
                if df is not None and not df.empty:
                    results = df.to_dict('records')
        except Exception as e:
            logger.error(f"查询市场数据失败: {e}")
        return results

    def _query_financial_data(self, query: DataQuery) -> List[Dict[str, Any]]:
        """查询财务数据"""
        results = []
        try:
            if query.stock_code:
                # 获取财务数据
                financial_data = self.data_service.get_financial_data(query.stock_code)
                if financial_data:
                    results = [financial_data]
        except Exception as e:
            logger.error(f"查询财务数据失败: {e}")
        return results

    def _query_fund_flow_data(self, query: DataQuery) -> List[Dict[str, Any]]:
        """查询资金流向数据"""
        # 预留接口
        return []

    def _query_technical_data(self, query: DataQuery) -> List[Dict[str, Any]]:
        """查询技术指标数据"""
        # 预留接口
        return []

    def get_available_categories(self) -> List[Dict[str, Any]]:
        """获取可用的数据类别"""
        return [
            {
                "category": cat.value,
                "name": cat.name,
                "description": self._get_category_description(cat)
            }
            for cat in DataCategory
        ]

    def get_category_statistics(self, category: DataCategory) -> DataStatistics:
        """
        获取数据类别统计

        Args:
            category: 数据类别

        Returns:
            数据统计
        """
        # 简化统计，返回基本信息
        today = datetime.now()
        start_date = today - timedelta(days=365)

        stats = DataStatistics(
            category=category,
            total_records=0,
            date_range={
                "start": start_date.strftime("%Y-%m-%d"),
                "end": today.strftime("%Y-%m-%d")
            },
            stock_count=0,
            last_update=today
        )

        # 根据数据服务可用性更新统计
        if self.data_service:
            if category == DataCategory.MARKET:
                stats.total_records = 1000  # 估算值
                stats.stock_count = 5000
            elif category == DataCategory.FINANCIAL:
                stats.total_records = 500
                stats.stock_count = 5000

        return stats

    def get_all_statistics(self) -> List[DataStatistics]:
        """获取所有数据类别的统计"""
        return [
            self.get_category_statistics(cat)
            for cat in DataCategory
        ]

    def _get_category_description(self, category: DataCategory) -> str:
        """获取数据类别描述"""
        descriptions = {
            DataCategory.MARKET: "股票实时行情、K线数据、成交量等市场数据",
            DataCategory.FINANCIAL: "财务报表、财务指标、业绩预告等财务数据",
            DataCategory.FUND_FLOW: "主力资金、北向资金、融资融券等资金流向数据",
            DataCategory.TECHNICAL: "技术指标、形态识别、量价分析等技术分析数据",
            DataCategory.SENTIMENT: "新闻情绪、社交媒体情绪、市场热度等情绪数据",
            DataCategory.RESEARCH: "券商研报、评级、目标价等研究报告数据"
        }
        return descriptions.get(category, "")

    def get_available_fields(self, category: DataCategory) -> List[Dict[str, str]]:
        """
        获取数据类别的可用字段

        Args:
            category: 数据类别

        Returns:
            字段列表
        """
        fields_map = {
            DataCategory.MARKET: [
                {"field": "stock_code", "name": "股票代码", "type": "string"},
                {"field": "stock_name", "name": "股票名称", "type": "string"},
                {"field": "date", "name": "日期", "type": "date"},
                {"field": "open", "name": "开盘价", "type": "float"},
                {"field": "high", "name": "最高价", "type": "float"},
                {"field": "low", "name": "最低价", "type": "float"},
                {"field": "close", "name": "收盘价", "type": "float"},
                {"field": "volume", "name": "成交量", "type": "int"},
                {"field": "amount", "name": "成交额", "type": "float"}
            ],
            DataCategory.FINANCIAL: [
                {"field": "stock_code", "name": "股票代码", "type": "string"},
                {"field": "report_date", "name": "报告期", "type": "date"},
                {"field": "revenue", "name": "营业收入", "type": "float"},
                {"field": "net_profit", "name": "净利润", "type": "float"},
                {"field": "eps", "name": "每股收益", "type": "float"},
                {"field": "roe", "name": "净资产收益率", "type": "float"}
            ]
        }
        return fields_map.get(category, [])
