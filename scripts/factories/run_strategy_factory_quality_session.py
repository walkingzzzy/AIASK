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


LOGGER = logging.getLogger("strategy_factory_quality_session")
MARKET_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_EXECUTION_MODE = "stock_first_observe_primary"


def _now() -> datetime:
    return datetime.now(MARKET_TZ)


def _iso_now() -> str:
    return _now().isoformat()


def _format_dt(value: str | None) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(str(value))
    except Exception:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MARKET_TZ)
    else:
        dt = dt.astimezone(MARKET_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S %z")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return "-"


def _json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dump(payload), encoding="utf-8")


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        synchronize = 0x00100000
        process = kernel32.OpenProcess(synchronize, False, int(pid))
        if not process:
            return False
        wait_result = kernel32.WaitForSingleObject(process, 0)
        kernel32.CloseHandle(process)
        return wait_result == 0x00000102
    except Exception:
        return True


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
    os.environ.setdefault("INCUBATION_FACTORY_PAPER_INTAKE_BATCH_LIMIT", "300")
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


def _split_run_ids(raw: Any) -> list[str]:
    value = str(raw or "").strip()
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


async def _resolve_latest_run_id_since(started_at_iso: str | None) -> str | None:
    db = get_db()
    recent = await handle_factory_runs(db, {"limit": 10})
    items = list(((recent or {}).get("data") or {}).get("items") or [])
    if not started_at_iso:
        return str((items[0] or {}).get("run_id") or "").strip() or None
    try:
        started_at = datetime.fromisoformat(started_at_iso)
    except Exception:
        started_at = None
    for item in items:
        run_id = str((item or {}).get("run_id") or "").strip()
        if not run_id:
            continue
        if started_at is None:
            return run_id
        try:
            candidate_started_at = datetime.fromisoformat(str((item or {}).get("started_at") or ""))
        except Exception:
            candidate_started_at = None
        if candidate_started_at is None or candidate_started_at >= started_at:
            return run_id
    return None


def _factory_module():
    return _load_script_module(
        "_strategy_factory_quality_run_strategy_factory",
        ROOT / "scripts" / "factories" / "run_strategy_factory.py",
    )


async def _run_strategy_factory_once(
    *,
    factory_mod,
    codes: list[str],
    execution_mode: str,
) -> dict[str, Any]:
    runner = factory_mod.StrategyFactoryRunner(
        interval_sec=300,
        run_once=True,
        target_codes=list(codes or []),
        execution_mode=execution_mode,
        dispatch_run_mode=False,
    )
    started_monotonic = time.monotonic()
    started_at = _iso_now()
    raw_result = await runner._execute_cycle()
    normalized = factory_mod._normalize_cycle_result(
        raw_result,
        elapsed_seconds=time.monotonic() - started_monotonic,
    )
    data = dict(normalized.get("data") or {})
    run_ids = _split_run_ids(data.get("run_id"))
    if not run_ids:
        fallback_run_id = await _resolve_latest_run_id_since(started_at)
        if fallback_run_id:
            run_ids = [fallback_run_id]
            data["run_id"] = fallback_run_id
            normalized["data"] = data
    return {
        "started_at": started_at,
        "completed_at": _iso_now(),
        "result": normalized,
        "run_ids": run_ids,
    }


async def _run_factor_mining_once(enabled: bool) -> dict[str, Any] | None:
    """每轮跑一轮因子挖掘,使因子超市持续有新候选供策略工厂使用。

    覆盖"四大核心持续运行"中的因子挖掘工厂 + 因子超市。失败不阻断本轮(只记录)。
    """
    if not enabled:
        return None
    started_at = _iso_now()
    try:
        from strategy_factory.runtime.factor_mining import get_factor_mining_factory

        factory = get_factor_mining_factory()
        result = await factory.run_mining_cycle(trigger="quality_session")
        return {
            "started_at": started_at,
            "completed_at": _iso_now(),
            "result": {
                "success": bool((result or {}).get("success")),
                "raw_candidate_count": int((result or {}).get("raw_candidate_count") or 0),
                "evolved_count": int((result or {}).get("evolved_count") or 0),
                "validated_count": int((result or {}).get("validated_count") or 0),
                "admitted_count": int((result or {}).get("admitted_count") or 0),
                "pool_size": int((result or {}).get("pool_size") or 0),
                "engines_used": list((result or {}).get("engines_used") or []),
                "error": (result or {}).get("error"),
            },
        }
    except Exception as exc:  # noqa: BLE001 - 因子挖掘失败不得拖垮整轮 session
        LOGGER.warning("Factor mining round failed: %s", exc)
        return {
            "started_at": started_at,
            "completed_at": _iso_now(),
            "result": {"success": False, "error": f"{type(exc).__name__}: {exc}"},
        }


async def _collect_factor_shelf_status() -> dict[str, Any]:
    """采集因子超市池状态(active/quarantine/retired + IC 健康度),用于每轮记录与质量追踪。"""
    try:
        from akshare_mcp.services.factor_mining_factory.api import get_factor_pool_gateway

        gateway = get_factor_pool_gateway()
        status = await gateway.get_pool_status()
        health = dict((status or {}).get("pool_health") or {})
        return {
            "pool_size": (status or {}).get("pool_size") or (status or {}).get("size"),
            "active_count": health.get("active_promoted_count"),
            "quarantine_count": health.get("quarantine_count"),
            "retired_count": health.get("retired_count"),
            "recent_60d_icir": health.get("recent_60d_icir"),
            "evidence_insufficient_count": health.get("evidence_insufficient_count"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


async def _run_signal_tracker_once(enabled: bool) -> dict[str, Any] | None:
    """P0-1: 在孵化前跑一轮 SignalTracker,为 observe 样本生成当日信号。

    历史断点:质量 session 只跑工厂+孵化,从不调度 SignalTracker,导致 strategy_signals
    表无新信号、孵化每轮 signals=0、纸面交易空转。此处显式驱动一轮,使信号→下单→成交链路
    在 session 内闭合。失败不阻断本轮(只记录)。
    """
    if not enabled:
        return None
    started_at = _iso_now()
    try:
        from akshare_mcp.services.signal_tracker import get_signal_tracker

        tracker = get_signal_tracker()
        result = await tracker.run_once()
        return {
            "started_at": started_at,
            "completed_at": _iso_now(),
            "result": {
                "signals_generated": int((result or {}).get("signals_generated") or 0),
                "incubation_orders": int((result or {}).get("incubation_orders") or 0),
                "forward_returns_computed": int((result or {}).get("forward_returns_computed") or 0),
                "errors": list((result or {}).get("errors") or [])[:8],
            },
        }
    except Exception as exc:  # noqa: BLE001 - 信号轮失败不得拖垮整轮 session
        LOGGER.warning("Signal tracker round failed: %s", exc)
        return {
            "started_at": started_at,
            "completed_at": _iso_now(),
            "result": {"signals_generated": 0, "error": f"{type(exc).__name__}: {exc}"},
        }


async def _run_incubation_once(enabled: bool) -> dict[str, Any] | None:
    if not enabled:
        return None
    runner = IncubationFactoryRunner(
        dry_run=False,
        owns_paper_trading=False,
    )
    started_at = _iso_now()
    result = await runner.run_once()
    return {
        "started_at": started_at,
        "completed_at": _iso_now(),
        "result": result,
    }


async def _call_optional_db_method(db, method_name: str, *args, **kwargs):
    method = getattr(db, method_name, None)
    if not callable(method):
        return None
    try:
        return await method(*args, **kwargs)
    except TypeError:
        try:
            return await method(*args)
        except Exception as exc:
            LOGGER.warning("Failed to call db.%s%s: %s", method_name, args, exc)
            return None
    except Exception as exc:
        LOGGER.warning("Failed to call db.%s%s: %s", method_name, args, exc)
        return None


async def _enrich_strategy_snapshot_with_persistence(
    strategy_snapshot: dict[str, Any],
    *,
    db,
    cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    snapshot = dict(strategy_snapshot or {})
    strategy_id = str(snapshot.get("strategy_id") or "").strip()
    if not strategy_id:
        return snapshot

    if cache is not None and strategy_id in cache:
        snapshot.update(dict(cache[strategy_id]))
        return snapshot

    strategy_row = dict(
        await _call_optional_db_method(db, "get_strategy", strategy_id) or {}
    )
    latest_quality_report = dict(
        await _call_optional_db_method(db, "get_latest_strategy_quality_report", strategy_id)
        or {}
    )
    params = dict(strategy_row.get("params") or {})
    storage_audit = dict(params.get("_storage_audit") or {})
    dropped_large_nodes = dict(storage_audit.get("dropped_large_nodes") or {})
    quality_summary = dict(latest_quality_report.get("summary") or {})
    quality_gate = dict(latest_quality_report.get("quality_gate") or {})

    def _normalized_runtime_scalar(value: Any) -> Any:
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            return value
        text = str(value or "").strip()
        if not text:
            return ""
        lowered = text.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        return lowered

    runtime_field_names = (
        "runtime_family_data_source",
        "proxy_runtime_used",
        "diagnostic_only",
        "execution_readiness_tier",
        "trade_prediction_contract_status",
        "trade_prediction_contract_observation_gap",
    )
    runtime_mismatch_fields: list[str] = []
    for field_name in runtime_field_names:
        gate_value = _normalized_runtime_scalar(quality_gate.get(field_name))
        summary_value = _normalized_runtime_scalar(quality_summary.get(field_name))
        if gate_value in (None, "") and summary_value in (None, ""):
            continue
        if gate_value != summary_value:
            runtime_mismatch_fields.append(field_name)

    diagnostics = {
        "persisted_params_storage_mode": str(storage_audit.get("storage_mode") or ""),
        "persisted_params_truncated": bool(storage_audit.get("truncated")),
        "persisted_params_original_size_bytes": _safe_int(storage_audit.get("original_size_bytes")),
        "persisted_params_dropped_large_keys": sorted(str(key) for key in dropped_large_nodes.keys()),
        "persisted_params_dropped_incubation_budget": "incubation_budget" in dropped_large_nodes,
        "persisted_observe_first_intake": params.get("observe_first_intake"),
        "persisted_incubation_budget_present": bool(params.get("incubation_budget")),
        "persisted_submission_lane": params.get("submission_lane"),
        "persisted_planned_submission_lane": params.get("planned_submission_lane"),
        "persisted_final_status": params.get("final_status"),
        "quality_report_submission_lane": quality_summary.get("submission_lane"),
        "quality_report_planned_submission_lane": quality_summary.get("planned_submission_lane"),
        "quality_report_incubation_budget_track": quality_summary.get("incubation_budget_track"),
        "quality_report_final_status": quality_summary.get("final_status"),
        "quality_report_formal_track_requested": quality_summary.get("formal_track_requested"),
        "quality_report_formal_track_eligible": quality_summary.get("formal_track_eligible"),
        "quality_report_submission_action_type": quality_summary.get("submission_action_type"),
        "quality_report_submission_action_trigger": quality_summary.get("submission_action_trigger"),
        "quality_report_runtime_bootstrap_reason": quality_summary.get("runtime_bootstrap_reason"),
        "quality_report_admission_decision": quality_summary.get("admission_decision"),
        "quality_report_runtime_family_data_source": quality_summary.get("runtime_family_data_source"),
        "quality_report_proxy_runtime_used": quality_summary.get("proxy_runtime_used"),
        "quality_report_diagnostic_only": quality_summary.get("diagnostic_only"),
        "quality_report_execution_readiness_tier": quality_summary.get("execution_readiness_tier"),
        "quality_report_trade_prediction_contract_status": quality_summary.get("trade_prediction_contract_status"),
        "quality_report_trade_prediction_contract_observation_gap": quality_summary.get(
            "trade_prediction_contract_observation_gap"
        ),
        "quality_gate_runtime_family_data_source": quality_gate.get("runtime_family_data_source"),
        "quality_gate_proxy_runtime_used": quality_gate.get("proxy_runtime_used"),
        "quality_gate_diagnostic_only": quality_gate.get("diagnostic_only"),
        "quality_gate_execution_readiness_tier": quality_gate.get("execution_readiness_tier"),
        "quality_gate_trade_prediction_contract_status": quality_gate.get("trade_prediction_contract_status"),
        "quality_gate_trade_prediction_contract_observation_gap": quality_gate.get(
            "trade_prediction_contract_observation_gap"
        ),
        "quality_runtime_context_consistent": not runtime_mismatch_fields,
        "quality_runtime_context_mismatch_fields": runtime_mismatch_fields,
    }
    snapshot.update(diagnostics)
    if cache is not None:
        cache[strategy_id] = dict(diagnostics)
    return snapshot


async def _collect_strategy_snapshot(strategy_id: str) -> dict[str, Any]:
    db = get_db()
    review_resp = await handle_review_report(db, {"strategy_id": strategy_id, "limit": 3})
    incubation_resp = await handle_incubation_overview(db, {"strategy_id": strategy_id})
    audit_resp = await handle_execution_audit_verification(db, {"strategy_id": strategy_id})
    review_data = dict((review_resp or {}).get("data") or {})
    incubation_data = dict((incubation_resp or {}).get("data") or {})
    audit_data = dict((audit_resp or {}).get("data") or {})
    review_summary = dict(review_data.get("summary") or {})
    signal_quality = dict(incubation_data.get("signal_quality") or {})
    business_admission = dict(review_data.get("business_admission_decision") or {})
    benchmark_comparison = dict(review_data.get("benchmark_comparison") or {})
    cost_sensitivity = dict(review_data.get("cost_sensitivity_summary") or {})
    review_passed = review_data.get("review_passed")
    if review_passed is None:
        review_passed = review_data.get("passed")
    strict_incubation_ready = review_data.get("strict_incubation_ready")
    if strict_incubation_ready is None:
        strict_incubation_ready = review_summary.get("strict_incubation_ready")
    audit_summary = dict(dict(audit_data.get("trade_round_trip") or {}).get("audit_summary") or {})
    snapshot = {
        "strategy_id": strategy_id,
        "review_passed": review_passed,
        "report_type": review_data.get("report_type"),
        "validation_grade": review_data.get("validation_grade") or review_summary.get("validation_grade"),
        "raw_validation_grade": review_data.get("raw_validation_grade") or review_summary.get("raw_validation_grade"),
        "validation_total_score": review_data.get("validation_total_score") or review_summary.get("validation_total_score"),
        "strategy_type": review_summary.get("strategy_type") or incubation_data.get("strategy_type"),
        "status_after_review": review_summary.get("status_after_review") or incubation_data.get("status"),
        "submission_lane": review_data.get("submission_lane") or review_summary.get("submission_lane"),
        "strict_incubation_ready": strict_incubation_ready,
        "live_candidate_ready": review_data.get("live_candidate_ready") or review_summary.get("live_candidate_ready"),
        "incubation_candidate_ready": review_data.get("incubation_candidate_ready")
        or review_summary.get("incubation_candidate_ready"),
        "admission_block_reasons": list(
            review_data.get("admission_block_reasons") or review_summary.get("admission_block_reasons") or []
        ),
        "trade_prediction_contract_status": review_data.get("trade_prediction_contract_status")
        or review_summary.get("trade_prediction_contract_status"),
        "trade_prediction_contract_reject_reasons": list(
            review_data.get("trade_prediction_contract_reject_reasons")
            or review_summary.get("trade_prediction_contract_reject_reasons")
            or []
        ),
        "evidence_gate_status": review_data.get("evidence_gate_status") or review_summary.get("evidence_gate_status"),
        "business_admission_status": business_admission.get("status"),
        "business_admission_decision": business_admission.get("decision"),
        "business_admission_reasons": list(business_admission.get("reasons") or []),
        "benchmark_oos_cagr": benchmark_comparison.get("oos_cagr"),
        "benchmark_oos_max_drawdown": benchmark_comparison.get("oos_max_drawdown"),
        "benchmark_available": benchmark_comparison.get("available"),
        "cost_review_decision": cost_sensitivity.get("review_decision"),
        "cost_post_cost_sharpe": (
            dict((list(cost_sensitivity.get("scenarios") or []) or [{}])[0]).get("post_cost_sharpe")
        ),
        "cost_total_return": (
            dict((list(cost_sensitivity.get("scenarios") or []) or [{}])[0]).get("total_return")
        ),
        "signal_coverage_ratio": signal_quality.get("coverage_ratio"),
        "primary_sample_count": signal_quality.get("primary_sample_count"),
        "primary_hit_rate": signal_quality.get("primary_hit_rate"),
        "primary_skill_lcb": signal_quality.get("primary_skill_lcb"),
        "audit_status": audit_data.get("status"),
        "audit_method": audit_data.get("method"),
        "execution_audit_gate_status": audit_data.get("execution_audit_gate_status") or audit_summary.get("execution_audit_gate_status"),
        "execution_audit_gate_reasons": list(
            audit_data.get("execution_audit_gate_reasons") or audit_summary.get("execution_audit_gate_reasons") or []
        ),
        "audit_recommendation_count": len(list(audit_data.get("recommendations") or [])),
        "audit_candidate_evidence_count": dict(audit_data.get("coverage") or {}).get("strategy_candidate_evidence_count"),
        "audit_signal_evidence_count": dict(audit_data.get("coverage") or {}).get("strategy_signal_evidence_count"),
        "forward_missing_days": list(signal_quality.get("missing_forward_days") or []),
    }
    return await _enrich_strategy_snapshot_with_persistence(snapshot, db=db)


async def _collect_paper_observation_backlog() -> dict[str, Any]:
    db = get_db()
    method = getattr(db, "get_paper_observation_backlog_status", None)
    if not callable(method):
        return {}
    try:
        return dict(await method(limit=500) or {})
    except TypeError:
        try:
            return dict(await method() or {})
        except Exception as exc:
            LOGGER.warning("Failed to collect paper observation backlog status: %s", exc)
            return {"error": str(exc)}
    except Exception as exc:
        LOGGER.warning("Failed to collect paper observation backlog status: %s", exc)
        return {"error": str(exc)}


def _normalize_blocker_reason(reason: Any) -> str:
    text = str(reason or "").strip()
    if not text:
        return ""
    return text.split(" ", 1)[0]


def _build_blocker_summary(strategies: list[dict[str, Any]]) -> dict[str, Any]:
    blocker_counts: Counter[str] = Counter()
    blocker_examples: dict[str, str] = {}
    strict_not_ready_count = 0
    strategies_with_blockers = 0

    for item in strategies:
        blockers = list(item.get("admission_block_reasons") or [])
        if item.get("strict_incubation_ready") is False:
            strict_not_ready_count += 1
        if blockers:
            strategies_with_blockers += 1
        for blocker in blockers:
            key = _normalize_blocker_reason(blocker)
            if not key:
                continue
            blocker_counts[key] += 1
            blocker_examples.setdefault(key, str(blocker))

    top_blockers = [
        {
            "reason": reason,
            "count": count,
            "example": blocker_examples.get(reason),
        }
        for reason, count in blocker_counts.most_common(10)
    ]
    return {
        "analyzed_strategy_count": len(strategies),
        "strict_not_ready_count": strict_not_ready_count,
        "strategies_with_blockers": strategies_with_blockers,
        "top_blockers": top_blockers,
    }


def _format_top_blockers(items: list[dict[str, Any]], limit: int = 5) -> str:
    if not items:
        return ""
    return "; ".join(
        f"{str(item.get('reason') or 'unknown')} x{_safe_int(item.get('count'))}"
        for item in items[: max(1, limit)]
    )


def _sort_strategy_samples(strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        list(strategies or []),
        key=lambda item: (
            item.get("validation_total_score") is not None,
            _safe_float(item.get("validation_total_score")),
            -len(list(item.get("admission_block_reasons") or [])),
        ),
        reverse=True,
    )


def _select_representative_samples(strategies: list[dict[str, Any]], limit: int = 2) -> list[dict[str, Any]]:
    ranked = _sort_strategy_samples(strategies)
    representatives: list[dict[str, Any]] = []

    for item in ranked:
        if (
            str(item.get("submission_lane") or "").strip().lower() == "observe_incubation"
            and bool(item.get("strict_incubation_ready"))
            and item.get("quality_report_formal_track_requested") is False
        ):
            representatives.append(item)

    for item in ranked:
        if item in representatives:
            continue
        if (
            str(item.get("submission_lane") or "").strip().lower() == "observe_incubation"
            and item.get("strict_incubation_ready") is False
            and _safe_float(item.get("validation_total_score")) >= 60.0
        ):
            representatives.append(item)

    unique_representatives = []
    seen_strategy_ids: set[str] = set()
    for item in representatives:
        strategy_id = str(item.get("strategy_id") or "").strip()
        if strategy_id and strategy_id in seen_strategy_ids:
            continue
        if strategy_id:
            seen_strategy_ids.add(strategy_id)
        unique_representatives.append(item)

    return unique_representatives[: max(1, limit)]


def _merge_strategy_samples(strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged_by_id: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []
    anonymous: list[dict[str, Any]] = []

    for raw_item in list(strategies or []):
        item = dict(raw_item or {})
        strategy_id = str(item.get("strategy_id") or "").strip()
        if not strategy_id:
            anonymous.append(item)
            continue
        if strategy_id not in merged_by_id:
            merged_by_id[strategy_id] = item
            ordered_ids.append(strategy_id)
            continue
        merged = dict(merged_by_id[strategy_id])
        for key, value in item.items():
            if merged.get(key) in (None, "", [], {}):
                merged[key] = value
        merged_by_id[strategy_id] = merged

    return [*anonymous, *(merged_by_id[strategy_id] for strategy_id in ordered_ids)]


def _quality_strategy_pool(quality: dict[str, Any]) -> list[dict[str, Any]]:
    return _merge_strategy_samples(
        [
            *list(quality.get("representative_samples") or []),
            *list(quality.get("sampled_strategies") or []),
        ]
    )


def _resolve_candidate_artifact(detail: dict[str, Any]) -> dict[str, Any]:
    primary = dict(detail.get("candidate_artifact") or {})
    if bool(primary.get("available")):
        return primary
    research_plane = dict(detail.get("research_plane") or {})
    plane_candidate = dict(research_plane.get("candidate_artifact") or {})
    if bool(plane_candidate.get("available")):
        return plane_candidate
    return primary


def _compact_run_detail(detail: dict[str, Any]) -> dict[str, Any]:
    summary = dict(detail.get("summary") or {})
    dedup = dict(detail.get("dedup_artifact") or {})
    candidate_artifact = _resolve_candidate_artifact(detail)
    submission_artifact = dict(detail.get("submission_artifact") or {})
    incubation_budget_summary = dict(submission_artifact.get("incubation_budget_summary") or {})
    return {
        "run_id": detail.get("run_id"),
        "status": detail.get("status"),
        "execution_mode": detail.get("execution_mode"),
        "candidates_spawned": _safe_int(detail.get("candidates_spawned")),
        "submitted": _safe_int(detail.get("submitted")),
        "readiness_score": _safe_float(detail.get("readiness_score")),
        "raw_validation_a_rate": _safe_float(detail.get("raw_validation_a_rate")),
        "raw_validation_b_rate": _safe_float(detail.get("raw_validation_b_rate")),
        "raw_validation_c_rate": _safe_float(detail.get("raw_validation_c_rate")),
        "raw_validation_d_rate": _safe_float(detail.get("raw_validation_d_rate")),
        "strict_incubation_ready_count": _safe_int(detail.get("strict_incubation_ready_count")),
        "raw_b_or_above_count": _safe_int(detail.get("raw_b_or_above_count")),
        "summary": {
            "gate_3_input": _safe_int(summary.get("gate_3_input")),
            "gate_3_passed": _safe_int(summary.get("gate_3_passed")),
            "gate_3_failed": _safe_int(summary.get("gate_3_failed")),
            "submitted": _safe_int(summary.get("submitted")),
            "submission_lane_counts": dict(summary.get("submission_lane_counts") or {}),
            "pipeline_fallback_counts": dict(summary.get("pipeline_fallback_counts") or {}),
            "gate_3_failure_topn": list(
                summary.get("gate_3_failure_topn") or summary.get("gate_3_failure_reason_topn") or []
            ),
        },
        "dedup_artifact": {
            "input_count": _safe_int(dedup.get("input_count")),
            "existing_count": _safe_int(dedup.get("existing_count")),
            "kept_count": _safe_int(dedup.get("kept_count")),
            "dropped_count": _safe_int(dedup.get("dropped_count")),
            "duplicate_level_counts": dict(dedup.get("duplicate_level_counts") or {}),
        },
        "candidate_artifact": {
            "family_counts": dict(candidate_artifact.get("family_counts") or {}),
            "candidate_origin_counts": dict(candidate_artifact.get("candidate_origin_counts") or {}),
        },
        "submission_artifact": {
            "incubation_budget_summary": {
                "formal_slots": _safe_int(incubation_budget_summary.get("formal_slots")),
                "observe_slots": _safe_int(incubation_budget_summary.get("observe_slots")),
                "formal_family_cap": _safe_int(incubation_budget_summary.get("formal_family_cap")),
                "observe_family_cap": _safe_int(incubation_budget_summary.get("observe_family_cap")),
                "exploration_reserved_slots": _safe_int(incubation_budget_summary.get("exploration_reserved_slots")),
                "feedback_available": bool(incubation_budget_summary.get("feedback_available")),
                "dominant_families": list(incubation_budget_summary.get("dominant_families") or []),
                "track_counts": dict(incubation_budget_summary.get("track_counts") or {}),
            },
            "strategy_status_counts": dict(submission_artifact.get("strategy_status_counts") or {}),
        },
    }


def _extract_issue_flags(
    detail: dict[str, Any],
    sampled_strategies: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    summary = dict(detail.get("summary") or {})
    submission_artifact = dict(detail.get("submission_artifact") or {})
    budget_summary = dict(submission_artifact.get("incubation_budget_summary") or {})
    dedup_artifact = dict(detail.get("dedup_artifact") or {})

    flags: list[str] = []
    notes: list[str] = []

    fallback_counts = dict(summary.get("pipeline_fallback_counts") or {})
    if fallback_counts:
        flags.append("pipeline_stage_fallback")
        notes.append(f"pipeline staged fallback observed: {fallback_counts}")
    if any("no_executable_specs" in str(key) for key in fallback_counts):
        flags.append("pipeline_no_executable_specs")
        notes.append(f"staged pipeline empty-spec fallback: {fallback_counts}")
    runtime_status = str(detail.get("status") or "").strip().lower()
    if runtime_status and runtime_status != "success":
        flags.append("factory_runtime_degraded")
        notes.append(f"factory runtime completed with degraded status `{runtime_status}`")
    if _safe_int(fallback_counts.get("cooldown_skip")) > 0:
        flags.append("llm_timeout_cooldown_active")
        notes.append(
            "staged pipeline entered timeout cooldown and skipped some LLM phases "
            f"(cooldown_skip={_safe_int(fallback_counts.get('cooldown_skip'))})"
        )

    if _safe_int(dedup_artifact.get("input_count")) > 0 and _safe_int(dedup_artifact.get("kept_count")) == 0:
        flags.append("dedup_zero_keep")
        notes.append(
            "all post-backtest candidates were removed by dedup "
            f"(input={_safe_int(dedup_artifact.get('input_count'))}, existing={_safe_int(dedup_artifact.get('existing_count'))})"
        )

    if _safe_int(detail.get("candidates_spawned")) > 0 and _safe_int(detail.get("submitted")) == 0:
        flags.append("no_submission_after_generation")
        notes.append(
            "factory generated candidates but produced no submissions "
            f"(spawned={_safe_int(detail.get('candidates_spawned'))}, submitted=0)"
        )

    submission_lane_counts = dict(summary.get("submission_lane_counts") or submission_artifact.get("submission_lane_counts") or {})
    submitted = _safe_int(detail.get("submitted") or summary.get("submitted"))
    observe_only_count = _safe_int(submission_lane_counts.get("observe_incubation"))
    if submitted > 0 and observe_only_count >= submitted:
        flags.append("observe_only_submission")
        notes.append(f"all submitted strategies were routed to observe_incubation ({observe_only_count}/{submitted})")
        if _safe_int(summary.get("gate_3_passed")) > 0:
            flags.append("gate_pass_but_observe_only")
            notes.append(
                "gate_3 reported passed candidates, but the completed round still routed all submissions to observe_incubation "
                f"(gate_3_passed={_safe_int(summary.get('gate_3_passed'))}, submitted={submitted})"
            )

    budget_track_counts = dict(budget_summary.get("track_counts") or {})
    if _safe_int(budget_track_counts.get("deferred_budget_queue")) > 0 and (
        _safe_int(budget_track_counts.get("formal_incubation")) == 0
        and _safe_int(budget_track_counts.get("observe_incubation")) == 0
    ):
        final_lane_total = sum(
            _safe_int(submission_lane_counts.get(name))
            for name in (
                "formal_incubation",
                "observe_incubation",
                "diagnostic_observation",
                "live_ready_review",
                "deferred_submission",
            )
        )
        if final_lane_total > 0:
            flags.append("budget_summary_final_lane_mismatch")
            notes.append(
                "incubation budget summary stayed in deferred_budget_queue, but final admission still produced concrete submission lanes; "
                "this points to a plan-vs-final routing contract mismatch rather than a pure no-track condition "
                f"(budget_track_counts={budget_track_counts}, final_lane_counts={submission_lane_counts})"
            )
        else:
            flags.append("budget_queue_without_track_assignment")
            notes.append(
                "incubation budget summary shows candidates staying in deferred_budget_queue with no formal/observe budget assignment "
                f"({budget_track_counts})"
            )

    if _safe_int(detail.get("strict_incubation_ready_count")) == 0 and _safe_int(detail.get("raw_b_or_above_count")) > 0:
        flags.append("strict_ready_zero_despite_raw_b")
        notes.append(
            "there are B-or-above strategies, but none reached strict incubation readiness "
            f"(raw_b_or_above={_safe_int(detail.get('raw_b_or_above_count'))})"
        )

    if _safe_float(detail.get("raw_validation_d_rate")) >= 0.5:
        flags.append("quality_d_heavy")
        notes.append(f"D-grade share is high ({_pct(detail.get('raw_validation_d_rate'))})")

    if any(bool(item.get("persisted_params_truncated")) for item in sampled_strategies):
        flags.append("strategy_params_storage_truncated")
        notes.append(
            "sampled strategy rows were stored in compact_json mode, so row-level params were truncated in SQLite "
            "and cannot be treated as complete persistence evidence"
        )

    if any(
        bool(item.get("persisted_params_dropped_incubation_budget"))
        and not bool(item.get("persisted_incubation_budget_present"))
        for item in sampled_strategies
    ):
        flags.append("strategy_params_budget_metadata_compacted_away")
        notes.append(
            "sampled strategy rows dropped `incubation_budget` from `strategies.params` during JSON compaction, "
            "so planner budget selections are not directly visible on persisted strategy rows"
        )

    if any(
        str(item.get("quality_report_submission_lane") or "").strip()
        and not str(item.get("quality_report_planned_submission_lane") or "").strip()
        and not str(item.get("quality_report_incubation_budget_track") or "").strip()
        for item in sampled_strategies
    ):
        flags.append("quality_report_plan_metadata_missing")
        notes.append(
            "sampled submission quality reports preserve the final `submission_lane`, but omit "
            "`planned_submission_lane` and `incubation_budget_track`, leaving a plan-vs-final metadata gap"
        )

    if any(
        str(item.get("quality_report_submission_lane") or "").strip()
        and not str(item.get("persisted_submission_lane") or "").strip()
        for item in sampled_strategies
    ):
        flags.append("strategy_row_submission_metadata_missing")
        notes.append(
            "sampled strategy rows do not retain `submission_lane` / `planned_submission_lane` in `strategies.params` "
            "even though submission quality reports record a final submission lane"
        )

    if any(item.get("quality_runtime_context_consistent") is False for item in sampled_strategies):
        flags.append("quality_report_runtime_context_mismatch")
        first_mismatch = next(
            (item for item in sampled_strategies if item.get("quality_runtime_context_consistent") is False),
            None,
        )
        mismatch_fields = list((first_mismatch or {}).get("quality_runtime_context_mismatch_fields") or [])
        notes.append(
            "sampled strategy quality reports still show runtime context mismatch between `quality_gate` and "
            "`summary`; blocker attribution cannot be trusted for those rows until the persisted runtime fields align "
            f"(fields={mismatch_fields})"
        )

    if any(
        bool(item.get("strict_incubation_ready"))
        and str(item.get("quality_report_submission_lane") or "").strip().lower() == "observe_incubation"
        and item.get("quality_report_formal_track_requested") is False
        for item in sampled_strategies
    ):
        flags.append("strict_ready_but_formal_not_requested")
        notes.append(
            "at least one sampled strategy reached `strict_incubation_ready=true`, but the persisted submission review still "
            "shows `formal_track_requested=false` and final lane `observe_incubation`; this points to observe-first pre-routing "
            "winning before formal admission is even requested"
        )
        first_match = next(
            (
                item
                for item in sampled_strategies
                if bool(item.get("strict_incubation_ready"))
                and str(item.get("quality_report_submission_lane") or "").strip().lower() == "observe_incubation"
                and item.get("quality_report_formal_track_requested") is False
            ),
            None,
        )
        if first_match:
            notes.append(
                "strict-ready observe sample: "
                f"{str(first_match.get('strategy_id') or '-')} "
                f"(trigger={str(first_match.get('quality_report_submission_action_trigger') or '-')}, "
                f"runtime_reason={str(first_match.get('quality_report_runtime_bootstrap_reason') or '-')})"
            )

    if any(
        bool(item.get("strict_incubation_ready"))
        and bool(item.get("persisted_observe_first_intake"))
        and str(item.get("quality_report_submission_lane") or "").strip().lower() == "observe_incubation"
        and item.get("quality_report_formal_track_requested") is False
        for item in sampled_strategies
    ):
        flags.append("strict_ready_observe_first_override")
        notes.append(
            "the strict-ready observe sample still carries `observe_first_intake=true`, which strengthens the case that "
            "observe-first pre-routing is overriding formal-track request before final admission"
        )

    if any(_safe_float(item.get("signal_coverage_ratio")) == 0.0 for item in sampled_strategies):
        flags.append("no_forward_signal_coverage_yet")
        notes.append("sampled submitted strategies still have zero forward-observation coverage")

    if any(str(item.get("audit_status") or "").strip().lower() == "needs_attention" for item in sampled_strategies):
        flags.append("execution_audit_needs_attention")
        notes.append("execution audit verification still reports needs_attention on sampled strategies")

    return list(dict.fromkeys(flags)), notes


async def _collect_run_snapshot(run_id: str, strategy_sample_limit: int) -> dict[str, Any]:
    db = get_db()
    detail_resp = await handle_factory_run_detail(db, {"run_id": run_id, "artifact_mode": "summary"})
    detail = dict((detail_resp or {}).get("data") or {})

    strategy_ids: list[str] = []
    for gate_name in ("gate_b", "gate_c"):
        gate_payload = dict(detail.get(gate_name) or {})
        for strategy_id in list(gate_payload.get("artifact_ids") or []):
            sid = str(strategy_id or "").strip()
            if sid and sid not in strategy_ids:
                strategy_ids.append(sid)

    analyzed_strategies: list[dict[str, Any]] = []
    analysis_limit = min(len(strategy_ids), max(10, max(1, strategy_sample_limit)))
    for strategy_id in strategy_ids[:analysis_limit]:
        analyzed_strategies.append(await _collect_strategy_snapshot(strategy_id))

    ranked_strategies = _sort_strategy_samples(analyzed_strategies)
    sampled_strategies = ranked_strategies[: max(1, strategy_sample_limit)]
    representative_samples = _select_representative_samples(ranked_strategies, limit=2)
    blocker_summary = _build_blocker_summary(analyzed_strategies)

    issue_flags, issue_notes = _extract_issue_flags(
        detail,
        _merge_strategy_samples([*representative_samples, *sampled_strategies]),
    )
    top_blockers = list(blocker_summary.get("top_blockers") or [])
    if top_blockers:
        issue_notes.append(
            "formal admission blockers among analyzed strategies: "
            f"{_format_top_blockers(top_blockers)}"
        )
    return {
        "run_id": run_id,
        "detail": _compact_run_detail(detail),
        "strategy_ids": strategy_ids,
        "sampled_strategies": sampled_strategies,
        "representative_samples": representative_samples,
        "blocker_summary": blocker_summary,
        "issue_flags": issue_flags,
        "issue_notes": issue_notes,
    }


async def _refresh_state_strategy_persistence_metadata(state: dict[str, Any]) -> bool:
    db = get_db()
    cache: dict[str, dict[str, Any]] = {}
    changed = False

    for entry in list(state.get("entries") or []):
        quality = dict(entry.get("quality_snapshot") or {})
        sampled_strategies = list(quality.get("sampled_strategies") or [])
        existing_representatives = list(quality.get("representative_samples") or [])
        if not sampled_strategies and not existing_representatives:
            continue

        refreshed_sampled = [
            await _enrich_strategy_snapshot_with_persistence(item, db=db, cache=cache)
            for item in sampled_strategies
        ]
        sampled_by_id = {
            str(item.get("strategy_id") or "").strip(): dict(item)
            for item in refreshed_sampled
            if str(item.get("strategy_id") or "").strip()
        }
        refreshed_existing_representatives: list[dict[str, Any]] = []
        for item in existing_representatives:
            strategy_id = str(item.get("strategy_id") or "").strip()
            if strategy_id and strategy_id in sampled_by_id:
                refreshed_existing_representatives.append(dict(sampled_by_id[strategy_id]))
                continue
            refreshed_existing_representatives.append(
                await _enrich_strategy_snapshot_with_persistence(item, db=db, cache=cache)
            )
        representative_pool = list(refreshed_sampled)
        seen_ids = {
            str(item.get("strategy_id") or "").strip()
            for item in representative_pool
            if str(item.get("strategy_id") or "").strip()
        }
        for item in refreshed_existing_representatives:
            strategy_id = str(item.get("strategy_id") or "").strip()
            if strategy_id and strategy_id in seen_ids:
                continue
            if strategy_id:
                seen_ids.add(strategy_id)
            representative_pool.append(item)
        refreshed_representatives = _select_representative_samples(representative_pool, limit=2)

        detail = dict(quality.get("detail") or {})
        derived_flags, derived_notes = _extract_issue_flags(
            detail,
            _merge_strategy_samples([*refreshed_representatives, *refreshed_sampled]),
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

        if (
            refreshed_sampled != sampled_strategies
            or refreshed_representatives != existing_representatives
            or merged_flags != existing_flags
            or merged_notes != existing_notes
        ):
            quality["sampled_strategies"] = refreshed_sampled
            quality["representative_samples"] = refreshed_representatives
            quality["issue_flags"] = merged_flags
            quality["issue_notes"] = merged_notes
            entry["quality_snapshot"] = quality
            changed = True

    return changed


def _sample_strategy_table(strategies: list[dict[str, Any]]) -> list[str]:
    if not strategies:
        return ["无关联策略快照。"]
    lines = [
        "| strategy_id | family | grade | score | review | signal_coverage | audit | status |",
        "| --- | --- | --- | ---: | --- | ---: | --- | --- |",
    ]
    for item in strategies:
        lines.append(
            "| {strategy_id} | {family} | {grade} | {score} | {review} | {coverage} | {audit} | {status} |".format(
                strategy_id=str(item.get("strategy_id") or "-"),
                family=str(item.get("strategy_type") or "-"),
                grade=str(item.get("validation_grade") or "-"),
                score=(
                    "-"
                    if item.get("validation_total_score") is None
                    else f"{_safe_float(item.get('validation_total_score')):.2f}"
                ),
                review=(
                    "-"
                    if item.get("review_passed") is None
                    else ("pass" if bool(item.get("review_passed")) else "fail")
                ),
                coverage=(
                    "-"
                    if item.get("signal_coverage_ratio") is None
                    else f"{_safe_float(item.get('signal_coverage_ratio')):.2f}"
                ),
                audit=str(item.get("audit_status") or "-"),
                status=str(item.get("status_after_review") or "-"),
            )
        )
    return lines


def _render_representative_samples(strategies: list[dict[str, Any]]) -> list[str]:
    if not strategies:
        return []
    lines = ["", "代表样本诊断"]
    for item in strategies:
        blockers = " | ".join(list(item.get("admission_block_reasons") or [])[:4]) or "-"
        lines.append(
            "- `{strategy_id}` grade={grade} score={score:.2f} lane={lane} strict_ready={strict_ready} "
            "forward_coverage={coverage} audit={audit} exec_gate={exec_gate} post_cost_sharpe={post_cost_sharpe} "
            "oos_cagr={oos_cagr} evidence_gate={evidence_gate}".format(
                strategy_id=str(item.get("strategy_id") or "-"),
                grade=str(item.get("validation_grade") or "-"),
                score=_safe_float(item.get("validation_total_score")),
                lane=str(item.get("submission_lane") or "-"),
                strict_ready=str(bool(item.get("strict_incubation_ready"))).lower(),
                coverage=(
                    "-"
                    if item.get("signal_coverage_ratio") is None
                    else f"{_safe_float(item.get('signal_coverage_ratio')):.2f}"
                ),
                audit=str(item.get("audit_status") or "-"),
                exec_gate=str(item.get("execution_audit_gate_status") or "-"),
                post_cost_sharpe=(
                    "-"
                    if item.get("cost_post_cost_sharpe") is None
                    else f"{_safe_float(item.get('cost_post_cost_sharpe')):.3f}"
                ),
                oos_cagr=(
                    "-"
                    if item.get("benchmark_oos_cagr") is None
                    else _pct(item.get("benchmark_oos_cagr"))
                ),
                evidence_gate=str(item.get("evidence_gate_status") or "-"),
            )
        )
        lines.append(f"- 核心阻塞: {blockers}")
        if bool(item.get("persisted_params_truncated")) or str(item.get("quality_report_submission_lane") or "").strip():
            lines.append(
                "- 持久化痕迹: params_storage={storage_mode} dropped_budget={dropped_budget} "
                "persisted_lane={persisted_lane} quality_lane={quality_lane} planned_lane={planned_lane} "
                "budget_track={budget_track} formal_requested={formal_requested} strict_ready={strict_ready}".format(
                    storage_mode=str(item.get("persisted_params_storage_mode") or "-"),
                    dropped_budget=str(bool(item.get("persisted_params_dropped_incubation_budget"))).lower(),
                    persisted_lane=str(item.get("persisted_submission_lane") or "-"),
                    quality_lane=str(item.get("quality_report_submission_lane") or "-"),
                    planned_lane=str(item.get("quality_report_planned_submission_lane") or "-"),
                    budget_track=str(item.get("quality_report_incubation_budget_track") or "-"),
                    formal_requested=str(item.get("quality_report_formal_track_requested")).lower(),
                    strict_ready=str(bool(item.get("strict_incubation_ready"))).lower(),
                )
            )
        if item.get("quality_runtime_context_consistent") is False:
            lines.append(
                "- runtime 一致性: gate_vs_summary_mismatch="
                + ", ".join(str(name) for name in list(item.get("quality_runtime_context_mismatch_fields") or []))
            )
            lines.append(
                "- runtime 对照: "
                "gate_family={gate_family} summary_family={summary_family} "
                "gate_proxy={gate_proxy} summary_proxy={summary_proxy} "
                "gate_diag={gate_diag} summary_diag={summary_diag} "
                "gate_tier={gate_tier} summary_tier={summary_tier}".format(
                    gate_family=str(item.get("quality_gate_runtime_family_data_source") or "-"),
                    summary_family=str(item.get("quality_report_runtime_family_data_source") or "-"),
                    gate_proxy=str(item.get("quality_gate_proxy_runtime_used")),
                    summary_proxy=str(item.get("quality_report_proxy_runtime_used")),
                    gate_diag=str(item.get("quality_gate_diagnostic_only")),
                    summary_diag=str(item.get("quality_report_diagnostic_only")),
                    gate_tier=str(item.get("quality_gate_execution_readiness_tier") or "-"),
                    summary_tier=str(item.get("quality_report_execution_readiness_tier") or "-"),
                )
            )
    lines.append("")
    return lines


def _strict_ready_example_payload(
    entry: dict[str, Any],
    detail: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any]:
    return {
        "round": _safe_int(entry.get("round")),
        "run_id": str(detail.get("run_id") or entry.get("run_id") or ""),
        "strategy_id": str(item.get("strategy_id") or ""),
        "validation_grade": item.get("validation_grade"),
        "validation_total_score": item.get("validation_total_score"),
        "submission_lane": item.get("submission_lane"),
        "quality_report_submission_lane": item.get("quality_report_submission_lane"),
        "quality_report_planned_submission_lane": item.get("quality_report_planned_submission_lane"),
        "quality_report_incubation_budget_track": item.get("quality_report_incubation_budget_track"),
        "quality_report_formal_track_requested": item.get("quality_report_formal_track_requested"),
        "quality_report_formal_track_eligible": item.get("quality_report_formal_track_eligible"),
        "quality_report_submission_action_trigger": item.get("quality_report_submission_action_trigger"),
        "quality_report_runtime_bootstrap_reason": item.get("quality_report_runtime_bootstrap_reason"),
        "persisted_observe_first_intake": item.get("persisted_observe_first_intake"),
        "persisted_submission_lane": item.get("persisted_submission_lane"),
        "persisted_params_storage_mode": item.get("persisted_params_storage_mode"),
        "persisted_params_dropped_incubation_budget": item.get("persisted_params_dropped_incubation_budget"),
        "strict_incubation_ready": item.get("strict_incubation_ready"),
        "admission_block_reasons": list(item.get("admission_block_reasons") or []),
    }


def _bool_text(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(bool(value)).lower()


def _format_strict_ready_example_evidence(example: dict[str, Any]) -> str:
    if not example:
        return ""
    parts: list[str] = []
    round_no = _safe_int(example.get("round"))
    if round_no > 0:
        parts.append(f"example_round={round_no}")
    strategy_id = str(example.get("strategy_id") or "").strip()
    if strategy_id:
        parts.append(f"example_strategy_id={strategy_id}")
    grade = str(example.get("validation_grade") or "").strip()
    if grade:
        parts.append(f"example_grade={grade}")
    score = example.get("validation_total_score")
    if score is not None:
        parts.append(f"example_score={_safe_float(score):.2f}")
    lane = str(
        example.get("quality_report_submission_lane")
        or example.get("submission_lane")
        or ""
    ).strip()
    if lane:
        parts.append(f"example_lane={lane}")
    parts.append(
        "example_formal_requested="
        f"{_bool_text(example.get('quality_report_formal_track_requested'))}"
    )
    parts.append(
        "example_observe_first="
        f"{_bool_text(example.get('persisted_observe_first_intake'))}"
    )
    trigger = str(example.get("quality_report_submission_action_trigger") or "").strip()
    if trigger:
        parts.append(f"example_trigger={trigger}")
    runtime_reason = str(example.get("quality_report_runtime_bootstrap_reason") or "").strip()
    if runtime_reason:
        parts.append(f"example_runtime_reason={runtime_reason}")
    return ", ".join(parts)


def _render_strict_ready_example(example: dict[str, Any]) -> list[str]:
    if not example:
        return []
    blockers = " | ".join(list(example.get("admission_block_reasons") or [])[:4]) or "-"
    lane = str(
        example.get("quality_report_submission_lane")
        or example.get("submission_lane")
        or "-"
    )
    lines = [
        f"- round={_safe_int(example.get('round'))} strategy=`{str(example.get('strategy_id') or '-')}` "
        f"grade={str(example.get('validation_grade') or '-')} "
        f"score={_safe_float(example.get('validation_total_score')):.2f} "
        f"lane={lane} strict_ready={_bool_text(example.get('strict_incubation_ready'))} "
        f"formal_requested={_bool_text(example.get('quality_report_formal_track_requested'))} "
        f"observe_first={_bool_text(example.get('persisted_observe_first_intake'))}"
    ]
    trace_parts: list[str] = []
    trigger = str(example.get("quality_report_submission_action_trigger") or "").strip()
    if trigger:
        trace_parts.append(f"trigger={trigger}")
    runtime_reason = str(example.get("quality_report_runtime_bootstrap_reason") or "").strip()
    if runtime_reason:
        trace_parts.append(f"runtime_reason={runtime_reason}")
    budget_track = str(example.get("quality_report_incubation_budget_track") or "").strip()
    if budget_track:
        trace_parts.append(f"budget_track={budget_track}")
    planned_lane = str(example.get("quality_report_planned_submission_lane") or "").strip()
    if planned_lane:
        trace_parts.append(f"planned_lane={planned_lane}")
    persisted_lane = str(example.get("persisted_submission_lane") or "").strip()
    if persisted_lane:
        trace_parts.append(f"persisted_lane={persisted_lane}")
    storage_mode = str(example.get("persisted_params_storage_mode") or "").strip()
    if storage_mode:
        trace_parts.append(f"params_storage={storage_mode}")
    if trace_parts:
        lines.append("- 运行轨迹: " + ", ".join(trace_parts))
    lines.append(f"- 核心阻塞: {blockers}")
    return lines


def _render_entry(entry: dict[str, Any], *, fallback_execution_mode: str | None = None) -> list[str]:
    factory_result = dict(entry.get("factory_result") or {})
    factory_data = dict(factory_result.get("data") or {})
    quality = dict(entry.get("quality_snapshot") or {})
    detail = dict(quality.get("detail") or {})
    summary = dict(detail.get("summary") or {})
    dedup = dict(detail.get("dedup_artifact") or {})
    candidate_artifact = dict(detail.get("candidate_artifact") or {})
    submission_artifact = dict(detail.get("submission_artifact") or {})
    incubation_budget_summary = dict(submission_artifact.get("incubation_budget_summary") or {})
    incubation_result = dict((entry.get("incubation_result") or {}).get("result") or {})
    incubation_intake = dict(incubation_result.get("intake") or {})
    paper_intake = dict(incubation_intake.get("paper_observation_intake") or {})
    incubation_verification = dict(incubation_result.get("verification") or {})
    incubation_pipeline = dict(incubation_result.get("pipeline") or {})
    incubation_report = dict(incubation_result.get("report") or {})
    paper_backlog = dict(incubation_result.get("paper_observation_backlog") or {})
    sampled_strategies = list(quality.get("sampled_strategies") or [])
    representative_samples = list(
        quality.get("representative_samples") or _select_representative_samples(sampled_strategies, limit=2)
    )
    blocker_summary = dict(quality.get("blocker_summary") or {})
    resolved_execution_mode = str(detail.get("execution_mode") or fallback_execution_mode or "-")

    lines = [
        f"### 第 {entry.get('round')} 轮",
        f"- 工厂开始: {_format_dt(entry.get('factory_started_at'))}",
        f"- 工厂结束: {_format_dt(entry.get('factory_completed_at'))}",
        f"- 工厂状态: `{str(factory_data.get('status') or factory_result.get('status') or 'unknown')}`",
        f"- run_id: `{detail.get('run_id') or factory_data.get('run_id') or '-'}`",
        f"- execution_mode: `{resolved_execution_mode}`",
        (
            "- 工厂核心漏斗: "
            f"spawned={_safe_int(detail.get('candidates_spawned'))}, "
            f"dedup_kept={_safe_int(dedup.get('kept_count'))}/{_safe_int(dedup.get('input_count'))}, "
            f"submitted={_safe_int(detail.get('submitted'))}, "
            f"G3={_safe_int(summary.get('gate_3_passed'))}/{_safe_int(summary.get('gate_3_input'))}"
        ),
        (
            "- 质量概览: "
            f"readiness={_safe_float(detail.get('readiness_score')):.2f}, "
            f"raw A/B/C/D={_pct(detail.get('raw_validation_a_rate'))}/"
            f"{_pct(detail.get('raw_validation_b_rate'))}/"
            f"{_pct(detail.get('raw_validation_c_rate'))}/"
            f"{_pct(detail.get('raw_validation_d_rate'))}"
        ),
        (
            "- 提交通道: "
            f"{json.dumps(summary.get('submission_lane_counts') or {}, ensure_ascii=False)}; "
            f"pipeline_fallback={json.dumps(summary.get('pipeline_fallback_counts') or {}, ensure_ascii=False)}"
        ),
        (
            "- Dedup: "
            f"existing={_safe_int(dedup.get('existing_count'))}, "
            f"kept={_safe_int(dedup.get('kept_count'))}, "
            f"dropped={_safe_int(dedup.get('dropped_count'))}, "
            f"duplicate_levels={json.dumps(dedup.get('duplicate_level_counts') or {}, ensure_ascii=False)}"
        ),
        (
            "- 候选来源: "
            f"families={json.dumps(candidate_artifact.get('family_counts') or {}, ensure_ascii=False)}, "
            f"origins={json.dumps(candidate_artifact.get('candidate_origin_counts') or {}, ensure_ascii=False)}"
        ),
        (
            "- 预算轨道摘要: "
            f"track_counts={json.dumps(incubation_budget_summary.get('track_counts') or {}, ensure_ascii=False)}, "
            f"formal_slots={_safe_int(incubation_budget_summary.get('formal_slots'))}, "
            f"observe_slots={_safe_int(incubation_budget_summary.get('observe_slots'))}, "
            f"dominant_families={json.dumps(incubation_budget_summary.get('dominant_families') or [], ensure_ascii=False)}"
        ),
    ]

    issue_flags = list(quality.get("issue_flags") or [])
    if issue_flags:
        lines.append("- 问题标记: " + ", ".join(f"`{item}`" for item in issue_flags))
    for note in list(quality.get("issue_notes") or []):
        lines.append(f"- 观察到的问题: {note}")
    top_blockers = list(blocker_summary.get("top_blockers") or [])
    if top_blockers:
        lines.append(
            "- formal 准入阻塞: "
            f"analyzed={_safe_int(blocker_summary.get('analyzed_strategy_count'))}, "
            f"strict_not_ready={_safe_int(blocker_summary.get('strict_not_ready_count'))}, "
            f"top={_format_top_blockers(top_blockers)}"
        )

    gate_fail_topn = list(summary.get("gate_3_failure_topn") or summary.get("gate_3_failure_reason_topn") or [])
    if gate_fail_topn:
        reason_text = "; ".join(
            f"{item.get('reason_code') or item.get('reason') or 'unknown'} x{_safe_int(item.get('count'))}"
            for item in gate_fail_topn[:5]
        )
        lines.append(f"- Gate 3 失败Top: {reason_text}")

    if incubation_result:
        lines.extend(
            [
                f"- 孵化状态: `{incubation_result.get('status', 'unknown')}`",
                (
                    "- 孵化摘要: "
                    f"accepted={_safe_int(dict(incubation_result.get('intake') or {}).get('accepted'))}, "
                    f"verified={_safe_int(dict(incubation_result.get('verification') or {}).get('verified'))}, "
                    f"paper_count={_safe_int(incubation_pipeline.get('paper_count'))}, "
                    f"stage_counts={json.dumps(incubation_pipeline.get('stage_counts') or {}, ensure_ascii=False)}"
                ),
                (
                    "- 孵化质量: "
                    f"overall_hit_rate={_pct(incubation_report.get('overall_hit_rate'))}, "
                    f"overall_skill_lcb={incubation_report.get('overall_skill_lcb', '-')}"
                ),
            ]
        )

    if incubation_result:
        lines.extend(
            [
                (
                    "- observe intake evidence: "
                    f"paper_scanned={_safe_int(paper_intake.get('scanned'))}, "
                    f"paper_recognized={_safe_int(paper_intake.get('recognized'))}"
                ),
                (
                    "- observe active pool: "
                    f"verified={_safe_int(incubation_verification.get('verified'))}/"
                    f"{_safe_int(incubation_verification.get('total'))}, "
                    f"incubating={_safe_int(incubation_verification.get('incubating_count'))}, "
                    f"paper_active={_safe_int(incubation_verification.get('paper_count'))}, "
                    f"diagnostic={_safe_int(incubation_verification.get('diagnostic_count'))}, "
                    f"errors={_safe_int(incubation_verification.get('errors'))}"
                ),
                (
                    "- paper backlog evidence: "
                    f"status=`{paper_backlog.get('paper_observation_backlog_status') or '-'}`, "
                    f"active={_safe_int(paper_backlog.get('paper_observation_active_count'))}, "
                    f"stage_paper_only={_safe_int(paper_backlog.get('paper_observation_backlog_count'))}, "
                    f"last_recognized_at={_format_dt(paper_backlog.get('paper_observation_last_recognized_at'))}"
                ),
                (
                    "- promotion evidence: "
                    f"auto_promoted={_safe_int(incubation_pipeline.get('auto_promoted'))}, "
                    f"stage_counts={json.dumps(incubation_pipeline.get('stage_counts') or {}, ensure_ascii=False)}"
                ),
            ]
        )

    lines.append("")
    lines.append("关联策略抽样")
    lines.extend(_sample_strategy_table(sampled_strategies))
    lines.extend(_render_representative_samples(representative_samples))
    lines.append("")
    return lines


def _build_aggregate_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    issue_counter: Counter[str] = Counter()
    gate_reason_counter: Counter[str] = Counter()
    blocker_reason_counter: Counter[str] = Counter()
    submitted_total = 0
    gate_input_total = 0
    gate_pass_total = 0
    spawned_total = 0
    observe_only_rounds = 0
    gate_pass_but_observe_only_rounds = 0
    paper_intake_rounds = 0
    paper_recognized_total = 0
    last_gate_pass_but_observe_only_example: dict[str, Any] = {}
    last_strict_ready_observe_example: dict[str, Any] = {}
    last_strict_ready_formal_missing_example: dict[str, Any] = {}
    last_strict_ready_observe_override_example: dict[str, Any] = {}

    for entry in entries:
        quality = dict(entry.get("quality_snapshot") or {})
        detail = dict(quality.get("detail") or {})
        summary = dict(detail.get("summary") or {})
        blocker_summary = dict(quality.get("blocker_summary") or {})
        incubation_result = dict((entry.get("incubation_result") or {}).get("result") or {})
        paper_intake = dict(dict(incubation_result.get("intake") or {}).get("paper_observation_intake") or {})
        issue_counter.update(list(quality.get("issue_flags") or []))
        spawned_total += _safe_int(detail.get("candidates_spawned"))
        submitted_total += _safe_int(detail.get("submitted"))
        gate_input_total += _safe_int(summary.get("gate_3_input"))
        gate_pass_total += _safe_int(summary.get("gate_3_passed"))
        lane_counts = dict(summary.get("submission_lane_counts") or {})
        if _safe_int(detail.get("submitted")) > 0 and _safe_int(lane_counts.get("observe_incubation")) >= _safe_int(detail.get("submitted")):
            observe_only_rounds += 1
            if _safe_int(summary.get("gate_3_passed")) > 0:
                gate_pass_but_observe_only_rounds += 1
                submission_artifact = dict(detail.get("submission_artifact") or {})
                budget_summary = dict(submission_artifact.get("incubation_budget_summary") or {})
                last_gate_pass_but_observe_only_example = {
                    "round": _safe_int(entry.get("round")),
                    "run_id": str(detail.get("run_id") or entry.get("run_id") or ""),
                    "execution_mode": str(detail.get("execution_mode") or ""),
                    "gate_3_passed": _safe_int(summary.get("gate_3_passed")),
                    "submitted": _safe_int(detail.get("submitted") or summary.get("submitted")),
                    "submission_lane_counts": dict(lane_counts),
                    "budget_track_counts": dict(budget_summary.get("track_counts") or {}),
                    "strategy_status_counts": dict(submission_artifact.get("strategy_status_counts") or {}),
                }
        paper_recognized = _safe_int(paper_intake.get("recognized"))
        paper_recognized_total += paper_recognized
        if paper_recognized > 0:
            paper_intake_rounds += 1
        for item in _quality_strategy_pool(quality):
            lane = str(
                item.get("quality_report_submission_lane")
                or item.get("submission_lane")
                or ""
            ).strip().lower()
            if bool(item.get("strict_incubation_ready")) and lane == "observe_incubation":
                example = _strict_ready_example_payload(entry, detail, item)
                last_strict_ready_observe_example = example
                if item.get("quality_report_formal_track_requested") is False:
                    last_strict_ready_formal_missing_example = example
                if (
                    item.get("quality_report_formal_track_requested") is False
                    and bool(item.get("persisted_observe_first_intake"))
                ):
                    last_strict_ready_observe_override_example = example
        for item in list(summary.get("gate_3_failure_topn") or summary.get("gate_3_failure_reason_topn") or []):
            key = str(item.get("reason_code") or item.get("reason") or "").strip()
            if key:
                gate_reason_counter[key] += _safe_int(item.get("count"), 1)
        for item in list(blocker_summary.get("top_blockers") or []):
            key = str(item.get("reason") or "").strip()
            if key:
                blocker_reason_counter[key] += _safe_int(item.get("count"), 1)

    return {
        "issue_counts": issue_counter,
        "gate_reason_counts": gate_reason_counter,
        "blocker_reason_counts": blocker_reason_counter,
        "spawned_total": spawned_total,
        "submitted_total": submitted_total,
        "gate_input_total": gate_input_total,
        "gate_pass_total": gate_pass_total,
        "observe_only_rounds": observe_only_rounds,
        "gate_pass_but_observe_only_rounds": gate_pass_but_observe_only_rounds,
        "paper_intake_rounds": paper_intake_rounds,
        "paper_recognized_total": paper_recognized_total,
        "last_gate_pass_but_observe_only_example": last_gate_pass_but_observe_only_example,
        "last_strict_ready_observe_example": last_strict_ready_observe_example,
        "last_strict_ready_formal_missing_example": last_strict_ready_formal_missing_example,
        "last_strict_ready_observe_override_example": last_strict_ready_observe_override_example,
    }


def _build_priority_findings(
    entries: list[dict[str, Any]],
    aggregate: dict[str, Any],
    session: dict[str, Any],
    last_detail: dict[str, Any],
    last_incubation_result: dict[str, Any],
    last_paper_backlog: dict[str, Any],
) -> list[dict[str, str]]:
    issue_counts: Counter[str] = aggregate["issue_counts"]
    blocker_reason_counts: Counter[str] = aggregate["blocker_reason_counts"]
    last_summary = dict(last_detail.get("summary") or {})
    last_verification = dict(last_incubation_result.get("verification") or {})
    last_pipeline = dict(last_incubation_result.get("pipeline") or {})

    findings: list[dict[str, str]] = []
    submitted_total = _safe_int(aggregate.get("submitted_total"))
    gate_input_total = _safe_int(aggregate.get("gate_input_total"))
    gate_pass_total = _safe_int(aggregate.get("gate_pass_total"))
    paper_intake_rounds = _safe_int(aggregate.get("paper_intake_rounds"))
    paper_recognized_total = _safe_int(aggregate.get("paper_recognized_total"))
    latest_submitted = _safe_int(last_detail.get("submitted") or last_summary.get("submitted"))
    latest_raw_b_or_above = _safe_int(last_detail.get("raw_b_or_above_count"))
    latest_strict_ready = _safe_int(last_detail.get("strict_incubation_ready_count"))
    latest_paper_active = _safe_int(last_verification.get("paper_count"))
    latest_incubating = _safe_int(last_verification.get("incubating_count"))
    latest_active_pool = _safe_int(last_paper_backlog.get("paper_observation_active_count"))
    latest_auto_promoted = _safe_int(last_pipeline.get("auto_promoted"))
    gate_pass_but_observe_only_rounds = _safe_int(aggregate.get("gate_pass_but_observe_only_rounds"))
    gate_pass_observe_example = dict(aggregate.get("last_gate_pass_but_observe_only_example") or {})
    strict_ready_observe_example = dict(aggregate.get("last_strict_ready_observe_example") or {})
    strict_ready_formal_missing_example = dict(
        aggregate.get("last_strict_ready_formal_missing_example") or {}
    )
    strict_ready_observe_override_example = dict(
        aggregate.get("last_strict_ready_observe_override_example") or {}
    )

    if submitted_total > 0 and paper_intake_rounds > 0:
        findings.append(
            {
                "priority": "P0",
                "status": "已解决",
                "title": "旧 G3 全拦 / record-only 卡死",
                "summary": "当前实跑已经证明策略能进入 observe 提交，并被 Incubation Factory 识别消费。",
                "evidence": (
                    f"累计 submitted={submitted_total}, Gate3={gate_pass_total}/{gate_input_total}, "
                    f"observe intake 识别轮数={paper_intake_rounds}, recognized 合计={paper_recognized_total}"
                ),
            }
        )
    else:
        findings.append(
            {
                "priority": "P0",
                "status": "未解决",
                "title": "旧 G3 全拦 / record-only 卡死",
                "summary": "当前记录里还缺少足够的提交和 observe intake 证据，不能证明旧式全拦已经解除。",
                "evidence": (
                    f"累计 submitted={submitted_total}, Gate3={gate_pass_total}/{gate_input_total}, "
                    f"observe intake 识别轮数={paper_intake_rounds}"
                ),
            }
        )

    if (
        issue_counts.get("strict_ready_zero_despite_raw_b", 0) > 0
        or issue_counts.get("no_forward_signal_coverage_yet", 0) > 0
        or issue_counts.get("execution_audit_needs_attention", 0) > 0
    ):
        findings.append(
            {
                "priority": "P0",
                "status": "未解决",
                "title": "高质量策略产出仍未打通",
                "summary": "虽然已不再全拦，但高质量策略还没有形成 formal readiness、前向覆盖和执行审计正反馈。",
                "evidence": (
                    f"strict_ready_zero={issue_counts.get('strict_ready_zero_despite_raw_b', 0)} 轮, "
                    f"zero_forward_coverage={issue_counts.get('no_forward_signal_coverage_yet', 0)} 轮, "
                    f"audit_needs_attention={issue_counts.get('execution_audit_needs_attention', 0)} 轮; "
                    f"最新轮 raw_b_or_above={latest_raw_b_or_above}, strict_ready={latest_strict_ready}, submitted={latest_submitted}"
                ),
            }
        )

    if (
        issue_counts.get("factory_runtime_degraded", 0) > 0
        or issue_counts.get("llm_timeout_cooldown_active", 0) > 0
    ):
        findings.append(
            {
                "priority": "P1",
                "status": "未解决",
                "title": "运行时退化仍在影响候选生成质量",
                "summary": "当前不只是候选质量本身偏弱，LLM 超时冷却和 partial_llm 退化也在把生成链路推回本地 fallback，压低可执行规格和策略上限。",
                "evidence": (
                    f"factory_runtime_degraded={issue_counts.get('factory_runtime_degraded', 0)} 轮, "
                    f"llm_timeout_cooldown_active={issue_counts.get('llm_timeout_cooldown_active', 0)} 轮, "
                    f"latest_factory_status={str(last_detail.get('status') or 'unknown')}"
                ),
            }
        )

    if gate_pass_but_observe_only_rounds > 0:
        findings.append(
            {
                "priority": "P0",
                "status": "未解决",
                "title": "G3 通过样本仍未进入 formal 通道",
                "summary": "当前执行模式下，G3 通过并不等于 formal_incubation；实跑已经出现“有 G3 通过样本，但整轮仍全部落在 observe”的现象。",
                "evidence": (
                    f"gate_pass_but_observe_only_rounds={gate_pass_but_observe_only_rounds}, "
                    f"latest_gate3_passed={_safe_int(last_summary.get('gate_3_passed'))}, "
                    f"latest_submitted={latest_submitted}, "
                    f"latest_lane_counts={json.dumps(last_summary.get('submission_lane_counts') or {}, ensure_ascii=False)}"
                ),
            }
        )

    observe_mode = str(
        gate_pass_observe_example.get("execution_mode")
        or session.get("execution_mode")
        or last_detail.get("execution_mode")
        or ""
    ).strip().lower()
    if observe_mode == "stock_first_observe_primary" and gate_pass_but_observe_only_rounds > 0:
        example_round = _safe_int(gate_pass_observe_example.get("round"))
        example_gate3_passed = _safe_int(gate_pass_observe_example.get("gate_3_passed"))
        example_submitted = _safe_int(gate_pass_observe_example.get("submitted"))
        example_lane_counts = dict(gate_pass_observe_example.get("submission_lane_counts") or {})
        example_budget_track_counts = dict(gate_pass_observe_example.get("budget_track_counts") or {})
        example_strategy_status_counts = dict(gate_pass_observe_example.get("strategy_status_counts") or {})
        evidence_parts = [
            f"execution_mode={observe_mode}",
            f"gate_pass_but_observe_only_rounds={gate_pass_but_observe_only_rounds}",
        ]
        if example_round > 0:
            evidence_parts.append(f"example_round={example_round}")
        if example_gate3_passed > 0 or example_submitted > 0:
            evidence_parts.append(f"example_gate3_passed={example_gate3_passed}")
            evidence_parts.append(f"example_submitted={example_submitted}")
        if example_lane_counts:
            evidence_parts.append(
                f"example_lane_counts={json.dumps(example_lane_counts, ensure_ascii=False)}"
            )
        if example_budget_track_counts:
            evidence_parts.append(
                f"example_budget_track_counts={json.dumps(example_budget_track_counts, ensure_ascii=False)}"
            )
        if example_strategy_status_counts:
            evidence_parts.append(
                f"example_strategy_status_counts={json.dumps(example_strategy_status_counts, ensure_ascii=False)}"
            )
        findings.append(
            {
                "priority": "P0",
                "status": "未解决",
                "title": "stock_first_observe_primary 模式疑似在提交前预路由到 observe 轨道",
                "summary": (
                    "当前模式级证据表明，候选在提交前就被 observe-first 路径优先送往 observe 轨道，"
                    "导致 G3 通过与 formal_incubation 进一步脱钩。"
                ),
                "evidence": ", ".join(evidence_parts),
            }
        )

    if issue_counts.get("strict_ready_but_formal_not_requested", 0) > 0:
        evidence_parts = [
            f"strict_ready_but_formal_not_requested={issue_counts.get('strict_ready_but_formal_not_requested', 0)} 轮",
        ]
        example_evidence = _format_strict_ready_example_evidence(strict_ready_formal_missing_example)
        if example_evidence:
            evidence_parts.append(example_evidence)
        findings.append(
            {
                "priority": "P0",
                "status": "未解决",
                "title": "strict-ready 样本仍未发起 formal 申请",
                "summary": (
                    "这已经不是单纯“formal 被质量门拦住”，而是有样本达到 strict incubation readiness 后，"
                    "持久化审查结果仍显示 `formal_track_requested=false`，说明 observe-first 预路由仍在压制 formal 申请。"
                ),
                "evidence": ", ".join(evidence_parts),
            }
        )

    if issue_counts.get("strict_ready_observe_first_override", 0) > 0:
        evidence_parts = [
            f"strict_ready_observe_first_override={issue_counts.get('strict_ready_observe_first_override', 0)} 轮",
        ]
        example_evidence = _format_strict_ready_example_evidence(strict_ready_observe_override_example)
        if example_evidence:
            evidence_parts.append(example_evidence)
        findings.append(
            {
                "priority": "P0",
                "status": "未解决",
                "title": "strict-ready 样本仍被 observe-first 标记压回 observe",
                "summary": (
                    "这说明问题已经不只是 formal 质量门或 runtime bootstrap 本身，"
                    "而是 strict-ready 样本在进入最终准入前仍带着 `observe_first_intake` 标记，"
                    "导致 formal 申请轨道被 observe-first 预路由覆盖。"
                ),
                "evidence": ", ".join(evidence_parts),
            }
        )

    if (
        issue_counts.get("strategy_params_budget_metadata_compacted_away", 0) > 0
        or issue_counts.get("quality_report_plan_metadata_missing", 0) > 0
        or issue_counts.get("strategy_row_submission_metadata_missing", 0) > 0
    ):
        findings.append(
            {
                "priority": "P1",
                "status": "未解决",
                "title": "预算/提交通道元数据的持久化可观测性不足",
                "summary": (
                    "planner 的 formal/observe 计划没有稳定保留在策略行与质量报告摘要里，"
                    "导致 plan-vs-final 路由链路难以直接从持久化结果回放。"
                ),
                "evidence": (
                    f"params_budget_metadata_compacted_away={issue_counts.get('strategy_params_budget_metadata_compacted_away', 0)} 轮, "
                    f"strategy_row_submission_metadata_missing={issue_counts.get('strategy_row_submission_metadata_missing', 0)} 轮, "
                    f"quality_report_plan_metadata_missing={issue_counts.get('quality_report_plan_metadata_missing', 0)} 轮"
                ),
            }
        )

    if issue_counts.get("quality_report_runtime_context_mismatch", 0) > 0:
        findings.append(
            {
                "priority": "P1",
                "status": "未解决",
                "title": "持久化质量报告仍存在 runtime 上下文不一致样本",
                "summary": (
                    "这说明部分样本的 `quality_gate` 与最终 `summary` 仍在使用不同 runtime 语义，"
                    "相关 formal blocker 和路由归因不能被直接当作可信证据。"
                ),
                "evidence": (
                    f"quality_report_runtime_context_mismatch={issue_counts.get('quality_report_runtime_context_mismatch', 0)} 轮"
                ),
            }
        )

    if latest_paper_active > 0 or latest_active_pool > 0:
        findings.append(
            {
                "priority": "P1",
                "status": "未解决",
                "title": "observe 池在消费，但没有转成 formal / promotion",
                "summary": "当前问题更像观察池持续堆积和 warmup 停留，而不是完全无人消费。",
                "evidence": (
                    f"最新轮 incubating={latest_incubating}, paper_active={latest_paper_active}, "
                    f"active_pool={latest_active_pool}, auto_promoted={latest_auto_promoted}"
                ),
            }
        )

    if issue_counts.get("pipeline_stage_fallback", 0) > 0 or issue_counts.get("pipeline_no_executable_specs", 0) > 0:
        findings.append(
            {
                "priority": "P1",
                "status": "未解决",
                "title": "生成管线仍有空规格 / fallback 产能损耗",
                "summary": "staged pipeline 仍会退回本地规则生成，限制可执行规格产出和候选质量上限。",
                "evidence": (
                    f"pipeline_stage_fallback={issue_counts.get('pipeline_stage_fallback', 0)} 次, "
                    f"pipeline_no_executable_specs={issue_counts.get('pipeline_no_executable_specs', 0)} 次"
                ),
            }
        )

    if blocker_reason_counts:
        findings.append(
            {
                "priority": "P1",
                "status": "未解决",
                "title": "formal 准入阻塞仍集中在交易质量指标",
                "summary": "当前主要不是流程断路，而是 post-cost sharpe、profit factor、win rate 等质量门没有被穿透。",
                "evidence": ", ".join(
                    f"{name} x{count}" for name, count in blocker_reason_counts.most_common(5)
                ),
            }
        )

    if entries and gate_input_total > 0 and gate_pass_total == 0:
        findings.append(
            {
                "priority": "P2",
                "status": "关注",
                "title": "当前阶段 Gate 3 通过仍偏低",
                "summary": "这不是旧式全拦，但说明当前轮次里真正能穿过 formal 质量门的候选仍然稀少。",
                "evidence": f"累计 Gate3={gate_pass_total}/{gate_input_total}",
            }
        )

    return findings


def _render_report(state: dict[str, Any]) -> str:
    entries = list(state.get("entries") or [])
    aggregate = _build_aggregate_summary(entries)
    issue_counts: Counter[str] = aggregate["issue_counts"]
    gate_reason_counts: Counter[str] = aggregate["gate_reason_counts"]
    blocker_reason_counts: Counter[str] = aggregate["blocker_reason_counts"]
    session = dict(state.get("session") or {})
    last_entry = entries[-1] if entries else {}
    last_quality = dict((last_entry or {}).get("quality_snapshot") or {})
    last_detail = dict(last_quality.get("detail") or {})
    last_incubation_result = dict(((last_entry or {}).get("incubation_result") or {}).get("result") or {})
    last_paper_backlog = dict(last_incubation_result.get("paper_observation_backlog") or {})
    priority_findings = _build_priority_findings(
        entries,
        aggregate,
        session,
        last_detail,
        last_incubation_result,
        last_paper_backlog,
    )

    lines = [
        f"# 策略工厂24小时运行与质量追踪",
        "",
        f"- session_id: `{session.get('session_id')}`",
        f"- started_at: `{session.get('started_at')}`",
        f"- updated_at: `{state.get('updated_at')}`",
        f"- duration_hours: `{session.get('hours')}`",
        f"- pause_sec_between_rounds: `{session.get('pause_sec')}`",
        f"- execution_mode: `{session.get('execution_mode')}`",
        f"- target_codes: `{', '.join(session.get('codes') or []) or 'default_universe'}`",
        f"- python: `{session.get('python_executable')}`",
        f"- sqlite: `{session.get('sqlite_path')}`",
        f"- report_path: `{session.get('report_path')}`",
        f"- data_source: `real Strategy Factory runtime + MCP-equivalent manager handlers`",
        "",
        "## 累计概览",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 记录轮数 | {len(entries)} |",
        f"| spawned 总数 | {aggregate['spawned_total']} |",
        f"| submitted 总数 | {aggregate['submitted_total']} |",
        f"| Gate 3 通过率 | {aggregate['gate_pass_total']}/{aggregate['gate_input_total']} |",
        f"| 全部 observe 提交轮数 | {aggregate['observe_only_rounds']} |",
        f"| observe 被 intake 识别轮数 | {aggregate['paper_intake_rounds']} |",
        f"| paper observation recognized 合计 | {aggregate['paper_recognized_total']} |",
        "",
        "## 优先级判断",
        "",
    ]

    if priority_findings:
        for item in priority_findings:
            lines.append(
                f"- `{item.get('priority')} {item.get('status')}` {item.get('title')}："
                f"{item.get('summary')} 证据：{item.get('evidence')}"
            )
    else:
        lines.append("- 暂无优先级结论。")

    lines.extend(["", "## 当前主要问题", ""])

    strict_ready_observe_example = dict(aggregate.get("last_strict_ready_observe_example") or {})
    if strict_ready_observe_example:
        lines.extend(["", "## 最近一次关键反例", ""])
        lines.extend(_render_strict_ready_example(strict_ready_observe_example))

    if issue_counts:
        for name, count in issue_counts.most_common(10):
            lines.append(f"- `{name}`: {count} 次")
    else:
        lines.append("- 暂无累计问题标记。")

    lines.extend(["", "## Gate 3 失败原因累计", ""])
    if gate_reason_counts:
        for name, count in gate_reason_counts.most_common(10):
            lines.append(f"- `{name}`: {count}")
    else:
        lines.append("- 暂无 Gate 3 失败原因。")

    lines.extend(["", "## Formal 准入阻塞累计", ""])
    if blocker_reason_counts:
        for name, count in blocker_reason_counts.most_common(10):
            lines.append(f"- `{name}`: {count}")
    else:
        lines.append("- 暂无 formal 准入阻塞统计。")

    lines.extend(["", "## 最新轮观察", ""])
    if last_entry:
        lines.extend(_render_entry(last_entry, fallback_execution_mode=str(session.get("execution_mode") or "")))
    else:
        lines.append("暂无运行记录。")

    lines.extend(["", "## 全部运行记录", ""])
    if entries:
        for entry in entries:
            lines.extend(_render_entry(entry, fallback_execution_mode=str(session.get("execution_mode") or "")))
    else:
        lines.append("暂无运行记录。")

    lines.extend(["", "## 当前判断", ""])
    if last_detail:
        if aggregate.get("paper_intake_rounds", 0) > 0:
            lines.append("- observe 通道已经被 incubation_factory 实际识别/消费，但目前还没有转化成正向前瞻信号覆盖或晋级证据。")
        if issue_counts.get("pipeline_no_executable_specs", 0) > 0:
            lines.append("- staged pipeline 仍然存在 `no_executable_specs` 型空规格回退，这是真实产能问题。")
        if issue_counts.get("dedup_zero_keep", 0) > 0:
            lines.append("- 去重存在批次性全清空现象，说明产出稳定性仍不足。")
        if issue_counts.get("observe_only_submission", 0) > 0:
            lines.append("- 当前多数提交仍落在 observe lane，说明正式孵化就绪率偏低。")
        if issue_counts.get("strict_ready_zero_despite_raw_b", 0) > 0:
            lines.append("- 出现了原始质量不差但 strict incubation readiness 仍为 0 的轮次，需要继续查 formal 准入约束。")
        if (
            issue_counts.get("strategy_params_budget_metadata_compacted_away", 0) > 0
            or issue_counts.get("quality_report_plan_metadata_missing", 0) > 0
        ):
            lines.append(
                "- 持久化可观测性存在缺口：`strategies.params` 会把 `incubation_budget` 作为大节点压缩掉，"
                "`strategy_quality_reports.summary` 也没有稳定保留 `planned_submission_lane` / `incubation_budget_track`。"
            )
        if blocker_reason_counts:
            lines.append(
                "- 当前 formal 准入阻塞集中在: "
                f"{', '.join(f'`{name}`' for name, _ in blocker_reason_counts.most_common(5))}。"
            )
        if _safe_int(last_paper_backlog.get("paper_observation_active_count")) > 0:
            lines.append(
                "- 当前 observe 池仍有 "
                f"{_safe_int(last_paper_backlog.get('paper_observation_active_count'))} "
                "条 active paper/warmup 策略，问题更像“观察池堆积、质量不转正”，而不是“无人消费”。"
            )
        if issue_counts.get("no_forward_signal_coverage_yet", 0) > 0:
            lines.append("- 新提交策略的前向观测覆盖还很低，短期内不应夸大其真实交易质量。")
    else:
        lines.append("- 尚未获得足够数据。")

    return "\n".join(lines).rstrip() + "\n"


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


_LEGACY_BUDGET_MISMATCH_FLAGS = {
    "budget_queue_without_track_assignment",
}

_LEGACY_BUDGET_MISMATCH_NOTE_FRAGMENTS = (
    "incubation budget summary shows candidates staying in deferred_budget_queue with no formal/observe budget assignment",
)


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
) -> dict[str, Any]:
    factor_mining_run = await _run_factor_mining_once(with_incubation)
    factory_run = await _run_strategy_factory_once(
        factory_mod=factory_mod,
        codes=codes,
        execution_mode=execution_mode,
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
