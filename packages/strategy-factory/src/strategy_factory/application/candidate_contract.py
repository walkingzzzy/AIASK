"""Shared portfolio candidate contract helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional

from ..api.contracts import FactoryBacktestAssumptions
from ..domain.strategy_profile import infer_candidate_strategy_profile
from ..domain.targets import (
    _build_task_signature,
    _extract_target_codes_from_payload,
    _normalize_target_codes,
    _normalize_research_task_contract,
)

_EMPTY_VALUES = (None, "", [], {})
_FACTOR_VALIDATION_TYPES = {"value_factor", "quality_factor", "growth_factor", "multi_factor"}
_TARGET_SYMBOL_KEYS = frozenset({
    "target_symbols",
    "symbols",
    "codes",
    "stock_codes",
    "same_theme_symbols",
    "theme_members",
})
_DYNAMIC_TARGETING_KEYS = frozenset({
    "coverage_ratio",
    "intersection_ratio",
    "target_overlap_count",
    "constraint_check",
})


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return bool(value)


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string(value: Any) -> str:
    return str(value or "").strip()


def _normalize_string_list(*values: Any) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, (list, tuple, set)):
            candidates = list(value)
        elif value in _EMPTY_VALUES:
            candidates = []
        else:
            candidates = [value]
        for item in candidates:
            token = _string(item)
            if not token or token in seen:
                continue
            seen.add(token)
            ordered.append(token)
    return ordered


def _canonical_target_symbols(values: Any, *, limit: int = 40) -> list[str]:
    return sorted(_normalize_target_codes(values, limit=limit))


def _canonicalize_target_pool_id(pool_id: Any, *, target_symbols: Optional[list[str]] = None) -> Optional[str]:
    normalized_pool_id = _string(pool_id)
    if not normalized_pool_id:
        return None
    canonical_targets = list(target_symbols or [])
    if not canonical_targets or ":" not in normalized_pool_id:
        return normalized_pool_id
    prefix, suffix = normalized_pool_id.split(":", 1)
    if not prefix or not suffix:
        return normalized_pool_id
    suffix_symbols = _canonical_target_symbols(suffix)
    if suffix_symbols and suffix_symbols == canonical_targets:
        return f"{prefix}:{','.join(canonical_targets)}"
    return normalized_pool_id


def _canonicalize_contract_value(value: Any, *, key: Optional[str] = None) -> Any:
    if isinstance(value, Mapping):
        canonical: dict[str, Any] = {}
        for child_key, child_value in value.items():
            normalized_key = str(child_key)
            if key == "targeting" and normalized_key in _DYNAMIC_TARGETING_KEYS:
                continue
            canonical[normalized_key] = _canonicalize_contract_value(child_value, key=normalized_key)
        target_symbols = _canonical_target_symbols(canonical.get("target_symbols")) if "target_symbols" in canonical else []
        if target_symbols:
            canonical["target_symbols"] = target_symbols
        if "target_pool_id" in canonical:
            canonical["target_pool_id"] = _canonicalize_target_pool_id(
                canonical.get("target_pool_id"),
                target_symbols=target_symbols,
            )
        return canonical
    if key in _TARGET_SYMBOL_KEYS:
        return _canonical_target_symbols(value)
    if isinstance(value, (list, tuple, set)):
        return [_canonicalize_contract_value(item) for item in value]
    return value


def _semantic_contract_payload(contract: Mapping[str, Any]) -> dict[str, Any]:
    canonical = _canonicalize_contract_value(contract)
    if not isinstance(canonical, dict):
        canonical = dict(contract)
    canonical.pop("candidate_id", None)
    canonical.pop("name", None)
    lineage = dict(canonical.get("lineage") or {})
    lineage.pop("run_id", None)
    lineage.pop("parent_strategy_ids", None)
    canonical["lineage"] = lineage
    return canonical


def candidate_contract_value(candidate: Optional[Mapping[str, Any]], key: str, default: Any = None) -> Any:
    payload = dict(candidate or {})
    params = _as_dict(payload.get("params"))
    research_task = _as_dict(payload.get("research_task"))
    lineage = _as_dict(payload.get("lineage"))
    provenance = _as_dict(payload.get("candidate_provenance"))
    for source in (payload, params, lineage, provenance, research_task):
        if key in source and source.get(key) not in _EMPTY_VALUES:
            return source.get(key)
    return default


def _resolve_validation_profile(
    candidate: Optional[Mapping[str, Any]],
    *,
    research_task: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    payload = dict(candidate or {})
    normalized_task = _normalize_research_task_contract(research_task or payload.get("research_task") or {})
    strategy_type = _string(payload.get("strategy_type")).lower()
    explicit_profile = _as_dict(candidate_contract_value(payload, "validation_profile", {}))
    profile_name = _string(explicit_profile.get("profile")).lower()
    validation_focus = _string(
        explicit_profile.get("validation_focus")
        or normalized_task.get("validation_focus")
        or ("event_target_only" if normalized_task.get("task_source") == "event_driven" else "target_plus_representative")
    ).lower() or "target_plus_representative"
    if not profile_name:
        if strategy_type in _FACTOR_VALIDATION_TYPES:
            profile_name = "factor_rank_validation"
        elif strategy_type == "macro_timing":
            profile_name = "macro_regime_validation"
        elif normalized_task.get("task_source") == "event_driven" or validation_focus == "event_target_only":
            profile_name = "event_trade_validation"
        else:
            profile_name = "trade_rule_validation"
    primary_validation_layer = _string(explicit_profile.get("primary_validation_layer")).lower()
    if not primary_validation_layer:
        if validation_focus == "event_target_only":
            primary_validation_layer = "target"
        elif validation_focus == "broad_generalization" or profile_name == "factor_rank_validation":
            primary_validation_layer = "combined"
        else:
            primary_validation_layer = "target"
    return {
        "profile": profile_name,
        "validation_focus": validation_focus,
        "primary_validation_layer": primary_validation_layer,
    }


def _resolve_target_pool_id(
    candidate: Optional[Mapping[str, Any]],
    *,
    research_task: Optional[Mapping[str, Any]] = None,
    target_symbols: Optional[list[str]] = None,
) -> Optional[str]:
    payload = dict(candidate or {})
    params = _as_dict(payload.get("params"))
    normalized_task = _normalize_research_task_contract(research_task or payload.get("research_task") or {})
    stock_pool = _as_dict(candidate_contract_value(payload, "stock_pool", {}))
    task_stock_pool = _as_dict(normalized_task.get("stock_pool"))
    provenance = _as_dict(candidate_contract_value(payload, "candidate_provenance", {}))
    resolved_symbols = list(target_symbols or _extract_target_codes_from_payload(payload, limit=12))
    canonical_symbols = _canonical_target_symbols(resolved_symbols)
    for source in (payload, params, stock_pool, task_stock_pool, provenance, normalized_task):
        for key in ("target_pool_id", "pool_id", "active_pool_id", "candidate_pool_id", "theme_code", "theme_id"):
            value = _string(source.get(key))
            if value:
                return value
    selection_mode = _string(stock_pool.get("selection_mode") or task_stock_pool.get("selection_mode")).lower()
    if selection_mode and canonical_symbols:
        return f"{selection_mode}:{','.join(canonical_symbols)}"
    if canonical_symbols:
        return f"symbols:{','.join(canonical_symbols)}"
    return None


def _resolve_lineage(
    candidate: Optional[Mapping[str, Any]],
    *,
    research_task: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    payload = dict(candidate or {})
    normalized_task = _normalize_research_task_contract(research_task or payload.get("research_task") or {})
    explicit = _as_dict(candidate_contract_value(payload, "lineage", {}))
    event_context = _as_dict(payload.get("event_context") or normalized_task.get("event_context"))
    task_signature = _string(
        explicit.get("task_signature")
        or candidate_contract_value(payload, "task_signature")
        or normalized_task.get("task_signature")
        or _build_task_signature({**normalized_task, **event_context})
    )
    lineage_id = _string(
        explicit.get("lineage_id")
        or candidate_contract_value(payload, "lineage_id")
        or task_signature
    )
    run_id = _string(
        explicit.get("run_id")
        or candidate_contract_value(payload, "run_id")
        or candidate_contract_value(payload, "factory_run_id")
    )
    parent_strategy_ids = _normalize_string_list(
        explicit.get("parent_strategy_ids"),
        explicit.get("parent_candidate_ids"),
        candidate_contract_value(payload, "parent_strategy_ids"),
        candidate_contract_value(payload, "parent_candidate_ids"),
        candidate_contract_value(payload, "parent_strategy_id"),
        candidate_contract_value(payload, "parent_candidate_id"),
    )
    return {
        "lineage_id": lineage_id or None,
        "run_id": run_id or None,
        "task_signature": task_signature or None,
        "parent_strategy_ids": parent_strategy_ids,
    }


def build_portfolio_candidate_contract(candidate: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    payload = dict(candidate or {})
    normalized_task = _normalize_research_task_contract(candidate_contract_value(payload, "research_task", {}) or {})
    strategy_profile = infer_candidate_strategy_profile(payload, research_task=normalized_task)
    provenance = _as_dict(candidate_contract_value(payload, "candidate_provenance", {}))
    target_symbols = _extract_target_codes_from_payload(payload, limit=12)
    constraint_check = _as_dict(candidate_contract_value(payload, "constraint_check", {}))
    validation_profile = _resolve_validation_profile(payload, research_task=normalized_task)
    candidate_family = _string(
        candidate_contract_value(payload, "candidate_family")
        or provenance.get("candidate_family")
        or strategy_profile.get("strategy_family")
        or payload.get("strategy_type")
    ).lower()
    candidate_family_id = _string(
        candidate_contract_value(payload, "candidate_family_id")
        or provenance.get("candidate_family_id")
        or strategy_profile.get("candidate_family_id")
    )
    stock_pool = _as_dict(candidate_contract_value(payload, "stock_pool", {}))
    target_source = _string(
        candidate_contract_value(payload, "target_source")
        or stock_pool.get("selection_mode")
        or normalized_task.get("task_source")
        or payload.get("source")
    ).lower()
    targeting = {
        "target_symbols": list(target_symbols),
        "stock_pool": stock_pool,
        "target_pool_id": _resolve_target_pool_id(payload, research_task=normalized_task, target_symbols=target_symbols),
        "coverage_ratio": None
        if constraint_check.get("coverage_ratio") is None
        else round(_safe_float(constraint_check.get("coverage_ratio")), 4),
        "intersection_ratio": None
        if constraint_check.get("intersection_ratio") is None
        else round(_safe_float(constraint_check.get("intersection_ratio")), 4),
        "target_overlap_count": _safe_int(constraint_check.get("target_overlap_count")),
        "target_source": target_source or None,
        "constraint_check": constraint_check,
    }
    return {
        "candidate_id": _string(payload.get("candidate_id") or payload.get("id")) or None,
        "name": _string(payload.get("name")) or None,
        "strategy_type": _string(payload.get("strategy_type")).lower() or "unknown",
        "generator_mode": _string(payload.get("generator_mode") or strategy_profile.get("generator_mode")).lower() or None,
        "candidate_family": candidate_family or None,
        "candidate_family_id": candidate_family_id or None,
        "targeting": targeting,
        "research_task": normalized_task,
        "holding_horizon": _as_dict(candidate_contract_value(payload, "holding_horizon", {})),
        "trade_plan": _as_dict(candidate_contract_value(payload, "trade_plan", {})),
        "risk_rules": _as_dict(candidate_contract_value(payload, "risk_rules", {})),
        "rebalance_rule": candidate_contract_value(payload, "rebalance_rule", {}),
        "portfolio_spec": _as_dict(candidate_contract_value(payload, "portfolio_spec", {})),
        "execution_assumptions": _as_dict(candidate_contract_value(payload, "execution_assumptions", {})),
        "validation_profile": validation_profile,
        "lineage": _resolve_lineage(payload, research_task=normalized_task),
    }


def build_candidate_contract_hash(
    candidate: Optional[Mapping[str, Any]] = None,
    *,
    contract: Optional[Mapping[str, Any]] = None,
) -> str:
    payload = dict(contract or build_portfolio_candidate_contract(candidate))
    semantic_payload = _semantic_contract_payload(payload)
    serialized = json.dumps(semantic_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


def build_candidate_identity_signature(candidate: Optional[Mapping[str, Any]]) -> str:
    contract = _semantic_contract_payload(build_portfolio_candidate_contract(candidate))
    targeting = dict(contract.get("targeting") or {})
    lineage = dict(contract.get("lineage") or {})
    identity_payload = {
        "strategy_type": contract.get("strategy_type"),
        "candidate_family_id": contract.get("candidate_family_id"),
        "validation_profile": dict(contract.get("validation_profile") or {}),
        "targeting": {
            "target_pool_id": targeting.get("target_pool_id"),
            "target_symbols": list(targeting.get("target_symbols") or []),
        },
        "holding_horizon": dict(contract.get("holding_horizon") or {}),
        "trade_plan": dict(contract.get("trade_plan") or {}),
        "risk_rules": dict(contract.get("risk_rules") or {}),
        "rebalance_rule": contract.get("rebalance_rule"),
        "portfolio_spec": dict(contract.get("portfolio_spec") or {}),
        "execution_assumptions": dict(contract.get("execution_assumptions") or {}),
        "lineage_id": lineage.get("lineage_id"),
        "task_signature": lineage.get("task_signature"),
    }
    serialized = json.dumps(identity_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


def build_factory_backtest_assumptions(candidate: Optional[Mapping[str, Any]]) -> FactoryBacktestAssumptions:
    contract = build_portfolio_candidate_contract(candidate)
    execution_assumptions = dict(contract.get("execution_assumptions") or {})
    portfolio_spec = dict(contract.get("portfolio_spec") or {})
    validation_profile = dict(contract.get("validation_profile") or {})
    target_symbols = list((contract.get("targeting") or {}).get("target_symbols") or [])
    target_weight_scheme = _string(
        portfolio_spec.get("target_weight_scheme")
        or ("equal_weight" if len(target_symbols) > 1 else "single_name")
    ) or ("equal_weight" if len(target_symbols) > 1 else "single_name")
    return FactoryBacktestAssumptions(
        initial_capital=_safe_float(execution_assumptions.get("initial_capital"), 100000.0),
        commission_rate=_safe_float(execution_assumptions.get("commission_rate"), 0.00025),
        slippage_bps=_safe_float(
            execution_assumptions.get("slippage_bps"),
            _safe_float(execution_assumptions.get("slippage"), 0.0) * 10000.0,
        ),
        market_impact_bps=_safe_float(execution_assumptions.get("market_impact_bps"), 0.0),
        arrival_price_policy=_string(execution_assumptions.get("arrival_price_policy") or "next_open_proxy") or "next_open_proxy",
        implementation_shortfall_proxy=_safe_float(execution_assumptions.get("implementation_shortfall_proxy"), 0.0),
        tradability_filter=_safe_bool(execution_assumptions.get("tradability_filter"), True),
        slippage_model=_string(execution_assumptions.get("slippage_model") or "fixed") or "fixed",
        max_position_pct=(
            None
            if portfolio_spec.get("max_position_pct") is None
            else _safe_float(portfolio_spec.get("max_position_pct"))
        ),
        capacity_participation_rate=_safe_float(execution_assumptions.get("capacity_participation_rate"), 0.0),
        adv_ratio_limit=_safe_float(execution_assumptions.get("adv_ratio_limit"), 0.0),
        capacity_bucket=_string(execution_assumptions.get("capacity_bucket")) or None,
        position_assumption=_string(
            portfolio_spec.get("position_assumption")
            or ("equal_weight_proxy" if len(target_symbols) > 1 else "single_name_full_notional")
        )
        or ("equal_weight_proxy" if len(target_symbols) > 1 else "single_name_full_notional"),
        target_weight_scheme=target_weight_scheme,
        target_weight_map=_as_dict(portfolio_spec.get("target_weight_map")),
        market_ruleset=_string(execution_assumptions.get("market_ruleset") or "cn_equity") or "cn_equity",
        sell_tax_rate=_safe_float(execution_assumptions.get("sell_tax_rate"), 0.001),
        min_trade_lot=max(1, _safe_int(execution_assumptions.get("min_trade_lot"), 100)),
        t_plus_one=_safe_bool(execution_assumptions.get("t_plus_one"), True),
        validation_focus=_string(validation_profile.get("validation_focus") or "target_plus_representative")
        or "target_plus_representative",
    )


__all__ = [
    "build_candidate_contract_hash",
    "build_candidate_identity_signature",
    "build_factory_backtest_assumptions",
    "build_portfolio_candidate_contract",
    "candidate_contract_value",
]
