
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
            result = (
                save_lineage(strategy_id, parent_strategy_id, reason, snapshot, metadata=lineage_metadata)
                if accepts_metadata
                else save_lineage(strategy_id, parent_strategy_id, reason, snapshot)
            )
            if inspect.isawaitable(result):
                await result

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
            ):
                value = candidate.get(field_name)
                if value in (None, "", [], {}):
                    value = existing_params.get(field_name)
                _assign_if_present(stored_params, field_name, value)
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
            contract_source = {
                **existing,
                **dict(candidate or {}),
                "id": strategy_id,
                "name": name,
                "strategy_type": candidate["strategy_type"],
                "params": dict(stored_params),
                "target_symbols": list(stored_params.get("target_symbols") or []),
                "stock_pool": dict(stored_params.get("stock_pool") or {}),
                "research_task": dict(stored_params.get("research_task") or {}),
            }
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
                    dict.fromkeys([*(existing.get("tags") or []), "auto_generated", "factory", candidate["strategy_type"], *(candidate.get("tags") or [])])
                ),
            }

        async def _evaluate_reports(self, candidate: dict, db) -> tuple[Optional[dict], Optional[dict]]:
            """先计算验证/风险报告，避免在 Gate-3 前产生持久化副作用。"""
            report_params = self._candidate_report_params(candidate)
            validation_report = None
            try:
                validation_report = await self._get_validation_gateway().run_validation_report(
                    candidate["strategy_type"],
                    report_params,
                    db,
                )
            except Exception as exc:
                logger.warning("StrategySubmitter: validation report failed for %s: %s", candidate.get("strategy_type"), exc)
            if _report_is_degraded(validation_report):
                validation_report = _build_validation_report_fallback(
                    candidate,
                    dict(candidate.get("backtest_metrics") or candidate.get("backtest_result", {}).get("metrics") or {}),
                    reason="validation_gateway_empty_or_degraded",
                )

            risk_report = None
            try:
                risk_report = await self._get_risk_gateway().run_risk_report(
                    candidate["strategy_type"],
                    report_params,
                    db,
                )
            except Exception as exc:
                logger.warning("StrategySubmitter: risk report failed for %s: %s", candidate.get("strategy_type"), exc)
            if _report_is_degraded(risk_report):
                risk_report = _build_risk_report_fallback(
                    candidate,
                    dict(candidate.get("backtest_metrics") or candidate.get("backtest_result", {}).get("metrics") or {}),
                    reason="risk_gateway_empty_or_degraded",
                )

            return validation_report, risk_report

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
                try:
                    await db.save_strategy_metrics(
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
                except Exception as exc:
                    logger.warning("StrategySubmitter: save backtest metrics failed for %s: %s", strategy_id, exc)

            if validation_report:
                try:
                    rating = validation_report.get("rating", {})
                    await db.save_strategy_metrics(
                        strategy_id,
                        "validation",
                        {
                            "grade": rating.get("grade"),
                            "total_score": rating.get("total_score"),
                            "oos_rank_ic": validation_report.get("walk_forward", {}).get("oos_rank_ic_mean"),
                            "recommendation": rating.get("recommendation"),
                        },
                    )
                except Exception as exc:
                    logger.warning("StrategySubmitter: save validation metrics failed for %s: %s", strategy_id, exc)

            if risk_report:
                try:
                    await db.save_strategy_metrics(strategy_id, "risk", risk_report)
                except Exception as exc:
                    logger.warning("StrategySubmitter: save risk metrics failed for %s: %s", strategy_id, exc)

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
                "incubation_policy": {
                    "warmup_target_signals": 20,
                    "warmup_soft_timeout_days": 5,
                    "warmup_hard_timeout_days": 20,
                    "warmup_max_days": 30,
                },
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
