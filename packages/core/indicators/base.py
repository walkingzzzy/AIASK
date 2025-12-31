"""
技术指标基类
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Union
import numpy as np
import pandas as pd


class BaseIndicator(ABC):
    """技术指标基类"""
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        计算指标
        
        Args:
            data: 包含OHLCV数据的DataFrame
                  必须包含: open, high, low, close, volume
                  
        Returns:
            添加了指标列的DataFrame
        """
        pass
    
    @staticmethod
    def validate_data(data: pd.DataFrame, required_columns: List[str]) -> bool:
        """验证数据是否包含必要的列"""
        return all(col in data.columns for col in required_columns)
    
    @staticmethod
    def to_numpy(series: pd.Series) -> np.ndarray:
        """转换为numpy数组"""
        return series.values.astype(float)


def prepare_dataframe(data: Union[pd.DataFrame, List[Dict]]) -> pd.DataFrame:
    """
    准备标准化的DataFrame
    
    Args:
        data: 原始数据，可以是DataFrame或字典列表
        
    Returns:
        标准化的DataFrame，列名为小写
    """
    if isinstance(data, list):
        df = pd.DataFrame(data)
    else:
        df = data.copy()
    
    # 标准化列名
    column_mapping = {
        '开盘': 'open', '开盘价': 'open',
        '最高': 'high', '最高价': 'high',
        '最低': 'low', '最低价': 'low',
        '收盘': 'close', '收盘价': 'close',
        '成交量': 'volume',
        '成交额': 'amount',
        '日期': 'date'
    }
    
    df.columns = [column_mapping.get(col, col.lower()) for col in df.columns]
    
    return df
