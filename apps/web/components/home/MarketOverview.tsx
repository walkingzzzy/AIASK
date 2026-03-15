'use client';

import { SectionCard, KpiCard, KpiGrid, Skeleton, SkeletonCard } from '@/components/ui';
import { ErrorState, EmptyState } from '@/components/status-state';
import { fmtNum } from '@/lib/data-utils';
import { isTradingHours } from '@/lib/trading-hours';
import Link from 'next/link';
import type { DashboardQuoteSnapshot } from '@aiask/shared-types';

/* ------------------------------------------------------------------ */
/* Props                                                               */
/* ------------------------------------------------------------------ */

export interface MarketOverviewProps {
  mounted: boolean;
  dateStr: string;
  lastUpdated: Date | null;
  fgValue: number;
  luStats: Record<string, unknown>;
  latestNorth: Record<string, unknown> | null;
  fmtAmount: (v: unknown) => string;

  /* Multi-index quotes */
  dashboardVisibility: Record<string, boolean>;
  idxQ: { error: string | null; isPending: boolean; data: unknown; refetch: () => void };
  validIndices: DashboardQuoteSnapshot[];
  INDEX_CODES: readonly string[];

  /* Sector heatmap */
  sectorQ: { error: string | null; isPending: boolean; data: unknown; refetch: () => void };
  sectors: Record<string, unknown>[];
}

/* ------------------------------------------------------------------ */
/* Market Pulse Bar                                                    */
/* ------------------------------------------------------------------ */

function MarketPulse({
  mounted, dateStr, lastUpdated, fgValue, luStats, latestNorth, fmtAmount,
}: Pick<MarketOverviewProps, 'mounted' | 'dateStr' | 'lastUpdated' | 'fgValue' | 'luStats' | 'latestNorth' | 'fmtAmount'>) {
  const marketOpen = mounted ? isTradingHours() : false;
  const lastUpdatedLabel = mounted && lastUpdated ? lastUpdated.toLocaleTimeString('zh-CN') : null;
  return (
    <div className="glass rounded-xl p-4 mb-4 flex items-center justify-between flex-wrap gap-3">
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${marketOpen ? 'bg-success animate-pulse' : 'bg-text-muted'}`} />
        <span className="text-sm font-medium">{marketOpen ? '交易中' : '已休市'}</span>
        <span className="text-xs text-text-muted">{mounted ? dateStr : ''}</span>
      </div>
      <div className="flex items-center gap-4 text-xs text-text-secondary">
        {lastUpdatedLabel ? <span>更新: {lastUpdatedLabel}</span> : null}
        <span>恐贪: <span className={fgValue > 60 ? 'text-danger font-medium' : fgValue < 40 ? 'text-success font-medium' : 'font-medium'}>{fgValue.toFixed(0)}</span></span>
        <span>涨停: <span className="font-medium">{String(luStats.totalLimitUp ?? luStats.total ?? luStats.count ?? '-')}</span></span>
        <span>北向: <span className={Number(latestNorth?.total ?? latestNorth?.netInflow ?? 0) >= 0 ? 'text-danger font-medium' : 'text-success font-medium'}>{fmtAmount(latestNorth?.total ?? latestNorth?.netInflow)}</span></span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Multi-Index Quotes                                                  */
/* ------------------------------------------------------------------ */

function MultiIndexQuotes({ dashboardVisibility, idxQ, validIndices, INDEX_CODES }: Pick<MarketOverviewProps, 'dashboardVisibility' | 'idxQ' | 'validIndices' | 'INDEX_CODES'>) {
  if (!dashboardVisibility['market']) return null;
  return (
    <SectionCard className="p-4">
      <h3 className="mt-0">主要指数</h3>
      {idxQ.error ? <ErrorState text={idxQ.error} onRetry={() => idxQ.refetch()} /> : null}
      {validIndices.length > 0 ? (
        <KpiGrid cols={4}>
          {validIndices.map((q, i) => {
            const chg = Number(q.changePercent ?? q.change_pct ?? 0);
            const chgAmt = Number(q.change ?? 0);
            return (
              <Link key={i} href={`/market?tab=index&indexCode=${encodeURIComponent(String(q.code ?? INDEX_CODES[i]))}`} className="no-underline text-inherit">
                <KpiCard
                  title={String(q.name ?? q.code ?? `指数${i + 1}`)}
                  value={fmtNum(q.price, 2)}
                  suffix={chgAmt ? ' ' + (chgAmt > 0 ? '+' : '') + fmtNum(chgAmt, 2) : undefined}
                  change={chg}
                  changeType="percent"
                />
              </Link>
            );
          })}
        </KpiGrid>
      ) : idxQ.isPending ? (
        <KpiGrid cols={4}><SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard /></KpiGrid>
      ) : !idxQ.error ? (
        <EmptyState text="主要指数暂时没有可用行情" hint="如果是开盘前或收盘后出现空态属正常现象；也可以前往市场页查看更完整的行情面板。" action={<Link href="/market" className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline">打开市场看板</Link>} />
      ) : null}
    </SectionCard>
  );
}

/* ------------------------------------------------------------------ */
/* Sector Heatmap                                                      */
/* ------------------------------------------------------------------ */

function SectorHeatmap({ dashboardVisibility, sectorQ, sectors }: Pick<MarketOverviewProps, 'dashboardVisibility' | 'sectorQ' | 'sectors'>) {
  if (!dashboardVisibility['market']) return null;
  return (
    <SectionCard className="p-4 mt-4">
      <h3 className="mt-0">板块热力</h3>
      {sectorQ.error ? <ErrorState text={sectorQ.error} onRetry={() => sectorQ.refetch()} /> : null}
      {sectors.length > 0 ? (
        <div className="grid grid-cols-4 sm:grid-cols-5 gap-2">
          {sectors.map((s, i) => {
            const chg = Number(s.avgChange ?? s.avg_change ?? s.change_pct ?? 0);
            return (
              <Link key={i} href={`/market?tab=blocks&block=${encodeURIComponent(String(s.code ?? s.block_code ?? ''))}`}
                className={`glass rounded-lg p-2 text-center text-xs no-underline text-inherit ${chg >= 0 ? 'border border-danger/30' : 'border border-success/30'} transition-transform hover:scale-105`}
                aria-label={`${String(s.name ?? '')} ${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%`}>
                <div className="truncate font-medium">{String(s.name ?? '').slice(0, 6)}</div>
                <div className={`text-sm font-bold ${chg >= 0 ? 'text-danger' : 'text-success'}`}>{chg >= 0 ? '+' : ''}{chg.toFixed(2)}%</div>
              </Link>
            );
          })}
        </div>
      ) : sectorQ.isPending ? (
        <div className="grid grid-cols-4 sm:grid-cols-5 gap-2">
          {Array.from({ length: 20 }).map((_, i) => <Skeleton key={i} height={52} />)}
        </div>
      ) : !sectorQ.error ? <EmptyState text="当前没有板块热力数据" hint="非交易时段或数据源波动时可能为空，稍后刷新通常会恢复。" action={<Link href="/market?tab=blocks" className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline">查看板块页</Link>} /> : null}
    </SectionCard>
  );
}

/* ------------------------------------------------------------------ */
/* Composed export                                                     */
/* ------------------------------------------------------------------ */

export function MarketOverview(props: MarketOverviewProps) {
  return (
    <>
      <MarketPulse
        mounted={props.mounted}
        dateStr={props.dateStr}
        lastUpdated={props.lastUpdated}
        fgValue={props.fgValue}
        luStats={props.luStats}
        latestNorth={props.latestNorth}
        fmtAmount={props.fmtAmount}
      />
      <MultiIndexQuotes
        dashboardVisibility={props.dashboardVisibility}
        idxQ={props.idxQ}
        validIndices={props.validIndices}
        INDEX_CODES={props.INDEX_CODES}
      />
      <SectorHeatmap
        dashboardVisibility={props.dashboardVisibility}
        sectorQ={props.sectorQ}
        sectors={props.sectors}
      />
    </>
  );
}
