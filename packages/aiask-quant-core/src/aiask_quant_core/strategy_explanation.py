"""Shared strategy explanation helpers.

The helpers in this module turn the many low-level generation fields carried by
AIASK strategies into a compact, stable, human-facing explanation contract.
They intentionally avoid any MCP, Agent, database, or Strategy Factory imports.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


EXPLANATION_VERSION = "strategy_explanation.v1"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _non_empty(value: Any) -> bool:
    return value not in (None, "", [], {})


def _first(*values: Any) -> Any:
    for value in values:
        if _non_empty(value):
            return value
    return None


def _text(value: Any, *, limit: int = 360) -> str | None:
    if not _non_empty(value):
        return None
    if isinstance(value, Mapping):
        for key in ("summary", "rationale", "reason", "description", "thesis", "note"):
            nested = _text(value.get(key), limit=limit)
            if nested:
                return nested
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _string_list(*values: Any, limit: int = 12) -> list[str]:
    result: list[str] = []

    def visit(value: Any) -> None:
        if not _non_empty(value) or len(result) >= limit:
            return
        if isinstance(value, Mapping):
            for key in ("symbols", "codes", "stock_codes", "target_symbols", "tags", "labels"):
                visit(value.get(key))
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)
            return
        token = str(value).strip()
        if token and token not in result:
            result.append(token)

    for value in values:
        visit(value)
    return result


def _compact(value: Any, *, depth: int = 2, max_items: int = 10, max_list: int = 8) -> Any:
    if depth <= 0:
        if isinstance(value, Mapping):
            return {"_omitted_keys": len(value)}
        if isinstance(value, (list, tuple, set)):
            return {"_omitted_items": len(value)}
        return _text(value, limit=160) if isinstance(value, str) else value
    if isinstance(value, Mapping):
        compacted: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                compacted["_omitted_keys"] = len(value) - max_items
                break
            if not _non_empty(item):
                continue
            compacted[str(key)] = _compact(item, depth=depth - 1, max_items=max_items, max_list=max_list)
        return compacted
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        compacted_list = [
            _compact(item, depth=depth - 1, max_items=max_items, max_list=max_list)
            for item in items[:max_list]
            if _non_empty(item)
        ]
        if len(items) > max_list:
            compacted_list.append({"_omitted_items": len(items) - max_list})
        return compacted_list
    return _text(value, limit=240) if isinstance(value, str) else value


def _compact_keys(value: Any, keys: tuple[str, ...], *, depth: int = 2) -> dict[str, Any]:
    payload = _mapping(value)
    return {
        key: _compact(payload.get(key), depth=depth)
        for key in keys
        if _non_empty(payload.get(key))
    }


def _metric_summary(metrics: Any) -> dict[str, Any]:
    payload = _mapping(metrics)
    if not payload:
        return {}
    keys = (
        "sharpe_ratio",
        "total_return",
        "annual_return",
        "max_drawdown",
        "win_rate",
        "trade_count",
        "trades_count",
        "validation_grade",
        "validation_total_score",
    )
    return {key: payload.get(key) for key in keys if _non_empty(payload.get(key))}


def _format_pct(value: Any) -> str | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return f"{number:.1%}"


def _format_float(value: Any) -> str | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return f"{number:.2f}"


def _label(prefix: str, value: Any) -> str | None:
    token = str(value or "").strip().lower().replace(" ", "_")
    return f"{prefix}:{token}" if token else None


def _resolve_horizon_label(holding_horizon: dict[str, Any]) -> str | None:
    max_days = holding_horizon.get("max_days") or holding_horizon.get("max_holding_days")
    min_days = holding_horizon.get("min_days")
    if max_days and min_days:
        return f"horizon:{min_days}-{max_days}d"
    if max_days:
        return f"horizon:max_{max_days}d"
    return None


def _build_summary(
    *,
    name: str | None,
    strategy_type: str | None,
    thesis: str | None,
    target_symbols: list[str],
    generator_type: str | None,
) -> str:
    if thesis:
        return thesis
    subject = name or strategy_type or "strategy"
    target = f" for {len(target_symbols)} target symbol(s)" if target_symbols else ""
    generator = f" generated by {generator_type}" if generator_type else ""
    return f"{subject} is a {strategy_type or 'trading'} candidate{target}{generator}."


def _build_why(
    *,
    generation_reason: dict[str, Any],
    research_task: dict[str, Any],
    event_context: dict[str, Any],
    thesis: str | None,
    target_symbols: list[str],
    generator_type: str | None,
    source: str | None,
) -> str:
    parts: list[str] = []
    source_value = _first(generation_reason.get("source"), source, generator_type)
    if source_value:
        parts.append(f"source={source_value}")
    provider = generation_reason.get("provider")
    if provider and provider != source_value:
        parts.append(f"provider={provider}")
    model = generation_reason.get("model")
    if model:
        parts.append(f"model={model}")
    category = _first(generation_reason.get("category"), research_task.get("candidate_family"))
    if category:
        parts.append(f"category={category}")
    opportunity = _first(research_task.get("opportunity_type"), event_context.get("event_type"))
    if opportunity:
        parts.append(f"opportunity={opportunity}")
    theme = _first(research_task.get("theme"), research_task.get("theme_name"), event_context.get("theme_name"))
    if theme:
        parts.append(f"theme={theme}")
    rationale = _text(
        _first(
            generation_reason.get("rationale"),
            research_task.get("rationale"),
            event_context.get("event_summary"),
            thesis,
        ),
        limit=220,
    )
    if rationale:
        parts.append(f"rationale={rationale}")
    fallback = generation_reason.get("fallback_reason")
    if fallback:
        parts.append(f"fallback={fallback}")
    if target_symbols:
        parts.append(f"targets={','.join(target_symbols[:6])}")
    return "; ".join(parts)


def build_strategy_explanation(
    strategy: Mapping[str, Any] | None,
    *,
    metrics: Mapping[str, Any] | None = None,
    existing: Mapping[str, Any] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Build a compact explanation contract for a generated strategy.

    The returned shape is append-only by convention: callers can safely persist
    it under ``params.strategy_explanation`` and surface it in domain events.
    """

    payload = _mapping(strategy)
    params = _mapping(payload.get("params"))
    existing_payload = _mapping(existing)
    existing_params = _mapping(existing_payload.get("params"))
    inherited = _mapping(
        _first(
            payload.get("strategy_explanation"),
            params.get("strategy_explanation"),
            existing_payload.get("strategy_explanation"),
            existing_params.get("strategy_explanation"),
        )
    )
    generation_reason = _mapping(
        _first(payload.get("generation_reason"), params.get("generation_reason"), inherited.get("generation_reason"))
    )
    research_task = _mapping(_first(payload.get("research_task"), params.get("research_task")))
    event_context = _mapping(_first(payload.get("event_context"), params.get("event_context")))
    trade_plan = _mapping(_first(payload.get("trade_plan"), params.get("trade_plan")))
    risk_rules = _mapping(_first(payload.get("risk_rules"), params.get("risk_rules")))
    holding_horizon = _mapping(_first(payload.get("holding_horizon"), params.get("holding_horizon")))
    validation_profile = _mapping(_first(payload.get("validation_profile"), params.get("validation_profile")))
    constraint_check = _mapping(_first(payload.get("constraint_check"), params.get("constraint_check")))
    stock_pool = _mapping(_first(payload.get("stock_pool"), params.get("stock_pool"), generation_reason.get("stock_pool")))
    metrics_summary = _metric_summary(metrics or payload.get("backtest_metrics") or params.get("backtest_metrics"))

    name = _text(_first(payload.get("name"), existing_payload.get("name")), limit=120)
    description = _text(_first(payload.get("description"), existing_payload.get("description")), limit=360)
    strategy_type = _text(_first(payload.get("strategy_type"), params.get("strategy_type")), limit=80)
    generator_type = _text(
        _first(
            payload.get("generator_type"),
            params.get("generator_type"),
            generation_reason.get("engine"),
            generation_reason.get("provider"),
            source,
        ),
        limit=120,
    )
    thesis = _text(
        _first(
            payload.get("hypothesis"),
            params.get("hypothesis"),
            generation_reason.get("rationale"),
            research_task.get("rationale"),
            description,
        ),
        limit=360,
    )
    candidate_family = _text(
        _first(
            payload.get("candidate_family"),
            params.get("candidate_family"),
            research_task.get("candidate_family"),
            strategy_type,
        ),
        limit=80,
    )
    risk_level = _text(
        _first(payload.get("risk_level"), params.get("risk_level"), generation_reason.get("risk_level")),
        limit=80,
    )
    target_symbols = _string_list(
        payload.get("target_symbols"),
        params.get("target_symbols"),
        stock_pool,
        generation_reason.get("target_symbols"),
        limit=12,
    )
    selection_logic = _string_list(
        payload.get("selection_logic"),
        params.get("selection_logic"),
        generation_reason.get("selection_logic"),
        limit=8,
    )

    summary = _text(inherited.get("summary"), limit=360) or description or _build_summary(
        name=name,
        strategy_type=strategy_type,
        thesis=thesis,
        target_symbols=target_symbols,
        generator_type=generator_type,
    )
    why_generated = _text(inherited.get("why_generated"), limit=420) or _build_why(
        generation_reason=generation_reason,
        research_task=research_task,
        event_context=event_context,
        thesis=thesis,
        target_symbols=target_symbols,
        generator_type=generator_type,
        source=source,
    )

    labels = _string_list(
        inherited.get("labels"),
        payload.get("tags"),
        params.get("tags"),
        existing_payload.get("tags"),
        [
            "strategy_explained",
            _label("type", strategy_type),
            _label("family", candidate_family),
            _label("generator", generator_type),
            _label("risk", risk_level),
            _resolve_horizon_label(holding_horizon),
            "targeted_universe" if target_symbols else None,
            _label("source", source),
        ],
        limit=18,
    )

    result = {
        **inherited,
        "version": EXPLANATION_VERSION,
        "summary": summary,
        "labels": labels,
        "strategy_type": strategy_type,
        "strategy_family": candidate_family,
        "generator": {
            key: value
            for key, value in {
                "type": generator_type,
                "source": source,
                "provider": generation_reason.get("provider"),
                "model": generation_reason.get("model"),
            }.items()
            if _non_empty(value)
        },
        "why_generated": why_generated,
        "thesis": thesis,
        "target_scope": {
            key: value
            for key, value in {
                "symbols": target_symbols,
                "symbol_count": len(target_symbols),
                "stock_pool": _compact_keys(stock_pool, ("selection_mode", "symbols", "filters", "rationale")),
                "theme": _first(research_task.get("theme"), research_task.get("theme_name"), event_context.get("theme_name")),
                "opportunity_type": research_task.get("opportunity_type"),
                "validation_focus": validation_profile.get("validation_focus"),
            }.items()
            if _non_empty(value)
        },
        "signal_logic": {
            key: value
            for key, value in {
                "selection_logic": selection_logic,
                "entry": _first(trade_plan.get("entry_bias"), trade_plan.get("entry_rule"), trade_plan.get("entry_policy")),
                "exit": _first(trade_plan.get("exit_bias"), trade_plan.get("exit_rule"), trade_plan.get("exit_policy")),
                "rebalance": _compact(_first(payload.get("rebalance_rule"), params.get("rebalance_rule")), depth=1),
                "holding_horizon": _compact(holding_horizon, depth=1),
            }.items()
            if _non_empty(value)
        },
        "risk_notes": {
            key: value
            for key, value in {
                "risk_level": risk_level,
                "risk_rules": _compact(risk_rules, depth=1),
                "failure_mode": _compact(_first(payload.get("failure_mode"), params.get("failure_mode")), depth=1),
                "constraints": _compact_keys(constraint_check, ("status", "reason", "reject_reasons", "warnings")),
            }.items()
            if _non_empty(value)
        },
        "evidence": {
            key: value
            for key, value in {
                "generation_reason": _compact_keys(
                    generation_reason,
                    (
                        "source",
                        "provider",
                        "model",
                        "category",
                        "formula",
                        "rationale",
                        "fallback_reason",
                        "target_symbols",
                        "selection_logic",
                    ),
                ),
                "research_task": _compact_keys(
                    research_task,
                    (
                        "task_id",
                        "task_source",
                        "theme",
                        "theme_name",
                        "opportunity_type",
                        "direction",
                        "horizon",
                        "candidate_family",
                    ),
                ),
                "validation": _compact_keys(
                    {
                        **validation_profile,
                        "spec_completeness": _first(payload.get("spec_completeness"), params.get("spec_completeness")),
                        "completion_issues": _first(payload.get("completion_issues"), params.get("completion_issues")),
                    },
                    ("profile", "validation_focus", "primary_validation_layer", "spec_completeness", "completion_issues"),
                ),
                "metrics": metrics_summary,
            }.items()
            if _non_empty(value)
        },
    }
    return {key: value for key, value in result.items() if _non_empty(value) or key == "version"}


def render_strategy_description(
    name: str | None,
    explanation: Mapping[str, Any] | None,
    *,
    metrics: Mapping[str, Any] | None = None,
) -> str:
    """Render a compact multi-line description from an explanation contract."""

    payload = _mapping(explanation)
    lines: list[str] = []

    def add(prefix: str, value: Any) -> None:
        text = _text(value, limit=360)
        if not text:
            return
        line = f"{prefix}: {text}" if prefix else text
        if line not in lines:
            lines.append(line)

    add("", payload.get("summary") or name)
    add("Why", payload.get("why_generated"))
    target_scope = _mapping(payload.get("target_scope"))
    symbols = _string_list(target_scope.get("symbols"), limit=6)
    if symbols:
        add("Targets", ", ".join(symbols))
    signal_logic = _mapping(payload.get("signal_logic"))
    add("Entry", signal_logic.get("entry"))
    add("Exit", signal_logic.get("exit"))
    risk_notes = _mapping(payload.get("risk_notes"))
    add("Risk", risk_notes.get("risk_level"))
    metric_payload = _metric_summary(metrics or _mapping(_mapping(payload.get("evidence")).get("metrics")))
    metric_parts = [
        f"Sharpe {_format_float(metric_payload.get('sharpe_ratio'))}" if metric_payload.get("sharpe_ratio") is not None else None,
        f"Return {_format_pct(metric_payload.get('total_return'))}" if metric_payload.get("total_return") is not None else None,
        f"Drawdown {_format_pct(metric_payload.get('max_drawdown'))}" if metric_payload.get("max_drawdown") is not None else None,
        f"Win {_format_pct(metric_payload.get('win_rate'))}" if metric_payload.get("win_rate") is not None else None,
    ]
    metrics_line = " | ".join(part for part in metric_parts if part)
    add("Backtest", metrics_line)
    labels = _string_list(payload.get("labels"), limit=8)
    if labels:
        add("Labels", ", ".join(labels))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Completeness / incubation explanation / reason-code map (P0-P2)
# ---------------------------------------------------------------------------

INCUBATION_EXPLANATION_VERSION = "incubation_explanation.v1"
CASE_FILE_VERSION = "strategy_case_file.v1"

# Stable machine codes -> Chinese operator-facing explanations.
REASON_CODE_ZH: dict[str, str] = {
    "execution_audit_missing": "缺少执行审计快照，无法证明 paper 成交与持仓闭环。",
    "execution_audit_bootstrap_pending": "执行审计仍在 bootstrap：尚无足够已实现成交样本。",
    "execution_audit_gate:missing": "执行 hard gate 状态为 missing：尚无可用审计证据。",
    "execution_audit_gate:bootstrap_pending": "执行 hard gate 仍为 bootstrap_pending：需更多 closed round-trip。",
    "execution_audit_gate:insufficient_samples": "已实现成交样本不足 production floor。",
    "execution_audit_gate:failed_metrics": "执行指标未过 hard gate（期望收益/转化效率不合格）。",
    "execution_audit_gate:bootstrap_ready": "样本过 bootstrap 门槛但未达 production trade floor，不能当 production 通过。",
    "execution_audit_gate:passed": "执行 hard gate 已通过。",
    "missing_signal_id_on_orders": "部分订单缺少 signal_id，血缘不完整。",
    "missing_realized_trade_evidence": "尚无已实现成交证据（signals/orders/trades 为空或不足）。",
    "trades_without_signals": "有成交记录但缺少对应信号，血缘断裂。",
    "bootstrap_factory_runtime": "策略/信号/订单/成交全空：需启动四工厂 + SignalTracker 并确认同一 SQLite。",
    "start_signal_tracker_sidecar": "运行池存在但 strategy_signals=0：SignalTracker sidecar 未产出证据。",
    "refresh_signal_tracker_sidecar": "信号证据过期：需重新运行 SignalTracker。",
    "restore_exit_continuity": "有未平仓但无 closed round-trip：退出路径饥饿。",
    "investigate_exit_signal_gap": "有退出信号但未形成退出订单：需查候选选择/血缘 fail-closed。",
    "accumulate_realized_samples": "hard gate 多为 missing/bootstrap：需积累真实 paper 成交与平仓。",
    "explain_formal_blockers": "formal=0 且存在可统计 blockers：按 top blocker 修复证据。",
    "explain_empty_formal_pool": "formal=0 且 blockers 未暴露：需检查 hard gate 直方图与审计快照。",
    "repair_signal_lineage": "订单 signal_id 覆盖率不足：启用 fail-closed 并回填血缘。",
    "primary_effective_n": "主持有周期有效前向样本不足 promotion floor。",
    "secondary_effective_n": "次持有周期有效前向样本不足。",
    "primary_skill_lcb": "主信号 skill 下界未 > 0。",
    "secondary_skill_lcb": "次信号 skill 下界未 > 0。",
    "recent_primary_skill_lcb": "近期主信号 skill 下界未 > 0。",
    "coverage_ratio": "信号覆盖率未达 promotion floor。",
    "stability_gap": "稳定性缺口过大或缺失。",
    "stability_gap_missing": "稳定性缺口字段缺失（fail-closed）。",
    "execution_hard_gate_passed": "执行 hard gate 未通过，不能 promotion_ready。",
    "risk_hard_gate_status": "风险 hard gate 未 passed。",
    "no_blockers": "仍存在未清理 blockers。",
    "explanation_incomplete": "策略说明不完整：缺少 thesis/rationale 或 why_generated。",
    "monitor": "当前计数器未发现关键工厂生产阻塞。",
}


def explain_reason_code(code: Any) -> str:
    token = str(code or "").strip()
    if not token:
        return "未提供原因码。"
    if token in REASON_CODE_ZH:
        return REASON_CODE_ZH[token]
    # prefix match for dynamic codes like execution_audit_gate:foo
    for key, text in REASON_CODE_ZH.items():
        if token.startswith(key):
            return text
    if token.startswith("cross_regime_skill_lcb_non_positive"):
        return f"跨 regime skill 非正：{token.split(':', 1)[-1]}"
    if ":" in token:
        head, tail = token.split(":", 1)
        if head in REASON_CODE_ZH:
            return f"{REASON_CODE_ZH[head]}（{tail}）"
    return f"未映射原因码：{token}"


def evaluate_strategy_explanation_completeness(
    explanation: Mapping[str, Any] | None,
    *,
    require_rationale: bool = True,
) -> dict[str, Any]:
    """Return completeness report for generation-side explanation."""

    payload = _mapping(explanation)
    why = _text(payload.get("why_generated"), limit=500) or ""
    thesis = _text(payload.get("thesis"), limit=500)
    summary = _text(payload.get("summary"), limit=500)
    signal_logic = _mapping(payload.get("signal_logic"))
    target_scope = _mapping(payload.get("target_scope"))
    evidence = _mapping(payload.get("evidence"))
    generation_reason = _mapping(evidence.get("generation_reason") or payload.get("generation_reason"))
    rationale = _text(
        _first(generation_reason.get("rationale"), thesis, payload.get("summary")),
        limit=240,
    )
    missing: list[str] = []
    if not summary:
        missing.append("summary")
    if not why:
        missing.append("why_generated")
    if require_rationale and not rationale:
        missing.append("rationale_or_thesis")
    if not signal_logic.get("entry") and not signal_logic.get("exit"):
        missing.append("signal_logic_entry_or_exit")
    if not target_scope.get("symbols") and not target_scope.get("theme"):
        missing.append("target_scope")
    if not generation_reason.get("source") and not _mapping(payload.get("generator")).get("type"):
        missing.append("generator_source")

    complete = not missing
    quality = "complete" if complete else ("partial" if why or thesis or summary else "empty")
    return {
        "complete": complete,
        "quality": quality,
        "missing_fields": missing,
        "has_why_generated": bool(why),
        "has_thesis": bool(thesis),
        "has_rationale": bool(rationale),
        "human_summary": (
            "策略说明完整，可向用户展示为什么生成。"
            if complete
            else "策略说明不完整：" + "、".join(missing) + "。生成侧应补齐 rationale/thesis 与 why_generated。"
        ),
    }


def ensure_strategy_explanation(
    strategy: Mapping[str, Any] | None,
    *,
    metrics: Mapping[str, Any] | None = None,
    source: str | None = None,
    require_rationale: bool = True,
) -> dict[str, Any]:
    """Build explanation and attach completeness block (always)."""

    explanation = build_strategy_explanation(strategy, metrics=metrics, source=source)
    completeness = evaluate_strategy_explanation_completeness(
        explanation,
        require_rationale=require_rationale,
    )
    labels = list(explanation.get("labels") or [])
    if completeness.get("complete"):
        if "explanation_complete" not in labels:
            labels.append("explanation_complete")
    else:
        if "explanation_incomplete" not in labels:
            labels.append("explanation_incomplete")
    explanation["labels"] = labels
    explanation["completeness"] = completeness
    return explanation


def build_incubation_explanation(
    *,
    strategy: Mapping[str, Any] | None = None,
    overview: Mapping[str, Any] | None = None,
    pipeline_stage: Any = None,
    decision: Any = None,
    blockers: Any = None,
    risk_flags: Any = None,
    hard_gate_status: Any = None,
    promotion_ready: Any = None,
    evidence_snapshot: Mapping[str, Any] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Human + machine narrative for why a strategy is incubating / blocked."""

    payload = _mapping(strategy)
    params = _mapping(payload.get("params"))
    overview_payload = _mapping(overview)
    evidence = _mapping(evidence_snapshot)
    stage = _text(
        _first(
            pipeline_stage,
            overview_payload.get("pipeline_stage"),
            overview_payload.get("stage"),
            params.get("pipeline_stage"),
            payload.get("status"),
        ),
        limit=80,
    )
    decision_token = _text(_first(decision, overview_payload.get("decision")), limit=80)
    hard_status = _text(
        _first(
            hard_gate_status,
            overview_payload.get("execution_audit_gate_status"),
            overview_payload.get("execution_hard_gate_status"),
            _mapping(overview_payload.get("execution_quality")).get("execution_audit_gate_status"),
        ),
        limit=80,
    )
    promotion = overview_payload.get("promotion_ready") if promotion_ready is None else promotion_ready
    if isinstance(promotion, Mapping):
        promotion_flag = bool(promotion.get("promotion_ready"))
        promotion_blockers = list(promotion.get("blockers") or [])
    else:
        promotion_flag = bool(promotion)
        promotion_blockers = []

    blocker_codes = _string_list(blockers, overview_payload.get("blockers"), promotion_blockers, limit=12)
    risk_codes = _string_list(risk_flags, overview_payload.get("risk_flags"), limit=8)
    why_parts: list[str] = []
    if stage:
        why_parts.append(f"当前阶段={stage}")
    if decision_token:
        why_parts.append(f"孵化决策={decision_token}")
    if hard_status:
        why_parts.append(f"执行门禁={hard_status}（{explain_reason_code(f'execution_audit_gate:{hard_status}')}）")
    if promotion_flag:
        why_parts.append("promotion_ready=true")
    else:
        why_parts.append("promotion_ready=false")
    if blocker_codes:
        top = blocker_codes[0]
        why_parts.append(f"主阻塞={top}：{explain_reason_code(top)}")
    if risk_codes:
        why_parts.append(f"风险标记={','.join(risk_codes[:4])}")

    signals = evidence.get("signals_total")
    orders = evidence.get("orders_total")
    trades = evidence.get("trades_total")
    open_pos = evidence.get("open_positions")
    closed = evidence.get("closed_positions") or evidence.get("closed")
    evidence_bits = []
    for label, value in (
        ("signals", signals),
        ("orders", orders),
        ("trades", trades),
        ("open", open_pos),
        ("closed", closed),
    ):
        if value is not None:
            evidence_bits.append(f"{label}={value}")
    if evidence_bits:
        why_parts.append("证据快照 " + ", ".join(evidence_bits))

    next_needed: list[str] = []
    if hard_status in {None, "", "missing", "bootstrap_pending", "insufficient_samples", "bootstrap_ready"}:
        next_needed.append("积累真实 paper 成交与 closed round-trip，使 execution_audit_gate 达到 passed")
    if hard_status == "failed_metrics":
        next_needed.append("修复 expectancy/转化效率指标，或淘汰该策略")
    if blocker_codes:
        next_needed.append(f"优先处理 blocker：{blocker_codes[0]}（{explain_reason_code(blocker_codes[0])}）")
    if not evidence_bits or (signals in (0, None) and orders in (0, None)):
        next_needed.append("确认 SignalTracker sidecar 与孵化 paper 引擎在同一 DB 上运行")
    if not next_needed:
        next_needed.append("继续观察命中率与退出连续性，等待 promotion_ready 全检查通过")

    human = "；".join(why_parts) if why_parts else "孵化说明不足：缺少 stage/gate/blocker 上下文。"
    return {
        "version": INCUBATION_EXPLANATION_VERSION,
        "source": source or "incubation_explanation",
        "pipeline_stage": stage,
        "decision": decision_token,
        "hard_gate_status": hard_status,
        "promotion_ready": promotion_flag,
        "why_incubating": human,
        "why_blocked": (
            None
            if promotion_flag
            else (
                f"{explain_reason_code(blocker_codes[0])}（{blocker_codes[0]}）"
                if blocker_codes
                else explain_reason_code(f"execution_audit_gate:{hard_status}" if hard_status else "missing_realized_trade_evidence")
            )
        ),
        "blockers": [{"code": code, "detail_zh": explain_reason_code(code)} for code in blocker_codes],
        "risk_flags": risk_codes,
        "next_evidence_needed": next_needed,
        "evidence_snapshot": {k: v for k, v in evidence.items() if _non_empty(v)},
        "labels": _string_list(
            [
                "incubation_explained",
                _label("stage", stage),
                _label("gate", hard_status),
                "promotion_ready" if promotion_flag else "promotion_blocked",
            ],
            limit=12,
        ),
    }


def build_strategy_case_file(
    *,
    strategy: Mapping[str, Any] | None = None,
    strategy_explanation: Mapping[str, Any] | None = None,
    incubation_explanation: Mapping[str, Any] | None = None,
    metrics: Mapping[str, Any] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Merge generation + incubation explanations into one operator case file."""

    payload = _mapping(strategy)
    params = _mapping(payload.get("params"))
    gen = _mapping(strategy_explanation) or ensure_strategy_explanation(
        payload,
        metrics=metrics,
        source=source or "case_file",
    )
    inc = _mapping(incubation_explanation)
    completeness = _mapping(gen.get("completeness")) or evaluate_strategy_explanation_completeness(gen)
    return {
        "version": CASE_FILE_VERSION,
        "source": source or "strategy_case_file",
        "strategy_id": _first(payload.get("id"), payload.get("strategy_id"), params.get("strategy_id")),
        "name": _text(_first(payload.get("name"), params.get("name")), limit=120),
        "status": _text(_first(payload.get("status"), params.get("status")), limit=40),
        "generation": gen,
        "incubation": inc or None,
        "completeness": completeness,
        "why_generated": gen.get("why_generated"),
        "why_incubating": inc.get("why_incubating") if inc else None,
        "why_blocked": inc.get("why_blocked") if inc else None,
        "next_evidence_needed": list(inc.get("next_evidence_needed") or []) if inc else [],
        "readable": {
            "generation_zh": gen.get("why_generated"),
            "incubation_zh": inc.get("why_incubating") if inc else None,
            "blocked_zh": inc.get("why_blocked") if inc else None,
            "completeness_zh": completeness.get("human_summary"),
        },
    }


__all__ = [
    "CASE_FILE_VERSION",
    "EXPLANATION_VERSION",
    "INCUBATION_EXPLANATION_VERSION",
    "REASON_CODE_ZH",
    "build_incubation_explanation",
    "build_strategy_case_file",
    "build_strategy_explanation",
    "ensure_strategy_explanation",
    "evaluate_strategy_explanation_completeness",
    "explain_reason_code",
    "render_strategy_description",
]

