'use client';

import { SectionCard, KpiCard, KpiGrid, Skeleton, SkeletonCard } from '@/components/ui';
import { GaugeChart, BarChart, COLORS } from '@/components/charts';
import { ErrorState, EmptyState } from '@/components/status-state';
import { fmtPct } from '@/lib/data-utils';

/* ------------------------------------------------------------------ */
/* Props                                                               */
/* ------------------------------------------------------------------ */

export interface FundFlowSectionProps {
  dashboardVisibility: Record<string, boolean>;
  fmtAmount: (v: unknown) => string;

  /* Fear-Greed */
  fearGreedQ: { error: string | null; isPending: boolean; data: unknown; refetch: () => void };
  fgValue: number;
  fgLabel: string;

  /* Sector fund flow */
  sectorFlowQ: { error: string | null; isPending: boolean; data: unknown; refetch: () => void };
  sectorFlows: Array<{ label: string; value: number }>;

  /* Limit-Up */
  limitUpQ: { error: string | null; isPending: boolean; data: unknown; refetch: () => void };
  luStats: Record<string, unknown>;

  /* North fund */
  northQ: { error: string | null; isPending: boolean; data: unknown; refetch: () => void };
  latestNorth: Record<string, unknown> | null;
  northFlows: Record<string, unknown>[];
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export function FundFlowSection(props: FundFlowSectionProps) {
  const { dashboardVisibility, fmtAmount, fearGreedQ, fgValue, fgLabel, sectorFlowQ, sectorFlows, limitUpQ, luStats, northQ, latestNorth, northFlows } = props;

  return (
    <>
      {/* Fear-Greed + Sector Fund Flow side by side */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
        {dashboardVisibility['sentiment'] && (
          <SectionCard className="p-4">
            <h3 className="mt-0">恐贪指数</h3>
            {fearGreedQ.error ? <ErrorState text={fearGreedQ.error} onRetry={() => fearGreedQ.refetch()} /> : null}
            {fearGreedQ.data != null ? (
              <GaugeChart
                value={fgValue} min={0} max={100} title={fgLabel} height={200}
                zones={[
                  { start: 0, end: 25, color: COLORS.down },
                  { start: 25, end: 40, color: COLORS.warning },
                  { start: 40, end: 60, color: '#94a3b8' },
                  { start: 60, end: 75, color: '#f97316' },
                  { start: 75, end: 100, color: COLORS.up },
                ]}
              />
            ) : fearGreedQ.isPending ? <Skeleton height={200} /> : !fearGreedQ.error ? <EmptyState text="暂无恐贪数据" /> : null}
          </SectionCard>
        )}

        {dashboardVisibility['fund-flow'] && (
          <SectionCard className="p-4">
            <h3 className="mt-0">板块资金流向</h3>
            {sectorFlowQ.error ? <ErrorState text={sectorFlowQ.error} onRetry={() => sectorFlowQ.refetch()} /> : null}
            {sectorFlows.length > 0 ? (
              <BarChart items={sectorFlows} height={200} yAxisName="净流入(亿)" colorByValue horizontal />
            ) : sectorFlowQ.isPending ? <Skeleton height={200} /> : !sectorFlowQ.error ? <EmptyState text="暂无板块资金流向" /> : null}
          </SectionCard>
        )}
      </div>

      {/* Limit-Up Stats + North Fund side by side */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
        {dashboardVisibility['market'] && (
          <SectionCard className="p-4">
            <h3 className="mt-0">涨停统计</h3>
            {limitUpQ.error ? <ErrorState text={limitUpQ.error} onRetry={() => limitUpQ.refetch()} /> : null}
            {limitUpQ.data ? (
              <>
                <KpiGrid cols={3}>
                  <KpiCard title="涨停家数" value={String(luStats.totalLimitUp ?? luStats.total ?? luStats.count ?? '-')} />
                  <KpiCard title="首板" value={String(luStats.firstBoard ?? luStats.first_board ?? '-')} />
                  <KpiCard title="连板成功率" value={fmtPct(luStats.successRate ?? luStats.success_rate)} />
                </KpiGrid>
                {Number(luStats.totalLimitUp ?? luStats.total ?? luStats.count ?? 0) === 0 && (
                  <p className="text-text-muted text-xs mt-2">盘前/盘后数据为零属正常现象</p>
                )}
              </>
            ) : limitUpQ.isPending ? (
              <KpiGrid cols={3}><SkeletonCard /><SkeletonCard /><SkeletonCard /></KpiGrid>
            ) : !limitUpQ.error ? <EmptyState text="暂无涨停统计数据" /> : null}
          </SectionCard>
        )}

        {dashboardVisibility['fund-flow'] && (
          <SectionCard className="p-4">
            <h3 className="mt-0">北向资金</h3>
            {northQ.error ? <ErrorState text={northQ.error} onRetry={() => northQ.refetch()} /> : null}
            {latestNorth ? (
              <KpiGrid cols={2}>
                <KpiCard
                  title="今日净流入"
                  value={fmtAmount(latestNorth.total ?? latestNorth.netInflow ?? latestNorth.net_inflow)}
                  change={Number(latestNorth.total ?? latestNorth.netInflow ?? latestNorth.net_inflow ?? null)}
                  changeType="absolute"
                />
                <KpiCard title="累计净流入" value={fmtAmount(latestNorth.cumulative ?? latestNorth.cumNetInflow ?? latestNorth.cum_net_inflow)} />
              </KpiGrid>
            ) : northQ.isPending ? (
              <KpiGrid cols={2}><SkeletonCard /><SkeletonCard /></KpiGrid>
            ) : !northQ.error ? <EmptyState text="暂无北向资金数据（非交易时段）" /> : null}
          </SectionCard>
        )}
      </div>

      {/* North Fund Trend */}
      {dashboardVisibility['fund-flow'] && (
        <SectionCard className="p-4 mt-4">
          <h3 className="mt-0">北向资金走势（近20日）</h3>
          {northFlows.length > 1 ? (
            <BarChart
              items={northFlows.slice(-20).map((x) => ({
                label: String(x.date ?? '').slice(5),
                value: Number(x.total ?? x.netInflow ?? x.net_inflow ?? 0) / 1e8,
              }))}
              height={240} yAxisName="净流入(亿)" colorByValue
            />
          ) : northQ.isPending ? <Skeleton height={240} /> : <EmptyState text="暂无北向资金走势（非交易时段）" />}
        </SectionCard>
      )}
    </>
  );
}
