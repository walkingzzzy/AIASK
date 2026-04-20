

def _classify_active_pool_exclusion(entry: dict[str, Any]) -> str:
    item = dict(entry.get("item") or {})
    risk_audit = item.get("risk_audit") if isinstance(item.get("risk_audit"), dict) else {}
    admission_blocked = bool(item.get("admission_blocked")) or bool(risk_audit.get("blocked"))
    if admission_blocked:
        return "blocked"
    if bool(entry.get("provisional_eligible")):
        return "pending"
    return "ineligible"


def _resolve_active_pool_exclusion_reasons(entry: dict[str, Any], classification: str) -> list[str]:
    item = dict(entry.get("item") or {})
    risk_audit = item.get("risk_audit") if isinstance(item.get("risk_audit"), dict) else {}
    if classification == "blocked":
        return _dedupe_tokens(
            item.get("admission_block_reasons")
            or risk_audit.get("block_reasons")
            or ["admission_blocked"]
        )
    if classification == "pending":
        pending_reason_code = str(entry.get("pending_reason_code") or "").strip().lower()
        if pending_reason_code:
            return [pending_reason_code]
        return _dedupe_tokens(entry.get("strict_reasons") or entry.get("provisional_reasons"))
    return _dedupe_tokens(entry.get("provisional_reasons") or entry.get("strict_reasons"))


def _build_active_pool_candidate_entry(
    item: dict[str, Any],
    *,
    pool_entry_mode: str | None = None,
    reasons: list[str] | None = None,
    exclusion_bucket: str | None = None,
) -> dict[str, Any]:
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    rating = item.get("rating") if isinstance(item.get("rating"), dict) else {}
    risk_audit = item.get("risk_audit") if isinstance(item.get("risk_audit"), dict) else {}
    lineage = item.get("lineage") if isinstance(item.get("lineage"), dict) else {}
    family = str(candidate.get("family") or "unknown").strip().lower() or "unknown"
    recommendation = str(rating.get("recommendation") or "").strip().lower()
    registry_stage = str(item.get("registry_stage") or "").strip().lower()
    score = _safe_float(rating.get("total_score"), 0.0)
    regimes = candidate.get("expected_regime") if isinstance(candidate.get("expected_regime"), list) else []

    payload = {
        "artifact_id": item.get("artifact_id"),
        "name": candidate.get("name"),
        "family": family,
        "expected_regime": regimes,
        "expected_holding_period": candidate.get("expected_holding_period"),
        "grade": rating.get("grade"),
        "recommendation": recommendation,
        "registry_stage": registry_stage,
        "total_score": score,
        "risk_audit": risk_audit,
        "admission_blocked": bool(item.get("admission_blocked")),
        "admission_block_reasons": list(item.get("admission_block_reasons") or []),
        "source_generation_artifact_id": item.get("source_generation_artifact_id"),
        "source_validation_artifact_id": item.get("source_validation_artifact_id"),
        "memory_record_id": item.get("memory_record_id"),
        "latest_validation_at": item.get("latest_validation_at"),
        "validation_params": dict(item.get("validation_params") or {}),
        "model_registry_stages": list(item.get("model_registry_stages") or []),
        "lineage": lineage,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }
    if pool_entry_mode:
        payload["pool_entry_mode"] = pool_entry_mode
    if reasons is not None:
        payload["reasons"] = list(reasons)
    if exclusion_bucket:
        payload["exclusion_bucket"] = exclusion_bucket
    return payload


def _build_active_candidate_pool(items: list[dict]) -> dict:
    stage_rank = {"champion": 4, "challenger": 3, "governed": 2, "validated": 1}
    family_bucket = {}
    regime_counts = {}
    evaluated_items = []
    latest_candidate_updated_at = None

    for item in list(items or []):
        updated_at = str(item.get("latest_validation_at") or item.get("updated_at") or item.get("created_at") or "").strip() or None

        if updated_at and (latest_candidate_updated_at is None or updated_at > latest_candidate_updated_at):
            latest_candidate_updated_at = updated_at

        evaluated_items.append(
            {
                "item": item,
                "updated_at": updated_at,
                **_evaluate_active_pool_eligibility(item),
            }
        )

    strict_candidates = [entry for entry in evaluated_items if bool(entry.get("strict_eligible"))]
    provisional_candidates = [entry for entry in evaluated_items if bool(entry.get("provisional_eligible"))]
    provisional_spillover_candidates: list[dict[str, Any]] = []
    provisional_only_candidates: list[dict[str, Any]] = []
    provisional_spillover_policy: dict[str, Any] = {
        "enabled": bool(STRICT_ACTIVE_POOL_SPILLOVER_ENABLED),
        "min_strict_count": int(STRICT_ACTIVE_POOL_MIN_COUNT),
        "spillover_limit": int(STRICT_ACTIVE_POOL_PROVISIONAL_SPILLOVER_LIMIT),
        "status": "empty",
        "decision": "empty",
        "strict_count": len(strict_candidates),
        "provisional_count": len(provisional_candidates),
        "provisional_only_count": 0,
        "selected_spillover_count": 0,
        "pending_provisional_count": 0,
        "strict_shortfall_count": 0,
        "pending_reason_code": None,
    }
    if strict_candidates:
        active_pool_mode = STRICT_ACTIVE_POOL_MODE
        selected_candidates = list(strict_candidates)
        provisional_only_candidates = [
            entry
            for entry in provisional_candidates
            if not bool(entry.get("strict_eligible"))
        ]
        provisional_only_candidates.sort(
            key=lambda entry: (
                _safe_float(
                    (
                        dict((entry.get("item") or {}).get("rating") or {}).get("total_score")
                    ),
                    0.0,
                ),
                str(entry.get("updated_at") or ""),
                str(dict(entry.get("item") or {}).get("artifact_id") or ""),
            ),
            reverse=True,
        )
        spillover_budget = 0
        strict_shortfall_count = max(STRICT_ACTIVE_POOL_MIN_COUNT - len(strict_candidates), 0)
        if STRICT_ACTIVE_POOL_SPILLOVER_ENABLED:
            spillover_budget = min(
                strict_shortfall_count,
                len(provisional_only_candidates),
                STRICT_ACTIVE_POOL_PROVISIONAL_SPILLOVER_LIMIT,
            )
        if spillover_budget > 0:
            provisional_spillover_candidates = provisional_only_candidates[:spillover_budget]
            selected_candidates.extend(provisional_spillover_candidates)
        pending_reason_code = None
        pending_provisional_count = max(
            len(provisional_only_candidates) - len(provisional_spillover_candidates),
            0,
        )
        if len(provisional_only_candidates) > 0:
            if strict_shortfall_count <= 0:
                policy_status = "awaiting_governed_promotion"
                policy_decision = "strict_only"
                pending_reason_code = "awaiting_governed_promotion"
            elif not STRICT_ACTIVE_POOL_SPILLOVER_ENABLED:
                policy_status = "spillover_disabled"
                policy_decision = "strict_only"
                pending_reason_code = "spillover_disabled"
            elif pending_provisional_count > 0:
                policy_status = "spillover_capacity_exhausted"
                policy_decision = "spillover_capped"
                pending_reason_code = "spillover_capacity_exhausted"
            else:
                policy_status = "spillover_applied"
                policy_decision = "spillover_applied"
        else:
            if strict_shortfall_count > 0:
                policy_status = "strict_pool_shortfall_without_provisional_supply"
                policy_decision = "strict_only"
            else:
                policy_status = "strict_pool_sufficient"
                policy_decision = "strict_only"
        provisional_spillover_policy = {
            "enabled": bool(STRICT_ACTIVE_POOL_SPILLOVER_ENABLED),
            "min_strict_count": int(STRICT_ACTIVE_POOL_MIN_COUNT),
            "spillover_limit": int(STRICT_ACTIVE_POOL_PROVISIONAL_SPILLOVER_LIMIT),
            "status": policy_status,
            "decision": policy_decision,
            "strict_count": len(strict_candidates),
            "provisional_count": len(provisional_candidates),
            "provisional_only_count": len(provisional_only_candidates),
            "selected_spillover_count": len(provisional_spillover_candidates),
            "pending_provisional_count": pending_provisional_count,
            "strict_shortfall_count": strict_shortfall_count,
            "pending_reason_code": pending_reason_code,
        }
        if pending_reason_code:
            for entry in provisional_only_candidates[len(provisional_spillover_candidates):]:
                entry["pending_reason_code"] = pending_reason_code
        selected_entry_ids = {id(entry) for entry in selected_candidates}
        excluded_source = [entry for entry in evaluated_items if id(entry) not in selected_entry_ids]
        exclusion_reason_key = "strict_reasons"
    elif provisional_candidates:
        active_pool_mode = PROVISIONAL_ACTIVE_POOL_MODE
        selected_candidates = provisional_candidates
        provisional_spillover_policy = {
            "enabled": bool(STRICT_ACTIVE_POOL_SPILLOVER_ENABLED),
            "min_strict_count": int(STRICT_ACTIVE_POOL_MIN_COUNT),
            "spillover_limit": int(STRICT_ACTIVE_POOL_PROVISIONAL_SPILLOVER_LIMIT),
            "status": "provisional_pool_only",
            "decision": "provisional_only",
            "strict_count": 0,
            "provisional_count": len(provisional_candidates),
            "provisional_only_count": len(provisional_candidates),
            "selected_spillover_count": 0,
            "pending_provisional_count": 0,
            "strict_shortfall_count": int(STRICT_ACTIVE_POOL_MIN_COUNT),
            "pending_reason_code": None,
        }
        excluded_source = [
            entry
            for entry in evaluated_items
            if not bool(entry.get("provisional_eligible"))
        ]
        exclusion_reason_key = "provisional_reasons"
    else:
        active_pool_mode = EMPTY_ACTIVE_POOL_MODE
        selected_candidates = []
        provisional_spillover_policy = {
            "enabled": bool(STRICT_ACTIVE_POOL_SPILLOVER_ENABLED),
            "min_strict_count": int(STRICT_ACTIVE_POOL_MIN_COUNT),
            "spillover_limit": int(STRICT_ACTIVE_POOL_PROVISIONAL_SPILLOVER_LIMIT),
            "status": "empty",
            "decision": "empty",
            "strict_count": 0,
            "provisional_count": 0,
            "provisional_only_count": 0,
            "selected_spillover_count": 0,
            "pending_provisional_count": 0,
            "strict_shortfall_count": int(STRICT_ACTIVE_POOL_MIN_COUNT),
            "pending_reason_code": None,
        }
        excluded_source = list(evaluated_items)
        exclusion_reason_key = "provisional_reasons"

    top_candidates = []
    latest_active_candidate_updated_at = None
    provisional_spillover_ids = {id(entry) for entry in provisional_spillover_candidates}
    for entry in selected_candidates:
        item = dict(entry.get("item") or {})
        candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        rating = item.get("rating") if isinstance(item.get("rating"), dict) else {}
        family = str(candidate.get("family") or "unknown").strip().lower() or "unknown"
        recommendation = str(rating.get("recommendation") or "").strip().lower()
        score = _safe_float(rating.get("total_score"), 0.0)
        regimes = candidate.get("expected_regime") if isinstance(candidate.get("expected_regime"), list) else []

        bucket = family_bucket.setdefault(
            family,
            {
                "family": family,
                "count": 0,
                "promote_count": 0,
                "review_count": 0,
                "scores": [],
            },
        )
        bucket["count"] += 1
        bucket["scores"].append(score)
        if recommendation == "promote":
            bucket["promote_count"] += 1
        if recommendation == "review":
            bucket["review_count"] += 1

        for regime in [str(r).strip().lower() for r in regimes if str(r).strip()]:
            regime_counts[regime] = int(regime_counts.get(regime, 0)) + 1

        top_candidates.append(
            _build_active_pool_candidate_entry(
                item,
                pool_entry_mode=(
                    PROVISIONAL_ACTIVE_POOL_MODE
                    if id(entry) in provisional_spillover_ids
                    else active_pool_mode
                ),
            )
        )
        updated_at = entry.get("updated_at")
        if updated_at and (
            latest_active_candidate_updated_at is None or updated_at > latest_active_candidate_updated_at
        ):
            latest_active_candidate_updated_at = updated_at

    excluded_candidates = []
    exclusion_reason_counts = {}
    blocked_excluded_count = 0
    blocked_exclusion_reason_counts = {}
    pending_excluded_count = 0
    pending_exclusion_reason_counts = {}
    ineligible_excluded_count = 0
    ineligible_exclusion_reason_counts = {}
    latest_blocked_candidate_updated_at = None
    for entry in excluded_source:
        item = dict(entry.get("item") or {})
        classification = _classify_active_pool_exclusion(entry)
        reasons = _resolve_active_pool_exclusion_reasons(entry, classification)
        if classification == "blocked":
            target_reason_counts = blocked_exclusion_reason_counts
            blocked_excluded_count += 1
        elif classification == "pending":
            target_reason_counts = pending_exclusion_reason_counts
            pending_excluded_count += 1
        else:
            target_reason_counts = ineligible_exclusion_reason_counts
            ineligible_excluded_count += 1
        for reason in reasons:
            exclusion_reason_counts[reason] = int(exclusion_reason_counts.get(reason, 0)) + 1
            target_reason_counts[reason] = int(target_reason_counts.get(reason, 0)) + 1
        excluded_candidates.append(
            _build_active_pool_candidate_entry(
                item,
                reasons=reasons,
                exclusion_bucket=classification,
            )
        )
        updated_at = entry.get("updated_at")
        if updated_at and (
            latest_blocked_candidate_updated_at is None or updated_at > latest_blocked_candidate_updated_at
        ):
            latest_blocked_candidate_updated_at = updated_at

    family_summary = []
    for bucket in family_bucket.values():
        scores = list(bucket.pop("scores") or [])
        bucket["avg_total_score"] = round(float(np.mean(scores)), 6) if scores else 0.0
        bucket["max_total_score"] = round(float(max(scores)), 6) if scores else 0.0
        family_summary.append(bucket)
    family_summary.sort(key=lambda item: (item.get("avg_total_score", 0.0), item.get("count", 0)), reverse=True)

    regime_summary = [
        {"regime": regime, "count": count}
        for regime, count in sorted(regime_counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    ]
    top_candidates.sort(
        key=lambda item: (
            stage_rank.get(str(item.get("registry_stage") or "").strip().lower(), 0),
            item.get("total_score", 0.0),
            str(item.get("artifact_id") or ""),
        ),
        reverse=True,
    )
    excluded_candidates.sort(
        key=lambda item: (item.get("total_score", 0.0), str(item.get("artifact_id") or "")),
        reverse=True,
    )

    return {
        "active_pool_mode": active_pool_mode,
        "source_count": len(list(items or [])),
        "count": len(top_candidates),
        "strict_count": len(strict_candidates),
        "provisional_count": len(provisional_candidates),
        "provisional_spillover_count": len(provisional_spillover_candidates),
        "provisional_spillover_enabled": bool(STRICT_ACTIVE_POOL_SPILLOVER_ENABLED),
        "provisional_spillover_policy": provisional_spillover_policy,
        "excluded_count": len(excluded_candidates),
        "family_summary": family_summary,
        "regime_summary": regime_summary,
        "latest_candidate_updated_at": latest_candidate_updated_at,
        "latest_active_candidate_updated_at": latest_active_candidate_updated_at,
        "latest_blocked_candidate_updated_at": latest_blocked_candidate_updated_at,
        "top_candidates": top_candidates[:20],
        "provisional_spillover_artifact_ids": [
            str(dict(entry.get("item") or {}).get("artifact_id") or "")
            for entry in provisional_spillover_candidates
            if str(dict(entry.get("item") or {}).get("artifact_id") or "")
        ],
        "excluded_candidates": excluded_candidates[:20],
        "exclusion_reason_counts": exclusion_reason_counts,
        "blocked_excluded_count": blocked_excluded_count,
        "blocked_exclusion_reason_counts": blocked_exclusion_reason_counts,
        "pending_excluded_count": pending_excluded_count,
        "pending_exclusion_reason_counts": pending_exclusion_reason_counts,
        "ineligible_excluded_count": ineligible_excluded_count,
        "ineligible_exclusion_reason_counts": ineligible_exclusion_reason_counts,
    }


async def handle_factor_research_memory(
    *,
    kw: dict[str, Any],
    ok: Callable[..., dict],
    fail: Callable[..., dict],
    memory_service_factory: Callable[[], Any] = get_factor_research_memory_service,
) -> dict:
    memory_service = memory_service_factory()
    op = str(kw.get("op", "list") or "list").strip().lower()

    if op in {"list", "ls"}:
        codes = _as_code_list(kw.get("codes"))
        status = str(kw.get("status") or "").strip() or None
        family = str(kw.get("family") or "").strip() or None
        limit = max(1, min(int(kw.get("limit", 20) or 20), 100))
        items = await memory_service.list_memory_records(limit=limit, codes=codes or None, status=status, family=family)
        return ok(
            {"op": "list", "count": len(items), "items": items},
            source_chain=["services.factor_research_memory", "services.factor_candidate_storage"],
        )

    if op in {"get", "detail"}:
        artifact_id = str(kw.get("artifact_id") or "").strip()
        if not artifact_id:
            return fail("factor_research_memory get 需要 artifact_id")
        item = await memory_service.get_memory_record(artifact_id)
        if not item:
            return fail(f"memory record not found: {artifact_id}")
        return ok(
            {"op": "get", "item": item},
            source_chain=["services.factor_research_memory", "services.factor_candidate_storage"],
        )

    if op in {"recall", "search"}:
        raw_candidate = kw.get("candidate")
        if isinstance(raw_candidate, str) and raw_candidate.strip():
            try:
                raw_candidate = json.loads(raw_candidate)
            except Exception:
                return fail("candidate 必须是 dict 或可解析的 JSON 字符串")
        query_text = str(kw.get("query_text") or "").strip() or None
        codes = _as_code_list(kw.get("codes"))
        status = str(kw.get("status") or "").strip() or None
        limit = max(1, min(int(kw.get("limit", 5) or 5), 20))
        items = await memory_service.recall_similar_candidates(
            candidate=raw_candidate if isinstance(raw_candidate, dict) else None,
            query_text=query_text,
            codes=codes or None,
            status=status,
            limit=limit,
        )
        return ok(
            {"op": "recall", "count": len(items), "items": items},
            source_chain=["services.factor_research_memory", "services.factor_candidate_storage"],
        )

    if op in {"stats", "summary"}:
        codes = _as_code_list(kw.get("codes"))
        status = str(kw.get("status") or "").strip() or None
        family = str(kw.get("family") or "").strip() or None
        limit = max(1, min(int(kw.get("limit", 200) or 200), 500))
        stats = await memory_service.summarize_memory_records(
            limit=limit,
            codes=codes or None,
            status=status,
            family=family,
        )
        return ok(
            {"op": "stats", "stats": stats},
            source_chain=["services.factor_research_memory", "services.factor_candidate_storage"],
        )

    if op in {"feedback_sync", "write_feedback"}:
        artifact_id = str(kw.get("artifact_id") or "").strip()
        if not artifact_id:
            return fail("factor_research_memory feedback_sync 需要 artifact_id")
        raw_feedback = kw.get("feedback")
        if isinstance(raw_feedback, str) and raw_feedback.strip():
            try:
                raw_feedback = json.loads(raw_feedback)
            except Exception:
                return fail("feedback 必须是 dict 或可解析的 JSON 字符串")
        if not isinstance(raw_feedback, dict):
            return fail("feedback 必须是包含反馈信号的 dict（decay_detected / regime_shift_detected / forward_return 等）")
        try:
            updated = await memory_service.record_feedback(
                artifact_id=artifact_id,
                feedback=raw_feedback,
                source_feedback_artifact_id=str(kw.get("source_feedback_artifact_id") or "").strip() or None,
                source_model_registry_artifact_id=str(kw.get("source_model_registry_artifact_id") or "").strip() or None,
            )
        except ValueError as exc:
            return fail(str(exc))
        return ok(
            {
                "op": "feedback_sync",
                "artifact_id": artifact_id,
                "new_status": updated.get("status"),
                "last_feedback_recommended_action": updated.get("last_feedback_recommended_action"),
                "runtime_feedback_count": len(updated.get("runtime_feedback") or []),
                "item": updated,
            },
            source_chain=["services.factor_research_memory", "services.factor_candidate_storage"],
        )

    return fail("Unknown factor_research_memory op. Supported: list|get|recall|stats|feedback_sync")
