"""
SchemaBase — 连接池管理、事件循环检测、DDL 初始化入口

SchemaBase._init_tables() 委托给 schema_market / schema_strategy
两个模块分别创建市场数据表和策略相关表。
"""

import os
import asyncio
import logging
from typing import Optional
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

from ...env_loader import load_mcp_env

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    asyncpg = None


class SchemaBase:
    """TimescaleDB 连接管理与表结构初始化

    关键设计：asyncpg.Pool 绑定到创建它的事件循环。
    如果 FastMCP 回收/重建事件循环，旧 pool 会报 "Event loop is closed"。
    因此每次 acquire() 时检测当前事件循环是否与 pool 创建时一致，
    不一致则自动重建 pool。
    """

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._initialized = False
        self._init_lock: Optional[asyncio.Lock] = None
        self._init_lock_loop: Optional[asyncio.AbstractEventLoop] = None
        self._bound_loop: Optional[asyncio.AbstractEventLoop] = None
        self._pgvector_enabled = False

    def _get_init_lock(self) -> asyncio.Lock:
        """懒加载初始化锁，确保在当前事件循环中创建"""
        loop = asyncio.get_running_loop()
        if self._init_lock is None or self._init_lock_loop is not loop:
            self._init_lock = asyncio.Lock()
            self._init_lock_loop = loop
        return self._init_lock

    def _reset_pool_state(self) -> None:
        """重置连接池状态。"""
        self.pool = None
        self._initialized = False
        self._bound_loop = None
        self._init_lock = None
        self._init_lock_loop = None

    def _terminate_stale_pool(self, current_loop: asyncio.AbstractEventLoop) -> None:
        """事件循环切换时，尽力终止旧连接池，避免直接丢引用。"""
        old_pool = self.pool
        old_loop = self._bound_loop
        if old_pool is None or old_loop is current_loop:
            return

        if self._force_terminate_pool(old_pool, reason="event loop changed"):
            logger.info("Terminated stale connection pool after event loop change")

    def _force_terminate_pool(self, pool=None, *, reason: Optional[str] = None) -> bool:
        """同步强制终止连接池，用于 loop 已关闭或关闭超时的兜底路径。"""
        target_pool = pool or self.pool
        if target_pool is None:
            return False

        terminate = getattr(target_pool, 'terminate', None)
        if not callable(terminate):
            return False

        try:
            terminate()
            if reason:
                logger.info("Force terminated connection pool: %s", reason)
            return True
        except Exception as exc:
            if "event loop is closed" in str(exc).lower():
                logger.info("Skip stale pool terminate after loop close")
                return False
            logger.warning("Failed to terminate stale connection pool: %s", exc)
            return False

    async def _flush_close_callbacks(self) -> None:
        """给事件循环一次排空关闭回调的机会，减少 asyncpg transport 泄漏告警。"""
        try:
            await asyncio.sleep(0)
            await asyncio.sleep(0.01)
        except RuntimeError:
            return

    @staticmethod
    def _read_int_env(name: str, default: int, minimum: int) -> int:
        try:
            value = int(os.getenv(name, str(default)))
        except (TypeError, ValueError):
            value = default
        return max(minimum, value)

    @staticmethod
    def _read_float_env(name: str, default: float, minimum: float = 0.0) -> float:
        try:
            value = float(os.getenv(name, str(default)))
        except (TypeError, ValueError):
            value = default
        return max(minimum, value)

    @staticmethod
    def _resolve_startup_profile() -> str:
        raw = str(os.getenv('AKSHARE_MCP_STARTUP_PROFILE', 'full')).strip().lower()
        if raw in {'tool-only', 'tool_only', 'worker', 'lite'}:
            return 'tool-only'
        return 'full'

    def _build_db_config(self) -> dict:
        profile = self._resolve_startup_profile()
        default_min_size = 1
        default_max_size = 4 if profile == 'full' else 2
        min_size = self._read_int_env('AKSHARE_MCP_DB_POOL_MIN', default_min_size, 1)
        max_size = self._read_int_env('AKSHARE_MCP_DB_POOL_MAX', default_max_size, min_size)
        command_timeout = self._read_int_env('DB_CONNECT_TIMEOUT_MS', 10000, 1000) / 1000
        max_inactive_lifetime = self._read_float_env(
            'AKSHARE_MCP_DB_MAX_INACTIVE_LIFETIME_SEC',
            60.0,
            0.0,
        )

        return {
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'password'),
            'database': os.getenv('DB_NAME', 'postgres'),
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': self._read_int_env('DB_PORT', 5432, 1),
            'min_size': min_size,
            'max_size': max_size,
            'command_timeout': command_timeout,
            'max_inactive_connection_lifetime': max_inactive_lifetime,
            'server_settings': {
                'application_name': f'akshare-mcp:{profile}',
            },
        }

    async def initialize(self) -> None:
        """初始化数据库连接池"""
        current_loop = asyncio.get_running_loop()

        # 如果 pool 已存在但绑定的事件循环已变更，需要重建
        if self._initialized and self._bound_loop is not current_loop:
            logger.info("Event loop changed, recreating connection pool")
            self._terminate_stale_pool(current_loop)
            self._reset_pool_state()

        if self._initialized:
            return

        if not ASYNCPG_AVAILABLE:
            raise RuntimeError("asyncpg not installed. Run: pip install asyncpg")

        # 若未设置 DB_PASSWORD/DB_NAME，尝试从 MCP .env 加载 DB_* 配置
        if not os.getenv('DB_PASSWORD') or os.getenv('DB_PASSWORD') == 'password':
            load_mcp_env(override=True, only_prefixes=('DB_',))

        db_config = self._build_db_config()
        profile = self._resolve_startup_profile()

        try:
            self.pool = await asyncpg.create_pool(**db_config)
            self._initialized = True
            self._bound_loop = asyncio.get_running_loop()
            logger.info(
                "Connected to %s:%s/%s (profile=%s, pool=%s-%s)",
                db_config['host'],
                db_config['port'],
                db_config['database'],
                profile,
                db_config['min_size'],
                db_config['max_size'],
            )
            await self._init_tables()
        except Exception as e:
            logger.error("Connection failed: %s", e)
            raise

    async def _init_tables(self) -> None:
        """初始化数据库表结构（委托给 market / strategy 子模块）"""
        from .schema_market import init_market_tables
        from .schema_strategy import init_strategy_tables
        from .schema_vector import init_vector_tables

        async with self.acquire() as conn:
            await self._ensure_pgvector(conn)
            await init_market_tables(conn)
            await init_strategy_tables(conn, self._pgvector_enabled)
            await init_vector_tables(conn, self._pgvector_enabled)

        logger.info("All tables initialized successfully (aligned with Node version)")

    async def _ensure_pgvector(self, conn) -> None:
        """Best-effort 检测并启用 pgvector 扩展。"""
        enabled = False
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            enabled = True
        except Exception as exc:
            logger.warning("pgvector extension unavailable, fallback to JSON/vector-lite path: %s", exc)
            try:
                enabled = bool(await conn.fetchval("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"))
            except Exception:
                enabled = False
        self._pgvector_enabled = bool(enabled)

    def supports_pgvector(self) -> bool:
        return bool(self._pgvector_enabled)

    def get_vector_backend(self) -> str:
        return 'pgvector' if self.supports_pgvector() else 'index'

    async def close(self) -> None:
        """关闭连接池"""
        pool = self.pool
        if pool:
            try:
                await asyncio.wait_for(pool.close(), timeout=2.0)
            except Exception as exc:
                self._force_terminate_pool(pool, reason=str(exc))
            finally:
                self._reset_pool_state()
                await self._flush_close_callbacks()
                logger.info("Connection closed")

    @asynccontextmanager
    async def acquire(self):
        """获取数据库连接（自动处理事件循环变更和连接池重建）

        关键约束：@asynccontextmanager 生成器只能 yield 一次，且不能在 except 块中 yield。
        因此：先 acquire 连接（含重试），再 yield，最后在 finally 中 release。
        """
        lock = self._get_init_lock()

        if not self._initialized or self._bound_loop is not asyncio.get_running_loop():
            async with lock:
                if not self._initialized or self._bound_loop is not asyncio.get_running_loop():
                    await self.initialize()

        _pool_rebuild_triggers = (
            'event loop is closed',
            'pool is closed',
            'not running',
            'connection was closed',
            'connection is closed',
            'connectiondoesnotexist',
            'connection reset',
            'server closed the connection',
            'poolconnectionholder',
        )

        # 先获取连接（包含一次重试），再 yield，避免在 except 中 yield
        conn = None
        pool = self.pool
        try:
            conn = await pool.acquire()
        except Exception as e:
            err_msg = str(e).lower()
            if any(trigger in err_msg for trigger in _pool_rebuild_triggers):
                logger.warning("Pool/connection error detected (%s), rebuilding...", e)
                async with lock:
                    self._reset_pool_state()
                    await self.initialize()
                pool = self.pool
                conn = await pool.acquire()
            else:
                raise

        try:
            yield conn
        finally:
            try:
                await pool.release(conn)
            except Exception as exc:
                logger.warning("Error releasing connection back to pool: %s", exc)
