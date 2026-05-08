"""Candidate parameter materialization and structural identity helpers."""

from __future__ import annotations

import hashlib
import json
import random
from copy import deepcopy
from typing import Any, Mapping, Optional


PARAM_MATERIALIZATION_VERSION = "strategy_factory.param_materialization.v1"

_DEFAULT_TARGET_SYMBOLS = [
    "600519", "000858", "601318", "600036", "000333",
    "002415", "600276", "601012", "300750", "000001",
]

_IDENTITY_META_KEYS = {
    "candidate_contract_hash",
    "candidate_contract_snapshot",
    "candidate_identity_signature",
    "candidate_lineage_contract",
    "dsl_signature",
    "entry_exit_signature",
    "execution_contract_hash",
    "factor_signature",
    "logic_signature",
    "param_fingerprint",
    "target_fingerprint",
    "logic_fingerprint",
    "strategy_instance_hash",
    "tested_object_hash",
    "resolved_candidate_envelope",
}

_CORE_FIELDS: dict[str, tuple[str, ...]] = {
    "momentum": ("lookback", "threshold", "signal_rule"),
    "ma_cross": ("short_period", "long_period", "signal_rule"),
    "rsi": ("rsi_period", "oversold", "overbought", "signal_rule"),
    "value_factor": ("lookback", "buy_quantile", "sell_quantile", "signal_rule"),
    "quality_factor": ("lookback", "buy_quantile", "sell_quantile", "signal_rule"),
    "growth_factor": ("lookback", "buy_quantile", "sell_quantile", "signal_rule"),
    "multi_factor": ("lookback", "factor_weights", "signal_rule"),
    "macro_timing": ("lookback", "fear_threshold", "greed_threshold", "signal_rule"),
    "volatility_breakout": ("lookback", "threshold", "confirmation_window", "signal_rule"),
    "event_structure_breakout": ("lookback", "threshold", "confirmation_window", "signal_rule"),
    "gap_fill": ("gap_threshold", "confirmation_window", "signal_rule"),
    "mean_reversion_short": ("rsi_period", "oversold", "overbought", "signal_rule"),
    "sector_rotation": ("lookback", "factor_weights", "signal_rule"),
    "north_capital_track": ("lookback", "threshold", "signal_rule"),
    "margin_divergence": ("lookback", "rebound_window", "signal_rule"),
    "topn_equity_portfolio": ("target_symbols", "target_weights", "rebalance_rule", "selection_logic", "signal_rule"),
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _hash_payload(payload: Any) -> str:
    serialized = json.dumps(_json_safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


def _normalize_codes(values: Any, *, limit: int = 20) -> list[str]:
    items: list[str] = []
    queue = [values]
    while queue:
        value = queue.pop(0)
        if isinstance(value, Mapping):
            for key in ("symbols", "target_symbols", "codes", "constituents"):
                if key in value:
                    queue.append(value.get(key))
            if "code" in value:
                queue.append(value.get("code"))
            continue
        if isinstance(value, (list, tuple, set)):
            queue[:0] = list(value)
            continue
        token = str(value or "").strip()
        if token and token not in items:
            items.append(token)
    return items[: max(1, int(limit or 20))]


def _stable_rng(strategy_type: str, seed_context: Optional[Mapping[str, Any]], slot_index: int, targets: list[str]) -> random.Random:
    seed_payload = {
        "strategy_type": str(strategy_type or "").strip().lower(),
        "seed_context": dict(seed_context or {}),
        "slot_index": int(slot_index or 0),
        "targets": list(targets or []),
        "version": PARAM_MATERIALIZATION_VERSION,
    }
    return random.Random(int(_hash_payload(seed_payload)[:16], 16))


def _jitter_int(rng: random.Random, base: int, lo: int, hi: int, spread: float = 0.25) -> int:
    delta = max(1, int(abs(base) * spread))
    return max(lo, min(hi, int(base) + rng.randint(-delta, delta)))


def _jitter_float(rng: random.Random, base: float, lo: float, hi: float, spread: float = 0.25, digits: int = 4) -> float:
    delta = max(0.0001, abs(float(base)) * spread)
    return round(max(lo, min(hi, float(base) + rng.uniform(-delta, delta))), digits)


def _default_params(strategy_type: str, rng: random.Random, targets: list[str], *, slot_index: int = 0) -> dict[str, Any]:
    st = str(strategy_type or "").strip().lower()
    if st == "momentum":
        lookback = _jitter_int(rng, 20, 5, 60)
        threshold = _jitter_float(rng, 0.02, 0.006, 0.06)
        return {"lookback": lookback, "lookback_days": lookback, "threshold": threshold, "threshold_pct": threshold}
    if st == "ma_cross":
        short = _jitter_int(rng, 8, 3, 20)
        long = max(short + 5, _jitter_int(rng, 34, 18, 120))
        return {"short_period": short, "long_period": long}
    if st == "rsi":
        return {"rsi_period": _jitter_int(rng, 12, 4, 28), "oversold": _jitter_int(rng, 24, 16, 34), "overbought": _jitter_int(rng, 70, 56, 84)}
    if st in {"value_factor", "quality_factor", "growth_factor"}:
        base = {"value_factor": 72, "quality_factor": 80, "growth_factor": 48}.get(st, 60)
        return {"lookback": _jitter_int(rng, base, 25, 120), "buy_quantile": _jitter_float(rng, 0.82, 0.70, 0.92), "sell_quantile": _jitter_float(rng, 0.18, 0.08, 0.30)}
    if st == "multi_factor":
        raw = {"value": rng.uniform(0.2, 0.5), "quality": rng.uniform(0.2, 0.5), "momentum": rng.uniform(0.1, 0.4)}
        total = sum(raw.values()) or 1.0
        return {"lookback": _jitter_int(rng, 60, 25, 120), "factor_weights": {k: round(v / total, 4) for k, v in raw.items()}}
    if st == "macro_timing":
        return {"lookback": _jitter_int(rng, 28, 10, 60), "fear_threshold": _jitter_int(rng, 32, 20, 45), "greed_threshold": _jitter_int(rng, 70, 55, 85)}
    if st == "volatility_breakout":
        return {"lookback": _jitter_int(rng, 20, 5, 50), "threshold": _jitter_float(rng, 0.025, 0.008, 0.07), "confirmation_window": _jitter_int(rng, 4, 2, 10)}
    if st == "event_structure_breakout":
        return {"lookback": _jitter_int(rng, 14, 5, 40), "threshold": _jitter_float(rng, 0.02, 0.008, 0.06), "confirmation_window": _jitter_int(rng, 4, 2, 8)}
    if st == "gap_fill":
        return {"gap_threshold": _jitter_float(rng, 0.02, 0.008, 0.06), "confirmation_window": _jitter_int(rng, 3, 1, 8), "rsi_period": _jitter_int(rng, 5, 3, 14), "oversold": _jitter_int(rng, 24, 16, 34), "overbought": _jitter_int(rng, 60, 52, 76)}
    if st == "mean_reversion_short":
        return {"rsi_period": _jitter_int(rng, 8, 4, 16), "oversold": _jitter_int(rng, 22, 16, 30), "overbought": _jitter_int(rng, 72, 62, 84)}
    if st == "sector_rotation":
        raw = {"momentum": rng.uniform(0.25, 0.55), "quality": rng.uniform(0.15, 0.4), "value": rng.uniform(0.1, 0.35)}
        total = sum(raw.values()) or 1.0
        return {"lookback": _jitter_int(rng, 24, 10, 60), "factor_weights": {k: round(v / total, 4) for k, v in raw.items()}}
    if st == "north_capital_track":
        return {"lookback": _jitter_int(rng, 15, 5, 40), "threshold": _jitter_float(rng, 0.015, 0.004, 0.04)}
    if st == "margin_divergence":
        return {"lookback": _jitter_int(rng, 12, 6, 30), "rebound_window": _jitter_int(rng, 3, 2, 8), "repair_rebound_pct": _jitter_float(rng, 0.012, 0.004, 0.04)}
    if st == "topn_equity_portfolio":
        resolved = list(targets or _DEFAULT_TARGET_SYMBOLS)[:20]
        weights = {code: round(1.0 / len(resolved), 8) for code in resolved} if resolved else {}
        variants = [
            ("full_market_topn_score", 20),
            ("risk_adjusted_topn_score", 15),
            ("quality_balanced_topn_score", 30),
        ]
        selection_logic, frequency_days = variants[int(slot_index or 0) % len(variants)]
        return {
            "target_symbols": resolved,
            "target_weights": weights,
            "rebalance_rule": {"mode": "periodic", "frequency_days": frequency_days},
            "selection_logic": [selection_logic],
        }
    return {}


def _apply_generated_variant(strategy_type: str, params: dict[str, Any], rng: random.Random, slot_index: int) -> dict[str, Any]:
    """Create deterministic slot-level variants for factory-generated templates.

    Existing template params often arrive already populated. Without a tiny,
    reproducible slot variation, multiple candidates from different generator
    branches collapse to the same structural hash and are dropped before they
    can be evaluated.
    """
    resolved = dict(params or {})
    st = str(strategy_type or "").strip().lower()
    slot = max(0, int(slot_index or 0))
    if st == "momentum":
        if "lookback" in resolved or "lookback_days" in resolved:
            lookback = int(resolved.get("lookback", resolved.get("lookback_days", 20)) or 20)
            resolved["lookback"] = resolved["lookback_days"] = _jitter_int(rng, lookback + slot * 2, 5, 80, spread=0.18)
        if "threshold" in resolved or "threshold_pct" in resolved:
            threshold = float(resolved.get("threshold", resolved.get("threshold_pct", 0.02)) or 0.02)
            resolved["threshold"] = resolved["threshold_pct"] = _jitter_float(rng, threshold * (1.0 + slot * 0.08), 0.006, 0.08, spread=0.18)
    elif st == "ma_cross":
        if "short_period" in resolved:
            short = _jitter_int(rng, int(resolved.get("short_period") or 8) + slot, 3, 30, spread=0.18)
            long = _jitter_int(rng, int(resolved.get("long_period") or 34) + slot * 3, short + 5, 160, spread=0.18)
            resolved["short_period"] = short
            resolved["long_period"] = long
    elif st in {"rsi", "gap_fill", "mean_reversion_short"}:
        period_key = "rsi_period"
        if period_key in resolved:
            floor = 4 if st == "mean_reversion_short" else 3
            resolved[period_key] = _jitter_int(rng, int(resolved.get(period_key) or 8) + slot, floor, 28, spread=0.16)
        if "oversold" in resolved:
            resolved["oversold"] = _jitter_int(rng, int(resolved.get("oversold") or 24) - min(slot, 4), 14, 36, spread=0.12)
        if "overbought" in resolved:
            resolved["overbought"] = _jitter_int(rng, int(resolved.get("overbought") or 70) + min(slot, 5), 52, 88, spread=0.12)
    elif st in {"value_factor", "quality_factor", "growth_factor", "multi_factor", "sector_rotation"}:
        if "lookback" in resolved:
            resolved["lookback"] = _jitter_int(rng, int(resolved.get("lookback") or 60) + slot * 4, 20, 160, spread=0.16)
        if isinstance(resolved.get("factor_weights"), Mapping):
            raw = {str(k): max(0.0, float(v or 0.0) * rng.uniform(0.88, 1.12)) for k, v in dict(resolved.get("factor_weights") or {}).items()}
            total = sum(raw.values()) or 1.0
            resolved["factor_weights"] = {k: round(v / total, 4) for k, v in raw.items()}
    elif st in {"volatility_breakout", "north_capital_track"}:
        if "lookback" in resolved:
            resolved["lookback"] = _jitter_int(rng, int(resolved.get("lookback") or 20) + slot * 2, 5, 80, spread=0.18)
        if "threshold" in resolved:
            resolved["threshold"] = _jitter_float(rng, float(resolved.get("threshold") or 0.02) * (1.0 + slot * 0.07), 0.004, 0.09, spread=0.18)
    elif st == "event_structure_breakout":
        for key, lo, hi in (("lookback", 5, 60), ("breakout_window", 8, 60), ("confirmation_window", 2, 12), ("max_hold_bars", 4, 20)):
            if key in resolved:
                resolved[key] = _jitter_int(rng, int(resolved.get(key) or lo) + slot, lo, hi, spread=0.16)
        for key, lo, hi in (("threshold", 0.004, 0.08), ("breakout_buffer_pct", 0.001, 0.02), ("breakout_volume_ratio_min", 0.8, 2.5)):
            if key in resolved:
                resolved[key] = _jitter_float(rng, float(resolved.get(key) or lo) * (1.0 + slot * 0.05), lo, hi, spread=0.16)
    elif st == "macro_timing":
        if "lookback" in resolved:
            resolved["lookback"] = _jitter_int(rng, int(resolved.get("lookback") or 28) + slot * 2, 10, 90, spread=0.14)
        if "fear_threshold" in resolved:
            resolved["fear_threshold"] = _jitter_int(rng, int(resolved.get("fear_threshold") or 32) - min(slot, 5), 15, 55, spread=0.12)
        if "greed_threshold" in resolved:
            resolved["greed_threshold"] = _jitter_int(rng, int(resolved.get("greed_threshold") or 70) + min(slot, 5), 50, 90, spread=0.12)
    elif st == "margin_divergence":
        if "lookback" in resolved:
            resolved["lookback"] = _jitter_int(rng, int(resolved.get("lookback") or 12) + slot * 2, 6, 45, spread=0.16)
        if "rebound_window" in resolved:
            resolved["rebound_window"] = _jitter_int(rng, int(resolved.get("rebound_window") or 3) + slot, 2, 10, spread=0.16)
        if "repair_rebound_pct" in resolved:
            resolved["repair_rebound_pct"] = _jitter_float(rng, float(resolved.get("repair_rebound_pct") or 0.012) * (1.0 + slot * 0.08), 0.004, 0.06, spread=0.18)
    return resolved


def _default_signal_rule(strategy_type: str, params: Mapping[str, Any]) -> str:
    st = str(strategy_type or "").strip().lower()
    if st == "momentum":
        return f"close/close_lag_{params.get('lookback', params.get('lookback_days', 20))}-1 > {params.get('threshold', params.get('threshold_pct', 0.02))}"
    if st == "ma_cross":
        return f"ma_{params.get('short_period', 8)} crosses above ma_{params.get('long_period', 34)}"
    if st == "rsi":
        return f"rsi_{params.get('rsi_period', 12)} < {params.get('oversold', 24)} then exit > {params.get('overbought', 70)}"
    if st in {"value_factor", "quality_factor", "growth_factor", "multi_factor", "sector_rotation"}:
        return f"rank_top_quantile over lookback_{params.get('lookback', 60)}"
    if st in {"volatility_breakout", "event_structure_breakout"}:
        return f"breakout_{params.get('lookback', 20)} > {params.get('threshold', 0.02)} with confirmation_{params.get('confirmation_window', 4)}"
    if st == "gap_fill":
        return f"gap_down > {params.get('gap_threshold', 0.02)} and repair_confirmation_{params.get('confirmation_window', 3)}"
    if st == "mean_reversion_short":
        return f"short_reversion rsi_{params.get('rsi_period', 6)} < {params.get('oversold', 24)}"
    if st == "macro_timing":
        return f"fear_greed < {params.get('fear_threshold', 32)} or > {params.get('greed_threshold', 70)} over {params.get('lookback', 28)}"
    if st == "north_capital_track":
        return f"north_flow_{params.get('lookback', 15)} confirmation > {params.get('threshold', 0.015)}"
    if st == "margin_divergence":
        return f"margin_divergence_repair_{params.get('lookback', 12)} rebound_{params.get('rebound_window', 3)}"
    if st == "topn_equity_portfolio":
        selection_logic = params.get("selection_logic") or ["full_market_topn_score"]
        if isinstance(selection_logic, (list, tuple)) and selection_logic:
            selection_name = str(selection_logic[0] or "full_market_topn_score").strip() or "full_market_topn_score"
        else:
            selection_name = str(selection_logic or "full_market_topn_score").strip() or "full_market_topn_score"
        return f"rebalance to {selection_name} target_weights"
    return st or "custom_rule"


def executable_param_payload(strategy_type: str, params: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    source = dict(params or {})
    clean = {k: deepcopy(v) for k, v in source.items() if k not in _IDENTITY_META_KEYS and v not in (None, "", [], {})}
    return clean


def target_payload(candidate: Optional[Mapping[str, Any]], params: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    payload = dict(candidate or {})
    p = dict(params or payload.get("params") or {})
    symbols = _normalize_codes(
        payload.get("target_symbols")
        or payload.get("requested_target_symbols")
        or p.get("target_symbols")
        or p.get("requested_target_symbols")
        or payload.get("stock_pool")
        or p.get("stock_pool"),
        limit=20,
    )
    weights = dict(p.get("target_weights") or payload.get("target_weights") or {})
    return {"target_symbols": symbols, "target_weights": {str(k): weights[k] for k in sorted(weights)}}


def structural_identity(candidate: Optional[Mapping[str, Any]]) -> dict[str, str]:
    payload = dict(candidate or {})
    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    params = executable_param_payload(strategy_type, dict(payload.get("params") or {}))
    targets = target_payload(payload, params)
    logic_payload = {
        "signal_rule": params.get("signal_rule"),
        "factor_weights": params.get("factor_weights"),
        "entry_exit_signature": params.get("entry_exit_signature") or payload.get("entry_exit_signature"),
        "selection_logic": params.get("selection_logic") or payload.get("selection_logic"),
    }
    param_fingerprint = _hash_payload({"strategy_type": strategy_type, "params": params})
    target_fingerprint = _hash_payload(targets)
    logic_fingerprint = _hash_payload(logic_payload)
    strategy_instance_hash = _hash_payload(
        {
            "strategy_type": strategy_type,
            "param_fingerprint": param_fingerprint,
            "target_fingerprint": target_fingerprint,
            "logic_fingerprint": logic_fingerprint,
        }
    )
    tested_object_hash = _hash_payload(
        {
            "strategy_type": strategy_type,
            "param_fingerprint": param_fingerprint,
            "logic_fingerprint": logic_fingerprint,
        }
    )
    return {
        "param_fingerprint": param_fingerprint,
        "target_fingerprint": target_fingerprint,
        "logic_fingerprint": logic_fingerprint,
        "strategy_instance_hash": strategy_instance_hash,
        "tested_object_hash": tested_object_hash,
    }


def materialize_strategy_params(
    strategy_type: str,
    params: Optional[Mapping[str, Any]] = None,
    *,
    seed_context: Optional[Mapping[str, Any]] = None,
    slot_index: int = 0,
    targets: Optional[list[str]] = None,
    variant_existing: bool = False,
    refresh_signal_rule: bool = False,
) -> dict[str, Any]:
    st = str(strategy_type or "").strip().lower()
    target_list = _normalize_codes(targets, limit=20)
    rng = _stable_rng(st, seed_context, slot_index, target_list)
    incoming = dict(params or {})
    resolved = {**_default_params(st, rng, target_list, slot_index=slot_index), **incoming}
    if variant_existing and incoming:
        resolved = _apply_generated_variant(st, resolved, rng, slot_index)
    if st == "momentum":
        provided = dict(params or {})
        if "lookback" in provided:
            resolved["lookback_days"] = resolved["lookback"]
        elif "lookback_days" in provided:
            resolved["lookback"] = resolved["lookback_days"]
        elif "lookback" not in resolved and "lookback_days" in resolved:
            resolved["lookback"] = resolved["lookback_days"]
        elif "lookback_days" not in resolved and "lookback" in resolved:
            resolved["lookback_days"] = resolved["lookback"]
        if "threshold" in provided:
            resolved["threshold_pct"] = resolved["threshold"]
        elif "threshold_pct" in provided:
            resolved["threshold"] = resolved["threshold_pct"]
        elif "threshold" not in resolved and "threshold_pct" in resolved:
            resolved["threshold"] = resolved["threshold_pct"]
        elif "threshold_pct" not in resolved and "threshold" in resolved:
            resolved["threshold_pct"] = resolved["threshold"]
    if st == "volatility_breakout" and "confirmation_window" not in resolved:
        resolved["confirmation_window"] = _jitter_int(rng, 4, 2, 10)
    if st == "event_structure_breakout" and "confirmation_window" not in resolved:
        resolved["confirmation_window"] = _jitter_int(rng, 4, 2, 8)
    if st == "gap_fill" and "confirmation_window" not in resolved:
        resolved["confirmation_window"] = _jitter_int(rng, 3, 1, 8)
    if st == "topn_equity_portfolio" and target_list:
        resolved.setdefault("target_symbols", target_list)
        resolved.setdefault("target_weights", {code: round(1.0 / len(target_list), 8) for code in target_list})
    if st == "mean_reversion_short" and resolved.get("rsi_period") not in (None, ""):
        resolved["rsi_period"] = max(4, int(resolved.get("rsi_period") or 4))
    if refresh_signal_rule or not resolved.get("signal_rule"):
        resolved["signal_rule"] = _default_signal_rule(st, resolved)
    resolved.setdefault("parameter_source", "materialized_defaults")
    resolved["param_materialization_version"] = PARAM_MATERIALIZATION_VERSION
    identity = structural_identity({"strategy_type": st, "params": resolved, "target_symbols": target_list})
    resolved.update(identity)
    resolved.setdefault("candidate_contract_hash", identity["strategy_instance_hash"])
    return resolved


def has_executable_params(strategy_type: str, params: Optional[Mapping[str, Any]]) -> bool:
    st = str(strategy_type or "").strip().lower()
    payload = executable_param_payload(st, params)
    if not payload:
        return False
    required = _CORE_FIELDS.get(st)
    if not required:
        return bool(payload)
    return all(payload.get(key) not in (None, "", [], {}) for key in required)


def missing_executable_fields(strategy_type: str, params: Optional[Mapping[str, Any]]) -> list[str]:
    st = str(strategy_type or "").strip().lower()
    payload = executable_param_payload(st, params)
    return [key for key in _CORE_FIELDS.get(st, tuple()) if payload.get(key) in (None, "", [], {})]
