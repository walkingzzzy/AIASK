#!/usr/bin/env python3
"""孵化工厂独立运行入口（仓库根 wrapper）。

实际运行器位于 packages/akshare-mcp/scripts/run_incubation_factory.py；
本 wrapper 只是把仓库根作为 cwd 时的入口对齐到与
run_strategy_factory.py / run_factor_mining_factory.py 同位置，方便
operators 与 cron / systemd 配置统一。

用法：
    python run_incubation_factory.py              # 守护
    python run_incubation_factory.py --once       # 单次
    python run_incubation_factory.py --status     # 查状态
    python run_incubation_factory.py --dry-run    # 不写库
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path


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

_ROOT = Path(__file__).resolve().parent
_TARGET = _ROOT / "packages" / "akshare-mcp" / "scripts" / "run_incubation_factory.py"
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
            f"run_incubation_factory wrapper: target not found at {_TARGET}\n"
            "Make sure packages/akshare-mcp is checked out.\n"
        )
        return 2
    _bootstrap_local_package_paths()
    from akshare_mcp.env_loader import load_mcp_env
    from akshare_mcp.adapters.strategy_factory_runtime import (
        configure_strategy_factory_runtime_services,
    )
    from run_incubation_factory import main as target_main

    load_mcp_env(override=False)
    configure_strategy_factory_runtime_services()
    # Forward argv as-is and let the real runner do its own argparse.
    sys.argv[0] = str(_TARGET)
    target_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
