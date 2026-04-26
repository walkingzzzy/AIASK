'use client';

import { Badge, DataTable, SectionCard } from '@/components/ui';
import { ErrorState, LoadingState } from '@/components/status-state';

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function rowsFrom(value: unknown, ...keys: string[]) {
  const record = asRecord(value);
  for (const key of keys) {
    const raw = record[key];
    if (Array.isArray(raw)) return raw.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item));
  }
  if (Array.isArray(value)) return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item));
  return [];
}

function compactRows(rows: Record<string, unknown>[], limit = 8) {
  return rows.slice(0, limit).map((row, index) => ({
    id: String(row.id ?? row.run_id ?? row.strategy_id ?? row.snapshot_date ?? row.index_version ?? index + 1),
    status: String(row.status ?? row.pipeline_status ?? row.dispatch_status ?? '-'),
    date: String(row.snapshot_date ?? row.started_at ?? row.created_at ?? row.built_at ?? row.updated_at ?? '-'),
    metric: String(row.score ?? row.rank ?? row.profile_count ?? row.count ?? row.total_count ?? '-'),
    summary: String(row.name ?? row.title ?? row.message ?? row.index_name ?? row.strategy_id ?? row.run_id ?? '-'),
  }));
}

function ErrorList({ errors }: { errors: Array<string | null> }) {
  const actual = errors.filter((item): item is string => Boolean(item));
  if (!actual.length) return null;
  return (
    <div className="mt-3 grid gap-2">
      {actual.map((error) => <ErrorState key={error} text={error} />)}
    </div>
  );
}

export function StrategyFactoryRawArtifactsPanel({
  dailySnapshots,
  latestTopn,
  runTopn,
  dispatchStatus,
  expandedRunId,
  lastDispatchId,
  isPending,
  errors,
}: {
  dailySnapshots: unknown;
  latestTopn: unknown;
  runTopn: unknown;
  dispatchStatus: unknown;
  expandedRunId: string | null;
  lastDispatchId: string | null;
  isPending: boolean;
  errors: Array<string | null>;
}) {
  const snapshotRows = compactRows(rowsFrom(dailySnapshots, 'items', 'snapshots', 'daily_snapshots'), 6);
  const latestRows = compactRows(rowsFrom(latestTopn, 'items', 'strategies', 'topn'), 8);
  const runRows = compactRows(rowsFrom(runTopn, 'items', 'strategies', 'topn'), 8);
  const dispatch = asRecord(dispatchStatus);
  const dispatchRows = lastDispatchId
    ? [{
        id: lastDispatchId,
        status: String(dispatch.status ?? dispatch.dispatch_status ?? '-'),
        date: String(dispatch.started_at ?? dispatch.updated_at ?? dispatch.created_at ?? '-'),
        metric: String(dispatch.progress ?? dispatch.progress_pct ?? '-'),
        summary: String(dispatch.message ?? dispatch.error ?? dispatch.request_id ?? '-'),
      }]
    : [];

  return (
    <SectionCard className="mt-0" data-testid="strategy-factory-raw-artifacts-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="eyebrow">Raw Artifacts</div>
          <h2 className="mt-2">工厂原始产物直读</h2>
          <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
            日快照、TopN、run TopN 和最近 dispatch 状态直接从原始接口读取。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={snapshotRows.length ? 'success' : 'neutral'}>快照 {snapshotRows.length}</Badge>
          <Badge variant={latestRows.length ? 'success' : 'neutral'}>TopN {latestRows.length}</Badge>
          <Badge variant={dispatchRows.length ? 'info' : 'neutral'}>Dispatch {lastDispatchId ? '已选择' : '未选择'}</Badge>
        </div>
      </div>
      {isPending ? <LoadingState text="加载工厂原始产物..." /> : null}
      <ErrorList errors={errors} />
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <div>
          <h3 className="mt-0 text-sm">日快照</h3>
          <DataTable rows={snapshotRows} pageSize={6} emptyText="暂无日快照" />
        </div>
        <div>
          <h3 className="mt-0 text-sm">最新 TopN</h3>
          <DataTable rows={latestRows} pageSize={8} emptyText="暂无最新 TopN" />
        </div>
        <div>
          <h3 className="mt-0 text-sm">Run TopN {expandedRunId ? `· ${expandedRunId}` : ''}</h3>
          <DataTable rows={runRows} pageSize={8} emptyText="选择 run 后查看 TopN" />
        </div>
        <div>
          <h3 className="mt-0 text-sm">Dispatch 状态</h3>
          <DataTable rows={dispatchRows} pageSize={4} emptyText="还没有当前页面触发的 dispatch" />
        </div>
      </div>
    </SectionCard>
  );
}

export function StrategyFactoryVectorGovernancePanel({
  vectorHealth,
  vectorIndexes,
  vectorSnapshots,
  canViewOperatorPanels,
  isPending,
  errors,
  onReconcile,
  onRebuild,
  onCleanupDryRun,
  reconcilePending,
  rebuildPending,
  cleanupPending,
}: {
  vectorHealth: unknown;
  vectorIndexes: unknown;
  vectorSnapshots: unknown;
  canViewOperatorPanels: boolean;
  isPending: boolean;
  errors: Array<string | null>;
  onReconcile: () => void;
  onRebuild: () => void;
  onCleanupDryRun: () => void;
  reconcilePending: boolean;
  rebuildPending: boolean;
  cleanupPending: boolean;
}) {
  const health = asRecord(vectorHealth);
  const healthRows = Object.keys(health).length
    ? [{
        id: String(health.index_name ?? 'vector-health'),
        status: String(health.status ?? health.health_status ?? '-'),
        date: String(health.checked_at ?? health.updated_at ?? '-'),
        metric: String(health.index_count ?? health.version_count ?? health.profile_count ?? '-'),
        summary: String(health.message ?? health.reason ?? health.backend ?? '-'),
      }]
    : [];
  const indexRows = compactRows(rowsFrom(vectorIndexes, 'items', 'indexes', 'registries'), 8);
  const snapshotRows = compactRows(rowsFrom(vectorSnapshots, 'items', 'snapshots'), 8);

  return (
    <SectionCard className="mt-0" data-testid="strategy-factory-vector-governance-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="eyebrow">Vector Governance</div>
          <h2 className="mt-2">向量索引治理</h2>
          <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
            索引健康、索引注册表和快照在这里直读；维护动作只对管理员开放。
          </p>
        </div>
        {canViewOperatorPanels ? (
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={onReconcile} disabled={reconcilePending} className="action-chip cursor-pointer text-sm text-text-primary disabled:opacity-50">
              {reconcilePending ? '对账中' : '索引对账'}
            </button>
            <button type="button" onClick={onRebuild} disabled={rebuildPending} className="action-chip cursor-pointer text-sm text-text-primary disabled:opacity-50">
              {rebuildPending ? '重建中' : '重建索引'}
            </button>
            <button type="button" onClick={onCleanupDryRun} disabled={cleanupPending} className="action-chip cursor-pointer text-sm text-text-primary disabled:opacity-50">
              {cleanupPending ? '检查中' : '清理 dry-run'}
            </button>
          </div>
        ) : <Badge variant="neutral">只读</Badge>}
      </div>
      {isPending ? <LoadingState text="加载向量治理状态..." /> : null}
      <ErrorList errors={errors} />
      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <div>
          <h3 className="mt-0 text-sm">健康状态</h3>
          <DataTable rows={healthRows} pageSize={4} emptyText="暂无健康状态" />
        </div>
        <div>
          <h3 className="mt-0 text-sm">索引注册表</h3>
          <DataTable rows={indexRows} pageSize={8} emptyText="暂无索引注册记录" />
        </div>
        <div>
          <h3 className="mt-0 text-sm">索引快照</h3>
          <DataTable rows={snapshotRows} pageSize={8} emptyText="暂无索引快照" />
        </div>
      </div>
    </SectionCard>
  );
}
