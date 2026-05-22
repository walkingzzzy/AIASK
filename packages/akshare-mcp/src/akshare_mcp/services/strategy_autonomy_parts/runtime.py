

    async def run_cycle(
        self,
        db,
        snapshot: Optional[dict] = None,
        limit: int = 3,
        source: str = 'manual',
        parent_strategy_id: Optional[str] = None,
        auto_submit: bool = False,
        research_task: Optional[dict[str, Any]] = None,
    ) -> dict:
        snapshot, research_task, factor_research, event_context = await self._prepare_cycle_context(
            db,
            snapshot=snapshot,
            research_task=research_task,
        )
        lifecycle = AutonomyLifecycleTracker(auto_submit=auto_submit)
        task_run = {'id': None, 'trace_id': None}
        try:
            lifecycle.enter_phase('prepared', detail={
                'source': source,
                'snapshot_date': snapshot.get('date'),
                'task_source': research_task.get('task_source'),
            })
            task_run = await self._create_cycle_task_run(
                db,
                parent_strategy_id=parent_strategy_id,
                source=source,
                limit=limit,
                snapshot=snapshot,
                research_task=research_task,
                event_context=event_context,
                auto_submit=auto_submit,
            )
            lifecycle.complete_phase('prepared', metrics={
                'task_run_id': task_run.get('id'),
                'snapshot_date': snapshot.get('date'),
                'auto_submit': bool(auto_submit),
            })
            pipeline = await self._run_cycle_pipeline(
                db,
                snapshot=snapshot,
                limit=limit,
                source=source,
                parent_strategy_id=parent_strategy_id,
                research_task=research_task,
                task_run=task_run,
                auto_submit=auto_submit,
                lifecycle=lifecycle,
            )
            llm_report = dict(pipeline.get('llm_report') or {})
            rule_specs = list(pipeline.get('rule_specs') or [])
            llm_specs = list(pipeline.get('llm_specs') or [])
            evolved_specs = list(pipeline.get('evolved_specs') or [])
            merged_specs = list(pipeline.get('merged_specs') or [])
            reviewed_specs = list(pipeline.get('reviewed_specs') or [])
            committee_reviews = list(pipeline.get('committee_reviews') or [])
            rejected_count = int(pipeline.get('rejected_count') or 0)
            experiments = list(pipeline.get('experiments') or [])
            candidates = list(pipeline.get('candidates') or [])
            champion = dict(pipeline.get('champion') or {}) or None
            submit_result = pipeline.get('submit_result')
            lifecycle.enter_phase('completed', detail={
                'generated_count': len(candidates),
                'experiment_count': len(experiments),
            })

            generation_stats = {
                'rule_count': len(rule_specs),
                'llm_count': len(llm_specs),
                'evolved_count': len(evolved_specs),
                'merged_count': len(merged_specs),
                'llm_generation': llm_report,
                'research_task': research_task,
                'event_context': event_context,
                'factor_research': factor_research,
            }
            lifecycle.complete_phase('completed', metrics={
                'generated_count': len(candidates),
                'reviewed_count': len(reviewed_specs),
                'experiment_count': len(experiments),
                **self._submission_metrics(submit_result),
            })
            lifecycle_result = lifecycle.snapshot()
            task_run_result = self._build_task_run_result(
                task_run,
                source=source,
                snapshot_date=snapshot.get('date'),
                research_task=research_task,
                event_context=event_context,
            )
            task_run_result['lifecycle'] = lifecycle_result
            generation_result = self._build_generation_result(candidates, generation_stats, llm_report)
            review_result = self._build_review_result(reviewed_specs, rejected_count, committee_reviews, champion)
            experiments_result = self._build_experiments_result(experiments)
            submission_result = self._build_submission_result(auto_submit, submit_result, candidates)
            result = self._build_cycle_result(
                task_run_result=task_run_result,
                generation_result=generation_result,
                review_result=review_result,
                experiments_result=experiments_result,
                submission_result=submission_result,
                snapshot_date=snapshot.get('date'),
                research_task=research_task,
                factor_research=factor_research,
                event_context=event_context,
                lifecycle=lifecycle_result,
            )
            await self._save_cycle_completed_event(
                db,
                parent_strategy_id=parent_strategy_id,
                task_run=task_run,
                snapshot=snapshot,
                source=source,
                candidates=candidates,
                reviewed_specs=reviewed_specs,
                rejected_count=rejected_count,
                champion=champion,
                research_task=research_task,
                event_context=event_context,
                factor_research=factor_research,
                lifecycle=lifecycle_result,
            )
            if task_run.get('id') is not None:
                task_run_summary = self._build_task_run_result_summary(
                    task_run=task_run,
                    status='completed',
                    source=source,
                    snapshot_date=snapshot.get('date'),
                    research_task=research_task,
                    event_context=event_context,
                    factor_research=factor_research,
                    full_result=result,
                    artifact_info=None,
                )
                await db.update_strategy_task_run(
                    task_run['id'],
                    status='completed',
                    result=task_run_summary,
                )
            return result
        except asyncio.CancelledError as exc:
            cancellation_reason = 'cancelled'
            lifecycle.fail_phase(error=RuntimeError(cancellation_reason))
            lifecycle_result = lifecycle.snapshot()
            logger.warning(
                'StrategyAutonomyService.run_cycle cancelled '
                'task_run_id=%s source=%s task_key=%s phase=%s',
                task_run.get('id'),
                source,
                dict(research_task or {}).get('task_key'),
                lifecycle_result.get('current_phase'),
            )
            logger.debug('StrategyAutonomyService.run_cycle cancellation traceback', exc_info=True)
            if task_run.get('id') is not None:
                failure_result = {
                    'status': 'failed',
                    'snapshot_date': snapshot.get('date'),
                    'research_task': research_task,
                    'event_context': event_context,
                    'factor_research': factor_research,
                    'lifecycle': lifecycle_result,
                    'error': cancellation_reason,
                    'cancelled': True,
                }
                try:
                    await db.update_strategy_task_run(
                        task_run['id'],
                        status='failed',
                        error=cancellation_reason,
                        result=self._build_task_run_result_summary(
                            task_run=task_run,
                            status='failed',
                            source=source,
                            snapshot_date=snapshot.get('date'),
                            research_task=research_task,
                            event_context=event_context,
                            factor_research=factor_research,
                            full_result=failure_result,
                            artifact_info=None,
                            error=cancellation_reason,
                        ),
                    )
                    await self._save_cycle_failed_event(
                        db,
                        parent_strategy_id=parent_strategy_id,
                        task_run=task_run,
                        snapshot=snapshot,
                        source=source,
                        research_task=research_task,
                        event_context=event_context,
                        factor_research=factor_research,
                        lifecycle=lifecycle_result,
                        error=cancellation_reason,
                    )
                except Exception as cleanup_exc:
                    logger.debug(
                        'StrategyAutonomyService.run_cycle cancellation cleanup failed: %s',
                        cleanup_exc,
                        exc_info=True,
                    )
            setattr(exc, 'autonomy_lifecycle', lifecycle_result)
            setattr(exc, 'autonomy_task_run_id', task_run.get('id'))
            raise
        except Exception as exc:
            lifecycle.fail_phase(error=exc)
            lifecycle_result = lifecycle.snapshot()
            logger.error('StrategyAutonomyService.run_cycle failed: %s', exc, exc_info=True)
            if task_run.get('id') is not None:
                failure_result = {
                    'status': 'failed',
                    'snapshot_date': snapshot.get('date'),
                    'research_task': research_task,
                    'event_context': event_context,
                    'factor_research': factor_research,
                    'lifecycle': lifecycle_result,
                    'error': str(exc),
                }
                await db.update_strategy_task_run(
                    task_run['id'],
                    status='failed',
                    error=str(exc),
                    result=self._build_task_run_result_summary(
                        task_run=task_run,
                        status='failed',
                        source=source,
                        snapshot_date=snapshot.get('date'),
                        research_task=research_task,
                        event_context=event_context,
                        factor_research=factor_research,
                        full_result=failure_result,
                        artifact_info=None,
                        error=str(exc),
                    ),
                )
            await self._save_cycle_failed_event(
                db,
                parent_strategy_id=parent_strategy_id,
                task_run=task_run,
                snapshot=snapshot,
                source=source,
                research_task=research_task,
                event_context=event_context,
                factor_research=factor_research,
                lifecycle=lifecycle_result,
                error=str(exc),
            )
            setattr(exc, 'autonomy_lifecycle', lifecycle_result)
            setattr(exc, 'autonomy_task_run_id', task_run.get('id'))
            raise
