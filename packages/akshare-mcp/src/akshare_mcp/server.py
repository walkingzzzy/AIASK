"""
AKShare MCP Server v2
提供完整的A股量化分析服务
"""
from __future__ import annotations

import asyncio
import atexit
import os
import logging
import threading
from pathlib import Path

from .env_loader import load_mcp_env

# 禁用 tqdm 进度条输出，避免 AKShare/Tushare 内部进度条写入 stderr 被 MCP 当 [error] 刷屏
os.environ.setdefault("TQDM_DISABLE", "1")

# 在首次使用 get_db() 前加载 .env；若外部环境已注入配置，则不覆盖
load_mcp_env(override=False)

# 在所有导入之前抑制警告，避免干扰 MCP 协议通信
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*Pydantic.*")
warnings.filterwarnings("ignore", message=".*invalid escape sequence.*")

# 抑制 MCP 框架的 INFO 日志写入 stderr，避免被 Cursor 当 [error] 刷屏
for _log_name in ("mcp", "mcp.server", "mcp.server.server", "fastmcp", "uvicorn"):
    logging.getLogger(_log_name).setLevel(logging.WARNING)

from mcp.server.fastmcp import FastMCP

# 分步导入以便 UnicodeDecodeError 时定位到具体子模块
_base_tool_names = (
    "market", "finance", "fund_flow", "macro", "news", "options",
    "technical", "backtest", "portfolio", "valuation", "decision",
    "search", "semantic", "data_warmup", "alerts",
    "vector", "skills", "quant", "sentiment", "market_blocks",
    "basic_data", "data_sync", "managers",
    "factor_profile",
)
_tool_names = _base_tool_names
try:
    from .tools import (
        market, finance, fund_flow, macro, news, options,
        technical, backtest, portfolio, valuation, decision,
        search, semantic, data_warmup, alerts,
        vector, skills, quant, sentiment, market_blocks,
        basic_data, data_sync, managers,
        factor_profile,
    )
except UnicodeDecodeError as e:
    # 定位是哪个子模块触发的解码错误（多为路径或插件内文件编码问题）
    import importlib
    for _n in _tool_names:
        try:
            importlib.import_module(f"akshare_mcp.tools.{_n}")
        except UnicodeDecodeError:
            raise RuntimeError(
                f"UnicodeDecodeError when loading akshare_mcp.tools.{_n}. "
                "Ensure all .py files are UTF-8 and start with: python -X utf8 start_server.py"
            ) from e
    raise


from .services.data_sync import data_sync_service
from .services.factor_scheduler import get_factor_scheduler
from .services.matching_engine import get_matching_engine
from .services.nav_engine import get_nav_engine
from .services.signal_tracker import get_signal_tracker
from .storage import close_db


def _safe_shutdown_data_sync() -> None:
    """进程退出时尽力 flush/关闭数据同步后台任务。"""
    try:
        asyncio.run(data_sync_service.shutdown())
    except RuntimeError:
        # 若解释器退出阶段事件循环不可用，忽略并记录
        logging.getLogger(__name__).warning("[Server] skip data_sync shutdown: event loop unavailable")
    except Exception as e:
        logging.getLogger(__name__).warning(
            "[Server] data_sync shutdown failed", extra={"error": str(e)}
        )


atexit.register(_safe_shutdown_data_sync)


def _run_async_task_in_daemon_thread(coro_factory, name: str) -> threading.Thread:
    """Run an async task from the synchronous server bootstrap path."""
    logger = logging.getLogger(__name__)

    def _runner() -> None:
        try:
            asyncio.run(coro_factory())
        except Exception as e:  # pragma: no cover - defensive logging for background thread
            logger.warning("[Server] background task %s failed: %s", name, e, exc_info=True)

    thread = threading.Thread(target=_runner, name=name, daemon=True)
    thread.start()
    return thread


def _start_startup_validator_background() -> threading.Thread:
    """Schedule StartupValidator without depending on a pre-existing event loop."""
    from .services.startup_validator import get_startup_validator

    validator = get_startup_validator()
    return _run_async_task_in_daemon_thread(validator.run_async, "startup-validator")


def _safe_shutdown_db() -> None:
    """进程退出时关闭数据库连接池。"""
    try:
        asyncio.run(close_db())
    except RuntimeError:
        logging.getLogger(__name__).warning("[Server] skip db shutdown: event loop unavailable")
    except Exception as e:
        logging.getLogger(__name__).warning(
            "[Server] db shutdown failed", extra={"error": str(e)}
        )


atexit.register(_safe_shutdown_db)


# ===== FastMCP app =====

mcp = FastMCP("AKShare Stock Data Server v2")

market.register(mcp)
finance.register(mcp)
fund_flow.register(mcp)
macro.register(mcp)
news.register(mcp)
options.register(mcp)
technical.register(mcp)
backtest.register(mcp)
portfolio.register(mcp)
valuation.register(mcp)
decision.register(mcp)
search.register(mcp)
semantic.register(mcp)
data_warmup.register(mcp)
alerts.register(mcp)
managers.register(mcp)  # Phase 5: 统一注册，消除重复
vector.register(mcp)
skills.register(mcp)
quant.register(mcp)
sentiment.register(mcp)

# 注册因子画像工具 (Phase 3)
factor_profile.register(mcp)

# 注册基础数据工具 (Phase 3)
basic_data.register(mcp)

# 注册数据同步工具 (Phase 4)
data_sync.register(mcp)

# 注册市场板块工具
@mcp.tool()
async def get_market_blocks(block_type: str = "industry", limit: int | None = None):
    """获取市场板块列表

    Args:
        block_type (str, optional): 板块类型，可选 "industry"(行业) / "concept"(概念) / "region"(地域)，默认 "industry"
        limit (int | None, optional): 返回数量上限，None 表示不限制

    Returns:
        dict: {"success": bool, "data": {"blocks": [{"code": str, "name": str, ...}]}, "error": str|None}

    Errors:
        - block_type 不在枚举范围内时返回空列表
        - 数据源不可用时返回 success=false

    Examples:
        # 获取行业板块列表
        get_market_blocks(block_type="industry")
        # 获取概念板块（限制返回10个）
        get_market_blocks(block_type="concept", limit=10)
    """
    return await market_blocks.get_market_blocks(block_type=block_type, limit=limit)


@mcp.tool()
async def get_block_stocks(block_code: str):
    """获取指定板块的成分股列表

    Args:
        block_code (str, required): 板块代码，来自 get_market_blocks 返回的 code 字段

    Returns:
        dict: {"success": bool, "data": {"stocks": [{"code": str, "name": str, ...}]}, "error": str|None}

    Errors:
        - block_code 无效时返回空列表

    Examples:
        # 获取指定板块的成分股
        get_block_stocks(block_code="BK0477")
    """
    return await market_blocks.get_block_stocks(block_code=block_code)


def _as_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_startup_profile() -> str:
    raw = str(os.getenv("AKSHARE_MCP_STARTUP_PROFILE", "full")).strip().lower()
    if raw in {"tool-only", "tool_only", "worker", "lite"}:
        return "tool-only"
    return "full"


def _enforce_http_security_baseline() -> None:
    """
    Enforce minimal security checks when running MCP over HTTP-like transports.

    For stdio transport this function only logs hints and never blocks startup.
    """
    transport = str(os.getenv("MCP_TRANSPORT", "stdio")).strip().lower()
    host = str(os.getenv("MCP_HOST", "127.0.0.1")).strip()
    allowed_origins = str(os.getenv("MCP_ALLOWED_ORIGINS", "")).strip()
    auth_mode = str(os.getenv("MCP_AUTH_MODE", "")).strip().lower()
    token_passthrough = _as_bool(os.getenv("MCP_ALLOW_TOKEN_PASSTHROUGH"))

    http_transports = {"http", "streamable-http", "sse"}
    if transport not in http_transports:
        logging.getLogger(__name__).info(
            "[Security] MCP_TRANSPORT=%s, skip HTTP baseline enforcement", transport
        )
        return

    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(
            "Insecure MCP_HOST for HTTP transport. Use 127.0.0.1/localhost/::1 only."
        )

    if not allowed_origins:
        raise RuntimeError(
            "MCP_ALLOWED_ORIGINS is required for HTTP transport (Origin validation)."
        )

    if auth_mode in {"", "none"}:
        raise RuntimeError(
            "MCP_AUTH_MODE must be configured for HTTP transport (e.g. bearer/api-key)."
        )

    if token_passthrough:
        raise RuntimeError(
            "MCP_ALLOW_TOKEN_PASSTHROUGH=true is forbidden by security baseline."
        )


def main() -> None:
    """Start MCP server."""
    _enforce_http_security_baseline()
    startup_profile = _resolve_startup_profile()
    logger = logging.getLogger(__name__)
    logger.info("[Server] startup profile=%s", startup_profile)

    if startup_profile == "tool-only":
        logger.info("[Server] tool-only profile active, background schedulers and startup validators are disabled")
    else:
        # Start factor scheduler if enabled (default: enabled)
        if _as_bool(os.getenv("FACTOR_SCHEDULER_ENABLED", "true")):
            scheduler = get_factor_scheduler()
            scheduler.start()
            logger.info("[Server] FactorScheduler started")

        # Start matching engine for paper trading
        if _as_bool(os.getenv("MATCHING_ENGINE_ENABLED", "true")):
            engine = get_matching_engine()
            engine.start()
            logger.info("[Server] MatchingEngine started")

        # Start NAV engine for daily account valuation
        if _as_bool(os.getenv("NAV_ENGINE_ENABLED", "true")):
            nav = get_nav_engine()
            nav.start()
            logger.info("[Server] NavEngine started")

        # Start signal tracker for forward signal generation & verification
        if _as_bool(os.getenv("SIGNAL_TRACKER_ENABLED", "true")):
            tracker = get_signal_tracker()
            tracker.start()
            logger.info("[Server] SignalTracker started")

        # Start strategy factory for daily auto-generation & elimination
        if _as_bool(os.getenv("STRATEGY_FACTORY_ENABLED", "true")):
            from strategy_factory import get_strategy_factory_scheduler
            factory = get_strategy_factory_scheduler()
            factory.start()
            logger.info("[Server] StrategyFactory started")

        # Run startup validation (DB connectivity, schema, data freshness, coverage)
        if _as_bool(os.getenv("STARTUP_VALIDATION_ENABLED", "true")):
            _start_startup_validator_background()
            logger.info("[Server] StartupValidator scheduled")

        # Start data sync scheduler for automatic DB sync on startup & daily after market close
        if _as_bool(os.getenv("DATA_SYNC_SCHEDULER_ENABLED", "true")):
            from .services.data_sync_scheduler import get_data_sync_scheduler
            sync_scheduler = get_data_sync_scheduler()
            sync_scheduler.start()
            logger.info("[Server] DataSyncScheduler started")

    mcp.run()


if __name__ == "__main__":
    main()
