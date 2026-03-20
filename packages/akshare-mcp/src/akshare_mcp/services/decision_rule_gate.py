"""Rule and suitability gates for unified decision."""

from __future__ import annotations

from typing import Any

from ..tools.managers.compliance_manager import evaluate_order_compliance


STYLE_POSITION_CAP = {
    "aggressive": 0.35,
    "balanced": 0.20,
    "conservative": 0.10,
}

USER_RISK_CAP = {
    "aggressive": 0.35,
    "moderate": 0.20,
    "conservative": 0.10,
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize_style(style: str | None) -> str:
    raw = str(style or "").strip().lower()
    if raw in {"aggressive", "balanced", "conservative"}:
        return raw
    return "balanced"


def _flag(
    name: str,
    status: str,
    severity: str,
    message: str,
    *,
    blocking: bool = False,
    source: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "severity": severity,
        "blocking": blocking,
        "message": message,
        "source": source,
    }


def build_rule_gates(
    *,
    code: str,
    investment_style: str,
    stock_context: dict[str, Any],
    quant_context: dict[str, Any],
    event_context: dict[str, Any],
    user_context: dict[str, Any],
) -> dict[str, Any]:
    """Build non-blocking and blocking decision gates."""
    style = _normalize_style(investment_style)
    user_bucket = str(user_context.get("risk_bucket") or "moderate")
    position_cap_pct = min(STYLE_POSITION_CAP.get(style, 0.20), USER_RISK_CAP.get(user_bucket, 0.20))
    flags: list[dict[str, Any]] = []
    veto_reason: str | None = None
    gate_adjustment = 0.0

    current_price = stock_context.get("current_price") or 1.0
    compliance = evaluate_order_compliance(code, "buy", 100, current_price)
    if compliance.get("blocked"):
        veto_reason = "indicative_order_blocked"
        flags.append(
            _flag(
                "compliance",
                "blocked",
                "high",
                "指示性买入订单未通过合规校验",
                blocking=True,
                source="compliance_manager",
            )
        )
    elif compliance.get("warnings"):
        flags.append(
            _flag(
                "compliance",
                "warn",
                "low",
                str(compliance["warnings"][0]),
                source="compliance_manager",
            )
        )

    if event_context.get("hard_risk"):
        veto_reason = veto_reason or "event_risk_veto"
        flags.append(
            _flag(
                "event_risk",
                "blocked",
                "high",
                "事件面出现监管风险且文本情绪偏空，触发硬闸门",
                blocking=True,
                source="decision_event_builder",
            )
        )
        gate_adjustment -= 20.0

    volatility_20d = stock_context.get("volatility_20d")
    volatility_threshold = {"aggressive": 0.06, "balanced": 0.045, "conservative": 0.03}[style]
    if isinstance(volatility_20d, (int, float)) and volatility_20d > volatility_threshold:
        flags.append(
            _flag(
                "volatility",
                "warn",
                "medium",
                f"20 日波动率 {volatility_20d:.3f} 高于 {style} 风格阈值",
                source="decision_context_builder",
            )
        )
        gate_adjustment -= 6.0
        position_cap_pct *= 0.8

    if style == "aggressive" and user_bucket == "conservative":
        flags.append(
            _flag(
                "user_suitability",
                "warn",
                "medium",
                "请求风格偏激进，但用户画像更接近稳健型",
                source="decision_context_builder",
            )
        )
        gate_adjustment -= 8.0
        position_cap_pct *= 0.7

    weighted_profile = user_context.get("weighted_profile") or {}
    herd_tendency = weighted_profile.get("herd_tendency")
    greed_fear_axis = weighted_profile.get("greed_fear_axis")
    if isinstance(herd_tendency, (int, float)) and herd_tendency >= 0.7:
        flags.append(
            _flag(
                "behavior_bias",
                "warn",
                "medium",
                "用户画像显示从众倾向偏高，建议降低单次试仓幅度",
                source="user_profile_snapshots",
            )
        )
        gate_adjustment -= 4.0
        position_cap_pct *= 0.9
    if isinstance(greed_fear_axis, (int, float)) and abs(greed_fear_axis) >= 0.65:
        flags.append(
            _flag(
                "emotion_bias",
                "warn",
                "low",
                "近期情绪偏离中性，统一决策已主动下调仓位建议",
                source="user_profile_snapshots",
            )
        )
        gate_adjustment -= 2.0
        position_cap_pct *= 0.95

    if not flags:
        flags.append(
            _flag(
                "baseline",
                "pass",
                "low",
                "未触发额外硬闸门，按统一决策常规流程输出",
                source="decision_rule_gate",
            )
        )

    return {
        "blocked": veto_reason is not None,
        "veto_reason": veto_reason,
        "flags": flags,
        "gate_adjustment": round(gate_adjustment, 2),
        "position_cap_pct": round(_clamp(float(position_cap_pct), 0.0, 0.35), 4),
        "requested_style": style,
        "user_risk_level": user_context.get("risk_level"),
    }
