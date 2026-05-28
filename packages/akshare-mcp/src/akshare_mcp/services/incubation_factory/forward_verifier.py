"""孵化工厂 · 前向收益验证模块。

负责验证策略信号的前向收益，计算真实命中率。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

# 前向验证的时间窗口（交易日）
FORWARD_HORIZONS = [5, 10, 20]

# 孵化周期配置：不同策略类型有不同的孵化特性
INCUBATION_PROFILES: dict[str, dict[str, Any]] = {
    "high_frequency": {
        "families": [
            "momentum", "ma_cross", "mean_reversion_short", "gap_fill",
        ],
        "min_days": 20,
        "min_trades": 30,
        "primary_horizon": 5,
        "secondary_horizon": 10,
    },
    "medium_frequency": {
        "families": [
            "rsi", "volatility_breakout", "event_structure_breakout",
            "north_capital_track", "margin_divergence",
        ],
        "min_days": 30,
        "min_trades": 20,
        "primary_horizon": 10,
        "secondary_horizon": 20,
    },
    "low_frequency": {
        "families": [
            "value_factor", "quality_factor", "growth_factor",
            "multi_factor", "macro_timing", "sector_rotation",
        ],
        "min_days": 45,
        "min_trades": 12,
        "primary_horizon": 20,
        "secondary_horizon": 40,
    },
}


def resolve_incubation_profile(strategy_type: Optional[str]) -> dict[str, Any]:
    """根据策略类型解析孵化配置。"""
    normalized = str(strategy_type or "").strip().lower()
    for profile_name, profile in INCUBATION_PROFILES.items():
        if normalized in profile["families"]:
            return {**profile, "profile_name": profile_name}
    # 默认使用中频配置
    return {**INCUBATION_PROFILES["medium_frequency"], "profile_name": "medium_frequency"}


class ForwardVerifier:
    """前向收益验证器。

    验证策略历史信号在真实市场中的前向收益表现，
    计算无偏的命中率和技能指标。
    """

    async def verify(self, db: Any, strategy: dict[str, Any]) -> dict[str, Any]:
        """
        验证策略的前向收益。

        流程：
        1. 获取策略的历史信号
        2. 对每个信号计算 T+5, T+10, T+20 的前向收益
        3. 计算命中率和技能指标
        4. 返回验证结果
        """
        sid = str(strategy.get("id") or "").strip()
        strategy_type = str(strategy.get("strategy_type") or "").strip()
        profile = resolve_incubation_profile(strategy_type)

        # 获取信号证据
        evidence_list = await self._load_signal_evidence(db, sid)
        if not evidence_list:
            return self._empty_result(sid, profile)

        # 计算前向收益命中率
        primary_horizon = profile["primary_horizon"]
        secondary_horizon = profile["secondary_horizon"]

        primary_hits = []
        secondary_hits = []
        all_returns: list[float] = []
        primary_directions: list[float] = []
        primary_raw_returns: list[float] = []

        for evidence in evidence_list:
            forward_returns = dict(evidence.get("forward_returns") or {})
            direction = self._normalize_direction(evidence.get("direction"))

            # 主时间窗口
            primary_return = self._extract_forward_return(
                forward_returns, primary_horizon
            )
            if primary_return is not None:
                hit = (primary_return > 0 and direction > 0) or (
                    primary_return < 0 and direction < 0
                )
                primary_hits.append(1.0 if hit else 0.0)
                primary_directions.append(float(direction))
                primary_raw_returns.append(float(primary_return))
                all_returns.append(float(primary_return) * float(direction))

            # 次时间窗口
            secondary_return = self._extract_forward_return(
                forward_returns, secondary_horizon
            )
            if secondary_return is not None:
                hit = (secondary_return > 0 and direction > 0) or (
                    secondary_return < 0 and direction < 0
                )
                secondary_hits.append(1.0 if hit else 0.0)

        # 计算统计指标
        primary_n = len(primary_hits)
        secondary_n = len(secondary_hits)

        primary_hit_rate = float(np.mean(primary_hits)) if primary_hits else 0.0
        secondary_hit_rate = float(np.mean(secondary_hits)) if secondary_hits else 0.0

        # 计算 skill_lcb（95% 置信区间下界）
        primary_skill_lcb = self._compute_skill_lcb(primary_hits)
        secondary_skill_lcb = self._compute_skill_lcb(secondary_hits)

        # 近期表现（最近 20 个信号）
        recent_primary_hits = primary_hits[-20:] if len(primary_hits) > 20 else primary_hits
        recent_primary_hit_rate = float(np.mean(recent_primary_hits)) if recent_primary_hits else 0.0
        recent_primary_skill_lcb = self._compute_skill_lcb(recent_primary_hits)

        # 稳定性缺口
        stability_gap = self._compute_stability_gap(primary_hits)

        # 覆盖率
        coverage_ratio = self._compute_coverage_ratio(evidence_list, profile)

        # 前向 Sharpe
        forward_sharpe = self._compute_forward_sharpe(all_returns, primary_horizon)
        forward_ic = self._compute_forward_ic(primary_directions, primary_raw_returns)

        return {
            "strategy_id": sid,
            "profile": profile["profile_name"],
            "primary_horizon": primary_horizon,
            "secondary_horizon": secondary_horizon,
            "primary_effective_n": primary_n,
            "secondary_effective_n": secondary_n,
            "primary_hit_rate": round(primary_hit_rate, 4),
            "secondary_hit_rate": round(secondary_hit_rate, 4),
            "recent_primary_hit_rate": round(recent_primary_hit_rate, 4),
            "primary_skill_lcb": round(primary_skill_lcb, 4),
            "secondary_skill_lcb": round(secondary_skill_lcb, 4),
            "recent_primary_skill_lcb": round(recent_primary_skill_lcb, 4),
            "stability_gap": round(stability_gap, 4),
            "coverage_ratio": round(coverage_ratio, 4),
            "forward_ic": round(forward_ic, 4),
            "forward_sharpe": round(forward_sharpe, 4),
            "total_signals": len(evidence_list),
            "min_days_remaining": max(
                0, profile["min_days"] - len(evidence_list)
            ),
            "min_trades_remaining": max(
                0, profile["min_trades"] - primary_n
            ),
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _load_signal_evidence(
        self, db: Any, strategy_id: str
    ) -> list[dict[str, Any]]:
        """加载策略的信号证据。"""
        if hasattr(db, "list_strategy_signal_evidence"):
            try:
                return await db.list_strategy_signal_evidence(
                    strategy_id=strategy_id, limit=500
                )
            except Exception as exc:
                logger.warning(
                    "ForwardVerifier: load evidence failed for %s: %s",
                    strategy_id,
                    exc,
                )
        return []

    def _normalize_direction(self, direction: Any) -> int:
        """标准化信号方向。"""
        if direction is None:
            return 1
        text = str(direction).strip().lower()
        if text in ("up", "long", "buy", "1"):
            return 1
        if text in ("down", "short", "sell", "-1"):
            return -1
        try:
            return 1 if float(direction) >= 0 else -1
        except (TypeError, ValueError):
            return 1

    def _extract_forward_return(
        self, forward_returns: dict[str, Any], horizon: int
    ) -> Optional[float]:
        """提取指定时间窗口的前向收益。"""
        for key in (
            f"forward_{horizon}d",
            f"return_{horizon}d",
            f"fwd_{horizon}",
            str(horizon),
        ):
            value = forward_returns.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return None

    def _compute_skill_lcb(self, hits: list[float]) -> float:
        """
        计算技能下界（Skill Lower Confidence Bound）。

        Wilson lower bound of hit probability, minus the random baseline 0.5.
        """
        if len(hits) < 5:
            return 0.0
        arr = np.array(hits, dtype=np.float64)
        hit_rate = float(np.mean(arr))
        n = len(arr)
        z = 1.96
        denominator = 1.0 + z * z / n
        center = (hit_rate + z * z / (2.0 * n)) / denominator
        margin = z * np.sqrt(
            (hit_rate * (1.0 - hit_rate) + z * z / (4.0 * n)) / n
        ) / denominator
        return float(center - margin - 0.5)

    def _compute_stability_gap(self, hits: list[float]) -> float:
        """
        计算稳定性缺口。

        stability_gap = |recent_hit_rate - overall_hit_rate|
        近期定义为最近 1/3 的样本。
        """
        if len(hits) < 10:
            return 0.0
        arr = np.array(hits, dtype=np.float64)
        overall = float(np.mean(arr))
        split_point = max(5, len(arr) // 3)
        recent = float(np.mean(arr[-split_point:]))
        return abs(recent - overall)

    def _compute_coverage_ratio(
        self, evidence_list: list[dict[str, Any]], profile: dict[str, Any]
    ) -> float:
        """
        计算信号覆盖率。

        coverage = 有前向收益的信号数 / 总信号数
        """
        if not evidence_list:
            return 0.0
        total = len(evidence_list)
        with_returns = sum(
            1
            for e in evidence_list
            if dict(e.get("forward_returns") or {})
        )
        return with_returns / total if total > 0 else 0.0

    def _compute_forward_ic(
        self,
        directions: list[float],
        returns: list[float],
    ) -> float:
        """Compute signal-direction IC with directional mean fallback."""
        if len(directions) < 5 or len(returns) < 5:
            return 0.0
        dir_arr = np.array(directions, dtype=np.float64)
        ret_arr = np.array(returns, dtype=np.float64)
        if float(np.std(dir_arr)) > 1e-10 and float(np.std(ret_arr)) > 1e-10:
            corr = float(np.corrcoef(dir_arr, ret_arr)[0, 1])
            if np.isfinite(corr):
                return corr
        return float(np.mean(dir_arr * ret_arr))

    def _compute_forward_sharpe(self, returns: list[float], horizon_days: int = 1) -> float:
        """计算前向 Sharpe ratio。"""
        if len(returns) < 5:
            return 0.0
        arr = np.array(returns, dtype=np.float64)
        mean_return = float(np.mean(arr))
        std_return = float(np.std(arr, ddof=1))
        if std_return < 1e-10:
            return 0.0
        annualization = np.sqrt(252.0 / max(1, int(horizon_days or 1)))
        return float(mean_return / std_return * annualization)

    def _empty_result(self, strategy_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        """无信号时的空结果。"""
        return {
            "strategy_id": strategy_id,
            "profile": profile["profile_name"],
            "primary_horizon": profile["primary_horizon"],
            "secondary_horizon": profile["secondary_horizon"],
            "primary_effective_n": 0,
            "secondary_effective_n": 0,
            "primary_hit_rate": 0.0,
            "secondary_hit_rate": 0.0,
            "recent_primary_hit_rate": 0.0,
            "primary_skill_lcb": 0.0,
            "secondary_skill_lcb": 0.0,
            "recent_primary_skill_lcb": 0.0,
            "stability_gap": 0.0,
            "coverage_ratio": 0.0,
            "forward_ic": 0.0,
            "forward_sharpe": 0.0,
            "total_signals": 0,
            "min_days_remaining": profile["min_days"],
            "min_trades_remaining": profile["min_trades"],
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
