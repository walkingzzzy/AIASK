'use client';

import { Badge } from '@/components/ui';
import { formatCountSummary, formatRatioPercent } from '@/app/strategy-market/lib/factory-dashboard-helpers';
import type {
  FactoryQualityBaseline,
  FactoryQualitySummarySnapshot,
  FactoryStatusResponse,
} from '../../types';

import { isObjectRecord, toDisplayNumber } from './formatters';

export function FactoryHighConfidenceQualityPanel({
  factoryStatus,
}: {
  factoryStatus: FactoryStatusResponse | null | undefined;
}) {
  const qualityUiV2Enabled = Boolean(
    factoryStatus?.quality_ui_v2_enabled ?? factoryStatus?.feature_flags?.quality_ui_v2_enabled,
  );
  const qualityBaseline: Partial<FactoryQualityBaseline> = factoryStatus?.quality_baseline ?? {};
  const latestRun: Partial<FactoryQualitySummarySnapshot> = qualityBaseline.latest_run ?? {};
  const cohort: NonNullable<FactoryQualityBaseline['submitted_strategy_cohort']> =
    qualityBaseline.submitted_strategy_cohort ?? {};

  if (!qualityUiV2Enabled) return null;

  const hasHighConfidenceData = [
    latestRun.prediction_quality_distribution,
    latestRun.execution_quality_distribution,
    latestRun.evidence_alignment_distribution,
    latestRun.confidence_contract_ready_rate,
    cohort.prediction_quality_distribution,
    cohort.execution_quality_distribution,
    cohort.evidence_alignment_distribution,
    cohort.confidence_contract_ready_rate,
  ].some((value) => {
    if (isObjectRecord(value)) return Object.keys(value).length > 0;
    return value != null;
  });

  if (!hasHighConfidenceData) return null;

  const sections = [
    {
      key: 'latest',
      title: '最近一轮',
      summary: latestRun,
    },
    {
      key: 'cohort',
      title: '已提交 Cohort',
      summary: cohort,
    },
  ].filter((item) => {
    const summary = item.summary;
    return [
      summary.prediction_quality_distribution,
      summary.execution_quality_distribution,
      summary.evidence_alignment_distribution,
      summary.confidence_contract_ready_rate,
    ].some((value) => {
      if (isObjectRecord(value)) return Object.keys(value).length > 0;
      return value != null;
    });
  });

  return (
    <div className="mt-3 rounded border border-border bg-surface-alt p-3 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs font-medium text-text-primary">高置信质量面板</div>
        <Badge variant="info">UI V2</Badge>
      </div>
      <div className="text-xs text-text-secondary">
        预测质量、执行质量、证据对齐和合同就绪率按 cohort / 最近一轮并排展示，旧 KPI 卡片保持不变。
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        {sections.map(({ key, title, summary }) => (
          <div
            key={key}
            className="rounded border border-border bg-surface px-3 py-3 space-y-3 text-xs text-text-secondary"
          >
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="font-medium text-text-primary">{title}</div>
              <Badge variant="neutral">
                合同就绪率 {formatRatioPercent(toDisplayNumber(summary.confidence_contract_ready_rate))}
              </Badge>
            </div>
            <div className="grid grid-cols-1 gap-2">
              <div>预测质量：{formatCountSummary(summary.prediction_quality_distribution ?? {}) || '-'}</div>
              <div>执行质量：{formatCountSummary(summary.execution_quality_distribution ?? {}) || '-'}</div>
              <div>证据对齐：{formatCountSummary(summary.evidence_alignment_distribution ?? {}) || '-'}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
