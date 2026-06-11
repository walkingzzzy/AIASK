
        async def _submit_one(
            self,
            candidate: dict,
            snapshot: dict,
            db,
            *,
            read_only: bool = False,
        ) -> dict:
            """处理单个候选策略的完整提交流程。"""
            gate3_record_only = bool(_gate3_record_only_enabled())
            execution_options = SubmissionExecutionOptions(read_only=bool(read_only or gate3_record_only))
            quality_report_options = SubmissionExecutionOptions(
                read_only=read_only,
                record_only=gate3_record_only,
            )
            candidate = apply_resolved_candidate_envelope(candidate)
            candidate = self._ensure_runtime_playbook(candidate)
            run_submission_quality_gate = _local_run_submission_quality_gate

            existing_strategy = await self._resolve_existing_strategy(candidate, db)
            refresh_existing = existing_strategy is not None
            existing_status = str((existing_strategy or {}).get("status") or "draft")
            strategy_id = str((existing_strategy or {}).get("id") or f"factory_{int(_time.time())}_{uuid4().hex[:8]}")
            name = self._candidate_name(candidate, existing_strategy)
            metrics = dict(candidate.get("backtest_metrics") or {})
            backtest_metrics_contract = dict(
                candidate.get("backtest_metrics_contract")
                or metrics.get("backtest_metrics_contract")
                or {}
            )
            if backtest_metrics_contract and not metrics.get("backtest_metrics_contract"):
                metrics["backtest_metrics_contract"] = backtest_metrics_contract
            semantic_audit: dict[str, Any] = {}
            if _semantic_contract_feature_enabled():
                candidate = ensure_candidate_semantic_contract(candidate)
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
                    "backtest_metrics": dict(metrics or {}),
                    "backtest_metrics_contract": dict(backtest_metrics_contract or {}),
                }
            )
            if _semantic_contract_feature_enabled():
                candidate = _apply_candidate_semantic_contract(candidate, semantic_audit)
            validation_report = None
            risk_report = None
            if gate_a_override is None:
                validation_report, risk_report = await self._evaluate_reports(candidate, db)
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
            candidate = self._apply_gate_runtime_context(candidate, gate)
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
                read_only=read_only,
            )
            submission_lane = str(submission_action.get("submission_lane") or "deferred_submission")
            final_status = str(submission_action.get("final_status") or "submitted")
            diagnostic_ok, diagnostic_reason = (False, None)
            if not bool(submission_action.get("wide_intake_admitted")):
                diagnostic_ok, diagnostic_reason = _is_diagnostic_observation_candidate(
                    gate,
                    candidate,
                    metrics,
                    refresh_existing=refresh_existing,
                    read_only=read_only,
                )
            diagnostic_guard: dict[str, Any] = {}
            diagnostic_fingerprint = ""
            if diagnostic_ok:
                diagnostic_reason = diagnostic_reason or "diagnostic_observation"
                diagnostic_fingerprint = _diagnostic_observation_fingerprint(candidate, diagnostic_reason)
                diagnostic_guard = await self._diagnostic_observation_admission_guard(
                    db,
                    candidate=candidate,
                    reason=diagnostic_reason,
                    fingerprint=diagnostic_fingerprint,
                )
            if (
                diagnostic_ok
                and bool(diagnostic_guard.get("allowed"))
                and await self._claim_diagnostic_observation_slot(fingerprint=diagnostic_fingerprint)
            ):
                submission_action = _diagnostic_observation_submission_action(
                    submission_action,
                    reason=diagnostic_reason,
                )
                submission_lane = str(submission_action.get("submission_lane") or "diagnostic_observation")
                final_status = str(submission_action.get("final_status") or "submitted")
                diagnostic_params = {
                    "admission_layer": "diagnostic",
                    "diagnostic_observation": True,
                    "diagnostic_fingerprint": diagnostic_fingerprint,
                    "diagnostic_guard": dict(diagnostic_guard or {}),
                    "diagnostic_reason": diagnostic_reason,
                    "diagnostic_reason_code": diagnostic_reason,
                    "diagnostic_ttl_days": _diagnostic_observation_ttl_days(),
                    "source_lane": "diagnostic_observation",
                }
                nested_action = dict(submission_action.get("submission_action") or {})
                nested_action.update(diagnostic_params)
                submission_action = {
                    **dict(submission_action or {}),
                    **diagnostic_params,
                    "submission_action": nested_action,
                }
                candidate = {
                    **dict(candidate or {}),
                    **diagnostic_params,
                    "params": {
                        **dict(candidate.get("params") or {}),
                        **diagnostic_params,
                    },
                }
            candidate = self._apply_runtime_bootstrap_contract(
                candidate,
                submission_lane=submission_lane,
                runtime_bootstrap_eligible=bool(submission_action.get("runtime_bootstrap_eligible")),
                runtime_bootstrap_budget_tier=str(submission_action.get("runtime_bootstrap_budget_tier") or "") or None,
            )
            planned_submission_lane = str(
                submission_action.get("planned_submission_lane") or submission_lane
            )
            planned_final_status = str(
                submission_action.get("planned_final_status") or final_status
            )
            candidate_params = dict(candidate.get("params") or {})
            if str(submission_lane or "").strip():
                candidate_params["submission_lane"] = submission_lane
            if planned_submission_lane:
                candidate_params["planned_submission_lane"] = planned_submission_lane
            if str(final_status or "").strip():
                candidate_params["final_status"] = final_status
            if planned_final_status:
                candidate_params["planned_final_status"] = planned_final_status
            candidate_params["formal_track_requested"] = bool(
                submission_action.get("formal_track_requested")
            )
            candidate_params["formal_track_auto_corrected"] = bool(
                submission_action.get("formal_track_auto_corrected")
            )
            candidate_params["formal_track_eligible"] = bool(
                submission_action.get("formal_track_eligible")
            )
            candidate_params["observe_first_intake_requested"] = bool(
                submission_action.get("observe_first_intake_requested")
            )
            for field_name in (
                "runtime_bootstrap_eligible",
                "runtime_bootstrap_reason",
                "runtime_bootstrap_budget_tier",
                "wide_intake_admitted",
                "observe_intake_requested",
                "strategy_type_registered",
                "runtime_family_data_source",
                "proxy_runtime_used",
                "diagnostic_only",
                "execution_readiness_tier",
                "trade_prediction_contract_status",
                "trade_prediction_contract_observation_gap",
            ):
                value = submission_action.get(field_name)
                if value not in (None, "", [], {}):
                    candidate_params[field_name] = value
            predicted_incubation_track = str(
                submission_action.get("incubation_budget_track")
                or incubation_budget_track
                or dict(candidate.get("incubation_budget") or {}).get("track")
                or dict(candidate_params.get("incubation_budget") or {}).get("track")
                or ""
            ).strip().lower()
            if predicted_incubation_track:
                candidate_params["incubation_budget_track"] = predicted_incubation_track
            candidate = {
                **dict(candidate or {}),
                "params": candidate_params,
            }
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
                    "backtest_metrics": dict(metrics or {}),
                    "backtest_metrics_contract": dict(backtest_metrics_contract or {}),
                }
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
            if gate3_record_only:
                gate3_quality_record = _build_gate3_quality_record_contract(
                    gate=gate,
                    quality_summary=quality_summary,
                    read_only=read_only,
                    gate3_record_only=gate3_record_only,
                )
                planned_submission_lane = submission_lane
                planned_final_status = final_status
                record_status = "gate3_record_passed" if bool(gate.get("passed")) else "gate3_record_failed"
                record_action = dict(submission_action.get("submission_action") or {})
                record_action.update(
                    {
                        "type": "gate3_record_only",
                        "trigger_reason": "gate3_record_only",
                        "next_step": "await_manual_record_review",
                        "completed": False,
                        "planned_submission_lane": planned_submission_lane,
                        "planned_final_status": planned_final_status,
                        "record_status": record_status,
                        "strategy_created": False,
                        "lifecycle_action_executed": False,
                    }
                )
                submission_lane = "gate3_record_only"
                final_status = "gate3_recorded"
                post_gate = {
                    "submission_lane": submission_lane,
                    "final_status": final_status,
                    "planned_submission_lane": planned_submission_lane,
                    "planned_final_status": planned_final_status,
                    "gate3_record_only": True,
                    "record_only": True,
                    "gate_3_recorded": bool(not read_only),
                    "gate3_record_status": record_status,
                    **gate3_quality_record,
                    "quality_report_record_only": True,
                    "quality_report_persisted": False,
                    "gate3_audit_evidence_persisted": False,
                    "record_only_scope": "gate3_audit_evidence",
                    "automatic_downstream_action": False,
                    "strategy_created": False,
                    "lifecycle_action_executed": False,
                    "submission_action": record_action,
                    "submission_action_type": "gate3_record_only",
                    "submission_action_trigger": "gate3_record_only",
                    "submission_action_gaps": list(submission_action.get("submission_action_gaps") or []),
                    "submission_action_fallback_conditions": list(
                        submission_action.get("submission_action_fallback_conditions") or []
                    ),
                    "submission_action_next_step": "await_manual_record_review",
                    "submission_action_completed": False,
                    "admission_decision": submission_action.get("admission_decision"),
                    "formal_track_requested": bool(submission_action.get("formal_track_requested")),
                    "formal_track_eligible": bool(submission_action.get("formal_track_eligible")),
                    "formal_track_blockers": list(submission_action.get("formal_track_blockers") or []),
                    "runtime_bootstrap_reason": submission_action.get("runtime_bootstrap_reason"),
                    "wide_intake_admitted": bool(submission_action.get("wide_intake_admitted")),
                }
                self._apply_submission_action_audit(
                    quality_report,
                    final_status=final_status,
                    submission_lane=submission_lane,
                    submission_audit=post_gate,
                )
                if not read_only:
                    await self._record_experiment(
                        db,
                        candidate,
                        strategy_id,
                        name,
                        snapshot,
                        gate,
                        record_status,
                        validation_report,
                        risk_report,
                        quality_report,
                        metrics,
                        None,
                    )
                    evidence_record = await self._record_gate3_audit_evidence(
                        db,
                        candidate,
                        strategy_id,
                        snapshot,
                        gate,
                        quality_report,
                        metrics,
                        status=record_status,
                        planned_submission_lane=planned_submission_lane,
                        planned_final_status=planned_final_status,
                    )
                    if evidence_record:
                        post_gate["gate3_audit_evidence_id"] = evidence_record.get("id")
                        post_gate["gate3_audit_evidence_persisted"] = True
            else:
                await self._submission_coordinator.persist_candidate(
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
            if _semantic_contract_feature_enabled() and not read_only and not gate3_record_only:
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
            if gate3_record_only:
                factor_performance_report = {
                    "reported": False,
                    "skipped": True,
                    "reason": "gate3_record_only",
                }
            else:
                factor_performance_report = await self._report_factor_performance_after_submit(
                    candidate=candidate,
                    strategy_id=strategy_id,
                    metrics=metrics,
                    validation_report=validation_report,
                    gate=gate,
                    read_only=read_only,
                )
            quality_summary = dict(quality_report.get("summary") or {})
            candidate_params = dict(candidate.get("params") or {})
            candidate_budget = dict(candidate.get("incubation_budget") or {})
            if not candidate_budget:
                candidate_budget = dict(candidate_params.get("incubation_budget") or {})

            def _pick_value(*values: Any) -> Any:
                for value in values:
                    if value not in (None, "", [], {}):
                        return value
                return None

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
            for field_name in (
                "runtime_bootstrap_eligible",
                "runtime_bootstrap_reason",
                "runtime_bootstrap_budget_tier",
                "runtime_playbook_present",
                "runtime_contract_missing_fields",
                "wide_intake_admitted",
                "observe_intake_requested",
                "pre_observe_hard_reject_reasons",
                "strategy_type_registered",
                "formal_track_requested",
                "formal_track_auto_corrected",
                "formal_track_eligible",
                "formal_track_blockers",
                "observe_first_intake_requested",
                "planned_submission_lane",
                "planned_final_status",
                "execution_semantic_mode",
                "execution_semantic_gap",
                "execution_semantic_gap_reasons",
                "dsl_required",
                "dsl_compiled",
                "semantic_runtime_match",
                "runtime_family_data_source",
                "proxy_runtime_used",
                "diagnostic_only",
                "execution_readiness_tier",
                "semantic_contract_missing_fields",
                "trade_prediction_contract_status",
                "trade_prediction_contract_hash",
                "trade_prediction_contract_missing_fields",
                "trade_prediction_contract_reject_reasons",
                "trade_prediction_contract_observation_gap",
            ):
                value = _pick_value(
                    resolved_submission_action.get(field_name),
                    post_gate.get(field_name),
                    quality_summary.get(field_name),
                    gate.get(field_name),
                    candidate.get(field_name),
                    candidate_params.get(field_name),
                )
                if value not in (None, "", [], {}):
                    resolved_submission_action[field_name] = value
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

            summary = dict(quality_summary)
            summary.update({
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
                "formal_track_auto_corrected": bool(
                    post_gate.get(
                        "formal_track_auto_corrected",
                        submission_action.get("formal_track_auto_corrected"),
                    )
                ),
                "formal_track_eligible": bool(
                    post_gate.get("formal_track_eligible", submission_action.get("formal_track_eligible"))
                ),
                "formal_track_blockers": list(
                    post_gate.get("formal_track_blockers", submission_action.get("formal_track_blockers") or [])
                ),
                "observe_first_intake_requested": bool(
                    post_gate.get(
                        "observe_first_intake_requested",
                        submission_action.get("observe_first_intake_requested"),
                    )
                ),
                "planned_submission_lane": post_gate.get(
                    "planned_submission_lane",
                    _pick_value(
                        submission_action.get("planned_submission_lane"),
                        resolved_submission_action.get("planned_submission_lane"),
                        submission_lane,
                    ),
                ),
                "planned_final_status": post_gate.get(
                    "planned_final_status",
                    _pick_value(
                        submission_action.get("planned_final_status"),
                        resolved_submission_action.get("planned_final_status"),
                        final_status,
                    ),
                ),
                "runtime_bootstrap_reason": post_gate.get(
                    "runtime_bootstrap_reason",
                    _pick_value(
                        submission_action.get("runtime_bootstrap_reason"),
                        resolved_submission_action.get("runtime_bootstrap_reason"),
                        quality_summary.get("runtime_bootstrap_reason"),
                        gate.get("runtime_bootstrap_reason"),
                        candidate.get("runtime_bootstrap_reason"),
                        candidate_params.get("runtime_bootstrap_reason"),
                    ),
                ),
                "runtime_bootstrap_eligible": bool(
                    post_gate.get(
                        "runtime_bootstrap_eligible",
                        _pick_value(
                            submission_action.get("runtime_bootstrap_eligible"),
                            resolved_submission_action.get("runtime_bootstrap_eligible"),
                            quality_summary.get("runtime_bootstrap_eligible"),
                            gate.get("runtime_bootstrap_eligible"),
                            candidate.get("runtime_bootstrap_eligible"),
                            candidate_params.get("runtime_bootstrap_eligible"),
                        ),
                    )
                ),
                "runtime_bootstrap_budget_tier": post_gate.get(
                    "runtime_bootstrap_budget_tier",
                    _pick_value(
                        submission_action.get("runtime_bootstrap_budget_tier"),
                        resolved_submission_action.get("runtime_bootstrap_budget_tier"),
                        quality_summary.get("runtime_bootstrap_budget_tier"),
                        gate.get("runtime_bootstrap_budget_tier"),
                        candidate.get("runtime_bootstrap_budget_tier"),
                        candidate_params.get("runtime_bootstrap_budget_tier"),
                    ),
                ),
                "runtime_playbook_present": bool(
                    post_gate.get(
                        "runtime_playbook_present",
                        _pick_value(
                            submission_action.get("runtime_playbook_present"),
                            resolved_submission_action.get("runtime_playbook_present"),
                            quality_summary.get("runtime_playbook_present"),
                            gate.get("runtime_playbook_present"),
                            candidate.get("runtime_playbook_present"),
                            candidate_params.get("runtime_playbook_present"),
                        ),
                    )
                ),
                "runtime_contract_missing_fields": list(
                    post_gate.get(
                        "runtime_contract_missing_fields",
                        _pick_value(
                            submission_action.get("runtime_contract_missing_fields"),
                            resolved_submission_action.get("runtime_contract_missing_fields"),
                            quality_summary.get("runtime_contract_missing_fields"),
                            gate.get("runtime_contract_missing_fields"),
                            candidate.get("runtime_contract_missing_fields"),
                            candidate_params.get("runtime_contract_missing_fields"),
                            [],
                        ) or [],
                    )
                ),
                "wide_intake_admitted": bool(
                    post_gate.get(
                        "wide_intake_admitted",
                        _pick_value(
                            submission_action.get("wide_intake_admitted"),
                            resolved_submission_action.get("wide_intake_admitted"),
                            quality_summary.get("wide_intake_admitted"),
                            gate.get("wide_intake_admitted"),
                            candidate.get("wide_intake_admitted"),
                            candidate_params.get("wide_intake_admitted"),
                        ),
                    )
                ),
                "observe_intake_requested": bool(
                    post_gate.get(
                        "observe_intake_requested",
                        _pick_value(
                            submission_action.get("observe_intake_requested"),
                            resolved_submission_action.get("observe_intake_requested"),
                            quality_summary.get("observe_intake_requested"),
                            gate.get("observe_intake_requested"),
                            candidate.get("observe_intake_requested"),
                            candidate_params.get("observe_intake_requested"),
                        ),
                    )
                ),
                "pre_observe_hard_reject_reasons": list(
                    post_gate.get(
                        "pre_observe_hard_reject_reasons",
                        submission_action.get("pre_observe_hard_reject_reasons") or [],
                    )
                ),
                "strategy_type_registered": bool(
                    post_gate.get(
                        "strategy_type_registered",
                        submission_action.get("strategy_type_registered"),
                    )
                ),
                "execution_semantic_mode": post_gate.get(
                    "execution_semantic_mode",
                    _pick_value(
                        submission_action.get("execution_semantic_mode"),
                        resolved_submission_action.get("execution_semantic_mode"),
                        quality_summary.get("execution_semantic_mode"),
                        gate.get("execution_semantic_mode"),
                        candidate.get("execution_semantic_mode"),
                        candidate_params.get("execution_semantic_mode"),
                    ),
                ),
                "execution_semantic_gap": bool(
                    post_gate.get(
                        "execution_semantic_gap",
                        _pick_value(
                            submission_action.get("execution_semantic_gap"),
                            resolved_submission_action.get("execution_semantic_gap"),
                            quality_summary.get("execution_semantic_gap"),
                            gate.get("execution_semantic_gap"),
                            candidate.get("execution_semantic_gap"),
                            candidate_params.get("execution_semantic_gap"),
                        ),
                    )
                ),
                "execution_semantic_gap_reasons": list(
                    post_gate.get(
                        "execution_semantic_gap_reasons",
                        submission_action.get("execution_semantic_gap_reasons") or [],
                    )
                ),
                "dsl_required": bool(
                    post_gate.get(
                        "dsl_required",
                        submission_action.get("dsl_required"),
                    )
                ),
                "dsl_compiled": bool(
                    post_gate.get(
                        "dsl_compiled",
                        submission_action.get("dsl_compiled"),
                    )
                ),
                "semantic_runtime_match": bool(
                    post_gate.get(
                        "semantic_runtime_match",
                        _pick_value(
                            submission_action.get("semantic_runtime_match"),
                            resolved_submission_action.get("semantic_runtime_match"),
                            quality_summary.get("semantic_runtime_match"),
                            gate.get("semantic_runtime_match"),
                            candidate.get("semantic_runtime_match"),
                            candidate_params.get("semantic_runtime_match"),
                        ),
                    )
                ),
                "runtime_family_data_source": post_gate.get(
                    "runtime_family_data_source",
                    _pick_value(
                        submission_action.get("runtime_family_data_source"),
                        resolved_submission_action.get("runtime_family_data_source"),
                        quality_summary.get("runtime_family_data_source"),
                        gate.get("runtime_family_data_source"),
                        candidate.get("runtime_family_data_source"),
                        candidate_params.get("runtime_family_data_source"),
                    ),
                ),
                "proxy_runtime_used": bool(
                    post_gate.get(
                        "proxy_runtime_used",
                        _pick_value(
                            submission_action.get("proxy_runtime_used"),
                            resolved_submission_action.get("proxy_runtime_used"),
                            quality_summary.get("proxy_runtime_used"),
                            gate.get("proxy_runtime_used"),
                            candidate.get("proxy_runtime_used"),
                            candidate_params.get("proxy_runtime_used"),
                        ),
                    )
                ),
                "execution_readiness_tier": post_gate.get(
                    "execution_readiness_tier",
                    _pick_value(
                        submission_action.get("execution_readiness_tier"),
                        resolved_submission_action.get("execution_readiness_tier"),
                        quality_summary.get("execution_readiness_tier"),
                        gate.get("execution_readiness_tier"),
                        candidate.get("execution_readiness_tier"),
                        candidate_params.get("execution_readiness_tier"),
                    ),
                ),
                "semantic_contract_missing_fields": list(
                    post_gate.get(
                        "semantic_contract_missing_fields",
                        submission_action.get("semantic_contract_missing_fields") or [],
                    )
                ),
                "trade_prediction_contract_status": post_gate.get(
                    "trade_prediction_contract_status",
                    _pick_value(
                        submission_action.get("trade_prediction_contract_status"),
                        resolved_submission_action.get("trade_prediction_contract_status"),
                        quality_summary.get("trade_prediction_contract_status"),
                        gate.get("trade_prediction_contract_status"),
                        candidate.get("trade_prediction_contract_status"),
                        candidate_params.get("trade_prediction_contract_status"),
                    ),
                ),
                "trade_prediction_contract_hash": post_gate.get(
                    "trade_prediction_contract_hash",
                    _pick_value(
                        submission_action.get("trade_prediction_contract_hash"),
                        resolved_submission_action.get("trade_prediction_contract_hash"),
                        quality_summary.get("trade_prediction_contract_hash"),
                        gate.get("trade_prediction_contract_hash"),
                        candidate.get("trade_prediction_contract_hash"),
                        candidate_params.get("trade_prediction_contract_hash"),
                    ),
                ),
                "trade_prediction_contract_missing_fields": list(
                    post_gate.get(
                        "trade_prediction_contract_missing_fields",
                        submission_action.get("trade_prediction_contract_missing_fields") or [],
                    )
                ),
                "trade_prediction_contract_reject_reasons": list(
                    post_gate.get(
                        "trade_prediction_contract_reject_reasons",
                        submission_action.get("trade_prediction_contract_reject_reasons") or [],
                    )
                ),
                "trade_prediction_contract_observation_gap": bool(
                    post_gate.get(
                        "trade_prediction_contract_observation_gap",
                        _pick_value(
                            submission_action.get("trade_prediction_contract_observation_gap"),
                            resolved_submission_action.get("trade_prediction_contract_observation_gap"),
                            quality_summary.get("trade_prediction_contract_observation_gap"),
                            gate.get("trade_prediction_contract_observation_gap"),
                            candidate.get("trade_prediction_contract_observation_gap"),
                            candidate_params.get("trade_prediction_contract_observation_gap"),
                        ),
                    )
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
                "admission_decision_contract_version": submission_action.get(
                    "admission_decision_contract_version"
                ),
                "admission_decision": submission_action.get("admission_decision"),
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
                "factor_performance_reported": bool(factor_performance_report.get("reported")),
                "factor_performance_report": factor_performance_report,
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
                "incubation_budget_track": _pick_value(
                    post_gate.get("incubation_budget_track"),
                    incubation_budget_track,
                    candidate_budget.get("track"),
                    dict(candidate_params.get("incubation_budget") or {}).get("track"),
                    quality_summary.get("incubation_budget_track"),
                ),
                "incubation_budget_rank": _pick_value(
                    post_gate.get("incubation_budget_rank"),
                    incubation_budget.get("rank"),
                    candidate_budget.get("rank"),
                    quality_summary.get("incubation_budget_rank"),
                ),
                "incubation_budget_priority_score": _pick_value(
                    post_gate.get("incubation_budget_priority_score"),
                    incubation_budget.get("priority_score"),
                    candidate_budget.get("priority_score"),
                    quality_summary.get("incubation_budget_priority_score"),
                ),
                "incubation_budget_exploration_candidate": bool(incubation_budget.get("exploration_candidate")),
                **post_gate,
            })
            created_total = bool(not refresh_existing and not read_only)
            created_strategy_pool = bool(
                created_total
                and final_status in {"submitted", "incubating"}
                and submission_lane != "diagnostic_observation"
            )
            created_audit_only = bool(not read_only and created_total and not created_strategy_pool)
            gate_3_recorded = bool(not read_only and gate3_record_only)
            gate3_quality_record = _build_gate3_quality_record_contract(
                gate=gate,
                quality_summary=quality_summary,
                read_only=read_only,
                gate3_record_only=gate3_record_only,
            )
            submitted = bool(
                final_status == "submitted"
                and not read_only
                and not gate3_record_only
            )
            resolved_diagnostic_only = post_gate.get("diagnostic_only")
            if resolved_diagnostic_only is None:
                resolved_diagnostic_only = quality_summary.get("diagnostic_only")
            if resolved_diagnostic_only is None:
                resolved_diagnostic_only = gate.get("diagnostic_only")
            if resolved_diagnostic_only is None:
                resolved_diagnostic_only = candidate.get("diagnostic_only")
            summary.update(
                {
                    "created_total": created_total,
                    "created_strategy_pool": created_strategy_pool,
                    "created_audit_only": created_audit_only,
                    "gate_3_recorded": gate_3_recorded,
                    "record_only": bool(gate3_record_only),
                    "gate3_record_only": bool(gate3_record_only),
                    "diagnostic_only": bool(
                        read_only if resolved_diagnostic_only is None else resolved_diagnostic_only
                    ),
                    "read_only": bool(read_only),
                    **gate3_quality_record,
                }
            )
            for field_name in _SEMANTIC_CONTRACT_FIELDS:
                _assign_optional_payload(summary, field_name, candidate.get(field_name))
            quality_report["summary"] = summary
            await self._submission_coordinator.save_quality_report(
                db,
                strategy_id,
                quality_report,
                options=quality_report_options,
            )
            return {
                "created": created_strategy_pool,
                "created_total": created_total,
                "created_strategy_pool": created_strategy_pool,
                "created_audit_only": created_audit_only,
                "gate_3_recorded": gate_3_recorded,
                **gate3_quality_record,
                "record_only": bool(gate3_record_only),
                "refreshed_existing": refresh_existing,
                "submitted": submitted,
                "passed": bool(gate.get("passed")),
                "gate_3": dict(gate or {}),
                "admission_decision_contract_version": submission_action.get(
                    "admission_decision_contract_version"
                ),
                "admission_decision": submission_action.get("admission_decision"),
                "factor_performance_reported": bool(factor_performance_report.get("reported")),
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
