'use client';

import { Badge, SectionCard } from '@/components/ui';
import type {
  CapabilityBadge,
  DailySnapshotResponse,
  FactoryRunDetailResponse,
  FactoryRunItem,
  FactoryRunSummary,
  FactoryStatusResponse,
  RunStatusFilter,
  TrendMetricKey,
} from '../types';

/* ---------- helper functions ---------- */

function formatRatioPercent(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return '-';
  return `${Math.round(Number(value) * 100)}%`;
}

function formatFactoryMetricValue(value?: number | null, digits = 0) {
  if (value == null || Number.isNaN(Number(value))) return '-';
  return Number(value).toFixed(digits);
}

function hasRunAuditMetrics(summary?: FactoryRunSummary | null) {
  if (!summary) return false;
  return [
    summary.deflated_sharpe_ratio_avg,
    summary.high_pbo_count,
    summary.formal_multiple_testing_count,
    summary.weak_white_reality_check_count,
    summary.weak_hansen_spa_count,
  ].some((value) => value != null);
}

function normalizeFactoryRunError(error?: string | null) {
  const text = String(error ?? '').trim();
  if (!text) return '未知错误';
  return text
    .split('\n')[0]
    .replace(/\s+/g, ' ')
    .replace(/[0-9]{4}-[0-9]{2}-[0-9]{2}[ t][0-9:.+-zZ]*/g, '<time>')
    .replace(/[0-9a-f]{8,}/gi, '<id>')
    .replace(/\b\d+\b/g, '<num>')
    .slice(0, 80);
}

function getFactoryRunErrorFingerprint(error?: string | null) {
  const example = normalizeFactoryRunError(error);
  const normalized = example.toLowerCase();

  const rules: Array<{ label: string; patterns: RegExp[] }> = [
    { label: '超时错误', patterns: [/timeout/i, /timed out/i, /deadline/i, /超时/] },
    { label: '网络连接错误', patterns: [/connection/i, /network/i, /socket/i, /dns/i, /refused/i, /unreachable/i, /http/i] },
    { label: '数据库错误', patterns: [/postgres/i, /database/i, /sql/i, /asyncpg/i, /timescaledb/i, /db error/i] },
    { label: '权限错误', patterns: [/permission/i, /forbidden/i, /unauthorized/i, /access denied/i, /鉴权/, /权限/] },
    { label: '配置缺失', patterns: [/missing/i, /env/i, /config/i, /credential/i, /token/i, /api key/i, /配置/] },
    { label: '输入校验错误', patterns: [/invalid/i, /validation/i, /valueerror/i, /typeerror/i, /keyerror/i, /assert/i, /参数/, /校验/] },
    { label: '依赖加载错误', patterns: [/module not found/i, /importerror/i, /cannot import/i, /no module named/i, /dependency/i] },
  ];

  const matched = rules.find((rule) => rule.patterns.some((pattern) => pattern.test(normalized)));
  return {
    label: matched?.label ?? '未分类错误',
    example,
    matched: Boolean(matched),
  };
}

function shortFactoryRunTime(value?: string | null) {
  if (!value) return '-';
  return String(value).replace('T', ' ').slice(0, 16);
}

function detectFailedStage(run?: FactoryRunItem | null) {
  if (!run || run.status !== 'failed') return '-';
  const order = ['collect', 'spawn', 'backtest', 'deduplicate', 'submit', 'elimination'];
  const stages = run.stages ?? {};
  for (const name of order) {
    const stage = stages[name];
    if (!stage) return name;
    if (stage.ok === false) return name;
  }
  return 'unknown';
}

/* ---------- small building blocks ---------- */

function FactoryMetric({ title, value }: { title: string; value: string | number }) {
  return (
    <div className="rounded border border-border px-3 py-2 bg-surface-alt">
      <div className="text-xs text-text-secondary">{title}</div>
      <div className="text-lg font-semibold mt-1">{value}</div>
    </div>
  );
}

function formatTaskLabel(value?: string | null) {
  if (!value) return '-';
  if (value === 'event_driven') return '事件驱动';
  if (value === 'snapshot') return '快照';
  return String(value).replaceAll('_', ' ');
}

function formatMixedFlag(value?: boolean | null) {
  return value ? '是' : '否';
}

function sortCountEntries(record?: Record<string, number> | null) {
  return Object.entries(record ?? {}).sort((a, b) => Number(b[1] ?? 0) - Number(a[1] ?? 0));
}

function formatCountSummary(record?: Record<string, number> | null, limit = 3) {
  const entries = sortCountEntries(record).slice(0, limit);
  if (entries.length === 0) return '-';
  return entries.map(([key, count]) => `${formatTaskLabel(key)} ${count}`).join(' · ');
}

function aggregateSummaryCounts(
  runs: FactoryRunItem[],
  selector: (summary: FactoryRunSummary) => Record<string, number> | undefined,
) {
  const merged = new Map<string, number>();
  runs.forEach((run) => {
    const counts = selector(run.summary ?? {});
    Object.entries(counts ?? {}).forEach(([key, count]) => {
      merged.set(key, (merged.get(key) ?? 0) + Number(count ?? 0));
    });
  });
  return Object.fromEntries(sortCountEntries(Object.fromEntries(merged.entries())));
}

function FactoryTaskStructurePanel({
  summary,
}: {
  summary: FactoryRunSummary;
}) {
  const taskSourceEntries = Object.entries(summary.task_source_counts ?? {});
  const scannerTaskTypeEntries = Object.entries(summary.scanner_task_types ?? {});
  const autonomyTaskBriefs = summary.autonomy_task_briefs ?? [];
  const hasTaskSummary = [
    summary.autonomy_task_count,
    summary.event_task_count,
    summary.snapshot_task_count,
  ].some((value) => value != null)
    || taskSourceEntries.length > 0
    || scannerTaskTypeEntries.length > 0
    || autonomyTaskBriefs.length > 0;

  if (!hasTaskSummary) return null;

  return (
    <div className="mt-3 rounded border border-border bg-surface-alt px-3 py-3 text-xs text-text-secondary space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className="font-medium text-text-primary">任务结构</span>
        <span>{summary.event_snapshot_mixed ? '事件 + 快照混合' : '单来源任务'}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div>研究任务：{summary.autonomy_task_count ?? autonomyTaskBriefs.length ?? '-'}</div>
        <div>事件任务：{summary.event_task_count ?? 0}</div>
        <div>快照任务：{summary.snapshot_task_count ?? 0}</div>
        <div>混合模式：{summary.event_snapshot_mixed ? '是' : '否'}</div>
      </div>
      {taskSourceEntries.length > 0 && (
        <div className="space-y-2">
          <div className="font-medium text-text-primary">来源分布</div>
          <div className="flex flex-wrap gap-2">
            {taskSourceEntries.map(([key, count]) => (
              <Badge key={key} variant="neutral">
                {formatTaskLabel(key)} {count}
              </Badge>
            ))}
          </div>
        </div>
      )}
      {scannerTaskTypeEntries.length > 0 && (
        <div className="space-y-2">
          <div className="font-medium text-text-primary">机会类型</div>
          <div className="flex flex-wrap gap-2">
            {scannerTaskTypeEntries.slice(0, 6).map(([key, count]) => (
              <Badge key={key} variant="info">
                {formatTaskLabel(key)} {count}
              </Badge>
            ))}
          </div>
        </div>
      )}
      {autonomyTaskBriefs.length > 0 && (
        <div className="space-y-2">
          <div className="font-medium text-text-primary">最近任务摘要</div>
          <div className="space-y-1">
            {autonomyTaskBriefs.slice(0, 4).map((item, idx) => (
              <div
                key={item.task_id ?? `${item.task_source ?? 'task'}-${idx}`}
                className="rounded border border-border bg-surface px-2 py-2"
              >
                <div className="text-text-primary">
                  {formatTaskLabel(item.opportunity_type)} · {formatTaskLabel(item.task_source)}
                </div>
                <div className="mt-1">
                  task_id: {item.task_id ?? '-'} · 预算 {item.generated_count ?? 0}/{item.generation_limit ?? '-'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FactoryRunStructureDiagnosticsPanel({ runs }: { runs: FactoryRunItem[] }) {
  const latest = runs[runs.length - 1];
  const earliest = runs[0];
  const mixedRunCount = runs.filter((run) => run.summary?.event_snapshot_mixed).length;
  const mixedRunRatio = runs.length > 0 ? Math.round((mixedRunCount / runs.length) * 100) : 0;
  const aggregatedSources = aggregateSummaryCounts(runs, (summary) => summary.task_source_counts);
  const aggregatedTypes = aggregateSummaryCounts(runs, (summary) => summary.scanner_task_types);
  const hasStructureData = mixedRunCount > 0
    || Object.keys(aggregatedSources).length > 0
    || Object.keys(aggregatedTypes).length > 0
    || Boolean(latest?.summary?.task_source_counts)
    || Boolean(earliest?.summary?.task_source_counts);

  if (!hasStructureData) return null;

  return (
    <div className="mt-3 rounded border border-border bg-surface-alt p-3 space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <FactoryMetric title="混合运行次数" value={mixedRunCount} />
        <FactoryMetric title="混合占比" value={`${mixedRunRatio}%`} />
        <FactoryMetric title="累计来源类别" value={Object.keys(aggregatedSources).length || 0} />
        <FactoryMetric title="累计机会类型" value={Object.keys(aggregatedTypes).length || 0} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-text-secondary">
        <div className="rounded border border-border bg-surface px-3 py-3">
          <div className="font-medium text-text-primary">最早一轮来源结构</div>
          <div className="mt-2">{formatCountSummary(earliest?.summary?.task_source_counts)}</div>
        </div>
        <div className="rounded border border-border bg-surface px-3 py-3">
          <div className="font-medium text-text-primary">最新一轮来源结构</div>
          <div className="mt-2">{formatCountSummary(latest?.summary?.task_source_counts)}</div>
        </div>
      </div>

      {Object.keys(aggregatedSources).length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-text-primary">窗口期累计来源分布</div>
          <div className="flex flex-wrap gap-2">
            {sortCountEntries(aggregatedSources).slice(0, 6).map(([key, count]) => (
              <Badge key={key} variant="neutral">
                {formatTaskLabel(key)} {count}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {Object.keys(aggregatedTypes).length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-text-primary">窗口期热点机会类型</div>
          <div className="flex flex-wrap gap-2">
            {sortCountEntries(aggregatedTypes).slice(0, 6).map(([key, count]) => (
              <Badge key={key} variant="info">
                {formatTaskLabel(key)} {count}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FactoryQualityAuditPanel({ summary }: { summary: FactoryRunSummary }) {
  const hasAuditMetrics = [
    summary.formal_multiple_testing_count,
    summary.deflated_sharpe_ratio_avg,
    summary.high_pbo_count,
    summary.weak_white_reality_check_count,
    summary.weak_hansen_spa_count,
    summary.attempt_adjusted_gate_failed,
  ].some((value) => value != null);

  if (!hasAuditMetrics) return null;

  return (
    <div className="mt-3 rounded border border-border bg-surface-alt p-3 space-y-3">
      <div className="text-xs font-medium text-text-primary">统计审计</div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <FactoryMetric title="正式多重检验" value={summary.formal_multiple_testing_count ?? 0} />
        <FactoryMetric title="平均 DSR" value={summary.deflated_sharpe_ratio_avg == null ? '-' : Number(summary.deflated_sharpe_ratio_avg).toFixed(2)} />
        <FactoryMetric title="高 PBO 数" value={summary.high_pbo_count ?? 0} />
        <FactoryMetric title="弱 White RC" value={summary.weak_white_reality_check_count ?? 0} />
        <FactoryMetric title="弱 Hansen SPA" value={summary.weak_hansen_spa_count ?? 0} />
        <FactoryMetric title="尝试惩罚失败" value={summary.attempt_adjusted_gate_failed ?? 0} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <FactoryMetric title="约束违例" value={summary.constraint_violation_count ?? 0} />
        <FactoryMetric title="交集均值" value={formatRatioPercent(summary.target_symbol_intersection_ratio_avg)} />
        <FactoryMetric title="扩池次数" value={summary.universe_expansion_count ?? 0} />
        <FactoryMetric title="偏好错配" value={summary.preference_mismatch_warning_count ?? 0} />
        <FactoryMetric title="事件窗污染" value={summary.event_window_contamination_warning_count ?? 0} />
        <FactoryMetric title="成本审计缺失" value={summary.cost_audit_missing_count ?? 0} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-text-secondary">
        <div>平均 proxy DSR：{summary.deflated_sharpe_proxy_avg == null ? '-' : Number(summary.deflated_sharpe_proxy_avg).toFixed(2)}</div>
        <div>高 PBO proxy：{summary.high_pbo_proxy_count ?? 0}</div>
        <div>尝试惩罚均值：{summary.attempt_adjusted_score_avg == null ? '-' : Number(summary.attempt_adjusted_score_avg).toFixed(2)}</div>
        <div>目标池交集均值：{formatRatioPercent(summary.target_symbol_intersection_ratio_avg)}</div>
      </div>
    </div>
  );
}

/* ---------- sub-panels ---------- */

function FactoryRunComparisonTable({ runs }: { runs: FactoryRunItem[] }) {
  const rows = [
    {
      label: '状态',
      value: (run: FactoryRunItem) => (
        run.status === 'success' ? '成功' : run.status === 'failed' ? '失败' : (run.status ?? '-')
      ),
    },
    { label: '候选生成', value: (run: FactoryRunItem) => String(run.summary?.candidates_spawned ?? 0) },
    { label: '去重后', value: (run: FactoryRunItem) => String(run.summary?.candidates_after_dedup ?? 0) },
    { label: '提交数', value: (run: FactoryRunItem) => String(run.summary?.submitted ?? 0) },
    { label: '质检通过', value: (run: FactoryRunItem) => String(run.summary?.passed_quality_gate ?? 0) },
    { label: '研究任务', value: (run: FactoryRunItem) => String(run.summary?.autonomy_task_count ?? run.summary?.autonomy_task_briefs?.length ?? 0) },
    { label: '事件任务', value: (run: FactoryRunItem) => String(run.summary?.event_task_count ?? 0) },
    { label: '快照任务', value: (run: FactoryRunItem) => String(run.summary?.snapshot_task_count ?? 0) },
    { label: '混合模式', value: (run: FactoryRunItem) => formatMixedFlag(run.summary?.event_snapshot_mixed) },
    {
      label: '来源摘要',
      value: (run: FactoryRunItem) => formatCountSummary(run.summary?.task_source_counts),
      wrap: true,
    },
    {
      label: '主导来源',
      value: (run: FactoryRunItem) => {
        const [top] = sortCountEntries(run.summary?.task_source_counts);
        return top ? `${formatTaskLabel(top[0])} ${top[1]}` : '-';
      },
    },
    {
      label: '机会类型摘要',
      value: (run: FactoryRunItem) => formatCountSummary(run.summary?.scanner_task_types),
      wrap: true,
    },
    {
      label: '主导机会类型',
      value: (run: FactoryRunItem) => {
        const [top] = sortCountEntries(run.summary?.scanner_task_types);
        return top ? `${formatTaskLabel(top[0])} ${top[1]}` : '-';
      },
      wrap: true,
    },
    { label: '淘汰数', value: (run: FactoryRunItem) => String(run.summary?.eliminated ?? 0) },
    { label: '平均 DSR', value: (run: FactoryRunItem) => formatFactoryMetricValue(run.summary?.deflated_sharpe_ratio_avg, 2) },
    { label: '高 PBO 数', value: (run: FactoryRunItem) => String(run.summary?.high_pbo_count ?? 0) },
    { label: '正式多重检验', value: (run: FactoryRunItem) => String(run.summary?.formal_multiple_testing_count ?? 0) },
    { label: '弱 White RC', value: (run: FactoryRunItem) => String(run.summary?.weak_white_reality_check_count ?? 0) },
    { label: '弱 Hansen SPA', value: (run: FactoryRunItem) => String(run.summary?.weak_hansen_spa_count ?? 0) },
    { label: '耗时(秒)', value: (run: FactoryRunItem) => String(run.elapsed_seconds ?? run.summary?.elapsed_seconds ?? '-') },
  ];

  return (
    <div className="overflow-x-auto rounded border border-border bg-surface-alt">
      <table className="min-w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-border bg-surface">
            <th className="px-3 py-2 text-left font-medium whitespace-nowrap">指标</th>
            {runs.map((run, idx) => (
              <th key={run.run_id ?? run.started_at ?? idx} className="px-3 py-2 text-left font-medium whitespace-nowrap min-w-28">
                <div>第 {idx + 1} 次</div>
                <div className="mt-1 text-caption text-text-secondary font-normal">
                  {run.completed_at ?? run.started_at ?? '-'}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-b border-border last:border-b-0">
              <td className="px-3 py-2 font-medium whitespace-nowrap">{row.label}</td>
              {runs.map((run, idx) => (
                <td
                  key={`${row.label}-${run.run_id ?? run.started_at ?? idx}`}
                  className={`px-3 py-2 text-text-secondary ${row.wrap ? 'whitespace-normal align-top min-w-36' : 'whitespace-nowrap'}`}
                >
                  {row.value(run)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FactoryRunTrendPanel({ runs, metricKey }: { runs: FactoryRunItem[]; metricKey: TrendMetricKey }) {
  const successCount = runs.filter((run) => run.status === 'success').length;
  const successRate = runs.length > 0 ? Math.round((successCount / runs.length) * 100) : 0;
  const avgElapsed = runs.length > 0
    ? (runs.reduce((sum, run) => sum + Number(run.elapsed_seconds ?? run.summary?.elapsed_seconds ?? 0), 0) / runs.length).toFixed(1)
    : '0.0';
  const latest = runs[runs.length - 1];
  const first = runs[0];

  const metrics = [
    { key: 'candidates_spawned', label: '候选生成', value: (run: FactoryRunItem) => Number(run.summary?.candidates_spawned ?? 0) },
    { key: 'submitted', label: '提交数', value: (run: FactoryRunItem) => Number(run.summary?.submitted ?? 0) },
    { key: 'passed_quality_gate', label: '质检通过', value: (run: FactoryRunItem) => Number(run.summary?.passed_quality_gate ?? 0) },
    { key: 'elapsed_seconds', label: '耗时(秒)', value: (run: FactoryRunItem) => Number(run.elapsed_seconds ?? run.summary?.elapsed_seconds ?? 0) },
    {
      key: 'autonomy_task_count',
      label: '研究任务',
      value: (run: FactoryRunItem) => Number(run.summary?.autonomy_task_count ?? run.summary?.autonomy_task_briefs?.length ?? 0),
    },
    { key: 'event_task_count', label: '事件任务', value: (run: FactoryRunItem) => Number(run.summary?.event_task_count ?? 0) },
    { key: 'snapshot_task_count', label: '快照任务', value: (run: FactoryRunItem) => Number(run.summary?.snapshot_task_count ?? 0) },
    { key: 'deflated_sharpe_ratio_avg', label: '平均 DSR', value: (run: FactoryRunItem) => Number(run.summary?.deflated_sharpe_ratio_avg ?? 0), digits: 2 },
    { key: 'high_pbo_count', label: '高 PBO 数', value: (run: FactoryRunItem) => Number(run.summary?.high_pbo_count ?? 0) },
    { key: 'formal_multiple_testing_count', label: '正式多重检验', value: (run: FactoryRunItem) => Number(run.summary?.formal_multiple_testing_count ?? 0) },
  ];
  const activeMetric = metrics.find((metric) => metric.key === metricKey) ?? metrics[0];

  return (
    <div className="rounded border border-border bg-surface-alt p-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <FactoryMetric title="最近成功率" value={`${successRate}%`} />
        <FactoryMetric title="平均耗时(秒)" value={avgElapsed} />
        <FactoryMetric title="最新候选数" value={latest?.summary?.candidates_spawned ?? 0} />
        <FactoryMetric title="最新质检通过" value={latest?.summary?.passed_quality_gate ?? 0} />
      </div>

      <div className="mt-4 space-y-3">
        {(() => {
          const values = runs.map(activeMetric.value);
          const max = Math.max(...values, 1);
          const latestValue = activeMetric.value(latest);
          const firstValue = activeMetric.value(first);
          const delta = latestValue - firstValue;
          const digits = activeMetric.digits ?? 0;

          return (
            <div className="rounded border border-border bg-surface px-3 py-3">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="font-medium">{activeMetric.label}</span>
                <span className="text-text-secondary">
                  最新 {formatFactoryMetricValue(latestValue, digits)} · 较最早 {delta > 0 ? '+' : ''}{formatFactoryMetricValue(delta, digits)}
                </span>
              </div>
              <div className="mt-2 flex items-end gap-2 h-24">
                {runs.map((run, idx) => {
                  const value = activeMetric.value(run);
                  const height = Math.max((value / max) * 100, value > 0 ? 8 : 2);
                  return (
                    <div key={`${activeMetric.key}-${run.run_id ?? idx}`} className="flex-1 min-w-0">
                      <div className="h-20 flex items-end">
                      <div
                          className={`w-full rounded-t ${run.status === 'failed' ? 'bg-danger/70' : 'bg-primary/70'}`}
                          style={{ height: `${height}%` }}
                          title={`${activeMetric.label}: ${formatFactoryMetricValue(value, digits)}`}
                        />
                      </div>
                      <div className="mt-1 text-center text-caption text-text-secondary truncate">
                        {idx + 1}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

function FactoryRunFailurePanel({ runs, totalRuns }: { runs: FactoryRunItem[]; totalRuns: number }) {
  const failureRate = totalRuns > 0 ? Math.round((runs.length / totalRuns) * 100) : 0;
  const latestFailed = runs[0];
  const reasonBuckets = new Map<string, { count: number; example: string }>();
  const stageBuckets = new Map<string, number>();
  const unclassifiedExamples = new Map<string, number>();
  const matchedLabels = new Set<string>();
  let matchedCount = 0;

  runs.forEach((run) => {
    const fingerprint = getFactoryRunErrorFingerprint(run.error);
    const current = reasonBuckets.get(fingerprint.label);
    reasonBuckets.set(fingerprint.label, {
      count: (current?.count ?? 0) + 1,
      example: current?.example ?? fingerprint.example,
    });

    if (fingerprint.matched) {
      matchedCount += 1;
      matchedLabels.add(fingerprint.label);
    } else {
      unclassifiedExamples.set(fingerprint.example, (unclassifiedExamples.get(fingerprint.example) ?? 0) + 1);
    }

    const stage = detectFailedStage(run);
    stageBuckets.set(stage, (stageBuckets.get(stage) ?? 0) + 1);
  });

  const topReasons = [...reasonBuckets.entries()]
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 3);
  const topStages = [...stageBuckets.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);
  const topUnclassifiedExamples = [...unclassifiedExamples.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);
  const unclassifiedCount = runs.length - matchedCount;
  const matchRate = runs.length > 0 ? Math.round((matchedCount / runs.length) * 100) : 0;
  const coverageCount = matchedLabels.size;

  return (
    <div className="rounded border border-border bg-surface-alt p-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <FactoryMetric title="最近失败次数" value={runs.length} />
        <FactoryMetric title="失败率" value={`${failureRate}%`} />
        <FactoryMetric title="最近失败阶段" value={detectFailedStage(latestFailed)} />
        <FactoryMetric title="最近失败时间" value={shortFactoryRunTime(latestFailed.completed_at ?? latestFailed.started_at)} />
      </div>

      <div className="mt-4 rounded border border-border bg-surface px-3 py-3">
        <div className="text-xs font-medium mb-3">规则命中统计</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <FactoryMetric title="规则命中失败" value={matchedCount} />
          <FactoryMetric title="规则命中率" value={`${matchRate}%`} />
          <FactoryMetric title="未分类错误" value={unclassifiedCount} />
          <FactoryMetric title="覆盖指纹种类" value={coverageCount} />
        </div>

        <div className="mt-3 text-xs text-text-secondary">
          统计口径：规则命中率 = 已命中规则失败数 / 最近失败总数；覆盖指纹种类仅统计已命中规则的错误类别。
        </div>

        {topUnclassifiedExamples.length > 0 && (
          <div className="mt-3 rounded border border-border bg-surface-alt px-3 py-3">
            <div className="text-xs font-medium mb-2">未分类错误示例</div>
            <div className="space-y-2 text-xs text-text-secondary">
              {topUnclassifiedExamples.map(([example, count]) => (
                <div key={example} className="flex items-start justify-between gap-3">
                  <span className="break-all">{example}</span>
                  <span className="shrink-0">{count} 次</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded border border-border bg-surface px-3 py-3">
          <div className="text-xs font-medium mb-2">常见错误原因</div>
          <div className="space-y-2 text-xs text-text-secondary">
            {topReasons.map(([reason, meta]) => (
              <div key={reason} className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="break-all">{reason}</div>
                  <div className="mt-1 text-caption text-text-tertiary break-all">示例：{meta.example}</div>
                </div>
                <span className="shrink-0">{meta.count} 次</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded border border-border bg-surface px-3 py-3">
          <div className="text-xs font-medium mb-2">失败阶段分布</div>
          <div className="space-y-2 text-xs text-text-secondary">
            {topStages.map(([stage, count]) => (
              <div key={stage} className="flex items-center justify-between gap-3">
                <span>{stage}</span>
                <span>{count} 次</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {latestFailed?.error && (
        <div className="mt-4 rounded border border-border bg-surface px-3 py-3">
          <div className="text-xs font-medium mb-2">最近失败详情</div>
          <div className="text-xs text-danger break-all">{normalizeFactoryRunError(latestFailed.error)}</div>
          <div className="mt-2 text-caption text-text-secondary">
            错误指纹：{getFactoryRunErrorFingerprint(latestFailed.error).label}
          </div>
        </div>
      )}
    </div>
  );
}

function FactoryRunDetailPanel({
  detail,
  loading,
  error,
}: {
  detail: FactoryRunDetailResponse | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) {
    return <div className="mt-3 text-xs text-text-secondary">加载运行详情...</div>;
  }
  if (error) {
    return <div className="mt-3 text-xs text-danger">加载详情失败：{error}</div>;
  }
  if (!detail) {
    return <div className="mt-3 text-xs text-text-secondary">暂无运行详情</div>;
  }

  const snapshotRows = Object.entries(detail.snapshot_summary ?? {});
  const stageRows = Object.entries(detail.stages ?? {});
  const summary = detail.summary ?? {};

  return (
    <div className="mt-3 rounded border border-border bg-surface px-3 py-3 space-y-3">
      <div>
        <div className="text-xs font-medium">运行标识</div>
        <div className="mt-1 text-xs text-text-secondary break-all">{detail.run_id ?? '-'}</div>
      </div>

      <div>
        <div className="text-xs font-medium">运行摘要</div>
        <div className="mt-1 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-text-secondary">
          <div>候选生成：{summary.candidates_spawned ?? 0}</div>
          <div>研究任务：{summary.autonomy_task_count ?? summary.autonomy_task_briefs?.length ?? 0}</div>
          <div>事件任务：{summary.event_task_count ?? 0}</div>
          <div>快照任务：{summary.snapshot_task_count ?? 0}</div>
          <div>提交数：{summary.submitted ?? 0}</div>
          <div>质检通过：{summary.passed_quality_gate ?? 0}</div>
          <div>淘汰数：{summary.eliminated ?? 0}</div>
          <div>混合模式：{formatMixedFlag(summary.event_snapshot_mixed)}</div>
        </div>
      </div>

      <FactoryTaskStructurePanel summary={summary} />
      <FactoryQualityAuditPanel summary={summary} />

      {snapshotRows.length > 0 && (
        <div>
          <div className="text-xs font-medium">快照摘要</div>
          <div className="mt-1 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-text-secondary">
            {snapshotRows.map(([key, value]) => (
              <div key={key}>{key}: {String(value ?? '-')}</div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="text-xs font-medium">阶段结果</div>
        {stageRows.length > 0 ? (
          <div className="mt-1 space-y-2">
            {stageRows.map(([stage, payload]) => (
              <div key={stage} className="rounded border border-border px-2 py-2 text-xs text-text-secondary">
                <div className="font-medium text-text-primary mb-1">{stage}</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {Object.entries(payload ?? {}).map(([key, value]) => (
                    <div key={key}>{key}: {String(value ?? '-')}</div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-1 text-xs text-text-secondary">暂无阶段详情</div>
        )}
      </div>

      {detail.error && (
        <div className="text-xs text-danger">错误信息：{detail.error}</div>
      )}
    </div>
  );
}

/* ---------- main export ---------- */

export type FactoryDashboardProps = {
  factoryStatus: FactoryStatusResponse | null | undefined;
  latestSnapshot: DailySnapshotResponse | null;
  capabilityBadges: CapabilityBadge[];
  capabilitiesError: string | null;
  dailySnapshotError: string | null;
  factorySummary: NonNullable<FactoryStatusResponse['last_summary']>;
  snapshotCompletionRatio?: number | null;
  snapshotDegraded: boolean;
  snapshotFailureCount: number;
  /* run factory */
  onRunFactory: () => void;
  runFactoryPending: boolean;
  runFactoryError: string | null;
  /* runs */
  factoryRunsLoading: boolean;
  factoryRuns: FactoryRunItem[];
  filteredRuns: FactoryRunItem[];
  failedRuns: FactoryRunItem[];
  comparableRuns: FactoryRunItem[];
  trendRuns: FactoryRunItem[];
  /* filters / expand */
  runStatusFilter: RunStatusFilter;
  onRunStatusFilterChange: (value: RunStatusFilter) => void;
  trendMetricKey: TrendMetricKey;
  onTrendMetricKeyChange: (value: TrendMetricKey) => void;
  expandedRunId: string | null;
  onExpandedRunIdChange: (id: string | null) => void;
  expandedRun: FactoryRunDetailResponse | null;
  expandedRunLoading: boolean;
  expandedRunError: string | null;
};

export function FactoryDashboard({
  factoryStatus,
  latestSnapshot,
  capabilityBadges,
  capabilitiesError,
  dailySnapshotError,
  factorySummary,
  snapshotCompletionRatio,
  snapshotDegraded,
  snapshotFailureCount,
  onRunFactory,
  runFactoryPending,
  runFactoryError,
  factoryRunsLoading,
  factoryRuns,
  filteredRuns,
  failedRuns,
  comparableRuns,
  trendRuns,
  runStatusFilter,
  onRunStatusFilterChange,
  trendMetricKey,
  onTrendMetricKeyChange,
  expandedRunId,
  onExpandedRunIdChange,
  expandedRun,
  expandedRunLoading,
  expandedRunError,
}: FactoryDashboardProps) {
  return (
    <SectionCard className="mt-4 p-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="m-0">策略工厂运行态</h3>
          <p className="m-0 mt-1 text-sm text-text-secondary">
            调度状态：{factoryStatus?.running ? '运行中' : '未启动'} · 上次运行：{factoryStatus?.last_run ?? '暂无'}
            {latestSnapshot?.snapshot_date ? ` · 最新快照：${latestSnapshot.snapshot_date}` : ''}
          </p>
        </div>
        <button
          onClick={onRunFactory}
          disabled={runFactoryPending}
          className="px-3 py-1.5 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
        >
          {runFactoryPending ? '运行中...' : '立即运行一轮工厂'}
        </button>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-3 mt-4 text-sm">
        <FactoryMetric title="候选生成" value={factorySummary.candidates_spawned ?? 0} />
        <FactoryMetric title="AI生成" value={factorySummary.autonomy_generated ?? 0} />
        <FactoryMetric title="通过回测" value={factorySummary.candidates_passed_backtest ?? 0} />
        <FactoryMetric title="去重后" value={factorySummary.candidates_after_dedup ?? 0} />
        <FactoryMetric title="质检通过" value={factorySummary.passed_quality_gate ?? 0} />
        <FactoryMetric title="快照完成率" value={formatRatioPercent(snapshotCompletionRatio)} />
        <FactoryMetric title="快照状态" value={snapshotDegraded ? '降级' : '正常'} />
        <FactoryMetric title="快照异常数" value={snapshotFailureCount} />
        <FactoryMetric title="淘汰数" value={factorySummary.eliminated ?? 0} />
        <FactoryMetric title="耗时(秒)" value={factorySummary.elapsed_seconds ?? '-'} />
      </div>
      <FactoryTaskStructurePanel summary={factorySummary} />
      <FactoryQualityAuditPanel summary={factorySummary} />
      <div className="mt-3 flex flex-wrap gap-2">
        {capabilityBadges.map((item) => (
          <Badge key={item.key} variant={item.enabled ? 'success' : 'neutral'}>
            {item.label}{item.enabled ? '已接入' : '未接入'}
          </Badge>
        ))}
      </div>
      {latestSnapshot && (
        <div className="mt-3 rounded border border-border bg-surface-alt px-3 py-2 text-xs text-text-secondary space-y-1">
          <div>
            恐慌贪婪：{latestSnapshot.fear_greed_index ?? '-'} · 已上架策略：{latestSnapshot.summary?.listed_count ?? '-'} · 缺失字段：{latestSnapshot.missing_fields?.length ?? 0}
          </div>
          {latestSnapshot.hot_sectors?.length ? <div>热点板块：{latestSnapshot.hot_sectors.slice(0, 4).join('、')}</div> : null}
          {snapshotFailureCount > 0 ? (
            <div className={snapshotDegraded ? 'text-warning' : ''}>
              快照异常：{(latestSnapshot.failure_reasons ?? []).slice(0, 3).join('；') || '存在异常但未返回原因'}
            </div>
          ) : null}
        </div>
      )}
      {capabilitiesError && <p className="mt-3 mb-0 text-sm text-danger">能力接口加载失败：{capabilitiesError}</p>}
      {dailySnapshotError && <p className="mt-3 mb-0 text-sm text-danger">日快照加载失败：{dailySnapshotError}</p>}
      {factoryStatus?.last_result?.status === 'failed' && (
        <p className="mt-3 mb-0 text-sm text-danger">最近一次工厂运行失败：{factoryStatus?.last_result?.error ?? '未知错误'}</p>
      )}
      {runFactoryError && <p className="mt-3 mb-0 text-sm text-danger">{runFactoryError}</p>}
      {factoryRunsLoading && <p className="mt-3 mb-0 text-sm text-text-secondary">加载运行历史...</p>}
      {!factoryRunsLoading && factoryRuns.length === 0 && (
        <p className="mt-3 mb-0 text-sm text-text-secondary">暂无工厂运行历史</p>
      )}
      {factoryRuns.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-xs text-text-secondary">状态筛选：</span>
          {[
            { key: 'all', label: '全部' },
            { key: 'success', label: '成功' },
            { key: 'failed', label: '失败' },
          ].map((item) => (
            <button
              key={item.key}
              onClick={() => onRunStatusFilterChange(item.key as RunStatusFilter)}
              className={`px-2 py-1 text-xs rounded border cursor-pointer ${runStatusFilter === item.key ? 'border-primary text-primary bg-primary/5' : 'border-border hover:bg-surface'}`}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
      {!factoryRunsLoading && factoryRuns.length > 0 && filteredRuns.length === 0 && (
        <p className="mt-3 mb-0 text-sm text-text-secondary">当前筛选条件下暂无运行记录</p>
      )}
      {filteredRuns.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="text-sm font-medium">最近运行历史</div>
          {filteredRuns.map((item) => (
            <div key={item.run_id ?? item.started_at} className="rounded border border-border bg-surface-alt px-3 py-2">
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="font-medium">{item.status === 'success' ? '成功' : item.status === 'failed' ? '失败' : (item.status ?? '-')}</span>
                <span className="text-text-secondary">{item.completed_at ?? item.started_at ?? '-'}</span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mt-2 text-xs text-text-secondary">
                <span>候选 {item.summary?.candidates_spawned ?? 0}</span>
                <span>去重后 {item.summary?.candidates_after_dedup ?? 0}</span>
                <span>提交 {item.summary?.submitted ?? 0}</span>
                <span>质检通过 {item.summary?.passed_quality_gate ?? 0}</span>
                <span>淘汰 {item.summary?.eliminated ?? 0}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <Badge variant="neutral">
                  研究任务 {item.summary?.autonomy_task_count ?? item.summary?.autonomy_task_briefs?.length ?? 0}
                </Badge>
                <Badge variant="neutral">事件 {item.summary?.event_task_count ?? 0}</Badge>
                <Badge variant="neutral">快照 {item.summary?.snapshot_task_count ?? 0}</Badge>
                <Badge variant={item.summary?.event_snapshot_mixed ? 'success' : 'neutral'}>
                  混合 {formatMixedFlag(item.summary?.event_snapshot_mixed)}
                </Badge>
                {(() => {
                  const [topSource] = sortCountEntries(item.summary?.task_source_counts);
                  return topSource ? (
                    <Badge variant="neutral">
                      主导来源 {formatTaskLabel(topSource[0])} {topSource[1]}
                    </Badge>
                  ) : null;
                })()}
                {(() => {
                  const [topType] = sortCountEntries(item.summary?.scanner_task_types);
                  return topType ? (
                    <Badge variant="info">
                      主导机会 {formatTaskLabel(topType[0])} {topType[1]}
                    </Badge>
                  ) : null;
                })()}
              </div>
              {hasRunAuditMetrics(item.summary) ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {item.summary?.deflated_sharpe_ratio_avg != null ? (
                    <Badge variant="info">
                      DSR 均值 {formatFactoryMetricValue(item.summary?.deflated_sharpe_ratio_avg, 2)}
                    </Badge>
                  ) : null}
                  <Badge variant={(item.summary?.high_pbo_count ?? 0) > 0 ? 'warning' : 'neutral'}>
                    高 PBO {item.summary?.high_pbo_count ?? 0}
                  </Badge>
                  <Badge variant={(item.summary?.formal_multiple_testing_count ?? 0) > 0 ? 'success' : 'neutral'}>
                    正式多重检验 {item.summary?.formal_multiple_testing_count ?? 0}
                  </Badge>
                  <Badge variant={(item.summary?.weak_white_reality_check_count ?? 0) > 0 ? 'warning' : 'neutral'}>
                    弱 White RC {item.summary?.weak_white_reality_check_count ?? 0}
                  </Badge>
                  <Badge variant={(item.summary?.weak_hansen_spa_count ?? 0) > 0 ? 'warning' : 'neutral'}>
                    弱 Hansen SPA {item.summary?.weak_hansen_spa_count ?? 0}
                  </Badge>
                </div>
              ) : null}
              <div className="mt-2 text-xs text-text-secondary">
                耗时：{item.elapsed_seconds ?? item.summary?.elapsed_seconds ?? '-'} 秒
              </div>
              {item.error && <div className="mt-2 text-xs text-danger">错误：{item.error}</div>}
              {item.run_id && (
                <div className="mt-3">
                  <button
                    onClick={() => onExpandedRunIdChange(expandedRunId === item.run_id ? null : item.run_id ?? null)}
                    className="px-2 py-1 text-xs rounded border border-border cursor-pointer hover:bg-surface"
                  >
                    {expandedRunId === item.run_id ? '收起详情' : '查看详情'}
                  </button>
                </div>
              )}
              {expandedRunId === item.run_id && (
                <FactoryRunDetailPanel
                  loading={expandedRunLoading}
                  detail={expandedRun}
                  error={expandedRunError}
                />
              )}
            </div>
          ))}
        </div>
      )}
      {comparableRuns.length > 1 && (
        <div className="mt-5">
          <div className="text-sm font-medium mb-2">最近运行对比</div>
          <FactoryRunComparisonTable runs={comparableRuns} />
        </div>
      )}
      {trendRuns.length > 1 && (
        <div className="mt-5">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <div className="text-sm font-medium">运行趋势</div>
            <div className="flex flex-wrap items-center gap-2">
                {[
                { key: 'candidates_spawned', label: '候选生成' },
                { key: 'submitted', label: '提交数' },
                { key: 'passed_quality_gate', label: '质检通过' },
                { key: 'elapsed_seconds', label: '耗时' },
                { key: 'autonomy_task_count', label: '研究任务' },
                { key: 'event_task_count', label: '事件任务' },
                { key: 'snapshot_task_count', label: '快照任务' },
                { key: 'deflated_sharpe_ratio_avg', label: '平均 DSR' },
                { key: 'high_pbo_count', label: '高 PBO 数' },
                { key: 'formal_multiple_testing_count', label: '正式多重检验' },
              ].map((item) => (
                <button
                  key={item.key}
                  onClick={() => onTrendMetricKeyChange(item.key as TrendMetricKey)}
                  className={`px-2 py-1 text-xs rounded border cursor-pointer ${trendMetricKey === item.key ? 'border-primary text-primary bg-primary/5' : 'border-border hover:bg-surface'}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <FactoryRunTrendPanel runs={trendRuns} metricKey={trendMetricKey} />
          <FactoryRunStructureDiagnosticsPanel runs={trendRuns} />
        </div>
      )}
      {failedRuns.length > 0 && (
        <div className="mt-5">
          <div className="text-sm font-medium mb-2">失败原因聚合</div>
          <FactoryRunFailurePanel runs={failedRuns} totalRuns={factoryRuns.length} />
        </div>
      )}
    </SectionCard>
  );
}
