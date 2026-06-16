#!/usr/bin/env python3
"""Run Strategy Factory repeatedly and record each completed run to Markdown.

This session runner is purpose-built for real runtime observation:
1. execute one real Strategy Factory run per round
2. collect run-quality snapshots through the same manager/service handlers that
   power the MCP strategy-manager surface
3. optionally execute one incubation-factory round after each strategy round
4. rewrite a root-level Markdown report after every round
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
for package_src in (
    ROOT / "packages" / "aiask-quant-core" / "src",
    ROOT / "packages" / "strategy-factory" / "src",
    ROOT / "packages" / "akshare-mcp" / "src",
):
    path = str(package_src)
    if package_src.exists() and path not in sys.path:
        sys.path.insert(0, path)

from strategy_factory.runtime_bootstrap import ensure_factory_runtime

ensure_factory_runtime(
    project_root=ROOT,
    script_path=Path(__file__).resolve(),
    argv=sys.argv[1:],
)

from akshare_mcp.adapters.strategy_factory_runtime import configure_strategy_factory_runtime_services
from akshare_mcp.env_loader import load_mcp_env
from akshare_mcp.storage.sqlite import close_db, get_db
from akshare_mcp.tools.managers.strategy_mgr_crud import handle_review_report
from akshare_mcp.tools.managers.strategy_mgr_lifecycle import (
    handle_execution_audit_verification,
    handle_factory_run_detail,
    handle_factory_runs,
    handle_incubation_overview,
)
from akshare_mcp.services.incubation_factory.runner import IncubationFactoryRunner


from _quality_session_common import (
    _LEGACY_BUDGET_MISMATCH_FLAGS,
    _LEGACY_BUDGET_MISMATCH_NOTE_FRAGMENTS,
    DEFAULT_EXECUTION_MODE,
    LOGGER,
    MARKET_TZ,
    _format_dt,
    _iso_now,
    _json_dump,
    _now,
    _pct,
    _process_alive,
    _safe_float,
    _safe_int,
    _write_json,
)
from _quality_session_render import (
    _bool_text,
    _build_aggregate_summary,
    _build_blocker_summary,
    _build_priority_findings,
    _compact_run_detail,
    _extract_issue_flags,
    _format_strict_ready_example_evidence,
    _format_top_blockers,
    _merge_strategy_samples,
    _normalize_blocker_reason,
    _quality_strategy_pool,
    _render_entry,
    _render_report,
    _render_representative_samples,
    _render_strict_ready_example,
    _resolve_candidate_artifact,
    _sample_strategy_table,
    _select_representative_samples,
    _sort_strategy_samples,
    _strict_ready_example_payload,
)


class SessionRunLock:
    def __init__(self, lock_path: Path):
        self._lock_path = lock_path
        self._held = False

    def acquire(self, *, session_id: str) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "session_id": session_id,
            "pid": os.getpid(),
            "acquired_at": _iso_now(),
            "script": str(Path(__file__).resolve()),
        }

        if self._lock_path.exists():
            try:
                existing = json.loads(self._lock_path.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
            existing_pid = _safe_int(existing.get("pid"), default=-1)
            if _process_alive(existing_pid):
                raise RuntimeError(
                    f"Session {session_id} is already running under pid={existing_pid}; "
                    "use --render-only to refresh markdown without starting a new run."
                )
            LOGGER.warning(
                "Removing stale session lock for session_id=%s from pid=%s at %s",
                session_id,
                existing.get("pid"),
                self._lock_path,
            )
            try:
                self._lock_path.unlink()
            except FileNotFoundError:
                pass

        fd = os.open(str(self._lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        self._held = True
        atexit.register(self.release)

    def release(self) -> None:
        if not self._held:
            return
        try:
            if self._lock_path.exists():
                existing = {}
                try:
                    existing = json.loads(self._lock_path.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}
                if _safe_int(existing.get("pid"), default=os.getpid()) == os.getpid():
                    self._lock_path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self._held = False


def _load_script_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolve_report_path(raw: str | None) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    return (ROOT / f"策略工厂24小时运行与质量追踪-{_now().strftime('%Y-%m-%d')}.md").resolve()


def _resolve_session_id(raw: str | None) -> str:
    if raw:
        return str(raw).strip()
    return f"strategy_factory_quality_{_now().strftime('%Y%m%d_%H%M%S')}"


def _resolve_logs_dir(session_id: str) -> Path:
    return (ROOT / "logs" / "strategy_factory_quality_sessions" / session_id).resolve()


def _configure_logging(logs_dir: Path, verbose: bool) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "session.log"
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def _apply_session_env(sqlite_path: Path) -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    os.environ.setdefault("AKSHARE_MCP_SQLITE_PATH", str(sqlite_path))
    os.environ.setdefault("AIASK_SQLITE_PATH", str(sqlite_path))

    os.environ.setdefault("FACTOR_MINING_FACTORY_ENABLED", "1")
    os.environ.setdefault("STRATEGY_FACTORY_FACTOR_CATALOG_ENABLED", "1")
    os.environ.setdefault("INCUBATION_FACTORY_PAPER_INTAKE_ENABLED", "1")
    # 1500/轮:observe(stage=paper)积压上万时加速收敛(实测每策略孵化 ~0.05s,
    # incubating200+paper1500 串行约 85s,远低于 BATCH_TIMEOUT_SEC=600)。
    os.environ.setdefault("INCUBATION_FACTORY_PAPER_INTAKE_BATCH_LIMIT", "1500")
    os.environ["INCUBATION_FACTORY_GATE3_RECORD_ONLY_INTAKE_ENABLED"] = "0"
    os.environ.setdefault("INCUBATION_FACTORY_GATE3_RECORD_ONLY_BATCH_LIMIT", "300")
    os.environ.setdefault("INCUBATION_FACTORY_GATE3_RECORD_ONLY_MIN_GRADE", "C")
    os.environ.setdefault("STRATEGY_FACTORY_FACTOR_IC_GENERIC_INTAKE_ENABLED", "1")
    os.environ.setdefault("STRATEGY_FACTORY_EVENT_RUNTIME_MODE", "refresh")

    os.environ["STRATEGY_FACTORY_EXECUTION_MODE"] = DEFAULT_EXECUTION_MODE
    os.environ["STRATEGY_FACTORY_OBSERVE_FIRST_ENABLED"] = "1"
    os.environ["STRATEGY_FACTORY_WIDE_INTAKE_OBSERVE_ENABLED"] = "1"
    os.environ.setdefault("STRATEGY_TRADE_PREDICTION_PROMOTION_GATE_ENABLED", "0")
    os.environ.setdefault("STRATEGY_TRADE_PREDICTION_BUDGET_FEEDBACK_ENABLED", "1")
    os.environ.setdefault("STRATEGY_TRADE_PREDICTION_FACTOR_DECAY_ENABLED", "1")
    os.environ["STRATEGY_FACTORY_MIN_VALIDATION_GRADE"] = "C"
    os.environ["STRATEGY_FACTORY_GATE3_RECORD_ONLY_ENABLED"] = "0"

    os.environ["LIVE_TRADING_ENABLED"] = "0"
    os.environ["LIVE_TRADING_ALLOW_WRITE"] = "0"
    os.environ["BROKER_ALLOW_WRITE"] = "0"
    os.environ["LIVE_TRADING_READ_ONLY"] = "1"
    os.environ["BROKER_READ_ONLY"] = "1"
    os.environ["INCUBATION_FACTORY_OWNS_PAPER_TRADING"] = "0"


def _factory_module():
    return _load_script_module(
        "_strategy_factory_quality_run_strategy_factory",
        ROOT / "scripts" / "factories" / "run_strategy_factory.py",
    )


from _quality_session_collectors import (
    _resolve_latest_run_id_since,
    _call_optional_db_method,
    _collect_factor_shelf_status,
    _collect_paper_observation_backlog,
    _collect_run_snapshot,
    _collect_strategy_snapshot,
    _enrich_strategy_snapshot_with_persistence,
    _refresh_state_strategy_persistence_metadata,
    _run_factor_mining_once,
    _run_incubation_once,
    _run_signal_tracker_once,
    _run_strategy_factory_once,
)


@dataclass
class SessionPaths:
    logs_dir: Path
    state_json: Path
    report_md: Path
    rounds_dir: Path
    lock_json: Path


def _load_existing_state(paths: SessionPaths) -> dict[str, Any] | None:
    if not paths.state_json.exists():
        return None
    try:
        state = json.loads(paths.state_json.read_text(encoding="utf-8"))
        return _normalize_loaded_state(state, paths)
    except Exception as exc:
        LOGGER.warning("Failed to load existing state from %s: %s", paths.state_json, exc)
        return None


def _build_session_state(args: argparse.Namespace, paths: SessionPaths) -> dict[str, Any]:
    return {
        "session": {
            "session_id": args.session_id,
            "started_at": _iso_now(),
            "hours": args.hours,
            "pause_sec": args.pause_sec,
            "codes": list(args.codes or []),
            "execution_mode": args.execution_mode,
            "python_executable": sys.executable,
            "sqlite_path": str((ROOT / "data" / "db" / "akshare_mcp.sqlite3").resolve()),
            "report_path": str(paths.report_md),
            "logs_dir": str(paths.logs_dir),
            "rounds_dir": str(paths.rounds_dir),
            "with_incubation": bool(args.with_incubation),
            "strategy_sample_limit": args.strategy_sample_limit,
        },
        "updated_at": _iso_now(),
        "entries": [],
    }


def _persist_state(state: dict[str, Any], paths: SessionPaths) -> None:
    state["updated_at"] = _iso_now()
    _write_json(paths.state_json, state)
    paths.report_md.write_text(_render_report(state), encoding="utf-8")


def _mark_session_active(state: dict[str, Any]) -> None:
    session = dict(state.get("session") or {})
    session.pop("completed_at", None)
    state["session"] = session


def _session_lock_is_active(paths: SessionPaths, session_id: str | None = None) -> bool:
    if not paths.lock_json.exists():
        return False
    try:
        payload = json.loads(paths.lock_json.read_text(encoding="utf-8"))
    except Exception:
        return False
    lock_session_id = str(payload.get("session_id") or "").strip()
    if session_id and lock_session_id and lock_session_id != session_id:
        return False
    return _process_alive(_safe_int(payload.get("pid"), default=-1))


def _normalize_loaded_state(state: dict[str, Any], paths: SessionPaths) -> dict[str, Any]:
    session = dict(state.get("session") or {})
    state["session"] = session
    if session.get("completed_at") and _session_lock_is_active(paths, str(session.get("session_id") or "")):
        session.pop("completed_at", None)

    for entry in list(state.get("entries") or []):
        quality = dict(entry.get("quality_snapshot") or {})
        detail = dict(quality.get("detail") or {})
        sampled_strategies = list(quality.get("sampled_strategies") or [])
        representative_samples = list(quality.get("representative_samples") or [])
        derived_flags, derived_notes = _extract_issue_flags(
            detail,
            _merge_strategy_samples([*representative_samples, *sampled_strategies]),
        )
        existing_flags = [
            item
            for item in list(quality.get("issue_flags") or [])
            if str(item or "").strip() not in _LEGACY_BUDGET_MISMATCH_FLAGS
        ]
        existing_notes = [
            item
            for item in list(quality.get("issue_notes") or [])
            if not any(fragment in str(item or "") for fragment in _LEGACY_BUDGET_MISMATCH_NOTE_FRAGMENTS)
        ]
        merged_flags = list(dict.fromkeys([*existing_flags, *derived_flags]))
        merged_notes = list(dict.fromkeys([*existing_notes, *derived_notes]))
        if merged_flags != existing_flags or merged_notes != existing_notes:
            quality["issue_flags"] = merged_flags
            quality["issue_notes"] = merged_notes
            entry["quality_snapshot"] = quality

    return state


def _persist_round(entry: dict[str, Any], paths: SessionPaths) -> None:
    paths.rounds_dir.mkdir(parents=True, exist_ok=True)
    round_no = _safe_int(entry.get("round"))
    _write_json(paths.rounds_dir / f"round_{round_no:03d}.json", entry)


async def _run_round(
    *,
    round_no: int,
    factory_mod,
    codes: list[str],
    execution_mode: str,
    with_incubation: bool,
    strategy_sample_limit: int,
    universe_limit: int = 0,
) -> dict[str, Any]:
    factor_mining_run = await _run_factor_mining_once(with_incubation, round_no=round_no)
    factory_run = await _run_strategy_factory_once(
        factory_mod=factory_mod,
        codes=codes,
        execution_mode=execution_mode,
        universe_limit=universe_limit,
    )
    run_ids = list(factory_run.get("run_ids") or [])
    quality_snapshot = await _collect_run_snapshot(run_ids[0], strategy_sample_limit) if run_ids else {
        "run_id": None,
        "detail": {},
        "strategy_ids": [],
        "sampled_strategies": [],
        "blocker_summary": {},
        "issue_flags": ["missing_run_id"],
        "issue_notes": ["factory runner did not return a run_id and fallback lookup failed"],
    }
    signal_tracker_run = await _run_signal_tracker_once(with_incubation)
    incubation_run = await _run_incubation_once(with_incubation)
    factor_shelf_status = await _collect_factor_shelf_status() if with_incubation else None
    incubation_result = dict((incubation_run or {}).get("result") or {})
    paper_backlog = await _collect_paper_observation_backlog()
    incubation_intake = dict(incubation_result.get("intake") or {})
    incubation_verification = dict(incubation_result.get("verification") or {})
    incubation_pipeline = dict(incubation_result.get("pipeline") or {})
    incubation_report = dict(incubation_result.get("report") or {})
    paper_intake = dict(incubation_intake.get("paper_observation_intake") or {})
    compact_factory_result = {
        "success": bool((factory_run.get("result") or {}).get("success")),
        "error": (factory_run.get("result") or {}).get("error"),
        "data": {
            "status": dict((factory_run.get("result") or {}).get("data") or {}).get("status"),
            "run_id": dict((factory_run.get("result") or {}).get("data") or {}).get("run_id"),
            "elapsed_seconds": dict((factory_run.get("result") or {}).get("data") or {}).get("elapsed_seconds"),
        },
    }
    compact_incubation_result = {
        "started_at": (incubation_run or {}).get("started_at"),
        "completed_at": (incubation_run or {}).get("completed_at"),
        "result": {
            "status": incubation_result.get("status"),
            "elapsed_seconds": incubation_result.get("elapsed_seconds"),
            "intake": {
                "accepted": incubation_intake.get("accepted"),
                "paper_observation_intake": {
                    "scanned": paper_intake.get("scanned"),
                    "recognized": paper_intake.get("recognized"),
                    "strategy_ids": list(paper_intake.get("strategy_ids") or []),
                },
            },
            "verification": {
                "total": incubation_verification.get("total"),
                "verified": incubation_verification.get("verified"),
                "incubating_count": incubation_verification.get("incubating_count"),
                "paper_count": incubation_verification.get("paper_count"),
                "diagnostic_count": incubation_verification.get("diagnostic_count"),
                "errors": incubation_verification.get("errors"),
            },
            "pipeline": {
                "paper_count": incubation_verification.get("paper_count"),
                "count": incubation_pipeline.get("count"),
                "auto_promoted": incubation_pipeline.get("auto_promoted"),
                "stage_counts": dict(incubation_pipeline.get("stage_counts") or {}),
            },
            "report": {
                "overall_hit_rate": incubation_report.get("overall_hit_rate"),
                "overall_skill_lcb": incubation_report.get("overall_skill_lcb"),
            },
            "paper_observation_backlog": {
                "paper_observation_backlog_count": paper_backlog.get("paper_observation_backlog_count"),
                "paper_observation_backlog_status": paper_backlog.get("paper_observation_backlog_status"),
                "paper_observation_active_count": paper_backlog.get("paper_observation_active_count"),
                "paper_observation_last_recognized_at": paper_backlog.get("paper_observation_last_recognized_at"),
                "paper_observation_latest_active_at": paper_backlog.get("paper_observation_latest_active_at"),
            },
        },
    } if incubation_run else None
    return {
        "round": round_no,
        "factory_started_at": factory_run.get("started_at"),
        "factory_completed_at": factory_run.get("completed_at"),
        "factory_result": compact_factory_result,
        "run_ids": run_ids,
        "quality_snapshot": quality_snapshot,
        "factor_mining_result": factor_mining_run,
        "factor_shelf_status": factor_shelf_status,
        "signal_tracker_result": signal_tracker_run,
        "incubation_result": compact_incubation_result,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Strategy Factory repeatedly and record each round.")
    parser.add_argument("--hours", type=float, default=24.0, help="session duration in hours")
    parser.add_argument("--pause-sec", type=int, default=300, help="sleep time between completed rounds")
    parser.add_argument("--max-runs", type=int, default=0, help="stop after N rounds; 0 means no explicit limit")
    parser.add_argument("--codes", nargs="*", default=["601288"], help="target stock codes; omit value to use current default universe")
    parser.add_argument("--universe-limit", type=int, default=0, help="若 >0 且未显式传 --codes,走 dispatch 默认 universe 模式,覆盖全市场前 N 只(中等规模验证建议 200-500)")
    parser.add_argument("--execution-mode", default=DEFAULT_EXECUTION_MODE, help="strategy factory execution mode")
    parser.add_argument("--report", default=None, help="root-level markdown report path")
    parser.add_argument("--session-id", default=None, help="explicit session id")
    parser.add_argument("--strategy-sample-limit", type=int, default=3, help="number of submitted strategies to sample per round")
    parser.add_argument("--with-incubation", action="store_true", help="run one incubation-factory round after each strategy round")
    parser.add_argument("--resume", action="store_true", help="resume an existing session_id/state.json if present")
    parser.add_argument("--render-only", action="store_true", help="only reload state.json and rewrite the markdown report")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    return parser.parse_args()


async def _async_main(args: argparse.Namespace) -> int:
    factory_mod = _factory_module()
    paths = SessionPaths(
        logs_dir=_resolve_logs_dir(args.session_id),
        state_json=_resolve_logs_dir(args.session_id) / "state.json",
        report_md=_resolve_report_path(args.report),
        rounds_dir=_resolve_logs_dir(args.session_id) / "rounds",
        lock_json=_resolve_logs_dir(args.session_id) / "session.lock.json",
    )
    run_lock = SessionRunLock(paths.lock_json)
    state = _load_existing_state(paths) if bool(args.resume) or bool(args.render_only) else None
    if state is None:
        if bool(args.render_only):
            LOGGER.error("Render-only requested but no existing state found for session_id=%s", args.session_id)
            return 1
        state = _build_session_state(args, paths)
        _persist_state(state, paths)
    else:
        session = dict(state.get("session") or {})
        state["session"] = session
        session.setdefault("session_id", args.session_id)
        session.setdefault("report_path", str(paths.report_md))
        session.setdefault("logs_dir", str(paths.logs_dir))
        session.setdefault("rounds_dir", str(paths.rounds_dir))
        session.setdefault("hours", args.hours)
        session.setdefault("pause_sec", args.pause_sec)
        session.setdefault("codes", list(args.codes or []))
        session.setdefault("execution_mode", args.execution_mode)
        session.setdefault("python_executable", sys.executable)
        session.setdefault("sqlite_path", str((ROOT / "data" / "db" / "akshare_mcp.sqlite3").resolve()))
        session.setdefault("with_incubation", bool(args.with_incubation))
        session.setdefault("strategy_sample_limit", args.strategy_sample_limit)
        if not bool(args.render_only):
            _mark_session_active(state)
        await _refresh_state_strategy_persistence_metadata(state)
        _persist_state(state, paths)

    if bool(args.render_only):
        await close_db()
        LOGGER.info("Render-only refresh complete: report=%s rounds=%s", paths.report_md, len(state.get("entries") or []))
        return 0

    run_lock.acquire(session_id=args.session_id)
    try:
        session = dict(state.get("session") or {})
        session_hours = max(0.01, float(session.get("hours") or args.hours))
        session_started_at = str(session.get("started_at") or _iso_now())
        try:
            session_deadline = datetime.fromisoformat(session_started_at) + timedelta(hours=session_hours)
        except Exception:
            session_deadline = _now() + timedelta(hours=session_hours)

        round_no = len(list(state.get("entries") or []))
        while _now() < session_deadline:
            if args.max_runs > 0 and round_no >= args.max_runs:
                break
            round_no += 1
            LOGGER.info("Starting round %s", round_no)
            entry = await _run_round(
                round_no=round_no,
                factory_mod=factory_mod,
                codes=list(args.codes or []),
                execution_mode=args.execution_mode,
                with_incubation=bool(args.with_incubation),
                strategy_sample_limit=max(1, int(args.strategy_sample_limit)),
                universe_limit=max(0, int(getattr(args, "universe_limit", 0) or 0)),
            )
            state["entries"].append(entry)
            _persist_round(entry, paths)
            _persist_state(state, paths)
            await close_db()

            if args.max_runs > 0 and round_no >= args.max_runs:
                break
            if _now() >= session_deadline:
                break
            if args.pause_sec > 0:
                LOGGER.info("Sleeping %ss before next round", args.pause_sec)
                await asyncio.sleep(args.pause_sec)

        state["updated_at"] = _iso_now()
        state["session"]["completed_at"] = _iso_now()
        _persist_state(state, paths)
        await close_db()
        LOGGER.info("Session finished: rounds=%s report=%s", len(state.get("entries") or []), paths.report_md)
        return 0
    finally:
        run_lock.release()


def main() -> int:
    args = _parse_args()
    args.session_id = _resolve_session_id(args.session_id)
    logs_dir = _resolve_logs_dir(args.session_id)
    _configure_logging(logs_dir, verbose=bool(args.verbose))
    sqlite_path = (ROOT / "data" / "db" / "akshare_mcp.sqlite3").resolve()
    _apply_session_env(sqlite_path)
    load_mcp_env(override=False)
    configure_strategy_factory_runtime_services()
    LOGGER.info(
        "Session bootstrap: session_id=%s report=%s python=%s sqlite=%s",
        args.session_id,
        _resolve_report_path(args.report),
        sys.executable,
        sqlite_path,
    )
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
