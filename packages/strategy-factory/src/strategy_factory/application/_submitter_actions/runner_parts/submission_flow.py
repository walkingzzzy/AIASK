
        @classmethod
        async def _save_strategy_lineage_record(
            cls,
            db,
            *,
            strategy_id: str,
            parent_strategy_id: Optional[str],
            reason: str,
            snapshot: dict,
            candidate: Optional[dict] = None,
        ) -> None:
            save_lineage = cls._get_optional_db_method(db, "save_strategy_lineage")
            if save_lineage is None:
                return
            contract_snapshot = dict((candidate or {}).get("candidate_contract_snapshot") or {})
            targeting = dict(contract_snapshot.get("targeting") or {})
            lineage_metadata = {
                "candidate_contract_hash": (candidate or {}).get("candidate_contract_hash"),
                "execution_contract_hash": (candidate or {}).get("execution_contract_hash"),
                "tested_object_hash": (candidate or {}).get("tested_object_hash"),
                "candidate_identity_signature": (candidate or {}).get("candidate_identity_signature"),
                "candidate_contract_snapshot": contract_snapshot,
                "candidate_lineage_contract": dict((candidate or {}).get("candidate_lineage_contract") or contract_snapshot.get("lineage") or {}),
                "logic_signature": (candidate or {}).get("logic_signature"),
                "dsl_signature": (candidate or {}).get("dsl_signature"),
                "factor_signature": (candidate or {}).get("factor_signature"),
                "entry_exit_signature": (candidate or {}).get("entry_exit_signature"),
                "target_pool_id": targeting.get("target_pool_id"),
                "task_signature": dict(contract_snapshot.get("lineage") or {}).get("task_signature"),
                "validation_profile": dict(contract_snapshot.get("validation_profile") or {}),
                "lineage_id": dict(contract_snapshot.get("lineage") or {}).get("lineage_id"),
                "multiple_testing_registry": dict((candidate or {}).get("multiple_testing_registry") or {}),
            }
            accepts_metadata = False
            try:
                signature = inspect.signature(save_lineage)
                params = list(signature.parameters.values())
                accepts_metadata = (
                    "metadata" in signature.parameters
                    or any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params)
                )
            except (TypeError, ValueError):
                accepts_metadata = False
            # PR-S0: 不再把 cycle 全量 snapshot 当 birth_regime 传入，
            # 改为只保留出生时的市场状态（fear_greed / regime / sector / factor 偏好）。
            # 这是 strategy_lineage 表的原始语义。cycle 全量字段（stages /
            # quality_gate / backtest_report / candidate_contract_snapshot 等）
            # 已经在 strategy_factory_runs / strategy_quality_reports / strategies.params
            # 中各有归宿，不需要在 lineage 表里再存一份 130 MB 的副本。
            birth_regime = cls._extract_birth_regime(snapshot)
            result = (
                save_lineage(strategy_id, parent_strategy_id, reason, birth_regime, metadata=lineage_metadata)
                if accepts_metadata
                else save_lineage(strategy_id, parent_strategy_id, reason, birth_regime)
            )
            if inspect.isawaitable(result):
                await result

        @classmethod
        def _extract_birth_regime(cls, snapshot: Optional[dict]) -> dict:
            """PR-S0: 从工厂 cycle snapshot 抽取轻量的"出生市场状态"字典。

            原 strategy_lineage.birth_regime 字段语义是"策略出生时的市场环境快照"，
            预期 ≤ 50 KB。此函数只摘取该语义需要的字段，丢弃 cycle 中的大对象。
            """
            snap = dict(snapshot or {})
            factor_research = dict(snap.get("factor_research") or {})
            factor_summary = dict(factor_research.get("summary") or {})
            market_temperature_context = resolve_market_temperature_context(snap)
            birth_regime = {
                "fg_level": snap.get("fg_level"),
                "fear_greed_index": snap.get("fear_greed_index"),
                "hot_sectors": list(snap.get("hot_sectors") or [])[:8],
                "cold_sectors": list(snap.get("cold_sectors") or [])[:8],
                "active_factors": list(factor_research.get("active_factors") or [])[:6],
                "preferred_strategy_types": list(factor_research.get("preferred_strategy_types") or [])[:6],
                "factor_research_summary": {
                    "top_factor_names": list(factor_summary.get("top_factor_names") or [])[:6],
                    "degraded": bool(factor_research.get("degraded")),
                },
                "regime_summary": dict(snap.get("regime_summary") or {}),
                "as_of": snap.get("as_of") or snap.get("date"),
                "snapshot_id": snap.get("snapshot_id") or snap.get("trace_id"),
                "factory_run_id": snap.get("factory_run_id"),
            }
            if bool(market_temperature_context.get("available")):
                birth_regime["market_temperature_context"] = {
                    "as_of": market_temperature_context.get("as_of"),
                    "temperature": market_temperature_context.get("temperature"),
                    "state": market_temperature_context.get("state"),
                    "quality_status": market_temperature_context.get("quality_status"),
                    "readiness_status": market_temperature_context.get("readiness_status"),
                    "staleness_days": market_temperature_context.get("staleness_days"),
                    "degraded": bool(market_temperature_context.get("degraded")),
                    "warnings": list(market_temperature_context.get("warnings") or [])[:8],
                    "source_chain": list(market_temperature_context.get("source_chain") or [])[:8],
                    "stock_count": market_temperature_context.get("stock_count"),
                    "industry_count": market_temperature_context.get("industry_count"),
                }
            return birth_regime

        @classmethod
        def _build_strategy_data(
            cls,
            strategy_id: str,
            name: str,
            candidate: dict,
            metrics: dict,
            existing: Optional[dict] = None,
        ) -> dict:
            """构建策略记录数据。"""
            candidate = apply_resolved_candidate_envelope(candidate)
            existing = dict(existing or {})
            description = f"{name}\n生成原因: {candidate.get('spawn_reason', '')}"
            if metrics:
                description += f"\n回测: Sharpe {metrics.get('sharpe_ratio', 0):.2f} | "
                description += f"收益 {metrics.get('total_return', 0):.1%} | "
                description += f"回撤 {metrics.get('max_drawdown', 0):.1%}"

            description = ""
            existing_params = dict(existing.get("params") or {})
            normalized_task = _normalize_research_task_contract(candidate.get("research_task") or existing_params.get("research_task") or {})
            candidate_provenance = cls._candidate_provenance(candidate, existing)
            research_validation_contract = dict(
                candidate.get("research_validation_contract")
                or existing_params.get("research_validation_contract")
                or {}
            )
            research_validation_contract_submission_adapter = adapt_research_validation_contract_for_submission(
                research_validation_contract
            )
            prediction_trace_id = normalize_prediction_trace_id(
                candidate.get("prediction_trace_id"),
                candidate.get("trace_id"),
                fallback=existing_params.get("prediction_trace_id") or existing_params.get("trace_id"),
            )

            def _assign_if_present(target: dict, key: str, value) -> None:
                if value not in (None, [], {}, ""):
                    target[key] = value

            stored_params = {
                **existing_params,
                **dict(candidate["params"] or {}),
                "target_symbols": list(candidate.get("target_symbols") or existing_params.get("target_symbols") or []),
                "stock_pool": dict(candidate.get("stock_pool") or existing_params.get("stock_pool") or {}),
                "research_task": normalized_task,
                "hypothesis": candidate.get("hypothesis") or existing_params.get("hypothesis"),
                "holding_horizon": dict(candidate.get("holding_horizon") or existing_params.get("holding_horizon") or {}),
                "trade_plan": dict(candidate.get("trade_plan") or existing_params.get("trade_plan") or {}),
                "risk_rules": dict(candidate.get("risk_rules") or existing_params.get("risk_rules") or {}),
                "position_sizing": dict(candidate.get("position_sizing") or existing_params.get("position_sizing") or {}),
                "execution_notes": candidate.get("execution_notes") or existing_params.get("execution_notes"),
                "rebalance_rule": dict(candidate.get("rebalance_rule") or existing_params.get("rebalance_rule") or {}),
                "portfolio_spec": dict(candidate.get("portfolio_spec") or existing_params.get("portfolio_spec") or {}),
                "execution_assumptions": dict(candidate.get("execution_assumptions") or existing_params.get("execution_assumptions") or {}),
                "runtime_playbook": dict(candidate.get("runtime_playbook") or existing_params.get("runtime_playbook") or {}),
                "validation_profile": dict(candidate.get("validation_profile") or existing_params.get("validation_profile") or {}),
                "targeting_policy": dict(candidate.get("targeting_policy") or existing_params.get("targeting_policy") or {}),
                "constraint_check": dict(candidate.get("constraint_check") or existing_params.get("constraint_check") or {}),
                "task_signature": _build_task_signature(normalized_task),
            }
            if research_validation_contract_submission_adapter:
                stored_params["validation_profile"] = {
                    **dict(research_validation_contract_submission_adapter.get("validation_profile") or {}),
                    **dict(stored_params.get("validation_profile") or {}),
                }
            _assign_if_present(stored_params, "research_validation_contract", research_validation_contract)
            _assign_if_present(
                stored_params,
                "research_validation_contract_submission_adapter",
                research_validation_contract_submission_adapter,
            )
            _assign_if_present(
                stored_params,
                "research_protocol_version",
                candidate.get("research_protocol_version")
                or existing_params.get("research_protocol_version")
                or research_validation_contract_submission_adapter.get("research_protocol_version"),
            )
            _assign_if_present(
                stored_params,
                "candidate_contract_version",
                candidate.get("candidate_contract_version") or existing_params.get("candidate_contract_version"),
            )
            _assign_if_present(
                stored_params,
                "spec_completeness",
                candidate.get("spec_completeness") or existing_params.get("spec_completeness"),
            )
            _assign_if_present(
                stored_params,
                "field_provenance",
                dict(candidate.get("field_provenance") or existing_params.get("field_provenance") or {}),
            )
            _assign_if_present(
                stored_params,
                "field_provenance_summary",
                dict(
                    candidate.get("field_provenance_summary")
                    or existing_params.get("field_provenance_summary")
                    or research_validation_contract_submission_adapter.get("field_provenance_summary")
                    or {}
                ),
            )
            _assign_if_present(
                stored_params,
                "completion_issues",
                list(
                    candidate.get("completion_issues")
                    or existing_params.get("completion_issues")
                    or research_validation_contract_submission_adapter.get("completion_issues")
                    or []
                ),
            )
            _assign_if_present(
                stored_params,
                "hard_failures",
                list(candidate.get("hard_failures") or existing_params.get("hard_failures") or []),
            )
            _assign_if_present(stored_params, "prediction_trace_id", prediction_trace_id)
            _assign_if_present(stored_params, "trace_id", prediction_trace_id)
            _assign_if_present(
                stored_params,
                "evidence_chain",
                dict(candidate.get("evidence_chain") or existing_params.get("evidence_chain") or {}),
            )
            _assign_if_present(
                stored_params,
                "prediction_contract",
                dict(candidate.get("prediction_contract") or existing_params.get("prediction_contract") or {}),
            )
            _assign_if_present(
                stored_params,
                "confidence_contract",
                dict(candidate.get("confidence_contract") or existing_params.get("confidence_contract") or {}),
            )
            _assign_if_present(
                stored_params,
                "evidence_alignment_audit",
                dict(candidate.get("evidence_alignment_audit") or existing_params.get("evidence_alignment_audit") or {}),
            )
            _assign_if_present(
                stored_params,
                "dsl_support_audit",
                dict(candidate.get("dsl_support_audit") or existing_params.get("dsl_support_audit") or {}),
            )
            _assign_if_present(
                stored_params,
                "claim_to_trade_plan_map",
                dict(candidate.get("claim_to_trade_plan_map") or existing_params.get("claim_to_trade_plan_map") or {}),
            )
            _assign_if_present(
                stored_params,
                "semantic_contract_backfilled",
                candidate.get("semantic_contract_backfilled")
                if candidate.get("semantic_contract_backfilled") is not None
                else existing_params.get("semantic_contract_backfilled"),
            )
            if candidate.get("legacy_semantic_contract") is not None:
                stored_params["legacy_semantic_contract"] = bool(candidate.get("legacy_semantic_contract"))
            if candidate.get("contradiction_count") is not None:
                stored_params["contradiction_count"] = int(candidate.get("contradiction_count") or 0)
            if candidate.get("proxy_dependency_score") is not None:
                stored_params["proxy_dependency_score"] = candidate.get("proxy_dependency_score")
            for field_name in (
                "semantic_runtime_match",
                "runtime_family_data_source",
                "proxy_runtime_used",
                "diagnostic_only",
                "execution_readiness_tier",
                "event_prefilter",
                "semantic_contract_missing_fields",
                "execution_semantic_gap_reasons",
                "execution_semantic_mode",
                "dsl_compiled",
                "execution_semantic_gap",
            ):
                value = candidate.get(field_name)
                if value in (None, "", [], {}):
                    value = existing_params.get(field_name)
                _assign_if_present(stored_params, field_name, value)
            for runtime_struct_field in (
                "instrument_profile",
                "trade_plan_to_dsl_map",
                "execution_semantic_contract",
                "fundamental_runtime_contract",
            ):
                _assign_if_present(
                    stored_params,
                    runtime_struct_field,
                    dict(
                        candidate.get(runtime_struct_field)
                        or existing_params.get(runtime_struct_field)
                        or {}
                    ),
                )
            if candidate_provenance:
                stored_params["candidate_provenance"] = candidate_provenance
                if candidate_provenance.get("source_candidate_artifact_id"):
                    stored_params["source_candidate_artifact_id"] = candidate_provenance.get("source_candidate_artifact_id")
                if candidate_provenance.get("source_generation_artifact_id"):
                    stored_params["source_generation_artifact_id"] = candidate_provenance.get("source_generation_artifact_id")
                if candidate_provenance.get("source_validation_artifact_id"):
                    stored_params["source_validation_artifact_id"] = candidate_provenance.get("source_validation_artifact_id")
                if candidate_provenance.get("memory_record_id"):
                    stored_params["candidate_memory_record_id"] = candidate_provenance.get("memory_record_id")
                _assign_if_present(
                    stored_params,
                    "strategy_profile",
                    dict(candidate_provenance.get("strategy_profile") or stored_params.get("strategy_profile") or {}),
                )
                if candidate_provenance.get("candidate_family"):
                    stored_params["candidate_family"] = candidate_provenance.get("candidate_family")
                _assign_if_present(stored_params, "candidate_family_id", candidate_provenance.get("candidate_family_id"))
                _assign_if_present(stored_params, "holding_period_bucket", candidate_provenance.get("holding_period_bucket"))
                _assign_if_present(stored_params, "alpha_source", candidate_provenance.get("alpha_source"))
                _assign_if_present(stored_params, "risk_level", candidate_provenance.get("risk_level"))
                _assign_if_present(stored_params, "regime_fit", candidate_provenance.get("regime_fit"))
                _assign_if_present(stored_params, "generator_mode", candidate_provenance.get("generator_mode"))
                _assign_if_present(stored_params, "direction_bias", candidate_provenance.get("direction_bias"))
                _assign_if_present(stored_params, "validation_profile_name", candidate_provenance.get("validation_profile"))
                _assign_if_present(stored_params, "target_symbol_count", candidate_provenance.get("target_symbol_count"))
                if candidate_provenance.get("candidate_registry_stage"):
                    stored_params["candidate_registry_stage"] = candidate_provenance.get("candidate_registry_stage")
                if candidate_provenance.get("validation_score") is not None:
                    stored_params["candidate_validation_score"] = candidate_provenance.get("validation_score")
                if candidate_provenance.get("expected_regime"):
                    stored_params["expected_regime"] = list(candidate_provenance.get("expected_regime") or [])
                if candidate_provenance.get("expected_holding_period") is not None:
                    stored_params["expected_holding_period"] = candidate_provenance.get("expected_holding_period")
                if candidate_provenance.get("latest_validation_at"):
                    stored_params["candidate_latest_validation_at"] = candidate_provenance.get("latest_validation_at")
                if candidate_provenance.get("latest_validation_age_days") is not None:
                    stored_params["candidate_latest_validation_age_days"] = candidate_provenance.get("latest_validation_age_days")
                if candidate_provenance.get("admission_block_reasons"):
                    stored_params["candidate_admission_block_reasons"] = list(
                        candidate_provenance.get("admission_block_reasons") or []
                    )
                if candidate_provenance.get("candidate_evidence_status"):
                    stored_params["candidate_evidence_status"] = dict(candidate_provenance.get("candidate_evidence_status") or {})
            if candidate.get("selection_logic") or existing_params.get("selection_logic"):
                stored_params["selection_logic"] = list(candidate.get("selection_logic") or existing_params.get("selection_logic") or [])
            if candidate.get("incubation_budget"):
                stored_params["incubation_budget"] = dict(candidate.get("incubation_budget") or {})
            strategy_explanation = build_strategy_explanation(
                {
                    **existing,
                    **dict(candidate or {}),
                    "id": strategy_id,
                    "strategy_id": strategy_id,
                    "name": name,
                    "strategy_type": candidate["strategy_type"],
                    "params": dict(stored_params),
                    "tags": list(
                        dict.fromkeys(
                            [
                                *(existing.get("tags") or []),
                                "auto_generated",
                                "factory",
                                candidate["strategy_type"],
                                *(candidate.get("tags") or []),
                            ]
                        )
                    ),
                },
                metrics=metrics,
                existing=existing,
                source="strategy_factory_submit",
            )
            if strategy_explanation:
                stored_params["strategy_explanation"] = strategy_explanation
                description = render_strategy_description(
                    name,
                    strategy_explanation,
                    metrics=metrics,
                )
            if not description:
                description = f"{name}\nGenerated reason: {candidate.get('spawn_reason', '')}"
            contract_source = {
                **existing,
                **dict(candidate or {}),
                "id": strategy_id,
                "strategy_id": strategy_id,
                "name": name,
                "strategy_type": candidate["strategy_type"],
                "params": dict(stored_params),
                "target_symbols": list(stored_params.get("target_symbols") or []),
                "stock_pool": dict(stored_params.get("stock_pool") or {}),
                "research_task": dict(stored_params.get("research_task") or {}),
            }
            trade_prediction_seed_params = dict(stored_params)
            explicit_trade_prediction_contract = dict(
                candidate.get("trade_prediction_contract")
                or stored_params.get("trade_prediction_contract")
                or {}
            )
            if explicit_trade_prediction_contract:
                explicit_trade_prediction_contract["strategy_id"] = strategy_id
                contract_source["trade_prediction_contract"] = explicit_trade_prediction_contract
                trade_prediction_seed_params["trade_prediction_contract"] = explicit_trade_prediction_contract
            from strategy_factory.application.trade_prediction_contract import freeze_trade_prediction_contract

            frozen_trade_prediction = freeze_trade_prediction_contract(
                {
                    **contract_source,
                    "id": strategy_id,
                    "strategy_id": strategy_id,
                    "trade_prediction_contract": explicit_trade_prediction_contract,
                    "params": trade_prediction_seed_params,
                }
            )
            stored_params["trade_prediction_contract"] = dict(frozen_trade_prediction.get("contract") or {})
            stored_params["trade_prediction_contract_status"] = frozen_trade_prediction.get("status")
            stored_params["trade_prediction_contract_hash"] = frozen_trade_prediction.get("contract_hash")
            stored_params["trade_prediction_contract_missing_fields"] = list(
                frozen_trade_prediction.get("missing_fields") or []
            )
            stored_params["trade_prediction_contract_reject_reasons"] = list(
                frozen_trade_prediction.get("reject_reasons") or []
            )
            contract_source["params"] = dict(stored_params)
            contract_snapshot = build_portfolio_candidate_contract(contract_source)
            resolved_candidate_envelope = build_resolved_candidate_envelope(contract_source)
            stored_params["candidate_contract_snapshot"] = contract_snapshot
            stored_params["candidate_contract_hash"] = build_candidate_contract_hash(contract=contract_snapshot)
            stored_params["execution_contract_hash"] = (
                str(resolved_candidate_envelope.get("execution_contract_hash") or "").strip()
                or build_execution_contract_hash(contract=contract_snapshot)
            )
            stored_params["tested_object_hash"] = (
                str(resolved_candidate_envelope.get("tested_object_hash") or "").strip()
                or build_tested_object_hash(contract_source)
            )
            stored_params["candidate_identity_signature"] = build_candidate_identity_signature(contract_source)
            stored_params["candidate_lineage_contract"] = dict(contract_snapshot.get("lineage") or {})
            stored_params["logic_signature"] = str(resolved_candidate_envelope.get("logic_signature") or "")
            stored_params["dsl_signature"] = str(resolved_candidate_envelope.get("dsl_signature") or "")
            stored_params["factor_signature"] = str(resolved_candidate_envelope.get("factor_signature") or "")
            stored_params["entry_exit_signature"] = str(resolved_candidate_envelope.get("entry_exit_signature") or "")
            stored_params["resolved_candidate_envelope"] = resolved_candidate_envelope
            return {
                "id": strategy_id,
                "name": name,
                "description": description,
                "author_id": existing.get("author_id") or "strategy_factory",
                "strategy_type": candidate["strategy_type"],
                "params": stored_params,
                "factor_weights": dict((candidate["params"] or {}).get("factor_weights", existing.get("factor_weights") or {})),
                "status": existing.get("status") or "draft",
                "prediction_trace_id": prediction_trace_id or None,
                "trace_id": prediction_trace_id or None,
                "research_protocol_version": stored_params.get("research_protocol_version"),
                "candidate_contract_version": stored_params.get("candidate_contract_version"),
                "spec_completeness": stored_params.get("spec_completeness"),
                "field_provenance_summary": dict(stored_params.get("field_provenance_summary") or {}),
                "completion_issues": list(stored_params.get("completion_issues") or []),
                "hard_failures": list(stored_params.get("hard_failures") or []),
                "tags": list(
                    dict.fromkeys(
                        [
                            *(existing.get("tags") or []),
                            "auto_generated",
                            "factory",
                            candidate["strategy_type"],
                            *(candidate.get("tags") or []),
                            *(strategy_explanation.get("labels") or []),
                        ]
                    )
                ),
            }

        @classmethod
        def _factor_pool_summary_float(cls, *values: Any) -> Optional[float]:
            for value in values:
                if value in (None, "", [], {}):
                    continue
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                if numeric == numeric and numeric not in (float("inf"), float("-inf")):
                    return float(numeric)
            return None

        @classmethod
        def _factor_pool_summary_blocks_submission(cls, summary: dict[str, Any]) -> bool:
            shelf_decision = dict(summary.get("qc_shelf_decision") or {})
            decision = str(shelf_decision.get("decision") or "").strip().lower()
            if decision not in {"retire", "quarantine", "reject"}:
                return False
            if bool(summary.get("qc_autoshelf_applied")):
                return True
            labels = summary.get("qc_labels")
            if not isinstance(labels, dict):
                return True
            availability_keys = {
                "oos_available",
                "layered_available",
                "robustness_available",
                "multiple_testing_available",
            }
            if any(key in labels for key in availability_keys):
                return any(bool(labels.get(key)) for key in availability_keys)
            numeric_keys = (
                "rank_ic_ir",
                "bootstrap_ci_lower",
                "monotonicity",
                "long_short_return",
                "window_stability",
                "param_sensitivity",
                "dsr",
                "pbo",
            )
            all_zero = True
            for key in numeric_keys:
                value = cls._factor_pool_summary_float(labels.get(key))
                if value is not None and abs(value) > 1e-12:
                    all_zero = False
                    break
            unknown_oos = (
                not bool(labels.get("oos_pass"))
                and str(labels.get("oos_grade") or "").strip().lower() in {"", "unknown"}
            )
            return not (all_zero and unknown_oos)

        @classmethod
        def _factor_pool_validation_report_from_params(
            cls,
            params: dict[str, Any],
            candidate: dict[str, Any],
            base_report: Optional[dict[str, Any]],
        ) -> Optional[dict[str, Any]]:
            summary = dict((params or {}).get("factor_pool_validation_summary") or {})
            if not summary or cls._factor_pool_summary_blocks_submission(summary):
                return base_report

            metrics = dict(summary.get("metrics") or {})
            evidence = dict(summary.get("evidence_summary") or {})
            quick = dict(summary.get("quick_evidence") or {})
            quick_evidence = dict(quick.get("evidence_summary") or {})
            rating = dict(summary.get("rating") or {})
            quality_evidence = dict(rating.get("quality_evidence") or {})
            quality_summary = dict(quality_evidence.get("summary") or {})
            governance = dict(rating.get("governance") or {})
            governance_raw = dict(governance.get("raw_metrics") or {})
            persisted = dict(summary.get("persisted_outputs") or {})
            avg_stability_ratio = cls._factor_pool_summary_float(governance_raw.get("avg_stability_ratio"))
            avg_degradation = cls._factor_pool_summary_float(governance_raw.get("avg_degradation"))

            quality_status = str(summary.get("quality_status") or "").strip().lower()
            recommendation = str(rating.get("recommendation") or "").strip().lower()
            if quality_status not in {"promoted", "active"} and recommendation != "promote":
                return base_report

            rank_ic_mean = cls._factor_pool_summary_float(
                metrics.get("rank_ic_mean"),
                evidence.get("rank_ic_mean"),
                quality_summary.get("rank_ic_mean"),
                quick.get("rank_ic_mean"),
                quick_evidence.get("rank_ic_mean"),
            )
            rank_ic_ir = cls._factor_pool_summary_float(
                metrics.get("rank_ic_ir"),
                evidence.get("rank_ic_ir"),
                quality_summary.get("rank_ic_ir"),
                quick.get("rank_ic_ir"),
                quick_evidence.get("rank_ic_ir"),
            )
            rank_ic_std = cls._factor_pool_summary_float(metrics.get("rank_ic_std"))
            sample_dates = cls._factor_pool_summary_float(
                metrics.get("sample_dates"),
                evidence.get("sample_dates"),
                quality_summary.get("sample_dates"),
                quick.get("sample_dates"),
                quick_evidence.get("sample_dates"),
            )
            bootstrap_ci_lower = cls._factor_pool_summary_float(
                metrics.get("bootstrap_ci_lower"),
                metrics.get("ci_lower"),
                evidence.get("bootstrap_ci_lower"),
                quality_summary.get("bootstrap_ci_lower"),
            )
            if (
                bootstrap_ci_lower is None
                and rank_ic_mean is not None
                and rank_ic_std is not None
                and sample_dates is not None
                and sample_dates > 1
            ):
                bootstrap_ci_lower = rank_ic_mean - 1.96 * (rank_ic_std / (sample_dates ** 0.5))

            if (
                rank_ic_ir is None
                or rank_ic_mean is None
                or bootstrap_ci_lower is None
                or rank_ic_ir < 0.3
                or rank_ic_mean < 0.02
                or bootstrap_ci_lower < 0.0
            ):
                return base_report

            factor_meta = dict(candidate.get("factor_pool_metadata") or {})
            factor_name = str(
                (params or {}).get("factor_name")
                or factor_meta.get("factor_name")
                or (params or {}).get("factor_pool_factor_id")
                or factor_meta.get("factor_id")
                or candidate.get("strategy_type")
                or "active_factor_pool"
            ).strip()
            report = dict(base_report or {})
            report["strategy_validation_report"] = dict(base_report or {})
            report["factor_name"] = factor_name
            report["n_periods"] = int(sample_dates or 0)
            report["n_stocks"] = int(
                cls._factor_pool_summary_float(
                    evidence.get("avg_cross_section_n"),
                    quality_summary.get("avg_cross_section_n"),
                    quick.get("avg_cross_section_n"),
                    quick_evidence.get("avg_cross_section_n"),
                )
                or 0
            )
            report["walk_forward"] = {
                **dict(report.get("walk_forward") or {}),
                "method": "active_factor_pool_governed_oos",
                "oos_rank_ic_mean": round(float(rank_ic_mean), 6),
                "oos_rank_ic_ir": round(float(rank_ic_ir), 6),
            }
            report["purged_kfold"] = {
                **dict(report.get("purged_kfold") or {}),
                "method": "active_factor_pool_governed_cross_section",
                "oos_rank_ic_mean": round(float(rank_ic_mean), 6),
                "oos_rank_ic_ir": round(float(rank_ic_ir), 6),
            }
            report["bootstrap_ci"] = {
                **dict(report.get("bootstrap_ci") or {}),
                "ci_lower": round(float(bootstrap_ci_lower), 6),
                "ic_mean": round(float(rank_ic_mean), 6),
                "sample_size": int(sample_dates or 0),
                "source": "active_factor_pool_validation_summary",
            }
            report["multiple_testing"] = {
                **dict(report.get("multiple_testing") or {}),
                "deflated_sharpe": {
                    "available": governance_raw.get("deflated_sharpe") is not None,
                    "dsr": cls._factor_pool_summary_float(governance_raw.get("deflated_sharpe")),
                },
                "pbo": {
                    "available": governance_raw.get("pbo") is not None,
                    "pbo": cls._factor_pool_summary_float(governance_raw.get("pbo")),
                },
                "white_reality_check": {
                    "available": governance_raw.get("white_reality_check_p_value") is not None,
                    "p_value": cls._factor_pool_summary_float(governance_raw.get("white_reality_check_p_value")),
                },
                "hansen_spa": {
                    "available": governance_raw.get("hansen_spa_p_value") is not None,
                    "p_value": cls._factor_pool_summary_float(governance_raw.get("hansen_spa_p_value")),
                },
            }
            report["rating"] = rating or dict(report.get("rating") or {})
            statistical_metrics = {
                **dict(report.get("statistical_metrics") or {}),
                "wf_ic_ir": {"value": round(float(rank_ic_ir), 6), "source": "active_factor_pool_validation_summary"},
                "pkf_ic": {"value": round(float(rank_ic_mean), 6), "source": "active_factor_pool_validation_summary"},
                "bootstrap_ci_lower": {
                    "value": round(float(bootstrap_ci_lower), 6),
                    "source": "active_factor_pool_validation_summary",
                    "derived": bool(rank_ic_std is not None),
                },
            }
            if avg_stability_ratio is not None:
                statistical_metrics["param_sensitivity"] = {
                    "value": round(max(0.0, min(1.0, 1.0 - float(avg_stability_ratio))), 6),
                    "source": "active_factor_pool_governance.avg_stability_ratio",
                    "derived": True,
                }
            if avg_degradation is not None:
                statistical_metrics["period_robustness"] = {
                    "value": {
                        "first_half_ic": round(float(rank_ic_mean), 6),
                        "second_half_ic": round(float(rank_ic_mean) - abs(float(avg_degradation)), 6),
                    },
                    "source": "active_factor_pool_governance.avg_degradation",
                    "derived": True,
                }
            report["statistical_metrics"] = statistical_metrics
            report["active_factor_pool_validation"] = {
                "source": "factor_pool_validation_summary",
                "quality_status": quality_status,
                "quality_score": summary.get("quality_score"),
                "sample_dates": sample_dates,
                "ic_history_rows": persisted.get("ic_history_rows_total") or persisted.get("ic_history_rows"),
                "source_candidate_artifact_id": (params or {}).get("source_candidate_artifact_id"),
                "source_validation_artifact_id": (params or {}).get("source_validation_artifact_id"),
            }
            report["validation_report_source"] = "active_factor_pool_validation_summary"
            return report

        async def _evaluate_reports(self, candidate: dict, db) -> tuple[Optional[dict], Optional[dict]]:
            """先计算验证/风险报告，避免在 Gate-3 前产生持久化副作用。优化：并发执行。"""
            import asyncio as _asyncio
            report_params = self._candidate_report_params(candidate)

            async def _run_validation():
                try:
                    return await self._get_validation_gateway().run_validation_report(
                        candidate["strategy_type"],
                        report_params,
                        db,
                    )
                except Exception as exc:
                    logger.warning("StrategySubmitter: validation report failed for %s: %s", candidate.get("strategy_type"), exc)
                    return None

            async def _run_risk():
                try:
                    return await self._get_risk_gateway().run_risk_report(
                        candidate["strategy_type"],
                        report_params,
                        db,
                    )
                except Exception as exc:
                    logger.warning("StrategySubmitter: risk report failed for %s: %s", candidate.get("strategy_type"), exc)
                    return None

            validation_report, risk_report = await _asyncio.gather(_run_validation(), _run_risk())
            validation_report = self._factor_pool_validation_report_from_params(
                report_params,
                candidate,
                validation_report,
            )
            try:
                from strategy_factory.application.research.statistical_robustness import (
                    enrich_validation_report_with_robustness_derivations,
                )

                candidate_index = int(
                    candidate.get("candidate_index")
                    or candidate.get("rank")
                    or candidate.get("priority_rank")
                    or 0
                )
                validation_report = enrich_validation_report_with_robustness_derivations(
                    validation_report,
                    backtest_metrics=dict(candidate.get("backtest_metrics") or {}),
                    candidate_index=candidate_index,
                )
            except Exception as exc:
                logger.warning(
                    "StrategySubmitter: validation robustness enrichment failed for %s: %s",
                    candidate.get("strategy_type"),
                    exc,
                )
            return validation_report, risk_report

        async def _save_metric_with_retry(
            self,
            db,
            strategy_id: str,
            period: str,
            payload: dict,
            *,
            attempts: int = 3,
            initial_delay: float = 0.2,
        ) -> bool:
            """PR-S3: 持久化指标带 retry + DLQ。

            最多 ``attempts`` 次（指数退避 0.2s → 0.5s → 1.0s），全部失败后
            将 (strategy_id, period, payload, last_error) 记入实例 DLQ 列表
            ``_persistence_dlq``，供 cycle runner / 监控读取。
            """
            delays = [0.0]
            delay = initial_delay
            for _ in range(max(attempts - 1, 0)):
                delays.append(delay)
                delay = min(delay * 2.5, 1.5)
            import asyncio as _asyncio_local
            last_exc: Optional[Exception] = None
            for delay in delays:
                if delay > 0:
                    await _asyncio_local.sleep(delay)
                try:
                    await db.save_strategy_metrics(strategy_id, period, payload)
                    return True
                except Exception as exc:
                    last_exc = exc
                    logger.debug(
                        "StrategySubmitter: save %s metrics attempt failed for %s (delay=%.1fs): %s",
                        period, strategy_id, delay, exc,
                    )
            logger.warning(
                "StrategySubmitter: save %s metrics failed for %s after %d attempts: %s",
                period, strategy_id, len(delays), last_exc,
            )
            dlq = getattr(self, "_persistence_dlq", None)
            if dlq is None:
                dlq = []
                setattr(self, "_persistence_dlq", dlq)
            dlq.append(
                {
                    "strategy_id": strategy_id,
                    "period": period,
                    "payload": payload,
                    "error": str(last_exc) if last_exc else None,
                    "error_type": type(last_exc).__name__ if last_exc else None,
                    "attempts": len(delays),
                }
            )
            return False

        async def _persist_metrics(
            self,
            strategy_id: str,
            metrics: dict,
            validation_report: Optional[dict],
            risk_report: Optional[dict],
            db,
        ) -> None:
            """Gate-3 决策后再落库指标，避免未通过候选提前写入。"""
            if metrics:
                await self._save_metric_with_retry(
                    db,
                    strategy_id,
                    "backtest",
                    {
                        "sharpe_ratio": metrics.get("sharpe_ratio"),
                        "total_return": metrics.get("total_return"),
                        "max_drawdown": metrics.get("max_drawdown"),
                        "win_rate": metrics.get("win_rate"),
                        "trade_count": int(metrics.get("trades_count", 0)),
                    },
                )

            if validation_report:
                rating = validation_report.get("rating", {})
                await self._save_metric_with_retry(
                    db,
                    strategy_id,
                    "validation",
                    {
                        "grade": rating.get("grade"),
                        "total_score": rating.get("total_score"),
                        "oos_rank_ic": validation_report.get("walk_forward", {}).get("oos_rank_ic_mean"),
                        "recommendation": rating.get("recommendation"),
                    },
                )

            if risk_report:
                await self._save_metric_with_retry(db, strategy_id, "risk", risk_report)

        @staticmethod
        def _factor_feedback_float(value, default: float = 0.0) -> float:
            try:
                if value is None:
                    return default
                return float(value)
            except (TypeError, ValueError):
                return default

        @classmethod
        def _factor_pool_factor_id_from_candidate(cls, candidate: dict) -> str:
            payload = dict(candidate or {})
            params = dict(payload.get("params") or {})
            metadata = dict(payload.get("metadata") or {})
            factor_meta = dict(payload.get("factor_pool_metadata") or {})
            return str(
                metadata.get("factor_pool_factor_id")
                or payload.get("factor_pool_factor_id")
                or params.get("factor_pool_factor_id")
                or factor_meta.get("factor_id")
                or ""
            ).strip()

        @classmethod
        def _factor_feedback_realized_ic(
            cls,
            metrics: dict,
            validation_report: Optional[dict],
        ) -> float:
            metric_payload = dict(metrics or {})
            for key in ("ic_mean", "rank_ic_mean", "mean_ic", "oos_rank_ic_mean"):
                if metric_payload.get(key) is not None:
                    return cls._factor_feedback_float(metric_payload.get(key))
            for bucket_name in ("factor_metrics", "statistical_validation", "validation"):
                bucket = dict(metric_payload.get(bucket_name) or {})
                for key in ("ic_mean", "rank_ic_mean", "oos_rank_ic_mean"):
                    if bucket.get(key) is not None:
                        return cls._factor_feedback_float(bucket.get(key))

            report = dict(validation_report or {})
            for bucket_name in ("walk_forward", "oos_validation", "metrics"):
                bucket = dict(report.get(bucket_name) or {})
                for key in ("oos_rank_ic_mean", "rank_ic_mean", "ic_mean"):
                    if bucket.get(key) is not None:
                        return cls._factor_feedback_float(bucket.get(key))
            return 0.0

        async def _report_factor_performance_after_submit(
            self,
            *,
            candidate: dict,
            strategy_id: str,
            metrics: dict,
            validation_report: Optional[dict],
            gate: dict,
            read_only: bool,
        ) -> dict[str, Any]:
            factor_id = self._factor_pool_factor_id_from_candidate(candidate)
            if read_only:
                return {"reported": False, "reason": "read_only"}
            if not factor_id:
                return {"reported": False, "reason": "missing_factor_pool_factor_id"}
            if not bool((gate or {}).get("passed")):
                return {"reported": False, "reason": "gate_not_passed", "factor_id": factor_id}

            payload = {
                "realized_ic": self._factor_feedback_realized_ic(metrics, validation_report),
                "realized_turnover": self._factor_feedback_float(
                    (metrics or {}).get("turnover_rate")
                    or (metrics or {}).get("turnover")
                ),
                "realized_cost": self._factor_feedback_float(
                    (metrics or {}).get("estimated_cost_rate")
                    or dict((metrics or {}).get("cost_assumptions") or {}).get("commission_rate")
                ),
                "period": "submission",
            }
            try:
                await self._get_factor_pool_gateway().report_factor_performance(
                    factor_id,
                    strategy_id,
                    payload,
                )
                return {"reported": True, "factor_id": factor_id, "metrics": payload}
            except Exception as exc:
                logger.debug(
                    "StrategySubmitter: factor performance report failed for %s/%s: %s",
                    factor_id,
                    strategy_id,
                    exc,
                )
                return {
                    "reported": False,
                    "factor_id": factor_id,
                    "reason": "report_failed",
                    "error": str(exc),
                }

        @staticmethod
        def _normalized_validation_grade(gate: Optional[dict[str, Any]]) -> str:
            normalized_gate = dict(gate or {})
            return str(
                normalized_gate.get("effective_validation_grade")
                or normalized_gate.get("validation_grade")
                or normalized_gate.get("raw_validation_grade")
                or ""
            ).strip().upper()

        @staticmethod
        def _strategy_type_registered(candidate: Optional[dict[str, Any]]) -> bool:
            strategy_type = str(
                candidate_contract_value(candidate or {}, "strategy_type")
                or dict(candidate or {}).get("strategy_type")
                or ""
            ).strip().lower()
            return bool(strategy_type) and strategy_type in _VALID_STRATEGY_TYPES

        @staticmethod
        def _default_runtime_holding_horizon(strategy_type: str) -> dict[str, Any]:
            normalized = str(strategy_type or "").strip().lower()
            if normalized in {"quality_factor", "value_factor"}:
                return {"min_days": 30, "max_days": 84, "cooldown_window_days": 7}
            if normalized in {"momentum", "ma_cross", "volatility_breakout"}:
                return {"min_days": 14, "max_days": 48, "cooldown_window_days": 5}
            return {"min_days": 5, "max_days": 20, "cooldown_window_days": 5}

        @staticmethod
        def _default_runtime_trade_plan(strategy_type: str) -> dict[str, Any]:
            normalized = str(strategy_type or "").strip().lower()
            if normalized == "momentum":
                return {
                    "entry_bias": "trend_persistence_confirmation",
                    "exit_bias": "false_breakout_or_momentum_decay",
                }
            if normalized == "ma_cross":
                return {
                    "entry_bias": "adaptive_cross_with_volume_confirmation",
                    "exit_bias": "range_reentry_or_cross_failure",
                }
            if normalized in {"quality_factor", "value_factor"}:
                return {
                    "entry_bias": "cross_sectional_rank",
                    "exit_bias": "rank_decay_or_periodic_rebalance",
                }
            return {
                "entry_bias": "signal_confirmed",
                "exit_bias": "signal_or_time_stop",
            }

        @classmethod
        def _default_runtime_risk_rules(cls, strategy_type: str, holding_horizon: dict[str, Any]) -> dict[str, Any]:
            normalized = str(strategy_type or "").strip().lower()
            max_holding_days = int(holding_horizon.get("max_days") or 20)
            if normalized in {"quality_factor", "value_factor"}:
                return {
                    "stop_loss_pct": 0.08,
                    "take_profit_pct": 0.18,
                    "max_holding_days": max(max_holding_days, 42),
                    "cooldown_days": max(5, int(holding_horizon.get("cooldown_window_days") or 7)),
                }
            return {
                "stop_loss_pct": 0.10,
                "take_profit_pct": 0.20,
                "max_holding_days": max_holding_days,
                "cooldown_days": max(3, int(holding_horizon.get("cooldown_window_days") or 5)),
            }

        @staticmethod
        def _default_runtime_incubation_policy(holding_horizon: dict[str, Any]) -> dict[str, Any]:
            max_days = max(8, int(dict(holding_horizon or {}).get("max_days") or 20))
            expected_trade_count = max(4.0, min(12.0, 252.0 / float(max_days)))
            warmup_target_signals = max(4, min(8, int(round(expected_trade_count / 2.5)) or 4))
            warmup_soft_timeout_days = max(5, min(18, int(round(max(5, warmup_target_signals * 2.0)))))
            warmup_hard_timeout_days = max(20, min(45, int(round(max(20, warmup_target_signals * 5.0)))))
            warmup_max_days = max(30, min(60, int(round(max(warmup_hard_timeout_days + 10, warmup_soft_timeout_days + 15)))))
            return {
                "warmup_target_signals": warmup_target_signals,
                "warmup_soft_timeout_days": warmup_soft_timeout_days,
                "warmup_hard_timeout_days": warmup_hard_timeout_days,
                "warmup_max_days": warmup_max_days,
            }

        @staticmethod
        def _default_runtime_execution_assumptions() -> dict[str, Any]:
            return {
                "commission_rate": 0.00025,
                "slippage_bps": 5,
                "tradability_filter": True,
                "slippage_model": "fixed",
            }

        @classmethod
        def _runtime_playbook_from_contract(cls, candidate: Optional[dict[str, Any]]) -> dict[str, Any]:
            payload = dict(candidate or {})
            playbook = dict(candidate_contract_value(payload, "runtime_playbook", {}) or {})
            if playbook:
                return playbook
            holding_horizon = dict(candidate_contract_value(payload, "holding_horizon", {}) or {})
            trade_plan = dict(candidate_contract_value(payload, "trade_plan", {}) or {})
            risk_rules = dict(candidate_contract_value(payload, "risk_rules", {}) or {})
            execution_assumptions = dict(candidate_contract_value(payload, "execution_assumptions", {}) or {})
            portfolio_spec = dict(candidate_contract_value(payload, "portfolio_spec", {}) or {})
            if not holding_horizon and not trade_plan and not risk_rules and not execution_assumptions:
                return {}

            strategy_type = str(payload.get("strategy_type") or "").strip().lower()
            stop_loss_pct = abs(float(risk_rules.get("stop_loss_pct") or risk_rules.get("stop_loss") or 0.08) or 0.08)
            take_profit_pct = abs(
                float(risk_rules.get("take_profit_pct") or risk_rules.get("take_profit") or max(stop_loss_pct * 2.0, 0.12))
                or max(stop_loss_pct * 2.0, 0.12)
            )
            time_stop_days = max(1, int(risk_rules.get("max_holding_days") or holding_horizon.get("max_days") or 20))
            cooldown_days = max(
                1,
                int(
                    risk_rules.get("cooldown_days")
                    or risk_rules.get("cooldown_window_days")
                    or trade_plan.get("cooldown_window_days")
                    or holding_horizon.get("cooldown_window_days")
                    or 5
                ),
            )
            max_position_pct = min(
                0.35,
                max(
                    0.02,
                    float(
                        portfolio_spec.get("max_position_pct")
                        or risk_rules.get("max_position_pct")
                        or 0.18
                    )
                    or 0.18,
                ),
            )
            family = "default"
            if strategy_type in {"momentum", "ma_cross", "volatility_breakout", "event_structure_breakout"}:
                family = "trend"
            elif strategy_type in {"quality_factor", "value_factor"}:
                family = "slow_factor"
                time_stop_days = max(time_stop_days, 42)
            failure_exit_rule = (
                "opposite_signal_or_breakout_failure"
                if family == "trend"
                else "quality_drift_or_rank_decay"
                if family == "slow_factor"
                else "signal_or_time_stop"
            )
            playbook = {
                "entry_policy": {
                    "order_style": "marketable_limit",
                    "signal_validity_days": max(1, min(5, max(1, time_stop_days // 5))),
                    "max_slippage_bps": float(
                        execution_assumptions.get("max_slippage_bps")
                        or execution_assumptions.get("slippage_bps")
                        or 5.0
                    ),
                    "tradability_guard": bool(
                        execution_assumptions.get("tradability_filter")
                        if execution_assumptions.get("tradability_filter") is not None
                        else True
                    ),
                },
                "exit_policy": {
                    "initial_stop_loss_pct": round(max(0.02, stop_loss_pct), 4),
                    "take_profit_pct": round(max(take_profit_pct, stop_loss_pct), 4),
                    "trailing_stop_pct": round(max(0.03, min(stop_loss_pct * (0.8 if family == "trend" else 1.0), 0.12)), 4),
                    "trailing_activation_profit_pct": round(max(stop_loss_pct, 0.05), 4),
                    "time_stop_days": int(time_stop_days),
                    "failure_exit_rule": failure_exit_rule,
                },
                "adverse_move_policy": {
                    "loss_bands": [
                        {
                            "threshold_pct": round(max(0.01, stop_loss_pct * 0.5), 4),
                            "action": "hold",
                            "label": "soft_drawdown_watch",
                        },
                        {
                            "threshold_pct": round(max(0.02, stop_loss_pct), 4),
                            "action": "reduce" if family == "slow_factor" else "exit",
                            "label": "primary_stop_band",
                        },
                        {
                            "threshold_pct": round(max(0.03, stop_loss_pct * 1.2), 4),
                            "action": "freeze_reentry",
                            "label": "hard_stop_band",
                        },
                    ],
                    "average_down": "forbid",
                    "freeze_after_stop": True,
                    "reduce_on_drawdown": family == "slow_factor",
                },
                "reentry_policy": {
                    "cooldown_days": int(cooldown_days),
                    "reclaim_condition": (
                        "reclaim_fast_ma_and_break_recent_high"
                        if family == "trend"
                        else "recover_rank_and_trend_alignment"
                        if family == "slow_factor"
                        else "signal_reconfirm_after_cooldown"
                    ),
                    "max_retries_per_20d": 1 if family == "slow_factor" else 2,
                },
                "position_policy": {
                    "budget_mode": "fixed_fraction",
                    "base_budget_pct": 0.05 if family == "slow_factor" else 0.04,
                    "max_position_pct": round(max_position_pct, 4),
                    "max_concurrent_positions": 2 if family in {"trend", "slow_factor"} else 1,
                    "scale_in": {"enabled": False, "mode": "forbid"},
                    "scale_out": {
                        "enabled": family == "slow_factor",
                        "mode": "reduce_then_exit" if family == "slow_factor" else "take_profit_or_trailing",
                    },
                },
                "incubation_policy": cls._default_runtime_incubation_policy(holding_horizon),
            }
            return playbook

        @classmethod
        def _ensure_runtime_playbook(cls, candidate: Optional[dict[str, Any]]) -> dict[str, Any]:
            payload = dict(candidate or {})
            params = dict(payload.get("params") or {})
            strategy_type = str(payload.get("strategy_type") or "").strip().lower()
            holding_horizon = dict(candidate_contract_value(payload, "holding_horizon", {}) or {})
            if not holding_horizon:
                holding_horizon = cls._default_runtime_holding_horizon(strategy_type)
            trade_plan = dict(candidate_contract_value(payload, "trade_plan", {}) or {})
            if not trade_plan:
                trade_plan = cls._default_runtime_trade_plan(strategy_type)
            risk_rules = dict(candidate_contract_value(payload, "risk_rules", {}) or {})
            if not risk_rules:
                risk_rules = cls._default_runtime_risk_rules(strategy_type, holding_horizon)
            execution_assumptions = dict(candidate_contract_value(payload, "execution_assumptions", {}) or {})
            if not execution_assumptions:
                execution_assumptions = cls._default_runtime_execution_assumptions()
            payload["holding_horizon"] = holding_horizon
            payload["trade_plan"] = trade_plan
            payload["risk_rules"] = risk_rules
            payload["execution_assumptions"] = execution_assumptions
            params.update(
                {
                    "holding_horizon": dict(holding_horizon),
                    "trade_plan": dict(trade_plan),
                    "risk_rules": dict(risk_rules),
                    "execution_assumptions": dict(execution_assumptions),
                }
            )
            playbook = cls._runtime_playbook_from_contract(payload)
            if not playbook:
                payload["params"] = params
                return payload
            params["runtime_playbook"] = dict(playbook)
            payload["params"] = params
            payload["runtime_playbook"] = dict(playbook)
            return payload
