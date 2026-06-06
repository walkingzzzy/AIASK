"""P2-1：每日因子质检流水线编排（残酷质检零件串成一条线）。

关联：开发周期计划-倒置架构与因子路由-2026-06-03.md · Phase 2 · P2-1
设计要点：
- **编排已有零件**，不重复实现统计：OOS(validate_factor_oos) + 分层(backtest_factor) +
  鲁棒性(factor_robustness_check) + multiple_testing + evaluate_validation_evidence。
- **依赖注入**：四个 runner 以可调用对象传入，单测无需 DB/网络。
- **两段 toggle**（默认 OFF，零变化）：
  - STRATEGY_FACTORY_FACTOR_QC_PIPELINE_ENABLED：是否运行质检流水线打标签。
  - STRATEGY_FACTORY_FACTOR_QC_AUTOSHELF_ENABLED：是否据标签自动改写 quality_status（上架/下架）。
    关闭时仅打标签 + 给出建议 shelf_decision，由人工确认（决策点 #5 的保守默认）。
- 写回沿用 factory.py 既有路径：把标签并入 record["validation_summary"]（不新造 status API）。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Awaitable, Callable, Mapping, Optional

logger = logging.getLogger(__name__)

# runner 签名：async (factor_name) -> dict（各质检工具的 data 段）
QcRunner = Callable[[str], Awaitable[Optional[dict]]]

# 分档统计阈值（自包含，镜像 research/incubation/live 三档；与 strategy-factory
# 的 *_ADMISSION_THRESHOLDS 同口径，但本地定义以避免跨包反向依赖）。
_QC_TIERED_THRESHOLDS: dict[str, dict[str, float]] = {
    "research": {
        "walk_forward_ic_ir_min": 0.20,
        "bootstrap_ci_lower_min": -0.01,
        "param_sensitivity_max": 0.35,
        "deflated_sharpe_ratio_min": -0.10,
        "pbo_max": 0.75,
    },
    "incubation": {
        "walk_forward_ic_ir_min": 0.30,
        "bootstrap_ci_lower_min": 0.0,
        "param_sensitivity_max": 0.30,
        "deflated_sharpe_ratio_min": 0.0,
        "pbo_max": 0.60,
    },
    "live": {
        "walk_forward_ic_ir_min": 0.45,
        "bootstrap_ci_lower_min": 0.02,
        "param_sensitivity_max": 0.20,
        "deflated_sharpe_ratio_min": 0.10,
        "pbo_max": 0.35,
    },
}
# AKSHARE_QUALITY_PROFILE(strict/lite/minimum) 到三档的映射。
_PROFILE_ALIAS = {"strict": "live", "lite": "incubation", "minimum": "research"}


def _resolve_qc_thresholds(profile: Optional[str]) -> dict[str, float]:
    raw = str(profile or os.getenv("AKSHARE_QUALITY_PROFILE", "strict")).strip().lower()
    tier = _PROFILE_ALIAS.get(raw, raw if raw in _QC_TIERED_THRESHOLDS else "incubation")
    return dict(_QC_TIERED_THRESHOLDS.get(tier, _QC_TIERED_THRESHOLDS["incubation"]))


def qc_pipeline_enabled() -> bool:
    raw = os.getenv("STRATEGY_FACTORY_FACTOR_QC_PIPELINE_ENABLED")
    return raw is not None and str(raw).strip().lower() in {"1", "true", "yes", "on"}


def qc_autoshelf_enabled() -> bool:
    raw = os.getenv("STRATEGY_FACTORY_FACTOR_QC_AUTOSHELF_ENABLED")
    return raw is not None and str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def derive_qc_labels(
    *,
    oos: Optional[Mapping[str, Any]] = None,
    layered: Optional[Mapping[str, Any]] = None,
    robustness: Optional[Mapping[str, Any]] = None,
    multiple_testing: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """把四类质检输出汇成统一标签字典（纯函数）。

    字段缺失时给保守缺省，不抛异常。
    """
    oos = dict(oos or {})
    layered = dict(layered or {})
    robustness = dict(robustness or {})
    mt = dict(multiple_testing or {})

    # OOS（walk-forward + purged-kfold + bootstrap）
    metrics = dict(oos.get("metrics") or {})
    rating = dict(oos.get("rating") or {})
    rank_ic_ir = _f(metrics.get("rank_ic_ir", metrics.get("walk_forward_ic_ir")))
    bootstrap_ci_lower = _f(
        (oos.get("bootstrap_ci") or {}).get("lower")
        if isinstance(oos.get("bootstrap_ci"), Mapping)
        else metrics.get("bootstrap_ci_lower")
    )
    oos_grade = str(rating.get("grade") or oos.get("grade") or "").strip().lower()
    oos_pass = bool(oos.get("passed")) or oos_grade in {"a", "b", "good", "strong"}

    # 分层 quantile 单调性
    monotonicity = _f(layered.get("monotonicity"))
    long_short = _f(layered.get("long_short_return"))

    # 鲁棒性
    window_stability = _f(robustness.get("window_stability"))
    param_sensitivity = _f(robustness.get("param_sensitivity_max", robustness.get("param_sensitivity")))

    # multiple testing
    dsr = _f((mt.get("deflated_sharpe") or {}).get("dsr") if isinstance(mt.get("deflated_sharpe"), Mapping) else mt.get("dsr"))
    pbo = _f(mt.get("pbo"))

    return {
        "rank_ic_ir": round(rank_ic_ir, 6),
        "bootstrap_ci_lower": round(bootstrap_ci_lower, 6),
        "oos_pass": oos_pass,
        "oos_grade": oos_grade or "unknown",
        "monotonicity": round(monotonicity, 6),
        "long_short_return": round(long_short, 6),
        "window_stability": round(window_stability, 6),
        "param_sensitivity": round(param_sensitivity, 6),
        "dsr": round(dsr, 6),
        "pbo": round(pbo, 6),
    }


def decide_shelf(labels: Mapping[str, Any], *, profile: Optional[str] = None) -> dict[str, Any]:
    """据标签 + 分档阈值给出 shelf 决策（promote / quarantine / retire）。

    使用本地分档阈值（research/incubation/live，由 AKSHARE_QUALITY_PROFILE 或显式 profile 选档）做卡点。
    """
    thr = _resolve_qc_thresholds(profile)

    reasons: list[str] = []
    if not labels.get("oos_pass"):
        reasons.append("oos_not_passed")
    if _f(labels.get("rank_ic_ir")) < _f(thr.get("walk_forward_ic_ir_min"), 0.0):
        reasons.append("rank_ic_ir_below_min")
    if _f(labels.get("bootstrap_ci_lower")) < _f(thr.get("bootstrap_ci_lower_min"), -1e9):
        reasons.append("bootstrap_ci_lower_below_min")
    if _f(labels.get("param_sensitivity")) > _f(thr.get("param_sensitivity_max"), 1e9):
        reasons.append("param_sensitivity_above_max")
    if _f(labels.get("dsr")) < _f(thr.get("deflated_sharpe_ratio_min"), -1e9):
        reasons.append("dsr_below_min")
    if _f(labels.get("pbo")) > _f(thr.get("pbo_max"), 1e9):
        reasons.append("pbo_above_max")
    if _f(labels.get("monotonicity")) < 0.5:
        reasons.append("monotonicity_weak")

    if not reasons:
        decision = "promote"
    elif len(reasons) >= 3 or "oos_not_passed" in reasons:
        decision = "retire"
    else:
        decision = "quarantine"

    return {
        "decision": decision,
        "reasons": reasons,
        "profile": str(profile or os.getenv("AKSHARE_QUALITY_PROFILE", "strict")),
    }


async def run_factor_qc(
    factor_name: str,
    *,
    oos_runner: Optional[QcRunner] = None,
    layered_runner: Optional[QcRunner] = None,
    robustness_runner: Optional[QcRunner] = None,
    multiple_testing_runner: Optional[QcRunner] = None,
    profile: Optional[str] = None,
) -> dict[str, Any]:
    """对单个因子顺序跑四类质检 → 打标签 → 给 shelf 决策。

    任一 runner 缺失或抛错都跳过该项（标签取缺省），不阻断其余质检。
    """
    async def _safe(runner: Optional[QcRunner]) -> Optional[dict]:
        if runner is None:
            return None
        try:
            return await runner(factor_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("qc_pipeline: runner failed for %s: %s", factor_name, exc)
            return None

    oos = await _safe(oos_runner)
    layered = await _safe(layered_runner)
    robustness = await _safe(robustness_runner)
    mt = await _safe(multiple_testing_runner)

    labels = derive_qc_labels(
        oos=oos, layered=layered, robustness=robustness, multiple_testing=mt
    )
    shelf = decide_shelf(labels, profile=profile)
    return {
        "factor_name": factor_name,
        "labels": labels,
        "shelf_decision": shelf,
        "autoshelf_applied": False,  # 由 apply_qc_to_record 在 autoshelf 开启时置 True
    }


def apply_qc_to_record(record: dict[str, Any], qc_result: Mapping[str, Any]) -> dict[str, Any]:
    """把 QC 标签并入 record["validation_summary"]；autoshelf 开启时改写 quality_status/status。

    - 始终写入 qc_labels + qc_shelf_decision（打标签，零破坏）。
    - autoshelf ON 时：promote→quality_status=promoted/status=active；
      quarantine→quality_status=quarantine；retire→quality_status=retired/status=retired。
    """
    rec = dict(record or {})
    vs = dict(rec.get("validation_summary") or {})
    labels = dict(qc_result.get("labels") or {})
    shelf = dict(qc_result.get("shelf_decision") or {})

    vs["qc_labels"] = labels
    vs["qc_shelf_decision"] = shelf

    if qc_autoshelf_enabled():
        decision = str(shelf.get("decision") or "").strip().lower()
        if decision == "promote":
            vs["quality_status"] = "promoted"
            rec["status"] = "active"
        elif decision == "retire":
            vs["quality_status"] = "retired"
            rec["status"] = "retired"
        elif decision == "quarantine":
            vs["quality_status"] = "quarantine"
        vs["qc_autoshelf_applied"] = True
    else:
        vs["qc_autoshelf_applied"] = False

    rec["validation_summary"] = vs
    return rec


__all__ = [
    "qc_pipeline_enabled",
    "qc_autoshelf_enabled",
    "derive_qc_labels",
    "decide_shelf",
    "run_factor_qc",
    "apply_qc_to_record",
]
