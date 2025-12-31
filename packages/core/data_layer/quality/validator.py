"""
数据质量验证器
验证数据完整性、准确性、一致性
"""
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

from ..sources.base_adapter import StockQuote, DailyBar, FinancialData

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    data: Any = None


class DataValidator:
    """数据质量验证器"""
    
    # 合理的数据范围
    PRICE_MIN = 0.01
    PRICE_MAX = 100000  # 最高价格限制
    CHANGE_PERCENT_MAX = 30  # 涨跌幅限制（考虑ST股票5%，普通股10%，科创板20%，北交所30%）
    PE_RATIO_MAX = 10000  # 市盈率上限
    VOLUME_MIN = 0
    
    def validate_quote(self, quote: StockQuote) -> ValidationResult:
        """
        验证实时行情数据
        
        Args:
            quote: 行情数据
            
        Returns:
            验证结果
        """
        errors = []
        warnings = []
        
        # 必填字段检查
        if not quote.stock_code:
            errors.append("股票代码为空")
        
        if not quote.stock_name:
            warnings.append("股票名称为空")
        
        # 价格合理性检查
        if quote.current_price <= 0:
            errors.append(f"当前价格异常: {quote.current_price}")
        elif quote.current_price > self.PRICE_MAX:
            warnings.append(f"当前价格过高: {quote.current_price}")
        
        # 涨跌幅检查
        if abs(quote.change_percent) > self.CHANGE_PERCENT_MAX:
            warnings.append(f"涨跌幅异常: {quote.change_percent}%")
        
        # 价格一致性检查
        if quote.high_price > 0 and quote.low_price > 0:
            if quote.current_price > quote.high_price * 1.01:
                errors.append(f"当前价格高于最高价: {quote.current_price} > {quote.high_price}")
            if quote.current_price < quote.low_price * 0.99:
                errors.append(f"当前价格低于最低价: {quote.current_price} < {quote.low_price}")
            if quote.high_price < quote.low_price:
                errors.append(f"最高价低于最低价: {quote.high_price} < {quote.low_price}")
        
        # 成交量检查
        if quote.volume < self.VOLUME_MIN:
            warnings.append(f"成交量为负: {quote.volume}")
        
        # 市盈率检查
        if quote.pe_ratio and quote.pe_ratio > self.PE_RATIO_MAX:
            warnings.append(f"市盈率过高: {quote.pe_ratio}")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            data=quote
        )
    
    def validate_daily_bars(self, bars: List[DailyBar]) -> ValidationResult:
        """
        验证日线数据
        
        Args:
            bars: 日线数据列表
            
        Returns:
            验证结果
        """
        errors = []
        warnings = []
        
        if not bars:
            errors.append("日线数据为空")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)
        
        prev_bar = None
        for i, bar in enumerate(bars):
            # 价格合理性
            if bar.close <= 0:
                errors.append(f"第{i+1}条数据收盘价异常: {bar.close}")
            
            # OHLC一致性
            if bar.high < bar.low:
                errors.append(f"{bar.date}: 最高价低于最低价")
            
            if bar.high > 0 and bar.low > 0:
                if bar.open > bar.high or bar.open < bar.low:
                    warnings.append(f"{bar.date}: 开盘价超出高低价范围")
                if bar.close > bar.high or bar.close < bar.low:
                    warnings.append(f"{bar.date}: 收盘价超出高低价范围")
            
            # 日期连续性检查（简化版）
            if prev_bar and bar.date <= prev_bar.date:
                warnings.append(f"日期顺序异常: {prev_bar.date} -> {bar.date}")
            
            # 涨跌幅检查
            if bar.change_percent and abs(bar.change_percent) > self.CHANGE_PERCENT_MAX:
                warnings.append(f"{bar.date}: 涨跌幅异常 {bar.change_percent}%")
            
            prev_bar = bar
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            data=bars
        )
    
    def validate_financial(self, data: FinancialData) -> ValidationResult:
        """
        验证财务数据
        
        Args:
            data: 财务数据
            
        Returns:
            验证结果
        """
        errors = []
        warnings = []
        
        if not data.stock_code:
            errors.append("股票代码为空")
        
        # ROE合理性检查
        if data.roe is not None:
            if data.roe > 100:
                warnings.append(f"ROE过高: {data.roe}%")
            elif data.roe < -100:
                warnings.append(f"ROE过低: {data.roe}%")
        
        # 资产负债率检查
        if data.debt_ratio is not None:
            if data.debt_ratio > 100:
                warnings.append(f"资产负债率超过100%: {data.debt_ratio}%")
            elif data.debt_ratio < 0:
                errors.append(f"资产负债率为负: {data.debt_ratio}%")
        
        # 毛利率检查
        if data.gross_margin is not None:
            if data.gross_margin > 100:
                warnings.append(f"毛利率超过100%: {data.gross_margin}%")
            elif data.gross_margin < -50:
                warnings.append(f"毛利率异常: {data.gross_margin}%")
        
        # 流动比率检查
        if data.current_ratio is not None:
            if data.current_ratio < 0:
                errors.append(f"流动比率为负: {data.current_ratio}")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            data=data
        )
    
    def validate_and_clean(self, data: Any, data_type: str) -> Tuple[bool, Any, List[str]]:
        """
        验证并清洗数据
        
        Args:
            data: 原始数据
            data_type: 数据类型 'quote'/'daily'/'financial'
            
        Returns:
            (是否有效, 清洗后的数据, 问题列表)
        """
        if data_type == 'quote':
            result = self.validate_quote(data)
        elif data_type == 'daily':
            result = self.validate_daily_bars(data)
        elif data_type == 'financial':
            result = self.validate_financial(data)
        else:
            return False, data, [f"未知数据类型: {data_type}"]
        
        issues = result.errors + result.warnings
        
        if result.errors:
            logger.warning(f"数据验证失败: {result.errors}")
        if result.warnings:
            logger.debug(f"数据验证警告: {result.warnings}")
        
        return result.is_valid, result.data, issues


# 全局单例
_validator_instance: Optional[DataValidator] = None


def get_validator() -> DataValidator:
    """获取验证器单例"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = DataValidator()
    return _validator_instance
