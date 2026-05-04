'use client';

import { Badge } from '@/components/ui';
import {
  detectFailedStage,
  formatCountSummary,
  formatFactoryMetricValue,
  formatMixedFlag,
  formatTaskLabel,
  getFactoryRunErrorFingerprint,
  getFactoryRunStatusLabel,
  normalizeFactoryRunError,
  shortFactoryRunTime,
  sortCountEntries,
} from '@/app/strategy-market/lib/factory-dashboard-helpers';
import type { FactoryRunItem, FactoryStatusResponse, TrendMetricKey } from '../../types';
import { FactoryMetric } from './metrics';

export const FACTORY_TREND_METRICS: Array<{ key: TrendMetricKey; label: string }> = [
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
];

export function FactoryRunComparisonTable({ runs }: { runs: FactoryRunItem[] }) {
  const rows = [
    {
      label: '状态',
      value: (run: FactoryRunItem) => getFactoryRunStatusLabel(run.status),
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

export function FactoryRunTrendPanel({ runs, metricKey }: { runs: FactoryRunItem[]; metricKey: TrendMetricKey }) {
  const successCount = runs.filter((run) => run.status === 'success').length;
  const successRate = runs.length > 0 ? Math.round((successCount / runs.length) * 100) : 0;
  const avgElapsed = runs.length > 0
    ? (runs.reduce((sum, run) => sum + Number(run.elapsed_seconds ?? run.summary?.elapsed_seconds ?? 0), 0) / runs.length).toFixed(1)
    : '0.0';
  const latest = runs[runs.length - 1];
  const first = runs[0];

  const metrics = FACTORY_TREND_METRICS.map((metric) => ({
    ...metric,
    value: (run: FactoryRunItem) => {
      switch (metric.key) {
        case 'candidates_spawned':
          return Number(run.summary?.candidates_spawned ?? 0);
        case 'submitted':
          return Number(run.summary?.submitted ?? 0);
        case 'passed_quality_gate':
          return Number(run.summary?.passed_quality_gate ?? 0);
        case 'elapsed_seconds':
          return Number(run.elapsed_seconds ?? run.summary?.elapsed_seconds ?? 0);
        case 'autonomy_task_count':
          return Number(run.summary?.autonomy_task_count ?? run.summary?.autonomy_task_briefs?.length ?? 0);
        case 'event_task_count':
          return Number(run.summary?.event_task_count ?? 0);
        case 'snapshot_task_count':
          return Number(run.summary?.snapshot_task_count ?? 0);
        case 'deflated_sharpe_ratio_avg':
          return Number(run.summary?.deflated_sharpe_ratio_avg ?? 0);
        case 'high_pbo_count':
          return Number(run.summary?.high_pbo_count ?? 0);
        case 'formal_multiple_testing_count':
          return Number(run.summary?.formal_multiple_testing_count ?? 0);
        default:
          return 0;
      }
    },
    digits: metric.key === 'deflated_sharpe_ratio_avg' ? 2 : 0,
  }));
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
                          className={`w-full rounded-t ${
                            run.status === 'failed'
                              ? 'bg-danger/70'
                              : run.status === 'partial'
                                ? 'bg-warning/70'
                                : run.status === 'skipped'
                                  ? 'bg-text-secondary/40'
                                  : 'bg-primary/70'
                          }`}
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

export function FactoryRunFailurePanel({ runs, totalRuns }: { runs: FactoryRunItem[]; totalRuns: number }) {
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

export function FactoryCapabilityStateStrip({ factoryStatus }: { factoryStatus: FactoryStatusResponse | null | undefined }) {
  if (!factoryStatus) return null;

  const items = [
    {
      key: 'trace-ledger',
      label: '追踪账本 V2',
      implemented: Boolean(factoryStatus.trace_ledger_v2_implemented),
      enabled: Boolean(factoryStatus.trace_ledger_v2_enabled),
    },
    {
      key: 'gate-report',
      label: 'Gate Report V2',
      implemented: Boolean(factoryStatus.governance_gate_report_v2_implemented),
      enabled: Boolean(factoryStatus.gate_model_v2_enabled),
    },
    {
      key: 'entity-chain',
      label: 'Execution Entity Chain',
      implemented: Boolean(factoryStatus.execution_audit_entity_chain_available),
      enabled: Boolean(factoryStatus.execution_audit_entity_chain_available),
    },
  ];

  return (
    <div className="mt-3 rounded border border-border bg-surface-alt px-3 py-3 text-xs text-text-secondary">
      <div className="font-medium text-text-primary">治理能力读面</div>
      <div className="mt-2 flex flex-wrap gap-2">
        {items.map((item) => (
          <Badge key={item.key} variant={item.implemented ? (item.enabled ? 'success' : 'warning') : 'neutral'}>
            {item.label} {item.implemented ? '已实现' : '未实现'} / {item.enabled ? '已启用' : '未启用'}
          </Badge>
        ))}
      </div>
    </div>
  );
}
