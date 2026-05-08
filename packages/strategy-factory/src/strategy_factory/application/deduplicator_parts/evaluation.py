
    @classmethod
    def _evaluate_existing_match_decision(
        cls,
        candidate: Optional[dict],
        match: Optional[dict],
        existing_item: Optional[dict] = None,
    ) -> dict[str, Any]:
        candidate = dict(candidate or {})
        match = dict(match or {})
        existing_payload = dict(existing_item or {})
        matched_status = str(match.get("matched_status") or "").strip().lower()
        matched_strategy_id = str(match.get("matched_strategy_id") or "").strip()
        parent_strategy_ids = cls._extract_parent_strategy_ids(candidate)
        parent_lineage_matched = bool(matched_strategy_id and matched_strategy_id in parent_strategy_ids)
        explicit_candidate_universe = cls._has_explicit_universe(candidate)
        explicit_existing_universe = cls._has_explicit_universe(existing_payload)
        exact_target_universe_match = (
            cls._has_exact_target_universe_match(candidate, existing_payload)
            if existing_payload and explicit_candidate_universe and explicit_existing_universe
            else False
        )
        target_overlap = float(match.get("target_overlap") or 0.0)
        research_task = _normalize_research_task_contract(candidate.get("research_task") or {})
        event_context = dict(candidate.get("event_context") or {}) or _extract_event_context(research_task)
        has_event_context = bool(
            event_context.get("event_id")
            or event_context.get("theme_code")
            or research_task.get("task_source") == "event_driven"
            or str(candidate.get("source") or "").startswith("strategy_factory:")
        )
        candidate_signature = cls._candidate_task_signature(candidate)
        existing_signature = cls._existing_task_signature(existing_payload) if existing_payload else ""
        candidate_identity = cls._candidate_identity_signature(candidate)
        existing_identity = cls._existing_identity_signature(existing_payload) if existing_payload else ""
        candidate_tested_object_hash = cls._candidate_tested_object_hash(candidate)
        existing_tested_object_hash = cls._existing_tested_object_hash(existing_payload) if existing_payload else ""
        tested_object_changed = None
        if existing_payload and candidate_tested_object_hash and existing_tested_object_hash:
            tested_object_changed = candidate_tested_object_hash != existing_tested_object_hash
        identity_changed = None
        if existing_payload and candidate_identity and existing_identity:
            identity_changed = candidate_identity != existing_identity
        task_signature_changed = None
        if existing_payload and candidate_signature and existing_signature:
            task_signature_changed = candidate_signature != existing_signature
        legacy_identity_partial = bool(
            existing_payload
            and (
                not cls._has_explicit_identity_contract(existing_payload)
                or not cls._has_explicit_tested_object_hash(existing_payload)
            )
        )
        refresh_improvement = cls._refresh_improvement_snapshot(candidate, existing_payload)
        refresh_lineage_depth = max(
            cls._lineage_operation_depth(candidate, mode="refresh"),
            cls._lineage_operation_depth(existing_payload, mode="refresh"),
        )
        revision_lineage_depth = max(
            cls._lineage_operation_depth(candidate, mode="revision"),
            cls._lineage_operation_depth(existing_payload, mode="revision"),
        )
        tested_object_backfill_incomplete = bool(
            existing_payload
            and not cls._has_explicit_tested_object_hash(existing_payload)
            and legacy_identity_partial
        )
        decision = {
            "refresh_existing": False,
            "spawn_revision_from_existing": False,
            "refresh_decision_basis": None,
            "revision_trigger_reason": None,
            "parent_lineage_matched": parent_lineage_matched,
            "candidate_task_signature": candidate_signature or None,
            "existing_task_signature": existing_signature or None,
            "task_signature_changed": task_signature_changed,
            "candidate_identity_signature": candidate_identity or None,
            "existing_identity_signature": existing_identity or None,
            "existing_identity_available": bool(existing_payload and existing_identity),
            "identity_changed": identity_changed,
            "candidate_tested_object_hash": candidate_tested_object_hash or None,
            "existing_tested_object_hash": existing_tested_object_hash or None,
            "tested_object_changed": tested_object_changed,
            "tested_object_hash_changed": tested_object_changed,
            "existing_tested_object_available": bool(existing_payload and existing_tested_object_hash),
            "legacy_identity_partial": legacy_identity_partial,
            "tested_object_backfill_incomplete": tested_object_backfill_incomplete,
            "exact_target_universe_match": exact_target_universe_match,
            "refresh_improvement_required": bool(refresh_improvement.get("required")),
            "refresh_improvement_passed": bool(refresh_improvement.get("passed")),
            "refresh_candidate_score": refresh_improvement.get("candidate_score"),
            "refresh_existing_score": refresh_improvement.get("existing_score"),
            "refresh_lineage_limit_reached": refresh_lineage_depth >= cls.MAX_REFRESH_PER_LINEAGE,
            "revision_lineage_limit_reached": revision_lineage_depth >= cls.MAX_REVISION_PER_LINEAGE,
        }
        decision.update(
            cls._lineage_quality_pressure(
                candidate,
                existing_payload,
                refresh_lineage_depth=refresh_lineage_depth,
                revision_lineage_depth=revision_lineage_depth,
                exact_target_universe_match=exact_target_universe_match,
            )
        )
        if matched_status not in {"incubating", "listed", "published"} or not matched_strategy_id:
            decision["refresh_decision_basis"] = "matched_strategy_not_refreshable"
            return decision
        if (
            decision.get("lineage_retire_recommended")
            and decision.get("lineage_structural_shift_required")
            and not decision.get("lineage_structural_shift_applied")
        ):
            decision["refresh_decision_basis"] = "low_quality_lineage_retired"
            return decision
        if not existing_payload:
            decision["refresh_existing"] = bool(has_event_context and explicit_candidate_universe)
            decision["refresh_decision_basis"] = (
                "event_context_fallback"
                if decision["refresh_existing"]
                else ("parent_lineage_without_existing_context" if parent_lineage_matched else "insufficient_existing_context")
            )
            return decision
        legacy_partial_refresh_allowed = bool(
            legacy_identity_partial
            and not bool(decision.get("existing_identity_available"))
            and exact_target_universe_match
            and bool(decision.get("refresh_improvement_passed"))
            and not bool(decision.get("refresh_lineage_limit_reached"))
            and (
                (parent_lineage_matched and task_signature_changed is not True)
                or (
                    has_event_context
                    and explicit_candidate_universe
                    and task_signature_changed is not True
                )
                or (task_signature_changed is False)
            )
        )
        if tested_object_changed is True:
            if legacy_partial_refresh_allowed:
                if (
                    decision.get("lineage_structural_shift_required")
                    and not decision.get("lineage_structural_shift_applied")
                ):
                    decision["refresh_decision_basis"] = "low_quality_lineage_refresh_blocked"
                    return decision
                decision["refresh_existing"] = True
                if parent_lineage_matched:
                    decision["refresh_decision_basis"] = "legacy_partial_parent_lineage_refresh"
                elif has_event_context and explicit_candidate_universe:
                    decision["refresh_decision_basis"] = "legacy_partial_event_context_refresh"
                else:
                    decision["refresh_decision_basis"] = "legacy_partial_task_signature_refresh"
                return decision
            decision["refresh_decision_basis"] = "tested_object_changed"
            decision["spawn_revision_from_existing"] = bool(
                not decision.get("revision_lineage_limit_reached")
                and (
                    parent_lineage_matched
                    or target_overlap >= 0.8
                    or exact_target_universe_match
                    or task_signature_changed is False
                )
            )
            if decision["spawn_revision_from_existing"]:
                if (
                    decision.get("lineage_structural_shift_required")
                    and not decision.get("lineage_structural_shift_applied")
                ):
                    decision["spawn_revision_from_existing"] = False
                    decision["refresh_decision_basis"] = "low_quality_lineage_shift_required"
                    return decision
                decision["revision_trigger_reason"] = decision["refresh_decision_basis"]
            elif decision.get("revision_lineage_limit_reached"):
                decision["refresh_decision_basis"] = "revision_limit_reached"
            return decision
        if identity_changed is True:
            decision["refresh_decision_basis"] = "identity_changed"
            decision["spawn_revision_from_existing"] = bool(
                not decision.get("revision_lineage_limit_reached")
                and (
                    parent_lineage_matched
                    or target_overlap >= 0.8
                    or exact_target_universe_match
                )
            )
            if decision["spawn_revision_from_existing"]:
                if (
                    decision.get("lineage_structural_shift_required")
                    and not decision.get("lineage_structural_shift_applied")
                ):
                    decision["spawn_revision_from_existing"] = False
                    decision["refresh_decision_basis"] = "low_quality_lineage_shift_required"
                    return decision
                decision["revision_trigger_reason"] = decision["refresh_decision_basis"]
            elif decision.get("revision_lineage_limit_reached"):
                decision["refresh_decision_basis"] = "revision_limit_reached"
            return decision
        if task_signature_changed is True:
            decision["refresh_decision_basis"] = "task_signature_changed"
            decision["spawn_revision_from_existing"] = bool(
                not decision.get("revision_lineage_limit_reached")
                and (parent_lineage_matched or target_overlap >= 0.8)
            )
            if decision["spawn_revision_from_existing"]:
                if (
                    decision.get("lineage_structural_shift_required")
                    and not decision.get("lineage_structural_shift_applied")
                ):
                    decision["spawn_revision_from_existing"] = False
                    decision["refresh_decision_basis"] = "low_quality_lineage_shift_required"
                    return decision
                decision["revision_trigger_reason"] = decision["refresh_decision_basis"]
            elif decision.get("revision_lineage_limit_reached"):
                decision["refresh_decision_basis"] = "revision_limit_reached"
            return decision
        if explicit_candidate_universe and explicit_existing_universe and not exact_target_universe_match:
            decision["refresh_decision_basis"] = "target_universe_changed"
            decision["spawn_revision_from_existing"] = bool(
                not decision.get("revision_lineage_limit_reached")
                and (parent_lineage_matched or target_overlap >= 0.8)
            )
            if decision["spawn_revision_from_existing"]:
                if (
                    decision.get("lineage_structural_shift_required")
                    and not decision.get("lineage_structural_shift_applied")
                ):
                    decision["spawn_revision_from_existing"] = False
                    decision["refresh_decision_basis"] = "low_quality_lineage_shift_required"
                    return decision
                decision["revision_trigger_reason"] = decision["refresh_decision_basis"]
            elif decision.get("revision_lineage_limit_reached"):
                decision["refresh_decision_basis"] = "revision_limit_reached"
            return decision
        if candidate_tested_object_hash and existing_tested_object_hash and candidate_tested_object_hash == existing_tested_object_hash:
            if legacy_identity_partial:
                if (
                    decision.get("lineage_structural_shift_required")
                    and not decision.get("lineage_structural_shift_applied")
                ):
                    decision["refresh_decision_basis"] = "low_quality_lineage_refresh_blocked"
                    return decision
                if (
                    not decision.get("refresh_improvement_required")
                    or bool(decision.get("refresh_improvement_passed"))
                ) and not bool(decision.get("refresh_lineage_limit_reached")) and (
                    parent_lineage_matched
                    or (
                        has_event_context
                        and explicit_candidate_universe
                        and (exact_target_universe_match or target_overlap >= 0.8)
                    )
                    or (
                        task_signature_changed is False
                        and (exact_target_universe_match or target_overlap >= 0.8)
                    )
                ):
                    decision["refresh_existing"] = True
                    if parent_lineage_matched:
                        decision["refresh_decision_basis"] = "same_tested_object_with_legacy_identity_parent_lineage"
                    elif has_event_context and explicit_candidate_universe:
                        decision["refresh_decision_basis"] = "same_tested_object_with_legacy_identity_event_context"
                    else:
                        decision["refresh_decision_basis"] = "same_tested_object_with_legacy_identity_backfill"
                    return decision
                if decision.get("refresh_lineage_limit_reached"):
                    decision["refresh_decision_basis"] = "refresh_limit_reached"
                    return decision
                if decision.get("refresh_improvement_required") and not decision.get("refresh_improvement_passed"):
                    decision["refresh_decision_basis"] = "same_tested_object_without_improvement"
                    return decision
                decision["refresh_decision_basis"] = "same_tested_object_but_legacy_identity_partial"
                decision["spawn_revision_from_existing"] = bool(
                    not decision.get("revision_lineage_limit_reached")
                    and (
                        parent_lineage_matched
                        or target_overlap >= 0.8
                        or exact_target_universe_match
                        or task_signature_changed is False
                    )
                )
                if decision["spawn_revision_from_existing"]:
                    if (
                        decision.get("lineage_structural_shift_required")
                        and not decision.get("lineage_structural_shift_applied")
                    ):
                        decision["spawn_revision_from_existing"] = False
                        decision["refresh_decision_basis"] = "low_quality_lineage_shift_required"
                        return decision
                    decision["revision_trigger_reason"] = decision["refresh_decision_basis"]
                elif decision.get("revision_lineage_limit_reached"):
                    decision["refresh_decision_basis"] = "revision_limit_reached"
                return decision
            if (
                decision.get("lineage_structural_shift_required")
                and not decision.get("lineage_structural_shift_applied")
            ):
                decision["refresh_decision_basis"] = "low_quality_lineage_refresh_blocked"
                return decision
            if decision.get("refresh_lineage_limit_reached"):
                decision["refresh_decision_basis"] = "refresh_limit_reached"
                return decision
            if decision.get("refresh_improvement_required") and not decision.get("refresh_improvement_passed"):
                decision["refresh_decision_basis"] = "same_tested_object_without_improvement"
                return decision
            decision["refresh_existing"] = True
            decision["refresh_decision_basis"] = "same_tested_object_and_identity"
            return decision
        decision["refresh_decision_basis"] = "no_refresh_basis"
        return decision

    @classmethod
    def _should_refresh_existing(
        cls,
        candidate: Optional[dict],
        match: Optional[dict],
        existing_item: Optional[dict] = None,
    ) -> bool:
        return bool(
            cls._evaluate_existing_match_decision(candidate, match, existing_item).get("refresh_existing")
        )

    @classmethod
    def _should_spawn_revision_from_existing(
        cls,
        candidate: Optional[dict],
        match: Optional[dict],
        existing_item: Optional[dict],
    ) -> bool:
        return bool(
            cls._evaluate_existing_match_decision(candidate, match, existing_item).get("spawn_revision_from_existing")
        )

    async def _find_duplicate(self, candidate: dict, existing: list, db) -> tuple[dict, dict]:
        best_match: Optional[dict] = None
        semantic_match: Optional[dict[str, Any]] = None
        semantic_match_priority: Optional[tuple[int, int, int, int, float, float]] = None
        suspicious: List[dict] = []
        candidate_params = self._normalize_params(candidate.get("params"))
        candidate_identity = structural_identity(candidate)
        candidate_strategy_hash = str(candidate.get("strategy_instance_hash") or candidate_params.get("strategy_instance_hash") or candidate_identity.get("strategy_instance_hash") or "").strip()
        candidate_tested_hash = str(candidate.get("tested_object_hash") or candidate_params.get("tested_object_hash") or candidate_identity.get("tested_object_hash") or "").strip()
        metrics = {
            "scanned_count": 0,
            "coarse_candidate_count": 0,
            "coarse_tag_hit_count": 0,
            "coarse_target_hit_count": 0,
            "vector_candidate_count": 0,
            "vector_candidate_trimmed_count": 0,
            "structural_hash_checks": 0,
            "structural_hash_duplicates": 0,
            "param_similarity_unreliable": not has_executable_params(candidate.get("strategy_type"), candidate_params),
        }
        for existing_item in existing:
            metrics["scanned_count"] += 1
            existing_params = self._normalize_params(existing_item.get("params"))
            existing_identity = structural_identity(existing_item)
            existing_strategy_hash = str(existing_item.get("strategy_instance_hash") or existing_params.get("strategy_instance_hash") or existing_identity.get("strategy_instance_hash") or "").strip()
            existing_tested_hash = str(existing_item.get("tested_object_hash") or existing_params.get("tested_object_hash") or existing_identity.get("tested_object_hash") or "").strip()
            metrics["structural_hash_checks"] += 1
            if candidate_strategy_hash and candidate_strategy_hash == existing_strategy_hash:
                metrics["structural_hash_duplicates"] += 1
                return {
                    "duplicate": True,
                    "duplicate_level": "persisted_hash",
                    "match_type": "structural_hash",
                    "refresh_mode": None,
                    "reason": "strategy_instance_hash matches an existing persisted strategy",
                    "threshold": self.THRESHOLD,
                    "vector_threshold": self.VECTOR_THRESHOLD,
                    "vector_checked": False,
                    "fallback_dedup_mode": "structural_hash",
                    "param_similarity_unreliable": bool(metrics.get("param_similarity_unreliable")),
                    "strategy_instance_hash": candidate_strategy_hash,
                    "tested_object_hash": candidate_tested_hash,
                    "matched_strategy_id": existing_item.get("id"),
                    "matched_name": existing_item.get("name") or existing_item.get("strategy_type"),
                    "matched_status": existing_item.get("status"),
                }, metrics
            if candidate_tested_hash and candidate_tested_hash == existing_tested_hash:
                metrics["structural_hash_duplicates"] += 1
                return {
                    "duplicate": True,
                    "duplicate_level": "persisted_hash",
                    "match_type": "structural_hash",
                    "refresh_mode": None,
                    "reason": "tested_object_hash matches an existing persisted strategy",
                    "threshold": self.THRESHOLD,
                    "vector_threshold": self.VECTOR_THRESHOLD,
                    "vector_checked": False,
                    "fallback_dedup_mode": "structural_hash",
                    "param_similarity_unreliable": bool(metrics.get("param_similarity_unreliable")),
                    "strategy_instance_hash": candidate_strategy_hash,
                    "tested_object_hash": candidate_tested_hash,
                    "matched_strategy_id": existing_item.get("id"),
                    "matched_name": existing_item.get("name") or existing_item.get("strategy_type"),
                    "matched_status": existing_item.get("status"),
                }, metrics
            param_similarity = self._param_sim(candidate_params, existing_params)
            target_overlap = self._target_overlap(candidate, existing_item)
            material_target_divergence = self._has_material_target_divergence(candidate, existing_item, target_overlap)
            tag_overlap = self._tag_overlap(candidate, existing_item)
            existing_dedup = dict(existing_item.get("dedup_result") or {})
            if tag_overlap > 0:
                metrics["coarse_tag_hit_count"] += 1
            if target_overlap is not None and target_overlap > 0:
                metrics["coarse_target_hit_count"] += 1
            effective_similarity = self._effective_similarity(param_similarity, target_overlap)
            match = {
                "matched_strategy_id": existing_item.get("id") or existing_dedup.get("matched_strategy_id"),
                "matched_name": (
                    existing_item.get("name")
                    or existing_dedup.get("matched_name")
                    or existing_item.get("strategy_type")
                ),
                "matched_status": existing_item.get("status") or existing_dedup.get("matched_status"),
                "param_similarity": round(param_similarity, 4),
                "target_overlap": target_overlap,
                "effective_similarity": round(effective_similarity, 4),
            }
            if best_match is None or effective_similarity > best_match.get("effective_similarity", 0):
                best_match = match
            decision: Optional[dict[str, Any]] = None
            decision_detail: dict[str, Any] = {}
            if not material_target_divergence:
                decision = self._evaluate_existing_match_decision(candidate, match, existing_item)
                decision_detail = self._decision_detail(decision)
                semantic_result = self._semantic_result_from_decision(candidate, match, existing_item, decision)
                if semantic_result is not None:
                    semantic_priority, semantic_detail = semantic_result
                    if semantic_match_priority is None or semantic_priority > semantic_match_priority:
                        semantic_match_priority = semantic_priority
                        semantic_match = semantic_detail
            if effective_similarity >= self.THRESHOLD and not material_target_divergence:
                overlap_text = f", 目标池重合度 {target_overlap:.4f}" if target_overlap is not None else ""
                if decision is None:
                    decision = self._evaluate_existing_match_decision(candidate, match, existing_item)
                    decision_detail = self._decision_detail(decision)
                if decision.get("refresh_existing"):
                    return {
                        "duplicate": False,
                        "refresh_existing": True,
                        "duplicate_level": "refresh_existing",
                        "match_type": "parameter",
                        "refresh_mode": "refresh_metrics_only",
                        "reason": f"综合相似度 {effective_similarity:.4f} ≥ 阈值 {self.THRESHOLD:.2f}（参数 {param_similarity:.4f}{overlap_text}），命中已有策略并转为刷新复用",
                        "threshold": self.THRESHOLD,
                        "vector_threshold": self.VECTOR_THRESHOLD,
                        "vector_checked": False,
                        "task_signature": self._candidate_task_signature(candidate),
                        **decision_detail,
                        **match,
                    }, metrics
                if decision.get("spawn_revision_from_existing"):
                    return {
                        "duplicate": False,
                        "refresh_existing": False,
                        "duplicate_level": "spawn_revision_from_existing",
                        "match_type": "parameter",
                        "refresh_mode": "spawn_revision_from_existing",
                        "parent_strategy_id": existing_item.get("id"),
                        "reason": (
                            f"综合相似度 {effective_similarity:.4f} ≥ 阈值 {self.THRESHOLD:.2f}，"
                            f"但已识别为策略对象变更（{decision.get('refresh_decision_basis') or 'revision'}），转为基于已有策略派生新实验"
                        ),
                        "threshold": self.THRESHOLD,
                        "vector_threshold": self.VECTOR_THRESHOLD,
                        "vector_checked": False,
                        "task_signature": self._candidate_task_signature(candidate),
                        **decision_detail,
                        **match,
                    }, metrics
                return {
                    "duplicate": True,
                    "duplicate_level": "parameter",
                    "match_type": "parameter",
                    "refresh_mode": None,
                    "reason": f"综合相似度 {effective_similarity:.4f} ≥ 阈值 {self.THRESHOLD:.2f}（参数 {param_similarity:.4f}{overlap_text}）",
                    "threshold": self.THRESHOLD,
                    "vector_threshold": self.VECTOR_THRESHOLD,
                    "vector_checked": False,
                    "task_signature": self._candidate_task_signature(candidate),
                    **decision_detail,
                    **match,
                }, metrics
            if effective_similarity >= self.VECTOR_TRIGGER_THRESHOLD:
                suspicious.append({
                    "existing_item": existing_item,
                    "param_similarity": round(param_similarity, 4),
                    "target_overlap": target_overlap,
                    "tag_overlap": round(tag_overlap, 4),
                    "effective_similarity": round(effective_similarity, 4),
                })

        metrics["coarse_candidate_count"] = len(suspicious)
        if semantic_match is not None:
            return semantic_match, metrics
        vector_candidates = self._select_vector_candidates(suspicious)
        metrics["vector_candidate_count"] = len(vector_candidates)
        metrics["vector_candidate_trimmed_count"] = max(0, len(suspicious) - len(vector_candidates))
        vector_detail = await self._vector_check(candidate, vector_candidates, db) if vector_candidates else None
        resolved_vector_threshold = self.VECTOR_THRESHOLD
        vector_keep_reason: Optional[str] = None
        if vector_detail:
            vector_similarity = float(vector_detail.get("similarity") or 0.0)
            param_similarity = float(vector_detail.get("param_similarity") or 0.0)
            target_overlap = vector_detail.get("target_overlap")
            has_candidate_universe = bool(_extract_target_codes_from_payload(candidate, limit=20))
            if has_candidate_universe and target_overlap is not None and target_overlap < 0.8:
                vector_keep_reason = (
                    f"目标池重合度 {target_overlap:.4f} < 0.80，保留为独立候选"
                )
                return {
                    "duplicate": False,
                    "refresh_existing": False,
                    "duplicate_level": "unique",
                    "match_type": None,
                    "refresh_mode": None,
                    "reason": vector_keep_reason,
                    "threshold": self.THRESHOLD,
                    "vector_threshold": self.VECTOR_THRESHOLD,
                    "vector_checked": True,
                    "param_similarity": round(param_similarity, 4),
                    "target_overlap": target_overlap,
                    "effective_similarity": round(vector_detail.get("effective_similarity", 0.0), 4),
                    "vector_similarity": round(vector_similarity, 4),
                    "vector_backend": vector_detail.get("backend"),
                    "matched_strategy_id": vector_detail.get("matched_strategy_id"),
                    "matched_name": vector_detail.get("matched_name"),
                    "matched_status": vector_detail.get("matched_status"),
                }, metrics
            require_param_confirmation = False
            if has_candidate_universe and target_overlap is None:
                resolved_vector_threshold = max(self.VECTOR_THRESHOLD, 0.98)
                require_param_confirmation = True
            vector_confirmed = vector_similarity >= resolved_vector_threshold
            if require_param_confirmation:
                vector_confirmed = vector_confirmed and param_similarity >= self.THRESHOLD
            if vector_confirmed:
                if require_param_confirmation:
                    reason = (
                        f"行为向量相似度 {vector_similarity:.4f} ≥ 阈值 {resolved_vector_threshold:.2f}，"
                        f"且目标池缺失场景下参数相似度 {param_similarity:.4f} ≥ {self.THRESHOLD:.2f}"
                    )
                else:
                    reason = f"行为向量相似度 {vector_similarity:.4f} ≥ 阈值 {resolved_vector_threshold:.2f}"
                return {
                    "duplicate": True,
                    "duplicate_level": "vector",
                    "match_type": "vector",
                    "refresh_mode": None,
                    "reason": reason,
                    "threshold": self.THRESHOLD,
                    "vector_threshold": resolved_vector_threshold,
                    "vector_checked": True,
                    "param_similarity": round(param_similarity, 4),
                    "target_overlap": target_overlap,
                    "effective_similarity": round(vector_detail.get("effective_similarity", 0.0), 4),
                    "vector_similarity": round(vector_similarity, 4),
                    "vector_backend": vector_detail.get("backend"),
                    "matched_strategy_id": vector_detail.get("matched_strategy_id"),
                    "matched_name": vector_detail.get("matched_name"),
                    "matched_status": vector_detail.get("matched_status"),
                }, metrics
            if require_param_confirmation and vector_similarity >= self.VECTOR_THRESHOLD:
                vector_keep_reason = (
                    f"行为向量相似但命中策略缺少目标池信息，参数相似度 {param_similarity:.4f} < {self.THRESHOLD:.2f}，暂不判重"
                )

        return {
            "duplicate": False,
            "refresh_existing": False,
            "duplicate_level": "unique",
            "match_type": None,
            "refresh_mode": None,
            "reason": vector_keep_reason or "未命中重复策略",
            "threshold": self.THRESHOLD,
            "vector_threshold": resolved_vector_threshold,
            "vector_checked": vector_detail is not None,
            "param_similarity": round((vector_detail or best_match or {}).get("param_similarity", 0.0), 4),
            "target_overlap": (vector_detail or best_match or {}).get("target_overlap"),
            "effective_similarity": round((vector_detail or best_match or {}).get("effective_similarity", 0.0), 4),
            "vector_similarity": round((vector_detail or {}).get("similarity", 0.0), 4),
            "vector_backend": (vector_detail or {}).get("backend"),
            "fallback_dedup_mode": "structural_hash" if not vector_detail else None,
            "param_similarity_unreliable": bool(metrics.get("param_similarity_unreliable")),
            "matched_strategy_id": (vector_detail or best_match or {}).get("matched_strategy_id"),
            "matched_name": (vector_detail or best_match or {}).get("matched_name"),
            "matched_status": (vector_detail or best_match or {}).get("matched_status"),
        }, metrics

    async def _prewarm_candidate_behaviors(self, candidates: List[dict], db) -> None:
        payloads = [
            (str(item.get("strategy_type") or "").strip(), self._normalize_params(item.get("params")))
            for item in list(candidates or [])
            if str(item.get("strategy_type") or "").strip()
        ]
        if payloads:
            unique_payloads: List[Tuple[str, dict]] = []
            seen_keys: set[str] = set()
            for strategy_type, params in payloads:
                cache_key = self._behavior_cache_key(strategy_type, params)
                if cache_key in seen_keys:
                    continue
                seen_keys.add(cache_key)
                unique_payloads.append((strategy_type, params))
            timeout_sec = self._resolve_prewarm_timeout_sec()
            try:
                await asyncio.wait_for(
                    self._bounded_behavior_gather(unique_payloads, db),
                    timeout=timeout_sec,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "deduplicator: prewarm timed out for %s payloads after %.2fs; continuing without full behavior cache",
                    len(unique_payloads),
                    timeout_sec,
                )

    @staticmethod
    def _normalize_params(value: object) -> dict:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except Exception:
                return {}
            return dict(parsed) if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _behavior_cache_key(strategy_type: str, params: Optional[dict]) -> str:
        return f"{strategy_type}:{json.dumps(params or {}, sort_keys=True, ensure_ascii=False, default=str)}"

    @classmethod
    def _resolve_timeout_sec(cls, setting_name: str, default: float) -> float:
        try:
            resolved = float(_compat_setting(setting_name, default) or default)
        except (TypeError, ValueError):
            return float(default)
        return float(default) if resolved <= 0 else resolved
