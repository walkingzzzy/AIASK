"""策略工厂轻量因子研究 artifact 构建。"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, List, Optional, Tuple

from ...domain.constants import (
    FACTORY_RESEARCH_FACTORS,
    STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK,
    STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
)
from ...infrastructure.mcp_services import (
    get_factor_scheduler_singleton,
    get_quant_manager_callable,
    get_strategy_lifecycle_shared_runtime,
)
from .._budget_feedback import (
    extract_feedback_root,
    extract_generator_mode,
    extract_holding_bucket,
    extract_target_pool_id,
    normalize_feedback_input_contract,
    normalize_text,
    resolve_feedback_metrics,
)
from .._stock_universe_loader import load_stock_universe_rows
from ..runtime import _call_optional_async
from ._artifact_summary import build_factor_research_summary
from ._builder_support import FactorResearchBuilderSupportMixin
from ._feedback_routes import (
    build_search_route_feedback_snapshot,
    load_budget_feedback,
    load_stock_family_allocation,
    rewrite_family_preference_order_by_feedback,
)


class FactorResearchBuilder(FactorResearchBuilderSupportMixin):
    """基于 collect 阶段已有因子摘要构建统一 artifact。"""

    HISTORY_LIMIT = 20
    STALE_AFTER_DAYS = 2
    EVIDENCE_FORWARD_WINDOWS = (1, 5, 10, 20)

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

    @classmethod
    def _feedback_ab_quality_score(cls, feedback_metrics: dict[str, Any]) -> float:
        raw_validation_a_rate = cls._safe_float(feedback_metrics.get("raw_validation_a_rate"))
        raw_validation_b_rate = cls._safe_float(feedback_metrics.get("raw_validation_b_rate"))
        raw_validation_d_rate = cls._safe_float(feedback_metrics.get("raw_validation_d_rate"))
        raw_validation_total_score_mean = max(
            0.0,
            min(cls._safe_float(feedback_metrics.get("raw_validation_total_score_mean")), 100.0),
        )
        strict_incubation_ready_rate = cls._safe_float(
            feedback_metrics.get("strict_incubation_ready_rate")
        )
        score = (
            raw_validation_a_rate * 1.3
            + raw_validation_b_rate * 0.95
            + strict_incubation_ready_rate * 0.7
            + max(raw_validation_total_score_mean - 50.0, 0.0) / 50.0 * 0.45
            - raw_validation_d_rate * 0.85
        )
        return round(score, 4)

    @classmethod
    def _resolve_search_route_action(
        cls,
        plan: dict[str, Any],
        feedback_metrics: dict[str, Any],
    ) -> str:
        control_mode = normalize_text(plan.get("feedback_control_mode")) or "normal"
        zero_signal_ratio = cls._safe_float(feedback_metrics.get("zero_signal_ratio"))
        evidence_debt_ratio = cls._safe_float(feedback_metrics.get("evidence_debt_ratio"))
        promotion_ready_ratio = cls._safe_float(
            feedback_metrics.get("promotion_ready_ratio"),
            1.0,
        )
        raw_validation_a_rate = cls._safe_float(feedback_metrics.get("raw_validation_a_rate"))
        raw_validation_b_rate = cls._safe_float(feedback_metrics.get("raw_validation_b_rate"))
        raw_validation_d_rate = cls._safe_float(feedback_metrics.get("raw_validation_d_rate"))
        raw_validation_total_score_mean = cls._safe_float(
            feedback_metrics.get("raw_validation_total_score_mean")
        )
        strict_incubation_ready_rate = cls._safe_float(
            feedback_metrics.get("strict_incubation_ready_rate")
        )
        budget_multiplier = cls._safe_float(plan.get("feedback_budget_multiplier"), 1.0)
        priority_adjustment = cls._safe_float(plan.get("feedback_priority_adjustment"))
        quality_score = cls._feedback_ab_quality_score(feedback_metrics)
        if bool(plan.get("feedback_family_freeze_active")) or control_mode == "freeze":
            return "family_freeze"
        if control_mode == "suppress":
            if zero_signal_ratio >= 0.65 or evidence_debt_ratio >= 0.65:
                return "family_retire"
            return "family_cooldown"
        if control_mode == "cooldown":
            return "family_cooldown"
        if (
            raw_validation_d_rate >= 0.75
            and raw_validation_a_rate <= 0.0
            and raw_validation_b_rate <= 0.12
            and raw_validation_total_score_mean <= 42.0
        ):
            return "family_cooldown"
        if (
            budget_multiplier > 1.0
            or priority_adjustment > 0.0
            or promotion_ready_ratio >= 0.35
            or strict_incubation_ready_rate >= 0.2
            or raw_validation_a_rate >= 0.1
            or raw_validation_b_rate >= 0.3
            or raw_validation_total_score_mean >= 58.0
            or quality_score >= 0.35
        ):
            return "family_explore"
        if zero_signal_ratio >= 0.3 or evidence_debt_ratio >= 0.35:
            return "family_cooldown"
        return "family_explore"

    @classmethod
    def _scope_route_action(
        cls,
        *,
        scope_name: str,
        scope_metrics: dict[str, Any],
        preferred_shift_target: str | None = None,
    ) -> tuple[str | None, dict[str, Any]]:
        if not scope_metrics:
            return None, {}
        control_mode = normalize_text(scope_metrics.get("control_mode")) or "normal"
        budget_multiplier = cls._safe_float(scope_metrics.get("budget_multiplier"), 1.0)
        priority_adjustment = cls._safe_float(scope_metrics.get("priority_adjustment"))
        promotion_ready_ratio = cls._safe_float(scope_metrics.get("promotion_ready_ratio"), 1.0)
        forward_window_coverage_ratio = cls._safe_float(
            scope_metrics.get("forward_window_coverage_ratio"),
            1.0,
        )
        zero_signal_ratio = cls._safe_float(scope_metrics.get("zero_signal_ratio"))
        evidence_debt_ratio = cls._safe_float(scope_metrics.get("evidence_debt_ratio"))
        payload = {
            "control_mode": control_mode,
            "budget_multiplier": round(budget_multiplier, 4),
            "priority_adjustment": round(priority_adjustment, 4),
            "reasons": list(scope_metrics.get("control_reasons") or []),
        }
        if scope_name == "target_pool":
            if control_mode in {"freeze", "suppress"} or evidence_debt_ratio >= 0.55:
                return "universe_shrink", payload
            if (
                budget_multiplier > 1.0
                or priority_adjustment > 0.0
                or promotion_ready_ratio >= 0.35
                or forward_window_coverage_ratio >= 0.55
            ):
                return "universe_expand", payload
            if control_mode == "cooldown":
                return "universe_shrink", payload
            return None, payload
        if scope_name == "holding_bucket":
            if control_mode in {"freeze", "suppress"} or zero_signal_ratio >= 0.55:
                return "holding_demote", payload
            if (
                budget_multiplier > 1.0
                or priority_adjustment > 0.0
                or promotion_ready_ratio >= 0.35
                or forward_window_coverage_ratio >= 0.55
            ):
                return "holding_promote", payload
            if control_mode == "cooldown":
                return "holding_demote", payload
            return None, payload
        if scope_name == "generator_mode":
            if (
                control_mode in {"freeze", "suppress", "cooldown"}
                or preferred_shift_target
            ):
                if preferred_shift_target:
                    payload["recommended_generator_mode"] = preferred_shift_target
                return "generator_mode_shift", payload
            if budget_multiplier > 1.0 or priority_adjustment > 0.0:
                payload["recommended_generator_mode"] = preferred_shift_target
                return "generator_mode_shift", payload
        return None, payload

    @classmethod
    def _preferred_generator_shift_target(
        cls,
        family_bucket: dict[str, Any],
        *,
        current_mode: str | None,
    ) -> str | None:
        generator_scope = dict(family_bucket.get("generator_mode_feedback") or {})
        ranked_modes: list[tuple[tuple[int, float, float, str], str]] = []
        for mode_name, mode_bucket in generator_scope.items():
            mode = normalize_text(mode_name)
            if not mode:
                continue
            metrics = resolve_feedback_metrics(
                {"family_gate_feedback": {"candidate_family": family_bucket}},
                family="candidate_family",
                generator_mode=mode,
            )
            control_mode = normalize_text(metrics.get("generator_mode_control_mode")) or "normal"
            ranked_modes.append(
                (
                    (
                        -{
                            "normal": 0,
                            "cooldown": 1,
                            "suppress": 2,
                            "freeze": 3,
                        }.get(control_mode, 0),
                        cls._safe_float(metrics.get("budget_multiplier"), 1.0),
                        cls._safe_float(metrics.get("priority_adjustment")),
                        mode,
                    ),
                    mode,
                )
            )
        if not ranked_modes:
            fallback = "rule" if normalize_text(current_mode) != "rule" else "external_llm"
            return fallback or None
        ranked_modes.sort(reverse=True)
        for _score, mode in ranked_modes:
            if mode != normalize_text(current_mode):
                return mode
        return ranked_modes[0][1]

    @classmethod
    def _rewrite_family_preference_order_by_feedback(
        cls,
        family_preference_order: List[str],
        *,
        family_plans: List[dict[str, Any]],
    ) -> List[str]:
        return rewrite_family_preference_order_by_feedback(
            cls,
            family_preference_order,
            family_plans=family_plans,
        )

    @classmethod
    def _build_search_route_feedback_snapshot(
        cls,
        *,
        family_preference_order: List[str],
        budget_feedback_root: Any = None,
    ) -> tuple[
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
        List[dict[str, Any]],
        List[dict[str, Any]],
    ]:
        return build_search_route_feedback_snapshot(
            cls,
            family_preference_order=family_preference_order,
            budget_feedback_root=budget_feedback_root,
        )

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

    @staticmethod
    def _resolve_promotion_review_outcome(
        status_counts: dict[str, Any] | None,
        recommendation_counts: dict[str, Any] | None,
    ) -> tuple[str | None, str | None]:
        normalized_status_counts = {
            normalize_text(key): int(value or 0)
            for key, value in dict(status_counts or {}).items()
            if normalize_text(key)
        }
        normalized_recommendation_counts = {
            normalize_text(key): int(value or 0)
            for key, value in dict(recommendation_counts or {}).items()
            if normalize_text(key)
        }
        status = next(
            (
                item
                for item in ("rejected", "watch", "approved")
                if int(normalized_status_counts.get(item) or 0) > 0
            ),
            None,
        )
        if status is None:
            status = next(
                (
                    key
                    for key, value in normalized_status_counts.items()
                    if int(value or 0) > 0
                ),
                None,
            )
        recommendation = next(
            (
                item
                for item in ("deprecate", "observe", "promote")
                if int(normalized_recommendation_counts.get(item) or 0) > 0
            ),
            None,
        )
        if recommendation is None:
            recommendation = next(
                (
                    key
                    for key, value in normalized_recommendation_counts.items()
                    if int(value or 0) > 0
                ),
                None,
        )
        return status, recommendation

    @classmethod
    def _fallback_feedback_evidence_overview(
        cls,
        signal_stats: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(signal_stats or {})
        observed_forward_days: list[int] = []
        for days in cls.EVIDENCE_FORWARD_WINDOWS:
            day_key = str(days)
            has_signal = any(
                dict(payload.get(metric_name) or {}).get(day_key) is not None
                or dict(payload.get(metric_name) or {}).get(days) is not None
                for metric_name in ("hit_rate", "forward_ic", "forward_sharpe")
            )
            if has_signal:
                observed_forward_days.append(days)
        total_signals = cls._safe_int(payload.get("total_signals"))
        minimum_signal_count = 10
        missing_forward_days = [
            days for days in cls.EVIDENCE_FORWARD_WINDOWS if days not in observed_forward_days
        ]
        promotion_ready = total_signals >= minimum_signal_count and not missing_forward_days
        return {
            "total_signals": total_signals,
            "minimum_signal_count": minimum_signal_count,
            "observed_forward_days": observed_forward_days,
            "missing_forward_days": missing_forward_days,
            "promotion_ready": promotion_ready,
            "blockers": [],
            "risk_flags": [],
        }

    @classmethod
    async def _load_feedback_evidence_overview(
        cls,
        db,
        strategy: dict[str, Any],
    ) -> dict[str, Any]:
        strategy_id = str((strategy or {}).get("id") or "").strip()
        if not strategy_id:
            return cls._fallback_feedback_evidence_overview({})

        lifecycle_runtime = get_strategy_lifecycle_shared_runtime()
        build_overview = getattr(lifecycle_runtime, "build_incubation_overview", None)
        if callable(build_overview):
            try:
                overview = await build_overview(db, strategy)
                if isinstance(overview, dict) and overview:
                    return overview
            except Exception:
                pass

        signal_stats = await _call_optional_async(
            db,
            "get_signal_stats",
            strategy_id,
            default={},
        )
        return cls._fallback_feedback_evidence_overview(signal_stats)

    @classmethod
    def _accumulate_feedback_bucket(
        cls,
        accumulator: dict[str, Any],
        *,
        strategy_id: str,
        metrics: dict[str, Any],
        runtime_alert_count: int,
        runtime_risk_event_count: int,
        evidence_overview: dict[str, Any] | None = None,
        promotion_review: dict[str, Any] | None = None,
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
        overview = dict(evidence_overview or {})
        total_signals = max(0, cls._safe_int(overview.get("total_signals")))
        minimum_signal_count = max(1, cls._safe_int(overview.get("minimum_signal_count") or 10))
        observed_forward_days = [
            int(day)
            for day in list(overview.get("observed_forward_days") or [])
            if int(day) in cls.EVIDENCE_FORWARD_WINDOWS
        ]
        missing_forward_days = [
            int(day)
            for day in list(overview.get("missing_forward_days") or [])
            if int(day) in cls.EVIDENCE_FORWARD_WINDOWS
        ]
        promotion_ready = bool(overview.get("promotion_ready"))
        accumulator["signal_count_total"] = int(
            accumulator.get("signal_count_total") or 0
        ) + total_signals
        accumulator["expected_forward_window_count"] = int(
            accumulator.get("expected_forward_window_count") or 0
        ) + len(cls.EVIDENCE_FORWARD_WINDOWS)
        accumulator["observed_forward_window_count"] = int(
            accumulator.get("observed_forward_window_count") or 0
        ) + len(observed_forward_days)
        accumulator["missing_forward_window_count"] = int(
            accumulator.get("missing_forward_window_count") or 0
        ) + len(missing_forward_days)
        if total_signals <= 0:
            accumulator["zero_signal_strategy_count"] = int(
                accumulator.get("zero_signal_strategy_count") or 0
            ) + 1
        if total_signals < minimum_signal_count:
            accumulator["low_signal_strategy_count"] = int(
                accumulator.get("low_signal_strategy_count") or 0
            ) + 1
        if promotion_ready:
            accumulator["promotion_ready_count"] = int(
                accumulator.get("promotion_ready_count") or 0
            ) + 1
        if total_signals < minimum_signal_count or missing_forward_days or not promotion_ready:
            accumulator["evidence_debt_strategy_count"] = int(
                accumulator.get("evidence_debt_strategy_count") or 0
            ) + 1
        raw_validation_grade = str(
            overview.get("raw_validation_grade")
            or overview.get("validation_grade")
            or ""
        ).strip().upper()
        if raw_validation_grade:
            raw_validation_grade_distribution = dict(
                accumulator.get("raw_validation_grade_distribution") or {}
            )
            raw_validation_grade_distribution[raw_validation_grade] = int(
                raw_validation_grade_distribution.get(raw_validation_grade) or 0
            ) + 1
            accumulator["raw_validation_grade_distribution"] = raw_validation_grade_distribution
        raw_validation_total_score = overview.get("raw_validation_total_score")
        if raw_validation_total_score is None:
            raw_validation_total_score = overview.get("validation_total_score")
        if raw_validation_total_score is not None:
            accumulator["raw_validation_total_score_total"] = cls._safe_float(
                accumulator.get("raw_validation_total_score_total")
            ) + cls._safe_float(raw_validation_total_score)
            accumulator["raw_validation_total_score_count"] = int(
                accumulator.get("raw_validation_total_score_count") or 0
            ) + 1
        if bool(overview.get("strict_incubation_ready")):
            accumulator["strict_incubation_ready_count"] = int(
                accumulator.get("strict_incubation_ready_count") or 0
            ) + 1
        if bool(overview.get("live_candidate_ready")):
            accumulator["live_candidate_ready_count"] = int(
                accumulator.get("live_candidate_ready_count") or 0
            ) + 1
        review = dict(promotion_review or {})
        if review:
            accumulator["promotion_review_count"] = int(
                accumulator.get("promotion_review_count") or 0
            ) + 1
            review_status = normalize_text(review.get("status"))
            if review_status:
                status_counts = dict(accumulator.get("promotion_review_status_counts") or {})
                status_counts[review_status] = int(status_counts.get(review_status) or 0) + 1
                accumulator["promotion_review_status_counts"] = status_counts
            review_recommendation = normalize_text(review.get("recommendation"))
            if review_recommendation:
                recommendation_counts = dict(
                    accumulator.get("promotion_review_recommendation_counts") or {}
                )
                recommendation_counts[review_recommendation] = int(
                    recommendation_counts.get(review_recommendation) or 0
                ) + 1
                accumulator["promotion_review_recommendation_counts"] = recommendation_counts
            if review.get("score") is not None:
                accumulator["promotion_review_score_total"] = cls._safe_float(
                    accumulator.get("promotion_review_score_total")
                ) + min(max(cls._safe_float(review.get("score")), 0.0), 1.0)

    @classmethod
    def _finalize_feedback_bucket(cls, accumulator: dict[str, Any]) -> dict[str, Any]:
        payload = dict(accumulator or {})
        strategy_count = max(0, int(payload.get("strategy_count") or 0))
        promotion_review_count = max(0, int(payload.get("promotion_review_count") or 0))
        raw_validation_grade_distribution = {
            str(key or "").strip().upper(): int(value or 0)
            for key, value in dict(payload.get("raw_validation_grade_distribution") or {}).items()
            if str(key or "").strip()
        }
        raw_validation_total_score_total = cls._safe_float(
            payload.get("raw_validation_total_score_total")
        )
        raw_validation_total_score_count = max(
            0,
            int(payload.get("raw_validation_total_score_count") or 0),
        )
        strict_incubation_ready_count = max(
            0,
            int(payload.get("strict_incubation_ready_count") or 0),
        )
        live_candidate_ready_count = max(
            0,
            int(payload.get("live_candidate_ready_count") or 0),
        )
        signal_count_total = max(0, int(payload.get("signal_count_total") or 0))
        expected_forward_window_count = max(
            0,
            int(payload.get("expected_forward_window_count") or 0),
        )
        observed_forward_window_count = max(
            0,
            int(payload.get("observed_forward_window_count") or 0),
        )
        missing_forward_window_count = max(
            0,
            int(payload.get("missing_forward_window_count") or 0),
        )
        zero_signal_strategy_count = max(
            0,
            int(payload.get("zero_signal_strategy_count") or 0),
        )
        low_signal_strategy_count = max(
            0,
            int(payload.get("low_signal_strategy_count") or 0),
        )
        promotion_ready_count = max(
            0,
            int(payload.get("promotion_ready_count") or 0),
        )
        evidence_debt_strategy_count = max(
            0,
            int(payload.get("evidence_debt_strategy_count") or 0),
        )
        promotion_review_status_counts = {
            normalize_text(key): int(value or 0)
            for key, value in dict(payload.get("promotion_review_status_counts") or {}).items()
            if normalize_text(key)
        }
        promotion_review_recommendation_counts = {
            normalize_text(key): int(value or 0)
            for key, value in dict(payload.get("promotion_review_recommendation_counts") or {}).items()
            if normalize_text(key)
        }
        promotion_review_status, promotion_review_recommendation = cls._resolve_promotion_review_outcome(
            promotion_review_status_counts,
            promotion_review_recommendation_counts,
        )
        target_pool_feedback = {
            str(key): cls._finalize_feedback_bucket(value)
            for key, value in dict(payload.get("target_pool_feedback") or {}).items()
            if isinstance(value, dict)
        }
        holding_bucket_feedback = {
            normalize_text(key): cls._finalize_feedback_bucket(value)
            for key, value in dict(payload.get("holding_bucket_feedback") or {}).items()
            if normalize_text(key) and isinstance(value, dict)
        }
        generator_mode_feedback = {
            str(key): cls._finalize_feedback_bucket(value)
            for key, value in dict(payload.get("generator_mode_feedback") or {}).items()
            if isinstance(value, dict)
        }
        zero_signal_ratio = round(zero_signal_strategy_count / strategy_count, 4) if strategy_count else 0.0
        low_signal_ratio = round(low_signal_strategy_count / strategy_count, 4) if strategy_count else 0.0
        promotion_ready_ratio = round(promotion_ready_count / strategy_count, 4) if strategy_count else 1.0
        promotion_review_coverage_ratio = (
            round(promotion_review_count / strategy_count, 4) if strategy_count else 1.0
        )
        forward_window_coverage_ratio = (
            round(observed_forward_window_count / expected_forward_window_count, 4)
            if expected_forward_window_count
            else 1.0
        )
        evidence_debt_ratio = round(
            min(
                max(
                    zero_signal_ratio * 0.45
                    + (1.0 - forward_window_coverage_ratio) * 0.25
                    + (1.0 - promotion_ready_ratio) * 0.15
                    + (1.0 - promotion_review_coverage_ratio) * 0.15,
                    0.0,
                ),
                1.0,
            ),
            4,
        )
        result = {
            "strategy_count": strategy_count,
            "strategy_ids": list(payload.get("strategy_ids") or [])[:20],
            "runtime_alert_count": int(payload.get("runtime_alert_count") or 0),
            "runtime_risk_event_count": int(payload.get("runtime_risk_event_count") or 0),
            "signal_count_total": signal_count_total,
            "avg_signal_count": round(signal_count_total / strategy_count, 4) if strategy_count else 0.0,
            "zero_signal_strategy_count": zero_signal_strategy_count,
            "zero_signal_ratio": zero_signal_ratio,
            "low_signal_strategy_count": low_signal_strategy_count,
            "low_signal_ratio": low_signal_ratio,
            "observed_forward_window_count": observed_forward_window_count,
            "missing_forward_window_count": missing_forward_window_count,
            "expected_forward_window_count": expected_forward_window_count,
            "forward_window_coverage_ratio": forward_window_coverage_ratio,
            "promotion_ready_count": promotion_ready_count,
            "promotion_ready_ratio": promotion_ready_ratio,
            "promotion_review_coverage_ratio": promotion_review_coverage_ratio,
            "evidence_debt_strategy_count": evidence_debt_strategy_count,
            "evidence_debt_ratio": evidence_debt_ratio,
            "raw_validation_a_rate": round(
                int(raw_validation_grade_distribution.get("A") or 0) / strategy_count,
                4,
            ) if strategy_count else 0.0,
            "raw_validation_b_rate": round(
                int(raw_validation_grade_distribution.get("B") or 0) / strategy_count,
                4,
            ) if strategy_count else 0.0,
            "raw_validation_c_rate": round(
                int(raw_validation_grade_distribution.get("C") or 0) / strategy_count,
                4,
            ) if strategy_count else 0.0,
            "raw_validation_d_rate": round(
                int(raw_validation_grade_distribution.get("D") or 0) / strategy_count,
                4,
            ) if strategy_count else 1.0,
            "raw_validation_total_score_mean": round(
                raw_validation_total_score_total / raw_validation_total_score_count,
                4,
            ) if raw_validation_total_score_count else 0.0,
            "strict_incubation_ready_count": strict_incubation_ready_count,
            "strict_incubation_ready_rate": round(
                strict_incubation_ready_count / strategy_count,
                4,
            ) if strategy_count else 0.0,
            "live_candidate_ready_count": live_candidate_ready_count,
            "live_candidate_ready_rate": round(
                live_candidate_ready_count / strategy_count,
                4,
            ) if strategy_count else 0.0,
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
        if raw_validation_grade_distribution:
            result["raw_validation_grade_distribution"] = raw_validation_grade_distribution
        if payload.get("ema_submit_count") is not None:
            result["ema_submit_count"] = round(cls._safe_float(payload.get("ema_submit_count")), 4)
        if promotion_review_count > 0:
            result["promotion_review_count"] = promotion_review_count
            if promotion_review_status_counts:
                result["promotion_review_status_counts"] = promotion_review_status_counts
            if promotion_review_recommendation_counts:
                result["promotion_review_recommendation_counts"] = (
                    promotion_review_recommendation_counts
                )
            if payload.get("promotion_review_score_total") is not None:
                result["promotion_review_score"] = round(
                    cls._safe_float(payload.get("promotion_review_score_total"))
                    / max(promotion_review_count, 1),
                    4,
                )
            if promotion_review_status:
                result["promotion_review_status"] = promotion_review_status
            if promotion_review_recommendation:
                result["promotion_review_recommendation"] = promotion_review_recommendation
        if target_pool_feedback:
            result["target_pool_feedback"] = target_pool_feedback
        if holding_bucket_feedback:
            result["holding_bucket_feedback"] = holding_bucket_feedback
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
        for scope_name in (
            "target_pool_feedback",
            "holding_bucket_feedback",
            "generator_mode_feedback",
        ):
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
        base_review_count = int(base_payload.get("promotion_review_count") or 0)
        fresh_review_count = int(fresh_payload.get("promotion_review_count") or 0)
        merged_review_count = base_review_count + fresh_review_count
        if merged_review_count > 0:
            merged["promotion_review_count"] = merged_review_count
            merged_status_counts: dict[str, int] = {}
            for mapping in (
                base_payload.get("promotion_review_status_counts"),
                fresh_payload.get("promotion_review_status_counts"),
            ):
                for key, value in dict(mapping or {}).items():
                    token = normalize_text(key)
                    if not token:
                        continue
                    merged_status_counts[token] = int(merged_status_counts.get(token) or 0) + int(
                        value or 0
                    )
            if merged_status_counts:
                merged["promotion_review_status_counts"] = merged_status_counts
            merged_recommendation_counts: dict[str, int] = {}
            for mapping in (
                base_payload.get("promotion_review_recommendation_counts"),
                fresh_payload.get("promotion_review_recommendation_counts"),
            ):
                for key, value in dict(mapping or {}).items():
                    token = normalize_text(key)
                    if not token:
                        continue
                    merged_recommendation_counts[token] = int(
                        merged_recommendation_counts.get(token) or 0
                    ) + int(value or 0)
            if merged_recommendation_counts:
                merged["promotion_review_recommendation_counts"] = merged_recommendation_counts
            weighted_score_total = 0.0
            weighted_score_count = 0
            for payload_item, review_count in (
                (base_payload, base_review_count),
                (fresh_payload, fresh_review_count),
            ):
                if review_count <= 0 or payload_item.get("promotion_review_score") is None:
                    continue
                weighted_score_total += cls._safe_float(payload_item.get("promotion_review_score")) * review_count
                weighted_score_count += review_count
            if weighted_score_count > 0:
                merged["promotion_review_score"] = round(
                    weighted_score_total / weighted_score_count,
                    4,
                )
            review_status, review_recommendation = cls._resolve_promotion_review_outcome(
                merged_status_counts,
                merged_recommendation_counts,
            )
            if review_status:
                merged["promotion_review_status"] = review_status
            if review_recommendation:
                merged["promotion_review_recommendation"] = review_recommendation
        return merged

    @classmethod
    async def _load_budget_feedback(
        cls,
        db,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        return await load_budget_feedback(cls, db, snapshot)

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
        family_preference_order: List[str],
        governed_top_candidates: List[dict[str, Any]],
        budget_feedback_root: Any = None,
    ) -> dict[str, Any]:
        return await load_stock_family_allocation(
            cls,
            db,
            snapshot,
            active_factors=active_factors,
            family_preference_order=family_preference_order,
            governed_top_candidates=governed_top_candidates,
            budget_feedback_root=budget_feedback_root,
        )

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
        governed_candidate_pool_provisional_spillover_count = int(
            active_candidate_pool.get("provisional_spillover_count") or 0
        )
        governed_candidate_pool_provisional_spillover_policy = dict(
            active_candidate_pool.get("provisional_spillover_policy") or {}
        )
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
            seed_feedback_root = extract_feedback_root(snapshot.get("family_gate_feedback") or {})
            budget_feedback_payload = normalize_feedback_input_contract(
                {"feedback": seed_feedback_root},
                available=bool(seed_feedback_root),
                reason="lightweight_mock_fallback" if not seed_feedback_root else None,
                summary={
                    "family_count": len(seed_feedback_root),
                    "seeded_family_count": len(seed_feedback_root),
                    "strategy_count": 0,
                    "runtime_alert_count": 0,
                    "runtime_risk_event_count": 0,
                    "target_pool_scope_count": 0,
                    "generator_mode_scope_count": 0,
                },
            )
        else:
            budget_feedback_payload = await cls._load_budget_feedback(db, snapshot)
        lifecycle_feedback_input = normalize_feedback_input_contract(budget_feedback_payload)
        budget_feedback_root = dict(lifecycle_feedback_input.get("feedback") or {})
        budget_feedback_summary = dict(lifecycle_feedback_input.get("summary") or {})
        governed_source_candidate_count = int(
            active_candidate_pool.get("source_count")
            or governed_registry_summary.get("count")
            or 0
        )
        governed_active_registry_candidate_count = int(
            governed_registry_summary.get("active_count")
            or active_candidate_pool.get("count")
            or 0
        )
        blocked_excluded_count = active_candidate_pool.get("blocked_excluded_count")
        governed_blocked_candidate_count = (
            int(blocked_excluded_count or 0)
            if blocked_excluded_count is not None
            else int(governed_registry_summary.get("blocked_active_count") or 0)
        )
        if governed_blocked_candidate_count <= 0:
            governed_blocked_candidate_count = sum(
                1
                for item in list(active_candidate_pool.get("excluded_candidates") or [])
                if bool((item or {}).get("admission_blocked"))
                or bool(dict((item or {}).get("risk_audit") or {}).get("blocked"))
            )
        pending_excluded_count = active_candidate_pool.get("pending_excluded_count")
        governed_pending_candidate_count = (
            int(pending_excluded_count or 0)
            if pending_excluded_count is not None
            else max(
                int(active_candidate_pool.get("excluded_count") or 0) - governed_blocked_candidate_count,
                0,
            )
        )
        ineligible_excluded_count = active_candidate_pool.get("ineligible_excluded_count")
        governed_ineligible_candidate_count = (
            int(ineligible_excluded_count or 0)
            if ineligible_excluded_count is not None
            else max(
                int(active_candidate_pool.get("excluded_count") or 0)
                - governed_blocked_candidate_count
                - governed_pending_candidate_count,
                0,
            )
        )
        governed_exclusion_reason_counts = {
            str(key): int(value or 0)
            for key, value in dict(active_candidate_pool.get("exclusion_reason_counts") or {}).items()
            if str(key).strip()
        }
        governed_blocking_reason_counts = {
            str(key): int(value or 0)
            for key, value in dict(active_candidate_pool.get("blocked_exclusion_reason_counts") or {}).items()
            if str(key).strip()
        }
        governed_pending_reason_counts = {
            str(key): int(value or 0)
            for key, value in dict(active_candidate_pool.get("pending_exclusion_reason_counts") or {}).items()
            if str(key).strip()
        }
        governed_ineligible_reason_counts = {
            str(key): int(value or 0)
            for key, value in dict(active_candidate_pool.get("ineligible_exclusion_reason_counts") or {}).items()
            if str(key).strip()
        }
        governed_candidate_pool_provisional_pending_count = int(
            governed_candidate_pool_provisional_spillover_policy.get("pending_provisional_count") or 0
        )
        governed_candidate_pool_strict_shortfall_count = int(
            governed_candidate_pool_provisional_spillover_policy.get("strict_shortfall_count") or 0
        )
        governed_candidate_pool_provisional_spillover_policy_status = (
            str(governed_candidate_pool_provisional_spillover_policy.get("status") or "").strip().lower() or None
        )
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
        governed_pending_ratio = round(
            governed_pending_candidate_count / max(governed_source_candidate_count, 1),
            6,
        ) if governed_source_candidate_count > 0 else 0.0
        governed_ineligible_ratio = round(
            governed_ineligible_candidate_count / max(governed_source_candidate_count, 1),
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
        family_preference_order_seed = cls._build_family_preference_order(
            snapshot,
            preferred_strategy_types=preferred_strategy_types,
        )
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
                family_preference_order=family_preference_order_seed,
                governed_top_candidates=governed_top_candidates,
                budget_feedback_root=budget_feedback_root,
            )
        stock_family_allocation = dict(stock_family_allocation_payload.get("allocation") or {})
        stock_family_allocation_summary = dict(stock_family_allocation_payload.get("summary") or {})
        family_preference_order = cls._build_family_preference_order(
            snapshot,
            preferred_strategy_types=preferred_strategy_types,
            allocation_family_counts=dict(stock_family_allocation_summary.get("family_counts") or {}),
        )
        family_preference_source_mode = cls._family_preference_source_mode(
            family_preference_order=family_preference_order,
            preferred_strategy_types=preferred_strategy_types,
            allocation_family_counts=dict(stock_family_allocation_summary.get("family_counts") or {}),
        )

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
        if int(budget_feedback_summary.get("promotion_review_count") or 0) > 0:
            rationale.append(
                "生命周期反馈已纳入 promotion review: "
                f"count={int(budget_feedback_summary.get('promotion_review_count') or 0)} "
                f"status={dict(budget_feedback_summary.get('promotion_review_status_counts') or {})}"
            )
        if cls._safe_float(budget_feedback_summary.get("zero_signal_ratio")) >= 0.40:
            rationale.append(
                "incubating 零信号 backlog 偏高: "
                f"{round(cls._safe_float(budget_feedback_summary.get('zero_signal_ratio')) * 100, 1)}%"
            )
        if cls._safe_float(budget_feedback_summary.get("forward_window_coverage_ratio"), 1.0) <= 0.50:
            rationale.append(
                "前向观察窗口覆盖不足: "
                f"{round(cls._safe_float(budget_feedback_summary.get('forward_window_coverage_ratio'), 1.0) * 100, 1)}%"
            )
        if cls._safe_float(budget_feedback_summary.get("evidence_debt_ratio")) >= 0.45:
            rationale.append(
                "生命周期证据债务偏高，下一轮应优先补 signals / forward windows / promotion review。"
            )
        if governed_blocked_ratio >= 0.40:
            rationale.append(f"治理候选池 blocked 比例偏高: {round(governed_blocked_ratio * 100, 1)}%")
        if governed_pending_ratio >= 0.50:
            rationale.append(f"治理候选池待晋级候选占比偏高: {round(governed_pending_ratio * 100, 1)}%")
        if governed_ineligible_candidate_count:
            rationale.append(
                "治理候选池存在应清退候选: "
                f"count={governed_ineligible_candidate_count} "
                f"reasons={governed_ineligible_reason_counts or {'ineligible': governed_ineligible_candidate_count}}"
            )
        if governed_candidate_pool_provisional_spillover_policy_status in {
            "spillover_applied",
            "spillover_capacity_exhausted",
            "spillover_disabled",
            "awaiting_governed_promotion",
        }:
            rationale.append(
                "治理候选池 spillover 策略: "
                f"status={governed_candidate_pool_provisional_spillover_policy_status} "
                f"strict_shortfall={governed_candidate_pool_strict_shortfall_count} "
                f"spillover={governed_candidate_pool_provisional_spillover_count} "
                f"pending={governed_candidate_pool_provisional_pending_count}"
            )
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
        if governed_pending_ratio >= 0.75:
            quality_flags.append("governed_candidate_pool_promotion_backlog_high")
        elif governed_pending_ratio >= 0.40:
            quality_flags.append("governed_candidate_pool_promotion_backlog_elevated")
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
        if cls._safe_float(budget_feedback_summary.get("zero_signal_ratio")) >= 0.75:
            quality_flags.append("budget_feedback_zero_signal_backlog_high")
        elif cls._safe_float(budget_feedback_summary.get("zero_signal_ratio")) >= 0.40:
            quality_flags.append("budget_feedback_zero_signal_backlog_elevated")
        if cls._safe_float(budget_feedback_summary.get("forward_window_coverage_ratio"), 1.0) <= 0.25:
            quality_flags.append("budget_feedback_forward_window_coverage_low")
        elif cls._safe_float(budget_feedback_summary.get("forward_window_coverage_ratio"), 1.0) <= 0.50:
            quality_flags.append("budget_feedback_forward_window_coverage_elevated")
        if cls._safe_float(budget_feedback_summary.get("evidence_debt_ratio")) >= 0.75:
            quality_flags.append("budget_feedback_evidence_debt_high")
        elif cls._safe_float(budget_feedback_summary.get("evidence_debt_ratio")) >= 0.45:
            quality_flags.append("budget_feedback_evidence_debt_elevated")
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
        (
            family_reward_table,
            family_debt_table,
            search_route_actions,
            search_route_family_plans,
        ) = cls._build_search_route_feedback_snapshot(
            family_preference_order=family_preference_order,
            budget_feedback_root=budget_feedback_root,
        )
        effective_family_preference_order = cls._rewrite_family_preference_order_by_feedback(
            family_preference_order,
            family_plans=search_route_family_plans,
        )
        feedback_routed = effective_family_preference_order != family_preference_order
        family_preference_order = effective_family_preference_order
        family_preference_source_mode = cls._family_preference_source_mode(
            family_preference_order=family_preference_order,
            preferred_strategy_types=preferred_strategy_types,
            allocation_family_counts=dict(stock_family_allocation_summary.get("family_counts") or {}),
            feedback_routed=feedback_routed,
        )
        search_route_action_counts: dict[str, int] = {}
        for action in search_route_actions:
            action_name = normalize_text(action.get("action")) or "unknown"
            search_route_action_counts[action_name] = (
                search_route_action_counts.get(action_name, 0) + 1
            )
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
            "lifecycle_feedback_input": lifecycle_feedback_input,
            "budget_feedback": budget_feedback_root,
            "active_candidate_pool": active_candidate_pool,
            "stock_family_allocation": stock_family_allocation,
            "family_preference_order": family_preference_order,
            "family_reward_table": family_reward_table,
            "family_debt_table": family_debt_table,
            "search_route_actions": search_route_actions,
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
            "summary": build_factor_research_summary(
                active_factors=active_factors,
                active_candidate_pool=active_candidate_pool,
                governed_source_candidate_count=governed_source_candidate_count,
                governed_active_registry_candidate_count=governed_active_registry_candidate_count,
                governed_blocked_candidate_count=governed_blocked_candidate_count,
                governed_blocked_ratio=governed_blocked_ratio,
                governed_pending_candidate_count=governed_pending_candidate_count,
                governed_pending_ratio=governed_pending_ratio,
                governed_ineligible_candidate_count=governed_ineligible_candidate_count,
                governed_ineligible_ratio=governed_ineligible_ratio,
                governed_latest_candidate_at=governed_latest_candidate_at,
                governed_freshness_days=governed_freshness_days,
                ranked_factors=ranked_factors,
                top_factor_names=top_factor_names,
                top_candidate_names=top_candidate_names,
                governed_family_summary=governed_family_summary,
                governed_regime_summary=governed_regime_summary,
                preferred_strategy_types=preferred_strategy_types,
                family_preference_order=family_preference_order,
                family_preference_source_mode=family_preference_source_mode,
                governed_top_candidates=governed_top_candidates,
                governed_pool_missing_after_scheduler_success=governed_pool_missing_after_scheduler_success,
                governed_candidate_pool_mode=governed_candidate_pool_mode,
                governed_candidate_pool_provisional=governed_candidate_pool_provisional,
                governed_candidate_pool_strict_count=governed_candidate_pool_strict_count,
                governed_candidate_pool_provisional_count=governed_candidate_pool_provisional_count,
                governed_candidate_pool_provisional_spillover_count=governed_candidate_pool_provisional_spillover_count,
                governed_candidate_pool_provisional_spillover_enabled=bool(
                    active_candidate_pool.get("provisional_spillover_enabled")
                ),
                governed_candidate_pool_provisional_spillover_policy=governed_candidate_pool_provisional_spillover_policy,
                governed_candidate_pool_provisional_spillover_policy_status=governed_candidate_pool_provisional_spillover_policy_status,
                governed_candidate_pool_provisional_pending_count=governed_candidate_pool_provisional_pending_count,
                governed_candidate_pool_strict_shortfall_count=governed_candidate_pool_strict_shortfall_count,
                scheduler_status=scheduler_status,
                scheduler_recent_success=scheduler_recent_success,
                scheduler_llm_validation_status=scheduler_llm_validation_status,
                scheduler_llm_provider=scheduler_llm_provider,
                scheduler_llm_provider_health_status=scheduler_llm_provider_health_status,
                lightweight_mock_fallback=lightweight_mock_fallback,
                governed_exclusion_reason_counts=governed_exclusion_reason_counts,
                governed_blocking_reason_counts=governed_blocking_reason_counts,
                governed_pending_reason_counts=governed_pending_reason_counts,
                governed_ineligible_reason_counts=governed_ineligible_reason_counts,
                governed_registry_summary=governed_registry_summary,
                top_candidate_lineage=top_candidate_lineage,
                model_registry_lineage=model_registry_lineage,
                model_lineage_summary=model_lineage_summary,
                stock_family_allocation_summary=stock_family_allocation_summary,
                lifecycle_feedback_input=lifecycle_feedback_input,
                budget_feedback_summary=budget_feedback_summary,
                search_route_action_counts=search_route_action_counts,
                degraded=degraded,
                freshness_days=freshness_days,
                latest_factor_date=latest_factor_date.isoformat() if latest_factor_date else None,
                stale=stale,
                quality_flags=quality_flags,
                decay_factors=decay_factors,
                stability_tags=stability_tags,
            ),
        }


__all__ = ["FactorResearchBuilder"]
