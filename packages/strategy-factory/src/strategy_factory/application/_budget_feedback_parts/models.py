

def resolve_task_feedback_metrics(
    snapshot_or_feedback: Any,
    *,
    task: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(task or {})
    family_candidates = extract_feedback_families(payload)
    target_pool_id = derive_target_pool_id(payload)
    holding_bucket = extract_holding_bucket(payload)
    generator_mode = extract_generator_mode(payload)
    if not family_candidates:
        family_candidates = ["unknown"]

    resolved_candidates = [
        resolve_feedback_metrics(
            snapshot_or_feedback,
            family=family,
            target_pool_id=target_pool_id,
            holding_bucket=holding_bucket,
            generator_mode=generator_mode,
        )
        for family in family_candidates
    ]
    resolved_candidates.sort(
        key=lambda item: (
            CONTROL_MODE_SEVERITY.get(normalize_text(item.get("control_mode")), 0),
            -safe_float(item.get("budget_multiplier"), 1.0),
            -safe_float(item.get("priority_adjustment"), 0.0),
            str(item.get("family") or ""),
        ),
        reverse=True,
    )
    selected = dict(resolved_candidates[0] or {})
    selected["family_candidates"] = list(family_candidates)
    selected["holding_bucket"] = selected.get("holding_bucket") or holding_bucket
    selected["family_control_modes"] = {
        str(item.get("family") or "unknown"): str(item.get("control_mode") or "normal")
        for item in resolved_candidates
    }
    return selected


def apply_feedback_controls_to_task(
    task: dict[str, Any] | None,
    snapshot_or_feedback: Any,
) -> dict[str, Any]:
    payload = dict(task or {})
    if not payload:
        return {}

    feedback = resolve_task_feedback_metrics(snapshot_or_feedback, task=payload)
    control_mode = normalize_text(feedback.get("control_mode")) or "normal"
    target_pool_control_mode = normalize_text(feedback.get("target_pool_control_mode")) or "normal"
    holding_bucket_control_mode = normalize_text(feedback.get("holding_bucket_control_mode")) or "normal"
    generator_mode_control_mode = normalize_text(feedback.get("generator_mode_control_mode")) or "normal"

    enriched = {
        **payload,
        "feedback_family": feedback.get("family"),
        "feedback_family_candidates": list(feedback.get("family_candidates") or []),
        "target_pool_id": feedback.get("target_pool_id") or derive_target_pool_id(payload),
        "holding_period_bucket": feedback.get("holding_bucket") or extract_holding_bucket(payload),
        "generator_mode": feedback.get("generator_mode") or extract_generator_mode(payload),
        "feedback_control_mode": control_mode,
        "feedback_legacy_control_mode": normalize_text(feedback.get("legacy_control_mode")) or control_mode,
        "feedback_skill_control_mode": normalize_text(feedback.get("skill_control_mode")) or "normal",
        "feedback_target_pool_control_mode": target_pool_control_mode,
        "feedback_holding_bucket_control_mode": holding_bucket_control_mode,
        "feedback_generator_mode_control_mode": generator_mode_control_mode,
        "feedback_skill_target_pool_control_mode": normalize_text(
            feedback.get("skill_target_pool_control_mode")
        )
        or "normal",
        "feedback_skill_holding_bucket_control_mode": normalize_text(
            feedback.get("skill_holding_bucket_control_mode")
        )
        or "normal",
        "feedback_skill_generator_mode_control_mode": normalize_text(
            feedback.get("skill_generator_mode_control_mode")
        )
        or "normal",
        "feedback_control_reasons": list(feedback.get("control_reasons") or []),
        "feedback_legacy_control_reasons": list(feedback.get("legacy_control_reasons") or []),
        "feedback_skill_control_reasons": list(feedback.get("skill_control_reasons") or []),
        "feedback_cooldown_active": bool(feedback.get("cooldown_active")),
        "feedback_suppressed": bool(feedback.get("suppressed")),
        "feedback_family_freeze_active": bool(feedback.get("family_freeze_active")),
        "feedback_target_pool_freeze_active": bool(feedback.get("target_pool_freeze_active")),
        "feedback_holding_bucket_freeze_active": bool(feedback.get("holding_bucket_freeze_active")),
        "feedback_generator_mode_freeze_active": bool(feedback.get("generator_mode_freeze_active")),
        "feedback_skill_cooldown_active": bool(feedback.get("skill_cooldown_active")),
        "feedback_skill_suppressed": bool(feedback.get("skill_suppressed")),
        "feedback_skill_family_freeze_active": bool(feedback.get("skill_family_freeze_active")),
        "feedback_skill_target_pool_freeze_active": bool(
            feedback.get("skill_target_pool_freeze_active")
        ),
        "feedback_skill_holding_bucket_freeze_active": bool(
            feedback.get("skill_holding_bucket_freeze_active")
        ),
        "feedback_skill_generator_mode_freeze_active": bool(
            feedback.get("skill_generator_mode_freeze_active")
        ),
        "feedback_budget_multiplier": safe_float(feedback.get("legacy_budget_multiplier"), 1.0),
        "feedback_priority_adjustment": safe_float(feedback.get("legacy_priority_adjustment")),
        "feedback_failure_penalty_adjustment": safe_float(
            feedback.get("legacy_failure_penalty_adjustment")
        ),
        "feedback_legacy_budget_multiplier": safe_float(
            feedback.get("legacy_budget_multiplier"),
            1.0,
        ),
        "feedback_legacy_priority_adjustment": safe_float(
            feedback.get("legacy_priority_adjustment")
        ),
        "feedback_skill_budget_multiplier": safe_float(
            feedback.get("skill_budget_multiplier"),
            1.0,
        ),
        "feedback_skill_priority_adjustment": safe_float(
            feedback.get("skill_priority_adjustment")
        ),
        "feedback_skill_failure_penalty_adjustment": safe_float(
            feedback.get("skill_failure_penalty_adjustment")
        ),
        "feedback_effective_signal": feedback.get("effective_feedback_signal") or "legacy_paper_hit_ratio",
        "feedback_execution_conversion_efficiency": (
            safe_float(feedback.get("execution_conversion_efficiency"))
            if feedback.get("execution_conversion_efficiency_available")
            else None
        ),
        "feedback_execution_conversion_efficiency_available": bool(
            feedback.get("execution_conversion_efficiency_available")
        ),
        "feedback_budget_action": feedback.get("budget_feedback_action"),
        "feedback_budget_action_applied": bool(feedback.get("budget_action_applied")),
        "feedback_prediction_axis": feedback.get("prediction_axis"),
        "feedback_execution_axis": feedback.get("execution_axis"),
        "feedback_retain_family": bool(feedback.get("retain_family")),
        "feedback_reduce_budget": bool(feedback.get("reduce_budget")),
        "feedback_execution_optimization_queue": bool(
            feedback.get("execution_optimization_queue")
        ),
        "feedback_small_budget_observe": bool(feedback.get("small_budget_observe")),
        "feedback_prioritize_scale": bool(feedback.get("prioritize_scale")),
        "feedback_cool_or_freeze": bool(feedback.get("cool_or_freeze")),
        "feedback_no_expansion": bool(feedback.get("no_expansion")),
        "feedback_metrics": feedback,
    }

    try:
        original_priority = int(enriched.get("priority") or 0)
    except Exception:
        original_priority = 0
    try:
        original_generation_limit = int(enriched.get("generation_limit") or 0)
    except Exception:
        original_generation_limit = 0

    if control_mode == "cooldown":
        adjusted_priority = original_priority + int(round(safe_float(feedback.get("priority_adjustment"), -6.0)))
        enriched["priority"] = max(1, adjusted_priority) if original_priority > 0 else max(1, adjusted_priority)
        if original_generation_limit > 0:
            enriched["generation_limit"] = max(1, min(original_generation_limit, 1))
        enriched["feedback_generation_limited"] = True
    elif control_mode in {"suppress", "freeze"}:
        enriched["feedback_generation_blocked"] = True
        enriched["feedback_generation_block_reason"] = control_mode

    return enriched


def _extract_control_reasons(payload: dict[str, Any] | None) -> list[str]:
    item = dict(payload or {})
    raw_reasons = item.get("feedback_control_reasons")
    if raw_reasons is None:
        raw_reasons = item.get("control_reasons")
    return [
        normalize_text(reason)
        for reason in list(raw_reasons or [])
        if normalize_text(reason)
    ]


def _uses_bulk_matrix_plan(payload: dict[str, Any] | None) -> bool:
    item = dict(payload or {})
    if normalize_text(item.get("task_source")) != "bulk_stock_matrix":
        return False
    for key in (
        "matrix_budget_slot",
        "matrix_plan_slot",
        "matrix_allocation_pass",
        "matrix_family_rank",
        "matrix_stock_rank",
        "matrix_shard_id",
        "matrix_batch_id",
    ):
        try:
            if int(item.get(key) or 0) > 0:
                return True
        except Exception:
            continue
    if safe_float(item.get("stock_family_priority"), 0.0) > 0.0:
        return True
    return bool(item.get("stock_family_allocation_source"))


def _resolve_research_task_source(payload: dict[str, Any] | None) -> str:
    item = dict(payload or {})
    research_task = dict(item.get("research_task") or {})
    return normalize_text(item.get("task_source") or research_task.get("task_source"))


def _supports_relaxed_research_backlog_control(payload: dict[str, Any] | None) -> bool:
    task_source = _resolve_research_task_source(payload)
    return task_source in {"bulk_stock_matrix", "snapshot"}


def resolve_relaxed_research_control_mode(payload: dict[str, Any] | None = None) -> str:
    item = dict(payload or {})
    if _resolve_research_task_source(item) in {"bulk_stock_matrix", "snapshot"}:
        return "normal"
    if _uses_bulk_matrix_plan(payload):
        return "normal"
    return "cooldown"


def _resolve_research_control_relax_reason(
    payload: dict[str, Any] | None,
    *,
    relaxed_mode: str,
) -> str:
    task_source = _resolve_research_task_source(payload)
    lane = "snapshot_research" if task_source == "snapshot" else "bulk_research"
    return (
        f"{lane}_backlog_normal_throttle"
        if relaxed_mode == "normal"
        else f"{lane}_backlog_cooldown"
    )


def is_relaxable_feedback_backlog_control(payload: dict[str, Any] | None) -> bool:
    reasons = _extract_control_reasons(payload)
    if not reasons:
        return False
    if any(
        any(marker in reason for marker in HARD_RESEARCH_CONTROL_REASON_MARKERS)
        for reason in reasons
    ):
        return False
    return all(
        any(marker in reason for marker in RELAXABLE_RESEARCH_CONTROL_REASON_MARKERS)
        for reason in reasons
    )


def relax_feedback_control_for_research_task(
    task: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(task or {})
    if not payload:
        return {}
    if not FACTORY_BACKLOG_RELAX_ENABLED:
        return payload

    if not _supports_relaxed_research_backlog_control(payload):
        return payload

    control_mode = normalize_text(payload.get("feedback_control_mode")) or "normal"
    if control_mode not in {"suppress", "freeze"}:
        return payload
    if not is_relaxable_feedback_backlog_control(payload):
        return payload

    relaxed = dict(payload)
    relaxed_mode = resolve_relaxed_research_control_mode(relaxed)
    relaxed["feedback_control_original_mode"] = control_mode
    relaxed["feedback_control_mode"] = relaxed_mode
    relaxed["feedback_generation_blocked"] = False
    relaxed.pop("feedback_generation_block_reason", None)
    relaxed["feedback_generation_limited"] = True
    relaxed["feedback_relaxed_throttle_active"] = True
    relaxed["feedback_control_relaxed"] = True
    relaxed["feedback_control_relaxed_mode"] = relaxed_mode
    relaxed["feedback_control_relax_reason"] = _resolve_research_control_relax_reason(
        relaxed,
        relaxed_mode=relaxed_mode,
    )

    try:
        generation_limit = int(relaxed.get("generation_limit") or 0)
    except Exception:
        generation_limit = 0
    relaxed["generation_limit"] = 1 if generation_limit <= 0 else max(1, min(generation_limit, 1))

    try:
        priority = int(relaxed.get("priority") or 0)
    except Exception:
        priority = 0
    if priority > 0:
        relaxed["priority"] = max(1, priority - int(FACTORY_BACKLOG_RELAX_PRIORITY_PENALTY))

    feedback_metrics = dict(relaxed.get("feedback_metrics") or {})
    if feedback_metrics:
        feedback_metrics["control_mode"] = relaxed_mode
        feedback_metrics["cooldown_active"] = relaxed_mode == "cooldown"
        feedback_metrics["suppressed"] = False
        feedback_metrics["relaxed_throttle_active"] = True
        relaxed["feedback_metrics"] = feedback_metrics

    reasons = _extract_control_reasons(relaxed)
    relax_reason = str(relaxed.get("feedback_control_relax_reason") or "").strip()
    if relax_reason and relax_reason not in reasons:
        reasons.append(relax_reason)
    relaxed["feedback_control_reasons"] = reasons
    return relaxed


def summarize_task_feedback_controls(tasks: list[dict[str, Any]] | None) -> dict[str, Any]:
    control_mode_counts: dict[str, int] = {}
    legacy_control_mode_counts: dict[str, int] = {}
    skill_control_mode_counts: dict[str, int] = {}
    target_pool_control_mode_counts: dict[str, int] = {}
    holding_bucket_control_mode_counts: dict[str, int] = {}
    generator_mode_control_mode_counts: dict[str, int] = {}
    skill_target_pool_control_mode_counts: dict[str, int] = {}
    skill_holding_bucket_control_mode_counts: dict[str, int] = {}
    skill_generator_mode_control_mode_counts: dict[str, int] = {}
    suppressed_families: list[str] = []
    suppressed_target_pools: list[str] = []
    suppressed_holding_buckets: list[str] = []
    suppressed_generator_modes: list[str] = []
    blocked_task_count = 0
    cooldown_task_count = 0
    limited_task_count = 0
    relaxed_task_count = 0
    budget_action_counts: dict[str, int] = {}
    execution_optimization_queue_count = 0
    small_budget_observe_count = 0
    prioritize_scale_count = 0
    cool_or_freeze_count = 0

    def _append_unique(bucket: list[str], value: Any) -> None:
        token = str(value or "").strip()
        if token and token not in bucket:
            bucket.append(token)

    for item in list(tasks or []):
        task = dict(item or {})
        control_mode = normalize_text(task.get("feedback_control_mode")) or "normal"
        legacy_control_mode = (
            normalize_text(task.get("feedback_legacy_control_mode")) or control_mode
        )
        skill_control_mode = normalize_text(task.get("feedback_skill_control_mode")) or "normal"
        target_pool_control_mode = normalize_text(task.get("feedback_target_pool_control_mode")) or "normal"
        holding_bucket_control_mode = (
            normalize_text(task.get("feedback_holding_bucket_control_mode")) or "normal"
        )
        generator_mode_control_mode = normalize_text(task.get("feedback_generator_mode_control_mode")) or "normal"
        skill_target_pool_control_mode = (
            normalize_text(task.get("feedback_skill_target_pool_control_mode")) or "normal"
        )
        skill_holding_bucket_control_mode = (
            normalize_text(task.get("feedback_skill_holding_bucket_control_mode")) or "normal"
        )
        skill_generator_mode_control_mode = (
            normalize_text(task.get("feedback_skill_generator_mode_control_mode")) or "normal"
        )
        control_mode_counts[control_mode] = control_mode_counts.get(control_mode, 0) + 1
        legacy_control_mode_counts[legacy_control_mode] = (
            legacy_control_mode_counts.get(legacy_control_mode, 0) + 1
        )
        skill_control_mode_counts[skill_control_mode] = (
            skill_control_mode_counts.get(skill_control_mode, 0) + 1
        )
        target_pool_control_mode_counts[target_pool_control_mode] = (
            target_pool_control_mode_counts.get(target_pool_control_mode, 0) + 1
        )
        holding_bucket_control_mode_counts[holding_bucket_control_mode] = (
            holding_bucket_control_mode_counts.get(holding_bucket_control_mode, 0) + 1
        )
        generator_mode_control_mode_counts[generator_mode_control_mode] = (
            generator_mode_control_mode_counts.get(generator_mode_control_mode, 0) + 1
        )
        skill_target_pool_control_mode_counts[skill_target_pool_control_mode] = (
            skill_target_pool_control_mode_counts.get(skill_target_pool_control_mode, 0) + 1
        )
        skill_holding_bucket_control_mode_counts[skill_holding_bucket_control_mode] = (
            skill_holding_bucket_control_mode_counts.get(skill_holding_bucket_control_mode, 0) + 1
        )
        skill_generator_mode_control_mode_counts[skill_generator_mode_control_mode] = (
            skill_generator_mode_control_mode_counts.get(skill_generator_mode_control_mode, 0) + 1
        )
        budget_action = normalize_text(task.get("feedback_budget_action"))
        if budget_action:
            budget_action_counts[budget_action] = budget_action_counts.get(budget_action, 0) + 1
        if bool(task.get("feedback_execution_optimization_queue")):
            execution_optimization_queue_count += 1
        if bool(task.get("feedback_small_budget_observe")):
            small_budget_observe_count += 1
        if bool(task.get("feedback_prioritize_scale")):
            prioritize_scale_count += 1
        if bool(task.get("feedback_cool_or_freeze")):
            cool_or_freeze_count += 1
        if control_mode == "cooldown":
            cooldown_task_count += 1
        if bool(task.get("feedback_generation_limited")):
            limited_task_count += 1
        if bool(task.get("feedback_control_relaxed")):
            relaxed_task_count += 1
        if control_mode in {"suppress", "freeze"} or bool(task.get("feedback_generation_blocked")):
            blocked_task_count += 1
            _append_unique(
                suppressed_families,
                task.get("feedback_family")
                or (task.get("feedback_family_candidates") or [None])[0],
            )
            _append_unique(suppressed_target_pools, task.get("target_pool_id"))
            _append_unique(suppressed_holding_buckets, task.get("holding_period_bucket"))
            _append_unique(suppressed_generator_modes, task.get("generator_mode"))

    return {
        "feedback_control_mode_counts": control_mode_counts,
        "feedback_legacy_control_mode_counts": legacy_control_mode_counts,
        "feedback_skill_control_mode_counts": skill_control_mode_counts,
        "feedback_target_pool_control_mode_counts": target_pool_control_mode_counts,
        "feedback_holding_bucket_control_mode_counts": holding_bucket_control_mode_counts,
        "feedback_generator_mode_control_mode_counts": generator_mode_control_mode_counts,
        "feedback_skill_target_pool_control_mode_counts": skill_target_pool_control_mode_counts,
        "feedback_skill_holding_bucket_control_mode_counts": skill_holding_bucket_control_mode_counts,
        "feedback_skill_generator_mode_control_mode_counts": (
            skill_generator_mode_control_mode_counts
        ),
        "feedback_cooldown_task_count": cooldown_task_count,
        "feedback_limited_task_count": limited_task_count,
        "feedback_relaxed_task_count": relaxed_task_count,
        "feedback_blocked_task_count": blocked_task_count,
        "feedback_budget_action_counts": budget_action_counts,
        "feedback_execution_optimization_queue_count": execution_optimization_queue_count,
        "feedback_small_budget_observe_count": small_budget_observe_count,
        "feedback_prioritize_scale_count": prioritize_scale_count,
        "feedback_cool_or_freeze_count": cool_or_freeze_count,
        "suppressed_families": suppressed_families,
        "suppressed_target_pools": suppressed_target_pools,
        "suppressed_holding_buckets": suppressed_holding_buckets,
        "suppressed_generator_modes": suppressed_generator_modes,
    }


def collect_generator_mode_feedback_controls(
    snapshot_or_feedback: Any,
) -> dict[str, dict[str, Any]]:
    feedback_root = extract_feedback_root(snapshot_or_feedback)
    controls: dict[str, dict[str, Any]] = {}
    for family_name, raw_bucket in feedback_root.items():
        normalized_family = normalize_text(family_name) or "unknown"
        family_bucket = dict(raw_bucket or {})
        generator_scope = dict(family_bucket.get("generator_mode_feedback") or {})
        for mode_name, mode_bucket in generator_scope.items():
            normalized_mode = normalize_text(mode_name)
            if not normalized_mode:
                continue
            scope_control = _derive_scope_control(
                dict(mode_bucket or {}),
                scope_name="generator_mode",
            )
            incoming_severity = int(scope_control.get("severity") or 0)
            existing = dict(controls.get(normalized_mode) or {})
            existing_mode = normalize_text(existing.get("control_mode")) or "normal"
            existing_severity = CONTROL_MODE_SEVERITY.get(existing_mode, 0)
            merged_reasons: list[str] = []
            for reason in [*list(existing.get("control_reasons") or []), *list(scope_control.get("reasons") or [])]:
                token = str(reason or "").strip()
                if token and token not in merged_reasons:
                    merged_reasons.append(token)
            families: list[str] = []
            for value in [*list(existing.get("families") or []), normalized_family]:
                token = normalize_text(value)
                if token and token not in families:
                    families.append(token)
            winner_mode = existing_mode
            if incoming_severity >= existing_severity:
                winner_mode = normalize_text(scope_control.get("mode")) or winner_mode
            skill_scope_control = _derive_skill_scope_control(
                dict(mode_bucket or {}),
                scope_name="generator_mode",
            )
            controls[normalized_mode] = {
                "control_mode": winner_mode or "normal",
                "legacy_control_mode": winner_mode or "normal",
                "skill_control_mode": normalize_text(skill_scope_control.get("mode")) or "normal",
                "control_reasons": merged_reasons,
                "legacy_control_reasons": merged_reasons,
                "skill_control_reasons": list(skill_scope_control.get("reasons") or []),
                "families": families,
                "feedback_observed_count": int(existing.get("feedback_observed_count") or 0) + 1,
                "source": "lifecycle_feedback",
            }
    return controls


def _apply_control_mode_caps(
    *,
    control_mode: str,
    budget_multiplier: float,
    priority_adjustment: float,
    failure_penalty_adjustment: float,
) -> tuple[float, float, float]:
    resolved_budget_multiplier = round(float(budget_multiplier), 4)
    resolved_priority_adjustment = round(float(priority_adjustment), 4)
    resolved_failure_penalty_adjustment = round(float(failure_penalty_adjustment), 4)
    normalized_mode = normalize_text(control_mode) or "normal"
    if normalized_mode == "cooldown":
        resolved_budget_multiplier = round(min(resolved_budget_multiplier, 0.55), 4)
        resolved_priority_adjustment = round(min(resolved_priority_adjustment, -6.0), 4)
        resolved_failure_penalty_adjustment = round(
            max(resolved_failure_penalty_adjustment, 0.12),
            4,
        )
    elif normalized_mode == "suppress":
        resolved_budget_multiplier = 0.0
        resolved_priority_adjustment = round(min(resolved_priority_adjustment, -18.0), 4)
        resolved_failure_penalty_adjustment = round(
            max(resolved_failure_penalty_adjustment, 0.22),
            4,
        )
    elif normalized_mode == "freeze":
        resolved_budget_multiplier = 0.0
        resolved_priority_adjustment = round(min(resolved_priority_adjustment, -24.0), 4)
        resolved_failure_penalty_adjustment = round(
            max(resolved_failure_penalty_adjustment, 0.3),
            4,
        )
    return (
        resolved_budget_multiplier,
        resolved_priority_adjustment,
        resolved_failure_penalty_adjustment,
    )
