
        async def _submit_one(
            self,
            candidate: dict,
            snapshot: dict,
            db,
            *,
            read_only: bool = False,
        ) -> dict:
            """处理单个候选策略的完整提交流程。"""
            execution_options = SubmissionExecutionOptions(read_only=read_only)
            candidate = apply_resolved_candidate_envelope(candidate)
            candidate = self._ensure_runtime_playbook(candidate)
            run_submission_quality_gate = _local_run_submission_quality_gate

            existing_strategy = await self._resolve_existing_strategy(candidate, db)
            refresh_existing = existing_strategy is not None
            existing_status = str((existing_strategy or {}).get("status") or "draft")
            strategy_id = str((existing_strategy or {}).get("id") or f"factory_{int(_time.time())}_{uuid4().hex[:8]}")
            name = self._candidate_name(candidate, existing_strategy)
            metrics = candidate.get("backtest_metrics", {})
            semantic_audit: dict[str, Any] = {}
            if _semantic_contract_feature_enabled():
                candidate["confidence_contract"] = synthesize_confidence_contract(candidate)
                semantic_audit = audit_candidate_semantic_contract(candidate)
                candidate = _apply_candidate_semantic_contract(candidate, semantic_audit)
            gate_a_override = _build_gate_a_spec_override(candidate)
            data = self._build_strategy_data(strategy_id, name, candidate, metrics, existing=existing_strategy)
            candidate = apply_resolved_candidate_envelope(
                {
                    **dict(candidate or {}),
                    "id": strategy_id,
                    "name": name,
                    "params": dict(data.get("params") or {}),
                    "target_symbols": list((data.get("params") or {}).get("target_symbols") or candidate.get("target_symbols") or []),
                    "stock_pool": dict((data.get("params") or {}).get("stock_pool") or candidate.get("stock_pool") or {}),
                    "research_task": dict((data.get("params") or {}).get("research_task") or candidate.get("research_task") or {}),
                    "validation_profile": dict(
                        (data.get("params") or {}).get("validation_profile")
                        or candidate.get("validation_profile")
                        or {}
                    ),
                    "targeting_policy": dict(
                        (data.get("params") or {}).get("targeting_policy")
                        or candidate.get("targeting_policy")
                        or {}
                    ),
                    "constraint_check": dict(
                        (data.get("params") or {}).get("constraint_check")
                        or candidate.get("constraint_check")
                        or {}
                    ),
                    "candidate_contract_snapshot": dict((data.get("params") or {}).get("candidate_contract_snapshot") or {}),
                    "candidate_contract_hash": str((data.get("params") or {}).get("candidate_contract_hash") or ""),
                    "execution_contract_hash": str((data.get("params") or {}).get("execution_contract_hash") or ""),
                    "tested_object_hash": str((data.get("params") or {}).get("tested_object_hash") or ""),
                    "candidate_identity_signature": str((data.get("params") or {}).get("candidate_identity_signature") or ""),
                    "candidate_lineage_contract": dict((data.get("params") or {}).get("candidate_lineage_contract") or {}),
                    "logic_signature": str((data.get("params") or {}).get("logic_signature") or ""),
                    "dsl_signature": str((data.get("params") or {}).get("dsl_signature") or ""),
                    "factor_signature": str((data.get("params") or {}).get("factor_signature") or ""),
                    "entry_exit_signature": str((data.get("params") or {}).get("entry_exit_signature") or ""),
                    "prediction_trace_id": str(
                        (data.get("params") or {}).get("prediction_trace_id")
                        or candidate.get("prediction_trace_id")
                        or ""
                    ),
                    "trace_id": str(
                        (data.get("params") or {}).get("trace_id")
                        or candidate.get("trace_id")
                        or ""
                    ),
                    "research_validation_contract": dict(
                        (data.get("params") or {}).get("research_validation_contract")
                        or candidate.get("research_validation_contract")
                        or {}
                    ),
                    "research_validation_contract_submission_adapter": dict(
                        (data.get("params") or {}).get("research_validation_contract_submission_adapter")
                        or candidate.get("research_validation_contract_submission_adapter")
                        or {}
                    ),
                    "research_protocol_version": str(
                        (data.get("params") or {}).get("research_protocol_version")
                        or candidate.get("research_protocol_version")
                        or ""
                    ),
                    "candidate_contract_version": str(
                        (data.get("params") or {}).get("candidate_contract_version")
                        or candidate.get("candidate_contract_version")
                        or ""
                    ),
                    "spec_completeness": str(
                        (data.get("params") or {}).get("spec_completeness")
                        or candidate.get("spec_completeness")
                        or ""
                    ),
                    "field_provenance": dict(
                        (data.get("params") or {}).get("field_provenance")
                        or candidate.get("field_provenance")
                        or {}
                    ),
                    "field_provenance_summary": dict(
                        (data.get("params") or {}).get("field_provenance_summary")
                        or candidate.get("field_provenance_summary")
                        or {}
                    ),
                    "completion_issues": list(
                        (data.get("params") or {}).get("completion_issues")
                        or candidate.get("completion_issues")
                        or []
                    ),
                    "hard_failures": list(
                        (data.get("params") or {}).get("hard_failures")
                        or candidate.get("hard_failures")
                        or []
                    ),
                }
            )
            if _semantic_contract_feature_enabled():
                candidate = _apply_candidate_semantic_contract(candidate, semantic_audit)
            validation_report = None
            risk_report = None
            if gate_a_override is None:
                validation_report, risk_report = await self._evaluate_reports(candidate, db)
                formal_evidence_missing = bool(_report_is_degraded(validation_report) or _report_is_degraded(risk_report))
                gate = await run_submission_quality_gate(
                    db,
                    {**data, "status": existing_status if refresh_existing else "submitted"},
                    validation_report=validation_report,
                    risk_report=risk_report,
                    backtest_metrics={
                        **dict(metrics or {}),
                        "trade_count": metrics.get("trade_count"),
                        "trades_count": metrics.get("trades_count"),
                    },
                    incubation_budget_track=str(candidate.get("incubation_budget", {}).get("track") or "formal_incubation"),
                )
                if formal_evidence_missing:
                    live_eval = dict((gate.get("admission_evaluations") or {}).get("live") or {})
                    live_eval["passed"] = False
                    live_eval["reasons"] = list(dict.fromkeys([*list(live_eval.get("reasons") or []), "formal_risk_validation_evidence_missing"]))
                    gate["admission_evaluations"] = {**dict(gate.get("admission_evaluations") or {}), "live": live_eval}
                    gate["live_candidate_ready"] = False
                    gate["formal_risk_validation_evidence_missing"] = True
            else:
                gate = dict(gate_a_override)
            gate = self._apply_factory_submission_policy(
                candidate,
                name=name,
                gate=gate,
                backtest_metrics=metrics,
                refresh_existing=refresh_existing,
            )
            if _semantic_contract_feature_enabled():
                gate = _apply_semantic_contract_gate(gate, semantic_audit)
            candidate_provenance = self._candidate_provenance(candidate, existing_strategy)
            strategy_profile = dict(candidate_provenance.get("strategy_profile") or {})
            incubation_budget = dict(candidate.get("incubation_budget") or {})
            incubation_budget_track = str(incubation_budget.get("track") or "formal_incubation").strip().lower()

            submission_action = self._resolve_submission_action_plan(
                gate,
                candidate=candidate,
                refresh_existing=refresh_existing,
                existing_status=existing_status,
                incubation_budget_track=incubation_budget_track,
            )
            submission_lane = str(submission_action.get("submission_lane") or "deferred_submission")
            final_status = str(submission_action.get("final_status") or "submitted")
            candidate = self._apply_runtime_bootstrap_contract(
                candidate,
                submission_lane=submission_lane,
                runtime_bootstrap_eligible=bool(submission_action.get("runtime_bootstrap_eligible")),
                runtime_bootstrap_budget_tier=str(submission_action.get("runtime_bootstrap_budget_tier") or "") or None,
            )
            data = self._build_strategy_data(strategy_id, name, candidate, metrics, existing=existing_strategy)
            candidate = apply_resolved_candidate_envelope(
                {
                    **dict(candidate or {}),
                    "id": strategy_id,
                    "name": name,
                    "params": dict(data.get("params") or {}),
                    "target_symbols": list((data.get("params") or {}).get("target_symbols") or candidate.get("target_symbols") or []),
                    "stock_pool": dict((data.get("params") or {}).get("stock_pool") or candidate.get("stock_pool") or {}),
                    "research_task": dict((data.get("params") or {}).get("research_task") or candidate.get("research_task") or {}),
                    "validation_profile": dict(
                        (data.get("params") or {}).get("validation_profile")
                        or candidate.get("validation_profile")
                        or {}
                    ),
                    "targeting_policy": dict(
                        (data.get("params") or {}).get("targeting_policy")
                        or candidate.get("targeting_policy")
                        or {}
                    ),
                    "constraint_check": dict(
                        (data.get("params") or {}).get("constraint_check")
                        or candidate.get("constraint_check")
                        or {}
                    ),
                    "candidate_contract_snapshot": dict((data.get("params") or {}).get("candidate_contract_snapshot") or {}),
                    "candidate_contract_hash": str((data.get("params") or {}).get("candidate_contract_hash") or ""),
                    "execution_contract_hash": str((data.get("params") or {}).get("execution_contract_hash") or ""),
                    "tested_object_hash": str((data.get("params") or {}).get("tested_object_hash") or ""),
                    "candidate_identity_signature": str((data.get("params") or {}).get("candidate_identity_signature") or ""),
                    "candidate_lineage_contract": dict((data.get("params") or {}).get("candidate_lineage_contract") or {}),
                    "logic_signature": str((data.get("params") or {}).get("logic_signature") or ""),
                    "dsl_signature": str((data.get("params") or {}).get("dsl_signature") or ""),
                    "factor_signature": str((data.get("params") or {}).get("factor_signature") or ""),
                    "entry_exit_signature": str((data.get("params") or {}).get("entry_exit_signature") or ""),
                    "prediction_trace_id": str(
                        (data.get("params") or {}).get("prediction_trace_id")
                        or candidate.get("prediction_trace_id")
                        or ""
                    ),
                    "trace_id": str(
                        (data.get("params") or {}).get("trace_id")
                        or candidate.get("trace_id")
                        or ""
                    ),
                    "research_validation_contract": dict(
                        (data.get("params") or {}).get("research_validation_contract")
                        or candidate.get("research_validation_contract")
                        or {}
                    ),
                    "research_validation_contract_submission_adapter": dict(
                        (data.get("params") or {}).get("research_validation_contract_submission_adapter")
                        or candidate.get("research_validation_contract_submission_adapter")
                        or {}
                    ),
                    "research_protocol_version": str(
                        (data.get("params") or {}).get("research_protocol_version")
                        or candidate.get("research_protocol_version")
                        or ""
                    ),
                    "candidate_contract_version": str(
                        (data.get("params") or {}).get("candidate_contract_version")
                        or candidate.get("candidate_contract_version")
                        or ""
                    ),
                    "spec_completeness": str(
                        (data.get("params") or {}).get("spec_completeness")
                        or candidate.get("spec_completeness")
                        or ""
                    ),
                    "field_provenance": dict(
                        (data.get("params") or {}).get("field_provenance")
                        or candidate.get("field_provenance")
                        or {}
                    ),
                    "field_provenance_summary": dict(
                        (data.get("params") or {}).get("field_provenance_summary")
                        or candidate.get("field_provenance_summary")
                        or {}
                    ),
                    "completion_issues": list(
                        (data.get("params") or {}).get("completion_issues")
                        or candidate.get("completion_issues")
                        or []
                    ),
                    "hard_failures": list(
                        (data.get("params") or {}).get("hard_failures")
                        or candidate.get("hard_failures")
                        or []
                    ),
                }
            )
            should_persist_strategy = await self._submission_coordinator.persist_candidate(
                strategy_id=strategy_id,
                candidate=candidate,
                data=data,
                metrics=metrics,
                validation_report=validation_report,
                risk_report=risk_report,
                gate=gate,
                db=db,
                refresh_existing=refresh_existing,
                options=execution_options,
            )
            quality_report = self._build_quality_report(
                strategy_id=strategy_id,
                candidate=candidate,
                snapshot=snapshot,
                backtest_metrics=metrics,
                quality_gate=gate,
                validation_report=validation_report,
                risk_report=risk_report,
                final_status=final_status,
                submission_lane=submission_lane,
            )
            quality_report = _enrich_quality_report_v2(
                quality_report,
                candidate=candidate,
                gate=gate,
                final_status=final_status,
            )
            quality_summary = dict(quality_report.get("summary") or {})
            quality_summary["candidate_contract_hash"] = candidate.get("candidate_contract_hash")
            quality_summary["execution_contract_hash"] = candidate.get("execution_contract_hash")
            quality_summary["tested_object_hash"] = candidate.get("tested_object_hash")
            quality_summary["candidate_identity_signature"] = candidate.get("candidate_identity_signature")
            quality_summary["target_pool_id"] = (
                dict((candidate.get("candidate_contract_snapshot") or {}).get("targeting") or {}).get("target_pool_id")
            )
            quality_summary["lineage_id"] = (
                dict((candidate.get("candidate_contract_snapshot") or {}).get("lineage") or {}).get("lineage_id")
            )
            quality_summary["multiple_testing_registry"] = dict(gate.get("multiple_testing_registry") or {})
            quality_report["summary"] = quality_summary
            quality_report["candidate_contract_hash"] = candidate.get("candidate_contract_hash")
            quality_report["execution_contract_hash"] = candidate.get("execution_contract_hash")
            quality_report["tested_object_hash"] = candidate.get("tested_object_hash")
            quality_report["candidate_identity_signature"] = candidate.get("candidate_identity_signature")
            quality_report["candidate_contract_snapshot"] = dict(candidate.get("candidate_contract_snapshot") or {})
            quality_report["candidate_lineage_contract"] = dict(candidate.get("candidate_lineage_contract") or {})
            quality_report["logic_signature"] = candidate.get("logic_signature")
            quality_report["dsl_signature"] = candidate.get("dsl_signature")
            quality_report["factor_signature"] = candidate.get("factor_signature")
            quality_report["entry_exit_signature"] = candidate.get("entry_exit_signature")

            multiple_testing_registry = dict(gate.get("multiple_testing_registry") or {})
            multiple_testing_registry_record_id = None
            if refresh_existing:
                post_gate = await self._submission_coordinator.handle_existing_refresh(
                    strategy_id=strategy_id,
                    name=name,
                    candidate=candidate,
                    gate=gate,
                    quality_report=quality_report,
                    backtest_metrics=metrics,
                    snapshot=snapshot,
                    validation_report=validation_report,
                    risk_report=risk_report,
                    db=db,
                    existing_status=existing_status,
                    submission_lane=submission_lane,
                    submission_action=submission_action,
                    options=execution_options,
                )
            else:
                post_gate = await self._submission_coordinator.handle_new_candidate(
                    strategy_id=strategy_id,
                    name=name,
                    candidate=candidate,
                    data=data,
                    gate=gate,
                    quality_report=quality_report,
                    backtest_metrics=metrics,
                    snapshot=snapshot,
                    validation_report=validation_report,
                    risk_report=risk_report,
                    db=db,
                    submission_lane=submission_lane,
                    submission_action=submission_action,
                    options=execution_options,
                )
                if not read_only:
                    try:
                        parent_strategy_id = (
                            str((candidate.get("dedup_result") or {}).get("parent_strategy_id") or "").strip()
                            or str(candidate.get("parent_strategy_id") or "").strip()
                            or None
                        )
                        await self._save_strategy_lineage_record(
                            db,
                            strategy_id=strategy_id,
                            parent_strategy_id=parent_strategy_id,
                            reason=str(candidate.get("spawn_reason") or ""),
                            snapshot=snapshot,
                            candidate={**dict(candidate or {}), "multiple_testing_registry": multiple_testing_registry},
                        )
                    except Exception as exc:
                        logger.warning("StrategySubmitter: save lineage failed for %s: %s", strategy_id, exc)
                    if multiple_testing_registry and callable(getattr(db, "save_factory_task_evidence", None)):
                        research_task = _normalize_research_task_contract(candidate.get("research_task") or {})
                        evidence_payload = {
                            "task_key": str(
                                multiple_testing_registry.get("task_key")
                                or multiple_testing_registry.get("registry_key")
                                or multiple_testing_registry.get("task_signature")
                                or strategy_id
                            ).strip(),
                            "event_id": research_task.get("event_id"),
                            "theme_code": str(research_task.get("theme_code") or "").strip(),
                            "symbol": next(iter(_normalize_target_codes(candidate.get("target_symbols") or [])), None),
                            "evidence_type": "multiple_testing_registry",
                            "weight": float((multiple_testing_registry.get("selection_ratio") or 0.0) or 0.0),
                            "evidence_payload": {
                                **multiple_testing_registry,
                                "strategy_id": strategy_id,
                                "status": str(post_gate.get("final_status") or final_status),
                            },
                        }
                        try:
                            persisted_registry = db.save_factory_task_evidence(evidence_payload)
                            if inspect.isawaitable(persisted_registry):
                                persisted_registry = await persisted_registry
                            if isinstance(persisted_registry, dict):
                                multiple_testing_registry_record_id = persisted_registry.get("id")
                                multiple_testing_registry = {
                                    **multiple_testing_registry,
                                    "evidence_record_id": multiple_testing_registry_record_id,
                                }
                        except Exception as exc:
                            logger.warning(
                                "StrategySubmitter: save multiple-testing registry failed for %s: %s",
                                strategy_id,
                                exc,
                            )
            if _semantic_contract_feature_enabled() and not read_only:
                candidate_evidence_rows = build_candidate_evidence_records(
                    candidate,
                    strategy_id=strategy_id,
                )
                if callable(getattr(db, "save_strategy_candidate_evidence", None)):
                    for evidence_payload in candidate_evidence_rows:
                        try:
                            persisted_candidate_evidence = db.save_strategy_candidate_evidence(
                                {
                                    "id": evidence_payload.get("id"),
                                    "candidate_id": evidence_payload.get("candidate_id"),
                                    "strategy_id": strategy_id,
                                    "candidate_artifact_id": evidence_payload.get("candidate_artifact_id"),
                                    "experiment_id": evidence_payload.get("experiment_id"),
                                    "evidence_id": evidence_payload.get("evidence_id"),
                                    "evidence_type": evidence_payload.get("evidence_type"),
                                    "source_type": evidence_payload.get("source_type"),
                                    "event_type": evidence_payload.get("event_type"),
                                    "target_symbols": evidence_payload.get("target_symbols") or [],
                                    "direction": evidence_payload.get("direction"),
                                    "horizon_days": evidence_payload.get("horizon_days"),
                                    "raw_confidence": evidence_payload.get("raw_confidence"),
                                    "calibrated_confidence": evidence_payload.get("calibrated_confidence"),
                                    "freshness_ts": evidence_payload.get("freshness_ts"),
                                    "proxy_only": evidence_payload.get("proxy_only"),
                                    "support_metric": evidence_payload.get("support_metric") or {},
                                    "doc_uid": evidence_payload.get("doc_uid"),
                                    "headline_label_id": evidence_payload.get("headline_label_id"),
                                    "source_task_key": evidence_payload.get("source_task_key") or evidence_payload.get("task_key"),
                                    "payload": evidence_payload.get("evidence_payload") or evidence_payload,
                                }
                            )
                            if inspect.isawaitable(persisted_candidate_evidence):
                                await persisted_candidate_evidence
                        except Exception as exc:
                            logger.warning(
                                "StrategySubmitter: save candidate evidence failed for %s: %s",
                                strategy_id,
                                exc,
                            )
            final_status = str(post_gate.get("final_status") or final_status)
            submission_lane = str(post_gate.get("submission_lane") or submission_lane)
            await self._submission_coordinator.save_quality_report(
                db,
                strategy_id,
                quality_report,
                options=execution_options,
            )

            resolved_submission_action = dict(post_gate.get("submission_action") or submission_action.get("submission_action") or {})
            resolved_submission_action_type = post_gate.get("submission_action_type", submission_action.get("submission_action_type"))
            resolved_submission_action_trigger = post_gate.get("submission_action_trigger", submission_action.get("submission_action_trigger"))
            resolved_submission_action_gaps = list(
                post_gate.get("submission_action_gaps", submission_action.get("submission_action_gaps") or [])
                or []
            )
            resolved_submission_action_fallback_conditions = list(
                post_gate.get(
                    "submission_action_fallback_conditions",
                    submission_action.get("submission_action_fallback_conditions") or [],
                )
                or []
            )
            resolved_submission_action_next_step = post_gate.get(
                "submission_action_next_step",
                submission_action.get("submission_action_next_step"),
            )
            dedup_result = dict(candidate.get("dedup_result") or {})
            constraint_check = dict(candidate.get("constraint_check") or {})
            validation_profile = dict(candidate.get("validation_profile") or {})
            precompile_validation = dict(candidate.get("_generator_precompile_validation") or {})
            precompile_constraint_check = dict(precompile_validation.get("constraint_check") or {})
            feedback_metrics = dict(incubation_budget.get("feedback_metrics") or {})
            target_alignment_violation = (
                str(
                    constraint_check.get("alignment_contract_violation")
                    or precompile_constraint_check.get("alignment_contract_violation")
                    or ""
                ).strip().lower()
                or None
            )
            generator_precompile_reject_reason = (
                str(precompile_validation.get("generator_precompile_reject_reason") or "").strip() or None
            )
            contract_reject_reasons = [
                str(reason).strip()
                for reason in list(precompile_validation.get("contract_reject_reasons") or [])
                if str(reason).strip()
            ]
            feedback_control_mode = str(
                feedback_metrics.get("control_mode")
                or incubation_budget.get("feedback_control_mode")
                or "normal"
            ).strip().lower() or "normal"
            feedback_target_pool_control_mode = str(
                feedback_metrics.get("target_pool_control_mode") or "normal"
            ).strip().lower() or "normal"
            feedback_generator_mode_control_mode = str(
                feedback_metrics.get("generator_mode_control_mode") or "normal"
            ).strip().lower() or "normal"
            prediction_trace_id = normalize_prediction_trace_id(
                candidate.get("prediction_trace_id"),
                candidate.get("trace_id"),
                fallback=quality_summary.get("prediction_trace_id"),
            )
            gate_a_summary = _gate_a_payload(candidate)
            gate_b_summary = _gate_b_payload(candidate, gate)
            gate_c_summary = _gate_c_payload({**candidate, **post_gate}, gate, final_status)

            summary = {
                "strategy_id": strategy_id,
                "prediction_trace_id": prediction_trace_id or None,
                "trace_id": prediction_trace_id or None,
                "experiment_id": candidate.get("experiment_id"),
                "generator_type": candidate.get("generator_type"),
                "name": name,
                "status": final_status,
                "passed": bool(gate.get("passed")),
                "passed_strict": bool(gate.get("passed_strict", gate.get("passed"))),
                "provisional_pass": bool(gate.get("provisional_pass")),
                "admission_stage": gate.get("admission_stage"),
                "incubation_pass_mode": gate.get("incubation_pass_mode"),
                "research_candidate_ready": bool(gate.get("research_candidate_ready")),
                "incubation_candidate_ready": bool(gate.get("incubation_candidate_ready")),
                "live_candidate_ready": bool(gate.get("live_candidate_ready")),
                "gate_b_review_decision": gate.get("gate_b_review_decision"),
                "business_admission_decision": dict(gate.get("business_admission_decision") or {}),
                "benchmark_comparison": dict(gate.get("benchmark_comparison") or {}),
                "cost_sensitivity_summary": dict(gate.get("cost_sensitivity_summary") or {}),
                "cash_sleeve_audit": dict(gate.get("cash_sleeve_audit") or {}),
                "family_holding_bucket": dict(gate.get("family_holding_bucket") or {}),
                "submission_lane": submission_lane,
                "formal_track_requested": bool(
                    post_gate.get("formal_track_requested", submission_action.get("formal_track_requested"))
                ),
                "formal_track_eligible": bool(
                    post_gate.get("formal_track_eligible", submission_action.get("formal_track_eligible"))
                ),
                "formal_track_blockers": list(
                    post_gate.get("formal_track_blockers", submission_action.get("formal_track_blockers") or [])
                ),
                "runtime_bootstrap_reason": post_gate.get(
                    "runtime_bootstrap_reason",
                    submission_action.get("runtime_bootstrap_reason"),
                ),
                "submission_action_type": resolved_submission_action_type,
                "submission_action_trigger": resolved_submission_action_trigger,
                "submission_action_gaps": resolved_submission_action_gaps,
                "submission_action_fallback_conditions": resolved_submission_action_fallback_conditions,
                "submission_action_next_step": resolved_submission_action_next_step,
                "submission_action_completed": bool(
                    post_gate.get("submission_action_completed", submission_action.get("submission_action_completed"))
                ),
                "submission_action": resolved_submission_action,
                "direct_trade_candidate": bool(gate.get("live_candidate_ready")),
                "pool_admission_applied": bool(post_gate.get("pool_admission_applied")),
                "promotion_applied_transition": dict(post_gate.get("promotion_applied_transition") or {}),
                "admission_block_reasons": list(gate.get("admission_block_reasons") or []),
                "admission_evaluations": dict(gate.get("admission_evaluations") or {}),
                "reasons": gate.get("reasons") or [],
                "reason_codes": gate.get("reason_codes") or [],
                "warning_codes": gate.get("warning_codes") or [],
                "gate_3": dict(gate or {}),
                "dedup_result": dedup_result,
                "refresh_mode": dedup_result.get("refresh_mode"),
                "refresh_decision_basis": dedup_result.get("refresh_decision_basis"),
                "revision_trigger_reason": dedup_result.get("revision_trigger_reason"),
                "tested_object_hash_changed": dedup_result.get(
                    "tested_object_hash_changed",
                    dedup_result.get("tested_object_changed"),
                ),
                "existing_identity_available": bool(dedup_result.get("existing_identity_available")),
                "existing_tested_object_available": bool(dedup_result.get("existing_tested_object_available")),
                "constraint_check": constraint_check,
                "validation_profile": validation_profile,
                "target_alignment_violation": target_alignment_violation,
                "generator_precompile_reject_reason": generator_precompile_reject_reason,
                "contract_reject_reasons": contract_reject_reasons,
                "feedback_control_mode": feedback_control_mode,
                "feedback_target_pool_control_mode": feedback_target_pool_control_mode,
                "feedback_generator_mode_control_mode": feedback_generator_mode_control_mode,
                "primary_validation_layer": gate.get("primary_validation_layer"),
                "quality_summary": quality_summary,
                "validation_grade": quality_summary.get("validation_grade"),
                "raw_validation_grade": quality_summary.get("raw_validation_grade"),
                "effective_validation_grade": quality_summary.get("effective_validation_grade"),
                "validation_grade_adjustment_reason": quality_summary.get(
                    "validation_grade_adjustment_reason"
                ),
                "validation_total_score": quality_summary.get("validation_total_score"),
                "raw_validation_total_score": quality_summary.get("raw_validation_total_score"),
                "strict_incubation_ready": bool(
                    quality_summary.get("strict_incubation_ready", gate.get("strict_incubation_ready"))
                ),
                "strict_incubation_blocked": bool(
                    quality_summary.get("strict_incubation_blocked", gate.get("strict_incubation_blocked"))
                ),
                "event_window_config": dict(metrics.get("event_window_config") or {}),
                "event_window_metrics": dict(metrics.get("event_window_metrics") or {}),
                "position_assumption": metrics.get("position_assumption"),
                "cost_assumptions": dict(metrics.get("cost_assumptions") or {}),
                "explicit_cost_breakdown": dict(metrics.get("explicit_cost_breakdown") or {}),
                "implicit_cost_breakdown": dict(metrics.get("implicit_cost_breakdown") or {}),
                "backtest_assumptions": dict(metrics.get("backtest_assumptions") or {}),
                "execution_reality": dict(quality_report.get("execution_reality") or {}),
                "attempt_adjustment": dict(gate.get("attempt_adjustment") or {}),
                "committee_review": dict(candidate.get("committee_review") or {}),
                "run_correction": {
                    "mode": gate.get("run_correction_mode"),
                    "deflated_sharpe_proxy": gate.get("deflated_sharpe_proxy"),
                    "pbo_proxy": gate.get("pbo_proxy"),
                    "reality_check_pvalue_proxy": gate.get("reality_check_pvalue_proxy"),
                    "spa_pvalue_proxy": gate.get("spa_pvalue_proxy"),
                    "multiple_testing_mode": gate.get("multiple_testing_mode"),
                    "deflated_sharpe_ratio": gate.get("deflated_sharpe_ratio"),
                    "deflated_sharpe_reference_sharpe": gate.get("deflated_sharpe_reference_sharpe"),
                    "deflated_sharpe_effective_trials": gate.get("deflated_sharpe_effective_trials"),
                    "pbo": gate.get("pbo"),
                    "white_reality_check_pvalue": gate.get("white_reality_check_pvalue"),
                    "hansen_spa_pvalue": gate.get("hansen_spa_pvalue"),
                    "multiple_testing": dict(gate.get("multiple_testing") or {}),
                },
                "multiple_testing_registry": multiple_testing_registry,
                "multiple_testing_registry_record_id": multiple_testing_registry_record_id,
                "task_preference": dict(gate.get("task_preference") or {}),
                "task_signature": _build_task_signature(candidate.get("research_task") or {}),
                "candidate_contract_hash": candidate.get("candidate_contract_hash"),
                "execution_contract_hash": candidate.get("execution_contract_hash"),
                "tested_object_hash": candidate.get("tested_object_hash"),
                "candidate_identity_signature": candidate.get("candidate_identity_signature"),
                "research_protocol_version": candidate.get("research_protocol_version"),
                "candidate_contract_version": candidate.get("candidate_contract_version"),
                "spec_completeness": candidate.get("spec_completeness"),
                "field_provenance_summary": dict(candidate.get("field_provenance_summary") or {}),
                "completion_issues": list(candidate.get("completion_issues") or []),
                "hard_failures": list(candidate.get("hard_failures") or []),
                "gate_a": gate_a_summary,
                "gate_b": gate_b_summary,
                "gate_c": gate_c_summary,
                "candidate_contract_snapshot": dict(candidate.get("candidate_contract_snapshot") or {}),
                "candidate_lineage_contract": dict(candidate.get("candidate_lineage_contract") or {}),
                "logic_signature": candidate.get("logic_signature"),
                "dsl_signature": candidate.get("dsl_signature"),
                "factor_signature": candidate.get("factor_signature"),
                "entry_exit_signature": candidate.get("entry_exit_signature"),
                "target_pool_id": (
                    dict((candidate.get("candidate_contract_snapshot") or {}).get("targeting") or {}).get("target_pool_id")
                ),
                "candidate_provenance": candidate_provenance,
                "strategy_profile": strategy_profile,
                "source_candidate_artifact_id": candidate_provenance.get("source_candidate_artifact_id"),
                "source_generation_artifact_id": candidate_provenance.get("source_generation_artifact_id"),
                "source_validation_artifact_id": candidate_provenance.get("source_validation_artifact_id"),
                "candidate_memory_record_id": candidate_provenance.get("memory_record_id"),
                "candidate_family": candidate_provenance.get("candidate_family"),
                "candidate_family_id": candidate_provenance.get("candidate_family_id"),
                "holding_period_bucket": candidate_provenance.get("holding_period_bucket"),
                "alpha_source": candidate_provenance.get("alpha_source"),
                "risk_level": candidate_provenance.get("risk_level"),
                "regime_fit": candidate_provenance.get("regime_fit"),
                "generator_mode": candidate_provenance.get("generator_mode"),
                "direction_bias": candidate_provenance.get("direction_bias"),
                "validation_profile_name": candidate_provenance.get("validation_profile"),
                "target_symbol_count": candidate_provenance.get("target_symbol_count"),
                "candidate_registry_stage": candidate_provenance.get("candidate_registry_stage"),
                "candidate_validation_score": candidate_provenance.get("validation_score"),
                "expected_regime": list(candidate_provenance.get("expected_regime") or []),
                "expected_holding_period": candidate_provenance.get("expected_holding_period"),
                "candidate_latest_validation_at": candidate_provenance.get("latest_validation_at"),
                "candidate_latest_validation_age_days": candidate_provenance.get("latest_validation_age_days"),
                "incubation_budget": incubation_budget,
                "incubation_budget_track": incubation_budget_track,
                "incubation_budget_rank": incubation_budget.get("rank"),
                "incubation_budget_priority_score": incubation_budget.get("priority_score"),
                "incubation_budget_exploration_candidate": bool(incubation_budget.get("exploration_candidate")),
                **post_gate,
            }
            created_total = bool(not refresh_existing and not read_only)
            created_strategy_pool = bool(created_total and final_status in {"submitted", "incubating"})
            created_audit_only = bool(not read_only and created_total and not created_strategy_pool)
            summary.update(
                {
                    "created_total": created_total,
                    "created_strategy_pool": created_strategy_pool,
                    "created_audit_only": created_audit_only,
                    "diagnostic_only": bool(read_only),
                    "read_only": bool(read_only),
                }
            )
            for field_name in _SEMANTIC_CONTRACT_FIELDS:
                _assign_optional_payload(summary, field_name, candidate.get(field_name))
            return {
                "created": created_strategy_pool,
                "created_total": created_total,
                "created_strategy_pool": created_strategy_pool,
                "created_audit_only": created_audit_only,
                "refreshed_existing": refresh_existing,
                "submitted": bool(gate.get("passed")),
                "passed": bool(gate.get("passed")),
                "gate_3": dict(gate or {}),
                "summary": summary,
            }

        @staticmethod
        async def _resolve_existing_strategy(candidate: dict, db) -> Optional[dict]:
            dedup_result = dict(candidate.get("dedup_result") or {})
            if not dedup_result.get("refresh_existing"):
                return None
            if str(dedup_result.get("refresh_mode") or "").strip().lower() == "spawn_revision_from_existing":
                return None
            strategy_id = str(dedup_result.get("matched_strategy_id") or "").strip()
            if not strategy_id or not hasattr(db, "get_strategy"):
                return None
            try:
                existing = await db.get_strategy(strategy_id)
            except Exception as exc:
                logger.warning("StrategySubmitter: load existing strategy failed for %s: %s", strategy_id, exc)
                return None
            return dict(existing or {}) if existing else None
