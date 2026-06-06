
        async def _run_autonomy_batches(self, db, snapshot: dict) -> dict:
            factory_pkg = get_strategy_factory_package()
            scanner = factory_pkg.MarketOpportunityScanner()
            scan_report = await scanner.scan(db, snapshot)
            autonomy_gateway = self._get_autonomy_gateway()
            factor_research = dict(snapshot.get("factor_research") or {})
            feedback_root = extract_feedback_root(
                factor_research.get("lifecycle_feedback_input")
                or factor_research.get("budget_feedback")
                or {}
            )
            recent_run_summaries = await self._load_recent_factory_run_summaries(db, limit=4)
            external_provider_health = self._external_llm_health_snapshot(autonomy_gateway)
            external_provider_control = self._build_external_provider_control(
                recent_run_summaries,
                external_provider_health,
            )
            generator_mode_controls = self._build_generator_mode_controls(
                recent_run_summaries,
                feedback_root=feedback_root,
            )
            scan_tasks = self._apply_scheduler_planning_controls(
                list(scan_report.get("tasks") or []),
                feedback_root=feedback_root,
                provider_control=external_provider_control,
                generator_mode_controls=generator_mode_controls,
            )
            tasks = list(scan_tasks)
            scan_summary = dict(scan_report.get("summary") or {})
            scan_feedback_summary = summarize_task_feedback_controls(scan_tasks)
            scan_summary.update(
                {
                    "feedback_control_mode_counts": dict(scan_feedback_summary.get("feedback_control_mode_counts") or {}),
                    "feedback_legacy_control_mode_counts": dict(
                        scan_feedback_summary.get("feedback_legacy_control_mode_counts")
                        or scan_feedback_summary.get("feedback_control_mode_counts")
                        or {}
                    ),
                    "feedback_skill_control_mode_counts": dict(
                        scan_feedback_summary.get("feedback_skill_control_mode_counts") or {}
                    ),
                    "feedback_target_pool_control_mode_counts": dict(
                        scan_feedback_summary.get("feedback_target_pool_control_mode_counts") or {}
                    ),
                    "feedback_holding_bucket_control_mode_counts": dict(
                        scan_feedback_summary.get("feedback_holding_bucket_control_mode_counts") or {}
                    ),
                    "feedback_generator_mode_control_mode_counts": dict(
                        scan_feedback_summary.get("feedback_generator_mode_control_mode_counts") or {}
                    ),
                    "feedback_skill_target_pool_control_mode_counts": dict(
                        scan_feedback_summary.get("feedback_skill_target_pool_control_mode_counts")
                        or {}
                    ),
                    "feedback_skill_holding_bucket_control_mode_counts": dict(
                        scan_feedback_summary.get("feedback_skill_holding_bucket_control_mode_counts")
                        or {}
                    ),
                    "feedback_skill_generator_mode_control_mode_counts": dict(
                        scan_feedback_summary.get("feedback_skill_generator_mode_control_mode_counts")
                        or {}
                    ),
                    "feedback_cooldown_task_count": int(
                        scan_feedback_summary.get("feedback_cooldown_task_count") or 0
                    ),
                    "feedback_blocked_task_count": int(
                        scan_feedback_summary.get("feedback_blocked_task_count") or 0
                    ),
                    "suppressed_families": list(scan_feedback_summary.get("suppressed_families") or []),
                    "suppressed_target_pools": list(scan_feedback_summary.get("suppressed_target_pools") or []),
                    "suppressed_generator_modes": list(scan_feedback_summary.get("suppressed_generator_modes") or []),
                    "external_llm_provider_control_mode": external_provider_control.get("control_mode"),
                    "external_llm_provider_control_reasons": list(
                        external_provider_control.get("control_reasons") or []
                    ),
                    "generator_mode_controls": dict(generator_mode_controls or {}),
                }
            )
            scan_report = {**scan_report, "summary": scan_summary, "tasks": scan_tasks}
            scan_task_artifact = dict(scan_report.get("task_artifact") or {})
            if not scan_task_artifact:
                scan_task_artifact = self._build_task_scan_artifact(
                    scan_report,
                    task_source_counts=dict(scan_summary.get("task_sources") or {}),
                    event_task_count=int(scan_summary.get("event_task_count") or 0),
                    snapshot_task_count=int((scan_summary.get("task_sources") or {}).get("snapshot") or 0),
                    bulk_stock_task_count=0,
                )
            scan_summary.update(
                {
                    "task_artifact_contract_version": scan_task_artifact.get("contract_version"),
                    "task_artifact_available": bool(scan_task_artifact.get("available")),
                }
            )
            scan_report = {
                **scan_report,
                "summary": scan_summary,
                "task_artifact": scan_task_artifact,
            }
            bulk_cursor = await self._resolve_bulk_stock_matrix_cursor(db)
            bulk_window_state = self._bulk_stock_matrix_run_window_state(self._now())
            runtime_mode_flags = resolve_runtime_mode_flags(
                snapshot.get("factory_execution_mode")
                or snapshot.get("execution_mode")
                or getattr(self, "execution_mode", None)
            )
            if bool(runtime_mode_flags.get("stock_first_observe_mode")) and not bool(
                bulk_window_state.get("run_window_active")
            ):
                bulk_window_state = {
                    **bulk_window_state,
                    "configured_enabled": True,
                    "run_window_active": True,
                    "skip_reason": None,
                    "activation_source": "stock_first_observe_mode",
                }
            resume_from_cursor = bool(
                bulk_cursor.get("available")
                and bulk_cursor.get("enabled")
                and str(bulk_cursor.get("source") or "").strip().lower() in {"last_result", "persisted_run"}
                and not bool(bulk_window_state.get("run_window_active"))
            )
            if resume_from_cursor:
                bulk_window_state = {
                    **bulk_window_state,
                    "configured_enabled": True,
                    "run_window_active": True,
                    "skip_reason": None,
                }
            bulk_report: dict[str, Any] = _build_default_bulk_report_payload(
                bulk_window_state,
                bulk_cursor,
            )
            if bool(bulk_window_state.get("run_window_active")):
                try:
                    bulk_report = await StockStrategyMatrixPlanner().plan(
                        db,
                        {
                            **snapshot,
                            "bulk_stock_matrix_task_offset": int(bulk_cursor.get("next_task_offset") or 0),
                            "bulk_stock_matrix_universe_offset": int(bulk_cursor.get("next_universe_offset") or 0),
                            "bulk_stock_matrix_cycle_index": int(self._cycle_count),
                            "bulk_stock_matrix_cursor_source": bulk_cursor.get("source"),
                            "bulk_stock_matrix_cursor_resume_from_run_id": bulk_cursor.get("resume_from_run_id"),
                        },
                    )
                except Exception as exc:
                    logger.warning("StrategyFactory: bulk stock-strategy matrix planning failed: %s", exc)
                    bulk_report = _build_bulk_planner_error_report_payload(
                        bulk_window_state,
                        bulk_cursor,
                        exc,
                    )
            bulk_report = _normalize_bulk_report_summary_payload(
                bulk_report,
                bulk_window_state,
                bulk_cursor,
            )
            full_market_score_rows = [
                dict(item or {})
                for item in list(bulk_report.pop("full_market_score_rows", []) or [])
                if isinstance(item, dict)
            ]
            full_market_topn = dict(bulk_report.get("full_market_topn") or {})
            run_id_hint = str(
                snapshot.get("factory_run_id") or snapshot.get("run_id") or ""
            ).strip()
            trace_id_hint = str(snapshot.get("trace_id") or "").strip()
            if full_market_topn and run_id_hint:
                full_market_topn["snapshot_id"] = (
                    str(full_market_topn.get("snapshot_id") or "").strip()
                    or f"fmt_{run_id_hint}"
                )
                full_market_topn["portfolio_candidate_id"] = (
                    str(full_market_topn.get("portfolio_candidate_id") or "").strip()
                    or f"factory_topn_{run_id_hint}"
                )
                full_market_topn["run_id"] = run_id_hint
                full_market_topn["trace_id"] = trace_id_hint or None
                full_market_topn["correlation_id"] = run_id_hint
            bulk_summary = dict(bulk_report.get("summary") or {})
            bulk_tasks = self._apply_scheduler_planning_controls(
                list(bulk_report.get("tasks") or []),
                feedback_root=feedback_root,
                provider_control=external_provider_control,
                generator_mode_controls=generator_mode_controls,
            )
            bulk_feedback_summary = summarize_task_feedback_controls(bulk_tasks)
            bulk_summary.update(
                {
                    "feedback_control_mode_counts": dict(bulk_feedback_summary.get("feedback_control_mode_counts") or {}),
                    "feedback_legacy_control_mode_counts": dict(
                        bulk_feedback_summary.get("feedback_legacy_control_mode_counts")
                        or bulk_feedback_summary.get("feedback_control_mode_counts")
                        or {}
                    ),
                    "feedback_skill_control_mode_counts": dict(
                        bulk_feedback_summary.get("feedback_skill_control_mode_counts") or {}
                    ),
                    "feedback_target_pool_control_mode_counts": dict(
                        bulk_feedback_summary.get("feedback_target_pool_control_mode_counts") or {}
                    ),
                    "feedback_holding_bucket_control_mode_counts": dict(
                        bulk_feedback_summary.get("feedback_holding_bucket_control_mode_counts") or {}
                    ),
                    "feedback_generator_mode_control_mode_counts": dict(
                        bulk_feedback_summary.get("feedback_generator_mode_control_mode_counts") or {}
                    ),
                    "feedback_skill_target_pool_control_mode_counts": dict(
                        bulk_feedback_summary.get("feedback_skill_target_pool_control_mode_counts")
                        or {}
                    ),
                    "feedback_skill_holding_bucket_control_mode_counts": dict(
                        bulk_feedback_summary.get("feedback_skill_holding_bucket_control_mode_counts")
                        or {}
                    ),
                    "feedback_skill_generator_mode_control_mode_counts": dict(
                        bulk_feedback_summary.get("feedback_skill_generator_mode_control_mode_counts")
                        or {}
                    ),
                    "feedback_cooldown_task_count": int(
                        bulk_feedback_summary.get("feedback_cooldown_task_count") or 0
                    ),
                    "feedback_blocked_task_count": int(
                        bulk_feedback_summary.get("feedback_blocked_task_count") or 0
                    ),
                    "suppressed_families": list(bulk_feedback_summary.get("suppressed_families") or []),
                    "suppressed_target_pools": list(bulk_feedback_summary.get("suppressed_target_pools") or []),
                    "suppressed_generator_modes": list(bulk_feedback_summary.get("suppressed_generator_modes") or []),
                    "external_llm_provider_control_mode": external_provider_control.get("control_mode"),
                    "external_llm_provider_control_reasons": list(
                        external_provider_control.get("control_reasons") or []
                    ),
                    "generator_mode_controls": dict(generator_mode_controls or {}),
                }
            )
            bulk_report = {**bulk_report, "summary": bulk_summary, "tasks": bulk_tasks}
            bulk_task_artifact = dict(bulk_report.get("task_artifact") or {})
            if not bulk_task_artifact and bool((bulk_report.get("summary") or {}).get("enabled")):
                bulk_task_artifact = self._build_task_scan_artifact(
                    bulk_report,
                    task_source_counts={"bulk_stock_matrix": len(bulk_tasks)},
                    event_task_count=0,
                    snapshot_task_count=0,
                    bulk_stock_task_count=len(bulk_tasks),
                )
            if bulk_task_artifact:
                bulk_summary.update(
                    {
                        "task_artifact_contract_version": bulk_task_artifact.get("contract_version"),
                        "task_artifact_available": bool(bulk_task_artifact.get("available")),
                    }
                )
                bulk_report = {
                    **bulk_report,
                    "summary": bulk_summary,
                    "task_artifact": bulk_task_artifact,
                }
            if bulk_tasks:
                tasks, task_budget_meta = self._merge_autonomy_tasks_with_budget(
                    scanner,
                    scan_tasks,
                    bulk_tasks,
                )
            else:
                tasks = [
                    dict(task or {})
                    for task in list(scan_tasks or [])
                    if not bool(dict(task or {}).get("feedback_generation_blocked"))
                    and _normalize_feedback_text(dict(task or {}).get("feedback_control_mode")) not in {"suppress", "freeze"}
                ]
                task_budget_meta = _build_scan_only_task_budget_meta_payload(scan_tasks, tasks)
            task_source_counts = dict(scan_summary.get("task_sources") or scanner._build_task_source_counts(tasks))
            if bulk_tasks:
                task_source_counts = scanner._build_task_source_counts(tasks)
            event_task_count = int(scan_summary.get("event_task_count") or task_source_counts.get("event_driven", 0))
            combined_scan_report = _build_combined_scan_report_payload(
                scan_summary=scan_summary,
                tasks=tasks,
                task_source_counts=task_source_counts,
                event_task_count=event_task_count,
                bulk_tasks=bulk_tasks,
                bulk_report=bulk_report,
                bulk_cursor=bulk_cursor,
                task_budget_meta=task_budget_meta,
                external_provider_control=external_provider_control,
                generator_mode_controls=generator_mode_controls,
                opportunity_scan=scan_report,
            )
            autonomy_gateway = self._get_autonomy_gateway()
            generated_candidates: List[dict] = []
            all_experiments: List[dict] = []
            task_results: List[dict] = []
            external_status_counts: Dict[str, int] = {}
            total_attempt_count = 0
            total_network_request_count = 0
            total_real_request_count = 0
            total_compatibility_skip_count = 0
            total_cooldown_skip_count = 0
            total_compatibility_failure_count = 0
            total_effective_response_count = 0
            total_empty_200_response_count = 0
            total_request_status_counts: Dict[str, int] = {}
            total_selected_count = 0
            total_evidence_count = 0
            last_error_type = None
            last_error = None
            elapsed_seconds = 0.0
            persistence_failures: List[dict[str, Any]] = []
            _agg_lock = asyncio.Lock()
            shared_generation_context_preloaded = await self._prepare_shared_generation_context(autonomy_gateway, db, snapshot)
            has_bulk_tasks = bool([task for task in tasks if str(task.get("task_source") or "").strip().lower() == "bulk_stock_matrix"])
            effective_research_concurrency = self._resolve_research_task_concurrency(
                autonomy_gateway,
                has_bulk_tasks=has_bulk_tasks,
            )
            effective_bulk_research_concurrency = self._resolve_bulk_research_task_concurrency(
                autonomy_gateway,
                has_bulk_tasks=has_bulk_tasks,
            )
            split_bulk_concurrency = bool(
                has_bulk_tasks and effective_bulk_research_concurrency != effective_research_concurrency
            )
            sem = asyncio.Semaphore(effective_research_concurrency)
            bulk_sem = asyncio.Semaphore(effective_bulk_research_concurrency) if split_bulk_concurrency else sem

            async def _run_one_task(task: dict) -> None:
                nonlocal total_attempt_count, total_network_request_count
                nonlocal total_real_request_count
                nonlocal total_compatibility_skip_count, total_cooldown_skip_count
                nonlocal total_compatibility_failure_count, total_effective_response_count, total_empty_200_response_count
                nonlocal total_selected_count, total_evidence_count
                nonlocal last_error_type, last_error, elapsed_seconds
                task_source = str(dict(task or {}).get("task_source") or "").strip().lower()
                task_sem = bulk_sem if task_source == "bulk_stock_matrix" else sem
                def _record_task_persistence_failure(operation: str, exc: Exception) -> None:
                    logger.warning("StrategyFactory: %s failed: %s", operation, exc)
                    self._record_persistence_failure(
                        persistence_failures,
                        operation,
                        exc,
                        stage="autonomy",
                    )

                execution = await _execute_autonomy_task_payload(
                    _AutonomyTaskExecutionContext(
                        task=dict(task or {}),
                        task_semaphore=task_sem,
                        db=db,
                        snapshot=snapshot,
                        autonomy_gateway=autonomy_gateway,
                        persist_task_evidence=self._persist_task_evidence,
                        extract_event_context=_extract_event_context,
                        call_optional_async=_call_optional_async,
                        record_persistence_failure=_record_task_persistence_failure,
                        generate_for_research_task=self._generate_for_research_task,
                        extract_cycle_llm_generation=self._extract_cycle_llm_generation,
                        extract_cycle_lifecycle=self._extract_cycle_lifecycle,
                        extract_cycle_generated_count=self._extract_cycle_generated_count,
                        extract_cycle_reviewed_count=self._extract_cycle_reviewed_count,
                        extract_cycle_candidates=self._extract_cycle_candidates,
                        extract_cycle_experiments=self._extract_cycle_experiments,
                        enrich_candidate_targeting=self._enrich_candidate_targeting,
                        build_research_task_run_result_summary=self._build_research_task_run_result_summary,
                        summarize_request_status_counts=self._summarize_external_request_status_counts,
                        count_network_requests=self._count_external_network_requests,
                        count_real_requests=self._count_external_real_requests,
                        request_is_compatibility_failure=self._request_is_compatibility_failure,
                        request_is_empty_200_response=self._request_is_empty_200_response,
                        normalize_external_request_status=self._normalize_external_request_status,
                        summarize_autonomy_lifecycle=summarize_autonomy_lifecycle,
                        autonomy_phase_order=AUTONOMY_PHASE_ORDER,
                    )
                )
                async with _agg_lock:
                    generated_candidates.extend(execution.generated_candidates)
                    all_experiments.extend(execution.experiments)
                    external_status_counts[execution.external_status] = (
                        external_status_counts.get(execution.external_status, 0) + 1
                    )
                    total_attempt_count += int(execution.request_metrics.get("attempt_count") or 0)
                    total_network_request_count += int(
                        execution.request_metrics.get("network_request_count") or 0
                    )
                    total_real_request_count += int(execution.request_metrics.get("real_request_count") or 0)
                    total_compatibility_skip_count += int(
                        execution.request_metrics.get("compatibility_skip_count") or 0
                    )
                    total_cooldown_skip_count += int(
                        execution.request_metrics.get("cooldown_skip_count") or 0
                    )
                    total_compatibility_failure_count += int(
                        execution.request_metrics.get("compatibility_failure_count") or 0
                    )
                    total_effective_response_count += int(
                        execution.request_metrics.get("effective_response_count") or 0
                    )
                    total_empty_200_response_count += int(
                        execution.request_metrics.get("empty_200_response_count") or 0
                    )
                    for request_status, count in dict(
                        execution.request_metrics.get("request_status_counts") or {}
                    ).items():
                        total_request_status_counts[request_status] = (
                            total_request_status_counts.get(request_status, 0) + int(count or 0)
                        )
                    total_selected_count += int(execution.selected_count or 0)
                    total_evidence_count += int(execution.evidence_count or 0)
                    if execution.last_error_type:
                        last_error_type = execution.last_error_type
                        last_error = execution.last_error
                    elapsed_seconds += float(execution.elapsed_seconds or 0.0)
                    task_results.append(execution.task_result_summary)

            # 有界并发执行所有研究任务
            if tasks:
                logger.info(
                    "StrategyFactory: running %d research tasks with concurrency=%d",
                    len(tasks), effective_research_concurrency,
                )
                await asyncio.gather(*[_run_one_task(t) for t in tasks])

            lifecycle_metrics = self._aggregate_task_lifecycle_metrics(task_results)
            selected_feedback_summary = summarize_task_feedback_controls(tasks)
            stage = _build_autonomy_stage_summary_payload(
                task_results=task_results,
                task_source_counts=task_source_counts,
                event_task_count=event_task_count,
                bulk_report=bulk_report,
                bulk_cursor=bulk_cursor,
                generated_candidates=generated_candidates,
                all_experiments=all_experiments,
                external_status_counts=external_status_counts,
                total_attempt_count=total_attempt_count,
                total_network_request_count=total_network_request_count,
                total_real_request_count=total_real_request_count,
                total_compatibility_skip_count=total_compatibility_skip_count,
                total_cooldown_skip_count=total_cooldown_skip_count,
                total_compatibility_failure_count=total_compatibility_failure_count,
                total_effective_response_count=total_effective_response_count,
                total_empty_200_response_count=total_empty_200_response_count,
                total_request_status_counts=total_request_status_counts,
                total_selected_count=total_selected_count,
                total_evidence_count=total_evidence_count,
                last_error_type=last_error_type,
                last_error=last_error,
                elapsed_seconds=elapsed_seconds,
                external_provider_health=external_provider_health,
                effective_research_concurrency=effective_research_concurrency,
                has_bulk_tasks=has_bulk_tasks,
                effective_bulk_research_concurrency=effective_bulk_research_concurrency,
                bulk_tasks_use_external_llm=self._bulk_tasks_use_external_llm(autonomy_gateway),
                research_task_timeout_sec=self._resolve_research_task_timeout_sec(),
                task_budget_meta=task_budget_meta,
                selected_feedback_summary=selected_feedback_summary,
                external_provider_control=external_provider_control,
                generator_mode_controls=generator_mode_controls,
                shared_generation_context_preloaded=shared_generation_context_preloaded,
                persistence_failures=persistence_failures,
                lifecycle_metrics=lifecycle_metrics,
                combined_scan_report=combined_scan_report,
            )
            stage = _attach_autonomy_stage_artifacts_payload(
                stage=stage,
                scan_task_artifact=scan_task_artifact,
                bulk_task_artifact=bulk_task_artifact,
                generated_candidates=generated_candidates,
                all_experiments=all_experiments,
                build_task_artifact=build_task_artifact,
                build_candidate_artifact=build_candidate_artifact,
                build_research_evidence_artifact=build_research_evidence_artifact,
            )
            if full_market_topn:
                stage["full_market_topn"] = full_market_topn
            return {
                "stage": stage,
                "candidates": generated_candidates,
                "experiments": all_experiments,
                "full_market_topn": full_market_topn,
                "full_market_score_rows": full_market_score_rows,
            }

        async def run_once(self, db=None, *, execution_mode=None, dispatch_id: Optional[str] = None, target_codes: Optional[list[str]] = None) -> dict:
            """执行一次完整的策略工厂流程。"""
            current_loop = asyncio.get_running_loop()
            run_once_lock = self._get_run_once_task_lock()
            async with run_once_lock:
                task = self._run_once_task
                if task is not None and not task.done():
                    try:
                        task_loop = task.get_loop()
                    except Exception:
                        task_loop = current_loop
                    if task_loop is not current_loop:
                        logger.info(
                            "StrategyFactory run_once already in progress on another event loop; skipping join"
                        )
                        return {
                            "status": "skipped",
                            "reason": "run_once_in_progress_other_event_loop",
                            "summary": {
                                "skipped": True,
                                "skip_reason": "run_once_in_progress_other_event_loop",
                                "last_run": self.last_run.isoformat() if self.last_run else None,
                                "last_status": (self.last_result or {}).get("status")
                                if isinstance(self.last_result, dict)
                                else None,
                            },
                        }
                    logger.info("StrategyFactory run_once already in progress; joining in-flight execution")
                else:
                    async def _execute_once() -> dict:
                        resolved_db = self._load_db() if db is None else db
                        try:
                            restore_scheduler_state = getattr(self, "_restore_scheduler_state", None)
                            if callable(restore_scheduler_state):
                                restore_result = restore_scheduler_state(resolved_db)
                                if inspect.isawaitable(restore_result):
                                    await restore_result
                        except Exception as restore_exc:
                            logger.debug(
                                "StrategyFactory run_once: scheduler state restore failed: %s",
                                restore_exc,
                            )
                        previous_result = self.last_result
                        resolved_mode = resolve_factory_execution_mode(
                            execution_mode,
                            default=self.execution_mode,
                        )
                        board_task = None
                        claim_token = None
                        heartbeat_task = None
                        task_board = getattr(self, "_task_board", None)
                        try:
                            logger.info(
                                "StrategyFactory run_once: preparing execution mode=%s dispatch_id=%s target_codes=%d",
                                getattr(resolved_mode, "value", str(resolved_mode)),
                                dispatch_id or "-",
                                len(_normalize_target_codes(target_codes or [], limit=64)),
                            )
                            if task_board is not None:
                                claim_ttl_seconds = max(
                                    300,
                                    int(os.getenv("STRATEGY_FACTORY_TASK_BOARD_CLAIM_TTL_SEC", "1800") or 1800),
                                )
                                try:
                                    reclaimed = task_board.reclaim_stale(
                                        block_task_types=("research", "quality_gate"),
                                        block_reason=(
                                            "stale factory task reclaimed before new "
                                            "StrategyFactory run_once"
                                        ),
                                    )
                                    if reclaimed:
                                        logger.warning(
                                            "StrategyFactory run_once: reclaimed %d stale task_board tasks before start",
                                            len(reclaimed),
                                        )
                                except Exception as reclaim_exc:
                                    logger.debug(
                                        "StrategyFactory run_once: task_board stale reclaim failed: %s",
                                        reclaim_exc,
                                    )
                                try:
                                    def _pid_exists(pid: int) -> bool:
                                        if pid <= 0:
                                            return False
                                        if os.name == "nt":
                                            try:
                                                import ctypes

                                                kernel32 = ctypes.windll.kernel32
                                                handle = kernel32.OpenProcess(0x1000, False, pid)
                                                if handle:
                                                    kernel32.CloseHandle(handle)
                                                    return True
                                                return False
                                            except Exception:
                                                return True
                                        try:
                                            os.kill(pid, 0)
                                            return True
                                        except OSError:
                                            return False

                                    current_pid = os.getpid()
                                    active_run_once_tasks = task_board.list_tasks(
                                        statuses=("ready", "running"),
                                        task_type="research",
                                        title="Strategy factory run_once",
                                        limit=20,
                                    )
                                    blocked_active_count = 0
                                    for active_task in active_run_once_tasks:
                                        active_payload = dict(active_task.get("payload") or {})
                                        owner_pid = active_payload.get("owner_pid")
                                        try:
                                            owner_pid_int = int(owner_pid) if owner_pid is not None else 0
                                        except Exception:
                                            owner_pid_int = 0
                                        if owner_pid_int == current_pid:
                                            continue
                                        if owner_pid_int > 0 and _pid_exists(owner_pid_int):
                                            continue
                                        task_board.block_task(
                                            active_task["task_id"],
                                            "superseded by new StrategyFactory run_once after prior runner exit",
                                            claim_token=active_task.get("claim_token"),
                                        )
                                        blocked_active_count += 1
                                    if blocked_active_count:
                                        logger.warning(
                                            "StrategyFactory run_once: blocked %d active predecessor task_board run_once tasks",
                                            blocked_active_count,
                                        )
                                except Exception as predecessor_exc:
                                    logger.debug(
                                        "StrategyFactory run_once: active predecessor task_board cleanup failed: %s",
                                        predecessor_exc,
                                    )
                                board_task = task_board.create_task(
                                    task_type="research",
                                    title="Strategy factory run_once",
                                    payload={
                                        "execution_mode": getattr(resolved_mode, "value", str(resolved_mode)),
                                        "dispatch_id": dispatch_id,
                                        "owner_pid": os.getpid(),
                                        "target_codes": _normalize_target_codes(target_codes or [], limit=64),
                                    },
                                )
                                claimed_task = task_board.claim_task(
                                    board_task["task_id"],
                                    worker_id="strategy_factory_scheduler",
                                    ttl_seconds=claim_ttl_seconds,
                                )
                                if claimed_task is not None:
                                    board_task = claimed_task
                                    claim_token = claimed_task.get("claim_token")
                                logger.info(
                                    "StrategyFactory run_once: task board claimed task_id=%s ttl=%ss",
                                    (board_task or {}).get("task_id"),
                                    claim_ttl_seconds,
                                )
                                try:
                                    configured_heartbeat_seconds = int(
                                        os.getenv(
                                            "STRATEGY_FACTORY_TASK_BOARD_HEARTBEAT_SEC",
                                            "60",
                                        )
                                        or 60
                                    )
                                except Exception:
                                    configured_heartbeat_seconds = 60
                                try:
                                    minimum_heartbeat_seconds = int(
                                        os.getenv(
                                            "STRATEGY_FACTORY_TASK_BOARD_HEARTBEAT_MIN_SEC",
                                            "30",
                                        )
                                        or 30
                                    )
                                except Exception:
                                    minimum_heartbeat_seconds = 30
                                minimum_heartbeat_seconds = max(1, minimum_heartbeat_seconds)
                                heartbeat_interval_seconds = max(
                                    minimum_heartbeat_seconds,
                                    min(
                                        max(minimum_heartbeat_seconds, claim_ttl_seconds // 3),
                                        configured_heartbeat_seconds,
                                    ),
                                )

                                async def _heartbeat_task_board_claim() -> None:
                                    while True:
                                        await asyncio.sleep(heartbeat_interval_seconds)
                                        try:
                                            task_board.heartbeat(
                                                board_task["task_id"],
                                                claim_token,
                                                ttl_seconds=claim_ttl_seconds,
                                            )
                                        except Exception as heartbeat_exc:
                                            logger.debug(
                                                "StrategyFactory run_once: task_board heartbeat failed: %s",
                                                heartbeat_exc,
                                            )

                                heartbeat_task = asyncio.create_task(
                                    _heartbeat_task_board_claim(),
                                    name=f"strategy-factory-task-board-heartbeat:{board_task['task_id']}",
                                )
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
                                    f"StrategyFactory run_once exceeded {run_once_timeout_sec:g}s"
                                ) from timeout_exc
                            logger.info(
                                "StrategyFactory run_once: cycle returned run_id=%s status=%s",
                                results.get("run_id"),
                                results.get("status"),
                            )
                            try:
                                _alpha = 0.3
                                _ema_floor = float(os.getenv("STRATEGY_FACTORY_EMA_FLOOR", "0.15") or 0.15)
                                _exploration_reset_interval = int(
                                    os.getenv("STRATEGY_FACTORY_EMA_EXPLORATION_RESET_INTERVAL", "20") or 20
                                )
                                completed_cycle_count = max(0, int(getattr(self, "_cycle_count", 0) or 0)) + 1
                                updated_feedback, feedback_update = update_scheduler_family_gate_feedback(
                                    dict(getattr(self, "_family_gate_feedback", {}) or {}),
                                    results,
                                    cycle_count=completed_cycle_count,
                                    alpha=_alpha,
                                    ema_floor=_ema_floor,
                                    exploration_reset_interval=_exploration_reset_interval,
                                )
                                self._family_gate_feedback = updated_feedback
                                self._cycle_count = completed_cycle_count
                                summary = dict(results.get("summary") or {})
                                summary["family_gate_feedback_update"] = feedback_update
                                summary["scheduler_cycle_count"] = self._cycle_count
                                feedback_control_counts = dict(feedback_update.get("control_counts") or {})
                                summary["family_gate_feedback_control_counts"] = feedback_control_counts
                                summary["family_gate_feedback_updated_family_count"] = int(
                                    feedback_update.get("updated_family_count") or 0
                                )
                                summary["family_gate_feedback_tracked_family_count"] = int(
                                    feedback_update.get("tracked_family_count") or 0
                                )
                                summary["family_gate_feedback_active_families"] = list(
                                    feedback_update.get("active_families") or []
                                )
                                summary["family_gate_feedback_gate_3_input"] = int(
                                    feedback_update.get("gate_3_input") or 0
                                )
                                summary["family_gate_feedback_gate_3_passed"] = int(
                                    feedback_update.get("gate_3_passed") or 0
                                )
                                summary["family_gate_feedback_gate_3_failed"] = int(
                                    feedback_update.get("gate_3_failed") or 0
                                )
                                summary["family_gate_feedback_submitted"] = int(
                                    feedback_update.get("submitted") or 0
                                )
                                summary["family_gate_feedback_created_audit_only"] = int(
                                    feedback_update.get("created_audit_only") or 0
                                )
                                summary["family_gate_feedback_failure_reason_topn"] = list(
                                    feedback_update.get("gate_3_failure_reason_topn") or []
                                )
                                results["summary"] = summary
                            except Exception as feedback_exc:
                                logger.debug(
                                    "StrategyFactory run_once: family gate feedback update failed: %s",
                                    feedback_exc,
                                )
                            if task_board is not None and board_task is not None:
                                task_board.heartbeat(
                                    board_task["task_id"],
                                    claim_token,
                                    ttl_seconds=claim_ttl_seconds,
                                )
                            self.last_run = self._now()
                            self.last_result = results
                            await self._persist_run_result(
                                resolved_db,
                                results,
                                persistence_failures=persistence_failures,
                            )
                            logger.info(
                                "StrategyFactory run_once: persisted run_id=%s status=%s artifact_refs=%d",
                                results.get("run_id"),
                                results.get("status"),
                                len(results.get("artifact_refs") or []),
                            )
                            if task_board is not None and board_task is not None:
                                summary = dict(results.get("summary") or {})
                                completed_task = task_board.complete_task(
                                    board_task["task_id"],
                                    claim_token=claim_token,
                                    artifact_refs=list(results.get("artifact_refs") or []),
                                    result={
                                        "run_id": results.get("run_id"),
                                        "status": results.get("status"),
                                        "completed_at": results.get("completed_at"),
                                        "elapsed_seconds": results.get("elapsed_seconds"),
                                        "summary": {
                                            "trace_id": summary.get("trace_id"),
                                            "snapshot_completion_ratio": summary.get("snapshot_completion_ratio"),
                                            "snapshot_degraded": summary.get("snapshot_degraded"),
                                            "candidates_spawned": summary.get("candidates_spawned"),
                                            "autonomy_generated": summary.get("autonomy_generated"),
                                            "autonomy_task_count": summary.get("autonomy_task_count"),
                                            "autonomy_completed_task_count": summary.get("autonomy_completed_task_count"),
                                            "autonomy_failed_task_count": summary.get("autonomy_failed_task_count"),
                                        },
                                    },
                                )
                                results["task_board"] = {
                                    "task_id": board_task["task_id"],
                                    "status": (completed_task or {}).get("status"),
                                }
                                logger.info(
                                    "StrategyFactory run_once: task board completed task_id=%s status=%s",
                                    board_task["task_id"],
                                    (completed_task or {}).get("status"),
                                )
                        except asyncio.CancelledError:
                            if task_board is not None and board_task is not None:
                                try:
                                    task_board.block_task(
                                        board_task["task_id"],
                                        "StrategyFactory run_once cancelled before completion",
                                        claim_token=claim_token,
                                    )
                                except Exception as block_exc:
                                    logger.debug("StrategyFactory run_once: task_board cancel block failed: %s", block_exc)
                            raise
                        except Exception as exc:
                            if task_board is not None and board_task is not None:
                                try:
                                    task_board.block_task(board_task["task_id"], str(exc), claim_token=claim_token)
                                except Exception as block_exc:
                                    logger.debug("StrategyFactory run_once: task_board.block_task failed: %s", block_exc)
                            raise
                        finally:
                            if heartbeat_task is not None:
                                heartbeat_task.cancel()
                                with suppress(asyncio.CancelledError):
                                    await heartbeat_task

                        # P2-D：用本次孵化预算 family 计数更新反馈 EMA（α=0.3）
                        # 优化 3：EMA 饥饿保护（下限 + 周期性探索重置）
                        try:
                            family_counts: Dict[str, int] = dict(
                                (results.get("summary") or {}).get("incubation_budget_family_counts") or {}
                            )
                            if False and family_counts:
                                _alpha = 0.3
                                _ema_floor = float(os.getenv("STRATEGY_FACTORY_EMA_FLOOR", "0.15") or 0.15)
                                _exploration_reset_interval = int(
                                    os.getenv("STRATEGY_FACTORY_EMA_EXPLORATION_RESET_INTERVAL", "20") or 20
                                )
                                for family, count in family_counts.items():
                                    prev = dict(self._family_gate_feedback.get(family) or {})
                                    prev_ema = float(prev.get("ema_submit_count") or 0.0)
                                    new_ema = round(_alpha * float(count) + (1.0 - _alpha) * prev_ema, 4)
                                    self._family_gate_feedback[family] = {"ema_submit_count": new_ema}
                                # 衰减未出现的 family（带下限保护）
                                for family in list(self._family_gate_feedback):
                                    if family not in family_counts:
                                        prev_ema = float((self._family_gate_feedback[family] or {}).get("ema_submit_count") or 0.0)
                                        new_ema = max(_ema_floor, round((1.0 - _alpha) * prev_ema, 4))
                                        self._family_gate_feedback[family]["ema_submit_count"] = new_ema
                                # 周期性探索重置：每 N 轮重置低 EMA 的 family
                                if _exploration_reset_interval > 0 and self._cycle_count % _exploration_reset_interval == 0:
                                    for family, data in self._family_gate_feedback.items():
                                        if data.get("ema_submit_count", 0) < _ema_floor + 0.05:
                                            data["ema_submit_count"] = 0.5
                        except Exception as ema_exc:
                            logger.debug("StrategyFactory run_once: family gate feedback EMA update failed: %s", ema_exc)

                        # 优化 4：EMA 反馈状态持久化
                        try:
                            _save_scheduler_state = getattr(resolved_db, "save_scheduler_state", None)
                            if callable(_save_scheduler_state):
                                import inspect as _inspect
                                _state_payload = {
                                    "family_gate_feedback": self._family_gate_feedback,
                                    "cycle_count": self._cycle_count,
                                    "consecutive_failures": self._consecutive_failures,
                                    "circuit_state": getattr(self, "_circuit_state", "closed"),
                                }
                                _save_result = _save_scheduler_state(_state_payload)
                                if _inspect.isawaitable(_save_result):
                                    await _save_result
                                self._metrics.ema_feedback_persisted = True
                        except Exception as persist_exc:
                            logger.debug("StrategyFactory run_once: scheduler state persistence failed: %s", persist_exc)
                            self._metrics.ema_feedback_persisted = False

                        if dispatch_id:
                            summary = dict(results.get("summary") or {})
                            summary["dispatch_id"] = dispatch_id
                            results["summary"] = summary
                        logger.info(
                            "StrategyFactory run_once: returning run_id=%s status=%s",
                            results.get("run_id"),
                            results.get("status"),
                        )
                        return results

                    task = asyncio.create_task(_execute_once(), name="strategy-factory-run-once")
                    self._run_once_task = task

            try:
                return await asyncio.shield(task)
            finally:
                async with run_once_lock:
                    if self._run_once_task is task and task.done():
                        self._run_once_task = None
