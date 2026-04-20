

async def refresh_factory_run_summary_quality_contract(db, row: Optional[dict]) -> dict:
    detail = await refresh_factory_run_detail_quality_contract(db, row)
    if not detail:
        return {}
    summary = normalize_factory_run_summary_contract(detail)
    submission_artifact = dict(detail.get("submission_artifact") or summary.get("submission_artifact") or {})
    summary["submission_artifact"] = submission_artifact
    for field in _FACTORY_SUMMARY_OBSERVABILITY_FIELDS:
        value = detail.get(field)
        if value in (None, "", [], {}):
            continue
        summary[field] = deepcopy(value)
    summary["summary"] = merge_factory_run_summary_observability(
        summary.get("summary") or {},
        detail,
    )
    return summary


# list_quality_reports, get_latest_quality_report imported from strategy_lifecycle_shared


# ── Incubation overview builder (imported from strategy_lifecycle_shared) ────


# ── Backward-compatible aliases (underscore-prefixed names) ──────────────────
# External services import these via ``from ..tools.managers.strategy_manager import _xxx``.
# The main strategy_manager.py re-exports them, but we also define them here so that
# the helpers module itself is self-contained for direct imports.

_compute_nav_series = compute_nav_series
_normalize_status_alias = normalize_status_alias
_validate_transition = validate_transition
_update_status = update_status
_save_quality_report = save_quality_report
_metric_bucket_value = metric_bucket_value
_normalize_time_filter = normalize_time_filter
_parse_bool = parse_bool
_quality_gate_reason_code = quality_gate_reason_code
_normalize_quality_gate_result = normalize_quality_gate_result
_is_factory_ai_prototype_strategy = is_factory_ai_prototype_strategy
_has_only_statistical_gate_failures = has_only_statistical_gate_failures
_safe_metric_value = safe_metric_value
_maybe_grant_provisional_incubation = maybe_grant_provisional_incubation
_build_quality_report = build_quality_report
_list_quality_reports = list_quality_reports
_get_latest_quality_report = get_latest_quality_report
_build_incubation_overview = build_incubation_overview
