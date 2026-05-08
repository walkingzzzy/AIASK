"""策略工厂回测初筛。"""


from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from copy import deepcopy
from statistics import median
from typing import Any, Dict, List, Optional

import numpy as np

from ..api.contracts import FactoryBacktestAssumptions
from ..domain.constants import (
    BACKTEST_AI_PROTOTYPE_THRESHOLDS,
    BACKTEST_CONCURRENCY,
    BACKTEST_CODE_CONCURRENCY,
    BACKTEST_DEFAULT_THRESHOLDS,
    FACTORY_SUBMISSION_MIN_BACKTEST_TRADES,
    GATE1_REPRESENTATIVE_COUNT,
    BACKTEST_TYPE_THRESHOLDS,
    REPRESENTATIVE_STOCKS,
)
from ..domain.targets import _build_target_alignment_contract
from ..domain.targets import _extract_target_codes_from_payload
from ..domain.targets import _normalize_target_codes
from ..domain.targets import _normalize_research_task_contract
from ..domain.strategy_identity import materialize_strategy_params, structural_identity, executable_param_payload, target_payload
from ..infrastructure.mcp_services import get_backtest_engine_class
from .candidate_contract import (
    apply_resolved_candidate_envelope,
    build_candidate_contract_hash,
    build_factory_backtest_assumptions,
    build_portfolio_candidate_contract,
    build_tested_object_hash,
)
from .runtime import get_strategy_factory_package as _runtime_get_strategy_factory_package


logger = logging.getLogger(__name__)

_REPRESENTATIVE_STOCK_FALLBACKS = [
    "600519", "000858", "601318", "600036", "000333",
    "002415", "600276", "601012", "300750", "000001",
]


def _representative_stock_universe() -> list[str]:
    return list(dict.fromkeys([*list(REPRESENTATIVE_STOCKS or []), *_REPRESENTATIVE_STOCK_FALLBACKS]))

def _compat_setting(name: str, default: Any) -> Any:
    return default


def _get_strategy_factory_package():
    return _runtime_get_strategy_factory_package()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _unique_reasons(reasons: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for reason in reasons:
        token = str(reason or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def _has_explicit_research_task(candidate: Optional[dict[str, Any]]) -> bool:
    payload = dict(candidate or {})
    params = dict(payload.get("params") or {})
    envelope = dict(payload.get("resolved_candidate_envelope") or {})
    marker = envelope.get("had_explicit_research_task")
    if marker is None:
        marker = params.get("had_explicit_research_task")
    if marker is None:
        marker = payload.get("had_explicit_research_task")
    if marker is not None:
        return bool(marker)
    return bool(payload.get("research_task") or params.get("research_task"))


def _is_single_target_bulk_candidate_target_only(
    candidate: Optional[dict[str, Any]],
    *,
    research_task: Optional[dict[str, Any]] = None,
    validation_focus: Optional[str] = None,
    target_codes: Optional[list[str]] = None,
) -> bool:
    payload = dict(candidate or {})
    normalized_task = _normalize_research_task_contract(research_task or payload.get("research_task") or {})
    resolved_validation_focus = str(
        validation_focus if validation_focus is not None else normalized_task.get("validation_focus") or ""
    ).strip().lower()
    resolved_target_codes = list(
        target_codes
        if target_codes is not None
        else _extract_target_codes_from_payload(payload, limit=12)
    )
    return (
        str(normalized_task.get("task_source") or "").strip().lower() == "bulk_stock_matrix"
        and resolved_validation_focus == "candidate_target_only"
        and len(resolved_target_codes) == 1
    )


_TARGET_ONLY_VALIDATION_FOCUSES = frozenset({
    "candidate_target_only",
    "event_target_only",
    "target_only",
})


def _resolve_required_sample_count(
    candidate: Optional[dict[str, Any]],
    *,
    thresholds: Optional[dict[str, Any]] = None,
    research_task: Optional[dict[str, Any]] = None,
    validation_focus: Optional[str] = None,
    target_codes: Optional[list[str]] = None,
) -> int:
    payload = dict(candidate or {})
    normalized_task = _normalize_research_task_contract(research_task or payload.get("research_task") or {})
    resolved_validation_focus = str(
        validation_focus if validation_focus is not None else normalized_task.get("validation_focus") or ""
    ).strip().lower()
    resolved_target_codes = list(
        target_codes
        if target_codes is not None
        else _extract_target_codes_from_payload(payload, limit=12)
    )
    required_sample_count = max(1, int(dict(thresholds or {}).get("min_samples") or 1))
    if _is_single_target_bulk_candidate_target_only(
        payload,
        research_task=normalized_task,
        validation_focus=resolved_validation_focus,
        target_codes=resolved_target_codes,
    ):
        return 1

    if resolved_validation_focus not in _TARGET_ONLY_VALIDATION_FOCUSES or not resolved_target_codes:
        return required_sample_count

    # Target-only validation should not require more code samples than the basket
    # can actually provide. The floor still respects the target-alignment contract.
    target_sample_cap = max(1, len(resolved_target_codes))
    required_sample_count = min(required_sample_count, target_sample_cap)
    target_alignment_contract = _build_target_alignment_contract(normalized_task, candidate=payload)
    min_target_sample_count = max(0, int(target_alignment_contract.get("min_target_sample_count") or 0))
    if min_target_sample_count > 0:
        required_sample_count = max(
            required_sample_count,
            min(target_sample_cap, min_target_sample_count),
        )
    return max(1, required_sample_count)


def _preferred_target_order(candidate: Optional[dict[str, Any]]) -> list[str]:
    payload = dict(candidate or {})
    params = dict(payload.get("params") or {})
    envelope = dict(payload.get("resolved_candidate_envelope") or {})
    preferred: list[str] = []
    for source in (
        payload.get("requested_target_symbols"),
        params.get("requested_target_symbols"),
        envelope.get("requested_target_symbols"),
    ):
        preferred.extend(_normalize_target_codes(source, limit=12))
    return list(dict.fromkeys(preferred))


def _apply_preferred_code_order(codes: list[str], preferred: list[str]) -> list[str]:
    if not codes or not preferred:
        return list(codes)
    available = set(codes)
    ordered = [code for code in preferred if code in available]
    ordered.extend(code for code in codes if code not in ordered)
    return ordered


def _summarize_numeric_series(values: Any) -> dict[str, Any]:
    if not isinstance(values, (list, tuple)):
        return {}
    numeric: list[float] = []
    for item in values:
        try:
            numeric.append(float(item))
        except (TypeError, ValueError):
            continue
    if not numeric:
        return {"points": len(list(values or []))} if values else {}
    return {
        "points": len(list(values)),
        "first": round(float(numeric[0]), 6),
        "last": round(float(numeric[-1]), 6),
        "min": round(float(min(numeric)), 6),
        "max": round(float(max(numeric)), 6),
    }


def _compact_backtest_metric_payload(metric: Optional[dict[str, Any]]) -> dict[str, Any]:
    payload = dict(metric or {})
    compact: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {
            "equity_curve",
            "cash_curve",
            "gross_exposure_curve",
            "net_exposure_curve",
            "trades",
            "component_metrics",
            "metrics",
        }:
            continue
        if value in (None, "", [], {}):
            continue
        if isinstance(value, dict):
            compact[key] = dict(value)
            continue
        if isinstance(value, list):
            if value and all(isinstance(item, (str, int, float, bool)) or item is None for item in value):
                compact[key] = list(value)[:16]
            continue
        compact[key] = value

    for curve_key in ("equity_curve", "cash_curve", "gross_exposure_curve", "net_exposure_curve"):
        summary = _summarize_numeric_series(payload.get(curve_key))
        if summary:
            compact[f"{curve_key}_summary"] = summary
    return compact


def build_target_quality_gate_summary(
    candidate: Optional[dict],
    *,
    gate_1_metrics: Optional[dict[str, Any]] = None,
    backtest_result: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    payload = dict(candidate or {})
    research_task = _normalize_research_task_contract(payload.get("research_task") or {})
    target_alignment_contract = _build_target_alignment_contract(research_task, candidate=payload)
    target_codes = _extract_target_codes_from_payload(payload, limit=12)
    research_target_symbols = list(research_task.get("target_symbols") or target_codes)
    research_target_count = len(research_target_symbols)
    quality_gate_enabled = bool(target_alignment_contract.get("quality_gate_enabled"))

    constraint_check = dict(payload.get("constraint_check") or {})
    result_payload = dict(backtest_result or {})
    if isinstance(result_payload.get("constraint_check"), dict):
        constraint_check = dict(result_payload.get("constraint_check") or {})

    coverage_ratio_raw = constraint_check.get("coverage_ratio")
    intersection_ratio_raw = constraint_check.get("intersection_ratio")
    overlap_count_raw = constraint_check.get("target_overlap_count")
    coverage_ratio = None if coverage_ratio_raw is None else round(_safe_float(coverage_ratio_raw, 0.0), 4)
    intersection_ratio = None if intersection_ratio_raw is None else round(_safe_float(intersection_ratio_raw, 0.0), 4)
    overlap_count = (
        max(0, int(overlap_count_raw))
        if overlap_count_raw is not None
        else len(set(target_codes).intersection(research_target_symbols))
    )

    min_coverage_ratio = round(_safe_float(target_alignment_contract.get("min_coverage_ratio"), 0.0), 4)
    min_intersection_ratio = round(_safe_float(target_alignment_contract.get("min_intersection_ratio"), 0.0), 4)
    min_required_overlap_count = max(0, int(target_alignment_contract.get("min_required_overlap_count") or 0))
    min_target_sample_count = max(0, int(target_alignment_contract.get("min_target_sample_count") or 0))
    min_target_layer_stability = round(_safe_float(target_alignment_contract.get("min_target_layer_stability"), 0.0), 4)

    sampled_target_count = None
    target_sample_ratio = None
    target_layer_stability = None
    target_layer_dispersion = None
    target_sharpe = None
    representative_sharpe = None
    combined_sharpe = None

    gate_1_payload = dict(gate_1_metrics or {})
    if gate_1_payload:
        target_codes_payload = gate_1_payload.get("target_codes")
        if target_codes_payload is not None:
            sampled_target_count = len(list(target_codes_payload or []))
        if sampled_target_count is not None and research_target_count > 0:
            target_sample_ratio = round(sampled_target_count / research_target_count, 4)
        sharpe_values = [_safe_float(item, 0.0) for item in list(gate_1_payload.get("sharpe_values") or [])]
        if len(sharpe_values) >= 2:
            target_sharpe = round(_safe_float(gate_1_payload.get("avg_sharpe"), 0.0), 4)
            target_layer_dispersion = round(max(sharpe_values) - min(sharpe_values), 4)
            stability_denominator = max(abs(target_sharpe), 0.5) + 1.0
            target_layer_stability = round(
                max(0.0, min(1.0, 1.0 - target_layer_dispersion / stability_denominator)),
                4,
            )

    layers = dict(result_payload.get("layers") or {})
    if layers:
        target_layer = dict((layers.get("target") or {}))
        representative_layer = dict((layers.get("representative") or {}))
        combined_layer = dict((layers.get("combined") or {}))
        if sampled_target_count is None:
            sampled_target_count = len(list(target_layer.get("successful_codes") or []))
            if research_target_count > 0:
                target_sample_ratio = round(sampled_target_count / research_target_count, 4)
        target_metrics = dict(target_layer.get("metrics") or {})
        representative_metrics = dict(representative_layer.get("metrics") or {})
        combined_metrics = dict(combined_layer.get("metrics") or result_payload.get("metrics") or {})
        target_sharpe = round(_safe_float(target_metrics.get("sharpe_ratio"), 0.0), 4)
        representative_sharpe = round(_safe_float(representative_metrics.get("sharpe_ratio"), 0.0), 4)
        combined_sharpe = round(_safe_float(combined_metrics.get("sharpe_ratio"), 0.0), 4)
        stability_scale = max(abs(target_sharpe), abs(combined_sharpe), abs(representative_sharpe), 0.25)
        target_layer_dispersion = round(
            abs(target_sharpe - combined_sharpe) + abs(target_sharpe - representative_sharpe),
            4,
        )
        target_layer_stability = round(
            max(0.0, min(1.0, 1.0 - target_layer_dispersion / (stability_scale * 4.0))),
            4,
        )

    reasons: list[str] = []
    alignment_ok = True
    sample_sufficient = True
    target_layer_stable = True

    if quality_gate_enabled:
        if not target_codes:
            alignment_ok = False
            reasons.append("target_universe_alignment_too_low")
        elif coverage_ratio is not None and coverage_ratio < min_coverage_ratio:
            alignment_ok = False
            reasons.append("target_universe_alignment_too_low")
        elif intersection_ratio is not None and intersection_ratio < min_intersection_ratio:
            alignment_ok = False
            reasons.append("target_universe_alignment_too_low")
        elif min_required_overlap_count > 0 and overlap_count < min_required_overlap_count:
            alignment_ok = False
            reasons.append("target_universe_alignment_too_low")

        if sampled_target_count is not None and min_target_sample_count > 0 and sampled_target_count < min_target_sample_count:
            sample_sufficient = False
            reasons.append("target_sample_sufficiency_too_low")

        if (
            target_layer_stability is not None
            and min_target_layer_stability > 0.0
            and target_layer_stability < min_target_layer_stability
        ):
            target_layer_stable = False
            reasons.append("target_layer_stability_too_low")

    return {
        "profile": target_alignment_contract.get("profile"),
        "quality_gate_enabled": quality_gate_enabled,
        "targeted_snapshot": bool(target_alignment_contract.get("targeted_snapshot")),
        "research_target_count": research_target_count,
        "target_symbol_count": len(target_codes),
        "coverage_ratio": coverage_ratio,
        "min_coverage_ratio": min_coverage_ratio,
        "intersection_ratio": intersection_ratio,
        "min_intersection_ratio": min_intersection_ratio,
        "target_overlap_count": int(overlap_count),
        "min_required_overlap_count": min_required_overlap_count,
        "sampled_target_count": sampled_target_count,
        "min_target_sample_count": min_target_sample_count,
        "target_sample_ratio": target_sample_ratio,
        "target_layer_stability": target_layer_stability,
        "min_target_layer_stability": min_target_layer_stability,
        "target_layer_dispersion": target_layer_dispersion,
        "target_sharpe": target_sharpe,
        "representative_sharpe": representative_sharpe,
        "combined_sharpe": combined_sharpe,
        "alignment_ok": alignment_ok,
        "sample_sufficient": sample_sufficient,
        "target_layer_stable": target_layer_stable,
        "target_alignment_contract": dict(target_alignment_contract),
        "reasons": _unique_reasons(reasons),
    }

from strategy_factory._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'backtest_filter_parts',
    'class BacktestFilter:\n',
    ['normalizers.py', 'policy.py', 'evaluation.py', 'reporting.py', 'models.py'],
    future_annotations=True,
)
