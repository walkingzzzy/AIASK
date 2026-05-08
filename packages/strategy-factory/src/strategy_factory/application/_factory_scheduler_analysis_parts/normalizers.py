        def _build_task_source_counts(tasks: List[dict]) -> dict[str, int]:
            counts: dict[str, int] = {}
            for task in list(tasks or []):
                source = str((task or {}).get("task_source") or "unknown").strip() or "unknown"
                counts[source] = counts.get(source, 0) + 1
            return counts

        @staticmethod
        def _extract_cycle_candidates(cycle: dict) -> list[dict]:
            generation = dict((cycle or {}).get("generation") or {})
            candidates = generation.get("candidates")
            if isinstance(candidates, list):
                return list(candidates)
            return list((cycle or {}).get("candidates") or [])

        @staticmethod
        def _merge_explicit_stock_pool(base: Optional[dict], target_symbols: list[str]) -> dict:
            pool = dict(base or {})
            normalized = _normalize_target_codes(target_symbols, limit=12)
            if not normalized:
                return pool
            pool["selection_mode"] = pool.get("selection_mode") or "explicit"
            pool["symbols"] = normalized
            return pool

        @classmethod
        def _enrich_candidate_targeting(cls, candidate: Optional[dict], task: Optional[dict] = None) -> dict:
            item = dict(candidate or {})
            if not item:
                return {}

            base_task = dict(task or {})
            current_task = dict(item.get("research_task") or {})
            merged_task = {**base_task, **current_task}
            merged_task_event_context = {
                **dict(base_task.get("event_context") or {}),
                **dict(current_task.get("event_context") or {}),
            }
            if merged_task_event_context:
                merged_task["event_context"] = merged_task_event_context
            if merged_task:
                item["research_task"] = merged_task

            merged_event_context = {
                **merged_task_event_context,
                **dict(item.get("event_context") or {}),
            }
            if merged_event_context:
                item["event_context"] = merged_event_context

            target_symbols = _extract_target_codes_from_payload(item, limit=12)
            if not target_symbols:
                return item

            item["target_symbols"] = list(target_symbols)
            item["stock_pool"] = cls._merge_explicit_stock_pool(item.get("stock_pool"), target_symbols)

            params = dict(item.get("params") or {})
            if params:
                params["target_symbols"] = list(target_symbols)
                params["stock_pool"] = cls._merge_explicit_stock_pool(params.get("stock_pool"), target_symbols)
                if merged_task and not params.get("research_task"):
                    params["research_task"] = dict(merged_task)
                dsl = dict(params.get("dsl") or {})
                if dsl:
                    metadata = dict(dsl.get("metadata") or {})
                    metadata["target_symbols"] = list(target_symbols)
                    metadata["stock_pool"] = cls._merge_explicit_stock_pool(metadata.get("stock_pool"), target_symbols)
                    dsl["metadata"] = metadata
                    params["dsl"] = dsl
                item["params"] = params

            tags = list(item.get("tags") or [])
            if "targeted_universe" not in tags:
                item["tags"] = [*tags, "targeted_universe"]
            return apply_candidate_strategy_profile(item, research_task=merged_task or task)

        @staticmethod
        def _extract_cycle_experiments(cycle: dict) -> list[dict]:
            experiments = (cycle or {}).get("experiments")
            if isinstance(experiments, dict):
                return list(experiments.get("items") or [])
            if isinstance(experiments, list):
                return list(experiments)
            return list((cycle or {}).get("experiment_records") or [])

        @staticmethod
        def _extract_cycle_llm_generation(cycle: dict) -> dict:
            llm_generation = (cycle or {}).get("llm_generation")
            if isinstance(llm_generation, dict):
                return dict(llm_generation)
            generation = dict((cycle or {}).get("generation") or {})
            return dict(generation.get("llm_generation") or {})

        @classmethod
        def _extract_cycle_generated_count(cls, cycle: dict) -> int:
            value = (cycle or {}).get("generated_count")
            if value is None:
                value = dict((cycle or {}).get("generation") or {}).get("count")
            if value is None:
                value = len(cls._extract_cycle_candidates(cycle))
            return int(value or 0)

        @staticmethod
        def _extract_cycle_reviewed_count(cycle: dict) -> int:
            value = (cycle or {}).get("reviewed_count")
            if value is None:
                value = dict((cycle or {}).get("review") or {}).get("reviewed_count")
            return int(value or 0)

        @staticmethod
        def _extract_cycle_lifecycle(cycle: dict) -> dict:
            lifecycle = (cycle or {}).get("lifecycle")
            return dict(lifecycle) if isinstance(lifecycle, dict) else {}

        @staticmethod
        def _compact_active_candidate_pool(
            factor_research: Optional[dict[str, Any]],
            *,
            candidate_limit: int = 5,
            summary_limit: int = 5,
        ) -> dict[str, Any]:
            artifact = dict(factor_research or {})
            active_pool = dict(artifact.get("active_candidate_pool") or {})

            def _normalize_list(value: Any) -> list[str]:
                if isinstance(value, (list, tuple, set)):
                    return [str(item).strip() for item in value if str(item).strip()]
                token = str(value or "").strip()
                return [token] if token else []

            def _normalize_risk_audit(value: Any) -> dict[str, Any]:
                payload = dict(value or {}) if isinstance(value, dict) else {}
                return {
                    "lookahead_risk_level": str(payload.get("lookahead_risk_level") or "").strip() or None,
                    "multiple_testing_risk_level": str(payload.get("multiple_testing_risk_level") or "").strip() or None,
                    "overall_risk_level": str(payload.get("overall_risk_level") or "").strip() or None,
                    "lookahead_available": bool(payload.get("lookahead_available")),
                    "multiple_testing_available": bool(payload.get("multiple_testing_available")),
                    "required_audits_complete": bool(payload.get("required_audits_complete")),
                    "blocked": bool(payload.get("blocked")),
                    "block_reasons": _normalize_list(payload.get("block_reasons")),
                }

            def _normalize_lineage(value: Any) -> dict[str, Any]:
                payload = dict(value or {}) if isinstance(value, dict) else {}
                return {
                    "generation_artifact_id": str(payload.get("generation_artifact_id") or "").strip() or None,
                    "validation_artifact_id": str(payload.get("validation_artifact_id") or "").strip() or None,
                    "memory_record_id": str(payload.get("memory_record_id") or "").strip() or None,
                    "resolved_from": str(payload.get("resolved_from") or "").strip() or None,
                    "candidate_index": payload.get("candidate_index"),
                }

            top_candidates: list[dict[str, Any]] = []
            for item in list(active_pool.get("top_candidates") or [])[: max(1, int(candidate_limit or 5))]:
                if not isinstance(item, dict):
                    continue
                top_candidates.append(
                    {
                        "artifact_id": str(item.get("artifact_id") or "").strip() or None,
                        "name": str(item.get("name") or "").strip() or None,
                        "family": str(item.get("family") or "").strip() or None,
                        "expected_regime": _normalize_list(item.get("expected_regime")),
                        "expected_holding_period": item.get("expected_holding_period"),
                        "grade": str(item.get("grade") or "").strip() or None,
                        "recommendation": str(item.get("recommendation") or "").strip() or None,
                        "registry_stage": str(item.get("registry_stage") or "").strip() or None,
                        "pool_entry_mode": str(item.get("pool_entry_mode") or "").strip() or None,
                        "total_score": item.get("total_score"),
                        "admission_blocked": bool(item.get("admission_blocked")),
                        "admission_block_reasons": _normalize_list(item.get("admission_block_reasons")),
                        "source_generation_artifact_id": str(item.get("source_generation_artifact_id") or "").strip() or None,
                        "source_validation_artifact_id": str(item.get("source_validation_artifact_id") or "").strip() or None,
                        "memory_record_id": str(item.get("memory_record_id") or "").strip() or None,
                        "latest_validation_at": item.get("latest_validation_at"),
                        "latest_validation_age_days": item.get("latest_validation_age_days"),
                        "lineage": _normalize_lineage(item.get("lineage")),
                        "risk_audit": _normalize_risk_audit(item.get("risk_audit")),
                    }
                )

            excluded_candidates: list[dict[str, Any]] = []
            for item in list(active_pool.get("excluded_candidates") or [])[: max(1, int(candidate_limit or 5))]:
                if not isinstance(item, dict):
                    continue
                excluded_candidates.append(
                    {
                        "artifact_id": str(item.get("artifact_id") or "").strip() or None,
                        "name": str(item.get("name") or "").strip() or None,
                        "family": str(item.get("family") or "").strip() or None,
                        "expected_regime": _normalize_list(item.get("expected_regime")),
                        "expected_holding_period": item.get("expected_holding_period"),
                        "grade": str(item.get("grade") or "").strip() or None,
                        "recommendation": str(item.get("recommendation") or "").strip() or None,
                        "registry_stage": str(item.get("registry_stage") or "").strip() or None,
                        "total_score": item.get("total_score"),
                        "admission_blocked": bool(item.get("admission_blocked")),
                        "admission_block_reasons": _normalize_list(item.get("admission_block_reasons")),
                        "source_generation_artifact_id": str(item.get("source_generation_artifact_id") or "").strip() or None,
                        "source_validation_artifact_id": str(item.get("source_validation_artifact_id") or "").strip() or None,
                        "memory_record_id": str(item.get("memory_record_id") or "").strip() or None,
                        "latest_validation_at": item.get("latest_validation_at"),
                        "latest_validation_age_days": item.get("latest_validation_age_days"),
                        "lineage": _normalize_lineage(item.get("lineage")),
                        "reasons": _normalize_list(item.get("reasons")),
                        "risk_audit": _normalize_risk_audit(item.get("risk_audit")),
                    }
                )

            family_summary = [
                {
                    "family": str(item.get("family") or "").strip() or None,
                    "count": int(item.get("count") or 0),
                    "promote_count": int(item.get("promote_count") or 0),
                    "review_count": int(item.get("review_count") or 0),
                    "avg_total_score": item.get("avg_total_score"),
                    "max_total_score": item.get("max_total_score"),
                }
                for item in list(active_pool.get("family_summary") or [])[: max(1, int(summary_limit or 5))]
                if isinstance(item, dict)
            ]
            regime_summary = [
                {
                    "regime": str(item.get("regime") or "").strip() or None,
                    "count": int(item.get("count") or 0),
                }
                for item in list(active_pool.get("regime_summary") or [])[: max(1, int(summary_limit or 5))]
                if isinstance(item, dict)
            ]

            return {
                "active_pool_mode": str(active_pool.get("active_pool_mode") or "").strip() or None,
                "source_count": int(active_pool.get("source_count") or 0),
                "count": int(active_pool.get("count") or 0),
                "strict_count": int(active_pool.get("strict_count") or 0),
                "provisional_count": int(active_pool.get("provisional_count") or 0),
                "provisional_spillover_count": int(active_pool.get("provisional_spillover_count") or 0),
                "excluded_count": int(active_pool.get("excluded_count") or 0),
                "blocked_excluded_count": int(active_pool.get("blocked_excluded_count") or 0),
                "pending_excluded_count": int(active_pool.get("pending_excluded_count") or 0),
                "ineligible_excluded_count": int(active_pool.get("ineligible_excluded_count") or 0),
                "provisional_spillover_policy": dict(active_pool.get("provisional_spillover_policy") or {}),
                "top_candidates": top_candidates,
                "excluded_candidates": excluded_candidates,
                "exclusion_reason_counts": {
                    str(key): int(value or 0)
                    for key, value in dict(active_pool.get("exclusion_reason_counts") or {}).items()
                    if str(key).strip()
                },
                "blocked_exclusion_reason_counts": {
                    str(key): int(value or 0)
                    for key, value in dict(active_pool.get("blocked_exclusion_reason_counts") or {}).items()
                    if str(key).strip()
                },
                "pending_exclusion_reason_counts": {
                    str(key): int(value or 0)
                    for key, value in dict(active_pool.get("pending_exclusion_reason_counts") or {}).items()
                    if str(key).strip()
                },
                "ineligible_exclusion_reason_counts": {
                    str(key): int(value or 0)
                    for key, value in dict(active_pool.get("ineligible_exclusion_reason_counts") or {}).items()
                    if str(key).strip()
                },
                "family_summary": family_summary,
                "regime_summary": regime_summary,
            }

        @classmethod
        def _compact_factor_research_snapshot(
            cls,
            factor_research: Optional[dict[str, Any]],
        ) -> dict[str, Any]:
            artifact = dict(factor_research or {})
            summary = dict(artifact.get("summary") or {})
            freshness_repair = dict(artifact.get("freshness_repair") or {})
            return {
                "summary": {
                    "active_factor_count": int(summary.get("active_factor_count") or 0),
                    "active_candidate_count": int(summary.get("active_candidate_count") or 0),
                    "governed_source_candidate_count": int(summary.get("governed_source_candidate_count") or 0),
                    "governed_active_registry_candidate_count": int(
                        summary.get("governed_active_registry_candidate_count") or 0
                    ),
                    "governed_blocked_candidate_count": int(summary.get("governed_blocked_candidate_count") or 0),
                    "governed_active_blocked_candidate_count": int(summary.get("governed_active_blocked_candidate_count") or 0),
                    "governed_quarantined_candidate_count": int(summary.get("governed_quarantined_candidate_count") or 0),
                    "governed_governance_denominator": int(summary.get("governed_governance_denominator") or 0),
                    "governed_blocked_ratio": summary.get("governed_blocked_ratio"),
                    "governed_pending_candidate_count": int(summary.get("governed_pending_candidate_count") or 0),
                    "governed_pending_ratio": summary.get("governed_pending_ratio"),
                    "governed_ineligible_candidate_count": int(summary.get("governed_ineligible_candidate_count") or 0),
                    "governed_ineligible_ratio": summary.get("governed_ineligible_ratio"),
                    "governed_latest_candidate_at": summary.get("governed_latest_candidate_at"),
                    "governed_freshness_days": summary.get("governed_freshness_days"),
                    "governed_freshness_source": summary.get("governed_freshness_source"),
                    "ranked_factor_count": int(summary.get("ranked_factor_count") or 0),
                    "top_factor_names": list(summary.get("top_factor_names") or []),
                    "top_candidate_names": list(summary.get("top_candidate_names") or []),
                    "active_family_names": list(summary.get("active_family_names") or []),
                    "active_regime_names": list(summary.get("active_regime_names") or []),
                    "preferred_strategy_types": list(summary.get("preferred_strategy_types") or []),
                    "family_preference_order": list(summary.get("family_preference_order") or []),
                    "family_preference_source_mode": summary.get("family_preference_source_mode"),
                    "factor_source_mode": summary.get("factor_source_mode"),
                    "governed_candidate_pool_mode": summary.get("governed_candidate_pool_mode"),
                    "governed_candidate_pool_provisional": bool(summary.get("governed_candidate_pool_provisional")),
                    "governed_candidate_pool_strict_count": int(summary.get("governed_candidate_pool_strict_count") or 0),
                    "governed_candidate_pool_provisional_count": int(
                        summary.get("governed_candidate_pool_provisional_count") or 0
                    ),
                    "governed_candidate_pool_provisional_spillover_count": int(
                        summary.get("governed_candidate_pool_provisional_spillover_count") or 0
                    ),
                    "governed_candidate_pool_provisional_spillover_policy": dict(
                        summary.get("governed_candidate_pool_provisional_spillover_policy") or {}
                    ),
                    "governed_candidate_pool_provisional_spillover_policy_status": summary.get(
                        "governed_candidate_pool_provisional_spillover_policy_status"
                    ),
                    "governed_candidate_pool_provisional_pending_count": int(
                        summary.get("governed_candidate_pool_provisional_pending_count") or 0
                    ),
                    "governed_candidate_pool_strict_shortfall_count": int(
                        summary.get("governed_candidate_pool_strict_shortfall_count") or 0
                    ),
                    "scheduler_last_run": summary.get("scheduler_last_run"),
                    "scheduler_freshness_sec": summary.get("scheduler_freshness_sec"),
                    "scheduler_recent_success": bool(summary.get("scheduler_recent_success")),
                    "scheduler_llm_validation_status": summary.get("scheduler_llm_validation_status"),
                    "governed_exclusion_reason_counts": dict(summary.get("governed_exclusion_reason_counts") or {}),
                    "governed_blocking_reason_counts": dict(summary.get("governed_blocking_reason_counts") or {}),
                    "governed_active_blocking_reason_counts": dict(summary.get("governed_active_blocking_reason_counts") or {}),
                    "governed_pending_reason_counts": dict(summary.get("governed_pending_reason_counts") or {}),
                    "governed_ineligible_reason_counts": dict(summary.get("governed_ineligible_reason_counts") or {}),
                    "governed_registry_stage_counts": dict(summary.get("governed_registry_stage_counts") or {}),
                    "top_candidate_lineage": list(summary.get("top_candidate_lineage") or []),
                    "governed_risk_counts": dict(summary.get("governed_risk_counts") or {}),
                    "stock_family_allocation_count": int(summary.get("stock_family_allocation_count") or 0),
                    "stock_family_allocation_family_counts": dict(summary.get("stock_family_allocation_family_counts") or {}),
                    "stock_family_allocation_entropy": summary.get("stock_family_allocation_entropy"),
                    "stock_family_allocation_avg_priority": summary.get("stock_family_allocation_avg_priority"),
                    "stock_family_allocation_source_mode": summary.get("stock_family_allocation_source_mode"),
                    "degraded": bool(summary.get("degraded")),
                    "freshness_days": summary.get("freshness_days"),
                    "latest_factor_date": summary.get("latest_factor_date"),
                    "stale": bool(summary.get("stale")),
                    "quality_flags": list(summary.get("quality_flags") or []),
                    "budget_feedback_signal_count_total": int(summary.get("budget_feedback_signal_count_total") or 0),
                    "budget_feedback_zero_signal_strategy_count": int(summary.get("budget_feedback_zero_signal_strategy_count") or 0),
                    "budget_feedback_zero_signal_ratio": summary.get("budget_feedback_zero_signal_ratio"),
                    "budget_feedback_low_signal_strategy_count": int(summary.get("budget_feedback_low_signal_strategy_count") or 0),
                    "budget_feedback_low_signal_ratio": summary.get("budget_feedback_low_signal_ratio"),
                    "budget_feedback_observed_forward_window_count": int(summary.get("budget_feedback_observed_forward_window_count") or 0),
                    "budget_feedback_missing_forward_window_count": int(summary.get("budget_feedback_missing_forward_window_count") or 0),
                    "budget_feedback_expected_forward_window_count": int(summary.get("budget_feedback_expected_forward_window_count") or 0),
                    "budget_feedback_forward_window_coverage_ratio": summary.get("budget_feedback_forward_window_coverage_ratio"),
                    "budget_feedback_promotion_ready_count": int(summary.get("budget_feedback_promotion_ready_count") or 0),
                    "budget_feedback_promotion_ready_ratio": summary.get("budget_feedback_promotion_ready_ratio"),
                    "budget_feedback_promotion_review_count": int(summary.get("budget_feedback_promotion_review_count") or 0),
                    "budget_feedback_promotion_review_coverage_ratio": summary.get("budget_feedback_promotion_review_coverage_ratio"),
                    "budget_feedback_evidence_debt_strategy_count": int(summary.get("budget_feedback_evidence_debt_strategy_count") or 0),
                    "budget_feedback_evidence_debt_ratio": summary.get("budget_feedback_evidence_debt_ratio"),
                    "budget_feedback_fallback_evidence_strategy_count": int(summary.get("budget_feedback_fallback_evidence_strategy_count") or 0),
                    "budget_feedback_feedback_evidence_augmented_count": int(summary.get("budget_feedback_feedback_evidence_augmented_count") or 0),
                    "budget_feedback_fallback_evidence_mode_counts": dict(summary.get("budget_feedback_fallback_evidence_mode_counts") or {}),
                },
                "active_candidate_pool": cls._compact_active_candidate_pool(artifact),
                "degraded": bool(artifact.get("degraded")),
                "source_chain": list(artifact.get("source_chain") or []),
                "freshness_repair": {
                    "refresh_attempted": bool(freshness_repair.get("refresh_attempted")),
                    "refresh_status": freshness_repair.get("refresh_status"),
                    "refresh_trigger": freshness_repair.get("refresh_trigger"),
                },
            }

        @staticmethod
        def _aggregate_task_lifecycle_metrics(task_results: List[dict]) -> dict:
            lifecycle_state_counts: dict[str, int] = {}
            phase_status_counts: dict[str, int] = {}
            failed_phase_counts: dict[str, int] = {}
            observable_phases: list[str] = []
            for item in list(task_results or []):
                lifecycle_summary = dict(item.get("lifecycle_summary") or {})
                state = str(lifecycle_summary.get("state") or "unknown")
                lifecycle_state_counts[state] = lifecycle_state_counts.get(state, 0) + 1
                for status, count in dict(lifecycle_summary.get("phase_status_counts") or {}).items():
                    phase_status_counts[str(status)] = phase_status_counts.get(str(status), 0) + int(count or 0)
                failed_phase = str(lifecycle_summary.get("failed_phase") or "").strip()
                if failed_phase:
                    failed_phase_counts[failed_phase] = failed_phase_counts.get(failed_phase, 0) + 1
                phase_order = list(lifecycle_summary.get("phase_order") or [])
                if phase_order:
                    observable_phases = phase_order
            return {
                "lifecycle_state_counts": lifecycle_state_counts,
                "phase_status_counts": phase_status_counts,
                "failed_phase_counts": failed_phase_counts,
                "observable_phases": observable_phases or list(AUTONOMY_PHASE_ORDER),
            }

        @staticmethod
        def _with_stage_meta(
            stage_name: str,
            trace_id: str,
            payload: Optional[dict],
            *,
            status: StageStatus | str,
            ok: Optional[bool] = None,
            hard_failure: bool = False,
            degraded: Optional[bool] = None,
            skip_reason: Optional[str] = None,
        ) -> dict:
            return build_stage_result(
                stage_name,
                trace_id,
                payload,
                status=status,
                ok=ok,
                hard_failure=hard_failure,
                degraded=degraded,
                skip_reason=skip_reason,
            )

        @staticmethod
        def _record_persistence_failure(
            failures: list[dict[str, Any]],
            operation: str,
            exc: Exception,
            *,
            stage: Optional[str] = None,
        ) -> None:
            failures.append(
                {
                    "operation": str(operation or "unknown"),
                    "stage": str(stage or "").strip() or None,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                }
            )

        @classmethod
        def _build_pipeline_payload(
            cls,
            results: dict[str, Any],
            *,
            stage_summary: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            summary = dict(stage_summary or summarize_stage_results(results.get("stages") or {}))
            failed_stages = list(summary.get("failed_stages") or [])
            partial_stages = list(summary.get("partial_stages") or [])
            return {
                "trace_id": results.get("trace_id"),
                "status": results.get("status"),
                "stage_order": list(results.get("stages", {}).keys()),
                "total_stage_count": len(results.get("stages", {})),
                "failed_stage": failed_stages[0] if failed_stages else None,
                "partial_stage": partial_stages[0] if partial_stages else None,
                "stage_status_counts": dict(summary.get("stage_status_counts") or {}),
            }

        @classmethod
        def _apply_run_audit(
            cls,
            results: dict[str, Any],
            *,
            persistence_failures: Optional[list[dict[str, Any]]] = None,
        ) -> dict[str, Any]:
            failures = list(persistence_failures or [])
            stage_summary = summarize_stage_results(results.get("stages") or {})
            summary = dict(results.get("summary") or {})
            combined_skip_reasons: list[str] = []
            for reason in list(stage_summary.get("skip_reasons") or []) + list(summary.get("skip_reasons") or []):
                token = str(reason or "").strip()
                if token and token not in combined_skip_reasons:
                    combined_skip_reasons.append(token)
            if summary.get("skip_reason"):
                token = str(summary.get("skip_reason") or "").strip()
                if token and token not in combined_skip_reasons:
                    combined_skip_reasons.insert(0, token)

            resolved_status = resolve_run_status(
                results.get("status") or FactoryRunStatus.SUCCESS.value,
                results.get("stages") or {},
                persistence_failure_count=len(failures),
            )
            results["status"] = resolved_status.value
            summary.update(stage_summary)
            summary["skip_reasons"] = combined_skip_reasons
            summary["persistence_failure_count"] = len(failures)
            summary["persistence_failures"] = failures
            if not summary.get("skip_reason") and combined_skip_reasons:
                summary["skip_reason"] = combined_skip_reasons[0]
            results["summary"] = summary
            results["pipeline"] = cls._build_pipeline_payload(results, stage_summary=stage_summary)
            return results

        @staticmethod
        def _safe_float(value: Any, default: float = 0.0) -> float:
            try:
                return float(value or default)
            except Exception:
                return float(default)

        @staticmethod
        def _safe_int(value: Any, default: int = 0) -> int:
            try:
                return int(value or default)
            except Exception:
                return int(default)

        @staticmethod
        def _normalize_text(value: Any) -> str:
            return str(value or "").strip().lower()

        @classmethod
        def _safe_ratio(cls, numerator: Any, denominator: Any) -> float:
            den = cls._safe_float(denominator)
            if den <= 0.0:
                return 0.0
            return round(cls._safe_float(numerator) / den, 4)
