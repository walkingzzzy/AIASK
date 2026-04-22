
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
            *,
            trace_context: Optional[dict[str, Any]] = None,
        ) -> dict:
            review_account_id = None
            runtime_control = None
            promotion_review = None
            incubation_gateway = self._get_incubation_gateway()
            trace_payload = dict(trace_context or {})

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
                        "factory_run_id": trace_payload.get("factory_run_id"),
                        "correlation_id": trace_payload.get("correlation_id"),
                    },
                    metadata={
                        "submission_lane": "live_ready_review",
                        "snapshot_date": snapshot.get("date"),
                        "admission_stage": gate.get("admission_stage"),
                        "incubation_pass_mode": gate.get("incubation_pass_mode"),
                        **trace_payload,
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
                    metadata=trace_payload,
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

        async def _handle_post_gate(
            self,
            strategy_id: str,
            name: str,
            candidate: dict,
            data: dict,
            gate: dict,
            quality_report: dict,
            backtest_metrics: Optional[dict],
            snapshot: dict,
            validation_report: Optional[dict],
            risk_report: Optional[dict],
            db,
            submission_lane: str,
            submission_action: Optional[dict[str, Any]] = None,
        ) -> dict:
            """质检通过后的生命周期动作统一交给 coordinator 编排。"""
            from ..services.lifecycle_coordinator import LifecycleTransitionRequest

            incubation_budget = dict(candidate.get("incubation_budget") or {})
            incubation_budget_track = str(incubation_budget.get("track") or "formal_incubation").strip().lower()
            lifecycle_result = await self._lifecycle_coordinator.execute(
                db,
                LifecycleTransitionRequest(
                    strategy_id=strategy_id,
                    name=name,
                    candidate=candidate,
                    data=data,
                    gate=gate,
                    quality_report=quality_report,
                    snapshot=snapshot,
                    submission_lane=submission_lane,
                    submission_action=dict(submission_action or {}),
                    backtest_metrics=backtest_metrics,
                    validation_report=validation_report,
                    risk_report=risk_report,
                    factory_run_id=candidate.get("factory_run_id") or snapshot.get("factory_run_id"),
                    trace_id=candidate.get("trace_id"),
                    correlation_id=(
                        candidate.get("correlation_id")
                        or candidate.get("trace_id")
                        or snapshot.get("correlation_id")
                    ),
                    parent_task_run_id=candidate.get("task_run_id") or dict(candidate.get("params") or {}).get("task_run_id"),
                    source_action="strategy_factory_submit",
                    snapshot_date=snapshot.get("date"),
                    quality_gate_summary=dict(quality_report.get("summary") or {}),
                ),
            )
            lifecycle_payload = lifecycle_result.to_dict()
            incubation_binding = lifecycle_payload.get("incubation_binding")
            incubation_pipeline = lifecycle_payload.get("incubation_pipeline")
            vector_profile = lifecycle_payload.get("vector_profile")
            vector_audit = dict(lifecycle_payload.get("vector_audit") or {})
            live_review_action = dict(lifecycle_payload.get("live_review_action") or {})
            paper_action = dict(lifecycle_payload.get("paper_action") or {})
            action_audit = dict(lifecycle_payload.get("action_audit") or {})
            final_status = str(lifecycle_payload.get("final_status") or "rejected")

            self._apply_submission_action_audit(
                quality_report,
                final_status=final_status,
                submission_lane=submission_lane,
                submission_audit=action_audit,
            )

            if gate.get("passed"):
                await self._record_experiment(
                    db,
                    candidate,
                    strategy_id,
                    name,
                    snapshot,
                    gate,
                    "accepted",
                    validation_report,
                    risk_report,
                    quality_report,
                    backtest_metrics,
                    incubation_pipeline,
                )
            else:
                await self._record_experiment(
                    db,
                    candidate,
                    strategy_id,
                    name,
                    snapshot,
                    gate,
                    "rejected",
                    validation_report,
                    risk_report,
                    quality_report,
                    backtest_metrics,
                    None,
                )

            return {
                "incubation_account_id": ((incubation_binding or {}).get("account") or {}).get("id"),
                "incubation_pipeline_stage": ((incubation_pipeline or {}).get("snapshot") or {}).get("pipeline_stage"),
                "incubation_pipeline_status": ((incubation_pipeline or {}).get("snapshot") or {}).get("pipeline_status"),
                "incubation_readiness_score": ((incubation_pipeline or {}).get("snapshot") or {}).get("readiness_score"),
                "incubation_task_run_id": (incubation_pipeline or {}).get("task_run_id"),
                "incubation_budget_track": incubation_budget_track,
                "incubation_budget_rank": incubation_budget.get("rank"),
                "incubation_budget_priority_score": incubation_budget.get("priority_score"),
                "submission_lane": submission_lane,
                "vector_profile_id": (vector_profile or {}).get("id"),
                "vector_backend": (vector_profile or {}).get("backend"),
                "vector_backend_requested": (vector_audit or {}).get("backend_requested"),
                "vector_backend_used": (vector_audit or {}).get("backend_used"),
                "vector_fallback_used": (vector_audit or {}).get("fallback_used"),
                "vector_fallback_reason": (vector_audit or {}).get("fallback_reason"),
                "vector_latency_ms": (vector_audit or {}).get("latency_ms"),
                "execution_audit_snapshot_id": lifecycle_payload.get("execution_audit_snapshot_id"),
                "correlation_id": lifecycle_payload.get("correlation_id"),
                "trace_id": lifecycle_payload.get("trace_id"),
                "factory_run_id": lifecycle_payload.get("factory_run_id"),
                "parent_task_run_id": lifecycle_payload.get("parent_task_run_id"),
                "lifecycle_task_run_id": ((lifecycle_payload.get("lifecycle_task_run") or {}).get("id")),
                "lifecycle_transition_steps": lifecycle_payload.get("steps") or [],
                **paper_action,
                **live_review_action,
                **action_audit,
                "final_status": final_status,
            }

        @classmethod
        def _build_replay_candidate(
            cls,
            strategy: dict,
            *,
            latest_report: Optional[dict],
            backtest_metrics: Optional[dict],
        ) -> dict[str, Any]:
            payload = dict(strategy or {})
            params = dict(payload.get("params") or {})
            report = dict(latest_report or {})
            summary = dict(report.get("summary") or {})
            quality_gate = dict(report.get("quality_gate") or {})
            candidate = apply_resolved_candidate_envelope(
                {
                    **payload,
                    "id": payload.get("id"),
                    "name": payload.get("name"),
                    "strategy_type": payload.get("strategy_type"),
                    "params": params,
                    "spawn_reason": (
                        summary.get("spawn_reason")
                        or payload.get("spawn_reason")
                        or params.get("spawn_reason")
                    ),
                    "dedup_result": dict(
                        report.get("dedup_report")
                        or payload.get("dedup_result")
                        or params.get("dedup_result")
                        or {}
                    ),
                    "committee_review": dict(
                        report.get("committee_review")
                        or summary.get("committee_review")
                        or payload.get("committee_review")
                        or params.get("committee_review")
                        or {}
                    ),
                    "backtest_metrics": dict(backtest_metrics or report.get("backtest_metrics") or {}),
                }
            )
            incubation_budget = dict(
                candidate.get("incubation_budget")
                or params.get("incubation_budget")
                or summary.get("incubation_budget")
                or {}
            )
            summary_track = str(summary.get("incubation_budget_track") or "").strip()
            if summary_track and not incubation_budget.get("track"):
                incubation_budget["track"] = summary_track
            if summary.get("incubation_budget_rank") is not None and incubation_budget.get("rank") is None:
                incubation_budget["rank"] = summary.get("incubation_budget_rank")
            if (
                summary.get("incubation_budget_priority_score") is not None
                and incubation_budget.get("priority_score") is None
            ):
                incubation_budget["priority_score"] = summary.get("incubation_budget_priority_score")
            if (
                summary.get("incubation_budget_exploration_candidate") is not None
                and incubation_budget.get("exploration_candidate") is None
            ):
                incubation_budget["exploration_candidate"] = bool(
                    summary.get("incubation_budget_exploration_candidate")
                )
            if incubation_budget:
                candidate["incubation_budget"] = incubation_budget
            for field_name in _SEMANTIC_CONTRACT_FIELDS:
                value = candidate.get(field_name)
                if value in (None, "", [], {}):
                    value = params.get(field_name)
                if value in (None, "", [], {}):
                    value = summary.get(field_name)
                if value in (None, "", [], {}):
                    value = quality_gate.get(field_name)
                if value not in (None, "", [], {}):
                    candidate[field_name] = value
            return cls._ensure_runtime_playbook(candidate)
