"""策略工厂轻量因子研究 artifact 构建。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Optional, Tuple

from akshare_mcp.services.factor_scheduler import get_factor_scheduler

from ..domain.constants import FACTORY_RESEARCH_FACTORS, preferred_strategy_types_for_factor
from .runtime import _call_optional_async


class FactorResearchBuilder:
    """基于 collect 阶段已有因子摘要构建统一 artifact。"""

    HISTORY_LIMIT = 20
    STALE_AFTER_DAYS = 2

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value or 0)
        except Exception:
            return 0

    @classmethod
    def _normalize_trend(cls, value: Any) -> str:
        trend = str(value or "flat").strip().lower()
        return trend if trend in {"rising", "falling", "flat"} else "flat"

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        raw = str(value or "").strip()
        if not raw:
            return None
        for parser in (
            date.fromisoformat,
            lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")).date(),
        ):
            try:
                return parser(raw)
            except Exception:
                continue
        return None

    @classmethod
    def _days_since(cls, value: Optional[date], *, reference_date: Optional[date] = None) -> Optional[int]:
        if value is None:
            return None
        try:
            baseline = reference_date or date.today()
            return max((baseline - value).days, 0)
        except Exception:
            return None

    @classmethod
    def _preferred_types_for_factor(cls, factor_name: str) -> List[str]:
        return preferred_strategy_types_for_factor(factor_name)

    @classmethod
    def _history_summary(cls, rows: List[dict[str, Any]]) -> dict[str, Any]:
        history = [dict(item or {}) for item in list(rows or []) if isinstance(item, dict)]
        ic_values = [
            cls._safe_float(item.get("ic_value"))
            for item in history
            if item.get("ic_value") is not None
        ]
        latest_date = None
        if history:
            latest_date = cls._parse_date(history[0].get("ic_date"))
        recent_mean_5 = round(sum(ic_values[:5]) / max(len(ic_values[:5]), 1), 6) if ic_values else 0.0
        baseline_slice = ic_values[5:10] if len(ic_values) >= 10 else ic_values[5:]
        baseline_mean = round(sum(baseline_slice) / len(baseline_slice), 6) if baseline_slice else recent_mean_5
        delta = round(recent_mean_5 - baseline_mean, 6)
        latest_value = cls._safe_float(ic_values[0]) if ic_values else 0.0
        stability_tag = "insufficient_history"
        if len(ic_values) >= 10 and recent_mean_5 * baseline_mean < 0:
            stability_tag = "regime_flip"
        elif len(ic_values) >= 8 and abs(delta) <= 0.005:
            stability_tag = "stable"
        elif delta > 0.005:
            stability_tag = "improving"
        elif delta < -0.005:
            stability_tag = "weakening"
        elif ic_values:
            stability_tag = "short_history"
        decay_flag = bool(delta < -0.01 or (baseline_mean > 0.0 and recent_mean_5 <= 0.0))
        return {
            "history_count": len(ic_values),
            "latest_ic_date": latest_date.isoformat() if latest_date else None,
            "latest_ic_value": round(latest_value, 6),
            "recent_mean_5": recent_mean_5,
            "baseline_mean_5": baseline_mean,
            "delta_vs_baseline": delta,
            "stability_tag": stability_tag,
            "decay_flag": decay_flag,
        }

    @classmethod
    async def _load_factor_history_meta(
        cls,
        db,
        factor_names: List[str],
    ) -> Tuple[dict[str, dict[str, Any]], Optional[date]]:
        history_meta: dict[str, dict[str, Any]] = {}
        latest_dates: List[date] = []
        unique_factor_names = list(
            dict.fromkeys(
                [str(item or "").strip() for item in factor_names if str(item or "").strip()]
            )
        )
        for factor_name in unique_factor_names:
            rows = await _call_optional_async(
                db,
                "get_factor_ic_history",
                factor_name,
                "20",
                cls.HISTORY_LIMIT,
                default=[],
            )
            if not isinstance(rows, list):
                rows = []
            meta = cls._history_summary(rows)
            if meta.get("history_count"):
                history_meta[factor_name] = meta
            latest_date = cls._parse_date(meta.get("latest_ic_date"))
            if latest_date is not None:
                latest_dates.append(latest_date)
        latest_factor_date = max(latest_dates) if latest_dates else None
        return history_meta, latest_factor_date

    @classmethod
    async def build(cls, db, snapshot: dict[str, Any]) -> dict[str, Any]:
        factor_ic = dict(snapshot.get("factor_ic") or {})
        factor_trend = dict(snapshot.get("factor_ic_trend") or {})

        ranked_factors: List[dict[str, Any]] = []
        names = list(
            dict.fromkeys([*factor_ic.keys(), *factor_trend.keys(), *FACTORY_RESEARCH_FACTORS])
        )
        history_meta, latest_factor_date = await cls._load_factor_history_meta(db, names)
        names = [
            name
            for name in names
            if name in factor_ic or name in factor_trend or bool(history_meta.get(str(name)))
        ]
        scheduler_status = dict(get_factor_scheduler().status() or {})
        scheduler_quality_flags = list(scheduler_status.get("quality_flags") or [])
        factor_ic_source = dict((snapshot.get("sources") or {}).get("factor_ic") or {})

        for factor_name in names:
            ic_value = cls._safe_float(factor_ic.get(factor_name))
            trend = cls._normalize_trend(factor_trend.get(factor_name))
            trend_bonus = 0.02 if trend == "rising" else (-0.02 if trend == "falling" else 0.0)
            meta = dict(history_meta.get(str(factor_name)) or {})
            ranked_factors.append(
                {
                    "factor_name": str(factor_name),
                    "ic_value": round(ic_value, 6),
                    "trend": trend,
                    "score": round(ic_value + trend_bonus, 6),
                    "preferred_strategy_types": cls._preferred_types_for_factor(str(factor_name)),
                    "history_count": cls._safe_int(meta.get("history_count")),
                    "latest_ic_date": meta.get("latest_ic_date"),
                    "stability_tag": meta.get("stability_tag") or "insufficient_history",
                    "decay_flag": bool(meta.get("decay_flag")),
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
            if cls._normalize_trend(item.get("trend")) == "rising"
            and cls._safe_float(item.get("ic_value")) > 0.0
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

        snapshot_date = cls._parse_date(snapshot.get("date"))
        freshness_days = cls._days_since(latest_factor_date, reference_date=snapshot_date)
        stale = bool(
            ("stale" in scheduler_quality_flags)
            or (freshness_days is not None and freshness_days > cls.STALE_AFTER_DAYS)
        )
        decay_factors = [
            str(item.get("factor_name") or "")
            for item in ranked_factors
            if bool(item.get("decay_flag"))
        ]
        stability_tags = {
            str(item.get("factor_name") or ""): str(item.get("stability_tag") or "insufficient_history")
            for item in ranked_factors
            if str(item.get("factor_name") or "")
        }
        quality_flags: List[str] = []
        if stale:
            quality_flags.append("stale")
        if decay_factors:
            quality_flags.append("decay_detected")
        factor_ic_status = str(factor_ic_source.get("status") or "")
        if factor_ic_status and factor_ic_status != "success":
            quality_flags.append(f"factor_ic_{factor_ic_status}")
        if not ranked_factors:
            quality_flags.append("empty")
        quality_flags.extend([flag for flag in scheduler_quality_flags if flag not in quality_flags])

        if not rationale:
            rationale.append("未识别到显著活跃因子，后续阶段回退到原始快照因子摘要逻辑。")
        if stale:
            rationale.append("因子研究数据存在 freshness 风险，后续阶段应降低置信度或触发补算。")
        if decay_factors:
            rationale.append(f"检测到衰减因子: {', '.join(decay_factors[:3])}")

        degraded = not bool(ranked_factors) or stale
        return {
            "active_factors": active_factors,
            "ranked_factors": ranked_factors,
            "positive_rising_factors": positive_rising_factors,
            "preferred_strategy_types": preferred_strategy_types,
            "research_rationale": rationale,
            "source_chain": [
                "snapshot.factor_ic",
                "snapshot.factor_ic_trend",
                f"db.factor_ic_history(limit={cls.HISTORY_LIMIT})",
                "factor_scheduler.status",
                "artifact_v2",
            ],
            "degraded": degraded,
            "latest_factor_date": latest_factor_date.isoformat() if latest_factor_date else None,
            "freshness_days": freshness_days,
            "stale": stale,
            "quality_flags": quality_flags,
            "factor_history": history_meta,
            "scheduler_status": {
                "running": bool(scheduler_status.get("running")),
                "last_run": scheduler_status.get("last_run"),
                "freshness_sec": scheduler_status.get("freshness_sec"),
                "quality_flags": scheduler_quality_flags,
            },
            "summary": {
                "active_factor_count": len(active_factors),
                "ranked_factor_count": len(ranked_factors),
                "top_factor_names": top_factor_names,
                "preferred_strategy_types": preferred_strategy_types,
                "degraded": degraded,
                "freshness_days": freshness_days,
                "latest_factor_date": latest_factor_date.isoformat() if latest_factor_date else None,
                "stale": stale,
                "quality_flags": quality_flags,
                "decay_factor_names": decay_factors,
                "stability_tags": stability_tags,
            },
        }


__all__ = ["FactorResearchBuilder"]
