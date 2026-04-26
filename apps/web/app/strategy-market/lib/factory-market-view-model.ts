import type {
  CapabilityResponse,
  FactoryMarketViewResponse,
  FactoryRunDetailResponse,
  FactoryRunItem,
  FactoryStatusResponse,
} from '../types';

export type FactoryMarketViewModel = {
  status: FactoryStatusResponse | null;
  latestSnapshot: FactoryMarketViewResponse['snapshot'] | null;
  summary: NonNullable<FactoryStatusResponse['last_summary']>;
  capabilities: CapabilityResponse;
  actorPermissions: Record<string, unknown>;
  sectionErrors: NonNullable<FactoryMarketViewResponse['section_errors']>;
  snapshotCompletionRatio: number | null;
  snapshotFailureCount: number;
  snapshotDegraded: boolean;
  factoryRuns: FactoryRunItem[];
  failedRuns: FactoryRunItem[];
  visibleOutputs: NonNullable<NonNullable<FactoryMarketViewResponse['surface']>['visible_outputs']>;
  expandedRun: FactoryRunDetailResponse | null;
};

export function buildFactoryMarketViewModel(
  view: FactoryMarketViewResponse | null,
  expandedRunId?: string | null,
): FactoryMarketViewModel {
  const status = view?.status ?? null;
  const latestSnapshot = view?.snapshot ?? null;
  const summary = status?.last_summary ?? {};
  const capabilities = view?.capabilities ?? {};
  const actorPermissions =
    capabilities.actor_permissions && typeof capabilities.actor_permissions === 'object'
      ? (capabilities.actor_permissions as Record<string, unknown>)
      : {};
  const sectionErrors = view?.section_errors ?? {};
  const snapshotCompletionRatio =
    view?.surface?.snapshot_completion_ratio ??
    summary.snapshot_completion_ratio ??
    latestSnapshot?.completeness?.completion_ratio ??
    null;
  const snapshotFailureCount =
    view?.surface?.snapshot_failure_count ??
    summary.snapshot_failure_reason_count ??
    latestSnapshot?.failure_reasons?.length ??
    0;
  const snapshotDegraded =
    view?.surface?.snapshot_degraded ??
    summary.snapshot_degraded ??
    latestSnapshot?.degraded ??
    false;
  const factoryRuns = view?.runs?.items ?? [];
  const failedRuns = factoryRuns.filter((item) => item.status === 'failed');
  const visibleOutputs = view?.surface?.visible_outputs ?? [];
  const expandedRun =
    expandedRunId && view?.expanded_run?.run_id === expandedRunId ? (view.expanded_run as FactoryRunDetailResponse) : null;

  return {
    status,
    latestSnapshot,
    summary,
    capabilities,
    actorPermissions,
    sectionErrors,
    snapshotCompletionRatio,
    snapshotFailureCount,
    snapshotDegraded,
    factoryRuns,
    failedRuns,
    visibleOutputs,
    expandedRun,
  };
}
