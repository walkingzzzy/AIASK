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
            self._diagnostic_observation_lock = asyncio.Lock()
            self._diagnostic_observation_claimed = 0
            self._diagnostic_observation_limit = _diagnostic_observation_batch_limit()
            self._diagnostic_observation_fingerprints = set()
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
                    "diagnostic_observation_count": int(submission_lane_counts.get("diagnostic_observation") or 0),
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
                "diagnostic_observation_count": int(submission_lane_counts.get("diagnostic_observation") or 0),
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

        async def _claim_diagnostic_observation_slot(self, *, fingerprint: str | None = None) -> bool:
            if not _diagnostic_observation_enabled():
                return False
            lock = getattr(self, "_diagnostic_observation_lock", None)
            if lock is None:
                lock = asyncio.Lock()
                self._diagnostic_observation_lock = lock
            async with lock:
                limit = int(
                    getattr(
                        self,
                        "_diagnostic_observation_limit",
                        _diagnostic_observation_batch_limit(),
                    )
                    or 0
                )
                token = str(fingerprint or "").strip()
                claimed_fingerprints = getattr(self, "_diagnostic_observation_fingerprints", None)
                if claimed_fingerprints is None:
                    claimed_fingerprints = set()
                    self._diagnostic_observation_fingerprints = claimed_fingerprints
                if token and token in claimed_fingerprints:
                    return False
                claimed = int(getattr(self, "_diagnostic_observation_claimed", 0) or 0)
                if claimed >= max(1, limit):
                    return False
                if token:
                    claimed_fingerprints.add(token)
                self._diagnostic_observation_claimed = claimed + 1
                return True

        async def _diagnostic_observation_admission_guard(
            self,
            db,
            *,
            candidate: dict,
            reason: str,
            fingerprint: str,
        ) -> dict[str, Any]:
            guard = {
                "allowed": True,
                "reason": "accepted",
                "diagnostic_reason": str(reason or "diagnostic_observation"),
                "diagnostic_fingerprint": str(fingerprint or ""),
                "health_guard_enabled": _diagnostic_observation_health_guard_enabled(),
                "dedupe_enabled": _diagnostic_observation_dedupe_enabled(),
                "ttl_days": _diagnostic_observation_ttl_days(),
            }

            if _diagnostic_observation_health_guard_enabled():
                max_age_hours = _diagnostic_observation_health_max_age_hours()
                guard["health_max_age_hours"] = max_age_hours
                health = await self._call_optional_db_method(
                    db,
                    "get_incubation_factory_health",
                    max_age_hours=max_age_hours,
                )
                if isinstance(health, dict):
                    guard["incubation_factory_health"] = dict(health)
                    if not bool(health.get("healthy")):
                        guard["allowed"] = False
                        guard["reason"] = "incubation_factory_stale"
                        return guard
                else:
                    guard["incubation_factory_health"] = {
                        "supported": False,
                        "healthy": True,
                    }

            if _diagnostic_observation_dedupe_enabled() and fingerprint:
                existing = await self._call_optional_db_method(
                    db,
                    "find_active_diagnostic_observation_by_fingerprint",
                    str(fingerprint),
                    ttl_days=_diagnostic_observation_ttl_days(),
                )
                if existing:
                    payload = dict(existing or {})
                    guard["allowed"] = False
                    guard["reason"] = "diagnostic_fingerprint_duplicate"
                    guard["existing_strategy_id"] = payload.get("id") or payload.get("strategy_id")
                    guard["existing_account_id"] = payload.get("diagnostic_account_id") or payload.get("account_id")
                    return guard

            return guard
