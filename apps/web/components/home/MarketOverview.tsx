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
    <section className="mt-4 rounded-[24px] border border-border bg-surface p-5 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="eyebrow">市场脉搏</div>
          <div className="mt-3 flex items-center gap-3">
            <span className={`inline-flex h-3 w-3 rounded-full ${marketOpen ? 'bg-success animate-pulse' : 'bg-text-muted'}`} />
            <div className="text-xl font-semibold text-text-primary">{marketOpen ? '交易中' : '已休市'}</div>
          </div>
          <div className="mt-2 text-sm text-text-secondary">
            {mounted ? dateStr : ''}
            {lastUpdatedLabel ? ` · 最近更新 ${lastUpdatedLabel}` : ''}
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-3 lg:min-w-[540px]">
          <div className="rounded-[18px] border border-border bg-surface-alt/72 px-4 py-3">
            <div className="metric-label">情绪温度</div>
            <div className={`mt-2 text-lg font-semibold ${fgValue > 60 ? 'text-success' : fgValue < 40 ? 'text-danger' : 'text-text-primary'}`}>
              恐贪 {fgValue.toFixed(0)}
            </div>
          </div>
          <div className="rounded-[18px] border border-border bg-surface-alt/72 px-4 py-3">
            <div className="metric-label">涨停数量</div>
            <div className="mt-2 text-lg font-semibold text-text-primary">{String(luStats.totalLimitUp ?? luStats.total ?? luStats.count ?? '-')}</div>
          </div>
          <div className="rounded-[18px] border border-border bg-surface-alt/72 px-4 py-3">
            <div className="metric-label">北向资金</div>
            <div className={`mt-2 text-lg font-semibold ${Number(latestNorth?.total ?? latestNorth?.netInflow ?? 0) >= 0 ? 'text-success' : 'text-danger'}`}>
              {fmtAmount(latestNorth?.total ?? latestNorth?.netInflow)}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Multi-Index Quotes                                                  */
/* ------------------------------------------------------------------ */

function MultiIndexQuotes({ dashboardVisibility, idxQ, validIndices, INDEX_CODES }: Pick<MarketOverviewProps, 'dashboardVisibility' | 'idxQ' | 'validIndices' | 'INDEX_CODES'>) {
  if (!dashboardVisibility['market']) return null;
  return (
    <SectionCard className="min-h-[220px]">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <div className="eyebrow">市场基线</div>
          <h2 className="mt-2">主要指数</h2>
        </div>
      </div>
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
    <SectionCard className="min-h-[220px]">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <div className="eyebrow">轮动观察</div>
          <h2 className="mt-2">板块热力</h2>
        </div>
        <Link href="/market?tab=blocks" className="text-sm text-primary no-underline">查看全部</Link>
      </div>
      {sectorQ.error ? <ErrorState text={sectorQ.error} onRetry={() => sectorQ.refetch()} /> : null}
      {sectors.length > 0 ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
          {sectors.map((s, i) => {
            const chg = Number(s.avgChange ?? s.avg_change ?? s.change_pct ?? 0);
            return (
              <Link key={i} href={`/market?tab=blocks&block=${encodeURIComponent(String(s.code ?? s.block_code ?? ''))}`}
                className={`rounded-[18px] border p-3 text-left text-xs no-underline text-inherit shadow-sm transition-transform hover:-translate-y-0.5 ${chg >= 0 ? 'border-success/20 bg-success/8' : 'border-danger/20 bg-danger/8'}`}
                aria-label={`${String(s.name ?? '')} ${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%`}>
                <div className="truncate font-medium text-text-primary">{String(s.name ?? '').slice(0, 8)}</div>
                <div className="mt-2 flex items-center justify-between gap-2">
                  <span className="text-[11px] text-text-secondary">平均涨幅</span>
                  <span className={`text-sm font-semibold ${chg >= 0 ? 'text-success' : 'text-danger'}`}>{chg >= 0 ? '+' : ''}{chg.toFixed(2)}%</span>
                </div>
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
