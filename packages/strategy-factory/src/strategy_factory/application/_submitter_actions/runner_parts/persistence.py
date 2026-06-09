
        @classmethod
        def _runtime_bootstrap_context(
            cls,
            gate: Optional[dict[str, Any]],
            *,
            candidate: Optional[dict[str, Any]],
        ) -> dict[str, Any]:
            normalized_gate = dict(gate or {})
            payload = cls._ensure_runtime_playbook(candidate)
            validation_grade = cls._normalized_validation_grade(normalized_gate)
            strategy_type_registered = cls._strategy_type_registered(payload)
            missing_runtime_fields = [
                field_name
                for field_name in _RUNTIME_BOOTSTRAP_REQUIRED_FIELDS
                if candidate_contract_value(payload, field_name) in _EMPTY_CONTRACT_VALUES
            ]
            runtime_playbook_present = bool(candidate_contract_value(payload, "runtime_playbook", {}))
            execution_semantic_mode = str(
                candidate_contract_value(payload, "execution_semantic_mode") or ""
            ).strip().lower() or None
            execution_semantic_gap = bool(candidate_contract_value(payload, "execution_semantic_gap"))
            execution_semantic_gap_reasons = [
                str(item or "").strip()
                for item in list(candidate_contract_value(payload, "execution_semantic_gap_reasons", []) or [])
                if str(item or "").strip()
            ]
            dsl_required = bool(candidate_contract_value(payload, "dsl_required"))
            dsl_compiled = bool(candidate_contract_value(payload, "dsl_compiled"))
            semantic_runtime_match = bool(
                candidate_contract_value(payload, "semantic_runtime_match", True)
            )
            runtime_family_data_source = str(
                candidate_contract_value(payload, "runtime_family_data_source") or ""
            ).strip().lower() or None
            proxy_runtime_used = bool(candidate_contract_value(payload, "proxy_runtime_used"))
            diagnostic_only = bool(candidate_contract_value(payload, "diagnostic_only"))
            execution_readiness_tier = str(
                candidate_contract_value(payload, "execution_readiness_tier") or ""
            ).strip().lower() or None
            semantic_contract_missing_fields = [
                str(item or "").strip()
                for item in list(candidate_contract_value(payload, "semantic_contract_missing_fields", []) or [])
                if str(item or "").strip()
            ]
            trade_prediction_contract_status = str(
                candidate_contract_value(payload, "trade_prediction_contract_status") or ""
            ).strip().lower()
            trade_prediction_contract_hash = str(
                candidate_contract_value(payload, "trade_prediction_contract_hash") or ""
            ).strip()
            trade_prediction_contract = dict(
                candidate_contract_value(payload, "trade_prediction_contract", {}) or {}
            )
            trade_prediction_contract_reject_reasons = [
                str(item or "").strip().lower()
                for item in list(
                    candidate_contract_value(payload, "trade_prediction_contract_reject_reasons", []) or []
                )
                if str(item or "").strip()
            ]
            trade_prediction_contract_observation_gap = False
            if trade_prediction_contract_status != "ready":
                source = str(
                    trade_prediction_contract.get("contract_source") or ""
                ).strip().lower()
                invalid_reasons = [
                    reason
                    for reason in trade_prediction_contract_reject_reasons
                    if reason.startswith("invalid:")
                ]
                derived_gap_reasons = {"invalid:direction", "invalid:confidence"}
                missing_gap_reasons = {"missing:direction", "missing:confidence"}
                missing_reasons = [
                    reason
                    for reason in trade_prediction_contract_reject_reasons
                    if reason.startswith("missing:")
                ]
                trade_prediction_contract_observation_gap = bool(
                    source != "explicit"
                    and trade_prediction_contract_reject_reasons
                    and not any(reason not in derived_gap_reasons for reason in invalid_reasons)
                    and not any(reason not in missing_gap_reasons for reason in missing_reasons)
                    and (
                        any(
                            reason in missing_gap_reasons
                            for reason in trade_prediction_contract_reject_reasons
                        )
                        or any(reason in derived_gap_reasons for reason in trade_prediction_contract_reject_reasons)
                    )
                )
            if trade_prediction_contract_observation_gap:
                diagnostic_only = True
                if not execution_readiness_tier or execution_readiness_tier == "formal_runtime_ready":
                    execution_readiness_tier = "observe_diagnostic_only"
            semantic_hard_fail = bool(
                list(
                    dict(payload.get("evidence_alignment_audit") or {}).get("hard_fail_reasons") or []
                )
            )
            quality_passed = bool(normalized_gate.get("passed"))
            # === DEV-V1 P0: D 级硬否决 toggle 化 ===
            # 当 STRATEGY_FACTORY_OBSERVE_D_GRADE_ENABLED=1 时,D 级 + Gate passed 候选
            # 可以走 observe lane (paper micro budget tier 自动生效);
            # formal_track_blockers 中已有的 strict_incubation_pass 仍挡住 D 级升 formal,
            # formal 严格性零变化。
            allow_d_grade_observe = _observe_d_grade_enabled()
            # === INVERT-DESIGN P1 改动A: Layer 1 宽进准入 ===
            # 当 STRATEGY_FACTORY_WIDE_INTAKE_OBSERVE_ENABLED=1 时,放开"必须 Gate-3 passed"
            # 这一前置。结构合法(类型已注册 + runtime 字段齐 + 无 semantic hard fail)的候选,
            # 即使 quality_passed=False,也判 observe-eligible,走零资本 paper 观察。
            # 此开关只放开 observe,不改 formal(下方 formal_track_blockers 仍要求 strict pass)。
            incubation_budget = dict(payload.get("incubation_budget") or {})
            params = dict(payload.get("params") or {})
            if not incubation_budget:
                incubation_budget = dict(params.get("incubation_budget") or {})
            incubation_budget_track = str(incubation_budget.get("track") or "").strip().lower()
            observe_intake_requested = bool(
                candidate_contract_value(payload, "observe_first_intake")
                or params.get("observe_first_intake")
                or incubation_budget.get("observe_first_intake")
                or incubation_budget_track == "observe_incubation"
            )
            wide_intake_observe = _wide_intake_observe_enabled() or observe_intake_requested
            gate_reason_values: list[str] = []
            for key in (
                "hard_fail_reasons",
                "admission_block_reasons",
                "reason_codes",
                "reasons",
            ):
                raw_values = normalized_gate.get(key)
                if isinstance(raw_values, (list, tuple, set)):
                    gate_reason_values.extend(
                        str(item or "").strip().lower()
                        for item in raw_values
                        if str(item or "").strip()
                    )
                elif raw_values not in _EMPTY_CONTRACT_VALUES:
                    gate_reason_values.append(str(raw_values or "").strip().lower())
            gate_reason_values = list(dict.fromkeys(gate_reason_values))
            audit_only_fragments = (
                "insufficient_statistical_evidence",
                "missing_statistical_metrics",
                "missing_wf_ic_ir",
                "missing_pkf_ic",
                "missing_bootstrap_ci_lower",
                "missing_param_sensitivity",
                "weak_wf_ic_ir",
                "weak_pkf_ic",
                "weak_bootstrap_ci_lower",
                "weak_param_sensitivity",
                "walk_forward_ic_ir",
                "purged_kfold_ic",
                "bootstrap_ci_lower",
                "param_sensitivity",
                "period_robustness",
                "trade_count",
                "factory_policy_backtest_trade_count",
                "win_rate",
                "profit_factor",
                "expectancy",
                "out_of_sample_profit_factor",
            )
            hard_fail_fragments = (
                "trade_prediction_contract_not_ready",
                "missing_runtime_contract",
                "runtime_contract_missing",
                "semantic_hard_fail",
                "final_strategy_missing_semantic_contract",
                "prediction_contract_claim_missing_evidence_ids",
                "prediction_contract_conflict_resolution_rule_missing",
                "trade_plan_node_missing_claim_ids",
                "dsl_entry_not_mapped_to_trade_plan",
                "dsl_exit_not_mapped_to_trade_plan",
                "semantic_contract_contradiction_detected",
                "proxy_only_event_evidence_not_allowed",
                "dsl_contains_unsupported_rules",
                "lagging_entry_without_lead_evidence",
                "temporal_coherence_audit_failed",
                "ambiguous_regime_condition_not_allowed",
                "lookahead",
                "leakage",
                "live_trading",
                "broker_write",
                "precompile_reject",
                "generator_hard_reject",
                "not_executable",
                "non_executable",
            )
            pre_observe_hard_reasons = [
                reason
                for reason in gate_reason_values
                if any(fragment in reason for fragment in hard_fail_fragments)
                and not any(fragment in reason for fragment in audit_only_fragments)
            ]
            trade_prediction_ready = (
                trade_prediction_contract_status == "ready"
                and bool(trade_prediction_contract_hash)
                and bool(trade_prediction_contract)
            )
            if not trade_prediction_ready and not trade_prediction_contract_observation_gap:
                pre_observe_hard_reasons.append("trade_prediction_contract_not_ready")
            pre_observe_hard_reasons = list(dict.fromkeys(pre_observe_hard_reasons))
            semantic_hard_fail = bool(semantic_hard_fail or pre_observe_hard_reasons)
            structurally_valid = (
                strategy_type_registered
                and not missing_runtime_fields
                and not semantic_hard_fail
            )
            runtime_bootstrap_eligible = (
                quality_passed
                and (allow_d_grade_observe or validation_grade != "D")
                and strategy_type_registered
                and not missing_runtime_fields
                and not semantic_hard_fail
            )
            # 宽进:Gate-3 未过但结构合法 → 仍可进 observe。
            wide_intake_admitted = bool(
                wide_intake_observe
                and not runtime_bootstrap_eligible
                and structurally_valid
            )
            if wide_intake_admitted:
                runtime_bootstrap_eligible = True
            if runtime_bootstrap_eligible:
                # === DEV-V1 P0: D 级走 observe 时使用专用 reason ===
                if wide_intake_admitted:
                    runtime_bootstrap_reason = "wide_intake_observe_gate3_not_required"
                elif validation_grade == "D":
                    runtime_bootstrap_reason = "d_grade_observe_only_micro_budget"
                elif execution_semantic_gap:
                    runtime_bootstrap_reason = "execution_semantic_gap_observe_only"
                elif proxy_runtime_used:
                    runtime_bootstrap_reason = "proxy_runtime_observe_only"
                elif diagnostic_only:
                    runtime_bootstrap_reason = "diagnostic_only_observe"
                else:
                    runtime_bootstrap_reason = "quality_passed_non_d_candidate_with_complete_runtime_contract"
            elif not strategy_type_registered:
                runtime_bootstrap_reason = "strategy_type_not_registered"
            elif missing_runtime_fields:
                runtime_bootstrap_reason = f"missing_runtime_contract:{','.join(missing_runtime_fields)}"
            elif semantic_hard_fail:
                runtime_bootstrap_reason = str((pre_observe_hard_reasons or ["semantic_hard_fail"])[0])
            elif not quality_passed:
                runtime_bootstrap_reason = "quality_gate_failed"
            elif validation_grade == "D":
                # 仅在 toggle OFF 且 D 级 + Gate passed 时走到此分支
                runtime_bootstrap_reason = "validation_grade_d_not_allowed_for_runtime"
            else:
                runtime_bootstrap_reason = "runtime_bootstrap_blocked"
            budget_tier = None
            if runtime_bootstrap_eligible:
                budget_tier = (
                    "micro"
                    if wide_intake_admitted or execution_semantic_gap or proxy_runtime_used or diagnostic_only
                    else "standard" if _validation_grade_at_least(validation_grade, "A") else "micro"
                )
            return {
                "runtime_bootstrap_eligible": runtime_bootstrap_eligible,
                "runtime_bootstrap_reason": runtime_bootstrap_reason,
                "runtime_bootstrap_budget_tier": budget_tier,
                "wide_intake_admitted": wide_intake_admitted,
                "runtime_playbook_present": runtime_playbook_present,
                "runtime_contract_missing_fields": missing_runtime_fields,
                "observe_intake_requested": observe_intake_requested,
                "pre_observe_hard_reject_reasons": pre_observe_hard_reasons,
                "trade_prediction_contract_status": trade_prediction_contract_status or "missing",
                "trade_prediction_contract_hash": trade_prediction_contract_hash or None,
                "trade_prediction_contract_observation_gap": trade_prediction_contract_observation_gap,
                "strategy_type_registered": strategy_type_registered,
                "execution_semantic_mode": execution_semantic_mode,
                "execution_semantic_gap": execution_semantic_gap,
                "execution_semantic_gap_reasons": execution_semantic_gap_reasons,
                "dsl_required": dsl_required,
                "dsl_compiled": dsl_compiled,
                "semantic_runtime_match": semantic_runtime_match,
                "runtime_family_data_source": runtime_family_data_source,
                "proxy_runtime_used": proxy_runtime_used,
                "diagnostic_only": diagnostic_only,
                "execution_readiness_tier": execution_readiness_tier,
                "semantic_contract_missing_fields": semantic_contract_missing_fields,
            }

        @classmethod
        def _apply_runtime_bootstrap_contract(
            cls,
            candidate: Optional[dict[str, Any]],
            *,
            submission_lane: str,
            runtime_bootstrap_eligible: bool,
            runtime_bootstrap_budget_tier: Optional[str],
        ) -> dict[str, Any]:
            payload = cls._ensure_runtime_playbook(candidate)
            if (
                str(submission_lane or "").strip().lower() != "observe_incubation"
                or not runtime_bootstrap_eligible
                or runtime_bootstrap_budget_tier not in {"standard", "micro"}
            ):
                return payload
            playbook = dict(payload.get("runtime_playbook") or {})
            entry_policy = dict(playbook.get("entry_policy") or {})
            position_policy = dict(playbook.get("position_policy") or {})
            entry_policy["order_style"] = "marketable_limit"
            if runtime_bootstrap_budget_tier == "standard":
                position_policy["base_budget_pct"] = 0.06
                position_policy["max_concurrent_positions"] = 2
            else:
                position_policy["base_budget_pct"] = 0.03
                position_policy["max_concurrent_positions"] = 1
            playbook["entry_policy"] = entry_policy
            playbook["position_policy"] = position_policy
            params = dict(payload.get("params") or {})
            params["runtime_playbook"] = dict(playbook)
            payload["params"] = params
            payload["runtime_playbook"] = dict(playbook)
            return payload

        @classmethod
        def _should_bootstrap_observe_candidate(
            cls,
            gate: Optional[dict[str, Any]],
            *,
            incubation_budget_track: str,
        ) -> bool:
            normalized_gate = dict(gate or {})
            track = str(incubation_budget_track or "").strip().lower()
            if track not in {"", "deferred_budget_queue", "deferred_submission"}:
                return False
            if not bool(normalized_gate.get("passed")):
                return False
            if bool(normalized_gate.get("live_candidate_ready")):
                return False
            if bool(normalized_gate.get("research_only_due_to_trade_audit_gap")):
                return False
            if not bool(normalized_gate.get("research_candidate_ready")):
                return False
            if not bool(normalized_gate.get("strict_incubation_ready")):
                return False
            if str(normalized_gate.get("incubation_pass_mode") or "").strip().lower() != "strict":
                return False
            if bool(normalized_gate.get("provisional_pass")):
                return False
            validation_grade = cls._normalized_validation_grade(normalized_gate)
            return _validation_grade_at_least(validation_grade, "A")

        @classmethod
        def _allow_observe_trade_audit_bootstrap(
            cls,
            gate: Optional[dict[str, Any]],
            *,
            incubation_budget_track: str,
        ) -> bool:
            normalized_gate = dict(gate or {})
            if str(incubation_budget_track or "").strip().lower() != "observe_incubation":
                return False
            if not bool(normalized_gate.get("passed")):
                return False
            if not bool(normalized_gate.get("research_candidate_ready")):
                return False
            if bool(normalized_gate.get("live_candidate_ready")):
                return False
            validation_grade = cls._normalized_validation_grade(normalized_gate)
            return validation_grade != "D"

        @classmethod
        def _resolve_submission_action_plan(
            cls,
            gate: dict,
            *,
            candidate: Optional[dict[str, Any]] = None,
            refresh_existing: bool,
            existing_status: str,
            incubation_budget_track: str,
            read_only: bool = False,
        ) -> dict[str, Any]:
            return SubmissionAdmissionAuthority.resolve(
                gate,
                candidate=candidate,
                refresh_existing=refresh_existing,
                existing_status=existing_status,
                incubation_budget_track=incubation_budget_track,
                runtime_bootstrap_resolver=cls._runtime_bootstrap_context,
                read_only=read_only,
            )

        @classmethod
        def _resolve_submission_lane(
            cls,
            gate: dict,
            *,
            candidate: Optional[dict[str, Any]] = None,
            refresh_existing: bool,
            existing_status: str,
            incubation_budget_track: str,
        ) -> tuple[str, str]:
            plan = cls._resolve_submission_action_plan(
                gate,
                candidate=candidate,
                refresh_existing=refresh_existing,
                existing_status=existing_status,
                incubation_budget_track=incubation_budget_track,
            )
            return str(plan.get("submission_lane") or "deferred_submission"), str(plan.get("final_status") or "submitted")

        @staticmethod
        def _apply_submission_action_audit(
            quality_report: Optional[dict],
            *,
            final_status: str,
            submission_lane: str,
            submission_audit: Optional[dict] = None,
        ) -> dict:
            report = quality_report if isinstance(quality_report, dict) else {}
            summary = dict(report.get("summary") or {})
            audit = dict(submission_audit or {})
            summary["status_after_review"] = final_status
            summary["submission_lane"] = submission_lane
            report["submission_lane"] = submission_lane
            field_names = (
                "live_review_ready",
                "paper_lane_ready",
                "paper_account_id",
                "paper_account_status",
                "incubation_factory_required",
                "paper_observation_backlog_status",
                "paper_observation_handoff_warning",
                "diagnostic_observation",
                "diagnostic_lane_ready",
                "diagnostic_account_id",
                "diagnostic_account_status",
                "diagnostic_fingerprint",
                "diagnostic_guard",
                "diagnostic_reason",
                "diagnostic_reason_code",
                "diagnostic_ttl_days",
                "admission_layer",
                "live_review_account_id",
                "runtime_control_mode",
                "runtime_control_status",
                "promotion_review_id",
                "promotion_review_status",
                "promotion_review_recommendation",
                "promotion_review_score",
                "pool_admission_applied",
                "promotion_applied_transition",
                "trade_prediction_promotion_gate",
                "trade_prediction_promotion_gate_enabled",
                "trade_prediction_promotion_gate_hard_block",
                "trade_prediction_promotion_gate_reasons",
                "runtime_bootstrap_eligible",
                "runtime_bootstrap_reason",
                "runtime_bootstrap_budget_tier",
                "runtime_playbook_present",
                "formal_track_requested",
                "formal_track_eligible",
                "formal_track_blockers",
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
                "submission_action",
                "submission_action_type",
                "submission_action_trigger",
                "submission_action_gaps",
                "submission_action_fallback_conditions",
                "submission_action_next_step",
                "submission_action_completed",
            )
            clearable_fields = {"submission_action_next_step"}
            for field_name in field_names:
                if field_name not in audit:
                    continue
                value = audit.get(field_name)
                if value in (None, [], {}, "") and field_name not in clearable_fields:
                    continue
                summary[field_name] = value
                report[field_name] = value
            report["summary"] = summary
            return report

        async def _enqueue_paper_observation(
            self,
            db,
            strategy: dict,
            snapshot: dict,
        ) -> dict:
            paper_account_id = None
            paper_account_status = None
            handoff_warning = None
            incubation_gateway = self._get_incubation_gateway()

            try:
                binding = await incubation_gateway.ensure_account(
                    db,
                    strategy,
                    source_run_id=snapshot.get("date"),
                    stage="paper",
                )
                paper_account_id = (
                    (binding or {}).get("account_id")
                    or (binding or {}).get("id")
                    or ((binding or {}).get("account") or {}).get("id")
                    or ((binding or {}).get("account") or {}).get("account_id")
                    or ((binding or {}).get("binding") or {}).get("account_id")
                    or ((binding or {}).get("binding") or {}).get("id")
                )
                if paper_account_id:
                    updated = await self._call_optional_db_method(
                        db,
                        "update_paper_account_status",
                        paper_account_id,
                        "active",
                        stage="paper",
                        promotion_candidate=False,
                    )
                    paper_account_status = (updated or {}).get("status") if isinstance(updated, dict) else "active"
            except Exception as exc:
                handoff_warning = "paper_observation_account_unavailable"
                logger.warning("StrategyFactory: ensure paper observation account failed for %s: %s", strategy.get("id"), exc)

            paper_lane_ready = bool(paper_account_id)
            if not paper_lane_ready and not handoff_warning:
                handoff_warning = "paper_observation_account_unavailable"
            return {
                "paper_lane_ready": paper_lane_ready,
                "paper_account_id": paper_account_id,
                "paper_account_status": paper_account_status or ("active" if paper_account_id else None),
                "incubation_factory_required": True,
                "paper_observation_backlog_status": "queued" if paper_lane_ready else "handoff_failed",
                "paper_observation_handoff_warning": handoff_warning,
            }

        async def _enqueue_diagnostic_observation(
            self,
            db,
            strategy: dict,
            snapshot: dict,
        ) -> dict:
            diagnostic_account_id = None
            diagnostic_account_status = None
            incubation_gateway = self._get_incubation_gateway()
            trace = dict(strategy.get("_closure_trace") or {})
            trace.update(
                {
                    "admission_layer": "diagnostic",
                    "diagnostic_observation": True,
                    "diagnostic_reason": strategy.get("diagnostic_reason")
                    or trace.get("diagnostic_reason"),
                    "diagnostic_reason_code": strategy.get("diagnostic_reason_code")
                    or trace.get("diagnostic_reason_code")
                    or strategy.get("diagnostic_reason")
                    or trace.get("diagnostic_reason"),
                    "diagnostic_fingerprint": strategy.get("diagnostic_fingerprint")
                    or trace.get("diagnostic_fingerprint")
                    or dict(strategy.get("params") or {}).get("diagnostic_fingerprint"),
                    "diagnostic_guard": strategy.get("diagnostic_guard")
                    or trace.get("diagnostic_guard")
                    or dict(strategy.get("params") or {}).get("diagnostic_guard"),
                    "diagnostic_ttl_days": strategy.get("diagnostic_ttl_days")
                    or trace.get("diagnostic_ttl_days")
                    or _diagnostic_observation_ttl_days(),
                    "source_lane": "diagnostic_observation",
                }
            )
            strategy = {
                **dict(strategy or {}),
                "_closure_trace": trace,
            }

            try:
                binding = await incubation_gateway.ensure_account(
                    db,
                    strategy,
                    source_run_id=snapshot.get("date"),
                    stage="diagnostic",
                )
                diagnostic_account_id = (
                    ((binding or {}).get("account") or {}).get("id")
                    or ((binding or {}).get("binding") or {}).get("account_id")
                )
                if diagnostic_account_id:
                    updated = await self._call_optional_db_method(
                        db,
                        "update_paper_account_status",
                        diagnostic_account_id,
                        "active",
                        stage="diagnostic",
                        promotion_candidate=False,
                    )
                    diagnostic_account_status = (updated or {}).get("status") if isinstance(updated, dict) else "active"
            except Exception as exc:
                logger.warning("StrategyFactory: ensure diagnostic observation account failed for %s: %s", strategy.get("id"), exc)

            return {
                "diagnostic_observation": True,
                "diagnostic_lane_ready": bool(diagnostic_account_id),
                "diagnostic_account_id": diagnostic_account_id,
                "diagnostic_account_status": diagnostic_account_status or ("active" if diagnostic_account_id else None),
                "diagnostic_fingerprint": trace.get("diagnostic_fingerprint"),
                "diagnostic_guard": trace.get("diagnostic_guard"),
                "diagnostic_reason": trace.get("diagnostic_reason"),
                "diagnostic_reason_code": trace.get("diagnostic_reason_code"),
                "diagnostic_ttl_days": trace.get("diagnostic_ttl_days"),
                "admission_layer": "diagnostic",
            }

        async def _enqueue_live_ready_review(
            self,
            db,
            strategy: dict,
            snapshot: dict,
            gate: dict,
            trace_context: Optional[dict[str, Any]] = None,
        ) -> dict:
            review_account_id = None
            runtime_control = None
            promotion_review = None
            trade_prediction_gate: dict[str, Any] = {}
            incubation_gateway = self._get_incubation_gateway()

            try:
                binding = await incubation_gateway.ensure_account(
                    db,
                    strategy,
                    source_run_id=snapshot.get("date"),
                    stage="candidate",
                )
                review_account_id = (
                    ((binding or {}).get("account") or {}).get("id")
                    or ((binding or {}).get("binding") or {}).get("account_id")
                )
                if review_account_id:
                    await self._call_optional_db_method(
                        db,
                        "update_paper_account_status",
                        review_account_id,
                        "active",
                        stage="candidate",
                        promotion_candidate=True,
                    )
            except Exception as exc:
                logger.warning("StrategyFactory: ensure live-ready paper account failed for %s: %s", strategy.get("id"), exc)

            try:
                runtime_control = await get_strategy_runtime_control_service().set_control(
                    db,
                    strategy,
                    control_mode="monitor",
                    source="strategy_factory_live_ready_review",
                    reason="live_candidate_ready_submission",
                    trigger_event_type="factory_live_ready_submission",
                    action_summary={
                        "submission_lane": "live_ready_review",
                        "direct_trade_candidate": bool(gate.get("live_candidate_ready")),
                    },
                    metadata={
                        "submission_lane": "live_ready_review",
                        "snapshot_date": snapshot.get("date"),
                        "admission_stage": gate.get("admission_stage"),
                        "incubation_pass_mode": gate.get("incubation_pass_mode"),
                    },
                    apply_runtime_changes=True,
                )
            except Exception as exc:
                logger.warning("StrategyFactory: set live-ready runtime control failed for %s: %s", strategy.get("id"), exc)

            try:
                params = dict((strategy or {}).get("params") or {})
                contract = dict(params.get("trade_prediction_contract") or {})
                stock_code = (
                    contract.get("stock_code")
                    or params.get("stock_code")
                    or (strategy or {}).get("stock_code")
                )
                trade_prediction_gate = await evaluate_trade_prediction_promotion_gate(
                    db,
                    strategy_id=str((strategy or {}).get("id") or "").strip() or None,
                    stock_code=str(stock_code or "").strip() or None,
                )
            except Exception as exc:
                logger.warning("StrategyFactory: trade prediction promotion gate failed for %s: %s", strategy.get("id"), exc)
                trade_prediction_gate = {
                    "object": "strategy_factory.trade_prediction_promotion_gate",
                    "enabled": False,
                    "diagnostic_only": True,
                    "passed": True,
                    "diagnostic_passed": False,
                    "hard_block": False,
                    "degraded": True,
                    "error": str(exc),
                    "reasons": ["trade_prediction_gate_error"],
                }

            promotion_auto_apply = not bool(trade_prediction_gate.get("hard_block"))
            try:
                promotion_review = await get_strategy_promotion_pipeline_service().review(
                    db,
                    strategy,
                    source="strategy_factory_live_ready_review",
                    auto_apply=promotion_auto_apply,
                )
            except Exception as exc:
                logger.warning("StrategyFactory: trigger live-ready promotion review failed for %s: %s", strategy.get("id"), exc)

            review_payload = dict((promotion_review or {}).get("review") or {})
            applied_transition = dict((promotion_review or {}).get("applied_transition") or {})
            applied_status = str(applied_transition.get("to") or "").strip().lower()
            if bool(trade_prediction_gate.get("hard_block")) and applied_status:
                applied_transition = {}
                applied_status = ""
            action_audit: dict[str, Any] = {}
            if applied_status:
                action_audit["final_status"] = applied_status
                action_audit["pool_admission_applied"] = applied_status == "listed"
                action_audit["promotion_applied_transition"] = applied_transition
            if applied_status == "listed":
                action_audit.update(
                    {
                        "submission_action": {
                            "type": "pool_admission",
                            "trigger_reason": "live_candidate_ready_pool_admission",
                            "gaps": [],
                            "fallback_conditions": ["return_to_runtime_review_if_post_admission_controls_fail"],
                            "next_step": None,
                            "submission_lane": "live_ready_review",
                            "final_status": applied_status,
                            "completed": True,
                        },
                        "submission_action_type": "pool_admission",
                        "submission_action_trigger": "live_candidate_ready_pool_admission",
                        "submission_action_gaps": [],
                        "submission_action_fallback_conditions": [
                            "return_to_runtime_review_if_post_admission_controls_fail"
                        ],
                        "submission_action_next_step": None,
                        "submission_action_completed": True,
                    }
                )
            return {
                "live_review_ready": bool(review_account_id or runtime_control or review_payload),
                "paper_account_id": review_account_id,
                "live_review_account_id": review_account_id,
                "runtime_control_mode": (runtime_control or {}).get("control_mode"),
                "runtime_control_status": (runtime_control or {}).get("status"),
                "promotion_review_id": review_payload.get("id"),
                "promotion_review_status": review_payload.get("status"),
                "promotion_review_recommendation": review_payload.get("recommendation"),
                "promotion_review_score": review_payload.get("score"),
                "trade_prediction_promotion_gate": trade_prediction_gate,
                "trade_prediction_promotion_gate_enabled": bool(trade_prediction_gate.get("enabled")),
                "trade_prediction_promotion_gate_hard_block": bool(trade_prediction_gate.get("hard_block")),
                "trade_prediction_promotion_gate_reasons": list(trade_prediction_gate.get("reasons") or []),
                **action_audit,
            }

        async def _handle_existing_refresh(
            self,
            strategy_id: str,
            name: str,
            candidate: dict,
            gate: dict,
            quality_report: dict,
            backtest_metrics: Optional[dict],
            snapshot: dict,
            validation_report: Optional[dict],
            risk_report: Optional[dict],
            db,
            *,
            existing_status: str,
            submission_lane: str,
            submission_action: Optional[dict[str, Any]] = None,
        ) -> dict:
            """复用已有策略时，仅刷新质量报告与实验留痕。"""
            self._apply_submission_action_audit(
                quality_report,
                final_status=existing_status,
                submission_lane=submission_lane,
                submission_audit=dict(submission_action or {}),
            )
            await self._record_experiment(
                db,
                candidate,
                strategy_id,
                name,
                snapshot,
                gate,
                "accepted" if gate.get("passed") else "rejected",
                validation_report,
                risk_report,
                quality_report,
                backtest_metrics,
                None,
            )
            return {
                "refreshed_existing": True,
                "reused_existing_strategy_id": strategy_id,
                "existing_status": existing_status,
                "submission_lane": submission_lane,
                "final_status": existing_status,
                **dict(submission_action or {}),
            }
