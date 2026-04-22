'use client';

import Link from 'next/link';
import { Badge, DataTable, SectionCard } from '@/components/ui';
import { ErrorState, LoadingState } from '@/components/status-state';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import { buildStrategyDetailPlaceholderHref } from '@/lib/surface-contracts';
import { primaryRoundButtonCls, secondaryRoundButtonCls, secondaryRoundLinkCls, summaryChipCls } from './strategy-market-panel-styles';

type FactoryOverviewItem = {
  label: string;
  value: string;
};

type StrategyMarketFactoryOverviewSectionProps = {
  showEmptyStrategyState: boolean;
  snapshotDegraded: boolean;
  factoryOverview: FactoryOverviewItem[];
  snapshotCompletionRatio: number | null | undefined;
  snapshotFailureCount: number;
  failedRunsCount: number;
};

export function StrategyMarketFactoryOverviewSection({
  showEmptyStrategyState,
  snapshotDegraded,
  factoryOverview,
  snapshotCompletionRatio,
  snapshotFailureCount,
  failedRunsCount,
}: StrategyMarketFactoryOverviewSectionProps) {
  return (
    <SectionCard className="mt-0" data-testid="strategy-market-factory-overview">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="eyebrow">工厂概况</div>
          <h2 className="mt-2">{showEmptyStrategyState ? '先确认工厂有没有产出' : '只看关键工厂指标'}</h2>
        </div>
        <Badge variant={snapshotDegraded ? 'warning' : 'success'}>
          {snapshotDegraded ? '快照存在降级' : '快照完整'}
        </Badge>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {factoryOverview.map((item) => (
          <div key={item.label} className="metric-tile rounded-[24px] px-4 py-4">
            <div className="metric-label">{item.label}</div>
            <div className="mt-2 text-base font-semibold text-text-primary">{item.value}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-text-secondary">
        <span className={summaryChipCls}>
          快照完成率 {snapshotCompletionRatio == null ? '-' : fmtPct(snapshotCompletionRatio)}
        </span>
        <span className={summaryChipCls}>失败原因 {snapshotFailureCount}</span>
        <span className={summaryChipCls}>最近失败运行 {failedRunsCount}</span>
      </div>
    </SectionCard>
  );
}

type StrategyMarketObservabilitySectionProps = {
  isPending: boolean;
  error: string | null;
  schedulerStale: boolean;
  activeFactorCount: number;
  degraded: boolean;
  latestFactoryStatus: string;
  governedFactorCount: string;
  passedQualityGate: string;
  championCount: string;
  challengerCount: string;
  schedulerQualityStatus: string;
  recentGeneratedCandidateCount: string;
  recentValidatedCandidateCount: string;
  retrainPlanCount: string;
  latestFactoryRunId: string;
  schedulerFreshnessSec: number | null;
  blockedFactorCount: number;
  factoryRunsCount: number;
  recentGovernedActiveCountAfterRun: number;
  retrainPendingCount: number;
  errors: unknown[];
  stageRows: Array<Record<string, unknown>>;
  familyRows: Array<Record<string, unknown>>;
  recentRunGeneratedCount: number;
  recentRunValidatedCount: number;
  recentRunGovernedCount: number;
  regimeRows: Array<Record<string, unknown>>;
  retrainQueue: Array<Record<string, unknown>>;
  retrainStatusSummary: string;
};

export function StrategyMarketObservabilitySection({
  isPending,
  error,
  schedulerStale,
  activeFactorCount,
  degraded,
  latestFactoryStatus,
  governedFactorCount,
  passedQualityGate,
  championCount,
  challengerCount,
  schedulerQualityStatus,
  recentGeneratedCandidateCount,
  recentValidatedCandidateCount,
  retrainPlanCount,
  latestFactoryRunId,
  schedulerFreshnessSec,
  blockedFactorCount,
  factoryRunsCount,
  recentGovernedActiveCountAfterRun,
  retrainPendingCount,
  errors,
  stageRows,
  familyRows,
  recentRunGeneratedCount,
  recentRunValidatedCount,
  recentRunGovernedCount,
  regimeRows,
  retrainQueue,
  retrainStatusSummary,
}: StrategyMarketObservabilitySectionProps) {
  return (
    <SectionCard className="mt-0" data-testid="strategy-market-observability">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="eyebrow">联动观测</div>
          <h2 className="mt-2">工厂运行与因子治理是否真正接通</h2>
          <p className="mb-0 mt-2 text-sm text-text-secondary">
            这里把 factory 状态和 factor governed pool 放在一起看，避免出现“工厂看起来正常，但 active_pool 其实是空的或陈旧的”假阳性。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={schedulerStale ? 'warning' : 'success'}>
            {schedulerStale ? '因子调度陈旧' : '因子调度新鲜'}
          </Badge>
          <Badge variant={activeFactorCount > 0 ? 'success' : 'warning'}>
            {activeFactorCount > 0 ? 'governed pool 已就绪' : 'governed pool 为空'}
          </Badge>
          <Badge variant={degraded ? 'warning' : 'info'}>
            {degraded ? '聚合存在降级' : '聚合链路完整'}
          </Badge>
        </div>
      </div>

      {isPending ? <LoadingState text="加载工厂联动观测..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      {!isPending && !error ? (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <div className="metric-tile rounded-[24px] px-4 py-4">
              <div className="metric-label">最新工厂状态</div>
              <div className="mt-2 text-base font-semibold text-text-primary">{latestFactoryStatus}</div>
            </div>
            <div className="metric-tile rounded-[24px] px-4 py-4">
              <div className="metric-label">活跃因子数</div>
              <div className="mt-2 text-base font-semibold text-text-primary">{String(activeFactorCount)}</div>
            </div>
            <div className="metric-tile rounded-[24px] px-4 py-4">
              <div className="metric-label">治理通过</div>
              <div className="mt-2 text-base font-semibold text-text-primary">{governedFactorCount}</div>
            </div>
            <div className="metric-tile rounded-[24px] px-4 py-4">
              <div className="metric-label">质量门通过</div>
              <div className="mt-2 text-base font-semibold text-text-primary">{passedQualityGate}</div>
            </div>
            <div className="metric-tile rounded-[24px] px-4 py-4">
              <div className="metric-label">Champion / Challenger</div>
              <div className="mt-2 text-base font-semibold text-text-primary">
                {championCount} / {challengerCount}
              </div>
            </div>
            <div className="metric-tile rounded-[24px] px-4 py-4">
              <div className="metric-label">调度质量</div>
              <div className="mt-2 text-base font-semibold text-text-primary">{schedulerQualityStatus}</div>
            </div>
            <div className="metric-tile rounded-[24px] px-4 py-4">
              <div className="metric-label">本轮自动生成</div>
              <div className="mt-2 text-base font-semibold text-text-primary">{recentGeneratedCandidateCount}</div>
            </div>
            <div className="metric-tile rounded-[24px] px-4 py-4">
              <div className="metric-label">本轮验证通过</div>
              <div className="mt-2 text-base font-semibold text-text-primary">{recentValidatedCandidateCount}</div>
            </div>
            <div className="metric-tile rounded-[24px] px-4 py-4">
              <div className="metric-label">Retrain 队列</div>
              <div className="mt-2 text-base font-semibold text-text-primary">{retrainPlanCount}</div>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap gap-2 text-xs text-text-secondary">
            <span className={summaryChipCls}>最新工厂 Run {latestFactoryRunId}</span>
            <span className={summaryChipCls}>
              调度 freshness {schedulerFreshnessSec == null ? '-' : `${fmtNum(schedulerFreshnessSec, 1)}s`}
            </span>
            <span className={summaryChipCls}>被阻断候选 {blockedFactorCount}</span>
            <span className={summaryChipCls}>工厂最近 5 次 {factoryRunsCount} 条</span>
            <span className={summaryChipCls}>本轮 governed {recentGovernedActiveCountAfterRun}</span>
            <span className={summaryChipCls}>待执行 Retrain {retrainPendingCount}</span>
          </div>

          {errors.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {errors.map((item, index) => (
                <Badge key={`${String(item)}-${index}`} variant="warning">
                  {String(item)}
                </Badge>
              ))}
            </div>
          ) : null}

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <div className="panel-soft rounded-[24px] p-4">
              <div className="eyebrow">Registry Stage</div>
              <h3 className="mt-2">候选治理阶段</h3>
              {stageRows.length > 0 ? (
                <DataTable
                  rows={stageRows}
                  columns={[
                    { key: 'registry_stage', label: '阶段' },
                    { key: 'count', label: '数量', align: 'right' as const },
                  ]}
                />
              ) : (
                <p className="mb-0 mt-3 text-sm text-text-secondary">暂无 registry 阶段数据。</p>
              )}
            </div>

            <div className="panel-soft rounded-[24px] p-4">
              <div className="eyebrow">Active Pool</div>
              <h3 className="mt-2">活跃池家族分布</h3>
              {familyRows.length > 0 ? (
                <DataTable
                  rows={familyRows}
                  columns={[
                    { key: 'family', label: '家族' },
                    { key: 'count', label: '候选数', align: 'right' as const },
                    { key: 'promote_count', label: 'promote', align: 'right' as const },
                    {
                      key: 'avg_total_score',
                      label: '平均分',
                      align: 'right' as const,
                      render: (value: unknown) => fmtNum(value, 3),
                    },
                  ]}
                />
              ) : (
                <p className="mb-0 mt-3 text-sm text-text-secondary">active_pool 暂无家族分布。</p>
              )}
            </div>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            <div className="panel-soft rounded-[24px] p-4">
              <div className="eyebrow">Recent Auto Run</div>
              <h3 className="mt-2">最近一次自动挖掘</h3>
              <p className="mb-0 mt-3 text-sm leading-7 text-text-secondary">
                生成 {recentRunGeneratedCount} 个候选，验证通过 {recentRunValidatedCount} 个，运行后 governed active {recentRunGovernedCount} 个。
              </p>
            </div>

            <div className="panel-soft rounded-[24px] p-4">
              <div className="eyebrow">Regime Mix</div>
              <h3 className="mt-2">活跃池 Regime 分布</h3>
              {regimeRows.length > 0 ? (
                <DataTable
                  rows={regimeRows}
                  columns={[
                    { key: 'regime', label: 'Regime' },
                    { key: 'count', label: '数量', align: 'right' as const },
                  ]}
                />
              ) : (
                <p className="mb-0 mt-3 text-sm text-text-secondary">当前没有 regime 分布。</p>
              )}
            </div>

            <div className="panel-soft rounded-[24px] p-4">
              <div className="eyebrow">Retrain Queue</div>
              <h3 className="mt-2">重训练计划队列</h3>
              {retrainQueue.length > 0 ? (
                <DataTable
                  rows={retrainQueue}
                  columns={[
                    { key: 'family', label: '家族' },
                    { key: 'status', label: '状态' },
                    { key: 'priority', label: '优先级' },
                    { key: 'target_model_count', label: '目标模型', align: 'right' as const },
                  ]}
                />
              ) : (
                <p className="mb-0 mt-3 text-sm text-text-secondary">当前没有 retrain 计划。</p>
              )}
              <div className="mt-3 text-xs text-text-secondary">状态分布 {retrainStatusSummary || '-'}</div>
            </div>
          </div>
        </>
      ) : null}
    </SectionCard>
  );
}

type StrategyMarketEmptyStateSectionProps = {
  runFactoryPending: boolean;
  onRunFactory: () => void;
  onShowFactoryDetails: () => void;
};

export function StrategyMarketEmptyStateSection({
  runFactoryPending,
  onRunFactory,
  onShowFactoryDetails,
}: StrategyMarketEmptyStateSectionProps) {
  return (
    <SectionCard className="mt-0">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2>当前还没有可选策略</h2>
          <p className="mb-0 mt-2 text-sm text-text-secondary">
            常见原因是工厂尚未运行、最新候选还在质量门控里，或者策略仍停留在孵化态。建议先执行工厂，再去看详细运行态确认卡点。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onRunFactory}
            disabled={runFactoryPending}
            className={primaryRoundButtonCls}
          >
            {runFactoryPending ? '运行中...' : '立即运行一轮工厂'}
          </button>
          <button type="button" onClick={onShowFactoryDetails} className={secondaryRoundButtonCls}>
            查看工厂运行态
          </button>
          <Link href={buildStrategyDetailPlaceholderHref()} className={secondaryRoundLinkCls}>
            查看详情空态
          </Link>
          <a href="/paper-trading" className={secondaryRoundLinkCls}>
            了解孵化后的落地路径
          </a>
        </div>
      </div>
    </SectionCard>
  );
}
