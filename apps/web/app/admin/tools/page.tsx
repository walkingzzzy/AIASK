'use client';

import { useMemo, useState } from 'react';
import type { StrategyOperatorJobRecord, StrategyOperatorParityResponse } from '@aiask/shared-types';
import ResultWorkbench from '@/components/result-workbench';
import { PageContainer, SectionCard, KpiGrid, KpiCard, Badge } from '@/components/ui';
import { BarChart } from '@/components/charts';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { ErrorState } from '@/components/status-state';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';

/**
 * T-049: MCP Tools Dashboard
 * Shows tool call frequency, latency, error rate, and health status.
 */
export default function ToolsDashboardPage() {
  const [lastManualRefreshAt, setLastManualRefreshAt] = useState<string | null>(null);
  const [operatorAction, setOperatorAction] = useState('factory_dispatch_run');
  const [operatorStrategyId, setOperatorStrategyId] = useState('');
  const [operatorJobId, setOperatorJobId] = useState<string | null>(null);
  const statsQ = useApiQuery<unknown>('/admin/mcp-stats', {
    refetchInterval: 15000,
    parse: (raw) => raw,
  });
  const parityQ = useApiQuery<StrategyOperatorParityResponse>('/strategy-market/operator/parity', {
    refetchInterval: 60000,
    nonFatal: true,
  });
  const operatorJobQ = useApiQuery<StrategyOperatorJobRecord>(
    operatorJobId ? `/strategy-market/operator/jobs/${encodeURIComponent(operatorJobId)}` : null,
    {
      enabled: Boolean(operatorJobId),
      refetchInterval: 3000,
      nonFatal: true,
    },
  );
  const operatorJobApi = useApiMutation<StrategyOperatorJobRecord>({
    critical: true,
    successToast: 'MCP 运营任务已提交',
    onSuccess: (record) => setOperatorJobId(record.job.job_id),
  });

  const data = useMemo(() => {
    const raw = (statsQ.data ?? {}) as Record<string, unknown>;
    const tools = Array.isArray(raw.tools) ? raw.tools : [];
    return {
      totalCalls: Number(raw.totalCalls ?? 0),
      avgLatency: Number(raw.avgLatency ?? 0),
      p99Latency: Number(raw.p99Latency ?? 0),
      errorRate: Number(raw.errorRate ?? 0),
      failureModes: Array.isArray(raw.failureModes)
        ? raw.failureModes.map((item: Record<string, unknown>) => ({
          mode: String(item.mode ?? 'unknown'),
          count: Number(item.count ?? 0),
        })).filter((item) => item.count > 0)
        : [],
      queue: {
        shared: Number((raw.queue as Record<string, unknown> | undefined)?.shared ?? 0),
        dedicated: Number((raw.queue as Record<string, unknown> | undefined)?.dedicated ?? 0),
        poolSize: Number((raw.queue as Record<string, unknown> | undefined)?.poolSize ?? 0),
        acquireTimeoutMs: Number((raw.queue as Record<string, unknown> | undefined)?.acquireTimeoutMs ?? 0),
        toolTimeoutMs: Number((raw.queue as Record<string, unknown> | undefined)?.toolTimeoutMs ?? 0),
      },
      reachable: raw.reachable !== false,
      matched: raw.matched !== false,
      toolCount: Number(raw.toolCount ?? 0),
      expectedTools: Number(raw.expectedTools ?? 0),
      transportKind: String((raw.transport as Record<string, unknown> | undefined)?.transportKind ?? raw.source ?? 'unknown'),
      fallbackReason: String(raw.fallbackReason ?? '').trim(),
      tools: tools.slice(0, 20).map((t: Record<string, unknown>) => ({
        name: String(t.name ?? ''),
        calls: Number(t.calls ?? 0),
        avgMs: Number(t.avgMs ?? 0),
        p99Ms: Number(t.p99Ms ?? 0),
        errors: Number(t.errors ?? 0),
        status: String(t.status ?? 'healthy'),
        failureModes: Array.isArray(t.failureModes)
          ? t.failureModes.map((item: Record<string, unknown>) => ({
            mode: String(item.mode ?? 'unknown'),
            count: Number(item.count ?? 0),
          })).filter((item) => item.count > 0)
          : [],
      })),
    };
  }, [statsQ.data]);

  const barData = data.tools.map((t) => ({
    label: t.name.replace(/^(get_|create_|update_|delete_)/, ''),
    value: t.calls,
  }));
  const abnormalTools = useMemo(
    () => data.tools.filter((tool) => tool.status !== 'healthy' || tool.errors > 0).slice(0, 6),
    [data.tools],
  );
  const sortedTools = useMemo(
    () =>
      [...data.tools].sort((a, b) => {
        const aRisk = a.status !== 'healthy' || a.errors > 0 ? 1 : 0;
        const bRisk = b.status !== 'healthy' || b.errors > 0 ? 1 : 0;
        if (aRisk !== bRisk) return bRisk - aRisk;
        return b.calls - a.calls;
      }),
    [data.tools],
  );
  const operatorActions = useMemo(
    () => (parityQ.data?.coverage ?? []).filter((item) => item.job_action).map((item) => item.action),
    [parityQ.data],
  );
  const activeOperatorJob = operatorJobQ.data ?? operatorJobApi.data;
  const failureModeLabels: Record<string, string> = {
    timeout: '超时',
    transport: '传输',
    validation: '校验',
    tool_error: '工具错误',
    unknown: '未知',
  };

  const STATUS_COLORS: Record<string, 'success' | 'warning' | 'danger'> = {
    healthy: 'success',
    degraded: 'warning',
    down: 'danger',
  };
  const statsStatus = statsQ.isFetching ? '刷新中' : statsQ.data ? '统计可用' : '等待统计';
  const latestStatsRefreshText = statsQ.dataUpdatedAt
    ? new Date(statsQ.dataUpdatedAt).toLocaleString('zh-CN')
    : '等待首个工具快照';
  const driftHint = !data.matched
    ? `当前运行时工具数 ${data.toolCount}，配置期望值 ${data.expectedTools}，属于配置漂移而不是服务不可用。`
    : '';
  const mcpHealthLabel = !data.reachable
    ? 'MCP 不可达'
    : !data.matched
      ? 'MCP 配置漂移'
      : 'MCP 正常';

  async function refreshToolStats() {
    await statsQ.refetch();
    setLastManualRefreshAt(new Date().toLocaleString('zh-CN'));
  }

  const pageActions = [
    {
      id: 'admin-tools.refresh',
      label: '刷新工具统计',
      description: '重新拉取 MCP 统计与健康快照',
      keywords: ['刷新', '统计'],
      scope: 'page' as const,
      pageKey: 'admin-tools',
      run: async () => {
        await refreshToolStats();
        return { message: '已刷新工具统计' };
      },
    },
    {
      id: 'admin-tools.focus-abnormal',
      label: '聚焦异常工具区域',
      description: '滚动到异常工具列表，优先处理风险项',
      keywords: ['异常', '工具'],
      scope: 'page' as const,
      pageKey: 'admin-tools',
      run: () => {
        document.getElementById('admin-tools-abnormal-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return { message: '已聚焦异常工具区域' };
      },
    },
    {
      id: 'admin-tools.focus-mcp-jobs',
      label: '聚焦 MCP Job 队列',
      description: '滚动到 MCP 运营任务提交与轮询区域',
      keywords: ['MCP Job', '任务'],
      scope: 'page' as const,
      pageKey: 'admin-tools',
      run: () => {
        document.getElementById('admin-tools-mcp-job-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return { message: '已聚焦 MCP Job 队列' };
      },
    },
  ];

  usePageActions(pageActions);
  const queueDepth = data.queue.shared + data.queue.dedicated;
  const topFailureMode = data.failureModes[0];
  const toolsSummary = `当前状态 ${mcpHealthLabel}，总调用 ${data.totalCalls} 次，错误率 ${data.errorRate.toFixed(2)}%，异常工具 ${abnormalTools.length} 个，队列 ${queueDepth}，传输方式 ${data.transportKind}。`;
  const toolsResult = buildLocalResultContract({
    summary: toolsSummary,
    availableViews: abnormalTools.length > 1 ? ['compare'] : [],
    pageActions,
    preferredActionIds: ['admin-tools.refresh', 'admin-tools.focus-abnormal'],
    recommendedLinks: [
      { id: 'admin-tools-open-skills-link', label: '技能中心', href: '/skills?from=admin-tools' },
      { id: 'admin-tools-open-data-link', label: '数据中心', href: '/data?tab=resource' },
      { id: 'admin-tools-open-audit-link', label: '审计日志', href: '/settings/audit-log' },
    ],
    evidence: [
      { label: 'MCP 状态', value: mcpHealthLabel },
      { label: '总调用', value: String(data.totalCalls) },
      { label: '错误率', value: `${data.errorRate.toFixed(2)}%` },
      { label: '异常工具', value: String(abnormalTools.length) },
      { label: '失败模式', value: topFailureMode ? `${failureModeLabels[topFailureMode.mode] ?? topFailureMode.mode} ${topFailureMode.count}` : '无' },
      { label: '队列深度', value: String(queueDepth) },
      { label: '传输方式', value: data.transportKind },
    ],
    riskNotes: [
      ...(driftHint ? [driftHint] : []),
      ...(data.fallbackReason ? [data.fallbackReason] : []),
      ...(statsQ.error ? [statsQ.error] : []),
    ],
    freshness: statsQ.dataUpdatedAt ? { updatedAt: new Date(statsQ.dataUpdatedAt).toISOString(), label: '统计快照' } : null,
    platformMeta: {
      sourceTool: 'mcp-stats',
      sourceChain: ['admin-tools', data.transportKind],
      degraded: !data.reachable || !data.matched || Boolean(statsQ.error),
      fallbackReason: [data.fallbackReason, statsQ.error].filter((item): item is string => Boolean(item)),
    },
    workbenchTask: defaultWorkbenchTask('admin-tools', '复查 MCP 工具健康', '/admin/tools', 'tool-registry-review', {
      reachable: data.reachable,
      matched: data.matched,
      abnormalTools: abnormalTools.length,
    }),
  });

  usePageContext({
    pageKey: 'admin-tools',
    title: 'MCP 工具仪表盘',
    summary: toolsSummary,
    objectType: 'tool-registry',
    objectId: data.transportKind,
    resultType: 'mcp-tool-dashboard',
    tags: [
      mcpHealthLabel,
      `${abnormalTools.length} 个异常工具`,
      `${data.toolCount}/${data.expectedTools || data.toolCount} 工具`,
      `${data.transportKind} 传输`,
    ],
    suggestions: [
      '先总结当前 MCP 工具健康状态和最需要处理的异常项',
      '如果需要联动，请优先刷新统计或聚焦异常工具区域',
      '解释当前是服务不可用还是配置漂移',
    ],
    recommendedActions: toolsResult.recommendedActions ?? [],
    recommendedLinks: toolsResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(toolsResult.evidence),
    riskNotes: toolsResult.riskNotes ?? [],
    freshness: toolsResult.freshness ?? null,
    raw: {
      totalCalls: data.totalCalls,
      errorRate: data.errorRate,
      abnormalTools: abnormalTools.length,
      reachable: data.reachable,
      matched: data.matched,
      toolCount: data.toolCount,
      expectedTools: data.expectedTools,
      transportKind: data.transportKind,
      fallbackReason: data.fallbackReason || null,
      failureModes: data.failureModes,
      queue: data.queue,
    },
  });

  if (statsQ.error) {
    return (
      <PageContainer>
        <h1 className="text-lg font-semibold mb-4">🔧 MCP 工具仪表盘</h1>
        <ErrorState
          text={statsQ.error}
          hint="当前页面需要管理员权限；请求失败时不再伪装成空数据。"
          onRetry={() => statsQ.refetch()}
        />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <h1 className="text-lg font-semibold mb-4">🔧 MCP 工具仪表盘</h1>

      <ResultWorkbench pageKey="admin-tools" title="MCP 工具工作台" result={toolsResult} />

      <SectionCard className="mb-4 p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="mt-0 mb-1 text-base font-semibold">优先处理工具健康</h2>
            <p className="m-0 text-sm text-text-secondary">
              先看异常工具和延迟，再决定是否需要继续下钻调用明细。这个页面现在首屏只保留一个稳定低风险主动作。
            </p>
          </div>
          <button
            type="button"
            onClick={() => void refreshToolStats()}
            disabled={statsQ.isFetching}
            data-testid="page-primary-action"
            data-action-testid="admin-tools-refresh-action"
            className="inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {statsQ.isFetching ? '刷新中...' : '刷新工具统计'}
          </button>
        </div>
        <div
          data-testid="page-primary-status"
          className="mt-4 rounded-xl border border-border bg-surface-alt/35 px-3 py-3 text-sm"
        >
          <div className="font-medium text-text-primary">工具统计状态：{statsStatus}</div>
          <p className="mt-1 mb-0 text-xs text-text-secondary">
            总调用 {data.totalCalls.toLocaleString()} ｜ 错误率 {data.errorRate.toFixed(2)}% ｜ 异常工具{' '}
            {abnormalTools.length} 个
          </p>
          {driftHint ? (
            <p className="mt-2 mb-0 text-xs text-amber-700">{driftHint}</p>
          ) : null}
          <p className="mt-2 mb-0 text-xs text-text-secondary">
            最近快照：{latestStatsRefreshText}
            {lastManualRefreshAt ? ` ｜ 手动刷新：${lastManualRefreshAt}` : ''}
          </p>
        </div>
      </SectionCard>

      <SectionCard id="admin-tools-mcp-job-section" className="mb-4 p-4" data-testid="admin-tools-mcp-jobs">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="mt-0 mb-1 text-base font-semibold">MCP Job 管理</h2>
            <p className="m-0 text-sm text-text-secondary">
              高权限策略工厂动作通过后台任务提交，返回 job id 后在这里轮询状态。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={parityQ.data?.unmapped_actions === 0 ? 'success' : 'warning'}>
              action parity {parityQ.data ? `${parityQ.data.mapped_actions}/${parityQ.data.total_actions}` : '-'}
            </Badge>
            <Badge variant="info">job actions {operatorActions.length}</Badge>
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-[1fr_1fr_auto]">
          <select
            value={operatorAction}
            onChange={(event) => setOperatorAction(event.target.value)}
            className="rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary outline-none"
          >
            {(operatorActions.length ? operatorActions : ['factory_dispatch_run']).map((action) => (
              <option key={action} value={action}>
                {action}
              </option>
            ))}
          </select>
          <input
            value={operatorStrategyId}
            onChange={(event) => setOperatorStrategyId(event.target.value)}
            placeholder="strategy_id，可留空"
            className="rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary outline-none"
          />
          <button
            type="button"
            disabled={operatorJobApi.isPending}
            onClick={() => {
              if (!window.confirm(`确认提交 MCP 运营任务 ${operatorAction}？`)) return;
              operatorJobApi.trigger(
                '/strategy-market/operator/jobs',
                { method: 'POST' },
                {
                  action: operatorAction,
                  strategy_id: operatorStrategyId.trim() || undefined,
                  params: {},
                  confirmed: true,
                  confirmation_text: operatorAction,
                  reason: 'admin_tools_mcp_job_panel',
                  timeout_ms: operatorAction === 'factory_run_once' ? 300000 : 120000,
                },
              );
            }}
            className="inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {operatorJobApi.isPending ? '提交中...' : '提交 Job'}
          </button>
        </div>
        {operatorJobApi.error ? <p className="mt-3 mb-0 text-xs text-danger">{operatorJobApi.error}</p> : null}
        {activeOperatorJob ? (
          <div className="mt-4 rounded-xl border border-border bg-surface-alt/35 px-3 py-3 text-sm">
            <div className="font-medium text-text-primary">
              {activeOperatorJob.action} · {activeOperatorJob.job.status}
            </div>
            <p className="mt-1 mb-0 text-xs text-text-secondary">
              job {activeOperatorJob.job.job_id} ｜ poll {activeOperatorJob.poll_path}
              {activeOperatorJob.strategy_id ? ` ｜ strategy ${activeOperatorJob.strategy_id}` : ''}
            </p>
            {activeOperatorJob.job.error ? (
              <p className="mt-2 mb-0 text-xs text-danger">{activeOperatorJob.job.error}</p>
            ) : null}
          </div>
        ) : null}
      </SectionCard>

      <KpiGrid cols={4}>
        <KpiCard title="总调用次数" value={data.totalCalls.toLocaleString()} />
        <KpiCard title="平均延迟" value={`${data.avgLatency.toFixed(0)}ms`} />
        <KpiCard title="P99 延迟" value={`${data.p99Latency.toFixed(0)}ms`} />
        <KpiCard title="错误率" value={`${data.errorRate.toFixed(2)}%`} />
      </KpiGrid>

      <SectionCard className="mt-4 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="mt-0 text-sm font-semibold">MCP 失败模式聚合</h3>
            <p className="mt-1 mb-0 text-xs text-text-secondary">
              聚合 timeout、transport、validation 和 tool error，用于判断 P99 尾延迟是排队、连接还是工具侧失败。
            </p>
          </div>
          <Badge variant={queueDepth > 0 ? 'warning' : 'success'}>
            队列 {queueDepth} / 池 {data.queue.poolSize || '-'}
          </Badge>
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {(data.failureModes.length ? data.failureModes : [{ mode: 'none', count: 0 }]).map((item) => (
            <div key={item.mode} className="rounded-xl border border-glass-border bg-surface-alt/35 px-3 py-3">
              <div className="text-xs text-text-secondary">{failureModeLabels[item.mode] ?? (item.mode === 'none' ? '暂无失败' : item.mode)}</div>
              <div className="mt-2 text-xl font-semibold text-text-primary">{item.count}</div>
            </div>
          ))}
        </div>
        <p className="mt-3 mb-0 text-xs text-text-secondary">
          acquire timeout {data.queue.acquireTimeoutMs || '-'}ms ｜ tool timeout {data.queue.toolTimeoutMs || '-'}ms ｜ shared queue {data.queue.shared} ｜ dedicated queue {data.queue.dedicated}
        </p>
      </SectionCard>

      {abnormalTools.length > 0 && (
        <SectionCard id="admin-tools-abnormal-section" className="mt-4 p-4">
          <h3 className="mt-0 text-sm font-semibold">优先关注工具</h3>
          <p className="mt-1 text-xs text-text-secondary">
            以下工具当前存在降级、不可用或错误次数偏高的情况，已前置到首屏方便管理员优先处理。
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {abnormalTools.map((tool) => (
              <div
                key={tool.name}
                className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary"
              >
                <span className="font-medium text-text-primary">{tool.name}</span>
                {' · '}
                {tool.status !== 'healthy' ? `状态 ${tool.status}` : `错误 ${tool.errors} 次`}
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {barData.length > 0 && (
        <SectionCard className="mt-4 p-3">
          <h3 className="mt-0 text-sm font-semibold">调用频次 Top 20</h3>
          <BarChart items={barData} height={280} />
        </SectionCard>
      )}

      {data.tools.length > 0 && (
        <SectionCard className="mt-4 p-3">
          <h3 className="mt-0 text-sm font-semibold">工具健康度矩阵</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-glass-border text-text-secondary text-xs">
                  <th className="text-left py-2 px-2">工具名</th>
                  <th className="text-right py-2 px-2">调用数</th>
                  <th className="text-right py-2 px-2">平均延迟</th>
                  <th className="text-right py-2 px-2">P99</th>
                  <th className="text-right py-2 px-2">错误数</th>
                  <th className="text-left py-2 px-2">失败模式</th>
                  <th className="text-center py-2 px-2">状态</th>
                </tr>
              </thead>
              <tbody>
                {sortedTools.map((t) => (
                  <tr key={t.name} className="border-b border-glass-border/50 hover:bg-white/5">
                    <td className="py-2 px-2 font-mono text-xs">{t.name}</td>
                    <td className="py-2 px-2 text-right">{t.calls}</td>
                    <td className="py-2 px-2 text-right">{t.avgMs.toFixed(0)}ms</td>
                    <td className="py-2 px-2 text-right">{t.p99Ms.toFixed(0)}ms</td>
                    <td className={`py-2 px-2 text-right ${t.errors > 0 ? 'text-danger' : ''}`}>{t.errors}</td>
                    <td className="py-2 px-2 text-xs text-text-secondary">
                      {t.failureModes.length
                        ? t.failureModes.map((item) => `${failureModeLabels[item.mode] ?? item.mode}:${item.count}`).join(' / ')
                        : '-'}
                    </td>
                    <td className="py-2 px-2 text-center">
                      <Badge variant={STATUS_COLORS[t.status] ?? 'info'}>
                        {t.status === 'healthy' ? '🟢' : t.status === 'degraded' ? '🟡' : '🔴'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {!statsQ.data && (
        <SectionCard className="mt-4">
          <p className="text-text-secondary text-sm text-center py-8">
            {statsQ.isFetching ? '加载工具统计...' : '暂无统计数据'}
          </p>
        </SectionCard>
      )}
    </PageContainer>
  );
}
