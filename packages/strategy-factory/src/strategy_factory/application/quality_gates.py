"""策略工厂分级门禁。

Gate-0: 结构校验 — JSON 合法、strategy_type 合法、DSL 可编译
Gate-1: 快速筛选 — 少量代表性股票快速回测
Gate-2: 完整回测 — 仅对 Gate-1 Top-K 执行（复用 BacktestFilter）
Gate-3: 提交门禁 — 质量报告 + 风险报告 + 去重（委托 submission_gate / submitter 调用）
"""

from __future__ import annotations

import asyncio
import logging
import math
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .legacy_bridge import get_compat_symbol, get_compat_value
from ..domain.constants import (
    BACKTEST_CONCURRENCY,
    GATE1_PASS_RATIO,
    GATE1_REPRESENTATIVE_COUNT,
    GATE1_SHARPE_MIN,
    REPRESENTATIVE_STOCKS,
)
from ..infrastructure.mcp_services import get_strategy_dsl_compiler
from .runtime import get_strategy_factory_package as _runtime_get_strategy_factory_package

logger = logging.getLogger(__name__)

_LEGACY_QUALITY_GATES_MODULE = "akshare_mcp.services.strategy_factory.quality_gates"
_LEGACY_RUNTIME_MODULE = "akshare_mcp.services.strategy_factory.runtime"

def _compat_setting(name: str, default):
    return get_compat_value(_LEGACY_QUALITY_GATES_MODULE, name, default)


def _compat_gate_1_fast_screen(candidate: dict, db, *, kline_cache: Optional[Dict[str, list]] = None):
    target = get_compat_symbol(
        _LEGACY_QUALITY_GATES_MODULE,
        "gate_1_fast_screen",
        gate_1_fast_screen,
    )
    return target(candidate, db, kline_cache=kline_cache)


def get_strategy_factory_package():
    target = get_compat_symbol(
        _LEGACY_RUNTIME_MODULE,
        "get_strategy_factory_package",
        _runtime_get_strategy_factory_package,
        exclude=get_strategy_factory_package,
    )
    return target()


def _normalized_gate_3_counts(submission_result: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    payload = dict(submission_result or {})
    submitted = int(payload.get("submitted", 0))
    passed_count = int(payload.get("gate_3_passed", payload.get("passed_quality_gate", 0)))
    failed_count = int(payload.get("gate_3_failed", max(submitted - passed_count, 0)))
    provisional_passed_count = int(payload.get("gate_3_provisional_passed", 0))
    return {
        "submitted": submitted,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "provisional_passed_count": provisional_passed_count,
    }


def build_pending_gate_3_report(pending_count: int) -> Dict[str, Any]:
    return {
        "status": "pending_submission_gate",
        "input_count": int(pending_count),
        "passed_count": 0,
        "failed_count": 0,
        "pending_count": int(pending_count),
        "delegate": "submission_gate.run_submission_quality_gate",
        "reason": "gate_3_executes_during_submission",
    }


def build_completed_gate_3_report(submission_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = dict(submission_result or {})
    counts = _normalized_gate_3_counts(payload)
    return {
        "gate_3": {
            "status": "completed_submission_gate",
            "input_count": counts["submitted"],
            "passed_count": counts["passed_count"],
            "failed_count": counts["failed_count"],
            "pending_count": 0,
            "provisional_passed_count": counts["provisional_passed_count"],
            "failure_reason_topn": list(payload.get("gate_3_failure_reason_topn") or []),
        },
        "final_decision": {
            "stage": "gate_3",
            "passed_count": counts["passed_count"],
            "failed_count": counts["failed_count"],
            "provisional_passed_count": counts["provisional_passed_count"],
        },
    }


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    """单个门禁的结果。"""
    passed: bool
    gate: str
    reasons: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Gate-0: 结构校验
# ---------------------------------------------------------------------------

_VALID_STRATEGY_TYPES = frozenset({
    "momentum", "ma_cross", "rsi",
    "value_factor", "quality_factor", "growth_factor",
    "multi_factor", "macro_timing", "dsl_rule",
})


def gate_0_structural(candidate: dict) -> GateResult:
    """纯同步结构校验。"""
    reasons: list[str] = []
    strategy_type = str(candidate.get("strategy_type") or "").strip()
    if not strategy_type:
        reasons.append("missing_strategy_type")
    elif strategy_type not in _VALID_STRATEGY_TYPES:
        reasons.append(f"invalid_strategy_type:{strategy_type}")

    params = candidate.get("params")
    if params is None:
        reasons.append("missing_params")
    elif not isinstance(params, dict):
        reasons.append("params_not_dict")

    # DSL 编译检查（可选）
    if strategy_type == "dsl_rule":
        dsl = (params or {}).get("dsl") if isinstance(params, dict) else None
        if not dsl or not isinstance(dsl, dict):
            reasons.append("dsl_rule_missing_dsl_payload")
        else:
            try:
                compile_strategy_blueprint = get_strategy_dsl_compiler()
                compile_strategy_blueprint(candidate, tune_for_factory=True)
            except Exception as exc:
                reasons.append(f"dsl_compile_failed:{type(exc).__name__}")

    return GateResult(passed=len(reasons) == 0, gate="gate_0", reasons=reasons)


# ---------------------------------------------------------------------------
# Gate-1: 快速筛选
# ---------------------------------------------------------------------------

async def gate_1_fast_screen(
    candidate: dict,
    db,
    *,
    kline_cache: Optional[Dict[str, list]] = None,
) -> GateResult:
    """用少量代表性股票做快速回测，Sharpe ≥ GATE1_SHARPE_MIN 即通过。"""
    factory_pkg = get_strategy_factory_package()
    strategy_type = str(candidate.get("strategy_type") or "momentum")
    params = dict(candidate.get("params") or {})

    representative_stocks = list(_compat_setting("REPRESENTATIVE_STOCKS", REPRESENTATIVE_STOCKS))
    representative_count = int(_compat_setting("GATE1_REPRESENTATIVE_COUNT", GATE1_REPRESENTATIVE_COUNT) or GATE1_REPRESENTATIVE_COUNT)
    sharpe_min = float(_compat_setting("GATE1_SHARPE_MIN", GATE1_SHARPE_MIN) or GATE1_SHARPE_MIN)
    codes = list(representative_stocks[:representative_count])
    sharpe_values: list[float] = []
    errors: list[str] = []

    for code in codes:
        try:
            if kline_cache and code in kline_cache:
                klines = kline_cache[code]
            else:
                klines = await db.get_klines(code, limit=250)
            if not klines or len(klines) < 30:
                continue

            BacktestEngine = factory_pkg.BacktestEngine
            result = BacktestEngine.run_backtest(code, klines, strategy_type, params)
            payload = dict(result.get("data") or {}) if isinstance(result, dict) else {}
            if not result.get("success"):
                raise ValueError(result.get("error") or "backtest_failed")
            sharpe = float(payload.get("sharpe_ratio") or payload.get("sharpe") or 0.0)
            sharpe_values.append(sharpe)
        except Exception as exc:
            errors.append(f"{code}:{type(exc).__name__}")

    if not sharpe_values:
        return GateResult(
            passed=False,
            gate="gate_1",
            reasons=["no_backtest_results", *errors],
            metrics={"tested_codes": codes, "sharpe_values": []},
        )

    avg_sharpe = sum(sharpe_values) / len(sharpe_values)
    passed = avg_sharpe >= sharpe_min

    return GateResult(
        passed=passed,
        gate="gate_1",
        reasons=[] if passed else [f"avg_sharpe_{avg_sharpe:.4f}_below_{sharpe_min}"],
        metrics={
            "tested_codes": codes,
            "sharpe_values": [round(v, 4) for v in sharpe_values],
            "avg_sharpe": round(avg_sharpe, 4),
            "threshold": sharpe_min,
        },
    )


# ---------------------------------------------------------------------------
# Pipeline: Gate-0 → Gate-1 → select top-K → Gate-2 (full backtest)
# ---------------------------------------------------------------------------

async def run_gated_filter(
    candidates: List[dict],
    db,
    backtest_filter,
    *,
    kline_cache: Optional[Dict[str, list]] = None,
) -> Dict[str, Any]:
    """执行 Gate-0 → Gate-1 → Gate-2 全流程。

    Returns dict with:
        passed: Gate-2 通过的候选列表
        gate_0_results: Gate-0 结果
        gate_1_results: Gate-1 结果
        gate_2_results: Gate-2 结果（BacktestFilter 报告）
    """
    # --- Gate-0 ---
    gate_0_passed: list[dict] = []
    gate_0_failed: list[dict] = []
    for candidate in candidates:
        result = gate_0_structural(candidate)
        candidate["gate_0_result"] = {"passed": result.passed, "reasons": result.reasons}
        if result.passed:
            gate_0_passed.append(candidate)
        else:
            gate_0_failed.append(candidate)

    logger.info("Gate-0: %d/%d passed structural check", len(gate_0_passed), len(candidates))

    # --- Gate-1 ---
    backtest_concurrency = int(_compat_setting("BACKTEST_CONCURRENCY", BACKTEST_CONCURRENCY) or BACKTEST_CONCURRENCY)
    sem = asyncio.Semaphore(backtest_concurrency)

    async def _screen_one(c: dict) -> tuple[dict, GateResult]:
        async with sem:
            return c, await _compat_gate_1_fast_screen(c, db, kline_cache=kline_cache)

    gate_1_tasks = [_screen_one(c) for c in gate_0_passed]
    gate_1_raw = await asyncio.gather(*gate_1_tasks, return_exceptions=True)

    gate_1_scored: list[tuple[dict, float]] = []
    gate_1_failed: list[dict] = []
    for item in gate_1_raw:
        if isinstance(item, Exception):
            logger.warning("Gate-1 exception: %s", item)
            continue
        candidate, result = item
        candidate["gate_1_result"] = {
            "passed": result.passed,
            "reasons": result.reasons,
            "metrics": result.metrics,
        }
        if result.passed:
            avg_sharpe = float(result.metrics.get("avg_sharpe") or 0.0)
            gate_1_scored.append((candidate, avg_sharpe))
        else:
            gate_1_failed.append(candidate)

    # 按 avg_sharpe 排序，取 Top-K
    gate_1_scored.sort(key=lambda x: x[1], reverse=True)
    gate1_pass_ratio = float(_compat_setting("GATE1_PASS_RATIO", GATE1_PASS_RATIO) or GATE1_PASS_RATIO)
    top_k = max(1, math.ceil(len(gate_1_scored) * gate1_pass_ratio))
    gate_2_candidates = [c for c, _ in gate_1_scored[:top_k]]

    logger.info(
        "Gate-1: %d/%d passed fast screen, top-%d enter Gate-2",
        len(gate_1_scored), len(gate_0_passed), len(gate_2_candidates),
    )

    # --- Gate-2 (full backtest via BacktestFilter) ---
    if gate_2_candidates:
        gate_2_passed = await backtest_filter.filter(gate_2_candidates, db)
    else:
        gate_2_passed = []

    logger.info("Gate-2: %d/%d passed full backtest", len(gate_2_passed), len(gate_2_candidates))

    summary = {
        "input_count": len(candidates),
        "gate_0_passed": len(gate_0_passed),
        "gate_0_failed": len(gate_0_failed),
        "gate_1_passed": len(gate_1_scored),
        "gate_1_failed": len(gate_1_failed),
        "gate_2_input": len(gate_2_candidates),
        "gate_2_passed": len(gate_2_passed),
        "gate_3_pending": len(gate_2_passed),
    }
    gate_0_failed_details = [
        {"strategy_type": c.get("strategy_type"), "reasons": (c.get("gate_0_result") or {}).get("reasons")}
        for c in gate_0_failed
    ]
    gate_1_failed_details = [
        {
            "strategy_type": c.get("strategy_type"),
            "reasons": (c.get("gate_1_result") or {}).get("reasons"),
            "metrics": (c.get("gate_1_result") or {}).get("metrics") or {},
        }
        for c in gate_1_failed
    ]
    gate_2_report = backtest_filter.get_last_report() if hasattr(backtest_filter, "get_last_report") else {}
    gate_report = {
        "gate_0": {
            "passed_count": len(gate_0_passed),
            "failed_count": len(gate_0_failed),
            "failed": gate_0_failed_details,
        },
        "gate_1": {
            "passed_count": len(gate_1_scored),
            "failed_count": len(gate_1_failed),
            "failed": gate_1_failed_details,
            "passed_candidates": [
                {
                    "strategy_type": candidate.get("strategy_type"),
                    "avg_sharpe": round(score, 4),
                }
                for candidate, score in gate_1_scored
            ],
        },
        "gate_2": {
            "input_count": len(gate_2_candidates),
            "passed_count": len(gate_2_passed),
            "passed_candidates": gate_2_passed,
            "report": gate_2_report,
        },
        "gate_3": build_pending_gate_3_report(len(gate_2_passed)),
        "final_decision": {
            "stage": "gate_2",
            "passed_count": len(gate_2_passed),
            "pending_submission_gate_count": len(gate_2_passed),
        },
    }

    return {
        "passed": gate_2_passed,
        "summary": summary,
        "gate_0_failed": gate_0_failed_details,
        "quality_gate": gate_report,
        "gate_report": gate_report,
    }


async def run_gated_submission_pipeline(
    candidates: List[dict],
    snapshot: dict,
    db,
    *,
    backtest_filter=None,
    deduplicator=None,
    submitter=None,
    gated_runner=None,
    kline_cache: Optional[Dict[str, list]] = None,
) -> Dict[str, Any]:
    """执行 Gate-0/1/2 → 去重 → Gate-3 的统一工厂门禁编排。"""
    factory_pkg = get_strategy_factory_package()
    backtest_filter = backtest_filter or factory_pkg.BacktestFilter()
    deduplicator = deduplicator or factory_pkg.Deduplicator()
    submitter = submitter or factory_pkg.StrategySubmitter()

    gate_runner = gated_runner or getattr(factory_pkg, "run_gated_filter", run_gated_filter)

    gate_run = await gate_runner(
        candidates,
        db,
        backtest_filter,
        kline_cache=kline_cache,
    )
    gate_report = dict(gate_run.get("gate_report") or gate_run.get("quality_gate") or {})
    passed = list(gate_run.get("passed") or [])
    unique = await deduplicator.deduplicate(passed, db)
    submit_result = await submitter.submit(unique, snapshot, db)
    final_gate_report = finalize_gate_report(gate_report, submit_result)
    return {
        "passed": passed,
        "unique": unique,
        "submitted": list(submit_result.get("strategies") or []),
        "gate_run": gate_run,
        "submit_result": submit_result,
        "gate_report": final_gate_report,
        "quality_gate": final_gate_report,
        "dedup_report": (
            deduplicator.get_last_report()
            if hasattr(deduplicator, "get_last_report")
            else {}
        ),
        "backtest_report": (
            (gate_report.get("gate_2") or {}).get("report")
            or (
                backtest_filter.get_last_report()
                if hasattr(backtest_filter, "get_last_report")
                else {}
            )
        ),
    }


def build_legacy_gate_report(
    candidates: List[dict],
    passed: List[dict],
    backtest_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """为尚未切到统一 GateRunner 的调用方构造兼容 gate_report。"""
    backtest_report = dict(backtest_report or {})
    backtest_summary = dict(backtest_report.get("summary") or {})
    gate_2_passed = int(backtest_summary.get("passed_count", len(passed)))
    gate_2_input = int(backtest_summary.get("input_count", len(candidates)))
    gate_2_failed = int(backtest_summary.get("failed_count", max(gate_2_input - gate_2_passed, 0)))
    return {
        "gate_0": {
            "status": "legacy_backtest_only",
            "passed_count": None,
            "failed_count": None,
            "reason": "gate_0_not_recorded_in_legacy_path",
        },
        "gate_1": {
            "status": "legacy_backtest_only",
            "passed_count": None,
            "failed_count": None,
            "reason": "gate_1_not_recorded_in_legacy_path",
        },
        "gate_2": {
            "status": "legacy_backtest_only",
            "input_count": gate_2_input,
            "passed_count": gate_2_passed,
            "failed_count": gate_2_failed,
            "report": backtest_report,
        },
        "gate_3": build_pending_gate_3_report(gate_2_passed),
        "final_decision": {
            "stage": "gate_2",
            "passed_count": gate_2_passed,
            "pending_submission_gate_count": gate_2_passed,
        },
    }


def finalize_gate_report(
    base_gate_report: Optional[Dict[str, Any]],
    submission_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """将 Gate-3 提交结果合并进 Gate-0/1/2 报告，形成最终门禁闭环。"""
    merged = deepcopy(base_gate_report or {})
    submission_result = dict(submission_result or {})
    submit_gate_report = dict(submission_result.get("gate_report") or {})
    completed_gate_report = build_completed_gate_3_report(submission_result)
    merged["gate_3"] = dict(submit_gate_report.get("gate_3") or completed_gate_report["gate_3"])
    merged["final_decision"] = dict(
        submit_gate_report.get("final_decision") or completed_gate_report["final_decision"]
    )
    return merged
