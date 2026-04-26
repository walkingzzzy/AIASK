import {
  normalizeFactoryMarketViewResponse,
  type CapabilityResponse,
  type DailySnapshotResponse,
  type FactoryMarketMetricCard,
  type FactoryMarketViewResponse,
  type FactoryMarketVisibleOutput,
  type FactoryObservabilityResponse,
  type FactoryRunDetailResponse,
  type FactoryRunsResponse,
  type FactoryStatusResponse,
} from '@aiask/shared-types';

type FactoryMarketViewBuildInput = {
  capabilities: CapabilityResponse | null;
  status: FactoryStatusResponse | null;
  snapshot: DailySnapshotResponse | null;
  runs: FactoryRunsResponse | null;
  researchSurface?: Record<string, unknown> | null;
  topnLatest?: Record<string, unknown> | null;
  observability: FactoryObservabilityResponse | null;
  retrainSurface?: Record<string, unknown> | null;
  expandedRun: FactoryRunDetailResponse | null;
  selectedRunId?: string | null;
  sectionErrors?: Record<string, string | null | undefined>;
};

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item),
  );
}

function toCount(value: unknown, fallback = 0) {
  const count = Number(value);
  return Number.isFinite(count) ? count : fallback;
}

function toRatio(value: unknown): number | null {
  const ratio = Number(value);
  return Number.isFinite(ratio) ? ratio : null;
}

function toBoolean(value: unknown) {
  if (typeof value === 'boolean') return value;
  const normalized = String(value ?? '')
    .trim()
    .toLowerCase();
  if (!normalized) return false;
  if (['true', '1', 'yes', 'y'].includes(normalized)) return true;
  if (['false', '0', 'no', 'n'].includes(normalized)) return false;
  return false;
}

function formatStatusLabel(status?: string | null) {
  switch (
    String(status ?? '')
      .trim()
      .toLowerCase()
  ) {
    case 'success':
      return '成功';
    case 'partial':
      return '部分成功';
    case 'failed':
      return '失败';
    case 'skipped':
      return '已跳过';
    case 'running':
      return '运行中';
    case 'queued':
      return '排队中';
    default:
      return String(status ?? '').trim() || '未知';
  }
}

function metricCard(
  key: string,
  label: string,
  value: string,
  tone: FactoryMarketMetricCard['tone'] = 'default',
): FactoryMarketMetricCard {
  return { key, label, value, tone };
}

function outputStatusFromRun(status?: string | null): FactoryMarketVisibleOutput['status'] {
  switch (
    String(status ?? '')
      .trim()
      .toLowerCase()
  ) {
    case 'success':
      return 'available';
    case 'partial':
      return 'degraded';
    case 'failed':
      return 'degraded';
    case 'skipped':
      return 'empty';
    default:
      return 'available';
  }
}

function mergeRecords(...values: unknown[]): Record<string, unknown> {
  return values.reduce<Record<string, unknown>>((merged, value) => {
    const record = asRecord(value);
    if (Object.keys(record).length === 0) {
      return merged;
    }
    return {
      ...merged,
      ...record,
    };
  }, {});
}

function runItems(runs: FactoryRunsResponse | null): Record<string, unknown>[] {
  const items = asRecordArray(runs?.items);
  const latest = asRecord(runs?.latest as unknown);
  if (!latest.run_id) return items;
  if (items.some((item) => String(item.run_id ?? '').trim() === String(latest.run_id ?? '').trim())) {
    return items;
  }
  return [latest, ...items];
}

function extractResearchWindow(run: unknown): Record<string, unknown> {
  const record = asRecord(run);
  const summary = asRecord(record.summary);
  return mergeRecords(summary.research_window, record.research_window);
}

function hasResearchWindowData(value: unknown) {
  const researchWindow = asRecord(value);
  return Boolean(
    researchWindow.available ||
      researchWindow.loaded_stock_count ||
      researchWindow.selected_bulk_task_count ||
      researchWindow.planned_bulk_task_count,
  );
}

function resolveRecentResearchWindow(
  status: FactoryStatusResponse | null,
  runs: FactoryRunsResponse | null,
  researchSurface?: Record<string, unknown> | null,
): { window: Record<string, unknown>; run: Record<string, unknown> | null } {
  const statusResearchWindow = asRecord(status?.research_window);
  if (hasResearchWindowData(statusResearchWindow)) {
    return { window: statusResearchWindow, run: null };
  }

  const persistedResearchWindow = asRecord(asRecord(researchSurface).research_window);
  if (hasResearchWindowData(persistedResearchWindow)) {
    return {
      window: persistedResearchWindow,
      run: asRecord(asRecord(researchSurface).run),
    };
  }

  for (const run of runItems(runs)) {
    const researchWindow = extractResearchWindow(run);
    if (hasResearchWindowData(researchWindow)) {
      return { window: researchWindow, run };
    }
  }

  return { window: statusResearchWindow, run: null };
}

function extractGovernanceSnapshot(value: unknown): Record<string, unknown> {
  const summary = asRecord(value);
  const researchSummary = asRecord(summary.research_summary);
  const schedulerSlo = asRecord(summary.scheduler_slo);
  const governedBacklog = asRecord(schedulerSlo.governed_pool_promotion_backlog);
  const activeCandidateCount = toCount(
    summary.active_candidate_count,
    toCount(researchSummary.active_candidate_count),
  );
  const governedSourceCandidateCount = toCount(
    summary.governed_source_candidate_count,
    toCount(researchSummary.governed_source_candidate_count, Math.max(activeCandidateCount, 0)),
  );
  const governedPendingCandidateCount = toCount(
    summary.governed_pending_candidate_count,
    toCount(researchSummary.governed_pending_candidate_count, toCount(governedBacklog.governed_pending_candidate_count)),
  );
  const governedBlockedRatio =
    toRatio(summary.governed_blocked_ratio) ?? toRatio(researchSummary.governed_blocked_ratio);
  const governedPendingRatio =
    toRatio(summary.governed_pending_ratio) ??
    toRatio(researchSummary.governed_pending_ratio) ??
    toRatio(governedBacklog.governed_pending_ratio);
  const blockedCandidateCount = toCount(
    summary.governed_blocked_candidate_count,
    toCount(
      researchSummary.governed_blocked_candidate_count,
      governedSourceCandidateCount > 0 && governedBlockedRatio != null
        ? Math.round(governedSourceCandidateCount * governedBlockedRatio)
        : 0,
    ),
  );
  const governedCandidatePoolActive = toBoolean(
    summary.governed_candidate_pool_active ?? researchSummary.governed_candidate_pool_active,
  );
  const schedulerQualityStatus =
    String(schedulerSlo.status ?? summary.factor_scheduler_quality_status ?? '').trim() || null;
  const runtimeState =
    String(
      summary.governed_candidate_pool_runtime_state ?? researchSummary.governed_candidate_pool_runtime_state ?? '',
    ).trim() || null;

  return {
    active_candidate_count: activeCandidateCount,
    governed_source_candidate_count: governedSourceCandidateCount,
    governed_pending_candidate_count: governedPendingCandidateCount,
    governed_blocked_candidate_count: blockedCandidateCount,
    governed_blocked_ratio: governedBlockedRatio,
    governed_pending_ratio: governedPendingRatio,
    governed_candidate_pool_active: governedCandidatePoolActive,
    governed_candidate_pool_runtime_state: runtimeState,
    scheduler_quality_status: schedulerQualityStatus,
  };
}

function hasGovernanceData(value: unknown) {
  const snapshot = asRecord(value);
  return Boolean(
    snapshot.active_candidate_count ||
      snapshot.governed_pending_candidate_count ||
      snapshot.governed_blocked_candidate_count ||
      snapshot.governed_candidate_pool_active ||
      snapshot.governed_candidate_pool_runtime_state,
  );
}

function resolveGovernanceSurface({
  status,
  runs,
  observability,
}: {
  status: FactoryStatusResponse | null;
  runs: FactoryRunsResponse | null;
  observability: FactoryObservabilityResponse | null;
}): { source: 'observability' | 'run' | 'none'; snapshot: Record<string, unknown>; run: Record<string, unknown> | null } {
  const observabilityOverview = asRecord(observability?.overview);
  const factorGovernance = asRecord(observability?.factor_governance);
  const registrySummary = asRecord(factorGovernance.registry_summary);
  const activePool = asRecord(factorGovernance.active_pool);
  const activeFactorCount = toCount(
    observabilityOverview.active_factor_count,
    toCount(activePool.count, toCount(registrySummary.active_count)),
  );
  const governedFactorCount = toCount(
    observabilityOverview.governed_factor_count,
    toCount(registrySummary.governed_active_count),
  );
  const blockedFactorCount = toCount(
    observabilityOverview.blocked_factor_count,
    toCount(registrySummary.blocked_count),
  );

  if (activeFactorCount > 0 || governedFactorCount > 0 || blockedFactorCount > 0) {
    return {
      source: 'observability',
      snapshot: {
        active_factor_count: activeFactorCount,
        governed_factor_count: governedFactorCount,
        blocked_factor_count: blockedFactorCount,
        scheduler_quality_status: observabilityOverview.scheduler_quality_status,
      },
      run: null,
    };
  }

  const statusGovernance = extractGovernanceSnapshot(status?.last_summary);
  if (hasGovernanceData(statusGovernance)) {
    return {
      source: 'run',
      snapshot: statusGovernance,
      run: asRecord(runs?.latest as unknown),
    };
  }

  for (const run of runItems(runs)) {
    const governance = extractGovernanceSnapshot(asRecord(run).summary);
    if (hasGovernanceData(governance)) {
      return {
        source: 'run',
        snapshot: governance,
        run,
      };
    }
  }

  return { source: 'none', snapshot: {}, run: null };
}

function resolveRetrainSurface({
  observability,
  retrainSurface,
}: {
  observability: FactoryObservabilityResponse | null;
  retrainSurface?: Record<string, unknown> | null;
}) {
  const retrainRoot = asRecord(retrainSurface);
  const factorGovernance = asRecord(observability?.factor_governance);
  const retrainSummary = mergeRecords(
    asRecord(retrainRoot.summary),
    asRecord(factorGovernance.retrain_summary),
  );
  const retrainQueue = asRecordArray(factorGovernance.retrain_queue);
  const items = retrainQueue.length > 0 ? retrainQueue : asRecordArray(retrainRoot.items);
  const loaded = toBoolean(retrainRoot.loaded) || Object.keys(asRecord(retrainRoot.summary)).length > 0;
  return {
    summary: retrainSummary,
    items,
    loaded,
  };
}

function mergeObservabilityFallback({
  observability,
  status,
  runs,
  governance,
  retrain,
}: {
  observability: FactoryObservabilityResponse | null;
  status: FactoryStatusResponse | null;
  runs: FactoryRunsResponse | null;
  governance: { source: 'observability' | 'run' | 'none'; snapshot: Record<string, unknown>; run: Record<string, unknown> | null };
  retrain: { summary: Record<string, unknown>; items: Record<string, unknown>[]; loaded: boolean };
}): FactoryObservabilityResponse | null {
  if (!observability) return null;

  type ObservabilityFactory = NonNullable<FactoryObservabilityResponse['factory']>;

  const summary = asRecord(status?.last_summary);
  const latestRun = asRecord(runs?.latest as unknown);
  const overview = asRecord(observability.overview);
  const factory = asRecord(observability.factory);
  const factorGovernance = asRecord(observability.factor_governance);
  const registrySummary = asRecord(factorGovernance.registry_summary);
  const activePool = asRecord(factorGovernance.active_pool);
  const retrainSummary = asRecord(factorGovernance.retrain_summary);
  const retrainQueue = asRecordArray(factorGovernance.retrain_queue);
  const fallbackActiveCount =
    governance.source === 'observability'
      ? toCount(governance.snapshot.active_factor_count)
      : toCount(governance.snapshot.active_candidate_count);
  const fallbackBlockedCount =
    governance.source === 'observability'
      ? toCount(governance.snapshot.blocked_factor_count)
      : toCount(governance.snapshot.governed_blocked_candidate_count);
  const fallbackGovernedCount =
    governance.source === 'observability'
      ? toCount(governance.snapshot.governed_factor_count)
      : toCount(governance.snapshot.active_candidate_count);
  const fallbackSchedulerQuality =
    String(overview.scheduler_quality_status ?? governance.snapshot.scheduler_quality_status ?? '').trim() || null;
  const fallbackRetrainPlanCount = toCount(retrain.summary.count);
  const fallbackRetrainPendingCount = toCount(asRecord(retrain.summary.status_counts).planned);

  return {
    ...observability,
    overview: {
      ...overview,
      factory_running: Boolean(overview.factory_running ?? status?.running),
      latest_factory_run_id: overview.latest_factory_run_id ?? latestRun.run_id ?? null,
      latest_factory_status:
        overview.latest_factory_status ?? latestRun.status ?? asRecord(status?.last_result).status ?? null,
      scheduler_quality_status: fallbackSchedulerQuality,
      active_factor_count:
        toCount(overview.active_factor_count) > 0 ? toCount(overview.active_factor_count) : fallbackActiveCount,
      blocked_factor_count:
        toCount(overview.blocked_factor_count) > 0 ? toCount(overview.blocked_factor_count) : fallbackBlockedCount,
      governed_factor_count:
        toCount(overview.governed_factor_count) > 0
          ? toCount(overview.governed_factor_count)
          : fallbackGovernedCount,
      candidates_spawned:
        toCount(overview.candidates_spawned) > 0 ? toCount(overview.candidates_spawned) : toCount(summary.candidates_spawned),
      passed_quality_gate:
        toCount(overview.passed_quality_gate) > 0
          ? toCount(overview.passed_quality_gate)
          : toCount(summary.passed_quality_gate),
      recent_governed_active_count_after_run:
        toCount(overview.recent_governed_active_count_after_run) > 0
          ? toCount(overview.recent_governed_active_count_after_run)
          : fallbackGovernedCount,
      retrain_plan_count:
        toCount(overview.retrain_plan_count) > 0 ? toCount(overview.retrain_plan_count) : fallbackRetrainPlanCount,
      retrain_pending_count:
        toCount(overview.retrain_pending_count) > 0
          ? toCount(overview.retrain_pending_count)
          : fallbackRetrainPendingCount,
    },
    factory: {
      ...factory,
      status:
        Object.keys(asRecord(factory.status)).length > 0
          ? (factory.status as ObservabilityFactory['status'])
          : status,
      latest_run:
        Object.keys(asRecord(factory.latest_run)).length > 0
          ? (factory.latest_run as ObservabilityFactory['latest_run'])
          : (latestRun as ObservabilityFactory['latest_run']),
      runs:
        asRecordArray(factory.runs).length > 0
          ? (asRecordArray(factory.runs) as ObservabilityFactory['runs'])
          : ((runs?.items ?? []).slice(0, 5) as ObservabilityFactory['runs']),
    } as ObservabilityFactory,
    factor_governance: {
      ...factorGovernance,
      registry_summary:
        Object.keys(registrySummary).length > 0
          ? registrySummary
          : {
              active_count: fallbackActiveCount,
              governed_active_count: fallbackGovernedCount,
              blocked_count: fallbackBlockedCount,
            },
      active_pool:
        Object.keys(activePool).length > 0
          ? activePool
          : {
              count: fallbackActiveCount,
            },
      retrain_summary: Object.keys(retrainSummary).length > 0 ? retrainSummary : retrain.summary,
      retrain_queue: retrainQueue.length > 0 ? retrainQueue : retrain.items,
    },
    degraded: Boolean(observability.degraded),
    errors: Array.isArray(observability.errors) ? observability.errors : [],
  };
}

function resolveMarketStatus({
  status,
  runs,
  researchSurface,
  topnLatest,
}: {
  status: FactoryStatusResponse | null;
  runs: FactoryRunsResponse | null;
  researchSurface?: Record<string, unknown> | null;
  topnLatest?: Record<string, unknown> | null;
}): FactoryStatusResponse | null {
  const latestRun = runs?.latest ?? runs?.items?.[0] ?? null;
  const latestRunRecord = asRecord(latestRun as unknown);
  const latestRunSummary = asRecord(latestRunRecord.summary);
  const latestRunAt = String(latestRunRecord.completed_at ?? latestRunRecord.started_at ?? '').trim() || null;
  const resolvedResearchWindow = resolveRecentResearchWindow(status, runs, researchSurface).window;
  const topnLatestRoot = asRecord(topnLatest);
  const topnLatestSnapshot = asRecord(topnLatestRoot.snapshot);
  const resolvedTopn = mergeRecords(
    asRecord(status?.full_market_topn as unknown),
    latestRunSummary.full_market_topn,
    latestRunRecord.full_market_topn,
    topnLatestSnapshot,
  );

  if (Object.keys(resolvedTopn).length > 0) {
    const resolvedScoreRowCount = toCount(
      topnLatestRoot.score_row_count,
      toCount(resolvedTopn.score_row_count, 0),
    );
    if (resolvedScoreRowCount > 0 && !Number.isFinite(Number(resolvedTopn.score_row_count))) {
      resolvedTopn.score_row_count = resolvedScoreRowCount;
    }
    if (topnLatestRoot.available != null && resolvedTopn.available == null) {
      resolvedTopn.available = Boolean(topnLatestRoot.available);
    }
  }

  if (status) {
    return {
      ...status,
      last_run: status.last_run ?? latestRunAt,
      last_result:
        status.last_result ??
        (latestRun
          ? {
              status: String(latestRunRecord.status ?? ''),
              error: latestRunRecord.error == null ? undefined : String(latestRunRecord.error),
            }
          : undefined),
      last_summary:
        status.last_summary && Object.keys(asRecord(status.last_summary)).length > 0
          ? status.last_summary
          : (Object.keys(latestRunSummary).length > 0 ? (latestRunSummary as FactoryStatusResponse['last_summary']) : undefined),
      research_window:
        Object.keys(resolvedResearchWindow).length > 0
          ? (resolvedResearchWindow as FactoryStatusResponse['research_window'])
          : undefined,
      full_market_topn:
        Object.keys(resolvedTopn).length > 0 ? (resolvedTopn as FactoryStatusResponse['full_market_topn']) : undefined,
    };
  }

  if (!latestRun && Object.keys(resolvedResearchWindow).length === 0 && Object.keys(resolvedTopn).length === 0) {
    return null;
  }

  return {
    running: false,
    last_run: latestRunAt,
    last_result: latestRun
      ? {
          status: String(latestRunRecord.status ?? ''),
          error: latestRunRecord.error == null ? undefined : String(latestRunRecord.error),
        }
      : undefined,
    last_summary:
      Object.keys(latestRunSummary).length > 0 ? (latestRunSummary as FactoryStatusResponse['last_summary']) : undefined,
    research_window:
      Object.keys(resolvedResearchWindow).length > 0
        ? (resolvedResearchWindow as FactoryStatusResponse['research_window'])
        : undefined,
    full_market_topn:
      Object.keys(resolvedTopn).length > 0 ? (resolvedTopn as FactoryStatusResponse['full_market_topn']) : undefined,
  };
}

function buildVisibleOutputs({
  status,
  runs,
  researchSurface,
  observability,
  retrainSurface,
}: {
  status: FactoryStatusResponse | null;
  runs: FactoryRunsResponse | null;
  researchSurface?: Record<string, unknown> | null;
  observability: FactoryObservabilityResponse | null;
  retrainSurface?: Record<string, unknown> | null;
}): FactoryMarketVisibleOutput[] {
  const latestRun = runs?.latest ?? runs?.items?.[0] ?? null;
  const latestRunSummary = latestRun?.summary ?? {};
  const resolvedResearchWindow = resolveRecentResearchWindow(status, runs, researchSurface);
  const researchWindow = resolvedResearchWindow.window;
  const fullMarketTopn = status?.full_market_topn ?? latestRunSummary?.full_market_topn ?? null;
  const governance = resolveGovernanceSurface({ status, runs, observability });
  const observabilityOverview = asRecord(observability?.overview);
  const retrainRoot = asRecord(retrainSurface);
  const retrainSummary = mergeRecords(
    asRecord(retrainRoot.summary),
    asRecord(asRecord(observability?.factor_governance).retrain_summary),
  );
  const retrainQueue = asRecordArray(asRecord(observability?.factor_governance).retrain_queue);
  const retrainItems = retrainQueue.length > 0 ? retrainQueue : asRecordArray(retrainRoot.items);
  const retrainLoaded = toBoolean(retrainRoot.loaded) || Object.keys(asRecord(retrainRoot.summary)).length > 0;

  const outputs: FactoryMarketVisibleOutput[] = [];

  if (latestRun?.run_id) {
    outputs.push({
      key: 'latest_run',
      kind: 'factory_run',
      title: '最近工厂运行',
      status: outputStatusFromRun(latestRun.status),
      summary: `${String(latestRun.run_id)} · ${formatStatusLabel(latestRun.status)} · 候选 ${toCount(latestRun.summary?.candidates_spawned)} / 质检 ${toCount(latestRun.summary?.passed_quality_gate)}`,
      evidence: latestRun.completed_at
        ? `完成于 ${latestRun.completed_at}`
        : latestRun.started_at
          ? `开始于 ${latestRun.started_at}`
          : '',
      metadata: {
        run_id: latestRun.run_id,
        status: latestRun.status,
      },
    });
  }

  const researchWindowAvailable = Boolean(
    researchWindow?.available ||
    researchWindow?.loaded_stock_count ||
    researchWindow?.selected_bulk_task_count ||
    researchWindow?.planned_bulk_task_count,
  );
  if (researchWindowAvailable) {
    const researchSourceRunId = String(resolvedResearchWindow.run?.run_id ?? '').trim();
    outputs.push({
      key: 'research_window',
      kind: 'research_window',
      title: '研究窗口',
      status: 'available',
      summary: `扫描 ${toCount(researchWindow?.loaded_stock_count)} 只，规划 ${toCount(researchWindow?.planned_bulk_task_count)} 个任务，本轮执行 ${toCount(researchWindow?.selected_bulk_task_count)} 个`,
      evidence: `预算 ${toCount(researchWindow?.effective_task_budget)}，下一轮 offset ${toCount(researchWindow?.next_task_offset)}${researchSourceRunId ? ` · 来源 ${researchSourceRunId}` : ''}`,
      metadata: {
        ...asRecord(researchWindow as unknown),
        source_run_id: researchSourceRunId || undefined,
      },
    });
  }

  const topnConstituents = Array.isArray(fullMarketTopn?.constituents) ? fullMarketTopn?.constituents : [];
  const topnAvailable = Boolean(fullMarketTopn?.available || topnConstituents.length > 0);
  if (topnAvailable) {
    outputs.push({
      key: 'full_market_topn',
      kind: 'full_market_topn',
      title: '全市场 Top N',
      status: fullMarketTopn?.score_quality === 'degraded' ? 'degraded' : 'available',
      summary: `Top ${toCount(fullMarketTopn?.topn_n, topnConstituents.length)} · ${String(fullMarketTopn?.score_quality ?? 'unknown')} · ${String(fullMarketTopn?.as_of_date ?? '未标注日期')}`,
      evidence: `评分行 ${toCount(fullMarketTopn?.score_row_count)}，组合候选 ${String(fullMarketTopn?.portfolio_candidate_id ?? '未生成')}`,
      metadata: {
        snapshot_id: fullMarketTopn?.snapshot_id,
        score_quality: fullMarketTopn?.score_quality,
      },
    });
  }

  if (typeof fullMarketTopn?.portfolio_candidate_id === 'string' && fullMarketTopn.portfolio_candidate_id.trim()) {
    const candidateId = fullMarketTopn.portfolio_candidate_id.trim();
    outputs.push({
      key: 'portfolio_candidate',
      kind: 'portfolio_candidate',
      title: 'Top N 组合候选',
      status: 'available',
      summary: `策略 ID ${candidateId}`,
      evidence: `来自 ${String(fullMarketTopn?.snapshot_id ?? fullMarketTopn?.run_id ?? 'Top N 快照')}`,
      href: `/strategy-market/${encodeURIComponent(candidateId)}`,
      metadata: {
        strategy_id: candidateId,
      },
    });
  }

  if (governance.source === 'observability') {
    const activeFactorCount = toCount(governance.snapshot.active_factor_count);
    const governedFactorCount = toCount(governance.snapshot.governed_factor_count);
    const blockedFactorCount = toCount(governance.snapshot.blocked_factor_count);
    outputs.push({
      key: 'governance_registry',
      kind: 'governance_registry',
      title: '候选治理与活跃池',
      status: blockedFactorCount > 0 ? 'degraded' : 'available',
      summary: `活跃因子 ${activeFactorCount}，治理通过 ${governedFactorCount}，阻断 ${blockedFactorCount}`,
      evidence: `调度质量 ${String(governance.snapshot.scheduler_quality_status ?? '-')}`,
      metadata: {
        active_factor_count: activeFactorCount,
        governed_factor_count: governedFactorCount,
        blocked_factor_count: blockedFactorCount,
      },
    });
  } else if (governance.source === 'run') {
    const activeCandidateCount = toCount(governance.snapshot.active_candidate_count);
    const pendingCandidateCount = toCount(governance.snapshot.governed_pending_candidate_count);
    const blockedCandidateCount = toCount(governance.snapshot.governed_blocked_candidate_count);
    const sourceRunId = String(governance.run?.run_id ?? '').trim();
    outputs.push({
      key: 'governance_registry',
      kind: 'governance_registry',
      title: '候选治理与活跃池',
      status: blockedCandidateCount > 0 ? 'degraded' : 'available',
      summary: `活跃候选 ${activeCandidateCount}，待治理 ${pendingCandidateCount}，阻断 ${blockedCandidateCount}`,
      evidence: `治理池${toBoolean(governance.snapshot.governed_candidate_pool_active) ? '已激活' : '未激活'} · 调度质量 ${String(governance.snapshot.scheduler_quality_status ?? '-')}${sourceRunId ? ` · 来源 ${sourceRunId}` : ''}`,
      metadata: {
        ...governance.snapshot,
        source_run_id: sourceRunId || undefined,
      },
    });
  }

  const retrainPlanCount = toCount(observabilityOverview.retrain_plan_count, toCount(retrainSummary.count));
  const retrainPendingCount = toCount(
    observabilityOverview.retrain_pending_count,
    toCount(asRecord(retrainSummary.status_counts).planned),
  );
  if (retrainPlanCount > 0 || retrainItems.length > 0 || retrainLoaded) {
    outputs.push({
      key: 'retrain_queue',
      kind: 'retrain_queue',
      title: '重训练计划队列',
      status: retrainPlanCount > 0 || retrainItems.length > 0 ? 'available' : 'empty',
      summary:
        retrainPlanCount > 0 || retrainItems.length > 0
          ? `计划 ${retrainPlanCount} 个，待执行 ${retrainPendingCount} 个`
          : '当前无待执行重训练计划',
      evidence:
        retrainItems.length > 0
          ? `当前列表 ${retrainItems.length} 条`
          : retrainLoaded
            ? '已检查模型重训练计划库，当前 0 条'
            : `状态分布 ${
                Object.entries(asRecord(retrainSummary.status_counts))
                  .map(([key, value]) => `${key}:${String(value)}`)
                  .join(' / ') || '-'
              }`,
      metadata: {
        retrain_plan_count: retrainPlanCount,
        retrain_queue_size: retrainItems.length,
      },
    });
  }

  return outputs;
}

export function buildFactoryMarketViewResponse({
  capabilities,
  status,
  snapshot,
  runs,
  researchSurface,
  topnLatest,
  observability,
  retrainSurface,
  expandedRun,
  selectedRunId,
  sectionErrors,
}: FactoryMarketViewBuildInput): FactoryMarketViewResponse {
  const resolvedStatus = resolveMarketStatus({ status, runs, researchSurface, topnLatest });
  const summary = resolvedStatus?.last_summary ?? {};
  const latestRun = runs?.latest ?? runs?.items?.[0] ?? null;
  const failedRunCount = (runs?.items ?? []).filter((item) => item?.status === 'failed').length;
  const snapshotCompletionRatio =
    summary?.snapshot_completion_ratio ?? snapshot?.completeness?.completion_ratio ?? null;
  const snapshotFailureCount = summary?.snapshot_failure_reason_count ?? snapshot?.failure_reasons?.length ?? 0;
  const snapshotDegraded = Boolean(summary?.snapshot_degraded ?? snapshot?.degraded ?? false);
  const observabilityOverview = asRecord(observability?.overview);
  const resolvedTopn = asRecord(resolvedStatus?.full_market_topn as unknown);
  const latestSnapshotLabel = String(snapshot?.snapshot_date ?? resolvedTopn.as_of_date ?? resolvedStatus?.last_run ?? '暂无');
  const visibleOutputs = buildVisibleOutputs({
    status: resolvedStatus,
    runs,
    researchSurface,
    observability,
    retrainSurface,
  });
  const governance = resolveGovernanceSurface({ status: resolvedStatus, runs, observability });
  const retrain = resolveRetrainSurface({ observability, retrainSurface });
  const resolvedObservability = mergeObservabilityFallback({
    observability,
    status: resolvedStatus,
    runs,
    governance,
    retrain,
  });
  const responseErrors = Array.from(
    new Set(
      [
        ...Object.values(sectionErrors ?? {}).filter((value): value is string => Boolean(value)),
        ...(resolvedObservability?.errors ?? []),
      ].filter(Boolean),
    ),
  );

  const response = normalizeFactoryMarketViewResponse({
    dto_version: 'strategy_market.factory_market_view.v1',
    generated_at: new Date().toISOString(),
    selected_run_id: selectedRunId ?? null,
    degraded: snapshotDegraded || Boolean(resolvedObservability?.degraded) || responseErrors.length > 0,
    errors: responseErrors,
    section_errors: sectionErrors ?? {},
    capabilities,
    status: resolvedStatus,
    snapshot,
    runs,
    observability: resolvedObservability,
    expanded_run: expandedRun,
    surface: {
      snapshot_completion_ratio: snapshotCompletionRatio,
      snapshot_failure_count: snapshotFailureCount,
      snapshot_degraded: snapshotDegraded,
      failed_run_count: failedRunCount,
      overview_cards: [
        metricCard(
          'dispatch_status',
          '调度状态',
          status?.running ? '运行中' : '待命',
          status?.running ? 'success' : 'default',
        ),
        metricCard('candidates_spawned', '候选生成', String(toCount(summary?.candidates_spawned))),
        metricCard('passed_quality_gate', '质检通过', String(toCount(summary?.passed_quality_gate))),
        metricCard('latest_snapshot', '最新快照', latestSnapshotLabel),
      ],
      hero_cards: [
        metricCard('factory_runs', '最近工厂运行', String((runs?.items ?? []).length)),
        metricCard(
          'factory_dispatch',
          '调度状态',
          resolvedStatus?.running ? '运行中' : '待命',
          resolvedStatus?.running ? 'success' : 'default',
        ),
        metricCard('failed_runs', '最近失败运行', String(failedRunCount), failedRunCount > 0 ? 'danger' : 'success'),
        metricCard('snapshot_date', '最新快照', latestSnapshotLabel),
      ],
      observability_cards: [
        metricCard(
          'observability_status',
          '工厂状态',
          resolvedStatus?.running ? '运行中' : '待命',
          resolvedStatus?.running ? 'success' : 'default',
        ),
        metricCard(
          'active_factor_count',
          governance.source === 'observability' ? '活跃因子' : '活跃候选',
          String(
            governance.source === 'observability'
              ? toCount(observabilityOverview.active_factor_count)
              : toCount(governance.snapshot.active_candidate_count),
          ),
        ),
        metricCard(
          'scheduler_quality_status',
          '调度质量',
          String(observabilityOverview.scheduler_quality_status ?? governance.snapshot.scheduler_quality_status ?? '-'),
          observabilityOverview.scheduler_stale ? 'danger' : 'success',
        ),
      ],
      visible_outputs: visibleOutputs,
    },
  });

  if (!response.runs?.latest && latestRun) {
    response.runs = {
      ...(response.runs ?? {}),
      latest: latestRun,
      items: response.runs?.items ?? runs?.items ?? [],
      count: response.runs?.count ?? (runs?.items ?? []).length,
    };
  }

  return response;
}
