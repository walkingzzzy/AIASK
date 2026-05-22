
        async def dispatch_run(self, db=None, *, execution_mode=None) -> dict[str, Any]:
            resolved_db = self._load_db() if db is None else db
            current_dispatch_id = str(getattr(self, "_active_dispatch_id", "") or "").strip()
            if current_dispatch_id:
                current = await _call_optional_async(
                    resolved_db,
                    "get_strategy_factory_dispatch",
                    current_dispatch_id,
                    default=None,
                )
                if current:
                    return {
                        **dict(current or {}),
                        "accepted": True,
                        "already_running": True,
                        "queued": False,
                    }

            resolved_mode = resolve_factory_execution_mode(
                execution_mode,
                default=self.execution_mode,
            )
            dispatch_id = f"factory_dispatch_{uuid4().hex[:12]}"
            requested_at = self._now().isoformat()
            payload = {
                "dispatch_id": dispatch_id,
                "status": "queued",
                "execution_mode": resolved_mode.value,
                "requested_at": requested_at,
                "message": "策略工厂请求已受理，正在后台调度。",
                "metadata": {
                    "engine_version": str(getattr(self, "engine_version", None) or FACTORY_ENGINE_VERSION),
                },
            }
            persisted = await _call_optional_async(
                resolved_db,
                "create_strategy_factory_dispatch",
                payload,
                default=payload,
            )
            self._latest_dispatch_id = dispatch_id
            self._active_dispatch_id = dispatch_id

            async def _run_dispatch() -> None:
                try:
                    await _call_optional_async(
                        resolved_db,
                        "update_strategy_factory_dispatch",
                        dispatch_id,
                        status="running",
                        started_at=self._now().isoformat(),
                        message="策略工厂正在后台运行。",
                        metadata={
                            "engine_version": str(getattr(self, "engine_version", None) or FACTORY_ENGINE_VERSION),
                        },
                        default=None,
                    )
                    result = await self.run_once(
                        resolved_db,
                        execution_mode=resolved_mode,
                        dispatch_id=dispatch_id,
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
                        message=f"策略工厂后台运行完成，状态={result_status}。",
                        metadata={
                            "engine_version": str(getattr(self, "engine_version", None) or FACTORY_ENGINE_VERSION),
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
                        message="策略工厂后台运行失败。",
                        error=str(exc),
                        metadata={
                            "engine_version": str(getattr(self, "engine_version", None) or FACTORY_ENGINE_VERSION),
                            "error_type": exc.__class__.__name__,
                        },
                        default=None,
                    )
                finally:
                    self._dispatch_tasks.pop(dispatch_id, None)
                    if self._active_dispatch_id == dispatch_id:
                        self._active_dispatch_id = None

            task = asyncio.create_task(_run_dispatch(), name=f"strategy-factory-dispatch:{dispatch_id}")
            self._dispatch_tasks[dispatch_id] = task
            return {
                **dict(persisted or payload),
                "accepted": True,
                "queued": True,
                "already_running": False,
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
                result["status"] = "running"
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
                "latest_dispatch_id": str(getattr(self, "_latest_dispatch_id", "") or "").strip() or None,
            }
