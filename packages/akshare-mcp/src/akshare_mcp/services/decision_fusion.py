"""Fusion logic for unified decision summary/details."""

from __future__ import annotations

from statistics import pstdev
from typing import Any


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _decide_action(final_score: float, veto_reason: str | None, stock_recommendation: str) -> str:
    if veto_reason:
        return "watch"
    if final_score >= 74:
        return "buy"
    if final_score >= 60:
        return "hold"
    if final_score >= 42:
        return "watch"
    if stock_recommendation == "sell":
        return "sell"
    return "reduce"


def _position_label(suggested_position_pct: float, action: str, veto_reason: str | None) -> str:
    if veto_reason or action in {"watch", "sell"} or suggested_position_pct <= 0:
        return "暂不出手"
    if suggested_position_pct >= 0.20:
        return "可分批布局"
    if suggested_position_pct >= 0.10:
        return "小仓试探"
    return "轻仓观察"


def fuse_unified_decision(
    *,
    stock_context: dict[str, Any],
    quant_context: dict[str, Any],
    event_context: dict[str, Any],
    user_context: dict[str, Any],
    gate: dict[str, Any],
) -> dict[str, Any]:
    """Fuse stock/quant/event/user evidence into a single decision payload."""
    stock_score = float(stock_context.get("score", 50.0) or 50.0)
    quant_score = float(quant_context.get("score", 50.0) or 50.0)
    event_score = float(event_context.get("score", 50.0) or 50.0)
    gate_adjustment = float(gate.get("gate_adjustment", 0.0) or 0.0)

    score_breakdown = {
        "stock_context": round(stock_score, 2),
        "quant": round(quant_score, 2),
        "event": round(event_score, 2),
        "gate_adjustment": round(gate_adjustment, 2),
    }
    weights = {"stock_context": 0.55, "quant": 0.25, "event": 0.20}
    weighted_score = (
        stock_score * weights["stock_context"]
        + quant_score * weights["quant"]
        + event_score * weights["event"]
    )
    final_score = round(_clamp(weighted_score + gate_adjustment, 0.0, 100.0), 2)

    inputs = [stock_score, quant_score, event_score]
    dispersion = pstdev(inputs) if len(inputs) > 1 else 0.0
    confidence = 0.52 + max(0.0, 18.0 - dispersion) / 100.0
    if gate.get("blocked"):
        confidence -= 0.08
    confidence = round(_clamp(confidence, 0.35, 0.92), 4)

    stock_recommendation = str(stock_context.get("recommendation") or "wait")
    veto_reason = gate.get("veto_reason")
    action = _decide_action(final_score, veto_reason, stock_recommendation)

    reasons = _unique(
        list(stock_context.get("highlights", []))[:3]
        + list(quant_context.get("reasons", []))[:2]
        + list(event_context.get("reasons", []))[:2]
    )
    risks = _unique(
        list(stock_context.get("risks", []))[:3]
        + list(quant_context.get("risks", []))[:2]
        + list(event_context.get("risks", []))[:2]
        + [flag.get("message", "") for flag in gate.get("flags", []) if flag.get("status") != "pass"]
    )

    cap_pct = float(gate.get("position_cap_pct", 0.0) or 0.0)
    if veto_reason or action in {"watch", "sell"}:
        suggested_position_pct = 0.0
    elif final_score >= 80:
        suggested_position_pct = cap_pct
    elif final_score >= 65:
        suggested_position_pct = cap_pct * 0.75
    elif final_score >= 52:
        suggested_position_pct = cap_pct * 0.45
    else:
        suggested_position_pct = cap_pct * 0.20
    suggested_position_pct = round(_clamp(suggested_position_pct, 0.0, cap_pct), 4)

    summary_parts = []
    if veto_reason:
        summary_parts.append("统一闸门触发风险阻断，当前不建议直接执行买入动作。")
    elif action == "buy":
        summary_parts.append("多维证据整体偏正面，可以按节奏分批布局。")
    elif action == "hold":
        summary_parts.append("正面证据仍占优，但更适合耐心持有或等待更优入场点。")
    elif action == "reduce":
        summary_parts.append("综合分数偏弱，需控制仓位并降低决策激进度。")
    else:
        summary_parts.append("当前证据尚未形成高把握度交易窗口，建议继续观察。")
    if risks:
        summary_parts.append(f"主要风险集中在：{risks[0]}")

    position_signal = {
        "label": _position_label(suggested_position_pct, action, veto_reason),
        "suggested_position_pct": suggested_position_pct,
        "position_cap_pct": round(cap_pct, 4),
        "requested_style": gate.get("requested_style"),
        "user_risk_level": gate.get("user_risk_level"),
    }

    return {
        "action": action,
        "confidence": confidence,
        "final_score": final_score,
        "summary": " ".join(summary_parts).strip(),
        "reasons": reasons,
        "risks": risks,
        "veto_reason": veto_reason,
        "position_signal": position_signal,
        "score_breakdown": score_breakdown,
        "weights": weights,
    }
