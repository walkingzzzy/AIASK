"""
TdxQuant 公式计算系统模块

向后兼容：所有原始导出保持不变
"""

from .utils import _convert_to_tdx_code, _convert_period, _ensure_formula_api
from .fallback import (
    _get_kline_for_fallback,
    _aggregate_klines,
    _fallback_calculate_indicator,
    _fallback_screen_stocks,
    _fallback_expert_signals,
    _get_default_stock_pool,
)
from .api import calculate_indicator, screen_stocks, get_expert_signals, get_formula_data
from .shortcuts import (
    calculate_macd, calculate_kdj, calculate_rsi, calculate_boll,
    calculate_trix, calculate_dma, calculate_expma, calculate_dmi,
    calculate_cr, calculate_vr,
    register,
)

__all__ = [
    '_convert_to_tdx_code', '_convert_period', '_ensure_formula_api',
    '_get_kline_for_fallback', '_aggregate_klines',
    '_fallback_calculate_indicator', '_fallback_screen_stocks',
    '_fallback_expert_signals', '_get_default_stock_pool',
    'calculate_indicator', 'screen_stocks', 'get_expert_signals', 'get_formula_data',
    'calculate_macd', 'calculate_kdj', 'calculate_rsi', 'calculate_boll',
    'calculate_trix', 'calculate_dma', 'calculate_expma', 'calculate_dmi',
    'calculate_cr', 'calculate_vr',
    'register',
]
