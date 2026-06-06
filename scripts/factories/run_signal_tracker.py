#!/usr/bin/env python3
"""SignalTracker 独立运行入口（仓库根 wrapper）。

实际运行器位于 packages/akshare-mcp/scripts/run_signal_tracker.py；
本 wrapper 只是把仓库根作为 cwd 时的入口对齐到与
run_strategy_factory.py / run_factor_mining_factory.py /
run_incubation_factory.py 同位置，方便 operators 与
run_all_factories.py / cron / systemd 配置统一。

为何引入：
    SignalTracker 在传统部署里是 MCP server 的后台 daemon
    （server.py:570），但我们的 ``run_all_factories.py`` 只起
    strategy/factor/incubation 三个独立工厂进程，从不启动 MCP server，
    导致 SignalTracker 永远没运行 → strategy_signals 表始终为空 →
    孵化工厂 Phase 3 拿不到 signal 做前向验证 → 12 个 warmup 账户
    effective_n_5d 永远是 0 → 永远升不到 candidate 阶段。

    本 wrapper 让 SignalTracker 以独立进程方式跑，可由 supervisor
    在 18:00（incubation 18:30 之前）拉起，串联完整一日流水线：
        18:00  SignalTracker → 写 strategy_signals
        18:30  IncubationFactory → 读上面这张表做前向验证

用法：
    python run_signal_tracker.py             # 守护（默认 18:00）
    python run_signal_tracker.py --once      # 单次
    python run_signal_tracker.py --run-time 18:00 --daemon
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path


def _configure_stdio_utf8() -> None:
    """Force stdout/stderr to UTF-8 so Chinese chars render in
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

_ROOT = Path(__file__).resolve().parents[2]
_TARGET = _ROOT / "packages" / "akshare-mcp" / "scripts" / "run_signal_tracker.py"
_TARGET_SCRIPT_DIR = _TARGET.parent


def _bootstrap_local_package_paths() -> None:
    for package_src in (
        _ROOT / "packages" / "aiask-quant-core" / "src",
        _ROOT / "packages" / "strategy-factory" / "src",
        _ROOT / "packages" / "akshare-mcp" / "src",
        _TARGET_SCRIPT_DIR,
    ):
        path = str(package_src)
        if package_src.exists() and path not in sys.path:
            sys.path.insert(0, path)


def main() -> int:
    if not _TARGET.exists():
        sys.stderr.write(
            f"run_signal_tracker wrapper: target not found at {_TARGET}\n"
            "Make sure packages/akshare-mcp is checked out.\n"
        )
        return 2
    _bootstrap_local_package_paths()
    try:
        from akshare_mcp.adapters.strategy_factory_runtime import (
            configure_strategy_factory_runtime_services,
        )
        configure_strategy_factory_runtime_services()
    except Exception:
        # configure helper is best-effort; SignalTracker doesn't strictly need it
        pass
    from run_signal_tracker import main as target_main  # noqa: PLC0415

    sys.argv[0] = str(_TARGET)
    return target_main()


if __name__ == "__main__":
    raise SystemExit(main())
