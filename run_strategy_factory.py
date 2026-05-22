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
PROJECT_ROOT = Path(__file__).resolve().parent


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
            minimum=600,
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


class StrategyFactoryRunner:
    """策略工厂持续运行器。"""

    def __init__(
        self,
        *,
        interval_sec: int | None = None,
        run_once: bool = False,
        target_codes: list[str] | None = None,
    ):
        self.interval_sec = _resolve_runner_interval_sec(interval_sec)
        self.run_once = run_once
        self.target_codes = target_codes
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
                elif status == "skipped":
                    self._skipped_count += 1
                    logger.info(
                        "第 %d 轮跳过 状态=%s 耗时=%.1fs 原因: %s",
                        self._run_count, status, elapsed, result.get("error", "skipped"),
                    )
                else:
                    self._failure_count += 1
                    error = result.get("error", "unknown")
                    logger.warning("第 %d 轮失败 ❌ 错误: %s", self._run_count, error)

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
        dispatch = await self._claim_queued_dispatch(runtime_kwargs)
        if dispatch:
            dispatch_id = str(dispatch.get("dispatch_id") or "").strip()
            execution_mode = str(dispatch.get("execution_mode") or "").strip() or None
            target_codes = self.target_codes or list((dispatch.get("metadata") or {}).get("target_codes") or [])
            logger.info("鎵ц Strategy Factory dispatch: %s", dispatch_id)
            return await scheduler.run_once(
                execution_mode=execution_mode,
                dispatch_id=dispatch_id,
                target_codes=target_codes,
            )
        return await scheduler.run_once(target_codes=self.target_codes or [])

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
    return parser.parse_args()


def main():
    args = parse_args()

    runner = StrategyFactoryRunner(
        interval_sec=args.interval,
        run_once=args.once,
        target_codes=args.codes,
    )

    try:
        asyncio.run(runner.run())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt, 退出")


if __name__ == "__main__":
    main()
