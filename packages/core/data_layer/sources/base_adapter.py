"""
数据源适配器基类
定义统一的数据获取接口
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import pandas as pd


@dataclass
class StockQuote:
    """股票实时行情数据模型"""
    stock_code: str
    stock_name: str
    current_price: float
    change_percent: float
    change_amount: float
    open_price: float
    high_price: float
    low_price: float
    prev_close: float
    volume: int
    amount: float
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    market_cap: Optional[float] = None
    timestamp: Optional[datetime] = None


@dataclass
class DailyBar:
    """日线数据模型"""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float
    change_percent: Optional[float] = None
    turnover: Optional[float] = None


@dataclass
class FinancialData:
    """财务数据模型"""
    stock_code: str
    report_period: str
    eps: Optional[float] = None  # 每股收益
    roe: Optional[float] = None  # 净资产收益率
    gross_margin: Optional[float] = None  # 毛利率
    net_margin: Optional[float] = None  # 净利率
    debt_ratio: Optional[float] = None  # 资产负债率
    current_ratio: Optional[float] = None  # 流动比率
    quick_ratio: Optional[float] = None  # 速动比率
    revenue_growth: Optional[float] = None  # 营收增长率
    profit_growth: Optional[float] = None  # 净利润增长率


class BaseDataAdapter(ABC):
    """数据源适配器基类"""
    
    def __init__(self, name: str, priority: int = 0):
        """
        初始化适配器
        
        Args:
            name: 数据源名称
            priority: 优先级，数字越大优先级越高
        """
        self.name = name
        self.priority = priority
        self._is_available = True
        self._last_error: Optional[str] = None
    
    @property
    def is_available(self) -> bool:
        """数据源是否可用"""
        return self._is_available
    
    @abstractmethod
    def get_realtime_quote(self, stock_code: str) -> Optional[StockQuote]:
        """
        获取实时行情
        
        Args:
            stock_code: 股票代码，如 600519.SH
            
        Returns:
            StockQuote对象或None
        """
        pass
    
    @abstractmethod
    def get_daily_bars(self, stock_code: str, start_date: str, 
                       end_date: str) -> Optional[List[DailyBar]]:
        """
        获取日线数据
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            
        Returns:
            DailyBar列表或None
        """
        pass
    
    @abstractmethod
    def get_financial_data(self, stock_code: str) -> Optional[FinancialData]:
        """
        获取财务数据
        
        Args:
            stock_code: 股票代码
            
        Returns:
            FinancialData对象或None
        """
        pass
    
    @abstractmethod
    def get_stock_list(self, market: str = 'all') -> Optional[pd.DataFrame]:
        """
        获取股票列表
        
        Args:
            market: 市场类型 'SH'/'SZ'/'all'
            
        Returns:
            股票列表DataFrame或None
        """
        pass
    
    def health_check(self) -> bool:
        """
        健康检查
        
        Returns:
            数据源是否正常
        """
        try:
            # 尝试获取一个简单的数据来验证连接
            result = self.get_stock_list('SH')
            self._is_available = result is not None and len(result) > 0
            return self._is_available
        except Exception as e:
            self._is_available = False
            self._last_error = str(e)
            return False
    
    def get_last_error(self) -> Optional[str]:
        """获取最后一次错误信息"""
        return self._last_error
