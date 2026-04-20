        def _build_event_task_evidence_items(task: dict) -> List[dict]:
            event_context = _extract_event_context(task)
            task_key = str((task or {}).get("task_key") or (task or {}).get("task_id") or "").strip()
            event_id = str(event_context.get("event_id") or "").strip()
            if not task_key or not event_id:
                return []

            evidence_bundle = dict((task or {}).get("evidence_bundle") or {})
            score_summary = dict(event_context.get("score_summary") or {})
            theme_code = str(event_context.get("theme_code") or "").strip()
            supporting_reasons = list(event_context.get("supporting_reasons") or [])
            target_symbols = list(event_context.get("target_symbols") or [])
            symbol_details = {
                str((item or {}).get("code") or (item or {}).get("symbol") or "").strip(): dict(item or {})
                for item in list(evidence_bundle.get("symbol_details") or [])
                if str((item or {}).get("code") or (item or {}).get("symbol") or "").strip()
            }
            summary_weight = float(score_summary.get("avg_final_score") or 0.0)
            items: List[dict] = [
                {
                    "task_key": task_key,
                    "event_id": event_id,
                    "theme_code": theme_code,
                    "symbol": None,
                    "evidence_type": "event_theme_context",
                    "weight": summary_weight,
                    "evidence_payload": {**event_context, "snapshot_date": (task or {}).get("snapshot_date")},
                }
            ]
            for reason in supporting_reasons[:4]:
                items.append({
                    "task_key": task_key,
                    "event_id": event_id,
                    "theme_code": theme_code,
                    "symbol": None,
                    "evidence_type": "supporting_reason",
                    "weight": summary_weight,
                    "evidence_payload": {
                        "reason": reason,
                        "event_id": event_id,
                        "theme_code": theme_code,
                        "direction": event_context.get("direction"),
                        "horizon": event_context.get("horizon"),
                    },
                })
            for rank, symbol in enumerate(target_symbols[:5], 1):
                detail = symbol_details.get(symbol) or {}
                items.append({
                    "task_key": task_key,
                    "event_id": event_id,
                    "theme_code": theme_code,
                    "symbol": symbol,
                    "evidence_type": "target_symbol",
                    "weight": round(max(summary_weight - (rank - 1) * 0.05, 0.0), 4),
                    "evidence_payload": {
                        "symbol": symbol,
                        "rank": rank,
                        "event_id": event_id,
                        "theme_code": theme_code,
                        "event_summary": event_context.get("event_summary"),
                        "direction": event_context.get("direction"),
                        "horizon": event_context.get("horizon"),
                        "score_summary": score_summary,
                        "symbol_detail": detail,
                    },
                })
            return items

        @staticmethod
        def _compact_task_mapping(
            payload: Optional[dict[str, Any]],
            *,
            keys: tuple[str, ...],
        ) -> dict[str, Any]:
            source = dict(payload or {})
            result: dict[str, Any] = {}
            for key in keys:
                value = source.get(key)
                if value in (None, "", [], {}):
                    continue
                result[key] = value
            return result

        @staticmethod
        def _build_task_scan_artifact(
            report: Optional[dict[str, Any]],
            *,
            task_source_counts: Optional[dict[str, Any]] = None,
            event_task_count: Optional[int] = None,
            snapshot_task_count: Optional[int] = None,
            bulk_stock_task_count: Optional[int] = None,
        ) -> dict[str, Any]:
            payload = dict(report or {})
            summary = dict(payload.get("summary") or {})
            source_counts = dict(task_source_counts or summary.get("task_sources") or {})
            resolved_event_task_count = (
                int(event_task_count)
                if event_task_count is not None
                else int(summary.get("event_task_count") or 0)
            )
            resolved_snapshot_task_count = (
                int(snapshot_task_count)
                if snapshot_task_count is not None
                else int(source_counts.get("snapshot") or 0)
            )
            resolved_bulk_stock_task_count = (
                int(bulk_stock_task_count)
                if bulk_stock_task_count is not None
                else int(summary.get("bulk_stock_task_count") or source_counts.get("bulk_stock_matrix") or 0)
            )
            return build_task_artifact(
                {
                    "task_scan": payload,
                    "task_source_counts": source_counts,
                    "event_task_count": resolved_event_task_count,
                    "snapshot_task_count": resolved_snapshot_task_count,
                    "bulk_stock_task_count": resolved_bulk_stock_task_count,
                }
            )

        @staticmethod
        def _normalize_external_request_status(status: Any) -> str:
            return str(status or "").strip().lower() or "unknown"

        @classmethod
        def _summarize_external_request_status_counts(
            cls,
            requests: Optional[list[dict[str, Any]]],
        ) -> dict[str, int]:
            counts: dict[str, int] = {}
            for item in list(requests or []):
                status = cls._normalize_external_request_status(dict(item or {}).get("status"))
                counts[status] = counts.get(status, 0) + 1
            return counts

        @classmethod
        def _count_external_network_requests(
            cls,
            requests: Optional[list[dict[str, Any]]],
        ) -> int:
            total = 0
            for item in list(requests or []):
                payload = dict(item or {})
                status = cls._normalize_external_request_status(payload.get("status"))
                if status in {"compatibility_skip", "cooldown_skip"}:
                    continue
                metrics = dict(payload.get("request_metrics") or {})
                try:
                    attempt_count = int(metrics.get("attempt_count") or 0)
                except Exception:
                    attempt_count = 0
                total += max(attempt_count, 1)
            return total

        @classmethod
        def _count_external_real_requests(
            cls,
            requests: Optional[list[dict[str, Any]]],
        ) -> int:
            total = 0
            for item in list(requests or []):
                status = cls._normalize_external_request_status(dict(item or {}).get("status"))
                if status in {"compatibility_skip", "cooldown_skip"}:
                    continue
                total += 1
            return total

        @classmethod
        def _request_is_compatibility_failure(
            cls,
            request: Optional[dict[str, Any]],
        ) -> bool:
            payload = dict(request or {})
            status = cls._normalize_external_request_status(payload.get("status"))
            if status in {"compatibility_skip", "cooldown_skip"}:
                return False
            metrics = dict(payload.get("request_metrics") or {})
            metric_status = cls._normalize_external_request_status(metrics.get("status"))
            error_type = str(payload.get("error_type") or metrics.get("last_error_type") or "").strip().lower()
            error_text = str(payload.get("error") or metrics.get("last_error") or "").strip().lower()
            return (
                metric_status == "compatibility_failed"
                or error_type == "providercompatibilityerror"
                or "missing extractable content" in error_text
            )

        @classmethod
        def _request_is_empty_200_response(
            cls,
            request: Optional[dict[str, Any]],
        ) -> bool:
            payload = dict(request or {})
            metrics = dict(payload.get("request_metrics") or {})
            if bool(metrics.get("empty_200_response")):
                return True
            if not cls._request_is_compatibility_failure(payload):
                return False
            error_text = str(payload.get("error") or metrics.get("last_error") or "").strip().lower()
            return "missing extractable content" in error_text

        @classmethod
        def _summarize_task_llm_generation(cls, llm_generation: Optional[dict[str, Any]]) -> dict[str, Any]:
            payload = dict(llm_generation or {})
            external = dict(payload.get("external_provider") or {})
            requests = list(external.get("requests") or [])
            external_summary = cls._compact_task_mapping(
                external,
                keys=(
                    "enabled",
                    "provider",
                    "model",
                    "status",
                    "selected_count",
                    "viable_selected_count",
                    "fallback_count",
                    "elapsed_seconds",
                    "last_error_type",
                    "last_error",
                    "stage_attempt_count",
                    "network_request_count",
                    "real_request_count",
                    "compatibility_skip_count",
                    "cooldown_skip_count",
                    "compatibility_failure_count",
                    "compatibility_failure_ratio",
                    "effective_response_count",
                    "effective_response_ratio",
                    "empty_200_response_count",
                ),
            )
            request_status_counts = dict(external.get("request_status_counts") or {}) or cls._summarize_external_request_status_counts(requests)
            if requests:
                real_request_count = int(external.get("real_request_count") or cls._count_external_real_requests(requests))
                compatibility_failure_count = int(
                    external.get("compatibility_failure_count")
                    or sum(1 for item in requests if cls._request_is_compatibility_failure(item))
                )
                effective_response_count = int(
                    external.get("effective_response_count")
                    or sum(
                        1
                        for item in requests
                        if cls._normalize_external_request_status(dict(item or {}).get("status")) == "succeeded"
                    )
                )
                empty_200_response_count = int(
                    external.get("empty_200_response_count")
                    or sum(1 for item in requests if cls._request_is_empty_200_response(item))
                )
                external_summary["request_count"] = len(requests)
                external_summary["stage_attempt_count"] = int(external.get("stage_attempt_count") or len(requests))
                external_summary["network_request_count"] = int(
                    external.get("network_request_count") or cls._count_external_network_requests(requests)
                )
                external_summary["real_request_count"] = real_request_count
                external_summary["compatibility_skip_count"] = int(
                    external.get("compatibility_skip_count")
                    or request_status_counts.get("compatibility_skip", 0)
                )
                external_summary["cooldown_skip_count"] = int(
                    external.get("cooldown_skip_count")
                    or request_status_counts.get("cooldown_skip", 0)
                )
                external_summary["compatibility_failure_count"] = compatibility_failure_count
                external_summary["effective_response_count"] = effective_response_count
                external_summary["empty_200_response_count"] = empty_200_response_count
                external_summary["compatibility_failure_ratio"] = (
                    external.get("compatibility_failure_ratio")
                    if external.get("compatibility_failure_ratio") is not None
                    else (round(compatibility_failure_count / real_request_count, 4) if real_request_count else 0.0)
                )
                external_summary["effective_response_ratio"] = (
                    external.get("effective_response_ratio")
                    if external.get("effective_response_ratio") is not None
                    else (round(effective_response_count / real_request_count, 4) if real_request_count else 0.0)
                )
            elif request_status_counts:
                external_summary["request_count"] = int(external.get("stage_attempt_count") or 0)
            if external.get("request_limits"):
                external_summary["request_limits"] = list(external.get("request_limits") or [])[:4]
            if request_status_counts:
                external_summary["request_status_counts"] = request_status_counts
            if requests:
                external_summary["requests_preview"] = [
                    {
                        **cls._compact_task_mapping(
                            dict(item or {}),
                            keys=(
                                "request_index",
                                "request_limit",
                                "status",
                                "returned_candidate_count",
                                "compiled_candidate_count",
                                "non_executable_candidate_count",
                                "viable_candidate_count",
                                "open_dsl_candidate_count",
                                "open_dsl_compiled_candidate_count",
                                "open_dsl_viable_candidate_count",
                                "open_dsl_rejected_count",
                                "error_type",
                                "error",
                            ),
                        ),
                        "request_metrics": cls._compact_task_mapping(
                            dict((item or {}).get("request_metrics") or {}),
                            keys=(
                                "attempt_count",
                                "prompt_chars",
                                "response_chars",
                                "elapsed_seconds",
                                "last_error_type",
                                "last_error",
                            ),
                        ),
                    }
                    for item in requests[:3]
                ]
            analysis = dict(external.get("analysis") or {})
            if analysis:
                external_summary["analysis"] = cls._compact_task_mapping(
                    analysis,
                    keys=(
                        "style_bias",
                        "market_regime",
                        "theme",
                        "direction",
                        "risk_hint",
                        "confidence",
                    ),
                )
            summary = cls._compact_task_mapping(
                payload,
                keys=(
                    "requested_limit",
                    "market_frame_ready",
                    "market_frame_rows",
                    "market_frame_source",
                    "selected_count",
                    "pipeline_run_timeout_sec",
                ),
            )
            if payload.get("selected_generators"):
                summary["selected_generators"] = dict(payload.get("selected_generators") or {})
            if payload.get("research_context_summary"):
                summary["research_context_summary"] = dict(payload.get("research_context_summary") or {})
            if external_summary:
                summary["external_provider"] = external_summary
            return {key: value for key, value in summary.items() if value not in (None, "", [], {})}

        @classmethod
        def _summarize_research_task_for_task_run(cls, task: Optional[dict[str, Any]]) -> dict[str, Any]:
            payload = _normalize_research_task_contract(task or {}) if task else {}
            summary = cls._compact_task_mapping(
                payload,
                keys=(
                    "task_id",
                    "task_key",
                    "task_source",
                    "opportunity_type",
                    "theme_code",
                    "event_id",
                    "candidate_family",
                    "factor_name",
                    "generation_limit",
                    "source_candidate_artifact_id",
                    "task_run_id",
                    "evidence_count",
                    "preference_strength",
                    "validation_focus",
                ),
            )
            target_symbols = list(payload.get("target_symbols") or [])
            if target_symbols:
                summary["target_symbols"] = target_symbols[:12]
            preferred_strategy_types = [
                str(item).strip()
                for item in list(
                    payload.get("preferred_strategy_types")
                    or payload.get("strategy_preferences")
                    or []
                )
                if str(item).strip()
            ]
            if preferred_strategy_types:
                summary["preferred_strategy_types"] = preferred_strategy_types[:6]
                summary["strategy_preferences"] = preferred_strategy_types[:6]
            allowed_strategy_types = [
                str(item).strip()
                for item in list(payload.get("allowed_strategy_types") or [])
                if str(item).strip()
            ]
            if allowed_strategy_types:
                summary["allowed_strategy_types"] = allowed_strategy_types[:6]
            evidence_refs = list(payload.get("evidence_refs") or [])
            if evidence_refs:
                summary["evidence_preview"] = [
                    cls._compact_task_mapping(
                        dict(item or {}),
                        keys=("id", "evidence_type", "symbol", "weight"),
                    )
                    for item in evidence_refs[:3]
                ]
            return summary

        @classmethod
        def _build_research_task_run_result_summary(cls, task_result: Optional[dict[str, Any]]) -> dict[str, Any]:
            payload = dict(task_result or {})
            summary = {
                "storage_mode": "summary_only",
                "task": cls._summarize_research_task_for_task_run(payload.get("task")),
                "task_run_id": payload.get("task_run_id"),
                "task_source": payload.get("task_source"),
                "event_id": payload.get("event_id"),
                "theme_code": payload.get("theme_code"),
                "evidence_count": int(payload.get("evidence_count") or 0),
                "status": payload.get("status"),
                "generated_count": int(payload.get("generated_count") or 0),
                "reviewed_count": int(payload.get("reviewed_count") or 0),
                "external_llm_status": payload.get("external_llm_status"),
                "llm_generation": cls._summarize_task_llm_generation(payload.get("llm_generation")),
                "lifecycle": dict(payload.get("lifecycle") or {}),
                "lifecycle_summary": dict(payload.get("lifecycle_summary") or {}),
            }
            if payload.get("error") not in (None, ""):
                summary["error"] = payload.get("error")
            return {key: value for key, value in summary.items() if value not in (None, "", [], {})}

        async def _persist_task_evidence(self, db, task: dict) -> List[dict]:
            saved_rows: List[dict] = []
            seen: set[tuple[str, str, str]] = set()
            for item in self._build_event_task_evidence_items(task):
                dedupe_key = (
                    str(item.get("task_key") or ""),
                    str(item.get("evidence_type") or ""),
                    str(item.get("symbol") or ""),
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                row = await _call_optional_async(db, "save_factory_task_evidence", item, default=None)
                if row is not None:
                    saved_rows.append(dict(row))
            return saved_rows

        @staticmethod
        def _is_market_hours(now: datetime) -> bool:
            """判断是否为 A 股盘中时间（工作日 9:30-15:00）。"""
            if now.weekday() >= 5:  # 周六日
                return False
            t = now.time()
            return time(9, 30) <= t < time(15, 0)

        @classmethod
        def _bulk_stock_matrix_run_window_state(cls, now: datetime) -> dict[str, Any]:
            current_period = "market_hours" if cls._is_market_hours(now) else "off_hours"
            run_window = str(STOCK_STRATEGY_MATRIX_RUN_WINDOW or "always").strip().lower() or "always"
            configured_enabled = bool(STOCK_STRATEGY_MATRIX_ENABLED)
            run_window_active = configured_enabled and (
                run_window == "always" or run_window == current_period
            )
            skip_reason = None
            if not configured_enabled:
                skip_reason = "disabled"
            elif not run_window_active:
                skip_reason = "outside_run_window"
            return {
                "configured_enabled": configured_enabled,
                "run_window": run_window,
                "run_window_active": run_window_active,
                "current_period": current_period,
                "skip_reason": skip_reason,
            }

        def _compute_next_wait(self, now: datetime) -> float:
            """根据调度模式和当前时间计算下一次运行的等待秒数。"""
            # 首次运行使用启动延迟
            if self._cycle_count == 0:
                return float(AUTONOMY_STARTUP_DELAY_SEC)

            if self.schedule_mode == "daily":
                target = datetime.combine(now.date(), self.run_time, tzinfo=self._market_timezone)
                if target <= now:
                    target += timedelta(days=1)
                return (target - now).total_seconds()

            # continuous 模式
            if now.weekday() >= 5:
                # 周末
                return float(FACTORY_OFF_HOURS_INTERVAL_SEC)
            if self._is_market_hours(now):
                return float(FACTORY_MARKET_HOURS_INTERVAL_SEC)
            return float(FACTORY_OFF_HOURS_INTERVAL_SEC)
