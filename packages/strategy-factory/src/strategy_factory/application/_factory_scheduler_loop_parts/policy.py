
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

        async def _loop(self):
            while self._running:
                try:
                    now = self._now()
                    today_str = now.strftime("%Y-%m-%d")

                    # 日期变更 → 重置每日计数
                    if self._daily_run_date != today_str:
                        self._daily_run_date = today_str
                        self._daily_run_count = 0

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
                        await self.run_once()
                        self._daily_run_count += 1
                        self._cycle_count += 1
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error("StrategyFactory loop error: %s", exc, exc_info=True)
                    await asyncio.sleep(FACTORY_ERROR_BACKOFF_SEC)

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
                retry_task = dict(effective_task)
                retry_applied = False
                if not retry_task.get("disable_external_llm"):
                    retry_task["disable_external_llm"] = True
                    retry_task["external_llm_skip_reason"] = "task_timeout_local_fallback"
                    retry_applied = True
                if not retry_task.get("disable_pipeline_staged"):
                    retry_task["disable_pipeline_staged"] = True
                    retry_task["pipeline_staged_skip_reason"] = "task_timeout_local_fallback"
                    retry_applied = True
                if not retry_applied:
                    raise RuntimeError(
                        f"research task {task_id} timed out after {initial_timeout_sec:g}s"
                    ) from exc
                retry_task["task_timeout_local_fallback"] = True
                retry_task["task_timeout_local_fallback_attempts"] = int(
                    retry_task.get("task_timeout_local_fallback_attempts") or 0
                ) + 1
                try:
                    return await _run_generation(retry_task, local_fallback=True)
                except asyncio.TimeoutError as retry_exc:
                    fallback_timeout_sec = self._resolve_effective_research_task_timeout_sec(
                        autonomy_gateway,
                        retry_task,
                        base_timeout=base_timeout_sec,
                        local_fallback=True,
                    )
                    raise RuntimeError(
                        "research task "
                        f"{task_id} timed out after {initial_timeout_sec:g}s "
                        f"and local fallback timed out after {fallback_timeout_sec:g}s"
                    ) from retry_exc

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
            )
            if resolved_mode == FactoryExecutionMode.V2_PRIMARY:
                from .v2_engine import FactoryV2Engine

                outcome = await FactoryV2Engine(self, context).run()
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
            )
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
        def _resolve_external_research_task_timeout_cap_sec() -> float:
            raw = str(
                os.getenv("STRATEGY_FACTORY_EXTERNAL_RESEARCH_TASK_TIMEOUT_SEC", "20")
                or "20"
            ).strip()
            try:
                value = float(raw)
            except Exception:
                value = 20.0
            return max(0.001, min(value, 300.0))

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
