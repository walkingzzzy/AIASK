"""Unified decision contracts and payload builders."""

from __future__ import annotations

from typing import Any

from ..utils import now_iso, resolve_security_code
from .decision_context_builder import build_stock_context, build_user_context
from .decision_event_builder import build_event_context
from .decision_fusion import fuse_unified_decision
from .decision_quant_builder import build_quant_context
from .decision_rule_gate import build_rule_gates

UNIFIED_DECISION_VERSION = "unified-decision.v1"


def _normalize_style(style: str | None) -> str:
    raw = str(style or "").strip().lower()
    if raw in {"aggressive", "balanced", "conservative"}:
        return raw
    return "balanced"


def _provenance_entry(source: str, dataset: str, timestamp: str | None = None) -> dict[str, Any]:
    return {
        "source": source,
        "dataset": dataset,
        "timestamp": timestamp or now_iso(),
    }


def _merge_warnings(*sections: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    for section in sections:
        for item in section.get("warnings", []) or []:
            label = str(item or "").strip()
            if not label or label in seen:
                continue
            warnings.append(label)
            seen.add(label)
    return warnings


def _build_summary_payload(
    *,
    code: str,
    investment_style: str,
    user_id: str | None,
    stock_context: dict[str, Any],
    quant_context: dict[str, Any],
    event_context: dict[str, Any],
    user_context: dict[str, Any],
    gate: dict[str, Any],
    fusion: dict[str, Any],
) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "version": UNIFIED_DECISION_VERSION,
        "scene": "unified_decision",
        "code": code,
        "name": stock_context.get("name") or "",
        "action": fusion["action"],
        "confidence": fusion["confidence"],
        "final_score": fusion["final_score"],
        "summary": fusion["summary"],
        "reasons": fusion["reasons"],
        "risks": fusion["risks"],
        "gate_flags": gate.get("flags", []),
        "veto_reason": fusion.get("veto_reason"),
        "position_signal": fusion.get("position_signal"),
        "data_provenance": [
            _provenance_entry("decision_context_builder", "investment_analysis", stock_context.get("timestamp")),
            _provenance_entry("decision_quant_builder", "factor_profile+signal_hit_rate", quant_context.get("timestamp")),
            _provenance_entry("decision_event_builder", "stock_text_signals", event_context.get("timestamp")),
            _provenance_entry("decision_context_builder", "user_context", user_context.get("timestamp")),
        ],
        "compliance_notice": "本结果仅供研究与辅助决策，不构成投资建议。",
        "details_available": True,
        "details_hint": {
            "tool": "get_unified_decision_details",
            "args": {
                "code": code,
                "investment_style": investment_style,
                **({"user_id": user_id} if user_id else {}),
            },
        },
        "diagnostics": fusion.get("score_breakdown", {}),
        "warnings": _merge_warnings(stock_context, quant_context, event_context, user_context),
        "timestamp": timestamp,
    }


async def _build_pipeline_payload(
    *,
    code: str,
    investment_style: str = "balanced",
    user_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_code = resolve_security_code(code)
    if not normalized_code:
        raise ValueError("需要提供股票代码（支持 code / stock_code / symbol / ticker）")

    style = _normalize_style(investment_style)
    stock_context = await build_stock_context(normalized_code)
    quant_context = await build_quant_context(normalized_code)
    event_context = await build_event_context(normalized_code)
    user_context = await build_user_context(user_id)
    gate = build_rule_gates(
        code=normalized_code,
        investment_style=style,
        stock_context=stock_context,
        quant_context=quant_context,
        event_context=event_context,
        user_context=user_context,
    )
    fusion = fuse_unified_decision(
        stock_context=stock_context,
        quant_context=quant_context,
        event_context=event_context,
        user_context=user_context,
        gate=gate,
    )
    summary = _build_summary_payload(
        code=normalized_code,
        investment_style=style,
        user_id=user_id,
        stock_context=stock_context,
        quant_context=quant_context,
        event_context=event_context,
        user_context=user_context,
        gate=gate,
        fusion=fusion,
    )
    details = {
        "requested": {
            "code": normalized_code,
            "investment_style": style,
            "user_id": user_id,
        },
        "stock_context": stock_context,
        "quant_context": quant_context,
        "event_context": event_context,
        "user_context": user_context,
        "gate": gate,
        "fusion": fusion,
    }
    return summary, details


async def get_unified_decision_summary_payload(
    *,
    code: str,
    investment_style: str = "balanced",
    user_id: str | None = None,
) -> dict[str, Any]:
    summary, _ = await _build_pipeline_payload(
        code=code,
        investment_style=investment_style,
        user_id=user_id,
    )
    return summary


async def get_unified_decision_details_payload(
    *,
    code: str,
    investment_style: str = "balanced",
    user_id: str | None = None,
) -> dict[str, Any]:
    summary, details = await _build_pipeline_payload(
        code=code,
        investment_style=investment_style,
        user_id=user_id,
    )
    return {
        **summary,
        "details": details,
    }
