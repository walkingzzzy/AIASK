'use client';

import { SectionCard, KpiCard, KpiGrid, Skeleton, QuickAction, QuickActionGrid } from '@/components/ui';
import { EmptyState } from '@/components/status-state';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { fmtNum, fmtPct, fmtAmount } from '@/lib/data-utils';
import Link from 'next/link';
import type {
  AlertItem,
  DashboardMarketNewsItem,
  DashboardQuickAction,
  DashboardQuoteSnapshot,
  DashboardRecentStock,
  DashboardWatchlistItem,
  PaperTradingAccount,
  PaperTradingPosition,
  PaperTradingSummary,
} from '@aiask/shared-types';

/* ------------------------------------------------------------------ */
/* Props                                                               */
/* ------------------------------------------------------------------ */

export interface PersonalDashboardProps {
  /* Personal overview */
  nickname: string;
  paperSummary: PaperTradingSummary;
  paperAccount: PaperTradingAccount;
  paperPositions: PaperTradingPosition[];
  activeAlerts: AlertItem[];

  /* Watchlist & recent */
  watchlistItems: DashboardWatchlistItem[];
  recentStocks: DashboardRecentStock[];
  quoteMap: Map<string, DashboardQuoteSnapshot>;
  batchQIsFetching: boolean;
  mounted: boolean;

  /* Market news */
  marketNews: DashboardMarketNewsItem[];

  /* Quick actions */
  quickActions: DashboardQuickAction[];
}

/* ------------------------------------------------------------------ */
/* Personal Overview                                                   */
/* ------------------------------------------------------------------ */

function PersonalOverview({ nickname, paperSummary, paperAccount, paperPositions, activeAlerts }: Pick<PersonalDashboardProps, 'nickname' | 'paperSummary' | 'paperAccount' | 'paperPositions' | 'activeAlerts'>) {
  return (
    <>
      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_360px]">
        <div className="rounded-[28px] border border-border bg-surface p-5 shadow-sm">
          <div className="eyebrow">今日工作台</div>
          <h1 className="mt-3">欢迎回来，{nickname}</h1>
          <p className="page-lead mt-3 mb-0">首屏只保留今天最值得处理的信息：资产状态、待处理告警和下一步任务入口，减少空卡片和低优先级模块对注意力的争抢。</p>
        </div>
        <div className="rounded-[28px] border border-border bg-surface p-5 shadow-sm">
          <div className="eyebrow">今日焦点</div>
          <div className="mt-4 space-y-3 text-sm text-text-secondary">
            <div className="rounded-[18px] border border-border bg-surface-alt/72 px-4 py-3">
              <div className="metric-label">活跃告警</div>
              <div className="mt-2 text-lg font-semibold text-text-primary">{activeAlerts.length}</div>
              <div className="mt-1 text-xs">优先处理仍在触发中的策略和持仓提醒。</div>
            </div>
            <div className="rounded-[18px] border border-border bg-surface-alt/72 px-4 py-3">
              <div className="metric-label">在场资产</div>
              <div className="mt-2 text-lg font-semibold text-text-primary">{fmtAmount(paperSummary.total_value ?? paperAccount.total_value)}</div>
              <div className="mt-1 text-xs">如果没有持仓，建议先从看盘或模拟交易入口开始。</div>
            </div>
          </div>
        </div>
      </div>

      <div data-tour="dashboard">
        <SectionCard className="min-h-[180px]">
          <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
            <div>
              <div className="eyebrow">资产概览</div>
              <h2 className="mt-2">个人总览</h2>
            </div>
            <Link href="/paper-trading" className="text-sm text-primary no-underline">进入模拟盘</Link>
          </div>
          <KpiGrid cols={4}>
            <KpiCard title="总资产" value={fmtAmount(paperSummary.total_value ?? paperAccount.total_value)} />
            <KpiCard title="总收益率" value={fmtPct(paperSummary.total_return_pct ?? 0)} change={Number(paperSummary.total_return_pct ?? 0)} />
            <KpiCard title="持仓数" value={paperPositions.length} />
            <KpiCard title="活跃告警" value={activeAlerts.length} />
          </KpiGrid>
        </SectionCard>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* 3-column: watchlist / positions / news                              */
/* ------------------------------------------------------------------ */

function ThreeColumnCards({ watchlistItems, paperPositions, marketNews, quoteMap }: Pick<PersonalDashboardProps, 'watchlistItems' | 'paperPositions' | 'marketNews' | 'quoteMap'>) {
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
      {/* Watchlist */}
      <SectionCard className="min-h-[220px] xl:col-span-1">
        <div className="flex items-center justify-between mb-2">
          <div>
            <div className="eyebrow">重点标的</div>
            <h2 className="mt-2">自选股行情</h2>
          </div>
          <Link href="/watchlist" className="text-sm text-primary no-underline">更多</Link>
        </div>
        <div className="space-y-2">
          {watchlistItems.slice(0, 5).map((item) => {
            const q = quoteMap.get(item.code);
            const chg = Number(q?.changePercent ?? q?.change_pct ?? 0);
            return (
              <div key={item.code} className="flex items-center justify-between rounded-[16px] border border-border-light bg-surface-alt/50 px-3 py-2 text-sm">
                <StockLink code={item.code} name={item.name || item.code} />
                <span className={chg >= 0 ? 'text-danger text-xs' : 'text-success text-xs'}>
                  {q ? `${fmtNum(q.price, 2)} ${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%` : '--'}
                </span>
              </div>
            );
          })}
          {watchlistItems.length === 0 ? (
            <EmptyState
              text="还没有自选股"
              hint="可以先从市场看板或个股详情页添加关注标的，首页才会开始展示实时行情。"
              action={
                <>
                  <Link href="/market" className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline">去市场页</Link>
                  <Link href="/watchlist" className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">管理自选</Link>
                </>
              }
            />
          ) : null}
        </div>
      </SectionCard>

      {/* Positions */}
      <SectionCard className="min-h-[220px] xl:col-span-1">
        <div className="flex items-center justify-between mb-2">
          <div>
            <div className="eyebrow">持仓状态</div>
            <h2 className="mt-2">持仓概览</h2>
          </div>
          <Link href="/paper-trading" className="text-sm text-primary no-underline">更多</Link>
        </div>
        <div className="space-y-2">
          {paperPositions.slice(0, 5).map((item, i) => (
            <div key={String(item.stock_code ?? i)} className="flex items-center justify-between rounded-[16px] border border-border-light bg-surface-alt/50 px-3 py-2 text-sm">
              <StockLink code={String(item.stock_code ?? '')} name={String(item.stock_name ?? item.stock_code ?? '')} />
              <span className={Number(item.profit_rate ?? 0) >= 0 ? 'text-danger text-xs' : 'text-success text-xs'}>{fmtPct(item.profit_rate ?? 0)}</span>
            </div>
          ))}
          {paperPositions.length === 0 ? (
            <EmptyState
              text="模拟盘还没有持仓"
              hint="先创建账户或载入示例委托后，这里会显示持仓收益与盈亏变化。"
              action={<Link href="/paper-trading" className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline">去模拟盘建仓</Link>}
            />
          ) : null}
        </div>
      </SectionCard>

      {/* Market news */}
      <SectionCard className="min-h-[220px] xl:col-span-1">
        <div className="flex items-center justify-between mb-2">
          <div>
            <div className="eyebrow">信息提醒</div>
            <h2 className="mt-2">市场快讯</h2>
          </div>
          <Link href="/research" className="text-sm text-primary no-underline">更多</Link>
        </div>
        <div className="space-y-2">
          {marketNews.slice(0, 5).map((item, i) => (
            <div key={String(item.id ?? item.title ?? i)} className="rounded-[16px] border border-border-light bg-surface-alt/50 p-3 text-sm">
              <div className="font-medium line-clamp-2">{String(item.title ?? item.name ?? '未命名快讯')}</div>
              <div className="text-xs text-text-secondary mt-1">{String(item.publish_time ?? item.time ?? item.date ?? '-')}</div>
            </div>
          ))}
          {marketNews.length === 0 ? (
            <EmptyState
              text="当前没有市场快讯"
              hint="可以去研究页查看完整资讯源，或稍后返回首页等待快讯更新。"
              action={<Link href="/research" className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline">去研究页</Link>}
            />
          ) : null}
        </div>
      </SectionCard>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Watchlist + Recent Stocks (bottom section)                          */
/* ------------------------------------------------------------------ */

function WatchlistRecent({ mounted, watchlistItems, recentStocks, quoteMap, batchQIsFetching }: Pick<PersonalDashboardProps, 'mounted' | 'watchlistItems' | 'recentStocks' | 'quoteMap' | 'batchQIsFetching'>) {
  if (!mounted) {
    return (
      <div className="grid grid-cols-1 gap-4 mt-4 sm:grid-cols-2">
        {Array.from({ length: 2 }).map((_, index) => (
          <SectionCard key={`watchlist-recent-skeleton-${index}`} className="min-h-[220px] p-4">
            <div className="mb-3 flex items-center justify-between">
              <Skeleton width={120} height={20} />
              <Skeleton width={56} height={20} />
            </div>
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((__, itemIndex) => (
                <div key={`watchlist-recent-skeleton-row-${index}-${itemIndex}`} className="flex items-center justify-between border-b border-border/30 py-1.5">
                  <Skeleton width={110} height={16} />
                  <Skeleton width={72} height={16} />
                </div>
              ))}
            </div>
          </SectionCard>
        ))}
      </div>
    );
  }

  if (watchlistItems.length === 0 && recentStocks.length === 0) return null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
      {watchlistItems.length > 0 && (
        <SectionCard className="min-h-[220px] p-4">
          <h3 className="mt-0">我的自选 ({watchlistItems.length})</h3>
          <div className="space-y-1.5">
            {watchlistItems.slice(0, 8).map((item) => {
              const q = quoteMap.get(item.code);
              const chg = Number(q?.changePercent ?? q?.change_pct ?? 0);
              return (
                <div key={item.code} className="flex items-center justify-between text-sm py-1 border-b border-border/30">
                  <StockLink code={item.code} name={item.name || item.code} />
                  <div className="flex items-center gap-2">
                    {q ? <span className={`text-xs font-medium ${chg >= 0 ? 'text-danger' : 'text-success'}`}>{fmtNum(q.price, 2)} {chg >= 0 ? '+' : ''}{chg.toFixed(2)}%</span>
                      : batchQIsFetching ? <Skeleton width={80} height={16} /> : null}
                    <WatchlistButton code={item.code} name={item.name} />
                  </div>
                </div>
              );
            })}
          </div>
        </SectionCard>
      )}
      {recentStocks.length > 0 && (
        <SectionCard className="min-h-[220px] p-4">
          <h3 className="mt-0">最近查看</h3>
          <div className="space-y-1.5">
            {recentStocks.slice(0, 8).map((item) => {
              const q = quoteMap.get(item.code);
              const chg = Number(q?.changePercent ?? q?.change_pct ?? 0);
              return (
                <div key={item.code} className="flex items-center justify-between text-sm py-1 border-b border-border/30">
                  <StockLink code={item.code} name={item.name ? `${item.name} ${item.code}` : item.code} />
                  {q ? <span className={`text-xs font-medium ${chg >= 0 ? 'text-danger' : 'text-success'}`}>{fmtNum(q.price, 2)} {chg >= 0 ? '+' : ''}{chg.toFixed(2)}%</span>
                    : batchQIsFetching ? <Skeleton width={80} height={16} />
                      : <span className="text-xs text-text-muted">{new Date(item.ts).toLocaleDateString('zh-CN')}</span>}
                </div>
              );
            })}
          </div>
        </SectionCard>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Quick-action strip                                                  */
/* ------------------------------------------------------------------ */

function QuickActions({ quickActions }: Pick<PersonalDashboardProps, 'quickActions'>) {
  return (
    <SectionCard className="min-h-[180px]">
      <div className="mb-4">
        <div className="eyebrow">下一步行动</div>
        <h2 className="mt-2">任务流入口</h2>
      </div>
      <QuickActionGrid cols={5}>
        {quickActions.map((a) => (
          <QuickAction key={a.href} href={a.href} icon={a.icon} title={a.title} description={a.description} />
        ))}
      </QuickActionGrid>
    </SectionCard>
  );
}

/* ------------------------------------------------------------------ */
/* Composed export                                                     */
/* ------------------------------------------------------------------ */

export function PersonalDashboard(props: PersonalDashboardProps) {
  return (
    <>
      <PersonalOverview
        nickname={props.nickname}
        paperSummary={props.paperSummary}
        paperAccount={props.paperAccount}
        paperPositions={props.paperPositions}
        activeAlerts={props.activeAlerts}
      />
      <QuickActions quickActions={props.quickActions} />
      <ThreeColumnCards
        watchlistItems={props.watchlistItems}
        paperPositions={props.paperPositions}
        marketNews={props.marketNews}
        quoteMap={props.quoteMap}
      />
    </>
  );
}

export { WatchlistRecent };
