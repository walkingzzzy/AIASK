
    @mcp.tool(
        title="Factor Candidate Workflow",
        description="AI-facing factor candidate workflow for generation, validation, registry review and scheduler checks.",
        structured_output=True,
        meta=build_tool_meta("factor_candidate_workflow"),
    )
    async def factor_candidate_workflow(
        task: str = "pipeline",
        code: str | None = None,
        codes: list[str] | None = None,
        artifact_id: str | None = None,
        candidate_index: int = 0,
        candidate_count: int = 6,
        lookback_bars: int | None = None,
        horizon_days: int | None = None,
        max_dates: int | None = None,
        allow_fallback: bool = True,
        persist_artifact: bool = True,
        write_memory: bool = True,
        run_scheduler_now: bool = False,
        idempotency_key: str | None = None,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        workflow_deadline = started_at + 38.0
        workflow_task = str(task or "pipeline").strip().lower()
        normalized_codes = _normalize_codes(code=code, codes=codes) or ["600519"]
        steps: list[dict[str, Any]] = []
        source_chain = ["workflow.factor_candidate", "manager.quant_manager"]
        lineage_ctx = LineageContext.create(
            "factor_candidate_workflow",
            security_codes=list(normalized_codes),
        )
        try:
            generation_response: dict[str, Any] | None = None
            validation_response: dict[str, Any] | None = None
            registry_response: dict[str, Any] | None = None
            registry_pool_response: dict[str, Any] | None = None
            registry_item_response: dict[str, Any] | None = None
            memory_response: dict[str, Any] | None = None
            memory_item_response: dict[str, Any] | None = None

            if workflow_task in {"pipeline", "generate"}:
                generation_response = await _run_workflow_stage(
                    step="quant_manager.llm_factor_mining",
                    deadline=workflow_deadline,
                    stage_timeout=12.0,
                    coro=quant_manager(
                        action="llm_factor_mining",
                        params={
                            "codes": normalized_codes,
                            "artifact_id": artifact_id,
                            "candidate_count": max(1, min(int(candidate_count or 6), 24)),
                            "lookback_bars": int(lookback_bars) if lookback_bars is not None else None,
                            "allow_fallback": bool(allow_fallback),
                            "workflow_fast_mode": True,
                            "startup_warmup": False,
                            "explain": False,
                            "persist_artifact": bool(persist_artifact),
                        },
                    ),
                )
                steps.append(_step("quant_manager.llm_factor_mining", generation_response))
                gen_artifact_id = _response_data(generation_response).get("artifact_id")
                if gen_artifact_id:
                    lineage_ctx.set_artifact(str(gen_artifact_id))
                    lineage_ctx.extra["generation_artifact_id"] = str(gen_artifact_id)

            resolved_artifact_id = str(
                artifact_id
                or lineage_ctx.artifact_id
                or ""
            ).strip() or None

            if workflow_task in {"pipeline", "validate"} and resolved_artifact_id:
                validation_response = await _run_workflow_stage(
                    step="quant_manager.validate_factor_candidate",
                    deadline=workflow_deadline,
                    stage_timeout=10.0,
                    coro=quant_manager(
                        action="validate_factor_candidate",
                        params={
                            "artifact_id": resolved_artifact_id,
                            "candidate_index": max(0, int(candidate_index or 0)),
                            "codes": normalized_codes,
                            "lookback_bars": int(lookback_bars) if lookback_bars is not None else None,
                            "horizon_days": int(horizon_days) if horizon_days is not None else None,
                            "max_dates": int(max_dates) if max_dates is not None else None,
                            "persist_artifact": bool(persist_artifact),
                            "write_memory": bool(write_memory),
                        },
                    ),
                )
                steps.append(_step("quant_manager.validate_factor_candidate", validation_response))
                val_artifact_id = _response_data(validation_response).get("artifact_id")
                if val_artifact_id:
                    resolved_artifact_id = str(val_artifact_id)
                    lineage_ctx.set_validation(str(val_artifact_id))
                    lineage_ctx.extra["validation_artifact_id"] = str(val_artifact_id)

            if workflow_task in {"pipeline", "registry_review"}:
                registry_response = await _run_workflow_stage(
                    step="quant_manager.factor_candidate_registry",
                    deadline=workflow_deadline,
                    stage_timeout=3.0,
                    coro=quant_manager(
                        action="factor_candidate_registry",
                        params={
                            "op": "active_pool",
                            "artifact_id": resolved_artifact_id,
                            "codes": normalized_codes,
                            "limit": 20,
                        },
                    ),
                )
                steps.append(_step("quant_manager.factor_candidate_registry", registry_response))

                registry_pool_response = await _run_workflow_stage(
                    step="quant_manager.factor_candidate_registry.list",
                    deadline=workflow_deadline,
                    stage_timeout=3.0,
                    coro=quant_manager(
                        action="factor_candidate_registry",
                        params={
                            "op": "list",
                            "codes": normalized_codes,
                            "limit": 20,
                            "only_active": True,
                        },
                    ),
                )
                steps.append(_step("quant_manager.factor_candidate_registry.list", registry_pool_response))

                if resolved_artifact_id:
                    registry_item_response = await _run_workflow_stage(
                        step="quant_manager.factor_candidate_registry.get",
                        deadline=workflow_deadline,
                        stage_timeout=3.0,
                        coro=quant_manager(
                            action="factor_candidate_registry",
                            params={
                                "op": "get",
                                "artifact_id": resolved_artifact_id,
                            },
                        ),
                    )
                    steps.append(_step("quant_manager.factor_candidate_registry.get", registry_item_response))

                memory_response = await _run_workflow_stage(
                    step="quant_manager.factor_research_memory",
                    deadline=workflow_deadline,
                    stage_timeout=3.0,
                    coro=quant_manager(
                        action="factor_research_memory",
                        params={
                            "op": "stats",
                            "artifact_id": resolved_artifact_id,
                            "codes": normalized_codes,
                            "limit": 20,
                        },
                    ),
                )
                steps.append(_step("quant_manager.factor_research_memory", memory_response))

                memory_record_id = _resolve_memory_record_id(
                    validation_data=_response_data(validation_response),
                    registry_item=_nested_dict(_response_data(registry_item_response), "item"),
                )
                if memory_record_id:
                    memory_item_response = await _run_workflow_stage(
                        step="quant_manager.factor_research_memory.get",
                        deadline=workflow_deadline,
                        stage_timeout=3.0,
                        coro=quant_manager(
                            action="factor_research_memory",
                            params={
                                "op": "get",
                                "artifact_id": memory_record_id,
                            },
                        ),
                    )
                    steps.append(_step("quant_manager.factor_research_memory.get", memory_item_response))

            scheduler_response = await _run_workflow_stage(
                step="quant_manager.scheduler_status",
                deadline=workflow_deadline,
                stage_timeout=2.0,
                coro=quant_manager(action="scheduler_status", params={}),
            )
            steps.append(_step("quant_manager.scheduler_status", scheduler_response))
            if run_scheduler_now:
                scheduler_run_response = await _run_workflow_stage(
                    step="quant_manager.scheduler_run_now",
                    deadline=workflow_deadline,
                    stage_timeout=2.0,
                    coro=quant_manager(action="scheduler_run_now", params={}),
                )
                steps.append(_step("quant_manager.scheduler_run_now", scheduler_run_response))

            failed_steps = _collect_failed_steps(steps)
            degraded = bool(failed_steps) or bool(
                _response_data(generation_response).get("fallback_used")
            )

            # P1-4: Factor enrichment
            factor_enrichment_payload: dict[str, Any] | None = None
            try:
                from ..services.factor_enrichment import build_factor_enrichment

                gen_data = _response_data(generation_response)
                expression = gen_data.get("expression") or gen_data.get("factor_expression") or ""
                hypothesis = gen_data.get("hypothesis") or gen_data.get("description") or ""
                val_data = _response_data(validation_response) if validation_response else {}
                registry_item = _nested_dict(_response_data(registry_item_response), "item")
                memory_item = (
                    _nested_dict(_response_data(memory_item_response), "item")
                    or _nested_dict(val_data, "memory_record")
                )
                existing_pool = _extract_existing_factor_pool(
                    registry_pool_data=_response_data(registry_pool_response),
                    registry_active_pool_data=_response_data(registry_response),
                    exclude_artifact_id=resolved_artifact_id,
                )
                enrichment = build_factor_enrichment(
                    expression=str(expression),
                    hypothesis=str(hypothesis) if hypothesis else None,
                    existing_pool=existing_pool or None,
                    category=gen_data.get("category"),
                    validation_result=val_data if val_data else None,
                    registry_status=_derive_registry_status(
                        generation_data=gen_data,
                        validation_data=val_data,
                        registry_item=registry_item,
                    ),
                    decay_monitor_status=_derive_decay_monitor_status(
                        validation_data=val_data,
                        memory_item=memory_item,
                    ),
                )
                factor_enrichment_payload = enrichment.to_dict()
            except Exception:
                pass

            result_payload: dict[str, Any] = {
                "workflow": "factor_candidate_workflow",
                "task": workflow_task,
                "codes": normalized_codes,
                "steps": steps,
                "summary": {
                    "artifact_id": resolved_artifact_id,
                    "failed_steps": failed_steps,
                    "fallback_used": bool(_response_data(generation_response).get("fallback_used")),
                    "generation_mode": _response_data(generation_response).get("generation_mode"),
                },
            }
            if factor_enrichment_payload:
                result_payload["factor_enrichment"] = factor_enrichment_payload

            completed_stages = [s["step"] for s in steps if s.get("success")]
            result_payload["workflow_stage"] = {
                "completed_stages": completed_stages,
                "last_completed_stage": completed_stages[-1] if completed_stages else None,
                "recoverable": True,
                "resume_hint": (
                    "validate" if workflow_task == "pipeline" and generation_response and not validation_response
                    else None
                ),
                "resume_artifact_id": (
                    str(_response_data(generation_response).get("artifact_id") or "").strip() or None
                    if generation_response and not validation_response
                    else None
                ),
            }
            return ok_with_meta(
                result_payload,
                tool_name="factor_candidate_workflow",
                action=workflow_task,
                started_at=started_at,
                source_chain=source_chain,
                extra_meta={
                    "quality": _meta_quality(
                        workflow_name="factor_candidate_workflow",
                        steps=steps,
                        extra={"fallback_used": bool(_response_data(generation_response).get("fallback_used"))},
                    ),
                    "side_effect": {
                        "level": "stateful" if (persist_artifact or write_memory or run_scheduler_now) else "read_only",
                        "target": "quant_manager",
                        "confirmation_required": False,
                        "idempotent": False,
                    },
                    "pit": build_pit_meta_simple(as_of),
                    "lineage": lineage_ctx.to_meta(),
                    "idempotency_key": idempotency_key,
                    "degraded": degraded,
                },
            )
        except Exception as exc:
            completed_stages = [s["step"] for s in steps if s.get("success")]
            return fail_with_meta(
                str(exc),
                tool_name="factor_candidate_workflow",
                action=workflow_task,
                started_at=started_at,
                source_chain=source_chain,
                error_code="INTERNAL_ERROR",
                extra_meta={
                    "quality": {"status": "failed", "workflow": "factor_candidate_workflow"},
                    "side_effect": {"level": "stateful", "target": "quant_manager", "confirmation_required": False},
                    "pit": build_pit_meta_simple(as_of),
                    "lineage": lineage_ctx.to_meta(),
                    "idempotency_key": idempotency_key,
                    "degraded": True,
                    "workflow_stage": {
                        "completed_stages": completed_stages,
                        "last_completed_stage": completed_stages[-1] if completed_stages else None,
                        "recoverable": True,
                        "failed_at": "factor_candidate_workflow",
                    },
                },
            )

    @mcp.tool(
        title="Strategy Review Workflow",
        description="AI-facing strategy review workflow with lifecycle, runtime and promotion context.",
        structured_output=True,
        meta=build_tool_meta("strategy_review_workflow"),
    )
    async def strategy_review_workflow(
        strategy_id: str,
        include_factory_status: bool = True,
        include_review_report: bool = True,
        include_runtime_alerts: bool = True,
        run_factory_once: bool = False,
        run_runtime_cycle: bool = False,
        idempotency_key: str | None = None,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        resolved_strategy_id = str(strategy_id or "").strip()
        steps: list[dict[str, Any]] = []
        source_chain = ["workflow.strategy_review", "resource.strategy_review", "manager.strategy_manager"]
        lineage_ctx = LineageContext.create("strategy_review_workflow", strategy_id=resolved_strategy_id)
        try:
            result_payload = await build_strategy_review_workflow_payload(
                resolved_strategy_id,
                runtime_strategy_manager=strategy_manager,
                include_factory_status=include_factory_status,
                include_review_report=include_review_report,
                include_runtime_alerts=include_runtime_alerts,
                run_factory_once=run_factory_once,
                run_runtime_cycle=run_runtime_cycle,
                runtime_alert_limit=20,
            )
            steps = list(result_payload.get("steps") or [])
            failed_steps = _collect_failed_steps(steps)

            return ok_with_meta(
                result_payload,
                tool_name="strategy_review_workflow",
                action="review",
                started_at=started_at,
                source_chain=source_chain,
                extra_meta={
                    "quality": _meta_quality(workflow_name="strategy_review_workflow", steps=steps),
                    "side_effect": {
                        "level": "stateful" if (run_factory_once or run_runtime_cycle) else "read_only",
                        "target": resolved_strategy_id,
                        "confirmation_required": False,
                        "idempotent": False if (run_factory_once or run_runtime_cycle) else True,
                    },
                    "pit": build_pit_meta_simple(as_of),
                    "lineage": lineage_ctx.to_meta(),
                    "idempotency_key": idempotency_key,
                    "degraded": bool(failed_steps),
                },
            )
        except Exception as exc:
            completed_stages = [s["step"] for s in steps if s.get("success")]
            return fail_with_meta(
                str(exc),
                tool_name="strategy_review_workflow",
                action="review",
                started_at=started_at,
                source_chain=source_chain,
                error_code="INTERNAL_ERROR",
                extra_meta={
                    "quality": {"status": "failed", "workflow": "strategy_review_workflow"},
                    "side_effect": {"level": "stateful" if (run_factory_once or run_runtime_cycle) else "read_only", "target": resolved_strategy_id},
                    "pit": build_pit_meta_simple(as_of),
                    "lineage": lineage_ctx.to_meta(),
                    "idempotency_key": idempotency_key,
                    "degraded": True,
                    "workflow_stage": {
                        "completed_stages": completed_stages,
                        "last_completed_stage": completed_stages[-1] if completed_stages else None,
                        "recoverable": True,
                        "failed_at": "strategy_review_workflow",
                    },
                },
            )
