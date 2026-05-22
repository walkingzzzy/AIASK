    async def analyze_stock_workflow(
        code: str,
        investment_style: str = "balanced",
        include_kline: bool = True,
        include_financials: bool = True,
        include_decision: bool = True,
        kline_limit: int = 90,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        validated_code, _, validation_error = await resolve_existing_security_code_async(code=code)
        resolved_code = normalize_code(code)
        lineage = LineageContext.create(
            "analyze_stock_workflow",
            security_code=resolved_code,
        )
        try:
            if validation_error:
                return fail_with_meta(
                    validation_error,
                    tool_name="analyze_stock_workflow",
                    action="run",
                    started_at=started_at,
                    source_chain=["workflow.analyze_stock"],
                    extra_meta={
                        "side_effect": {"level": "read_only", "target": resolved_code, "confirmation_required": False},
                        "pit": build_pit_meta_simple(as_of),
                        "lineage": lineage.to_meta(),
                        "quality": {"status": "invalid_params", "workflow": "analyze_stock_workflow"},
                        "degraded": True,
                    },
                )
            resolved_code = str(validated_code)
            from ..resources.stock_and_watchlist import build_stock_profile_resource_payload

            steps: list[dict[str, Any]] = []
            source_chain = ["workflow.analyze_stock"]

            child_profile = lineage.child("stock_profile")
            profile_payload = await build_stock_profile_resource_payload(resolved_code)
            steps.append(_step("stock_profile", {"success": bool(profile_payload.get("found", True)), "data": profile_payload}))
            source_chain.append("resource.stock_profile")

            kline_payload: dict[str, Any] | None = None
            if include_kline:
                child_kline = lineage.child("daily_kline")
                kline_payload = await get_kline(stock_code=resolved_code, period="daily", limit=max(20, min(int(kline_limit or 90), 240)))
                steps.append(_step("daily_kline", kline_payload))
                source_chain.append("tool.get_kline")

            financial_payload: dict[str, Any] | None = None
            if include_financials:
                child_fin = lineage.child("financials")
                financial_payload = await get_financials(stock_code=resolved_code)
                steps.append(_step("financials", financial_payload))
                source_chain.append("tool.get_financials")

            decision_payload: dict[str, Any] | None = None
            if include_decision:
                child_decision = lineage.child("decision_summary")
                decision_payload = await get_unified_decision_summary(code=resolved_code, investment_style=investment_style)
                steps.append(_step("decision_summary", decision_payload))
                source_chain.append("tool.get_unified_decision_summary")

            failed_steps = _collect_failed_steps(steps)
            degraded = bool(failed_steps)
            result = {
                "workflow": "analyze_stock_workflow",
                "code": resolved_code,
                "steps": steps,
                "summary": {
                    "profile_found": bool(profile_payload.get("found", False)),
                    "quote_price": ((profile_payload.get("realtime_quote") or {}).get("price")),
                    "decision_action": _response_data(decision_payload).get("action"),
                    "failed_steps": failed_steps,
                },
                "artifacts": {
                    "stock_profile_resource": f"resource://stock/{resolved_code}/profile",
                },
            }
            return ok_with_meta(
                result,
                tool_name="analyze_stock_workflow",
                action="run",
                started_at=started_at,
                source_chain=source_chain,
                extra_meta={
                    "quality": _meta_quality(workflow_name="analyze_stock_workflow", steps=steps),
                    "side_effect": {
                        "level": "read_only",
                        "target": resolved_code,
                        "confirmation_required": False,
                        "idempotent": True,
                    },
                    "pit": build_pit_meta_simple(as_of),
                    "lineage": lineage.to_meta(),
                    "degraded": degraded,
                },
            )
        except Exception as exc:
            return fail_with_meta(
                str(exc),
                tool_name="analyze_stock_workflow",
                action="run",
                started_at=started_at,
                source_chain=["workflow.analyze_stock"],
                error_code="INTERNAL_ERROR",
                extra_meta={
                    "side_effect": {"level": "read_only", "target": resolved_code, "confirmation_required": False},
                    "pit": build_pit_meta_simple(as_of),
                    "lineage": lineage.to_meta(),
                    "quality": {"status": "failed", "workflow": "analyze_stock_workflow"},
                    "degraded": True,
                },
            )

    @mcp.tool(
        title="Analyze Stock Product Workflow",
        description="Unified stock deep-analysis workflow with protocolized stages and persisted report artifacts.",
        structured_output=True,
        meta=build_tool_meta("analyze_stock_product_workflow"),
    )
    async def analyze_stock_product_workflow(
        code: str = "",
        task: str = "deep_analysis",
        investment_style: str = "balanced",
        user_id: str | None = None,
        market: str = "cn",
        run_id: str | None = None,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        source_chain = ["workflow.stock_deep_analysis", "service.stock_deep_analysis"]
        validated_code, _, validation_error = await resolve_existing_security_code_async(code=code)
        lineage = LineageContext.create(
            "analyze_stock_product_workflow",
            security_code=normalize_code(code),
            run_id=run_id,
        )
        try:
            if validation_error:
                return fail_with_meta(
                    validation_error,
                    tool_name="analyze_stock_product_workflow",
                    action=str(task or "deep_analysis"),
                    started_at=started_at,
                    source_chain=source_chain,
                    error_code="INVALID_PARAMS",
                    extra_meta={
                        "side_effect": {"level": "stateful", "target": normalize_code(code), "confirmation_required": False},
                        "pit": build_pit_meta_simple(as_of),
                        "lineage": lineage.to_meta(),
                        "quality": {"status": "invalid_params", "workflow": "analyze_stock_product_workflow"},
                        "degraded": True,
                    },
                )
            payload = await run_stock_deep_analysis(
                code=str(validated_code),
                task=task,
                user_id=user_id,
                investment_style=investment_style,
                market=market,
                run_id=run_id,
            )
            stage_steps = [
                {
                    "step": str(item.get("stage") or ""),
                    "success": bool(item.get("success")),
                    "output": dict(item),
                }
                for item in list(payload.get("steps") or [])
                if isinstance(item, dict)
            ]
            return ok_with_meta(
                payload,
                tool_name="analyze_stock_product_workflow",
                action=str(task or "deep_analysis"),
                started_at=started_at,
                source_chain=source_chain,
                extra_meta={
                    "quality": _meta_quality(
                        workflow_name="analyze_stock_product_workflow",
                        steps=stage_steps,
                        extra={
                            "run_id": payload.get("run_id"),
                            "report_ready": bool((payload.get("summary") or {}).get("report_ready")),
                        },
                    ),
                    "side_effect": {
                        "level": "stateful",
                        "target": str(validated_code),
                        "confirmation_required": False,
                        "idempotent": False,
                    },
                    "pit": build_pit_meta_simple(as_of),
                    "lineage": lineage.to_meta(),
                    "degraded": payload.get("status") != "completed",
                },
            )
        except Exception as exc:
            return fail_with_meta(
                str(exc),
                tool_name="analyze_stock_product_workflow",
                action=str(task or "deep_analysis"),
                started_at=started_at,
                source_chain=source_chain,
                error_code="INTERNAL_ERROR",
                extra_meta={
                    "side_effect": {"level": "stateful", "target": normalize_code(code), "confirmation_required": False},
                    "pit": build_pit_meta_simple(as_of),
                    "lineage": lineage.to_meta(),
                    "quality": {"status": "failed", "workflow": "analyze_stock_product_workflow"},
                    "degraded": True,
                },
            )
