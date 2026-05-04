'use client';

import { useMemo, useState } from 'react';
import type {
  StrategyCapabilityDiagnosticsResponse,
  StrategyCapabilityGapIssue,
  StrategyCapabilityGapIssueKind,
  StrategyCapabilityMatchRow,
} from '../types';
import { Badge, SectionCard } from '@/components/ui';
import { ErrorState, LoadingState } from '@/components/status-state';

type IssueFilter = StrategyCapabilityGapIssueKind | 'all';

const ISSUE_LABELS: Record<StrategyCapabilityGapIssueKind, string> = {
  backend_without_frontend: '后端已有前端未接',
  frontend_without_backend: '前端承诺后端不可用',
  internal_not_user_exposed: '内部存在未暴露',
  naming_or_field_mismatch: '命名/字段不一致',
};

const ISSUE_FILTERS: Array<{ key: IssueFilter; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'backend_without_frontend', label: ISSUE_LABELS.backend_without_frontend },
  { key: 'frontend_without_backend', label: ISSUE_LABELS.frontend_without_backend },
  { key: 'internal_not_user_exposed', label: ISSUE_LABELS.internal_not_user_exposed },
  { key: 'naming_or_field_mismatch', label: ISSUE_LABELS.naming_or_field_mismatch },
];

function severityVariant(severity: string): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
  if (severity === 'p0') return 'danger';
  if (severity === 'p1') return 'warning';
  if (severity === 'p2') return 'info';
  return 'neutral';
}

function statusVariant(status: string): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
  if (status === 'matched') return 'success';
  if (status === 'gap') return 'warning';
  if (status === 'mismatch') return 'info';
  return 'neutral';
}

function compact(values: string[], limit = 3) {
  if (!values.length) return '-';
  const head = values.slice(0, limit).join(' / ');
  const rest = values.length - limit;
  return rest > 0 ? `${head} +${rest}` : head;
}

function rowMatchesFilter(row: StrategyCapabilityMatchRow, filter: IssueFilter) {
  if (filter === 'all') return true;
  return row.issues.some((issue) => issue.kind === filter);
}

function renderIssues(issues: StrategyCapabilityGapIssue[]) {
  if (!issues.length) {
    return <Badge variant="success">无显式缺口</Badge>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {issues.map((issueItem) => (
        <Badge key={`${issueItem.kind}:${issueItem.summary}`} variant={severityVariant(issueItem.severity)}>
          {ISSUE_LABELS[issueItem.kind]}
        </Badge>
      ))}
    </div>
  );
}

function DiagnosticRow({ row }: { row: StrategyCapabilityMatchRow }) {
  const primaryIssue = row.issues[0] ?? null;
  return (
    <tr className="border-t border-border align-top">
      <td className="min-w-[220px] px-3 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-text-primary">{row.label}</span>
          <Badge variant={statusVariant(row.status)}>{row.status}</Badge>
          <Badge variant={severityVariant(row.severity)}>{row.severity.toUpperCase()}</Badge>
        </div>
        <div className="mt-1 text-xs leading-5 text-text-secondary">{row.user_intent}</div>
      </td>
      <td className="min-w-[260px] px-3 py-3 text-xs leading-5 text-text-secondary">
        <div>
          <span className="font-medium text-text-primary">MCP</span>：{compact(row.mcp.manager_actions, 5)}
        </div>
        <div>
          <span className="font-medium text-text-primary">产物</span>：{compact(row.factory_artifacts.artifact_ids, 4)}
        </div>
        <div>
          <span className="font-medium text-text-primary">BFF</span>：{compact(row.bff.endpoints, 2)}
        </div>
        <div>
          <span className="font-medium text-text-primary">前端</span>：{compact(row.frontend.page_surfaces, 2)}
        </div>
      </td>
      <td className="min-w-[260px] px-3 py-3">
        {renderIssues(row.issues)}
        {primaryIssue ? (
          <div className="mt-2 text-xs leading-5 text-text-secondary">{primaryIssue.summary}</div>
        ) : null}
      </td>
      <td className="min-w-[260px] px-3 py-3 text-xs leading-5 text-text-secondary">
        {primaryIssue?.user_impact ?? row.user_visible_impact}
      </td>
    </tr>
  );
}

export function StrategyCapabilityGapPanel({
  diagnostics,
  isPending,
  error,
}: {
  diagnostics: StrategyCapabilityDiagnosticsResponse | null;
  isPending: boolean;
  error: string | null;
}) {
  const [filter, setFilter] = useState<IssueFilter>('all');
  const filteredRows = useMemo(
    () => (diagnostics?.items ?? []).filter((row) => rowMatchesFilter(row, filter)),
    [diagnostics?.items, filter],
  );
  const criticalRows = diagnostics?.critical_unmatched ?? [];
  const summary = diagnostics?.summary ?? null;

  return (
    <SectionCard className="mt-0" data-testid="strategy-capability-gap-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="eyebrow">能力诊断</div>
          <h2 className="mt-2">应用功能 / MCP / 工厂产物缺口表</h2>
          <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
            当前表按 MCP manager、策略工厂产物、BFF 接口、前端入口四层归一，直接标出会影响用户体验的未匹配项。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={summary && summary.gap + summary.mismatch === 0 ? 'success' : 'warning'}>
            缺口 {summary ? summary.gap + summary.mismatch : '-'}
          </Badge>
          <Badge variant={summary?.frontend_without_backend ? 'danger' : 'success'}>
            前端空承诺 {summary?.frontend_without_backend ?? '-'}
          </Badge>
          <Badge variant={summary?.backend_without_frontend ? 'warning' : 'success'}>
            后端未接 {summary?.backend_without_frontend ?? '-'}
          </Badge>
        </div>
      </div>

      {isPending ? <LoadingState text="加载能力缺口诊断..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      {summary ? (
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <div className="metric-tile px-4 py-4">
            <div className="metric-label">总功能</div>
            <div className="mt-2 text-base font-semibold text-text-primary">{summary.total}</div>
          </div>
          <div className="metric-tile px-4 py-4">
            <div className="metric-label">已匹配</div>
            <div className="mt-2 text-base font-semibold text-text-primary">{summary.matched}</div>
          </div>
          <div className="metric-tile px-4 py-4">
            <div className="metric-label">P1/P0</div>
            <div className="mt-2 text-base font-semibold text-text-primary">{summary.p0 + summary.p1}</div>
          </div>
          <div className="metric-tile px-4 py-4">
            <div className="metric-label">内部未暴露</div>
            <div className="mt-2 text-base font-semibold text-text-primary">{summary.internal_not_user_exposed}</div>
          </div>
          <div className="metric-tile px-4 py-4">
            <div className="metric-label">MCP runtime</div>
            <div className="mt-2 text-base font-semibold text-text-primary">
              {diagnostics?.mcp_runtime?.reachable ? 'reachable' : 'unknown'}
            </div>
          </div>
        </div>
      ) : null}

      {criticalRows.length ? (
        <div className="mt-4 rounded border border-border bg-surface-alt px-4 py-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="m-0 text-sm font-semibold text-text-primary">关键未匹配项</h3>
            <Badge variant="warning">{criticalRows.length} 项</Badge>
          </div>
          <div className="mt-3 grid gap-2 lg:grid-cols-2">
            {criticalRows.slice(0, 6).map((row) => (
              <div key={row.id} className="rounded border border-border bg-surface px-3 py-3 text-xs leading-5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-text-primary">{row.label}</span>
                  <Badge variant={severityVariant(row.severity)}>{row.severity.toUpperCase()}</Badge>
                </div>
                <div className="mt-1 text-text-secondary">{row.issues[0]?.user_impact ?? row.user_visible_impact}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        {ISSUE_FILTERS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setFilter(item.key)}
            className={`action-chip cursor-pointer text-xs ${filter === item.key ? 'border-primary/40 text-primary' : 'text-text-secondary'}`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="mt-4 overflow-x-auto rounded border border-border">
        <table className="min-w-full border-collapse bg-surface text-left">
          <thead className="bg-surface-alt text-xs text-text-secondary">
            <tr>
              <th className="px-3 py-3 font-medium">应用功能</th>
              <th className="px-3 py-3 font-medium">四层匹配</th>
              <th className="px-3 py-3 font-medium">问题类型</th>
              <th className="px-3 py-3 font-medium">用户影响</th>
            </tr>
          </thead>
          <tbody>
            {filteredRows.map((row) => (
              <DiagnosticRow key={row.id} row={row} />
            ))}
          </tbody>
        </table>
      </div>

      {!filteredRows.length && !isPending ? (
        <p className="mb-0 mt-3 text-sm text-text-secondary">当前筛选下没有诊断项。</p>
      ) : null}
    </SectionCard>
  );
}
