

def _is_rl_bandit_momentum_candidate(candidate: dict, research_task: Optional[dict] = None) -> bool:
    payload = dict(candidate or {})
    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    generation_mode = _candidate_generation_mode(payload, research_task)
    tags = _candidate_tags(payload)
    return strategy_type == "momentum" and (
        generation_mode == "rl_bandit"
        or "generator_rl_bandit" in tags
        or "rl_bandit" in tags
        or "rl_evolved" in tags
    )


def _is_rl_bandit_volatility_breakout_candidate(candidate: dict, research_task: Optional[dict] = None) -> bool:
    payload = dict(candidate or {})
    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    generation_mode = _candidate_generation_mode(payload, research_task)
    tags = _candidate_tags(payload)
    return strategy_type == "volatility_breakout" and (
        generation_mode == "rl_bandit"
        or "generator_rl_bandit" in tags
        or "rl_bandit" in tags
        or "rl_evolved" in tags
    )


def _gate_2_selection_signature(candidate: dict) -> str:
    try:
        return candidate_signature(candidate)
    except Exception:
        return json.dumps(
            {
                "strategy_type": str((candidate or {}).get("strategy_type") or "").strip().lower(),
                "target_symbols": list(_extract_target_codes_from_payload(candidate or {}, limit=12)),
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )


def _gate_2_priority_adjustments(candidate: dict, research_task: dict, gate_1_score: float) -> dict[str, Any]:
    payload = dict(candidate or {})
    tags = _candidate_tags(payload)
    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    target_codes = _extract_target_codes_from_payload(payload, limit=12)
    target_count = len(target_codes)
    validation_focus = str(research_task.get("validation_focus") or "").strip().lower()
    gate_1_metrics = dict((payload.get("gate_1_result") or {}).get("metrics") or {})
    constraint_check = _candidate_constraint_check(payload)
    coverage_ratio_raw = constraint_check.get("coverage_ratio")
    intersection_ratio_raw = constraint_check.get("intersection_ratio")
    coverage_ratio = None if coverage_ratio_raw is None else _safe_float(coverage_ratio_raw, 0.0)
    intersection_ratio = None if intersection_ratio_raw is None else _safe_float(intersection_ratio_raw, 0.0)
    avg_turnover_proxy = _safe_float(gate_1_metrics.get("avg_turnover_proxy"), 0.0)
    avg_total_return = _safe_float(gate_1_metrics.get("avg_total_return"), 0.0)
    target_quality_summary = build_target_quality_gate_summary(payload, gate_1_metrics=gate_1_metrics)
    sampled_target_count = int(target_quality_summary.get("sampled_target_count") or 0)
    min_target_sample_count = int(target_quality_summary.get("min_target_sample_count") or 0)
    target_layer_stability = (
        None
        if target_quality_summary.get("target_layer_stability") is None
        else _safe_float(target_quality_summary.get("target_layer_stability"), 0.0)
    )
    min_target_layer_stability = _safe_float(target_quality_summary.get("min_target_layer_stability"), 0.0)
    gate_1_threshold = float(_compat_setting("GATE1_SHARPE_MIN", GATE1_SHARPE_MIN) or GATE1_SHARPE_MIN)
    low_edge_cutoff = gate_1_threshold + _SNAPSHOT_LOW_EDGE_BUFFER
    targeted_snapshot = _is_targeted_snapshot_candidate(
        payload,
        research_task,
        tags=tags,
        target_count=target_count,
        validation_focus=validation_focus,
    )
    pipeline_staged_ma_cross = _is_pipeline_staged_ma_cross_candidate(payload, research_task)
    rl_bandit_momentum = _is_rl_bandit_momentum_candidate(payload, research_task)

    adjustments: dict[str, float] = {}
    if targeted_snapshot:
        if coverage_ratio is not None:
            if coverage_ratio <= 0.0:
                adjustments["coverage_zero_penalty"] = -12.0
            elif coverage_ratio < _SNAPSHOT_ALIGNMENT_SOFT_COVERAGE:
                adjustments["coverage_penalty"] = -8.0
            elif coverage_ratio < 0.6:
                adjustments["coverage_penalty"] = -4.0
            elif coverage_ratio >= 0.85:
                adjustments["coverage_bonus"] = 2.0
        if intersection_ratio is not None:
            if intersection_ratio <= 0.0:
                adjustments["intersection_zero_penalty"] = adjustments.get("intersection_zero_penalty", 0.0) - 8.0
            elif intersection_ratio < _SNAPSHOT_ALIGNMENT_SOFT_INTERSECTION:
                adjustments["intersection_penalty"] = adjustments.get("intersection_penalty", 0.0) - 4.0
            elif intersection_ratio < 0.5:
                adjustments["intersection_penalty"] = adjustments.get("intersection_penalty", 0.0) - 2.0
            else:
                adjustments["intersection_bonus"] = adjustments.get("intersection_bonus", 0.0) + 1.5
        if avg_turnover_proxy >= _SNAPSHOT_VERY_HIGH_TURNOVER_THRESHOLD and gate_1_score < (low_edge_cutoff + 0.06):
            adjustments["turnover_penalty"] = adjustments.get("turnover_penalty", 0.0) - 10.0
        elif avg_turnover_proxy >= _SNAPSHOT_HIGH_TURNOVER_THRESHOLD and gate_1_score < low_edge_cutoff:
            adjustments["turnover_penalty"] = adjustments.get("turnover_penalty", 0.0) - 6.0
        if avg_total_return <= 0.0 and gate_1_score < (low_edge_cutoff + 0.03):
            adjustments["low_edge_penalty"] = adjustments.get("low_edge_penalty", 0.0) - 4.0
        if avg_turnover_proxy > 0.0 and avg_turnover_proxy <= 0.6 and avg_total_return > 0.0 and gate_1_score >= (gate_1_threshold + 0.15):
            adjustments["efficient_turnover_bonus"] = adjustments.get("efficient_turnover_bonus", 0.0) + 3.0
        if min_target_sample_count > 0 and sampled_target_count < min_target_sample_count:
            adjustments["target_sample_penalty"] = adjustments.get("target_sample_penalty", 0.0) - 8.0
        if (
            target_layer_stability is not None
            and min_target_layer_stability > 0.0
            and target_layer_stability < min_target_layer_stability
        ):
            adjustments["target_layer_stability_penalty"] = adjustments.get("target_layer_stability_penalty", 0.0) - 6.0
        if pipeline_staged_ma_cross:
            if avg_turnover_proxy >= _PIPELINE_MA_CROSS_VERY_HIGH_TURNOVER_THRESHOLD:
                adjustments["pipeline_ma_cross_turnover_penalty"] = adjustments.get("pipeline_ma_cross_turnover_penalty", 0.0) - 18.0
            elif avg_turnover_proxy >= _PIPELINE_MA_CROSS_HIGH_TURNOVER_THRESHOLD:
                adjustments["pipeline_ma_cross_turnover_penalty"] = adjustments.get("pipeline_ma_cross_turnover_penalty", 0.0) - 12.0
            elif avg_turnover_proxy >= _SNAPSHOT_HIGH_TURNOVER_THRESHOLD:
                adjustments["pipeline_ma_cross_turnover_penalty"] = adjustments.get("pipeline_ma_cross_turnover_penalty", 0.0) - 6.0
            if avg_total_return <= 0.0:
                adjustments["pipeline_ma_cross_edge_penalty"] = adjustments.get("pipeline_ma_cross_edge_penalty", 0.0) - 5.0
            elif avg_total_return < _PIPELINE_MA_CROSS_EDGE_RETURN_FLOOR:
                adjustments["pipeline_ma_cross_edge_penalty"] = adjustments.get("pipeline_ma_cross_edge_penalty", 0.0) - 3.0
            if avg_turnover_proxy >= _PIPELINE_MA_CROSS_HIGH_TURNOVER_THRESHOLD and gate_1_score < (gate_1_threshold + 0.45):
                adjustments["pipeline_ma_cross_fragility_penalty"] = adjustments.get("pipeline_ma_cross_fragility_penalty", 0.0) - 4.0
        if rl_bandit_momentum:
            if coverage_ratio is not None:
                if coverage_ratio < _RL_BANDIT_ALIGNMENT_SOFT_COVERAGE:
                    adjustments["rl_bandit_coverage_penalty"] = adjustments.get("rl_bandit_coverage_penalty", 0.0) - 6.0
                if coverage_ratio < _RL_BANDIT_ALIGNMENT_HARD_BLOCK_COVERAGE:
                    adjustments["rl_bandit_coverage_penalty"] = adjustments.get("rl_bandit_coverage_penalty", 0.0) - 4.0
            if intersection_ratio is not None:
                if intersection_ratio < _RL_BANDIT_ALIGNMENT_SOFT_INTERSECTION:
                    adjustments["rl_bandit_intersection_penalty"] = adjustments.get("rl_bandit_intersection_penalty", 0.0) - 5.0
                if intersection_ratio < _RL_BANDIT_ALIGNMENT_HARD_BLOCK_INTERSECTION:
                    adjustments["rl_bandit_intersection_penalty"] = adjustments.get("rl_bandit_intersection_penalty", 0.0) - 4.0
            if target_count > 10:
                adjustments["rl_bandit_basket_penalty"] = adjustments.get("rl_bandit_basket_penalty", 0.0) - 2.5

    return {
        "score_delta": round(sum(adjustments.values()), 4),
        "adjustments": {key: round(value, 4) for key, value in adjustments.items()},
        "coverage_ratio": None if coverage_ratio is None else round(coverage_ratio, 4),
        "intersection_ratio": None if intersection_ratio is None else round(intersection_ratio, 4),
        "avg_turnover_proxy": round(avg_turnover_proxy, 4),
        "avg_total_return": round(avg_total_return, 6),
        "target_quality_summary": dict(target_quality_summary),
        "targeted_snapshot": targeted_snapshot,
    }


def _gate_2_disallow_same_group_fill(candidate: dict) -> bool:
    payload = dict(candidate or {})
    research_task = _normalize_research_task_contract(payload.get("research_task") or {})
    if not _is_targeted_snapshot_candidate(payload, research_task):
        return False
    return _is_rl_bandit_momentum_candidate(payload, research_task)


def _post_gate_1_target_quality_block_reason(candidate: dict, gate_1_score: float) -> Optional[str]:
    payload = dict(candidate or {})
    research_task = _normalize_research_task_contract(payload.get("research_task") or {})
    target_codes = _extract_target_codes_from_payload(payload, limit=12)
    target_count = len(target_codes)
    if target_count <= 1:
        return None

    tags = _candidate_tags(payload)
    validation_focus = str(research_task.get("validation_focus") or "").strip().lower()
    if not _is_targeted_snapshot_candidate(
        payload,
        research_task,
        tags=tags,
        target_count=target_count,
        validation_focus=validation_focus,
    ):
        return None

    gate_1_metrics = dict((payload.get("gate_1_result") or {}).get("metrics") or {})
    constraint_check = _candidate_constraint_check(payload)
    coverage_ratio_raw = constraint_check.get("coverage_ratio")
    intersection_ratio_raw = constraint_check.get("intersection_ratio")
    coverage_ratio = None if coverage_ratio_raw is None else _safe_float(coverage_ratio_raw, 0.0)
    intersection_ratio = None if intersection_ratio_raw is None else _safe_float(intersection_ratio_raw, 0.0)
    avg_turnover_proxy = _safe_float(gate_1_metrics.get("avg_turnover_proxy"), 0.0)
    avg_total_return = _safe_float(gate_1_metrics.get("avg_total_return"), 0.0)
    gate_1_threshold = float(_compat_setting("GATE1_SHARPE_MIN", GATE1_SHARPE_MIN) or GATE1_SHARPE_MIN)
    target_quality_summary = build_target_quality_gate_summary(payload, gate_1_metrics=gate_1_metrics)
    target_quality_reasons = list(target_quality_summary.get("reasons") or [])

    for reason in target_quality_reasons:
        if reason in {
            "target_universe_alignment_too_low",
            "target_sample_sufficiency_too_low",
            "target_layer_stability_too_low",
        }:
            return reason

    if _is_pipeline_staged_ma_cross_candidate(payload, research_task):
        if (
            avg_turnover_proxy >= _PIPELINE_MA_CROSS_VERY_HIGH_TURNOVER_THRESHOLD
            and gate_1_score < (gate_1_threshold + 0.75)
        ):
            return "snapshot_turnover_fragility_too_high"
        if (
            avg_turnover_proxy >= _PIPELINE_MA_CROSS_HIGH_TURNOVER_THRESHOLD
            and target_count >= 4
            and (
                gate_1_score < (gate_1_threshold + 0.55)
                or avg_total_return <= _PIPELINE_MA_CROSS_EDGE_RETURN_FLOOR
            )
        ):
            return "snapshot_turnover_fragility_too_high"

    if (
        _is_pipeline_staged_rsi_candidate(payload, research_task)
        and target_count >= 6
        and intersection_ratio is not None
        and intersection_ratio < _PIPELINE_RSI_ALIGNMENT_HARD_BLOCK_INTERSECTION
    ):
        return "target_universe_alignment_too_low"

    if _is_rl_bandit_momentum_candidate(payload, research_task):
        if (
            coverage_ratio is not None
            and coverage_ratio < _RL_BANDIT_ALIGNMENT_HARD_BLOCK_COVERAGE
            and intersection_ratio is not None
            and intersection_ratio < _RL_BANDIT_ALIGNMENT_HARD_BLOCK_INTERSECTION
        ):
            return "target_universe_alignment_too_low"
        if (
            target_count > 8
            and intersection_ratio is not None
            and intersection_ratio < _RL_BANDIT_ALIGNMENT_SOFT_INTERSECTION
        ):
            return "target_universe_alignment_too_low"

    return None


def _gate_2_priority_score(candidate: dict, gate_1_score: float, *, return_meta: bool = False):
    payload = dict(candidate or {})
    research_task = _normalize_research_task_contract(payload.get("research_task") or {})
    target_codes = _extract_target_codes_from_payload(payload, limit=12)
    target_count = len(target_codes)
    task_source = str(
        research_task.get("task_source")
        or payload.get("task_source")
        or payload.get("generator_mode")
        or ""
    ).strip().lower()
    validation_focus = str(research_task.get("validation_focus") or "").strip().lower()
    tags = {
        str(tag).strip().lower()
        for tag in list(payload.get("tags") or [])
        if str(tag).strip()
    }
    priority = _safe_float(payload.get("priority") or research_task.get("priority"))
    matrix_priority = _safe_float(
        payload.get("matrix_priority_score")
        or research_task.get("matrix_priority_score")
    )
    stock_family_priority = _safe_float(
        payload.get("stock_family_priority")
        or research_task.get("stock_family_priority")
    )
    base_score = _safe_float(gate_1_score) * 100.0
    priority_bonus = priority * 0.35
    matrix_bonus = matrix_priority * 0.25
    family_bonus = stock_family_priority * 25.0
    target_bonus = min(target_count, 8) * 0.9
    score = base_score + priority_bonus + matrix_bonus + family_bonus + target_bonus
    if target_count > 0:
        score += 4.0
    if "targeted_universe" in tags:
        score += 3.0
    if validation_focus in {"candidate_target_only", "event_target_only"}:
        score += 4.0
    if task_source in {"snapshot", "event_driven", "bulk_stock_matrix"} and target_count > 0:
        score += 2.0
    if not target_count and not research_task:
        score -= 12.0
    if _is_bulk_stock_matrix_candidate(payload):
        score += 8.0
    if str(research_task.get("candidate_family") or payload.get("candidate_family") or "").strip():
        score += 2.0
    quality_meta = _gate_2_priority_adjustments(payload, research_task, _safe_float(gate_1_score))
    score += _safe_float(quality_meta.get("score_delta"), 0.0)
    final_score = round(score, 4)
    if return_meta:
        return final_score, {
            "base_score": round(base_score, 4),
            "priority_bonus": round(priority_bonus, 4),
            "matrix_bonus": round(matrix_bonus, 4),
            "family_bonus": round(family_bonus, 4),
            "target_count_bonus": round(target_bonus, 4),
            **quality_meta,
        }
    return final_score


def _select_gate_2_candidates(
    gate_1_scored: list[tuple[dict, float]],
    top_k: int,
    *,
    per_group_cap: int = 2,
) -> list[dict]:
    if top_k <= 0 or not gate_1_scored:
        return []

    selected: list[dict] = []
    selected_groups: dict[str, int] = {}
    selected_ids: set[int] = set()
    selected_signatures: set[str] = set()

    def try_select(candidate: dict, *, require_new_group: bool, enforce_cap: bool) -> bool:
        group_key = _gate_2_group_key(candidate)
        current = int(selected_groups.get(group_key) or 0)
        if require_new_group and current > 0:
            return False
        if current > 0 and _gate_2_disallow_same_group_fill(candidate):
            return False
        if enforce_cap and current >= max(1, per_group_cap):
            return False
        marker = id(candidate)
        if marker in selected_ids:
            return False
        selection_signature = _gate_2_selection_signature(candidate)
        if selection_signature in selected_signatures:
            return False
        selected.append(candidate)
        selected_ids.add(marker)
        selected_signatures.add(selection_signature)
        selected_groups[group_key] = current + 1
        return True

    for candidate, _score in gate_1_scored:
        if len(selected) >= top_k:
            break
        try_select(candidate, require_new_group=True, enforce_cap=True)

    for candidate, _score in gate_1_scored:
        if len(selected) >= top_k:
            break
        try_select(candidate, require_new_group=False, enforce_cap=True)

    for candidate, _score in gate_1_scored:
        if len(selected) >= top_k:
            break
        try_select(candidate, require_new_group=False, enforce_cap=False)

    return selected[:top_k]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    """单个门禁的结果。"""
    passed: bool
    gate: str
    reasons: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _per_stock_quota_increment(candidate: dict, research_task: dict, target_codes: list[str]) -> float:
    count = len(list(target_codes or []))
    if count <= 1:
        return 1.0

    task_source = str(research_task.get("task_source") or "").strip().lower()
    validation_focus = str(research_task.get("validation_focus") or "").strip().lower()
    if task_source == "bulk_stock_matrix":
        return 1.0
    if validation_focus in {"candidate_target_only", "event_target_only"}:
        return 0.5 if count >= 4 else 0.75
    if count >= 4:
        return 0.5
    if count >= 3:
        return 0.65
    return 0.8


def _resolve_gate_2_top_k(total_passed: int, pass_ratio: float) -> int:
    if total_passed <= 0:
        return 0
    scaled = float(total_passed) * max(0.0, float(pass_ratio or 0.0))
    return max(1, min(int(total_passed), int(round(scaled))))


def _collect_symbol_summaries(candidate: dict, research_task: dict) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for source in (candidate, research_task, dict(research_task.get("stock_pool") or {})):
        if not isinstance(source, dict):
            continue
        for key in (
            "source_symbol_summary",
            "target_symbol_summary",
            "source_symbol_summaries",
            "target_symbol_summaries",
            "symbol_summaries",
        ):
            payload = source.get(key)
            if isinstance(payload, dict):
                summaries.append(dict(payload))
            elif isinstance(payload, list):
                summaries.extend(dict(item) for item in payload if isinstance(item, dict))
    return summaries


def _resolve_liquidity_requirement(candidate: dict, research_task: dict, target_codes: list[str]) -> str:
    explicit = str(
        candidate.get("liquidity_requirement")
        or research_task.get("liquidity_requirement")
        or candidate.get("market_liquidity_requirement")
        or ""
    ).strip().lower()
    if explicit in {"high", "medium", "low", "all"}:
        return explicit
    return "medium" if len(target_codes) <= 1 else "low"


def _estimate_liquidity_proxy(candidate: dict, research_task: dict, target_codes: list[str]) -> dict[str, Any]:
    summaries = _collect_symbol_summaries(candidate, research_task)
    if not summaries:
        return {"available": False, "proxy_kind": None, "proxy_value": None}

    target_set = {str(code).strip() for code in list(target_codes or []) if str(code).strip()}
    matched = [
        summary
        for summary in summaries
        if not target_set
        or not str(summary.get("code") or summary.get("symbol") or summary.get("stock_code") or "").strip()
        or str(summary.get("code") or summary.get("symbol") or summary.get("stock_code") or "").strip() in target_set
    ]
    if not matched:
        matched = summaries

    turnover_values = []
    for summary in matched:
        for field in ("avg_daily_turnover", "daily_turnover", "avg_turnover", "turnover", "amount"):
            value = _safe_float(summary.get(field), 0.0)
            if value > 0:
                turnover_values.append(value)
                break
    if turnover_values:
        return {
            "available": True,
            "proxy_kind": "avg_daily_turnover",
            "proxy_value": min(turnover_values),
        }

    market_caps = [_safe_float(summary.get("market_cap"), 0.0) for summary in matched]
    market_caps = [value for value in market_caps if value > 0]
    if market_caps:
        return {
            "available": True,
            "proxy_kind": "market_cap",
            "proxy_value": min(market_caps),
        }

    return {"available": False, "proxy_kind": None, "proxy_value": None}
