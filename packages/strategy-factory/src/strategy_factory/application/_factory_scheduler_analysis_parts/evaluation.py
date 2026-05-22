
        @classmethod
        def _build_factory_architecture_review(
            cls,
            results: dict[str, Any],
            current_summary: Optional[dict[str, Any]],
            previous_summary: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            del current_summary
            previous = dict(previous_summary or {})
            strategy_records = cls._iter_strategy_records(results)
            backtest_records = cls._iter_backtest_records(results)

            contract_issues: list[dict[str, Any]] = []
            contract_consistent_count = 0
            contract_missing_count = 0
            for record in strategy_records:
                strategy_id = str(record.get("strategy_id") or record.get("name") or "unknown")
                contract_hash = str(record.get("candidate_contract_hash") or "").strip()
                contract_snapshot = dict(record.get("candidate_contract_snapshot") or {})
                if not contract_hash or not contract_snapshot:
                    contract_missing_count += 1
                    contract_issues.append(
                        {
                            "strategy_id": strategy_id,
                            "issue": "missing_candidate_contract",
                        }
                    )
                    continue
                recomputed_hash = build_candidate_contract_hash(contract=contract_snapshot)
                if recomputed_hash == contract_hash:
                    contract_consistent_count += 1
                    continue
                contract_issues.append(
                    {
                        "strategy_id": strategy_id,
                        "issue": "candidate_contract_hash_mismatch",
                        "candidate_contract_hash": contract_hash,
                        "recomputed_contract_hash": recomputed_hash,
                    }
                )

            validation_issues: list[dict[str, Any]] = []
            validation_consistent_count = 0
            validation_missing_count = 0
            validation_total_count = 0
            for index, record in enumerate(backtest_records, 1):
                payload = dict(record.get("backtest_result") or record or {})
                candidate_hash = str(payload.get("candidate_contract_hash") or "").strip()
                tested_hash = str(payload.get("tested_object_hash") or "").strip()
                if not candidate_hash and not tested_hash:
                    continue
                validation_total_count += 1
                if not candidate_hash or not tested_hash:
                    validation_missing_count += 1
                    validation_issues.append(
                        {
                            "record": index,
                            "issue": "missing_tested_object_hash",
                            "candidate_contract_hash": candidate_hash or None,
                            "tested_object_hash": tested_hash or None,
                        }
                    )
                    continue
                validation_consistent_count += 1

            admission_issues: list[dict[str, Any]] = []
            admission_consistent_count = 0
            for record in strategy_records:
                strategy_id = str(record.get("strategy_id") or record.get("name") or "unknown")
                admission_stage = cls._normalize_text(record.get("admission_stage"))
                action_type = cls._normalize_text(record.get("submission_action_type"))
                submission_lane = cls._normalize_text(record.get("submission_lane"))
                passed = bool(record.get("passed"))
                live_candidate_ready = bool(record.get("live_candidate_ready"))
                live_review_ready = bool(record.get("live_review_ready"))
                direct_trade_candidate = bool(record.get("direct_trade_candidate"))
                pool_admission_applied = bool(record.get("pool_admission_applied"))
                admission_block_reasons = list(record.get("admission_block_reasons") or [])

                record_issues: list[str] = []
                if pool_admission_applied and action_type != "pool_admission":
                    record_issues.append("pool_admission_action_mismatch")
                if pool_admission_applied and admission_stage != "live":
                    record_issues.append("pool_admission_stage_mismatch")
                if pool_admission_applied and admission_block_reasons:
                    record_issues.append("pool_admission_has_blockers")
                if admission_stage == "live" and not live_candidate_ready:
                    record_issues.append("live_stage_without_live_candidate")
                if action_type in {"pool_admission", "runtime_review"} and not (
                    live_candidate_ready or live_review_ready or direct_trade_candidate
                ):
                    record_issues.append("live_ready_action_without_live_ready_candidate")
                if submission_lane == "live_ready_review" and not (
                    live_candidate_ready or live_review_ready or direct_trade_candidate
                ):
                    record_issues.append("live_ready_lane_without_live_ready_candidate")
                if not passed and pool_admission_applied:
                    record_issues.append("failed_candidate_pool_admitted")
                if record_issues:
                    admission_issues.append(
                        {
                            "strategy_id": strategy_id,
                            "issues": record_issues,
                            "admission_stage": admission_stage or None,
                            "submission_action_type": action_type or None,
                            "submission_lane": submission_lane or None,
                        }
                    )
                else:
                    admission_consistent_count += 1

            def _category_payload(
                *,
                total: int,
                consistent: int,
                missing: int,
                issues: list[dict[str, Any]],
            ) -> dict[str, Any]:
                mismatch_count = len(issues)
                return {
                    "status": cls._governance_status(
                        critical=mismatch_count > 0,
                        warning=missing > 0,
                        available=total > 0,
                    ),
                    "total_count": total,
                    "consistent_count": consistent,
                    "missing_count": missing,
                    "mismatch_count": mismatch_count,
                    "issues": issues[:8],
                }

            categories = {
                "contract_consistency": _category_payload(
                    total=len(strategy_records),
                    consistent=contract_consistent_count,
                    missing=contract_missing_count,
                    issues=contract_issues,
                ),
                "validation_object_consistency": _category_payload(
                    total=validation_total_count,
                    consistent=validation_consistent_count,
                    missing=validation_missing_count,
                    issues=validation_issues,
                ),
                "admission_consistency": _category_payload(
                    total=len(strategy_records),
                    consistent=admission_consistent_count,
                    missing=0,
                    issues=admission_issues,
                ),
            }

            current_week = cls._iso_week_label((results or {}).get("completed_at") or (results or {}).get("started_at"))
            previous_review = dict(previous.get("architecture_review") or {})
            previous_review_week = str(previous_review.get("review_week") or "").strip() or None
            cadence_due = previous_review_week != current_week

            overall_status = "healthy"
            category_statuses = {payload.get("status") for payload in categories.values()}
            if "critical" in category_statuses:
                overall_status = "attention_required"
            elif "warning" in category_statuses:
                overall_status = "warning"
            elif category_statuses == {"unavailable"}:
                overall_status = "unavailable"

            return {
                "status": overall_status,
                "review_week": current_week,
                "previous_review_week": previous_review_week,
                "cadence_due": cadence_due,
                "generated_at": (results or {}).get("completed_at") or datetime.now(_MARKET_TIMEZONE).isoformat(),
                "categories": categories,
                "strategy_record_count": len(strategy_records),
                "validation_record_count": validation_total_count,
            }

        @classmethod
        def _attach_runtime_governance(
            cls,
            results: dict[str, Any],
            *,
            previous_result: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            summary = dict(results.get("summary") or {})
            previous_summary = dict((previous_result or {}).get("summary") or {})
            summary["scheduler_slo"] = cls._build_scheduler_slo_summary(
                results,
                summary,
                previous_summary=previous_summary,
            )
            summary["architecture_review"] = cls._build_factory_architecture_review(
                results,
                summary,
                previous_summary=previous_summary,
            )
            results["summary"] = summary
            return results

        @staticmethod
        def _aggregate_backtest_audit_metrics(backtest_report: Optional[dict]) -> dict[str, Any]:
            report = dict(backtest_report or {})
            summary = dict(report.get("summary") or {})
            failed_reason_counts = {
                str(key): int(value or 0)
                for key, value in dict(summary.get("failed_reason_counts") or {}).items()
                if str(key).strip()
            }
            entries = list(report.get("passed") or []) + list(report.get("failed") or [])
            contamination_warning_count = 0
            cost_audit_missing_count = 0
            event_sample_source_counts: dict[str, int] = {}
            event_study_mode_counts: dict[str, int] = {}
            primary_metrics_source_counts: dict[str, int] = {}
            for entry in entries:
                backtest_result = dict((entry or {}).get("backtest_result") or {})
                contamination = dict(backtest_result.get("contamination_summary") or {})
                validation_focus = str(backtest_result.get("validation_focus") or "").strip().lower()
                if validation_focus == "event_target_only" and (
                    bool(contamination.get("representative_included")) or bool(contamination.get("mixed_layer_used"))
                ):
                    contamination_warning_count += 1
                if not backtest_result.get("cost_assumptions") or not backtest_result.get("position_assumption"):
                    cost_audit_missing_count += 1
                event_window_metrics = dict(backtest_result.get("event_window_metrics") or {})
                event_sample_source = str(event_window_metrics.get("event_sample_source") or "").strip().lower()
                if event_sample_source:
                    event_sample_source_counts[event_sample_source] = event_sample_source_counts.get(event_sample_source, 0) + 1
                event_study_mode = str(event_window_metrics.get("event_study_mode") or "").strip().lower()
                if event_study_mode:
                    event_study_mode_counts[event_study_mode] = event_study_mode_counts.get(event_study_mode, 0) + 1
                primary_layer = str(backtest_result.get("primary_validation_layer") or "").strip().lower()
                layer_results = dict(backtest_result.get("layer_results") or {})
                primary_metrics_source = str(
                    dict(layer_results.get(primary_layer) or {}).get("metrics_source") or ""
                ).strip().lower()
                if primary_metrics_source:
                    primary_metrics_source_counts[primary_metrics_source] = (
                        primary_metrics_source_counts.get(primary_metrics_source, 0) + 1
                    )
            return {
                "event_window_contamination_warning_count": contamination_warning_count,
                "cost_audit_missing_count": cost_audit_missing_count,
                "gate_2_portfolio_engine_required_count": int(failed_reason_counts.get("portfolio_engine_required") or 0),
                "gate_2_event_audit_incomplete_count": int(failed_reason_counts.get("event_audit_incomplete") or 0),
                "gate_2_event_samples_required_count": int(failed_reason_counts.get("event_samples_required") or 0),
                "gate_2_event_sample_source_counts": event_sample_source_counts,
                "gate_2_event_study_mode_counts": event_study_mode_counts,
                "gate_2_primary_metrics_source_counts": primary_metrics_source_counts,
                "gate_2_event_sample_source_auto_context_minimal_count": int(
                    event_sample_source_counts.get("auto_context_minimal") or 0
                ),
            }
