
    @staticmethod
    def _build_submission_result(auto_submit: bool, submit_result: Optional[dict], candidates: list[dict]) -> dict:
        payload = dict(submit_result or {})
        items = list(payload.get('items') or payload.get('strategies') or [])
        submitted_count = int(payload.get('submitted', len(items) if auto_submit and items else 0))
        inferred_passed_count = len([item for item in items if item.get('passed')])
        passed_count = int(payload.get('gate_3_passed', payload.get('passed_quality_gate', inferred_passed_count)))
        failed_count = int(payload.get('gate_3_failed', max(submitted_count - passed_count, 0)))
        return {
            'auto_submit': auto_submit,
            'attempted': bool(auto_submit and candidates),
            'submitted_count': submitted_count,
            'passed_count': passed_count,
            'failed_count': failed_count,
            'provisional_passed_count': int(payload.get('gate_3_provisional_passed', 0)),
            'failure_reason_topn': list(payload.get('gate_3_failure_reason_topn') or []),
            'items': items,
            'result': payload or None,
        }

    @staticmethod
    def _build_task_run_result(task_run: dict, *, source: str, snapshot_date: Any, research_task: dict, event_context: dict) -> dict:
        return {
            'id': task_run.get('id'),
            'trace_id': task_run.get('trace_id'),
            'status': 'completed',
            'source': source,
            'snapshot_date': snapshot_date,
            'research_task': research_task,
            'event_context': event_context,
        }

    @classmethod
    def _build_task_run_result_summary(
        cls,
        *,
        task_run: dict,
        status: str,
        source: str,
        snapshot_date: Any,
        research_task: Optional[dict[str, Any]],
        event_context: Optional[dict[str, Any]],
        factor_research: Optional[dict[str, Any]],
        full_result: dict[str, Any],
        artifact_info: Optional[dict[str, Any]],
        error: Optional[str] = None,
    ) -> dict[str, Any]:
        generation_result = dict(full_result.get('generation') or {})
        review_result = dict(full_result.get('review') or {})
        experiments_result = dict(full_result.get('experiments') or {})
        submission_result = dict(full_result.get('submission') or {})
        summary = {
            'storage_mode': 'summary_with_external_payload' if artifact_info else 'summary_only',
            'task_run_id': task_run.get('id'),
            'trace_id': task_run.get('trace_id'),
            'status': status,
            'source': source,
            'snapshot_date': snapshot_date,
            'task_source': dict(research_task or {}).get('task_source'),
            'research_task': cls._summarize_research_task(
                research_task,
                factor_research=factor_research,
            ),
            'event_context': cls._summarize_event_context(event_context),
            'factor_research': cls._summarize_factor_research(factor_research),
            'generated_count': int(
                full_result.get('generated_count')
                or generation_result.get('count')
                or 0
            ),
            'reviewed_count': int(
                full_result.get('reviewed_count')
                or review_result.get('reviewed_count')
                or 0
            ),
            'rejected_count': int(
                full_result.get('rejected_count')
                or review_result.get('rejected_count')
                or 0
            ),
            'generation': cls._summarize_generation_result(generation_result),
            'review': cls._summarize_review_result(review_result),
            'experiments': cls._summarize_experiments_result(experiments_result),
            'submission': cls._summarize_submission_result(submission_result),
            'champion': cls._compact_dict(
                dict(full_result.get('champion') or review_result.get('champion') or {}),
                keys=('experiment_id', 'generated_strategy_id', 'status', 'review_rank', 'final_score'),
            ),
            'lifecycle': dict(full_result.get('lifecycle') or {}),
        }
        if artifact_info:
            summary['full_result_artifact'] = dict(artifact_info)
        if error:
            summary['error'] = error
        return summary

    @staticmethod
    def _build_cycle_result(
        *,
        task_run_result: dict,
        generation_result: dict,
        review_result: dict,
        experiments_result: dict,
        submission_result: dict,
        snapshot_date: Any,
        research_task: dict,
        factor_research: dict,
        event_context: dict,
        lifecycle: dict,
    ) -> dict:
        experiment_items = list(experiments_result.get('items') or [])
        return {
            'task_run': task_run_result,
            'generation': generation_result,
            'review': review_result,
            'experiments': experiments_result,
            'submission': submission_result,
            'lifecycle': lifecycle,
            'task_run_id': task_run_result.get('id'),
            'snapshot_date': snapshot_date,
            'research_task': research_task,
            'factor_research': factor_research,
            'generated_count': generation_result.get('count', 0),
            'reviewed_count': review_result.get('reviewed_count', 0),
            'rejected_count': review_result.get('rejected_count', 0),
            'committee_reviews': list(review_result.get('committee_reviews') or []),
            'candidates': list(generation_result.get('candidates') or []),
            'experiment_records': experiment_items,
            'champion': review_result.get('champion'),
            'submitted': submission_result.get('result'),
            'llm_generation': generation_result.get('llm_generation') or {},
            'event_context': event_context,
            'generation_stats': generation_result.get('stats') or {},
            'artifacts': {
                'experiments': experiment_items,
            },
        }


    async def _prepare_cycle_context(
        self,
        db,
        *,
        snapshot: Optional[dict],
        research_task: Optional[dict[str, Any]],
    ) -> tuple[dict, dict, dict, dict]:
        resolved_snapshot = snapshot or (
            await db.get_daily_snapshot() if hasattr(db, 'get_daily_snapshot') else None
        ) or {'date': str(date.today())}
        resolved_task = dict(research_task or {})
        factor_research = dict(resolved_snapshot.get('factor_research') or {})
        task_metadata = dict(resolved_task.get('metadata') or {})
        task_factor_research = (
            task_metadata.get('factor_research')
            if isinstance(task_metadata.get('factor_research'), dict)
            else factor_research
        )
        if task_factor_research:
            task_metadata['factor_research'] = dict(task_factor_research)
        elif task_metadata.get('factor_research') not in (None, '', [], {}):
            task_metadata.pop('factor_research', None)
        if task_metadata:
            resolved_task = {**resolved_task, 'metadata': task_metadata}
        event_context = _extract_event_context(resolved_task)
        return resolved_snapshot, resolved_task, factor_research, event_context

    async def _create_cycle_task_run(
        self,
        db,
        *,
        parent_strategy_id: Optional[str],
        source: str,
        limit: int,
        snapshot: dict,
        research_task: dict,
        event_context: dict,
        auto_submit: bool,
    ) -> dict:
        trace_id = uuid4().hex[:12]
        payload = {
            'strategy_id': parent_strategy_id,
            'task_name': 'strategy_ai_cycle',
            'task_scope': source,
            'task_key': research_task.get('task_key') or parent_strategy_id or str(snapshot.get('date') or date.today()),
            'status': 'running',
            'trace_id': trace_id,
            'payload': {
                'limit': limit,
                'parent_strategy_id': parent_strategy_id,
                'snapshot_date': snapshot.get('date'),
                'research_task': research_task,
                'event_context': event_context,
                'auto_submit': auto_submit,
            },
        }
        try:
            persisted = await db.save_strategy_task_run(payload)
        except Exception as exc:
            logger.warning(
                'StrategyAutonomyService: save task run failed, continuing without persistence: %s',
                exc,
            )
            return {
                'id': None,
                'trace_id': trace_id,
                'persistence_error': str(exc),
            }
        if not isinstance(persisted, dict):
            persisted = {}
        return {
            'id': persisted.get('id'),
            'trace_id': persisted.get('trace_id') or trace_id,
            **persisted,
        }

    async def _run_cycle_pipeline(
        self,
        db,
        *,
        snapshot: dict,
        limit: int,
        source: str,
        parent_strategy_id: Optional[str],
        research_task: dict,
        task_run: dict,
        auto_submit: bool,
        lifecycle: AutonomyLifecycleTracker,
    ) -> dict:
        lifecycle.enter_phase('generating', detail={
            'source': source,
            'limit': int(limit or 0),
            'parent_strategy_id': parent_strategy_id,
        })
        generation_batch = await self.generation_service.generate(
            db,
            snapshot=snapshot,
            limit=limit,
            research_task=research_task,
            parent_strategy_id=parent_strategy_id,
        )
        llm_report = dict(generation_batch.get('llm_report') or {})
        rule_specs = list(generation_batch.get('rule_specs') or [])
        llm_specs = list(generation_batch.get('llm_specs') or [])
        evolved_specs = list(generation_batch.get('evolved_specs') or [])
        merged_specs = list(generation_batch.get('merged_specs') or [])
        lifecycle.complete_phase('generating', metrics={
            'rule_count': len(rule_specs),
            'llm_count': len(llm_specs),
            'evolved_count': len(evolved_specs),
            'merged_count': len(merged_specs),
        })

        lifecycle.enter_phase('reviewing', detail={'candidate_count': len(merged_specs)})
        review_batch = self.review_service.review_candidates(
            merged_specs,
            snapshot=snapshot,
            parent_strategy_id=parent_strategy_id,
            task_run_id=task_run.get('id'),
        )
        reviewed_specs = list(review_batch.get('reviewed_specs') or [])
        committee_reviews = list(review_batch.get('committee_reviews') or [])
        rejected_count = int(review_batch.get('rejected_count') or 0)
        lifecycle.complete_phase('reviewing', metrics={
            'reviewed_count': len(reviewed_specs),
            'rejected_count': rejected_count,
            'committee_review_count': len(committee_reviews),
        })

        lifecycle.enter_phase('recording', detail={'reviewed_count': len(reviewed_specs)})
        experiment_batch = await self.experiment_recorder.record_candidates(
            db,
            reviewed_specs,
            source=source,
            snapshot=snapshot,
            task_run=task_run,
        )
        experiments = list(experiment_batch.get('experiments') or [])
        candidates = list(experiment_batch.get('candidates') or [])
        champion = dict(experiment_batch.get('champion') or {}) or None
        lifecycle.complete_phase('recording', metrics={
            'experiment_count': len(experiments),
            'candidate_count': len(candidates),
            'champion_present': champion is not None,
        })

        submit_result = None
        if auto_submit and candidates:
            lifecycle.enter_phase('submitting', detail={'candidate_count': len(candidates)})
            from strategy_factory import StrategySubmitter
            submit_result = await StrategySubmitter().submit(candidates, snapshot, db)
            submission_batch = await self.experiment_recorder.apply_submission_results(db, experiments, submit_result)
            experiments = list(submission_batch.get('experiments') or [])
            by_experiment = dict(submission_batch.get('items_by_experiment') or {})
            if champion is not None:
                champion_item = by_experiment.get(champion.get('experiment_id')) or {}
                champion['generated_strategy_id'] = champion_item.get('strategy_id')
                champion['status'] = 'accepted' if champion_item.get('passed') else 'rejected'
            lifecycle.complete_phase('submitting', metrics=self._submission_metrics(submit_result))
        elif auto_submit:
            lifecycle.skip_phase('submitting', reason='no_candidates')
        else:
            lifecycle.skip_phase('submitting', reason='auto_submit_disabled')

        return {
            'llm_report': llm_report,
            'rule_specs': rule_specs,
            'llm_specs': llm_specs,
            'evolved_specs': evolved_specs,
            'merged_specs': merged_specs,
            'reviewed_specs': reviewed_specs,
            'committee_reviews': committee_reviews,
            'rejected_count': rejected_count,
            'experiments': experiments,
            'candidates': candidates,
            'champion': champion,
            'submit_result': submit_result,
        }

    async def _save_cycle_completed_event(
        self,
        db,
        *,
        parent_strategy_id: Optional[str],
        task_run: dict,
        snapshot: dict,
        source: str,
        candidates: list[dict],
        reviewed_specs: list[StrategySpec],
        rejected_count: int,
        champion: Optional[dict[str, Any]],
        research_task: dict,
        event_context: dict,
        factor_research: dict,
        lifecycle: dict,
    ) -> None:
        if not hasattr(db, 'save_strategy_domain_event'):
            return
        try:
            await db.save_strategy_domain_event({
            'strategy_id': parent_strategy_id,
            'aggregate_type': 'strategy_ai_cycle',
            'aggregate_id': str(task_run.get('id') or snapshot.get('date') or date.today()),
            'event_type': 'strategy_ai_cycle.completed',
            'source': source,
            'severity': 'info',
            'correlation_id': task_run.get('trace_id'),
            'payload': {
                'generated_count': len(candidates),
                'reviewed_count': len(reviewed_specs),
                'rejected_count': rejected_count,
                'task_run_id': task_run.get('id'),
                'champion_experiment_id': (champion or {}).get('experiment_id'),
                'research_task': research_task,
                'event_context': event_context,
                'factor_research': factor_research,
                'lifecycle': lifecycle,
            },
            })
        except Exception as exc:
            logger.warning(
                'StrategyAutonomyService: save completed domain event failed, continuing: %s',
                exc,
            )

    async def _save_cycle_failed_event(
        self,
        db,
        *,
        parent_strategy_id: Optional[str],
        task_run: dict,
        snapshot: dict,
        source: str,
        research_task: dict,
        event_context: dict,
        factor_research: dict,
        lifecycle: dict,
        error: str,
    ) -> None:
        if not hasattr(db, 'save_strategy_domain_event'):
            return
        try:
            await db.save_strategy_domain_event({
            'strategy_id': parent_strategy_id,
            'aggregate_type': 'strategy_ai_cycle',
            'aggregate_id': str(task_run.get('id') or snapshot.get('date') or date.today()),
            'event_type': 'strategy_ai_cycle.failed',
            'source': source,
            'severity': 'error',
            'correlation_id': task_run.get('trace_id'),
            'payload': {
                'task_run_id': task_run.get('id'),
                'snapshot_date': snapshot.get('date'),
                'research_task': research_task,
                'event_context': event_context,
                'factor_research': factor_research,
                'lifecycle': lifecycle,
                'error': error,
            },
            })
        except Exception as exc:
            logger.warning(
                'StrategyAutonomyService: save failed domain event failed, continuing: %s',
                exc,
            )
