"""Dynamic incubation slot allocator for the P2 factory lane."""

from __future__ import annotations

import math
from typing import Any

from ..domain.constants import (
    FACTORY_INCUBATION_EXPLORATION_RATIO,
    FACTORY_INCUBATION_FORMAL_SLOT_COUNT,
    FACTORY_INCUBATION_OBSERVE_SLOT_COUNT,
)


class IncubationBudgeter:
    """Allocate candidates into formal / observe / deferred incubation tracks."""

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    @staticmethod
    def _candidate_family(candidate: dict[str, Any]) -> str:
        payload = dict(candidate or {})
        research_task = dict(payload.get("research_task") or {})
        params = dict(payload.get("params") or {})
        candidate_provenance = dict(params.get("candidate_provenance") or {})
        return str(
            payload.get("candidate_family")
            or research_task.get("candidate_family")
            or params.get("candidate_family")
            or candidate_provenance.get("candidate_family")
            or payload.get("strategy_type")
            or "unknown"
        ).strip().lower() or "unknown"

    @staticmethod
    def _expected_regimes(candidate: dict[str, Any]) -> list[str]:
        payload = dict(candidate or {})
        params = dict(payload.get("params") or {})
        candidate_provenance = dict(params.get("candidate_provenance") or {})
        values = (
            payload.get("expected_regime")
            or params.get("expected_regime")
            or candidate_provenance.get("expected_regime")
            or []
        )
        if not isinstance(values, list):
            values = [values]
        return [
            str(item or "").strip().lower()
            for item in list(values or [])
            if str(item or "").strip()
        ]

    @staticmethod
    def _market_regime(snapshot: dict[str, Any]) -> str:
        fg = IncubationBudgeter._safe_float(snapshot.get("fear_greed_index"), 50.0)
        if fg >= 60:
            return "trend"
        if fg <= 40:
            return "mean_reversion"
        return "rotation"

    @classmethod
    def _regime_match_bonus(cls, candidate: dict[str, Any], snapshot: dict[str, Any]) -> float:
        market_regime = cls._market_regime(snapshot)
        expected_regimes = cls._expected_regimes(candidate)
        regime_fit = str(
            dict(candidate.get("research_task") or {}).get("regime_fit")
            or candidate.get("regime_fit")
            or dict(candidate.get("params") or {}).get("regime_fit")
            or ""
        ).strip().lower()
        if market_regime == "trend" and (
            "trend" in expected_regimes or "trend" in regime_fit or "breakout" in regime_fit
        ):
            return 6.0
        if market_regime == "mean_reversion" and (
            "mean_reversion" in expected_regimes
            or "mean_reversion" in regime_fit
            or "reversal" in regime_fit
        ):
            return 6.0
        if market_regime == "rotation" and (
            "rotation" in expected_regimes or "rotation" in regime_fit or "balanced" in regime_fit
        ):
            return 5.0
        return 0.0

    @classmethod
    def _priority_score(cls, candidate: dict[str, Any], snapshot: dict[str, Any]) -> float:
        payload = dict(candidate or {})
        metrics = dict(payload.get("backtest_metrics") or {})
        research_task = dict(payload.get("research_task") or {})
        params = dict(payload.get("params") or {})
        candidate_provenance = dict(params.get("candidate_provenance") or {})

        sharpe = cls._safe_float(metrics.get("sharpe_ratio"))
        total_return = cls._safe_float(metrics.get("total_return"))
        max_drawdown = max(0.0, cls._safe_float(metrics.get("max_drawdown")))
        validation_score = cls._safe_float(
            payload.get("candidate_validation_score")
            or candidate_provenance.get("validation_score")
            or params.get("candidate_validation_score")
        )
        task_priority = cls._safe_float(
            payload.get("priority")
            or research_task.get("priority")
            or payload.get("matrix_priority_score")
            or research_task.get("matrix_priority_score")
        )
        stock_family_priority = cls._safe_float(
            payload.get("stock_family_priority")
            or research_task.get("stock_family_priority")
        )
        registry_stage = str(
            payload.get("candidate_registry_stage")
            or candidate_provenance.get("candidate_registry_stage")
            or params.get("candidate_registry_stage")
            or ""
        ).strip().lower()
        risk_level = str(
            payload.get("risk_level")
            or research_task.get("risk_level")
            or params.get("risk_level")
            or candidate_provenance.get("risk_level")
            or ""
        ).strip().lower()
        active_family_names = {
            str(item or "").strip().lower()
            for item in list(((snapshot.get("factor_research") or {}).get("summary") or {}).get("active_family_names") or [])
            if str(item or "").strip()
        }
        family_name = cls._candidate_family(payload)

        score = 0.0
        score += max(-1.0, min(sharpe, 3.0)) * 20.0
        score += max(-0.2, min(total_return, 0.6)) * 40.0
        score -= min(max_drawdown, 0.6) * 15.0
        score += min(max(validation_score, 0.0), 100.0) * 0.25
        score += max(task_priority, 0.0) * 0.18
        score += max(stock_family_priority, 0.0) * 12.0
        score += cls._regime_match_bonus(payload, snapshot)
        if family_name in active_family_names:
            score += 4.0
        if registry_stage == "champion":
            score += 5.0
        elif registry_stage == "challenger":
            score += 4.0
        elif registry_stage == "governed":
            score += 3.0
        if risk_level == "low":
            score += 3.0
        elif risk_level == "high":
            score -= 4.0

        # P2-D 反馈回路：历史孵化成功率奖励（EMA 平滑）
        family_feedback = dict((snapshot.get("family_gate_feedback") or {}).get(family_name) or {})
        ema_submit = cls._safe_float(family_feedback.get("ema_submit_count"), -1.0)
        if ema_submit >= 0.0:
            if ema_submit > 3.0:
                score += 5.0
            elif ema_submit > 1.0:
                score += 2.5
            elif ema_submit < 0.3:
                score -= 2.0

        return round(score, 4)

    @classmethod
    def _is_exploration_candidate(
        cls,
        candidate: dict[str, Any],
        *,
        dominant_families: set[str],
        active_family_names: set[str],
    ) -> bool:
        family_name = cls._candidate_family(candidate)
        if family_name not in dominant_families:
            return True
        if family_name not in active_family_names:
            return True
        params = dict(candidate.get("params") or {})
        candidate_provenance = dict(params.get("candidate_provenance") or {})
        registry_stage = str(
            params.get("candidate_registry_stage")
            or candidate.get("candidate_registry_stage")
            or candidate_provenance.get("candidate_registry_stage")
            or ""
        ).strip().lower()
        return registry_stage not in {"champion", "challenger", "governed"}

    @classmethod
    def plan(
        cls,
        candidates: list[dict[str, Any]],
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        formal_slots = max(1, int(FACTORY_INCUBATION_FORMAL_SLOT_COUNT))
        observe_slots = max(0, int(FACTORY_INCUBATION_OBSERVE_SLOT_COUNT))
        total_budget = formal_slots + observe_slots
        if not candidates:
            return {
                "plans": {},
                "summary": {
                    "formal_slots": formal_slots,
                    "observe_slots": observe_slots,
                    "exploration_reserved_slots": 0,
                    "track_counts": {
                        "formal_incubation": 0,
                        "observe_incubation": 0,
                        "deferred_budget_queue": 0,
                    },
                    "family_counts": {},
                    "dominant_families": [],
                },
            }

        family_counts: dict[str, int] = {}
        family_best_scores: dict[str, float] = {}
        active_family_names = {
            str(item or "").strip().lower()
            for item in list(((snapshot.get("factor_research") or {}).get("summary") or {}).get("active_family_names") or [])
            if str(item or "").strip()
        }
        entries: list[dict[str, Any]] = []
        for candidate in list(candidates or []):
            family_name = cls._candidate_family(candidate)
            score = cls._priority_score(candidate, snapshot)
            family_counts[family_name] = family_counts.get(family_name, 0) + 1
            family_best_scores[family_name] = max(score, family_best_scores.get(family_name, score))
            entries.append(
                {
                    "marker": id(candidate),
                    "candidate": candidate,
                    "family": family_name,
                    "priority_score": score,
                }
            )

        dominant_family_pairs = sorted(
            family_best_scores.items(),
            key=lambda item: (-float(item[1]), -int(family_counts.get(item[0]) or 0), item[0]),
        )
        dominant_families = {family for family, _score in dominant_family_pairs[:3]}
        sorted_entries = sorted(
            entries,
            key=lambda item: (-float(item["priority_score"]), item["family"], item["marker"]),
        )
        exploration_reserved_slots = (
            min(total_budget, max(1, int(math.ceil(total_budget * FACTORY_INCUBATION_EXPLORATION_RATIO))))
            if total_budget > 0 and FACTORY_INCUBATION_EXPLORATION_RATIO > 0.0
            else 0
        )
        formal_family_cap = max(1, int(math.ceil(formal_slots * 0.45)))
        observe_family_cap = max(1, int(math.ceil(max(observe_slots, 1) * 0.55)))

        selected_formal: list[dict[str, Any]] = []
        selected_observe: list[dict[str, Any]] = []
        family_track_counts: dict[str, dict[str, int]] = {}
        selected_markers: set[int] = set()

        def _select_with_cap(
            target: list[dict[str, Any]],
            *,
            limit: int,
            family_cap: int,
        ) -> None:
            for entry in sorted_entries:
                if len(target) >= limit:
                    break
                marker = int(entry["marker"])
                if marker in selected_markers:
                    continue
                family_name = str(entry["family"])
                track_family_counts = family_track_counts.setdefault(family_name, {})
                if int(track_family_counts.get("selected") or 0) >= family_cap:
                    continue
                target.append(entry)
                selected_markers.add(marker)
                track_family_counts["selected"] = int(track_family_counts.get("selected") or 0) + 1
            for entry in sorted_entries:
                if len(target) >= limit:
                    break
                marker = int(entry["marker"])
                if marker in selected_markers:
                    continue
                family_name = str(entry["family"])
                track_family_counts = family_track_counts.setdefault(family_name, {})
                target.append(entry)
                selected_markers.add(marker)
                track_family_counts["selected"] = int(track_family_counts.get("selected") or 0) + 1

        _select_with_cap(selected_formal, limit=formal_slots, family_cap=formal_family_cap)
        _select_with_cap(selected_observe, limit=observe_slots, family_cap=observe_family_cap)

        selected_combined = [*selected_formal, *selected_observe]
        selected_exploration_count = sum(
            1
            for entry in selected_combined
            if cls._is_exploration_candidate(
                dict(entry.get("candidate") or {}),
                dominant_families=dominant_families,
                active_family_names=active_family_names,
            )
        )
        if exploration_reserved_slots > selected_exploration_count and observe_slots > 0:
            exploration_pool = [
                entry
                for entry in sorted_entries
                if int(entry["marker"]) not in selected_markers
                and cls._is_exploration_candidate(
                    dict(entry.get("candidate") or {}),
                    dominant_families=dominant_families,
                    active_family_names=active_family_names,
                )
            ]
            while (
                exploration_pool
                and selected_exploration_count < exploration_reserved_slots
                and selected_observe
            ):
                promoted = exploration_pool.pop(0)
                replaced_index = next(
                    (
                        index
                        for index in range(len(selected_observe) - 1, -1, -1)
                        if not cls._is_exploration_candidate(
                            dict(selected_observe[index].get("candidate") or {}),
                            dominant_families=dominant_families,
                            active_family_names=active_family_names,
                        )
                    ),
                    None,
                )
                if replaced_index is None:
                    break
                removed = selected_observe[replaced_index]
                selected_markers.discard(int(removed["marker"]))
                selected_observe[replaced_index] = promoted
                selected_markers.add(int(promoted["marker"]))
                selected_exploration_count += 1

        plans: dict[int, dict[str, Any]] = {}
        track_counts = {
            "formal_incubation": 0,
            "observe_incubation": 0,
            "deferred_budget_queue": 0,
        }
        rank = 0
        for track_name, bucket in (
            ("formal_incubation", selected_formal),
            ("observe_incubation", selected_observe),
        ):
            for entry in bucket:
                rank += 1
                candidate = dict(entry.get("candidate") or {})
                plan = {
                    "track": track_name,
                    "rank": rank,
                    "priority_score": float(entry.get("priority_score") or 0.0),
                    "family": entry.get("family"),
                    "exploration_candidate": cls._is_exploration_candidate(
                        candidate,
                        dominant_families=dominant_families,
                        active_family_names=active_family_names,
                    ),
                }
                plans[int(entry["marker"])] = plan
                track_counts[track_name] += 1

        for entry in sorted_entries:
            marker = int(entry["marker"])
            if marker in plans:
                continue
            rank += 1
            plans[marker] = {
                "track": "deferred_budget_queue",
                "rank": rank,
                "priority_score": float(entry.get("priority_score") or 0.0),
                "family": entry.get("family"),
                "exploration_candidate": cls._is_exploration_candidate(
                    dict(entry.get("candidate") or {}),
                    dominant_families=dominant_families,
                    active_family_names=active_family_names,
                ),
            }
            track_counts["deferred_budget_queue"] += 1

        return {
            "plans": plans,
            "summary": {
                "formal_slots": formal_slots,
                "observe_slots": observe_slots,
                "formal_family_cap": formal_family_cap,
                "observe_family_cap": observe_family_cap,
                "exploration_reserved_slots": exploration_reserved_slots,
                "exploration_selected_count": selected_exploration_count,
                "track_counts": track_counts,
                "family_counts": dict(sorted(family_counts.items(), key=lambda item: (-item[1], item[0]))),
                "dominant_families": [family for family, _score in dominant_family_pairs[:3]],
                "priority_score_avg": round(
                    sum(float(item.get("priority_score") or 0.0) for item in sorted_entries) / len(sorted_entries),
                    4,
                )
                if sorted_entries
                else 0.0,
            },
        }


__all__ = ["IncubationBudgeter"]
