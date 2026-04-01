import { Badge, DataTable, KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { fmtNum } from '@/lib/data-utils';
import { factorMiningNoteCardCls, factorMiningPanelCls } from '@/app/factor/components/factor-mining-panel-styles';
import { isRecord, joinList } from '@/app/factor/components/factor-mining-mappers';
import { BadgeValue, renderWarnings } from '@/app/factor/components/factor-mining-support';

type FactorMiningObservabilityProps = {
  isPending: boolean;
  error: string | null;
  hasData: boolean;
  degraded: boolean;
  observabilityOverview: Record<string, unknown>;
  observabilityScheduler: Record<string, unknown>;
  observabilityRecentValidation: Record<string, unknown>;
  observabilityMemoryStats: Record<string, unknown>;
  observabilityRetrainSummary: Record<string, unknown>;
  observabilityRetrainQueue: Array<Record<string, unknown>>;
  observabilityErrors: unknown[];
  observabilityFamilyRows: Array<Record<string, unknown>>;
  observabilityRegimeRows: Array<Record<string, unknown>>;
  observabilityExclusionRows: Array<Record<string, unknown>>;
  observabilityStageRows: Array<Record<string, unknown>>;
};

export default function FactorMiningObservability({
  isPending,
  error,
  hasData,
  degraded,
  observabilityOverview,
  observabilityScheduler,
  observabilityRecentValidation,
  observabilityMemoryStats,
  observabilityRetrainSummary,
  observabilityRetrainQueue,
  observabilityErrors,
  observabilityFamilyRows,
  observabilityRegimeRows,
  observabilityExclusionRows,
  observabilityStageRows,
}: FactorMiningObservabilityProps) {
  return (
    <SectionCard className="p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="eyebrow">Observability</div>
          <h3 className="mb-0 mt-2 text-xl font-semibold text-text-primary">自动挖掘与治理可观测性</h3>
          <p className="mt-2 text-sm leading-7 text-text-secondary">
            这里汇总 scheduler、governed pool、研究记忆和 champion/challenger 摘要，用来判断自动因子挖掘是否真的形成了生成
            → 验证 → 治理闭环。
          </p>
        </div>
        <div className={factorMiningPanelCls}>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前信号</div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge variant={observabilityOverview.scheduler_stale ? 'warning' : 'success'}>
              {observabilityOverview.scheduler_stale ? '调度结果陈旧' : '调度结果新鲜'}
            </Badge>
            <Badge variant={Number(observabilityOverview.active_count ?? 0) > 0 ? 'success' : 'warning'}>
              {Number(observabilityOverview.active_count ?? 0) > 0 ? 'active_pool 已形成' : 'active_pool 为空'}
            </Badge>
            <Badge variant={Number(observabilityOverview.champion_count ?? 0) > 0 ? 'info' : 'neutral'}>
              {Number(observabilityOverview.champion_count ?? 0) > 0 ? '已有 champion' : '尚无 champion'}
            </Badge>
          </div>
        </div>
      </div>

      {isPending ? (
        <LoadingState text="加载因子可观测性..." />
      ) : error ? (
        <ErrorState text={error} hint="BFF observability 聚合失败时，不影响下方手动操作链路。" />
      ) : hasData ? (
        <>
          <KpiGrid cols={6}>
            <KpiCard title="调度状态" value={String(observabilityScheduler.quality_status ?? '-')} />
            <KpiCard title="候选总量" value={String(observabilityOverview.candidate_count ?? '-')} />
            <KpiCard title="活跃池" value={String(observabilityOverview.active_count ?? '-')} />
            <KpiCard title="治理通过" value={String(observabilityOverview.governed_active_count ?? '-')} />
            <KpiCard title="研究记忆" value={String(observabilityMemoryStats.total_records ?? '-')} />
            <KpiCard
              title="Champion / Challenger"
              value={`${String(observabilityOverview.champion_count ?? 0)} / ${String(observabilityOverview.challenger_count ?? 0)}`}
            />
          </KpiGrid>

          <KpiGrid cols={6} className="mt-3">
            <KpiCard title="本轮生成" value={String(observabilityOverview.recent_generated_candidate_count ?? '-')} />
            <KpiCard title="本轮验证通过" value={String(observabilityOverview.recent_validated_candidate_count ?? '-')} />
            <KpiCard title="本轮验证失败" value={String(observabilityOverview.recent_validation_failed_count ?? '-')} />
            <KpiCard title="本轮 active_pool" value={String(observabilityOverview.recent_active_pool_count_after_run ?? '-')} />
            <KpiCard title="本轮 governed" value={String(observabilityOverview.recent_governed_active_count_after_run ?? '-')} />
            <KpiCard title="Retrain 计划" value={String(observabilityOverview.retrain_plan_count ?? '-')} />
          </KpiGrid>

          <div className="mt-3 flex flex-wrap gap-2">
            <BadgeValue value={!observabilityOverview.scheduler_stale} trueText="调度新鲜" falseText="调度待刷新" />
            <BadgeValue
              value={Number(observabilityOverview.active_count ?? 0) > 0}
              trueText="governed pool 可用"
              falseText="governed pool 待补"
            />
            <BadgeValue value={!degraded} trueText="聚合链路完整" falseText="聚合存在降级" />
            <Badge variant={Number(observabilityOverview.retrain_pending_count ?? 0) > 0 ? 'warning' : 'neutral'}>
              待执行 Retrain {String(observabilityOverview.retrain_pending_count ?? 0)}
            </Badge>
          </div>

          {observabilityErrors.length > 0 ? renderWarnings(observabilityErrors) : null}

          <div className={`${factorMiningPanelCls} mt-4`}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">Recent Auto Run</div>
            <div className="mt-3 grid gap-3 xl:grid-cols-2">
              <div className={factorMiningNoteCardCls}>
                <div className="font-medium text-text-primary">自动挖掘结果</div>
                <div className="mt-2 leading-6">
                  生成 {String(observabilityRecentValidation.generated_candidate_count ?? 0)} 个，验证通过{' '}
                  {String(observabilityRecentValidation.validated_candidate_count ?? 0)} 个，失败{' '}
                  {String(observabilityRecentValidation.validation_failed_count ?? 0)} 个。
                </div>
              </div>
              <div className={factorMiningNoteCardCls}>
                <div className="font-medium text-text-primary">运行后治理状态</div>
                <div className="mt-2 leading-6">
                  active_pool {String(observabilityRecentValidation.active_pool_count_after_run ?? 0)} 个，governed{' '}
                  {String(observabilityRecentValidation.governed_active_count_after_run ?? 0)} 个，registry refresh{' '}
                  {String(observabilityRecentValidation.registry_refresh_status ?? '-')}。
                </div>
              </div>
            </div>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            <div className={factorMiningPanelCls}>
              <h4 className="mb-2 text-sm font-medium text-text-primary">Registry 阶段分布</h4>
              {observabilityStageRows.length > 0 ? (
                <DataTable
                  rows={observabilityStageRows}
                  columns={[
                    { key: 'registry_stage', label: '阶段' },
                    { key: 'count', label: '数量', align: 'right' },
                  ]}
                />
              ) : (
                <EmptyState text="暂无 registry 阶段统计" />
              )}
            </div>

            <div className={factorMiningPanelCls}>
              <h4 className="mb-2 text-sm font-medium text-text-primary">活跃池家族</h4>
              {observabilityFamilyRows.length > 0 ? (
                <DataTable
                  rows={observabilityFamilyRows}
                  columns={[
                    { key: 'family', label: '家族' },
                    { key: 'count', label: '候选数', align: 'right' },
                    { key: 'promote_count', label: 'promote', align: 'right' },
                    { key: 'avg_total_score', label: '平均分', align: 'right', render: (value) => fmtNum(value, 3) },
                  ]}
                />
              ) : (
                <EmptyState text="active_pool 还没有可展示的家族分布" />
              )}
            </div>

            <div className={factorMiningPanelCls}>
              <h4 className="mb-2 text-sm font-medium text-text-primary">Regime 分布</h4>
              {observabilityRegimeRows.length > 0 ? (
                <DataTable
                  rows={observabilityRegimeRows}
                  columns={[
                    { key: 'regime', label: 'Regime' },
                    { key: 'count', label: '数量', align: 'right' },
                  ]}
                />
              ) : (
                <EmptyState text="当前没有 regime 分布统计" />
              )}
            </div>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <div className={factorMiningPanelCls}>
              <h4 className="mb-2 text-sm font-medium text-text-primary">排除原因</h4>
              {observabilityExclusionRows.length > 0 ? (
                <DataTable
                  rows={observabilityExclusionRows}
                  columns={[
                    { key: 'reason', label: '原因' },
                    { key: 'count', label: '数量', align: 'right' },
                  ]}
                />
              ) : (
                <EmptyState text="当前没有排除原因统计" />
              )}
            </div>

            <div className={factorMiningPanelCls}>
              <h4 className="mb-2 text-sm font-medium text-text-primary">Retrain 队列</h4>
              {observabilityRetrainQueue.length > 0 ? (
                <DataTable
                  rows={observabilityRetrainQueue}
                  columns={[
                    { key: 'family', label: '家族' },
                    { key: 'status', label: '状态' },
                    { key: 'priority', label: '优先级' },
                    { key: 'target_model_count', label: '目标模型', align: 'right' },
                    { key: 'reason_codes', label: '原因', render: (value) => joinList(value) },
                  ]}
                />
              ) : (
                <EmptyState text="当前没有 retrain 计划队列" />
              )}
              <div className="mt-3 text-xs text-text-secondary">
                队列总数 {String(observabilityRetrainSummary.count ?? 0)}，状态分布{' '}
                {joinList(
                  Object.entries(isRecord(observabilityRetrainSummary.status_counts) ? observabilityRetrainSummary.status_counts : {}).map(
                    ([status, count]) => `${status}:${count}`,
                  ),
                )}
              </div>
            </div>
          </div>
        </>
      ) : (
        <EmptyState text="可观测性聚合尚未返回数据" />
      )}
    </SectionCard>
  );
}
