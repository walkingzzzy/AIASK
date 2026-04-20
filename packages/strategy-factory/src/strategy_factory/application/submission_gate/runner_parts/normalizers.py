
from __future__ import annotations

import math
from typing import Any, Dict, Optional

import numpy as np

from ...domain.constants import (
    INCUBATION_ADMISSION_THRESHOLDS,
    LIVE_ADMISSION_THRESHOLDS,
    QUALITY_GATE_THRESHOLDS,
    RESEARCH_ADMISSION_THRESHOLDS,
    STRATEGY_FACTORY_SPEC_COMPLETENESS_MODE,
    TRADE_GATE_PROFILE_THRESHOLDS,
)
from ...domain.strategy_profile import infer_candidate_strategy_profile
from ...domain.targets import (
    _build_task_signature,
    _extract_target_codes_from_payload,
    _normalize_research_task_contract,
    _resolve_validation_focus_layer,
)
from ...infrastructure.mcp_services import get_normalize_klines, get_strategy_registry, get_validation_runtime
from ..candidate_contract import (
    apply_resolved_candidate_envelope,
    build_candidate_contract_hash,
    build_candidate_identity_signature,
    build_dsl_signature,
    build_entry_exit_signature,
    build_execution_contract_hash,
    build_factor_signature,
    build_logic_signature,
    build_portfolio_candidate_contract,
    build_tested_object_hash,
    resolve_candidate_validation_profile,
)
from ..research_protocol_contract import (
    adapt_research_validation_contract_for_submission,
    evaluate_research_validation_contract_admission,
)
from ..quality_reporting import maybe_grant_provisional_incubation, normalize_quality_gate_result, safe_metric_value


_FACTOR_VALIDATION_TYPES = {"value_factor", "quality_factor", "growth_factor", "multi_factor"}
_TRADE_PRIMARY_PROFILES = {"trade_rule_validation", "event_trade_validation", "macro_regime_validation"}
_ADMISSION_LEVEL_ORDER = ("research", "incubation", "live")
_ADMISSION_THRESHOLD_SETS = {
    "research": RESEARCH_ADMISSION_THRESHOLDS,
    "incubation": INCUBATION_ADMISSION_THRESHOLDS,
    "live": LIVE_ADMISSION_THRESHOLDS,
}
_SUPPLEMENTAL_STATISTICAL_FIELDS = {
    "wf_ic_ir",
    "pkf_ic",
    "bootstrap_ci_lower",
    "param_sensitivity",
    "period_robustness",
    "run_correction_mode",
    "raw_sharpe_proxy",
    "deflated_sharpe_proxy",
    "pbo_proxy",
    "reality_check_pvalue_proxy",
    "spa_pvalue_proxy",
    "multiple_testing_mode",
    "deflated_sharpe_ratio",
    "deflated_sharpe_reference_sharpe",
    "deflated_sharpe_effective_trials",
    "pbo",
    "white_reality_check_pvalue",
    "hansen_spa_pvalue",
    "multiple_testing",
    "multiple_testing_cohort_mode",
    "multiple_testing_panel_symbols",
    "multiple_testing_panel_size",
    "cohort_effective_trials",
    "batch_correlation_mode",
    "batch_correlation_multiplier",
    "batch_correlation_sibling_count",
}
_TARGET_ONLY_VALIDATION_FOCUSES = {"candidate_target_only", "event_target_only", "target_only"}
_NON_PROMOTABLE_VALIDATION_GRADES = {"D"}
_NON_PROMOTABLE_REVIEW_DECISIONS = {"reject", "revise", "retire", "drop", "defer", "watch", "observe", "paper"}
_NON_PROMOTABLE_REVIEW_RECOMMENDATIONS = {"reject", "revise", "defer", "observe_only", "paper_only"}
_LLM_CORRELATED_GENERATOR_MODES = {"external_llm", "pipeline_staged", "llm_proxy", "llm_proxy_fallback"}
_TRADE_AWARE_VALIDATION_GRADE_FAMILIES = {"momentum", "ma_cross", "quality_factor"}
_INCUBATION_OBSERVE_TARGET_LAYER_OOS_SOFT_BAND = 0.03
_INCUBATION_OBSERVE_MDD_SOFT_BAND = 0.03
_INCUBATION_OBSERVE_POST_COST_SHARPE_FLOOR = 0.55
_INCUBATION_OBSERVE_TRADE_COUNT_FLOOR = 8.0
_TREND_EXECUTABLE_DSL_TYPES = {"ma_cross", "momentum", "volatility_breakout", "event_structure_breakout"}
_PROXY_RUNTIME_FACTOR_TYPES = {"quality_factor", "value_factor", "growth_factor"}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_symbol_list(*values: Any, limit: int = 12) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    stack = list(values)
    while stack:
        value = stack.pop(0)
        if isinstance(value, (list, tuple, set)):
            stack[:0] = list(value)
            continue
        token = str(value or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
        if len(ordered) >= limit:
            break
    return ordered


def _normalize_event_anchor_payload(*values: Any) -> dict[str, Any]:
    anchor: dict[str, Any] = {}
    for value in values:
        if not isinstance(value, dict):
            continue
        payload = dict(value or {})
        if not payload:
            continue
        anchor = {
            "source": _normalize_text(payload.get("source")) or None,
            "id": _strip_text(payload.get("id")) or None,
            "type": _normalize_text(payload.get("type")) or None,
            "strength": payload.get("strength"),
            "theme_code": _strip_text(payload.get("theme_code")) or None,
            "focus_industries": _normalize_string_list(payload.get("focus_industries"), limit=6),
            "target_symbols": _normalize_symbol_list(payload.get("target_symbols"), limit=12),
        }
        if any(anchor.get(key) not in (None, "", [], {}) for key in ("source", "id", "type", "theme_code", "target_symbols")):
            return anchor
    return {}


def _materialize_backtest_metrics_contract(backtest_metrics: Optional[dict[str, Any]]) -> dict[str, Any]:
    metrics = dict(backtest_metrics or {})
    contract = dict(metrics.get("backtest_metrics_contract") or {})
    contract_status = _normalize_text(
        metrics.get("backtest_metrics_contract_status") or contract.get("status")
    ) or ("present" if contract else "missing")
    flattened = dict(metrics)
    flattened["backtest_metrics_contract"] = contract
    flattened["backtest_metrics_contract_status"] = contract_status
    if contract:
        for field_name in (
            "sharpe_ratio",
            "post_cost_sharpe",
            "trade_count",
            "trades_count",
            "max_drawdown",
            "win_rate",
            "validation_focus",
            "primary_validation_layer",
            "code_source",
            "target_codes",
        ):
            if flattened.get(field_name) in (None, "", []):
                flattened[field_name] = contract.get(field_name)
    return flattened


def _resolve_submission_generator_mode(
    strategy: dict,
    *,
    research_task: Optional[dict[str, Any]] = None,
    contract_snapshot: Optional[dict[str, Any]] = None,
) -> str | None:
    normalized_task = _normalize_research_task_contract(
        dict(
            research_task
            or _strategy_payload_value(strategy, "research_task")
            or strategy.get("research_task")
            or {}
        )
    )
    candidate_provenance = dict(
        _strategy_payload_value(strategy, "candidate_provenance")
        or strategy.get("candidate_provenance")
        or {}
    )
    snapshot = dict(
        contract_snapshot
        or _strategy_payload_value(strategy, "candidate_contract_snapshot")
        or strategy.get("candidate_contract_snapshot")
        or {}
    )
    strategy_profile = dict(snapshot.get("strategy_profile") or {})
    if not strategy_profile:
        try:
            strategy_profile = infer_candidate_strategy_profile(strategy, research_task=normalized_task)
        except Exception:
            strategy_profile = {}
    explicit_generator_mode = str(
        _strategy_payload_value(strategy, "generator_mode")
        or strategy.get("generator_mode")
        or candidate_provenance.get("generator_mode")
        or normalized_task.get("generator_mode")
        or normalized_task.get("generator_type")
        or ""
    ).strip().lower()
    had_explicit_research_task = bool(
        _strategy_payload_value(strategy, "had_explicit_research_task", strategy.get("research_task"))
    )
    generator_mode = explicit_generator_mode or str(strategy_profile.get("generator_mode") or "").strip().lower() or None
    if generator_mode == "snapshot" and not explicit_generator_mode and not had_explicit_research_task:
        generator_mode = "rule"
    return generator_mode


def _strategy_payload_value(strategy: dict, key: str, default: Any = None) -> Any:
    if key in strategy and strategy.get(key) is not None:
        return strategy.get(key)
    params = dict(strategy.get("params") or {})
    if key in params and params.get(key) is not None:
        return params.get(key)
    return default


def _resolve_semantic_runtime_context(strategy: dict, gate: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    target_codes = _extract_target_codes_from_payload(payload)
    single_name_trend = strategy_type in _TREND_EXECUTABLE_DSL_TYPES and len(target_codes) == 1
    evidence_chain = dict(_strategy_payload_value(payload, "evidence_chain") or {})
    prediction_contract = dict(_strategy_payload_value(payload, "prediction_contract") or {})
    confidence_contract = dict(_strategy_payload_value(payload, "confidence_contract") or {})
    semantic_contract_missing_fields: list[str] = []
    if strategy_type in (_TREND_EXECUTABLE_DSL_TYPES | _PROXY_RUNTIME_FACTOR_TYPES):
        if not evidence_chain:
            semantic_contract_missing_fields.append("evidence_chain")
        if not prediction_contract:
            semantic_contract_missing_fields.append("prediction_contract")
        if not confidence_contract:
            semantic_contract_missing_fields.append("confidence_contract")
    instrument_profile = dict(_strategy_payload_value(payload, "instrument_profile") or {})
    measurement_source = str(
        instrument_profile.get("measurement_source") or "default_board_profile"
    ).strip().lower() or "default_board_profile"
    measured_profile_complete = bool(instrument_profile.get("measured_profile_complete"))
    runtime_family_data_source = str(
        _strategy_payload_value(payload, "runtime_family_data_source")
        or ("price_proxy_runtime" if strategy_type in _PROXY_RUNTIME_FACTOR_TYPES else "market_data_runtime")
    ).strip().lower() or None
    proxy_runtime_used = bool(
        _strategy_payload_value(payload, "proxy_runtime_used")
    ) or (
        strategy_type in _PROXY_RUNTIME_FACTOR_TYPES
        and runtime_family_data_source != "fundamental_runtime"
    )
    semantic_runtime_match = (
        bool(_strategy_payload_value(payload, "semantic_runtime_match"))
        if _strategy_payload_value(payload, "semantic_runtime_match") is not None
        else not proxy_runtime_used
    )
    default_profile_not_allowed = single_name_trend and (
        measurement_source == "default_board_profile" or not measured_profile_complete
    )
    execution_readiness_tier = str(
        _strategy_payload_value(payload, "execution_readiness_tier")
        or (
            "missing_executable_contract"
            if single_name_trend and str(_strategy_payload_value(payload, "execution_semantic_mode") or "").strip().lower() != "compiled_dsl"
            else "observe_diagnostic_only"
            if proxy_runtime_used or default_profile_not_allowed or semantic_contract_missing_fields
            else "formal_runtime_ready"
        )
    ).strip().lower() or None
    diagnostic_only = bool(
        _strategy_payload_value(payload, "diagnostic_only")
    ) or bool(
        proxy_runtime_used
        or default_profile_not_allowed
        or semantic_contract_missing_fields
        or execution_readiness_tier == "observe_diagnostic_only"
    )
    hard_fail_reasons: list[str] = []
    if semantic_contract_missing_fields:
        hard_fail_reasons.append("final_strategy_missing_semantic_contract")
    if proxy_runtime_used:
        hard_fail_reasons.extend(
            [
                "runtime_family_semantic_mismatch",
                "proxy_runtime_not_allowed_for_formal_incubation",
            ]
        )
    if default_profile_not_allowed:
        hard_fail_reasons.append("default_profile_not_allowed_for_single_name_runtime")
    if not semantic_runtime_match and "runtime_family_semantic_mismatch" not in hard_fail_reasons:
        hard_fail_reasons.append("runtime_family_semantic_mismatch")
    if bool(dict(gate or {}).get("execution_semantic_gap")):
        hard_fail_reasons.append("execution_semantic_gap")
    return {
        "semantic_contract_missing_fields": semantic_contract_missing_fields,
        "semantic_runtime_match": semantic_runtime_match,
        "runtime_family_data_source": runtime_family_data_source,
        "proxy_runtime_used": proxy_runtime_used,
        "diagnostic_only": diagnostic_only,
        "execution_readiness_tier": execution_readiness_tier,
        "measurement_source": measurement_source,
        "measured_profile_complete": measured_profile_complete,
        "default_profile_not_allowed": default_profile_not_allowed,
        "hard_fail_reasons": list(dict.fromkeys(hard_fail_reasons)),
    }


def _should_route_single_target_bulk_factor_to_trade_profile(
    strategy: dict,
    *,
    research_task: Optional[dict[str, Any]] = None,
    validation_focus: Optional[str] = None,
) -> bool:
    strategy_type = str(strategy.get("strategy_type") or "").strip().lower()
    if strategy_type not in _FACTOR_VALIDATION_TYPES:
        return False
    raw_research_task = (
        research_task
        or _strategy_payload_value(strategy, "research_task")
        or strategy.get("research_task")
        or {}
    )
    if not raw_research_task:
        return False
    normalized_task = _normalize_research_task_contract(
        raw_research_task
    )
    resolved_validation_focus = str(
        validation_focus if validation_focus is not None else normalized_task.get("validation_focus") or ""
    ).strip().lower()
    target_codes = _extract_target_codes_from_payload(strategy)
    return (
        str(normalized_task.get("task_source") or "").strip().lower() == "bulk_stock_matrix"
        and resolved_validation_focus == "candidate_target_only"
        and len(target_codes) == 1
    )


def _resolve_validation_profile(strategy: dict) -> dict[str, Any]:
    research_task = _normalize_research_task_contract(
        _strategy_payload_value(strategy, "research_task") or strategy.get("research_task") or {}
    )
    raw_validation_profile = dict(
        _strategy_payload_value(strategy, "validation_profile")
        or strategy.get("validation_profile")
        or {}
    )
    research_protocol_adapter = dict(
        _strategy_payload_value(strategy, "research_validation_contract_submission_adapter")
        or strategy.get("research_validation_contract_submission_adapter")
        or {}
    )
    adapter_profile = dict(research_protocol_adapter.get("validation_profile") or {})
    resolved_profile = resolve_candidate_validation_profile(strategy, research_task=research_task)
    profile_name = str(resolved_profile.get("profile") or adapter_profile.get("profile") or "").strip().lower()
    validation_focus = str(
        resolved_profile.get("validation_focus") or adapter_profile.get("validation_focus") or ""
    ).strip().lower()
    primary_validation_layer = str(
        resolved_profile.get("primary_validation_layer") or adapter_profile.get("primary_validation_layer") or ""
    ).strip().lower() or "target"
    if profile_name == "factor_rank_validation" and _should_route_single_target_bulk_factor_to_trade_profile(
        strategy,
        research_task=research_task,
        validation_focus=validation_focus,
    ):
        profile_name = "trade_rule_validation"
        primary_validation_layer = "target"
    return {
        "profile": profile_name,
        "validation_focus": validation_focus,
        "primary_validation_layer": primary_validation_layer,
        "research_task": research_task,
        "objective_profile": str(
            raw_validation_profile.get("objective_profile")
            or adapter_profile.get("objective_profile")
            or research_task.get("objective_profile")
            or ""
        ).strip().lower() or None,
        "trade_density_preference": str(
            raw_validation_profile.get("trade_density_preference")
            or adapter_profile.get("trade_density_preference")
            or research_task.get("trade_density_preference")
            or ""
        ).strip().lower() or None,
        "entry_selectivity": str(
            raw_validation_profile.get("entry_selectivity")
            or adapter_profile.get("entry_selectivity")
            or ""
        ).strip().lower() or None,
        "regime_required": raw_validation_profile.get("regime_required")
        if raw_validation_profile.get("regime_required") is not None
        else adapter_profile.get("regime_required"),
        "cost_robust_required": raw_validation_profile.get("cost_robust_required")
        if raw_validation_profile.get("cost_robust_required") is not None
        else adapter_profile.get("cost_robust_required"),
    }


def _resolve_research_protocol_submission_adapter(strategy: dict) -> dict[str, Any]:
    adapter = dict(
        _strategy_payload_value(strategy, "research_validation_contract_submission_adapter")
        or strategy.get("research_validation_contract_submission_adapter")
        or {}
    )
    if adapter:
        return adapter
    contract = dict(
        _strategy_payload_value(strategy, "research_validation_contract")
        or strategy.get("research_validation_contract")
        or {}
    )
    if contract:
        return adapt_research_validation_contract_for_submission(contract)
    return {}


def _normalize_boolish(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    token = _normalize_text(value)
    if token in {"1", "true", "yes", "on", "required", "must"}:
        return True
    if token in {"0", "false", "no", "off", "optional"}:
        return False
    return bool(default)


def _normalize_string_list(*values: Any, limit: int = 8) -> list[str]:
    items: list[str] = []

    def visit(value: Any) -> None:
        if value in (None, "", [], {}):
            return
        if isinstance(value, dict):
            for key in ("source", "name", "value"):
                if value.get(key) not in (None, "", [], {}):
                    visit(value.get(key))
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)
            return
        token = str(value or "").strip()
        if not token:
            return
        if token not in items:
            items.append(token)

    for value in values:
        visit(value)
    return items[: max(1, int(limit or 8))]


def _strip_text(value: Any) -> str:
    return str(value or "").strip()


def _review_decision_rank(value: Any) -> int:
    token = _normalize_text(value)
    if token == "reject":
        return 3
    if token == "revise":
        return 2
    if token == "pending":
        return 1
    return 0


def _merge_review_decision(*values: Any) -> str:
    resolved = "pass"
    rank = -1
    for value in values:
        token = _normalize_text(value) or "pass"
        token_rank = _review_decision_rank(token)
        if token_rank > rank:
            resolved = token
            rank = token_rank
    return resolved
