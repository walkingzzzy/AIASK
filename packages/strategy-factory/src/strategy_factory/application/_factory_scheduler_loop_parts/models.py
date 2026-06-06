
        @staticmethod
        def _env_flag(name: str, default: bool = False) -> bool:
            raw = os.getenv(name)
            if raw is None:
                return bool(default)
            normalized = str(raw).strip().lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off"}:
                return False
            return bool(default)

        @classmethod
        def _full_cycle_parallel_enabled(cls) -> bool:
            return cls._env_flag("STRATEGY_FACTORY_ALLOW_PARALLEL_FULL_CYCLES", False)

        @classmethod
        def _resolve_dispatch_concurrency_limit(cls) -> int:
            raw = str(os.getenv("STRATEGY_FACTORY_MAX_CONCURRENT_DISPATCHES", "1") or "1").strip()
            try:
                configured = int(raw)
            except Exception:
                configured = 1
            configured = max(1, min(configured, 16))
            if not cls._full_cycle_parallel_enabled():
                return 1
            return configured

        def _get_dispatch_semaphore(self) -> asyncio.Semaphore:
            loop = asyncio.get_running_loop()
            limit = self._resolve_dispatch_concurrency_limit()
            if (
                getattr(self, "_dispatch_semaphore", None) is None
                or getattr(self, "_dispatch_semaphore_loop", None) is not loop
                or int(getattr(self, "_dispatch_semaphore_limit", 0) or 0) != limit
            ):
                self._dispatch_semaphore = asyncio.Semaphore(limit)
                self._dispatch_semaphore_loop = loop
                self._dispatch_semaphore_limit = limit
            return self._dispatch_semaphore

        def _active_dispatch_ids(self) -> list[str]:
            return [
                str(dispatch_id)
                for dispatch_id, task in dict(getattr(self, "_dispatch_tasks", {}) or {}).items()
                if task is not None and not task.done()
            ]

        async def _run_parallel_dispatch_cycle(
            self,
            resolved_db,
            *,
            resolved_mode,
            dispatch_id: str,
            target_codes: Optional[list[str]] = None,
        ) -> dict[str, Any]:
            try:
                restore_scheduler_state = getattr(self, "_restore_scheduler_state", None)
                if callable(restore_scheduler_state):
                    restore_result = restore_scheduler_state(resolved_db)
                    if inspect.isawaitable(restore_result):
                        await restore_result
            except Exception as restore_exc:
                logger.debug(
                    "StrategyFactory parallel dispatch: scheduler state restore failed: %s",
                    restore_exc,
                )

            previous_result = self.last_result
            run_once_timeout_sec = self._resolve_run_once_timeout_sec()
            try:
                results, persistence_failures = await asyncio.wait_for(
                    self._execute_factory_run_once_mode(
                        resolved_db,
                        previous_result=previous_result,
                        execution_mode=resolved_mode,
                        target_codes=_normalize_target_codes(target_codes or [], limit=64),
                    ),
                    timeout=run_once_timeout_sec,
                )
            except asyncio.TimeoutError as timeout_exc:
                raise TimeoutError(
                    f"StrategyFactory parallel dispatch exceeded {run_once_timeout_sec:g}s"
                ) from timeout_exc

            summary = dict(results.get("summary") or {})
            summary["dispatch_id"] = dispatch_id
            summary["parallel_full_cycle"] = True
            summary["scheduler_feedback_update_skipped"] = "parallel_full_cycle"
            results["summary"] = summary
            self.last_run = self._now()
            self.last_result = results
            await self._persist_run_result(
                resolved_db,
                results,
                persistence_failures=persistence_failures,
            )
            return results

        async def dispatch_run(
            self,
            db=None,
            *,
            execution_mode=None,
            target_codes: Optional[list[str]] = None,
        ) -> dict[str, Any]:
            resolved_db = self._load_db() if db is None else db
            resolved_mode = resolve_factory_execution_mode(
                execution_mode,
                default=self.execution_mode,
            )
            normalized_target_codes = _normalize_target_codes(target_codes or [], limit=64)
            dispatch_id = f"factory_dispatch_{uuid4().hex[:12]}"
            requested_at = self._now().isoformat()
            concurrency_limit = self._resolve_dispatch_concurrency_limit()
            parallel_full_cycles = self._full_cycle_parallel_enabled()
            payload = {
                "dispatch_id": dispatch_id,
                "status": "queued",
                "execution_mode": resolved_mode.value,
                "requested_at": requested_at,
                "message": "Strategy Factory request queued.",
                "metadata": {
                    "engine_version": str(getattr(self, "engine_version", None) or FACTORY_ENGINE_VERSION),
                    "dispatch_concurrency_limit": concurrency_limit,
                    "parallel_full_cycles": parallel_full_cycles,
                    "target_codes": normalized_target_codes,
                },
            }
            persisted = await _call_optional_async(
                resolved_db,
                "create_strategy_factory_dispatch",
                payload,
                default=payload,
            )
            self._latest_dispatch_id = dispatch_id

            async def _run_dispatch() -> None:
                try:
                    semaphore = self._get_dispatch_semaphore()
                    async with semaphore:
                        self._active_dispatch_id = dispatch_id
                        await _call_optional_async(
                            resolved_db,
                            "update_strategy_factory_dispatch",
                            dispatch_id,
                            status="running",
                            started_at=self._now().isoformat(),
                            message="Strategy Factory dispatch running.",
                            metadata={
                                "engine_version": str(getattr(self, "engine_version", None) or FACTORY_ENGINE_VERSION),
                                "dispatch_concurrency_limit": concurrency_limit,
                                "parallel_full_cycles": parallel_full_cycles,
                                "target_codes": normalized_target_codes,
                            },
                            default=None,
                        )
                        if parallel_full_cycles:
                            result = await self._run_parallel_dispatch_cycle(
                                resolved_db,
                                resolved_mode=resolved_mode,
                                dispatch_id=dispatch_id,
                                target_codes=normalized_target_codes,
                            )
                        else:
                            result = await self.run_once(
                                resolved_db,
                                execution_mode=resolved_mode,
                                dispatch_id=dispatch_id,
                                target_codes=normalized_target_codes,
                            )
                        result_status_raw = str(result.get("status") or "").strip().lower()
                        result_status = (
                            result_status_raw
                            if result_status_raw in {"success", "partial", "skipped", "failed"}
                            else "success"
                        )
                        parity_result = dict(result.get("parity_result") or {})
                        await _call_optional_async(
                            resolved_db,
                            "update_strategy_factory_dispatch",
                            dispatch_id,
                            status=result_status,
                            completed_at=self._now().isoformat(),
                            run_id=str(result.get("run_id") or "").strip() or None,
                            message=f"Strategy Factory dispatch completed with status={result_status}.",
                            metadata={
                                "engine_version": str(getattr(self, "engine_version", None) or FACTORY_ENGINE_VERSION),
                                "dispatch_concurrency_limit": concurrency_limit,
                                "parallel_full_cycles": parallel_full_cycles,
                                "target_codes": normalized_target_codes,
                                "result_status": result.get("status"),
                                "parity_status": parity_result.get("status"),
                                "artifact_refs": list(result.get("artifact_refs") or []),
                                "degraded": result_status == "partial",
                            },
                            default=None,
                        )
                except Exception as exc:
                    logger.error(
                        "StrategyFactory dispatch %s failed: %s",
                        dispatch_id,
                        exc,
                        exc_info=True,
                    )
                    await _call_optional_async(
                        resolved_db,
                        "update_strategy_factory_dispatch",
                        dispatch_id,
                        status="failed",
                        completed_at=self._now().isoformat(),
                        message="Strategy Factory dispatch failed.",
                        error=str(exc),
                        metadata={
                            "engine_version": str(getattr(self, "engine_version", None) or FACTORY_ENGINE_VERSION),
                            "dispatch_concurrency_limit": concurrency_limit,
                            "parallel_full_cycles": parallel_full_cycles,
                            "target_codes": normalized_target_codes,
                            "error_type": exc.__class__.__name__,
                        },
                        default=None,
                    )
                finally:
                    self._dispatch_tasks.pop(dispatch_id, None)
                    if self._active_dispatch_id == dispatch_id:
                        active_ids = self._active_dispatch_ids()
                        self._active_dispatch_id = active_ids[-1] if active_ids else None

            task = asyncio.create_task(_run_dispatch(), name=f"strategy-factory-dispatch:{dispatch_id}")
            self._dispatch_tasks[dispatch_id] = task
            return {
                **dict(persisted or payload),
                "accepted": True,
                "queued": True,
                "already_running": False,
                "dispatch_concurrency_limit": concurrency_limit,
                "parallel_full_cycles": parallel_full_cycles,
                "active_dispatch_count": len(self._active_dispatch_ids()),
            }

        async def get_dispatch_status(self, dispatch_id: str, db=None) -> Optional[dict[str, Any]]:
            resolved_db = self._load_db() if db is None else db
            token = str(dispatch_id or "").strip()
            if not token:
                return None
            row = await _call_optional_async(
                resolved_db,
                "get_strategy_factory_dispatch",
                token,
                default=None,
            )
            if row is None:
                return None
            result = dict(row or {})
            task = self._dispatch_tasks.get(token)
            if task is not None and not task.done():
                result["background_task_active"] = True
            return result

        def status(self) -> dict:
            bulk_window_state = self._bulk_stock_matrix_run_window_state(self._now())
            bulk_stock_matrix_cursor = self._extract_bulk_stock_cursor(
                ((self.last_result or {}).get("summary") or {}),
                source="last_result" if self.last_result else "default",
                run_id=(self.last_result or {}).get("run_id"),
            )
            bulk_stock_matrix_config = {
                "enabled": bool(STOCK_STRATEGY_MATRIX_ENABLED),
                "universe_limit": int(STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT),
                "families_per_stock": int(STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK),
                "max_tasks_per_run": int(STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN),
                "max_candidates_per_run": int(STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN),
                "generation_limit_per_task": int(STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK),
                "batch_size": int(STOCK_STRATEGY_MATRIX_BATCH_SIZE),
                "bulk_concurrency": int(STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY),
                "run_window": str(STOCK_STRATEGY_MATRIX_RUN_WINDOW),
                "run_window_active": bool(bulk_window_state.get("run_window_active")),
                "run_window_current_period": bulk_window_state.get("current_period"),
                "tasks_per_shard": int(STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD),
                "pre_gate_enabled": bool(FACTORY_PRE_GATE_ENABLED),
            }
            last_summary = (self.last_result or {}).get("summary") if self.last_result else None
            latest_parity_result = dict((self.last_result or {}).get("parity_result") or {})
            effective_execution_mode = (
                str((self.last_result or {}).get("execution_mode") or "").strip()
                or resolve_factory_execution_mode(
                    getattr(self, "execution_mode", FactoryExecutionMode.LEGACY_PRIMARY),
                    default=FactoryExecutionMode.LEGACY_PRIMARY,
                ).value
            )
            active_dispatch_ids = self._active_dispatch_ids()
            return {
                "running": self._running,
                "schedule_mode": self.schedule_mode,
                "run_time": str(self.run_time),
                "execution_mode": effective_execution_mode,
                "engine_version": str(getattr(self, "engine_version", None) or FACTORY_ENGINE_VERSION),
                "runtime_enabled": is_factory_runtime_enabled(),
                "event_runtime_mode": resolve_event_runtime_mode(),
                "factor_auto_refresh_enabled": is_factory_factor_auto_refresh_enabled(),
                "factor_refresh_timeout_sec": FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
                "readiness_hard_block_enabled": is_factory_readiness_hard_block_enabled(),
                "readiness_min_score": FACTORY_READINESS_MIN_SCORE,
                "readiness_min_completion_ratio": FACTORY_READINESS_MIN_COMPLETION_RATIO,
                "last_run": str(self.last_run) if self.last_run else None,
                "last_result": self.last_result,
                "last_summary": last_summary,
                "latest_parity_result": latest_parity_result or None,
                "scheduler_slo": dict((last_summary or {}).get("scheduler_slo") or {}) if last_summary else None,
                "architecture_review": dict((last_summary or {}).get("architecture_review") or {}) if last_summary else None,
                "bulk_stock_matrix_config": bulk_stock_matrix_config,
                "bulk_stock_matrix_cursor": bulk_stock_matrix_cursor,
                "daily_run_count": self._daily_run_count,
                "max_daily_runs": self.max_daily_runs,
                "cycle_count": self._cycle_count,
                "active_dispatch_id": str(getattr(self, "_active_dispatch_id", "") or "").strip() or None,
                "active_dispatch_ids": active_dispatch_ids,
                "active_dispatch_count": len(active_dispatch_ids),
                "dispatch_concurrency_limit": self._resolve_dispatch_concurrency_limit(),
                "parallel_full_cycles": self._full_cycle_parallel_enabled(),
                "latest_dispatch_id": str(getattr(self, "_latest_dispatch_id", "") or "").strip() or None,
            }
