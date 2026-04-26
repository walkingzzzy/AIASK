import type { StrategyDetailResponse, StrategyDetailViewModel } from './runtime';

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

function asRecordArray<T extends Record<string, unknown>>(value: unknown): T[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is T => Boolean(item) && typeof item === 'object' && !Array.isArray(item),
  );
}

function asNumberArray(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item) => item != null && item !== '')
    .map((item) => Number(item))
    .filter((item) => Number.isFinite(item));
}

function hasStrategyIdentity(value: unknown) {
  const record = asRecord(value);
  return typeof record.id === 'string' && record.id.trim().length > 0;
}

export function normalizeStrategyDetailResponse(payload: unknown): StrategyDetailResponse {
  const raw = asRecord(payload);
  const rawStrategy = hasStrategyIdentity(raw.strategy) ? asRecord(raw.strategy) : raw;
  if (typeof rawStrategy.id !== 'string' || rawStrategy.id.trim() === '') {
    throw new Error('strategy detail missing strategy.id');
  }

  const rawViewModel = asRecord(raw.view_model);
  const rawQuality = asRecord(rawViewModel.quality);
  const rawIncubation = asRecord(rawViewModel.incubation);
  const rawRuntime = asRecord(rawViewModel.runtime);
  const rawVectors = asRecord(rawViewModel.vectors);
  const rawDomain = asRecord(rawViewModel.domain);
  const rawActions = asRecord(rawViewModel.actions);

  const latestQualityReport =
    asRecord(raw.latest_quality_report).report_type || asRecord(raw.latest_quality_report).summary
      ? raw.latest_quality_report
      : rawQuality.latest_report ?? null;
  const incubationOverview = raw.incubation_overview ?? rawIncubation.overview ?? null;
  const incubationAccount = raw.incubation_account ?? rawIncubation.account ?? null;
  const latestIncubationMetric = raw.latest_incubation_metric ?? rawIncubation.latest_metric ?? null;
  const latestIncubationPipelineSnapshot =
    raw.latest_incubation_pipeline_snapshot ?? rawIncubation.latest_pipeline_snapshot ?? null;
  const runtimeControl = raw.runtime_control ?? rawRuntime.control ?? null;
  const latestRuntimeRiskSnapshot = raw.latest_runtime_risk_snapshot ?? rawRuntime.latest_risk_snapshot ?? null;
  const runtimeAlerts = asRecordArray(raw.runtime_alerts ?? rawRuntime.alerts);
  const openRiskEvents = asRecordArray(raw.open_risk_events ?? rawRuntime.risk_events);
  const vectorProfiles = asRecordArray(raw.vector_profiles ?? rawVectors.profiles);
  const similarVectorProfiles = asRecordArray(raw.similar_vector_profiles ?? rawVectors.similar_profiles);
  const latestVectorIndexSnapshot = raw.latest_vector_index_snapshot ?? rawVectors.latest_index_snapshot ?? null;
  const domainEvents = asRecordArray(raw.domain_events ?? rawDomain.events);
  const taskRuns = asRecordArray(raw.task_runs ?? rawDomain.task_runs);
  const latestProjectionSnapshot = raw.latest_projection_snapshot ?? rawDomain.latest_projection_snapshot ?? null;
  const runtimeActionContract =
    raw.runtime_action_contract ??
    rawStrategy.runtime_action_contract ??
    rawActions.runtime_action_contract ??
    null;
  const runtimeActions = asRecordArray(
    raw.runtime_actions ??
    rawStrategy.runtime_actions ??
    rawActions.items ??
    (asRecord(runtimeActionContract).actions),
  );
  const favoriteCount = Number(rawStrategy.favorite_count ?? rawStrategy.subscriber_count ?? 0);
  const strategy = {
    ...rawStrategy,
    favorite_count: Number.isFinite(favoriteCount) ? favoriteCount : 0,
  };

  const viewModel: StrategyDetailViewModel = {
    ...rawViewModel,
    quality: {
      ...rawQuality,
      latest_report: latestQualityReport as NonNullable<StrategyDetailViewModel['quality']>['latest_report'],
    },
    incubation: {
      ...rawIncubation,
      overview: incubationOverview as NonNullable<StrategyDetailViewModel['incubation']>['overview'],
      account: incubationAccount as NonNullable<StrategyDetailViewModel['incubation']>['account'],
      latest_metric: latestIncubationMetric as NonNullable<StrategyDetailViewModel['incubation']>['latest_metric'],
      latest_pipeline_snapshot:
        latestIncubationPipelineSnapshot as NonNullable<StrategyDetailViewModel['incubation']>['latest_pipeline_snapshot'],
    },
    runtime: {
      ...rawRuntime,
      control: runtimeControl as NonNullable<StrategyDetailViewModel['runtime']>['control'],
      latest_risk_snapshot:
        latestRuntimeRiskSnapshot as NonNullable<StrategyDetailViewModel['runtime']>['latest_risk_snapshot'],
      alerts: runtimeAlerts as NonNullable<StrategyDetailViewModel['runtime']>['alerts'],
      risk_events: openRiskEvents as NonNullable<StrategyDetailViewModel['runtime']>['risk_events'],
    },
    vectors: {
      ...rawVectors,
      profiles: vectorProfiles as NonNullable<StrategyDetailViewModel['vectors']>['profiles'],
      similar_profiles: similarVectorProfiles as NonNullable<StrategyDetailViewModel['vectors']>['similar_profiles'],
      latest_index_snapshot:
        latestVectorIndexSnapshot as NonNullable<StrategyDetailViewModel['vectors']>['latest_index_snapshot'],
    },
    domain: {
      ...rawDomain,
      events: domainEvents as NonNullable<StrategyDetailViewModel['domain']>['events'],
      task_runs: taskRuns as NonNullable<StrategyDetailViewModel['domain']>['task_runs'],
      latest_projection_snapshot:
        latestProjectionSnapshot as NonNullable<StrategyDetailViewModel['domain']>['latest_projection_snapshot'],
    },
    actions: {
      ...rawActions,
      runtime_action_contract:
        runtimeActionContract as NonNullable<StrategyDetailViewModel['actions']>['runtime_action_contract'],
      items: runtimeActions as NonNullable<StrategyDetailViewModel['actions']>['items'],
    },
  };

  return {
    ...raw,
    dto_version: 'strategy_market.detail.v2',
    strategy: strategy as StrategyDetailResponse['strategy'],
    metrics: asRecordArray(raw.metrics),
    reviews: asRecordArray(raw.reviews),
    nav_series: asNumberArray(raw.nav_series),
    latest_quality_report: latestQualityReport as StrategyDetailResponse['latest_quality_report'],
    incubation_overview: incubationOverview as StrategyDetailResponse['incubation_overview'],
    incubation_account: incubationAccount as StrategyDetailResponse['incubation_account'],
    latest_incubation_metric: latestIncubationMetric as StrategyDetailResponse['latest_incubation_metric'],
    latest_promotion_review: (raw.latest_promotion_review ?? null) as StrategyDetailResponse['latest_promotion_review'],
    latest_projection_snapshot: latestProjectionSnapshot as StrategyDetailResponse['latest_projection_snapshot'],
    latest_vector_index_snapshot: latestVectorIndexSnapshot as StrategyDetailResponse['latest_vector_index_snapshot'],
    latest_incubation_pipeline_snapshot:
      latestIncubationPipelineSnapshot as StrategyDetailResponse['latest_incubation_pipeline_snapshot'],
    latest_runtime_risk_snapshot:
      latestRuntimeRiskSnapshot as StrategyDetailResponse['latest_runtime_risk_snapshot'],
    runtime_control: runtimeControl as StrategyDetailResponse['runtime_control'],
    runtime_alerts: runtimeAlerts as StrategyDetailResponse['runtime_alerts'],
    open_risk_events: openRiskEvents as StrategyDetailResponse['open_risk_events'],
    vector_profiles: vectorProfiles as StrategyDetailResponse['vector_profiles'],
    similar_vector_profiles: similarVectorProfiles as StrategyDetailResponse['similar_vector_profiles'],
    domain_events: domainEvents as StrategyDetailResponse['domain_events'],
    task_runs: taskRuns as StrategyDetailResponse['task_runs'],
    runtime_action_contract: runtimeActionContract as StrategyDetailResponse['runtime_action_contract'],
    runtime_actions: runtimeActions as StrategyDetailResponse['runtime_actions'],
    view_model: viewModel,
  };
}
