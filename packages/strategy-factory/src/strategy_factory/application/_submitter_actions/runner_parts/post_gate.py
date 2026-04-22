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
