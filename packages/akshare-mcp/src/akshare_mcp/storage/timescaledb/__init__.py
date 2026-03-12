"""TimescaleDB 适配器包 — 拆分自 timescaledb.py

子模块:
- schema: 连接管理与 DDL 初始化 (SchemaBase)
- kline: K线数据读写 (KlineMixin)
- stock_info: 股票信息查询 (StockInfoMixin)
- financials: 财务数据查询 (FinancialsMixin)
- quotes: 实时行情保存与统计 (QuotesMixin)
- artifacts: 策略工件持久化 (ArtifactMixin)

向后兼容：
    from .timescaledb import TimescaleDBAdapter, get_db
仍然有效。
"""

import asyncio
import atexit
import logging
from typing import Awaitable, Optional, TypeVar

from .schema import SchemaBase
from .kline import KlineMixin
from .stock_info import StockInfoMixin
from .financials import FinancialsMixin
from .quotes import QuotesMixin
from .artifacts import ArtifactMixin
from .strategy import StrategyMixin
from .factor_storage import FactorStorageMixin
from .signal_tracking import SignalTrackingMixin

logger = logging.getLogger(__name__)
T = TypeVar('T')


class TimescaleDBAdapter(
    KlineMixin,
    StockInfoMixin,
    FinancialsMixin,
    QuotesMixin,
    ArtifactMixin,
    StrategyMixin,
    FactorStorageMixin,
    SignalTrackingMixin,
    SchemaBase,
):
    """TimescaleDB 异步适配器（Mixin 组合）

    通过 Mixin 组合:
    - SchemaBase: 连接池管理、事件循环检测、DDL 初始化
    - KlineMixin: K线数据 get_klines / save_klines
    - StockInfoMixin: 股票信息 get_stock_info / search_stocks
    - FinancialsMixin: 财务数据 get_financials
    - QuotesMixin: 实时行情 save_quote / get_stats
    - ArtifactMixin: 策略工件 save_artifact / get_artifact_by_id / list_artifacts_db
    - StrategyMixin: 策略超市 save_strategy / list_strategies / subscribe / review
    - FactorStorageMixin: 因子持久化 save_factor_values / get_factor_values / save_factor_ic
    - SignalTrackingMixin: 前向信号记录 save_signals / get_signals / get_signal_stats
    """
    pass


# 全局单例
_db_instance: Optional[TimescaleDBAdapter] = None
_shutdown_registered = False


def _safe_shutdown_db_atexit() -> None:
    """独立脚本退出时尽力关闭数据库连接池。"""
    if _db_instance is None:
        return
    try:
        asyncio.run(close_db())
    except RuntimeError:
        logger.warning("[storage] skip db shutdown: event loop unavailable")
    except Exception as exc:
        logger.warning("[storage] db shutdown failed: %s", exc)


def _ensure_shutdown_hook_registered() -> None:
    global _shutdown_registered
    if _shutdown_registered:
        return
    atexit.register(_safe_shutdown_db_atexit)
    _shutdown_registered = True


def get_db() -> TimescaleDBAdapter:
    """获取数据库实例（全局单例）

    TimescaleDBAdapter 内部会自动检测事件循环变更并重建连接池，
    因此单例模式是安全的。
    """
    global _db_instance
    _ensure_shutdown_hook_registered()
    if _db_instance is None:
        _db_instance = TimescaleDBAdapter()
    return _db_instance


async def close_db() -> None:
    """关闭全局数据库实例并释放连接池。"""
    global _db_instance
    if _db_instance is None:
        return
    try:
        await _db_instance.close()
    finally:
        _db_instance = None


async def await_with_db_cleanup(awaitable: Awaitable[T]) -> T:
    """在当前事件循环中运行 awaitable，并在结束前显式关闭 DB。"""
    try:
        return await awaitable
    finally:
        await close_db()


def run_with_db_cleanup(awaitable: Awaitable[T]) -> T:
    """独立脚本入口：使用 asyncio.run 包裹，并确保同 loop 收尾。"""
    return asyncio.run(await_with_db_cleanup(awaitable))


__all__ = [
    'TimescaleDBAdapter',
    'get_db',
    'close_db',
    'await_with_db_cleanup',
    'run_with_db_cleanup',
]