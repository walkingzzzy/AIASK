
        @classmethod
        def _resolve_effective_research_task_timeout_sec(
            cls,
            autonomy_gateway,
            task: dict[str, Any] | None,
            *,
            base_timeout: float,
            local_fallback: bool = False,
        ) -> float:
            effective_base_timeout = float(base_timeout or 0.0)
            if cls._research_task_uses_bulk_timeout(task):
                effective_base_timeout = max(
                    effective_base_timeout,
                    cls._resolve_bulk_research_task_timeout_sec(),
                )
            if not cls._research_task_uses_external_llm(autonomy_gateway, task):
                if local_fallback:
                    return min(
                        effective_base_timeout,
                        cls._resolve_local_fallback_research_task_timeout_cap_sec(),
                    )
                return effective_base_timeout

            external_cap = cls._resolve_external_research_task_timeout_cap_sec()
            if cls._research_task_uses_bulk_timeout(task):
                external_cap = max(external_cap, cls._resolve_bulk_research_task_timeout_sec())
            external_timeout = min(effective_base_timeout, external_cap)
            if not local_fallback:
                return external_timeout
            return min(
                external_timeout,
                cls._resolve_local_fallback_research_task_timeout_cap_sec(),
            )

        @staticmethod
        def _control_mode_from_severity(severity: int) -> str:
            normalized = max(0, int(severity or 0))
            if normalized >= 3:
                return "freeze"
            if normalized >= 2:
                return "suppress"
            if normalized >= 1:
                return "cooldown"
            return "normal"

        async def _load_recent_factory_run_summaries(
            self,
            db,
            *,
            limit: int = 4,
        ) -> list[dict[str, Any]]:
            summaries: list[dict[str, Any]] = []
            seen: set[str] = set()

            def _append(entry: Optional[dict[str, Any]]) -> None:
                payload = dict(entry or {})
                summary = dict(payload.get("summary") or {})
                if not summary:
                    return
                run_id = str(payload.get("run_id") or summary.get("run_id") or "").strip()
                marker = run_id or str(summary.get("trace_id") or summary.get("completed_at") or len(summaries))
                if marker in seen:
                    return
                seen.add(marker)
                summaries.append(summary)

            _append(dict(self.last_result or {}))
            fetch_limit = max(1, int(limit or 1))
            if hasattr(db, "list_strategy_factory_runs"):
                try:
                    rows = await _call_optional_async(
                        db,
                        "list_strategy_factory_runs",
                        fetch_limit,
                        default=[],
                    )
                except Exception:
                    rows = []
                for row in list(rows or []):
                    _append(dict(row or {}))
                    if len(summaries) >= fetch_limit:
                        break
            elif hasattr(db, "get_latest_strategy_factory_run"):
                try:
                    latest = await _call_optional_async(db, "get_latest_strategy_factory_run", default=None)
                except Exception:
                    latest = None
                _append(dict(latest or {}))
            return summaries[:fetch_limit]

        @classmethod
        def _build_external_provider_control(
            cls,
            recent_summaries: list[dict[str, Any]],
            provider_health: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            summaries = [dict(item or {}) for item in list(recent_summaries or []) if isinstance(item, dict)]
            health = dict(provider_health or {})
            active_attempt_run_count = 0
            zero_attempt_run_streak = 0
            zero_attempt_streak_open = True
            for item in summaries:
                attempt_count = int(
                    item.get("external_llm_stage_attempt_count") or item.get("external_llm_attempt_count") or 0
                )
                real_request_count = int(item.get("external_llm_real_request_count") or 0)
                if attempt_count > 0 or real_request_count > 0:
                    active_attempt_run_count += 1
                    zero_attempt_streak_open = False
                    continue
                if zero_attempt_streak_open:
                    zero_attempt_run_streak += 1
            stage_attempt_count = sum(
                int(item.get("external_llm_stage_attempt_count") or item.get("external_llm_attempt_count") or 0)
                for item in summaries
            )
            real_request_count = sum(int(item.get("external_llm_real_request_count") or 0) for item in summaries)
            compatibility_skip_count = sum(int(item.get("external_llm_compatibility_skip_count") or 0) for item in summaries)
            compatibility_failure_count = sum(
                int(item.get("external_llm_compatibility_failure_count") or 0) for item in summaries
            )
            effective_response_count = sum(
                int(item.get("external_llm_effective_response_count") or 0) for item in summaries
            )
            empty_200_response_count = sum(
                int(item.get("external_llm_empty_200_response_count") or 0) for item in summaries
            )
            compatibility_skip_ratio = (
                round(compatibility_skip_count / stage_attempt_count, 4) if stage_attempt_count else 0.0
            )
            compatibility_failure_ratio = (
                round(compatibility_failure_count / real_request_count, 4) if real_request_count else 0.0
            )
            effective_response_ratio = (
                round(effective_response_count / real_request_count, 4) if real_request_count else 0.0
            )
            empty_200_response_ratio = (
                round(empty_200_response_count / real_request_count, 4) if real_request_count else 0.0
            )

            severity = 0
            reasons: list[str] = []
            health_status = _normalize_feedback_text(health.get("health_status"))
            if bool(health.get("scheduler_should_disable")) or health_status in {"failed", "error"}:
                severity = max(severity, 2)
                reasons.append(
                    str(health.get("scheduler_skip_reason") or health_status or "provider_health_blocked")
                )
            elif health_status in {"degraded", "warning"} or bool(health.get("compatibility_cooldown_active")):
                severity = max(severity, 1)
                reasons.append("provider_health_degraded")

            suppress_recovery_probe_recommended = False
            suppress_recovery_probe_reason = None
            if stage_attempt_count >= 3 and compatibility_skip_ratio >= 0.75:
                skip_severity = 2
                if (
                    real_request_count <= 0
                    and compatibility_failure_count <= 0
                    and active_attempt_run_count <= 1
                    and zero_attempt_run_streak >= 1
                    and not bool(health.get("scheduler_should_disable"))
                ):
                    skip_severity = 1
                    suppress_recovery_probe_recommended = True
                    suppress_recovery_probe_reason = "skip_only_history_without_recent_probe"
                severity = max(severity, skip_severity)
                reasons.append("compatibility_skip_ratio_too_high")
            elif stage_attempt_count >= 2 and compatibility_skip_ratio >= 0.4:
                severity = max(severity, 1)
                reasons.append("compatibility_skip_ratio_elevated")

            if real_request_count >= 2 and (
                effective_response_ratio <= 0.15
                or compatibility_failure_ratio >= 0.65
                or empty_200_response_ratio >= 0.5
            ):
                severity = max(severity, 2)
                reasons.append("effective_response_ratio_too_low")
            elif real_request_count >= 2 and (
                effective_response_ratio < 0.45
                or compatibility_failure_ratio >= 0.35
                or empty_200_response_ratio >= 0.25
            ):
                severity = max(severity, 1)
                reasons.append("effective_response_ratio_degraded")

            deduped_reasons: list[str] = []
            for reason in reasons:
                token = str(reason or "").strip()
                if token and token not in deduped_reasons:
                    deduped_reasons.append(token)

            control_mode = cls._control_mode_from_severity(severity)
            return {
                "control_mode": control_mode,
                "control_reasons": deduped_reasons,
                "health_status": health_status or None,
                "stage_attempt_count": stage_attempt_count,
                "real_request_count": real_request_count,
                "compatibility_skip_count": compatibility_skip_count,
                "compatibility_skip_ratio": compatibility_skip_ratio,
                "compatibility_failure_count": compatibility_failure_count,
                "compatibility_failure_ratio": compatibility_failure_ratio,
                "effective_response_count": effective_response_count,
                "effective_response_ratio": effective_response_ratio,
                "empty_200_response_count": empty_200_response_count,
                "empty_200_response_ratio": empty_200_response_ratio,
                "active_attempt_run_count": active_attempt_run_count,
                "zero_attempt_run_streak": zero_attempt_run_streak,
                "suppress_recovery_probe_recommended": suppress_recovery_probe_recommended,
                "suppress_recovery_probe_reason": suppress_recovery_probe_reason,
                "scheduler_should_disable": bool(health.get("scheduler_should_disable")),
                "scheduler_skip_reason": health.get("scheduler_skip_reason"),
            }

        @classmethod
        def _build_generator_mode_controls(
            cls,
            recent_summaries: list[dict[str, Any]],
            *,
            feedback_root: Any = None,
        ) -> dict[str, dict[str, Any]]:
            history_by_mode: dict[str, list[dict[str, Any]]] = {}
            for item in list(recent_summaries or []):
                summary = dict(item or {})
                mode_metrics = dict(summary.get("generator_mode_submission_metrics") or {})
                for mode_name, raw_metrics in mode_metrics.items():
                    normalized_mode = _normalize_feedback_text(mode_name)
                    if not normalized_mode:
                        continue
                    history_by_mode.setdefault(normalized_mode, []).append(dict(raw_metrics or {}))

            controls: dict[str, dict[str, Any]] = {}
            for mode_name in ("external_llm", "pipeline_staged", "rl_bandit"):
                history = history_by_mode.get(mode_name) or []
                stagnant_runs = 0
                last_metrics: dict[str, Any] = {}
                for metrics in history:
                    last_metrics = dict(metrics or {})
                    strategy_count = int(last_metrics.get("strategy_count") or 0)
                    if strategy_count <= 0:
                        break
                    created_total_count = int(last_metrics.get("created_total_count") or 0)
                    refresh_absorption_ratio = float(last_metrics.get("refresh_absorption_ratio") or 0.0)
                    tested_object_hash_changed_count = int(
                        last_metrics.get("tested_object_hash_changed_count") or 0
                    )
                    if (
                        created_total_count == 0
                        and refresh_absorption_ratio >= 0.6
                        and tested_object_hash_changed_count <= 0
                    ):
                        stagnant_runs += 1
                        continue
                    break
                if stagnant_runs <= 0:
                    continue
                severity = 2 if stagnant_runs >= 3 else 1
                controls[mode_name] = {
                    "control_mode": cls._control_mode_from_severity(severity),
                    "stagnant_runs": stagnant_runs,
                    "control_reasons": ["refresh_absorption_without_creation"],
                    "metrics": last_metrics,
                }
            feedback_controls = collect_generator_mode_feedback_controls(feedback_root)
            for mode_name, incoming_control in feedback_controls.items():
                normalized_mode = _normalize_feedback_text(mode_name)
                if not normalized_mode:
                    continue
                existing = dict(controls.get(normalized_mode) or {})
                existing_mode = _normalize_feedback_text(existing.get("control_mode")) or "normal"
                incoming_mode = _normalize_feedback_text(incoming_control.get("control_mode")) or "normal"
                existing_severity = CONTROL_MODE_SEVERITY.get(existing_mode, 0)
                incoming_severity = CONTROL_MODE_SEVERITY.get(incoming_mode, 0)
                merged_reasons: list[str] = []
                for reason in [
                    *list(existing.get("control_reasons") or []),
                    *list(incoming_control.get("control_reasons") or []),
                ]:
                    token = str(reason or "").strip()
                    if token and token not in merged_reasons:
                        merged_reasons.append(token)
                merged_sources: list[str] = []
                for source in [existing.get("source"), incoming_control.get("source")]:
                    token = str(source or "").strip()
                    if token and token not in merged_sources:
                        merged_sources.append(token)
                merged_families: list[str] = []
                for family in [
                    *list(existing.get("families") or []),
                    *list(incoming_control.get("families") or []),
                ]:
                    token = _normalize_feedback_text(family)
                    if token and token not in merged_families:
                        merged_families.append(token)
                winner = dict(existing or {})
                if incoming_severity >= existing_severity:
                    winner.update(dict(incoming_control or {}))
                winner["control_mode"] = (
                    incoming_mode if incoming_severity >= existing_severity else existing_mode
                ) or "normal"
                winner["control_reasons"] = merged_reasons
                winner["source"] = merged_sources[0] if len(merged_sources) == 1 else merged_sources
                winner["families"] = merged_families
                winner["feedback_observed_count"] = int(
                    incoming_control.get("feedback_observed_count")
                    or existing.get("feedback_observed_count")
                    or 0
                )
                controls[normalized_mode] = winner
            return controls

        @classmethod
        def _apply_scheduler_planning_controls(
            cls,
            tasks: list[dict[str, Any]],
            *,
            feedback_root: Any,
            provider_control: Optional[dict[str, Any]] = None,
            generator_mode_controls: Optional[dict[str, dict[str, Any]]] = None,
        ) -> list[dict[str, Any]]:
            return _apply_scheduler_planning_controls_payload(
                list(tasks or []),
                feedback_root=feedback_root,
                provider_control=provider_control or {},
                generator_mode_controls=generator_mode_controls or {},
            )

        @classmethod
        def _merge_autonomy_tasks_with_budget(
            cls,
            scanner,
            scan_tasks: list[dict[str, Any]],
            bulk_tasks: list[dict[str, Any]],
        ) -> tuple[list[dict[str, Any]], dict[str, int]]:
            return _merge_autonomy_tasks_with_budget_payload(
                scanner,
                scan_tasks,
                bulk_tasks,
            )
