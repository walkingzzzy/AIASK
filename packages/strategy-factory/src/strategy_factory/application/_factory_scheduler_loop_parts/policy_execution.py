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
            effective_engine_version = resolve_factory_engine_version(
                resolved_mode,
                default=str(getattr(self, "engine_version", None) or FACTORY_ENGINE_VERSION),
            )
            context = FactoryRunContext(
                db=resolved_db,
                factory_pkg=get_strategy_factory_package(),
                runtime_adapters=self._runtime_adapters,
                start=start,
                trace_id=effective_trace_id,
                run_id=effective_run_id,
                execution_mode=resolved_mode.value,
                engine_version=effective_engine_version,
                parity_role=str(parity_role or "primary"),
                read_only=bool(read_only),
                target_codes=_normalize_target_codes(target_codes or [], limit=64),
            )
            await self._persist_run_status_marker(
                resolved_db,
                run_id=effective_run_id,
                status="running",
                started_at=start,
                execution_mode=resolved_mode.value,
                engine_version=effective_engine_version,
                trace_id=effective_trace_id,
                parity_role=str(parity_role or "primary"),
                read_only=bool(read_only),
                reason="cycle_started",
            )
            try:
                if resolved_mode == FactoryExecutionMode.V2_PRIMARY:
                    # V2_PRIMARY is deprecated: it runs the same FactoryCycleRunner.
                    # Kept as alias for forward-compat; no separate engine.
                    from . import factory_scheduler as scheduler_module

                    outcome = await scheduler_module.FactoryCycleRunner(self, context).run()
                else:
                    from . import factory_scheduler as scheduler_module

                    outcome = await scheduler_module.FactoryCycleRunner(self, context).run()
            except asyncio.CancelledError:
                completed = self._now()
                await self._persist_run_status_marker(
                    resolved_db,
                    run_id=effective_run_id,
                    status="interrupted",
                    started_at=start,
                    completed_at=completed,
                    elapsed_seconds=round((completed - start).total_seconds(), 1),
                    execution_mode=resolved_mode.value,
                    engine_version=effective_engine_version,
                    trace_id=effective_trace_id,
                    parity_role=str(parity_role or "primary"),
                    read_only=bool(read_only),
                    error="StrategyFactory run_once cancelled before completion",
                    reason="cancelled",
                )
                raise
            except Exception as exc:
                completed = self._now()
                await self._persist_run_status_marker(
                    resolved_db,
                    run_id=effective_run_id,
                    status="failed",
                    started_at=start,
                    completed_at=completed,
                    elapsed_seconds=round((completed - start).total_seconds(), 1),
                    execution_mode=resolved_mode.value,
                    engine_version=effective_engine_version,
                    trace_id=effective_trace_id,
                    parity_role=str(parity_role or "primary"),
                    read_only=bool(read_only),
                    error=str(exc),
                    reason=exc.__class__.__name__,
                )
                raise
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
            def _set_paper_trading_cycle(payload: dict[str, Any]) -> None:
                primary_result["paper_trading_cycle"] = payload
                if isinstance(primary_result.get("summary"), dict):
                    primary_result["summary"]["paper_trading_cycle"] = payload

            if resolved_mode == FactoryExecutionMode.SHADOW_READONLY:
                _set_paper_trading_cycle({
                    "status": "skipped",
                    "skipped": True,
                    "reason": "shadow_readonly",
                    "write_path": "paper_trading_cycle",
                })
            elif _gate3_record_only_enabled():
                _set_paper_trading_cycle({
                    "status": "skipped",
                    "skipped": True,
                    "reason": "gate3_record_only",
                    "write_path": "paper_trading_cycle",
                })
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
                    _set_paper_trading_cycle(paper_result)
                except asyncio.TimeoutError:
                    logger.warning(
                        "StrategyFactory: paper trading post-cycle timed out after %ss",
                        paper_timeout_sec,
                    )
                    _set_paper_trading_cycle({
                        "status": "timeout",
                        "error": f"paper trading cycle exceeded {paper_timeout_sec}s",
                    })
                except Exception as _paper_exc:
                    _set_paper_trading_cycle({"status": "failed", "error": str(_paper_exc)})
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
