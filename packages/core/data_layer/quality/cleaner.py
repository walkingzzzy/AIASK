"""
数据清洗器
处理缺失值、异常值、数据格式标准化
"""
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass
import logging
import pandas as pd
import numpy as np

from ..sources.base_adapter import StockQuote, DailyBar, FinancialData

logger = logging.getLogger(__name__)


@dataclass
class CleaningResult:
    """清洗结果"""
    success: bool
    data: Any
    changes: List[str]
    dropped_count: int = 0


class DataCleaner:
    """数据清洗器"""
    
    def __init__(self):
        self.cleaning_stats = {
            'total_cleaned': 0,
            'nulls_filled': 0,
            'outliers_fixed': 0,
            'duplicates_removed': 0
        }
    
    def clean_quote(self, quote: StockQuote) -> CleaningResult:
        """
        清洗实时行情数据
        
        Args:
            quote: 原始行情数据
            
        Returns:
            清洗结果
        """
        changes = []
        
        # 股票代码标准化
        if quote.stock_code:
            original_code = quote.stock_code
            quote.stock_code = self._normalize_stock_code(quote.stock_code)
            if quote.stock_code != original_code:
                changes.append(f"股票代码标准化: {original_code} -> {quote.stock_code}")
        
        # 处理负价格
        if quote.current_price < 0:
            quote.current_price = abs(quote.current_price)
            changes.append(f"修正负价格: {quote.current_price}")
        
        # 处理异常涨跌幅（超过30%的截断）
        if abs(quote.change_percent) > 30:
            original = quote.change_percent
            quote.change_percent = max(-30, min(30, quote.change_percent))
            changes.append(f"涨跌幅截断: {original} -> {quote.change_percent}")
        
        # 处理缺失的PE/PB
        if quote.pe_ratio is None or quote.pe_ratio <= 0:
            quote.pe_ratio = None  # 保持为None而不是填充
        
        if quote.pb_ratio is None or quote.pb_ratio <= 0:
            quote.pb_ratio = None
        
        self.cleaning_stats['total_cleaned'] += 1
        
        return CleaningResult(
            success=True,
            data=quote,
            changes=changes
        )
    
    def clean_daily_bars(self, bars: List[DailyBar], 
                         fill_missing: bool = True) -> CleaningResult:
        """
        清洗日线数据
        
        Args:
            bars: 原始日线数据
            fill_missing: 是否填充缺失值
            
        Returns:
            清洗结果
        """
        if not bars:
            return CleaningResult(success=False, data=[], changes=["数据为空"])
        
        changes = []
        cleaned_bars = []
        dropped = 0
        
        for i, bar in enumerate(bars):
            # 跳过完全无效的数据
            if bar.close <= 0 and bar.open <= 0:
                dropped += 1
                continue
            
            # 修复OHLC异常
            if bar.high < bar.low and bar.high > 0 and bar.low > 0:
                bar.high, bar.low = bar.low, bar.high
                changes.append(f"{bar.date}: 交换高低价")
            
            # 修复开盘价超出范围
            if bar.high > 0 and bar.low > 0:
                if bar.open > bar.high:
                    bar.open = bar.high
                    changes.append(f"{bar.date}: 开盘价修正为最高价")
                elif bar.open < bar.low:
                    bar.open = bar.low
                    changes.append(f"{bar.date}: 开盘价修正为最低价")
                
                # 修复收盘价超出范围
                if bar.close > bar.high:
                    bar.close = bar.high
                    changes.append(f"{bar.date}: 收盘价修正为最高价")
                elif bar.close < bar.low:
                    bar.close = bar.low
                    changes.append(f"{bar.date}: 收盘价修正为最低价")
            
            # 处理负成交量
            if bar.volume < 0:
                bar.volume = abs(bar.volume)
                changes.append(f"{bar.date}: 修正负成交量")
            
            cleaned_bars.append(bar)
        
        # 按日期排序
        cleaned_bars.sort(key=lambda x: x.date)
        
        # 去重
        seen_dates = set()
        unique_bars = []
        for bar in cleaned_bars:
            if bar.date not in seen_dates:
                seen_dates.add(bar.date)
                unique_bars.append(bar)
            else:
                dropped += 1
                changes.append(f"{bar.date}: 移除重复数据")
        
        self.cleaning_stats['total_cleaned'] += len(unique_bars)
        self.cleaning_stats['duplicates_removed'] += dropped
        
        return CleaningResult(
            success=True,
            data=unique_bars,
            changes=changes,
            dropped_count=dropped
        )
    
    def clean_financial(self, data: FinancialData) -> CleaningResult:
        """
        清洗财务数据
        
        Args:
            data: 原始财务数据
            
        Returns:
            清洗结果
        """
        changes = []
        
        # 股票代码标准化
        if data.stock_code:
            original_code = data.stock_code
            data.stock_code = self._normalize_stock_code(data.stock_code)
            if data.stock_code != original_code:
                changes.append(f"股票代码标准化: {original_code} -> {data.stock_code}")
        
        # 处理异常ROE（超过200%的截断）
        if data.roe is not None and abs(data.roe) > 200:
            original = data.roe
            data.roe = max(-200, min(200, data.roe))
            changes.append(f"ROE截断: {original} -> {data.roe}")
        
        # 处理异常资产负债率
        if data.debt_ratio is not None:
            if data.debt_ratio < 0:
                data.debt_ratio = 0
                changes.append("资产负债率修正为0")
            elif data.debt_ratio > 150:
                data.debt_ratio = 150
                changes.append(f"资产负债率截断为150%")
        
        # 处理异常毛利率
        if data.gross_margin is not None:
            if data.gross_margin > 100:
                data.gross_margin = 100
                changes.append("毛利率截断为100%")
        
        self.cleaning_stats['total_cleaned'] += 1
        
        return CleaningResult(
            success=True,
            data=data,
            changes=changes
        )
    
    def clean_dataframe(self, df: pd.DataFrame, 
                        config: Optional[Dict] = None) -> CleaningResult:
        """
        清洗DataFrame数据
        
        Args:
            df: 原始DataFrame
            config: 清洗配置
            
        Returns:
            清洗结果
        """
        if df is None or df.empty:
            return CleaningResult(success=False, data=df, changes=["数据为空"])
        
        changes = []
        original_len = len(df)
        df = df.copy()
        
        config = config or {}
        
        # 1. 移除完全重复的行
        if config.get('remove_duplicates', True):
            before = len(df)
            df = df.drop_duplicates()
            if len(df) < before:
                changes.append(f"移除{before - len(df)}行重复数据")
        
        # 2. 处理缺失值
        if config.get('fill_nulls', True):
            null_counts = df.isnull().sum()
            for col in df.columns:
                if null_counts[col] > 0:
                    if df[col].dtype in ['float64', 'int64']:
                        # 数值列用前值填充
                        df[col] = df[col].fillna(method='ffill').fillna(method='bfill')
                        changes.append(f"列{col}填充{null_counts[col]}个缺失值")
                    else:
                        # 非数值列用空字符串
                        df[col] = df[col].fillna('')
        
        # 3. 处理异常值（使用IQR方法）
        if config.get('fix_outliers', False):
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            for col in numeric_cols:
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower = Q1 - 3 * IQR
                upper = Q3 + 3 * IQR
                
                outliers = ((df[col] < lower) | (df[col] > upper)).sum()
                if outliers > 0:
                    df[col] = df[col].clip(lower=lower, upper=upper)
                    changes.append(f"列{col}修正{outliers}个异常值")
        
        dropped = original_len - len(df)
        
        return CleaningResult(
            success=True,
            data=df,
            changes=changes,
            dropped_count=dropped
        )
    
    def _normalize_stock_code(self, code: str) -> str:
        """
        标准化股票代码
        
        支持格式：
        - 600519 -> 600519.SH
        - 000001 -> 000001.SZ
        - 600519.SH -> 600519.SH
        """
        code = code.strip().upper()
        
        # 已经是标准格式
        if '.' in code:
            return code
        
        # 根据代码前缀判断市场
        if code.startswith(('6', '9')):
            return f"{code}.SH"
        elif code.startswith(('0', '3', '2')):
            return f"{code}.SZ"
        elif code.startswith(('4', '8')):
            return f"{code}.BJ"  # 北交所
        else:
            return code
    
    def get_stats(self) -> Dict[str, int]:
        """获取清洗统计"""
        return self.cleaning_stats.copy()
    
    def reset_stats(self):
        """重置统计"""
        self.cleaning_stats = {
            'total_cleaned': 0,
            'nulls_filled': 0,
            'outliers_fixed': 0,
            'duplicates_removed': 0
        }


# 全局单例
_cleaner_instance: Optional[DataCleaner] = None


def get_cleaner() -> DataCleaner:
    """获取清洗器单例"""
    global _cleaner_instance
    if _cleaner_instance is None:
        _cleaner_instance = DataCleaner()
    return _cleaner_instance
