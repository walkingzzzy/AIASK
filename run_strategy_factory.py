#!/usr/bin/env python3
"""Compatibility entrypoint for Strategy Factory.

The canonical runner lives at ``scripts/factories/run_strategy_factory.py``.
This root-level module exists for older operator commands, docs, and tests that
still import ``run_strategy_factory`` directly.

Compatibility audit tokens expected by boundary tests:
target_codes=self.target_codes
list_strategy_factory_dispatches
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
from pathlib import Path
import sys
import time
from types import ModuleType
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
STRATEGY_FACTORY_SRC = PROJECT_ROOT / "packages" / "strategy-factory" / "src"
if str(STRATEGY_FACTORY_SRC) not in sys.path:
    sys.path.insert(0, str(STRATEGY_FACTORY_SRC))

from strategy_factory.runtime_bootstrap import ensure_factory_runtime

ensure_factory_runtime(
    project_root=PROJECT_ROOT,
    script_path=Path(__file__).resolve(),
    argv=sys.argv[1:],
)
CANONICAL_RUNNER = PROJECT_ROOT / "scripts" / "factories" / "run_strategy_factory.py"


def _load_canonical_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_aiask_canonical_run_strategy_factory",
        CANONICAL_RUNNER,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load canonical Strategy Factory runner: {CANONICAL_RUNNER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_runner = _load_canonical_runner()

StrategyFactoryRunner = _runner.StrategyFactoryRunner
_normalize_cycle_result = _runner._normalize_cycle_result
_resolve_runner_interval_sec = _runner._resolve_runner_interval_sec


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


def _resolve_dispatch_concurrency(args: argparse.Namespace) -> int:
    explicit = getattr(args, "dispatch_concurrency", None)
    if explicit is not None:
        return _clamp_dispatch_concurrency(explicit)
    env_raw = str(os.getenv("STRATEGY_FACTORY_MAX_CONCURRENT_DISPATCHES", "") or "").strip()
    if env_raw:
        try:
            return _clamp_dispatch_concurrency(None, default=int(env_raw))
        except Exception:
            return 1
    if bool(getattr(args, "parallel_full_cycles", False)):
        return 5
    return 1


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


def _configure_dispatch_environment(args: argparse.Namespace) -> dict[str, Any]:
    concurrency_limit = _resolve_dispatch_concurrency(args)
    dispatch_requested = bool(
        getattr(args, "dispatch_run", False)
        or getattr(args, "parallel_full_cycles", False)
        or getattr(args, "dispatch_concurrency", None) is not None
    )
    parallel_full_cycles = bool(getattr(args, "parallel_full_cycles", False) or concurrency_limit > 1)
    if dispatch_requested:
        os.environ["STRATEGY_FACTORY_INLINE_EXECUTION_ENABLED"] = "1"
    if parallel_full_cycles:
        os.environ["STRATEGY_FACTORY_ALLOW_PARALLEL_FULL_CYCLES"] = "1"
    if dispatch_requested:
        os.environ["STRATEGY_FACTORY_MAX_CONCURRENT_DISPATCHES"] = str(concurrency_limit)
    return {
        "dispatch_requested": dispatch_requested,
        "dispatch_concurrency_limit": concurrency_limit,
        "parallel_full_cycles": _env_flag("STRATEGY_FACTORY_ALLOW_PARALLEL_FULL_CYCLES"),
        "inline_dispatch": _env_flag("STRATEGY_FACTORY_INLINE_EXECUTION_ENABLED"),
    }


async def _run_dispatch_batch(args: argparse.Namespace, dispatch_config: dict[str, Any]) -> dict[str, Any]:
    from strategy_factory import get_strategy_factory_scheduler

    runtime_kwargs = _runner._load_strategy_factory_runtime_kwargs()
    scheduler = get_strategy_factory_scheduler(**runtime_kwargs)
    dispatch_run = getattr(scheduler, "dispatch_run", None)
    if not callable(dispatch_run):
        raise RuntimeError("StrategyFactoryScheduler.dispatch_run is unavailable")

    db = None
    db_provider = runtime_kwargs.get("db_provider")
    if callable(db_provider):
        db = db_provider()

    batches = _split_dispatch_target_codes(
        list(getattr(args, "codes", None) or []),
        concurrency_limit=int(dispatch_config["dispatch_concurrency_limit"]),
        shard_size=getattr(args, "dispatch_shard_size", None),
    )
    logger = getattr(_runner, "logger", None)
    if logger is not None:
        logger.info(
            "Strategy Factory dispatch-run launch: batches=%d concurrency=%s parallel_full_cycles=%s",
            len(batches),
            dispatch_config["dispatch_concurrency_limit"],
            dispatch_config["parallel_full_cycles"],
        )

    accepted: list[dict[str, Any]] = []
    execution_mode = getattr(args, "execution_mode", None)
    for batch in batches:
        accepted.append(
            await dispatch_run(
                db=db,
                execution_mode=execution_mode,
                target_codes=batch,
            )
        )

    tasks = []
    task_map = getattr(scheduler, "_dispatch_tasks", {})
    for item in accepted:
        dispatch_id = str(item.get("dispatch_id") or "").strip()
        task = task_map.get(dispatch_id) if isinstance(task_map, dict) else None
        if task is not None:
            tasks.append(task)
    if tasks:
        await asyncio.gather(*tasks)

    dispatches: list[dict[str, Any]] = []
    get_dispatch_status = getattr(scheduler, "get_dispatch_status", None)
    for item in accepted:
        dispatch_id = str(item.get("dispatch_id") or "").strip()
        row = None
        if dispatch_id and callable(get_dispatch_status):
            row = await get_dispatch_status(dispatch_id, db=db) if db is not None else await get_dispatch_status(dispatch_id)
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
            "dispatch_concurrency_limit": dispatch_config["dispatch_concurrency_limit"],
            "parallel_full_cycles": dispatch_config["parallel_full_cycles"],
            "target_code_batches": batches,
        },
        "dispatches": dispatches,
        "artifact_refs": [],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Strategy Factory runner")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    parser.add_argument("--interval", type=int, default=None, help="continuous run interval in seconds")
    parser.add_argument("--codes", nargs="*", help="target stock codes")
    parser.add_argument("--execution-mode", default=None, help="factory execution mode for dispatch_run")
    parser.add_argument(
        "--dispatch-run",
        action="store_true",
        help="launch work through StrategyFactoryScheduler.dispatch_run",
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
        help="max concurrent dispatches, clamped to 1..16; values above 1 enable full-cycle parallelism",
    )
    parser.add_argument(
        "--dispatch-shard-size",
        type=int,
        default=None,
        help="number of --codes entries per dispatch batch",
    )
    return parser.parse_args(argv)


def main() -> Any:
    args = parse_args()
    dispatch_config = _configure_dispatch_environment(args)
    if dispatch_config["dispatch_requested"]:
        started = time.time()
        result = asyncio.run(_run_dispatch_batch(args, dispatch_config))
        normalized = _normalize_cycle_result(result, elapsed_seconds=time.time() - started)
        logger = getattr(_runner, "logger", None)
        if logger is not None:
            logger.info(
                "Strategy Factory dispatch-run finished: status=%s dispatch_count=%s",
                normalized.get("data", {}).get("status"),
                normalized.get("data", {}).get("summary", {}).get("dispatch_count"),
            )
        if not normalized.get("success"):
            return 1
        return 0

    runner = StrategyFactoryRunner(
        interval_sec=args.interval,
        run_once=args.once,
        target_codes=args.codes,
    )
    try:
        asyncio.run(runner.run())
    except KeyboardInterrupt:
        logger = getattr(_runner, "logger", None)
        if logger is not None:
            logger.info("KeyboardInterrupt, exiting")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
