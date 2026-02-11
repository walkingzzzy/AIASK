"""
回测引擎包 - 使用Numba JIT优化 + Ray并行计算

向后兼容：所有原始导出保持不变
"""

from .utils import _ensure_dict_list, _resolve_slippage_model, _compute_slippage_rate
from .strategies import (
    _backtest_ma_cross_jit,
    _backtest_ma_cross_with_trades_jit,
    _backtest_momentum_jit,
    _backtest_rsi_jit,
)
from .engine import BacktestEngine, backtest_engine
from .advanced import AdvancedBacktestEngine, advanced_backtest_engine

# 条件导入并行引擎
from .parallel import RAY_AVAILABLE
if RAY_AVAILABLE:
    from .parallel import ParallelBacktestEngine

__all__ = [
    # 工具函数
    '_ensure_dict_list', '_resolve_slippage_model', '_compute_slippage_rate',
    # 策略函数
    '_backtest_ma_cross_jit', '_backtest_ma_cross_with_trades_jit',
    '_backtest_momentum_jit', '_backtest_rsi_jit',
    # 引擎类和实例
    'BacktestEngine', 'backtest_engine',
    'AdvancedBacktestEngine', 'advanced_backtest_engine',
    'RAY_AVAILABLE',
]
