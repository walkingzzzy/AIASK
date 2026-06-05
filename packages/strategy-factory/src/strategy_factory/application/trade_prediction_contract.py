"""Trade prediction contract helpers.

The existing semantic ``prediction_contract`` explains claims and evidence.
This module adds a sibling contract focused on one frozen, machine-verifiable
trade prediction. P0 intentionally stops at normalization, validation, and
stable hashing; outcome scoring belongs to later phases.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timezone
from typing import Any, Mapping, Optional

TRADE_PREDICTION_CONTRACT_VERSION = "strategy_factory.trade_prediction_contract.v1"
TRADE_PREDICTION_CONTRACT_READY = "ready"
TRADE_PREDICTION_CONTRACT_REJECTED = "rejected"
DERIVED_FROM_LEGACY_CONTRACT = "derived_from_legacy_contract"
EXPLICIT_CONTRACT = "explicit"

_EMPTY_VALUES = (None, "", [], {})
_DIRECTION_ALIASES = {
    "up": "up",
    "bullish": "up",
    "long": "up",
    "buy": "up",
    "rise": "up",
    "rising": "up",
    "上涨": "up",
    "看多": "up",
    "down": "down",
    "bearish": "down",
    "short": "down",
    "sell": "down",
    "fall": "down",
    "falling": "down",
    "下跌": "down",
    "看空": "down",
    "neutral": "neutral",
    "flat": "neutral",
    "sideways": "neutral",
    "hold": "neutral",
    "震荡": "neutral",
    "中性": "neutral",
}
_REQUIRED_FIELDS = (
    "strategy_id",
    "stock_code",
    "prediction_as_of",
    "target_trading_date",
    "direction",
    "confidence",
    "horizon",
    "evidence_refs",
    "contract_version",
    "contract_source",
)


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


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in _EMPTY_VALUES:
            return value
    return None


def _candidate_value(candidate: Mapping[str, Any], key: str) -> Any:
    params = _as_dict(candidate.get("params"))
    if candidate.get(key) not in _EMPTY_VALUES:
        return candidate.get(key)
    if params.get(key) not in _EMPTY_VALUES:
        return params.get(key)
    return None


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
        normalized = text.replace("Z", "+00:00")
        parsers = (
            lambda item: datetime.fromisoformat(item),
            lambda item: datetime.combine(date.fromisoformat(item[:10]), time.min),
        )
        dt = None
        for parser in parsers:
            try:
                dt = parser(normalized)
                break
            except Exception:
                continue
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


def _coerce_iso_date(value: Any) -> Optional[str]:
    if value in _EMPTY_VALUES:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _string(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except Exception:
        pass
    ts = _coerce_iso_ts(text)
    return ts[:10] if ts else None


def _coerce_stock_code(value: Any) -> Optional[str]:
    token = _string(value).upper()
    if not token:
        return None
    if "." in token:
        return token
    digits = "".join(ch for ch in token if ch.isdigit())
    if len(digits) == 6:
        suffix = "SH" if digits.startswith(("5", "6", "9")) else "SZ"
        return f"{digits}.{suffix}"
    return token


def _first_stock_code(candidate: Mapping[str, Any], contract: Mapping[str, Any]) -> Optional[str]:
    direct = _first_non_empty(
        contract.get("stock_code"),
        contract.get("code"),
        contract.get("symbol"),
        _candidate_value(candidate, "stock_code"),
        _candidate_value(candidate, "code"),
        _candidate_value(candidate, "symbol"),
    )
    if direct not in _EMPTY_VALUES:
        return _coerce_stock_code(direct)
    for key in ("target_symbols", "symbols", "codes", "stock_codes"):
        values = _as_list(_candidate_value(candidate, key))
        if values:
            return _coerce_stock_code(values[0])
    stock_pool = _as_dict(_candidate_value(candidate, "stock_pool"))
    for key in ("symbols", "target_symbols", "codes", "stock_codes"):
        values = _as_list(stock_pool.get(key))
        if values:
            return _coerce_stock_code(values[0])
    return None


def _normalize_direction(value: Any) -> Optional[str]:
    token = _string(value).lower()
    if not token:
        return None
    return _DIRECTION_ALIASES.get(token)


def _coerce_confidence(value: Any) -> Optional[float]:
    try:
        if value in _EMPTY_VALUES:
            return None
        resolved = float(value)
    except Exception:
        return None
    if resolved < 0.0 or resolved > 1.0:
        return None
    return round(resolved, 6)


def _normalize_evidence_refs(value: Any) -> list[Any]:
    refs: list[Any] = []
    seen: set[str] = set()
    for item in _as_list(value):
        ref: Any
        if isinstance(item, Mapping):
            payload = {str(key): val for key, val in dict(item).items() if val not in _EMPTY_VALUES}
            ref_id = _first_non_empty(payload.get("id"), payload.get("evidence_id"), payload.get("event_id"))
            if ref_id not in _EMPTY_VALUES:
                payload.setdefault("id", _string(ref_id))
            ref = payload
        else:
            token = _string(item)
            if not token:
                continue
            ref = token
        marker = json.dumps(ref, ensure_ascii=False, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        refs.append(ref)
    return refs


def _derive_evidence_refs(candidate: Mapping[str, Any]) -> list[Any]:
    refs: list[Any] = []
    prediction_contract = _as_dict(_candidate_value(candidate, "prediction_contract"))
    for claim in _as_list(prediction_contract.get("claims")):
        claim_payload = _as_dict(claim)
        for key in ("evidence_refs", "evidence_ids", "evidences"):
            refs.extend(_as_list(claim_payload.get(key)))
    evidence_chain = _as_dict(_candidate_value(candidate, "evidence_chain"))
    for evidence in _as_list(evidence_chain.get("evidences") or evidence_chain.get("evidence")):
        evidence_payload = _as_dict(evidence)
        refs.append(
            _first_non_empty(
                evidence_payload.get("id"),
                evidence_payload.get("evidence_id"),
                evidence_payload.get("source"),
            )
            or evidence
        )
    return _normalize_evidence_refs(refs)


def _extract_explicit_contract(candidate: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    payload = dict(candidate or {})
    params = _as_dict(payload.get("params"))
    for value in (payload.get("trade_prediction_contract"), params.get("trade_prediction_contract")):
        if isinstance(value, Mapping) and value:
            return dict(value)
    contract_markers = {
        "stock_code",
        "target_trading_date",
        "direction",
        "confidence",
        "prediction_as_of",
        "horizon",
    }
    if contract_markers.intersection(payload):
        return dict(payload)
    return None


def derive_trade_prediction_contract(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Build a minimum contract from legacy semantic fields."""

    payload = dict(candidate or {})
    params = _as_dict(payload.get("params"))
    confidence_contract = _as_dict(_candidate_value(payload, "confidence_contract"))
    holding_horizon = _as_dict(_candidate_value(payload, "holding_horizon"))
    trade_plan = _as_dict(_candidate_value(payload, "trade_plan"))
    prediction_contract = _as_dict(_candidate_value(payload, "prediction_contract"))
    claims = _as_list(prediction_contract.get("claims"))
    first_claim = _as_dict(claims[0]) if claims else {}
    return {
        "contract_version": TRADE_PREDICTION_CONTRACT_VERSION,
        "contract_source": DERIVED_FROM_LEGACY_CONTRACT,
        "strategy_id": _string(
            _first_non_empty(
                payload.get("strategy_id"),
                payload.get("id"),
                params.get("strategy_id"),
                params.get("id"),
            )
        )
        or None,
        "stock_code": _first_stock_code(payload, {}),
        "prediction_as_of": _coerce_iso_ts(
            _first_non_empty(
                payload.get("prediction_as_of"),
                params.get("prediction_as_of"),
                payload.get("as_of"),
                payload.get("as_of_date"),
                params.get("as_of"),
                params.get("as_of_date"),
                payload.get("snapshot_date"),
                params.get("snapshot_date"),
                payload.get("created_at"),
                params.get("created_at"),
            )
        ),
        "target_trading_date": _coerce_iso_date(
            _first_non_empty(
                payload.get("target_trading_date"),
                params.get("target_trading_date"),
                first_claim.get("target_trading_date"),
                first_claim.get("target_date"),
                trade_plan.get("target_trading_date"),
            )
        ),
        "direction": _normalize_direction(
            _first_non_empty(
                payload.get("direction"),
                params.get("direction"),
                first_claim.get("direction"),
                first_claim.get("expected_direction"),
                trade_plan.get("direction"),
                trade_plan.get("entry_bias"),
            )
        ),
        "confidence": _coerce_confidence(
            _first_non_empty(
                payload.get("confidence"),
                params.get("confidence"),
                first_claim.get("confidence"),
                confidence_contract.get("calibrated_probability"),
                confidence_contract.get("probability"),
            )
        ),
        "horizon": _string(
            _first_non_empty(
                payload.get("horizon"),
                params.get("horizon"),
                first_claim.get("horizon"),
                holding_horizon.get("horizon"),
                holding_horizon.get("label"),
                trade_plan.get("holding_horizon"),
            )
        )
        or None,
        "evidence_refs": _derive_evidence_refs(payload),
    }


def normalize_trade_prediction_contract(candidate_or_contract: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize an explicit contract or derive one from a strategy candidate."""

    payload = dict(candidate_or_contract or {})
    explicit = _extract_explicit_contract(payload)
    source = EXPLICIT_CONTRACT if explicit is not None else DERIVED_FROM_LEGACY_CONTRACT
    candidate = payload if explicit is not payload else {}
    raw = explicit if explicit is not None else derive_trade_prediction_contract(payload)
    contract = dict(raw or {})
    contract["contract_version"] = _string(contract.get("contract_version")) or TRADE_PREDICTION_CONTRACT_VERSION
    contract["contract_source"] = _string(contract.get("contract_source")) or source
    contract["strategy_id"] = _string(
        _first_non_empty(
            contract.get("strategy_id"),
            _candidate_value(candidate, "strategy_id"),
            _candidate_value(candidate, "id"),
        )
    ) or None
    contract["stock_code"] = _first_stock_code(candidate, contract)
    contract["prediction_as_of"] = _coerce_iso_ts(contract.get("prediction_as_of"))
    contract["target_trading_date"] = _coerce_iso_date(contract.get("target_trading_date"))
    contract["direction"] = _normalize_direction(contract.get("direction"))
    contract["confidence"] = _coerce_confidence(contract.get("confidence"))
    contract["horizon"] = _string(contract.get("horizon")) or None
    contract["evidence_refs"] = _normalize_evidence_refs(
        contract.get("evidence_refs") or contract.get("evidence_ids")
    )
    for optional_key in (
        "target_price_range",
        "time_buckets",
        "entry_window",
        "exit_window",
        "risk_plan",
        "metadata",
    ):
        if optional_key in contract and isinstance(contract.get(optional_key), Mapping):
            contract[optional_key] = {
                str(key): value
                for key, value in dict(contract.get(optional_key) or {}).items()
                if value not in _EMPTY_VALUES
            }
    return {key: value for key, value in contract.items() if value not in (None, "")}


def validate_trade_prediction_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_trade_prediction_contract(contract)
    missing_fields = [
        field_name
        for field_name in _REQUIRED_FIELDS
        if normalized.get(field_name) in _EMPTY_VALUES
    ]
    reject_reasons = [f"missing:{field_name}" for field_name in missing_fields]
    if normalized.get("contract_version") != TRADE_PREDICTION_CONTRACT_VERSION:
        reject_reasons.append("invalid:contract_version")
    if normalized.get("direction") not in {"up", "down", "neutral"}:
        reject_reasons.append("invalid:direction")
    if normalized.get("confidence") is None:
        reject_reasons.append("invalid:confidence")
    status = TRADE_PREDICTION_CONTRACT_READY if not reject_reasons else TRADE_PREDICTION_CONTRACT_REJECTED
    return {
        "status": status,
        "contract": normalized,
        "missing_fields": sorted(set(missing_fields)),
        "reject_reasons": list(dict.fromkeys(reject_reasons)),
    }


def stable_trade_prediction_contract_hash(contract: Mapping[str, Any]) -> str:
    frozen = dict(contract or {})
    frozen.pop("contract_hash", None)
    frozen.pop("prediction_id", None)
    serialized = json.dumps(
        frozen,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def freeze_trade_prediction_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    validation = validate_trade_prediction_contract(contract)
    normalized = dict(validation.get("contract") or {})
    contract_hash = (
        stable_trade_prediction_contract_hash(normalized)
        if validation.get("status") == TRADE_PREDICTION_CONTRACT_READY
        else None
    )
    if contract_hash:
        normalized["contract_hash"] = contract_hash
    return {
        **validation,
        "contract": normalized,
        "contract_hash": contract_hash,
    }


def apply_trade_prediction_contract(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Return candidate with P0 trade prediction diagnostics attached."""

    payload = dict(candidate or {})
    frozen = freeze_trade_prediction_contract(payload)
    contract = dict(frozen.get("contract") or {})
    params = {
        **_as_dict(payload.get("params")),
        "trade_prediction_contract": contract,
        "trade_prediction_contract_status": frozen.get("status"),
        "trade_prediction_contract_hash": frozen.get("contract_hash"),
        "trade_prediction_contract_missing_fields": list(frozen.get("missing_fields") or []),
        "trade_prediction_contract_reject_reasons": list(frozen.get("reject_reasons") or []),
    }
    return {
        **payload,
        "params": params,
        "trade_prediction_contract": contract,
        "trade_prediction_contract_status": frozen.get("status"),
        "trade_prediction_contract_hash": frozen.get("contract_hash"),
        "trade_prediction_contract_missing_fields": list(frozen.get("missing_fields") or []),
        "trade_prediction_contract_reject_reasons": list(frozen.get("reject_reasons") or []),
    }


__all__ = [
    "DERIVED_FROM_LEGACY_CONTRACT",
    "EXPLICIT_CONTRACT",
    "TRADE_PREDICTION_CONTRACT_READY",
    "TRADE_PREDICTION_CONTRACT_REJECTED",
    "TRADE_PREDICTION_CONTRACT_VERSION",
    "apply_trade_prediction_contract",
    "derive_trade_prediction_contract",
    "freeze_trade_prediction_contract",
    "normalize_trade_prediction_contract",
    "stable_trade_prediction_contract_hash",
    "validate_trade_prediction_contract",
]
