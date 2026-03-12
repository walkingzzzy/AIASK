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
        self._bound_loop: Optional[asyncio.AbstractEventLoop] = None
        self._pgvector_enabled = False

    def _get_init_lock(self) -> asyncio.Lock:
        """懒加载初始化锁，确保在当前事件循环中创建"""
        loop = asyncio.get_running_loop()
        if self._init_lock is None or self._bound_loop is not loop:
            self._init_lock = asyncio.Lock()
        return self._init_lock

    def _reset_pool_state(self) -> None:
        """重置连接池状态。"""
        self.pool = None
        self._initialized = False
        self._bound_loop = None
        self._init_lock = None

    def _terminate_stale_pool(self, current_loop: asyncio.AbstractEventLoop) -> None:
        """事件循环切换时，尽力终止旧连接池，避免直接丢引用。"""
        old_pool = self.pool
        old_loop = self._bound_loop
        if old_pool is None or old_loop is current_loop:
            return

        terminate = getattr(old_pool, 'terminate', None)
        if callable(terminate):
            try:
                terminate()
                logger.info("Terminated stale connection pool after event loop change")
            except Exception as exc:
                logger.warning("Failed to terminate stale connection pool: %s", exc)

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

        db_config = {
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'password'),
            'database': os.getenv('DB_NAME', 'postgres'),
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', '5432')),
            'min_size': 10,
            'max_size': 20,
            'command_timeout': int(os.getenv('DB_CONNECT_TIMEOUT_MS', '10000')) / 1000,
        }

        try:
            self.pool = await asyncpg.create_pool(**db_config)
            self._initialized = True
            self._bound_loop = asyncio.get_running_loop()
            logger.info("Connected to %s:%s/%s", db_config['host'], db_config['port'], db_config['database'])
            await self._init_tables()
        except Exception as e:
            logger.error("Connection failed: %s", e)
            raise

    async def _init_tables(self) -> None:
        """初始化数据库表结构（委托给 market / strategy 子模块）"""
        from .schema_market import init_market_tables
        from .schema_strategy import init_strategy_tables

        async with self.acquire() as conn:
            await self._ensure_pgvector(conn)
            await init_market_tables(conn)
            await init_strategy_tables(conn, self._pgvector_enabled)

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
                await pool.close()
            except Exception:
                terminate = getattr(pool, 'terminate', None)
                if callable(terminate):
                    try:
                        terminate()
                    except Exception:
                        pass
            self._reset_pool_state()
            logger.info("Connection closed")

    @asynccontextmanager
    async def acquire(self):
        """获取数据库连接（自动处理事件循环变更和连接池重建）"""
        lock = self._get_init_lock()

        if not self._initialized or self._bound_loop is not asyncio.get_running_loop():
            async with lock:
                if not self._initialized or self._bound_loop is not asyncio.get_running_loop():
                    await self.initialize()

        try:
            async with self.pool.acquire() as conn:
                yield conn
        except Exception as e:
            err_msg = str(e).lower()
            if 'event loop is closed' in err_msg or 'pool is closed' in err_msg or 'not running' in err_msg:
                logger.warning("Pool error detected (%s), rebuilding...", e)
                async with lock:
                    self._reset_pool_state()
                    await self.initialize()
                async with self.pool.acquire() as conn:
                    yield conn
            else:
                raise
