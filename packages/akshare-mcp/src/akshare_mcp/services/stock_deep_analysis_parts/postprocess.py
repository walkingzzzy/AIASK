

async def run_stock_deep_analysis(
    *,
    code: str = "",
    task: str = "deep_analysis",
    user_id: str | None = None,
    investment_style: str = "balanced",
    market: str = "cn",
    run_id: str | None = None,
) -> dict[str, Any]:
    normalized_task = _normalize_task(task)
    if normalized_task == "rebuild_report":
        resolved_run_id = str(run_id or "").strip()
        if not resolved_run_id:
            raise ValueError("run_id is required for rebuild_report")
        return await _rebuild_report_from_artifacts(resolved_run_id)

    target = await _resolve_target(code)
    resolved_code = str(target.get("code") or normalize_code(code))
    resolved_run_id = str(run_id or f"stock-analysis-run-{resolved_code or 'unknown'}-{uuid4().hex[:12]}")
    profile = _task_profile(normalized_task)
    stages: list[dict[str, Any]] = []
    artifact_ids = {
        "run": resolved_run_id,
        "input": _artifact_id(resolved_run_id, "input"),
        "evidence": _artifact_id(resolved_run_id, "evidence"),
        "gaps": _artifact_id(resolved_run_id, "gaps"),
        "review": _artifact_id(resolved_run_id, "review"),
        "synthesis": _artifact_id(resolved_run_id, "synthesis"),
        "report": _artifact_id(resolved_run_id, "report"),
        "trade_plan": _artifact_id(resolved_run_id, "trade_plan"),
    }

    assembled = {
        "version": ANALYSIS_VERSION,
        "run_id": resolved_run_id,
        "task": normalized_task,
        "market": market,
        "target": target,
        "code": resolved_code,
        "name": target.get("name") or "",
        "investment_style": investment_style,
        "requested_by_user_id": user_id,
        "requested_at": _utcnow_iso(),
        "resource_uris": {
            "profile": f"resource://stock/{resolved_code}/profile" if resolved_code else None,
            "latest_stock": f"resource://stock/{resolved_code}/deep-analysis" if resolved_code else None,
        },
    }
    await _persist_artifact(
        artifact_id=artifact_ids["input"],
        artifact_type="analysis_input",
        code=resolved_code,
        run_id=resolved_run_id,
        task=normalized_task,
        payload=assembled,
    )

    if not target.get("resolved"):
        stages.append(
            _stage_result(
                "target_resolution",
                status="blocked",
                success=False,
                detail={
                    "resolution_mode": target.get("resolution_mode"),
                    "candidate_count": len(list(target.get("candidates") or [])),
                },
            )
        )
        gap_report = {
            "run_id": resolved_run_id,
            "code": resolved_code,
            "status": "blocked",
            "blocked": True,
            "critical_missing": [
                {
                    "field": "target.code",
                    "severity": "critical",
                    "message": f"unable to resolve stock target: {target.get('resolution_mode')}",
                    "recovery_action": "ask user to confirm one candidate code before continuing",
                }
            ],
            "non_critical_missing": [],
            "fallback_flags": [],
            "recovery_actions": ["确认股票代码或从候选列表中选择一个标的"],
            "candidates": list(target.get("candidates") or []),
            "checked_at": _utcnow_iso(),
        }
        await _persist_artifact(
            artifact_id=artifact_ids["gaps"],
            artifact_type="analysis_gap_report",
            code=resolved_code,
            run_id=resolved_run_id,
            task=normalized_task,
            payload=gap_report,
        )
        payload = _orchestrated_summary(
            run_id=resolved_run_id,
            task=normalized_task,
            status="partial_failed",
            assembled=assembled,
            stages=stages,
            evidence_pack=None,
            gap_report=gap_report,
            agent_review=None,
            synthesis=None,
            report_bundle=None,
            artifact_ids=artifact_ids,
        )
        await _persist_artifact(
            artifact_id=resolved_run_id,
            artifact_type="analysis_run_summary",
            code=resolved_code,
            run_id=resolved_run_id,
            task=normalized_task,
            payload=payload,
        )
        return payload

    stages.append(_stage_result("target_resolution", status="completed", success=True, detail={"code": resolved_code}))

    profile_payload, financial_payload, contexts_bundle, decision_summary = await asyncio.gather(
        _safe_profile_payload(resolved_code),
        _safe_financial_payload(resolved_code),
        _assemble_contexts(resolved_code, user_id),
        _safe_decision_summary(resolved_code, investment_style, user_id),
    )
    stock_context, quant_context, event_context, user_context = contexts_bundle

    assembled.update(
        {
            "name": str(target.get("name") or (profile_payload.get("stock") or {}).get("name") or ""),
            "profile": profile_payload,
            "financials": _response_data(financial_payload),
            "financials_meta": {
                "success": bool(financial_payload.get("success")) if isinstance(financial_payload, dict) else False,
                "source": (financial_payload or {}).get("source") if isinstance(financial_payload, dict) else None,
            },
            "decision": decision_summary,
            "contexts": {
                "stock": stock_context,
                "quant": quant_context,
                "event": event_context,
                "user": user_context,
            },
        }
    )
    if not str(target.get("name") or "").strip():
        resolved_name = str(
            assembled.get("name")
            or (decision_summary.get("name") if isinstance(decision_summary, dict) else "")
            or ""
        ).strip()
        if resolved_name:
            target["name"] = resolved_name
            assembled["name"] = resolved_name
    stages.append(
        _stage_result(
            "data_assembly",
            status="completed",
            success=True,
            detail={
                "profile_found": bool(profile_payload.get("found")),
                "financials_present": bool(assembled["financials"]),
                "decision_action": decision_summary.get("action"),
            },
        )
    )
    await _persist_artifact(
        artifact_id=artifact_ids["input"],
        artifact_type="analysis_input",
        code=resolved_code,
        run_id=resolved_run_id,
        task=normalized_task,
        payload=assembled,
    )

    evidence_pack = _build_evidence_pack(assembled, task=normalized_task)
    stages.append(
        _stage_result(
            "evidence_normalization",
            status="completed",
            success=True,
            detail={"evidence_count": (evidence_pack.get("summary") or {}).get("count")},
        )
    )
    await _persist_artifact(
        artifact_id=artifact_ids["evidence"],
        artifact_type="analysis_evidence",
        code=resolved_code,
        run_id=resolved_run_id,
        task=normalized_task,
        payload=evidence_pack,
    )

    integrity = validate_analysis_integrity(assembled, task=normalized_task)
    gap_report = _build_gap_report(
        run_id=resolved_run_id,
        code=resolved_code,
        integrity=integrity,
        target=target,
    )
    stages.append(
        _stage_result(
            "integrity_gate",
            status=str(integrity.get("status")),
            success=not bool(integrity.get("blocked")),
            detail={
                "completeness_score": integrity.get("completeness_score"),
                "critical_gap_count": len(list(integrity.get("critical_missing") or [])),
            },
        )
    )
    await _persist_artifact(
        artifact_id=artifact_ids["gaps"],
        artifact_type="analysis_gap_report",
        code=resolved_code,
        run_id=resolved_run_id,
        task=normalized_task,
        payload=gap_report,
    )

    if integrity.get("blocked") and normalized_task != "recover_gaps":
        payload = _orchestrated_summary(
            run_id=resolved_run_id,
            task=normalized_task,
            status="partial_failed",
            assembled=assembled,
            stages=stages,
            evidence_pack=evidence_pack,
            gap_report=gap_report,
            agent_review=None,
            synthesis=None,
            report_bundle=None,
            artifact_ids=artifact_ids,
        )
        await _persist_artifact(
            artifact_id=resolved_run_id,
            artifact_type="analysis_run_summary",
            code=resolved_code,
            run_id=resolved_run_id,
            task=normalized_task,
            payload=payload,
        )
        return payload

    agent_review = _build_agent_review(assembled, evidence_pack, gap_report)
    stages.append(
        _stage_result(
            "agent_review",
            status=agent_review.get("verdict", "pass"),
            success=agent_review.get("verdict") != "needs_recovery",
            detail={"conflict_count": len(list(agent_review.get("conflicts") or []))},
        )
    )
    await _persist_artifact(
        artifact_id=artifact_ids["review"],
        artifact_type="analysis_agent_review",
        code=resolved_code,
        run_id=resolved_run_id,
        task=normalized_task,
        payload=agent_review,
    )

    synthesis = _build_synthesis(assembled, evidence_pack, gap_report, task=normalized_task)
    stages.append(
        _stage_result(
            "synthesis",
            status="completed",
            success=True,
            detail={"section_count": len(list(synthesis.get("sections") or []))},
        )
    )
    await _persist_artifact(
        artifact_id=artifact_ids["synthesis"],
        artifact_type="analysis_synthesis",
        code=resolved_code,
        run_id=resolved_run_id,
        task=normalized_task,
        payload=synthesis,
    )

    final_check = _final_check(synthesis)
    stages.append(
        _stage_result(
            "final_check",
            status="passed" if final_check.get("passed") else "blocked",
            success=bool(final_check.get("passed")),
            detail=final_check,
        )
    )
    report_bundle: dict[str, Any] | None = None
    trade_plan_payload: dict[str, Any] | None = None

    if final_check.get("passed") and profile.get("include_report"):
        report_bundle = _build_report_bundle(
            assembled,
            synthesis,
            gap_report,
            artifact_ids,
            status="completed",
        )
        await _persist_artifact(
            artifact_id=artifact_ids["report"],
            artifact_type="analysis_report_bundle",
            code=resolved_code,
            run_id=resolved_run_id,
            task=normalized_task,
            payload=report_bundle,
        )
        stages.append(_stage_result("report_render", status="completed", success=True, detail={"has_html": True}))

    if profile.get("include_trade_plan"):
        trade_plan_payload = await generate_plan(
            resolved_code,
            capital=1_000_000,
            risk_per_trade=0.02,
            style=investment_style,
        )
        await _persist_artifact(
            artifact_id=artifact_ids["trade_plan"],
            artifact_type="trade_plan_bundle",
            code=resolved_code,
            run_id=resolved_run_id,
            task=normalized_task,
            payload=dict(trade_plan_payload or {}),
        )
        stages.append(_stage_result("trade_plan", status="completed", success=True, detail={"source": "generate_trade_plan"}))

    overall_status = "completed" if final_check.get("passed") and (report_bundle or not profile.get("include_report")) else "partial_failed"
    payload = _orchestrated_summary(
        run_id=resolved_run_id,
        task=normalized_task,
        status=overall_status,
        assembled=assembled,
        stages=stages,
        evidence_pack=evidence_pack,
        gap_report=gap_report,
        agent_review=agent_review,
        synthesis=synthesis,
        report_bundle=report_bundle,
        artifact_ids=artifact_ids,
        trade_plan=trade_plan_payload,
    )
    await _persist_artifact(
        artifact_id=resolved_run_id,
        artifact_type="analysis_run_summary",
        code=resolved_code,
        run_id=resolved_run_id,
        task=normalized_task,
        payload=payload,
    )
    return payload


async def get_analysis_run_summary(run_id: str) -> dict[str, Any]:
    artifact = await get_artifact_async(str(run_id or "").strip())
    if artifact:
        payload = dict(artifact.get("payload") or {})
        if payload:
            return payload
    return {
        "run_id": str(run_id or "").strip(),
        "found": False,
        "error": f"analysis run not found: {run_id}",
    }


async def get_analysis_report_bundle(run_id: str) -> dict[str, Any]:
    artifact = await get_artifact_async(_artifact_id(str(run_id or "").strip(), "report"))
    if artifact:
        payload = dict(artifact.get("payload") or {})
        if payload:
            return payload
    return {
        "run_id": str(run_id or "").strip(),
        "found": False,
        "error": f"analysis report not found: {run_id}",
    }


async def find_latest_analysis_run_id(code: str) -> str | None:
    resolved_code = normalize_code(code)
    if not resolved_code:
        return None
    rows = await list_artifacts_async(limit=200, strategy=ANALYSIS_STRATEGY)
    for row in rows:
        artifact_id = str((row or {}).get("artifact_id") or "").strip()
        if not artifact_id or ":" in artifact_id:
            continue
        if str((row or {}).get("code") or "").strip() != resolved_code:
            continue
        return artifact_id
    return None


async def get_latest_analysis_summary_for_code(code: str) -> dict[str, Any]:
    latest_run_id = await find_latest_analysis_run_id(code)
    if not latest_run_id:
        resolved_code = normalize_code(code)
        return {
            "code": resolved_code,
            "found": False,
            "error": f"no deep analysis run found for {resolved_code}",
        }
    payload = await get_analysis_run_summary(latest_run_id)
    if payload.get("found") is False:
        return payload
    return payload


def compact_run_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return {field: payload.get(field) for field in _SUMMARY_ONLY_FIELDS if field in payload}
