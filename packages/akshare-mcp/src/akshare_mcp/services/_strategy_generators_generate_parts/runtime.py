
        async def generate(self, db, limit: int = 3, snapshot: Optional[dict] = None, parent_strategies: Optional[list[dict]] = None, research_task: Optional[dict[str, Any]] = None) -> list[StrategySpec]:
            snapshot = snapshot or {}
            shared_generation_context = dict(snapshot.get('_shared_generation_context') or {})
            if parent_strategies is None and shared_generation_context.get('parent_strategies'):
                parent_strategies = [dict(item or {}) for item in list(shared_generation_context.get('parent_strategies') or [])]
            requested_limit = max(1, min(int(limit or 3), 10))
            history_summary = [
                dict(item or {})
                for item in list(shared_generation_context.get('history_summary') or [])
            ]
            if not history_summary:
                history_summary = await self._recent_experiments(db, parent_strategies=parent_strategies)
            research_context = await self._build_research_context(
                db,
                snapshot,
                parent_strategies=parent_strategies,
                history_summary=history_summary,
                research_task=research_task,
            )
            research_context_summary = self._summarize_research_context(research_context)
            task_target_context = dict(research_context.get('task_target_context') or {})
            target_context_blocked = bool(research_context.get('blocked_by_target_universe'))
            targeted_research = bool(
                task_target_context.get('targeted_task')
                or self._normalize_code_list((research_task or {}).get('target_symbols'))
            )
            allowed_strategy_types = {
                str(item).strip().lower()
                for item in list((research_task or {}).get('allowed_strategy_types') or [])
                if str(item).strip()
            }
            allow_target_context_recovery = bool(
                self.external_provider.is_enabled()
                and (
                    'dsl_rule' in allowed_strategy_types
                    or 'open_dsl' in allowed_strategy_types
                    or 'llm_defined' in allowed_strategy_types
                )
            )
            recovered_target_frame: Optional[pd.DataFrame] = None
            recovered_target_context = False
            # 多阶段 pipeline 路径
            _pipeline_fallback_reason: Optional[str] = None
            skip_monolithic_external_provider = False
            monolithic_external_provider_skip_reason: Optional[str] = None
            suppress_post_pipeline_fallback = False
            post_pipeline_suppression_reason: Optional[str] = None
            pipeline_run_timeout_sec: Optional[float] = None
            pipeline_mode, _pipeline_factory = _resolve_pipeline_runtime_symbols()
            pipeline_disabled_by_scheduler = bool((research_task or {}).get('disable_pipeline_staged'))
            pipeline_disable_reason = str(
                (research_task or {}).get('pipeline_staged_skip_reason') or 'generator_mode_cooldown'
            ).strip()
            if targeted_research and target_context_blocked and allow_target_context_recovery:
                recovered_target_frame = await self._build_market_frame(db, research_task=research_task)
                if recovered_target_frame is not None and not recovered_target_frame.empty:
                    recovered_target_context = True
                    target_context_blocked = False
                    task_target_context = {
                        **task_target_context,
                        'status': 'recovered_from_explicit_target_frame',
                        'blocked_by_target_universe': False,
                        'matched_target_symbols': list(
                            self._normalize_code_list((research_task or {}).get('target_symbols'))
                        ),
                        'candidate_universe_symbols': list(
                            self._normalize_code_list((research_task or {}).get('target_symbols'))
                        ),
                    }
                    research_context = {
                        **research_context,
                        'blocked_by_target_universe': False,
                        'target_context_status': 'recovered_from_explicit_target_frame',
                        'task_target_context': task_target_context,
                    }
                    research_context_summary = self._summarize_research_context(research_context)
                else:
                    recovered_target_frame = None
            if targeted_research and target_context_blocked:
                if pipeline_mode == 'staged':
                    _pipeline_fallback_reason = 'target_context_blocked'
                report: dict[str, Any] = {
                    'requested_limit': requested_limit,
                    'market_frame_ready': False,
                    'market_frame_rows': 0,
                    'market_frame_source': 'target_context_blocked',
                    'research_context': research_context,
                    'research_context_summary': research_context_summary,
                    'external_provider': {
                        'enabled': bool(self.external_provider.is_enabled()),
                        'provider': getattr(self.external_provider.config, 'provider', None),
                        'model': getattr(self.external_provider.config, 'model', None),
                        'status': 'skipped_target_context_blocked',
                        'request_limits': [],
                        'requests': [],
                        'selected_count': 0,
                        'viable_selected_count': 0,
                        'fallback_count': 0,
                        'analysis': {},
                    },
                    'local_generator': {
                        'status': 'skipped_target_context_blocked',
                        'precompile_rejected_count': 0,
                        'precompile_rejections': [],
                    },
                    'selected_count': 0,
                    'selected_generators': {},
                    'research_task': dict(research_task or {}),
                    'pipeline_run_timeout_sec': None,
                }
                if _pipeline_fallback_reason:
                    report['pipeline_staged_fallback_reason'] = _pipeline_fallback_reason
                report['external_provider'] = _finalize_external_provider_report(report.get('external_provider'))
                self.last_report = report
                return []
            if pipeline_disabled_by_scheduler and pipeline_mode == 'staged':
                _pipeline_fallback_reason = pipeline_disable_reason or 'generator_mode_cooldown'
            elif pipeline_mode == 'staged' and self.external_provider.is_enabled():
                pipeline_run_timeout_sec = self._pipeline_run_timeout_sec()
                try:
                    staged_specs = await self._generate_via_pipeline(
                        db=db,
                        limit=limit,
                        snapshot=snapshot,
                        research_task=research_task,
                        timeout_sec=pipeline_run_timeout_sec,
                    )
                    if staged_specs:
                        return staged_specs
                    pipeline_report = dict(getattr(self, 'last_report', None) or {})
                    pipeline_fallback_counts = dict(pipeline_report.get('pipeline_fallback_counts') or {})
                    pipeline_stage_reasons = dict(pipeline_report.get('pipeline_stage_fallback_reasons') or {})
                    invalid_stage_ids = list(pipeline_report.get('pipeline_invalid_output_stage_ids') or [])
                    provider_output_format_failed = _pipeline_report_has_provider_output_format_failure(pipeline_report)
                    empty_reason = (
                        'invalid_output:' + ','.join(invalid_stage_ids)
                        if invalid_stage_ids
                        else 'no_executable_specs'
                    )
                    _pipeline_fallback_reason = f'returned_empty:{empty_reason}'
                    allow_empty_monolithic_fallback = str(
                        os.getenv('STRATEGY_FACTORY_ALLOW_PIPELINE_EMPTY_MONOLITHIC_FALLBACK', '0') or '0'
                    ).strip().lower() in {'1', 'true', 'yes', 'on'}
                    skip_empty_monolithic_fallback = str(
                        os.getenv('STRATEGY_FACTORY_PIPELINE_EMPTY_SKIP_MONOLITHIC_FALLBACK', '1') or '1'
                    ).strip().lower() in {'1', 'true', 'yes', 'on'}
                    if provider_output_format_failed:
                        suppress_post_pipeline_fallback = True
                        post_pipeline_suppression_reason = 'provider_output_format_failure'
                        logger.warning(
                            'Pipeline staged mode returned no specs after provider output format failure; '
                            'suppressing monolithic/local fallback. reason=%s stage_reasons=%s fallback_counts=%s',
                            empty_reason,
                            pipeline_stage_reasons,
                            pipeline_fallback_counts,
                        )
                    elif skip_empty_monolithic_fallback:
                        skip_monolithic_external_provider = True
                        monolithic_external_provider_skip_reason = 'staged_pipeline_empty'
                        logger.info(
                            'Pipeline staged mode returned no specs; skipping monolithic external provider '
                            'and continuing with local fallback. reason=%s stage_reasons=%s fallback_counts=%s',
                            empty_reason,
                            pipeline_stage_reasons,
                            pipeline_fallback_counts,
                        )
                    elif not allow_empty_monolithic_fallback:
                        suppress_post_pipeline_fallback = True
                        post_pipeline_suppression_reason = 'staged_pipeline_empty'
                        logger.warning(
                            'Pipeline staged mode returned no specs; suppressing monolithic/local fallback. '
                            'reason=%s stage_reasons=%s fallback_counts=%s',
                            empty_reason,
                            pipeline_stage_reasons,
                            pipeline_fallback_counts,
                        )
                    else:
                        logger.info(
                            'Pipeline staged mode returned no specs, falling back to monolithic; '
                            'reason=%s stage_reasons=%s fallback_counts=%s',
                            empty_reason,
                            pipeline_stage_reasons,
                            pipeline_fallback_counts,
                        )
                except asyncio.TimeoutError as exc:
                    _pipeline_fallback_reason = 'pipeline_timeout'
                    skip_monolithic_external_provider = True
                    monolithic_external_provider_skip_reason = 'pipeline_timeout'
                    suppress_post_pipeline_fallback = True
                    post_pipeline_suppression_reason = 'pipeline_timeout'
                    logger.warning(
                        'Pipeline staged mode timed out after %.1fs; suppressing monolithic/local fallback: %s',
                        float(pipeline_run_timeout_sec or 0.0),
                        exc,
                    )
                except Exception as exc:
                    _pipeline_fallback_reason = f'{type(exc).__name__}: {exc}'
                    suppress_post_pipeline_fallback = True
                    post_pipeline_suppression_reason = 'pipeline_exception'
                    logger.warning('Pipeline staged mode failed: %s; suppressing monolithic/local fallback', exc)

            frame = recovered_target_frame
            frame_source = (
                'recovered_explicit_target_frame'
                if recovered_target_context and frame is not None and not frame.empty
                else 'none'
            )
            if frame is None or frame.empty:
                frame = await self._build_market_frame(db, research_task=research_task)
                frame_source = 'primary_market_frame' if frame is not None and not frame.empty else 'none'
            frame_cache = await self._build_symbol_frame_cache(db, research_context=research_context, research_task=research_task)
            if (frame is None or frame.empty) and frame_cache:
                for cached_frame in frame_cache.values():
                    if cached_frame is not None and not cached_frame.empty:
                        frame = cached_frame.tail(120).copy()
                        frame_source = 'research_context_frame_cache'
                        break
            if frame is None or frame.empty:
                synthetic_frame = self._build_synthetic_market_frame(research_context)
                if synthetic_frame is not None and not synthetic_frame.empty:
                    frame = synthetic_frame
                    frame_source = 'synthetic_research_context_frame'
            pipeline_report = dict(getattr(self, 'last_report', None) or {}) if _pipeline_fallback_reason else {}
            report: dict[str, Any] = {
                'requested_limit': requested_limit,
                'market_frame_ready': bool(frame is not None and not frame.empty),
                'market_frame_rows': int(len(frame)) if frame is not None and not frame.empty else 0,
                'market_frame_source': frame_source,
                'research_context': research_context,
                'research_context_summary': research_context_summary,
                'external_provider': {
                    'enabled': bool(self.external_provider.is_enabled()),
                    'provider': getattr(self.external_provider.config, 'provider', None),
                    'model': getattr(self.external_provider.config, 'model', None),
                    'status': 'skipped',
                    'request_limits': [],
                    'requests': [],
                    'selected_count': 0,
                    'viable_selected_count': 0,
                    'fallback_count': 0,
                    'analysis': {},
                },
                'local_generator': {
                    'status': 'pending',
                    'precompile_rejected_count': 0,
                    'precompile_rejections': [],
                },
                'selected_count': 0,
                'selected_generators': {},
                'research_task': dict(research_task or {}),
                'pipeline_run_timeout_sec': round(float(pipeline_run_timeout_sec or 0.0), 4) if pipeline_run_timeout_sec is not None else None,
                'pipeline_staged_fallback_reason': _pipeline_fallback_reason,
                'pipeline_staged_fallback_counts': dict(pipeline_report.get('pipeline_fallback_counts') or {}),
                'pipeline_staged_stage_fallback_reasons': dict(
                    pipeline_report.get('pipeline_stage_fallback_reasons') or {}
                ),
                'pipeline_staged_invalid_output_stage_ids': list(
                    pipeline_report.get('pipeline_invalid_output_stage_ids') or []
                ),
                'pipeline_staged_provenance': pipeline_report.get('pipeline_provenance'),
                'pipeline_staged_error': pipeline_report.get('pipeline_error'),
                'post_pipeline_fallback_suppressed': bool(suppress_post_pipeline_fallback),
                'post_pipeline_suppression_reason': post_pipeline_suppression_reason,
            }
            external_specs: list[StrategySpec] = []
            fallback_external_specs: list[StrategySpec] = []
            if suppress_post_pipeline_fallback:
                if post_pipeline_suppression_reason == 'provider_output_format_failure':
                    status = 'failed_output_format'
                    error_type = 'ProviderOutputFormatFailure'
                    error_text = 'staged pipeline provider output format failed; monolithic/local fallback suppressed for this task'
                elif post_pipeline_suppression_reason == 'pipeline_timeout':
                    status = 'skipped_after_pipeline_timeout'
                    error_type = 'PipelineTimeout'
                    error_text = 'staged pipeline timed out; monolithic/local fallback suppressed for this task'
                elif post_pipeline_suppression_reason == 'pipeline_exception':
                    status = 'failed'
                    error_type = 'PipelineFailure'
                    error_text = 'staged pipeline failed; monolithic/local fallback suppressed for this task'
                else:
                    status = 'non_executable'
                    error_type = 'NoExecutableCandidates'
                    error_text = 'staged pipeline returned no executable specs; monolithic/local fallback suppressed for this task'
                report['external_provider']['status'] = status
                report['external_provider']['last_error_type'] = error_type
                report['external_provider']['last_error'] = error_text
                report['external_provider']['monolithic_fallback_suppressed'] = True
                report['external_provider']['local_fallback_suppressed'] = True
                report['local_generator']['status'] = 'skipped_after_pipeline_failure'
                report['local_generator']['local_fallback_suppressed'] = True
                report['external_provider'] = _finalize_external_provider_report(report.get('external_provider'))
                self.last_report = report
                return []
            if skip_monolithic_external_provider:
                if monolithic_external_provider_skip_reason == 'staged_pipeline_empty':
                    report['external_provider']['status'] = 'skipped_after_pipeline_empty'
                    report['external_provider']['last_error_type'] = 'NoExecutableCandidates'
                    report['external_provider']['last_error'] = (
                        'staged pipeline returned no executable specs; monolithic external provider skipped '
                        'and local fallback allowed for this task'
                    )
                else:
                    report['external_provider']['status'] = 'skipped_after_pipeline_timeout'
                    report['external_provider']['last_error_type'] = 'PipelineTimeout'
                    report['external_provider']['last_error'] = 'staged pipeline timed out; monolithic external provider skipped for this task'
                report['external_provider']['monolithic_external_provider_skipped'] = True
                report['external_provider']['monolithic_external_provider_skip_reason'] = (
                    monolithic_external_provider_skip_reason or 'pipeline_timeout'
                )
            elif frame is not None and not frame.empty and self.external_provider.is_enabled():
                base_request_limit = max(2, min(int(limit or 3), 3))
                request_limits = [base_request_limit for _ in range(max(1, min(int(LLM_FAN_OUT_COUNT or 1), 4)))]
                report['external_provider']['request_limits'] = list(request_limits)
                last_exc: Optional[Exception] = None
                successful_request_without_specs = False
                external_started_at = time.perf_counter()
                request_results = await asyncio.gather(*[
                    self._run_external_provider_request(
                        snapshot=snapshot,
                        frame=frame,
                        frame_cache=frame_cache,
                        research_context=research_context,
                        parent_strategies=list(parent_strategies or []),
                        history_summary=history_summary,
                        research_task=research_task,
                        request_limit=request_limit,
                        request_index=request_index,
                    )
                    for request_index, request_limit in enumerate(request_limits, 1)
                ])
                aggregated_viable_specs: list[StrategySpec] = []
                aggregated_all_specs: list[StrategySpec] = []
                for result in sorted(request_results, key=lambda item: int(item.get('request_index') or 0)):
                    report['external_provider']['requests'].append(dict(result.get('request_report') or {}))
                    successful_request_without_specs = successful_request_without_specs or bool(result.get('successful_without_specs'))
                    aggregated_viable_specs.extend(list(result.get('viable_specs') or []))
                    aggregated_all_specs.extend(list(result.get('all_specs') or []))
                    analysis = dict(result.get('analysis') or {})
                    if analysis and not report['external_provider']['analysis']:
                        report['external_provider']['analysis'] = analysis
                    if result.get('status') == 'failed' and result.get('exception') is not None:
                        last_exc = result.get('exception')
                aggregated_viable_specs = self._dedupe_specs(sorted(aggregated_viable_specs, key=self._spec_preflight_score, reverse=True))
                aggregated_all_specs = self._dedupe_specs(sorted(aggregated_all_specs, key=self._spec_preflight_score, reverse=True))
                open_dsl_cap = open_dsl_max_candidates_per_run()

                def _apply_open_dsl_cap(specs: list[StrategySpec]) -> tuple[list[StrategySpec], int, int]:
                    if open_dsl_cap < 0:
                        return list(specs), 0, 0
                    capped: list[StrategySpec] = []
                    selected_open_dsl = 0
                    overflow = 0
                    for spec in list(specs or []):
                        if is_open_dsl_spec_metadata(dict(spec.metadata or {})):
                            if selected_open_dsl >= open_dsl_cap:
                                overflow += 1
                                continue
                            selected_open_dsl += 1
                        capped.append(spec)
                    return capped, selected_open_dsl, overflow

                aggregated_viable_specs, open_dsl_viable_selected_count, open_dsl_viable_overflow_count = _apply_open_dsl_cap(
                    aggregated_viable_specs
                )
                aggregated_all_specs, _open_dsl_all_selected_count, open_dsl_all_overflow_count = _apply_open_dsl_cap(
                    aggregated_all_specs
                )
                if aggregated_viable_specs:
                    external_specs = aggregated_viable_specs[:limit]
                    selected_keys = {
                        (str(spec.strategy_type or ''), json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str))
                        for spec in external_specs
                    }
                    fallback_external_specs = [
                        spec for spec in aggregated_all_specs
                        if (
                            str(spec.strategy_type or ''),
                            json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str),
                        ) not in selected_keys
                    ]
                elif aggregated_all_specs:
                    fallback_external_specs = aggregated_all_specs[:limit]
                report['external_provider']['elapsed_seconds'] = round(time.perf_counter() - external_started_at, 4)
                report['external_provider']['viable_selected_count'] = len(external_specs)
                report['external_provider']['fallback_count'] = len(fallback_external_specs)
                report['external_provider']['open_dsl_max_candidates_per_run'] = open_dsl_cap
                report['external_provider']['open_dsl_viable_selected_count'] = open_dsl_viable_selected_count
                report['external_provider']['open_dsl_selected_count'] = sum(
                    1 for spec in [*external_specs, *fallback_external_specs]
                    if is_open_dsl_spec_metadata(dict(spec.metadata or {}))
                )
                report['external_provider']['open_dsl_overflow_count'] = max(
                    open_dsl_viable_overflow_count,
                    open_dsl_all_overflow_count,
                )
                if external_specs:
                    report['external_provider']['status'] = 'succeeded'
                elif fallback_external_specs:
                    report['external_provider']['status'] = 'fallback_only'
                elif successful_request_without_specs:
                    report['external_provider']['status'] = 'non_executable'
                    report['external_provider']['last_error_type'] = 'NoExecutableCandidates'
                    report['external_provider']['last_error'] = 'external llm returned candidates but none compiled into executable strategies'
                elif last_exc is not None:
                    report['external_provider']['status'] = 'failed'
                    last_metrics = dict(getattr(last_exc, 'metrics', {}) or {})
                    report['external_provider']['last_error_type'] = last_metrics.get('last_error_type') or last_exc.__class__.__name__
                    report['external_provider']['last_error'] = last_metrics.get('last_error') or str(last_exc) or last_exc.__class__.__name__
                if self.external_provider.config.strict and last_exc is not None and not external_specs and not fallback_external_specs:
                    self.last_report = report
                    raise last_exc

            if frame is None or frame.empty:
                selected = (external_specs or fallback_external_specs)[:limit]
                generator_counts: dict[str, int] = {}
                for spec in selected:
                    generator_type = str(spec.metadata.get('generator_type') or 'unknown')
                    generator_counts[generator_type] = generator_counts.get(generator_type, 0) + 1
                report['selected_count'] = len(selected)
                report['selected_generators'] = generator_counts
                report['external_provider']['selected_count'] = generator_counts.get('external_llm', 0)
                report['local_generator']['status'] = 'skipped_no_market_frame'
                report['external_provider'] = _finalize_external_provider_report(report.get('external_provider'))
                self.last_report = report
                return selected
            local_specs: list[StrategySpec] = []
            allow_local_specs = not targeted_research or (not external_specs and not fallback_external_specs)
            if allow_local_specs:
                report['local_generator']['status'] = 'running'
                local_limit = limit
                if targeted_research and str((research_task or {}).get('task_source') or '').strip().lower() == 'event_driven':
                    local_limit = 1
                raw = self.miner.generate_factor_candidates(frame, news_data=None, num_candidates=max(local_limit, 3))
                raw = sorted(
                    raw,
                    key=lambda item: self._local_category_rank(str((item or {}).get('category') or 'custom').strip().lower(), research_task=research_task),
                )
                for candidate in raw:
                    spec = self._local_candidate_to_spec(candidate, research_task=research_task)
                    if spec is not None:
                        local_specs.append(spec)
                    elif candidate.get("_generator_precompile_reject_reasons"):
                        report['local_generator']['precompile_rejected_count'] += 1
                        if len(report['local_generator']['precompile_rejections']) < 8:
                            report['local_generator']['precompile_rejections'].append(
                                {
                                    'name': str(candidate.get('name') or ''),
                                    'category': str(candidate.get('category') or ''),
                                    'reject_reasons': list(candidate.get("_generator_precompile_reject_reasons") or []),
                                }
                            )
                    if len(local_specs) >= local_limit:
                        break
                report['local_generator']['status'] = 'succeeded' if local_specs else 'empty'
            else:
                report['local_generator']['status'] = 'skipped_external_selected'
            if len(external_specs) >= limit:
                selected = external_specs[:limit]
                generator_counts: dict[str, int] = {}
                for spec in selected:
                    generator_type = str(spec.metadata.get('generator_type') or 'unknown')
                    generator_counts[generator_type] = generator_counts.get(generator_type, 0) + 1
                report['selected_count'] = len(selected)
                report['selected_generators'] = generator_counts
                report['external_provider']['selected_count'] = generator_counts.get('external_llm', 0)
                self.last_report = report
                return selected
            merged: list[StrategySpec] = []
            seen = set()
            if self.external_provider.config.strict:
                fallback_order = [*external_specs, *fallback_external_specs, *local_specs]
            else:
                preferred_external = fallback_external_specs[:1]
                remaining_external = fallback_external_specs[1:]
                fallback_order = [*external_specs, *preferred_external, *local_specs, *remaining_external]
            for spec in fallback_order:
                key = (spec.strategy_type, json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(spec)
                if len(merged) >= limit:
                    break
            generator_counts: dict[str, int] = {}
            for spec in merged:
                generator_type = str(spec.metadata.get('generator_type') or 'unknown')
                generator_counts[generator_type] = generator_counts.get(generator_type, 0) + 1
            report['selected_count'] = len(merged)
            report['selected_generators'] = generator_counts
            report['external_provider']['selected_count'] = generator_counts.get('external_llm', 0)
            if _pipeline_fallback_reason:
                report['pipeline_staged_fallback_reason'] = _pipeline_fallback_reason
                pipeline_report = getattr(self, 'last_report', None) or {}
                report['pipeline_staged_provenance'] = pipeline_report.get('pipeline_provenance')
                report['pipeline_staged_error'] = pipeline_report.get('pipeline_error')
            report['external_provider'] = _finalize_external_provider_report(report.get('external_provider'))
            self.last_report = report
            return merged
