"""策略工厂分级门禁。

Gate-0: 结构校验 — JSON 合法、strategy_type 合法、DSL 可编译
Gate-1: 快速筛选 — 少量代表性股票快速回测
Gate-2: 完整回测 — 仅对 Gate-1 Top-K 执行（复用 BacktestFilter）
Gate-3: 提交门禁 — 质量报告 + 风险报告 + 去重（由 submitter 调用）
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .constants import (
    BACKTEST_CONCURRENCY,
    GATE1_PASS_RATIO,
    GATE1_REPRESENTATIVE_COUNT,
    GATE1_SHARPE_MIN,
    REPRESENTATIVE_STOCKS,
)
from .utils import get_strategy_factory_package

logger = logging.getLogger(__name__)


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
                from ..strategy_dsl_compiler import compile_strategy_blueprint
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

    codes = list(REPRESENTATIVE_STOCKS[:GATE1_REPRESENTATIVE_COUNT])
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
            engine = BacktestEngine(strategy_type, params, klines)
            result = engine.run()
            sharpe = float(result.get("sharpe_ratio") or result.get("sharpe") or 0.0)
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
    passed = avg_sharpe >= GATE1_SHARPE_MIN

    return GateResult(
        passed=passed,
        gate="gate_1",
        reasons=[] if passed else [f"avg_sharpe_{avg_sharpe:.4f}_below_{GATE1_SHARPE_MIN}"],
        metrics={
            "tested_codes": codes,
            "sharpe_values": [round(v, 4) for v in sharpe_values],
            "avg_sharpe": round(avg_sharpe, 4),
            "threshold": GATE1_SHARPE_MIN,
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
    sem = asyncio.Semaphore(BACKTEST_CONCURRENCY)

    async def _screen_one(c: dict) -> tuple[dict, GateResult]:
        async with sem:
            return c, await gate_1_fast_screen(c, db, kline_cache=kline_cache)

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
    top_k = max(1, math.ceil(len(gate_1_scored) * GATE1_PASS_RATIO))
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

    return {
        "passed": gate_2_passed,
        "summary": {
            "input_count": len(candidates),
            "gate_0_passed": len(gate_0_passed),
            "gate_0_failed": len(gate_0_failed),
            "gate_1_passed": len(gate_1_scored),
            "gate_1_failed": len(gate_1_failed),
            "gate_2_input": len(gate_2_candidates),
            "gate_2_passed": len(gate_2_passed),
        },
        "gate_0_failed": [
            {"strategy_type": c.get("strategy_type"), "reasons": (c.get("gate_0_result") or {}).get("reasons")}
            for c in gate_0_failed
        ],
    }
