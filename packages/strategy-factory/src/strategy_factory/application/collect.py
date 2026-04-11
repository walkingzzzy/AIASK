"""策略工厂数据快照采集。"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import numpy as np

from ..domain.constants import FACTORY_RESEARCH_FACTORS, resolve_event_runtime_mode
from .runtime import get_strategy_factory_package

logger = logging.getLogger(__name__)


def get_sentiment_analyzer():
    from ..infrastructure.mcp_services import get_sentiment_analyzer as _get_sentiment_analyzer

    return _get_sentiment_analyzer()


class DataCollector:
    """汇总每日市场数据快照。"""

    def __init__(
        self,
        *,
        sentiment_analyzer_factory=None,
        index_kline_provider=None,
    ):
        self._sentiment_analyzer_factory = sentiment_analyzer_factory
        self._index_kline_provider = index_kline_provider

    @staticmethod
    def _iso_now() -> str:
        return datetime.now().astimezone().isoformat()

    @staticmethod
    def _freshness_sec(asof_time: Optional[str], *, now: Optional[datetime] = None) -> float:
        if not asof_time:
            return 0.0
        try:
            observed = datetime.fromisoformat(str(asof_time).replace("Z", "+00:00"))
        except Exception:
            return 0.0
        current = now or datetime.now().astimezone()
        if observed.tzinfo is None:
            observed = observed.astimezone()
        return round(max((current - observed).total_seconds(), 0.0), 3)

    @staticmethod
    def _ordered_flags(flags: List[str]) -> List[str]:
        seen: set[str] = set()
        ordered: List[str] = []
        for flag in list(flags or []):
            item = str(flag or "").strip()
            if not item or item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered

    @classmethod
    def _build_quality_flags(
        cls,
        *,
        status: str,
        freshness_sec: float,
        stale_after_sec: Optional[float] = None,
        missing_fields: Optional[List[str]] = None,
        extra_flags: Optional[List[str]] = None,
    ) -> List[str]:
        flags: List[str] = list(extra_flags or [])
        normalized_status = str(status or "unknown").strip().lower() or "unknown"
        if normalized_status in {"partial", "fallback"}:
            flags.append(normalized_status)
        if normalized_status != "success":
            flags.append("degraded")
        if missing_fields:
            flags.append("missing_fields")
        if stale_after_sec is not None and float(freshness_sec or 0.0) > float(stale_after_sec):
            flags.append("stale")
        return cls._ordered_flags(flags)

    @classmethod
    def _build_source_status(
        cls,
        status: str,
        fields: List[str],
        reason: Optional[str] = None,
        details: Optional[dict] = None,
        *,
        source_name: Optional[str] = None,
        asof_time: Optional[str] = None,
    ) -> dict:
        resolved_asof_time = asof_time or cls._iso_now()
        freshness_sec = cls._freshness_sec(resolved_asof_time)
        payload = {
            "status": status,
            "source": str(source_name or "strategy_factory.collector"),
            "asof_time": resolved_asof_time,
            "freshness_sec": freshness_sec,
            "quality_flags": cls._build_quality_flags(
                status=status,
                freshness_sec=freshness_sec,
            ),
            "fields": list(fields),
            "degraded": status != "success",
        }
        if reason:
            payload["reason"] = reason
        if details:
            payload["details"] = details
        return payload

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value or default)
        except Exception:
            return float(default)

    @staticmethod
    def _clip_score(value: Any, default: float = 0.0) -> float:
        try:
            score = float(value)
        except Exception:
            score = float(default)
        return max(0.0, min(score, 1.0))

    @staticmethod
    def _compact_text(value: Any, limit: int = 120) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 3)] + "..."

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    @staticmethod
    def _normalize_codes(values: Any, limit: int = 5) -> List[str]:
        from ..domain.targets import _normalize_target_codes

        return _normalize_target_codes(values, limit=limit)

    @staticmethod
    def _is_factory_generated_strategy(strategy: Optional[dict]) -> bool:
        payload = dict(strategy or {})
        tags = {str(tag or "").strip().lower() for tag in list(payload.get("tags") or [])}
        author_id = str(payload.get("author_id") or "").strip().lower()
        source = str(payload.get("source") or "").strip().lower()
        if "factory" in tags or "auto_generated" in tags:
            return True
        if author_id == "strategy_factory":
            return True
        return source.startswith("strategy_factory")

    @classmethod
    def _observed_forward_days(cls, signal_stats: Optional[dict]) -> List[int]:
        payload = dict(signal_stats or {})
        observed: List[int] = []
        for days in (1, 5, 10, 20):
            day_found = False
            for metric_name in ("hit_rate", "forward_ic", "forward_sharpe"):
                metric = dict(payload.get(metric_name) or {})
                if metric.get(days) is not None or metric.get(str(days)) is not None:
                    day_found = True
                    break
            if day_found:
                observed.append(days)
        return observed

    @staticmethod
    async def _load_latest_quality_report(db, strategy_id: str) -> Optional[dict]:
        getter = getattr(db, "get_latest_strategy_quality_report", None)
        if callable(getter):
            report = getter(strategy_id)
            if hasattr(report, "__await__"):
                report = await report
            return dict(report or {}) if report else None
        getter = getattr(db, "list_strategy_quality_reports", None)
        if callable(getter):
            rows = getter(strategy_id, limit=1)
            if hasattr(rows, "__await__"):
                rows = await rows
            first = list(rows or [])[:1]
            return dict(first[0] or {}) if first else None
        getter = getattr(db, "get_strategy_quality_report", None)
        if callable(getter):
            report = getter(strategy_id)
            if hasattr(report, "__await__"):
                report = await report
            return dict(report or {}) if report else None
        return None

    async def _collect_parameter_distribution_snapshot(
        self,
        db,
        *,
        limit_per_status: int = 120,
        max_samples: int = 96,
    ) -> dict:
        list_strategies = getattr(db, "list_strategies", None)
        get_signal_stats = getattr(db, "get_signal_stats", None)
        if not callable(list_strategies) or not callable(get_signal_stats):
            return {
                "items": [],
                "summary": {
                    "eligible_sample_count": 0,
                    "factory_strategy_count": 0,
                    "strategy_type_counts": {},
                    "source": "unavailable",
                },
            }

        submitted, incubating, listed = await asyncio.gather(
            list_strategies("submitted", limit=limit_per_status),
            list_strategies("incubating", limit=limit_per_status),
            list_strategies("listed", limit=limit_per_status),
        )
        strategy_map: dict[str, dict] = {}
        for row in [*list(submitted or []), *list(incubating or []), *list(listed or [])]:
            strategy = dict(row or {})
            strategy_id = str(strategy.get("id") or "").strip()
            if not strategy_id or not self._is_factory_generated_strategy(strategy):
                continue
            strategy_map[strategy_id] = strategy

        strategies = list(strategy_map.values())
        if not strategies:
            return {
                "items": [],
                "summary": {
                    "eligible_sample_count": 0,
                    "factory_strategy_count": 0,
                    "strategy_type_counts": {},
                    "source": "empty",
                },
            }

        quality_reports, signal_stats_rows = await asyncio.gather(
            asyncio.gather(
                *(self._load_latest_quality_report(db, str(strategy.get("id") or "")) for strategy in strategies)
            ),
            asyncio.gather(
                *(get_signal_stats(str(strategy.get("id") or "")) for strategy in strategies)
            ),
        )

        items: list[dict[str, Any]] = []
        strategy_type_counts: dict[str, int] = {}
        validation_grade_distribution: dict[str, int] = {}
        promotion_ready_count = 0
        quality_passed_count = 0
        for strategy, quality_report, signal_stats in zip(strategies, quality_reports, signal_stats_rows):
            params = dict(strategy.get("params") or {})
            strategy_type = str(strategy.get("strategy_type") or "").strip()
            if not strategy_type or not params:
                continue
            report = dict(quality_report or {})
            summary = dict(report.get("summary") or {})
            validation_grade = str(summary.get("validation_grade") or "").strip().upper()
            total_signals = self._safe_int(dict(signal_stats or {}).get("total_signals"), 0)
            observed_forward_days = self._observed_forward_days(signal_stats)
            quality_passed = bool(report.get("passed"))
            promotion_ready = (
                quality_passed
                and total_signals >= 10
                and {1, 5, 10, 20}.issubset(set(observed_forward_days))
                and validation_grade in {"A", "B", "C"}
            )
            oos_passed = (
                quality_passed
                and total_signals >= 10
                and validation_grade in {"A", "B", "C"}
                and bool({5, 10, 20} & set(observed_forward_days))
            )
            if not oos_passed:
                continue
            sampling_weight = round(
                {"A": 1.0, "B": 0.85, "C": 0.7}.get(validation_grade, 0.5)
                + min(total_signals / 20.0, 1.0) * 0.3
                + min(len(observed_forward_days) / 4.0, 1.0) * 0.25
                + (0.15 if promotion_ready else 0.0),
                4,
            )
            validation_grade_distribution[validation_grade] = (
                validation_grade_distribution.get(validation_grade, 0) + 1
            )
            if promotion_ready:
                promotion_ready_count += 1
            if quality_passed:
                quality_passed_count += 1
            items.append(
                {
                    "strategy_id": str(strategy.get("id") or ""),
                    "strategy_type": strategy_type,
                    "params": params,
                    "validation_grade": validation_grade,
                    "quality_passed": quality_passed,
                    "promotion_ready": promotion_ready,
                    "total_signals": total_signals,
                    "observed_forward_days": observed_forward_days,
                    "oos_passed": oos_passed,
                    "sampling_weight": sampling_weight,
                }
            )
            strategy_type_counts[strategy_type] = strategy_type_counts.get(strategy_type, 0) + 1

        items.sort(
            key=lambda item: (
                -float(item.get("sampling_weight") or 0.0),
                -int(item.get("total_signals") or 0),
                str(item.get("strategy_id") or ""),
            )
        )
        return {
            "items": items[:max_samples],
            "summary": {
                "eligible_sample_count": len(items[:max_samples]),
                "factory_strategy_count": len(strategies),
                "strategy_type_counts": strategy_type_counts,
                "validation_grade_distribution": validation_grade_distribution,
                "promotion_ready_count": promotion_ready_count,
                "quality_passed_count": quality_passed_count,
                "source": "strategy_population_quality_reports",
            },
        }

    def _get_sentiment_analyzer(self):
        if self._sentiment_analyzer_factory is None:
            self._sentiment_analyzer_factory = get_sentiment_analyzer
        return self._sentiment_analyzer_factory()

    async def _load_index_klines(self, code: str, *, limit: int = 60) -> List[dict]:
        provider = self._index_kline_provider
        if provider is None:
            from ..infrastructure.mcp_services import get_index_kline_provider

            provider = get_index_kline_provider()
        result = provider(code, limit=limit)
        if hasattr(result, "__await__"):
            result = await result
        if isinstance(result, dict) and result.get("success"):
            payload = result.get("data")
            if isinstance(payload, list):
                return payload
            return []
        if isinstance(result, list):
            return result
        return []

    @staticmethod
    def _normalize_fear_greed_level(value: Any, *, fallback_index: Any = 50) -> str:
        level = str(value or "").strip().lower()
        if level in {"fear", "neutral", "greed"}:
            return level
        try:
            numeric = float(fallback_index)
        except Exception:
            numeric = 50.0
        if numeric >= 70:
            return "greed"
        if numeric <= 30:
            return "fear"
        return "neutral"

    @classmethod
    def _extract_recent_successful_fear_greed(cls, snapshot: Any) -> Optional[dict]:
        if not isinstance(snapshot, dict):
            return None
        sources = snapshot.get("sources")
        fear_greed_source = sources.get("fear_greed") if isinstance(sources, dict) else None
        if not isinstance(fear_greed_source, dict):
            return None
        if str(fear_greed_source.get("status") or "").strip().lower() != "success":
            return None
        try:
            fear_greed_index = int(round(float(snapshot.get("fear_greed_index"))))
        except Exception:
            return None
        fg_components = snapshot.get("fg_components")
        return {
            "fear_greed_index": fear_greed_index,
            "fg_level": cls._normalize_fear_greed_level(
                snapshot.get("fg_level"),
                fallback_index=fear_greed_index,
            ),
            "fg_components": dict(fg_components) if isinstance(fg_components, dict) else {},
            "snapshot_date": str(snapshot.get("date") or snapshot.get("snapshot_date") or "").strip(),
        }

    async def _load_recent_successful_fear_greed_snapshot(
        self,
        db,
        *,
        current_date: Optional[Any] = None,
        limit: int = 10,
    ) -> Optional[dict]:
        getter = getattr(db, "list_daily_snapshots", None)
        if not callable(getter):
            return None
        rows = getter(limit=max(1, int(limit or 10)), end_date=current_date)
        if hasattr(rows, "__await__"):
            rows = await rows
        for item in list(rows or []):
            reused = self._extract_recent_successful_fear_greed(item)
            if reused is not None:
                return reused
        return None

    @classmethod
    def _event_strategy_preferences(
        cls,
        direction: str,
        theme_name: str,
        opportunity_hint: str,
    ) -> List[str]:
        from .research.opportunity import MarketOpportunityScanner

        return MarketOpportunityScanner._event_strategy_preferences(
            direction=direction,
            theme_name=theme_name,
            opportunity_type=opportunity_hint,
        )

    @classmethod
    def _default_theme_code(cls, cluster: dict[str, Any], fallback: str = "general") -> str:
        raw_themes = list(cluster.get("themes") or [])
        for item in raw_themes:
            if isinstance(item, dict):
                code = str(
                    item.get("theme_code") or item.get("code") or item.get("theme") or ""
                ).strip()
            else:
                code = str(item or "").strip()
            if code:
                return code
        return str(cluster.get("event_type") or fallback).strip() or fallback

    @classmethod
    def _finalize_snapshot_contract(
        cls,
        snapshot: Dict[str, Any],
        sources: Dict[str, dict],
        failure_reasons: List[dict],
        missing_fields: List[str],
        *,
        asof_time: str,
    ) -> dict:
        source_status_counts: Dict[str, int] = {}
        degraded_sources: List[str] = []
        missing_sources: List[str] = []
        for name, item in sources.items():
            status = str(item.get("status") or "unknown")
            source_status_counts[status] = source_status_counts.get(status, 0) + 1
            if status != "success":
                degraded_sources.append(name)
            if status == "fallback":
                missing_sources.append(name)

        total_sources = len(sources)
        available_sources = total_sources - len(degraded_sources)
        completion_ratio = round(available_sources / total_sources, 2) if total_sources else 1.0
        degraded = bool(degraded_sources)
        freshness_sec = cls._freshness_sec(asof_time)
        extra_flags: List[str] = []
        if degraded:
            extra_flags.append("degraded")
        if degraded or missing_fields:
            extra_flags.append("incomplete")
        event_state = dict(snapshot.get("event_driven") or {})
        snapshot["summary"] = {
            "date": snapshot.get("date"),
            "fear_greed_index": snapshot.get("fear_greed_index"),
            "fg_level": snapshot.get("fg_level"),
            "listed_count": snapshot.get("listed_count", 0),
            "incubating_count": snapshot.get("incubating_count", 0),
            "hot_sector_count": len(snapshot.get("hot_sectors") or []),
            "cold_sector_count": len(snapshot.get("cold_sectors") or []),
            "event_count": int(event_state.get("event_count") or 0),
            "event_task_ready_count": int(event_state.get("tasks_ready_count") or 0),
            "source_status_counts": source_status_counts,
            "degraded": degraded,
        }
        snapshot["completeness"] = {
            "is_complete": not degraded and not missing_fields,
            "total_sources": total_sources,
            "available_sources": available_sources,
            "degraded_sources": sorted(degraded_sources),
            "missing_sources": sorted(missing_sources),
            "completion_ratio": completion_ratio,
        }
        snapshot["source"] = "strategy_factory.collector"
        snapshot["asof_time"] = asof_time
        snapshot["freshness_sec"] = freshness_sec
        snapshot["quality_flags"] = cls._build_quality_flags(
            status="partial" if degraded else "success",
            freshness_sec=freshness_sec,
            stale_after_sec=24 * 60 * 60,
            missing_fields=missing_fields,
            extra_flags=extra_flags,
        )
        snapshot["sources"] = sources
        snapshot["failure_reasons"] = failure_reasons
        snapshot["missing_fields"] = sorted(set(missing_fields))
        snapshot["degraded"] = degraded
        snapshot["fear_greed"] = snapshot.get("fear_greed_index")
        snapshot["sentiment"] = snapshot.get("sentiment") or snapshot.get("fg_level")
        snapshot["north_fund"] = dict(snapshot.get("north_fund") or {})
        snapshot["north_fund"].setdefault("net_3d", snapshot.get("north_fund_3d_net"))
        return snapshot

    @classmethod
    async def _collect_event_driven_snapshot(
        cls,
        db,
    ) -> tuple[dict, str, Optional[str], Optional[dict]]:
        payload = {
            "enabled": False,
            "event_count": 0,
            "active_theme_count": 0,
            "signal_count": 0,
            "tasks_ready_count": 0,
            "events": [],
        }
        list_clusters = getattr(db, "list_factory_event_clusters", None)
        list_signals = getattr(db, "list_factory_event_signals", None)
        list_themes = getattr(db, "list_factory_theme_definitions", None)
        if not callable(list_clusters):
            return payload, "success", None, {"enabled": False}

        try:
            clusters = list_clusters(status="active", limit=8)
            if hasattr(clusters, "__await__"):
                clusters = await clusters
        except Exception as exc:
            return payload, "fallback", f"event_driven failed: {exc}", None

        theme_defs: Dict[str, dict] = {}
        if callable(list_themes):
            try:
                definitions = list_themes(active_only=True, limit=256)
                if hasattr(definitions, "__await__"):
                    definitions = await definitions
                theme_defs = {
                    str((item or {}).get("theme_code") or "").strip(): dict(item or {})
                    for item in list(definitions or [])
                    if str((item or {}).get("theme_code") or "").strip()
                }
            except Exception:
                theme_defs = {}

        payload["enabled"] = True
        raw_events = []
        total_signals = 0
        total_themes = 0
        ready_themes = 0

        for cluster in list(clusters or []):
            cluster = dict(cluster or {})
            event_id = str(cluster.get("event_id") or "").strip()
            if not event_id:
                continue
            grouped: Dict[str, dict] = {}
            for item in list(cluster.get("themes") or []):
                if isinstance(item, dict):
                    theme_code = str(
                        item.get("theme_code") or item.get("code") or item.get("theme") or ""
                    ).strip()
                    theme_name = str(item.get("theme_name") or theme_code).strip() or theme_code
                    direction = (
                        str(item.get("direction") or cluster.get("direction") or "neutral")
                        .strip()
                        .lower()
                        or "neutral"
                    )
                else:
                    theme_code = str(item or "").strip()
                    theme_name = (
                        str((theme_defs.get(theme_code) or {}).get("theme_name") or theme_code).strip()
                        or theme_code
                    )
                    direction = (
                        str(cluster.get("direction") or "neutral").strip().lower() or "neutral"
                    )
                if theme_code:
                    grouped[theme_code] = {
                        "theme_code": theme_code,
                        "theme_name": theme_name,
                        "direction": direction,
                        "signal_rows": [],
                        "supporting_reasons": [],
                    }

            signal_rows: List[dict] = []
            if callable(list_signals):
                try:
                    result = list_signals(event_id=event_id, limit=24)
                    if hasattr(result, "__await__"):
                        result = await result
                    signal_rows = [dict(item or {}) for item in list(result or [])]
                except Exception:
                    signal_rows = []

            if signal_rows:
                total_signals += len(signal_rows)
            for signal in signal_rows:
                theme_code = str(signal.get("theme_code") or "").strip() or cls._default_theme_code(
                    cluster
                )
                theme_def = theme_defs.get(theme_code) or {}
                direction = (
                    str(
                        signal.get("direction")
                        or (signal.get("evidence") or {}).get("direction")
                        or cluster.get("direction")
                        or "neutral"
                    )
                    .strip()
                    .lower()
                    or "neutral"
                )
                group = grouped.setdefault(
                    theme_code,
                    {
                        "theme_code": theme_code,
                        "theme_name": str(theme_def.get("theme_name") or theme_code).strip()
                        or theme_code,
                        "direction": direction,
                        "signal_rows": [],
                        "supporting_reasons": [],
                    },
                )
                group["direction"] = direction or group.get("direction") or "neutral"
                symbol = str(signal.get("symbol") or signal.get("code") or "").strip()
                final_score = cls._clip_score(signal.get("final_score"), default=0.0)
                theme_score = cls._clip_score(signal.get("theme_score"), default=final_score)
                exposure_score = cls._clip_score(signal.get("exposure_score"), default=final_score)
                price_confirm_score = cls._clip_score(signal.get("price_confirm_score"), default=0.0)
                flow_confirm_score = cls._clip_score(signal.get("flow_confirm_score"), default=0.0)
                rationale = cls._compact_text(
                    signal.get("rationale") or (signal.get("evidence") or {}).get("summary"),
                    limit=100,
                )
                if rationale and rationale not in group["supporting_reasons"]:
                    group["supporting_reasons"].append(rationale)
                if symbol:
                    group["signal_rows"].append(
                        {
                            "symbol": symbol,
                            "final_score": final_score,
                            "theme_score": theme_score,
                            "exposure_score": exposure_score,
                            "price_confirm_score": price_confirm_score,
                            "flow_confirm_score": flow_confirm_score,
                            "rationale": rationale,
                        }
                    )

            theme_payloads: List[dict] = []
            for theme_code, theme in grouped.items():
                signal_values = list(theme.get("signal_rows") or [])
                signal_values.sort(
                    key=lambda item: float(item.get("final_score") or 0.0), reverse=True
                )
                final_scores = [
                    cls._clip_score(item.get("final_score"), default=0.0)
                    for item in signal_values
                ]
                avg_final_score = (
                    round(sum(final_scores) / len(final_scores), 4) if final_scores else 0.0
                )
                max_final_score = round(max(final_scores), 4) if final_scores else 0.0
                from ..domain.constants import OPPORTUNITY_TARGET_SYMBOLS_PER_TASK as _COLLECT_LIMIT
                target_symbols = [
                    item.get("symbol") for item in signal_values if item.get("symbol")
                ][:_COLLECT_LIMIT]
                opportunity_hint = (
                    "factor_acceleration"
                    if "factor" in str(theme_code or "").lower()
                    else "sector_breakout"
                )
                strategy_prefs = cls._event_strategy_preferences(
                    direction=theme.get("direction") or cluster.get("direction") or "neutral",
                    theme_name=theme.get("theme_name") or theme_code,
                    opportunity_hint=opportunity_hint,
                )
                theme_direction = (
                    theme.get("direction")
                    or str(cluster.get("direction") or "neutral").strip().lower()
                    or "neutral"
                )
                theme_payload = {
                    "theme_code": theme_code,
                    "theme_name": theme.get("theme_name") or theme_code,
                    "direction": theme_direction,
                    "horizon": str(cluster.get("horizon") or "swing_5_20d").strip()
                    or "swing_5_20d",
                    "signal_count": len(signal_values),
                    "target_symbols": target_symbols,
                    "strategy_preferences": strategy_prefs,
                    "preferred_strategy_types": list(strategy_prefs),
                    "allowed_strategy_types": [],
                    "target_symbol_policy": "strict_intersection",
                    "universe_expansion_policy": "allow_same_theme_only",
                    "preference_strength": "medium",
                    "preference_reason": f"event_evidence:{theme_code}:{theme_direction}",
                    "validation_focus": "event_target_only",
                    "supporting_reasons": list(theme.get("supporting_reasons") or [])[:4],
                    "score_summary": {
                        "avg_final_score": avg_final_score,
                        "max_final_score": max_final_score,
                        "top_symbols": target_symbols,
                    },
                }
                total_themes += 1
                if target_symbols:
                    ready_themes += 1
                theme_payloads.append(theme_payload)

            if not theme_payloads:
                continue
            theme_payloads.sort(
                key=lambda item: (
                    float((item.get("score_summary") or {}).get("avg_final_score") or 0.0),
                    int(item.get("signal_count") or 0),
                ),
                reverse=True,
            )
            raw_events.append(
                {
                    "event_id": event_id,
                    "event_type": cluster.get("event_type"),
                    "event_name": cluster.get("event_name") or cluster.get("summary") or event_id,
                    "summary": cls._compact_text(
                        cluster.get("summary") or cluster.get("event_name") or event_id,
                        limit=160,
                    ),
                    "direction": str(cluster.get("direction") or "neutral").strip().lower()
                    or "neutral",
                    "intensity": cls._clip_score(cluster.get("intensity"), default=0.0),
                    "confidence": cls._clip_score(cluster.get("confidence"), default=0.0),
                    "horizon": str(cluster.get("horizon") or "swing_5_20d").strip()
                    or "swing_5_20d",
                    "occurred_at": cluster.get("occurred_at"),
                    "last_seen_at": cluster.get("last_seen_at"),
                    "themes": theme_payloads[:4],
                }
            )

        raw_events.sort(
            key=lambda item: (
                float(item.get("confidence") or 0.0),
                float(item.get("intensity") or 0.0),
                max(
                    float((theme.get("score_summary") or {}).get("avg_final_score") or 0.0)
                    for theme in list(item.get("themes") or [{}])
                ),
            ),
            reverse=True,
        )
        payload.update(
            {
                "event_count": len(raw_events),
                "active_theme_count": total_themes,
                "signal_count": total_signals,
                "tasks_ready_count": ready_themes,
                "events": raw_events[:6],
            }
        )
        return payload, "success", None, {
            "enabled": True,
            "event_count": len(raw_events),
            "active_theme_count": total_themes,
            "tasks_ready_count": ready_themes,
        }

    async def collect(self, db) -> dict:
        factory_pkg = get_strategy_factory_package()
        snapshot: Dict[str, Any] = {"date": str(date.today())}
        collected_at = self._iso_now()
        sources: Dict[str, dict] = {}
        failure_reasons: List[dict] = []
        missing_fields: List[str] = []

        def record_source(
            name: str,
            status: str,
            fields: List[str],
            reason: Optional[str] = None,
            details: Optional[dict] = None,
        ) -> None:
            sources[name] = self._build_source_status(
                status,
                fields,
                reason=reason,
                details=details,
                source_name=name,
                asof_time=collected_at,
            )
            if status != "success":
                failure_reasons.append(
                    {
                        "source": name,
                        "status": status,
                        "reason": reason or f"{name} degraded",
                        "fallback_used": status == "fallback",
                        "fields": list(fields),
                    }
                )
                if status == "fallback":
                    missing_fields.extend(fields)

        try:
            sentiment_analyzer = self._get_sentiment_analyzer()
            index_klines = []
            try:
                index_klines = await db.get_klines("sh000001", limit=60)
            except Exception:
                index_klines = []
            if not index_klines:
                try:
                    index_klines = await self._load_index_klines("000001", limit=60)
                except Exception:
                    index_klines = []
            if not index_klines:
                raise ValueError("index klines empty")
            breadth = None
            try:
                breadth = await db.get_limit_up_stats()
            except Exception:
                pass
            fg = sentiment_analyzer.calculate_fear_greed_index(index_klines, breadth)
            snapshot["fear_greed_index"] = fg.get("index", 50)
            snapshot["fg_level"] = fg.get("level", "neutral")
            snapshot["fg_components"] = fg.get("components", {})
            record_source(
                "fear_greed",
                "success",
                ["fear_greed_index", "fg_level", "fg_components"],
            )
        except Exception as exc:
            logger.warning("DataCollector: fear_greed failed: %s", exc)
            fallback_details: Dict[str, Any] = {}
            reused_snapshot = await self._load_recent_successful_fear_greed_snapshot(
                db,
                current_date=snapshot.get("date"),
            )
            if reused_snapshot is not None:
                snapshot["fear_greed_index"] = reused_snapshot["fear_greed_index"]
                snapshot["fg_level"] = reused_snapshot["fg_level"]
                snapshot["fg_components"] = reused_snapshot["fg_components"]
                reused_date = reused_snapshot.get("snapshot_date")
                if reused_date:
                    fallback_details["reused_snapshot_date"] = reused_date
                fallback_details["reuse_mode"] = "recent_successful_snapshot"
            else:
                snapshot["fear_greed_index"] = 50
                snapshot["fg_level"] = "neutral"
                snapshot["fg_components"] = {}
                fallback_details["reuse_mode"] = "neutral_default"
            record_source(
                "fear_greed",
                "fallback",
                ["fear_greed_index", "fg_level", "fg_components"],
                reason=f"fear_greed failed: {exc}",
                details=fallback_details,
            )

        factor_ic: Dict[str, float] = {}
        factor_ic_trend: Dict[str, str] = {}
        factor_ic_failures: List[dict] = []
        for fname in FACTORY_RESEARCH_FACTORS:
            try:
                rows = await db.get_factor_ic_history(fname, "20", 20)
                ics = [row.get("ic_value", 0) for row in (rows or []) if row.get("ic_value") is not None]
                if ics:
                    factor_ic[fname] = ics[0]
                    if len(ics) >= 10:
                        avg5 = np.mean(ics[:5])
                        avg10 = np.mean(ics[5:10])
                        delta = avg5 - avg10
                        factor_ic_trend[fname] = (
                            "rising" if delta > 0.005 else ("falling" if delta < -0.005 else "flat")
                        )
                    else:
                        factor_ic_trend[fname] = "flat"
            except Exception as exc:
                factor_ic_failures.append({"factor": fname, "reason": str(exc)})
        snapshot["factor_ic"] = factor_ic
        snapshot["factor_ic_trend"] = factor_ic_trend
        factor_ic_fields = ["factor_ic", "factor_ic_trend"]
        if factor_ic_failures and factor_ic:
            record_source(
                "factor_ic",
                "partial",
                factor_ic_fields,
                reason=f"{len(factor_ic_failures)} 个因子 IC 拉取失败",
                details={"failed_factors": factor_ic_failures},
            )
        elif factor_ic_failures:
            record_source(
                "factor_ic",
                "fallback",
                factor_ic_fields,
                reason=f"factor_ic failed: {len(factor_ic_failures)} 个因子拉取失败",
                details={"failed_factors": factor_ic_failures},
            )
        elif factor_ic:
            record_source("factor_ic", "success", factor_ic_fields)
        else:
            record_source(
                "factor_ic",
                "fallback",
                factor_ic_fields,
                reason="factor_ic history empty",
                details={"expected_factors": FACTORY_RESEARCH_FACTORS},
            )

        event_runtime_mode = resolve_event_runtime_mode()
        event_refresh_attempted = False
        event_refresh_summary = {
            "engine": "local_db_rule_v1",
            "mode": event_runtime_mode,
            "refresh_attempted": False,
        }
        if event_runtime_mode == "refresh":
            event_refresh_attempted = True
            event_refresh_summary["refresh_attempted"] = True
            try:
                get_event_engine = getattr(factory_pkg, "get_local_event_engine", None)
                if callable(get_event_engine):
                    event_refresh_summary = {
                        **event_refresh_summary,
                        **dict(await get_event_engine().refresh(db, snapshot) or {}),
                    }
                else:
                    event_refresh_summary.update({
                        "enabled": False,
                        "error": "event engine unavailable",
                    })
            except Exception as exc:
                logger.warning("DataCollector: local event engine refresh failed: %s", exc)
                event_refresh_summary.update({"enabled": False, "error": str(exc)})
        else:
            event_refresh_summary.update({
                "enabled": False,
                "read_only": True,
                "reason": "event runtime mode is readonly",
            })

        snapshot["north_fund_3d_net"] = 0.0
        snapshot["margin_5d_change_pct"] = 0.0
        snapshot.setdefault("hot_sectors", [])
        snapshot.setdefault("cold_sectors", [])

        north_fund_ok = False
        try:
            north_summary = None
            getter = getattr(db, "get_recent_north_fund_summary", None)
            if callable(getter):
                north_summary = getter(days=3, sample_limit=5)
                if hasattr(north_summary, "__await__"):
                    north_summary = await north_summary
            if isinstance(north_summary, dict) and int(north_summary.get("sample_count") or 0) >= 3:
                snapshot["north_fund_3d_net"] = round(float(north_summary.get("total_net") or 0.0), 2)
                north_fund_ok = True
        except Exception as exc:
            logger.debug("DataCollector: north_fund summary failed: %s", exc)
        if north_fund_ok:
            record_source(
                "north_fund",
                "success",
                ["north_fund_3d_net"],
                details={"mode": "db_method", "summary": north_summary},
            )
        else:
            record_source(
                "north_fund",
                "fallback",
                ["north_fund_3d_net"],
                reason="north_fund db summary unavailable",
            )

        local_internals = dict((event_refresh_summary or {}).get("market_internals") or {})
        if not local_internals:
            try:
                latest_internal = None
                getter = getattr(db, "get_factory_market_internal_snapshot", None)
                if callable(getter):
                    latest_internal = getter(snapshot_date=snapshot.get("date"))
                    if hasattr(latest_internal, "__await__"):
                        latest_internal = await latest_internal
                    if latest_internal is None:
                        latest_internal = getter()
                        if hasattr(latest_internal, "__await__"):
                            latest_internal = await latest_internal
                if isinstance(latest_internal, dict):
                    local_internals = dict(latest_internal)
            except Exception as exc:
                logger.debug("DataCollector: factory market internals fallback failed: %s", exc)
        margin_proxy = local_internals.get("margin_proxy_5d_change_pct")
        if margin_proxy is not None:
            snapshot["margin_5d_change_pct"] = round(float(margin_proxy or 0.0), 2)
            record_source(
                "margin_data",
                "success",
                ["margin_5d_change_pct"],
                details={
                    "mode": "local_proxy",
                    "engine": (event_refresh_summary or {}).get("engine"),
                    "market_internals": local_internals,
                },
            )
        else:
            margin_summary = None
            try:
                getter = getattr(db, "get_recent_margin_summary", None)
                if callable(getter):
                    margin_summary = getter(days=10, sample_limit=10, change_lookback_days=5)
                    if hasattr(margin_summary, "__await__"):
                        margin_summary = await margin_summary
            except Exception as exc:
                logger.debug("DataCollector: margin summary failed: %s", exc)
            if isinstance(margin_summary, dict) and margin_summary.get("margin_balance_change_5d") is not None:
                snapshot["margin_5d_change_pct"] = round(
                    float(margin_summary.get("margin_balance_change_5d") or 0.0),
                    2,
                )
                record_source(
                    "margin_data",
                    "success",
                    ["margin_5d_change_pct"],
                    details={"mode": "db_method", "summary": margin_summary},
                )
            else:
                record_source(
                    "margin_data",
                    "fallback",
                    ["margin_5d_change_pct"],
                    reason="margin proxy unavailable",
                )

        hot_sectors = [
            str(item).strip()
            for item in list(snapshot.get("hot_sectors") or local_internals.get("hot_sectors") or [])
            if str(item).strip()
        ]
        cold_sectors = [
            str(item).strip()
            for item in list(snapshot.get("cold_sectors") or local_internals.get("cold_sectors") or [])
            if str(item).strip()
        ]
        snapshot["hot_sectors"] = hot_sectors[:5]
        snapshot["cold_sectors"] = cold_sectors[:5]
        if snapshot["hot_sectors"] or snapshot["cold_sectors"]:
            record_source(
                "sector_fund_flow",
                "success",
                ["hot_sectors", "cold_sectors"],
                details={
                    "mode": "local_rotation",
                    "engine": (event_refresh_summary or {}).get("engine"),
                    "market_internals": local_internals,
                },
            )
        else:
            record_source(
                "sector_fund_flow",
                "fallback",
                ["hot_sectors", "cold_sectors"],
                reason="local sector rotation unavailable",
            )

        snapshot["event_driven"] = {
            "enabled": False,
            "event_count": 0,
            "active_theme_count": 0,
            "signal_count": 0,
            "tasks_ready_count": 0,
            "events": [],
        }
        event_driven, event_status, event_reason, event_details = await self._collect_event_driven_snapshot(db)
        snapshot["event_driven"] = event_driven
        event_details = {
            **dict(event_details or {}),
            "runtime_mode": event_runtime_mode,
            "refresh_attempted": event_refresh_attempted,
            "refresh": dict(event_refresh_summary or {}),
        }
        snapshot["event_runtime"] = {
            "mode": event_runtime_mode,
            "refresh_attempted": event_refresh_attempted,
            "read_only": event_runtime_mode != "refresh",
            "refresh": dict(event_refresh_summary or {}),
        }
        record_source("event_driven", event_status, ["event_driven"], reason=event_reason, details=event_details)

        try:
            counts = await db.count_strategies_by_type("listed")
            snapshot["category_counts"] = counts
            snapshot["listed_count"] = sum(counts.values())
            incubating = await db.count_strategies_by_type("incubating")
            snapshot["incubating_count"] = sum(incubating.values())
            record_source(
                "strategy_population",
                "success",
                ["category_counts", "listed_count", "incubating_count"],
            )
        except Exception:
            snapshot["category_counts"] = {}
            snapshot["listed_count"] = 0
            snapshot["incubating_count"] = 0
            record_source(
                "strategy_population",
                "fallback",
                ["category_counts", "listed_count", "incubating_count"],
                reason="strategy_population failed",
            )

        try:
            parameter_distribution = await self._collect_parameter_distribution_snapshot(db)
            snapshot["parameter_distribution_samples"] = list(parameter_distribution.get("items") or [])
            snapshot["parameter_distribution_summary"] = dict(parameter_distribution.get("summary") or {})
        except Exception as exc:
            logger.warning("DataCollector: parameter distribution snapshot failed: %s", exc)
            snapshot["parameter_distribution_samples"] = []
            snapshot["parameter_distribution_summary"] = {
                "eligible_sample_count": 0,
                "factory_strategy_count": 0,
                "strategy_type_counts": {},
                "source": "failed",
                "error": str(exc),
            }

        self._finalize_snapshot_contract(
            snapshot,
            sources,
            failure_reasons,
            missing_fields,
            asof_time=collected_at,
        )

        try:
            await db.save_daily_snapshot(date.today(), snapshot)
        except Exception as exc:
            logger.warning("DataCollector: save snapshot failed: %s", exc)

        return snapshot


__all__ = ["DataCollector"]
