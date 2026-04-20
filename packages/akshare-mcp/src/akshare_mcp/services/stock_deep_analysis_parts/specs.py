

def _build_evidence_pack(assembled: dict[str, Any], *, task: str) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    target = dict(assembled.get("target") or {})
    profile = dict(assembled.get("profile") or {})
    profile_stock = dict(profile.get("stock") or {})
    quote = dict(profile.get("realtime_quote") or {})
    financials = dict(assembled.get("financials") or {})
    decision = dict(assembled.get("decision") or {})
    contexts = dict(assembled.get("contexts") or {})
    stock_context = dict(contexts.get("stock") or {})
    quant_context = dict(contexts.get("quant") or {})
    event_context = dict(contexts.get("event") or {})

    _append_evidence(
        evidence,
        section="overview",
        label="实时价格",
        statement=f"最新价格约为 {quote.get('price')}",
        value=quote.get("price"),
        source="stock_profile",
        source_field="realtime_quote.price",
    )
    _append_evidence(
        evidence,
        section="valuation",
        label="市盈率",
        statement=f"资源画像中的 PE 为 {profile_stock.get('pe_ratio')}",
        value=profile_stock.get("pe_ratio"),
        source="stock_profile",
        source_field="stock.pe_ratio",
    )
    _append_evidence(
        evidence,
        section="financial_quality",
        label="营业收入",
        statement=f"最新财报收入为 {financials.get('revenue')}",
        value=financials.get("revenue"),
        source="financials",
        source_field="revenue",
    )
    _append_evidence(
        evidence,
        section="financial_quality",
        label="净利润",
        statement=f"最新财报净利润为 {financials.get('netProfit')}",
        value=financials.get("netProfit"),
        source="financials",
        source_field="netProfit",
    )
    _append_evidence(
        evidence,
        section="financial_quality",
        label="ROE",
        statement=f"ROE 为 {financials.get('roe')}",
        value=financials.get("roe"),
        source="financials",
        source_field="roe",
    )
    _append_evidence(
        evidence,
        section="trend_and_structure",
        label="市场上下文评分",
        statement=f"市场上下文评分为 {stock_context.get('score')}",
        value=stock_context.get("score"),
        source="stock_context",
        source_field="score",
    )
    _append_evidence(
        evidence,
        section="trend_and_structure",
        label="主力资金净流入",
        statement=f"主力资金净流入为 {((stock_context.get('fund_flow_snapshot') or {}).get('main_net_inflow'))}",
        value=((stock_context.get("fund_flow_snapshot") or {}).get("main_net_inflow")),
        source="stock_context",
        source_field="fund_flow_snapshot.main_net_inflow",
    )
    _append_evidence(
        evidence,
        section="trend_and_structure",
        label="量化评分",
        statement=f"量化上下文评分为 {quant_context.get('score')}",
        value=quant_context.get("score"),
        source="quant_context",
        source_field="score",
    )
    _append_evidence(
        evidence,
        section="events_and_catalysts",
        label="事件情绪",
        statement=f"事件情绪为 {event_context.get('sentiment')}",
        value=event_context.get("sentiment"),
        source="event_context",
        source_field="sentiment",
    )
    _append_evidence(
        evidence,
        section="events_and_catalysts",
        label="事件评分",
        statement=f"事件上下文评分为 {event_context.get('score')}",
        value=event_context.get("score"),
        source="event_context",
        source_field="score",
    )
    _append_evidence(
        evidence,
        section="action_plan",
        label="统一决策动作",
        statement=f"统一决策建议为 {decision.get('action')}",
        value=decision.get("action"),
        source="unified_decision",
        source_field="action",
        kind="inference",
    )
    _append_evidence(
        evidence,
        section="action_plan",
        label="统一决策置信度",
        statement=f"统一决策置信度为 {decision.get('confidence')}",
        value=decision.get("confidence"),
        source="unified_decision",
        source_field="confidence",
        kind="inference",
    )

    if str(task) != "quick_scan":
        for reason in list(decision.get("reasons") or [])[:4]:
            _append_evidence(
                evidence,
                section="overview",
                label="决策理由",
                statement=str(reason),
                value=str(reason),
                source="unified_decision",
                source_field="reasons",
                kind="inference",
            )
        for risk in list(decision.get("risks") or [])[:4]:
            _append_evidence(
                evidence,
                section="risks_and_counterpoints",
                label="决策风险",
                statement=str(risk),
                value=str(risk),
                source="unified_decision",
                source_field="risks",
                kind="inference",
            )

    return {
        "version": ANALYSIS_VERSION,
        "code": target.get("code"),
        "task": task,
        "evidence": evidence,
        "summary": {
            "count": len(evidence),
            "sections": sorted(dict.fromkeys(item["section"] for item in evidence)),
            "fact_count": sum(1 for item in evidence if item.get("kind") == "fact"),
            "inference_count": sum(1 for item in evidence if item.get("kind") == "inference"),
        },
    }


def _build_gap_report(
    *,
    run_id: str,
    code: str,
    integrity: dict[str, Any],
    target: dict[str, Any],
) -> dict[str, Any]:
    resolution_message = None
    if not target.get("resolved"):
        mode = str(target.get("resolution_mode") or "unresolved")
        candidate_count = len(list(target.get("candidates") or []))
        resolution_message = f"target resolution blocked: {mode}, candidates={candidate_count}"

    return {
        "run_id": run_id,
        "code": code,
        "status": integrity.get("status"),
        "blocked": bool(integrity.get("blocked")),
        "resolution_message": resolution_message,
        "critical_missing": list(integrity.get("critical_missing") or []),
        "non_critical_missing": list(integrity.get("non_critical_missing") or []),
        "fallback_flags": list(integrity.get("fallback_flags") or []),
        "recovery_actions": list(integrity.get("recovery_actions") or []),
        "checked_at": _utcnow_iso(),
    }


def _build_agent_review(assembled: dict[str, Any], evidence_pack: dict[str, Any], gap_report: dict[str, Any]) -> dict[str, Any]:
    decision = dict(assembled.get("decision") or {})
    contexts = dict(assembled.get("contexts") or {})
    quant_context = dict(contexts.get("quant") or {})
    event_context = dict(contexts.get("event") or {})

    conflicts: list[str] = []
    action = str(decision.get("action") or "").lower()
    quant_score = _safe_float(quant_context.get("score"))
    event_sentiment = str(event_context.get("sentiment") or "")
    if action == "buy" and quant_score is not None and quant_score < 45:
        conflicts.append("统一决策偏买入，但量化评分偏弱")
    if action == "buy" and event_sentiment == "bearish":
        conflicts.append("统一决策偏买入，但事件情绪偏空")
    if action == "sell" and quant_score is not None and quant_score > 60:
        conflicts.append("统一决策偏卖出，但量化评分仍偏强")

    risks = list(dict.fromkeys(list(decision.get("risks") or [])[:5] + conflicts))
    cited_evidence_ids = [str(item.get("evidence_id")) for item in list(evidence_pack.get("evidence") or [])[:8]]
    blocked = bool(gap_report.get("blocked"))
    verdict = "needs_recovery" if blocked else "pass_with_caution" if conflicts else "pass"
    next_actions = list(gap_report.get("recovery_actions") or [])
    if not next_actions:
        next_actions = [
            "核对估值与财务口径是否与最新财报日期一致",
            "将结论与统一决策摘要一起展示，避免单维度解释",
        ]

    return {
        "run_id": assembled.get("run_id"),
        "reviewer": "aiask_protocol_reviewer_v1",
        "verdict": verdict,
        "cited_evidence_ids": cited_evidence_ids,
        "risks": risks,
        "conflicts": conflicts,
        "next_actions": next_actions,
        "checked_at": _utcnow_iso(),
    }


def _section_evidence_ids(evidence: list[dict[str, Any]], section: str, minimum: int = 1) -> list[str]:
    matched = [str(item.get("evidence_id")) for item in evidence if item.get("section") == section]
    if len(matched) >= minimum:
        return matched[:6]
    return [str(item.get("evidence_id")) for item in evidence[:minimum]]


def _first_matching_statement(evidence: list[dict[str, Any]], section: str, fallback: str) -> str:
    for item in evidence:
        if item.get("section") == section and item.get("statement"):
            return str(item.get("statement"))
    return fallback


def _build_synthesis(assembled: dict[str, Any], evidence_pack: dict[str, Any], gap_report: dict[str, Any], *, task: str) -> dict[str, Any]:
    evidence = list(evidence_pack.get("evidence") or [])
    decision = dict(assembled.get("decision") or {})
    target = dict(assembled.get("target") or {})
    financials = dict(assembled.get("financials") or {})
    contexts = dict(assembled.get("contexts") or {})
    stock_context = dict(contexts.get("stock") or {})
    quant_context = dict(contexts.get("quant") or {})
    event_context = dict(contexts.get("event") or {})

    sections: list[dict[str, Any]] = [
        {
            "key": "overview",
            "title": "标的概览",
            "narrative": f"{target.get('name') or target.get('code')} 当前统一决策为 {decision.get('action') or '待确认'}，"
            f"置信度 {decision.get('confidence') or '未知'}。"
            f" { _first_matching_statement(evidence, 'overview', '需要结合更多事实证据。') }",
            "evidence_ids": _section_evidence_ids(evidence, "overview", minimum=2),
        },
        {
            "key": "valuation",
            "title": "估值结论",
            "narrative": (
                f"资源画像中的 PE 约为 {((assembled.get('profile') or {}).get('stock') or {}).get('pe_ratio') or '未知'}，"
                f"当前估值判断需要和财务质量一起解读。"
            ),
            "evidence_ids": _section_evidence_ids(evidence, "valuation", minimum=1),
        },
        {
            "key": "financial_quality",
            "title": "财务质量",
            "narrative": (
                f"最新财报日期 {financials.get('reportDate') or '未知'}，收入 {financials.get('revenue') or '未知'}，"
                f"净利润 {financials.get('netProfit') or '未知'}，ROE {financials.get('roe') or '未知'}。"
            ),
            "evidence_ids": _section_evidence_ids(evidence, "financial_quality", minimum=2),
        },
        {
            "key": "trend_and_structure",
            "title": "趋势与交易结构",
            "narrative": (
                f"市场评分 {stock_context.get('score') or '未知'}，量化评分 {quant_context.get('score') or '未知'}，"
                f"更适合作为节奏与仓位判断的依据，而不是单独决定方向。"
            ),
            "evidence_ids": _section_evidence_ids(evidence, "trend_and_structure", minimum=2),
        },
        {
            "key": "events_and_catalysts",
            "title": "事件与催化",
            "narrative": (
                f"事件情绪 {event_context.get('sentiment') or '未知'}，事件评分 {event_context.get('score') or '未知'}，"
                f"候选催化包括 {', '.join(str(item) for item in list(event_context.get('candidate_actions') or [])[:3]) or '暂无明确结构化催化'}。"
            ),
            "evidence_ids": _section_evidence_ids(evidence, "events_and_catalysts", minimum=1),
        },
        {
            "key": "risks_and_counterpoints",
            "title": "风险与反证",
            "narrative": (
                "主要风险来自统一决策风险项、事件情绪冲突以及完整性缺口。"
                f" 当前缺口数量 {len(list(gap_report.get('critical_missing') or [])) + len(list(gap_report.get('non_critical_missing') or []))}。"
            ),
            "evidence_ids": _section_evidence_ids(evidence, "risks_and_counterpoints", minimum=1),
        },
        {
            "key": "action_plan",
            "title": "行动建议",
            "narrative": (
                f"建议以 {decision.get('action') or '观察'} 为主线，结合 {decision.get('recommended_horizon') or '当前阶段'} 的持有期，"
                "先确认缺口是否已经关闭，再决定是否升级为正式交易动作。"
            ),
            "evidence_ids": _section_evidence_ids(evidence, "action_plan", minimum=2),
        },
        {
            "key": "evidence_and_gaps",
            "title": "证据与缺口说明",
            "narrative": (
                f"当前 evidence {len(evidence)} 条，完整性状态 {gap_report.get('status')}，"
                f"fallback 标记 {', '.join(list(gap_report.get('fallback_flags') or [])[:4]) or '无'}。"
            ),
            "evidence_ids": [str(item.get("evidence_id")) for item in evidence[:4]],
        },
    ]

    allowed_sections = set(_task_profile(task)["section_keys"])
    filtered_sections = [section for section in sections if section["key"] in allowed_sections]
    digest = (
        f"{target.get('name') or target.get('code')} 的 {task.replace('_', ' ')} 显示统一决策为 "
        f"{decision.get('action') or '待确认'}，市场/量化/事件评分分别为 "
        f"{stock_context.get('score') or '未知'} / {quant_context.get('score') or '未知'} / {event_context.get('score') or '未知'}。"
    )

    return {
        "run_id": assembled.get("run_id"),
        "code": target.get("code"),
        "task": task,
        "digest": digest,
        "sections": filtered_sections,
        "summary": {
            "action": decision.get("action"),
            "confidence": decision.get("confidence"),
            "gap_status": gap_report.get("status"),
        },
    }


def _final_check(synthesis: dict[str, Any]) -> dict[str, Any]:
    missing_citations = [
        str(section.get("key"))
        for section in list(synthesis.get("sections") or [])
        if not list(section.get("evidence_ids") or [])
    ]
    passed = not missing_citations
    return {
        "passed": passed,
        "missing_citations": missing_citations,
        "checked_at": _utcnow_iso(),
    }


def _perspective_cards(assembled: dict[str, Any], gap_report: dict[str, Any]) -> list[dict[str, Any]]:
    contexts = dict(assembled.get("contexts") or {})
    stock_context = dict(contexts.get("stock") or {})
    quant_context = dict(contexts.get("quant") or {})
    event_context = dict(contexts.get("event") or {})
    financials = dict(assembled.get("financials") or {})
    return [
        {"key": "fundamental", "title": "基本面", "value": financials.get("roe"), "note": f"财报日期 {financials.get('reportDate') or '未知'}"},
        {"key": "valuation", "title": "估值", "value": ((assembled.get("profile") or {}).get("stock") or {}).get("pe_ratio"), "note": "优先与财报口径联读"},
        {"key": "trend", "title": "趋势", "value": quant_context.get("score"), "note": "量化上下文评分"},
        {"key": "risk", "title": "风险", "value": len(list(gap_report.get("critical_missing") or [])), "note": "关键缺口数量"},
        {"key": "fund_flow", "title": "资金/情绪", "value": stock_context.get("score"), "note": f"事件情绪 {event_context.get('sentiment') or '未知'}"},
        {"key": "events", "title": "事件催化", "value": event_context.get("score"), "note": "事件上下文评分"},
    ]


def _build_summary_card(assembled: dict[str, Any], synthesis: dict[str, Any], gap_report: dict[str, Any]) -> dict[str, Any]:
    decision = dict(assembled.get("decision") or {})
    target = dict(assembled.get("target") or {})
    profile = dict(assembled.get("profile") or {})
    quote = dict(profile.get("realtime_quote") or {})
    bullets = [
        f"统一决策: {decision.get('action') or '待确认'} / 置信度 {decision.get('confidence') or '未知'}",
        f"实时价格: {quote.get('price') or '未知'}",
        f"完整性状态: {gap_report.get('status')}",
    ]
    return {
        "title": f"{target.get('name') or target.get('code')} {synthesis.get('task')}",
        "subtitle": synthesis.get("digest"),
        "bullets": bullets,
    }


def _build_manifest(
    *,
    run_id: str,
    code: str,
    task: str,
    status: str,
    artifact_ids: dict[str, str],
    gap_report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "code": code,
        "task": task,
        "status": status,
        "artifact_ids": artifact_ids,
        "generated_at": _utcnow_iso(),
        "gap_status": gap_report.get("status"),
        "critical_gap_count": len(list(gap_report.get("critical_missing") or [])),
        "warning_gap_count": len(list(gap_report.get("non_critical_missing") or [])),
    }
