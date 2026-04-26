'use client';

import { useEffect, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import CollapsibleSectionCard from '@/components/collapsible-section-card';
import LightOverviewHero from '@/components/light-overview-hero';
import ProgressiveWorkbenchSection from '@/components/progressive-workbench-section';
import { Badge, PageContainer, SectionCard } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useMobile } from '@/hooks/use-mobile';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStableSearchParams } from '@/hooks/use-stable-search-params';
import { EmptyState } from '@/components/status-state';
import { fmtNum } from '@/lib/data-utils';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';
import type { ExecutionArtifactResponse } from '@aiask/shared-types';
import { buildExecutionArtifactDetailHref, isSurfacePlaceholderId } from '@/lib/surface-contracts';

function warningBadgeVariant(count: number) {
  if (count > 0) return 'warning' as const;
  return 'success' as const;
}

export default function ExecutionArtifactDetailPage() {
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
  const params = useParams<{ artifactId: string }>();
  const router = useRouter();
  const searchParams = useStableSearchParams();
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const addWorkbenchTask = useWorkbenchStore((state) => state.addTask);
  const workbenchContext = useWorkbenchStore((state) => selectActiveWorkspace(state).context);

  const artifactId = String(params?.artifactId ?? '').trim();
  const emptyDetailContract = isSurfacePlaceholderId(artifactId);
  const accountId = searchParams.get('account_id') ?? workbenchContext.accountId ?? '';
  const queryPath = useMemo(() => {
    if (!artifactId || emptyDetailContract) return null;
    const query = new URLSearchParams();
    if (accountId) query.set('accountId', accountId);
    return `/execution/artifact/${encodeURIComponent(artifactId)}${query.toString() ? `?${query.toString()}` : ''}`;
  }, [accountId, artifactId, emptyDetailContract]);
  const artifactQ = useApiQuery<ExecutionArtifactResponse>(queryPath, {
    nonFatal: emptyDetailContract,
    fallbackData: emptyDetailContract
      ? {
          artifactId,
          count: 0,
          latestTaskId: null,
          latestTask: null,
          taskIds: [],
          detail: null,
          sourceTools: {},
          argsMatched: { artifactId, accountId: accountId || undefined },
          result: { tasks: null, detail: null },
        }
      : null,
  });

  const latestTask = artifactQ.data?.latestTask ?? null;
  const detail = artifactQ.data?.detail ?? null;
  const warnings = detail?.warnings ?? [];
  const executionId = detail?.taskId ?? artifactQ.data?.latestTaskId ?? '';
  const stockCode = latestTask?.code ?? detail?.overview?.code ?? '';
  const performanceHref = useMemo(() => {
    const query = new URLSearchParams();
    query.set('mode', 'account');
    query.set('days', '30');
    if (accountId) query.set('account_id', accountId);
    if (executionId) query.set('execution_id', executionId);
    return `/performance?${query.toString()}`;
  }, [accountId, executionId]);
  const riskHref = useMemo(() => {
    const query = new URLSearchParams();
    query.set('lookbackDays', '30');
    if (accountId) query.set('account_id', accountId);
    return `/risk?${query.toString()}`;
  }, [accountId]);
  const executionHref = useMemo(() => {
    const query = new URLSearchParams();
    if (stockCode) query.set('code', stockCode);
    if (accountId) query.set('account_id', accountId);
    if (executionId) query.set('execution_id', executionId);
    if (!emptyDetailContract) query.set('artifact_id', artifactId);
    return `/execution?${query.toString()}`;
  }, [accountId, artifactId, emptyDetailContract, executionId, stockCode]);

  useEffect(() => {
    if (!artifactId) return;
    updateWorkbenchContext({
      stockCode: stockCode || null,
      accountId: accountId || null,
      executionId: executionId || null,
      artifactId,
    });
  }, [accountId, artifactId, executionId, stockCode, updateWorkbenchContext]);

  function openExecution() {
    addWorkbenchTask({
      pageKey: 'execution',
      title: executionId ? `回执行中心查看 ${executionId}` : `回执行中心查看 artifact ${artifactId}`,
      href: executionHref,
      kind: 'execution-review',
      payload: { accountId, executionId, artifactId },
    });
    router.push(executionHref);
  }

  function openPerformance() {
    addWorkbenchTask({
      pageKey: 'execution',
      title: executionId ? `去绩效中心复盘执行 ${executionId}` : `去绩效中心复盘 artifact ${artifactId}`,
      href: performanceHref,
      kind: 'performance-review',
      payload: { accountId, executionId, artifactId },
    });
    router.push(performanceHref);
  }

  function openRisk() {
    addWorkbenchTask({
      pageKey: 'execution',
      title: executionId ? `去风险中心复核执行 ${executionId}` : `去风险中心复核 artifact ${artifactId}`,
      href: riskHref,
      kind: 'risk-review',
      payload: { accountId, executionId, artifactId },
    });
    router.push(riskHref);
  }

  function openStock() {
    if (!stockCode) return;
    const href = `/stock?code=${encodeURIComponent(stockCode)}`;
    addWorkbenchTask({
      pageKey: 'execution',
      title: `查看 ${stockCode} 个股详情`,
      href,
      kind: 'stock-review',
      payload: { code: stockCode, accountId, executionId, artifactId },
    });
    router.push(href);
  }

  const artifactActions = emptyDetailContract ? [
    {
      id: 'artifact.open-execution',
      label: '回执行中心',
      description: '回执行中心继续查看执行上下文',
      keywords: ['执行中心', 'artifact'],
      scope: 'page' as const,
      pageKey: 'execution',
      run: () => {
        openExecution();
        return { message: '已打开执行中心' };
      },
    },
  ] : [
    {
      id: 'artifact.refresh',
      label: '刷新 artifact 详情',
      description: '重新加载当前 artifact 的任务与执行详情',
      keywords: ['artifact', '刷新'],
      scope: 'page' as const,
      pageKey: 'execution',
      run: async () => {
        await artifactQ.refetch();
        return { message: `已刷新 artifact ${artifactId}` };
      },
    },
    {
      id: 'artifact.open-execution',
      label: '回执行中心',
      description: '带着当前 artifact 和 task 上下文回到执行中心',
      keywords: ['执行中心', 'artifact'],
      scope: 'page' as const,
      pageKey: 'execution',
      run: () => {
        openExecution();
        return { message: '已打开执行中心' };
      },
    },
    {
      id: 'artifact.open-performance',
      label: '打开绩效中心',
      description: '进入绩效中心查看该 artifact 关联执行的收益表现',
      keywords: ['绩效', '复盘'],
      scope: 'page' as const,
      pageKey: 'execution',
      run: () => {
        openPerformance();
        return { message: '已打开绩效中心' };
      },
    },
    {
      id: 'artifact.open-risk',
      label: '打开风险中心',
      description: '进入风险中心复核当前 artifact 相关告警',
      keywords: ['风险', '告警'],
      scope: 'page' as const,
      pageKey: 'execution',
      run: () => {
        openRisk();
        return { message: '已打开风险中心' };
      },
    },
  ];
  usePageActions(artifactActions);
  const artifactSummary = emptyDetailContract
    ? '当前环境还没有可进入的 Artifact 详情数据，页面按空态契约渲染。'
    : `当前 artifact 为 ${artifactId}，关联任务 ${artifactQ.data?.count ?? 0} 条，最新任务 ${executionId || '未找到'}。`;
  const artifactResult = buildLocalResultContract({
    summary: artifactSummary,
    availableViews: artifactQ.data?.count && artifactQ.data.count > 1 ? ['compare'] : [],
    pageActions: artifactActions,
    preferredActionIds: emptyDetailContract
      ? ['artifact.open-execution']
      : ['artifact.refresh', 'artifact.open-execution', 'artifact.open-performance', 'artifact.open-risk'],
    recommendedLinks: [
      { id: 'artifact-link-execution', label: '执行中心', href: executionHref },
      { id: 'artifact-link-performance', label: '绩效中心', href: performanceHref },
      { id: 'artifact-link-risk', label: '风险中心', href: riskHref },
      ...(stockCode ? [{ id: 'artifact-link-stock', label: '个股详情', href: `/stock?code=${encodeURIComponent(stockCode)}` }] : []),
    ],
    evidence: [
      { label: 'Artifact', value: artifactId || '-' },
      { label: '关联任务', value: String(artifactQ.data?.count ?? 0) },
      { label: '最新任务', value: executionId || '-' },
      { label: '股票代码', value: stockCode || '-' },
      { label: '执行告警', value: String(warnings.length), tone: warnings.length > 0 ? 'warning' : 'neutral' },
    ],
    riskNotes: [
      ...(emptyDetailContract ? ['当前为详情空态契约，只能回执行中心补充真实 Artifact。'] : []),
      ...(warnings.length > 0 ? [`当前存在 ${warnings.length} 条执行告警。`] : []),
      ...(artifactQ.error ? [artifactQ.error] : []),
    ],
    platformMeta: {
      sourceTool: 'execution/artifact',
      sourceChain: ['execution', 'artifact-detail'],
      degraded: emptyDetailContract || Boolean(artifactQ.error),
      fallbackReason: [artifactQ.error].filter((item): item is string => Boolean(item)),
    },
    workbenchTask: defaultWorkbenchTask('execution', `复查 Artifact ${artifactId}`, executionHref, 'artifact-review', {
      artifactId,
      accountId: accountId || null,
      executionId: executionId || null,
      warningCount: warnings.length,
    }),
  });
  usePageContext({
    pageKey: 'execution',
    title: 'Artifact 详情',
    summary: artifactSummary,
    stockCode: stockCode || undefined,
    objectType: 'execution-artifact',
    objectId: artifactId || 'artifact',
    resultType: 'execution-artifact-detail',
    tags: [
      emptyDetailContract ? '空态契约' : null,
      accountId ? `账户 ${accountId}` : '未指定账户',
      `${artifactQ.data?.count ?? 0} 条任务`,
      `${warnings.length} 条告警`,
    ].filter((item): item is string => Boolean(item)),
    suggestions: [
      executionId ? `回执行中心查看 ${executionId}` : '回执行中心继续查询任务',
      '打开绩效中心复盘执行结果',
      warnings.length > 0 ? '打开风险中心复核告警' : '打开个股详情继续查看标的',
    ],
    recommendedActions: artifactResult.recommendedActions ?? [],
    recommendedLinks: artifactResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(artifactResult.evidence),
    riskNotes: artifactResult.riskNotes ?? [],
    freshness: artifactResult.freshness ?? null,
    raw: {
      artifactId,
      emptyDetailContract,
      accountId: accountId || null,
      executionId: executionId || null,
      stockCode: stockCode || null,
      taskCount: artifactQ.data?.count ?? 0,
      warningCount: warnings.length,
    },
  });

  if (emptyDetailContract) {
    return (
      <PageContainer>
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h1 className="m-0 text-lg font-semibold">Artifact 详情</h1>
            <p className="mb-0 mt-1 text-xs text-text-secondary">独立查看 artifact 关联的任务、执行摘要和后续复盘入口。</p>
          </div>
          <Badge variant="neutral">{artifactId}</Badge>
        </div>
        <SectionCard className="p-4">
          <EmptyState
            variant="full"
            text="当前环境还没有可用的 Artifact 详情数据"
            hint="当前路由走的是详情空态契约。可以先回执行中心提交一笔带 artifact_id 的执行，或保留这条空态作为回归用例。"
            action={
              <>
                <Link href={executionHref} className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">
                  回执行中心
                </Link>
                <Link href={buildExecutionArtifactDetailHref('', accountId)} className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">
                  重新打开空态
                </Link>
              </>
            }
          />
        </SectionCard>
      </PageContainer>
    );
  }

  return (
    <PageContainer className="space-y-4">
      <LightOverviewHero
        eyebrow="Execution Artifact"
        title="Artifact 详情"
        summary="先确认 artifact 关联任务、当前告警和下一步跳转，原始详情与长文本默认折叠。"
        badges={(
          <>
            <Badge variant={artifactQ.data?.count ? 'success' : 'neutral'}>{artifactId || '未指定 artifact'}</Badge>
            <Badge variant={warningBadgeVariant(warnings.length)}>
              {warnings.length > 0 ? `${warnings.length} 条告警` : '无显式告警'}
            </Badge>
          </>
        )}
        actions={(
          <>
            <button type="button" onClick={() => openExecution()} className="action-chip cursor-pointer text-sm text-text-primary">
              执行中心
            </button>
            <button type="button" onClick={() => openPerformance()} className="action-chip cursor-pointer text-sm text-text-primary">
              绩效中心
            </button>
            <button type="button" onClick={() => openRisk()} className="action-chip cursor-pointer text-sm text-text-primary">
              风险中心
            </button>
          </>
        )}
        status={(
          <div
            data-testid="page-primary-status"
            className="rounded-[20px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
          >
            <div className="font-medium text-text-primary">
              Artifact {artifactId || '-'} ｜ 关联任务 {artifactQ.data?.count ?? 0} ｜ 最新任务 {executionId || '-'}
            </div>
            <p className="mb-0 mt-1 text-xs leading-6 text-text-secondary">
              {stockCode ? `标的 ${stockCode}` : '当前还没有关联标的'} ｜ {warnings.length > 0 ? '建议先处理告警，再解释执行细节。' : '可以先看摘要，再决定是否下钻原始详情。'}
            </p>
          </div>
        )}
        metrics={[
          { key: 'artifact-task-count', label: '关联任务', value: String(artifactQ.data?.count ?? 0) },
          { key: 'artifact-latest-task', label: '最新任务', value: executionId || '-' },
          { key: 'artifact-stock', label: '股票代码', value: stockCode || '-' },
          { key: 'artifact-warning-count', label: '执行告警', value: String(warnings.length) },
        ]}
        compact
        detailsTitle="展开上下文与更多入口"
        detailsContent={(
          <div className="space-y-3 text-sm text-text-secondary">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="metric-tile rounded-[20px] p-3 text-xs">
                账户：<span className="font-medium text-text-primary">{accountId || detail?.accountId || '-'}</span>
              </div>
              <div className="metric-tile rounded-[20px] p-3 text-xs">
                Artifact：<span className="font-medium text-text-primary">{artifactId || '-'}</span>
              </div>
            </div>
            {stockCode ? (
              <button type="button" onClick={() => openStock()} className="action-chip cursor-pointer text-sm text-text-primary">
                个股详情
              </button>
            ) : null}
          </div>
        )}
      />

      {!compactLayout ? (
        <ProgressiveWorkbenchSection pageKey="execution" title="Artifact 结果工作台" result={artifactResult} summaryMode="strip" />
      ) : null}

      <CollapsibleSectionCard
        title="Artifact 摘要"
        summary={artifactQ.data ? `artifact ${artifactQ.data.artifactId} 当前关联 ${artifactQ.data.count} 条任务。` : '等待 artifact 查询结果。'}
        defaultOpen={!compactLayout}
      >
        {latestTask ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border border-border bg-surface-alt/30 p-3 text-xs text-text-secondary">
              <div className="font-medium text-text-primary">最新任务</div>
              <div className="mt-2">任务 ID：{latestTask.taskId || '-'}</div>
              <div>算法：{latestTask.algorithm || '-'}</div>
              <div>状态：{latestTask.status || '-'}</div>
            </div>
            <div className="rounded-xl border border-border bg-surface-alt/30 p-3 text-xs text-text-secondary">
              <div className="font-medium text-text-primary">执行规模</div>
              <div className="mt-2">数量：{latestTask.totalShares ?? '-'}</div>
              <div>时长：{latestTask.durationMinutes ?? '-'} 分钟</div>
              <div>分片：{detail?.overview?.slices ?? '-'}</div>
            </div>
            <div className="rounded-xl border border-border bg-surface-alt/30 p-3 text-xs text-text-secondary">
              <div className="font-medium text-text-primary">成本与风险</div>
              <div className="mt-2">告警：{latestTask.warningCount ?? 0}</div>
              <div>高严重级：{latestTask.hasHighSeverity ? '是' : '否'}</div>
              <div>预估成本：{detail?.cost?.estimatedTotal != null ? fmtNum(detail.cost.estimatedTotal) : '-'}</div>
            </div>
            <div className="rounded-xl border border-border bg-surface-alt/30 p-3 text-xs text-text-secondary">
              <div className="font-medium text-text-primary">账户上下文</div>
              <div className="mt-2">账户：{accountId || detail?.accountId || '-'}</div>
              <div>标的：{stockCode || '-'}</div>
              <div>Artifact：{artifactId}</div>
            </div>
          </div>
        ) : (
          <div className="text-sm text-text-secondary">当前 artifact 未匹配到关联任务。</div>
        )}
      </CollapsibleSectionCard>

      <CollapsibleSectionCard
        title="执行告警"
        summary="默认收起最新任务对应的软闸门与预交易告警，只有需要排障时再展开。"
        badge={<Badge variant={warningBadgeVariant(warnings.length)}>{warnings.length > 0 ? `${warnings.length} 条告警` : '无显式告警'}</Badge>}
      >
        {warnings.length > 0 ? (
          <div className="space-y-3">
            {warnings.map((warning) => (
              <div key={warning.id} className="rounded-xl border border-border bg-surface-alt/30 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium text-text-primary">{warning.title}</div>
                  <Badge variant={warning.severity === 'high' ? 'warning' : warning.severity === 'medium' ? 'neutral' : 'success'}>
                    {warning.severity || 'unknown'}
                  </Badge>
                </div>
                {warning.message ? <div className="mt-2 text-xs text-text-secondary">{warning.message}</div> : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-text-secondary">当前 artifact 暂无可展示告警。</div>
        )}
      </CollapsibleSectionCard>

      {detail ? (
        <CollapsibleSectionCard
          title="原始详情"
          summary="保留任务详情原始数据，便于继续排查链路问题。"
        >
          <pre className="mb-0 max-h-[480px] overflow-auto rounded-xl border border-border bg-surface-alt/30 p-3 text-[11px] leading-5 text-text-secondary">
            {JSON.stringify(detail, null, 2)}
          </pre>
        </CollapsibleSectionCard>
      ) : null}
    </PageContainer>
  );
}
