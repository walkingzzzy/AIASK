    _TASK_RUN_PREVIEW_LIMIT = 3

    @classmethod
    def _preview_items(
        cls,
        items: list[dict] | tuple[dict, ...] | None,
        *,
        fields: tuple[str, ...],
        limit: Optional[int] = None,
    ) -> list[dict]:
        preview: list[dict] = []
        for item in list(items or [])[: limit or cls._TASK_RUN_PREVIEW_LIMIT]:
            if not isinstance(item, dict):
                preview.append({'value': str(item)})
                continue
            compact = {
                key: item.get(key)
                for key in fields
                if item.get(key) not in (None, "", [], {})
            }
            if not compact:
                compact = {'keys': sorted(str(key) for key in item.keys())[:8]}
            preview.append(compact)
        return preview

    @staticmethod
    def _compact_dict(
        payload: Optional[dict[str, Any]],
        *,
        keys: tuple[str, ...],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        source = dict(payload or {})
        for key in keys:
            value = source.get(key)
            if value in (None, "", [], {}):
                continue
            result[key] = value
        return result

    @staticmethod
    def _normalize_external_request_status(status: Any) -> str:
        return str(status or "").strip().lower() or "unknown"

    @classmethod
    def _summarize_external_request_status_counts(
        cls,
        requests: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in list(requests or []):
            status = cls._normalize_external_request_status(dict(item or {}).get("status"))
            counts[status] = counts.get(status, 0) + 1
        return counts

    @classmethod
    def _count_external_network_requests(
        cls,
        requests: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
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
        requests: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    ) -> int:
        total = 0
        for item in list(requests or []):
            status = cls._normalize_external_request_status(dict(item or {}).get("status"))
            if status in {"compatibility_skip", "cooldown_skip"}:
                continue
            total += 1
        return total

    @classmethod
    def _request_is_compatibility_failure(cls, request: Optional[dict[str, Any]]) -> bool:
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
    def _request_is_empty_200_response(cls, request: Optional[dict[str, Any]]) -> bool:
        payload = dict(request or {})
        metrics = dict(payload.get("request_metrics") or {})
        if bool(metrics.get("empty_200_response")):
            return True
        if not cls._request_is_compatibility_failure(payload):
            return False
        error_text = str(payload.get("error") or metrics.get("last_error") or "").strip().lower()
        return "missing extractable content" in error_text

    @classmethod
    def _summarize_factor_research(cls, factor_research: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(factor_research or {})
        summary = dict(payload.get('summary') or {})
        freshness_repair = dict(payload.get('freshness_repair') or {})
        compact = {
            'top_factor_names': list(
                summary.get('top_factor_names')
                or payload.get('active_factors')
                or []
            )[:6],
            'preferred_strategy_types': [
                str(item).strip()
                for item in list(payload.get('preferred_strategy_types') or [])
                if str(item).strip()
            ][:6],
            'degraded': bool(payload.get('degraded')),
        }
        compact.update(
            cls._compact_dict(
                summary,
                keys=(
                    'active_candidate_count',
                    'candidate_pool_size',
                    'registry_size',
                    'freshness_days',
                    'refresh_status',
                ),
            )
        )
        if freshness_repair:
            compact['freshness_repair'] = cls._compact_dict(
                freshness_repair,
                keys=(
                    'refresh_attempted',
                    'refresh_status',
                    'refresh_trigger',
                    'fallback_reason',
                    'stale_days',
                ),
            )
        return {key: value for key, value in compact.items() if value not in (None, "", [], {})}

    @classmethod
    def _summarize_research_task(
        cls,
        research_task: Optional[dict[str, Any]],
        *,
        factor_research: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        task = _safe_normalize_research_task(research_task) or dict(research_task or {})
        metadata = dict(task.get('metadata') or {})
        summary = cls._compact_dict(
            task,
            keys=(
                'task_id',
                'task_key',
                'task_source',
                'opportunity_type',
                'theme_code',
                'event_id',
                'candidate_family',
                'factor_name',
                'generation_limit',
                'source_candidate_artifact_id',
                'evidence_count',
                'preference_strength',
                'validation_focus',
            ),
        )
        target_symbols = list(task.get('target_symbols') or [])
        if target_symbols:
            summary['target_symbols'] = target_symbols[:12]
        preferred_strategy_types = [
            str(item).strip()
            for item in list(
                task.get('preferred_strategy_types')
                or task.get('strategy_preferences')
                or []
            )
            if str(item).strip()
        ]
        if preferred_strategy_types:
            summary['preferred_strategy_types'] = preferred_strategy_types[:6]
            summary['strategy_preferences'] = preferred_strategy_types[:6]
        allowed_strategy_types = [
            str(item).strip()
            for item in list(task.get('allowed_strategy_types') or [])
            if str(item).strip()
        ]
        if allowed_strategy_types:
            summary['allowed_strategy_types'] = allowed_strategy_types[:6]
        factor_summary = cls._summarize_factor_research(
            metadata.get('factor_research') if isinstance(metadata.get('factor_research'), dict) else factor_research
        )
        if factor_summary:
            summary['metadata'] = {'factor_research': factor_summary}
        return summary

    @classmethod
    def _summarize_event_context(cls, event_context: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(event_context or {})
        summary = cls._compact_dict(
            payload,
            keys=(
                'task_source',
                'event_id',
                'theme_code',
                'event_type',
                'opportunity_type',
                'candidate_family',
                'factor_name',
            ),
        )
        target_symbols = list(payload.get('target_symbols') or payload.get('symbols') or [])
        if target_symbols:
            summary['target_symbols'] = target_symbols[:12]
        score_summary = dict(payload.get('score_summary') or {})
        if score_summary:
            summary['score_summary'] = cls._compact_dict(
                score_summary,
                keys=(
                    'score',
                    'confidence',
                    'impact_score',
                    'urgency_score',
                    'priority',
                ),
            )
        return summary

    @classmethod
    def _summarize_llm_report(cls, llm_report: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(llm_report or {})
        external = dict(payload.get('external_provider') or {})
        requests = list(external.get('requests') or [])
        external_summary = cls._compact_dict(
            external,
            keys=(
                'enabled',
                'provider',
                'model',
                'status',
                'selected_count',
                'viable_selected_count',
                'fallback_count',
                'elapsed_seconds',
                'last_error_type',
                'last_error',
                'stage_attempt_count',
                'network_request_count',
                'real_request_count',
                'compatibility_skip_count',
                'cooldown_skip_count',
                'compatibility_failure_count',
                'compatibility_failure_ratio',
                'effective_response_count',
                'effective_response_ratio',
                'empty_200_response_count',
            ),
        )
        request_status_counts = dict(external.get('request_status_counts') or {}) or cls._summarize_external_request_status_counts(requests)
        if requests:
            real_request_count = int(external.get('real_request_count') or cls._count_external_real_requests(requests))
            compatibility_failure_count = int(
                external.get('compatibility_failure_count')
                or sum(1 for item in requests if cls._request_is_compatibility_failure(item))
            )
            effective_response_count = int(
                external.get('effective_response_count')
                or sum(
                    1
                    for item in requests
                    if cls._normalize_external_request_status(dict(item or {}).get('status')) == 'succeeded'
                )
            )
            empty_200_response_count = int(
                external.get('empty_200_response_count')
                or sum(1 for item in requests if cls._request_is_empty_200_response(item))
            )
            external_summary['request_count'] = len(requests)
            external_summary['stage_attempt_count'] = int(external.get('stage_attempt_count') or len(requests))
            external_summary['network_request_count'] = int(
                external.get('network_request_count') or cls._count_external_network_requests(requests)
            )
            external_summary['real_request_count'] = real_request_count
            external_summary['compatibility_skip_count'] = int(
                external.get('compatibility_skip_count')
                or request_status_counts.get('compatibility_skip', 0)
            )
            external_summary['cooldown_skip_count'] = int(
                external.get('cooldown_skip_count')
                or request_status_counts.get('cooldown_skip', 0)
            )
            external_summary['compatibility_failure_count'] = compatibility_failure_count
            external_summary['effective_response_count'] = effective_response_count
            external_summary['empty_200_response_count'] = empty_200_response_count
            external_summary['compatibility_failure_ratio'] = (
                external.get('compatibility_failure_ratio')
                if external.get('compatibility_failure_ratio') is not None
                else (round(compatibility_failure_count / real_request_count, 4) if real_request_count else 0.0)
            )
            external_summary['effective_response_ratio'] = (
                external.get('effective_response_ratio')
                if external.get('effective_response_ratio') is not None
                else (round(effective_response_count / real_request_count, 4) if real_request_count else 0.0)
            )
        elif request_status_counts:
            external_summary['request_count'] = int(external.get('stage_attempt_count') or 0)
        if external.get('request_limits'):
            external_summary['request_limits'] = list(external.get('request_limits') or [])[:4]
        if request_status_counts:
            external_summary['request_status_counts'] = request_status_counts
        if requests:
            external_summary['requests_preview'] = [
                {
                    **cls._compact_dict(
                        dict(item or {}),
                        keys=(
                            'request_index',
                            'request_limit',
                            'status',
                            'returned_candidate_count',
                            'compiled_candidate_count',
                            'non_executable_candidate_count',
                            'viable_candidate_count',
                            'open_dsl_candidate_count',
                            'open_dsl_compiled_candidate_count',
                            'open_dsl_viable_candidate_count',
                            'open_dsl_rejected_count',
                            'error_type',
                            'error',
                        ),
                    ),
                    'request_metrics': cls._compact_dict(
                        dict((item or {}).get('request_metrics') or {}),
                        keys=(
                            'attempt_count',
                            'prompt_chars',
                            'response_chars',
                            'elapsed_seconds',
                            'last_error_type',
                            'last_error',
                        ),
                    ),
                }
                for item in requests[: cls._TASK_RUN_PREVIEW_LIMIT]
            ]
        analysis = dict(external.get('analysis') or {})
        if analysis:
            external_summary['analysis'] = cls._compact_dict(
                analysis,
                keys=(
                    'style_bias',
                    'market_regime',
                    'theme',
                    'direction',
                    'risk_hint',
                    'confidence',
                ),
            )
        summary = cls._compact_dict(
            payload,
            keys=(
                'requested_limit',
                'market_frame_ready',
                'market_frame_rows',
                'market_frame_source',
                'selected_count',
                'pipeline_run_timeout_sec',
            ),
        )
        if payload.get('selected_generators'):
            summary['selected_generators'] = dict(payload.get('selected_generators') or {})
        if payload.get('research_context_summary'):
            summary['research_context_summary'] = dict(payload.get('research_context_summary') or {})
        if external_summary:
            summary['external_provider'] = external_summary
        return summary

    @classmethod
    def _summarize_generation_result(cls, generation_result: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(generation_result or {})
        stats = dict(payload.get('stats') or {})
        return {
            'count': int(payload.get('count') or len(payload.get('candidates') or [])),
            'stats': cls._compact_dict(
                stats,
                keys=('rule_count', 'llm_count', 'evolved_count', 'merged_count'),
            ),
            'llm_generation': cls._summarize_llm_report(payload.get('llm_generation')),
            'candidate_preview': cls._preview_items(
                payload.get('candidates') or [],
                fields=('experiment_id', 'strategy_type', 'name', 'generated_strategy_id', 'status'),
            ),
        }

    @classmethod
    def _summarize_review_result(cls, review_result: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(review_result or {})
        return {
            'reviewed_count': int(payload.get('reviewed_count') or 0),
            'rejected_count': int(payload.get('rejected_count') or 0),
            'committee_review_count': len(payload.get('committee_reviews') or []),
            'committee_review_preview': cls._preview_items(
                payload.get('committee_reviews') or [],
                fields=('experiment_id', 'decision', 'final_score', 'review_rank', 'strategy_type', 'name'),
            ),
            'champion': cls._compact_dict(
                dict(payload.get('champion') or {}),
                keys=('experiment_id', 'generated_strategy_id', 'status', 'review_rank', 'final_score'),
            ),
        }

    @classmethod
    def _summarize_experiments_result(cls, experiments_result: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(experiments_result or {})
        return {
            'count': int(payload.get('count') or len(payload.get('items') or [])),
            'status_counts': dict(payload.get('status_counts') or {}),
            'preview': cls._preview_items(
                payload.get('items') or [],
                fields=('experiment_id', 'status', 'strategy_id', 'generated_strategy_id', 'generator_type', 'optimizer_type'),
            ),
        }

    @classmethod
    def _summarize_submission_result(cls, submission_result: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(submission_result or {})
        items = list(payload.get('items') or [])
        return {
            'auto_submit': bool(payload.get('auto_submit')),
            'attempted': bool(payload.get('attempted')),
            'submitted_count': int(payload.get('submitted_count') or 0),
            'passed_count': int(payload.get('passed_count') or 0),
            'failed_count': int(payload.get('failed_count') or 0),
            'provisional_passed_count': int(payload.get('provisional_passed_count') or 0),
            'failure_reason_topn': list(payload.get('failure_reason_topn') or [])[: cls._TASK_RUN_PREVIEW_LIMIT],
            'items_preview': cls._preview_items(
                items,
                fields=('experiment_id', 'strategy_id', 'passed', 'duplicate', 'reason_code'),
            ),
        }

    @staticmethod
    def _submission_metrics(submit_result: Optional[dict]) -> dict:
        payload = dict(submit_result or {})
        items = list(payload.get('items') or payload.get('strategies') or [])
        submitted_count = int(payload.get('submitted', len(items)))
        passed_count = int(
            payload.get(
                'gate_3_passed',
                payload.get(
                    'passed_quality_gate',
                    len([item for item in items if item.get('passed')]),
                ),
            )
        )
        failed_count = int(payload.get('gate_3_failed', max(submitted_count - passed_count, 0)))
        return {
            'submitted_count': submitted_count,
            'passed_count': passed_count,
            'failed_count': failed_count,
        }

    def __init__(self):
        self.generation_service = CandidateGenerationService(
            rule_generator=RuleStrategyGenerator(),
            llm_generator=LLMProxyStrategyGenerator(),
            optimizer=BanditParameterOptimizer(),
        )
        self.review_service = CommitteeReviewService(reviewer=MultiAgentStrategyReviewer())
        self.experiment_recorder = ExperimentRecorder()
        self.rule_generator = self.generation_service.rule_generator
        self.llm_generator = self.generation_service.llm_generator
        self.optimizer = self.generation_service.optimizer
        self.reviewer = self.review_service.reviewer

    async def _select_parents(self, db, parent_strategy_id: Optional[str] = None) -> list[dict]:
        return await self.generation_service.select_parents(db, parent_strategy_id=parent_strategy_id)

    @staticmethod
    def _attach_lineage(spec: StrategySpec, *, parent_strategy_id: Optional[str], task_run_id: Optional[int], review_rank: Optional[int] = None, is_champion: bool = False) -> StrategySpec:
        return CommitteeReviewService.attach_lineage(
            spec,
            parent_strategy_id=parent_strategy_id,
            task_run_id=task_run_id,
            review_rank=review_rank,
            is_champion=is_champion,
        )

    @staticmethod
    def _review_score(spec: StrategySpec) -> float:
        return CommitteeReviewService.review_score(spec)

    async def _record_experiment(self, db, spec: StrategySpec, source: str, snapshot: dict, task_run: dict) -> dict:
        return await self.experiment_recorder.record_experiment(db, spec, source, snapshot, task_run)

    async def generate_factory_candidates(self, db, snapshot: dict, limit: int = 3, research_task: Optional[dict[str, Any]] = None, source: str = 'strategy_factory') -> dict:
        cycle = await self.run_cycle(db, snapshot=snapshot, limit=limit, source=source, auto_submit=False, research_task=research_task)
        return cycle

    @staticmethod
    def _build_generation_result(candidates: list[dict], generation_stats: dict, llm_report: dict[str, Any]) -> dict:
        return {
            'count': len(candidates),
            'stats': generation_stats,
            'llm_generation': llm_report,
            'candidates': candidates,
        }

    @staticmethod
    def _build_review_result(reviewed_specs: list[StrategySpec], rejected_count: int, committee_reviews: list[dict[str, Any]], champion: Optional[dict[str, Any]]) -> dict:
        return {
            'reviewed_count': len(reviewed_specs),
            'rejected_count': rejected_count,
            'committee_reviews': committee_reviews,
            'champion': champion,
        }

    @staticmethod
    def _build_experiments_result(experiments: list[dict]) -> dict:
        status_counts = Counter(
            str((item or {}).get('status') or 'unknown')
            for item in list(experiments or [])
        )
        return {
            'count': len(experiments),
            'items': experiments,
            'status_counts': dict(status_counts),
        }
