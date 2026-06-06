"""Evidence-first alpha helpers for Strategy Factory candidates.

The helpers in this module are intentionally pure: they only inspect a
candidate and the current market snapshot, then attach compact evidence,
direction, confidence, and generation-quality diagnostics. Storage, LLM calls,
and trading side effects stay outside the domain layer.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import date, datetime, time, timezone
from typing import Any, Mapping, Optional

_EMPTY_VALUES = (None, "", [], {})
_DIRECTION_ALIASES = {
    "up": "up",
    "bullish": "up",
    "long": "up",
    "buy": "up",
    "rise": "up",
    "rising": "up",
    "positive": "up",
    "down": "down",
    "bearish": "down",
    "short": "down",
    "sell": "down",
    "fall": "down",
    "falling": "down",
    "negative": "down",
    "neutral": "neutral",
    "flat": "neutral",
    "sideways": "neutral",
    "hold": "neutral",
}
_FACTOR_SOURCE_TYPES = {"factor_ic_validated", "active_factor_pool"}
_EVENT_SOURCE_TYPES = {"event_catalyst"}
_NON_PROXY_SOURCE_TYPES = {
    "factor_ic_validated",
    "active_factor_pool",
    "event_catalyst",
    "price_volume_confirmation",
    "fund_flow",
    "regime_context",
}
_TEMPLATE_SOURCE_TYPES = {"template_fallback", "rule_template_contract", "strategy_logic"}
_SHORT_BIAS_TYPES = {"mean_reversion_short"}


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    if value in _EMPTY_VALUES:
        return []
    return [value]


def _string(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in _EMPTY_VALUES:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in _EMPTY_VALUES:
            return int(default)
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _candidate_value(candidate: Mapping[str, Any], key: str) -> Any:
    params = _as_dict(candidate.get("params"))
    if candidate.get(key) not in _EMPTY_VALUES:
        return candidate.get(key)
    if params.get(key) not in _EMPTY_VALUES:
        return params.get(key)
    return None


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in _EMPTY_VALUES:
            return value
    return None


def _normalize_direction(value: Any) -> Optional[str]:
    token = _string(value).lower().replace("-", "_").replace(" ", "_")
    if not token:
        return None
    if token in _DIRECTION_ALIASES:
        return _DIRECTION_ALIASES[token]
    if any(part in token for part in ("short", "bear", "sell", "risk_off", "negative")):
        return "down"
    if any(part in token for part in ("neutral", "hedge", "sideways")):
        return "neutral"
    if any(part in token for part in ("long", "bull", "buy", "repair", "breakout", "positive")):
        return "up"
    return None


def _direction_from_expected_move(value: Any) -> Optional[str]:
    if value in _EMPTY_VALUES:
        return None
    if isinstance(value, Mapping):
        payload = dict(value)
        for key in ("direction", "expected_direction", "bias"):
            direction = _normalize_direction(payload.get(key))
            if direction:
                return direction
        for key in ("return", "return_pct", "pct", "move", "expected_return"):
            if payload.get(key) in _EMPTY_VALUES:
                continue
            numeric = _safe_float(payload.get(key))
            if numeric > 0:
                return "up"
            if numeric < 0:
                return "down"
        return None
    direction = _normalize_direction(value)
    if direction:
        return direction
    text = _string(value)
    try:
        numeric = float(text.rstrip("%"))
    except (TypeError, ValueError):
        return None
    if "%" in text:
        numeric /= 100.0
    if numeric > 0:
        return "up"
    if numeric < 0:
        return "down"
    return "neutral"


def _coerce_iso_ts(value: Any) -> Optional[str]:
    if value in _EMPTY_VALUES:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time.min)
    else:
        text = _string(value)
        if not text:
            return None
        for parser in (
            lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")),
            lambda item: datetime.combine(date.fromisoformat(item[:10]), time.min),
        ):
            try:
                dt = parser(text)
                break
            except Exception:
                dt = None
        if dt is None:
            digits = "".join(ch for ch in text if ch.isdigit())
            if len(digits) < 8:
                return None
            try:
                dt = datetime(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
            except Exception:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _evidence_time_is_post_hoc(evidence_time: Any, prediction_as_of: Any) -> bool:
    ev_ts = _coerce_iso_ts(evidence_time)
    as_of_ts = _coerce_iso_ts(prediction_as_of)
    if not ev_ts or not as_of_ts:
        return False
    try:
        return datetime.fromisoformat(ev_ts) > datetime.fromisoformat(as_of_ts)
    except Exception:
        return False


def _evidence_source_type(raw_source: Any, candidate_source: str) -> str:
    source = _string(raw_source).lower()
    if source in {
        "factor_ic_validated",
        "active_factor_pool",
        "event_catalyst",
        "price_volume_confirmation",
        "fund_flow",
        "regime_context",
        "template_fallback",
    }:
        return source
    if source in {"factor_ic", "factor_research", "factor"}:
        return "factor_ic_validated"
    if source in {"factor_pool", "active_pool"}:
        return "active_factor_pool"
    if source in {"event_driven", "announcement", "news", "sector_catalyst"}:
        return "event_catalyst"
    if source in {"fund_flow", "north_fund", "margin"}:
        return "fund_flow"
    if source in {"fear_greed", "volatility", "macro", "regime"}:
        return "regime_context"
    if source in {"technical", "price_action", "volume", "kline", "ohlcv", "market_microstructure"}:
        return "price_volume_confirmation"
    if source in {"rule_template_contract", "strategy_logic", "quota_fill", "signal_variation", "unknown"}:
        return "template_fallback"
    if candidate_source == "factor_ic":
        return "factor_ic_validated"
    if candidate_source == "factor_pool":
        return "active_factor_pool"
    if candidate_source == "event_driven":
        return "event_catalyst"
    if candidate_source == "fund_flow":
        return "fund_flow"
    if candidate_source in {"fear_greed", "volatility"}:
        return "regime_context"
    return "template_fallback"


def _ic_direction(value: Any, *, strategy_type: str = "") -> Optional[str]:
    ic_value = _safe_float(value)
    if ic_value > 0:
        return "down" if strategy_type in _SHORT_BIAS_TYPES else "up"
    if ic_value < 0:
        return "up" if strategy_type in _SHORT_BIAS_TYPES else "down"
    return None


def _entry_from_existing_evidence(
    evidence: Mapping[str, Any],
    *,
    candidate_source: str,
    strategy_type: str,
    prediction_as_of: Any,
    index: int,
) -> dict[str, Any]:
    payload = dict(evidence or {})
    source_type = _evidence_source_type(payload.get("source_type") or payload.get("source"), candidate_source)
    support_metric = _as_dict(payload.get("support_metric") or payload.get("metrics"))
    direction = (
        _normalize_direction(payload.get("direction"))
        or _direction_from_expected_move(payload.get("expected_move"))
        or _ic_direction(
            _first_non_empty(
                support_metric.get("ic_value"),
                support_metric.get("rank_ic"),
                payload.get("ic_value"),
                payload.get("rank_ic"),
            ),
            strategy_type=strategy_type,
        )
    )
    proxy_only = bool(payload.get("proxy_only")) or source_type in _TEMPLATE_SOURCE_TYPES
    evidence_time = _first_non_empty(
        payload.get("evidence_time"),
        payload.get("occurred_at"),
        payload.get("as_of"),
        support_metric.get("evidence_time"),
    )
    post_hoc = _evidence_time_is_post_hoc(evidence_time, prediction_as_of)
    return {
        "evidence_id": _string(payload.get("evidence_id") or payload.get("id")) or f"ev_existing_{index}",
        "source_type": source_type,
        "direction": direction or "neutral",
        "weight": _evidence_weight(source_type, payload),
        "proxy_only": proxy_only,
        "summary": _string(payload.get("summary") or payload.get("description")) or source_type,
        "support_metric": support_metric,
        "evidence_time": evidence_time,
        "post_hoc": post_hoc,
    }


def _evidence_weight(source_type: str, payload: Mapping[str, Any]) -> float:
    support_metric = _as_dict(payload.get("support_metric") or payload.get("metrics"))
    if source_type == "factor_ic_validated":
        return _clamp(abs(_safe_float(_first_non_empty(support_metric.get("ic_value"), payload.get("ic_value")))) * 5.0, 0.25, 0.8)
    if source_type == "active_factor_pool":
        fitness = abs(_safe_float(_first_non_empty(support_metric.get("fitness"), payload.get("fitness"))))
        ic_value = abs(_safe_float(_first_non_empty(support_metric.get("current_ic"), payload.get("current_ic"))))
        return _clamp(0.25 + fitness * 0.08 + ic_value * 3.0, 0.25, 0.75)
    if source_type == "event_catalyst":
        strength = abs(_safe_float(_first_non_empty(payload.get("strength"), support_metric.get("strength"), 0.5), 0.5))
        return _clamp(0.35 + strength * 0.25, 0.35, 0.75)
    if source_type == "fund_flow":
        return 0.45
    if source_type == "price_volume_confirmation":
        return 0.35
    if source_type == "regime_context":
        return 0.25
    return 0.12


def _factor_research(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return _as_dict(snapshot.get("factor_research"))


def _factor_maps(snapshot: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, str]]:
    artifact = _factor_research(snapshot)
    ranked_factors = [dict(item or {}) for item in _as_list(artifact.get("ranked_factors")) if isinstance(item, Mapping)]
    factor_ic: dict[str, float] = {}
    factor_trend: dict[str, str] = {}
    for item in ranked_factors:
        name = _string(item.get("factor_name") or item.get("name"))
        if not name:
            continue
        factor_ic[name] = _safe_float(item.get("ic_value"))
        factor_trend[name] = _string(item.get("trend")).lower() or "flat"
    if factor_ic:
        return factor_ic, factor_trend
    for item in [
        *[dict(row or {}) for row in _as_list(artifact.get("active_factor_context")) if isinstance(row, Mapping)],
        *[dict(row or {}) for row in _as_list(snapshot.get("active_factor_context")) if isinstance(row, Mapping)],
    ]:
        name = _string(item.get("factor_name") or item.get("name"))
        if not name:
            continue
        factor_ic[name] = _safe_float(
            _first_non_empty(item.get("ic_value"), item.get("current_ic"), item.get("rank_ic"))
        )
        factor_trend[name] = _string(item.get("trend")).lower() or (
            "rising" if factor_ic[name] > 0 else "falling" if factor_ic[name] < 0 else "flat"
        )
    if factor_ic:
        return factor_ic, factor_trend
    return (
        {str(key): _safe_float(value) for key, value in _as_dict(snapshot.get("factor_ic")).items()},
        {str(key): _string(value).lower() or "flat" for key, value in _as_dict(snapshot.get("factor_ic_trend")).items()},
    )


def _active_factor_records(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    artifact = _factor_research(snapshot)
    records: list[dict[str, Any]] = []
    for raw in [
        *_as_list(artifact.get("ranked_factors")),
        *_as_list(artifact.get("active_factor_context")),
        *_as_list(snapshot.get("active_factor_context")),
    ]:
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        name = _string(item.get("factor_name") or item.get("name"))
        if not name:
            continue
        ic_value = _safe_float(
            _first_non_empty(item.get("ic_value"), item.get("current_ic"), item.get("rank_ic"))
        )
        records.append(
            {
                "factor_name": name,
                "family": _string(item.get("family")).lower(),
                "ic_value": ic_value,
                "trend": _string(item.get("trend")).lower()
                or ("rising" if ic_value > 0 else "falling" if ic_value < 0 else "flat"),
            }
        )
    deduped: dict[str, dict[str, Any]] = {}
    for record in records:
        name = str(record.get("factor_name"))
        existing = deduped.get(name)
        if existing is None or abs(_safe_float(record.get("ic_value"))) > abs(_safe_float(existing.get("ic_value"))):
            deduped[name] = record
    return list(deduped.values())


def _inferred_factor_names_for_candidate(
    candidate: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    factor_ic: Mapping[str, float],
) -> list[str]:
    strategy_type = _string(candidate.get("strategy_type")).lower()
    records = _active_factor_records(snapshot)
    if not records and factor_ic:
        records = [
            {"factor_name": name, "family": "", "ic_value": _safe_float(value), "trend": ""}
            for name, value in dict(factor_ic).items()
        ]
    if not records:
        return []

    positive = [item for item in records if _safe_float(item.get("ic_value")) > 0]
    negative = [item for item in records if _safe_float(item.get("ic_value")) < 0]

    def _rank(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(items, key=lambda item: abs(_safe_float(item.get("ic_value"))), reverse=True)

    def _family_or_name_matches(item: Mapping[str, Any], *tokens: str) -> bool:
        text = " ".join([
            _string(item.get("factor_name")).lower(),
            _string(item.get("family")).lower(),
        ])
        return any(token and token in text for token in tokens)

    if strategy_type in {"momentum", "ma_cross", "volatility_breakout", "event_structure_breakout"}:
        preferred = [item for item in positive if _family_or_name_matches(item, "momentum", "trend", "breakout")]
        chosen = _rank(preferred or positive or records)[:1]
    elif strategy_type in {"mean_reversion_short", "margin_divergence"}:
        preferred = [item for item in positive if _family_or_name_matches(item, "momentum", "crowding", "trend")]
        chosen = _rank(preferred or positive or records)[:1]
    elif strategy_type in {"rsi", "gap_fill"}:
        preferred = [item for item in negative if _family_or_name_matches(item, "reversal", "mean", "liquidity", "custom")]
        chosen = _rank(preferred or negative or records)[:1]
    elif strategy_type in {"multi_factor", "fundamental_multi_factor"}:
        chosen = _rank(records)[:3]
    elif strategy_type in {"quality_factor", "value_factor", "growth_factor"}:
        preferred = [
            item
            for item in records
            if _family_or_name_matches(item, "quality", "value", "growth", "liquidity", "custom", "momentum")
        ]
        chosen = _rank(preferred or records)[:1]
    else:
        chosen = _rank(records)[:1]
    return [_string(item.get("factor_name")) for item in chosen if _string(item.get("factor_name"))]


def _selected_factor_names(candidate: Mapping[str, Any]) -> list[str]:
    params = _as_dict(candidate.get("params"))
    names = []
    for value in (
        params.get("factor_name"),
        candidate.get("factor_name"),
        params.get("factor_pool_factor_name"),
        candidate.get("factor_pool_factor_name"),
        _as_dict(candidate.get("factor_pool_metadata")).get("factor_name"),
    ):
        token = _string(value)
        if token:
            names.append(token)
    for mapping in (
        _as_dict(params.get("factor_weights")),
        _as_dict(candidate.get("factor_weights")),
    ):
        names.extend(_string(key) for key in mapping if _string(key))
    return list(dict.fromkeys(names))


def _candidate_source(candidate: Mapping[str, Any]) -> str:
    generation_reason = _as_dict(candidate.get("generation_reason"))
    return _string(generation_reason.get("source") or candidate.get("source")).lower() or "unknown"


def _snapshot_factor_entries(candidate: Mapping[str, Any], snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    params = _as_dict(candidate.get("params"))
    strategy_type = _string(candidate.get("strategy_type")).lower()
    entries: list[dict[str, Any]] = []
    factor_ic, factor_trend = _factor_maps(snapshot)
    selected_names = _selected_factor_names(candidate)
    if not selected_names:
        selected_names = _inferred_factor_names_for_candidate(candidate, snapshot, factor_ic)

    direct_ic = _first_non_empty(
        params.get("factor_ic"),
        params.get("factor_pool_current_ic"),
        candidate.get("factor_ic"),
        _as_dict(candidate.get("factor_pool_metadata")).get("current_ic"),
    )
    if direct_ic not in _EMPTY_VALUES:
        name = selected_names[0] if selected_names else _string(params.get("factor_name") or "candidate_factor")
        entries.append(
            {
                "evidence_id": f"ev_factor_{len(entries) + 1}",
                "source_type": "factor_ic_validated"
                if _candidate_source(candidate) == "factor_ic"
                else "active_factor_pool",
                "direction": _ic_direction(direct_ic, strategy_type=strategy_type) or "neutral",
                "weight": _clamp(abs(_safe_float(direct_ic)) * 5.0, 0.25, 0.8),
                "proxy_only": False,
                "summary": f"{name} IC={_safe_float(direct_ic):.4f}",
                "support_metric": {
                    "factor_name": name,
                    "ic_value": round(_safe_float(direct_ic), 6),
                    "trend": _string(params.get("factor_ic_trend") or _as_dict(candidate.get("factor_pool_metadata")).get("trend")) or None,
                },
            }
        )

    for name in selected_names:
        if name not in factor_ic:
            continue
        if any(_as_dict(entry.get("support_metric")).get("factor_name") == name for entry in entries):
            continue
        ic_value = _safe_float(factor_ic.get(name))
        entries.append(
            {
                "evidence_id": f"ev_factor_{len(entries) + 1}",
                "source_type": "factor_ic_validated",
                "direction": _ic_direction(ic_value, strategy_type=strategy_type) or "neutral",
                "weight": _clamp(abs(ic_value) * 5.0, 0.25, 0.8),
                "proxy_only": False,
                "summary": f"{name} IC={ic_value:.4f} trend={factor_trend.get(name, 'flat')}",
                "support_metric": {
                    "factor_name": name,
                    "ic_value": round(ic_value, 6),
                    "trend": factor_trend.get(name, "flat"),
                },
            }
        )

    source = _candidate_source(candidate)
    if not entries and source == "factor_ic":
        trigger = _as_dict(candidate.get("trigger_signal"))
        name = _string(trigger.get("factor"))
        ic_value = trigger.get("value")
        if name and ic_value not in _EMPTY_VALUES:
            entries.append(
                {
                    "evidence_id": "ev_factor_trigger",
                    "source_type": "factor_ic_validated",
                    "direction": _ic_direction(ic_value, strategy_type=strategy_type) or "neutral",
                    "weight": _clamp(abs(_safe_float(ic_value)) * 5.0, 0.25, 0.8),
                    "proxy_only": False,
                    "summary": f"{name} trigger IC={_safe_float(ic_value):.4f}",
                    "support_metric": {
                        "factor_name": name,
                        "ic_value": round(_safe_float(ic_value), 6),
                        "trend": _string(trigger.get("trend")) or None,
                    },
                }
            )
    return entries


def _event_entries(candidate: Mapping[str, Any], prediction_as_of: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    event_anchor = _as_dict(_candidate_value(candidate, "event_anchor"))
    event_prefilter = _as_dict(_candidate_value(candidate, "event_prefilter"))
    if not event_anchor:
        event_anchor = _as_dict(event_prefilter.get("event_anchor"))
    trigger = _as_dict(candidate.get("trigger_signal"))
    event_id = _string(
        _first_non_empty(
            event_anchor.get("id"),
            event_prefilter.get("event_id"),
            trigger.get("event_id"),
        )
    )
    source = _string(event_anchor.get("source") or _candidate_source(candidate)).lower()
    if not event_id:
        return entries
    evidence_time = _first_non_empty(
        event_anchor.get("evidence_time"),
        event_anchor.get("occurred_at"),
        event_prefilter.get("evidence_time"),
        event_prefilter.get("occurred_at"),
        trigger.get("evidence_time"),
    )
    strength = _safe_float(_first_non_empty(event_anchor.get("strength"), event_prefilter.get("anchor_strength"), 0.5), 0.5)
    entries.append(
        {
            "evidence_id": event_id or "ev_event_anchor",
            "source_type": "event_catalyst",
            "direction": _normalize_direction(event_anchor.get("direction") or event_prefilter.get("direction")) or "neutral",
            "weight": _clamp(0.35 + strength * 0.25, 0.35, 0.75),
            "proxy_only": False,
            "summary": _string(event_prefilter.get("evidence_summary")) or f"event catalyst {event_id or source}",
            "support_metric": {
                "event_id": event_id or None,
                "theme_code": _first_non_empty(event_anchor.get("theme_code"), event_prefilter.get("theme_code")),
                "source": source,
                "strength": strength,
            },
            "evidence_time": evidence_time,
            "post_hoc": _evidence_time_is_post_hoc(evidence_time, prediction_as_of),
        }
    )
    return entries


def _fund_flow_entries(candidate: Mapping[str, Any], snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = _candidate_source(candidate)
    trigger = _as_dict(candidate.get("trigger_signal"))
    entries: list[dict[str, Any]] = []
    north_3d = _safe_float(_first_non_empty(trigger.get("value") if trigger.get("field") == "north_fund_3d_net" else None, snapshot.get("north_fund_3d_net")))
    margin_5d = _safe_float(_first_non_empty(trigger.get("value") if trigger.get("field") == "margin_5d_change_pct" else None, snapshot.get("margin_5d_change_pct")))
    if source == "fund_flow" or abs(north_3d) >= 5_000_000_000:
        if abs(north_3d) >= 5_000_000_000:
            direction = "up" if north_3d > 0 else "down"
            entries.append(
                {
                    "evidence_id": "ev_fund_flow_north",
                    "source_type": "fund_flow",
                    "direction": direction,
                    "weight": 0.45,
                    "proxy_only": False,
                    "summary": f"north_fund_3d_net={north_3d:.0f}",
                    "support_metric": {"north_fund_3d_net": north_3d},
                }
            )
    if source == "fund_flow" or abs(margin_5d) >= 2.0:
        if abs(margin_5d) >= 2.0:
            direction = "up" if margin_5d > 0 else "down"
            entries.append(
                {
                    "evidence_id": "ev_fund_flow_margin",
                    "source_type": "fund_flow",
                    "direction": direction,
                    "weight": 0.35,
                    "proxy_only": False,
                    "summary": f"margin_5d_change_pct={margin_5d:.2f}",
                    "support_metric": {"margin_5d_change_pct": margin_5d},
                }
            )
    return entries


def _regime_entries(candidate: Mapping[str, Any], snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = _candidate_source(candidate)
    if source not in {"fear_greed", "volatility", "quota_fill", "signal_variation"}:
        return []
    fear_greed = _safe_float(snapshot.get("fear_greed_index"), 50.0)
    volatility = _safe_float(_as_dict(snapshot.get("fg_components")).get("volatility"), 50.0)
    if fear_greed <= 35:
        direction = "neutral"
    elif fear_greed >= 70:
        direction = "up"
    elif volatility >= 65:
        direction = "neutral"
    else:
        direction = "neutral"
    return [
        {
            "evidence_id": "ev_regime_context",
            "source_type": "regime_context",
            "direction": direction,
            "weight": 0.22,
            "proxy_only": source in {"quota_fill", "signal_variation"},
            "summary": f"fear_greed={fear_greed:.1f}, volatility={volatility:.1f}",
            "support_metric": {"fear_greed_index": fear_greed, "volatility": volatility},
        }
    ]


def _template_entry(candidate: Mapping[str, Any]) -> dict[str, Any]:
    source = _candidate_source(candidate)
    strategy_type = _string(candidate.get("strategy_type")).lower()
    return {
        "evidence_id": "ev_template_fallback",
        "source_type": "template_fallback",
        "direction": "neutral",
        "weight": 0.1,
        "proxy_only": True,
        "summary": f"{strategy_type or 'strategy'} template fallback",
        "support_metric": {
            "source": source,
            "strategy_type": strategy_type,
            "template_entry_bias": _as_dict(_candidate_value(candidate, "trade_plan")).get("entry_bias"),
        },
    }


def build_market_evidence_pack(
    candidate: Mapping[str, Any],
    snapshot: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    payload = dict(candidate or {})
    snapshot_payload = dict(snapshot or {})
    source = _candidate_source(payload)
    strategy_type = _string(payload.get("strategy_type")).lower()
    prediction_as_of = _first_non_empty(
        payload.get("prediction_as_of"),
        _as_dict(payload.get("params")).get("prediction_as_of"),
        snapshot_payload.get("as_of"),
        snapshot_payload.get("as_of_date"),
        snapshot_payload.get("date"),
    )
    entries: list[dict[str, Any]] = []
    evidence_chain = _as_dict(_candidate_value(payload, "evidence_chain"))
    for index, evidence in enumerate(_as_list(evidence_chain.get("evidences")), 1):
        if isinstance(evidence, Mapping):
            entries.append(
                _entry_from_existing_evidence(
                    evidence,
                    candidate_source=source,
                    strategy_type=strategy_type,
                    prediction_as_of=prediction_as_of,
                    index=index,
                )
            )
    entries.extend(_snapshot_factor_entries(payload, snapshot_payload))
    entries.extend(_event_entries(payload, prediction_as_of))
    entries.extend(_fund_flow_entries(payload, snapshot_payload))
    entries.extend(_regime_entries(payload, snapshot_payload))

    if not entries:
        entries.append(_template_entry(payload))

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        key = (_string(entry.get("evidence_id")), _string(entry.get("source_type")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)

    source_counts = Counter(str(entry.get("source_type") or "unknown") for entry in deduped)
    non_proxy_count = sum(1 for entry in deduped if not bool(entry.get("proxy_only")))
    template_count = sum(
        1
        for entry in deduped
        if bool(entry.get("proxy_only")) or str(entry.get("source_type")) in _TEMPLATE_SOURCE_TYPES
    )
    non_proxy_ratio = round(non_proxy_count / max(1, len(deduped)), 4)
    template_dominance_score = round(template_count / max(1, len(deduped)), 4)
    return {
        "contract_version": "strategy_factory.market_evidence_pack.v1",
        "producer": "strategy_factory.evidence_first",
        "strategy_type": strategy_type,
        "candidate_source": source,
        "as_of": _coerce_iso_ts(prediction_as_of),
        "evidences": deduped,
        "evidence_source_counts": dict(source_counts),
        "non_proxy_evidence_ratio": non_proxy_ratio,
        "template_dominance_score": template_dominance_score,
        "factor_backed": any(
            entry.get("source_type") in _FACTOR_SOURCE_TYPES and not bool(entry.get("proxy_only"))
            for entry in deduped
        ),
        "event_backed": any(
            entry.get("source_type") in _EVENT_SOURCE_TYPES and not bool(entry.get("proxy_only"))
            for entry in deduped
        ),
        "post_hoc_rejected": any(bool(entry.get("post_hoc")) for entry in deduped),
        "data_quality_status": _string(snapshot_payload.get("data_quality_status")) or "unknown",
    }


def resolve_direction_and_confidence(
    candidate: Mapping[str, Any],
    market_evidence_pack: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    evidences = [dict(item or {}) for item in _as_list(market_evidence_pack.get("evidences")) if isinstance(item, Mapping)]
    vote_scores = {"up": 0.0, "down": 0.0, "neutral": 0.0}
    support: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for evidence in evidences:
        direction = _normalize_direction(evidence.get("direction")) or "neutral"
        weight = _safe_float(evidence.get("weight"), 0.0)
        if bool(evidence.get("post_hoc")):
            conflicts.append(
                {
                    "evidence_id": evidence.get("evidence_id"),
                    "reason": "post_hoc_rejected",
                    "direction": direction,
                }
            )
            continue
        vote_scores[direction] = vote_scores.get(direction, 0.0) + weight
        support.append(
            {
                "evidence_id": evidence.get("evidence_id"),
                "source_type": evidence.get("source_type"),
                "direction": direction,
                "weight": round(weight, 4),
            }
        )

    total_weight = sum(max(0.0, value) for value in vote_scores.values())
    sorted_votes = sorted(vote_scores.items(), key=lambda item: item[1], reverse=True)
    top_direction, top_score = sorted_votes[0] if sorted_votes else ("neutral", 0.0)
    second_score = sorted_votes[1][1] if len(sorted_votes) > 1 else 0.0
    margin = top_score - second_score
    if total_weight <= 0:
        direction = "neutral"
        direction_source = "no_valid_evidence"
    elif margin < max(0.08, total_weight * 0.12):
        direction = "neutral"
        direction_source = "conflicting_market_evidence"
    else:
        direction = top_direction
        direction_source = "market_evidence_vote"

    for other_direction, score in vote_scores.items():
        if other_direction != direction and score > 0:
            conflicts.append(
                {
                    "direction": other_direction,
                    "weight": round(score, 4),
                    "reason": "opposing_evidence",
                }
            )

    non_proxy_ratio = _safe_float(market_evidence_pack.get("non_proxy_evidence_ratio"))
    template_dominance = _safe_float(market_evidence_pack.get("template_dominance_score"))
    evidence_count = len(evidences)
    non_proxy_count = sum(1 for evidence in evidences if not bool(evidence.get("proxy_only")))
    agreement = margin / total_weight if total_weight > 0 else 0.0
    evidence_strength = _clamp(total_weight / 1.5, 0.0, 1.0)
    evidence_quality_score = _clamp(
        0.18
        + non_proxy_ratio * 0.35
        + agreement * 0.25
        + min(non_proxy_count, 4) * 0.06
        + evidence_strength * 0.16
        - template_dominance * 0.22
        - min(len(conflicts), 4) * 0.04,
        0.0,
        1.0,
    )
    confidence = _clamp(0.35 + evidence_quality_score * 0.5, 0.35, 0.85)
    if direction == "neutral":
        confidence = min(confidence, 0.52)
    if bool(market_evidence_pack.get("post_hoc_rejected")):
        confidence = min(confidence, 0.38)

    if template_dominance >= 0.999 and non_proxy_count <= 0:
        direction = "neutral"
        direction_source = "template_fallback_diagnostic"
        confidence = min(confidence, 0.45)

    direction_resolution = {
        "contract_version": "strategy_factory.direction_resolution.v1",
        "direction": direction,
        "direction_source": direction_source,
        "vote_scores": {key: round(value, 4) for key, value in vote_scores.items()},
        "supporting_evidence": support,
        "conflict_count": len(conflicts),
        "conflicts": conflicts[:8],
        "post_hoc_rejected": bool(market_evidence_pack.get("post_hoc_rejected")),
    }
    confidence_calibration = {
        "contract_version": "strategy_factory.confidence_calibration.v1",
        "confidence": round(confidence, 6),
        "confidence_source": "market_evidence_quality",
        "evidence_quality_score": round(evidence_quality_score, 6),
        "non_proxy_evidence_ratio": round(non_proxy_ratio, 4),
        "template_dominance_score": round(template_dominance, 4),
        "evidence_count": evidence_count,
        "conflict_count": len(conflicts),
        "calibration_inputs": {
            "agreement": round(agreement, 6),
            "evidence_strength": round(evidence_strength, 6),
            "non_proxy_count": non_proxy_count,
        },
    }
    return direction_resolution, confidence_calibration


def _claim_ids_from_prediction_contract(prediction_contract: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    for claim in _as_list(prediction_contract.get("claims")):
        payload = _as_dict(claim)
        claim_id = _string(payload.get("claim_id") or payload.get("id"))
        if claim_id:
            ids.append(claim_id)
    return ids


def _build_evidence_chain_from_pack(
    candidate: Mapping[str, Any],
    market_evidence_pack: Mapping[str, Any],
    direction_resolution: Mapping[str, Any],
    confidence_calibration: Mapping[str, Any],
) -> dict[str, Any]:
    existing = _as_dict(_candidate_value(candidate, "evidence_chain"))
    pack_has_non_template = any(
        not bool(_as_dict(item).get("proxy_only"))
        and _string(_as_dict(item).get("source_type")) not in _TEMPLATE_SOURCE_TYPES
        for item in _as_list(market_evidence_pack.get("evidences"))
        if isinstance(item, Mapping)
    )
    if existing.get("evidences") and not pack_has_non_template:
        return existing
    direction = _string(direction_resolution.get("direction")) or "neutral"
    confidence = _safe_float(confidence_calibration.get("confidence"), 0.45)
    evidences = []
    for index, item in enumerate(_as_list(market_evidence_pack.get("evidences")), 1):
        evidence = _as_dict(item)
        evidences.append(
            {
                "evidence_id": _string(evidence.get("evidence_id")) or f"ev_market_{index}",
                "source_type": _string(evidence.get("source_type")) or "template_fallback",
                "direction": _string(evidence.get("direction")) or direction,
                "summary": _string(evidence.get("summary")) or _string(evidence.get("source_type")) or "market evidence",
                "proxy_only": bool(evidence.get("proxy_only")),
                "raw_confidence": confidence,
                "calibrated_confidence": confidence,
                "claim_ids": ["claim_entry"],
                "support_metric": _as_dict(evidence.get("support_metric")),
                **({"evidence_time": evidence.get("evidence_time")} if evidence.get("evidence_time") else {}),
            }
        )
    return {
        "contract_version": "strategy_factory.semantic_contract.v1",
        "producer": "strategy_factory.evidence_first",
        "generation_mode": "market_evidence_pack",
        "thesis": f"Evidence-first {direction} thesis for {_string(candidate.get('strategy_type')) or 'strategy'}",
        "evidences": evidences,
    }


def _build_prediction_contract_from_pack(
    candidate: Mapping[str, Any],
    market_evidence_pack: Mapping[str, Any],
    direction_resolution: Mapping[str, Any],
    confidence_calibration: Mapping[str, Any],
) -> dict[str, Any]:
    existing = _as_dict(_candidate_value(candidate, "prediction_contract"))
    if existing.get("claims"):
        payload = dict(existing)
        direction = _string(direction_resolution.get("direction")) or _direction_from_expected_move(
            _as_dict(_as_list(payload.get("claims"))[0] if _as_list(payload.get("claims")) else {}).get("expected_move")
        ) or "neutral"
        confidence = _safe_float(confidence_calibration.get("confidence"), 0.45)
        replace_diagnostic = bool(market_evidence_pack.get("factor_backed") or market_evidence_pack.get("event_backed")) and (
            str(payload.get("generation_mode") or "").strip().lower()
            in {"full_market_topn_target_injection", "factory_semantic_contract_backfill"}
            or str(payload.get("direction_source") or "").strip().lower().startswith("target_injection")
            or bool(payload.get("template_fallback_used"))
        )
        if replace_diagnostic:
            evidence_ids = [
                _string(_as_dict(evidence).get("evidence_id"))
                for evidence in _as_list(market_evidence_pack.get("evidences"))
                if _string(_as_dict(evidence).get("evidence_id"))
                and _string(_as_dict(evidence).get("source_type")) not in _TEMPLATE_SOURCE_TYPES
            ]
            payload["direction"] = direction
            payload["confidence"] = confidence
            payload["direction_source"] = direction_resolution.get("direction_source")
            payload["confidence_source"] = confidence_calibration.get("confidence_source")
            payload["evidence_quality_score"] = confidence_calibration.get("evidence_quality_score")
            payload["conflict_count"] = direction_resolution.get("conflict_count")
            payload["template_fallback_used"] = _safe_float(market_evidence_pack.get("template_dominance_score")) > 0
            payload["generation_mode"] = "market_evidence_pack"
            claims = []
            for index, claim in enumerate(_as_list(payload.get("claims"))):
                claim_payload = _as_dict(claim)
                if index == 0 or _string(claim_payload.get("claim_type")).lower() in {"entry", "signal", "thesis"}:
                    claim_payload["expected_move"] = direction
                    claim_payload["confidence"] = confidence
                    claim_payload["calibrated_confidence"] = confidence
                    if evidence_ids:
                        claim_payload["evidence_ids"] = evidence_ids
                claims.append(claim_payload)
            if claims:
                payload["claims"] = claims
        else:
            payload.setdefault("direction", direction)
            payload.setdefault("confidence", confidence)
            payload.setdefault("direction_source", direction_resolution.get("direction_source"))
            payload.setdefault("confidence_source", confidence_calibration.get("confidence_source"))
            payload.setdefault("evidence_quality_score", confidence_calibration.get("evidence_quality_score"))
            payload.setdefault("conflict_count", direction_resolution.get("conflict_count"))
            payload.setdefault("template_fallback_used", _safe_float(market_evidence_pack.get("template_dominance_score")) > 0)
        return payload

    direction = _string(direction_resolution.get("direction")) or "neutral"
    confidence = _safe_float(confidence_calibration.get("confidence"), 0.45)
    evidences = _as_list(market_evidence_pack.get("evidences"))
    evidence_ids = [
        _string(_as_dict(evidence).get("evidence_id"))
        for evidence in evidences
        if _string(_as_dict(evidence).get("evidence_id"))
    ] or ["ev_template_fallback"]
    horizon_days = max(1, _safe_int(_first_non_empty(_as_dict(candidate.get("params")).get("lookback"), 5), 5))
    horizon_days = min(horizon_days, 20)
    return {
        "contract_version": "strategy_factory.prediction_contract.v1",
        "producer": "strategy_factory.evidence_first",
        "generation_mode": "market_evidence_pack",
        "primary_horizon_days": horizon_days,
        "target": "forward_return_positive" if direction == "up" else "forward_return_negative" if direction == "down" else "forward_return_neutral",
        "direction": direction,
        "confidence": confidence,
        "direction_source": direction_resolution.get("direction_source"),
        "confidence_source": confidence_calibration.get("confidence_source"),
        "evidence_quality_score": confidence_calibration.get("evidence_quality_score"),
        "conflict_count": direction_resolution.get("conflict_count"),
        "template_fallback_used": _safe_float(market_evidence_pack.get("template_dominance_score")) > 0,
        "conflict_resolution_rule": {
            "policy": "evidence_vote_with_neutral_on_conflict",
            "tie_breaker": "neutral_when_margin_small",
        },
        "claims": [
            {
                "claim_id": "claim_entry",
                "claim_type": "entry",
                "summary": f"{direction} thesis resolved from market evidence",
                "expected_move": direction,
                "expected_horizon": horizon_days,
                "confidence": confidence,
                "calibrated_confidence": confidence,
                "evidence_ids": evidence_ids,
                "failure_condition": "evidence vote reverses or entry thesis is invalidated",
                "conflict_resolution_rule": {"policy": "evidence_vote_with_neutral_on_conflict"},
            },
            {
                "claim_id": "claim_exit",
                "claim_type": "exit",
                "summary": "Exit when evidence deteriorates, risk stop triggers, or time stop expires.",
                "expected_move": "down" if direction == "up" else "up" if direction == "down" else "neutral",
                "expected_horizon": max(1, horizon_days // 2),
                "evidence_ids": evidence_ids,
                "failure_condition": "entry thesis restored",
                "conflict_resolution_rule": {"policy": "risk_first"},
            },
        ],
    }


def _build_alpha_thesis(
    candidate: Mapping[str, Any],
    market_evidence_pack: Mapping[str, Any],
    direction_resolution: Mapping[str, Any],
    confidence_calibration: Mapping[str, Any],
) -> dict[str, Any]:
    direction = _string(direction_resolution.get("direction")) or "neutral"
    evidences = [
        {
            "evidence_id": _as_dict(item).get("evidence_id"),
            "source_type": _as_dict(item).get("source_type"),
            "direction": _as_dict(item).get("direction"),
            "summary": _as_dict(item).get("summary"),
        }
        for item in _as_list(market_evidence_pack.get("evidences"))[:8]
        if isinstance(item, Mapping)
    ]
    status = "diagnostic_only" if _safe_float(market_evidence_pack.get("template_dominance_score")) >= 0.999 else "research_alpha"
    return {
        "contract_version": "strategy_factory.alpha_thesis.v1",
        "status": status,
        "direction": direction,
        "confidence": confidence_calibration.get("confidence"),
        "long_reason": "positive evidence vote" if direction == "up" else None,
        "short_reason": "negative evidence vote" if direction == "down" else None,
        "neutral_reason": "conflicting or low-quality evidence" if direction == "neutral" else None,
        "conflict_evidence": list(direction_resolution.get("conflicts") or []),
        "entry_window": _as_dict(_candidate_value(candidate, "trade_plan")).get("entry_window"),
        "exit_window": _as_dict(_candidate_value(candidate, "trade_plan")).get("exit_window"),
        "failure_condition": "evidence vote reverses, data quality degrades, or risk stop triggers",
        "evidence_refs": evidences,
        "template_fallback_used": _safe_float(market_evidence_pack.get("template_dominance_score")) > 0,
    }


def apply_evidence_first_candidate(
    candidate: Mapping[str, Any],
    snapshot: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    payload = dict(candidate or {})
    params = _as_dict(payload.get("params"))
    market_evidence_pack = build_market_evidence_pack(payload, snapshot=snapshot)
    direction_resolution, confidence_calibration = resolve_direction_and_confidence(payload, market_evidence_pack)
    alpha_thesis = _build_alpha_thesis(payload, market_evidence_pack, direction_resolution, confidence_calibration)
    evidence_chain = _build_evidence_chain_from_pack(
        payload,
        market_evidence_pack,
        direction_resolution,
        confidence_calibration,
    )
    prediction_contract = _build_prediction_contract_from_pack(
        payload,
        market_evidence_pack,
        direction_resolution,
        confidence_calibration,
    )
    template_dominance = _safe_float(market_evidence_pack.get("template_dominance_score"))
    non_proxy_ratio = _safe_float(market_evidence_pack.get("non_proxy_evidence_ratio"))
    diagnostic_only = bool(payload.get("diagnostic_only")) or bool(params.get("diagnostic_only"))
    evidence_backed = bool(market_evidence_pack.get("factor_backed") or market_evidence_pack.get("event_backed"))
    if evidence_backed:
        diagnostic_only = False
    if template_dominance >= 0.999 and non_proxy_ratio <= 0.0:
        diagnostic_only = True

    fields = {
        "market_evidence_pack": market_evidence_pack,
        "alpha_thesis": alpha_thesis,
        "template_dominance_score": round(template_dominance, 4),
        "non_proxy_evidence_ratio": round(non_proxy_ratio, 4),
        "direction_resolution": direction_resolution,
        "confidence_calibration": confidence_calibration,
        "direction": direction_resolution.get("direction"),
        "confidence": confidence_calibration.get("confidence"),
        "evidence_chain": evidence_chain,
        "prediction_contract": prediction_contract,
        "diagnostic_only": diagnostic_only,
    }
    if evidence_backed:
        # A target-injection run may already carry a frozen P0 trade contract.
        # Real market evidence must refresh that P0 contract downstream instead
        # of letting the old diagnostic neutral contract shadow the new thesis.
        fields.update(
            {
                "trade_prediction_contract": {},
                "trade_prediction_contract_status": None,
                "trade_prediction_contract_hash": None,
                "trade_prediction_contract_missing_fields": [],
                "trade_prediction_contract_reject_reasons": [],
            }
        )
        for field_name in (
            "trade_prediction_contract",
            "trade_prediction_contract_status",
            "trade_prediction_contract_hash",
            "trade_prediction_contract_missing_fields",
            "trade_prediction_contract_reject_reasons",
        ):
            params.pop(field_name, None)
    params = {**params, **fields}
    return {**payload, **fields, "params": params}


def summarize_generation_quality(candidates: list[Mapping[str, Any]] | None) -> dict[str, Any]:
    items = [dict(item or {}) for item in list(candidates or []) if isinstance(item, Mapping)]
    direction_counts: Counter[str] = Counter()
    evidence_source_counts: Counter[str] = Counter()
    confidences: list[float] = []
    template_dominance_count = 0
    factor_backed_candidate_count = 0
    event_backed_candidate_count = 0
    non_proxy_ratios: list[float] = []

    for item in items:
        direction = _string(_as_dict(item.get("direction_resolution")).get("direction") or item.get("direction")) or "unknown"
        direction_counts[direction] += 1
        confidence = _safe_float(_as_dict(item.get("confidence_calibration")).get("confidence"), math.nan)
        if not math.isnan(confidence):
            confidences.append(confidence)
        pack = _as_dict(item.get("market_evidence_pack"))
        evidence_source_counts.update({str(key): int(value) for key, value in _as_dict(pack.get("evidence_source_counts")).items()})
        template_score = _safe_float(item.get("template_dominance_score"))
        if template_score >= 0.5:
            template_dominance_count += 1
        if bool(pack.get("factor_backed")):
            factor_backed_candidate_count += 1
        if bool(pack.get("event_backed")):
            event_backed_candidate_count += 1
        non_proxy_ratios.append(_safe_float(item.get("non_proxy_evidence_ratio")))

    confidence_mean = round(sum(confidences) / len(confidences), 6) if confidences else None
    confidence_std = None
    if confidences:
        confidence_std = round((sum((value - (confidence_mean or 0.0)) ** 2 for value in confidences) / len(confidences)) ** 0.5, 6)
    total = len(items)
    up_ratio = (direction_counts.get("up", 0) / total) if total else 0.0
    flags: list[str] = []
    if total and up_ratio > 0.85:
        flags.append("generation_direction_collapse")
    if total and len([key for key, value in direction_counts.items() if value > 0 and key != "unknown"]) < 2:
        flags.append("generation_direction_low_entropy")
    if confidence_std is not None and confidence_std < 0.015 and total >= 3:
        flags.append("confidence_collapse")
    if total and factor_backed_candidate_count <= 0:
        flags.append("factor_evidence_absent")
    return {
        "direction_counts": dict(direction_counts),
        "confidence_distribution": {
            "count": len(confidences),
            "min": round(min(confidences), 6) if confidences else None,
            "max": round(max(confidences), 6) if confidences else None,
            "mean": confidence_mean,
            "std": confidence_std,
        },
        "evidence_source_counts": dict(evidence_source_counts),
        "template_dominance_count": template_dominance_count,
        "factor_backed_candidate_count": factor_backed_candidate_count,
        "event_backed_candidate_count": event_backed_candidate_count,
        "non_proxy_evidence_ratio_mean": (
            round(sum(non_proxy_ratios) / len(non_proxy_ratios), 6) if non_proxy_ratios else None
        ),
        "generation_quality_flags": flags,
    }


__all__ = [
    "apply_evidence_first_candidate",
    "build_market_evidence_pack",
    "resolve_direction_and_confidence",
    "summarize_generation_quality",
]
