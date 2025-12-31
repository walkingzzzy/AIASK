# 数据层模块
# 提供多数据源适配、缓存、数据质量验证、持久化存储等功能

from .sources.akshare_adapter import AKShareAdapter
from .sources.eastmoney_adapter import EastMoneyAdapter
from .sources.source_aggregator import DataSourceAggregator
from .cache.cache_manager import CacheManager
from .quality.validator import DataValidator
from .quality.cleaner import DataCleaner
from .quality.monitor import DataQualityMonitor
from .storage.timeseries_db import TimeSeriesDB
from .storage.document_db import DocumentDB

__all__ = [
    # 数据源
    'AKShareAdapter',
    'EastMoneyAdapter',
    'DataSourceAggregator',
    # 缓存
    'CacheManager',
    # 数据质量
    'DataValidator',
    'DataCleaner',
    'DataQualityMonitor',
    # 持久化存储
    'TimeSeriesDB',
    'DocumentDB'
]
