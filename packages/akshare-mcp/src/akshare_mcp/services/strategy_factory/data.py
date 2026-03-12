"""策略工厂数据模块兼容导出。"""

from .collect import DataCollector
from .opportunity import MarketOpportunityScanner

__all__ = ["DataCollector", "MarketOpportunityScanner"]
