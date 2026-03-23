"""策略工厂候选生成。"""

from __future__ import annotations

import json
import random
from typing import Any, Dict, List, Optional

from .constants import (
    CATEGORY_MINIMUMS,
    SPAWNER_EVENT_FILL_BUDGET_MAX,
    SPAWNER_FILL_BUDGET_MAX,
    SPAWNER_TARGET_TOTAL,
    preferred_strategy_types_for_factor,
)


class StrategySpawner:
    """根据每日数据快照生成候选策略。"""

    def __init__(self):
        self.last_report: dict = {
            "summary": {
                "candidate_count": 0,
                "source_counts": {},
                "strategy_type_counts": {},
                "quota_fill_count": 0,
                "signal_trigger_count": 0,
                "threshold_hit_count": 0,
            }
        }

    def get_last_report(self) -> dict:
        return self.last_report

    @staticmethod
    def _threshold(field: str, operator: str, threshold: Any, actual: Any, label: Optional[str] = None) -> dict:
        item = {
            "field": field,
            "operator": operator,
            "threshold": threshold,
            "actual": actual,
            "matched": True,
        }
        if label:
            item["label"] = label
        return item

    @staticmethod
    def _build_generation_reason(
        source: str,
        reason: str,
        trigger_signal: Optional[dict] = None,
        trigger_thresholds: Optional[List[dict]] = None,
        quota_fill: Optional[dict] = None,
        kind: str = "signal_trigger",
    ) -> dict:
        return {
            "kind": kind,
            "source": source,
            "summary": reason,
            "trigger_signal": trigger_signal or {},
            "trigger_thresholds": list(trigger_thresholds or []),
            "quota_fill": quota_fill,
        }

    @staticmethod
    def _build_spawn_report(candidates: List[dict]) -> dict:
        source_counts: Dict[str, int] = {}
        strategy_type_counts: Dict[str, int] = {}
        quota_fill_count = 0
        signal_trigger_count = 0
        threshold_hit_count = 0
        for candidate in candidates:
            generation_reason = candidate.get("generation_reason") or {}
            source = str(generation_reason.get("source") or "unknown")
            strategy_type = str(candidate.get("strategy_type") or "unknown")
            source_counts[source] = source_counts.get(source, 0) + 1
            strategy_type_counts[strategy_type] = strategy_type_counts.get(strategy_type, 0) + 1
            threshold_hit_count += len(candidate.get("trigger_thresholds") or [])
            if candidate.get("quota_fill"):
                quota_fill_count += 1
            else:
                signal_trigger_count += 1
        return {
            "summary": {
                "candidate_count": len(candidates),
                "source_counts": source_counts,
                "strategy_type_counts": strategy_type_counts,
                "quota_fill_count": quota_fill_count,
                "signal_trigger_count": signal_trigger_count,
                "threshold_hit_count": threshold_hit_count,
            }
        }

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _factor_research(snapshot: dict) -> dict:
        return dict(snapshot.get("factor_research") or {})

    @classmethod
    def _factor_maps(cls, snapshot: dict) -> tuple[Dict[str, float], Dict[str, str]]:
        artifact = cls._factor_research(snapshot)
        ranked_factors = list(artifact.get("ranked_factors") or [])
        factor_ic: Dict[str, float] = {}
        factor_trend: Dict[str, str] = {}
        for item in ranked_factors:
            name = str((item or {}).get("factor_name") or "").strip()
            if not name:
                continue
            factor_ic[name] = cls._safe_float((item or {}).get("ic_value"))
            factor_trend[name] = str((item or {}).get("trend") or "flat").strip().lower() or "flat"
        if factor_ic or factor_trend:
            return factor_ic, factor_trend
        active_candidate_pool = dict(artifact.get("active_candidate_pool") or {})
        top_candidates = list(active_candidate_pool.get("top_candidates") or [])
        for item in top_candidates:
            family = str((item or {}).get("family") or "").strip().lower()
            if not family:
                continue
            factor_ic[family] = max(
                factor_ic.get(family, 0.0),
                cls._safe_float((item or {}).get("total_score")) / 100.0,
            )
            factor_trend[family] = "rising"
        if factor_ic or factor_trend:
            return factor_ic, factor_trend
        return dict(snapshot.get("factor_ic") or {}), dict(snapshot.get("factor_ic_trend") or {})

    @classmethod
    def _strong_rising_factor_names(cls, snapshot: dict, minimum_ic: float = 0.04) -> List[str]:
        factor_ic, factor_trend = cls._factor_maps(snapshot)
        return [
            name
            for name, ic_value in factor_ic.items()
            if cls._safe_float(ic_value) >= minimum_ic and str(factor_trend.get(name) or "").strip().lower() == "rising"
        ]

    @classmethod
    def _factor_preferred_strategy_types(cls, snapshot: dict) -> List[str]:
        artifact = cls._factor_research(snapshot)
        preferred = [
            str(item).strip()
            for item in list(artifact.get("preferred_strategy_types") or [])
            if str(item).strip() in CATEGORY_MINIMUMS
        ]
        if preferred:
            return preferred

        factor_ic, factor_trend = cls._factor_maps(snapshot)
        derived: List[str] = []
        for factor_name in ("momentum", "value", "quality", "growth"):
            trend = str(factor_trend.get(factor_name) or "").strip().lower()
            ic_value = cls._safe_float(factor_ic.get(factor_name))
            if trend == "rising" and ic_value > 0.0:
                mapped = tuple(preferred_strategy_types_for_factor(factor_name, default=[]))
                for strategy_type in mapped:
                    if strategy_type in CATEGORY_MINIMUMS and strategy_type not in derived:
                        derived.append(strategy_type)
        return derived

    def spawn(self, snapshot: dict) -> List[dict]:
        signal_candidates: List[dict] = []
        event_ready = self._event_research_ready(snapshot)
        event_ready_supplemental = self._event_ready_supports_local_fill(snapshot)
        fear_greed = float(snapshot.get("fear_greed_index") or 50.0)
        if not event_ready or fear_greed < 30 or fear_greed > 70:
            signal_candidates += self._from_fear_greed(snapshot)
        signal_candidates += self._from_factor_ic(snapshot)
        if not event_ready or event_ready_supplemental:
            signal_candidates += self._from_volatility(snapshot)
            signal_candidates += self._from_fund_flow(snapshot)
        signal_candidates += self._expand_signal_variants(snapshot, signal_candidates)
        quota_candidates = self._fill_gaps(snapshot, signal_candidates)
        candidates = [*signal_candidates, *quota_candidates]
        self.last_report = self._build_spawn_report(candidates)
        return candidates

    @staticmethod
    def _event_research_ready(snapshot: dict) -> bool:
        event_driven = dict(snapshot.get("event_driven") or {})
        return bool(int(event_driven.get("event_count") or 0) or int(event_driven.get("tasks_ready_count") or 0))

    @staticmethod
    def _event_ready_supports_local_fill(snapshot: dict) -> bool:
        strong_factor_count = len(StrategySpawner._strong_rising_factor_names(snapshot, minimum_ic=0.04))
        fear_greed = float(snapshot.get("fear_greed_index") or 50.0)
        volatility = float(dict(snapshot.get("fg_components") or {}).get("volatility") or 50.0)
        north_3d = abs(float(snapshot.get("north_fund_3d_net") or 0.0)) >= 5_000_000_000
        margin_5d = abs(float(snapshot.get("margin_5d_change_pct") or 0.0)) >= 2.0
        extreme_fg = abs(fear_greed - 50.0) >= 18.0
        extreme_volatility = volatility <= 35.0 or volatility >= 65.0
        return bool(strong_factor_count or extreme_fg or extreme_volatility or north_3d or margin_5d)

    @staticmethod
    def _generated_type_counts(candidates: List[dict]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in list(candidates or []):
            strategy_type = str(item.get("strategy_type") or "").strip()
            if not strategy_type:
                continue
            counts[strategy_type] = counts.get(strategy_type, 0) + 1
        return counts

    @classmethod
    def _preferred_fill_types(cls, snapshot: dict, current_counts: Optional[Dict[str, int]] = None) -> List[str]:
        preferred: List[str] = []

        def add(*types: str) -> None:
            for strategy_type in types:
                if strategy_type in CATEGORY_MINIMUMS and strategy_type not in preferred:
                    preferred.append(strategy_type)

        fear_greed = int(snapshot.get("fear_greed_index") or 50)
        if fear_greed <= 35:
            add("rsi", "value_factor", "quality_factor", "macro_timing")
        elif fear_greed >= 65:
            add("momentum", "growth_factor", "quality_factor", "ma_cross")
        else:
            add("ma_cross", "momentum", "quality_factor", "value_factor")

        north_3d = float(snapshot.get("north_fund_3d_net") or 0.0)
        if north_3d >= 5_000_000_000:
            add("growth_factor", "quality_factor", "momentum")
        elif north_3d <= -5_000_000_000:
            add("value_factor", "macro_timing", "rsi")

        margin_5d = float(snapshot.get("margin_5d_change_pct") or 0.0)
        if margin_5d >= 2.0:
            add("momentum", "ma_cross")
        elif margin_5d <= -2.0:
            add("rsi", "value_factor")

        add(*cls._factor_preferred_strategy_types(snapshot))

        event_driven = dict(snapshot.get("event_driven") or {})
        if int(event_driven.get("event_count") or 0) > 0 or int(event_driven.get("tasks_ready_count") or 0) > 0:
            add("momentum", "ma_cross", "quality_factor", "value_factor")

        if not preferred:
            add("ma_cross", "momentum", "quality_factor")

        counts = current_counts or {}
        return sorted(preferred, key=lambda strategy_type: (int(counts.get(strategy_type) or 0), preferred.index(strategy_type)))

    @staticmethod
    def _quota_fill_budget(snapshot: dict, signal_candidate_count: int) -> int:
        completeness = dict(snapshot.get("completeness") or {})
        completion_ratio = float(completeness.get("completion_ratio") or 1.0)
        event_ready = StrategySpawner._event_research_ready(snapshot)
        target_total = SPAWNER_TARGET_TOTAL
        if completion_ratio < 1.0:
            target_total = min(target_total, max(4, int(round(SPAWNER_TARGET_TOTAL * 0.75))))
        budget = max(0, target_total - max(0, int(signal_candidate_count or 0)))
        if event_ready:
            if signal_candidate_count <= 0 or not StrategySpawner._event_ready_supports_local_fill(snapshot):
                return 0
            return min(budget, SPAWNER_EVENT_FILL_BUDGET_MAX)
        return min(budget, SPAWNER_FILL_BUDGET_MAX)

    @staticmethod
    def _signal_expansion_budget(snapshot: dict, signal_candidate_count: int) -> int:
        if signal_candidate_count <= 0:
            return 0
        remaining = max(0, SPAWNER_TARGET_TOTAL - max(0, int(signal_candidate_count or 0)))
        if remaining <= 0:
            return 0
        strong_factor_count = len(StrategySpawner._strong_rising_factor_names(snapshot, minimum_ic=0.04))
        extreme_fg = abs(float(snapshot.get("fear_greed_index") or 50.0) - 50.0) >= 18.0
        north_3d = abs(float(snapshot.get("north_fund_3d_net") or 0.0)) >= 5_000_000_000
        margin_5d = abs(float(snapshot.get("margin_5d_change_pct") or 0.0)) >= 2.0
        signal_strength = strong_factor_count + int(extreme_fg) + int(north_3d) + int(margin_5d)
        if signal_strength <= 0:
            return 0
        return min(remaining, SPAWNER_FILL_BUDGET_MAX, max(1, signal_strength + 1))

    def _expand_signal_variants(self, snapshot: dict, signal_candidates: List[dict]) -> List[dict]:
        expansion_budget = self._signal_expansion_budget(snapshot, len(signal_candidates))
        if expansion_budget <= 0:
            return []

        current_counts = self._generated_type_counts(signal_candidates)
        threshold_hits: Dict[str, int] = {}
        preferred_types = self._preferred_fill_types(snapshot, current_counts)
        for item in list(signal_candidates or []):
            strategy_type = str(item.get("strategy_type") or "").strip()
            if not strategy_type:
                continue
            threshold_hits[strategy_type] = threshold_hits.get(strategy_type, 0) + len(item.get("trigger_thresholds") or [])

        ranked_types = sorted(
            current_counts.keys(),
            key=lambda strategy_type: (
                int(current_counts.get(strategy_type) or 0),
                int(threshold_hits.get(strategy_type) or 0),
                -(preferred_types.index(strategy_type) if strategy_type in preferred_types else len(preferred_types)),
            ),
            reverse=True,
        )
        if not ranked_types:
            return []

        existing_keys = {
            (
                str(item.get("strategy_type") or ""),
                json.dumps(item.get("params") or {}, sort_keys=True, ensure_ascii=False, default=str),
            )
            for item in list(signal_candidates or [])
        }
        out: List[dict] = []
        variation_counts: Dict[str, int] = {}

        for strategy_type in ranked_types:
            if len(out) >= expansion_budget:
                break
            desired_variants = min(
                3,
                max(
                    1,
                    int(current_counts.get(strategy_type) or 0) - 1 + (1 if int(threshold_hits.get(strategy_type) or 0) >= 3 else 0),
                ),
            )
            for _ in range(desired_variants):
                if len(out) >= expansion_budget:
                    break
                slot_index = int(current_counts.get(strategy_type) or 0) + int(variation_counts.get(strategy_type) or 0)
                params = self._varied_defaults(strategy_type, slot_index)
                key = (strategy_type, json.dumps(params or {}, sort_keys=True, ensure_ascii=False, default=str))
                if key in existing_keys:
                    continue
                existing_keys.add(key)
                variation_counts[strategy_type] = int(variation_counts.get(strategy_type) or 0) + 1
                out.append(
                    self._make(
                        strategy_type,
                        params,
                        f"{strategy_type} 强信号延展参数变体#{variation_counts[strategy_type]}",
                        source="signal_variation",
                        trigger_signal={
                            "field": f"signal_type_counts.{strategy_type}",
                            "value": int(current_counts.get(strategy_type) or 0),
                            "threshold_hits": int(threshold_hits.get(strategy_type) or 0),
                        },
                        trigger_thresholds=[
                            self._threshold(
                                f"signal_type_counts.{strategy_type}",
                                ">=",
                                1,
                                int(current_counts.get(strategy_type) or 0),
                                "强信号变体扩容",
                            )
                        ],
                    )
                )
        return out

    def _from_fear_greed(self, snapshot: dict) -> List[dict]:
        out: List[dict] = []
        fear_greed = snapshot.get("fear_greed_index", 50)
        if fear_greed < 30:
            out.append(self._make("rsi", {"rsi_period": 14, "oversold": 25, "overbought": 75}, f"恐贪{fear_greed}，恐惧区RSI抄底", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "fear"}, trigger_thresholds=[self._threshold("fear_greed_index", "<", 30, fear_greed, "恐贪阈值")]))
            out.append(self._make("rsi", {"rsi_period": 6, "oversold": 20, "overbought": 80}, f"恐贪{fear_greed}，短周期RSI超跌", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "fear"}, trigger_thresholds=[self._threshold("fear_greed_index", "<", 30, fear_greed, "恐贪阈值")]))
            out.append(self._make("value_factor", {"lookback": 60, "buy_quantile": 0.85, "sell_quantile": 0.15}, f"恐贪{fear_greed}，恐惧期精选价值", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "fear"}, trigger_thresholds=[self._threshold("fear_greed_index", "<", 30, fear_greed, "恐贪阈值")]))
        elif fear_greed > 70:
            out.append(self._make("momentum", {"lookback": 5, "threshold": 0.01}, f"恐贪{fear_greed}，贪婪期短周期动量", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "greed"}, trigger_thresholds=[self._threshold("fear_greed_index", ">", 70, fear_greed, "恐贪阈值")]))
            out.append(self._make("momentum", {"lookback": 10, "threshold": 0.02}, f"恐贪{fear_greed}，贪婪期中周期动量", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "greed"}, trigger_thresholds=[self._threshold("fear_greed_index", ">", 70, fear_greed, "恐贪阈值")]))
            out.append(self._make("growth_factor", {"lookback": 40, "buy_quantile": 0.85, "sell_quantile": 0.15}, f"恐贪{fear_greed}，贪婪期成长加速", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "greed"}, trigger_thresholds=[self._threshold("fear_greed_index", ">", 70, fear_greed, "恐贪阈值")]))
            out.append(self._make("rsi", {"rsi_period": 14, "oversold": 35, "overbought": 65}, f"恐贪{fear_greed}，贪婪期RSI逃顶", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "greed"}, trigger_thresholds=[self._threshold("fear_greed_index", ">", 70, fear_greed, "恐贪阈值")]))
        else:
            out.append(self._make("ma_cross", {"short_period": 5, "long_period": 20}, f"恐贪{fear_greed}，中性标准均线", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "neutral"}, trigger_thresholds=[self._threshold("fear_greed_index", ">=", 30, fear_greed, "恐贪下界"), self._threshold("fear_greed_index", "<=", 70, fear_greed, "恐贪上界")]))
            out.append(self._make("momentum", {"lookback": 20, "threshold": 0.02}, f"恐贪{fear_greed}，中性标准动量", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "neutral"}, trigger_thresholds=[self._threshold("fear_greed_index", ">=", 30, fear_greed, "恐贪下界"), self._threshold("fear_greed_index", "<=", 70, fear_greed, "恐贪上界")]))
        return out

    def _from_factor_ic(self, snapshot: dict) -> List[dict]:
        out: List[dict] = []
        factor_ic, trend = self._factor_maps(snapshot)

        for factor_name, ic_value in factor_ic.items():
            trend_value = trend.get(factor_name, "flat")
            if ic_value > 0.03 and trend_value == "rising":
                if factor_name == "momentum":
                    for lookback in [5, 10, 20]:
                        out.append(self._make("momentum", {"lookback": lookback, "threshold": 0.02}, f"momentum IC={ic_value:.3f}上升，{lookback}日动量", source="factor_ic", trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value}, trigger_thresholds=[self._threshold(f"factor_ic.{factor_name}", ">", 0.03, ic_value, "IC阈值"), self._threshold(f"factor_ic_trend.{factor_name}", "==", "rising", trend_value, "趋势阈值")]))
                elif factor_name == "value":
                    out.append(self._make("value_factor", {"lookback": 60, "buy_quantile": 0.8, "sell_quantile": 0.2}, f"value IC={ic_value:.3f}上升", source="factor_ic", trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value}, trigger_thresholds=[self._threshold(f"factor_ic.{factor_name}", ">", 0.03, ic_value, "IC阈值"), self._threshold(f"factor_ic_trend.{factor_name}", "==", "rising", trend_value, "趋势阈值")]))
                elif factor_name == "quality":
                    out.append(self._make("quality_factor", {"lookback": 60, "buy_quantile": 0.8, "sell_quantile": 0.2}, f"quality IC={ic_value:.3f}上升", source="factor_ic", trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value}, trigger_thresholds=[self._threshold(f"factor_ic.{factor_name}", ">", 0.03, ic_value, "IC阈值"), self._threshold(f"factor_ic_trend.{factor_name}", "==", "rising", trend_value, "趋势阈值")]))
                elif factor_name == "reversal":
                    out.append(self._make("rsi", {"rsi_period": 14, "oversold": 30, "overbought": 70}, f"reversal IC={ic_value:.3f}上升，反转有效", source="factor_ic", trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value}, trigger_thresholds=[self._threshold(f"factor_ic.{factor_name}", ">", 0.03, ic_value, "IC阈值"), self._threshold(f"factor_ic_trend.{factor_name}", "==", "rising", trend_value, "趋势阈值")]))
            elif ic_value < -0.02 and trend_value == "falling" and factor_name == "momentum":
                out.append(self._make("rsi", {"rsi_period": 14, "oversold": 30, "overbought": 70}, f"momentum IC={ic_value:.3f}下降，转反转", source="factor_ic", trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value}, trigger_thresholds=[self._threshold(f"factor_ic.{factor_name}", "<", -0.02, ic_value, "IC阈值"), self._threshold(f"factor_ic_trend.{factor_name}", "==", "falling", trend_value, "趋势阈值")]))

        weights: Dict[str, float] = {}
        factor_signal_count = 0
        for factor_name in ["value", "quality", "growth"]:
            ic_value = factor_ic.get(factor_name, 0)
            trend_value = trend.get(factor_name, "flat")
            if trend_value == "rising":
                weights[factor_name] = max(0.1, 0.33 + ic_value * 2)
                if float(ic_value or 0.0) > 0.0:
                    factor_signal_count += 1
            elif trend_value == "falling":
                weights[factor_name] = max(0.05, 0.33 - abs(ic_value) * 2)
                if float(ic_value or 0.0) < 0.0:
                    factor_signal_count += 1
            else:
                weights[factor_name] = 0.33
        total = sum(weights.values()) or 1.0
        weights = {key: round(value / total, 2) for key, value in weights.items()}
        if factor_signal_count > 0:
            out.append(self._make("multi_factor", {"factor_weights": weights, "lookback": 60}, f"IC驱动多因子权重: {weights}", source="factor_ic", trigger_signal={"field": "factor_ic_weights", "value": weights}, trigger_thresholds=[self._threshold("factor_ic_weights", "derived_from", {"positive_ic": 0.0, "trend_preference": "rising"}, {"factor_ic": factor_ic, "factor_ic_trend": trend, "weights": weights}, "权重派生规则")]))
        return out

    def _from_volatility(self, snapshot: dict) -> List[dict]:
        out: List[dict] = []
        volatility = snapshot.get("fg_components", {}).get("volatility", 50)
        if volatility < 35:
            out.append(self._make("ma_cross", {"short_period": 10, "long_period": 60}, f"波动率{volatility}，高波动长周期均线", source="volatility", trigger_signal={"field": "fg_components.volatility", "value": volatility}, trigger_thresholds=[self._threshold("fg_components.volatility", "<", 35, volatility, "波动率阈值")]))
            out.append(self._make("macro_timing", {"fear_threshold": 30, "greed_threshold": 70, "lookback": 30}, f"波动率{volatility}，高波动宏观择时", source="volatility", trigger_signal={"field": "fg_components.volatility", "value": volatility}, trigger_thresholds=[self._threshold("fg_components.volatility", "<", 35, volatility, "波动率阈值")]))
        elif volatility > 65:
            out.append(self._make("ma_cross", {"short_period": 3, "long_period": 15}, f"波动率{volatility}，低波动短周期均线", source="volatility", trigger_signal={"field": "fg_components.volatility", "value": volatility}, trigger_thresholds=[self._threshold("fg_components.volatility", ">", 65, volatility, "波动率阈值")]))
        return out

    def _from_fund_flow(self, snapshot: dict) -> List[dict]:
        out: List[dict] = []
        north_3d = snapshot.get("north_fund_3d_net", 0)
        margin_5d = snapshot.get("margin_5d_change_pct", 0)

        if north_3d > 5_000_000_000:
            out.append(self._make("growth_factor", {"lookback": self._jitter(40, 30, 60), "buy_quantile": 0.85, "sell_quantile": 0.15}, f"北向3日净流入{north_3d / 1e8:.0f}亿，成长加速", source="fund_flow", trigger_signal={"field": "north_fund_3d_net", "value": north_3d}, trigger_thresholds=[self._threshold("north_fund_3d_net", ">", 5_000_000_000, north_3d, "北向净流入阈值")]))
            out.append(self._make("quality_factor", {"lookback": self._jitter(60, 40, 80), "buy_quantile": 0.8, "sell_quantile": 0.2}, f"北向3日净流入{north_3d / 1e8:.0f}亿，质量优选", source="fund_flow", trigger_signal={"field": "north_fund_3d_net", "value": north_3d}, trigger_thresholds=[self._threshold("north_fund_3d_net", ">", 5_000_000_000, north_3d, "北向净流入阈值")]))
        elif north_3d < -5_000_000_000:
            out.append(self._make("value_factor", {"lookback": self._jitter(60, 40, 80), "buy_quantile": 0.85, "sell_quantile": 0.15}, f"北向3日净流出{abs(north_3d) / 1e8:.0f}亿，价值防御", source="fund_flow", trigger_signal={"field": "north_fund_3d_net", "value": north_3d}, trigger_thresholds=[self._threshold("north_fund_3d_net", "<", -5_000_000_000, north_3d, "北向净流出阈值")]))
            out.append(self._make("macro_timing", {"fear_threshold": 30, "greed_threshold": 60, "lookback": self._jitter(25, 15, 35)}, f"北向3日净流出{abs(north_3d) / 1e8:.0f}亿，宏观择时", source="fund_flow", trigger_signal={"field": "north_fund_3d_net", "value": north_3d}, trigger_thresholds=[self._threshold("north_fund_3d_net", "<", -5_000_000_000, north_3d, "北向净流出阈值")]))

        if margin_5d > 2.0:
            out.append(self._make("momentum", {"lookback": self._jitter(5, 3, 10), "threshold": 0.01}, f"融资5日增速{margin_5d:.1f}%，短周期动量", source="fund_flow", trigger_signal={"field": "margin_5d_change_pct", "value": margin_5d}, trigger_thresholds=[self._threshold("margin_5d_change_pct", ">", 2.0, margin_5d, "融资增速阈值")]))
        elif margin_5d < -2.0:
            out.append(self._make("rsi", {"rsi_period": self._jitter(6, 4, 10), "oversold": 20, "overbought": 80}, f"融资5日降速{abs(margin_5d):.1f}%，RSI超跌", source="fund_flow", trigger_signal={"field": "margin_5d_change_pct", "value": margin_5d}, trigger_thresholds=[self._threshold("margin_5d_change_pct", "<", -2.0, margin_5d, "融资降速阈值")]))
        return out

    def _fill_gaps(self, snapshot: dict, current_candidates: Optional[List[dict]] = None) -> List[dict]:
        current_candidates = list(current_candidates or [])
        current_counts = self._generated_type_counts(current_candidates)
        fill_budget = self._quota_fill_budget(snapshot, len(current_candidates))
        if fill_budget <= 0:
            return []

        preferred_types = self._preferred_fill_types(snapshot, current_counts)
        out: List[dict] = []
        fill_counts: Dict[str, int] = {}

        def maybe_add(strategy_type: str, preferred_rank: int) -> bool:
            current = int(current_counts.get(strategy_type) or 0) + int(fill_counts.get(strategy_type) or 0)
            desired_generated_count = 1 if preferred_rank > 2 else 2
            if current >= desired_generated_count:
                return False
            slot_index = int(fill_counts.get(strategy_type) or 0) + 1
            params = self._varied_defaults(strategy_type, slot_index - 1)
            quota_fill = {
                "strategy_type": strategy_type,
                "current_count": int(current_counts.get(strategy_type) or 0),
                "minimum_required": CATEGORY_MINIMUMS.get(strategy_type, 0),
                "desired_generated_count": desired_generated_count,
                "fill_budget": fill_budget,
                "preferred_rank": preferred_rank,
                "slot_index": slot_index,
            }
            out.append(
                self._make(
                    strategy_type,
                    params,
                    f"{strategy_type}研究信号不足，按市场状态补位#{slot_index}",
                    source="quota_fill",
                    trigger_signal={"field": f"generated_type_counts.{strategy_type}", "value": int(current_counts.get(strategy_type) or 0)},
                    trigger_thresholds=[
                        self._threshold(
                            f"generated_type_counts.{strategy_type}",
                            "<",
                            desired_generated_count,
                            int(current_counts.get(strategy_type) or 0),
                            "研究候选补位阈值",
                        )
                    ],
                    quota_fill=quota_fill,
                    kind="quota_fill",
                )
            )
            fill_counts[strategy_type] = slot_index
            return True

        for pass_index in range(2):
            for preferred_rank, strategy_type in enumerate(preferred_types, 1):
                if len(out) >= fill_budget:
                    break
                if pass_index == 0 and int(current_counts.get(strategy_type) or 0) > 0:
                    continue
                maybe_add(strategy_type, preferred_rank)
            if len(out) >= fill_budget:
                break

        return out[:fill_budget]

    @staticmethod
    def _jitter(base: int, lo: int, hi: int) -> int:
        delta = max(1, int(base * 0.2))
        return max(lo, min(hi, base + random.randint(-delta, delta)))

    @staticmethod
    def _jitter_f(base: float, lo: float, hi: float) -> float:
        delta = max(0.01, base * 0.15)
        return round(max(lo, min(hi, base + random.uniform(-delta, delta))), 2)

    def _varied_defaults(self, strategy_type: str, idx: int) -> dict:
        if strategy_type == "momentum":
            lookbacks = [10, 20, 30]
            lookback = lookbacks[idx % len(lookbacks)]
            return {"lookback": self._jitter(lookback, 5, 40), "threshold": self._jitter_f(0.02, 0.005, 0.05)}
        if strategy_type == "ma_cross":
            pairs = [(5, 20), (10, 30), (5, 60)]
            short_period, long_period = pairs[idx % len(pairs)]
            short_period = self._jitter(short_period, 3, 15)
            long_period = self._jitter(long_period, max(short_period + 5, 15), 80)
            return {"short_period": short_period, "long_period": long_period}
        if strategy_type == "rsi":
            periods = [6, 14, 21]
            period = periods[idx % len(periods)]
            return {"rsi_period": self._jitter(period, 4, 28), "oversold": self._jitter(30, 20, 40), "overbought": self._jitter(70, 60, 80)}
        if strategy_type == "value_factor":
            return {"lookback": self._jitter(60, 30, 90), "buy_quantile": self._jitter_f(0.8, 0.7, 0.9), "sell_quantile": self._jitter_f(0.2, 0.1, 0.3)}
        if strategy_type == "quality_factor":
            return {"lookback": self._jitter(60, 30, 90), "buy_quantile": self._jitter_f(0.8, 0.7, 0.9), "sell_quantile": self._jitter_f(0.2, 0.1, 0.3)}
        if strategy_type == "growth_factor":
            return {"lookback": self._jitter(40, 25, 70), "buy_quantile": self._jitter_f(0.8, 0.7, 0.9), "sell_quantile": self._jitter_f(0.2, 0.1, 0.3)}
        if strategy_type == "multi_factor":
            weights = {
                "value": random.uniform(0.2, 0.5),
                "quality": random.uniform(0.2, 0.5),
                "growth": random.uniform(0.2, 0.5),
            }
            total = sum(weights.values())
            weights = {key: round(value / total, 2) for key, value in weights.items()}
            return {"factor_weights": weights, "lookback": self._jitter(60, 30, 90)}
        if strategy_type == "macro_timing":
            return {"fear_threshold": self._jitter(35, 25, 45), "greed_threshold": self._jitter(65, 55, 75), "lookback": self._jitter(20, 10, 35)}
        return {}

    @staticmethod
    def _make(
        strategy_type: str,
        params: dict,
        reason: str = "",
        *,
        source: str = "unknown",
        trigger_signal: Optional[dict] = None,
        trigger_thresholds: Optional[List[dict]] = None,
        quota_fill: Optional[dict] = None,
        kind: str = "signal_trigger",
    ) -> dict:
        generation_reason = StrategySpawner._build_generation_reason(
            source=source,
            reason=reason,
            trigger_signal=trigger_signal,
            trigger_thresholds=trigger_thresholds,
            quota_fill=quota_fill,
            kind=kind,
        )
        return {
            "strategy_type": strategy_type,
            "params": params,
            "spawn_reason": reason,
            "generation_reason": generation_reason,
            "trigger_signal": generation_reason["trigger_signal"],
            "trigger_thresholds": generation_reason["trigger_thresholds"],
            "quota_fill": quota_fill,
        }
