#!/usr/bin/env python3
"""策略工厂持续运行脚本。

启动后持续运行，按调度策略自动执行策略生产周期，
直到收到 SIGINT (Ctrl+C) 或 SIGTERM 信号才停止。

用法：
    python run_strategy_factory.py              # 默认模式
    python run_strategy_factory.py --once       # 只跑一次然后退出
    python run_strategy_factory.py --interval 300  # 每 5 分钟跑一次

环境变量（从 .env 自动加载）：
    STRATEGY_LLM_ENABLED=1
    STRATEGY_LLM_BASE_URL=https://ai.centos.hk/v1
    STRATEGY_LLM_API_KEY=sk-xxx
    STRATEGY_LLM_MODEL=claude-sonnet-4-6
    AKSHARE_MCP_SQLITE_PATH=./data/db/akshare_mcp.sqlite3
"""

from __future__ import annotations

import argparse
import asyncio
import io
import inspect
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def _configure_stdio_utf8() -> None:
    """Force stdout/stderr to UTF-8 so Chinese + box-drawing chars render in
    Windows PowerShell / cmd (default codepage 936)."""
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleCP(65001)
            kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
            continue
        except Exception:
            pass
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            try:
                setattr(
                    sys,
                    stream_name,
                    io.TextIOWrapper(
                        buffer,
                        encoding="utf-8",
                        errors="replace",
                        line_buffering=True,
                    ),
                )
            except Exception:
                continue


_configure_stdio_utf8()

# 确保项目路径
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _bootstrap_local_package_paths() -> None:
    for package_src in (
        PROJECT_ROOT / "packages" / "aiask-quant-core" / "src",
        PROJECT_ROOT / "packages" / "strategy-factory" / "src",
        PROJECT_ROOT / "packages" / "akshare-mcp" / "src",
    ):
        path = str(package_src)
        if package_src.exists() and path not in sys.path:
            sys.path.insert(0, path)


_bootstrap_local_package_paths()


def _load_strategy_factory_runtime_kwargs() -> dict:
    try:
        from akshare_mcp.adapters.strategy_factory_runtime import (
            build_strategy_factory_scheduler_kwargs,
        )
    except ModuleNotFoundError as exc:
        if not str(getattr(exc, "name", "") or "").startswith("akshare_mcp"):
            raise
        akshare_src = PROJECT_ROOT / "packages" / "akshare-mcp" / "src"
        if not akshare_src.exists():
            raise
        path = str(akshare_src)
        inserted = path not in sys.path
        if inserted:
            sys.path.insert(0, path)
        try:
            from akshare_mcp.adapters.strategy_factory_runtime import (
                build_strategy_factory_scheduler_kwargs,
            )
        finally:
            if inserted:
                try:
                    sys.path.remove(path)
                except ValueError:
                    pass
    return build_strategy_factory_scheduler_kwargs()

# 加载 .env
def _load_dotenv():
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            os.environ.setdefault(key, value)
    try:
        from strategy_factory.infrastructure.env_loader import load_strategy_llm_env

        load_strategy_llm_env(explicit_path=str(env_path))
    except Exception:
        pass

_load_dotenv()

# 确保关键配置
os.environ.setdefault("STRATEGY_FACTORY_READINESS_HARD_BLOCK", "0")
os.environ.setdefault("STRATEGY_FACTORY_FACTOR_AUTO_REFRESH", "0")

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("strategy_factory_runner")


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    try:
        value = int(os.getenv(name, str(default)) or default)
    except Exception:
        value = int(default)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _market_timezone() -> ZoneInfo:
    name = os.getenv("STRATEGY_FACTORY_TIMEZONE", "Asia/Shanghai").strip() or "Asia/Shanghai"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def _is_market_hours_now(now: datetime | None = None) -> bool:
    current = now or datetime.now(_market_timezone())
    if current.tzinfo is None:
        current = current.replace(tzinfo=_market_timezone())
    else:
        current = current.astimezone(_market_timezone())
    if current.weekday() >= 5:
        return False
    minute_of_day = current.hour * 60 + current.minute
    return (9 * 60 + 30 <= minute_of_day <= 11 * 60 + 30) or (
        13 * 60 <= minute_of_day <= 15 * 60
    )


def _resolve_runner_interval_sec(
    explicit_interval: int | None = None,
    *,
    now: datetime | None = None,
) -> int:
    if explicit_interval is not None:
        interval = int(explicit_interval)
        if interval <= 0:
            raise ValueError("--interval must be a positive number of seconds")
        return interval

    current = now or datetime.now(_market_timezone())
    if current.tzinfo is None:
        current = current.replace(tzinfo=_market_timezone())
    else:
        current = current.astimezone(_market_timezone())
    if current.weekday() >= 5:
        return _env_int(
            "STRATEGY_FACTORY_NON_TRADING_DAY_INTERVAL_SEC",
            7200,
            minimum=300,
            maximum=86400,
        )
    if _is_market_hours_now(current):
        return _env_int(
            "STRATEGY_FACTORY_MARKET_HOURS_INTERVAL_SEC",
            720,
            minimum=60,
            maximum=7200,
        )
    return _env_int(
        "STRATEGY_FACTORY_OFF_HOURS_INTERVAL_SEC",
        3600,
        minimum=300,
        maximum=86400,
    )


def _normalize_cycle_result(result: dict, *, elapsed_seconds: float) -> dict:
    """Normalize scheduler-native and manager-envelope results for the runner."""
    if not isinstance(result, dict):
        return {
            "success": False,
            "error": f"unexpected_result_type:{type(result).__name__}",
            "data": {
                "status": "failed",
                "elapsed_seconds": elapsed_seconds,
                "raw_result": result,
            },
        }

    if "success" in result:
        normalized = dict(result)
        data = normalized.get("data")
        if not isinstance(data, dict):
            data = {}
        if "elapsed_seconds" not in data:
            data["elapsed_seconds"] = elapsed_seconds
        status = str(data.get("status") or normalized.get("status") or "").strip().lower()
        if status and not data.get("status"):
            data["status"] = status
        if status == "partial":
            data["degraded"] = True
        if bool(normalized.get("success")):
            if not status:
                status = "success"
                data["status"] = status
            elif status == "partial":
                normalized["success"] = False
                normalized.setdefault(
                    "error",
                    data.get("error") or data.get("reason") or "status=partial",
                )
            elif status == "skipped":
                normalized["success"] = False
                normalized.setdefault(
                    "error",
                    data.get("reason") or data.get("skip_reason") or "status=skipped",
                )
            elif status != "success":
                normalized["success"] = False
                normalized.setdefault("error", data.get("error") or f"status={status}")
        normalized["data"] = data
        if not bool(normalized.get("success")):
            normalized.setdefault(
                "error",
                data.get("error")
                or result.get("error")
                or data.get("reason")
                or data.get("skip_reason")
                or result.get("reason")
                or result.get("skip_reason")
                or "unknown",
            )
        return normalized

    data = dict(result)
    status = str(data.get("status") or "").strip().lower()
    if "elapsed_seconds" not in data:
        data["elapsed_seconds"] = elapsed_seconds
    if status == "success":
        return {"success": True, "data": data}
    if status == "partial":
        data["degraded"] = True
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    error = (
        data.get("error")
        or summary.get("error")
        or data.get("reason")
        or data.get("skip_reason")
        or f"status={status or 'unknown'}"
    )
    return {"success": False, "error": error, "data": data}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _clamp_dispatch_concurrency(value: int | None, *, default: int = 1) -> int:
    try:
        resolved = int(default if value is None else value)
    except Exception:
        resolved = int(default)
    return max(1, min(resolved, 16))


def _resolve_dispatch_concurrency(value: int | None = None) -> int:
    if value is not None:
        return _clamp_dispatch_concurrency(value)
    raw = str(os.getenv("STRATEGY_FACTORY_MAX_CONCURRENT_DISPATCHES", "") or "").strip()
    if raw:
        try:
            return _clamp_dispatch_concurrency(None, default=int(raw))
        except Exception:
            return 1
    return 1


def _normalize_dispatch_stock_code(value) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    if "." in token:
        prefix, _, suffix = token.partition(".")
        if suffix.upper() in {"SH", "SZ", "BJ"} and prefix:
            token = prefix
    return token


def _resolve_dispatch_default_universe_limit(
    value: int | None,
    *,
    concurrency_limit: int,
    shard_size: int | None,
) -> int:
    if value is not None:
        return max(1, min(int(value), 10000))
    raw = str(os.getenv("STRATEGY_FACTORY_DISPATCH_DEFAULT_UNIVERSE_LIMIT", "") or "").strip()
    if raw:
        try:
            return max(1, min(int(raw), 10000))
        except Exception:
            pass
    per_dispatch = max(1, int(shard_size or 1))
    return max(1, min(max(1, int(concurrency_limit or 1)) * per_dispatch, 10000))


def _split_dispatch_target_codes(
    target_codes: list[str] | None,
    *,
    concurrency_limit: int,
    shard_size: int | None = None,
) -> list[list[str]]:
    codes = [str(code).strip() for code in list(target_codes or []) if str(code).strip()]
    if not codes:
        return [[]]
    if shard_size is not None:
        size = max(1, int(shard_size))
    else:
        limit = max(1, int(concurrency_limit or 1))
        size = max(1, (len(codes) + limit - 1) // limit)
    return [codes[index:index + size] for index in range(0, len(codes), size)]


def _configure_dispatch_launch_options(
    *,
    dispatch_run_mode: bool,
    parallel_full_cycles: bool,
    dispatch_concurrency: int | None,
) -> int:
    concurrency_limit = _resolve_dispatch_concurrency(dispatch_concurrency)
    if dispatch_run_mode:
        os.environ["STRATEGY_FACTORY_INLINE_EXECUTION_ENABLED"] = "1"
    if parallel_full_cycles or concurrency_limit > 1:
        os.environ["STRATEGY_FACTORY_ALLOW_PARALLEL_FULL_CYCLES"] = "1"
    if dispatch_concurrency is not None or dispatch_run_mode:
        os.environ["STRATEGY_FACTORY_MAX_CONCURRENT_DISPATCHES"] = str(concurrency_limit)
    return concurrency_limit


class StrategyFactoryRunner:
    """策略工厂持续运行器。"""

    def __init__(
        self,
        *,
        interval_sec: int | None = None,
        run_once: bool = False,
        target_codes: list[str] | None = None,
        execution_mode: str | None = None,
        dispatch_run_mode: bool = False,
        dispatch_concurrency_limit: int | None = None,
        dispatch_shard_size: int | None = None,
        dispatch_default_universe: bool = False,
        dispatch_default_universe_limit: int | None = None,
    ):
        self.interval_sec = _resolve_runner_interval_sec(interval_sec)
        self.run_once = run_once
        self.target_codes = target_codes
        self.execution_mode = execution_mode
        self.dispatch_run_mode = dispatch_run_mode
        self.dispatch_concurrency_limit = _resolve_dispatch_concurrency(dispatch_concurrency_limit)
        self.dispatch_shard_size = dispatch_shard_size
        self.dispatch_default_universe = bool(dispatch_default_universe)
        self.dispatch_default_universe_limit = dispatch_default_universe_limit
        self._running = True
        self._run_count = 0
        self._success_count = 0
        self._partial_count = 0
        self._skipped_count = 0
        self._failure_count = 0
        self._last_result: dict | None = None
        self._active_dispatch: dict | None = None

    def _setup_signals(self):
        """注册信号处理器。"""
        def _handle_stop(signum, frame):
            sig_name = signal.Signals(signum).name
            logger.info("收到 %s 信号，准备停止...", sig_name)
            self._running = False

        signal.signal(signal.SIGINT, _handle_stop)
        signal.signal(signal.SIGTERM, _handle_stop)

    async def run(self):
        """主运行循环。"""
        self._setup_signals()
        logger.info("=" * 60)
        logger.info("策略工厂启动")
        logger.info("  模式: %s", "单次运行" if self.run_once else f"持续运行 (间隔 {self.interval_sec}s)")
        logger.info("  目标股票: %s", self.target_codes or "默认宇宙")
        logger.info("  LLM: %s (%s)", os.getenv("STRATEGY_LLM_MODEL", "未配置"), os.getenv("STRATEGY_LLM_BASE_URL", ""))
        logger.info("  数据库: %s", os.getenv("AKSHARE_MCP_SQLITE_PATH", "默认"))
        logger.info("=" * 60)

        while self._running:
            cycle_start = time.time()
            self._run_count += 1
            logger.info("─" * 40)
            logger.info("第 %d 轮策略生产周期开始", self._run_count)

            try:
                raw_result = await self._execute_cycle()
                result = _normalize_cycle_result(
                    raw_result,
                    elapsed_seconds=time.time() - cycle_start,
                )
                await self._complete_active_dispatch(result)
                self._last_result = result

                data = result.get("data", {})
                if not isinstance(data, dict):
                    data = {}
                status = str(data.get("status") or "").strip().lower()
                elapsed = data.get("elapsed_seconds", time.time() - cycle_start)

                if result.get("success") and status == "success":
                    self._success_count += 1
                    logger.info(
                        "第 %d 轮完成 ✅ 状态=%s 耗时=%.1fs",
                        self._run_count, status, elapsed,
                    )
                    self._log_stages(data)
                elif status == "partial":
                    self._partial_count += 1
                    logger.warning(
                        "第 %d 轮部分完成 ⚠ 状态=%s 耗时=%.1fs 错误: %s",
                        self._run_count, status, elapsed, result.get("error", "partial"),
                    )
                    self._log_stages(data)
                elif status in ("partial_infra", "partial_llm",
                                "success_no_strategy", "success_no_submission"):
                    # These are "basically success with caveats" — per
                    # run_models.py priority table, they sit above failure
                    # but report quality/infra warnings. Group with partial.
                    self._partial_count += 1
                    flavor = {
                        "partial_infra": "基础设施降级",
                        "partial_llm": "LLM 降级",
                        "success_no_strategy": "成功但未产策略",
                        "success_no_submission": "成功但未提交",
                    }.get(status, status)
                    logger.warning(
                        "第 %d 轮部分完成 ⚠ 状态=%s (%s) 耗时=%.1fs",
                        self._run_count, status, flavor, elapsed,
                    )
                    self._log_stages(data)
                elif status == "skipped":
                    self._skipped_count += 1
                    logger.info(
                        "第 %d 轮跳过 状态=%s 耗时=%.1fs 原因: %s",
                        self._run_count, status, elapsed, result.get("error", "skipped"),
                    )
                else:
                    self._failure_count += 1
                    error = result.get("error", "unknown")
                    logger.warning(
                        "第 %d 轮失败 ❌ 状态=%s 错误: %s",
                        self._run_count, status or "(empty)", error,
                    )

            except asyncio.CancelledError as exc:
                if self._active_dispatch:
                    self._failure_count += 1
                    await self._fail_active_dispatch(exc)
                logger.info("运行被取消")
                break
            except Exception as exc:
                self._failure_count += 1
                await self._fail_active_dispatch(exc)
                logger.error("第 %d 轮异常: %s", self._run_count, exc, exc_info=True)

            # 单次模式直接退出
            if self.run_once:
                break

            # 等待下一轮
            if self._running:
                logger.info(
                    "等待 %d 秒后开始下一轮... (成功=%d 部分=%d 跳过=%d 失败=%d)",
                    self.interval_sec,
                    self._success_count,
                    self._partial_count,
                    self._skipped_count,
                    self._failure_count,
                )
                try:
                    await self._interruptible_sleep(self.interval_sec)
                except asyncio.CancelledError:
                    break

        logger.info("=" * 60)
        logger.info("策略工厂停止")
        logger.info(
            "  总运行: %d 轮, 成功: %d, 部分: %d, 跳过: %d, 失败: %d",
            self._run_count,
            self._success_count,
            self._partial_count,
            self._skipped_count,
            self._failure_count,
        )
        logger.info("=" * 60)

    async def _execute_cycle(self) -> dict:
        """执行一次策略生产周期。"""
        from strategy_factory import get_strategy_factory_scheduler

        runtime_kwargs = _load_strategy_factory_runtime_kwargs()
        scheduler = get_strategy_factory_scheduler(**runtime_kwargs)
        if self.dispatch_run_mode:
            return await self._execute_dispatch_run_batch(scheduler, runtime_kwargs)
        dispatch = await self._claim_queued_dispatch(runtime_kwargs)
        if dispatch:
            dispatch_id = str(dispatch.get("dispatch_id") or "").strip()
            execution_mode = str(dispatch.get("execution_mode") or "").strip() or None
            target_codes = self.target_codes or list((dispatch.get("metadata") or {}).get("target_codes") or [])
            logger.info("执行 Strategy Factory dispatch: %s", dispatch_id)
            return await scheduler.run_once(
                execution_mode=execution_mode,
                dispatch_id=dispatch_id,
                target_codes=target_codes,
            )
        return await scheduler.run_once(target_codes=self.target_codes or [])

    async def _execute_dispatch_run_batch(self, scheduler, runtime_kwargs: dict) -> dict:
        dispatch_run = getattr(scheduler, "dispatch_run", None)
        if not callable(dispatch_run):
            raise RuntimeError("StrategyFactoryScheduler.dispatch_run is unavailable")

        db = None
        db_provider = runtime_kwargs.get("db_provider")
        if callable(db_provider):
            db = db_provider()

        target_codes = list(self.target_codes or [])
        default_universe_codes: list[str] = []
        if not target_codes and self.dispatch_default_universe:
            default_universe_codes = await self._load_dispatch_default_target_codes(db)
            target_codes = list(default_universe_codes)

        batches = _split_dispatch_target_codes(
            target_codes,
            concurrency_limit=self.dispatch_concurrency_limit,
            shard_size=self.dispatch_shard_size,
        )
        accepted: list[dict] = []
        for batch in batches:
            accepted.append(
                await dispatch_run(
                    db=db,
                    execution_mode=self.execution_mode,
                    target_codes=batch,
                )
            )

        task_map = getattr(scheduler, "_dispatch_tasks", {})
        tasks = []
        for item in accepted:
            dispatch_id = str(item.get("dispatch_id") or "").strip()
            task = task_map.get(dispatch_id) if isinstance(task_map, dict) else None
            if task is not None:
                tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks)

        dispatches: list[dict] = []
        get_dispatch_status = getattr(scheduler, "get_dispatch_status", None)
        for item in accepted:
            dispatch_id = str(item.get("dispatch_id") or "").strip()
            row = None
            if dispatch_id and callable(get_dispatch_status):
                if db is not None:
                    row = await get_dispatch_status(dispatch_id, db=db)
                else:
                    row = await get_dispatch_status(dispatch_id)
            dispatches.append(dict(row or item))

        statuses = [str(item.get("status") or "").strip().lower() for item in dispatches]
        if statuses and all(status == "success" for status in statuses):
            status = "success"
        elif any(status == "failed" for status in statuses):
            status = "failed"
        else:
            status = "partial"
        return {
            "status": status,
            "run_id": ",".join(
                str(item.get("run_id") or "").strip()
                for item in dispatches
                if str(item.get("run_id") or "").strip()
            ) or None,
            "summary": {
                "dispatch_run_batch": True,
                "dispatch_ids": [item.get("dispatch_id") for item in dispatches],
                "dispatch_count": len(dispatches),
                "dispatch_concurrency_limit": self.dispatch_concurrency_limit,
                "parallel_full_cycles": _env_flag("STRATEGY_FACTORY_ALLOW_PARALLEL_FULL_CYCLES"),
                "target_code_batches": batches,
                "default_universe_dispatch": bool(default_universe_codes),
                "default_universe_code_count": len(default_universe_codes),
            },
            "dispatches": dispatches,
            "artifact_refs": [],
        }

    async def _load_dispatch_default_target_codes(self, db) -> list[str]:
        if db is None:
            logger.warning("Strategy Factory dispatch default universe requested but db provider is unavailable")
            return []
        list_stock_universe = getattr(db, "list_stock_universe", None)
        if not callable(list_stock_universe):
            logger.warning("Strategy Factory dispatch default universe requested but db.list_stock_universe is unavailable")
            return []
        limit = _resolve_dispatch_default_universe_limit(
            self.dispatch_default_universe_limit,
            concurrency_limit=self.dispatch_concurrency_limit,
            shard_size=self.dispatch_shard_size,
        )
        result = list_stock_universe(limit=limit, offset=0)
        if inspect.isawaitable(result):
            result = await result
        codes: list[str] = []
        for row in list(result or []):
            payload = dict(row or {}) if isinstance(row, dict) else {"code": row}
            code = _normalize_dispatch_stock_code(
                payload.get("code")
                or payload.get("symbol")
                or payload.get("ts_code")
                or payload.get("stock_code")
            )
            if code and code not in codes:
                codes.append(code)
        logger.info(
            "Strategy Factory dispatch default universe loaded: codes=%d limit=%d",
            len(codes),
            limit,
        )
        return codes

    async def _claim_queued_dispatch(self, runtime_kwargs: dict) -> dict | None:
        if self.run_once:
            return None
        db_provider = runtime_kwargs.get("db_provider")
        if not callable(db_provider):
            return None
        db = db_provider()
        if not hasattr(db, "list_strategy_factory_dispatches") or not hasattr(db, "update_strategy_factory_dispatch"):
            return None
        queued = await db.list_strategy_factory_dispatches(status="queued", limit=1)
        if not queued:
            return None
        dispatch = dict(queued[0] or {})
        dispatch_id = str(dispatch.get("dispatch_id") or "").strip()
        if not dispatch_id:
            return None
        claimed = await db.update_strategy_factory_dispatch(
            dispatch_id,
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
            message="Strategy Factory dispatch claimed by standalone runner.",
            metadata={
                **dict(dispatch.get("metadata") or {}),
                "runner": "standalone",
                "claimed_by": "run_strategy_factory.py",
            },
        )
        self._active_dispatch = {**dict(claimed or dispatch), "_db": db}
        return self._active_dispatch

    async def _complete_active_dispatch(self, result: dict) -> None:
        dispatch = self._active_dispatch
        self._active_dispatch = None
        if not dispatch:
            return
        db = dispatch.get("_db")
        dispatch_id = str(dispatch.get("dispatch_id") or "").strip()
        if not dispatch_id or db is None or not hasattr(db, "update_strategy_factory_dispatch"):
            return
        data = dict(result.get("data") or {})
        status = str(data.get("status") or "").strip().lower()
        if status not in {"success", "partial", "skipped", "failed"}:
            status = "success" if result.get("success") else "failed"
        await db.update_strategy_factory_dispatch(
            dispatch_id,
            status=status,
            completed_at=datetime.now(timezone.utc).isoformat(),
            run_id=str(data.get("run_id") or "").strip() or None,
            message=f"Strategy Factory standalone runner completed with status={status}.",
            error=None if result.get("success") else str(result.get("error") or ""),
            metadata={
                **dict(dispatch.get("metadata") or {}),
                "runner": "standalone",
                "result_status": status,
                "artifact_refs": list(data.get("artifact_refs") or []),
            },
        )

    async def _fail_active_dispatch(self, exc: BaseException) -> None:
        dispatch = self._active_dispatch
        self._active_dispatch = None
        if not dispatch:
            return
        db = dispatch.get("_db")
        dispatch_id = str(dispatch.get("dispatch_id") or "").strip()
        if not dispatch_id or db is None or not hasattr(db, "update_strategy_factory_dispatch"):
            return
        cancelled = isinstance(exc, asyncio.CancelledError)
        await db.update_strategy_factory_dispatch(
            dispatch_id,
            status="failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            message=(
                "Strategy Factory standalone runner cancelled."
                if cancelled
                else "Strategy Factory standalone runner failed."
            ),
            error=("cancelled" if cancelled and not str(exc) else str(exc)),
            metadata={
                **dict(dispatch.get("metadata") or {}),
                "runner": "standalone",
                "error_type": exc.__class__.__name__,
                "cancelled": cancelled,
            },
        )

    async def _interruptible_sleep(self, seconds: float):
        """可中断的等待。"""
        end_time = time.time() + seconds
        while self._running and time.time() < end_time:
            await asyncio.sleep(min(1.0, end_time - time.time()))

    def _log_stages(self, data: dict):
        """打印各阶段结果。"""
        pipeline = data.get("cycle_pipeline", {})
        stage_results = pipeline.get("stage_results") if isinstance(pipeline, dict) else None
        if stage_results:
            for item in stage_results:
                if not isinstance(item, dict):
                    continue
                name = item.get("name", "?")
                status = item.get("status", "?")
                logger.info("  stage %-20s: %s", name, status)
            return
        stages = data.get("stages", {})
        if not stages:
            return
        for name, info in stages.items():
            if isinstance(info, dict):
                status = info.get("status", "?")
                detail = ""
                if "candidates_generated" in info:
                    detail = f" (生成={info['candidates_generated']})"
                elif "submitted_count" in info:
                    detail = f" (提交={info['submitted_count']})"
                elif "computed_count" in info:
                    detail = f" (计算={info['computed_count']})"
                logger.info("  阶段 %-20s: %s%s", name, status, detail)


def parse_args():
    parser = argparse.ArgumentParser(description="策略工厂持续运行脚本")
    parser.add_argument("--once", action="store_true", help="只运行一次然后退出")
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="运行间隔（秒）；未指定时按 Strategy Factory 环境变量和当前交易时段解析",
    )
    parser.add_argument("--codes", nargs="*", help="目标股票代码（不指定则使用默认宇宙）")
    parser.add_argument("--execution-mode", default=None, help="Strategy Factory execution mode")
    parser.add_argument(
        "--dispatch-run",
        action="store_true",
        help="submit each cycle through StrategyFactoryScheduler.dispatch_run",
    )
    parser.add_argument(
        "--parallel-full-cycles",
        action="store_true",
        help="enable bounded full-cycle dispatch concurrency",
    )
    parser.add_argument(
        "--dispatch-concurrency",
        type=int,
        default=None,
        help="max concurrent dispatches, clamped to 1..16",
    )
    parser.add_argument(
        "--dispatch-shard-size",
        type=int,
        default=None,
        help="number of --codes entries per dispatch batch",
    )
    parser.add_argument(
        "--dispatch-default-universe",
        action="store_true",
        help="when --codes is omitted, load the default stock universe and shard it into dispatches",
    )
    parser.add_argument(
        "--dispatch-default-universe-limit",
        type=int,
        default=None,
        help="max default stock-universe codes to load for dispatch sharding",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    dispatch_concurrency_limit = _configure_dispatch_launch_options(
        dispatch_run_mode=args.dispatch_run,
        parallel_full_cycles=args.parallel_full_cycles,
        dispatch_concurrency=args.dispatch_concurrency,
    )

    runner = StrategyFactoryRunner(
        interval_sec=args.interval,
        run_once=args.once,
        target_codes=args.codes,
        execution_mode=args.execution_mode,
        dispatch_run_mode=args.dispatch_run,
        dispatch_concurrency_limit=dispatch_concurrency_limit,
        dispatch_shard_size=args.dispatch_shard_size,
        dispatch_default_universe=(
            args.dispatch_default_universe
            or _env_flag("STRATEGY_FACTORY_DISPATCH_DEFAULT_UNIVERSE_ENABLED")
        ),
        dispatch_default_universe_limit=args.dispatch_default_universe_limit,
    )

    try:
        asyncio.run(runner.run())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt, 退出")


if __name__ == "__main__":
    main()
