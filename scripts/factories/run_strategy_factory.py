#!/usr/bin/env python3
"""Run Strategy Factory from the maintained package runtime.

This script is intentionally thin: process lifecycle belongs here, while the
factory implementation stays in ``packages/strategy-factory``.  It is safe by
default for trading operations: live/broker writes are disabled in the child
environment unless a caller has explicitly configured otherwise outside this
runner.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "akshare_mcp.sqlite3"
DEFAULT_INTERVAL_SEC = 300


def _configure_import_paths() -> None:
    for path in (
        PROJECT_ROOT / "packages" / "strategy-factory" / "src",
        PROJECT_ROOT / "packages" / "akshare-mcp" / "src",
        PROJECT_ROOT / "packages" / "aiask-quant-core" / "src",
    ):
        token = str(path)
        if token not in sys.path:
            sys.path.insert(0, token)


def _configure_runtime_env() -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    if "AIASK_SQLITE_PATH" not in os.environ and "AKSHARE_MCP_SQLITE_PATH" not in os.environ:
        os.environ["AIASK_SQLITE_PATH"] = str(DEFAULT_DB_PATH)
        os.environ["AKSHARE_MCP_SQLITE_PATH"] = str(DEFAULT_DB_PATH)
    os.environ.setdefault("LIVE_TRADING_ENABLED", "0")
    os.environ.setdefault("LIVE_TRADING_ALLOW_WRITE", "0")
    os.environ.setdefault("BROKER_ALLOW_WRITE", "0")
    os.environ.setdefault("LIVE_TRADING_READ_ONLY", "1")
    os.environ.setdefault("BROKER_READ_ONLY", "1")


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _json_default(value: Any) -> str:
    try:
        return value.isoformat()
    except Exception:
        return str(value)


def _normalize_cycle_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return dict(result)
    return {"status": "unknown", "result": result}


def _resolve_runner_interval_sec(value: int | None = None) -> int:
    if value is not None:
        return max(1, int(value))
    raw = os.getenv("STRATEGY_FACTORY_RUNNER_INTERVAL_SEC")
    try:
        return max(1, int(str(raw or DEFAULT_INTERVAL_SEC).strip()))
    except Exception:
        return DEFAULT_INTERVAL_SEC


def _resolve_db_path() -> Path:
    raw = os.getenv("AIASK_SQLITE_PATH") or os.getenv("AKSHARE_MCP_SQLITE_PATH") or str(DEFAULT_DB_PATH)
    return Path(raw).expanduser().resolve()


def _load_default_universe(limit: int | None) -> list[str]:
    db_path = _resolve_db_path()
    if not db_path.exists():
        return []
    max_rows = max(1, min(int(limit or 500), 5000))
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=15)
    try:
        rows = conn.execute(
            """
            SELECT stock_code
            FROM stocks
            WHERE COALESCE(stock_code, '') <> ''
            ORDER BY stock_code
            LIMIT ?
            """,
            (max_rows,),
        ).fetchall()
        return [str(row[0]).strip() for row in rows if str(row[0] or "").strip()]
    finally:
        conn.close()


def _apply_dispatch_env(args: argparse.Namespace) -> None:
    if args.parallel_full_cycles:
        os.environ["STRATEGY_FACTORY_ALLOW_PARALLEL_FULL_CYCLES"] = "1"
    if args.dispatch_concurrency is not None:
        os.environ["STRATEGY_FACTORY_MAX_CONCURRENT_DISPATCHES"] = str(args.dispatch_concurrency)
    if args.execution_mode:
        os.environ["STRATEGY_FACTORY_EXECUTION_MODE"] = str(args.execution_mode)


def _load_strategy_factory_runtime_kwargs(db: Any | None = None) -> dict[str, Any]:
    _configure_import_paths()
    _configure_runtime_env()
    from strategy_factory.runtime.default_bootstrap import build_default_scheduler_kwargs

    return build_default_scheduler_kwargs(db=db)


def _build_scheduler():
    _configure_import_paths()
    _configure_runtime_env()
    from strategy_factory.api import get_strategy_factory_scheduler
    from strategy_factory.runtime.default_bootstrap import build_default_scheduler_kwargs

    return get_strategy_factory_scheduler(**build_default_scheduler_kwargs())


class StrategyFactoryRunner:
    def __init__(
        self,
        *,
        interval_sec: int | None = None,
        execution_mode: str | None = None,
        target_codes: list[str] | None = None,
        dispatch_run: bool = False,
    ) -> None:
        self.interval_sec = _resolve_runner_interval_sec(interval_sec)
        self.execution_mode = execution_mode
        self.target_codes = list(target_codes or [])
        self.dispatch_run = bool(dispatch_run)

    async def run_once(self) -> dict[str, Any]:
        scheduler = _build_scheduler()
        if self.dispatch_run:
            result = await scheduler.dispatch_run(
                execution_mode=self.execution_mode,
                target_codes=self.target_codes,
            )
        else:
            result = await scheduler.run_once(
                execution_mode=self.execution_mode,
                target_codes=self.target_codes,
            )
        return _normalize_cycle_result(result)

    async def run_forever(self) -> None:
        while True:
            try:
                result = await self.run_once()
                print(json.dumps(result, ensure_ascii=False, default=_json_default), flush=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(
                    json.dumps(
                        {
                            "status": "failed",
                            "error": str(exc),
                            "error_type": exc.__class__.__name__,
                            "ts": _timestamp(),
                        },
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                    flush=True,
                )
            await asyncio.sleep(self.interval_sec)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AIASK Strategy Factory.")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Validate configuration without running a cycle.")
    parser.add_argument("--json", action="store_true", help="Print run result as JSON.")
    parser.add_argument("--interval", type=int, default=None, help="Loop interval seconds when not using --once.")
    parser.add_argument("--codes", nargs="*", default=None, help="Optional target stock codes.")
    parser.add_argument("--execution-mode", default=None, help="Strategy Factory execution mode override.")
    parser.add_argument("--dispatch-run", action="store_true", help="Queue via scheduler.dispatch_run instead of direct run_once.")
    parser.add_argument("--parallel-full-cycles", action="store_true", help="Allow bounded parallel full-cycle dispatches.")
    parser.add_argument("--dispatch-concurrency", type=int, default=None, help="Dispatch concurrency limit.")
    parser.add_argument("--dispatch-shard-size", type=int, default=None, help="Accepted for supervisor compatibility.")
    parser.add_argument("--dispatch-default-universe", action="store_true", help="Load target codes from stocks table.")
    parser.add_argument("--dispatch-default-universe-limit", type=int, default=None, help="Max default-universe codes.")
    return parser.parse_args(argv)


async def _run_async(args: argparse.Namespace) -> int:
    _configure_runtime_env()
    _apply_dispatch_env(args)
    target_codes = list(args.codes or [])
    if args.dispatch_default_universe and not target_codes:
        target_codes = _load_default_universe(args.dispatch_default_universe_limit)
    if args.dispatch_shard_size is not None:
        os.environ["STRATEGY_FACTORY_DISPATCH_SHARD_SIZE"] = str(args.dispatch_shard_size)

    if args.dry_run:
        payload = {
            "status": "dry_run",
            "db_path": str(_resolve_db_path()),
            "db_exists": _resolve_db_path().exists(),
            "execution_mode": args.execution_mode or os.getenv("STRATEGY_FACTORY_EXECUTION_MODE"),
            "dispatch_run": bool(args.dispatch_run),
            "parallel_full_cycles": bool(args.parallel_full_cycles),
            "dispatch_concurrency": args.dispatch_concurrency,
            "target_code_count": len(target_codes),
            "interval_sec": _resolve_runner_interval_sec(args.interval),
            "live_trading_enabled": os.getenv("LIVE_TRADING_ENABLED"),
            "broker_allow_write": os.getenv("BROKER_ALLOW_WRITE"),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
        return 0 if payload["db_exists"] else 1

    runner = StrategyFactoryRunner(
        interval_sec=args.interval,
        execution_mode=args.execution_mode,
        target_codes=target_codes,
        dispatch_run=args.dispatch_run,
    )
    if args.once:
        result = await runner.run_once()
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default), flush=True)
        else:
            print(
                f"{_timestamp()} StrategyFactory run_once status={result.get('status')} "
                f"run_id={result.get('run_id')}",
                flush=True,
            )
        status = str(result.get("status") or "").lower()
        return 0 if status in {"success", "partial", "partial_infra", "partial_llm", "success_no_strategy", "skipped"} else 1

    await runner.run_forever()
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_import_paths()
    args = parse_args(argv)
    try:
        return asyncio.run(_run_async(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
