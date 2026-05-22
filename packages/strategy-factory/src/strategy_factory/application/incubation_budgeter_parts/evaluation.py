    @classmethod
    def _is_exploration_candidate(
        cls,
        candidate: dict[str, Any],
        *,
        dominant_families: set[str],
        active_family_names: set[str],
    ) -> bool:
        family_name = cls._candidate_family(candidate)
        if family_name not in dominant_families:
            return True
        if family_name not in active_family_names:
            return True
        params = dict(candidate.get("params") or {})
        candidate_provenance = dict(params.get("candidate_provenance") or {})
        registry_stage = str(
            params.get("candidate_registry_stage")
            or candidate.get("candidate_registry_stage")
            or candidate_provenance.get("candidate_registry_stage")
            or ""
        ).strip().lower()
        return registry_stage not in {"champion", "challenger", "governed"}

    @classmethod
    def plan(
        cls,
        candidates: list[dict[str, Any]],
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        formal_slots = max(1, int(FACTORY_INCUBATION_FORMAL_SLOT_COUNT))
        observe_slots = max(0, int(FACTORY_INCUBATION_OBSERVE_SLOT_COUNT))
        total_budget = formal_slots + observe_slots
        if not candidates:
            return {
                "plans": {},
                "summary": {
                    "formal_slots": formal_slots,
                    "observe_slots": observe_slots,
                    "exploration_reserved_slots": 0,
                    "track_counts": {
                        "formal_incubation": 0,
                        "observe_incubation": 0,
                        "deferred_budget_queue": 0,
                    },
                    "family_counts": {},
                    "dominant_families": [],
                },
            }

        family_counts: dict[str, int] = {}
        family_best_scores: dict[str, float] = {}
        budget_feedback_root = cls._resolve_budget_feedback_root(snapshot)
        feedback_family_names: set[str] = set()
        feedback_target_pool_ids: set[str] = set()
        feedback_generator_modes: set[str] = set()
        feedback_candidate_count = 0
        feedback_budget_multiplier_values: list[float] = []
        feedback_priority_adjustment_values: list[float] = []
        feedback_skill_budget_multiplier_values: list[float] = []
        feedback_skill_priority_adjustment_values: list[float] = []
        feedback_paper_skill_lcb_values: list[float] = []
        feedback_paper_recent_skill_lcb_values: list[float] = []
        feedback_paper_stability_gap_values: list[float] = []
        feedback_paper_coverage_ratio_values: list[float] = []
        feedback_execution_conversion_efficiency_values: list[float] = []
        feedback_budget_promoted_count = 0
        feedback_budget_constrained_count = 0
        feedback_budget_action_counts: dict[str, int] = {}
        feedback_dual_axis_action_count = 0
        feedback_execution_optimization_queue_count = 0
        feedback_small_budget_observe_count = 0
        feedback_prioritize_scale_count = 0
        feedback_cool_or_freeze_count = 0
        feedback_controlled_count = 0
        feedback_cooldown_count = 0
        feedback_suppressed_count = 0
        feedback_freeze_count = 0
        feedback_skill_budget_promoted_count = 0
        feedback_skill_budget_constrained_count = 0
        feedback_skill_controlled_count = 0
        feedback_skill_cooldown_count = 0
        feedback_skill_suppressed_count = 0
        feedback_skill_freeze_count = 0
        feedback_target_pool_freeze_count = 0
        feedback_generator_mode_freeze_count = 0
        feedback_skill_target_pool_freeze_count = 0
        feedback_skill_generator_mode_freeze_count = 0
        active_family_names = {
            str(item or "").strip().lower()
            for item in list(((snapshot.get("factor_research") or {}).get("summary") or {}).get("active_family_names") or [])
            if str(item or "").strip()
        }
        entries: list[dict[str, Any]] = []
        for candidate in list(candidates or []):
            family_name = cls._candidate_family(candidate)
            feedback_payload = cls._candidate_feedback(
                candidate,
                snapshot,
                budget_feedback_root=budget_feedback_root,
            )
            feedback_metrics = dict(feedback_payload.get("metrics") or {})
            feedback_scope = dict(feedback_payload.get("scope") or {})
            score = cls._priority_score(
                candidate,
                snapshot,
                budget_feedback_root=budget_feedback_root,
            )
            family_counts[family_name] = family_counts.get(family_name, 0) + 1
            family_best_scores[family_name] = max(score, family_best_scores.get(family_name, score))
            if bool(feedback_scope.get("feedback_available")):
                feedback_candidate_count += 1
                feedback_family_names.add(family_name)
                target_pool_id = str(feedback_scope.get("target_pool_id") or "").strip()
                generator_mode = str(feedback_scope.get("generator_mode") or "").strip().lower()
                if target_pool_id and bool(feedback_scope.get("target_pool_feedback_available")):
                    feedback_target_pool_ids.add(target_pool_id)
                if generator_mode and bool(feedback_scope.get("generator_mode_feedback_available")):
                    feedback_generator_modes.add(generator_mode)
                feedback_budget_multiplier = cls._safe_float(feedback_metrics.get("budget_multiplier"), 1.0)
                feedback_priority_adjustment = cls._safe_float(feedback_metrics.get("priority_adjustment"))
                feedback_skill_budget_multiplier = cls._safe_float(
                    feedback_metrics.get("skill_budget_multiplier"),
                    1.0,
                )
                feedback_skill_priority_adjustment = cls._safe_float(
                    feedback_metrics.get("skill_priority_adjustment")
                )
                feedback_budget_multiplier_values.append(feedback_budget_multiplier)
                feedback_priority_adjustment_values.append(feedback_priority_adjustment)
                feedback_skill_budget_multiplier_values.append(feedback_skill_budget_multiplier)
                feedback_skill_priority_adjustment_values.append(feedback_skill_priority_adjustment)
                feedback_paper_skill_lcb_values.append(
                    cls._safe_float(feedback_metrics.get("paper_skill_lcb"))
                )
                feedback_paper_recent_skill_lcb_values.append(
                    cls._safe_float(feedback_metrics.get("paper_recent_skill_lcb"))
                )
                feedback_paper_stability_gap_values.append(
                    cls._safe_float(feedback_metrics.get("paper_stability_gap"))
                )
                feedback_paper_coverage_ratio_values.append(
                    cls._safe_float(feedback_metrics.get("paper_coverage_ratio"), 1.0)
                )
                if bool(feedback_metrics.get("execution_conversion_efficiency_available")):
                    feedback_execution_conversion_efficiency_values.append(
                        cls._safe_float(
                            feedback_metrics.get("execution_conversion_efficiency")
                        )
                    )
                budget_action = str(
                    feedback_metrics.get("budget_feedback_action") or ""
                ).strip().lower()
                if budget_action:
                    feedback_dual_axis_action_count += 1
                    feedback_budget_action_counts[budget_action] = (
                        feedback_budget_action_counts.get(budget_action, 0) + 1
                    )
                if bool(feedback_metrics.get("execution_optimization_queue")):
                    feedback_execution_optimization_queue_count += 1
                if bool(feedback_metrics.get("small_budget_observe")):
                    feedback_small_budget_observe_count += 1
                if bool(feedback_metrics.get("prioritize_scale")):
                    feedback_prioritize_scale_count += 1
                if bool(feedback_metrics.get("cool_or_freeze")):
                    feedback_cool_or_freeze_count += 1
                if feedback_budget_multiplier > 1.02 or feedback_priority_adjustment > 0.5:
                    feedback_budget_promoted_count += 1
                if feedback_budget_multiplier < 0.98 or feedback_priority_adjustment < -0.5:
                    feedback_budget_constrained_count += 1
                if feedback_skill_budget_multiplier > 1.02 or feedback_skill_priority_adjustment > 0.5:
                    feedback_skill_budget_promoted_count += 1
                if feedback_skill_budget_multiplier < 0.98 or feedback_skill_priority_adjustment < -0.5:
                    feedback_skill_budget_constrained_count += 1
            control_mode = str(feedback_metrics.get("control_mode") or "").strip().lower()
            skill_control_mode = str(feedback_metrics.get("skill_control_mode") or "").strip().lower()
            if control_mode and control_mode != "normal":
                feedback_controlled_count += 1
            if control_mode == "cooldown":
                feedback_cooldown_count += 1
            elif control_mode == "suppress":
                feedback_suppressed_count += 1
            elif control_mode == "freeze":
                feedback_freeze_count += 1
            if skill_control_mode and skill_control_mode != "normal":
                feedback_skill_controlled_count += 1
            if skill_control_mode == "cooldown":
                feedback_skill_cooldown_count += 1
            elif skill_control_mode == "suppress":
                feedback_skill_suppressed_count += 1
            elif skill_control_mode == "freeze":
                feedback_skill_freeze_count += 1
            if bool(feedback_metrics.get("target_pool_freeze_active")):
                feedback_target_pool_freeze_count += 1
            if bool(feedback_metrics.get("generator_mode_freeze_active")):
                feedback_generator_mode_freeze_count += 1
            if bool(feedback_metrics.get("skill_target_pool_freeze_active")):
                feedback_skill_target_pool_freeze_count += 1
            if bool(feedback_metrics.get("skill_generator_mode_freeze_active")):
                feedback_skill_generator_mode_freeze_count += 1
            entries.append(
                {
                    "marker": id(candidate),
                    "candidate": candidate,
                    "family": family_name,
                    "priority_score": score,
                    "feedback_metrics": feedback_metrics,
                    "feedback_scope": feedback_scope,
                    "feedback_budget_multiplier": cls._safe_float(
                        feedback_metrics.get("budget_multiplier"),
                        1.0,
                    ),
                    "feedback_priority_adjustment": cls._safe_float(
                        feedback_metrics.get("priority_adjustment")
                    ),
                    "feedback_failure_penalty_adjustment": cls._safe_float(
                        feedback_metrics.get("failure_penalty_adjustment")
                    ),
                    "feedback_legacy_budget_multiplier": cls._safe_float(
                        feedback_metrics.get("legacy_budget_multiplier"),
                        1.0,
                    ),
                    "feedback_legacy_priority_adjustment": cls._safe_float(
                        feedback_metrics.get("legacy_priority_adjustment")
                    ),
                    "feedback_skill_budget_multiplier": cls._safe_float(
                        feedback_metrics.get("skill_budget_multiplier"),
                        1.0,
                    ),
                    "feedback_skill_priority_adjustment": cls._safe_float(
                        feedback_metrics.get("skill_priority_adjustment")
                    ),
                    "feedback_skill_failure_penalty_adjustment": cls._safe_float(
                        feedback_metrics.get("skill_failure_penalty_adjustment")
                    ),
                    "feedback_control_mode": control_mode or "normal",
                    "feedback_legacy_control_mode": str(
                        feedback_metrics.get("legacy_control_mode") or control_mode or "normal"
                    ),
                    "feedback_skill_control_mode": skill_control_mode or "normal",
                    "feedback_control_reasons": list(feedback_metrics.get("control_reasons") or []),
                    "feedback_legacy_control_reasons": list(
                        feedback_metrics.get("legacy_control_reasons") or []
                    ),
                    "feedback_skill_control_reasons": list(
                        feedback_metrics.get("skill_control_reasons") or []
                    ),
                    "feedback_cooldown_active": bool(feedback_metrics.get("cooldown_active")),
                    "feedback_suppressed": bool(feedback_metrics.get("suppressed")),
                    "feedback_family_freeze_active": bool(feedback_metrics.get("family_freeze_active")),
                    "feedback_target_pool_freeze_active": bool(feedback_metrics.get("target_pool_freeze_active")),
                    "feedback_generator_mode_freeze_active": bool(feedback_metrics.get("generator_mode_freeze_active")),
                    "feedback_skill_cooldown_active": bool(
                        feedback_metrics.get("skill_cooldown_active")
                    ),
                    "feedback_skill_suppressed": bool(feedback_metrics.get("skill_suppressed")),
                    "feedback_skill_family_freeze_active": bool(
                        feedback_metrics.get("skill_family_freeze_active")
                    ),
                    "feedback_skill_target_pool_freeze_active": bool(
                        feedback_metrics.get("skill_target_pool_freeze_active")
                    ),
                    "feedback_skill_generator_mode_freeze_active": bool(
                        feedback_metrics.get("skill_generator_mode_freeze_active")
                    ),
                    "feedback_paper_skill_lcb": cls._safe_float(
                        feedback_metrics.get("paper_skill_lcb")
                    ),
                    "feedback_paper_recent_skill_lcb": cls._safe_float(
                        feedback_metrics.get("paper_recent_skill_lcb")
                    ),
                    "feedback_paper_stability_gap": cls._safe_float(
                        feedback_metrics.get("paper_stability_gap")
                    ),
                    "feedback_paper_coverage_ratio": cls._safe_float(
                        feedback_metrics.get("paper_coverage_ratio"),
                        1.0,
                    ),
                    "feedback_execution_conversion_efficiency": (
                        cls._safe_float(feedback_metrics.get("execution_conversion_efficiency"))
                        if feedback_metrics.get("execution_conversion_efficiency_available")
                        else None
                    ),
                    "feedback_execution_conversion_efficiency_available": bool(
                        feedback_metrics.get("execution_conversion_efficiency_available")
                    ),
                    "feedback_budget_action": feedback_metrics.get("budget_feedback_action"),
                    "feedback_budget_action_applied": bool(
                        feedback_metrics.get("budget_action_applied")
                    ),
                    "feedback_prediction_axis": feedback_metrics.get("prediction_axis"),
                    "feedback_execution_axis": feedback_metrics.get("execution_axis"),
                    "feedback_retain_family": bool(feedback_metrics.get("retain_family")),
                    "feedback_reduce_budget": bool(feedback_metrics.get("reduce_budget")),
                    "feedback_execution_optimization_queue": bool(
                        feedback_metrics.get("execution_optimization_queue")
                    ),
                    "feedback_small_budget_observe": bool(
                        feedback_metrics.get("small_budget_observe")
                    ),
                    "feedback_prioritize_scale": bool(
                        feedback_metrics.get("prioritize_scale")
                    ),
                    "feedback_cool_or_freeze": bool(feedback_metrics.get("cool_or_freeze")),
                    "feedback_no_expansion": bool(feedback_metrics.get("no_expansion")),
                    "feedback_effective_signal": str(
                        feedback_metrics.get("effective_feedback_signal")
                        or "legacy_paper_hit_ratio"
                    ),
                }
            )

        dominant_family_pairs = sorted(
            family_best_scores.items(),
            key=lambda item: (-float(item[1]), -int(family_counts.get(item[0]) or 0), item[0]),
        )
        dominant_families = {family for family, _score in dominant_family_pairs[:3]}
        sorted_entries = sorted(
            entries,
            key=lambda item: (-float(item["priority_score"]), item["family"], item["marker"]),
        )
        selectable_entries = [
            entry
            for entry in sorted_entries
            if str(entry.get("feedback_control_mode") or "normal").strip().lower() == "normal"
        ]
        exploration_reserved_slots = (
            min(total_budget, max(1, int(math.ceil(total_budget * FACTORY_INCUBATION_EXPLORATION_RATIO))))
            if total_budget > 0 and FACTORY_INCUBATION_EXPLORATION_RATIO > 0.0
            else 0
        )
        formal_family_cap = max(1, int(math.ceil(formal_slots * 0.45)))
        observe_family_cap = max(1, int(math.ceil(max(observe_slots, 1) * 0.55)))

        selected_formal: list[dict[str, Any]] = []
        selected_observe: list[dict[str, Any]] = []
        family_track_counts: dict[str, dict[str, int]] = {}
        selected_markers: set[int] = set()

        def _select_with_cap(
            target: list[dict[str, Any]],
            *,
            limit: int,
            family_cap: int,
        ) -> None:
            for entry in selectable_entries:
                if len(target) >= limit:
                    break
                marker = int(entry["marker"])
                if marker in selected_markers:
                    continue
                family_name = str(entry["family"])
                track_family_counts = family_track_counts.setdefault(family_name, {})
                if int(track_family_counts.get("selected") or 0) >= family_cap:
                    continue
                target.append(entry)
                selected_markers.add(marker)
                track_family_counts["selected"] = int(track_family_counts.get("selected") or 0) + 1
            for entry in selectable_entries:
                if len(target) >= limit:
                    break
                marker = int(entry["marker"])
                if marker in selected_markers:
                    continue
                family_name = str(entry["family"])
                track_family_counts = family_track_counts.setdefault(family_name, {})
                target.append(entry)
                selected_markers.add(marker)
                track_family_counts["selected"] = int(track_family_counts.get("selected") or 0) + 1

        _select_with_cap(selected_formal, limit=formal_slots, family_cap=formal_family_cap)
        _select_with_cap(selected_observe, limit=observe_slots, family_cap=observe_family_cap)

        selected_combined = [*selected_formal, *selected_observe]
        selected_exploration_count = sum(
            1
            for entry in selected_combined
            if cls._is_exploration_candidate(
                dict(entry.get("candidate") or {}),
                dominant_families=dominant_families,
                active_family_names=active_family_names,
            )
        )
        if exploration_reserved_slots > selected_exploration_count and observe_slots > 0:
            exploration_pool = [
                entry
                for entry in selectable_entries
                if int(entry["marker"]) not in selected_markers
                and cls._is_exploration_candidate(
                    dict(entry.get("candidate") or {}),
                    dominant_families=dominant_families,
                    active_family_names=active_family_names,
                )
            ]
            # PR-S11: 按 priority_score 升序找替换目标（最小质量损失原则），
            # 取代旧的"末尾反向找第一个非探索候选"
            def _entry_score(entry: dict[str, Any]) -> float:
                try:
                    return float(entry.get("priority_score") or 0.0)
                except (TypeError, ValueError):
                    return 0.0
            while (
                exploration_pool
                and selected_exploration_count < exploration_reserved_slots
                and selected_observe
            ):
                promoted = exploration_pool.pop(0)
                # 在 selected_observe 中找所有"非探索"候选，按 priority_score 升序选最低
                non_exploration_indices = [
                    index
                    for index in range(len(selected_observe))
                    if not cls._is_exploration_candidate(
                        dict(selected_observe[index].get("candidate") or {}),
                        dominant_families=dominant_families,
                        active_family_names=active_family_names,
                    )
                ]
                if not non_exploration_indices:
                    break
                replaced_index = min(
                    non_exploration_indices,
                    key=lambda idx: _entry_score(selected_observe[idx]),
                )
                # 仅当 promoted 的分数高于 replaced 时才替换；否则放弃，避免反向降级
                if _entry_score(promoted) < _entry_score(selected_observe[replaced_index]):
                    break
                removed = selected_observe[replaced_index]
                selected_markers.discard(int(removed["marker"]))
                selected_observe[replaced_index] = promoted
                selected_markers.add(int(promoted["marker"]))
                selected_exploration_count += 1

        plans: dict[int, dict[str, Any]] = {}
        track_counts = {
            "formal_incubation": 0,
            "observe_incubation": 0,
            "deferred_budget_queue": 0,
        }
        rank = 0
        for track_name, bucket in (
            ("formal_incubation", selected_formal),
            ("observe_incubation", selected_observe),
        ):
            for entry in bucket:
                rank += 1
                candidate = dict(entry.get("candidate") or {})
                plan = {
                    "track": track_name,
                    "rank": rank,
                    "priority_score": float(entry.get("priority_score") or 0.0),
                    "family": entry.get("family"),
                    "feedback_metrics": dict(entry.get("feedback_metrics") or {}),
                    "feedback_scope": dict(entry.get("feedback_scope") or {}),
                    "feedback_budget_multiplier": float(entry.get("feedback_budget_multiplier") or 1.0),
                    "feedback_priority_adjustment": float(entry.get("feedback_priority_adjustment") or 0.0),
                    "feedback_failure_penalty_adjustment": float(
                        entry.get("feedback_failure_penalty_adjustment") or 0.0
                    ),
                    "feedback_control_mode": str(entry.get("feedback_control_mode") or "normal"),
                    "feedback_legacy_control_mode": str(
                        entry.get("feedback_legacy_control_mode") or "normal"
                    ),
                    "feedback_skill_control_mode": str(
                        entry.get("feedback_skill_control_mode") or "normal"
                    ),
                    "feedback_control_reasons": list(entry.get("feedback_control_reasons") or []),
                    "feedback_legacy_control_reasons": list(
                        entry.get("feedback_legacy_control_reasons") or []
                    ),
                    "feedback_skill_control_reasons": list(
                        entry.get("feedback_skill_control_reasons") or []
                    ),
                    "feedback_cooldown_active": bool(entry.get("feedback_cooldown_active")),
                    "feedback_suppressed": bool(entry.get("feedback_suppressed")),
                    "feedback_family_freeze_active": bool(entry.get("feedback_family_freeze_active")),
                    "feedback_target_pool_freeze_active": bool(entry.get("feedback_target_pool_freeze_active")),
                    "feedback_generator_mode_freeze_active": bool(entry.get("feedback_generator_mode_freeze_active")),
                    "feedback_skill_cooldown_active": bool(
                        entry.get("feedback_skill_cooldown_active")
                    ),
                    "feedback_skill_suppressed": bool(entry.get("feedback_skill_suppressed")),
                    "feedback_skill_family_freeze_active": bool(
                        entry.get("feedback_skill_family_freeze_active")
                    ),
                    "feedback_skill_target_pool_freeze_active": bool(
                        entry.get("feedback_skill_target_pool_freeze_active")
                    ),
                    "feedback_skill_generator_mode_freeze_active": bool(
                        entry.get("feedback_skill_generator_mode_freeze_active")
                    ),
                    "feedback_legacy_budget_multiplier": cls._safe_float(
                        entry.get("feedback_legacy_budget_multiplier"),
                        1.0,
                    ),
                    "feedback_legacy_priority_adjustment": float(
                        entry.get("feedback_legacy_priority_adjustment") or 0.0
                    ),
                    "feedback_skill_budget_multiplier": cls._safe_float(
                        entry.get("feedback_skill_budget_multiplier"),
                        1.0,
                    ),
                    "feedback_skill_priority_adjustment": float(
                        entry.get("feedback_skill_priority_adjustment") or 0.0
                    ),
                    "feedback_skill_failure_penalty_adjustment": float(
                        entry.get("feedback_skill_failure_penalty_adjustment") or 0.0
                    ),
                    "feedback_paper_skill_lcb": cls._safe_float(
                        entry.get("feedback_paper_skill_lcb")
                    ),
                    "feedback_paper_recent_skill_lcb": cls._safe_float(
                        entry.get("feedback_paper_recent_skill_lcb")
                    ),
                    "feedback_paper_stability_gap": cls._safe_float(
                        entry.get("feedback_paper_stability_gap")
                    ),
                    "feedback_paper_coverage_ratio": cls._safe_float(
                        entry.get("feedback_paper_coverage_ratio"),
                        1.0,
                    ),
                    "feedback_execution_conversion_efficiency": entry.get(
                        "feedback_execution_conversion_efficiency"
                    ),
                    "feedback_execution_conversion_efficiency_available": bool(
                        entry.get("feedback_execution_conversion_efficiency_available")
                    ),
                    "feedback_budget_action": entry.get("feedback_budget_action"),
                    "feedback_budget_action_applied": bool(
                        entry.get("feedback_budget_action_applied")
                    ),
                    "feedback_prediction_axis": entry.get("feedback_prediction_axis"),
                    "feedback_execution_axis": entry.get("feedback_execution_axis"),
                    "feedback_retain_family": bool(entry.get("feedback_retain_family")),
                    "feedback_reduce_budget": bool(entry.get("feedback_reduce_budget")),
                    "feedback_execution_optimization_queue": bool(
                        entry.get("feedback_execution_optimization_queue")
                    ),
                    "feedback_small_budget_observe": bool(
                        entry.get("feedback_small_budget_observe")
                    ),
                    "feedback_prioritize_scale": bool(entry.get("feedback_prioritize_scale")),
                    "feedback_cool_or_freeze": bool(entry.get("feedback_cool_or_freeze")),
                    "feedback_no_expansion": bool(entry.get("feedback_no_expansion")),
                    "feedback_effective_signal": str(
                        entry.get("feedback_effective_signal") or "legacy_paper_hit_ratio"
                    ),
                    "exploration_candidate": cls._is_exploration_candidate(
                        candidate,
                        dominant_families=dominant_families,
                        active_family_names=active_family_names,
                    ),
                }
                plans[int(entry["marker"])] = plan
                track_counts[track_name] += 1

        for entry in sorted_entries:
            marker = int(entry["marker"])
            if marker in plans:
                continue
            rank += 1
            plans[marker] = {
                "track": "deferred_budget_queue",
                "rank": rank,
                "priority_score": float(entry.get("priority_score") or 0.0),
                "family": entry.get("family"),
                "feedback_metrics": dict(entry.get("feedback_metrics") or {}),
                "feedback_scope": dict(entry.get("feedback_scope") or {}),
                "feedback_budget_multiplier": float(entry.get("feedback_budget_multiplier") or 1.0),
                "feedback_priority_adjustment": float(entry.get("feedback_priority_adjustment") or 0.0),
                "feedback_failure_penalty_adjustment": float(
                    entry.get("feedback_failure_penalty_adjustment") or 0.0
                ),
                "feedback_control_mode": str(entry.get("feedback_control_mode") or "normal"),
                "feedback_legacy_control_mode": str(
                    entry.get("feedback_legacy_control_mode") or "normal"
                ),
                "feedback_skill_control_mode": str(
                    entry.get("feedback_skill_control_mode") or "normal"
                ),
                "feedback_control_reasons": list(entry.get("feedback_control_reasons") or []),
                "feedback_legacy_control_reasons": list(
                    entry.get("feedback_legacy_control_reasons") or []
                ),
                "feedback_skill_control_reasons": list(
                    entry.get("feedback_skill_control_reasons") or []
                ),
                "feedback_cooldown_active": bool(entry.get("feedback_cooldown_active")),
                "feedback_suppressed": bool(entry.get("feedback_suppressed")),
                "feedback_family_freeze_active": bool(entry.get("feedback_family_freeze_active")),
                "feedback_target_pool_freeze_active": bool(entry.get("feedback_target_pool_freeze_active")),
                "feedback_generator_mode_freeze_active": bool(entry.get("feedback_generator_mode_freeze_active")),
                "feedback_skill_cooldown_active": bool(
                    entry.get("feedback_skill_cooldown_active")
                ),
                "feedback_skill_suppressed": bool(entry.get("feedback_skill_suppressed")),
                "feedback_skill_family_freeze_active": bool(
                    entry.get("feedback_skill_family_freeze_active")
                ),
                "feedback_skill_target_pool_freeze_active": bool(
                    entry.get("feedback_skill_target_pool_freeze_active")
                ),
                "feedback_skill_generator_mode_freeze_active": bool(
                    entry.get("feedback_skill_generator_mode_freeze_active")
                ),
                "feedback_legacy_budget_multiplier": cls._safe_float(
                    entry.get("feedback_legacy_budget_multiplier"),
                    1.0,
                ),
                "feedback_legacy_priority_adjustment": float(
                    entry.get("feedback_legacy_priority_adjustment") or 0.0
                ),
                "feedback_skill_budget_multiplier": cls._safe_float(
                    entry.get("feedback_skill_budget_multiplier"),
                    1.0,
                ),
                "feedback_skill_priority_adjustment": float(
                    entry.get("feedback_skill_priority_adjustment") or 0.0
                ),
                "feedback_skill_failure_penalty_adjustment": float(
                    entry.get("feedback_skill_failure_penalty_adjustment") or 0.0
                ),
                "feedback_paper_skill_lcb": cls._safe_float(
                    entry.get("feedback_paper_skill_lcb")
                ),
                "feedback_paper_recent_skill_lcb": cls._safe_float(
                    entry.get("feedback_paper_recent_skill_lcb")
                ),
                "feedback_paper_stability_gap": cls._safe_float(
                    entry.get("feedback_paper_stability_gap")
                ),
                "feedback_paper_coverage_ratio": cls._safe_float(
                    entry.get("feedback_paper_coverage_ratio"),
                    1.0,
                ),
                "feedback_execution_conversion_efficiency": entry.get(
                    "feedback_execution_conversion_efficiency"
                ),
                "feedback_execution_conversion_efficiency_available": bool(
                    entry.get("feedback_execution_conversion_efficiency_available")
                ),
                "feedback_budget_action": entry.get("feedback_budget_action"),
                "feedback_budget_action_applied": bool(
                    entry.get("feedback_budget_action_applied")
                ),
                "feedback_prediction_axis": entry.get("feedback_prediction_axis"),
                "feedback_execution_axis": entry.get("feedback_execution_axis"),
                "feedback_retain_family": bool(entry.get("feedback_retain_family")),
                "feedback_reduce_budget": bool(entry.get("feedback_reduce_budget")),
                "feedback_execution_optimization_queue": bool(
                    entry.get("feedback_execution_optimization_queue")
                ),
                "feedback_small_budget_observe": bool(
                    entry.get("feedback_small_budget_observe")
                ),
                "feedback_prioritize_scale": bool(entry.get("feedback_prioritize_scale")),
                "feedback_cool_or_freeze": bool(entry.get("feedback_cool_or_freeze")),
                "feedback_no_expansion": bool(entry.get("feedback_no_expansion")),
                "feedback_effective_signal": str(
                    entry.get("feedback_effective_signal") or "legacy_paper_hit_ratio"
                ),
                "exploration_candidate": cls._is_exploration_candidate(
                    dict(entry.get("candidate") or {}),
                    dominant_families=dominant_families,
                    active_family_names=active_family_names,
                ),
            }
            track_counts["deferred_budget_queue"] += 1

        return {
            "plans": plans,
            "summary": {
                "formal_slots": formal_slots,
                "observe_slots": observe_slots,
                "formal_family_cap": formal_family_cap,
                "observe_family_cap": observe_family_cap,
                "exploration_reserved_slots": exploration_reserved_slots,
                "exploration_selected_count": selected_exploration_count,
                "track_counts": track_counts,
                "family_counts": dict(sorted(family_counts.items(), key=lambda item: (-item[1], item[0]))),
                "dominant_families": [family for family, _score in dominant_family_pairs[:3]],
                "feedback_available": bool(budget_feedback_root),
                "feedback_candidate_count": feedback_candidate_count,
                "feedback_family_count": len(feedback_family_names),
                "feedback_target_pool_scope_count": len(feedback_target_pool_ids),
                "feedback_generator_mode_scope_count": len(feedback_generator_modes),
                "feedback_budget_multiplier_avg": round(
                    sum(feedback_budget_multiplier_values) / len(feedback_budget_multiplier_values),
                    4,
                )
                if feedback_budget_multiplier_values
                else 0.0,
                "feedback_priority_adjustment_avg": round(
                    sum(feedback_priority_adjustment_values) / len(feedback_priority_adjustment_values),
                    4,
                )
                if feedback_priority_adjustment_values
                else 0.0,
                "feedback_skill_budget_multiplier_avg": round(
                    sum(feedback_skill_budget_multiplier_values)
                    / len(feedback_skill_budget_multiplier_values),
                    4,
                )
                if feedback_skill_budget_multiplier_values
                else 0.0,
                "feedback_skill_priority_adjustment_avg": round(
                    sum(feedback_skill_priority_adjustment_values)
                    / len(feedback_skill_priority_adjustment_values),
                    4,
                )
                if feedback_skill_priority_adjustment_values
                else 0.0,
                "feedback_paper_skill_lcb_avg": round(
                    sum(feedback_paper_skill_lcb_values) / len(feedback_paper_skill_lcb_values),
                    4,
                )
                if feedback_paper_skill_lcb_values
                else 0.0,
                "feedback_paper_recent_skill_lcb_avg": round(
                    sum(feedback_paper_recent_skill_lcb_values)
                    / len(feedback_paper_recent_skill_lcb_values),
                    4,
                )
                if feedback_paper_recent_skill_lcb_values
                else 0.0,
                "feedback_paper_stability_gap_avg": round(
                    sum(feedback_paper_stability_gap_values)
                    / len(feedback_paper_stability_gap_values),
                    4,
                )
                if feedback_paper_stability_gap_values
                else 0.0,
                "feedback_paper_coverage_ratio_avg": round(
                    sum(feedback_paper_coverage_ratio_values)
                    / len(feedback_paper_coverage_ratio_values),
                    4,
                )
                if feedback_paper_coverage_ratio_values
                else 0.0,
                "feedback_execution_conversion_efficiency_avg": round(
                    sum(feedback_execution_conversion_efficiency_values)
                    / len(feedback_execution_conversion_efficiency_values),
                    4,
                )
                if feedback_execution_conversion_efficiency_values
                else 0.0,
                "feedback_budget_action_counts": feedback_budget_action_counts,
                "feedback_dual_axis_action_count": feedback_dual_axis_action_count,
                "feedback_execution_optimization_queue_count": (
                    feedback_execution_optimization_queue_count
                ),
                "feedback_small_budget_observe_count": feedback_small_budget_observe_count,
                "feedback_prioritize_scale_count": feedback_prioritize_scale_count,
                "feedback_cool_or_freeze_count": feedback_cool_or_freeze_count,
                "feedback_budget_promoted_count": feedback_budget_promoted_count,
                "feedback_budget_constrained_count": feedback_budget_constrained_count,
                "feedback_skill_budget_promoted_count": feedback_skill_budget_promoted_count,
                "feedback_skill_budget_constrained_count": feedback_skill_budget_constrained_count,
                "feedback_controlled_count": feedback_controlled_count,
                "feedback_cooldown_count": feedback_cooldown_count,
                "feedback_suppressed_count": feedback_suppressed_count,
                "feedback_freeze_count": feedback_freeze_count,
                "feedback_skill_controlled_count": feedback_skill_controlled_count,
                "feedback_skill_cooldown_count": feedback_skill_cooldown_count,
                "feedback_skill_suppressed_count": feedback_skill_suppressed_count,
                "feedback_skill_freeze_count": feedback_skill_freeze_count,
                "feedback_target_pool_freeze_count": feedback_target_pool_freeze_count,
                "feedback_generator_mode_freeze_count": feedback_generator_mode_freeze_count,
                "feedback_skill_target_pool_freeze_count": feedback_skill_target_pool_freeze_count,
                "feedback_skill_generator_mode_freeze_count": (
                    feedback_skill_generator_mode_freeze_count
                ),
                "priority_score_avg": round(
                    sum(float(item.get("priority_score") or 0.0) for item in sorted_entries) / len(sorted_entries),
                    4,
                )
                if sorted_entries
                else 0.0,
            },
        }
