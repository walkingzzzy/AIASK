'use client';

import { FormEvent, useMemo, useState } from 'react';
import ResultWorkbench from '@/components/result-workbench';
import { Badge, PageContainer, SectionCard } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
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
  const [code, setCode] = useState('600519');
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
  const stages = (run?.steps ?? []) as AnalysisStage[];
  const summary = run?.summary ?? null;
  const activeTaskOption = TASK_OPTIONS.find((item) => item.value === task);

  const stageStats = useMemo(() => {
    const total = stages.length;
    const success = stages.filter((item) => item.success).length;
    return { total, success };
  }, [stages]);
  async function startAnalysis(nextTask = task, runId?: string) {
    const normalizedCode = code.trim();
    if (!normalizedCode) return;
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
  const deepStockActions = useMemo(
    () => [
      {
        id: 'deep-stock.start-analysis',
        label: '启动分析',
        description: '按当前代码与任务模式启动或刷新一轮深度分析',
        keywords: ['深度分析', '启动', code.trim()],
        scope: 'page' as const,
        pageKey: 'analysis-deep-stock',
        run: async () => {
          await startAnalysis(task);
          return { message: `已发起 ${code.trim() || '当前标的'} 的 ${task}` };
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
    ],
    [activeRunId, code, task],
  );
  usePageActions(deepStockActions);
  const deepStockSummary = run
    ? `${code.trim() || summary?.code || '当前标的'} 当前状态 ${run.status ?? 'unknown'}，已完成 ${stageStats.success}/${stageStats.total} 个阶段，缺口 ${gaps.length} 个，报告 ${summary?.report_ready ? '已就绪' : '待生成'}。`
    : `${code.trim() || '当前标的'} 还没有创建深度分析 run，建议先启动一次分析，确认 evidence、review、synthesis 和报告工件是否完整。`;
  const deepStockResult = buildLocalResultContract({
    summary: deepStockSummary,
    availableViews: report?.standalone_html || stages.length > 1 ? ['compare', 'visual'] : [],
    pageActions: deepStockActions,
    preferredActionIds: ['deep-stock.start-analysis', 'deep-stock.rebuild-report'],
    recommendedLinks: [
      { id: 'deep-stock-link-stock', label: '去个股详情', href: `/stock?code=${encodeURIComponent(code.trim() || '600519')}` },
      { id: 'deep-stock-link-research', label: '去研究页', href: `/research?code=${encodeURIComponent(code.trim() || '600519')}` },
      { id: 'deep-stock-link-assistant', label: '继续追问 Copilot', href: `/assistant?from=analysis-deep-stock&code=${encodeURIComponent(code.trim() || '600519')}` },
    ],
    evidence: [
      { label: '当前代码', value: code.trim() || summary?.code || '-' },
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
    workbenchTask: defaultWorkbenchTask('analysis-deep-stock', `复查深度分析 ${code.trim() || '600519'}`, '/analysis/deep-stock', 'deep-stock-review', {
      code: code.trim() || '600519',
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
    objectId: code.trim() || summary?.code || 'deep-stock',
    resultType: 'deep-stock-analysis',
    tags: [
      code.trim() || summary?.code || '未指定标的',
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
      code: code.trim() || summary?.code || null,
      task,
      runId: activeRunId,
      status: run?.status ?? null,
      gapCount: gaps.length,
      reportReady: summary?.report_ready ?? false,
    },
  });

  return (
    <PageContainer className="px-4 py-6 sm:px-6 lg:px-8" narrow>
      <section className="rounded-[32px] border border-border bg-[linear-gradient(135deg,rgba(254,247,237,0.92),rgba(239,246,255,0.92))] p-6 shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="text-xs uppercase tracking-[0.28em] text-text-secondary">Stock Deep Analysis</div>
            <h1 className="mt-2 text-3xl font-semibold text-text-primary sm:text-4xl">个股深度分析工作台</h1>
            <p className="mt-3 text-sm leading-6 text-text-secondary">
              统一走 `workflow / skill / resource / BFF / Web` 同一条运行链。当前阶段会展示 target 解析、完整性门禁、AI review、synthesis 与报告工件。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={summary?.report_ready ? 'success' : 'warning'}>
              {summary?.report_ready ? '报告已就绪' : '等待报告'}
            </Badge>
            <Badge variant={badgeVariant(run?.status ?? '')}>{run?.status ?? 'idle'}</Badge>
            {activeRunId ? <Badge variant="info">Run {activeRunId}</Badge> : null}
          </div>
        </div>

        <form className="mt-6 grid gap-4 lg:grid-cols-[1.5fr_1fr_auto_auto]" onSubmit={handleSubmit}>
          <label className="flex flex-col gap-2">
            <span className="text-sm font-medium text-text-secondary">股票代码或名称</span>
            <input
              className="h-12 rounded-2xl border border-border bg-white/80 px-4 text-sm outline-none transition focus:border-primary"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              placeholder="例如 600519 / 贵州茅台"
            />
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
          <button
            type="button"
            className="h-12 rounded-2xl border border-border bg-white/80 px-5 text-sm font-medium text-text-primary transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
            onClick={rebuildReport}
            disabled={!activeRunId || createRun.isPending}
          >
            重建报告
          </button>
        </form>

        <div className="mt-3 text-sm text-text-secondary">
          当前任务说明: {activeTaskOption?.hint ?? '无'}
        </div>
        {createRun.error ? <div className="mt-4 text-sm text-danger">{createRun.error}</div> : null}
      </section>

      <ResultWorkbench pageKey="analysis-deep-stock" title="深度分析结果工作台" result={deepStockResult} />

      <div className="mt-6 grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <SectionCard className="mt-0">
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

        <SectionCard className="mt-0">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-text-primary">运行摘要</h2>
              <p className="mt-1 text-sm text-text-secondary">对外展示用 summary card / digest / run manifest</p>
            </div>
            {summary?.gap_count ? <Badge variant="warning">{summary.gap_count} 个缺口</Badge> : null}
          </div>
          <div className="mt-5 rounded-[24px] border border-border bg-[linear-gradient(135deg,rgba(255,255,255,0.92),rgba(246,250,255,0.92))] p-5">
            <div className="text-xs uppercase tracking-[0.22em] text-text-secondary">Summary Card</div>
            <div className="mt-3 text-2xl font-semibold text-text-primary">
              {report?.summary_card?.title ?? run?.name ?? summary?.code ?? '等待运行'}
            </div>
            <p className="mt-3 text-sm leading-6 text-text-secondary">
              {report?.summary_card?.subtitle ?? summary?.digest ?? '运行完成后，这里会显示 one-paragraph digest。'}
            </p>
            <div className="mt-4 grid gap-2">
              {(report?.summary_card?.bullets ?? []).map((bullet) => (
                <div key={bullet} className="rounded-2xl border border-border bg-white/80 px-3 py-2 text-sm text-text-primary">
                  {bullet}
                </div>
              ))}
            </div>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {(report?.perspective_cards ?? []).map((card) => (
              <div key={card.key} className="rounded-2xl border border-border bg-white/70 px-4 py-4">
                <div className="text-xs uppercase tracking-[0.18em] text-text-secondary">{card.title}</div>
                <div className="mt-2 text-xl font-semibold text-text-primary">{String(card.value ?? '-')}</div>
                <div className="mt-1 text-sm text-text-secondary">{card.note ?? ''}</div>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      <div className="mt-6 grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <SectionCard className="mt-0">
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

        <SectionCard className="mt-0">
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
      </div>
    </PageContainer>
  );
}
