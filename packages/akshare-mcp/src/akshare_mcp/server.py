"""
AKShare MCP Server v2
提供完整的A股量化分析服务
"""
from __future__ import annotations

import asyncio
import atexit
import inspect
import importlib as _importlib
import logging
import os
import tempfile
import threading
from pathlib import Path

import anyio

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback path
    fcntl = None

from .env_loader import load_mcp_env
from .auth import build_http_security_components, wrap_http_auth_app
from .resources import register as register_resources
from .prompts import register as register_prompts

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

# --- Core lightweight tools: import eagerly (essential for all profiles) ---
_core_tool_names = (
    "market", "finance", "fund_flow", "macro", "news", "options",
    "technical", "backtest", "portfolio", "valuation", "decision",
    "search", "semantic", "data_warmup", "alerts",
    "market_blocks", "basic_data", "managers", "research",
)
try:
    from .tools import (
        market, finance, fund_flow, macro, news, options,
        technical, backtest, portfolio, valuation, decision,
        search, semantic, data_warmup, alerts,
        market_blocks, basic_data, managers, research,
    )
except UnicodeDecodeError as e:
    for _n in _core_tool_names:
        try:
            _importlib.import_module(f"akshare_mcp.tools.{_n}")
        except UnicodeDecodeError:
            raise RuntimeError(
                f"UnicodeDecodeError when loading akshare_mcp.tools.{_n}. "
                "Ensure all .py files are UTF-8 and start with: python -X utf8 start_server.py"
            ) from e
    raise

# --- Heavy tool modules: deferred import via importlib ---
_heavy_tool_names = ("vector", "skills", "quant", "sentiment", "data_sync", "factor_profile")
_heavy_modules: dict[str, object] = {}
_tool_only_manager_excludes = (
    "data_sync_manager",
    "quant_manager",
    "sentiment_manager",
    "vector_search_manager",
)


def _current_startup_profile() -> str:
    raw = str(os.getenv("AKSHARE_MCP_STARTUP_PROFILE", "full")).strip().lower()
    if raw == "worker":
        return "worker"
    if raw in {"tool-only", "tool_only", "lite"}:
        return "tool-only"
    return "full"


def _load_heavy_module(name: str) -> object:
    """Lazily import a heavy tool module and cache it."""
    if name not in _heavy_modules:
        try:
            _heavy_modules[name] = _importlib.import_module(f".tools.{name}", package="akshare_mcp")
        except UnicodeDecodeError as e:
            raise RuntimeError(
                f"UnicodeDecodeError when loading akshare_mcp.tools.{name}. "
                "Ensure all .py files are UTF-8 and start with: python -X utf8 start_server.py"
            ) from e
    return _heavy_modules[name]


def get_factor_scheduler():
    from .services.factor_scheduler import get_factor_scheduler as _get_factor_scheduler

    return _get_factor_scheduler()


def get_matching_engine():
    from .services.matching_engine import get_matching_engine as _get_matching_engine

    return _get_matching_engine()


def get_nav_engine():
    from .services.nav_engine import get_nav_engine as _get_nav_engine

    return _get_nav_engine()


def get_signal_tracker():
    from .services.signal_tracker import get_signal_tracker as _get_signal_tracker

    return _get_signal_tracker()

_started_background_services: list[tuple[str, object]] = []
_shutdown_lock = threading.Lock()
_shutdown_completed = False
_background_services_lock_handle = None


def _remember_started_service(name: str, service: object) -> object:
    _started_background_services.append((name, service))
    return service


async def _stop_started_background_services() -> None:
    logger = logging.getLogger(__name__)
    while _started_background_services:
        name, service = _started_background_services.pop()
        shutdown = getattr(service, "shutdown", None)
        stop = getattr(service, "stop", None)
        closer = shutdown if callable(shutdown) else stop
        if not callable(closer):
            continue
        try:
            result = closer()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            logger.warning("[Server] stop %s failed: %s", name, exc)


class _AsyncTaskServiceHandle:
    """可纳入统一 shutdown 路径的后台 task 包装器。"""

    def __init__(self, name: str, task: "asyncio.Task[object]"):
        self._name = name
        self._task = task

    async def shutdown(self) -> None:
        if self._task.done():
            try:
                await self._task
            except asyncio.CancelledError:
                return
            except Exception as exc:  # pragma: no cover - defensive logging
                logging.getLogger(__name__).warning("[Server] background task %s failed: %s", self._name, exc)
            return

        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            return
        except Exception as exc:  # pragma: no cover - defensive logging
            logging.getLogger(__name__).warning("[Server] background task %s failed during shutdown: %s", self._name, exc)


def _start_startup_validator_background() -> _AsyncTaskServiceHandle:
    """在当前事件循环内调度 StartupValidator，并纳入统一 shutdown。"""
    from .services.startup_validator import get_startup_validator

    validator = get_startup_validator()
    task = asyncio.create_task(validator.run_async(), name="startup-validator")
    return _AsyncTaskServiceHandle("startup-validator", task)


def _background_services_lock_path() -> Path:
    raw = str(os.getenv("AKSHARE_MCP_BACKGROUND_SERVICES_LOCK_PATH", "")).strip()
    if raw:
        return Path(raw)
    return Path(tempfile.gettempdir()) / "akshare-mcp-background-services.lock"


def _acquire_background_services_leader() -> bool:
    """Ensure only one local MCP process starts autonomous background services."""
    global _background_services_lock_handle

    logger = logging.getLogger(__name__)
    handle = None
    if _background_services_lock_handle is not None:
        return True
    if fcntl is None:  # pragma: no cover - platform-specific safeguard
        logger.warning("[Server] background leader lock unavailable on this platform; proceeding without single-leader guard")
        return True

    lock_path = _background_services_lock_path()
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a+", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        _background_services_lock_handle = handle
        logger.info("[Server] acquired background services leader lock: %s", lock_path)
        return True
    except BlockingIOError:
        try:
            handle.close()
        except Exception:
            pass
        logger.info("[Server] background services leader lock already held: %s", lock_path)
        return False
    except Exception as exc:
        try:
            handle.close()
        except Exception:
            pass
        logger.warning("[Server] background services leader lock failed: %s", exc)
        return False


def _release_background_services_leader() -> None:
    global _background_services_lock_handle

    handle = _background_services_lock_handle
    if handle is None:
        return
    _background_services_lock_handle = None
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except Exception as exc:  # pragma: no cover - defensive cleanup logging
        logging.getLogger(__name__).warning("[Server] background leader unlock failed: %s", exc)
    finally:
        try:
            handle.close()
        except Exception:
            pass


async def _shutdown_services_async() -> None:
    """按依赖顺序关闭后台服务，避免先关 DB 导致后续关闭失败。"""
    global _shutdown_completed
    with _shutdown_lock:
        if _shutdown_completed:
            return
        _shutdown_completed = True
    logger = logging.getLogger(__name__)
    from .services import close_shared_runtime_clients
    from .services.data_sync import data_sync_service
    from .storage import close_db

    await _stop_started_background_services()
    # 给取消后的任务一次排空连接释放/close 回调的机会，避免残留 transport 警告。
    await asyncio.sleep(0)
    await asyncio.sleep(0.05)
    try:
        await data_sync_service.shutdown()
    except Exception as e:
        logger.warning(
            "[Server] data_sync shutdown failed", extra={"error": str(e)}
        )
    try:
        await close_shared_runtime_clients()
    except Exception as e:
        logger.warning(
            "[Server] shared client shutdown failed", extra={"error": str(e)}
        )
    try:
        await close_db()
    except Exception as e:
        logger.warning(
            "[Server] db shutdown failed", extra={"error": str(e)}
        )
    _release_background_services_leader()


def _safe_shutdown_services() -> None:
    try:
        asyncio.run(_shutdown_services_async())
    except RuntimeError:
        logging.getLogger(__name__).warning("[Server] skip service shutdown: event loop unavailable")
    except Exception as e:
        logging.getLogger(__name__).warning(
            "[Server] service shutdown failed", extra={"error": str(e)}
        )


atexit.register(_safe_shutdown_services)


# ===== FastMCP app =====
# T04: Configure host/port for HTTP transports from env vars and wire
# FastMCP auth/token_verifier/transport_security for request-time enforcement.

_mcp_host = str(os.getenv("MCP_HOST", "127.0.0.1")).strip() or "127.0.0.1"
_mcp_port = int(os.getenv("MCP_PORT", "8000"))
_mcp_auth, _mcp_token_verifier, _mcp_transport_security, _mcp_auth_mode = build_http_security_components(
    _mcp_host,
    _mcp_port,
)

mcp = FastMCP(
    "AKShare Stock Data Server v2",
    host=_mcp_host,
    port=_mcp_port,
    auth=_mcp_auth,
    token_verifier=_mcp_token_verifier,
    transport_security=_mcp_transport_security,
)

def _register_market_block_tools(app: FastMCP) -> None:
    @app.tool()
    async def get_market_blocks(block_type: str = "industry", limit: int | None = None):
        """获取市场板块列表。"""
        return await market_blocks.get_market_blocks(block_type=block_type, limit=limit)

    @app.tool()
    async def get_block_stocks(block_code: str):
        """获取指定板块的成分股列表。"""
        return await market_blocks.get_block_stocks(block_code=block_code)


def _register_core_tools(app: FastMCP, *, startup_profile: str) -> None:
    market.register(app)
    finance.register(app)
    fund_flow.register(app)
    macro.register(app)
    news.register(app)
    options.register(app)
    technical.register(app)
    backtest.register(app)
    portfolio.register(app)
    valuation.register(app)
    decision.register(app)
    search.register(app)
    semantic.register(app)
    research.register(app)
    data_warmup.register(app)
    alerts.register(app)
    basic_data.register(app)
    managers.register(
        app,
        exclude=_tool_only_manager_excludes if startup_profile == "tool-only" else None,
    )
    register_resources(app)
    register_prompts(app)
    _register_market_block_tools(app)


def _register_full_only_tools(app: FastMCP) -> None:
    for module_name in _heavy_tool_names:
        _load_heavy_module(module_name).register(app)


def _register_runtime_surface(app: FastMCP, *, startup_profile: str) -> None:
    _register_core_tools(app, startup_profile=startup_profile)
    if startup_profile in {"full", "worker"}:
        _register_full_only_tools(app)


_register_runtime_surface(mcp, startup_profile=_current_startup_profile())


def _as_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_startup_profile() -> str:
    return _current_startup_profile()


def _resolve_transport() -> tuple[str, str | None]:
    raw = str(os.getenv("MCP_TRANSPORT", "stdio")).strip().lower()
    mount_path = str(os.getenv("MCP_MOUNT_PATH", "")).strip() or None
    if raw in {"", "stdio"}:
        return "stdio", None
    if raw == "sse":
        return "sse", mount_path
    if raw in {"http", "streamable-http", "streamable_http"}:
        return "streamable-http", None
    raise RuntimeError(f"Unsupported MCP transport: {raw}")


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

    if _mcp_auth is None or _mcp_token_verifier is None:
        raise RuntimeError(
            "HTTP transport requires FastMCP auth/token_verifier to be configured with static tokens."
        )

    if token_passthrough:
        raise RuntimeError(
            "MCP_ALLOW_TOKEN_PASSTHROUGH=true is forbidden by security baseline."
        )


def _build_http_asgi_app(transport: str, mount_path: str | None):
    if transport == "sse":
        app = mcp.sse_app(mount_path)
    elif transport == "streamable-http":
        app = mcp.streamable_http_app()
    else:  # pragma: no cover - defensive guard
        raise RuntimeError(f"Unsupported HTTP transport: {transport}")
    return wrap_http_auth_app(app, auth_mode=_mcp_auth_mode)


async def _run_mcp_transport_async(transport: str, mount_path: str | None) -> None:
    if transport == "stdio":
        await mcp.run_stdio_async()
        return
    if transport == "sse":
        import uvicorn

        app = _build_http_asgi_app(transport, mount_path)
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=mcp.settings.host,
                port=mcp.settings.port,
                log_level=mcp.settings.log_level.lower(),
            )
        )
        await server.serve()
        return
    if transport == "streamable-http":
        import uvicorn

        app = _build_http_asgi_app(transport, mount_path)
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=mcp.settings.host,
                port=mcp.settings.port,
                log_level=mcp.settings.log_level.lower(),
            )
        )
        await server.serve()
        return
    raise RuntimeError(f"Unsupported MCP transport: {transport}")


async def _main_async(transport: str, mount_path: str | None) -> None:
    global _shutdown_completed
    with _shutdown_lock:
        _shutdown_completed = False
    startup_profile = _resolve_startup_profile()
    logger = logging.getLogger(__name__)
    logger.info("[Server] startup profile=%s transport=%s", startup_profile, transport)

    if startup_profile == "tool-only":
        logger.info("[Server] tool-only profile active, background schedulers and startup validators are disabled")
    elif startup_profile == "worker":
        logger.info("[Server] worker profile active, heavy tools enabled but autonomous background services remain disabled")
    elif not _acquire_background_services_leader():
        logger.info("[Server] full profile active, but this process is not the background-services leader; autonomous services stay disabled")
    else:
        # Start factor scheduler if enabled (default: enabled)
        if _as_bool(os.getenv("FACTOR_SCHEDULER_ENABLED", "true")):
            scheduler = _remember_started_service("FactorScheduler", get_factor_scheduler())
            scheduler.start()
            logger.info("[Server] FactorScheduler started")

        # Start matching engine for paper trading
        if _as_bool(os.getenv("MATCHING_ENGINE_ENABLED", "true")):
            engine = _remember_started_service("MatchingEngine", get_matching_engine())
            engine.start()
            logger.info("[Server] MatchingEngine started")

        # Start NAV engine for daily account valuation
        if _as_bool(os.getenv("NAV_ENGINE_ENABLED", "true")):
            nav = _remember_started_service("NavEngine", get_nav_engine())
            nav.start()
            logger.info("[Server] NavEngine started")

        # Start signal tracker for forward signal generation & verification
        if _as_bool(os.getenv("SIGNAL_TRACKER_ENABLED", "true")):
            tracker = _remember_started_service("SignalTracker", get_signal_tracker())
            tracker.start()
            logger.info("[Server] SignalTracker started")

        # Start strategy factory for daily auto-generation & elimination
        if _as_bool(os.getenv("STRATEGY_FACTORY_ENABLED", "true")):
            from strategy_factory import get_strategy_factory_scheduler
            factory = _remember_started_service("StrategyFactory", get_strategy_factory_scheduler())
            factory.start()
            logger.info("[Server] StrategyFactory started")

        # Run startup validation (DB connectivity, schema, data freshness, coverage)
        if _as_bool(os.getenv("STARTUP_VALIDATION_ENABLED", "true")):
            _remember_started_service("StartupValidator", _start_startup_validator_background())
            logger.info("[Server] StartupValidator scheduled")

        # Start data sync scheduler for automatic DB sync on startup & daily after market close
        if _as_bool(os.getenv("DATA_SYNC_SCHEDULER_ENABLED", "true")):
            from .services.data_sync_scheduler import get_data_sync_scheduler
            sync_scheduler = _remember_started_service("DataSyncScheduler", get_data_sync_scheduler())
            sync_scheduler.start()
            logger.info("[Server] DataSyncScheduler started")

    try:
        await _run_mcp_transport_async(transport, mount_path)
    finally:
        await _shutdown_services_async()


def main() -> None:
    """Start MCP server."""
    _enforce_http_security_baseline()
    transport, mount_path = _resolve_transport()
    anyio.run(_main_async, transport, mount_path)


if __name__ == "__main__":
    main()
