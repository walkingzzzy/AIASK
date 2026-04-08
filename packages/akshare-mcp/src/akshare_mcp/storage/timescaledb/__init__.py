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
import threading
import weakref
from typing import Awaitable, Optional, TypeVar

from .schema import SchemaBase
from .kline import KlineMixin
from .stock_info import StockInfoMixin
from .financials import FinancialsMixin
from .quotes import QuotesMixin
from .market_context import MarketContextMixin
from .vector_unified import VectorUnifiedMixin
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
    MarketContextMixin,
    VectorUnifiedMixin,
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


# 兼容旧测试/调用方的别名；真实缓存已按 loop/thread 隔离
_db_instance: Optional[TimescaleDBAdapter] = None
_db_instances_by_loop: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, TimescaleDBAdapter] = weakref.WeakKeyDictionary()
_db_instances_by_thread: dict[int, TimescaleDBAdapter] = {}
_db_instance_lock = threading.Lock()
_shutdown_registered = False


def _force_terminate_instance(instance: Optional[TimescaleDBAdapter], *, reason: str) -> None:
    if instance is None:
        return
    terminate = getattr(instance, '_force_terminate_pool', None)
    if callable(terminate):
        try:
            terminate(reason=reason)
        except Exception as exc:
            logger.warning("[storage] force terminate failed: %s", exc)
    reset = getattr(instance, '_reset_pool_state', None)
    if callable(reset):
        try:
            reset()
        except Exception as exc:
            logger.warning("[storage] reset pool state failed: %s", exc)


async def _flush_cleanup_callbacks() -> None:
    """让底层 HTTP/DB transport 在 loop 结束前完成关闭回调。"""
    await asyncio.sleep(0)
    await asyncio.sleep(0.01)


async def drain_cleanup_callbacks() -> None:
    """Public wrapper for transport cleanup drains used by shared shutdown paths."""
    await _flush_cleanup_callbacks()


def _snapshot_instances_locked() -> list[TimescaleDBAdapter]:
    instances: list[TimescaleDBAdapter] = []
    seen: set[int] = set()
    for instance in list(_db_instances_by_loop.values()) + list(_db_instances_by_thread.values()) + [_db_instance]:
        if instance is None:
            continue
        marker = id(instance)
        if marker in seen:
            continue
        seen.add(marker)
        instances.append(instance)
    return instances


def _refresh_legacy_alias_locked() -> None:
    global _db_instance
    remaining = _snapshot_instances_locked()
    _db_instance = remaining[0] if remaining else None


async def _close_instance(
    instance: Optional[TimescaleDBAdapter],
    *,
    current_loop: asyncio.AbstractEventLoop | None,
    force_foreign_loop: bool,
) -> None:
    if instance is None:
        return
    bound_loop = getattr(instance, '_bound_loop', None)
    if force_foreign_loop and current_loop is not None and bound_loop not in (None, current_loop):
        _force_terminate_instance(instance, reason="close_db called from different event loop")
        return
    await asyncio.shield(instance.close())


async def _close_all_db_instances() -> None:
    global _db_instance, _db_instances_by_loop, _db_instances_by_thread
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    with _db_instance_lock:
        instances = _snapshot_instances_locked()
        _db_instance = None
        _db_instances_by_loop = weakref.WeakKeyDictionary()
        _db_instances_by_thread = {}

    first_error: Exception | None = None
    for instance in instances:
        try:
            await _close_instance(
                instance,
                current_loop=current_loop,
                force_foreign_loop=True,
            )
        except Exception as exc:
            if first_error is None:
                first_error = exc

    if first_error is not None:
        raise first_error


def _safe_shutdown_db_atexit() -> None:
    """独立脚本退出时尽力关闭数据库连接池。"""
    global _db_instance, _db_instances_by_loop, _db_instances_by_thread
    with _db_instance_lock:
        instances = _snapshot_instances_locked()
    if not instances:
        return
    try:
        asyncio.run(_close_all_db_instances())
    except RuntimeError:
        logger.warning("[storage] skip db shutdown: event loop unavailable")
        for instance in instances:
            _force_terminate_instance(instance, reason="atexit runtime loop unavailable")
        with _db_instance_lock:
            _db_instance = None
            _db_instances_by_loop = weakref.WeakKeyDictionary()
            _db_instances_by_thread = {}
    except Exception as exc:
        logger.warning("[storage] db shutdown failed: %s", exc)
        for instance in instances:
            _force_terminate_instance(instance, reason=f"atexit close failure: {exc}")
        with _db_instance_lock:
            _db_instance = None
            _db_instances_by_loop = weakref.WeakKeyDictionary()
            _db_instances_by_thread = {}


def _ensure_shutdown_hook_registered() -> None:
    global _shutdown_registered
    if _shutdown_registered:
        return
    atexit.register(_safe_shutdown_db_atexit)
    _shutdown_registered = True


def get_db() -> TimescaleDBAdapter:
    """获取数据库实例。

    asyncpg 连接池绑定事件循环；重型 MCP 请求若分发到不同 loop/thread，
    共享同一个 adapter 仍可能出现跨 loop 复用与连接被中途关闭的问题。
    因此这里改为按“当前事件循环 / 当前线程”隔离实例。
    """
    global _db_instance
    _ensure_shutdown_hook_registered()
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    with _db_instance_lock:
        thread_id = threading.get_ident()
        if current_loop is not None:
            instance = _db_instances_by_loop.get(current_loop)
            if instance is None:
                thread_instance = _db_instances_by_thread.get(thread_id)
                if thread_instance is not None and getattr(thread_instance, '_bound_loop', None) in (None, current_loop):
                    instance = thread_instance
                    _db_instances_by_thread.pop(thread_id, None)
                else:
                    instance = TimescaleDBAdapter()
                _db_instances_by_loop[current_loop] = instance
        else:
            instance = _db_instances_by_thread.get(thread_id)
            if instance is None:
                instance = TimescaleDBAdapter()
                _db_instances_by_thread[thread_id] = instance

        _db_instance = instance
        return instance


async def close_db() -> None:
    """关闭当前事件循环/线程作用域下的数据库实例。"""
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    with _db_instance_lock:
        thread_id = threading.get_ident()
        instances: list[TimescaleDBAdapter] = []
        if current_loop is not None:
            loop_instance = _db_instances_by_loop.pop(current_loop, None)
            thread_instance = _db_instances_by_thread.get(thread_id)
            if thread_instance is not None and getattr(thread_instance, '_bound_loop', None) in (None, current_loop):
                _db_instances_by_thread.pop(thread_id, None)
            else:
                thread_instance = None
            for instance in (loop_instance, thread_instance):
                if instance is not None and instance not in instances:
                    instances.append(instance)
        else:
            instance = _db_instances_by_thread.pop(thread_id, None)
            instances = [instance] if instance is not None else []
        _refresh_legacy_alias_locked()

    if not instances:
        return

    for instance in instances:
        await _close_instance(
            instance,
            current_loop=current_loop,
            force_foreign_loop=False,
        )


async def await_with_db_cleanup(awaitable: Awaitable[T]) -> T:
    """在当前事件循环中运行 awaitable，并在结束前显式关闭共享资源。"""
    try:
        return await awaitable
    finally:
        try:
            from ...services import close_shared_runtime_clients
        except Exception:
            close_shared_runtime_clients = None
        if callable(close_shared_runtime_clients):
            try:
                await asyncio.shield(close_shared_runtime_clients())
            except Exception as exc:
                logger.warning("[storage] shared runtime client shutdown failed: %s", exc)
        try:
            await asyncio.shield(close_db())
        except Exception as exc:
            logger.warning("[storage] db shutdown failed during cleanup: %s", exc)
        try:
            await asyncio.shield(_flush_cleanup_callbacks())
        except Exception as exc:
            logger.warning("[storage] cleanup callback drain failed: %s", exc)


def run_with_db_cleanup(awaitable: Awaitable[T]) -> T:
    """独立脚本入口：使用 asyncio.run 包裹，并确保同 loop 收尾。"""
    return asyncio.run(await_with_db_cleanup(awaitable))


__all__ = [
    'TimescaleDBAdapter',
    'get_db',
    'close_db',
    'drain_cleanup_callbacks',
    'await_with_db_cleanup',
    'run_with_db_cleanup',
]
