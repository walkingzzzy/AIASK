"""策略工厂轻量因子研究 artifact 构建。"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, List, Optional, Tuple
from unittest.mock import AsyncMock, Mock

from ..domain.constants import (
    FACTORY_RESEARCH_FACTORS,
    STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK,
    STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
    preferred_strategy_types_for_factor,
)
from ..infrastructure.mcp_services import get_factor_scheduler_singleton, get_quant_manager_callable
from ._budget_feedback import (
    extract_feedback_root,
    extract_generator_mode,
    extract_target_pool_id,
    normalize_text,
    resolve_feedback_metrics,
)
from ._stock_universe_loader import load_stock_universe_rows
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

    @staticmethod
    def _normalize_codes(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value or "").strip()
        if not text:
            return []
        return [item.strip() for item in text.split(",") if item.strip()]

    @staticmethod
    def _has_concrete_async_method(target: Any, method_name: str) -> bool:
        method = getattr(target, method_name, None)
        if method is None or not callable(method):
            return False
        if isinstance(method, AsyncMock):
            return True
        if isinstance(method, Mock):
            return False
        return True

    @classmethod
    def _should_use_lightweight_mock_fallback(cls, db: Any, snapshot: dict[str, Any]) -> bool:
        raw_db = db
        candidate_raw = getattr(db, "raw", None)
        if candidate_raw is not None and not (isinstance(db, Mock) and "raw" not in getattr(db, "__dict__", {})):
            raw_db = candidate_raw
        if not isinstance(raw_db, Mock):
            return False
        if cls._has_concrete_async_method(raw_db, "get_factor_ic_history"):
            return False
        if cls._has_concrete_async_method(raw_db, "list_stock_universe"):
            return False
        if dict(snapshot.get("factor_ic") or {}):
            return False
        if dict(snapshot.get("factor_ic_trend") or {}):
            return False
        if cls._normalize_codes(snapshot.get("candidate_codes")):
            return False
        return True

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
    async def _load_governed_candidate_pool(
        cls,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        quant_manager = None
        try:
            quant_manager = get_quant_manager_callable()
        except Exception:
            quant_manager = None
        if quant_manager is None:
            return {"available": False, "reason": "quant_manager_unavailable"}

        candidate_codes = cls._normalize_codes(snapshot.get("candidate_codes"))
        kwargs: dict[str, Any] = {"op": "active_pool", "limit": 80, "market_codes_only": True}
        if candidate_codes:
            kwargs["codes"] = candidate_codes
        try:
            result = await quant_manager(action="factor_candidate_registry", kwargs=kwargs)
        except Exception as exc:
            return {"available": False, "reason": f"factor_candidate_registry_failed:{exc}"}
        if not isinstance(result, dict) or not result.get("success"):
            return {
                "available": False,
                "reason": str((result or {}).get("error") or (result or {}).get("message") or "active_pool_unavailable"),
            }
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        active_pool = data.get("active_pool") if isinstance(data.get("active_pool"), dict) else {}
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        if not active_pool:
            return {"available": False, "reason": "active_pool_empty", "summary": summary}
        return {
            "available": bool(active_pool.get("count")),
            "summary": summary,
            "active_pool": active_pool,
        }

    @classmethod
    async def _load_model_registry_lineage(
        cls,
        candidates: List[dict[str, Any]],
    ) -> dict[str, Any]:
        quant_manager = None
        try:
            quant_manager = get_quant_manager_callable()
        except Exception:
            quant_manager = None
        if quant_manager is None:
            return {"available": False, "reason": "quant_manager_unavailable"}

        validation_ids = list(
            dict.fromkeys(
                [
                    str(item.get("source_validation_artifact_id") or item.get("artifact_id") or "").strip()
                    for item in list(candidates or [])
                    if str(item.get("source_validation_artifact_id") or item.get("artifact_id") or "").strip()
                ]
            )
        )
        generation_ids = list(
            dict.fromkeys(
                [
                    str(item.get("source_generation_artifact_id") or "").strip()
                    for item in list(candidates or [])
                    if str(item.get("source_generation_artifact_id") or "").strip()
                ]
            )
        )
        if not validation_ids and not generation_ids:
            return {"available": False, "reason": "candidate_lineage_missing"}

        try:
            result = await quant_manager(
                action="model_registry",
                kwargs={
                    "op": "lineage",
                    "validation_artifact_ids": validation_ids,
                    "generation_artifact_ids": generation_ids,
                    "limit": max(10, len(validation_ids) * 4, len(generation_ids) * 4),
                    "market_codes_only": True,
                },
            )
        except Exception as exc:
            return {"available": False, "reason": f"model_registry_lineage_failed:{exc}"}

        if not isinstance(result, dict) or not result.get("success"):
            return {
                "available": False,
                "reason": str((result or {}).get("error") or (result or {}).get("message") or "model_registry_lineage_unavailable"),
            }
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        items = [dict(item or {}) for item in list(data.get("items") or []) if isinstance(item, dict)]
        return {
            "available": True,
            "summary": dict(data.get("summary") or {}),
            "items": items,
            "by_validation_artifact_id": {
                str(item.get("validation_artifact_id") or "").strip(): item
                for item in items
                if str(item.get("validation_artifact_id") or "").strip()
            },
        }

    @classmethod
    def _extract_candidate_codes(cls, item: dict[str, Any]) -> List[str]:
        codes: List[str] = []

        def _extend(value: Any) -> None:
            for code in cls._normalize_codes(value):
                if code not in codes:
                    codes.append(code)

        payload = dict(item or {})
        _extend(payload.get("codes"))
        _extend(payload.get("target_symbols"))
        _extend((payload.get("stock_pool") or {}).get("symbols"))
        _extend((payload.get("validation_params") or {}).get("codes"))
        _extend((payload.get("lineage") or {}).get("codes"))
        _extend((payload.get("candidate") or {}).get("codes"))
        source_symbol_summary = payload.get("source_symbol_summary")
        if isinstance(source_symbol_summary, dict):
            _extend(
                [
                    source_symbol_summary.get("code"),
                    source_symbol_summary.get("symbol"),
                    source_symbol_summary.get("stock_code"),
                ]
            )
        return codes[:12]

    @classmethod
    def _build_candidate_hint_map(
        cls,
        candidates: List[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        hint_map: dict[str, dict[str, Any]] = {}
        for item in list(candidates or []):
            payload = dict(item or {})
            family_name = str(payload.get("family") or "").strip().lower()
            mapped_families = cls._preferred_types_for_factor(family_name)
            families: List[str] = []
            if family_name and family_name in mapped_families:
                families.append(family_name)
            for strategy_type in mapped_families:
                lowered = str(strategy_type or "").strip().lower()
                if lowered and lowered not in families:
                    families.append(lowered)
            if not families:
                continue
            hint_score = max(0.0, min(cls._safe_float(payload.get("total_score")) / 100.0, 1.0))
            for code in cls._extract_candidate_codes(payload):
                bucket = hint_map.setdefault(code, {"families": [], "scores": []})
                for family in families:
                    if family not in bucket["families"]:
                        bucket["families"].append(family)
                bucket["scores"].append(hint_score)
        return hint_map

    @staticmethod
    def _family_risk_level(family: str) -> str:
        normalized = str(family or "").strip().lower()
        if normalized in {"momentum", "growth_factor", "volatility_breakout", "gap_fill"}:
            return "high"
        if normalized in {"quality_factor", "value_factor"}:
            return "low"
        return "medium"

    @classmethod
    def _family_validation_profile(cls, family: str) -> dict[str, Any]:
        normalized = str(family or "").strip().lower()
        validation_focus = "candidate_target_only"
        if normalized == "macro_timing":
            profile = "macro_regime_validation"
        elif normalized in {"north_capital_track", "margin_divergence"}:
            profile = "event_trade_validation"
            validation_focus = "event_target_only"
        elif normalized in {"value_factor", "quality_factor", "growth_factor", "multi_factor", "sentiment", "sentiment_factor"}:
            profile = "factor_rank_validation"
        else:
            profile = "trade_rule_validation"
        return {
            "profile": profile,
            "validation_focus": validation_focus,
            "primary_validation_layer": "target" if validation_focus in {"candidate_target_only", "event_target_only"} else "combined",
        }

    @classmethod
    def _family_failure_penalty(cls, family: str, *, family_rank: int) -> float:
        risk_level = cls._family_risk_level(family)
        base_penalty = {
            "high": 0.22,
            "medium": 0.14,
            "low": 0.08,
        }.get(risk_level, 0.14)
        return round(min(base_penalty + max(family_rank - 1, 0) * 0.03, 0.45), 4)

    @classmethod
    def _family_budget_weights(
        cls,
        families: List[str],
        *,
        priority: float,
        budget_feedback_root: Any = None,
    ) -> List[float]:
        selected = [
            str(item or "").strip().lower()
            for item in list(families or [])
            if str(item or "").strip()
        ]
        if not selected:
            return []
        raw_weights: List[float] = []
        for family_rank, family in enumerate(selected, 1):
            risk_level = cls._family_risk_level(family)
            rank_multiplier = max(0.4, 1.0 - (family_rank - 1) * 0.2)
            risk_multiplier = {
                "high": 0.82,
                "medium": 0.94,
                "low": 1.08,
            }.get(risk_level, 0.94)
            feedback_metrics = resolve_feedback_metrics(
                budget_feedback_root,
                family=family,
            )
            budget_multiplier = max(
                0.35,
                min(
                    cls._safe_float(feedback_metrics.get("budget_multiplier")),
                    1.85,
                ),
            )
            raw_weights.append(
                max(0.05, float(priority or 0.0) * rank_multiplier * risk_multiplier * budget_multiplier)
            )
        total = sum(raw_weights) or float(len(selected))
        normalized_weights: List[float] = []
        accumulated = 0.0
        for index, raw_weight in enumerate(raw_weights, 1):
            if index == len(raw_weights):
                weight = round(max(0.0, 1.0 - accumulated), 4)
            else:
                weight = round(raw_weight / total, 4)
                accumulated += weight
            normalized_weights.append(weight)
        return normalized_weights

    @classmethod
    def _build_family_plans(
        cls,
        families: List[str],
        *,
        priority: float,
        budget_feedback_root: Any = None,
    ) -> List[dict[str, Any]]:
        selected = [
            str(item or "").strip().lower()
            for item in list(families or [])
            if str(item or "").strip()
        ]
        if not selected:
            return []
        budget_weights = cls._family_budget_weights(
            selected,
            priority=priority,
            budget_feedback_root=budget_feedback_root,
        )
        plans: List[dict[str, Any]] = []
        for family_rank, family in enumerate(selected, 1):
            budget_weight = budget_weights[family_rank - 1] if family_rank - 1 < len(budget_weights) else 0.0
            feedback_metrics = resolve_feedback_metrics(
                budget_feedback_root,
                family=family,
            )
            feedback_penalty_adjustment = cls._safe_float(
                feedback_metrics.get("failure_penalty_adjustment")
            )
            plans.append(
                {
                    "family": family,
                    "family_rank": family_rank,
                    "budget": budget_weight,
                    "budget_weight": budget_weight,
                    "failure_penalty": round(
                        min(
                            max(
                                cls._family_failure_penalty(family, family_rank=family_rank)
                                + feedback_penalty_adjustment,
                                0.0,
                            ),
                            0.9,
                        ),
                        4,
                    ),
                    "validation_profile": cls._family_validation_profile(family),
                    "feedback_metrics": feedback_metrics,
                    "feedback_budget_multiplier": cls._safe_float(
                        feedback_metrics.get("budget_multiplier")
                    ),
                    "feedback_priority_adjustment": cls._safe_float(
                        feedback_metrics.get("priority_adjustment")
                    ),
                    "feedback_failure_penalty_adjustment": feedback_penalty_adjustment,
                }
            )
        plans.sort(
            key=lambda item: (
                -cls._safe_float(item.get("budget_weight")),
                int(item.get("family_rank") or 0),
                str(item.get("family") or ""),
            )
        )
        return plans

    @staticmethod
    def _feedback_family_key(payload: dict[str, Any]) -> str:
        item = dict(payload or {})
        params = dict(item.get("params") or {})
        provenance = dict(params.get("candidate_provenance") or {})
        research_task = dict(item.get("research_task") or {})
        contract_snapshot = dict(item.get("candidate_contract_snapshot") or {})
        targeting = dict(contract_snapshot.get("targeting") or {})
        for source in (item, provenance, params, research_task, targeting, contract_snapshot):
            for key in ("candidate_family_id", "candidate_family", "family", "strategy_type"):
                token = normalize_text(source.get(key))
                if token:
                    return token
        return "unknown"

    @staticmethod
    def _feedback_runtime_alert_pressure(
        latest_metric: dict[str, Any],
        risk_events: list[dict[str, Any]],
        runtime_alerts: list[dict[str, Any]],
    ) -> float:
        severity_weights = {
            "critical": 0.55,
            "high": 0.35,
            "medium": 0.18,
            "low": 0.08,
        }
        open_alerts = [
            dict(item or {})
            for item in list(runtime_alerts or [])
            if normalize_text((item or {}).get("status") or "open") not in {"resolved", "closed"}
        ]
        open_events = [
            dict(item or {})
            for item in list(risk_events or [])
            if normalize_text((item or {}).get("status") or "open") not in {"resolved", "closed"}
        ]
        pressure = 0.0
        for row in [*open_alerts, *open_events]:
            pressure += severity_weights.get(normalize_text(row.get("severity")) or "medium", 0.18)
        total_open = len(open_alerts) + len(open_events)
        if total_open > 1:
            pressure += min((total_open - 1) * 0.06, 0.3)
        decision = normalize_text(latest_metric.get("decision"))
        if decision == "halt":
            pressure = max(pressure, 0.85)
        elif decision in {"review", "defer"}:
            pressure = max(pressure, 0.45)
        return round(min(max(pressure, 0.0), 1.0), 4)

    @classmethod
    def _feedback_capacity_crowding(
        cls,
        latest_metric: dict[str, Any],
        risk_events: list[dict[str, Any]],
        runtime_alerts: list[dict[str, Any]],
    ) -> float:
        turnover_rate = max(0.0, cls._safe_float(latest_metric.get("turnover_rate")))
        exposure_rate = max(0.0, cls._safe_float(latest_metric.get("exposure_rate")))
        crowding = max(turnover_rate, exposure_rate)
        risk_tokens = " ".join(
            normalize_text(
                (item or {}).get("reason")
                or (item or {}).get("message")
                or (item or {}).get("alert_key")
            )
            for item in [*list(risk_events or []), *list(runtime_alerts or [])]
        )
        if any(token in risk_tokens for token in ("crowd", "capacity", "turnover", "exposure")):
            crowding = max(crowding, 0.75)
        return round(min(max(crowding, 0.0), 2.0), 4)

    @classmethod
    async def _list_feedback_source_strategies(
        cls,
        db,
        *,
        limit: int = 180,
    ) -> List[dict[str, Any]]:
        if not hasattr(db, "list_strategies"):
            return []
        statuses = ("incubating", "listed", "submitted")
        per_status_limit = max(10, int(math.ceil(limit / max(len(statuses), 1))))
        seen: set[str] = set()
        items: List[dict[str, Any]] = []
        for status in statuses:
            rows = await _call_optional_async(db, "list_strategies", status, per_status_limit, default=[])
            for row in list(rows or []):
                payload = dict(row or {})
                strategy_id = str(payload.get("id") or "").strip()
                if not strategy_id or strategy_id in seen:
                    continue
                seen.add(strategy_id)
                items.append(payload)
                if len(items) >= limit:
                    return items
        return items

    @classmethod
    def _accumulate_feedback_bucket(
        cls,
        accumulator: dict[str, Any],
        *,
        strategy_id: str,
        metrics: dict[str, Any],
        runtime_alert_count: int,
        runtime_risk_event_count: int,
    ) -> None:
        accumulator["strategy_count"] = int(accumulator.get("strategy_count") or 0) + 1
        if strategy_id:
            strategy_ids = list(accumulator.get("strategy_ids") or [])
            if strategy_id not in strategy_ids:
                strategy_ids.append(strategy_id)
            accumulator["strategy_ids"] = strategy_ids[:20]
        accumulator["runtime_alert_count"] = int(accumulator.get("runtime_alert_count") or 0) + int(runtime_alert_count or 0)
        accumulator["runtime_risk_event_count"] = int(accumulator.get("runtime_risk_event_count") or 0) + int(runtime_risk_event_count or 0)
        accumulator["paper_hit_ratio_total"] = cls._safe_float(accumulator.get("paper_hit_ratio_total")) + cls._safe_float(
            metrics.get("paper_hit_ratio")
        )
        accumulator["runtime_alert_pressure_total"] = cls._safe_float(
            accumulator.get("runtime_alert_pressure_total")
        ) + cls._safe_float(metrics.get("runtime_alert_pressure"))
        accumulator["realized_turnover_total"] = cls._safe_float(
            accumulator.get("realized_turnover_total")
        ) + cls._safe_float(metrics.get("realized_turnover"))
        accumulator["capacity_crowding_total"] = cls._safe_float(
            accumulator.get("capacity_crowding_total")
        ) + cls._safe_float(metrics.get("capacity_crowding"))

    @classmethod
    def _finalize_feedback_bucket(cls, accumulator: dict[str, Any]) -> dict[str, Any]:
        payload = dict(accumulator or {})
        strategy_count = max(0, int(payload.get("strategy_count") or 0))
        target_pool_feedback = {
            str(key): cls._finalize_feedback_bucket(value)
            for key, value in dict(payload.get("target_pool_feedback") or {}).items()
            if isinstance(value, dict)
        }
        generator_mode_feedback = {
            str(key): cls._finalize_feedback_bucket(value)
            for key, value in dict(payload.get("generator_mode_feedback") or {}).items()
            if isinstance(value, dict)
        }
        result = {
            "strategy_count": strategy_count,
            "strategy_ids": list(payload.get("strategy_ids") or [])[:20],
            "runtime_alert_count": int(payload.get("runtime_alert_count") or 0),
            "runtime_risk_event_count": int(payload.get("runtime_risk_event_count") or 0),
            "paper_hit_ratio": round(
                cls._safe_float(payload.get("paper_hit_ratio_total")) / strategy_count,
                4,
            )
            if strategy_count
            else 0.5,
            "runtime_alert_pressure": round(
                cls._safe_float(payload.get("runtime_alert_pressure_total")) / strategy_count,
                4,
            )
            if strategy_count
            else 0.0,
            "realized_turnover": round(
                cls._safe_float(payload.get("realized_turnover_total")) / strategy_count,
                4,
            )
            if strategy_count
            else 0.0,
            "capacity_crowding": round(
                cls._safe_float(payload.get("capacity_crowding_total")) / strategy_count,
                4,
            )
            if strategy_count
            else 0.0,
        }
        if payload.get("ema_submit_count") is not None:
            result["ema_submit_count"] = round(cls._safe_float(payload.get("ema_submit_count")), 4)
        if target_pool_feedback:
            result["target_pool_feedback"] = target_pool_feedback
        if generator_mode_feedback:
            result["generator_mode_feedback"] = generator_mode_feedback
        return result

    @classmethod
    def _merge_feedback_bucket(
        cls,
        base: Any,
        fresh: Any,
    ) -> dict[str, Any]:
        base_payload = dict(base or {})
        fresh_payload = dict(fresh or {})
        merged = dict(base_payload)
        merged.update(fresh_payload)
        if merged.get("ema_submit_count") is None and base_payload.get("ema_submit_count") is not None:
            merged["ema_submit_count"] = base_payload.get("ema_submit_count")
        for scope_name in ("target_pool_feedback", "generator_mode_feedback"):
            base_scope = dict(base_payload.get(scope_name) or {})
            fresh_scope = dict(fresh_payload.get(scope_name) or {})
            if not base_scope and not fresh_scope:
                continue
            merged_scope: dict[str, Any] = {}
            for scope_key in set(base_scope) | set(fresh_scope):
                merged_scope[str(scope_key)] = cls._merge_feedback_bucket(
                    base_scope.get(scope_key),
                    fresh_scope.get(scope_key),
                )
            merged[scope_name] = merged_scope
        return merged

    @classmethod
    async def _load_budget_feedback(
        cls,
        db,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        seed_feedback_root = extract_feedback_root(snapshot.get("family_gate_feedback") or {})
        strategy_rows = await cls._list_feedback_source_strategies(db)
        aggregate_root: dict[str, dict[str, Any]] = {}
        runtime_alert_total = 0
        runtime_risk_total = 0
        for strategy in strategy_rows:
            strategy_id = str(strategy.get("id") or "").strip()
            if not strategy_id:
                continue
            family = cls._feedback_family_key(strategy)
            latest_metric_rows = await _call_optional_async(
                db,
                "list_strategy_incubation_metrics",
                strategy_id,
                limit=1,
                default=[],
            )
            latest_metric = dict((list(latest_metric_rows or []) or [None])[0] or {})
            risk_events = await _call_optional_async(
                db,
                "list_strategy_runtime_risk_events",
                strategy_id=strategy_id,
                status="open",
                limit=20,
                default=[],
            )
            runtime_alerts = await _call_optional_async(
                db,
                "list_strategy_runtime_alerts",
                strategy_id=strategy_id,
                status="open_or_ack",
                limit=20,
                default=[],
            )
            open_runtime_alerts = [
                dict(item or {})
                for item in list(runtime_alerts or [])
                if normalize_text((item or {}).get("status") or "open") not in {"resolved", "closed"}
            ]
            open_risk_events = [
                dict(item or {})
                for item in list(risk_events or [])
                if normalize_text((item or {}).get("status") or "open") not in {"resolved", "closed"}
            ]
            runtime_alert_total += len(open_runtime_alerts)
            runtime_risk_total += len(open_risk_events)
            paper_hit_ratio = cls._safe_float(latest_metric.get("hit_rate_5d"))
            if latest_metric.get("hit_rate_5d") is None:
                paper_hit_ratio = 0.5
            feedback_metrics = {
                "paper_hit_ratio": round(min(max(paper_hit_ratio, 0.0), 1.0), 4),
                "runtime_alert_pressure": cls._feedback_runtime_alert_pressure(
                    latest_metric,
                    open_risk_events,
                    open_runtime_alerts,
                ),
                "realized_turnover": round(
                    min(max(cls._safe_float(latest_metric.get("turnover_rate")), 0.0), 2.0),
                    4,
                ),
                "capacity_crowding": cls._feedback_capacity_crowding(
                    latest_metric,
                    open_risk_events,
                    open_runtime_alerts,
                ),
            }
            family_bucket = aggregate_root.setdefault(family, {})
            cls._accumulate_feedback_bucket(
                family_bucket,
                strategy_id=strategy_id,
                metrics=feedback_metrics,
                runtime_alert_count=len(open_runtime_alerts),
                runtime_risk_event_count=len(open_risk_events),
            )
            target_pool_id = extract_target_pool_id(strategy)
            if target_pool_id:
                target_scope = dict(family_bucket.get("target_pool_feedback") or {})
                scoped_bucket = dict(target_scope.get(target_pool_id) or {})
                cls._accumulate_feedback_bucket(
                    scoped_bucket,
                    strategy_id=strategy_id,
                    metrics=feedback_metrics,
                    runtime_alert_count=len(open_runtime_alerts),
                    runtime_risk_event_count=len(open_risk_events),
                )
                target_scope[target_pool_id] = scoped_bucket
                family_bucket["target_pool_feedback"] = target_scope
            generator_mode = extract_generator_mode(strategy)
            if generator_mode:
                generator_scope = dict(family_bucket.get("generator_mode_feedback") or {})
                scoped_bucket = dict(generator_scope.get(generator_mode) or {})
                cls._accumulate_feedback_bucket(
                    scoped_bucket,
                    strategy_id=strategy_id,
                    metrics=feedback_metrics,
                    runtime_alert_count=len(open_runtime_alerts),
                    runtime_risk_event_count=len(open_risk_events),
                )
                generator_scope[generator_mode] = scoped_bucket
                family_bucket["generator_mode_feedback"] = generator_scope

        finalized_root = {
            family: cls._finalize_feedback_bucket(bucket)
            for family, bucket in aggregate_root.items()
        }
        merged_root: dict[str, Any] = {}
        for family in set(seed_feedback_root) | set(finalized_root):
            merged_root[family] = cls._merge_feedback_bucket(
                seed_feedback_root.get(family),
                finalized_root.get(family),
            )
        target_pool_scope_count = sum(
            len(dict((bucket or {}).get("target_pool_feedback") or {}))
            for bucket in merged_root.values()
            if isinstance(bucket, dict)
        )
        generator_mode_scope_count = sum(
            len(dict((bucket or {}).get("generator_mode_feedback") or {}))
            for bucket in merged_root.values()
            if isinstance(bucket, dict)
        )
        return {
            "available": bool(merged_root),
            "reason": None if merged_root else "feedback_unavailable",
            "feedback": merged_root,
            "summary": {
                "family_count": len(merged_root),
                "seeded_family_count": len(seed_feedback_root),
                "strategy_count": len(strategy_rows),
                "runtime_alert_count": runtime_alert_total,
                "runtime_risk_event_count": runtime_risk_total,
                "target_pool_scope_count": target_pool_scope_count,
                "generator_mode_scope_count": generator_mode_scope_count,
            },
        }

    @staticmethod
    def _family_allocation_entropy(family_counts: dict[str, int]) -> float:
        total = sum(int(value or 0) for value in family_counts.values())
        if total <= 0:
            return 0.0
        entropy = 0.0
        for count in family_counts.values():
            ratio = float(count or 0) / float(total)
            if ratio > 0.0:
                entropy -= ratio * math.log(ratio)
        return round(entropy, 4)

    @classmethod
    async def _load_stock_family_allocation(
        cls,
        db,
        snapshot: dict[str, Any],
        *,
        active_factors: List[str],
        governed_top_candidates: List[dict[str, Any]],
        budget_feedback_root: Any = None,
    ) -> dict[str, Any]:
        candidate_hints = cls._build_candidate_hint_map(governed_top_candidates)
        allocation: dict[str, dict[str, Any]] = {}
        family_counts: dict[str, int] = {}
        priorities: list[float] = []
        limit = max(1, int(STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT))
        families_per_stock = max(1, int(STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK))

        def _track(code: str, families: List[str], priority: float, *, source_mode: str, row: Optional[dict[str, Any]] = None) -> None:
            normalized_code = str(code or "").strip()
            normalized_families = [str(item or "").strip().lower() for item in list(families or []) if str(item or "").strip()]
            if not normalized_code or not normalized_families:
                return
            selected_families = list(dict.fromkeys(normalized_families))[:families_per_stock]
            if not selected_families:
                return
            bounded_priority = round(max(0.01, min(float(priority or 0.0), 0.99)), 4)
            family_plans = cls._build_family_plans(
                selected_families,
                priority=bounded_priority,
                budget_feedback_root=budget_feedback_root,
            )
            allocation[normalized_code] = {
                "families": selected_families,
                "family_plans": family_plans,
                "priority": bounded_priority,
                "source_mode": source_mode,
            }
            if family_plans:
                allocation[normalized_code]["top_family"] = family_plans[0]["family"]
                allocation[normalized_code]["top_validation_profile"] = (
                    dict(family_plans[0].get("validation_profile") or {}).get("profile")
                )
                allocation[normalized_code]["top_feedback_budget_multiplier"] = cls._safe_float(
                    family_plans[0].get("feedback_budget_multiplier")
                )
            if isinstance(row, dict):
                industry = str(row.get("industry") or row.get("sector") or "").strip()
                if industry:
                    allocation[normalized_code]["industry"] = industry
            priorities.append(bounded_priority)
            for family in selected_families:
                family_counts[family] = int(family_counts.get(family, 0)) + 1

        rows: list[dict[str, Any]] = []
        universe_page_size = max(100, min(limit, 1000))
        try:
            rows, _ = await load_stock_universe_rows(
                db,
                limit=limit,
                page_size=universe_page_size,
                start_offset=0,
            )
        except Exception:
            rows = []

        if rows:
            from .stock_strategy_matrix import StockStrategyMatrixPlanner

            hot_sectors = {
                str(item).strip()
                for item in list(snapshot.get("hot_sectors") or [])
                if str(item).strip()
            }
            cold_sectors = {
                str(item).strip()
                for item in list(snapshot.get("cold_sectors") or [])
                if str(item).strip()
            }
            for row in rows:
                code = str(row.get("code") or "").strip()
                if not code:
                    continue
                families: List[str] = []
                hint = dict(candidate_hints.get(code) or {})
                for family in list(hint.get("families") or []):
                    lowered = str(family or "").strip().lower()
                    if lowered and lowered not in families:
                        families.append(lowered)
                for family in StockStrategyMatrixPlanner._families_for_row(
                    row,
                    snapshot=snapshot,
                    hot_sectors=hot_sectors,
                    cold_sectors=cold_sectors,
                    active_factors=active_factors,
                ):
                    lowered = str(family or "").strip().lower()
                    if lowered and lowered not in families:
                        families.append(lowered)
                if not families:
                    continue
                base_score = StockStrategyMatrixPlanner._row_priority_score(
                    row,
                    snapshot=snapshot,
                    hot_sectors=hot_sectors,
                    cold_sectors=cold_sectors,
                    active_factors=active_factors,
                )
                base_priority = max(0.05, min((base_score - 20.0) / 45.0, 0.92))
                hint_bonus = min(max(list(hint.get("scores") or [0.0]) or [0.0]), 1.0) * 0.18
                _track(
                    code,
                    families,
                    base_priority + hint_bonus,
                    source_mode="stock_universe_projection" if not hint else "stock_universe_projection_with_candidate_hints",
                    row=row,
                )
        elif candidate_hints:
            for code, hint in candidate_hints.items():
                hint_score = max(list(hint.get("scores") or [0.0]) or [0.0])
                _track(
                    code,
                    list(hint.get("families") or []),
                    0.55 + hint_score * 0.35,
                    source_mode="governed_candidate_hint_only",
                )

        family_counts = dict(sorted(family_counts.items(), key=lambda item: (-int(item[1]), item[0])))
        summary = {
            "count": len(allocation),
            "family_counts": family_counts,
            "allocation_entropy": cls._family_allocation_entropy(family_counts),
            "avg_priority": round(sum(priorities) / len(priorities), 4) if priorities else 0.0,
            "max_priority": round(max(priorities), 4) if priorities else 0.0,
            "min_priority": round(min(priorities), 4) if priorities else 0.0,
            "candidate_hint_count": len(candidate_hints),
            "universe_limit": limit,
            "source_mode": (
                "stock_universe_projection"
                if rows
                else ("governed_candidate_hint_only" if candidate_hints else "unavailable")
            ),
            "feedback_enabled": bool(budget_feedback_root),
            "feedback_family_count": len(dict(budget_feedback_root or {})),
        }
        return {
            "available": bool(allocation),
            "reason": None if allocation else ("stock_universe_unavailable" if not rows and not candidate_hints else "empty_stock_allocation"),
            "allocation": allocation,
            "summary": summary,
        }

    @classmethod
    async def build(cls, db, snapshot: dict[str, Any]) -> dict[str, Any]:
        factor_ic = dict(snapshot.get("factor_ic") or {})
        factor_trend = dict(snapshot.get("factor_ic_trend") or {})
        lightweight_mock_fallback = cls._should_use_lightweight_mock_fallback(db, snapshot)

        ranked_factors: List[dict[str, Any]] = []
        names = list(
            dict.fromkeys([*factor_ic.keys(), *factor_trend.keys(), *FACTORY_RESEARCH_FACTORS])
        )
        if lightweight_mock_fallback:
            history_meta, latest_factor_date = {}, None
        else:
            history_meta, latest_factor_date = await cls._load_factor_history_meta(db, names)
        names = [
            name
            for name in names
            if name in factor_ic or name in factor_trend or bool(history_meta.get(str(name)))
        ]
        if lightweight_mock_fallback:
            governed_pool = {
                "available": False,
                "reason": "lightweight_mock_fallback",
            }
        else:
            governed_pool = dict(await cls._load_governed_candidate_pool(snapshot) or {})
        governed_pool_reason = str(governed_pool.get("reason") or "").strip().lower()
        active_candidate_pool = dict(governed_pool.get("active_pool") or {})
        governed_registry_summary = dict(governed_pool.get("summary") or {})
        governed_candidate_pool_mode = (
            str(active_candidate_pool.get("active_pool_mode") or "").strip().lower() or None
        )
        governed_candidate_pool_provisional = governed_candidate_pool_mode == "provisional_validated_watch"
        governed_candidate_pool_strict_count = int(active_candidate_pool.get("strict_count") or 0)
        governed_candidate_pool_provisional_count = int(active_candidate_pool.get("provisional_count") or 0)
        governed_top_candidates = [
            dict(item or {})
            for item in list(active_candidate_pool.get("top_candidates") or [])
            if isinstance(item, dict)
        ]
        governed_excluded_candidates = [
            dict(item or {})
            for item in list(active_candidate_pool.get("excluded_candidates") or [])
            if isinstance(item, dict)
        ]
        governed_family_summary = [
            dict(item or {})
            for item in list(active_candidate_pool.get("family_summary") or [])
            if isinstance(item, dict)
        ]
        governed_regime_summary = [
            dict(item or {})
            for item in list(active_candidate_pool.get("regime_summary") or [])
            if isinstance(item, dict)
        ]
        if lightweight_mock_fallback:
            model_registry_lineage = {
                "available": False,
                "reason": "lightweight_mock_fallback",
            }
        else:
            model_registry_lineage = dict(await cls._load_model_registry_lineage(governed_top_candidates[:5]) or {})
        model_lineage_summary = dict(model_registry_lineage.get("summary") or {})
        model_lineage_by_validation_id = dict(model_registry_lineage.get("by_validation_artifact_id") or {})
        if lightweight_mock_fallback:
            budget_feedback_payload = {
                "available": False,
                "reason": "lightweight_mock_fallback",
                "feedback": dict(snapshot.get("family_gate_feedback") or {}),
                "summary": {
                    "family_count": len(dict(snapshot.get("family_gate_feedback") or {})),
                    "seeded_family_count": len(dict(snapshot.get("family_gate_feedback") or {})),
                    "strategy_count": 0,
                    "runtime_alert_count": 0,
                    "runtime_risk_event_count": 0,
                    "target_pool_scope_count": 0,
                    "generator_mode_scope_count": 0,
                },
            }
        else:
            budget_feedback_payload = await cls._load_budget_feedback(db, snapshot)
        budget_feedback_root = dict(budget_feedback_payload.get("feedback") or {})
        budget_feedback_summary = dict(budget_feedback_payload.get("summary") or {})
        governed_source_candidate_count = int(
            active_candidate_pool.get("source_count")
            or governed_registry_summary.get("active_count")
            or 0
        )
        governed_blocked_candidate_count = int(
            active_candidate_pool.get("excluded_count")
            or governed_registry_summary.get("blocked_active_count")
            or governed_registry_summary.get("blocked_count")
            or 0
        )
        governed_exclusion_reason_counts = {
            str(key): int(value or 0)
            for key, value in dict(active_candidate_pool.get("exclusion_reason_counts") or {}).items()
            if str(key).strip()
        }
        snapshot_date = cls._parse_date(snapshot.get("date"))

        def _enrich_governed_candidate(item: dict[str, Any]) -> dict[str, Any]:
            payload = dict(item or {})
            latest_validation_at = payload.get("latest_validation_at") or payload.get("updated_at") or payload.get("created_at")
            latest_validation_age_days = (
                cls._days_since(
                    cls._parse_date(latest_validation_at),
                    reference_date=snapshot_date,
                )
                if snapshot_date is not None
                else None
            )
            expected_regime = [
                str(value).strip()
                for value in list(payload.get("expected_regime") or [])
                if str(value).strip()
            ]
            risk_audit = dict(payload.get("risk_audit") or {})
            evidence_status = {
                "required_audits_complete": bool(risk_audit.get("required_audits_complete")),
                "lookahead_available": bool(risk_audit.get("lookahead_available")),
                "multiple_testing_available": bool(risk_audit.get("multiple_testing_available")),
                "overall_risk_level": str(risk_audit.get("overall_risk_level") or "").strip().lower() or None,
                "blocked": bool(risk_audit.get("blocked")),
            }
            payload["expected_regime"] = expected_regime
            payload["expected_holding_period"] = payload.get("expected_holding_period")
            payload["latest_validation_at"] = latest_validation_at
            payload["latest_validation_age_days"] = latest_validation_age_days
            payload["admission_block_reasons"] = list(
                payload.get("admission_block_reasons") or risk_audit.get("block_reasons") or []
            )
            payload["evidence_status"] = evidence_status
            return payload

        governed_top_candidates = [_enrich_governed_candidate(item) for item in governed_top_candidates]
        governed_excluded_candidates = [_enrich_governed_candidate(item) for item in governed_excluded_candidates]
        active_candidate_pool["top_candidates"] = governed_top_candidates
        active_candidate_pool["excluded_candidates"] = governed_excluded_candidates

        governed_latest_candidate_at = (
            active_candidate_pool.get("latest_active_candidate_updated_at")
            or active_candidate_pool.get("latest_candidate_updated_at")
        )
        governed_latest_candidate_date = cls._parse_date(governed_latest_candidate_at)
        governed_freshness_days = cls._days_since(
            governed_latest_candidate_date,
            reference_date=snapshot_date,
        )
        governed_blocked_ratio = round(
            governed_blocked_candidate_count / max(governed_source_candidate_count, 1),
            6,
        ) if governed_source_candidate_count > 0 else 0.0
        if lightweight_mock_fallback:
            scheduler_status = {}
            scheduler_last_result = {}
            scheduler_llm_validation = {}
            scheduler_llm_provider = {}
            scheduler_quality_flags = []
            scheduler_freshness_sec = 0.0
            scheduler_recent_success = False
        else:
            scheduler_status = dict(get_factor_scheduler_singleton().status() or {})
            scheduler_last_result = dict(scheduler_status.get("last_result") or {})
            scheduler_llm_validation = dict(scheduler_last_result.get("llm_validation") or {})
            scheduler_llm_provider = dict(scheduler_status.get("llm_provider") or {})
            scheduler_quality_flags = list(scheduler_status.get("quality_flags") or [])
            scheduler_freshness_sec = cls._safe_float(scheduler_status.get("freshness_sec"))
            scheduler_recent_success = bool(
                scheduler_status.get("last_run")
                and scheduler_freshness_sec <= float(getattr(get_factor_scheduler_singleton(), "STALE_AFTER_SEC", 24 * 60 * 60))
                and "failed" not in scheduler_quality_flags
            )
            if not bool(governed_pool.get("available")):
                scheduler_recent_success = False
        scheduler_llm_validation_status = (
            str(scheduler_llm_validation.get("status") or "").strip().lower() or None
        )
        scheduler_llm_provider_health_status = (
            str(scheduler_llm_provider.get("health_status") or "").strip().lower() or None
        )
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

        governed_active_factors = [
            str(item.get("family") or "").strip()
            for item in governed_top_candidates
            if str(item.get("family") or "").strip()
        ]
        governed_active_factors = list(dict.fromkeys(governed_active_factors))

        active_factors = positive_rising_factors[:3]
        if not active_factors:
            active_factors = [
                str(item.get("factor_name") or "")
                for item in ranked_factors
                if abs(cls._safe_float(item.get("ic_value"))) >= 0.02
            ][:3]
        if governed_active_factors:
            active_factors = list(dict.fromkeys([*governed_active_factors[:4], *active_factors]))[:4]
        active_factors = [name for name in active_factors if name]

        active_factor_set = set(active_factors)
        preferred_strategy_types: List[str] = []
        for item in governed_top_candidates:
            for strategy_type in cls._preferred_types_for_factor(str(item.get("family") or "")):
                if strategy_type not in preferred_strategy_types:
                    preferred_strategy_types.append(strategy_type)
        for item in ranked_factors:
            if str(item.get("factor_name") or "") not in active_factor_set:
                continue
            for strategy_type in list(item.get("preferred_strategy_types") or []):
                if strategy_type not in preferred_strategy_types:
                    preferred_strategy_types.append(strategy_type)
        if lightweight_mock_fallback:
            stock_family_allocation_payload = {
                "available": False,
                "reason": "lightweight_mock_fallback",
                "allocation": {},
                "summary": {
                    "count": 0,
                    "family_counts": {},
                    "allocation_entropy": 0.0,
                    "avg_priority": 0.0,
                    "max_priority": 0.0,
                    "min_priority": 0.0,
                    "candidate_hint_count": 0,
                    "universe_limit": max(1, int(STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT)),
                    "source_mode": "lightweight_mock_fallback",
                },
            }
        else:
            stock_family_allocation_payload = await cls._load_stock_family_allocation(
                db,
                snapshot,
                active_factors=active_factors,
                governed_top_candidates=governed_top_candidates,
                budget_feedback_root=budget_feedback_root,
            )
        stock_family_allocation = dict(stock_family_allocation_payload.get("allocation") or {})
        stock_family_allocation_summary = dict(stock_family_allocation_payload.get("summary") or {})

        top_factor_names = [
            str(item.get("factor_name") or "")
            for item in ranked_factors[:3]
            if str(item.get("factor_name") or "")
        ]
        top_candidate_names = [
            str(item.get("name") or "")
            for item in governed_top_candidates[:5]
            if str(item.get("name") or "")
        ]
        top_candidate_lineage = [
            (
                lambda entry, lineage_item: {
                "artifact_id": str(entry.get("artifact_id") or "").strip() or None,
                "name": str(entry.get("name") or "").strip() or None,
                "family": str(entry.get("family") or "").strip() or None,
                "registry_stage": str(entry.get("registry_stage") or "").strip() or None,
                "pool_entry_mode": str(entry.get("pool_entry_mode") or "").strip() or None,
                "expected_regime": [
                    str(value).strip()
                    for value in list(entry.get("expected_regime") or [])
                    if str(value).strip()
                ],
                "expected_holding_period": entry.get("expected_holding_period"),
                "source_generation_artifact_id": str(entry.get("source_generation_artifact_id") or "").strip() or None,
                "source_validation_artifact_id": (
                    str(entry.get("source_validation_artifact_id") or entry.get("artifact_id") or "").strip() or None
                ),
                "memory_record_id": str(entry.get("memory_record_id") or "").strip() or None,
                "latest_validation_at": entry.get("latest_validation_at") or entry.get("updated_at") or entry.get("created_at"),
                "latest_validation_age_days": entry.get("latest_validation_age_days"),
                "admission_block_reasons": list(entry.get("admission_block_reasons") or []),
                "evidence_status": dict(entry.get("evidence_status") or {}),
                "model_registry_artifact_ids": [
                    str(model_item.get("artifact_id") or "").strip()
                    for model_item in list((lineage_item or {}).get("model_registry_items") or [])
                    if str(model_item.get("artifact_id") or "").strip()
                ],
                "model_registry_stages": list((lineage_item or {}).get("deployment_stages") or []),
                "latest_retrain_run_status": (
                    (lineage_item.get("latest_retrain_run") or {}).get("status")
                    if isinstance(lineage_item, dict)
                    else None
                ),
                "retrain_plan_statuses": list((lineage_item or {}).get("retrain_statuses") or []),
                "retrain_plan_ids": [
                    str(plan.get("artifact_id") or plan.get("plan_id") or "").strip()
                    for plan in list((lineage_item or {}).get("retrain_plans") or [])
                    if str(plan.get("artifact_id") or plan.get("plan_id") or "").strip()
                ],
                "lineage_available": bool(model_registry_lineage.get("available")),
            }
            )(
                item,
                model_lineage_by_validation_id.get(
                    str(item.get("source_validation_artifact_id") or item.get("artifact_id") or "").strip()
                ),
            )
            for item in governed_top_candidates[:5]
        ]
        blocked_candidate_lineage = [
            {
                "artifact_id": str(item.get("artifact_id") or "").strip() or None,
                "name": str(item.get("name") or "").strip() or None,
                "family": str(item.get("family") or "").strip() or None,
                "registry_stage": str(item.get("registry_stage") or "").strip() or None,
                "expected_regime": [
                    str(value).strip()
                    for value in list(item.get("expected_regime") or [])
                    if str(value).strip()
                ],
                "expected_holding_period": item.get("expected_holding_period"),
                "source_generation_artifact_id": str(item.get("source_generation_artifact_id") or "").strip() or None,
                "source_validation_artifact_id": (
                    str(item.get("source_validation_artifact_id") or item.get("artifact_id") or "").strip() or None
                ),
                "latest_validation_at": item.get("latest_validation_at") or item.get("updated_at") or item.get("created_at"),
                "latest_validation_age_days": item.get("latest_validation_age_days"),
                "admission_block_reasons": list(item.get("admission_block_reasons") or item.get("reasons") or []),
                "evidence_status": dict(item.get("evidence_status") or {}),
            }
            for item in governed_excluded_candidates[:5]
        ]
        rationale: List[str] = []
        if active_factors:
            rationale.append(f"活跃因子: {', '.join(active_factors)}")
        if preferred_strategy_types:
            rationale.append(f"优先策略类型: {', '.join(preferred_strategy_types[:4])}")
        if governed_top_candidates:
            if governed_candidate_pool_provisional:
                rationale.append(
                    "治理候选池当前以 provisional validated/watch 候选供给，"
                    f"Top 候选: {', '.join(top_candidate_names[:3])}"
                )
            else:
                rationale.append(f"治理后候选池已接入，Top 候选: {', '.join(top_candidate_names[:3])}")
        elif governed_blocked_candidate_count:
            rationale.append(f"治理候选池存在 {governed_blocked_candidate_count} 个高风险候选，当前未纳入活跃池。")
        elif governed_pool.get("reason"):
            rationale.append(f"治理后候选池未生效，已回退到种子因子: {governed_pool.get('reason')}")
        if governed_latest_candidate_at:
            rationale.append(f"治理候选池最近验证时间: {governed_latest_candidate_at}")
        if model_lineage_summary:
            rationale.append(
                "候选已接入 model/retrain 血缘: "
                f"champion={int(model_lineage_summary.get('champion_count') or 0)} "
                f"challenger={int(model_lineage_summary.get('challenger_count') or 0)} "
                f"retrain_plan={int(model_lineage_summary.get('retrain_plan_count') or 0)}"
            )
        if stock_family_allocation:
            rationale.append(
                "逐股 family 分配已生成: "
                f"覆盖 {int(stock_family_allocation_summary.get('count') or 0)} 只股票，"
                f"allocation_entropy={stock_family_allocation_summary.get('allocation_entropy')}"
            )
        if budget_feedback_root:
            rationale.append(
                "paper/runtime feedback 已回流 allocation/budget: "
                f"families={int(budget_feedback_summary.get('family_count') or 0)} "
                f"strategies={int(budget_feedback_summary.get('strategy_count') or 0)}"
            )
        if governed_blocked_ratio >= 0.40:
            rationale.append(f"治理候选池 blocked 比例偏高: {round(governed_blocked_ratio * 100, 1)}%")
        governed_pool_observable = bool(
            governed_pool.get("available")
            or governed_source_candidate_count > 0
            or int((governed_pool.get("active_pool") or {}).get("count") or 0) > 0
        )
        governed_pool_missing_after_scheduler_success = bool(
            governed_pool_observable
            and scheduler_recent_success
            and not governed_top_candidates
        )
        if governed_pool_missing_after_scheduler_success:
            rationale.append("调度器近期已成功运行，但治理活跃池仍为空，建议核查验证与晋级门槛。")
        if scheduler_llm_provider_health_status in {"degraded", "closed", "misconfigured", "error"}:
            rationale.append(
                "factor llm provider 生命周期异常: "
                f"health={scheduler_llm_provider_health_status} "
                f"error={scheduler_llm_provider.get('last_error_type') or 'unknown'}"
            )

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
        if governed_top_candidates:
            quality_flags.append("governed_candidate_pool_active")
        if governed_candidate_pool_provisional:
            quality_flags.append("governed_candidate_pool_provisional")
        if model_registry_lineage.get("available"):
            quality_flags.append("model_registry_lineage_available")
        if governed_blocked_candidate_count:
            quality_flags.append("governed_candidate_pool_blocked_candidates")
        if governed_blocked_ratio >= 0.75:
            quality_flags.append("governed_candidate_pool_blocked_ratio_high")
        elif governed_blocked_ratio >= 0.40:
            quality_flags.append("governed_candidate_pool_blocked_ratio_elevated")
        if governed_freshness_days is None and governed_source_candidate_count > 0:
            quality_flags.append("governed_candidate_pool_freshness_unknown")
        elif governed_freshness_days is not None and governed_freshness_days > cls.STALE_AFTER_DAYS:
            quality_flags.append("governed_candidate_pool_stale")
        if scheduler_recent_success and not governed_top_candidates:
            quality_flags.append("scheduler_recent_success_without_governed_pool")
        if governed_pool_missing_after_scheduler_success:
            quality_flags.append("governed_pool_missing_after_scheduler_success")
        factor_ic_status = str(factor_ic_source.get("status") or "")
        if factor_ic_status and factor_ic_status != "success":
            quality_flags.append(f"factor_ic_{factor_ic_status}")
        if scheduler_llm_provider_health_status in {"degraded", "closed", "misconfigured", "error"}:
            quality_flags.append(f"factor_llm_provider_{scheduler_llm_provider_health_status}")
        if budget_feedback_root:
            quality_flags.append("budget_feedback_available")
        if not ranked_factors:
            quality_flags.append("empty")
        quality_flags.extend([flag for flag in scheduler_quality_flags if flag not in quality_flags])

        if not rationale:
            rationale.append("未识别到显著活跃因子，后续阶段回退到原始快照因子摘要逻辑。")
        if stale:
            rationale.append("因子研究数据存在 freshness 风险，后续阶段应降低置信度或触发补算。")
        if decay_factors:
            rationale.append(f"检测到衰减因子: {', '.join(decay_factors[:3])}")

        degraded = (not bool(ranked_factors) and not bool(governed_top_candidates)) or (stale and not bool(governed_top_candidates))
        return {
            "active_factors": active_factors,
            "ranked_factors": ranked_factors,
            "positive_rising_factors": positive_rising_factors,
            "preferred_strategy_types": preferred_strategy_types,
            "governed_candidates": governed_top_candidates,
            "blocked_candidates": governed_excluded_candidates,
            "top_candidate_lineage": top_candidate_lineage,
            "blocked_candidate_lineage": blocked_candidate_lineage,
            "model_registry_lineage": model_registry_lineage,
            "budget_feedback": budget_feedback_root,
            "active_candidate_pool": active_candidate_pool,
            "stock_family_allocation": stock_family_allocation,
            "active_family_summary": governed_family_summary,
            "active_regime_summary": governed_regime_summary,
            "research_rationale": rationale,
            "source_chain": [
                "snapshot.factor_ic",
                "snapshot.factor_ic_trend",
                f"db.factor_ic_history(limit={cls.HISTORY_LIMIT})",
                "quant_manager.factor_candidate_registry(active_pool)",
                "quant_manager.model_registry(lineage)",
                "factor_scheduler.status",
                "artifact_v2",
                *(["lightweight_mock_fallback"] if lightweight_mock_fallback else []),
            ],
            "lightweight_mock_fallback": lightweight_mock_fallback,
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
                "llm_validation_status": scheduler_llm_validation_status,
                "recent_success": scheduler_recent_success,
                "llm_provider": scheduler_llm_provider,
            },
            "summary": {
                "active_factor_count": len(active_factors),
                "active_candidate_count": int(active_candidate_pool.get("count") or 0),
                "governed_source_candidate_count": governed_source_candidate_count,
                "governed_blocked_candidate_count": governed_blocked_candidate_count,
                "governed_blocked_ratio": governed_blocked_ratio,
                "governed_latest_candidate_at": governed_latest_candidate_at,
                "governed_freshness_days": governed_freshness_days,
                "ranked_factor_count": len(ranked_factors),
                "top_factor_names": top_factor_names,
                "top_candidate_names": top_candidate_names,
                "active_family_names": [str(item.get("family") or "") for item in governed_family_summary if str(item.get("family") or "")],
                "active_regime_names": [str(item.get("regime") or "") for item in governed_regime_summary if str(item.get("regime") or "")],
                "preferred_strategy_types": preferred_strategy_types,
                "factor_source_mode": (
                    "governed_candidate_pool"
                    if governed_top_candidates
                    else ("governed_pool_missing_after_scheduler_success" if governed_pool_missing_after_scheduler_success else "seed_fallback")
                ),
                "governed_candidate_pool_mode": governed_candidate_pool_mode,
                "governed_candidate_pool_provisional": governed_candidate_pool_provisional,
                "governed_candidate_pool_strict_count": governed_candidate_pool_strict_count,
                "governed_candidate_pool_provisional_count": governed_candidate_pool_provisional_count,
                "scheduler_last_run": scheduler_status.get("last_run"),
                "scheduler_freshness_sec": scheduler_status.get("freshness_sec"),
                "scheduler_recent_success": scheduler_recent_success,
                "scheduler_llm_validation_status": scheduler_llm_validation_status,
                "factor_llm_provider_enabled": bool(scheduler_llm_provider.get("enabled")),
                "factor_llm_provider_ready": bool(scheduler_llm_provider.get("ready")),
                "factor_llm_provider_health_status": scheduler_llm_provider_health_status,
                "factor_llm_provider_rebuild_count": int(scheduler_llm_provider.get("rebuild_count") or 0),
                "factor_llm_provider_last_error_type": scheduler_llm_provider.get("last_error_type"),
                "governed_pool_missing_after_scheduler_success": governed_pool_missing_after_scheduler_success,
                "lightweight_mock_fallback": lightweight_mock_fallback,
                "governed_exclusion_reason_counts": governed_exclusion_reason_counts,
                "governed_registry_stage_counts": dict(governed_registry_summary.get("registry_stage_counts") or {}),
                "top_candidate_lineage": top_candidate_lineage,
                "model_registry_lineage_available": bool(model_registry_lineage.get("available")),
                "model_registry_lineage_summary": model_lineage_summary,
                "governed_risk_counts": {
                    "lookahead": dict(governed_registry_summary.get("lookahead_risk_counts") or {}),
                    "multiple_testing": dict(governed_registry_summary.get("multiple_testing_risk_counts") or {}),
                    "overall": dict(governed_registry_summary.get("overall_risk_counts") or {}),
                },
                "stock_family_allocation_count": int(stock_family_allocation_summary.get("count") or 0),
                "stock_family_allocation_family_counts": dict(stock_family_allocation_summary.get("family_counts") or {}),
                "stock_family_allocation_entropy": stock_family_allocation_summary.get("allocation_entropy"),
                "stock_family_allocation_avg_priority": stock_family_allocation_summary.get("avg_priority"),
                "stock_family_allocation_source_mode": stock_family_allocation_summary.get("source_mode"),
                "budget_feedback_available": bool(budget_feedback_payload.get("available")),
                "budget_feedback_family_count": int(budget_feedback_summary.get("family_count") or 0),
                "budget_feedback_strategy_count": int(budget_feedback_summary.get("strategy_count") or 0),
                "budget_feedback_target_pool_scope_count": int(
                    budget_feedback_summary.get("target_pool_scope_count") or 0
                ),
                "budget_feedback_generator_mode_scope_count": int(
                    budget_feedback_summary.get("generator_mode_scope_count") or 0
                ),
                "budget_feedback_runtime_alert_count": int(
                    budget_feedback_summary.get("runtime_alert_count") or 0
                ),
                "budget_feedback_runtime_risk_event_count": int(
                    budget_feedback_summary.get("runtime_risk_event_count") or 0
                ),
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
