
        async def replay_existing_submission(
            self,
            strategy: dict,
            snapshot: dict,
            db,
            *,
            validation_report: Optional[dict] = None,
            risk_report: Optional[dict] = None,
            backtest_metrics: Optional[dict] = None,
            latest_report: Optional[dict] = None,
            read_only: bool = False,
        ) -> dict[str, Any]:
            strategy_payload = dict(strategy or {})
            strategy_id = str(strategy_payload.get("id") or "").strip()
            if not strategy_id:
                raise ValueError("strategy_id is required for replay_existing_submission")
            execution_options = SubmissionExecutionOptions(read_only=read_only)
            name = str(strategy_payload.get("name") or strategy_id).strip()
            report = dict(latest_report or {})
            metrics = dict(backtest_metrics or report.get("backtest_metrics") or {})
            candidate = self._build_replay_candidate(
                strategy_payload,
                latest_report=report,
                backtest_metrics=metrics,
            )
            semantic_audit: dict[str, Any] = {}
            if _semantic_contract_feature_enabled():
                candidate["confidence_contract"] = synthesize_confidence_contract(candidate)
                semantic_audit = audit_candidate_semantic_contract(candidate)
                candidate = _apply_candidate_semantic_contract(candidate, semantic_audit)
            incubation_budget = dict(candidate.get("incubation_budget") or {})
            incubation_budget_track = str(
                incubation_budget.get("track")
                or dict(report.get("summary") or {}).get("incubation_budget_track")
                or "formal_incubation"
            ).strip().lower() or "formal_incubation"
            run_submission_quality_gate = _local_run_submission_quality_gate
            gate = await run_submission_quality_gate(
                db,
                {**strategy_payload, "status": strategy_payload.get("status")},
                validation_report=validation_report,
                risk_report=risk_report,
                backtest_metrics={
                    **dict(metrics or {}),
                    "trade_count": metrics.get("trade_count"),
                    "trades_count": metrics.get("trades_count"),
                },
                incubation_budget_track=incubation_budget_track,
            )
            gate = self._apply_factory_submission_policy(
                candidate,
                name=name,
                gate=gate,
                backtest_metrics=metrics,
                refresh_existing=False,
            )
            if _semantic_contract_feature_enabled():
                gate = _apply_semantic_contract_gate(gate, semantic_audit)
            submission_action = self._resolve_submission_action_plan(
                gate,
                candidate=candidate,
                refresh_existing=False,
                existing_status=str(strategy_payload.get("status") or "submitted"),
                incubation_budget_track=incubation_budget_track,
            )
            submission_lane = str(submission_action.get("submission_lane") or "deferred_submission")
            final_status = str(submission_action.get("final_status") or strategy_payload.get("status") or "submitted")
            candidate = self._apply_runtime_bootstrap_contract(
                candidate,
                submission_lane=submission_lane,
                runtime_bootstrap_eligible=bool(submission_action.get("runtime_bootstrap_eligible")),
                runtime_bootstrap_budget_tier=str(submission_action.get("runtime_bootstrap_budget_tier") or "") or None,
            )
            strategy_payload = {
                **strategy_payload,
                "params": {
                    **dict(strategy_payload.get("params") or {}),
                    "runtime_playbook": dict(candidate.get("runtime_playbook") or {}),
                },
            }
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
            post_gate = await self._submission_coordinator.handle_new_candidate(
                strategy_id=strategy_id,
                name=name,
                candidate=candidate,
                data=strategy_payload,
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
            final_status = str(post_gate.get("final_status") or final_status)
            submission_lane = str(post_gate.get("submission_lane") or submission_lane)
            await self._submission_coordinator.save_quality_report(
                db,
                strategy_id,
                quality_report,
                options=execution_options,
            )
            return {
                "strategy_id": strategy_id,
                "name": name,
                "status": final_status,
                "submission_lane": submission_lane,
                "incubation_budget_track": incubation_budget_track,
                "gate": dict(gate or {}),
                "quality_report": quality_report,
                "diagnostic_only": bool(read_only),
                **dict(post_gate or {}),
            }

        @classmethod
        async def _record_experiment(
            cls,
            db,
            candidate: dict,
            strategy_id: str,
            name: str,
            snapshot: dict,
            gate: dict,
            status: str,
            validation_report: Optional[dict],
            risk_report: Optional[dict],
            quality_report: Optional[dict],
            backtest_metrics: Optional[dict],
            incubation_pipeline: Optional[dict],
        ) -> None:
            """记录策略生成实验（通过/未通过共用）。"""
            experiment_id = candidate.get("experiment_id")
            if not experiment_id or not hasattr(db, "save_strategy_generation_experiment"):
                return

            def _assign_if_present(target: dict, key: str, value) -> None:
                if value not in (None, [], {}, ""):
                    target[key] = value

            try:
                existing = await db.get_strategy_generation_experiment(experiment_id) if hasattr(db, "get_strategy_generation_experiment") else None
                existing = dict(existing or {})
                existing_spec = dict(existing.get("strategy_spec") or {})
                existing_evaluation = dict(existing.get("evaluation") or {})
                existing_result = dict(existing.get("result") or {})
                candidate_provenance = cls._candidate_provenance(candidate)
                quality_payload = dict(quality_report or {})
                backtest_payload = dict(backtest_metrics or {})
                event_window_config = dict(
                    quality_payload.get("event_window_config")
                    or backtest_payload.get("event_window_config")
                    or {}
                )
                event_window_metrics = dict(
                    quality_payload.get("event_window_metrics")
                    or backtest_payload.get("event_window_metrics")
                    or {}
                )
                cost_assumptions = dict(
                    quality_payload.get("cost_assumptions")
                    or backtest_payload.get("cost_assumptions")
                    or {}
                )
                backtest_assumptions = dict(
                    quality_payload.get("backtest_assumptions")
                    or backtest_payload.get("backtest_assumptions")
                    or {}
                )
                execution_reality = dict(quality_payload.get("execution_reality") or {})
                quality_summary = dict(quality_payload.get("summary") or {})

                research_task = _normalize_research_task_contract(
                    dict(candidate.get("research_task") or {})
                    or dict(existing_spec.get("research_task") or {})
                    or dict(existing_evaluation.get("research_task") or {})
                )
                contract_snapshot = dict(candidate.get("candidate_contract_snapshot") or {})
                try:
                    contract_snapshot = build_portfolio_candidate_contract(
                        {
                            **dict(candidate or {}),
                            "research_task": research_task,
                        }
                    )
                except Exception as exc:
                    logger.warning(
                        "StrategySubmitter: rebuild candidate contract snapshot failed for %s: %s",
                        strategy_id,
                        exc,
                    )
                    if research_task:
                        contract_snapshot = {
                            **contract_snapshot,
                            "research_task": research_task,
                        }
                candidate_lineage_contract = dict(
                    candidate.get("candidate_lineage_contract")
                    or contract_snapshot.get("lineage")
                    or {}
                )
                event_context = (
                    dict(candidate.get("event_context") or {})
                    or _extract_event_context(research_task)
                    or dict(existing_spec.get("event_context") or {})
                    or dict(existing_evaluation.get("event_context") or {})
                )
                parameters = {
                    **dict(existing.get("parameters") or {}),
                    **dict(candidate.get("params") or {}),
                }
                _assign_if_present(parameters, "target_symbols", list(candidate.get("target_symbols") or parameters.get("target_symbols") or []))
                _assign_if_present(parameters, "stock_pool", dict(candidate.get("stock_pool") or parameters.get("stock_pool") or {}))
                _assign_if_present(parameters, "research_task", research_task)
                _assign_if_present(parameters, "event_context", event_context)
                _assign_if_present(parameters, "candidate_contract_snapshot", contract_snapshot)
                _assign_if_present(parameters, "candidate_lineage_contract", candidate_lineage_contract)
                _assign_if_present(parameters, "candidate_provenance", candidate_provenance)
                _assign_if_present(parameters, "source_candidate_artifact_id", candidate_provenance.get("source_candidate_artifact_id"))
                _assign_if_present(parameters, "candidate_family", candidate_provenance.get("candidate_family"))
                _assign_if_present(parameters, "strategy_profile", candidate_provenance.get("strategy_profile"))
                _assign_if_present(parameters, "candidate_family_id", candidate_provenance.get("candidate_family_id"))
                _assign_if_present(parameters, "holding_period_bucket", candidate_provenance.get("holding_period_bucket"))
                _assign_if_present(parameters, "alpha_source", candidate_provenance.get("alpha_source"))
                _assign_if_present(parameters, "risk_level", candidate_provenance.get("risk_level"))
                _assign_if_present(parameters, "regime_fit", candidate_provenance.get("regime_fit"))
                _assign_if_present(parameters, "generator_mode", candidate_provenance.get("generator_mode"))
                _assign_if_present(parameters, "direction_bias", candidate_provenance.get("direction_bias"))
                _assign_if_present(parameters, "validation_profile_name", candidate_provenance.get("validation_profile"))
                _assign_if_present(parameters, "target_symbol_count", candidate_provenance.get("target_symbol_count"))
                _assign_if_present(parameters, "candidate_contract_hash", candidate.get("candidate_contract_hash"))
                _assign_if_present(parameters, "execution_contract_hash", candidate.get("execution_contract_hash"))
                _assign_if_present(parameters, "tested_object_hash", candidate.get("tested_object_hash"))
                _assign_if_present(parameters, "candidate_identity_signature", candidate.get("candidate_identity_signature"))
                _assign_if_present(parameters, "logic_signature", candidate.get("logic_signature"))
                _assign_if_present(parameters, "dsl_signature", candidate.get("dsl_signature"))
                _assign_if_present(parameters, "factor_signature", candidate.get("factor_signature"))
                _assign_if_present(parameters, "entry_exit_signature", candidate.get("entry_exit_signature"))
                for field_name in _SEMANTIC_CONTRACT_FIELDS:
                    _assign_if_present(parameters, field_name, candidate.get(field_name))

                strategy_spec = dict(existing_spec)
                _assign_if_present(strategy_spec, "strategy_type", candidate.get("strategy_type"))
                _assign_if_present(strategy_spec, "name", name)
                _assign_if_present(strategy_spec, "params", candidate.get("params") or existing_spec.get("params"))
                _assign_if_present(strategy_spec, "target_symbols", list(candidate.get("target_symbols") or existing_spec.get("target_symbols") or []))
                _assign_if_present(strategy_spec, "stock_pool", dict(candidate.get("stock_pool") or existing_spec.get("stock_pool") or {}))
                _assign_if_present(strategy_spec, "selection_logic", list(candidate.get("selection_logic") or existing_spec.get("selection_logic") or []))
                _assign_if_present(strategy_spec, "research_scope", dict(candidate.get("research_scope") or existing_spec.get("research_scope") or {}))
                _assign_if_present(strategy_spec, "research_task", research_task)
                _assign_if_present(strategy_spec, "event_context", event_context)
                _assign_if_present(strategy_spec, "candidate_provenance", candidate_provenance)
                _assign_if_present(strategy_spec, "source_candidate_artifact_id", candidate_provenance.get("source_candidate_artifact_id"))
                _assign_if_present(strategy_spec, "candidate_family", candidate_provenance.get("candidate_family"))
                _assign_if_present(strategy_spec, "strategy_profile", candidate_provenance.get("strategy_profile"))
                _assign_if_present(strategy_spec, "candidate_family_id", candidate_provenance.get("candidate_family_id"))
                _assign_if_present(strategy_spec, "holding_period_bucket", candidate_provenance.get("holding_period_bucket"))
                _assign_if_present(strategy_spec, "alpha_source", candidate_provenance.get("alpha_source"))
                _assign_if_present(strategy_spec, "risk_level", candidate_provenance.get("risk_level"))
                _assign_if_present(strategy_spec, "regime_fit", candidate_provenance.get("regime_fit"))
                _assign_if_present(strategy_spec, "generator_mode", candidate_provenance.get("generator_mode"))
                _assign_if_present(strategy_spec, "direction_bias", candidate_provenance.get("direction_bias"))
                _assign_if_present(strategy_spec, "validation_profile_name", candidate_provenance.get("validation_profile"))
                _assign_if_present(strategy_spec, "target_symbol_count", candidate_provenance.get("target_symbol_count"))
                _assign_if_present(strategy_spec, "candidate_contract_hash", candidate.get("candidate_contract_hash"))
                _assign_if_present(strategy_spec, "execution_contract_hash", candidate.get("execution_contract_hash"))
                _assign_if_present(strategy_spec, "tested_object_hash", candidate.get("tested_object_hash"))
                _assign_if_present(strategy_spec, "candidate_identity_signature", candidate.get("candidate_identity_signature"))
                _assign_if_present(strategy_spec, "candidate_contract_snapshot", contract_snapshot)
                _assign_if_present(strategy_spec, "candidate_lineage_contract", candidate_lineage_contract)
                _assign_if_present(strategy_spec, "logic_signature", candidate.get("logic_signature"))
                _assign_if_present(strategy_spec, "dsl_signature", candidate.get("dsl_signature"))
                _assign_if_present(strategy_spec, "factor_signature", candidate.get("factor_signature"))
                _assign_if_present(strategy_spec, "entry_exit_signature", candidate.get("entry_exit_signature"))
                for field_name in _SEMANTIC_CONTRACT_FIELDS:
                    _assign_if_present(strategy_spec, field_name, candidate.get(field_name))

                evaluation = dict(existing_evaluation)
                _assign_if_present(evaluation, "generation_reason", candidate.get("generation_reason") or existing_evaluation.get("generation_reason"))
                _assign_if_present(evaluation, "llm_prompt", candidate.get("llm_prompt") or existing_evaluation.get("llm_prompt"))
                _assign_if_present(evaluation, "llm_response", candidate.get("llm_response") or existing_evaluation.get("llm_response"))
                _assign_if_present(evaluation, "target_symbols", list(candidate.get("target_symbols") or strategy_spec.get("target_symbols") or []))
                _assign_if_present(evaluation, "stock_pool", dict(candidate.get("stock_pool") or strategy_spec.get("stock_pool") or {}))
                _assign_if_present(evaluation, "selection_logic", list(candidate.get("selection_logic") or strategy_spec.get("selection_logic") or []))
                _assign_if_present(evaluation, "research_scope", dict(candidate.get("research_scope") or strategy_spec.get("research_scope") or {}))
                _assign_if_present(evaluation, "research_task", research_task)
                _assign_if_present(evaluation, "event_context", event_context)
                _assign_if_present(evaluation, "candidate_provenance", candidate_provenance)
                _assign_if_present(evaluation, "source_candidate_artifact_id", candidate_provenance.get("source_candidate_artifact_id"))
                _assign_if_present(evaluation, "candidate_family", candidate_provenance.get("candidate_family"))
                _assign_if_present(evaluation, "strategy_profile", candidate_provenance.get("strategy_profile"))
                _assign_if_present(evaluation, "candidate_family_id", candidate_provenance.get("candidate_family_id"))
                _assign_if_present(evaluation, "holding_period_bucket", candidate_provenance.get("holding_period_bucket"))
                _assign_if_present(evaluation, "alpha_source", candidate_provenance.get("alpha_source"))
                _assign_if_present(evaluation, "risk_level", candidate_provenance.get("risk_level"))
                _assign_if_present(evaluation, "regime_fit", candidate_provenance.get("regime_fit"))
                _assign_if_present(evaluation, "generator_mode", candidate_provenance.get("generator_mode"))
                _assign_if_present(evaluation, "direction_bias", candidate_provenance.get("direction_bias"))
                _assign_if_present(evaluation, "validation_profile_name", candidate_provenance.get("validation_profile"))
                _assign_if_present(evaluation, "target_symbol_count", candidate_provenance.get("target_symbol_count"))
                _assign_if_present(evaluation, "candidate_contract_hash", candidate.get("candidate_contract_hash"))
                _assign_if_present(evaluation, "execution_contract_hash", candidate.get("execution_contract_hash"))
                _assign_if_present(evaluation, "tested_object_hash", candidate.get("tested_object_hash"))
                _assign_if_present(evaluation, "candidate_identity_signature", candidate.get("candidate_identity_signature"))
                _assign_if_present(evaluation, "candidate_contract_snapshot", contract_snapshot)
                _assign_if_present(evaluation, "candidate_lineage_contract", candidate_lineage_contract)
                _assign_if_present(evaluation, "logic_signature", candidate.get("logic_signature"))
                _assign_if_present(evaluation, "dsl_signature", candidate.get("dsl_signature"))
                _assign_if_present(evaluation, "factor_signature", candidate.get("factor_signature"))
                _assign_if_present(evaluation, "entry_exit_signature", candidate.get("entry_exit_signature"))
                for field_name in _SEMANTIC_CONTRACT_FIELDS:
                    _assign_if_present(evaluation, field_name, candidate.get(field_name))
                evaluation["quality_gate"] = gate
                if validation_report is not None or "validation_report" not in evaluation:
                    evaluation["validation_report"] = validation_report or {}
                if risk_report is not None or "risk_report" not in evaluation:
                    evaluation["risk_report"] = risk_report or {}
                _assign_if_present(evaluation, "quality_summary", quality_summary)
                _assign_if_present(evaluation, "backtest_metrics", backtest_payload)
                _assign_if_present(evaluation, "event_window_config", event_window_config)
                _assign_if_present(evaluation, "event_window_metrics", event_window_metrics)
                _assign_if_present(evaluation, "position_assumption", quality_payload.get("position_assumption") or backtest_payload.get("position_assumption"))
                _assign_if_present(evaluation, "cost_assumptions", cost_assumptions)
                _assign_if_present(evaluation, "backtest_assumptions", backtest_assumptions)
                _assign_if_present(evaluation, "execution_reality", execution_reality)
                _assign_if_present(evaluation, "constraint_check", quality_payload.get("constraint_check") or backtest_payload.get("constraint_check"))
                _assign_if_present(evaluation, "admission_stage", gate.get("admission_stage"))
                _assign_if_present(evaluation, "incubation_pass_mode", gate.get("incubation_pass_mode"))
                _assign_if_present(
                    evaluation,
                    "submission_lane",
                    quality_payload.get("submission_lane") or quality_summary.get("submission_lane"),
                )
                evaluation["research_candidate_ready"] = bool(gate.get("research_candidate_ready"))
                evaluation["incubation_candidate_ready"] = bool(gate.get("incubation_candidate_ready"))
                evaluation["live_candidate_ready"] = bool(gate.get("live_candidate_ready"))
                evaluation["direct_trade_candidate"] = bool(
                    quality_payload.get("direct_trade_candidate") or quality_summary.get("direct_trade_candidate")
                )
                evaluation["admission_block_reasons"] = list(gate.get("admission_block_reasons") or [])
                evaluation["admission_evaluations"] = dict(gate.get("admission_evaluations") or {})

                result = dict(existing_result)
                result.update({"strategy_id": strategy_id, "generated_strategy_id": strategy_id, "status": status})
                _assign_if_present(result, "candidate_provenance", candidate_provenance)
                _assign_if_present(result, "source_candidate_artifact_id", candidate_provenance.get("source_candidate_artifact_id"))
                _assign_if_present(result, "candidate_family", candidate_provenance.get("candidate_family"))
                _assign_if_present(result, "strategy_profile", candidate_provenance.get("strategy_profile"))
                _assign_if_present(result, "candidate_family_id", candidate_provenance.get("candidate_family_id"))
                _assign_if_present(result, "holding_period_bucket", candidate_provenance.get("holding_period_bucket"))
                _assign_if_present(result, "alpha_source", candidate_provenance.get("alpha_source"))
                _assign_if_present(result, "risk_level", candidate_provenance.get("risk_level"))
                _assign_if_present(result, "regime_fit", candidate_provenance.get("regime_fit"))
                _assign_if_present(result, "generator_mode", candidate_provenance.get("generator_mode"))
                _assign_if_present(result, "direction_bias", candidate_provenance.get("direction_bias"))
                _assign_if_present(result, "validation_profile_name", candidate_provenance.get("validation_profile"))
                _assign_if_present(result, "target_symbol_count", candidate_provenance.get("target_symbol_count"))
                _assign_if_present(result, "candidate_contract_hash", candidate.get("candidate_contract_hash"))
                _assign_if_present(result, "execution_contract_hash", candidate.get("execution_contract_hash"))
                _assign_if_present(result, "tested_object_hash", candidate.get("tested_object_hash"))
                _assign_if_present(result, "candidate_identity_signature", candidate.get("candidate_identity_signature"))
                _assign_if_present(result, "candidate_contract_snapshot", contract_snapshot)
                _assign_if_present(result, "candidate_lineage_contract", candidate_lineage_contract)
                _assign_if_present(result, "logic_signature", candidate.get("logic_signature"))
                _assign_if_present(result, "dsl_signature", candidate.get("dsl_signature"))
                _assign_if_present(result, "factor_signature", candidate.get("factor_signature"))
                _assign_if_present(result, "entry_exit_signature", candidate.get("entry_exit_signature"))
                for field_name in _SEMANTIC_CONTRACT_FIELDS:
                    _assign_if_present(result, field_name, candidate.get(field_name))
                _assign_if_present(result, "quality_summary", quality_summary)
                _assign_if_present(result, "backtest_metrics", backtest_payload)
                _assign_if_present(result, "event_window_config", event_window_config)
                _assign_if_present(result, "event_window_metrics", event_window_metrics)
                _assign_if_present(result, "position_assumption", quality_payload.get("position_assumption") or backtest_payload.get("position_assumption"))
                _assign_if_present(result, "cost_assumptions", cost_assumptions)
                _assign_if_present(result, "backtest_assumptions", backtest_assumptions)
                _assign_if_present(result, "execution_reality", execution_reality)
                _assign_if_present(result, "constraint_check", quality_payload.get("constraint_check") or backtest_payload.get("constraint_check"))
                _assign_if_present(result, "admission_stage", gate.get("admission_stage"))
                _assign_if_present(result, "incubation_pass_mode", gate.get("incubation_pass_mode"))
                _assign_if_present(
                    result,
                    "submission_lane",
                    quality_payload.get("submission_lane") or quality_summary.get("submission_lane"),
                )
                result["research_candidate_ready"] = bool(gate.get("research_candidate_ready"))
                result["incubation_candidate_ready"] = bool(gate.get("incubation_candidate_ready"))
                result["live_candidate_ready"] = bool(gate.get("live_candidate_ready"))
                result["direct_trade_candidate"] = bool(
                    quality_payload.get("direct_trade_candidate") or quality_summary.get("direct_trade_candidate")
                )
                result["admission_block_reasons"] = list(gate.get("admission_block_reasons") or [])
                result["admission_evaluations"] = dict(gate.get("admission_evaluations") or {})
                if incubation_pipeline:
                    evaluation["incubation_pipeline"] = (incubation_pipeline or {}).get("snapshot") or {}
                    result["incubation_pipeline"] = (incubation_pipeline or {}).get("snapshot") or {}

                parent_strategy_id = existing.get("parent_strategy_id") or candidate.get("parent_strategy_id")
                experiment_strategy_id = existing.get("strategy_id") or parent_strategy_id or strategy_id
                prompt_payload = existing.get("prompt") or (str(candidate.get("llm_prompt")) if candidate.get("llm_prompt") else str(snapshot.get("date") or ""))

                await db.save_strategy_generation_experiment(
                    {
                        **existing,
                        "experiment_id": experiment_id,
                        "strategy_id": experiment_strategy_id,
                        "parent_strategy_id": parent_strategy_id,
                        "generated_strategy_id": strategy_id,
                        "task_run_id": candidate.get("task_run_id") or existing.get("task_run_id"),
                        "source": candidate.get("source") or existing.get("source") or "strategy_factory",
                        "generator_type": candidate.get("generator_type") or existing.get("generator_type") or "rule",
                        "optimizer_type": candidate.get("optimizer_type") or existing.get("optimizer_type"),
                        "status": status,
                        "hypothesis": candidate.get("spawn_reason") or existing.get("hypothesis"),
                        "prompt": prompt_payload,
                        "parameters": parameters,
                        "strategy_spec": strategy_spec,
                        "evaluation": evaluation,
                        "result": result,
                        "parent_experiment_id": existing.get("parent_experiment_id"),
                        "artifact_id": existing.get("artifact_id"),
                    }
                )
            except Exception as exc:
                logger.warning("StrategySubmitter: record experiment failed for %s: %s", strategy_id, exc)
