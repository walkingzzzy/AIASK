"""孵化工厂 · 观察生命周期策略（INVERT-DESIGN P2 改动C）。

把"每日 observe/promote/halt 决策"从 MetricsRecorder._derive_decision 抽成独立、
可单测、可扩展的 policy 对象。核心遵循设计方案 §4 改动C：
- 用 skill_lcb（命中率置信下界）而非单一 win_rate/Sharpe 一刀切。
- 样本不足时继续观察（不误杀也不误晋升）。
- regime 维度（改动D）可选纳入：任一达标 regime 标签近期 skill 转负 → 倾向 halt。

决策语义：
- ``promote``：前向 skill 显著为正且稳定，推荐晋升评估（非直接上资本）。
- ``observe``：样本不足或表现一般，继续观察。
- ``halt``：近期 skill 转负或稳定性崩坏，建议暂停（释放观察槽）。

阈值默认值与历史 ``_derive_decision`` 完全一致，保证抽取零行为变化；
所有阈值可通过构造参数覆盖，便于回测/调参。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except (TypeError, ValueError):
        return int(default)


@dataclass(slots=True)
class ObservationLifecycleDecision:
    """决策结果 + 可解释证据（reasons）。"""

    decision: str
    reasons: list[str]
    regime_evaluated: bool = False
    regime_negative_labels: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reasons": list(self.reasons),
            "regime_evaluated": bool(self.regime_evaluated),
            "regime_negative_labels": list(self.regime_negative_labels),
        }


@dataclass(slots=True)
class ObservationLifecyclePolicy:
    """画像化淘汰/晋升策略（多维 + skill_lcb，非单一盈利数）。"""

    # 样本量门槛：低于此值一律继续观察。
    min_primary_n: int = 10
    # 近期 skill_lcb 跌破此值 → halt。
    halt_recent_skill_lcb: float = -0.03
    # 稳定性缺口超过此值 → halt。
    halt_stability_gap: float = 0.10
    # 覆盖率低于此值 → 继续观察（数据不足判定）。
    observe_min_coverage: float = 0.25
    # 晋升所需：skill_lcb 显著为正。
    promote_skill_lcb: float = 0.02
    promote_min_coverage: float = 0.60
    promote_max_stability_gap: float = 0.05
    # regime 门：达标样本量；任一达标 regime 标签近期 skill<=0 → 倾向 halt。
    regime_min_n: int = 20
    regime_enabled: bool = False

    def decide(
        self,
        *,
        primary_skill_lcb: float,
        recent_primary_skill_lcb: float,
        stability_gap: float,
        coverage_ratio: float,
        primary_n: int,
        hit_rate_by_regime: Optional[Mapping[str, Any]] = None,
    ) -> ObservationLifecycleDecision:
        """返回结构化决策（含 reasons）。纯函数，无副作用。"""
        primary_skill_lcb = _safe_float(primary_skill_lcb)
        recent_primary_skill_lcb = _safe_float(recent_primary_skill_lcb)
        stability_gap = _safe_float(stability_gap)
        coverage_ratio = _safe_float(coverage_ratio)
        primary_n = _safe_int(primary_n)

        reasons: list[str] = []

        # 1) 样本不足 → 继续观察。
        if primary_n < self.min_primary_n:
            reasons.append(f"insufficient_samples:{primary_n}<{self.min_primary_n}")
            return ObservationLifecycleDecision("observe", reasons)

        # 2) regime 维度近期转负（改动D 输入，可选）→ halt。
        regime_eval = self._evaluate_regime(hit_rate_by_regime)
        if self.regime_enabled and regime_eval["evaluated"] and regime_eval["negative_labels"]:
            reasons.append(
                "regime_skill_negative:" + ",".join(regime_eval["negative_labels"])
            )
            return ObservationLifecycleDecision(
                "halt",
                reasons,
                regime_evaluated=True,
                regime_negative_labels=tuple(regime_eval["negative_labels"]),
            )

        # 3) 近期 skill_lcb 转负 → halt。
        if recent_primary_skill_lcb < self.halt_recent_skill_lcb:
            reasons.append(
                f"recent_skill_lcb_negative:{recent_primary_skill_lcb:.4f}<{self.halt_recent_skill_lcb}"
            )
            return ObservationLifecycleDecision(
                "halt", reasons, regime_evaluated=regime_eval["evaluated"]
            )

        # 4) 稳定性崩坏 → halt。
        if stability_gap > self.halt_stability_gap:
            reasons.append(f"stability_gap_high:{stability_gap:.4f}>{self.halt_stability_gap}")
            return ObservationLifecycleDecision(
                "halt", reasons, regime_evaluated=regime_eval["evaluated"]
            )

        # 5) 覆盖率太低 → 继续观察。
        if coverage_ratio < self.observe_min_coverage:
            reasons.append(f"coverage_low:{coverage_ratio:.4f}<{self.observe_min_coverage}")
            return ObservationLifecycleDecision(
                "observe", reasons, regime_evaluated=regime_eval["evaluated"]
            )

        # 6) skill_lcb 显著为正 + 稳定 + 覆盖足 → promote。
        if (
            primary_skill_lcb > self.promote_skill_lcb
            and recent_primary_skill_lcb > 0.0
            and stability_gap <= self.promote_max_stability_gap
            and coverage_ratio >= self.promote_min_coverage
        ):
            # regime 启用时，要求达标 regime 标签无近期转负（已在步骤2拦截），
            # 这里附带证据说明跨 regime 通过。
            reasons.append(
                f"promote:skill_lcb={primary_skill_lcb:.4f}>{self.promote_skill_lcb}"
            )
            if regime_eval["evaluated"]:
                reasons.append("regime_cross_positive")
            return ObservationLifecycleDecision(
                "promote", reasons, regime_evaluated=regime_eval["evaluated"]
            )

        reasons.append("observe_default")
        return ObservationLifecycleDecision(
            "observe", reasons, regime_evaluated=regime_eval["evaluated"]
        )

    def _evaluate_regime(self, hit_rate_by_regime: Optional[Mapping[str, Any]]) -> dict[str, Any]:
        """评估各 regime 维度近期 skill（用 recent_skill_lcb，缺失回退 skill_lcb）。"""
        source = dict(hit_rate_by_regime or {})
        evaluated_labels: list[str] = []
        negative_labels: list[str] = []
        for dimension, buckets in source.items():
            for label, stats in dict(buckets or {}).items():
                payload = dict(stats or {})
                n = _safe_int(payload.get("n") or payload.get("effective_n"))
                if n < int(self.regime_min_n):
                    continue
                recent = payload.get("recent_skill_lcb")
                skill = _safe_float(recent if recent is not None else payload.get("skill_lcb"))
                tag = f"{dimension}:{label}"
                evaluated_labels.append(tag)
                if skill <= 0.0:
                    negative_labels.append(tag)
        return {
            "evaluated": bool(evaluated_labels),
            "evaluated_labels": evaluated_labels,
            "negative_labels": negative_labels,
        }


__all__ = [
    "ObservationLifecyclePolicy",
    "ObservationLifecycleDecision",
]
