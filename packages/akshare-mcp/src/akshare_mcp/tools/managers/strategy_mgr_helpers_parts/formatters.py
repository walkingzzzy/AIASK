

async def build_factory_quality_baseline(
    db,
    *,
    latest_run: Optional[dict] = None,
    limit_per_status: int = 200,
) -> dict:
    captured_at = datetime.now(timezone.utc).isoformat()
    latest_run_summary = normalize_factory_run_summary_contract(latest_run or {})
    latest_run_submission_artifact = dict(latest_run_summary.get("submission_artifact") or {})
    latest_run_strategy_briefs = [
        dict(item or {})
        for item in list(latest_run_submission_artifact.get("strategy_briefs") or [])
        if isinstance(item, dict)
    ]
    latest_run_generation_lane_panel, latest_run_generation_mode_counts = (
        _build_generation_lane_quality_panel(latest_run_strategy_briefs)
    )
    latest_run_high_confidence = _summarize_high_confidence_quality(
        latest_run_strategy_briefs
    )
    latest_run_payload = {
        "run_id": str(latest_run_summary.get("run_id") or "").strip() or None,
        "status": str(latest_run_summary.get("status") or "").strip() or None,
        "started_at": latest_run_summary.get("started_at"),
        "completed_at": latest_run_summary.get("completed_at"),
        "candidates_spawned": int(latest_run_summary.get("candidates_spawned") or 0),
        "submitted": int(latest_run_summary.get("submitted") or 0),
        "research_only_count": int(latest_run_summary.get("research_only_count") or 0),
        "deferred_submission_count": int(latest_run_summary.get("deferred_submission_count") or 0),
        "validation_grade_distribution": dict(latest_run_summary.get("validation_grade_distribution") or {}),
        "raw_validation_grade_distribution": dict(
            latest_run_summary.get("raw_validation_grade_distribution")
            or latest_run_summary.get("validation_grade_distribution")
            or {}
        ),
        "effective_validation_grade_distribution": dict(
            latest_run_summary.get("effective_validation_grade_distribution")
            or latest_run_summary.get("validation_grade_distribution")
            or {}
        ),
        "raw_validation_total_score_mean": _safe_float(
            latest_run_summary.get("raw_validation_total_score_mean"),
            0.0,
        ),
        "raw_validation_total_score_p50": _safe_float(
            latest_run_summary.get("raw_validation_total_score_p50"),
            0.0,
        ),
        "raw_validation_total_score_p90": _safe_float(
            latest_run_summary.get("raw_validation_total_score_p90"),
            0.0,
        ),
        "raw_validation_a_rate": _safe_float(latest_run_summary.get("raw_validation_a_rate"), 0.0),
        "raw_validation_b_rate": _safe_float(latest_run_summary.get("raw_validation_b_rate"), 0.0),
        "raw_validation_c_rate": _safe_float(latest_run_summary.get("raw_validation_c_rate"), 0.0),
        "raw_validation_d_rate": _safe_float(latest_run_summary.get("raw_validation_d_rate"), 0.0),
        "strict_incubation_ready_count": int(
            latest_run_summary.get("strict_incubation_ready_count") or 0
        ),
        "strict_incubation_ready_rate": _safe_float(
            latest_run_summary.get("strict_incubation_ready_rate"),
            0.0,
        ),
        "live_candidate_ready_count": int(
            latest_run_summary.get("live_candidate_ready_count") or 0
        ),
        "live_candidate_ready_rate": _safe_float(
            latest_run_summary.get("live_candidate_ready_rate"),
            0.0,
        ),
        "raw_b_or_above_count": int(latest_run_summary.get("raw_b_or_above_count") or 0),
        "raw_b_or_above_rate": _safe_float(latest_run_summary.get("raw_b_or_above_rate"), 0.0),
        "strict_ready_given_raw_b_count": int(
            latest_run_summary.get("strict_ready_given_raw_b_count") or 0
        ),
        "strict_ready_given_raw_b_rate": _safe_float(
            latest_run_summary.get("strict_ready_given_raw_b_rate"),
            0.0,
        ),
        "live_ready_given_raw_b_count": int(
            latest_run_summary.get("live_ready_given_raw_b_count") or 0
        ),
        "live_ready_given_raw_b_rate": _safe_float(
            latest_run_summary.get("live_ready_given_raw_b_rate"),
            0.0,
        ),
        "validation_family_quality_panel": list(
            latest_run_summary.get("validation_family_quality_panel") or []
        ),
        "prediction_quality_distribution": dict(
            latest_run_summary.get("prediction_quality_distribution")
            or latest_run_high_confidence.get("prediction_quality_distribution")
            or {}
        ),
        "execution_quality_distribution": dict(
            latest_run_summary.get("execution_quality_distribution")
            or latest_run_high_confidence.get("execution_quality_distribution")
            or {}
        ),
        "evidence_alignment_distribution": dict(
            latest_run_summary.get("evidence_alignment_distribution")
            or latest_run_high_confidence.get("evidence_alignment_distribution")
            or {}
        ),
        "confidence_contract_ready_rate": _safe_float(
            latest_run_summary.get("confidence_contract_ready_rate"),
            latest_run_high_confidence.get("confidence_contract_ready_rate") or 0.0,
        ),
        "generation_lane_definition": _FACTORY_GENERATION_LANE_DEFINITION,
        "generation_lane_quality_panel": latest_run_generation_lane_panel,
        "generation_mode_counts": latest_run_generation_mode_counts,
        "external_llm_provider_health_status": latest_run_summary.get("external_llm_provider_health_status"),
        "external_llm_provider_control_mode": latest_run_summary.get("external_llm_provider_control_mode"),
    }

    if not hasattr(db, "list_strategies"):
        return {
            "contract_version": "strategy_factory.quality_baseline.v1",
            "captured_at": captured_at,
            "latest_run": latest_run_payload,
            "submitted_strategy_cohort": {
                "statuses": ["submitted", "incubating", "listed"],
                "factory_strategy_count": 0,
                "status_counts": {},
                "validation_grade_distribution": {},
                "raw_validation_grade_distribution": {},
                "effective_validation_grade_distribution": {},
                "raw_validation_total_score_mean": 0.0,
                "raw_validation_total_score_p50": 0.0,
                "raw_validation_total_score_p90": 0.0,
                "raw_validation_a_rate": 0.0,
                "raw_validation_b_rate": 0.0,
                "raw_validation_c_rate": 0.0,
                "raw_validation_d_rate": 0.0,
                "zero_signal_count": 0,
                "zero_signal_rate": 0.0,
                "forward_coverage_count": 0,
                "forward_coverage_rate": 0.0,
                "promotion_ready_count": 0,
                "promotion_ready_rate": 0.0,
                "quality_passed_count": 0,
                "quality_pass_rate": 0.0,
                "baseline_forward_days": list(_FACTORY_BASELINE_FORWARD_DAYS),
                "quality_report_missing_count": 0,
                "zero_signal_definition": "raw_signal_count <= 0",
                "forward_coverage_definition": "observed all baseline forward days",
                "strict_incubation_ready_count": 0,
                "strict_incubation_ready_rate": 0.0,
                "live_candidate_ready_count": 0,
                "live_candidate_ready_rate": 0.0,
                "live_gate_ready_count": 0,
                "live_gate_ready_rate": 0.0,
                "raw_b_or_above_count": 0,
                "raw_b_or_above_rate": 0.0,
                "strict_ready_given_raw_b_count": 0,
                "strict_ready_given_raw_b_rate": 0.0,
                "live_ready_given_raw_b_count": 0,
                "live_ready_given_raw_b_rate": 0.0,
                "strict_live_alignment_gap_count": 0,
                "strict_live_alignment_gap_rate": 0.0,
                "strict_live_alignment_status_counts": {},
                "validation_grade_d_strict_incubation_pass_count": 0,
                "validation_grade_d_strict_incubation_pass_rate": 0.0,
                "validation_grade_d_promotion_ready_count": 0,
                "validation_grade_d_promotion_ready_rate": 0.0,
                "validation_family_quality_panel": [],
                "prediction_quality_distribution": {},
                "execution_quality_distribution": {},
                "evidence_alignment_distribution": {},
                "confidence_contract_ready_rate": 0.0,
                "generation_lane_definition": _FACTORY_GENERATION_LANE_DEFINITION,
                "generation_lane_quality_panel": [],
                "generation_mode_counts": {},
            },
        }

    cohort_statuses = ("submitted", "incubating", "listed")
    listed_rows, incubating_rows, submitted_rows = await asyncio.gather(
        db.list_strategies("listed", limit=limit_per_status),
        db.list_strategies("incubating", limit=limit_per_status),
        db.list_strategies("submitted", limit=limit_per_status),
    )
    strategies_by_id: dict[str, dict] = {}
    status_counts: dict[str, int] = {}
    for row in [*submitted_rows, *incubating_rows, *listed_rows]:
        strategy = dict(row or {})
        strategy_id = str(strategy.get("id") or "").strip()
        if not strategy_id or not is_factory_generated_strategy(strategy):
            continue
        strategies_by_id[strategy_id] = strategy
        status_key = normalize_status_alias(strategy.get("status"))
        status_counts[status_key] = status_counts.get(status_key, 0) + 1

    cohort = list(strategies_by_id.values())
    overviews = await asyncio.gather(
        *(build_incubation_overview(db, strategy) for strategy in cohort),
        return_exceptions=True,
    )
    validation_grade_distribution: dict[str, int] = {}
    raw_validation_grade_distribution: dict[str, int] = {}
    effective_validation_grade_distribution: dict[str, int] = {}
    raw_validation_total_scores: list[float] = []
    zero_signal_count = 0
    forward_coverage_count = 0
    promotion_ready_count = 0
    quality_passed_count = 0
    quality_report_missing_count = 0
    strict_incubation_ready_count = 0
    live_gate_ready_count = 0
    raw_b_or_above_count = 0
    strict_ready_given_raw_b_count = 0
    live_ready_given_raw_b_count = 0
    strict_live_alignment_gap_count = 0
    strict_live_alignment_status_counts: dict[str, int] = {}
    validation_grade_d_strict_incubation_pass_count = 0
    validation_grade_d_promotion_ready_count = 0
    processed_count = 0
    cohort_records: list[dict[str, Any]] = []

    for strategy, overview in zip(cohort, overviews):
        if isinstance(overview, Exception):
            logger.warning("factory quality baseline skipped strategy due to overview error: %s", overview)
            continue
        cohort_records.append(
            {
                **dict(strategy or {}),
                **dict(overview or {}),
                "params": dict(strategy.get("params") or {}),
                "tags": list(strategy.get("tags") or []),
            }
        )
        processed_count += 1
        validation_grade = str(overview.get("validation_grade") or "UNKNOWN").strip().upper()
        raw_validation_grade = str(
            overview.get("raw_validation_grade") or validation_grade or "UNKNOWN"
        ).strip().upper()
        effective_validation_grade = str(
            overview.get("effective_validation_grade") or validation_grade or "UNKNOWN"
        ).strip().upper()
        validation_grade_distribution[validation_grade] = (
            validation_grade_distribution.get(validation_grade, 0) + 1
        )
        raw_validation_grade_distribution[raw_validation_grade] = (
            raw_validation_grade_distribution.get(raw_validation_grade, 0) + 1
        )
        effective_validation_grade_distribution[effective_validation_grade] = (
            effective_validation_grade_distribution.get(effective_validation_grade, 0) + 1
        )
        if overview.get("raw_validation_total_score") is not None:
            raw_validation_total_scores.append(_safe_float(overview.get("raw_validation_total_score")))
        raw_signal_count = int(overview.get("raw_signal_count") or overview.get("total_signals") or 0)
        if raw_signal_count <= 0:
            zero_signal_count += 1
        observed_forward_days = {
            int(item)
            for item in list(overview.get("observed_forward_days") or [])
            if str(item).strip()
        }
        if set(_FACTORY_BASELINE_FORWARD_DAYS).issubset(observed_forward_days):
            forward_coverage_count += 1
        if overview.get("promotion_ready"):
            promotion_ready_count += 1
        if overview.get("quality_passed"):
            quality_passed_count += 1
        strict_ready = overview.get("strict_incubation_ready") is True
        live_ready = overview.get("live_candidate_ready") is True
        if strict_ready:
            strict_incubation_ready_count += 1
        if live_ready:
            live_gate_ready_count += 1
        if raw_validation_grade in {"A", "B"}:
            raw_b_or_above_count += 1
            if strict_ready:
                strict_ready_given_raw_b_count += 1
            if live_ready:
                live_ready_given_raw_b_count += 1
        if overview.get("strict_live_alignment_gap"):
            strict_live_alignment_gap_count += 1
        alignment_status = str(overview.get("strict_live_alignment_status") or "").strip().lower()
        if alignment_status:
            strict_live_alignment_status_counts[alignment_status] = (
                strict_live_alignment_status_counts.get(alignment_status, 0) + 1
            )
        if raw_validation_grade == "D" and overview.get("strict_incubation_ready") is True:
            validation_grade_d_strict_incubation_pass_count += 1
        if raw_validation_grade == "D" and overview.get("promotion_ready"):
            validation_grade_d_promotion_ready_count += 1
        if validation_grade == "UNKNOWN":
            quality_report_missing_count += 1

    denominator = max(processed_count, 1)
    family_quality_panel = _build_family_quality_panel(cohort_records)
    generation_lane_quality_panel, generation_mode_counts = _build_generation_lane_quality_panel(
        cohort_records
    )
    cohort_high_confidence = _summarize_high_confidence_quality(cohort_records)
    return {
        "contract_version": "strategy_factory.quality_baseline.v1",
        "captured_at": captured_at,
        "latest_run": latest_run_payload,
        "submitted_strategy_cohort": {
            "statuses": list(cohort_statuses),
            "factory_strategy_count": processed_count,
            "status_counts": status_counts,
            "validation_grade_distribution": validation_grade_distribution,
            "raw_validation_grade_distribution": raw_validation_grade_distribution,
            "effective_validation_grade_distribution": effective_validation_grade_distribution,
            "raw_validation_total_score_mean": round(
                sum(raw_validation_total_scores) / len(raw_validation_total_scores),
                4,
            ) if raw_validation_total_scores else 0.0,
            "raw_validation_total_score_p50": _percentile(raw_validation_total_scores, 0.5),
            "raw_validation_total_score_p90": _percentile(raw_validation_total_scores, 0.9),
            **_grade_rates(raw_validation_grade_distribution, processed_count),
            "zero_signal_count": zero_signal_count,
            "zero_signal_rate": round(zero_signal_count / denominator, 4) if processed_count else 0.0,
            "forward_coverage_count": forward_coverage_count,
            "forward_coverage_rate": round(forward_coverage_count / denominator, 4) if processed_count else 0.0,
            "promotion_ready_count": promotion_ready_count,
            "promotion_ready_rate": round(promotion_ready_count / denominator, 4) if processed_count else 0.0,
            "quality_passed_count": quality_passed_count,
            "quality_pass_rate": round(quality_passed_count / denominator, 4) if processed_count else 0.0,
            "strict_incubation_ready_count": strict_incubation_ready_count,
            "strict_incubation_ready_rate": round(strict_incubation_ready_count / denominator, 4) if processed_count else 0.0,
            "live_candidate_ready_count": live_gate_ready_count,
            "live_candidate_ready_rate": round(live_gate_ready_count / denominator, 4) if processed_count else 0.0,
            "live_gate_ready_count": live_gate_ready_count,
            "live_gate_ready_rate": round(live_gate_ready_count / denominator, 4) if processed_count else 0.0,
            "raw_b_or_above_count": raw_b_or_above_count,
            "raw_b_or_above_rate": round(raw_b_or_above_count / denominator, 4) if processed_count else 0.0,
            "strict_ready_given_raw_b_count": strict_ready_given_raw_b_count,
            "strict_ready_given_raw_b_rate": _rate(
                strict_ready_given_raw_b_count,
                raw_b_or_above_count,
            ),
            "live_ready_given_raw_b_count": live_ready_given_raw_b_count,
            "live_ready_given_raw_b_rate": _rate(
                live_ready_given_raw_b_count,
                raw_b_or_above_count,
            ),
            "strict_live_alignment_gap_count": strict_live_alignment_gap_count,
            "strict_live_alignment_gap_rate": round(strict_live_alignment_gap_count / denominator, 4) if processed_count else 0.0,
            "strict_live_alignment_status_counts": strict_live_alignment_status_counts,
            "validation_grade_d_strict_incubation_pass_count": validation_grade_d_strict_incubation_pass_count,
            "validation_grade_d_strict_incubation_pass_rate": round(
                validation_grade_d_strict_incubation_pass_count / denominator,
                4,
            ) if processed_count else 0.0,
            "validation_grade_d_promotion_ready_count": validation_grade_d_promotion_ready_count,
            "validation_grade_d_promotion_ready_rate": round(
                validation_grade_d_promotion_ready_count / denominator,
                4,
            ) if processed_count else 0.0,
            "validation_family_quality_panel": family_quality_panel,
            "prediction_quality_distribution": dict(
                cohort_high_confidence.get("prediction_quality_distribution") or {}
            ),
            "execution_quality_distribution": dict(
                cohort_high_confidence.get("execution_quality_distribution") or {}
            ),
            "evidence_alignment_distribution": dict(
                cohort_high_confidence.get("evidence_alignment_distribution") or {}
            ),
            "confidence_contract_ready_rate": _safe_float(
                cohort_high_confidence.get("confidence_contract_ready_rate"),
                0.0,
            ),
            "generation_lane_definition": _FACTORY_GENERATION_LANE_DEFINITION,
            "generation_lane_quality_panel": generation_lane_quality_panel,
            "generation_mode_counts": generation_mode_counts,
            "baseline_forward_days": list(_FACTORY_BASELINE_FORWARD_DAYS),
            "quality_report_missing_count": quality_report_missing_count,
            "zero_signal_definition": "raw_signal_count <= 0",
            "forward_coverage_definition": "observed all baseline forward days",
        },
    }


# metric_bucket_value imported from strategy_lifecycle_shared


def normalize_time_filter(value: Any, *, is_end: bool = False) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 10:
        dt = datetime.fromisoformat(text)
        if is_end:
            dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    return default


def quality_gate_reason_code(reason: str) -> str:
    return _shared_quality_gate_reason_code(reason)


def normalize_quality_gate_result(result: Optional[dict]) -> dict:
    return _shared_normalize_quality_gate_result(result)


def is_factory_ai_prototype_strategy(strategy: Optional[dict]) -> bool:
    payload = dict(strategy or {})
    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    tags = {str(tag).strip().lower() for tag in list(payload.get("tags") or [])}
    if "factory" not in tags and "auto_generated" not in tags:
        return False
    if "external_llm" in tags or "ai_generated" in tags:
        return True
    return strategy_type == "dsl_rule"


def has_only_statistical_gate_failures(gate_result: Optional[dict]) -> bool:
    gate = normalize_quality_gate_result(gate_result)
    codes = list(gate.get("reason_codes") or [])
    if not codes:
        return False
    allowed_prefixes = (
        "walk_forward_ic_ir",
        "purged_k_fold_ic",
        "bootstrap_ci_lower",
        "parameter_sensitivity",
        "multi_period_ic",
    )
    return all(any(str(code).startswith(prefix) for prefix in allowed_prefixes) for code in codes)


def safe_metric_value(payload: Optional[dict], *keys: str) -> float:
    data = dict(payload or {})
    for key in keys:
        if key in data and data.get(key) is not None:
            try:
                return float(data.get(key) or 0.0)
            except Exception:
                return 0.0
    return 0.0


def _count_statistical_checks_passed(gate: dict) -> tuple[int, list[str], list[str]]:
    """统计质量门 5 项统计检查中通过了几项，返回 (通过数, 通过项列表, 失败项列表)。"""
    check_map = {
        "walk_forward_ic_ir": ("wf_ic_ir", QUALITY_GATE_THRESHOLDS["walk_forward_ic_ir_min"], ">="),
        "purged_kfold_ic": ("pkf_ic", QUALITY_GATE_THRESHOLDS["purged_kfold_ic_min"], ">="),
        "bootstrap_ci_lower": ("bootstrap_ci_lower", QUALITY_GATE_THRESHOLDS["bootstrap_ci_lower_min"], ">="),
        "param_sensitivity": ("param_sensitivity", QUALITY_GATE_THRESHOLDS["param_sensitivity_max"], "<="),
    }
    passed_checks: list[str] = []
    failed_checks: list[str] = []
    for check_name, (key, threshold, op) in check_map.items():
        value = gate.get(key)
        if value is None:
            failed_checks.append(check_name)
            continue
        try:
            val = float(value)
        except (TypeError, ValueError):
            failed_checks.append(check_name)
            continue
        if op == ">=" and val >= threshold:
            passed_checks.append(check_name)
        elif op == "<=" and val <= threshold:
            passed_checks.append(check_name)
        else:
            failed_checks.append(check_name)

    # 5th check: multi-period robustness (from period_robustness dict in gate)
    pr = gate.get("period_robustness") or {}
    first_ic = pr.get("first_half_ic")
    second_ic = pr.get("second_half_ic")
    if first_ic is not None and second_ic is not None:
        try:
            f_ic, s_ic = float(first_ic), float(second_ic)
            direction_consistent = not (f_ic > 0.01 and s_ic < -0.01) and not (f_ic < -0.01 and s_ic > 0.01)
            both_non_negative = f_ic >= -0.02 and s_ic >= -0.02
            if both_non_negative and direction_consistent:
                passed_checks.append("multi_period_robustness")
            else:
                failed_checks.append("multi_period_robustness")
        except (TypeError, ValueError):
            failed_checks.append("multi_period_robustness")
    else:
        # Data not available — treat as not checked (don't count as failed)
        pass

    return len(passed_checks), passed_checks, failed_checks


# 临时孵化要求至少通过的统计检查项数（5 项中至少通过 2 项）
PROVISIONAL_MIN_STATISTICAL_CHECKS_PASSED = 2
