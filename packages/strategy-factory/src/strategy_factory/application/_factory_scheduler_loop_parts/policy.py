
        @classmethod
        def _extract_bulk_stock_cursor(
            cls,
            summary: Optional[dict[str, Any]],
            *,
            source: str,
            run_id: Optional[str] = None,
        ) -> dict[str, Any]:
            return _extract_bulk_stock_cursor_payload(
                summary,
                source=source,
                run_id=run_id,
            )

        async def _resolve_bulk_stock_matrix_cursor(self, db) -> dict[str, Any]:
            return await _resolve_bulk_stock_matrix_cursor_payload(
                last_result=self.last_result,
                db=db,
                logger_=logger,
                call_optional_async=_call_optional_async,
            )

        @staticmethod
        def _maintenance_env_bool(name: str, default: bool = False) -> bool:
            raw = str(os.getenv(name) or "").strip().lower()
            return raw in ("1", "true", "yes", "on") if raw else default

        @staticmethod
        def _maintenance_seconds(name: str, default: int) -> int:
            try:
                return max(1, int(os.getenv(name, str(default)) or default))
            except Exception:
                return max(1, int(default))

        @staticmethod
        def _maintenance_due(last_at: Optional[datetime], now: datetime, interval_seconds: int) -> bool:
            if last_at is None:
                return True
            return (now - last_at).total_seconds() >= float(interval_seconds)

        async def _drain_event_outbox_maintenance(self, db, *, limit: int) -> dict[str, Any]:
            from .research.event_task_generator import generate_tasks_from_active_events

            generated = await generate_tasks_from_active_events(
                db,
                force_enabled=True,
                persist_lineage=False,
                event_limit=max(1, limit),
            )
            tasks = list(generated.get("tasks") or [])
            lineage_records = list(generated.get("lineage_records") or [])
            lineage_by_key = {
                str(item.get("dedupe_key") or "").strip(): dict(item or {})
                for item in lineage_records
                if str(item.get("dedupe_key") or "").strip()
            }
            processed = 0
            skipped = 0
            failed = 0
            for task in tasks[: max(1, limit)]:
                context = dict(task.get("event_context") or {})
                dedupe_key = str(context.get("dedupe_key") or "").strip()
                record = lineage_by_key.get(dedupe_key)
                if not dedupe_key or not record:
                    skipped += 1
                    continue
                try:
                    claim = await db.claim_event_outbox(
                        {
                            "dedupe_key": dedupe_key,
                            "source_event_id": record.get("event_id") or context.get("event_id"),
                            "theme_code": record.get("theme_code") or task.get("candidate_family"),
                            "event_type": context.get("event_type") or task.get("opportunity_type"),
                        }
                    )
                    if not claim.get("claimed"):
                        skipped += 1
                        continue
                    await db.upsert_event_task_lineage(record)
                    await db.mark_event_outbox_processed(dedupe_key)
                    processed += 1
                except Exception as exc:
                    failed += 1
                    with suppress(Exception):
                        await db.mark_event_outbox_failed(dedupe_key, error=str(exc))
            return {
                "status": "completed",
                "generated_task_count": len(tasks),
                "candidate_lineage_count": len(lineage_records),
                "processed": processed,
                "skipped": skipped,
                "failed": failed,
            }

        async def _run_event_theme_maintenance_if_due(self, db=None) -> dict[str, Any]:
            now = self._now()
            if self._is_market_hours(now):
                return {"status": "skipped", "reason": "market_hours"}

            exposure_enabled = self._maintenance_env_bool(
                "STRATEGY_FACTORY_THEME_EXPOSURE_AUTO_REFRESH_ENABLED",
                False,
            )
            outbox_enabled = self._maintenance_env_bool(
                "STRATEGY_FACTORY_EVENT_OUTBOX_AUTO_DRAIN_ENABLED",
                False,
            )
            regression_enabled = self._maintenance_env_bool(
                "STRATEGY_FACTORY_THEME_REGRESSION_AUTO_RUN_ENABLED",
                False,
            )
            if not (exposure_enabled or outbox_enabled or regression_enabled):
                return {"status": "disabled"}

            resolved_db = self._load_db() if db is None else db
            results: dict[str, Any] = {
                "status": "completed",
                "ran": [],
                "skipped": [],
                "errors": [],
            }

            if outbox_enabled:
                interval = self._maintenance_seconds(
                    "STRATEGY_FACTORY_EVENT_OUTBOX_DRAIN_INTERVAL_SEC",
                    1800,
                )
                if self._maintenance_due(self._last_event_outbox_drain_at, now, interval):
                    try:
                        limit = max(1, min(int(os.getenv("STRATEGY_FACTORY_EVENT_OUTBOX_DRAIN_LIMIT", "10") or 10), 100))
                        results["outbox_drain"] = await self._drain_event_outbox_maintenance(resolved_db, limit=limit)
                        self._last_event_outbox_drain_at = now
                        results["ran"].append("outbox_drain")
                    except Exception as exc:
                        results["errors"].append({"step": "outbox_drain", "error": str(exc)})
                else:
                    results["skipped"].append("outbox_drain_not_due")

            if exposure_enabled:
                interval = self._maintenance_seconds(
                    "STRATEGY_FACTORY_THEME_EXPOSURE_REFRESH_INTERVAL_SEC",
                    86400,
                )
                if self._maintenance_due(self._last_theme_exposure_refresh_at, now, interval):
                    try:
                        from .research.theme_exposure_builder import ThemeExposureBuilder

                        batch_size = max(1, min(int(os.getenv("STRATEGY_FACTORY_THEME_EXPOSURE_BATCH_SIZE", "1000") or 1000), 10000))
                        results["theme_exposure_refresh"] = await ThemeExposureBuilder(
                            batch_size=batch_size,
                        ).build(resolved_db, batch_size=batch_size)
                        self._last_theme_exposure_refresh_at = now
                        results["ran"].append("theme_exposure_refresh")
                    except Exception as exc:
                        results["errors"].append({"step": "theme_exposure_refresh", "error": str(exc)})
                else:
                    results["skipped"].append("theme_exposure_refresh_not_due")

            if regression_enabled:
                interval = self._maintenance_seconds(
                    "STRATEGY_FACTORY_THEME_REGRESSION_INTERVAL_SEC",
                    604800,
                )
                if self._maintenance_due(self._last_theme_regression_run_at, now, interval):
                    try:
                        from .research.theme_response_regression import ThemeResponseRegression

                        results["theme_regression_run"] = await ThemeResponseRegression().run_full_update(resolved_db)
                        self._last_theme_regression_run_at = now
                        results["ran"].append("theme_regression_run")
                    except Exception as exc:
                        results["errors"].append({"step": "theme_regression_run", "error": str(exc)})
                else:
                    results["skipped"].append("theme_regression_not_due")

            if results["errors"]:
                results["status"] = "partial"
            self._last_event_theme_maintenance_result = results
            return results

        async def _loop(self):
            while self._running:
                try:
                    now = self._now()
                    today_str = now.strftime("%Y-%m-%d")

                    # 日期变更 → 重置每日计数
                    if self._daily_run_date != today_str:
                        self._daily_run_date = today_str
                        self._daily_run_count = 0

                    # 优化 2：断路器状态机（CLOSED → OPEN → HALF_OPEN → CLOSED）
                    if self._circuit_state == "open":
                        if self._circuit_open_until is not None and now >= self._circuit_open_until:
                            # 冷却期结束 → 进入 HALF_OPEN 探测
                            self._circuit_state = "half_open"
                            self._metrics.record_half_open_probe()
                            logger.info(
                                "StrategyFactory: circuit breaker → HALF_OPEN, probing recovery..."
                            )
                        else:
                            sleep_sec = (self._circuit_open_until - now).total_seconds() if self._circuit_open_until else 300
                            logger.warning(
                                "StrategyFactory: circuit breaker OPEN, sleeping %.0fs until %s",
                                sleep_sec, (self._circuit_open_until or "unknown"),
                            )
                            await asyncio.sleep(min(sleep_sec + 1, 300))
                            continue

                    if self._circuit_state == "half_open":
                        # HALF_OPEN：执行一次探测
                        try:
                            self._metrics.record_cycle_start()
                            await self.run_once()
                            # 探测成功 → 完全恢复
                            self._circuit_state = "closed"
                            self._consecutive_failures = 0
                            self._circuit_open_until = None
                            self._circuit_open_backoff_sec = self._circuit_open_backoff_sec_initial
                            self._daily_run_count += 1
                            self._cycle_count += 1
                            self._metrics.record_cycle_success(
                                (self._now() - now).total_seconds(), self._now()
                            )
                            logger.info("StrategyFactory: circuit breaker HALF_OPEN → CLOSED (probe succeeded)")
                        except Exception as probe_exc:
                            # 探测失败 → 重新打开，指数退避
                            self._circuit_open_backoff_sec = min(
                                self._circuit_open_backoff_sec * 2, 7200
                            )
                            self._circuit_state = "open"
                            self._circuit_open_until = self._now() + timedelta(
                                seconds=self._circuit_open_backoff_sec
                            )
                            self._metrics.record_cycle_failure(probe_exc, self._now())
                            logger.warning(
                                "StrategyFactory: HALF_OPEN probe failed, circuit → OPEN (backoff %ds): %s",
                                self._circuit_open_backoff_sec, probe_exc,
                            )
                        continue

                    # 达到每日上限 → 睡到午夜
                    if self._daily_run_count >= self.max_daily_runs:
                        tomorrow = datetime.combine(now.date() + timedelta(days=1), time(0, 0), tzinfo=self._market_timezone)
                        sleep_sec = (tomorrow - now).total_seconds() + 1
                        logger.info(
                            "StrategyFactory: daily limit reached (%d/%d), sleeping %.0fs until midnight",
                            self._daily_run_count, self.max_daily_runs, sleep_sec,
                        )
                        await asyncio.sleep(sleep_sec)
                        continue

                    wait = self._compute_next_wait(now)
                    logger.info(
                        "StrategyFactory [%s]: cycle #%d, today %d/%d runs, next in %.0fs",
                        self.schedule_mode, self._cycle_count, self._daily_run_count,
                        self.max_daily_runs, wait,
                    )
                    await asyncio.sleep(wait)

                    if self._running:
                        self._metrics.record_cycle_start()
                        cycle_start = self._now()
                        await self._run_event_theme_maintenance_if_due()
                        await self.run_once()
                        self._daily_run_count += 1
                        self._cycle_count += 1
                        # 成功 → 重置断路器
                        self._consecutive_failures = 0
                        self._circuit_open_until = None
                        self._circuit_state = "closed"
                        self._metrics.record_cycle_success(
                            (self._now() - cycle_start).total_seconds(), self._now()
                        )
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    self._consecutive_failures += 1
                    self._metrics.record_cycle_failure(exc, self._now())
                    logger.error(
                        "StrategyFactory loop error (#%d consecutive): %s",
                        self._consecutive_failures, exc, exc_info=True,
                    )
                    if self._consecutive_failures >= self._max_consecutive_failures:
                        self._circuit_state = "open"
                        self._circuit_open_until = self._now() + timedelta(
                            seconds=self._circuit_open_backoff_sec
                        )
                        self._metrics.record_circuit_trip()
                        logger.critical(
                            "StrategyFactory: circuit breaker OPEN after %d consecutive failures, "
                            "will retry at %s",
                            self._consecutive_failures,
                            self._circuit_open_until.isoformat(),
                        )
                    # 优化 6：指数退避 + 抖动
                    await asyncio.sleep(self._compute_error_backoff())

        async def _generate_for_research_task(self, autonomy_gateway, db, snapshot: dict, task: dict) -> dict:
            effective_task = dict(task or {})
            provider_health = self._external_llm_health_snapshot(autonomy_gateway)
            if provider_health.get("scheduler_should_disable"):
                effective_task["disable_external_llm"] = True
                effective_task["external_llm_skip_reason"] = (
                    provider_health.get("scheduler_skip_reason") or "provider_health_blocked"
                )
            limit = max(
                1,
                min(int(effective_task.get("generation_limit") or AUTONOMY_CANDIDATES_PER_TASK), AUTONOMY_TASK_HARD_CAP),
            )
            source = f"strategy_factory:{effective_task.get('opportunity_type') or 'general'}"
            gateway_db = self._adapt_gateway_repository(db)
            task_id = str(effective_task.get("task_id") or effective_task.get("task_key") or source).strip() or source
            base_timeout_sec = self._resolve_research_task_timeout_sec()

            async def _run_generation(task_payload: dict[str, Any], *, local_fallback: bool = False) -> dict:
                timeout_sec = self._resolve_effective_research_task_timeout_sec(
                    autonomy_gateway,
                    task_payload,
                    base_timeout=base_timeout_sec,
                    local_fallback=local_fallback,
                )
                return await asyncio.wait_for(
                    autonomy_gateway.generate_factory_candidates(
                        gateway_db,
                        snapshot,
                        limit=limit,
                        research_task=task_payload,
                        source=source,
                    ),
                    timeout=timeout_sec,
                )

            try:
                return await _run_generation(effective_task)
            except asyncio.TimeoutError as exc:
                initial_timeout_sec = self._resolve_effective_research_task_timeout_sec(
                    autonomy_gateway,
                    effective_task,
                    base_timeout=base_timeout_sec,
                )
                # P3 (R7.3): classify the timeout source so dashboards can
                # tell apart external LLM gateway timeouts (network) from
                # pipeline-stage timeouts (LLM responded but a stage took
                # too long) from bulk-research timeouts (long-tail bulk
                # task hit the bulk timeout cap).
                timeout_kind = _classify_research_task_timeout_kind(
                    effective_task,
                    base_timeout_sec=base_timeout_sec,
                    effective_timeout_sec=initial_timeout_sec,
                )
                logger.warning(
                    "StrategyFactory: research task %s timed out after %.1fs "
                    "(kind=%s); skipping generation without local fallback",
                    task_id,
                    float(initial_timeout_sec or 0.0),
                    timeout_kind,
                )
                timeout_lifecycle = {
                    "state": "skipped",
                    "current_phase": "generating",
                    "failed_phase": None,
                    "terminal_phase": "skipped_timeout",
                    "phase_order": ["prepare", "generate", "review", "complete"],
                    "phase_status_counts": {"skipped": 1},
                    "completed_phase_count": 0,
                    "event_count": 1,
                    "events": [
                        {
                            "phase": "generating",
                            "status": "skipped",
                            "reason": "ResearchTaskTimeout",
                            "timeout_sec": round(float(initial_timeout_sec or 0.0), 4),
                        }
                    ],
                }
                return {
                    "status": "skipped_timeout",
                    "generated_count": 0,
                    "reviewed_count": 0,
                    "generation": {"count": 0, "candidates": []},
                    "candidates": [],
                    "experiments": [],
                    "llm_generation": {
                        "requested_limit": limit,
                        "selected_count": 0,
                        "research_task": dict(effective_task),
                        "task_timeout_skip": True,
                        "task_timeout_sec": round(float(initial_timeout_sec or 0.0), 4),
                        "task_timeout_policy": "skip_without_local_fallback",
                        "task_timeout_kind": timeout_kind,
                        "requeue_recommended": True,
                        "external_provider": {
                            "enabled": bool(not effective_task.get("disable_external_llm")),
                            "status": "skipped_timeout",
                            "requests": [],
                            "selected_count": 0,
                            "viable_selected_count": 0,
                            "fallback_count": 0,
                            "last_error_type": "ResearchTaskTimeout",
                            "last_error": f"research task {task_id} exceeded {initial_timeout_sec:g}s",
                            "elapsed_seconds": round(float(initial_timeout_sec or 0.0), 4),
                        },
                    },
                    "lifecycle": timeout_lifecycle,
                }

        async def _persist_full_market_topn(
            self,
            db,
            results: dict[str, Any],
            *,
            persistence_failures: list[dict[str, Any]],
        ) -> None:
            topn_payload = dict(results.get("full_market_topn") or {})
            score_rows = [
                dict(item or {})
                for item in list(results.get("_full_market_score_rows") or [])
                if isinstance(item, dict)
            ]
            run_id = str(results.get("run_id") or "").strip()
            trace_id = str(results.get("trace_id") or "").strip() or None
            if not topn_payload or not run_id:
                return

            try:
                portfolio_candidate = build_portfolio_candidate_from_topn(
                    topn_payload,
                    run_id=run_id,
                    trace_id=trace_id,
                )
            except Exception as exc:
                logger.warning(
                    "StrategyFactory: failed to build full-market Top N portfolio candidate for run %s: %s",
                    run_id,
                    exc,
                )
                self._record_persistence_failure(
                    persistence_failures,
                    "build_portfolio_candidate_from_topn",
                    exc,
                    stage="full_market_topn",
                )
                portfolio_candidate = None

            enriched_snapshot = {
                **topn_payload,
                "run_id": run_id,
                "trace_id": trace_id,
                "correlation_id": str(topn_payload.get("correlation_id") or run_id).strip() or run_id,
                "source_action": "factory_run_once",
            }
            if portfolio_candidate is not None:
                enriched_snapshot["portfolio_candidate_id"] = portfolio_candidate.get("id")

            if portfolio_candidate is not None and hasattr(db, "save_strategy"):
                try:
                    await db.save_strategy(portfolio_candidate)
                except Exception as exc:
                    logger.warning(
                        "StrategyFactory: failed to persist Top N portfolio candidate for run %s: %s",
                        run_id,
                        exc,
                    )
                    self._record_persistence_failure(
                        persistence_failures,
                        "save_strategy:topn_portfolio_candidate",
                        exc,
                        stage="full_market_topn",
                    )

            if hasattr(db, "save_strategy_factory_topn_snapshot"):
                try:
                    saved_snapshot = await db.save_strategy_factory_topn_snapshot(enriched_snapshot)
                    if isinstance(saved_snapshot, dict):
                        enriched_snapshot = {**enriched_snapshot, **saved_snapshot}
                except Exception as exc:
                    logger.warning(
                        "StrategyFactory: failed to persist Top N snapshot for run %s: %s",
                        run_id,
                        exc,
                    )
                    self._record_persistence_failure(
                        persistence_failures,
                        "save_strategy_factory_topn_snapshot",
                        exc,
                        stage="full_market_topn",
                    )

            if score_rows and hasattr(db, "replace_strategy_factory_full_market_scores"):
                try:
                    await db.replace_strategy_factory_full_market_scores(
                        run_id=run_id,
                        snapshot_id=str(enriched_snapshot.get("snapshot_id") or "").strip() or f"fmt_{run_id}",
                        as_of_date=enriched_snapshot.get("as_of_date"),
                        trace_id=trace_id,
                        correlation_id=enriched_snapshot.get("correlation_id"),
                        rows=score_rows,
                    )
                except Exception as exc:
                    logger.warning(
                        "StrategyFactory: failed to persist full-market scores for run %s: %s",
                        run_id,
                        exc,
                    )
                    self._record_persistence_failure(
                        persistence_failures,
                        "replace_strategy_factory_full_market_scores",
                        exc,
                        stage="full_market_topn",
                    )

            results["full_market_topn"] = enriched_snapshot
            if isinstance(results.get("summary"), dict):
                results["summary"]["full_market_topn"] = enriched_snapshot

        async def _persist_run_result(
            self,
            db,
            results: dict[str, Any],
            *,
            persistence_failures: list[dict[str, Any]],
        ) -> None:
            await self._persist_run_artifacts(
                db,
                results,
                persistence_failures=persistence_failures,
            )
            await self._persist_full_market_topn(
                db,
                results,
                persistence_failures=persistence_failures,
            )
            self._apply_run_audit(results, persistence_failures=persistence_failures)
            if not hasattr(db, "save_strategy_factory_run"):
                return
            try:
                await db.save_strategy_factory_run(results)
            except Exception as exc:
                logger.warning("StrategyFactory: failed to persist run %s: %s", results.get("run_id"), exc)
                self._record_persistence_failure(
                    persistence_failures,
                    "save_strategy_factory_run",
                    exc,
                    stage="run",
                )
                self._apply_run_audit(results, persistence_failures=persistence_failures)

        async def _persist_run_artifacts(
            self,
            db,
            results: dict[str, Any],
            *,
            persistence_failures: list[dict[str, Any]],
        ) -> None:
            artifacts = [
                dict(item or {})
                for item in list(results.get("artifacts") or [])
                if isinstance(item, dict)
            ]
            if not artifacts:
                return
            if not hasattr(db, "save_strategy_factory_run_artifact"):
                results["artifact_refs"] = build_artifact_refs(artifacts)
                return
            persisted: list[dict[str, Any]] = []
            run_id = str(results.get("run_id") or "").strip()
            for artifact in artifacts:
                try:
                    row = await _call_optional_async(
                        db,
                        "save_strategy_factory_run_artifact",
                        {
                            **artifact,
                            "run_id": run_id,
                        },
                        default=None,
                    )
                except Exception as exc:
                    logger.warning(
                        "StrategyFactory: failed to persist artifact %s for run %s: %s",
                        artifact.get("artifact_type"),
                        run_id,
                        exc,
                    )
                    self._record_persistence_failure(
                        persistence_failures,
                        f"save_strategy_factory_run_artifact:{artifact.get('artifact_type')}",
                        exc,
                        stage="artifact",
                    )
                    continue
                if row is not None:
                    persisted.append(dict(row))
            results["artifact_refs"] = build_artifact_refs(persisted or artifacts)

        async def _execute_factory_cycle_once(
            self,
            resolved_db,
            *,
            previous_result: Optional[dict[str, Any]],
            execution_mode: FactoryExecutionMode | str,
            parity_role: str = "primary",
            read_only: bool = False,
            run_id: Optional[str] = None,
            trace_id: Optional[str] = None,
            target_codes: Optional[list[str]] = None,
        ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
            start = self._now()
            resolved_mode = resolve_factory_execution_mode(
                execution_mode,
                default=self.execution_mode,
            )
            effective_run_id = (
                str(run_id or "").strip()
                or f"factory_run_{int(start.timestamp())}_{uuid4().hex[:8]}"
            )
            effective_trace_id = (
                str(trace_id or "").strip()
                or f"strategy_factory:{uuid4().hex[:12]}"
            )
            if parity_role and parity_role != "primary":
                effective_trace_id = f"{effective_trace_id}:{parity_role}"
            context = FactoryRunContext(
                db=resolved_db,
                factory_pkg=get_strategy_factory_package(),
                runtime_adapters=self._runtime_adapters,
                start=start,
                trace_id=effective_trace_id,
                run_id=effective_run_id,
                execution_mode=resolved_mode.value,
                engine_version=resolve_factory_engine_version(
                    resolved_mode,
                    default=str(getattr(self, "engine_version", None) or FACTORY_ENGINE_VERSION),
                ),
                parity_role=str(parity_role or "primary"),
                read_only=bool(read_only),
                target_codes=_normalize_target_codes(target_codes or [], limit=64),
            )
            if resolved_mode == FactoryExecutionMode.V2_PRIMARY:
                # V2_PRIMARY is deprecated: it runs the same FactoryCycleRunner.
                # Kept as alias for forward-compat; no separate engine.
                from . import factory_scheduler as scheduler_module

                outcome = await scheduler_module.FactoryCycleRunner(self, context).run()
            else:
                from . import factory_scheduler as scheduler_module

                outcome = await scheduler_module.FactoryCycleRunner(self, context).run()
            results = dict(outcome.result or {})
            self._attach_runtime_governance(results, previous_result=previous_result)
            return results, list(outcome.persistence_failures or [])

        async def _execute_factory_run_once_mode(
            self,
            resolved_db,
            *,
            previous_result: Optional[dict[str, Any]],
            execution_mode: FactoryExecutionMode | str,
            target_codes: Optional[list[str]] = None,
        ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
            resolved_mode = resolve_factory_execution_mode(
                execution_mode,
                default=self.execution_mode,
            )
            primary_result, persistence_failures = await self._execute_factory_cycle_once(
                resolved_db,
                previous_result=previous_result,
                execution_mode=resolved_mode,
                parity_role="primary",
                read_only=False,
                target_codes=target_codes,
            )
            if resolved_mode == FactoryExecutionMode.SHADOW_READONLY:
                primary_result["paper_trading_cycle"] = {
                    "status": "skipped",
                    "skipped": True,
                    "reason": "shadow_readonly",
                    "write_path": "paper_trading_cycle",
                }
            else:
                # PR-D1: 策略工厂 cycle 完成后，执行模拟盘日循环
                try:
                    from strategy_factory.application.research.paper_trading_scheduler import run_paper_trading_cycle
                    paper_timeout_sec = max(
                        1,
                        int(os.getenv("STRATEGY_FACTORY_PAPER_TRADING_CYCLE_TIMEOUT_SEC", "300") or 300),
                    )
                    logger.info(
                        "StrategyFactory: starting paper trading post-cycle timeout=%ss",
                        paper_timeout_sec,
                    )
                    paper_result = await asyncio.wait_for(
                        run_paper_trading_cycle(resolved_db),
                        timeout=paper_timeout_sec,
                    )
                    primary_result["paper_trading_cycle"] = paper_result
                except asyncio.TimeoutError:
                    logger.warning(
                        "StrategyFactory: paper trading post-cycle timed out after %ss",
                        paper_timeout_sec,
                    )
                    primary_result["paper_trading_cycle"] = {
                        "status": "timeout",
                        "error": f"paper trading cycle exceeded {paper_timeout_sec}s",
                    }
                except Exception as _paper_exc:
                    primary_result["paper_trading_cycle"] = {"status": "failed", "error": str(_paper_exc)}
            if resolved_mode != FactoryExecutionMode.SHADOW_READONLY:
                return primary_result, persistence_failures

            shadow_run_id = f"{str(primary_result.get('run_id') or '').strip()}__shadow"
            shadow_trace_id = str(primary_result.get("trace_id") or "").strip()
            shadow_result: Optional[dict[str, Any]] = None
            try:
                shadow_result, shadow_failures = await self._execute_factory_cycle_once(
                    resolved_db,
                    previous_result=previous_result,
                    execution_mode=resolved_mode,
                    parity_role="shadow",
                    read_only=True,
                    run_id=shadow_run_id,
                    trace_id=shadow_trace_id,
                    target_codes=target_codes,
                )
                persistence_failures.extend(shadow_failures)
                parity_result = build_shadow_parity_result(primary_result, shadow_result)
                primary_result["shadow_run"] = {
                    "run_id": shadow_result.get("run_id"),
                    "trace_id": shadow_result.get("trace_id"),
                    "status": shadow_result.get("status"),
                    "summary": dict(shadow_result.get("summary") or {}),
                    "read_only": True,
                }
            except Exception as exc:
                logger.warning("StrategyFactory: shadow readonly execution failed: %s", exc, exc_info=True)
                parity_result = {
                    "comparison_contract_version": "strategy_factory.shadow_parity.v1",
                    "status": "shadow_failed",
                    "mismatch_count": 1,
                    "mismatches": ["shadow_run_error"],
                    "comparisons": {},
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                }
            primary_result["parity_result"] = parity_result
            summary = dict(primary_result.get("summary") or {})
            summary["parity_status"] = parity_result.get("status")
            summary["shadow_readonly_enabled"] = True
            summary["shadow_run_id"] = shadow_run_id
            primary_result["summary"] = summary
            primary_result["artifacts"] = build_run_artifacts(primary_result)
            primary_result["artifact_refs"] = build_artifact_refs(primary_result.get("artifacts") or [])
            return primary_result, persistence_failures

        async def _prepare_shared_generation_context(self, autonomy_gateway, db, snapshot: dict[str, Any]) -> bool:
            autonomy_target = getattr(autonomy_gateway, "raw", autonomy_gateway)
            generation_service = getattr(autonomy_target, "generation_service", None)
            builder = getattr(generation_service, "build_shared_generation_context", None)
            if not callable(builder):
                return False
            try:
                snapshot["_shared_generation_context"] = await _call_optional_async(
                    generation_service,
                    "build_shared_generation_context",
                    db,
                    snapshot=snapshot,
                    default={},
                )
                return bool(snapshot.get("_shared_generation_context"))
            except Exception as exc:
                logger.warning("StrategyFactory: shared generation context preload failed: %s", exc)
                return False

        @staticmethod
        def _get_external_llm_provider(autonomy_gateway):
            autonomy_target = getattr(autonomy_gateway, "raw", autonomy_gateway)
            generation_service = getattr(autonomy_target, "generation_service", None)
            llm_generator = getattr(generation_service, "llm_generator", None) or getattr(autonomy_target, "llm_generator", None)
            return getattr(llm_generator, "external_provider", None)

        @classmethod
        def _external_llm_health_snapshot(cls, autonomy_gateway) -> dict[str, Any]:
            external_provider = cls._get_external_llm_provider(autonomy_gateway)
            if external_provider is None:
                return {}
            snapshot_getter = getattr(external_provider, "get_health_snapshot", None)
            if not callable(snapshot_getter):
                return {}
            try:
                snapshot = snapshot_getter()
            except Exception:
                return {}
            return dict(snapshot or {})

        @classmethod
        def _external_llm_should_participate(cls, autonomy_gateway) -> bool:
            external_provider = cls._get_external_llm_provider(autonomy_gateway)
            if external_provider is None:
                return False
            try:
                if callable(getattr(external_provider, "is_enabled", None)) and not external_provider.is_enabled():
                    return False
            except Exception:
                return False
            return not bool(cls._external_llm_health_snapshot(autonomy_gateway).get("scheduler_should_disable"))

        @classmethod
        def _resolve_external_llm_concurrency_limit(cls, autonomy_gateway) -> Optional[int]:
            external_provider = cls._get_external_llm_provider(autonomy_gateway)
            if external_provider is None or not cls._external_llm_should_participate(autonomy_gateway):
                return None
            try:
                limit = int(getattr(getattr(external_provider, "config", None), "max_concurrency", 0) or 0)
            except Exception:
                return None
            return max(1, limit) if limit > 0 else None

        @staticmethod
        def _env_bool(*names: str, default: bool) -> bool:
            for name in names:
                raw = os.getenv(str(name or "").strip())
                if raw is None:
                    continue
                text = str(raw).strip().lower()
                if text in {"1", "true", "yes", "y", "on"}:
                    return True
                if text in {"0", "false", "no", "n", "off"}:
                    return False
            return bool(default)

        @classmethod
        def _bulk_tasks_use_external_llm(cls, autonomy_gateway) -> bool:
            if not cls._external_llm_should_participate(autonomy_gateway):
                return False
            autonomy_target = getattr(autonomy_gateway, "raw", autonomy_gateway)
            generation_service = getattr(autonomy_target, "generation_service", None)
            resolver = getattr(generation_service, "_bulk_llm_enabled", None)
            if callable(resolver):
                try:
                    return bool(resolver())
                except Exception:
                    pass
            return cls._env_bool(
                "STRATEGY_FACTORY_BULK_LLM_ENABLED",
                "STRATEGY_FACTORY_BULK_STOCK_MATRIX_LLM_ENABLED",
                default=False,
            )

        @classmethod
        def _research_task_uses_external_llm(cls, autonomy_gateway, task: dict[str, Any] | None) -> bool:
            payload = dict(task or {})
            if payload.get("disable_external_llm"):
                return False
            if not cls._external_llm_should_participate(autonomy_gateway):
                return False
            task_source = str(payload.get("task_source") or "").strip().lower()
            if task_source == "bulk_stock_matrix":
                return cls._bulk_tasks_use_external_llm(autonomy_gateway)
            return True

        @classmethod
        def _resolve_research_task_concurrency(cls, autonomy_gateway, *, has_bulk_tasks: bool = False) -> int:
            effective = RESEARCH_TASK_CONCURRENCY
            provider_limit = cls._resolve_external_llm_concurrency_limit(autonomy_gateway)
            if provider_limit is not None:
                effective = min(effective, provider_limit)
            if has_bulk_tasks and cls._bulk_tasks_use_external_llm(autonomy_gateway):
                bulk_target = max(1, int(STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY))
                if provider_limit is not None:
                    bulk_target = min(bulk_target, provider_limit)
                effective = max(effective, bulk_target)
            return max(1, effective)

        @classmethod
        def _resolve_bulk_research_task_concurrency(cls, autonomy_gateway, *, has_bulk_tasks: bool = False) -> int:
            if not has_bulk_tasks:
                return cls._resolve_research_task_concurrency(autonomy_gateway, has_bulk_tasks=False)
            if cls._bulk_tasks_use_external_llm(autonomy_gateway):
                return cls._resolve_research_task_concurrency(autonomy_gateway, has_bulk_tasks=True)
            return max(1, int(STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY))

        @staticmethod
        def _resolve_research_task_timeout_sec() -> float:
            raw = str(os.getenv("STRATEGY_FACTORY_RESEARCH_TASK_TIMEOUT_SEC", "180") or "180").strip()
            try:
                value = float(raw)
            except Exception:
                value = 180.0
            return max(15.0, min(value, 1800.0))

        @staticmethod
        def _research_task_uses_bulk_timeout(task: dict[str, Any] | None) -> bool:
            payload = dict(task or {})
            task_source = str(payload.get("task_source") or "").strip().lower()
            task_id = str(payload.get("task_id") or payload.get("task_key") or "").strip().lower()
            opportunity_type = str(payload.get("opportunity_type") or "").strip().lower()
            return (
                task_source in {"bulk_stock_matrix", "stock_strategy_matrix", "matrix"}
                or "bulk_matrix" in task_id
                or "bulk_stock_matrix" in task_id
                or opportunity_type in {"bulk_stock_matrix", "stock_strategy_matrix"}
            )

        @staticmethod
        def _resolve_run_once_timeout_sec() -> float:
            raw = str(os.getenv("STRATEGY_FACTORY_RUN_ONCE_TIMEOUT_SEC", "1800") or "1800").strip()
            try:
                value = float(raw)
            except Exception:
                value = 1800.0
            return max(60.0, min(value, 7200.0))

        @staticmethod
        def _resolve_external_research_task_timeout_cap_sec() -> float:
            # PR-R2: 默认从 20s 提到 120s。LLM 网关 P95 ~30s，fan-out 4 次 + staged pipeline
            # 多阶段需要 60–120s 才能完成。20s 导致每轮 4–8 个 task 被 timeout 降级。
            raw = str(
                os.getenv("STRATEGY_FACTORY_EXTERNAL_RESEARCH_TASK_TIMEOUT_SEC", "120")
                or "120"
            ).strip()
            try:
                value = float(raw)
            except Exception:
                value = 120.0
            return max(0.001, min(value, 600.0))

        @staticmethod
        def _resolve_bulk_research_task_timeout_sec() -> float:
            raw = str(os.getenv("STRATEGY_FACTORY_BULK_RESEARCH_TASK_TIMEOUT_SEC", "360") or "360").strip()
            try:
                value = float(raw)
            except Exception:
                value = 360.0
            return max(60.0, min(value, 1800.0))

        @staticmethod
        def _resolve_local_fallback_research_task_timeout_cap_sec() -> float:
            raw = str(
                os.getenv("STRATEGY_FACTORY_LOCAL_FALLBACK_TASK_TIMEOUT_SEC", "10")
                or "10"
            ).strip()
            try:
                value = float(raw)
            except Exception:
                value = 10.0
            return max(0.001, min(value, 120.0))
