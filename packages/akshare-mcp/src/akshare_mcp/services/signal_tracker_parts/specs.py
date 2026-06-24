

class SignalTracker:
    """Asyncio-based daily signal tracking scheduler."""

    def __init__(self, run_time: time = time(18, 30)):
        self.run_time = run_time
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.last_run: Optional[datetime] = None
        self.last_result: Optional[dict] = None

    def start(self):
        if self._running:
            logger.warning("SignalTracker already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="signal-tracker")
        logger.info("SignalTracker started, daily run at %s", self.run_time)

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("SignalTracker stopped")

    async def shutdown(self, grace_sec: float = 5.0):
        self._running = False
        task = self._task
        self._task = None
        if task is None:
            logger.info("SignalTracker stopped")
            return
        if not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=max(0.0, grace_sec))
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        else:
            with suppress(asyncio.CancelledError):
                await task
        logger.info("SignalTracker stopped")

    async def _loop(self):
        while self._running:
            try:
                now = datetime.now()
                target = datetime.combine(now.date(), self.run_time)
                if target <= now:
                    target += timedelta(days=1)
                wait_seconds = (target - now).total_seconds()
                logger.info("SignalTracker: next run in %.0f seconds at %s", wait_seconds, target)
                await asyncio.sleep(wait_seconds)

                if self._running:
                    await self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("SignalTracker loop error: %s", e, exc_info=True)
                await asyncio.sleep(60)

    @staticmethod
    def _merge_unique_strategies(*groups: list[dict]) -> list[dict]:
        merged: list[dict] = []
        seen: set[str] = set()
        for group in groups:
            for strategy in list(group or []):
                strategy_id = str((strategy or {}).get("id") or "").strip()
                if not strategy_id or strategy_id in seen:
                    continue
                seen.add(strategy_id)
                merged.append(strategy)
        return merged

    async def _load_runtime_submitted_strategies(self, db, *, limit: int = 200) -> list[dict]:
        if not hasattr(db, "list_strategies"):
            return []
        rows = await db.list_strategies("submitted", limit=limit)
        if not rows:
            return []
        get_quality_report = getattr(db, "get_strategy_quality_report", None)
        eligible: list[dict] = []
        for row in list(rows or []):
            if await self._is_runtime_submitted_strategy(
                db,
                row,
                get_quality_report=get_quality_report,
            ):
                eligible.append(row)
        return eligible

    async def _is_runtime_submitted_strategy(self, db, strategy: dict, *, get_quality_report=None) -> bool:
        strategy_id = str((strategy or {}).get("id") or "").strip()
        if not strategy_id:
            return False
        report = None
        if callable(get_quality_report):
            try:
                report = await get_quality_report(strategy_id, "submission")
            except Exception:
                report = None
        summary = dict((report or {}).get("summary") or {})
        lane = str(
            summary.get("submission_lane")
            or (report or {}).get("submission_lane")
            or ""
        ).strip().lower()
        if lane in {"observe_incubation", "live_ready_review"}:
            return True
        for field_name in (
            "paper_lane_ready",
            "live_review_ready",
            "paper_account_id",
            "live_review_account_id",
        ):
            if summary.get(field_name) or (report or {}).get(field_name):
                return True
        params = dict((strategy or {}).get("params") or {})
        incubation_budget = dict(params.get("incubation_budget") or {})
        return str(incubation_budget.get("track") or "").strip().lower() in {
            "observe_incubation",
            "live_ready_review",
        }

    async def _load_runtime_observation_strategies(self, db, *, limit: int = 200) -> list[dict]:
        """Load paper/observe strategies for signal generation and paper execution."""
        candidates: list[dict] = []
        for method_name in (
            "list_active_paper_observation_strategies",
            "list_paper_observation_strategies",
        ):
            method = getattr(db, method_name, None)
            if not callable(method):
                continue
            try:
                rows = await method(limit=limit)
            except TypeError:
                try:
                    rows = await method()
                except Exception as exc:
                    logger.warning("SignalTracker: %s failed: %s", method_name, exc)
                    continue
            except Exception as exc:
                logger.warning("SignalTracker: %s failed: %s", method_name, exc)
                continue
            candidates.extend(list(rows or []))
        return self._merge_unique_strategies(candidates)

    @staticmethod
    def _phase_timeout_seconds(phase_name: str) -> float:
        specific = f"STRATEGY_SIGNAL_TRACKER_PHASE_{phase_name.upper()}_TIMEOUT_SEC"
        raw = os.getenv(specific) or os.getenv("STRATEGY_SIGNAL_TRACKER_PHASE_TIMEOUT_SEC") or "45"
        try:
            value = float(str(raw).strip())
        except Exception:
            value = 45.0
        return max(5.0, min(value, 300.0))

    @staticmethod
    def _resolve_strategy_universe(strategy: dict, default_universe: list[str]) -> list[str]:
        payload = dict(strategy or {})
        params = dict(payload.get("params") or {})
        ordered: list[str] = []
        seen: set[str] = set()
        filter_payloads: list[dict[str, Any]] = []

        def _push(value: Any) -> None:
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    _push(item)
                return
            if isinstance(value, dict):
                for key in ("symbols", "target_symbols", "symbol", "stock_code", "code"):
                    if key in value:
                        _push(value.get(key))
                return
            text = str(value or "").strip()
            if not text or text in seen:
                return
            seen.add(text)
            ordered.append(text)

        def _collect_codes(value: Any) -> list[str]:
            codes: list[str] = []
            code_seen: set[str] = set()

            def _visit(item: Any) -> None:
                if isinstance(item, (list, tuple, set)):
                    for entry in item:
                        _visit(entry)
                    return
                if isinstance(item, dict):
                    for key in (
                        "prioritized_symbols",
                        "preferred_symbols",
                        "universe_priority_symbols",
                        "excluded_symbols",
                        "symbols",
                        "target_symbols",
                        "symbol",
                        "stock_code",
                        "code",
                    ):
                        if key in item:
                            _visit(item.get(key))
                    return
                text = str(item or "").strip()
                if not text or text in code_seen:
                    return
                code_seen.add(text)
                codes.append(text)

            _visit(value)
            return codes

        for candidate in (
            payload.get("target_symbols"),
            payload.get("stock_pool"),
            payload.get("research_task"),
            params.get("target_symbols"),
            params.get("stock_pool"),
            params.get("research_task"),
            dict(params.get("dsl") or {}).get("metadata"),
        ):
            _push(candidate)
        for candidate in (
            payload.get("stock_pool"),
            payload.get("research_task"),
            params.get("stock_pool"),
            params.get("research_task"),
            dict(params.get("dsl") or {}).get("metadata"),
        ):
            if isinstance(candidate, dict):
                filters = dict(candidate.get("filters") or {})
                if filters:
                    filter_payloads.append(filters)

        prioritized_symbols = _collect_codes(
            [
                params.get("prioritized_symbols"),
                params.get("preferred_symbols"),
                params.get("universe_priority_symbols"),
                [payload_.get("prioritized_symbols") for payload_ in filter_payloads],
                [payload_.get("preferred_symbols") for payload_ in filter_payloads],
                [payload_.get("universe_priority_symbols") for payload_ in filter_payloads],
            ]
        )
        excluded_symbols = set(
            _collect_codes(
                [
                    params.get("excluded_symbols"),
                    [payload_.get("excluded_symbols") for payload_ in filter_payloads],
                ]
            )
        )

        budget_candidates = [
            params.get("max_active_symbols"),
            *[payload_.get("max_active_symbols") for payload_ in filter_payloads],
        ]
        max_active_symbols = 0
        for raw_budget in budget_candidates:
            try:
                max_active_symbols = max(max_active_symbols, int(raw_budget or 0))
            except Exception:
                continue

        resolved = [code for code in ordered if code not in excluded_symbols]
        if prioritized_symbols:
            priority_order = [code for code in prioritized_symbols if code in resolved]
            remaining = [code for code in resolved if code not in set(priority_order)]
            resolved = [*priority_order, *remaining]
        if max_active_symbols > 0:
            resolved = resolved[:max_active_symbols]
        return resolved or list(default_universe or [])

    @staticmethod
    def _get_default_universe() -> list[str]:
        from .factor_scheduler import DEFAULT_UNIVERSE

        return list(DEFAULT_UNIVERSE)

    @staticmethod
    def _build_signal_tracking_artifacts(instance: Any, klines: list[dict[str, Any]], *, execution_semantic_mode: str) -> dict[str, Any]:
        return _build_signal_tracking_artifacts(
            instance,
            klines,
            execution_semantic_mode=execution_semantic_mode,
        )

    @staticmethod
    async def _load_executable_strategies_with_fallback(
        db,
        *,
        limit: int = 500,
        use_contract: bool = True,
    ) -> list[dict]:
        from .execution_universe_adapter import load_executable_strategies_with_fallback

        return await load_executable_strategies_with_fallback(
            db,
            limit=limit,
            use_contract=use_contract,
        )

    @staticmethod
    def _get_runtime_control_service():
        from .runtime_control import get_strategy_runtime_control_service

        return get_strategy_runtime_control_service()

    @staticmethod
    def _get_runtime_risk_service():
        from .runtime_risk import get_strategy_runtime_risk_service

        return get_strategy_runtime_risk_service()

    @staticmethod
    async def _run_lifecycle_scan(db):
        from ..tools.managers.strategy_manager import _lifecycle_scan

        return await _lifecycle_scan(db)

    @staticmethod
    def _get_vector_governance_service():
        from .vector_governance import get_strategy_vector_governance_service

        return get_strategy_vector_governance_service()

    @staticmethod
    def _get_domain_projection_service():
        from .domain_projection import get_strategy_domain_projection_service

        return get_strategy_domain_projection_service()

    async def run_once(self):
        """Compat entrypoint delegating canonical orchestration to strategy-factory."""
        from strategy_factory.runtime.signal_tracker import build_signal_tracker_runtime

        runtime = build_signal_tracker_runtime(support=self, run_time=self.run_time)
        return await runtime.run_once()

    async def backfill_forward_returns(
        self,
        db=None,
        *,
        forward_days_list: Optional[List[int]] = None,
        batch_limit: int = FORWARD_RETURN_BATCH_LIMIT,
        max_rounds: int = FORWARD_RETURN_MAX_ROUNDS,
    ) -> dict:
        """批量回填历史前向收益，支持在日常 Phase B 中复用。"""
        from ..storage import get_db

        database = db or get_db()
        windows = [int(item) for item in list(forward_days_list or FORWARD_DAYS) if int(item) > 0]
        per_window: dict[str, Any] = {}
        total_computed = 0

        for forward_days in windows:
            window_key = f"{forward_days}D"
            rounds = 0
            computed = 0
            pending_seen = 0
            cursor_signal_date: Optional[date] = None
            cursor_id = 0
            truncated = False

            while rounds < max(1, int(max_rounds or 1)):
                rounds += 1
                pending = await database.get_pending_forward_returns(
                    forward_days,
                    limit=batch_limit,
                    after_signal_date=cursor_signal_date,
                    after_id=cursor_id,
                )
                if not pending:
                    break
                pending_seen += len(pending)
                saved = await self._compute_forward_returns_batch(
                    database,
                    pending,
                    forward_days=forward_days,
                )
                computed += saved
                total_computed += saved
                last_record = dict(pending[-1] or {})
                cursor_signal_date = self._coerce_trade_date(
                    last_record.get("effective_signal_date") or last_record.get("signal_date")
                )
                cursor_id = int(last_record.get("id") or 0)
            else:
                truncated = True
                logger.warning(
                    "SignalTracker: forward-return backfill truncated for %s after %d rounds",
                    window_key,
                    rounds,
                )

            per_window[window_key] = {
                "rounds": rounds,
                "pending_seen": pending_seen,
                "computed": computed,
                "stalled": truncated,
            }

        return {
            "computed": total_computed,
            "batch_limit": max(1, int(batch_limit or FORWARD_RETURN_BATCH_LIMIT)),
            "max_rounds": max(1, int(max_rounds or FORWARD_RETURN_MAX_ROUNDS)),
            "windows": per_window,
        }

    async def _compute_forward_returns_batch(
        self,
        db,
        pending: List[dict],
        *,
        forward_days: int,
    ) -> int:
        if not pending:
            return 0

        pending_by_code: Dict[str, List[dict]] = {}
        for record in list(pending or []):
            code = str(record.get("code") or "").strip()
            if not code:
                continue
            pending_by_code.setdefault(code, []).append(record)

        rows_to_save: list[dict[str, Any]] = []
        for code, records in pending_by_code.items():
            base_dates = [self._resolve_signal_base_date(item) for item in records]
            base_dates = [item for item in base_dates if item is not None]
            if not base_dates:
                continue
            earliest_signal_date = min(base_dates)
            klines = await self._get_klines_with_fallback(
                db,
                code,
                start_date=earliest_signal_date,
                limit=None,
                allow_data_source_fallback=True,
                required_base_dates=base_dates,
                forward_days=forward_days,
            )
            close_series = self._build_close_series(klines)
            if not close_series:
                continue
            index_by_date = {trade_date: idx for idx, (trade_date, _close) in enumerate(close_series)}
            closes = [close for _trade_date, close in close_series]
            for record in records:
                signal_date = self._resolve_signal_base_date(record)
                if signal_date is None:
                    continue
                base_index = self._resolve_forward_base_index(
                    close_series,
                    signal_date,
                    index_by_date=index_by_date,
                )
                if base_index is None:
                    continue
                future_index = base_index + int(forward_days)
                if future_index >= len(closes):
                    continue
                base_close = float(closes[base_index] or 0.0)
                future_close = float(closes[future_index] or 0.0)
                if base_close <= 0:
                    continue
                rows_to_save.append(
                    {
                        "signal_id": int(record["id"]),
                        "forward_days": int(forward_days),
                        "actual_return": (future_close - base_close) / base_close,
                    }
                )

        if not rows_to_save:
            return 0

        if hasattr(db, "save_forward_returns_batch"):
            return int(await db.save_forward_returns_batch(rows_to_save) or 0)

        saved = 0
        for row in rows_to_save:
            await db.save_forward_returns(
                row["signal_id"],
                row["forward_days"],
                row["actual_return"],
            )
            saved += 1
        return saved

    @staticmethod
    def _decode_signal_metadata(record: dict[str, Any]) -> dict[str, Any]:
        raw = dict(record or {}).get("signal_metadata")
        if isinstance(raw, dict):
            return dict(raw)
        if raw in (None, "", [], {}):
            return {}
        try:
            import json

            parsed = json.loads(str(raw))
            return dict(parsed or {}) if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _resolve_signal_record_date(self, signal_row: dict[str, Any]) -> Optional[date]:
        metadata = dict((signal_row or {}).get("signal_metadata") or {})
        for key in ("latest_bar_date", "latest_nonzero_signal_date", "latest_event_date"):
            resolved = self._coerce_trade_date(metadata.get(key))
            if resolved is not None:
                return resolved
        return self._coerce_trade_date((signal_row or {}).get("signal_date"))

    def _resolve_signal_base_date(self, record: dict[str, Any]) -> Optional[date]:
        metadata = self._decode_signal_metadata(record)
        for key in ("latest_bar_date", "latest_nonzero_signal_date", "latest_event_date"):
            resolved = self._coerce_trade_date(metadata.get(key))
            if resolved is not None:
                return resolved
        return self._coerce_trade_date((record or {}).get("signal_date"))

    @staticmethod
    def _coerce_trade_date(value: Any) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10])
        except Exception:
            return None

    def _build_close_series(self, klines: List[dict]) -> List[tuple[date, float]]:
        close_by_date: dict[date, float] = {}
        for kline in list(klines or []):
            trade_date = self._coerce_trade_date(kline.get("date") or kline.get("time"))
            if trade_date is None:
                continue
            try:
                close = float(kline.get("close") or 0.0)
            except Exception:
                continue
            if close <= 0:
                continue
            close_by_date[trade_date] = close
        return sorted(close_by_date.items(), key=lambda item: item[0])

    @staticmethod
    def _resolve_forward_base_index(
        close_series: List[tuple[date, float]],
        base_date: date,
        *,
        index_by_date: Optional[dict[date, int]] = None,
    ) -> Optional[int]:
        if not close_series or base_date is None:
            return None
        index_map = index_by_date or {
            trade_date: idx for idx, (trade_date, _close) in enumerate(close_series)
        }
        exact_index = index_map.get(base_date)
        if exact_index is not None:
            return exact_index
        previous_index: Optional[int] = None
        for idx, (trade_date, _close) in enumerate(close_series):
            if trade_date > base_date:
                break
            previous_index = idx
        return previous_index

    def _has_forward_coverage(
        self,
        close_series: List[tuple[date, float]],
        *,
        required_base_dates: Optional[List[date]] = None,
        forward_days: Optional[int] = None,
    ) -> bool:
        if not close_series:
            return False
        base_dates = [item for item in list(required_base_dates or []) if item is not None]
        if not base_dates:
            return True
        horizon = max(int(forward_days or 0), 0)
        index_by_date = {trade_date: idx for idx, (trade_date, _close) in enumerate(close_series)}
        for base_date in base_dates:
            base_index = self._resolve_forward_base_index(
                close_series,
                base_date,
                index_by_date=index_by_date,
            )
            if base_index is None:
                return False
            if horizon > 0 and base_index + horizon >= len(close_series):
                return False
        return True

    @staticmethod
    def _normalize_provider_klines(code: str, rows: list[dict]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for row in list(rows or []):
            if not isinstance(row, dict):
                continue
            payload = dict(row)
            payload.setdefault("code", code)
            if not payload.get("date") and payload.get("time"):
                payload["date"] = str(payload.get("time"))[:10]
            if not payload.get("date") or payload.get("close") in (None, ""):
                continue
            normalized.append(payload)
        return normalized

    async def _fetch_provider_klines(self, code: str, *, limit: int) -> list[dict[str, Any]]:
        providers: list[tuple[str, Any]] = []
        try:
            from akshare_mcp.services.data_sync import data_sync_service

            providers.append(
                (
                    "data_sync_service",
                    lambda: data_sync_service.get_kline_with_cache(
                        code,
                        "daily",
                        "",
                        "",
                        limit,
                        use_cache=True,
                    ),
                )
            )
        except Exception:
            pass

        for provider_name, loader in providers:
            try:
                payload = await loader()
            except Exception as exc:
                logger.warning(
                    "SignalTracker: provider kline refresh failed for %s via %s: %s",
                    code,
                    provider_name,
                    exc,
                )
                continue
            if isinstance(payload, dict):
                rows = payload.get("data") or payload.get("rows") or []
            else:
                rows = payload
            normalized = self._normalize_provider_klines(code, list(rows or []))
            if normalized:
                return normalized
        return []

    async def _get_klines_with_fallback(
        self,
        db,
        code: str,
        limit: Optional[int] = 200,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        allow_data_source_fallback: bool = False,
        required_base_dates: Optional[List[date]] = None,
        forward_days: Optional[int] = None,
    ) -> list:
        """从 DB 获取 K 线；仅在前向收益补证据时按开关刷新 provider 数据。"""
        kwargs: dict[str, Any] = {}
        if start_date is not None:
            kwargs["start_date"] = start_date.isoformat()
        if end_date is not None:
            kwargs["end_date"] = end_date.isoformat()
        if limit is not None:
            kwargs["limit"] = limit

        klines = await db.get_klines(code, **kwargs)
        minimum_bars = 1 if start_date is not None or end_date is not None else 20
        close_series = self._build_close_series(list(klines or []))
        if (
            klines
            and len(klines) >= minimum_bars
            and self._has_forward_coverage(
                close_series,
                required_base_dates=required_base_dates,
                forward_days=forward_days,
            )
        ):
            return klines
        if not allow_data_source_fallback or not _forward_return_provider_refresh_enabled():
            return klines or []

        provider_limit = _forward_return_provider_refresh_limit()
        if start_date is not None:
            provider_limit = max(provider_limit, min(5000, (date.today() - start_date).days * 2 + 60))
        provider_rows = self._normalize_provider_klines(
            code,
            await self._fetch_provider_klines(code, limit=provider_limit),
        )
        if provider_rows and hasattr(db, "save_klines"):
            try:
                await db.save_klines(code, provider_rows)
            except Exception as exc:
                logger.warning(
                    "SignalTracker: provider kline save failed for %s: %s",
                    code,
                    exc,
                )
        merged = [*list(klines or []), *provider_rows]
        return merged or list(klines or [])

    def status(self) -> dict:
        return {
            "running": self._running,
            "run_time": str(self.run_time),
            "last_run": str(self.last_run) if self.last_run else None,
            "last_result": self.last_result,
        }
