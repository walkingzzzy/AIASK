#!/usr/bin/env python3
"""Incubation Factory standalone runner."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import os
import sys
from datetime import time as dt_time
from pathlib import Path


def _configure_stdio_utf8() -> None:
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_FACTORY_SRC = PROJECT_ROOT / "packages" / "strategy-factory" / "src"
if str(STRATEGY_FACTORY_SRC) not in sys.path:
    sys.path.insert(0, str(STRATEGY_FACTORY_SRC))

from strategy_factory.runtime_bootstrap import ensure_factory_runtime

ensure_factory_runtime(
    project_root=PROJECT_ROOT,
    script_path=Path(__file__).resolve(),
    argv=sys.argv[1:],
    editable_packages=(
        "packages/strategy-factory",
        "packages/aiask-quant-core",
        "packages/akshare-mcp",
    ),
    distribution_names=(
        "strategy-factory",
        "aiask-quant-core",
        "akshare-mcp",
    ),
    uv_project="packages/agent",
)


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


def _load_project_env() -> None:
    try:
        from akshare_mcp.env_loader import load_mcp_env

        load_mcp_env(override=False)
    except Exception:
        pass


def _setup_logging(verbose: bool = False) -> None:
    log_dir = PROJECT_ROOT / "packages" / "akshare-mcp" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if verbose else logging.INFO
    handlers = [
        logging.FileHandler(log_dir / "incubation_factory.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )

    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def _parse_time(value: str) -> dt_time:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"invalid time format: {value}; expected HH:MM")
    try:
        hour, minute = int(parts[0]), int(parts[1])
        return dt_time(hour, minute)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(f"invalid time format: {value}") from exc


def _build_runtime(args: argparse.Namespace):
    from strategy_factory.runtime.default_bootstrap import ensure_default_runtime_services
    from strategy_factory.runtime.incubation import build_incubation_runtime

    ensure_default_runtime_services()
    return build_incubation_runtime(
        run_time=_parse_time(args.run_time),
        dry_run=args.dry_run,
    )


async def _run_once(args: argparse.Namespace) -> None:
    runtime = _build_runtime(args)
    result = await runtime.run_once()

    print("\n" + "=" * 60)
    print("Incubation Factory Result")
    print("=" * 60)

    status = result.get("status", "unknown")
    print(f"status: {status}")
    print(f"elapsed: {result.get('elapsed_seconds', 0):.1f}s")

    if status == "completed":
        intake = result.get("intake", {})
        verification = result.get("verification", {})
        pipeline = result.get("pipeline", {})
        report = result.get("report", {})

        print(f"\naccepted: {intake.get('accepted', 0)}")
        print(f"verified: {verification.get('verified', 0)}")
        print(f"metrics_recorded: {verification.get('metrics_recorded', 0)}")
        print(f"auto_promoted: {pipeline.get('auto_promoted', 0)}")
        print(f"stage_counts: {pipeline.get('stage_counts', {})}")

        hit_rate = report.get("overall_hit_rate")
        skill_lcb = report.get("overall_skill_lcb")
        if hit_rate is not None:
            print(f"\noverall_hit_rate: {hit_rate * 100:.2f}%")
        if skill_lcb is not None:
            print(f"overall_skill_lcb: {skill_lcb:.4f}")
    elif status == "failed":
        print(f"error: {result.get('error', 'unknown')}")

    print("=" * 60)

    if args.json:
        print("\nfull_json:")
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


async def _run_daemon(args: argparse.Namespace) -> None:
    runtime = _build_runtime(args)
    print(
        f"Incubation Factory daemon started (run_time={args.run_time}, dry_run={args.dry_run})"
    )
    print("Press Ctrl+C to stop")

    try:
        await runtime.run_daemon()
    except KeyboardInterrupt:
        print("\nIncubation Factory daemon stopped")


async def _show_status(_args: argparse.Namespace) -> None:
    from akshare_mcp.storage import close_db, get_db

    db = get_db()
    await db.initialize()

    print("Incubation Factory Status")
    print("=" * 60)

    try:
        incubating = await db.list_strategies("incubating", limit=500)
        print(f"incubating_strategies: {len(incubating)}")
    except Exception as exc:
        print(f"query_failed: {exc}")

    if hasattr(db, "list_strategy_domain_events"):
        try:
            events = await db.list_strategy_domain_events(
                event_type="incubation_factory.heartbeat",
                limit=1,
            )
            if events:
                payload = dict((events[0] or {}).get("payload") or {})
                print(f"last_heartbeat: {payload.get('timestamp', 'unknown')}")
                print(f"run_count: {payload.get('run_count', 0)}")
                print(f"error_count: {payload.get('error_count', 0)}")
            else:
                print("last_heartbeat: none")
        except Exception:
            print("last_heartbeat: query_failed")

        try:
            reports = await db.list_strategy_domain_events(
                event_type="incubation_factory.hit_rate_report_generated",
                limit=1,
            )
            if reports:
                report_payload = dict((reports[0] or {}).get("payload") or {})
                overall = dict(
                    (report_payload.get("hit_rate_dashboard") or {}).get("overall") or {}
                )
                print(f"last_hit_rate_report: {report_payload.get('report_date', 'unknown')}")
                print(f"overall_hit_rate: {float(overall.get('hit_rate') or 0) * 100:.2f}%")
                print(f"overall_skill_lcb: {overall.get('avg_skill_lcb', 0):.4f}")
                print(f"total_signals: {overall.get('total_signals', 0)}")
            else:
                print("last_hit_rate_report: none")
        except Exception:
            print("last_hit_rate_report: query_failed")

    await close_db()
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Incubation Factory standalone runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="daemon mode",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run without persistence side effects where supported",
    )
    parser.add_argument(
        "--run-time",
        default="18:30",
        help="daily daemon run time in HH:MM format",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="show current incubation status",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the full run_once payload as JSON",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="enable verbose logging",
    )

    args = parser.parse_args()
    _load_project_env()
    _setup_logging(verbose=args.verbose)

    if args.status:
        asyncio.run(_show_status(args))
    elif args.daemon:
        asyncio.run(_run_daemon(args))
    else:
        asyncio.run(_run_once(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
