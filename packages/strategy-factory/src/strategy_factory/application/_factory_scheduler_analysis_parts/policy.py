
        @staticmethod
        def _governance_status(*, critical: bool = False, warning: bool = False, available: bool = True) -> str:
            if not available:
                return "unavailable"
            if critical:
                return "critical"
            if warning:
                return "warning"
            return "healthy"

        @classmethod
        def _iso_week_label(cls, value: Any = None) -> str:
            resolved = None
            if isinstance(value, datetime):
                resolved = value
            elif value is not None:
                try:
                    resolved = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                except Exception:
                    resolved = None
            if resolved is None:
                resolved = datetime.now(_MARKET_TIMEZONE)
            if resolved.tzinfo is None:
                resolved = resolved.replace(tzinfo=_MARKET_TIMEZONE)
            iso = resolved.isocalendar()
            return f"{iso.year}-W{iso.week:02d}"

        @staticmethod
        def _iter_strategy_records(results: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
            submit_stage = dict(((results or {}).get("stages") or {}).get("submit") or {})
            records = submit_stage.get("strategies")
            if isinstance(records, list):
                return [dict(item or {}) for item in records if isinstance(item, dict)]
            return []

        @staticmethod
        def _iter_backtest_records(results: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
            backtest_stage = dict(((results or {}).get("stages") or {}).get("backtest") or {})
            records: list[dict[str, Any]] = []
            for bucket_name in ("passed", "failed"):
                for item in list(backtest_stage.get(bucket_name) or []):
                    if isinstance(item, dict):
                        records.append(dict(item or {}))
            if records:
                return records
            gate_report = dict((results or {}).get("quality_gate") or (results or {}).get("gate_report") or {})
            gate_2 = dict(gate_report.get("gate_2") or {})
            for bucket_name in ("passed", "failed"):
                for item in list(gate_2.get(bucket_name) or []):
                    if isinstance(item, dict):
                        records.append(dict(item or {}))
            return records

        @classmethod
        def _summarize_refresh_result(cls, payload: Any) -> dict[str, Any]:
            if not isinstance(payload, dict):
                return {"result_type": type(payload).__name__}
            summary: dict[str, Any] = {}
            for key in ("computed", "errors", "elapsed_seconds", "universe_size", "source", "asof_time"):
                if payload.get(key) is not None:
                    summary[key] = payload.get(key)
            flags = list(payload.get("quality_flags") or [])
            if flags:
                summary["quality_flags"] = flags
            return summary

        @classmethod
        def _build_scheduler_slo_summary(
            cls,
            results: dict[str, Any],
            current_summary: Optional[dict[str, Any]],
            previous_summary: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            summary = dict(current_summary or {})
            previous = dict(previous_summary or {})
            alerts: list[dict[str, Any]] = []

            def _append_alert(code: str, severity: str, message: str, **payload: Any) -> None:
                alerts.append(
                    {
                        "code": str(code),
                        "severity": str(severity),
                        "message": str(message),
                        **payload,
                    }
                )

            factor_source_mode = cls._normalize_text(summary.get("factor_source_mode"))
            staleness_days = summary.get("governed_freshness_days")
            if staleness_days is None or factor_source_mode != "governed_candidate_pool":
                staleness_days = summary.get("factor_research_freshness_days")
            staleness_days = cls._safe_float(staleness_days)
            staleness_status = cls._governance_status(
                critical=bool(summary.get("factor_research_stale")) and staleness_days >= 5.0,
                warning=bool(summary.get("factor_research_stale")) or staleness_days >= 2.0,
            )
            if staleness_status != "healthy":
                _append_alert(
                    "scheduler_staleness_high",
                    "critical" if staleness_status == "critical" else "warning",
                    "Factor research freshness drifted beyond the scheduler SLO.",
                    staleness_days=round(staleness_days, 4),
                    factor_source_mode=factor_source_mode or None,
                )

            autonomy_stage = dict((results.get("stages") or {}).get("autonomy") or {})
            autonomy_status_counts = {
                str(key): cls._safe_int(value)
                for key, value in dict(autonomy_stage.get("external_llm_status_counts") or {}).items()
            }
            fallback_components: dict[str, float] = {
                "factor_source_mode": 1.0 if factor_source_mode == "seed_fallback" else 0.0,
            }
            autonomy_total = sum(autonomy_status_counts.values())
            if autonomy_total > 0:
                fallback_components["autonomy_external_llm"] = cls._safe_ratio(
                    autonomy_status_counts.get("fallback_only", 0),
                    autonomy_total,
                )
            bulk_fallback_signals = [
                1.0 if summary.get("bulk_stock_matrix_universe_offset_fallback") else 0.0,
                1.0 if summary.get("bulk_stock_matrix_task_offset_fallback") else 0.0,
            ]
            if bulk_fallback_signals:
                fallback_components["bulk_cursor"] = round(
                    sum(bulk_fallback_signals) / len(bulk_fallback_signals),
                    4,
                )
            fallback_ratio = round(
                sum(fallback_components.values()) / max(len(fallback_components), 1),
                4,
            )
            fallback_status = cls._governance_status(
                critical=fallback_ratio >= 0.65,
                warning=fallback_ratio >= 0.25,
            )
            if fallback_status != "healthy":
                _append_alert(
                    "scheduler_fallback_ratio_high",
                    "critical" if fallback_status == "critical" else "warning",
                    "Fallback paths are carrying too much of the scheduler pipeline.",
                    ratio=fallback_ratio,
                    components=fallback_components,
                )

            def _gate_rates(payload: dict[str, Any]) -> dict[str, float]:
                return {
                    "gate_0": cls._safe_ratio(payload.get("gate_0_passed"), payload.get("candidates_spawned")),
                    "pre_gate": cls._safe_ratio(payload.get("pre_gate_passed"), payload.get("gate_0_passed")),
                    "gate_1": cls._safe_ratio(payload.get("gate_1_passed"), payload.get("pre_gate_passed")),
                    "gate_2": cls._safe_ratio(payload.get("gate_2_passed"), payload.get("gate_2_input")),
                    "gate_3": cls._safe_ratio(payload.get("gate_3_passed"), payload.get("gate_3_input")),
                }

            current_gate_rates = _gate_rates(summary)
            previous_gate_rates = _gate_rates(previous) if previous else {}
            gate_rate_deltas = {
                key: round(current_gate_rates.get(key, 0.0) - previous_gate_rates.get(key, 0.0), 4)
                for key in current_gate_rates
                if previous_gate_rates
            }
            gate_drift_value = (
                round(max(abs(delta) for delta in gate_rate_deltas.values()), 4)
                if gate_rate_deltas
                else 0.0
            )
            gate_drift_status = cls._governance_status(
                critical=gate_drift_value >= 0.3,
                warning=gate_drift_value >= 0.12,
            )
            if gate_drift_status != "healthy":
                _append_alert(
                    "scheduler_gate_drift_high",
                    "critical" if gate_drift_status == "critical" else "warning",
                    "Gate conversion rates drifted sharply versus the previous run.",
                    value=gate_drift_value,
                    deltas=gate_rate_deltas,
                )

            current_refresh_ratio = cls._safe_float(
                dict(summary.get("incubation_summary") or {}).get("refresh_ratio", {}).get("ratio")
            )
            if current_refresh_ratio <= 0.0:
                current_refresh_ratio = cls._safe_ratio(
                    summary.get("refresh_metrics_only_count"),
                    summary.get("candidates_after_dedup"),
                )
            previous_refresh_ratio = cls._safe_float(
                dict(previous.get("incubation_summary") or {}).get("refresh_ratio", {}).get("ratio")
            )
            if previous_refresh_ratio <= 0.0:
                previous_refresh_ratio = cls._safe_ratio(
                    previous.get("refresh_metrics_only_count"),
                    previous.get("candidates_after_dedup"),
                )
            refresh_failed = bool(summary.get("factor_research_refresh_attempted")) and cls._normalize_text(
                summary.get("factor_research_refresh_status")
            ) not in {"success", "succeeded", "completed"}
            refresh_drift_value = abs(current_refresh_ratio - previous_refresh_ratio) if previous else 0.0
            if refresh_failed:
                refresh_drift_value = max(refresh_drift_value, 0.45)
            refresh_drift_value = round(refresh_drift_value, 4)
            refresh_drift_status = cls._governance_status(
                critical=refresh_drift_value >= 0.35,
                warning=refresh_drift_value >= 0.1,
            )
            if refresh_drift_status != "healthy":
                _append_alert(
                    "scheduler_refresh_drift_high",
                    "critical" if refresh_drift_status == "critical" else "warning",
                    "Refresh behaviour drifted versus the previous run or the latest refresh failed.",
                    value=refresh_drift_value,
                    refresh_failed=refresh_failed,
                    current_ratio=current_refresh_ratio,
                    previous_ratio=previous_refresh_ratio,
                )

            planned_bulk = cls._safe_int(summary.get("planned_bulk_task_count"))
            selected_bulk = cls._safe_int(summary.get("selected_bulk_task_count"))
            configured_bulk_budget = max(
                cls._safe_int(summary.get("max_bulk_research_tasks")),
                cls._safe_int(summary.get("reserved_bulk_task_budget")),
            )
            selected_batch_count = cls._safe_int(summary.get("bulk_stock_matrix_selected_batch_count"))
            batch_count = cls._safe_int(summary.get("bulk_stock_matrix_batch_count"))
            budgeted_bulk_target = (
                min(planned_bulk, configured_bulk_budget)
                if planned_bulk > 0 and configured_bulk_budget > 0
                else planned_bulk
            )
            bulk_fill_ratio = cls._safe_ratio(selected_bulk, budgeted_bulk_target) if budgeted_bulk_target > 0 else 1.0
            planner_batch_coverage_ratio = cls._safe_ratio(selected_batch_count, batch_count) if batch_count > 0 else 1.0
            bulk_imbalance_value = round(
                max(0.0, 1.0 - bulk_fill_ratio),
                4,
            ) if budgeted_bulk_target > 0 else 0.0
            bulk_imbalance_status = cls._governance_status(
                critical=budgeted_bulk_target > 0 and bulk_fill_ratio < 0.35,
                warning=budgeted_bulk_target > 0 and bulk_fill_ratio < 0.8,
            )
            if bulk_imbalance_status != "healthy":
                _append_alert(
                    "bulk_queue_imbalance",
                    "critical" if bulk_imbalance_status == "critical" else "warning",
                    "Bulk stock matrix queue fill fell below the expected scheduler SLO.",
                    value=bulk_imbalance_value,
                    selected_bulk_task_count=selected_bulk,
                    planned_bulk_task_count=planned_bulk,
                    budgeted_bulk_task_target=budgeted_bulk_target,
                    selected_batch_count=selected_batch_count,
                    batch_count=batch_count,
                )

            warmup_status = cls._normalize_text(summary.get("warmup_status"))
            warmup_failed = cls._safe_int(summary.get("warmup_failed"))
            if warmup_status in {"failed", "partial"} or warmup_failed > 0:
                _append_alert(
                    "scheduler_warmup_failed",
                    "critical" if warmup_status == "failed" or warmup_failed > 0 else "warning",
                    "Warmup did not complete cleanly before the run started.",
                    warmup_status=warmup_status or None,
                    warmup_failed=warmup_failed,
                )

            provider_health_status = cls._normalize_text(summary.get("factor_llm_provider_health_status"))
            provider_enabled = bool(summary.get("factor_llm_provider_enabled"))
            provider_ready = bool(summary.get("factor_llm_provider_ready"))
            external_llm_status = cls._normalize_text(summary.get("external_llm_status"))
            provider_degraded = provider_health_status in {"degraded", "failed", "error"} or (
                provider_enabled and not provider_ready
            ) or external_llm_status in {"failed", "partial"}
            if provider_degraded:
                _append_alert(
                    "factor_provider_degraded",
                    "critical" if provider_health_status in {"failed", "error"} or external_llm_status == "failed" else "warning",
                    "Provider health degraded during the scheduler run.",
                    factor_llm_provider_health_status=provider_health_status or None,
                    factor_llm_provider_ready=provider_ready,
                    external_llm_status=external_llm_status or None,
                )

            governed_pool_active = bool(summary.get("governed_candidate_pool_active"))
            governed_blocked_ratio = cls._safe_float(summary.get("governed_blocked_ratio"))
            if not governed_pool_active or governed_blocked_ratio >= 0.5:
                _append_alert(
                    "governed_pool_blocked",
                    "critical" if (not governed_pool_active) or governed_blocked_ratio >= 0.75 else "warning",
                    "Governed candidate pool is unavailable or heavily blocked.",
                    governed_candidate_pool_active=governed_pool_active,
                    governed_blocked_ratio=round(governed_blocked_ratio, 4),
                    factor_source_mode=factor_source_mode or None,
                )
            governed_pending_ratio = cls._safe_float(summary.get("governed_pending_ratio"))
            if governed_pool_active and governed_pending_ratio >= 0.5:
                _append_alert(
                    "governed_pool_promotion_backlog",
                    "warning",
                    "A large share of candidates remain pending promotion into the governed active pool.",
                    governed_pending_ratio=round(governed_pending_ratio, 4),
                    governed_pending_candidate_count=cls._safe_int(
                        summary.get("governed_pending_candidate_count")
                    ),
                    governed_source_candidate_count=cls._safe_int(
                        summary.get("governed_source_candidate_count")
                    ),
                )

            overall_status = "healthy"
            if any(str(item.get("severity")) == "critical" for item in alerts):
                overall_status = "critical"
            elif alerts:
                overall_status = "warning"

            return {
                "status": overall_status,
                "alert_count": len(alerts),
                "alert_codes": [str(item.get("code")) for item in alerts],
                "alerts": alerts,
                "staleness": {
                    "status": staleness_status,
                    "days": round(staleness_days, 4),
                    "factor_source_mode": factor_source_mode or None,
                },
                "fallback_ratio": {
                    "status": fallback_status,
                    "ratio": fallback_ratio,
                    "components": fallback_components,
                },
                "gate_drift": {
                    "status": gate_drift_status,
                    "value": gate_drift_value,
                    "current_rates": current_gate_rates,
                    "previous_rates": previous_gate_rates,
                    "deltas": gate_rate_deltas,
                },
                "refresh_drift": {
                    "status": refresh_drift_status,
                    "value": refresh_drift_value,
                    "current_ratio": round(current_refresh_ratio, 4),
                    "previous_ratio": round(previous_refresh_ratio, 4),
                    "refresh_failed": refresh_failed,
                },
                "bulk_queue_imbalance": {
                    "status": bulk_imbalance_status,
                    "value": bulk_imbalance_value,
                    "bulk_fill_ratio": round(bulk_fill_ratio, 4),
                    "budgeted_bulk_task_target": budgeted_bulk_target,
                    "planner_batch_coverage_ratio": round(planner_batch_coverage_ratio, 4),
                    "selected_bulk_task_count": selected_bulk,
                    "planned_bulk_task_count": planned_bulk,
                    "selected_batch_count": selected_batch_count,
                    "batch_count": batch_count,
                },
                "governed_pool_promotion_backlog": {
                    "status": (
                        "warning"
                        if governed_pool_active and governed_pending_ratio >= 0.5
                        else "healthy"
                    ),
                    "governed_pending_ratio": round(governed_pending_ratio, 4),
                    "governed_pending_candidate_count": cls._safe_int(
                        summary.get("governed_pending_candidate_count")
                    ),
                    "governed_source_candidate_count": cls._safe_int(
                        summary.get("governed_source_candidate_count")
                    ),
                },
            }
