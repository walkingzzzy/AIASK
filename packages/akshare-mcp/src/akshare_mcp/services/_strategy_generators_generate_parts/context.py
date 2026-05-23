        def _l2_hypothesis_replay_enabled() -> bool:
            raw = os.getenv("STRATEGY_FACTORY_L2_HYPOTHESIS_REPLAY_ENABLED")
            if raw is None:
                raw = os.getenv("STRATEGY_FACTORY_L2_REPLAY_ENABLED")
            if raw is None:
                return True
            return str(raw).strip().lower() in {"1", "true", "yes", "on"}

        @classmethod
        def _replay_strategy_spec_from_experiment(
            cls,
            row: dict[str, Any],
            *,
            research_task: Optional[dict[str, Any]] = None,
        ) -> Optional[StrategySpec]:
            payload = dict(row or {})
            strategy_spec = dict(payload.get("strategy_spec") or {})
            evaluation = dict(payload.get("evaluation") or {})
            replay_contract = dict(strategy_spec.get("replay_contract") or {})
            contract = dict(replay_contract or strategy_spec)
            strategy_type = str(contract.get("strategy_type") or strategy_spec.get("strategy_type") or "").strip()
            if not strategy_type:
                return None
            params = dict(contract.get("params") or {})
            name = str(contract.get("name") or strategy_spec.get("name") or "").strip() or "历史回放候选"
            description = str(
                contract.get("description")
                or strategy_spec.get("description")
                or payload.get("hypothesis")
                or ""
            ).strip()
            target_symbols = cls._normalize_code_list(
                [
                    contract.get("target_symbols"),
                    strategy_spec.get("target_symbols"),
                    evaluation.get("target_symbols"),
                ]
            )
            normalized_task = normalize_research_task_contract(research_task or {})
            requested_targets = set(cls._normalize_code_list(normalized_task.get("target_symbols")))
            if requested_targets and target_symbols and not requested_targets.intersection(target_symbols):
                return None
            allowed_strategy_types = {
                str(item or "").strip().lower()
                for item in list(normalized_task.get("allowed_strategy_types") or [])
                if str(item or "").strip()
            }
            if allowed_strategy_types and strategy_type.strip().lower() not in allowed_strategy_types:
                return None

            hypothesis_artifact = dict(
                contract.get("hypothesis_artifact")
                or strategy_spec.get("hypothesis_artifact")
                or evaluation.get("hypothesis_artifact")
                or {}
            )
            metadata = {
                "generator_type": "hypothesis_replay",
                "hypothesis": str(
                    hypothesis_artifact.get("alpha_hypothesis")
                    or payload.get("hypothesis")
                    or description
                    or name
                ).strip(),
                "holding_horizon": dict(contract.get("holding_horizon") or {}),
                "trade_plan": dict(contract.get("trade_plan") or {}),
                "risk_rules": dict(contract.get("risk_rules") or {}),
                "position_sizing": dict(contract.get("position_sizing") or {}),
                "execution_notes": contract.get("execution_notes"),
                "rebalance_rule": dict(contract.get("rebalance_rule") or {}),
                "portfolio_spec": dict(contract.get("portfolio_spec") or {}),
                "execution_assumptions": dict(contract.get("execution_assumptions") or {}),
                "validation_profile": dict(contract.get("validation_profile") or {}),
                "targeting_policy": dict(contract.get("targeting_policy") or {}),
                "constraint_check": dict(contract.get("constraint_check") or {}),
                "target_symbols": list(target_symbols),
                "stock_pool": dict(contract.get("stock_pool") or {}),
                "selection_logic": list(contract.get("selection_logic") or []),
                "research_task": dict(contract.get("research_task") or strategy_spec.get("research_task") or normalized_task),
                "event_context": dict(contract.get("event_context") or strategy_spec.get("event_context") or {}),
                "hypothesis_artifact": hypothesis_artifact,
                "hypothesis_lowering_audit": dict(
                    contract.get("hypothesis_lowering_audit")
                    or evaluation.get("hypothesis_lowering_audit")
                    or {}
                ),
                "holding_rationale": hypothesis_artifact.get("holding_rationale"),
                "alpha_half_life": hypothesis_artifact.get("alpha_half_life"),
                "cost_sensitivity_grid": hypothesis_artifact.get("cost_sensitivity_grid"),
                "position_model": hypothesis_artifact.get("position_model"),
                "capacity_assumption": hypothesis_artifact.get("capacity_assumption"),
                "market_regime_assumption": hypothesis_artifact.get("market_regime_assumption"),
                "economic_semantics_score": hypothesis_artifact.get("economic_semantics_score"),
                "economic_semantics_missing_fields": list(
                    hypothesis_artifact.get("economic_semantics_missing_fields") or []
                ),
                "validation_focus": (
                    hypothesis_artifact.get("validation_focus")
                    or dict(contract.get("validation_profile") or {}).get("validation_focus")
                ),
                "replay_source": {
                    "experiment_id": payload.get("experiment_id"),
                    "generator_type": payload.get("generator_type"),
                    "status": payload.get("status"),
                    "source": payload.get("source"),
                },
                "committee_review": dict(evaluation.get("committee_review") or {}),
                "llm_analysis": dict(evaluation.get("llm_analysis") or {}),
                "llm_research_context": dict(evaluation.get("llm_research_context") or {}),
                "source_candidate": {
                    "name": name,
                    "description": description,
                    "strategy_type": strategy_type,
                    "params": dict(params),
                    "target_symbols": list(target_symbols),
                    "stock_pool": dict(contract.get("stock_pool") or {}),
                    "selection_logic": list(contract.get("selection_logic") or []),
                    "research_task": dict(contract.get("research_task") or strategy_spec.get("research_task") or normalized_task),
                    "event_context": dict(contract.get("event_context") or strategy_spec.get("event_context") or {}),
                    "hypothesis_artifact": hypothesis_artifact,
                },
            }
            tags = list(
                dict.fromkeys(
                    [
                        "hypothesis_replay",
                        *(list(contract.get("tags") or strategy_spec.get("tags") or [])[:8]),
                    ]
                )
            )
            return StrategySpec(
                strategy_type=strategy_type,
                params=params,
                name=name,
                description=description,
                tags=tags,
                metadata=metadata,
            )

        async def replay_persisted_specs(
            self,
            db,
            *,
            limit: int = 3,
            snapshot: Optional[dict[str, Any]] = None,
            parent_strategies: Optional[list[dict[str, Any]]] = None,
            research_task: Optional[dict[str, Any]] = None,
            trigger_reason: str = "provider_health_blocked",
        ) -> dict[str, Any]:
            del snapshot
            if not self._l2_hypothesis_replay_enabled() or not hasattr(db, "list_strategy_generation_experiments"):
                return {
                    "specs": [],
                    "report": {
                        "status": "disabled",
                        "trigger_reason": trigger_reason,
                        "selected_count": 0,
                    },
                }

            requested_limit = max(1, min(int(limit or 3), 10))
            rows: list[dict[str, Any]] = []
            for parent in list(parent_strategies or [])[:3]:
                parent_id = str((parent or {}).get("id") or "").strip()
                if not parent_id:
                    continue
                try:
                    rows.extend(
                        await db.list_strategy_generation_experiments(
                            parent_strategy_id=parent_id,
                            limit=max(6, requested_limit * 4),
                        )
                    )
                except Exception as exc:
                    logger.warning(
                        "LLMProxyStrategyGenerator: replay experiment lookup failed for %s: %s",
                        parent_id,
                        exc,
                    )
            replay_specs: list[tuple[tuple[float, int, int], StrategySpec, dict[str, Any]]] = []
            seen_ids: set[str] = set()
            for row in rows:
                row_payload = dict(row or {})
                experiment_id = str(row_payload.get("experiment_id") or "").strip()
                if experiment_id and experiment_id in seen_ids:
                    continue
                if experiment_id:
                    seen_ids.add(experiment_id)
                spec = self._replay_strategy_spec_from_experiment(row_payload, research_task=research_task)
                if spec is None:
                    continue
                evaluation = dict(row_payload.get("evaluation") or {})
                review = dict(evaluation.get("committee_review") or {})
                decision = str(review.get("decision") or "").strip().lower()
                status = str(row_payload.get("status") or "").strip().lower()
                decision_rank = {
                    "accept": 4,
                    "accepted": 4,
                    "revise": 3,
                    "retry": 2,
                    "generated": 2,
                    "review": 1,
                    "reject": 0,
                    "rejected": 0,
                }.get(decision, 1 if status in {"generated", "accepted"} else 0)
                try:
                    score = float(review.get("final_score") or 0.0)
                except Exception:
                    score = 0.0
                target_symbols = set(self._normalize_code_list(spec.metadata.get("target_symbols")))
                requested_targets = set(
                    self._normalize_code_list((research_task or {}).get("target_symbols"))
                )
                overlap = len(target_symbols.intersection(requested_targets)) if requested_targets else 0
                replay_specs.append(((score, overlap, decision_rank), spec, row_payload))

            replay_specs.sort(key=lambda item: item[0], reverse=True)
            deduped_specs = self._dedupe_specs([item[1] for item in replay_specs])
            selected_specs = deduped_specs[:requested_limit]
            selected_ids: list[str] = []
            selected_status_counts: dict[str, int] = {}
            for _rank, _spec, row_payload in replay_specs:
                if len(selected_ids) >= len(selected_specs):
                    break
                candidate_key = (
                    str(_spec.strategy_type or ""),
                    json.dumps(_spec.params or {}, sort_keys=True, ensure_ascii=False, default=str),
                )
                if candidate_key not in {
                    (
                        str(spec.strategy_type or ""),
                        json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str),
                    )
                    for spec in selected_specs
                }:
                    continue
                experiment_id = str(row_payload.get("experiment_id") or "").strip()
                if experiment_id:
                    selected_ids.append(experiment_id)
                status = str(row_payload.get("status") or "unknown").strip().lower() or "unknown"
                selected_status_counts[status] = selected_status_counts.get(status, 0) + 1

            return {
                "specs": selected_specs,
                "report": {
                    "status": "succeeded" if selected_specs else "empty",
                    "trigger_reason": trigger_reason,
                    "available_count": len(replay_specs),
                    "selected_count": len(selected_specs),
                    "experiment_ids": selected_ids,
                    "status_counts": selected_status_counts,
                },
            }

        async def _generate_via_pipeline(
            self,
            db,
            limit: int = 3,
            snapshot: Optional[dict] = None,
            research_task: Optional[dict[str, Any]] = None,
            timeout_sec: Optional[float] = None,
        ) -> list[StrategySpec]:
            """使用多阶段 Pipeline 生成策略候选。"""
            _pipeline_mode, pipeline_factory = _resolve_pipeline_runtime_symbols()
            pipeline = pipeline_factory()
            pipeline_timeout_sec = float(timeout_sec or self._pipeline_run_timeout_sec())
            pipeline_result = await asyncio.wait_for(
                pipeline.run_pipeline(
                    db=db,
                    snapshot=snapshot or {},
                    research_task=research_task,
                ),
                timeout=pipeline_timeout_sec,
            )

            specs: list[StrategySpec] = []
            pipeline_precompile_rejections: list[dict[str, Any]] = []
            normalized_research_task = (
                normalize_research_task_contract(research_task)
                if isinstance(research_task, dict) and research_task
                else {}
            )
            for candidate in pipeline_result.candidates[:limit]:
                candidate_payload = dict(candidate or {})
                if normalized_research_task and not candidate_payload.get("research_task"):
                    candidate_payload["research_task"] = dict(normalized_research_task)
                spec = self._pipeline_candidate_to_spec(candidate_payload, pipeline_result.provenance)
                if spec is not None:
                    specs.append(spec)
                elif candidate_payload.get("_generator_precompile_reject_reasons"):
                    pipeline_precompile_rejections.append(
                        {
                            "name": str(candidate_payload.get("name") or ""),
                            "strategy_type": str(candidate_payload.get("strategy_type") or ""),
                            "reject_reasons": list(candidate_payload.get("_generator_precompile_reject_reasons") or []),
                        }
                    )

            stage_requests: list[dict[str, Any]] = []
            llm_attempt_count = 0
            llm_success_count = 0
            llm_elapsed_seconds = 0.0
            last_error = None
            last_error_type = None
            pipeline_provenance = dict(pipeline_result.provenance or {})
            stage_fallback_reasons = dict(pipeline_provenance.get("stage_fallback_reasons") or {})
            pipeline_fallback_counts: dict[str, int] = {}
            for reason in stage_fallback_reasons.values():
                token = str(reason or "fallback").strip() or "fallback"
                pipeline_fallback_counts[token] = pipeline_fallback_counts.get(token, 0) + 1
            for stage_id, stage_result in pipeline_result.stages.items():
                stage_error = getattr(stage_result, "llm_error", None) or stage_result.error
                stage_error_type = getattr(stage_result, "llm_error_type", None)
                stage_error_metrics = dict(getattr(stage_result, "llm_error_metrics", {}) or {})
                if stage_error and last_error is None:
                    last_error = stage_error
                    last_error_type = stage_error_type or (
                        stage_error.split(":", 1)[0] if ":" in stage_error else stage_error
                    )
                if not getattr(stage_result, "llm_attempted", False):
                    continue
                llm_attempt_count += 1
                llm_elapsed_seconds += float(stage_result.elapsed_sec or 0.0)
                if not stage_result.used_fallback:
                    llm_success_count += 1
                request_status = "succeeded"
                if stage_result.used_fallback:
                    metric_status = _normalize_external_request_status(stage_error_metrics.get("status"))
                    request_status = metric_status if metric_status in _NON_REQUEST_SKIP_STATUSES else "fallback"
                request_attempt_count = 0
                if request_status not in _NON_REQUEST_SKIP_STATUSES:
                    try:
                        request_attempt_count = int(stage_error_metrics.get("attempt_count") or 0)
                    except Exception:
                        request_attempt_count = 0
                    request_attempt_count = max(request_attempt_count, 1)
                request_metrics = {
                    "status": stage_error_metrics.get("status"),
                    "attempt_count": request_attempt_count,
                    "prompt_chars": int(stage_result.prompt_chars or 0),
                    "response_chars": int(stage_result.response_chars or 0),
                    "elapsed_seconds": round(float(stage_result.elapsed_sec or 0.0), 4),
                    "last_error_type": stage_error_type,
                    "last_error": stage_error,
                    "last_error_status_code": (
                        stage_error_metrics.get("last_error_status_code")
                        or stage_error_metrics.get("status_code")
                    ),
                    "empty_200_response": bool(stage_error_metrics.get("empty_200_response")),
                }
                for key in (
                    "local_fallback_suppressed",
                    "suppression_reason",
                    "validation_failure_reason",
                    "output_keys",
                ):
                    if key in stage_error_metrics:
                        request_metrics[key] = stage_error_metrics.get(key)
                stage_requests.append(
                    {
                        "stage_id": stage_id,
                        "status": request_status,
                        "used_fallback": bool(stage_result.used_fallback),
                        "elapsed_seconds": round(float(stage_result.elapsed_sec or 0.0), 4),
                        "prompt_chars": int(stage_result.prompt_chars or 0),
                        "response_chars": int(stage_result.response_chars or 0),
                        "error": stage_error,
                        "error_type": stage_error_type,
                        "request_metrics": request_metrics,
                    }
                )

            if specs:
                external_status = "succeeded" if llm_success_count > 0 else "fallback_only"
            elif pipeline_result.error:
                external_status = "failed"
            elif llm_attempt_count > 0:
                external_status = "non_executable"
            else:
                external_status = "skipped"

            self.last_report = {
                'pipeline_mode': 'staged',
                'pipeline_provenance': pipeline_provenance,
                'pipeline_error': pipeline_result.error,
                'pipeline_stage_fallback_reasons': stage_fallback_reasons,
                'pipeline_fallback_counts': pipeline_fallback_counts,
                'pipeline_invalid_output_stage_ids': list(
                    pipeline_provenance.get("invalid_output_stage_ids") or []
                ),
                'selected_count': len(specs),
                'selected_generators': {'pipeline_staged': len(specs)},
                'pipeline_precompile_rejected_count': len(pipeline_precompile_rejections),
                'pipeline_precompile_rejections': pipeline_precompile_rejections[:8],
                'external_provider': {
                    'enabled': True,
                    'provider': getattr(self.external_provider.config, 'provider', None),
                    'model': getattr(self.external_provider.config, 'model', None),
                    'status': external_status,
                    'requests': stage_requests,
                    'selected_count': len(specs),
                    'viable_selected_count': len(specs),
                    'fallback_count': len(specs) if external_status == 'fallback_only' else 0,
                    'elapsed_seconds': round(llm_elapsed_seconds, 4),
                    'last_error_type': last_error_type,
                    'last_error': last_error,
                },
            }
            self.last_report['external_provider'] = _finalize_external_provider_report(
                self.last_report.get('external_provider')
            )
            return specs
