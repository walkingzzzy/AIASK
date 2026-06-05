
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional

from ..api.contracts import FactoryBacktestAssumptions, normalize_execution_assumptions
from ..domain.strategy_profile import infer_candidate_strategy_profile
from ..domain.targets import (
    _apply_target_symbol_policy,
    _build_task_signature,
    _extract_candidate_origin_target_codes,
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
_LOGIC_PARAM_SKIP_KEYS = frozenset({
    "candidate_contract_hash",
    "candidate_contract_snapshot",
    "candidate_identity_signature",
    "candidate_local_attempt_count",
    "candidate_local_selected_count",
    "candidate_lineage_contract",
    "candidate_provenance",
    "confidence_contract",
    "constraint_check",
    "contradiction_count",
    "evidence_alignment_audit",
    "evidence_chain",
    "event_context",
    "execution_contract_hash",
    "execution_assumptions",
    "factor_signature",
    "factory_attempt_count",
    "factory_global_attempt_count",
    "factory_global_selected_count",
    "factory_selected_count",
    "had_explicit_research_task",
    "holding_horizon",
    "legacy_semantic_contract",
    "logic_signature",
    "lineage",
    "lineage_id",
    "parent_candidate_id",
    "parent_candidate_ids",
    "parent_strategy_id",
    "parent_strategy_ids",
    "portfolio_spec",
    "prediction_contract",
    "proxy_dependency_score",
    "rebalance_rule",
    "request_target_symbols",
    "requested_target_symbols",
    "research_task",
    "resolved_candidate_envelope",
    "risk_rules",
    "runtime_playbook",
    "stock_pool",
    "strategy_profile",
    "target_pool_id",
    "target_symbols",
    "targeting_policy",
    "task_signature",
    "task_local_attempt_count",
    "task_local_selected_count",
    "tested_object_hash",
    "trade_plan",
    "trade_prediction_contract",
    "trade_prediction_contract_hash",
    "trade_prediction_contract_missing_fields",
    "trade_prediction_contract_reject_reasons",
    "trade_prediction_contract_status",
    "validation_profile",
    "dsl_signature",
    "entry_exit_signature",
    "legacy_identity_partial",
    "tested_object_backfill_incomplete",
})
_LOGIC_METADATA_SKIP_KEYS = frozenset({
    "candidate_contract_hash",
    "candidate_contract_snapshot",
    "candidate_family",
    "candidate_family_id",
    "candidate_identity_signature",
    "candidate_lineage_contract",
    "candidate_provenance",
    "confidence_contract",
    "codes",
    "contradiction_count",
    "dsl_signature",
    "evidence_alignment_audit",
    "evidence_chain",
    "entry_exit_signature",
    "event_context",
    "execution_contract_hash",
    "factor_signature",
    "lineage",
    "lineage_id",
    "logic_signature",
    "parent_candidate_id",
    "parent_candidate_ids",
    "parent_strategy_id",
    "parent_strategy_ids",
    "pool_id",
    "prediction_contract",
    "proxy_dependency_score",
    "research_task",
    "run_id",
    "runtime_playbook",
    "same_theme_symbols",
    "stock_codes",
    "strategy_profile",
    "strategy_tags",
    "symbols",
    "target_pool_id",
    "target_symbols",
    "task_signature",
    "tested_object_hash",
    "tested_object_backfill_incomplete",
    "trade_prediction_contract",
    "trade_prediction_contract_hash",
    "trade_prediction_contract_missing_fields",
    "trade_prediction_contract_reject_reasons",
    "trade_prediction_contract_status",
    "theme_code",
    "theme_id",
    "theme_members",
    "legacy_semantic_contract",
    "legacy_identity_partial",
})
_TOP_LEVEL_LOGIC_KEYS = (
    "alpha_formula",
    "entry_logic",
    "exit_logic",
    "factor_weights",
    "formula",
    "ranking_logic",
    "selection_logic",
    "signal_formula",
)
_FACTOR_SIGNATURE_LOGIC_KEYS = frozenset({
    "alpha_formula",
    "factor_weights",
    "formula",
    "ranking_logic",
    "selection_logic",
    "signal_formula",
})
_FACTOR_SIGNATURE_PARAM_TOKENS = ("alpha", "factor", "formula", "rank", "score", "select", "signal", "weight")
_ENTRY_EXIT_LOGIC_KEYS = frozenset({
    "entry_logic",
    "exit_logic",
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


def _compact_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        compact: dict[str, Any] = {}
        for key, child in value.items():
            compact_child = _compact_payload(child)
            if compact_child in _EMPTY_VALUES:
                continue
            compact[str(key)] = compact_child
        return compact
    if isinstance(value, (list, tuple, set)):
        compact_items = [_compact_payload(item) for item in value]
        return [item for item in compact_items if item not in _EMPTY_VALUES]
    return value


def _canonicalize_logic_value(value: Any, *, key: Optional[str] = None) -> Any:
    if isinstance(value, Mapping):
        canonical: dict[str, Any] = {}
        for child_key, child_value in value.items():
            normalized_key = str(child_key)
            if normalized_key in _LOGIC_METADATA_SKIP_KEYS:
                continue
            canonical_value = _canonicalize_logic_value(child_value, key=normalized_key)
            if canonical_value in _EMPTY_VALUES:
                continue
            canonical[normalized_key] = canonical_value
        return canonical
    if key in _TARGET_SYMBOL_KEYS:
        return []
    if isinstance(value, (list, tuple, set)):
        return [_canonicalize_logic_value(item) for item in value]
    return value


def _build_candidate_logic_payload(candidate: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    payload = dict(candidate or {})
    params = _as_dict(payload.get("params"))
    dsl = _as_dict(params.get("dsl") or payload.get("dsl"))
    if dsl:
        dsl = {
            str(key): _canonicalize_logic_value(value, key=str(key))
            for key, value in dsl.items()
            if str(key) != "metadata"
        }
    alpha_params = {
        str(key): _canonicalize_logic_value(value, key=str(key))
        for key, value in params.items()
        if str(key) not in _LOGIC_PARAM_SKIP_KEYS and str(key) not in {"dsl", "factor_weights", "selection_logic"}
    }
    top_level_logic = {
        key: _canonicalize_logic_value(payload.get(key), key=key)
        for key in _TOP_LEVEL_LOGIC_KEYS
        if payload.get(key) not in _EMPTY_VALUES
    }
    if "factor_weights" not in top_level_logic:
        factor_weights = _canonicalize_logic_value(params.get("factor_weights"), key="factor_weights")
        if factor_weights not in _EMPTY_VALUES:
            top_level_logic["factor_weights"] = factor_weights
    if "selection_logic" not in top_level_logic:
        selection_logic = _canonicalize_logic_value(params.get("selection_logic"), key="selection_logic")
        if selection_logic not in _EMPTY_VALUES:
            top_level_logic["selection_logic"] = selection_logic
    return _compact_payload({
        "strategy_type": _string(payload.get("strategy_type")).lower() or "unknown",
        "dsl": dsl,
        "logic_fields": top_level_logic,
        "alpha_params": alpha_params,
    })


def _hash_payload(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


def _has_material_logic_payload(payload: Optional[Mapping[str, Any]]) -> bool:
    item = dict(payload or {})
    return bool(
        item.get("dsl")
        or item.get("logic_fields")
        or item.get("alpha_params")
    )


def _should_include_factor_param(strategy_type: str, key: str) -> bool:
    normalized_key = _string(key).lower()
    if not normalized_key:
        return False
    if strategy_type in _FACTOR_VALIDATION_TYPES:
        return True
    return any(token in normalized_key for token in _FACTOR_SIGNATURE_PARAM_TOKENS)


def _build_dsl_signature_payload(logic_payload: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(logic_payload or {})
    return _compact_payload({
        "strategy_type": payload.get("strategy_type"),
        "dsl": dict(payload.get("dsl") or {}),
    })


def _build_factor_signature_payload(logic_payload: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(logic_payload or {})
    strategy_type = _string(payload.get("strategy_type")).lower() or "unknown"
    logic_fields = {
        str(key): value
        for key, value in dict(payload.get("logic_fields") or {}).items()
        if str(key) in _FACTOR_SIGNATURE_LOGIC_KEYS
    }
    alpha_params = {
        str(key): value
        for key, value in dict(payload.get("alpha_params") or {}).items()
        if _should_include_factor_param(strategy_type, str(key))
    }
    return _compact_payload({
        "strategy_type": strategy_type,
        "logic_fields": logic_fields,
        "alpha_params": alpha_params,
    })


def _build_entry_exit_signature_payload(logic_payload: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(logic_payload or {})
    dsl = {
        str(key): value
        for key, value in dict(payload.get("dsl") or {}).items()
        if "entry" in str(key).lower() or "exit" in str(key).lower()
    }
    logic_fields = {
        str(key): value
        for key, value in dict(payload.get("logic_fields") or {}).items()
        if str(key) in _ENTRY_EXIT_LOGIC_KEYS
    }
    return _compact_payload({
        "strategy_type": payload.get("strategy_type"),
        "dsl": dsl,
        "logic_fields": logic_fields,
    })


def build_logic_signature(candidate: Optional[Mapping[str, Any]]) -> str:
    return _hash_payload(_build_candidate_logic_payload(candidate))


def build_dsl_signature(candidate: Optional[Mapping[str, Any]]) -> Optional[str]:
    payload = _build_dsl_signature_payload(_build_candidate_logic_payload(candidate))
    if not dict(payload).get("dsl"):
        return None
    return _hash_payload(payload)


def build_factor_signature(candidate: Optional[Mapping[str, Any]]) -> Optional[str]:
    payload = _build_factor_signature_payload(_build_candidate_logic_payload(candidate))
    if not dict(payload).get("logic_fields") and not dict(payload).get("alpha_params"):
        return None
    return _hash_payload(payload)


def build_entry_exit_signature(candidate: Optional[Mapping[str, Any]]) -> Optional[str]:
    payload = _build_entry_exit_signature_payload(_build_candidate_logic_payload(candidate))
    if not dict(payload).get("dsl") and not dict(payload).get("logic_fields"):
        return None
    return _hash_payload(payload)


def build_alpha_identity_components(candidate: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    logic_payload = _build_candidate_logic_payload(candidate)
    dsl_payload = _build_dsl_signature_payload(logic_payload)
    factor_payload = _build_factor_signature_payload(logic_payload)
    entry_exit_payload = _build_entry_exit_signature_payload(logic_payload)
    return {
        "strategy_type": logic_payload.get("strategy_type"),
        "has_material_logic": _has_material_logic_payload(logic_payload),
        "logic_signature": _hash_payload(logic_payload),
        "dsl_signature": _hash_payload(dsl_payload) if dict(dsl_payload).get("dsl") else None,
        "factor_signature": (
            _hash_payload(factor_payload)
            if dict(factor_payload).get("logic_fields") or dict(factor_payload).get("alpha_params")
            else None
        ),
        "entry_exit_signature": (
            _hash_payload(entry_exit_payload)
            if dict(entry_exit_payload).get("dsl") or dict(entry_exit_payload).get("logic_fields")
            else None
        ),
    }


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
