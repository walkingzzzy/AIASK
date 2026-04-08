#!/usr/bin/env python3
"""Run strategy-factory throughput verification and emit a Markdown report."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
for relative in (
    ROOT / "packages" / "akshare-mcp" / "src",
    ROOT / "packages" / "strategy-factory" / "src",
):
    path_str = str(relative)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return float(default)


def _per_hour(total: float, elapsed_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 0.0
    return round(total * 3600.0 / elapsed_seconds, 4)


def _write_report(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _render_markdown(report: dict[str, Any]) -> str:
    metrics = dict(report.get("metrics") or {})
    config = dict(report.get("config") or {})
    lines = [
        "# 策略工厂吞吐验证报告",
        "",
        f"- 生成时间: {report.get('generated_at')}",
        f"- 标签: {report.get('label')}",
        f"- 运行轮数: {report.get('cycles')}",
        "",
        "## 关键指标",
        "",
        f"- 累计候选数: {metrics.get('total_candidates')}",
        f"- 累计 Gate-3 通过数: {metrics.get('total_gate3_passed')}",
        f"- 总 wall time: {metrics.get('wall_elapsed_seconds')} 秒",
        f"- 总 run elapsed: {metrics.get('total_run_elapsed_seconds')} 秒",
        f"- 计算吞吐 candidates/hour: {metrics.get('compute_candidates_per_hour')}",
        f"- 计算吞吐 gate3/hour: {metrics.get('compute_gate3_per_hour')}",
        f"- 盘中调度折算 candidates/hour: {metrics.get('market_schedule_candidates_per_hour')}",
        f"- 盘中调度折算 gate3/hour: {metrics.get('market_schedule_gate3_per_hour')}",
        f"- 目标达成: {'是' if metrics.get('market_schedule_target_met') else '否'}",
        "",
        "## 配置",
        "",
        f"- event runtime mode: {config.get('event_runtime_mode')}",
        f"- factor auto refresh: {config.get('factor_auto_refresh')}",
        f"- market interval sec: {config.get('market_interval_sec')}",
        f"- off-hours interval sec: {config.get('off_hours_interval_sec')}",
        f"- target candidates/hour: {config.get('target_candidates_per_hour')}",
        f"- target gate3/hour: {config.get('target_gate3_per_hour')}",
        "",
        "## 单轮摘要",
        "",
        "| run_id | status | elapsed_seconds | candidates_spawned | gate_3_passed | readiness_score |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in list(report.get("runs") or []):
        lines.append(
            "| {run_id} | {status} | {elapsed_seconds} | {candidates_spawned} | {gate_3_passed} | {readiness_score} |".format(
                run_id=item.get("run_id"),
                status=item.get("status"),
                elapsed_seconds=item.get("elapsed_seconds"),
                candidates_spawned=item.get("candidates_spawned"),
                gate_3_passed=item.get("gate_3_passed"),
                readiness_score=item.get("factory_readiness_score"),
            )
        )
    lines.append("")
    return "\n".join(lines)


async def _run_benchmark(args) -> dict[str, Any]:
    from akshare_mcp.services import close_shared_runtime_clients
    from akshare_mcp.storage import close_db, get_db
    from strategy_factory import get_factory_constants, get_strategy_factory_scheduler

    db = get_db()
    scheduler = get_strategy_factory_scheduler()
    config = dict(get_factory_constants() or {})
    try:
        wall_start = time.perf_counter()
        runs: list[dict[str, Any]] = []
        for _ in range(max(args.cycles, 1)):
            result = await scheduler.run_once()
            summary = dict(result.get("summary") or {})
            runs.append(
                {
                    "run_id": result.get("run_id"),
                    "status": result.get("status"),
                    "elapsed_seconds": _safe_float(result.get("elapsed_seconds")),
                    "candidates_spawned": _safe_int(summary.get("candidates_spawned")),
                    "gate_3_passed": _safe_int(summary.get("gate_3_passed")),
                    "factory_readiness_score": _safe_float(summary.get("factory_readiness_score")),
                    "factor_research_refresh_status": summary.get("factor_research_refresh_status"),
                    "event_runtime_mode": summary.get("event_runtime_mode"),
                }
            )
        wall_elapsed = round(time.perf_counter() - wall_start, 4)
        total_candidates = sum(_safe_int(item.get("candidates_spawned")) for item in runs)
        total_gate3_passed = sum(_safe_int(item.get("gate_3_passed")) for item in runs)
        total_run_elapsed = round(sum(_safe_float(item.get("elapsed_seconds")) for item in runs), 4)
        avg_candidates_per_run = round(total_candidates / max(len(runs), 1), 4)
        avg_gate3_per_run = round(total_gate3_passed / max(len(runs), 1), 4)

        market_interval = _safe_int(config.get("FACTORY_MARKET_HOURS_INTERVAL_SEC"), 900)
        off_hours_interval = _safe_int(config.get("FACTORY_OFF_HOURS_INTERVAL_SEC"), 3600)
        target_candidates = _safe_int(config.get("FACTORY_THROUGHPUT_TARGET_CANDIDATES_PER_HOUR"), 100)
        target_gate3 = _safe_int(config.get("FACTORY_THROUGHPUT_TARGET_GATE3_PER_HOUR"), 10)

        metrics = {
            "total_candidates": total_candidates,
            "total_gate3_passed": total_gate3_passed,
            "wall_elapsed_seconds": wall_elapsed,
            "total_run_elapsed_seconds": total_run_elapsed,
            "avg_candidates_per_run": avg_candidates_per_run,
            "avg_gate3_per_run": avg_gate3_per_run,
            "compute_candidates_per_hour": _per_hour(total_candidates, total_run_elapsed or wall_elapsed),
            "compute_gate3_per_hour": _per_hour(total_gate3_passed, total_run_elapsed or wall_elapsed),
            "wall_candidates_per_hour": _per_hour(total_candidates, wall_elapsed),
            "wall_gate3_per_hour": _per_hour(total_gate3_passed, wall_elapsed),
            "market_schedule_candidates_per_hour": round(avg_candidates_per_run * (3600.0 / max(market_interval, 1)), 4),
            "market_schedule_gate3_per_hour": round(avg_gate3_per_run * (3600.0 / max(market_interval, 1)), 4),
            "off_hours_schedule_candidates_per_hour": round(avg_candidates_per_run * (3600.0 / max(off_hours_interval, 1)), 4),
            "off_hours_schedule_gate3_per_hour": round(avg_gate3_per_run * (3600.0 / max(off_hours_interval, 1)), 4),
        }
        metrics["market_schedule_target_met"] = bool(
            metrics["market_schedule_candidates_per_hour"] >= target_candidates
            and metrics["market_schedule_gate3_per_hour"] >= target_gate3
        )

        return {
            "label": args.label,
            "cycles": args.cycles,
            "generated_at": datetime.now().astimezone().isoformat(),
            "config": {
                "event_runtime_mode": config.get("FACTORY_EVENT_RUNTIME_MODE"),
                "factor_auto_refresh": config.get("FACTORY_FACTOR_AUTO_REFRESH"),
                "market_interval_sec": market_interval,
                "off_hours_interval_sec": off_hours_interval,
                "target_candidates_per_hour": target_candidates,
                "target_gate3_per_hour": target_gate3,
            },
            "metrics": metrics,
            "runs": runs,
        }
    finally:
        await close_shared_runtime_clients()
        await close_db()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify strategy factory throughput and save a Markdown report.")
    parser.add_argument("--cycles", type=int, default=3, help="Number of consecutive factory runs.")
    parser.add_argument("--label", default="manual", help="Benchmark label stored in report filenames.")
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "reports" / "strategy_factory"),
        help="Directory for JSON/Markdown reports.",
    )
    parser.add_argument("--event-runtime-mode", choices=["readonly", "refresh"], help="Override event runtime mode.")
    parser.add_argument("--disable-factor-auto-refresh", action="store_true", help="Disable factor freshness auto-repair.")
    args = parser.parse_args()

    if args.event_runtime_mode:
        os.environ["STRATEGY_FACTORY_EVENT_RUNTIME_MODE"] = args.event_runtime_mode
    if args.disable_factor_auto_refresh:
        os.environ["STRATEGY_FACTORY_FACTOR_AUTO_REFRESH"] = "0"

    report = asyncio.run(_run_benchmark(args))
    output_dir = Path(args.output_dir)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = f"strategy-factory-throughput-{args.label}-{timestamp}"
    md_path = output_dir / f"{stem}.md"
    _write_report(md_path, _render_markdown(report))

    print(f"markdown_report: {md_path}")
    print(f"total_candidates: {report['metrics'].get('total_candidates')}")
    print(f"total_gate3_passed: {report['metrics'].get('total_gate3_passed')}")
    print(f"market_schedule_target_met: {report['metrics'].get('market_schedule_target_met')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
