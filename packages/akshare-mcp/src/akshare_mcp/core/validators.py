"""
数据验证器（使用Pydantic）
确保返回数据的完整性和正确性
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


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

    model_config = ConfigDict(extra='allow')

    @field_validator('price')
    @classmethod
    def price_must_be_positive(cls, v):
        """价格必须大于0"""
        if v is not None and v <= 0:
            raise ValueError('价格必须大于0')
        return v

    @field_validator('volume', mode='before')
    @classmethod
    def convert_volume_to_int(cls, v):
        """将成交量转换为整数（处理浮点数输入）"""
        if v is None:
            return None
        try:
            # 如果是浮点数，转换为整数
            return int(float(v))
        except (ValueError, TypeError):
            return None

    @field_validator('volume')
    @classmethod
    def volume_must_be_non_negative(cls, v):
        """成交量不能为负"""
        if v is not None and v < 0:
            raise ValueError('成交量不能为负')
        return v

    @field_validator('amount')
    @classmethod
    def amount_must_be_non_negative(cls, v):
        """成交额不能为负"""
        if v is not None and v < 0:
            raise ValueError('成交额不能为负')
        return v


class KlineData(BaseModel):
    """K线数据模型"""

    date: str = Field(..., description="日期")
    open: Optional[float] = Field(None, description="开盘价")
    close: Optional[float] = Field(None, description="收盘价")
    high: Optional[float] = Field(None, description="最高价")
    low: Optional[float] = Field(None, description="最低价")
    volume: Optional[int] = Field(None, description="成交量")
    amount: Optional[float] = Field(None, description="成交额")
    turnover: Optional[float] = Field(None, description="换手率(%)")
    change_pct: Optional[float] = Field(None, description="涨跌幅(%)")
    source: str = Field(default="unknown", description="数据源")

    model_config = ConfigDict(extra='allow')

    @field_validator('open', 'close', 'high', 'low')
    @classmethod
    def price_must_be_positive(cls, v):
        """价格必须大于0"""
        if v is not None and v <= 0:
            raise ValueError('价格必须大于0')
        return v

    @field_validator('volume', mode='before')
    @classmethod
    def convert_volume_to_int(cls, v):
        """将成交量转换为整数（处理浮点数输入）"""
        if v is None:
            return None
        try:
            # 如果是浮点数，转换为整数
            return int(float(v))
        except (ValueError, TypeError):
            return None

    @field_validator('volume')
    @classmethod
    def volume_must_be_non_negative(cls, v):
        """成交量不能为负"""
        if v is not None and v < 0:
            raise ValueError('成交量不能为负')
        return v

    @model_validator(mode='after')
    def validate_ohlc_relationships(self):
        """确保 high/low 与 open/close 之间满足基本 OHLC 约束。"""
        upper_bounds = [value for value in (self.open, self.close, self.low) if value is not None]
        if self.high is not None and upper_bounds and self.high < max(upper_bounds):
            raise ValueError('最高价不能低于开盘价、收盘价或最低价')

        lower_bounds = [value for value in (self.open, self.close, self.high) if value is not None]
        if self.low is not None and lower_bounds and self.low > min(lower_bounds):
            raise ValueError('最低价不能高于开盘价、收盘价或最高价')

        return self


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
            validated.append(validated_data.model_dump())
        except ValueError as e:
            # 跳过无效数据，记录警告
            import sys
            print(f"Warning: K线数据第{i}条验证失败: {e}", file=sys.stderr)
            continue
    
    return validated
