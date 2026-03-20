"""策略工厂数据快照采集。"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import numpy as np

from ..domain.constants import FACTORY_RESEARCH_FACTORS
from ..infrastructure.mcp_services import get_sentiment_analyzer
from .utils import get_strategy_factory_package

logger = logging.getLogger(__name__)


class DataCollector:
    """汇总每日市场数据快照。"""

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
        return text[: max(0, limit - 1)] + "..."

    @staticmethod
    def _normalize_codes(values: Any, limit: int = 5) -> List[str]:
        codes: List[str] = []
        seen: set[str] = set()

        def visit(value: Any) -> None:
            if value is None:
                return
            if isinstance(value, dict):
                for key in ("code", "symbol", "stock_code"):
                    if value.get(key) is not None:
                        visit(value.get(key))
                for key in ("codes", "symbols", "stock_codes", "target_symbols"):
                    if value.get(key) is not None:
                        visit(value.get(key))
                return
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    visit(item)
                return
            raw = str(value or "").strip()
            if not raw:
                return
            if any(sep in raw for sep in [",", ";", "|", "\n", "\t", " "]):
                normalized = (
                    raw.replace(";", ",")
                    .replace("|", ",")
                    .replace("\n", ",")
                    .replace("\t", ",")
                    .replace(" ", ",")
                )
                for part in normalized.split(","):
                    visit(part)
                return
            code = raw.split(".")[0].strip()
            if not code or code in seen:
                return
            seen.add(code)
            codes.append(code)

        visit(values)
        return codes[: max(1, min(int(limit or 5), 12))]

    @classmethod
    def _event_strategy_preferences(
        cls,
        direction: str,
        theme_name: str,
        opportunity_hint: str,
    ) -> List[str]:
        lowered = str(theme_name or "").lower()
        direction = str(direction or "neutral").strip().lower() or "neutral"
        if direction in {"negative", "bearish", "cost_up"}:
            return ["rsi", "quality_factor", "value_factor"]
        if any(
            token in lowered
            for token in ["quality", "roe", "dividend", "cashflow", "防御", "高股息"]
        ):
            return ["quality_factor", "value_factor", "ma_cross"]
        if any(
            token in lowered
            for token in ["芯片", "半导体", "算力", "机器人", "ai", "军工", "油", "gas", "资源", "航运"]
        ):
            return ["momentum", "ma_cross", "growth_factor"]
        if opportunity_hint == "factor_acceleration":
            return ["growth_factor", "momentum", "ma_cross"]
        return ["ma_cross", "momentum", "quality_factor"]

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
                target_symbols = [
                    item.get("symbol") for item in signal_values if item.get("symbol")
                ][:5]
                opportunity_hint = (
                    "factor_acceleration"
                    if "factor" in str(theme_code or "").lower()
                    else "sector_breakout"
                )
                theme_payload = {
                    "theme_code": theme_code,
                    "theme_name": theme.get("theme_name") or theme_code,
                    "direction": theme.get("direction")
                    or str(cluster.get("direction") or "neutral").strip().lower()
                    or "neutral",
                    "horizon": str(cluster.get("horizon") or "swing_5_20d").strip()
                    or "swing_5_20d",
                    "signal_count": len(signal_values),
                    "target_symbols": target_symbols,
                    "strategy_preferences": cls._event_strategy_preferences(
                        direction=theme.get("direction") or cluster.get("direction") or "neutral",
                        theme_name=theme.get("theme_name") or theme_code,
                        opportunity_hint=opportunity_hint,
                    ),
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
            sentiment_analyzer = get_sentiment_analyzer()
            index_klines = []
            try:
                index_klines = await db.get_klines("000001", limit=60)
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
            snapshot["fear_greed_index"] = 50
            snapshot["fg_level"] = "neutral"
            snapshot["fg_components"] = {}
            record_source(
                "fear_greed",
                "fallback",
                ["fear_greed_index", "fg_level", "fg_components"],
                reason=f"fear_greed failed: {exc}",
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

        event_refresh_summary = None
        try:
            get_event_engine = getattr(factory_pkg, "get_local_event_engine", None)
            if callable(get_event_engine):
                event_refresh_summary = await get_event_engine().refresh(db, snapshot)
        except Exception as exc:
            logger.warning("DataCollector: local event engine refresh failed: %s", exc)
            event_refresh_summary = {"engine": "local_db_rule_v1", "enabled": False, "error": str(exc)}

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
        if event_refresh_summary is not None:
            event_details = {**dict(event_details or {}), "refresh": event_refresh_summary}
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
