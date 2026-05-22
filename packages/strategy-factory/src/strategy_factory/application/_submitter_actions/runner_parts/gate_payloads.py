        async def submit(
            self,
            candidates: List[dict],
            snapshot: dict,
            db,
            *,
            read_only: bool = False,
        ) -> dict:
            """批量提交候选策略，每个策略独立处理，单个失败不影响其他。"""
            created = 0
            created_total = 0
            created_strategy_pool = 0
            created_audit_only = 0
            refreshed = 0
            submitted = 0
            gate_3_input = 0
            passed = 0
            gate_3_passed = 0
            gate_3_failed = 0
            gate_3_provisional_passed = 0
            gate_3_failure_codes: Counter[str] = Counter()
            submission_lane_counts: Counter[str] = Counter()
            submission_action_type_counts: Counter[str] = Counter()
            admission_decision_counts: Counter[str] = Counter()
            strict_incubation_ready_count = 0
            factor_performance_reported_count = 0
            submitted_items: List[dict] = []
            incubation_budget_plan = IncubationBudgeter.plan(candidates, snapshot)
            incubation_budget_summary = dict(incubation_budget_plan.get("summary") or {})
            for candidate in candidates:
                marker = int(id(candidate))
                candidate["incubation_budget"] = dict(
                    (incubation_budget_plan.get("plans") or {}).get(marker) or {}
                )
            submit_concurrency = int(_compat_setting("SUBMIT_CONCURRENCY", SUBMIT_CONCURRENCY) or SUBMIT_CONCURRENCY)
            sem = asyncio.Semaphore(submit_concurrency)

            async def _submit_guarded(candidate: dict) -> Optional[dict]:
                async with sem:
                    try:
                        return await self._submit_one(
                            candidate,
                            snapshot,
                            db,
                            read_only=read_only,
                        )
                    except Exception as exc:
                        logger.warning("StrategySubmitter: failed for %s: %s", candidate.get("strategy_type"), exc)
                        return None

            results = await asyncio.gather(
                *[_submit_guarded(c) for c in candidates],
                return_exceptions=True,
            )
            for result in results:
                if result is None or isinstance(result, BaseException):
                    continue
                gate_3_input += 1
                if result.get("created_total", result.get("created", False)):
                    created_total += 1
                if result.get("created_strategy_pool", result.get("created", False)):
                    created += 1
                    created_strategy_pool += 1
                if result.get("created_audit_only"):
                    created_audit_only += 1
                if result.get("refreshed_existing"):
                    refreshed += 1
                if result.get("submitted"):
                    submitted += 1
                if result.get("passed"):
                    passed += 1
                gate_3 = dict(result.get("gate_3") or {})
                gate_a_decision = str(gate_3.get("gate_a_decision") or "").strip().lower()
                gate_a_short_circuit = gate_a_decision in {"revise", "reject"} and str(
                    gate_3.get("admission_stage") or ""
                ).strip().lower() == "gate_a"
                if gate_3.get("passed"):
                    gate_3_passed += 1
                    if gate_3.get("provisional_pass"):
                        gate_3_provisional_passed += 1
                elif not gate_a_short_circuit:
                    gate_3_failed += 1
                    for code in gate_3.get("reason_codes") or []:
                        normalized = str(code or "").strip()
                        if normalized:
                            gate_3_failure_codes[normalized] += 1
                summary = dict(result["summary"] or {})
                submission_lane = str(summary.get("submission_lane") or "").strip().lower()
                if submission_lane:
                    submission_lane_counts[submission_lane] += 1
                action_type = str(summary.get("submission_action_type") or "").strip().lower()
                if action_type:
                    submission_action_type_counts[action_type] += 1
                admission_decision = str(summary.get("admission_decision") or "").strip().lower()
                if admission_decision:
                    admission_decision_counts[admission_decision] += 1
                if bool(summary.get("strict_incubation_ready")):
                    strict_incubation_ready_count += 1
                if bool(summary.get("factor_performance_reported")):
                    factor_performance_reported_count += 1
                submitted_items.append(summary)

            gate_report = build_completed_gate_3_report(
                {
                    "gate_3_input": gate_3_input,
                    "submitted": submitted,
                    "gate_3_passed": gate_3_passed,
                    "gate_3_failed": gate_3_failed,
                    "gate_3_provisional_passed": gate_3_provisional_passed,
                    "gate_3_failure_reason_topn": [
                        {"reason_code": reason_code, "count": count}
                        for reason_code, count in gate_3_failure_codes.most_common(5)
                    ],
                    "formal_incubation_count": int(submission_lane_counts.get("formal_incubation") or 0),
                    "observe_incubation_count": int(submission_lane_counts.get("observe_incubation") or 0),
                    "live_ready_review_count": int(submission_lane_counts.get("live_ready_review") or 0),
                    "deferred_submission_count": int(submission_lane_counts.get("deferred_submission") or 0),
                    "research_only_count": int(submission_action_type_counts.get("research_only") or 0),
                    "strict_incubation_ready_count": strict_incubation_ready_count,
                }
            )

            # PR-S3: 排空持久化 DLQ，附在 submit_result 中供 cycle runner 摘要暴露
            persistence_dlq = []
            drain = getattr(self, "drain_persistence_dlq", None)
            if callable(drain):
                persistence_dlq = drain()
            return {
                "created": created,
                "created_total": created_total,
                "created_strategy_pool": created_strategy_pool,
                "created_audit_only": created_audit_only,
                "refreshed": refreshed,
                "gate_3_input": gate_3_input,
                "submitted": submitted,
                "passed_quality_gate": passed,
                "gate_3_passed": gate_3_passed,
                "gate_3_failed": gate_3_failed,
                "gate_3_provisional_passed": gate_3_provisional_passed,
                "gate_3_failure_reason_topn": gate_report["gate_3"]["failure_reason_topn"],
                "formal_incubation_count": int(submission_lane_counts.get("formal_incubation") or 0),
                "observe_incubation_count": int(submission_lane_counts.get("observe_incubation") or 0),
                "live_ready_review_count": int(submission_lane_counts.get("live_ready_review") or 0),
                "deferred_submission_count": int(submission_lane_counts.get("deferred_submission") or 0),
                "research_only_count": int(submission_action_type_counts.get("research_only") or 0),
                "strict_incubation_ready_count": strict_incubation_ready_count,
                "factor_performance_reported_count": factor_performance_reported_count,
                "quality_gate": gate_report,
                "gate_report": gate_report,
                "incubation_budget_summary": incubation_budget_summary,
                "admission_decision_counts": dict(admission_decision_counts),
                "strategies": submitted_items,
                "persistence_dlq_count": len(persistence_dlq),
                "persistence_dlq": persistence_dlq,
            }
