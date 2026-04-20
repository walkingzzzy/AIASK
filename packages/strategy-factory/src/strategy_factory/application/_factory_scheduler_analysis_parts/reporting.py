
        @classmethod
        def _aggregate_submission_audit_metrics(cls, submit_result: Optional[dict]) -> dict[str, Any]:
            payload = dict(submit_result or {})
            strategies = list(payload.get("strategies") or [])
            attempt_adjusted_gate_failed = 0
            attempt_penalties: list[float] = []
            refresh_metrics_only_count = 0
            spawn_revision_from_existing_count = 0
            constraint_violation_count = 0
            intersection_ratios: list[float] = []
            universe_expansion_count = 0
            preference_mismatch_warning_count = 0
            deflated_sharpe_values: list[float] = []
            formal_deflated_sharpe_values: list[float] = []
            high_pbo_proxy_count = 0
            high_pbo_count = 0
            formal_multiple_testing_count = 0
            weak_white_reality_check_count = 0
            weak_hansen_spa_count = 0
            incubation_readiness_values: list[float] = []
            formal_incubation_count = 0
            observe_incubation_count = 0
            deferred_budget_queue_count = 0
            live_ready_review_count = 0
            direct_trade_candidate_count = 0
            paper_account_bound_count = 0
            runtime_review_count = 0
            promotion_review_count = 0
            promotion_review_status_counts: dict[str, int] = {}
            gate_protocol_counts: dict[str, int] = {}
            alignment_contract_violation_counts: dict[str, int] = {}
            constraint_violation_reason_counts: dict[str, int] = {}
            target_expansion_source_counts: dict[str, int] = {}
            refresh_decision_basis_counts: dict[str, int] = {}
            revision_trigger_reason_counts: dict[str, int] = {}
            generator_precompile_reject_reason_counts: dict[str, int] = {}
            contract_reject_reason_counts: dict[str, int] = {}
            feedback_control_mode_counts: dict[str, int] = {}
            feedback_target_pool_control_mode_counts: dict[str, int] = {}
            feedback_holding_bucket_control_mode_counts: dict[str, int] = {}
            feedback_generator_mode_control_mode_counts: dict[str, int] = {}
            trade_validation_audit_missing_count = 0
            gate_3_event_audit_incomplete_count = 0
            gate_3_event_sample_source_auto_context_minimal_count = 0
            gate_3_supplemental_statistical_gate_count = 0
            feedback_controlled_count = 0
            feedback_cooldown_count = 0
            feedback_suppressed_count = 0
            feedback_freeze_count = 0
            feedback_target_pool_freeze_count = 0
            feedback_generator_mode_freeze_count = 0
            tested_object_hash_changed_count = 0
            existing_identity_available_count = 0
            existing_tested_object_available_count = 0
            generator_mode_metrics: dict[str, dict[str, int]] = {}

            def _normalized_text(value: Any) -> str:
                return str(value or "").strip().lower()

            def _generator_mode_value(record: dict[str, Any]) -> str:
                provenance = dict(record.get("candidate_provenance") or {})
                strategy_profile = dict(record.get("strategy_profile") or {})
                return (
                    _normalized_text(record.get("generator_mode"))
                    or _normalized_text(record.get("generator_type"))
                    or _normalized_text(provenance.get("generator_mode"))
                    or _normalized_text(provenance.get("generator_type"))
                    or _normalized_text(strategy_profile.get("generator_mode"))
                    or "unknown"
                )

            def _ensure_mode_bucket(mode: str) -> dict[str, int]:
                return generator_mode_metrics.setdefault(
                    mode,
                    {
                        "strategy_count": 0,
                        "created_total_count": 0,
                        "refresh_metrics_only_count": 0,
                        "spawn_revision_from_existing_count": 0,
                        "tested_object_hash_changed_count": 0,
                    },
                )

            for item in strategies:
                summary = dict(item or {})
                generator_mode = _generator_mode_value(summary)
                mode_bucket = _ensure_mode_bucket(generator_mode)
                mode_bucket["strategy_count"] += 1
                gate = dict(summary.get("gate_3") or {})
                gate_protocol = str(gate.get("gate_protocol") or "").strip().lower()
                if gate_protocol:
                    gate_protocol_counts[gate_protocol] = gate_protocol_counts.get(gate_protocol, 0) + 1
                attempt_adjustment = dict(gate.get("attempt_adjustment") or {})
                penalty = cls._safe_float(attempt_adjustment.get("penalty"))
                if penalty > 0:
                    attempt_penalties.append(penalty)
                    if not gate.get("passed"):
                        attempt_adjusted_gate_failed += 1
                deflated_proxy = gate.get("deflated_sharpe_proxy")
                if deflated_proxy is not None:
                    deflated_sharpe_values.append(cls._safe_float(deflated_proxy))
                deflated_formal = gate.get("deflated_sharpe_ratio")
                if deflated_formal is not None:
                    formal_deflated_sharpe_values.append(cls._safe_float(deflated_formal))
                if cls._safe_float(gate.get("pbo_proxy")) > 0.55:
                    high_pbo_proxy_count += 1
                if str(gate.get("multiple_testing_mode") or "").strip().lower() == "formal_runtime":
                    formal_multiple_testing_count += 1
                pbo_effective = gate.get("pbo")
                if pbo_effective is None:
                    pbo_effective = gate.get("pbo_proxy")
                if cls._safe_float(pbo_effective) > 0.55:
                    high_pbo_count += 1
                white_effective = gate.get("white_reality_check_pvalue")
                if white_effective is None:
                    white_effective = gate.get("reality_check_pvalue_proxy")
                if cls._safe_float(white_effective) > 0.2:
                    weak_white_reality_check_count += 1
                spa_effective = gate.get("hansen_spa_pvalue")
                if spa_effective is None:
                    spa_effective = gate.get("spa_pvalue_proxy")
                if cls._safe_float(spa_effective) > 0.2:
                    weak_hansen_spa_count += 1

                constraint_check = dict(summary.get("constraint_check") or {})
                constraint_violation = str(constraint_check.get("constraint_violation") or "").strip().lower()
                if constraint_violation:
                    constraint_violation_count += 1
                    constraint_violation_reason_counts[constraint_violation] = (
                        constraint_violation_reason_counts.get(constraint_violation, 0) + 1
                    )
                if constraint_check.get("expansion_applied"):
                    universe_expansion_count += 1
                expansion_source = str(constraint_check.get("expansion_source") or "").strip().lower()
                if expansion_source:
                    target_expansion_source_counts[expansion_source] = (
                        target_expansion_source_counts.get(expansion_source, 0) + 1
                    )
                alignment_contract_violation = str(
                    constraint_check.get("alignment_contract_violation") or ""
                ).strip().lower()
                if alignment_contract_violation:
                    alignment_contract_violation_counts[alignment_contract_violation] = (
                        alignment_contract_violation_counts.get(alignment_contract_violation, 0) + 1
                    )
                intersection_ratio = constraint_check.get("intersection_ratio")
                if intersection_ratio is not None:
                    intersection_ratios.append(cls._safe_float(intersection_ratio))
                if any("preference" in str(code or "").lower() for code in list(summary.get("warning_codes") or [])):
                    preference_mismatch_warning_count += 1
                readiness_score = summary.get("incubation_readiness_score")
                if readiness_score is not None:
                    incubation_readiness_values.append(cls._safe_float(readiness_score))
                track = str(summary.get("incubation_budget_track") or "").strip().lower()
                if summary.get("passed"):
                    if track == "formal_incubation":
                        formal_incubation_count += 1
                    elif track == "observe_incubation":
                        observe_incubation_count += 1
                    elif track == "deferred_budget_queue":
                        deferred_budget_queue_count += 1
                if bool(summary.get("direct_trade_candidate")):
                    direct_trade_candidate_count += 1
                submission_lane = str(summary.get("submission_lane") or "").strip().lower()
                if submission_lane == "live_ready_review":
                    live_ready_review_count += 1
                if summary.get("paper_account_id") or summary.get("incubation_account_id"):
                    paper_account_bound_count += 1
                if str(summary.get("runtime_control_mode") or "").strip():
                    runtime_review_count += 1
                promotion_review_status = str(summary.get("promotion_review_status") or "").strip().lower()
                if summary.get("promotion_review_id") or promotion_review_status:
                    promotion_review_count += 1
                if promotion_review_status:
                    promotion_review_status_counts[promotion_review_status] = (
                        promotion_review_status_counts.get(promotion_review_status, 0) + 1
                    )
                if bool(gate.get("trade_validation_audit_missing")):
                    trade_validation_audit_missing_count += 1
                if bool(gate.get("event_audit_incomplete")):
                    gate_3_event_audit_incomplete_count += 1
                if str(gate.get("event_sample_source") or "").strip().lower() == "auto_context_minimal":
                    gate_3_event_sample_source_auto_context_minimal_count += 1
                if gate.get("supplemental_statistical_gate") not in (None, "", [], {}):
                    gate_3_supplemental_statistical_gate_count += 1

                refresh_decision_basis = str(
                    summary.get("refresh_decision_basis")
                    or dict(summary.get("dedup_result") or {}).get("refresh_decision_basis")
                    or ""
                ).strip().lower()
                if refresh_decision_basis:
                    refresh_decision_basis_counts[refresh_decision_basis] = (
                        refresh_decision_basis_counts.get(refresh_decision_basis, 0) + 1
                    )
                revision_trigger_reason = str(
                    summary.get("revision_trigger_reason")
                    or dict(summary.get("dedup_result") or {}).get("revision_trigger_reason")
                    or ""
                ).strip().lower()
                if revision_trigger_reason:
                    revision_trigger_reason_counts[revision_trigger_reason] = (
                        revision_trigger_reason_counts.get(revision_trigger_reason, 0) + 1
                    )
                if bool(
                    summary.get("tested_object_hash_changed", summary.get("tested_object_changed"))
                ):
                    tested_object_hash_changed_count += 1
                    mode_bucket["tested_object_hash_changed_count"] += 1
                if bool(summary.get("existing_identity_available")):
                    existing_identity_available_count += 1
                if bool(summary.get("existing_tested_object_available")):
                    existing_tested_object_available_count += 1
                if bool(summary.get("created_total")):
                    mode_bucket["created_total_count"] += 1
                generator_precompile_reject_reason = str(
                    summary.get("generator_precompile_reject_reason") or ""
                ).strip().lower()
                if generator_precompile_reject_reason:
                    generator_precompile_reject_reason_counts[generator_precompile_reject_reason] = (
                        generator_precompile_reject_reason_counts.get(generator_precompile_reject_reason, 0) + 1
                    )
                for reason in list(summary.get("contract_reject_reasons") or []):
                    normalized_reason = str(reason or "").strip().lower()
                    if normalized_reason:
                        contract_reject_reason_counts[normalized_reason] = (
                            contract_reject_reason_counts.get(normalized_reason, 0) + 1
                        )

                incubation_budget = dict(summary.get("incubation_budget") or {})
                feedback_metrics = dict(incubation_budget.get("feedback_metrics") or {})
                feedback_control_mode = str(
                    summary.get("feedback_control_mode")
                    or feedback_metrics.get("control_mode")
                    or ""
                ).strip().lower()
                if feedback_control_mode:
                    feedback_control_mode_counts[feedback_control_mode] = (
                        feedback_control_mode_counts.get(feedback_control_mode, 0) + 1
                    )
                    if feedback_control_mode != "normal":
                        feedback_controlled_count += 1
                    if feedback_control_mode == "cooldown":
                        feedback_cooldown_count += 1
                    elif feedback_control_mode == "suppress":
                        feedback_suppressed_count += 1
                    elif feedback_control_mode == "freeze":
                        feedback_freeze_count += 1
                feedback_target_pool_control_mode = str(
                    summary.get("feedback_target_pool_control_mode")
                    or feedback_metrics.get("target_pool_control_mode")
                    or ""
                ).strip().lower()
                if feedback_target_pool_control_mode:
                    feedback_target_pool_control_mode_counts[feedback_target_pool_control_mode] = (
                        feedback_target_pool_control_mode_counts.get(feedback_target_pool_control_mode, 0) + 1
                    )
                feedback_holding_bucket_control_mode = str(
                    summary.get("feedback_holding_bucket_control_mode")
                    or feedback_metrics.get("holding_bucket_control_mode")
                    or ""
                ).strip().lower()
                if feedback_holding_bucket_control_mode:
                    feedback_holding_bucket_control_mode_counts[feedback_holding_bucket_control_mode] = (
                        feedback_holding_bucket_control_mode_counts.get(
                            feedback_holding_bucket_control_mode,
                            0,
                        )
                        + 1
                    )
                feedback_generator_mode_control_mode = str(
                    summary.get("feedback_generator_mode_control_mode")
                    or feedback_metrics.get("generator_mode_control_mode")
                    or ""
                ).strip().lower()
                if feedback_generator_mode_control_mode:
                    feedback_generator_mode_control_mode_counts[feedback_generator_mode_control_mode] = (
                        feedback_generator_mode_control_mode_counts.get(feedback_generator_mode_control_mode, 0) + 1
                    )
                if bool(feedback_metrics.get("target_pool_freeze_active")):
                    feedback_target_pool_freeze_count += 1
                if bool(feedback_metrics.get("generator_mode_freeze_active")):
                    feedback_generator_mode_freeze_count += 1

                refresh_mode = str(
                    summary.get("refresh_mode")
                    or dict(summary.get("dedup_result") or {}).get("refresh_mode")
                    or ""
                ).strip().lower()
                if refresh_mode == "refresh_metrics_only":
                    refresh_metrics_only_count += 1
                    mode_bucket["refresh_metrics_only_count"] += 1
                elif refresh_mode == "spawn_revision_from_existing":
                    spawn_revision_from_existing_count += 1
                    mode_bucket["spawn_revision_from_existing_count"] += 1

            generator_mode_submission_metrics = {
                mode: {
                    **dict(bucket or {}),
                    "refresh_absorption_ratio": round(
                        cls._safe_float((bucket or {}).get("refresh_metrics_only_count"))
                        / max(1, int((bucket or {}).get("strategy_count") or 0)),
                        4,
                    ),
                    "revision_creation_ratio": round(
                        cls._safe_float((bucket or {}).get("spawn_revision_from_existing_count"))
                        / max(1, int((bucket or {}).get("created_total_count") or 0)),
                        4,
                    ),
                }
                for mode, bucket in generator_mode_metrics.items()
            }

            return {
                "constraint_violation_count": constraint_violation_count,
                "target_symbol_intersection_ratio_avg": round(sum(intersection_ratios) / len(intersection_ratios), 4)
                if intersection_ratios
                else 0.0,
                "universe_expansion_count": universe_expansion_count,
                "preference_mismatch_warning_count": preference_mismatch_warning_count,
                "attempt_adjusted_gate_failed": attempt_adjusted_gate_failed,
                "attempt_adjusted_score_avg": round(sum(attempt_penalties) / len(attempt_penalties), 4)
                if attempt_penalties
                else 0.0,
                "deflated_sharpe_proxy_avg": round(sum(deflated_sharpe_values) / len(deflated_sharpe_values), 4)
                if deflated_sharpe_values
                else 0.0,
                "deflated_sharpe_ratio_avg": round(sum(formal_deflated_sharpe_values) / len(formal_deflated_sharpe_values), 4)
                if formal_deflated_sharpe_values
                else 0.0,
                "high_pbo_proxy_count": high_pbo_proxy_count,
                "high_pbo_count": high_pbo_count,
                "formal_multiple_testing_count": formal_multiple_testing_count,
                "weak_white_reality_check_count": weak_white_reality_check_count,
                "weak_hansen_spa_count": weak_hansen_spa_count,
                "avg_incubation_readiness_score": round(
                    sum(incubation_readiness_values) / len(incubation_readiness_values),
                    4,
                )
                if incubation_readiness_values
                else 0.0,
                "formal_incubation_count": formal_incubation_count,
                "observe_incubation_count": observe_incubation_count,
                "deferred_budget_queue_count": deferred_budget_queue_count,
                "live_ready_review_count": live_ready_review_count,
                "direct_trade_candidate_count": direct_trade_candidate_count,
                "paper_account_bound_count": paper_account_bound_count,
                "runtime_review_count": runtime_review_count,
                "promotion_review_count": promotion_review_count,
                "promotion_review_status_counts": promotion_review_status_counts,
                "refresh_metrics_only_count": refresh_metrics_only_count,
                "spawn_revision_from_existing_count": spawn_revision_from_existing_count,
                "revision_creation_ratio": round(
                    cls._safe_float(spawn_revision_from_existing_count)
                    / max(1, int(payload.get("created_total") or 0)),
                    4,
                ),
                "refresh_absorption_ratio": round(
                    cls._safe_float(refresh_metrics_only_count)
                    / max(1, len(strategies)),
                    4,
                ),
                "gate_3_gate_protocol_counts": gate_protocol_counts,
                "gate_3_trade_validation_audit_missing_count": trade_validation_audit_missing_count,
                "gate_3_statistical_fallback_research_only_count": int(
                    gate_protocol_counts.get("trade_rule_validation:statistical_fallback_research_only") or 0
                )
                + int(gate_protocol_counts.get("event_trade_validation:statistical_fallback_research_only") or 0),
                "gate_3_hard_fail_missing_trade_audit_count": int(
                    gate_protocol_counts.get("trade_rule_validation:hard_fail_missing_trade_audit") or 0
                )
                + int(gate_protocol_counts.get("event_trade_validation:hard_fail_missing_trade_audit") or 0),
                "gate_3_trade_primary_with_supplemental_audit_count": int(
                    gate_protocol_counts.get("trade_rule_validation:trade_primary_with_supplemental_audit") or 0
                )
                + int(gate_protocol_counts.get("event_trade_validation:trade_primary_with_supplemental_audit") or 0),
                "gate_3_event_audit_incomplete_count": gate_3_event_audit_incomplete_count,
                "gate_3_event_sample_source_auto_context_minimal_count": gate_3_event_sample_source_auto_context_minimal_count,
                "gate_3_supplemental_statistical_gate_count": gate_3_supplemental_statistical_gate_count,
                "refresh_decision_basis_counts": refresh_decision_basis_counts,
                "revision_trigger_reason_counts": revision_trigger_reason_counts,
                "tested_object_hash_changed_count": tested_object_hash_changed_count,
                "existing_identity_available_count": existing_identity_available_count,
                "existing_tested_object_available_count": existing_tested_object_available_count,
                "target_alignment_violation_counts": alignment_contract_violation_counts,
                "generator_precompile_reject_reason_counts": generator_precompile_reject_reason_counts,
                "contract_reject_reason_counts": contract_reject_reason_counts,
                "constraint_violation_reason_counts": constraint_violation_reason_counts,
                "target_expansion_source_counts": target_expansion_source_counts,
                "feedback_control_mode_counts": feedback_control_mode_counts,
                "feedback_target_pool_control_mode_counts": feedback_target_pool_control_mode_counts,
                "feedback_holding_bucket_control_mode_counts": (
                    feedback_holding_bucket_control_mode_counts
                ),
                "feedback_generator_mode_control_mode_counts": feedback_generator_mode_control_mode_counts,
                "feedback_controlled_count": feedback_controlled_count,
                "feedback_cooldown_count": feedback_cooldown_count,
                "feedback_suppressed_count": feedback_suppressed_count,
                "feedback_freeze_count": feedback_freeze_count,
                "feedback_target_pool_freeze_count": feedback_target_pool_freeze_count,
                "feedback_generator_mode_freeze_count": feedback_generator_mode_freeze_count,
                "generator_mode_submission_metrics": generator_mode_submission_metrics,
            }
