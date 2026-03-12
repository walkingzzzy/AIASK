"""策略工厂轻量因子研究 artifact 构建。"""

from __future__ import annotations

from typing import Any, Dict, List


class FactorResearchBuilder:
    """基于 collect 阶段已有因子摘要构建统一 artifact。"""

    FACTOR_STRATEGY_MAPPING: Dict[str, List[str]] = {
        "momentum": ["momentum", "ma_cross"],
        "value": ["value_factor", "multi_factor"],
        "quality": ["quality_factor", "multi_factor"],
        "growth": ["growth_factor", "momentum"],
        "reversal": ["rsi", "value_factor"],
        "volatility": ["macro_timing", "ma_cross"],
    }

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except Exception:
            return 0.0

    @classmethod
    def _normalize_trend(cls, value: Any) -> str:
        trend = str(value or "flat").strip().lower()
        return trend if trend in {"rising", "falling", "flat"} else "flat"

    @classmethod
    def _preferred_types_for_factor(cls, factor_name: str) -> List[str]:
        lowered = str(factor_name or "").strip().lower()
        for token, mapped in cls.FACTOR_STRATEGY_MAPPING.items():
            if token in lowered:
                return list(mapped)
        return ["multi_factor"]

    @classmethod
    async def build(cls, _db, snapshot: dict[str, Any]) -> dict[str, Any]:
        factor_ic = dict(snapshot.get("factor_ic") or {})
        factor_trend = dict(snapshot.get("factor_ic_trend") or {})

        ranked_factors: List[dict[str, Any]] = []
        names = list(dict.fromkeys([*factor_ic.keys(), *factor_trend.keys()]))
        for factor_name in names:
            ic_value = cls._safe_float(factor_ic.get(factor_name))
            trend = cls._normalize_trend(factor_trend.get(factor_name))
            trend_bonus = 0.02 if trend == "rising" else (-0.02 if trend == "falling" else 0.0)
            ranked_factors.append(
                {
                    "factor_name": str(factor_name),
                    "ic_value": round(ic_value, 6),
                    "trend": trend,
                    "score": round(ic_value + trend_bonus, 6),
                    "preferred_strategy_types": cls._preferred_types_for_factor(str(factor_name)),
                }
            )

        ranked_factors.sort(
            key=lambda item: (
                cls._safe_float(item.get("score")),
                cls._safe_float(item.get("ic_value")),
                str(item.get("factor_name") or ""),
            ),
            reverse=True,
        )

        positive_rising_factors = [
            str(item.get("factor_name") or "")
            for item in ranked_factors
            if cls._normalize_trend(item.get("trend")) == "rising" and cls._safe_float(item.get("ic_value")) > 0.0
        ]
        positive_rising_factors = [name for name in positive_rising_factors if name]

        active_factors = positive_rising_factors[:3]
        if not active_factors:
            active_factors = [
                str(item.get("factor_name") or "")
                for item in ranked_factors
                if abs(cls._safe_float(item.get("ic_value"))) >= 0.02
            ][:3]
        active_factors = [name for name in active_factors if name]

        active_factor_set = set(active_factors)
        preferred_strategy_types: List[str] = []
        for item in ranked_factors:
            if str(item.get("factor_name") or "") not in active_factor_set:
                continue
            for strategy_type in list(item.get("preferred_strategy_types") or []):
                if strategy_type not in preferred_strategy_types:
                    preferred_strategy_types.append(strategy_type)

        top_factor_names = [
            str(item.get("factor_name") or "")
            for item in ranked_factors[:3]
            if str(item.get("factor_name") or "")
        ]
        rationale: List[str] = []
        if active_factors:
            rationale.append(f"活跃因子: {', '.join(active_factors)}")
        if preferred_strategy_types:
            rationale.append(f"优先策略类型: {', '.join(preferred_strategy_types[:4])}")
        if not rationale:
            rationale.append("未识别到显著活跃因子，后续阶段回退到原始快照因子摘要逻辑。")

        degraded = not bool(ranked_factors)
        return {
            "active_factors": active_factors,
            "ranked_factors": ranked_factors,
            "positive_rising_factors": positive_rising_factors,
            "preferred_strategy_types": preferred_strategy_types,
            "research_rationale": rationale,
            "source_chain": ["snapshot.factor_ic", "snapshot.factor_ic_trend", "artifact_v1"],
            "degraded": degraded,
            "summary": {
                "active_factor_count": len(active_factors),
                "ranked_factor_count": len(ranked_factors),
                "top_factor_names": top_factor_names,
                "preferred_strategy_types": preferred_strategy_types,
                "degraded": degraded,
            },
        }