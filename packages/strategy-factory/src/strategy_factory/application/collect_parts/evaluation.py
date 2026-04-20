
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
