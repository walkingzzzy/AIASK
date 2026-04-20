
from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Mapping, Optional

_EMPTY_VALUES = (None, "", [], {})
_SUPPORTED_DSL_FIELDS = {"open", "high", "low", "close", "volume"}
_SUPPORTED_DSL_INDICATORS = {
    "sma",
    "ema",
    "roc",
    "rsi",
    "stddev",
    "zscore",
    "highest",
    "lowest",
    "volume_ratio",
    "atr",
    "adx",
    "turnover_rate",
    "upper_shadow_ratio",
    "rolling_count",
    "slope",
}
_SUPPORTED_DSL_COMPARE_OPS = {
    "gt",
    "gte",
    "lt",
    "lte",
    "eq",
    "ne",
    "cross_above",
    "cross_below",
}
_SUPPORTED_DSL_BINARY_OPS = {"add", "sub", "mul", "div", "max", "min"}
_CONFIDENCE_CONTRACT_VERSION = "p2-stable/v1"
_TREND_EXECUTABLE_DSL_TYPES = {"ma_cross", "momentum", "volatility_breakout", "event_structure_breakout"}
_AMBIGUOUS_REGIME_TOKENS = {
    "明显震荡",
    "震荡",
    "高波动",
    "低波动",
    "趋势良好",
    "趋势较强",
    "市场不好",
    "市场较差",
    "风险较高",
    "风险较低",
    "high noise",
    "range bound",
    "chop",
    "noisy",
    "volatile",
}


def _string(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in _EMPTY_VALUES:
            return value
    return None


def _dedup_strings(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = _string(value)
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def _string_list(value: Any) -> list[str]:
    return [token for token in (_string(item) for item in _as_list(value)) if token]


def _normalized_source_type(value: Any) -> Optional[str]:
    token = _string(value).lower()
    return token or None


def _normalize_conflict_resolution_rule(value: Any) -> Optional[Any]:
    if isinstance(value, Mapping):
        payload = {
            key: item
            for key, item in dict(value).items()
            if item not in _EMPTY_VALUES
        }
        return payload or None
    token = _string(value)
    return token or None


def _candidate_value(candidate: Optional[Mapping[str, Any]], key: str) -> Any:
    payload = dict(candidate or {})
    params = _as_dict(payload.get("params"))
    if key in payload and payload.get(key) not in _EMPTY_VALUES:
        return payload.get(key)
    if key in params and params.get(key) not in _EMPTY_VALUES:
        return params.get(key)
    return None


def _normalized_strategy_type(candidate: Optional[Mapping[str, Any]]) -> Optional[str]:
    token = _string(_candidate_value(candidate, "strategy_type") or dict(candidate or {}).get("strategy_type")).lower()
    return token or None


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
            if len(digits) >= 8:
                try:
                    dt = datetime(
                        int(digits[:4]),
                        int(digits[4:6]),
                        int(digits[6:8]),
                        tzinfo=timezone.utc,
                    )
                except Exception:
                    return None
            else:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _coerce_signal_ts(value: Any) -> Optional[str]:
    return _coerce_iso_ts(value)


def _quality_band(
    *,
    support_samples: int,
    brier_score: Optional[float],
    ece: Optional[float],
) -> str:
    if support_samples <= 0 and brier_score is None and ece is None:
        return "unknown"
    score = 0
    if support_samples >= 100:
        score += 2
    elif support_samples >= 50:
        score += 1
    if brier_score is not None:
        if brier_score <= 0.10:
            score += 2
        elif brier_score <= 0.20:
            score += 1
    if ece is not None:
        if ece <= 0.04:
            score += 2
        elif ece <= 0.08:
            score += 1
    if score >= 5:
        return "good"
    if score >= 3:
        return "fair"
    if score >= 1:
        return "medium"
    return "unknown"


def _collect_probability_payloads(candidate: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    payload = dict(candidate or {})
    evidence_chain = _as_dict(_candidate_value(payload, "evidence_chain"))
    prediction_contract = _as_dict(_candidate_value(payload, "prediction_contract"))
    confidence_contract = _as_dict(_candidate_value(payload, "confidence_contract"))
    prediction_quality = _as_dict(
        confidence_contract.get("prediction_quality")
        or confidence_contract.get("probability_quality")
    )
    prediction_interval = _as_dict(confidence_contract.get("prediction_interval"))
    claims = _normalize_claims(prediction_contract)
    evidences = _normalize_evidences(evidence_chain)
    raw_probs: list[float] = []
    calibrated_probs: list[float] = []
    support_samples: list[int] = []
    ece = _safe_float(
        _first_non_empty(
            prediction_quality.get("ece"),
            confidence_contract.get("ece"),
        )
    )
    brier_score = _safe_float(
        _first_non_empty(
            prediction_quality.get("brier_score"),
            confidence_contract.get("brier_score"),
        )
    )
    calibration_gap = _safe_float(
        _first_non_empty(
            prediction_quality.get("calibration_gap"),
            confidence_contract.get("calibration_gap"),
        )
    )

    def _append_probability(
        raw_value: Any,
        calibrated_value: Any,
        sample_size_value: Any,
    ) -> None:
        raw = _safe_float(raw_value)
        calibrated = _safe_float(calibrated_value)
        sample_size = _safe_int(sample_size_value)
        if raw is not None:
            raw_probs.append(raw)
        if calibrated is not None:
            calibrated_probs.append(calibrated)
        if sample_size > 0:
            support_samples.append(sample_size)

    _append_probability(
        _first_non_empty(
            prediction_quality.get("raw_probability"),
            confidence_contract.get("raw_probability"),
            confidence_contract.get("probability"),
        ),
        _first_non_empty(
            prediction_quality.get("calibrated_probability"),
            confidence_contract.get("calibrated_probability"),
        ),
        _first_non_empty(
            prediction_quality.get("support_samples"),
            prediction_quality.get("sample_size"),
            confidence_contract.get("support_samples"),
            confidence_contract.get("sample_size"),
        ),
    )

    for claim in claims:
        _append_probability(
            _first_non_empty(
                claim.get("raw_probability"),
                claim.get("probability"),
                claim.get("confidence"),
                claim.get("expected_probability"),
            ),
            _first_non_empty(
                claim.get("calibrated_probability"),
                claim.get("calibrated_confidence"),
            ),
            _first_non_empty(
                claim.get("support_samples"),
                claim.get("sample_size"),
            ),
        )

    for evidence in evidences:
        _append_probability(
            _first_non_empty(
                evidence.get("raw_confidence"),
                evidence.get("raw_probability"),
                evidence.get("confidence"),
            ),
            _first_non_empty(
                evidence.get("calibrated_confidence"),
                evidence.get("calibrated_probability"),
            ),
            _first_non_empty(
                evidence.get("support_samples"),
                evidence.get("sample_size"),
            ),
        )

    return {
        "existing_contract": confidence_contract,
        "prediction_quality": prediction_quality,
        "prediction_interval": prediction_interval,
        "claims": claims,
        "evidences": evidences,
        "raw_probs": raw_probs,
        "calibrated_probs": calibrated_probs,
        "support_samples": support_samples,
        "ece": ece,
        "brier_score": brier_score,
        "calibration_gap": calibration_gap,
    }
