'use client';

import { FormEvent, useMemo, useState } from 'react';
import CollapsibleSectionCard from '@/components/collapsible-section-card';
import LightOverviewHero from '@/components/light-overview-hero';
import { Badge, PageContainer, SectionCard } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { useMobile } from '@/hooks/use-mobile';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStockCode } from '@/hooks/use-stock-code';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { ensureRecord } from '@/lib/query-parse';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import type {
  AnalysisGapItem,
  AnalysisReportBundle,
  AnalysisStage,
  AnalysisSynthesis,
  DeepAnalysisRunResponse,
  DeepAnalysisTask,
} from '@aiask/shared-types';

const TASK_OPTIONS: Array<{ value: DeepAnalysisTask; label: string; hint: string }> = [
  { value: 'deep_analysis', label: '深度分析', hint: '完整 evidence / review / synthesis / report 链路' },
  { value: 'quick_scan', label: '快速扫描', hint: '保留核心结论，缩短报告深度' },
  { value: 'trade_plan', label: '交易计划', hint: '在深度分析基础上附加交易计划' },
  { value: 'recover_gaps', label: '恢复缺口', hint: '优先输出 gap recovery 视图' },
];

function parseRun(raw: unknown): DeepAnalysisRunResponse {
  return ensureRecord(raw, '个股深度分析运行') as DeepAnalysisRunResponse;
}

function parseReport(raw: unknown): AnalysisReportBundle {
  return ensureRecord(raw, '个股深度分析报告') as AnalysisReportBundle;
}

function badgeVariant(status: string): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
  const normalized = String(status ?? '').toLowerCase();
  if (normalized.includes('completed') || normalized.includes('passed') || normalized.includes('pass')) return 'success';
  if (normalized.includes('blocked') || normalized.includes('fail')) return 'danger';
  if (normalized.includes('recover') || normalized.includes('warning')) return 'warning';
  if (normalized.includes('progress')) return 'info';
  return 'neutral';
}

function gapItems(run: DeepAnalysisRunResponse | null): AnalysisGapItem[] {
  const report = run?.analysis_gap_report;
  return [
    ...(report?.critical_missing ?? []),
    ...(report?.non_critical_missing ?? []),
  ];
}

export default function DeepStockAnalysisPage() {
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
  const { code, setCode, codeError, validate, trimmedCode, resolvedCode } = useStockCode();
  const [task, setTask] = useState<DeepAnalysisTask>('deep_analysis');
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  const createRun = useApiMutation<DeepAnalysisRunResponse>({
    parse: parseRun,
    successToast: '深度分析运行已创建',
    onSuccess: (data) => {
      const nextRunId = data.run_id ?? data.summary?.run_id ?? null;
      if (nextRunId) setActiveRunId(nextRunId);
    },
  });

  const runQuery = useApiQuery<DeepAnalysisRunResponse>(
    activeRunId ? `/v1/analysis/deep-stock/runs/${encodeURIComponent(activeRunId)}` : null,
    {
      parse: parseRun,
      placeholderData: 'keepPrevious',
    },
  );

  const reportQuery = useApiQuery<AnalysisReportBundle>(
    activeRunId ? `/v1/analysis/deep-stock/runs/${encodeURIComponent(activeRunId)}/report` : null,
    {
      parse: parseReport,
      placeholderData: 'keepPrevious',
      nonFatal: true,
    },
  );

  const run = runQuery.data ?? createRun.data;
  const report = reportQuery.data?.found === false ? null : reportQuery.data;
  const synthesis = (run?.analysis_synthesis ?? null) as AnalysisSynthesis | null;
  const gaps = gapItems(run);
  const stages = useMemo(() => (run?.steps ?? []) as AnalysisStage[], [run?.steps]);
  const summary = run?.summary ?? null;
  const activeTaskOption = TASK_OPTIONS.find((item) => item.value === task);
  const focusCode = trimmedCode || summary?.code || resolvedCode || '';
  const focusLabel = focusCode || '未指定标的';

  const stageStats = useMemo(() => {
    const total = stages.length;
    const success = stages.filter((item) => item.success).length;
    return { total, success };
  }, [stages]);
  async function startAnalysis(nextTask = task, runId?: string) {
    const normalizedCode = (code.trim() || resolvedCode || '').trim();
    if (!validate(normalizedCode)) return;
    await createRun.triggerAsync(
      '/v1/analysis/deep-stock/runs',
      { method: 'POST' },
      { code: normalizedCode, task: nextTask, ...(runId ? { runId } : {}) },
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await startAnalysis(task);
  }

  async function rebuildReport() {
    if (!activeRunId) return;
    await startAnalysis('rebuild_report', activeRunId);
  }
  const deepStockActions = [
    {
      id: 'deep-stock.start-analysis',
      label: '启动分析',
      description: '按当前代码与任务模式启动或刷新一轮深度分析',
      keywords: ['深度分析', '启动', focusCode],
      scope: 'page' as const,
      pageKey: 'analysis-deep-stock',
      run: async () => {
        await startAnalysis(task);
        return { message: `已发起 ${focusLabel} 的 ${task}` };
      },
    },
    {
      id: 'deep-stock.rebuild-report',
      label: '重建报告',
      description: '针对当前 run 重新生成 standalone 报告工件',
      keywords: ['报告', '重建'],
      scope: 'page' as const,
      pageKey: 'analysis-deep-stock',
      run: async () => {
        if (!activeRunId) throw new Error('当前还没有可重建的 run');
        await rebuildReport();
        return { message: '已触发报告重建' };
      },
    },
  ];
  usePageActions(deepStockActions);
  const deepStockSummary = run
    ? `${focusLabel} 当前状态 ${run.status ?? 'unknown'}，已完成 ${stageStats.success}/${stageStats.total} 个阶段，缺口 ${gaps.length} 个，报告 ${summary?.report_ready ? '已就绪' : '待生成'}。`
    : `${focusLabel} 还没有创建深度分析 run，建议先启动一次分析，确认 evidence、review、synthesis 和报告工件是否完整。`;
  const deepStockResult = buildLocalResultContract({
    summary: deepStockSummary,
    availableViews: report?.standalone_html || stages.length > 1 ? ['compare', 'visual'] : [],
    pageActions: deepStockActions,
    preferredActionIds: ['deep-stock.start-analysis', 'deep-stock.rebuild-report'],
    recommendedLinks: [
      { id: 'deep-stock-link-stock', label: focusCode ? '去个股详情' : '选择标的', href: focusCode ? `/stock?code=${encodeURIComponent(focusCode)}` : '/watchlist?from=analysis-deep-stock' },
      { id: 'deep-stock-link-research', label: '去研究页', href: focusCode ? `/research?code=${encodeURIComponent(focusCode)}` : '/research?from=analysis-deep-stock' },
      { id: 'deep-stock-link-assistant', label: '继续追问 Copilot', href: focusCode ? `/assistant?from=analysis-deep-stock&code=${encodeURIComponent(focusCode)}` : '/assistant?from=analysis-deep-stock' },
    ],
    evidence: [
      { label: '当前代码', value: focusCode || '-' },
      { label: '任务模式', value: task },
      { label: '运行状态', value: String(run?.status ?? 'idle') },
      { label: '阶段进度', value: `${stageStats.success}/${stageStats.total}` },
      { label: '缺口数量', value: String(gaps.length), tone: gaps.length > 0 ? 'warning' : 'neutral' },
      { label: '报告状态', value: summary?.report_ready ? '已就绪' : '待生成' },
    ],
    riskNotes: [
      ...(createRun.error ? [createRun.error] : []),
      ...(reportQuery.error ? [reportQuery.error] : []),
      ...(gaps.length > 0 ? [`当前存在 ${gaps.length} 个结构化缺口。`] : []),
      ...(run?.analysis_agent_review?.conflicts?.length ? [`AI Review 有 ${run.analysis_agent_review.conflicts.length} 条冲突待消解。`] : []),
    ],
    freshness: summary?.updated_at ? { updatedAt: summary.updated_at, label: '分析运行快照' } : null,
    platformMeta: {
      sourceTool: 'analysis/deep-stock',
      sourceChain: ['workflow', 'skill', 'resource', 'bff', 'web'],
      degraded: Boolean(createRun.error || reportQuery.error),
      fallbackReason: [createRun.error, reportQuery.error].filter((item): item is string => Boolean(item)),
    },
    workbenchTask: defaultWorkbenchTask('analysis-deep-stock', `复查深度分析 ${focusLabel}`, focusCode ? `/analysis/deep-stock?code=${encodeURIComponent(focusCode)}` : '/analysis/deep-stock', 'deep-stock-review', {
      code: focusCode || null,
      task,
      runId: activeRunId,
      gapCount: gaps.length,
    }),
  });
  usePageContext({
    pageKey: 'analysis-deep-stock',
    title: '个股深度分析工作台',
    summary: deepStockSummary,
    objectType: 'stock',
    objectId: focusCode || 'deep-stock',
    resultType: 'deep-stock-analysis',
    tags: [
      focusLabel,
      task,
      run?.status ?? 'idle',
      summary?.report_ready ? '报告已就绪' : '等待报告',
    ],
    suggestions: [
      '总结当前深度分析还缺哪些关键证据',
      '如果 integrity gate 阻断了结果，解释下一步恢复动作',
      '给出应该先看阶段进度、缺口还是最终报告的判断',
    ],
    recommendedActions: deepStockResult.recommendedActions ?? [],
    recommendedLinks: deepStockResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(deepStockResult.evidence),
    riskNotes: deepStockResult.riskNotes ?? [],
    freshness: deepStockResult.freshness ?? null,
    raw: {
      code: focusCode || null,
      task,
      runId: activeRunId,
      status: run?.status ?? null,
      gapCount: gaps.length,
      reportReady: summary?.report_ready ?? false,
    },
  });

  return (
    <PageContainer className="px-4 py-6 sm:px-6 lg:px-8" narrow>
      <LightOverviewHero
        eyebrow="个股深度分析"
        title="个股深度分析工作台"
        summary={
          compactLayout
            ? '先确认标的和任务模式，再决定是否启动或重建分析。'
            : '统一走 workflow / skill / resource / BFF / Web 同一条运行链。首屏先收口到状态、主动作和当前运行摘要。'
        }
        badges={compactLayout ? (
          <>
            <Badge variant={summary?.report_ready ? 'success' : 'warning'}>
              {summary?.report_ready ? '报告已就绪' : '等待报告'}
            </Badge>
            <Badge variant={badgeVariant(run?.status ?? '')}>{run?.status ?? 'idle'}</Badge>
          </>
        ) : (
          <>
            <Badge variant={summary?.report_ready ? 'success' : 'warning'}>
              {summary?.report_ready ? '报告已就绪' : '等待报告'}
            </Badge>
            <Badge variant={badgeVariant(run?.status ?? '')}>{run?.status ?? 'idle'}</Badge>
            {activeRunId ? <Badge variant="info">Run {activeRunId}</Badge> : null}
          </>
        )}
        actions={(
          compactLayout ? (
            <button
              type="button"
              onClick={() => void startAnalysis(task)}
              className="inline-flex h-11 items-center justify-center rounded-2xl bg-text-primary px-5 text-sm font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={createRun.isPending}
            >
              {createRun.isPending ? '运行中...' : '启动分析'}
            </button>
          ) : (
          <>
            <button
              type="button"
              onClick={() => void startAnalysis(task)}
              className="inline-flex h-11 items-center justify-center rounded-2xl bg-text-primary px-5 text-sm font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={createRun.isPending}
            >
              {createRun.isPending ? '运行中...' : '启动分析'}
            </button>
            <button
              type="button"
              className="inline-flex h-11 items-center justify-center rounded-2xl border border-border bg-white/80 px-5 text-sm font-medium text-text-primary transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
              onClick={rebuildReport}
              disabled={!activeRunId || createRun.isPending}
            >
              重建报告
            </button>
          </>
          )
        )}
        status={compactLayout ? null : (
          <div
            data-testid="page-primary-status"
            className="rounded-[20px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
          >
            <div className="font-medium text-text-primary">
              当前代码 {focusCode || '-'} ｜ 任务 {task} ｜ 阶段 {stageStats.success}/{stageStats.total}
            </div>
            <p className="mt-1 mb-0 text-xs leading-6 text-text-secondary">
              当前任务说明：{activeTaskOption?.hint ?? '无'} ｜ 缺口 {gaps.length} 个
            </p>
          </div>
        )}
        metrics={compactLayout ? [] : [
          { key: 'deep-stock-code', label: '当前代码', value: focusCode || '-' },
          { key: 'deep-stock-task', label: '任务模式', value: task },
          { key: 'deep-stock-stages', label: '阶段进度', value: `${stageStats.success}/${stageStats.total}` },
          { key: 'deep-stock-gaps', label: '结构化缺口', value: String(gaps.length) },
        ]}
        compact
        detailsTitle="展开运行说明"
        detailsContent={!compactLayout && createRun.error ? <div className="text-sm text-danger">{createRun.error}</div> : null}
      />

      <SectionCard className="p-4">
        <form className="grid gap-4 lg:grid-cols-[1.5fr_1fr_auto_auto]" onSubmit={handleSubmit}>
          <label className="flex flex-col gap-2">
            <span className="text-sm font-medium text-text-secondary">股票代码或名称</span>
            <input
              className="h-12 rounded-2xl border border-border bg-white/80 px-4 text-sm outline-none transition focus:border-primary"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              placeholder="例如 600519 / 贵州茅台"
            />
            {codeError ? <span className="text-xs text-danger">{codeError}</span> : null}
          </label>
          <label className="flex flex-col gap-2">
            <span className="text-sm font-medium text-text-secondary">任务模式</span>
            <select
              className="h-12 rounded-2xl border border-border bg-white/80 px-4 text-sm outline-none transition focus:border-primary"
              value={task}
              onChange={(event) => setTask(event.target.value as DeepAnalysisTask)}
            >
              {TASK_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            className="h-12 rounded-2xl bg-text-primary px-5 text-sm font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={createRun.isPending}
          >
            {createRun.isPending ? '运行中...' : '启动分析'}
          </button>
          {!compactLayout ? (
            <button
              type="button"
              className="h-12 rounded-2xl border border-border bg-white/80 px-5 text-sm font-medium text-text-primary transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
              onClick={rebuildReport}
              disabled={!activeRunId || createRun.isPending}
            >
              重建报告
            </button>
          ) : null}
        </form>
      </SectionCard>

      <div className="mt-6 space-y-4">
        <CollapsibleSectionCard
          title="运行摘要"
          summary={
            compactLayout
              ? '移动端先收起长摘要，避免结果区压住输入动作。'
              : '默认只展开对外摘要和关键视角卡。阶段进度、缺口恢复和最终报告改成按需下钻。'
          }
          defaultOpen={!compactLayout}
          badge={summary?.gap_count ? <Badge variant="warning">{summary.gap_count} 个缺口</Badge> : <Badge variant="info">主结果</Badge>}
        >
          <div className="rounded-[24px] border border-border bg-[linear-gradient(135deg,rgba(255,255,255,0.92),rgba(246,250,255,0.92))] p-5">
            <div className="text-xs uppercase tracking-[0.22em] text-text-secondary">Summary Card</div>
            <div className="mt-3 text-2xl font-semibold text-text-primary">
              {report?.summary_card?.title ?? run?.name ?? summary?.code ?? '等待运行'}
            </div>
            <p className="mt-3 text-sm leading-6 text-text-secondary">
              {report?.summary_card?.subtitle ?? summary?.digest ?? '运行完成后，这里会显示 one-paragraph digest。'}
            </p>
            {!compactLayout ? (
              <div className="mt-4 grid gap-2">
                {(report?.summary_card?.bullets ?? []).map((bullet) => (
                  <div key={bullet} className="rounded-2xl border border-border bg-white/80 px-3 py-2 text-sm text-text-primary">
                    {bullet}
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          {!compactLayout ? (
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {(report?.perspective_cards ?? []).map((card) => (
                <div key={card.key} className="rounded-2xl border border-border bg-white/70 px-4 py-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-text-secondary">{card.title}</div>
                  <div className="mt-2 text-xl font-semibold text-text-primary">{String(card.value ?? '-')}</div>
                  <div className="mt-1 text-sm text-text-secondary">{card.note ?? ''}</div>
                </div>
              ))}
            </div>
          ) : null}
        </CollapsibleSectionCard>

        <CollapsibleSectionCard
          title="阶段进度"
          summary={`当前已完成 ${stageStats.success}/${stageStats.total} 个阶段。阶段详情可展开查看，便于先确认整体进度。`}
          badge={summary?.current_stage ? <Badge variant={badgeVariant(summary.current_stage)}>{summary.current_stage}</Badge> : null}
        >
          <SectionCard className="mt-0 border-0 bg-transparent p-0 shadow-none">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-text-primary">阶段进度</h2>
              <p className="mt-1 text-sm text-text-secondary">
                已完成 {stageStats.success}/{stageStats.total} 个阶段
              </p>
            </div>
            {summary?.current_stage ? (
              <Badge variant={badgeVariant(summary.current_stage)}>{summary.current_stage}</Badge>
            ) : null}
          </div>

          <div className="mt-5 grid gap-3">
            {stages.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border px-4 py-6 text-sm text-text-secondary">
                尚未创建 deep-analysis run。
              </div>
            ) : (
              stages.map((stage) => (
                <div
                  key={`${stage.stage}-${stage.updated_at ?? ''}`}
                  className="rounded-2xl border border-border bg-white/70 px-4 py-4"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-text-primary">{stage.stage}</div>
                      <div className="mt-1 text-xs text-text-secondary">
                        {stage.detail ? JSON.stringify(stage.detail) : '无阶段细节'}
                      </div>
                    </div>
                    <Badge variant={badgeVariant(stage.status)}>{stage.status}</Badge>
                  </div>
                </div>
              ))
            )}
          </div>
          </SectionCard>
        </CollapsibleSectionCard>

        <CollapsibleSectionCard
          title="缺口与恢复"
          summary="这里集中查看完整性检查、恢复动作和 AI 复核冲突；只有需要排障时再展开处理。"
          badge={run?.analysis_gap_report?.status ? <Badge variant={badgeVariant(run.analysis_gap_report.status)}>{run.analysis_gap_report.status}</Badge> : null}
        >
          <SectionCard className="mt-0 border-0 bg-transparent p-0 shadow-none">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-text-primary">缺口与恢复</h2>
              <p className="mt-1 text-sm text-text-secondary">供 integrity gate 与 `recover_gaps` 共用</p>
            </div>
            {run?.analysis_gap_report?.status ? (
              <Badge variant={badgeVariant(run.analysis_gap_report.status)}>
                {run.analysis_gap_report.status}
              </Badge>
            ) : null}
          </div>

          <div className="mt-5 grid gap-3">
            {gaps.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border px-4 py-6 text-sm text-text-secondary">
                当前没有检测到结构化缺口。
              </div>
            ) : (
              gaps.map((gap) => (
                <div key={`${gap.field}-${gap.message}`} className="rounded-2xl border border-border bg-white/70 px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-medium text-text-primary">{gap.field}</div>
                    <Badge variant={badgeVariant(gap.severity)}>{gap.severity}</Badge>
                  </div>
                  <p className="mt-2 text-sm text-text-secondary">{gap.message}</p>
                  <p className="mt-2 text-xs text-text-secondary">恢复动作: {gap.recovery_action}</p>
                </div>
              ))
            )}
          </div>

          {(run?.analysis_gap_report?.recovery_actions ?? []).length > 0 ? (
            <div className="mt-4 rounded-2xl border border-border bg-white/70 px-4 py-4">
              <div className="text-sm font-medium text-text-primary">建议恢复动作</div>
              <ul className="mt-2 list-disc pl-5 text-sm text-text-secondary">
                {(run?.analysis_gap_report?.recovery_actions ?? []).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {(run?.analysis_agent_review?.conflicts ?? []).length ? (
            <div className="mt-4 rounded-2xl border border-border bg-white/70 px-4 py-4">
              <div className="text-sm font-medium text-text-primary">AI Review 冲突</div>
              <ul className="mt-2 list-disc pl-5 text-sm text-text-secondary">
                {(run?.analysis_agent_review?.conflicts ?? []).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
          </SectionCard>
        </CollapsibleSectionCard>

        <CollapsibleSectionCard
          title="最终报告"
          summary="报告 HTML、章节 narrative 和引用默认折叠。先确认运行摘要成立，再决定是否进入长报告。"
          badge={reportQuery.isFetching ? <Badge variant="info">刷新中</Badge> : <Badge variant="neutral">长报告</Badge>}
        >
          <SectionCard className="mt-0 border-0 bg-transparent p-0 shadow-none">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-text-primary">最终报告</h2>
              <p className="mt-1 text-sm text-text-secondary">standalone HTML + sections + manifest</p>
            </div>
            {reportQuery.isFetching ? <Badge variant="info">刷新中</Badge> : null}
          </div>

          <div className="mt-5 grid gap-4">
            {(synthesis?.sections ?? []).map((section) => (
              <div key={section.key} className="rounded-2xl border border-border bg-white/70 px-4 py-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-medium text-text-primary">{section.title}</div>
                  <Badge variant="neutral">{section.evidence_ids.length} 条引用</Badge>
                </div>
                <p className="mt-2 text-sm leading-6 text-text-secondary">{section.narrative}</p>
                <div className="mt-3 text-xs text-text-secondary">
                  Evidence: {section.evidence_ids.join(', ') || '-'}
                </div>
              </div>
            ))}
          </div>

          {report?.standalone_html ? (
            <div className="mt-5 overflow-hidden rounded-[28px] border border-border bg-white">
              <iframe
                title="deep-analysis-report"
                srcDoc={report.standalone_html}
                className="h-[720px] w-full border-0"
              />
            </div>
          ) : (
            <div className="mt-5 rounded-2xl border border-dashed border-border px-4 py-8 text-sm text-text-secondary">
              报告尚未生成，或者当前 run 被完整性门禁阻断。
            </div>
          )}
          </SectionCard>
        </CollapsibleSectionCard>
      </div>
    </PageContainer>
  );
}
