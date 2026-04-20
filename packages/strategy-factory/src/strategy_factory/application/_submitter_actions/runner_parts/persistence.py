
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
            semantic_hard_fail = bool(
                list(
                    dict(payload.get("evidence_alignment_audit") or {}).get("hard_fail_reasons") or []
                )
            )
            quality_passed = bool(normalized_gate.get("passed"))
            runtime_bootstrap_eligible = (
                quality_passed
                and validation_grade != "D"
                and strategy_type_registered
                and not missing_runtime_fields
                and not semantic_hard_fail
            )
            if runtime_bootstrap_eligible:
                runtime_bootstrap_reason = (
                    "execution_semantic_gap_observe_only"
                    if execution_semantic_gap
                    else "proxy_runtime_observe_only"
                    if proxy_runtime_used
                    else "diagnostic_only_observe"
                    if diagnostic_only
                    else "quality_passed_non_d_candidate_with_complete_runtime_contract"
                )
            elif not quality_passed:
                runtime_bootstrap_reason = "quality_gate_failed"
            elif validation_grade == "D":
                runtime_bootstrap_reason = "validation_grade_d_not_allowed_for_runtime"
            elif not strategy_type_registered:
                runtime_bootstrap_reason = "strategy_type_not_registered"
            elif missing_runtime_fields:
                runtime_bootstrap_reason = f"missing_runtime_contract:{','.join(missing_runtime_fields)}"
            elif semantic_hard_fail:
                runtime_bootstrap_reason = "semantic_hard_fail"
            else:
                runtime_bootstrap_reason = "runtime_bootstrap_blocked"
            budget_tier = None
            if runtime_bootstrap_eligible:
                budget_tier = (
                    "micro"
                    if execution_semantic_gap or proxy_runtime_used or diagnostic_only
                    else "standard" if validation_grade in {"A", "B"} else "micro"
                )
            return {
                "runtime_bootstrap_eligible": runtime_bootstrap_eligible,
                "runtime_bootstrap_reason": runtime_bootstrap_reason,
                "runtime_bootstrap_budget_tier": budget_tier,
                "runtime_playbook_present": runtime_playbook_present,
                "runtime_contract_missing_fields": missing_runtime_fields,
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
            return validation_grade in {"A", "B"}

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
        ) -> dict[str, Any]:
            normalized_gate = dict(gate or {})
            runtime_bootstrap = cls._runtime_bootstrap_context(
                normalized_gate,
                candidate=candidate,
            )
            gate_a_decision = str(normalized_gate.get("gate_a_decision") or "").strip().lower()
            readiness_fields = (
                "research_candidate_ready",
                "incubation_candidate_ready",
                "live_candidate_ready",
                "research_only_due_to_trade_audit_gap",
            )
            if bool(normalized_gate.get("passed")) and not any(field in normalized_gate for field in readiness_fields):
                normalized_gate["research_candidate_ready"] = True
                normalized_gate["incubation_candidate_ready"] = True
            admission_block_reasons = list(normalized_gate.get("admission_block_reasons") or normalized_gate.get("reasons") or [])
            strict_formal_ready = bool(normalized_gate.get("strict_incubation_ready")) or (
                str(normalized_gate.get("incubation_pass_mode") or "").strip().lower() == "strict"
            )
            formal_track_requested = str(incubation_budget_track or "").strip().lower() == "formal_incubation"
            formal_track_blockers: list[str] = []
            if formal_track_requested:
                if not bool(runtime_bootstrap.get("runtime_bootstrap_eligible")):
                    formal_track_blockers.append(
                        str(runtime_bootstrap.get("runtime_bootstrap_reason") or "runtime_bootstrap_not_eligible")
                    )
                if bool(runtime_bootstrap.get("execution_semantic_gap")):
                    formal_track_blockers.extend(
                        list(runtime_bootstrap.get("execution_semantic_gap_reasons") or [])
                        or ["execution_semantic_gap"]
                    )
                if not bool(runtime_bootstrap.get("semantic_runtime_match")):
                    formal_track_blockers.append("semantic_runtime_mismatch")
                if bool(runtime_bootstrap.get("proxy_runtime_used")):
                    formal_track_blockers.append("proxy_runtime_not_allowed_for_formal_incubation")
                if bool(runtime_bootstrap.get("diagnostic_only")):
                    formal_track_blockers.append("diagnostic_only_runtime")
                readiness_tier = (
                    str(runtime_bootstrap.get("execution_readiness_tier") or "").strip().lower() or "unknown"
                )
                if readiness_tier != "formal_runtime_ready":
                    formal_track_blockers.append(f"execution_readiness_tier:{readiness_tier}")
                if not strict_formal_ready:
                    formal_track_blockers.append("strict_incubation_pass_required_for_formal_track")
            formal_track_blockers = list(
                dict.fromkeys([item for item in formal_track_blockers if str(item).strip()])
            )
            formal_track_eligible = bool(formal_track_requested and not formal_track_blockers)
            if refresh_existing:
                action_type = "refresh_existing"
                submission_lane = "refresh_existing"
                final_status = str(existing_status or "draft")
                trigger = "existing_strategy_refresh"
                gaps = []
                fallback_conditions = ["manual_review_if_contract_changes"]
                next_step = "existing_status_preserved"
                completed = True
            elif gate_a_decision == "revise" and not bool(normalized_gate.get("passed")):
                action_type = "research_only"
                submission_lane = "deferred_submission"
                final_status = "draft"
                trigger = "gate_a_revision_required"
                gaps = admission_block_reasons
                fallback_conditions = ["supply_required_research_protocol_fields_and_replay_submission"]
                next_step = "research"
                completed = True
            elif gate_a_decision == "reject" and not bool(normalized_gate.get("passed")):
                action_type = "research_only"
                submission_lane = "rejected"
                final_status = "rejected"
                trigger = "gate_a_reject"
                gaps = admission_block_reasons
                fallback_conditions = ["restore_required_research_protocol_fields_before_submission_replay"]
                next_step = "research"
                completed = True
            elif not bool(normalized_gate.get("passed")):
                action_type = "research_only"
                submission_lane = "rejected"
                final_status = "rejected"
                trigger = "quality_gate_failed"
                gaps = admission_block_reasons
                fallback_conditions = ["re_enter_after_quality_gaps_closed"]
                next_step = "incubation"
                completed = True
            elif bool(normalized_gate.get("live_candidate_ready")) and not bool(runtime_bootstrap.get("execution_semantic_gap")):
                formal_runtime_ready = (
                    bool(runtime_bootstrap.get("semantic_runtime_match"))
                    and not bool(runtime_bootstrap.get("proxy_runtime_used"))
                    and not bool(runtime_bootstrap.get("diagnostic_only"))
                    and str(runtime_bootstrap.get("execution_readiness_tier") or "").strip().lower() == "formal_runtime_ready"
                )
                if not formal_runtime_ready:
                    action_type = "paper"
                    submission_lane = "observe_incubation"
                    final_status = "submitted"
                    trigger = str(
                        runtime_bootstrap.get("runtime_bootstrap_reason")
                        or "formal_lane_requires_semantic_runtime_match"
                    )
                    gaps = list(
                        dict.fromkeys(
                            [
                                *admission_block_reasons,
                                trigger,
                            ]
                        )
                    )
                    fallback_conditions = [
                        "promote_after_runtime_data_source_and_semantic_contract_are_repaired",
                    ]
                    next_step = "runtime_review"
                    completed = False
                else:
                    action_type = "runtime_review"
                    submission_lane = "live_ready_review"
                    final_status = "submitted"
                    trigger = "live_candidate_ready"
                    gaps = []
                    fallback_conditions = [
                        "downgrade_to_paper_if_runtime_review_fails",
                        "return_to_research_if_runtime_alerts_fire",
                    ]
                    next_step = "pool_admission"
                    completed = False
            elif formal_track_eligible:
                action_type = "incubation"
                submission_lane = "formal_incubation"
                final_status = "incubating"
                trigger = "strict_incubation_ready_and_budget_formal"
                gaps = admission_block_reasons
                fallback_conditions = [
                    "downgrade_to_observe_if_signal_quality_or_execution_evidence_weakens",
                    "return_to_research_if_runtime_risk_accumulates",
                ]
                next_step = "paper"
                completed = False
            elif runtime_bootstrap.get("runtime_bootstrap_eligible"):
                action_type = "paper"
                submission_lane = "observe_incubation"
                final_status = "submitted"
                trigger = "runtime_bootstrap_observe"
                gaps = admission_block_reasons
                fallback_conditions = [
                    "promote_to_formal_after_signal_quality_and_execution_conversion_improve",
                    "return_to_research_if_runtime_bootstrap_evidence_turns_negative",
                ]
                next_step = "runtime_review"
                completed = False
            elif formal_track_requested:
                action_type = "research_only"
                submission_lane = "deferred_submission"
                final_status = "submitted" if bool(normalized_gate.get("research_candidate_ready")) else "rejected"
                trigger = "formal_incubation_requires_bootstrap_or_strict_gate"
                gaps = list(
                    dict.fromkeys(
                        [
                            *list(admission_block_reasons),
                            *formal_track_blockers,
                        ]
                    )
                )
                fallback_conditions = [
                    "promote_after_runtime_contract_is_repaired_or_quality_improves",
                    "observe_track_allowed_after_runtime_bootstrap_eligibility_is_restored",
                ]
                next_step = "research"
                completed = True
            elif str(incubation_budget_track or "").strip().lower() == "observe_incubation":
                action_type = "research_only"
                submission_lane = "deferred_submission"
                final_status = "submitted" if bool(normalized_gate.get("research_candidate_ready")) else "rejected"
                trigger = str(runtime_bootstrap.get("runtime_bootstrap_reason") or "observe_track_runtime_contract_incomplete")
                gaps = list(dict.fromkeys([*admission_block_reasons, trigger]))
                fallback_conditions = ["repair_runtime_contract_and_replay_submission"]
                next_step = "research"
                completed = True
            else:
                action_type = "research_only"
                submission_lane = "deferred_submission"
                final_status = "submitted"
                trigger = str(runtime_bootstrap.get("runtime_bootstrap_reason") or "budget_deferred_research_only")
                gaps = list(dict.fromkeys([*admission_block_reasons, trigger]))
                fallback_conditions = ["promote_to_observe_after_runtime_bootstrap_eligibility_is_restored"]
                next_step = "incubation"
                completed = True

            plan = {
                "type": action_type,
                "trigger_reason": trigger,
                "gaps": list(gaps),
                "fallback_conditions": list(fallback_conditions),
                "next_step": next_step,
                "submission_lane": submission_lane,
                "final_status": final_status,
                "completed": bool(completed),
                "formal_track_requested": formal_track_requested,
                "formal_track_eligible": formal_track_eligible,
                "formal_track_blockers": list(formal_track_blockers),
                **runtime_bootstrap,
            }
            return {
                "submission_action": plan,
                "submission_action_type": action_type,
                "submission_action_trigger": trigger,
                "submission_action_gaps": list(gaps),
                "submission_action_fallback_conditions": list(fallback_conditions),
                "submission_action_next_step": next_step,
                "submission_action_completed": bool(completed),
                "submission_lane": submission_lane,
                "final_status": final_status,
                "formal_track_requested": formal_track_requested,
                "formal_track_eligible": formal_track_eligible,
                "formal_track_blockers": list(formal_track_blockers),
                **runtime_bootstrap,
            }

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
                "live_review_account_id",
                "runtime_control_mode",
                "runtime_control_status",
                "promotion_review_id",
                "promotion_review_status",
                "promotion_review_recommendation",
                "promotion_review_score",
                "pool_admission_applied",
                "promotion_applied_transition",
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
            incubation_gateway = self._get_incubation_gateway()

            try:
                binding = await incubation_gateway.ensure_account(
                    db,
                    strategy,
                    source_run_id=snapshot.get("date"),
                    stage="paper",
                )
                paper_account_id = (
                    ((binding or {}).get("account") or {}).get("id")
                    or ((binding or {}).get("binding") or {}).get("account_id")
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
                logger.warning("StrategyFactory: ensure paper observation account failed for %s: %s", strategy.get("id"), exc)

            return {
                "paper_lane_ready": bool(paper_account_id),
                "paper_account_id": paper_account_id,
                "paper_account_status": paper_account_status or ("active" if paper_account_id else None),
            }

        async def _enqueue_live_ready_review(
            self,
            db,
            strategy: dict,
            snapshot: dict,
            gate: dict,
        ) -> dict:
            review_account_id = None
            runtime_control = None
            promotion_review = None
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
                promotion_review = await get_strategy_promotion_pipeline_service().review(
                    db,
                    strategy,
                    source="strategy_factory_live_ready_review",
                    auto_apply=True,
                )
            except Exception as exc:
                logger.warning("StrategyFactory: trigger live-ready promotion review failed for %s: %s", strategy.get("id"), exc)

            review_payload = dict((promotion_review or {}).get("review") or {})
            applied_transition = dict((promotion_review or {}).get("applied_transition") or {})
            applied_status = str(applied_transition.get("to") or "").strip().lower()
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
