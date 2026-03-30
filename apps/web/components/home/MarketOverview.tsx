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
  mounted,
  dateStr,
  lastUpdated,
  fgValue,
  luStats,
  latestNorth,
  fmtAmount,
}: Pick<
  MarketOverviewProps,
  'mounted' | 'dateStr' | 'lastUpdated' | 'fgValue' | 'luStats' | 'latestNorth' | 'fmtAmount'
>) {
  const marketOpen = mounted ? isTradingHours() : false;
  const lastUpdatedLabel = mounted && lastUpdated ? lastUpdated.toLocaleTimeString('zh-CN') : null;
  return (
    <section className="panel-soft rounded-[32px] p-4 sm:p-5">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div>
          <div className="eyebrow">Market Pulse</div>
          <h3 className="mb-0 mt-2 text-[1.4rem] font-semibold tracking-[-0.03em] text-text-primary">
            交易状态、情绪与增量资金
          </h3>
          <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
            这一段负责给首页市场区定调。它不再单独做成第二个
            hero，而是作为总览工作流的第一块内容，先说明市场是否开盘、情绪温度和最近一次可靠刷新时点。
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="action-chip text-sm text-text-primary">
              <span
                className={`inline-flex h-2.5 w-2.5 rounded-full ${marketOpen ? 'bg-success animate-pulse' : 'bg-text-muted'}`}
              />
              {marketOpen ? '交易中' : '已休市'}
            </span>
            <span className="action-chip text-sm text-text-primary">{mounted ? dateStr : '等待时间同步'}</span>
            {lastUpdatedLabel ? (
              <span className="action-chip text-sm text-text-primary">最近更新 {lastUpdatedLabel}</span>
            ) : null}
            <Link href="/fund-flow" className="action-chip text-sm no-underline text-inherit">
              去资金流
            </Link>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
          <div className="rounded-[24px] border border-white/50 bg-white/35 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">情绪温度</div>
            <div
              className={`mt-3 text-xl font-semibold ${fgValue > 60 ? 'text-success' : fgValue < 40 ? 'text-danger' : 'text-text-primary'}`}
            >
              恐贪 {fgValue.toFixed(0)}
            </div>
            <div className="mt-1 text-xs text-text-secondary">帮助判断今天更偏趋势还是防守</div>
          </div>
          <div className="rounded-[24px] border border-white/50 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.62)]">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">涨停数量</div>
            <div className="mt-3 text-xl font-semibold text-text-primary">
              {String(luStats.totalLimitUp ?? luStats.total ?? luStats.count ?? '-')}
            </div>
            <div className="mt-1 text-xs text-text-secondary">用于判断情绪扩散和题材热度</div>
          </div>
          <div className="rounded-[24px] border border-white/50 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.56)]">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">北向资金</div>
            <div
              className={`mt-3 text-xl font-semibold ${Number(latestNorth?.total ?? latestNorth?.netInflow ?? 0) >= 0 ? 'text-success' : 'text-danger'}`}
            >
              {fmtAmount(latestNorth?.total ?? latestNorth?.netInflow)}
            </div>
            <div className="mt-1 text-xs text-text-secondary">帮助判断外资增量方向</div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Multi-Index Quotes                                                  */
/* ------------------------------------------------------------------ */

function MultiIndexQuotes({
  dashboardVisibility,
  idxQ,
  validIndices,
  INDEX_CODES,
}: Pick<MarketOverviewProps, 'dashboardVisibility' | 'idxQ' | 'validIndices' | 'INDEX_CODES'>) {
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
              <Link
                key={i}
                href={`/market?tab=index&indexCode=${encodeURIComponent(String(q.code ?? INDEX_CODES[i]))}`}
                className="no-underline text-inherit"
              >
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
        <KpiGrid cols={4}>
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </KpiGrid>
      ) : !idxQ.error ? (
        <EmptyState
          text="主要指数暂时没有可用行情"
          hint="如果是开盘前或收盘后出现空态属正常现象；也可以前往市场页查看更完整的行情面板。"
          action={
            <Link
              href="/market"
              className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline"
            >
              打开市场看板
            </Link>
          }
        />
      ) : null}
    </SectionCard>
  );
}

/* ------------------------------------------------------------------ */
/* Sector Heatmap                                                      */
/* ------------------------------------------------------------------ */

function SectorHeatmap({
  dashboardVisibility,
  sectorQ,
  sectors,
}: Pick<MarketOverviewProps, 'dashboardVisibility' | 'sectorQ' | 'sectors'>) {
  if (!dashboardVisibility['market']) return null;
  return (
    <SectionCard className="min-h-[220px]">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <div className="eyebrow">轮动观察</div>
          <h2 className="mt-2">板块热力</h2>
        </div>
        <Link href="/market?tab=blocks" className="text-sm text-primary no-underline">
          查看全部
        </Link>
      </div>
      {sectorQ.error ? <ErrorState text={sectorQ.error} onRetry={() => sectorQ.refetch()} /> : null}
      {sectors.length > 0 ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
          {sectors.map((s, i) => {
            const chg = Number(s.avgChange ?? s.avg_change ?? s.change_pct ?? 0);
            return (
              <Link
                key={i}
                href={`/market?tab=blocks&block=${encodeURIComponent(String(s.code ?? s.block_code ?? ''))}`}
                className={`metric-tile glass-hover p-3 text-left text-xs no-underline text-inherit ${chg >= 0 ? 'border-success/20' : 'border-danger/20'}`}
                aria-label={`${String(s.name ?? '')} ${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%`}
              >
                <div className="truncate font-medium text-text-primary">{String(s.name ?? '').slice(0, 8)}</div>
                <div className="mt-2 flex items-center justify-between gap-2">
                  <span className="text-[11px] text-text-secondary">平均涨幅</span>
                  <span className={`text-sm font-semibold ${chg >= 0 ? 'text-success' : 'text-danger'}`}>
                    {chg >= 0 ? '+' : ''}
                    {chg.toFixed(2)}%
                  </span>
                </div>
              </Link>
            );
          })}
        </div>
      ) : sectorQ.isPending ? (
        <div className="grid grid-cols-4 sm:grid-cols-5 gap-2">
          {Array.from({ length: 20 }).map((_, i) => (
            <Skeleton key={i} height={52} />
          ))}
        </div>
      ) : !sectorQ.error ? (
        <EmptyState
          text="当前没有板块热力数据"
          hint="非交易时段或数据源波动时可能为空，稍后刷新通常会恢复。"
          action={
            <Link
              href="/market?tab=blocks"
              className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline"
            >
              查看板块页
            </Link>
          }
        />
      ) : null}
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
      <SectorHeatmap dashboardVisibility={props.dashboardVisibility} sectorQ={props.sectorQ} sectors={props.sectors} />
    </>
  );
}
