'use client';

import { SectionCard, KpiCard, KpiGrid, Skeleton, SkeletonCard } from '@/components/ui';
import { GaugeChart, BarChart, COLORS } from '@/components/charts';
import { DataQualityBanner, ErrorState, EmptyState } from '@/components/status-state';
import { fmtPct } from '@/lib/data-utils';
import type { DataTrust } from '@/lib/api';
import Link from 'next/link';

/* ------------------------------------------------------------------ */
/* Props                                                               */
/* ------------------------------------------------------------------ */

export interface FundFlowSectionProps {
  dashboardVisibility: Record<string, boolean>;
  fmtAmount: (v: unknown) => string;

  /* Fear-Greed */
  fearGreedQ: { error: string | null; isPending: boolean; data: unknown; trust?: DataTrust; refetch: () => void };
  fgValue: number | null;
  fgLabel: string;

  /* Sector fund flow */
  sectorFlowQ: { error: string | null; isPending: boolean; data: unknown; trust?: DataTrust; refetch: () => void };
  sectorFlows: Array<{ label: string; value: number }>;

  /* Limit-Up */
  limitUpQ: { error: string | null; isPending: boolean; data: unknown; trust?: DataTrust; refetch: () => void };
  luStats: Record<string, unknown>;

  /* North fund */
  northQ: { error: string | null; isPending: boolean; data: unknown; trust?: DataTrust; refetch: () => void };
  latestNorth: Record<string, unknown> | null;
  northFlows: Record<string, unknown>[];
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export function FundFlowSection(props: FundFlowSectionProps) {
  const { dashboardVisibility, fmtAmount, fearGreedQ, fgValue, fgLabel, sectorFlowQ, sectorFlows, limitUpQ, luStats, northQ, latestNorth, northFlows } = props;
  const fearGreedUnavailable = Boolean(fearGreedQ.trust?.degraded);
  const sectorFlowUnavailable = Boolean(sectorFlowQ.trust?.degraded);
  const limitUpUnavailable = Boolean(limitUpQ.trust?.degraded);
  const northUnavailable = Boolean(northQ.trust?.degraded);
  const hasLimitUpStats = [luStats.totalLimitUp, luStats.total, luStats.count, luStats.firstBoard, luStats.first_board, luStats.successRate, luStats.success_rate]
    .some((value) => value != null && value !== '');

  return (
    <>
      {/* Fear-Greed + Sector Fund Flow side by side */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
        {dashboardVisibility['sentiment'] && (
          <SectionCard className="p-4">
            <h3 className="mt-0">恐贪指数</h3>
            {fearGreedQ.error ? <ErrorState text={fearGreedQ.error} onRetry={() => fearGreedQ.refetch()} /> : null}
            <DataQualityBanner trust={fearGreedQ.trust} title="恐贪指数数据质量" onRetry={() => void fearGreedQ.refetch()} className="mb-3" />
            {fearGreedQ.data != null && !fearGreedUnavailable && fgValue != null ? (
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
            ) : fearGreedQ.isPending ? <Skeleton height={200} /> : !fearGreedQ.error ? <EmptyState text={fearGreedUnavailable ? '恐贪指数数据不可用' : '当前没有恐贪指数'} hint={fearGreedUnavailable ? '页面已停止把降级占位值当作真实情绪展示。' : '情绪源在非交易时段偶尔会为空，稍后刷新即可。'} action={<Link href="/sentiment" className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline">打开情绪页</Link>} /> : null}
          </SectionCard>
        )}

        {dashboardVisibility['fund-flow'] && (
          <SectionCard className="p-4">
            <h3 className="mt-0">板块资金流向</h3>
            {sectorFlowQ.error ? <ErrorState text={sectorFlowQ.error} onRetry={() => sectorFlowQ.refetch()} /> : null}
            <DataQualityBanner trust={sectorFlowQ.trust} title="板块资金流数据质量" onRetry={() => void sectorFlowQ.refetch()} className="mb-3" />
            {sectorFlows.length > 0 && !sectorFlowUnavailable ? (
              <BarChart items={sectorFlows} height={200} yAxisName="净流入(亿)" colorByValue horizontal />
            ) : sectorFlowQ.isPending ? <Skeleton height={200} /> : !sectorFlowQ.error ? <EmptyState text={sectorFlowUnavailable ? '板块资金流数据不可用' : '当前没有板块资金流向榜单'} hint={sectorFlowUnavailable ? '上游未返回可验证资金流，页面不再展示默认空榜作为正常结果。' : '适合在交易时段查看热点轮动；若现在为空，可稍后刷新或直接进入资金流页。'} action={<Link href="/fund-flow" className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline">打开资金流页</Link>} /> : null}
          </SectionCard>
        )}
      </div>

      {/* Limit-Up Stats + North Fund side by side */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
        {dashboardVisibility['market'] && (
          <SectionCard className="p-4">
            <h3 className="mt-0">涨停统计</h3>
            {limitUpQ.error ? <ErrorState text={limitUpQ.error} onRetry={() => limitUpQ.refetch()} /> : null}
            <DataQualityBanner trust={limitUpQ.trust} title="涨停统计数据质量" onRetry={() => void limitUpQ.refetch()} className="mb-3" />
            {limitUpQ.data && hasLimitUpStats && !limitUpUnavailable ? (
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
            ) : !limitUpQ.error ? <EmptyState text={limitUpUnavailable ? '涨停统计数据不可用' : '当前没有涨停统计数据'} hint={limitUpUnavailable ? '上游没有返回可验证涨停统计，页面不再把空值解释为盘前/盘后正常。' : '开盘前、收盘后或节假日出现空态都比较常见。'} action={<Link href="/market?tab=limitup" className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline">查看涨停页</Link>} /> : null}
          </SectionCard>
        )}

        {dashboardVisibility['fund-flow'] && (
          <SectionCard className="p-4">
            <h3 className="mt-0">北向资金</h3>
            {northQ.error ? <ErrorState text={northQ.error} onRetry={() => northQ.refetch()} /> : null}
            <DataQualityBanner trust={northQ.trust} title="北向资金数据质量" onRetry={() => void northQ.refetch()} className="mb-3" />
            {latestNorth && !northUnavailable ? (
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
            ) : !northQ.error ? <EmptyState text={northUnavailable ? '北向资金数据不可用' : '当前没有北向资金数据'} hint={northUnavailable ? '上游未返回可验证北向资金，页面不再把空值当作正常资金流。' : '北向资金在非交易时段常常为空，交易时段或收盘后通常会恢复。'} action={<Link href="/fund-flow?tab=north" className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline">查看北向页</Link>} /> : null}
          </SectionCard>
        )}
      </div>

      {/* North Fund Trend */}
      {dashboardVisibility['fund-flow'] && (
        <SectionCard className="p-4 mt-4">
          <h3 className="mt-0">北向资金走势（近20日）</h3>
          {northFlows.length > 1 && !northUnavailable ? (
            <BarChart
              items={northFlows.slice(-20).map((x) => ({
                label: String(x.date ?? '').slice(5),
                value: Number(x.total ?? x.netInflow ?? x.net_inflow ?? 0) / 1e8,
              }))}
              height={240} yAxisName="净流入(亿)" colorByValue
            />
          ) : northQ.isPending ? <Skeleton height={240} /> : <EmptyState text={northUnavailable ? '北向资金走势不可用' : '当前没有北向资金走势'} hint={northUnavailable ? '上游北向资金链路当前不可用，无法确认近 20 日净流入节奏。' : '如果你在做盘后复盘，可以稍后再回来确认近 20 日净流入节奏。'} action={<Link href="/fund-flow?tab=north" className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline">打开资金流页</Link>} />}
        </SectionCard>
      )}
    </>
  );
}
