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
        if normalized_status == "optional_unavailable":
            flags.append("optional_unavailable")
            if stale_after_sec is not None and float(freshness_sec or 0.0) > float(stale_after_sec):
                flags.append("stale")
            return cls._ordered_flags(flags)
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
        normalized_status = str(status or "unknown").strip().lower() or "unknown"
        optional_unavailable = normalized_status == "optional_unavailable"
        payload = {
            "status": normalized_status,
            "source": str(source_name or "strategy_factory.collector"),
            "asof_time": resolved_asof_time,
            "freshness_sec": freshness_sec,
            "quality_flags": cls._build_quality_flags(
                status=normalized_status,
                freshness_sec=freshness_sec,
            ),
            "fields": list(fields),
            "degraded": normalized_status != "success" and not optional_unavailable,
            "optional": optional_unavailable,
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

    @staticmethod
    async def _gather_bounded_calls(
        call_factories: List[Any],
        *,
        concurrency: int = 6,
    ) -> List[Any]:
        factories = list(call_factories or [])
        if not factories:
            return []
        limit = max(1, min(int(concurrency or 1), len(factories)))
        semaphore = asyncio.Semaphore(limit)
        results: List[Any] = [None] * len(factories)

        async def _runner(index: int, factory) -> None:
            async with semaphore:
                try:
                    value = factory()
                    if hasattr(value, "__await__"):
                        value = await value
                    results[index] = value
                except Exception as exc:
                    results[index] = exc

        await asyncio.gather(*(_runner(index, factory) for index, factory in enumerate(factories)))
        return results

    async def _collect_parameter_distribution_snapshot(
        self,
        db,
        *,
        limit_per_status: int = 120,
        max_samples: int = 96,
        query_concurrency: int = 6,
    ) -> dict:
        list_strategies = getattr(db, "list_strategies", None)
        get_signal_stats = getattr(db, "get_signal_stats", None)
        if not callable(list_strategies) or not callable(get_signal_stats):
            return {
                "items": [],
                "summary": {
                    "sample_count": 0,
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
                    "sample_count": 0,
                    "eligible_sample_count": 0,
                    "factory_strategy_count": 0,
                    "strategy_type_counts": {},
                    "source": "empty",
                },
            }

        strategy_ids = [str(strategy.get("id") or "").strip() for strategy in strategies]
        quality_reports = await self._gather_bounded_calls(
            [
                (lambda strategy_id=strategy_id: self._load_latest_quality_report(db, strategy_id))
                for strategy_id in strategy_ids
            ],
            concurrency=query_concurrency,
        )
        signal_stats_rows = await self._gather_bounded_calls(
            [
                (lambda strategy_id=strategy_id: get_signal_stats(strategy_id))
                for strategy_id in strategy_ids
            ],
            concurrency=query_concurrency,
        )

        items: list[dict[str, Any]] = []
        strategy_type_counts: dict[str, int] = {}
        validation_grade_distribution: dict[str, int] = {}
        promotion_ready_count = 0
        quality_passed_count = 0
        quality_query_error_count = 0
        signal_query_error_count = 0
        for strategy, quality_report, signal_stats in zip(strategies, quality_reports, signal_stats_rows):
            if isinstance(quality_report, Exception):
                quality_query_error_count += 1
                quality_report = {}
            if isinstance(signal_stats, Exception):
                signal_query_error_count += 1
                signal_stats = {}
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
        selected_items = items[:max_samples]
        return {
            "items": selected_items,
            "summary": {
                "sample_count": len(selected_items),
                "eligible_sample_count": len(selected_items),
                "factory_strategy_count": len(strategies),
                "strategy_type_counts": strategy_type_counts,
                "validation_grade_distribution": validation_grade_distribution,
                "promotion_ready_count": promotion_ready_count,
                "quality_passed_count": quality_passed_count,
                "quality_query_error_count": quality_query_error_count,
                "signal_query_error_count": signal_query_error_count,
                "query_concurrency": max(1, int(query_concurrency or 1)),
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
        optional_unavailable_sources: List[str] = []
        required_source_count = 0
        required_available_count = 0
        for name, item in sources.items():
            status = str(item.get("status") or "unknown").strip().lower() or "unknown"
            source_status_counts[status] = source_status_counts.get(status, 0) + 1
            optional_unavailable = status == "optional_unavailable"
            if optional_unavailable:
                optional_unavailable_sources.append(name)
                continue
            required_source_count += 1
            if status == "success":
                required_available_count += 1
            else:
                degraded_sources.append(name)
            if status == "fallback":
                missing_sources.append(name)

        total_sources = len(sources)
        available_sources = required_available_count
        completion_ratio = (
            round(required_available_count / required_source_count, 2)
            if required_source_count
            else 1.0
        )
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
            "required_sources": required_source_count,
            "required_available_sources": required_available_count,
            "degraded_sources": sorted(degraded_sources),
            "missing_sources": sorted(missing_sources),
            "optional_unavailable_sources": sorted(optional_unavailable_sources),
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
