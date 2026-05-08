"""策略拥挤度监控 (Gap 3).

基于真实信号向量的策略间相关性检查，区别于 governance_monitor 中
现有的名称/表达式启发式 crowding check。

输出结构对接 governance_monitor 和 incubation_pipeline，可作为
promotion review 的 soft/hard gate 输入。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_CROWDING_LOOKBACK_DAYS = 60
DEFAULT_CROWDING_CORRELATION_THRESHOLD = 0.60
DEFAULT_CROWDING_MAX_CORRELATED = 3
DEFAULT_CROWDING_MIN_COMMON_DATES = 10


def _string(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


async def _get_strategy_signal_vectors(
    db,
    strategy_id: str,
    lookback_days: int = DEFAULT_CROWDING_LOOKBACK_DAYS,
) -> Dict[str, float]:
    """获取策略在日期维度的信号向量 (date -> avg_signal)."""
    vectors: Dict[str, float] = {}

    if not hasattr(db, "get_signals"):
        return vectors

    try:
        start_date = date.today() - timedelta(days=lookback_days)
        signals = await db.get_signals(strategy_id, start_date=start_date, limit=2000)
    except Exception as exc:
        logger.debug("get_strategy_signal_vectors: query failed for %s: %s", strategy_id, exc)
        return vectors

    # 按日期聚合信号
    by_date: Dict[str, List[float]] = {}
    for s in (signals or []):
        signal_date = s.get("signal_date")
        signal_val = _safe_float(s.get("signal"))
        if signal_date is None or signal_val == 0:
            continue
        key = str(signal_date)[:10]
        by_date.setdefault(key, []).append(signal_val)

    for dt, vals in by_date.items():
        if vals:
            vectors[dt] = sum(vals) / len(vals)

    return vectors


def _calc_signal_correlation(
    vec_a: Dict[str, float],
    vec_b: Dict[str, float],
) -> Optional[float]:
    """计算两个信号向量在公共日期上的 Pearson 相关系数（纯 Python）."""
    common_dates = sorted(set(vec_a.keys()) & set(vec_b.keys()))
    if len(common_dates) < DEFAULT_CROWDING_MIN_COMMON_DATES:
        return None

    x = [vec_a[d] for d in common_dates]
    y = [vec_b[d] for d in common_dates]
    n = len(x)

    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi * xi for xi in x)
    sum_y2 = sum(yi * yi for yi in y)

    numerator = n * sum_xy - sum_x * sum_y
    denom_x = (n * sum_x2 - sum_x * sum_x) ** 0.5
    denom_y = (n * sum_y2 - sum_y * sum_y) ** 0.5

    if denom_x <= 0 or denom_y <= 0:
        return None

    corr = numerator / (denom_x * denom_y)
    return round(float(corr), 4)


async def check_strategy_crowding(
    db,
    candidate_id: str,
    existing_ids: List[str],
    *,
    lookback_days: int = DEFAULT_CROWDING_LOOKBACK_DAYS,
    correlation_threshold: float = DEFAULT_CROWDING_CORRELATION_THRESHOLD,
    max_correlated: int = DEFAULT_CROWDING_MAX_CORRELATED,
) -> dict:
    """检查候选策略与已有策略的信号拥挤度.

    Args:
        db: 数据库适配器
        candidate_id: 候选策略 ID
        existing_ids: 已有上市/孵化策略 ID 列表
        lookback_days: 信号回看天数
        correlation_threshold: 相关性阈值
        max_correlated: 最大允许高相关策略数

    Returns:
        {
            "crowding_risk": "low" | "medium" | "high",
            "correlated_strategies": [{"id": ..., "correlation": ...}],
            "avg_correlation": float,
            "recommendation": "approve" | "review" | "reject",
        }
    """
    candidate_vec = await _get_strategy_signal_vectors(db, candidate_id, lookback_days)

    if len(candidate_vec) < DEFAULT_CROWDING_MIN_COMMON_DATES:
        return {
            "crowding_risk": "low",
            "recommendation": "approve",
            "correlated_strategies": [],
            "avg_correlation": 0.0,
            "reason": "insufficient_candidate_signals",
        }

    correlated: List[dict] = []
    correlations: List[float] = []

    for eid in existing_ids:
        if eid == candidate_id:
            continue
        existing_vec = await _get_strategy_signal_vectors(db, eid, lookback_days)
        corr = _calc_signal_correlation(candidate_vec, existing_vec)
        if corr is not None and corr > correlation_threshold:
            correlated.append({"id": eid, "correlation": corr})
            correlations.append(corr)

    avg_corr = round(sum(correlations) / len(correlations), 4) if correlations else 0.0

    if len(correlated) >= max_correlated:
        crowding_risk = "high"
        recommendation = "reject"
    elif len(correlated) >= max(1, max_correlated // 2):
        crowding_risk = "medium"
        recommendation = "review"
    else:
        crowding_risk = "low"
        recommendation = "approve"

    return {
        "crowding_risk": crowding_risk,
        "correlated_strategies": correlated,
        "avg_correlation": avg_corr,
        "recommendation": recommendation,
        "lookback_days": lookback_days,
        "correlation_threshold": correlation_threshold,
    }


async def check_strategy_crowding_for_promotion(
    db,
    strategy: dict,
    *,
    lookback_days: int = DEFAULT_CROWDING_LOOKBACK_DAYS,
) -> Optional[dict]:
    """Promotion review 专用的拥挤度检查包装.

    自动获取同类型 listed 策略作为对比基准。
    """
    sid = str(strategy.get("id") or "").strip()
    if not sid:
        return None

    # 获取同类型 listed 策略
    existing_ids: List[str] = []
    if hasattr(db, "list_strategies"):
        try:
            listed = await db.list_strategies("listed", limit=100)
            for s in (listed or []):
                eid = str(s.get("id") or "").strip()
                if eid and eid != sid:
                    existing_ids.append(eid)
        except Exception:
            pass

    if not existing_ids:
        return None

    return await check_strategy_crowding(
        db,
        sid,
        existing_ids,
        lookback_days=lookback_days,
    )
