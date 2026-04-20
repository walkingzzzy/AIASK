type ObservabilitySection = {
  data: Record<string, unknown>;
  error: string | null;
};

export type StrategyServiceFactoryObservabilityDeps = {
  factoryStatus: () => Promise<unknown>;
  factoryRuns: (limit?: number) => Promise<unknown>;
  callQuantManager: (action: string, params?: Record<string, unknown>) => Promise<unknown>;
  flattenMcpResult: (payload: unknown) => Record<string, unknown>;
  unwrapSettledObject: (result: PromiseSettledResult<unknown>, section: string) => ObservabilitySection;
  asRecord: (value: unknown) => Record<string, unknown>;
  asRecordArray: (value: unknown) => Record<string, unknown>[];
  toNum: (value: unknown) => number | null;
};

export async function loadFactoryObservability(
  deps: StrategyServiceFactoryObservabilityDeps,
) {
  const sections = await Promise.allSettled([
    deps.factoryStatus(),
    deps.factoryRuns(5),
    deps.callQuantManager('scheduler_status').then((payload) => deps.flattenMcpResult(payload)),
    deps.callQuantManager('factor_candidate_registry', { op: 'summary', limit: 200 }).then((payload) =>
      deps.flattenMcpResult(payload),
    ),
    deps.callQuantManager('factor_candidate_registry', { op: 'active_pool', limit: 20 }).then((payload) =>
      deps.flattenMcpResult(payload),
    ),
    deps.callQuantManager('model_registry', { op: 'summary', limit: 200 }).then((payload) =>
      deps.flattenMcpResult(payload),
    ),
    deps.callQuantManager('model_registry', { op: 'retrain_summary', limit: 200 }).then((payload) =>
      deps.flattenMcpResult(payload),
    ),
    deps.callQuantManager('model_registry', { op: 'retrain_list', limit: 5 }).then((payload) =>
      deps.flattenMcpResult(payload),
    ),
  ]);

  const factoryStatus = deps.unwrapSettledObject(sections[0], 'factory_status');
  const factoryRuns = deps.unwrapSettledObject(sections[1], 'factory_runs');
  const scheduler = deps.unwrapSettledObject(sections[2], 'scheduler_status');
  const registrySummaryRoot = deps.unwrapSettledObject(sections[3], 'registry_summary');
  const activePoolRoot = deps.unwrapSettledObject(sections[4], 'active_pool');
  const modelRoot = deps.unwrapSettledObject(sections[5], 'model_registry_summary');
  const retrainSummaryRoot = deps.unwrapSettledObject(sections[6], 'retrain_summary');
  const retrainQueueRoot = deps.unwrapSettledObject(sections[7], 'retrain_queue');

  const factorySummary = deps.asRecord(factoryStatus.data.last_summary);
  const latestRun =
    deps.asRecord(factoryRuns.data.latest).run_id != null
      ? deps.asRecord(factoryRuns.data.latest)
      : (deps.asRecordArray(factoryRuns.data.items)[0] ?? {});
  const registrySummary = deps.asRecord(registrySummaryRoot.data.summary);
  const activePool = deps.asRecord(activePoolRoot.data.active_pool);
  const modelRegistrySummary = deps.asRecord(modelRoot.data.summary);
  const retrainSummary = deps.asRecord(retrainSummaryRoot.data.summary);
  const retrainQueue = deps.asRecordArray(retrainQueueRoot.data.items);
  const schedulerLastResult = deps.asRecord(scheduler.data.last_result);
  const recentValidation = deps.asRecord(schedulerLastResult.llm_validation);

  return {
    overview: {
      factory_running: Boolean(factoryStatus.data.running),
      latest_factory_run_id: latestRun.run_id ?? factorySummary.run_id ?? null,
      latest_factory_status: latestRun.status ?? factorySummary.status ?? null,
      scheduler_quality_status: scheduler.data.quality_status ?? null,
      scheduler_stale: Boolean(scheduler.data.stale),
      active_factor_count: deps.toNum(activePool.count) ?? deps.toNum(registrySummary.active_count) ?? 0,
      blocked_factor_count: deps.toNum(registrySummary.blocked_count) ?? 0,
      governed_factor_count: deps.toNum(registrySummary.governed_active_count) ?? 0,
      champion_count: deps.toNum(modelRegistrySummary.champion_count) ?? 0,
      challenger_count: deps.toNum(modelRegistrySummary.challenger_count) ?? 0,
      candidates_spawned: deps.toNum(factorySummary.candidates_spawned) ?? 0,
      passed_quality_gate: deps.toNum(factorySummary.passed_quality_gate) ?? 0,
      recent_generated_candidate_count: deps.toNum(recentValidation.generated_candidate_count) ?? 0,
      recent_validated_candidate_count: deps.toNum(recentValidation.validated_candidate_count) ?? 0,
      recent_governed_active_count_after_run: deps.toNum(recentValidation.governed_active_count_after_run) ?? 0,
      retrain_plan_count: deps.toNum(retrainSummary.count) ?? 0,
      retrain_pending_count: deps.toNum(deps.asRecord(retrainSummary.status_counts).planned) ?? 0,
    },
    factory: {
      status: factoryStatus.data,
      latest_run: latestRun,
      runs: deps.asRecordArray(factoryRuns.data.items).slice(0, 5),
    },
    factor_governance: {
      scheduler: scheduler.data,
      registry_summary: registrySummary,
      active_pool: activePool,
      model_registry_summary: modelRegistrySummary,
      retrain_summary: retrainSummary,
      retrain_queue: retrainQueue,
      recent_run: recentValidation,
    },
    degraded: sections.some((section) => section.status === 'rejected'),
    errors: [
      factoryStatus.error,
      factoryRuns.error,
      scheduler.error,
      registrySummaryRoot.error,
      activePoolRoot.error,
      modelRoot.error,
      retrainSummaryRoot.error,
      retrainQueueRoot.error,
    ].filter(Boolean),
  };
}
