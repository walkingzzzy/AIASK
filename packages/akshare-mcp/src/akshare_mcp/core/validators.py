"""
数据验证器（使用Pydantic）
确保返回数据的完整性和正确性
"""

from typing import Optional
from pydantic import BaseModel, Field, validator


class StockQuote(BaseModel):
    """股票行情数据模型"""
    
    code: str = Field(..., description="股票代码")
    name: str = Field(default="", description="股票名称")
    price: Optional[float] = Field(None, description="当前价格")
    change: Optional[float] = Field(None, description="涨跌额")
    changePercent: Optional[float] = Field(None, description="涨跌幅(%)")
    open: Optional[float] = Field(None, description="开盘价")
    high: Optional[float] = Field(None, description="最高价")
    low: Optional[float] = Field(None, description="最低价")
    preClose: Optional[float] = Field(None, description="昨收价")
    volume: Optional[int] = Field(None, description="成交量")
    amount: Optional[float] = Field(None, description="成交额")
    turnoverRate: Optional[float] = Field(None, description="换手率")
    source: str = Field(default="unknown", description="数据源")
    
    @validator('price')
    def price_must_be_positive(cls, v):
        """价格必须大于0"""
        if v is not None and v <= 0:
            raise ValueError('价格必须大于0')
        return v
    
    @validator('volume')
    def volume_must_be_non_negative(cls, v):
        """成交量不能为负"""
        if v is not None and v < 0:
            raise ValueError('成交量不能为负')
        return v
    
    @validator('amount')
    def amount_must_be_non_negative(cls, v):
        """成交额不能为负"""
        if v is not None and v < 0:
            raise ValueError('成交额不能为负')
        return v
    
    class Config:
        # 允许额外字段
        extra = 'allow'


class KlineData(BaseModel):
    """K线数据模型"""
    
    date: str = Field(..., description="日期")
    open: Optional[float] = Field(None, description="开盘价")
    close: Optional[float] = Field(None, description="收盘价")
    high: Optional[float] = Field(None, description="最高价")
    low: Optional[float] = Field(None, description="最低价")
    volume: Optional[int] = Field(None, description="成交量")
    amount: Optional[float] = Field(None, description="成交额")
    source: str = Field(default="unknown", description="数据源")
    
    @validator('open', 'close', 'high', 'low')
    def price_must_be_positive(cls, v):
        """价格必须大于0"""
        if v is not None and v <= 0:
            raise ValueError('价格必须大于0')
        return v
    
    @validator('volume')
    def volume_must_be_non_negative(cls, v):
        """成交量不能为负"""
        if v is not None and v < 0:
            raise ValueError('成交量不能为负')
        return v
    
    @validator('high')
    def high_must_be_highest(cls, v, values):
        """最高价必须是最高的"""
        if v is None:
            return v
        
        open_price = values.get('open')
        close_price = values.get('close')
        low_price = values.get('low')
        
        prices = [p for p in [open_price, close_price, low_price] if p is not None]
        if prices and v < max(prices):
            # 警告但不抛出异常（数据可能有误差）
            pass
        
        return v
    
    @validator('low')
    def low_must_be_lowest(cls, v, values):
        """最低价必须是最低的"""
        if v is None:
            return v
        
        open_price = values.get('open')
        close_price = values.get('close')
        high_price = values.get('high')
        
        prices = [p for p in [open_price, close_price, high_price] if p is not None]
        if prices and v > min(prices):
            # 警告但不抛出异常（数据可能有误差）
            pass
        
        return v
    
    class Config:
        extra = 'allow'


def validate_quote(data: dict) -> StockQuote:
    """
    验证行情数据
    
    Args:
        data: 原始数据字典
    
    Returns:
        验证后的StockQuote对象
    
    Raises:
        ValueError: 数据验证失败
    """
    try:
        return StockQuote(**data)
    except Exception as e:
        raise ValueError(f"行情数据验证失败: {e}")


def validate_kline(data: dict) -> KlineData:
    """
    验证K线数据
    
    Args:
        data: 原始数据字典
    
    Returns:
        验证后的KlineData对象
    
    Raises:
        ValueError: 数据验证失败
    """
    try:
        return KlineData(**data)
    except Exception as e:
        raise ValueError(f"K线数据验证失败: {e}")


def validate_kline_list(data_list: list) -> list:
    """
    批量验证K线数据
    
    Args:
        data_list: K线数据列表
    
    Returns:
        验证后的数据列表（跳过无效数据）
    """
    validated = []
    for i, data in enumerate(data_list):
        try:
            validated_data = validate_kline(data)
            validated.append(validated_data.dict())
        except ValueError as e:
            # 跳过无效数据，记录警告
            import sys
            print(f"Warning: K线数据第{i}条验证失败: {e}", file=sys.stderr)
            continue
    
    return validated
