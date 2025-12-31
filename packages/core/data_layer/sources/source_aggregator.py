"""
数据源聚合器
实现多数据源容错和自动切换
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from .base_adapter import (
    BaseDataAdapter, StockQuote, DailyBar, FinancialData
)
from .akshare_adapter import AKShareAdapter
from .local_db_adapter import LocalDBAdapter

logger = logging.getLogger(__name__)


class DataSourceAggregator:
    """
    数据源聚合器
    
    功能：
    1. 管理多个数据源适配器
    2. 按优先级自动切换数据源
    3. 数据源健康检查和故障转移
    """
    
    def __init__(self):
        self._adapters: List[BaseDataAdapter] = []
        self._init_default_adapters()
    
    def _init_default_adapters(self):
        """初始化默认数据源"""
        # 本地数据库作为主数据源（优先级最高）
        local_adapter = LocalDBAdapter()
        if local_adapter.health_check():
            self.register_adapter(local_adapter)
            logger.info("本地数据库数据源已启用（主数据源）")
        else:
            logger.warning("本地数据库不可用")
        
        # AKShare作为备用数据源
        self.register_adapter(AKShareAdapter())

        # Tushare作为第三数据源
        try:
            from .tushare_adapter import TushareAdapter

            tushare_adapter = TushareAdapter()
            if tushare_adapter.health_check():
                self.register_adapter(tushare_adapter)
                logger.info("Tushare备用数据源已启用")
            else:
                logger.info("Tushare未配置或不可用，跳过")
        except Exception as e:
            logger.debug(f"Tushare初始化跳过: {e}")
    
    def register_adapter(self, adapter: BaseDataAdapter):
        """
        注册数据源适配器
        
        Args:
            adapter: 数据源适配器实例
        """
        self._adapters.append(adapter)
        # 按优先级排序，优先级高的在前
        self._adapters.sort(key=lambda x: x.priority, reverse=True)
        logger.info(f"注册数据源: {adapter.name}, 优先级: {adapter.priority}")
    
    def get_available_adapters(self) -> List[BaseDataAdapter]:
        """获取所有可用的数据源"""
        return [a for a in self._adapters if a.is_available]
    
    def _try_adapters(self, method_name: str, *args, **kwargs) -> Optional[Any]:
        """
        尝试从多个数据源获取数据
        
        Args:
            method_name: 要调用的方法名
            *args, **kwargs: 方法参数
            
        Returns:
            第一个成功返回的结果，或None
        """
        for adapter in self._adapters:
            if not adapter.is_available:
                continue
            
            try:
                method = getattr(adapter, method_name)
                result = method(*args, **kwargs)
                if result is not None:
                    logger.debug(f"从 {adapter.name} 获取数据成功")
                    return result
            except Exception as e:
                logger.warning(f"{adapter.name} 获取数据失败: {str(e)}")
                continue
        
        logger.error(f"所有数据源均无法获取数据: {method_name}")
        return None
    
    def get_realtime_quote(self, stock_code: str) -> Optional[StockQuote]:
        """获取实时行情（多源容错）"""
        return self._try_adapters('get_realtime_quote', stock_code)
    
    def get_daily_bars(self, stock_code: str, start_date: str,
                       end_date: str) -> Optional[List[DailyBar]]:
        """获取日线数据（多源容错）"""
        return self._try_adapters('get_daily_bars', stock_code, start_date, end_date)
    
    def get_financial_data(self, stock_code: str) -> Optional[FinancialData]:
        """获取财务数据（多源容错）"""
        return self._try_adapters('get_financial_data', stock_code)
    
    def get_stock_list(self, market: str = 'all') -> Optional[Any]:
        """获取股票列表（多源容错）"""
        return self._try_adapters('get_stock_list', market)
    
    def get_north_fund_flow(self) -> Optional[Any]:
        """获取北向资金流向"""
        return self._try_adapters('get_north_fund_flow')
    
    def get_sector_fund_flow(self) -> Optional[Any]:
        """获取行业资金流向"""
        return self._try_adapters('get_sector_fund_flow')
    
    def health_check_all(self) -> Dict[str, bool]:
        """
        检查所有数据源健康状态
        
        Returns:
            {数据源名称: 是否健康}
        """
        results = {}
        for adapter in self._adapters:
            results[adapter.name] = adapter.health_check()
        return results
    
    def get_status(self) -> Dict[str, Any]:
        """获取聚合器状态"""
        return {
            "total_adapters": len(self._adapters),
            "available_adapters": len(self.get_available_adapters()),
            "adapters": [
                {
                    "name": a.name,
                    "priority": a.priority,
                    "available": a.is_available,
                    "last_error": a.get_last_error()
                }
                for a in self._adapters
            ]
        }


# 全局单例
_aggregator_instance: Optional[DataSourceAggregator] = None


def get_data_source() -> DataSourceAggregator:
    """获取数据源聚合器单例"""
    global _aggregator_instance
    if _aggregator_instance is None:
        _aggregator_instance = DataSourceAggregator()
    return _aggregator_instance
