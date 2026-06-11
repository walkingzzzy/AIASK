"""Historical trend strategy recompile/backfill helpers."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional

from strategy_factory.api.semantic_contract import apply_resolved_candidate_envelope

from .instrument_profile_measurement import measure_instrument_profile_from_db
from .fundamental_runtime_contract import build_fundamental_runtime_contract_from_db
from .strategy_spec import StrategySpec

_EMPTY_VALUES = (None, "", [], {})
_TREND_RECOMPILE_TYPES = {"ma_cross", "momentum", "volatility_breakout"}
_DEFAULT_STATUSES = ("submitted", "incubating")
_ALWAYS_REPLACE_PARAM_FIELDS = {
    "execution_semantic_mode",
    "execution_semantic_gap",
    "execution_semantic_gap_reasons",
    "dsl_required",
    "dsl_compiled",
    "dsl_compile_failure_reasons",
    "runtime_recompile_backfill",
    "revision_required",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    token = _text(value).lower()
    return token in {"1", "true", "yes", "y", "on"}


def _normalize_strategy_ids(values: Any) -> list[str]:
    queue = [values]
    ordered: list[str] = []
    seen: set[str] = set()
    while queue:
        value = queue.pop(0)
        if isinstance(value, (list, tuple, set)):
            queue[:0] = list(value)
            continue
        token = _text(value)
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def _normalize_statuses(values: Any) -> list[str]:
    resolved = _normalize_strategy_ids(values)
    return resolved or list(_DEFAULT_STATUSES)


def _normalize_target_symbols(strategy: dict[str, Any]) -> list[str]:
    payloads = [
        strategy.get("target_symbols"),
        strategy.get("stock_pool"),
        dict(strategy.get("params") or {}).get("target_symbols"),
        dict(strategy.get("params") or {}).get("stock_pool"),
        dict(strategy.get("params") or {}).get("research_task"),
    ]
    ordered: list[str] = []
    seen: set[str] = set()

    def visit(value: Any) -> None:
        if value in _EMPTY_VALUES:
            return
        if isinstance(value, dict):
            for key in ("target_symbols", "symbols", "stock_pool"):
                if value.get(key) not in _EMPTY_VALUES:
                    visit(value.get(key))
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)
            return
        code = _text(value).split(".")[0]
        if code and code not in seen:
            seen.add(code)
            ordered.append(code)

    for payload in payloads:
        visit(payload)
    return ordered[:12]


def _pick_backtest_metrics(rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    metrics_rows = list(rows or [])
    if not metrics_rows:
        return {}
    for preferred_period in ("backtest", "all"):
        selected = next((dict(item) for item in metrics_rows if _text(item.get("period")).lower() == preferred_period), None)
        if selected:
            return selected
    return dict(metrics_rows[0] or {})


def _backfill_metadata(strategy: dict[str, Any], *, backtest_metrics: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    params = dict(strategy.get("params") or {})
    metadata = {
        "source_candidate": strategy,
        "target_symbols": strategy.get("target_symbols") or params.get("target_symbols"),
        "stock_pool": strategy.get("stock_pool") or params.get("stock_pool"),
        "research_task": strategy.get("research_task") or params.get("research_task"),
        "event_context": strategy.get("event_context") or params.get("event_context"),
        "selection_logic": strategy.get("selection_logic") or params.get("selection_logic"),
        "research_scope": strategy.get("research_scope") or params.get("research_scope"),
        "hypothesis_artifact": strategy.get("hypothesis_artifact") or params.get("hypothesis_artifact"),
        "holding_horizon": strategy.get("holding_horizon") or params.get("holding_horizon"),
        "trade_plan": strategy.get("trade_plan") or params.get("trade_plan"),
        "risk_rules": strategy.get("risk_rules") or params.get("risk_rules"),
        "position_sizing": strategy.get("position_sizing") or params.get("position_sizing"),
        "rebalance_rule": strategy.get("rebalance_rule") or params.get("rebalance_rule"),
        "portfolio_spec": strategy.get("portfolio_spec") or params.get("portfolio_spec"),
        "execution_assumptions": strategy.get("execution_assumptions") or params.get("execution_assumptions"),
        "runtime_playbook": strategy.get("runtime_playbook") or params.get("runtime_playbook"),
        "validation_profile": strategy.get("validation_profile") or params.get("validation_profile"),
        "targeting_policy": strategy.get("targeting_policy") or params.get("targeting_policy"),
        "constraint_check": strategy.get("constraint_check") or params.get("constraint_check"),
        "holding_rationale": strategy.get("holding_rationale") or params.get("holding_rationale"),
        "alpha_half_life": strategy.get("alpha_half_life") or params.get("alpha_half_life"),
        "cost_sensitivity_grid": strategy.get("cost_sensitivity_grid") or params.get("cost_sensitivity_grid"),
        "position_model": strategy.get("position_model") or params.get("position_model"),
        "capacity_assumption": strategy.get("capacity_assumption") or params.get("capacity_assumption"),
        "market_regime_assumption": strategy.get("market_regime_assumption") or params.get("market_regime_assumption"),
        "instrument_profile": strategy.get("instrument_profile") or params.get("instrument_profile"),
        "source_symbol_summary": strategy.get("source_symbol_summary") or params.get("source_symbol_summary"),
        "backtest_metrics": backtest_metrics or strategy.get("backtest_metrics") or params.get("backtest_metrics"),
        "evidence_chain": strategy.get("evidence_chain") or params.get("evidence_chain"),
        "prediction_contract": strategy.get("prediction_contract") or params.get("prediction_contract"),
        "confidence_contract": strategy.get("confidence_contract") or params.get("confidence_contract"),
        "evidence_alignment_audit": strategy.get("evidence_alignment_audit") or params.get("evidence_alignment_audit"),
        "dsl_support_audit": strategy.get("dsl_support_audit") or params.get("dsl_support_audit"),
        "claim_to_trade_plan_map": strategy.get("claim_to_trade_plan_map") or params.get("claim_to_trade_plan_map"),
        "trade_plan_to_dsl_map": strategy.get("trade_plan_to_dsl_map") or params.get("trade_plan_to_dsl_map"),
        "regime_filter_contract": strategy.get("regime_filter_contract") or params.get("regime_filter_contract"),
        "parameter_coherence_audit": strategy.get("parameter_coherence_audit") or params.get("parameter_coherence_audit"),
        "thesis_invalidation_contract": strategy.get("thesis_invalidation_contract") or params.get("thesis_invalidation_contract"),
        "drawdown_invalidation_contract": strategy.get("drawdown_invalidation_contract") or params.get("drawdown_invalidation_contract"),
        "family_specialization": strategy.get("family_specialization") or params.get("family_specialization"),
        "generation_reason": strategy.get("generation_reason") or params.get("generation_reason"),
        "committee_review": strategy.get("committee_review") or params.get("committee_review"),
        "description": strategy.get("description"),
    }
    return {key: deepcopy(value) for key, value in metadata.items() if value not in _EMPTY_VALUES}


def _deep_fill(existing: Any, generated: Any) -> tuple[Any, bool, bool]:
    if existing in _EMPTY_VALUES:
        return deepcopy(generated), True, False
    if generated in _EMPTY_VALUES:
        return deepcopy(existing), False, False
    if isinstance(existing, dict) and isinstance(generated, dict):
        merged = deepcopy(existing)
        applied = False
        skipped = False
        for key, value in generated.items():
            if key not in merged:
                merged[key] = deepcopy(value)
                applied = True
                continue
            merged_value, child_applied, child_skipped = _deep_fill(merged.get(key), value)
            merged[key] = merged_value
            applied = applied or child_applied
            skipped = skipped or child_skipped or (child_applied is False and merged.get(key) != value and value not in _EMPTY_VALUES)
        return merged, applied, skipped
    return deepcopy(existing), False, True


def _merge_params(
    existing_params: dict[str, Any],
    generated_params: dict[str, Any],
    *,
    force: bool = False,
) -> tuple[dict[str, Any], list[str], list[str]]:
    merged = deepcopy(existing_params)
    applied_fields: list[str] = []
    preserved_fields: list[str] = []
    for key, value in generated_params.items():
        if key in _ALWAYS_REPLACE_PARAM_FIELDS or force:
            if merged.get(key) != value:
                merged[key] = deepcopy(value)
                applied_fields.append(key)
            continue
        if key not in merged or merged.get(key) in _EMPTY_VALUES:
            merged[key] = deepcopy(value)
            applied_fields.append(key)
            continue
        merged_value, applied, skipped = _deep_fill(merged.get(key), value)
        if applied:
            merged[key] = merged_value
            applied_fields.append(key)
        elif skipped:
            preserved_fields.append(key)
    return merged, sorted(set(applied_fields)), sorted(set(preserved_fields))


def _strategy_save_payload(strategy: dict[str, Any], params: dict[str, Any], *, tags: Optional[list[str]] = None) -> dict[str, Any]:
    return {
        "id": strategy.get("id"),
        "name": strategy.get("name"),
        "description": strategy.get("description"),
        "author_id": strategy.get("author_id") or "strategy_factory",
        "strategy_type": strategy.get("strategy_type"),
        "params": params,
        "factor_weights": dict(strategy.get("factor_weights") or {}),
        "status": strategy.get("status") or "draft",
        "tags": list(tags or strategy.get("tags") or []),
        "backtest_artifact_id": strategy.get("backtest_artifact_id"),
    }


def _save_payload_changed(strategy: dict[str, Any], updated_payload: dict[str, Any]) -> bool:
    comparable_fields = (
        "name",
        "description",
        "strategy_type",
        "params",
        "factor_weights",
        "tags",
        "backtest_artifact_id",
    )
    return any(updated_payload.get(field) != strategy.get(field) for field in comparable_fields)


# 仅与 DSL 可执行性相关的 gap 原因前缀。其余 gap(如语义契约缺失)不影响"DSL 能否被
# 信号生成引擎执行",不应让 _is_compiled_dsl_ready 误判为未编译。
_DSL_BLOCKING_GAP_PREFIXES = (
    "compiled_dsl_missing",
    "trade_plan_to_dsl_map_missing",
    "dsl_compile_failed",
    "dsl_compile_failure",
    "trend_family_dsl_synthesis_failed",
)


def _is_compiled_dsl_ready(params: dict[str, Any]) -> bool:
    """判断 DSL 是否已编译且可被信号生成引擎执行。

    只看 DSL 可执行性,不混入语义契约完整性(evidence/prediction/confidence)——
    后者属 formal 晋升关卡(由 _recompiled_formal_ready 把关),与"规则引擎能否产信号"无关。
    """
    payload = dict(params or {})
    mode = str(payload.get("execution_semantic_mode") or "").strip().lower()
    if mode != "compiled_dsl" or not bool(payload.get("dsl_compiled")):
        return False
    # 仅当存在真正与 DSL 相关的 gap 时才判未就绪
    gap_reasons = [str(r or "").strip().lower() for r in (payload.get("execution_semantic_gap_reasons") or [])]
    for reason in gap_reasons:
        if any(reason.startswith(prefix) for prefix in _DSL_BLOCKING_GAP_PREFIXES):
            return False
    return True


def _strict_gate_passed(strategy: dict[str, Any], params: dict[str, Any]) -> bool:
    """读取原策略的 strict gate 通过证据(来自提交期 quality summary)。

    缺证据时返回 False —— 宁可不升 formal,也不误升未经严格门的样本。
    """
    for source in (params, strategy):
        payload = dict(source or {})
        for key in ("strict_incubation_ready", "passed_strict"):
            value = payload.get(key)
            if isinstance(value, bool):
                if value:
                    return True
            elif _safe_bool(value) and _text(value):
                return True
    return False


def _recompiled_formal_ready(params: dict[str, Any], strategy: dict[str, Any]) -> bool:
    """重编译 + 测量后,判断样本是否满足 formal_runtime 升级条件。

    严格复核,不另造门:复用 admission_authority.formal_runtime_ready 的等价语义子集。
    趋势家族要求 compiled_dsl + measured profile;因子家族要求真实 fundamental_runtime。
    """
    payload = dict(params or {})
    strategy_type = _text(strategy.get("strategy_type")).lower()
    is_factor_family = strategy_type in _FACTOR_RECOMPILE_TYPES

    if bool(payload.get("proxy_runtime_used")):
        return False
    if bool(payload.get("diagnostic_only")):
        return False
    if str(payload.get("execution_readiness_tier") or "").strip().lower() != "formal_runtime_ready":
        return False
    if str(payload.get("trade_prediction_contract_status") or "").strip().lower() != "ready":
        return False
    if not bool(payload.get("semantic_runtime_match", True)):
        return False

    if is_factor_family:
        contract = dict(payload.get("fundamental_runtime_contract") or {})
        if not contract.get("measured_fields"):
            return False
        if str(payload.get("runtime_family_data_source") or "").strip().lower() != "fundamental_runtime":
            return False
    else:
        if not _is_compiled_dsl_ready(payload):
            return False
        instrument_profile = dict(payload.get("instrument_profile") or {})
        measurement_source = str(instrument_profile.get("measurement_source") or "").strip().lower()
        if measurement_source not in {"measured", "measured_runtime"}:
            return False
        if not bool(instrument_profile.get("measured_profile_complete")):
            return False
    return _strict_gate_passed(strategy, payload)


def build_trend_strategy_recompile_backfill(
    strategy: dict[str, Any],
    *,
    backtest_metrics: Optional[dict[str, Any]] = None,
    measured_profile_summary: Optional[dict[str, Any]] = None,
    force: bool = False,
    timestamp: Optional[str] = None,
) -> dict[str, Any]:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    strategy_id = _text(payload.get("id"))
    strategy_type = _text(payload.get("strategy_type")).lower()
    status = _text(payload.get("status")).lower()
    target_symbols = _normalize_target_symbols(payload)
    timestamp_value = timestamp or datetime.now(timezone.utc).isoformat()
    eligible_status = status in set(_DEFAULT_STATUSES)
    eligible_type = strategy_type in _TREND_RECOMPILE_TYPES
    deterministic_eligible = eligible_type and len(target_symbols) == 1

    if not eligible_type:
        return {
            "strategy_id": strategy_id,
            "status": "skipped",
            "reason": "unsupported_strategy_type",
            "deterministic_recompile_eligible": False,
            "updated_payload": _strategy_save_payload(payload, params),
        }
    if not eligible_status:
        return {
            "strategy_id": strategy_id,
            "status": "skipped",
            "reason": "unsupported_status",
            "deterministic_recompile_eligible": deterministic_eligible,
            "updated_payload": _strategy_save_payload(payload, params),
        }

    # P1-2: 已成功重编译过的样本直接跳过(返回原 payload,不改不 save),
    # 避免 save 刷新 updated_at 把已处理样本顶到扫描窗口前列、霸占 batch,
    # 让扫描自然推进到尚未补齐的存量 observe 样本。force=True 时不跳过。
    if not force and _is_compiled_dsl_ready(params) and params.get("runtime_recompile_backfill"):
        return {
            "strategy_id": strategy_id,
            "status": "already_compiled",
            "reason": "compiled_dsl_already_present",
            "deterministic_recompile_eligible": deterministic_eligible,
            "updated_payload": _strategy_save_payload(payload, params),
        }

    updated_params = deepcopy(params)
    tags = list(dict.fromkeys([*list(payload.get("tags") or []), "high_confidence_recompile_backfill"]))
    if not deterministic_eligible:
        reasons = [
            *[
                _text(item)
                for item in list(updated_params.get("execution_semantic_gap_reasons") or [])
                if _text(item)
            ],
            "historical_trend_recompile_requires_single_target_symbol",
        ]
        updated_params.update(
            {
                "execution_semantic_mode": "missing_executable_contract",
                "execution_semantic_gap": True,
                "execution_semantic_gap_reasons": list(dict.fromkeys(reasons)),
                "revision_required": True,
                "runtime_recompile_backfill": {
                    "status": "revision_required",
                    "reason": "historical_trend_recompile_requires_single_target_symbol",
                    "strategy_type": strategy_type,
                    "target_symbols": target_symbols,
                    "deterministic_recompile_eligible": False,
                    "recommended_submission_lane": "observe_incubation",
                    "recompiled_at": timestamp_value,
                },
            }
        )
        return {
            "strategy_id": strategy_id,
            "status": "revision_required",
            "reason": "historical_trend_recompile_requires_single_target_symbol",
            "deterministic_recompile_eligible": False,
            "target_symbols": target_symbols,
            "updated_payload": _strategy_save_payload(payload, updated_params, tags=tags),
            "applied_param_fields": [
                "execution_semantic_mode",
                "execution_semantic_gap",
                "execution_semantic_gap_reasons",
                "revision_required",
                "runtime_recompile_backfill",
            ],
            "preserved_param_fields": [],
        }

    metadata = _backfill_metadata(payload, backtest_metrics=backtest_metrics)
    # P0-b: 注入真实测量的 instrument-profile 指标,使 StrategySpec 重建时
    # _normalize_instrument_profile 把 measurement_source 升级为 measured,
    # 解除 default_profile_not_allowed_for_single_name_runtime 阻塞。
    if measured_profile_summary and bool(measured_profile_summary.get("measured")):
        existing_summary = dict(metadata.get("source_symbol_summary") or {})
        existing_summary.update(measured_profile_summary)
        metadata["source_symbol_summary"] = existing_summary
    spec = StrategySpec(
        strategy_type=strategy_type,
        params=deepcopy(params),
        name=_text(payload.get("name")),
        description=_text(payload.get("description")),
        tags=list(payload.get("tags") or []),
        metadata=metadata,
    )
    generated_candidate = apply_resolved_candidate_envelope(
        spec.to_candidate(source="trend_recompile_backfill", experiment_id=f"recompile_backfill:{strategy_id}")
    )
    generated_params = dict(generated_candidate.get("params") or {})
    merged_params, applied_fields, preserved_fields = _merge_params(updated_params, generated_params, force=force)
    compiled_ready = _is_compiled_dsl_ready(merged_params)
    result_status = "recompiled" if compiled_ready else "revision_required"
    result_reason = None if compiled_ready else "deterministic_recompile_did_not_produce_compiled_dsl"
    if compiled_ready:
        merged_params["revision_required"] = False
    else:
        reasons = [
            *[_text(item) for item in list(merged_params.get("execution_semantic_gap_reasons") or []) if _text(item)],
            "deterministic_recompile_did_not_produce_compiled_dsl",
        ]
        merged_params["execution_semantic_mode"] = (
            _text(merged_params.get("execution_semantic_mode")) or "missing_executable_contract"
        )
        merged_params["execution_semantic_gap"] = True
        merged_params["execution_semantic_gap_reasons"] = list(dict.fromkeys(reasons))
        merged_params["revision_required"] = True
    merged_params["runtime_recompile_backfill"] = {
        "status": result_status,
        "reason": result_reason,
        "strategy_type": strategy_type,
        "target_symbols": target_symbols,
        "deterministic_recompile_eligible": True,
        "recompiled_at": timestamp_value,
        "source": "trend_recompile_backfill",
        "applied_param_fields": applied_fields,
        "preserved_param_fields": preserved_fields,
    }
    updated_payload = _strategy_save_payload(payload, merged_params, tags=tags)
    return {
        "strategy_id": strategy_id,
        "status": result_status,
        "reason": result_reason,
        "deterministic_recompile_eligible": True,
        "target_symbols": target_symbols,
        "updated_payload": updated_payload,
        "generated_candidate": generated_candidate,
        "applied_param_fields": applied_fields,
        "preserved_param_fields": preserved_fields,
    }


_FACTOR_RECOMPILE_TYPES = {"quality_factor", "value_factor", "growth_factor"}


def build_factor_strategy_recompile_backfill(
    strategy: dict[str, Any],
    *,
    fundamental_contract: Optional[dict[str, Any]] = None,
    backtest_metrics: Optional[dict[str, Any]] = None,
    force: bool = False,
    timestamp: Optional[str] = None,
) -> dict[str, Any]:
    """因子家族(quality/value/growth)重建:注入真实 fundamental_runtime_contract,
    使 spec 重算 runtime_family_data_source=fundamental_runtime,解除 proxy 阻塞。

    无真实 fundamental_contract 时不强行升级,保持 proxy(observe),只回显诊断。
    """
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    strategy_id = _text(payload.get("id"))
    strategy_type = _text(payload.get("strategy_type")).lower()
    status = _text(payload.get("status")).lower()
    target_symbols = _normalize_target_symbols(payload)
    timestamp_value = timestamp or datetime.now(timezone.utc).isoformat()

    if strategy_type not in _FACTOR_RECOMPILE_TYPES:
        return {
            "strategy_id": strategy_id,
            "status": "skipped",
            "reason": "unsupported_strategy_type",
            "updated_payload": _strategy_save_payload(payload, params),
        }
    if status not in set(_DEFAULT_STATUSES):
        return {
            "strategy_id": strategy_id,
            "status": "skipped",
            "reason": "unsupported_status",
            "updated_payload": _strategy_save_payload(payload, params),
        }
    if not fundamental_contract or not bool(fundamental_contract.get("measured_fields")):
        # 无真实财务数据 → 不造空壳,保持 proxy(observe)。
        return {
            "strategy_id": strategy_id,
            "status": "revision_required",
            "reason": "fundamental_runtime_contract_unavailable",
            "updated_payload": _strategy_save_payload(payload, params),
        }

    metadata = _backfill_metadata(payload, backtest_metrics=backtest_metrics)
    metadata["fundamental_runtime_contract"] = dict(fundamental_contract)
    metadata["runtime_family_data_source"] = "fundamental_runtime"
    spec_params = deepcopy(params)
    spec_params["fundamental_runtime_contract"] = dict(fundamental_contract)
    spec_params["runtime_family_data_source"] = "fundamental_runtime"
    spec = StrategySpec(
        strategy_type=strategy_type,
        params=spec_params,
        name=_text(payload.get("name")),
        description=_text(payload.get("description")),
        tags=list(payload.get("tags") or []),
        metadata=metadata,
    )
    generated_candidate = apply_resolved_candidate_envelope(
        spec.to_candidate(source="factor_recompile_backfill", experiment_id=f"factor_backfill:{strategy_id}")
    )
    generated_params = dict(generated_candidate.get("params") or {})
    merged_params, applied_fields, preserved_fields = _merge_params(
        deepcopy(params), generated_params, force=force
    )
    # 强制落上真实契约(确保不被旧值覆盖)
    merged_params["fundamental_runtime_contract"] = dict(fundamental_contract)
    if str(merged_params.get("runtime_family_data_source") or "").strip().lower() != "fundamental_runtime":
        merged_params["runtime_family_data_source"] = "fundamental_runtime"
    proxy_cleared = not bool(merged_params.get("proxy_runtime_used"))
    result_status = "recompiled" if proxy_cleared else "revision_required"
    result_reason = None if proxy_cleared else "proxy_runtime_not_cleared_after_fundamental_contract"
    merged_params["runtime_recompile_backfill"] = {
        "status": result_status,
        "reason": result_reason,
        "strategy_type": strategy_type,
        "target_symbols": target_symbols,
        "recompiled_at": timestamp_value,
        "source": "factor_recompile_backfill",
        "fundamental_data_quality": fundamental_contract.get("data_quality"),
        "fundamental_report_date": fundamental_contract.get("report_date"),
    }
    tags = list(dict.fromkeys([*list(payload.get("tags") or []), "fundamental_runtime_backfill"]))
    updated_payload = _strategy_save_payload(payload, merged_params, tags=tags)
    return {
        "strategy_id": strategy_id,
        "status": result_status,
        "reason": result_reason,
        "target_symbols": target_symbols,
        "updated_payload": updated_payload,
        "generated_candidate": generated_candidate,
        "applied_param_fields": applied_fields,
        "preserved_param_fields": preserved_fields,
    }


async def backfill_historical_trend_strategies(
    db,
    *,
    strategy_ids: Optional[list[str]] = None,
    statuses: Optional[list[str]] = None,
    limit: Optional[int] = None,
    offset: int = 0,
    batch_size: int = 100,
    dry_run: bool = False,
    force: bool = False,
    measure_profile: bool = True,
    promote_ready: bool = True,
) -> dict[str, Any]:
    ids = _normalize_strategy_ids(strategy_ids or [])
    rows: list[dict[str, Any]] = []
    if ids:
        for strategy_id in ids:
            strategy = await db.get_strategy(strategy_id)
            if strategy:
                rows.append(strategy)
    else:
        resolved_statuses = _normalize_statuses(statuses)
        current_offset = max(0, int(offset or 0))
        remaining = int(limit or 0) if limit else None
        while True:
            fetch_limit = min(max(1, int(batch_size or 100)), remaining or max(1, int(batch_size or 100)))
            batch = await db.list_strategies(status=resolved_statuses, limit=fetch_limit, offset=current_offset)
            if not batch:
                break
            rows.extend(list(batch))
            current_offset += len(batch)
            if remaining is not None:
                remaining -= len(batch)
                if remaining <= 0:
                    break
            if len(batch) < fetch_limit:
                break

    scanned = 0
    updated = 0
    recompiled = 0
    revision_required = 0
    skipped = 0
    promoted_count = 0
    items: list[dict[str, Any]] = []
    for strategy in rows:
        scanned += 1
        backtest_metrics = {}
        if hasattr(db, "get_strategy_metrics"):
            metrics_rows = await db.get_strategy_metrics(_text(strategy.get("id")))
            backtest_metrics = _pick_backtest_metrics(metrics_rows)
        strategy_type = _text(strategy.get("strategy_type")).lower()
        target_symbols = _normalize_target_symbols(strategy)
        if strategy_type in _FACTOR_RECOMPILE_TYPES:
            fundamental_contract = None
            primary_code = target_symbols[0] if len(target_symbols) >= 1 else None
            if primary_code:
                fundamental_contract = await build_fundamental_runtime_contract_from_db(
                    db, strategy_type, primary_code
                )
            result = build_factor_strategy_recompile_backfill(
                strategy,
                fundamental_contract=fundamental_contract,
                backtest_metrics=backtest_metrics,
                force=force,
            )
        else:
            measured_profile_summary = None
            if measure_profile and strategy_type in _TREND_RECOMPILE_TYPES and len(target_symbols) == 1:
                measured_profile_summary = await measure_instrument_profile_from_db(
                    db, target_symbols[0]
                )
            result = build_trend_strategy_recompile_backfill(
                strategy,
                backtest_metrics=backtest_metrics,
                measured_profile_summary=measured_profile_summary,
                force=force,
            )
        updated_payload = dict(result.get("updated_payload") or {})
        promoted = False
        if (
            promote_ready
            and result.get("status") == "recompiled"
            and _text(strategy.get("status")).lower() == "submitted"
        ):
            merged_params = dict(updated_payload.get("params") or {})
            if _recompiled_formal_ready(merged_params, strategy):
                merged_params["submission_lane"] = "formal_incubation"
                merged_params["incubation_budget_track"] = "formal_incubation"
                merged_params["final_status"] = "incubating"
                merged_params["formal_track_requested"] = True
                merged_params["formal_track_auto_corrected"] = True
                merged_params["formal_promoted_via"] = "trend_recompile_backfill"
                updated_payload["params"] = merged_params
                updated_payload["status"] = "incubating"
                promoted = True
        changed = _save_payload_changed(strategy, updated_payload) or promoted
        if result.get("status") == "recompiled":
            recompiled += 1
        elif result.get("status") == "revision_required":
            revision_required += 1
        else:
            skipped += 1
        if promoted:
            promoted_count += 1
        if changed:
            updated += 1
            if not dry_run:
                await db.save_strategy(updated_payload)
        items.append(
            {
                "strategy_id": result.get("strategy_id"),
                "status": result.get("status"),
                "reason": result.get("reason"),
                "deterministic_recompile_eligible": bool(result.get("deterministic_recompile_eligible")),
                "target_symbols": list(result.get("target_symbols") or []),
                "changed": changed,
                "promoted_to_formal": promoted,
                "applied_param_fields": list(result.get("applied_param_fields") or []),
                "preserved_param_fields": list(result.get("preserved_param_fields") or []),
            }
        )
    return {
        "scanned": scanned,
        "updated": updated,
        "recompiled": recompiled,
        "revision_required": revision_required,
        "skipped": skipped,
        "promoted_to_formal": promoted_count,
        "dry_run": bool(dry_run),
        "force": bool(force),
        "items": items,
    }
