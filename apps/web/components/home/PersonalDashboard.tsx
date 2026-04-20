'use client';

import { SectionCard, Skeleton, QuickAction, QuickActionGrid } from '@/components/ui';
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

  /* Layout */
  showSecondaryCards?: boolean;
}

/* ------------------------------------------------------------------ */
/* Personal Overview                                                   */
/* ------------------------------------------------------------------ */

function PersonalOverview({
  nickname,
  paperSummary,
  paperAccount,
  paperPositions,
  activeAlerts,
}: Pick<PersonalDashboardProps, 'nickname' | 'paperSummary' | 'paperAccount' | 'paperPositions' | 'activeAlerts'>) {
  return (
    <>
      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
        <div className="panel-soft rounded-[32px] p-5 sm:p-6">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-primary/15 bg-white/60 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-primary">
              个人中心
            </span>
            <span className="rounded-full border border-white/55 bg-white/34 px-3 py-1 text-xs text-text-primary">
              {paperPositions.length > 0 ? `${paperPositions.length} 个持仓` : '等待建立持仓'}
            </span>
          </div>
          <h2 className="mb-0 mt-4 text-[1.75rem] font-semibold tracking-[-0.03em] text-text-primary">
            欢迎回来，{nickname}
          </h2>
          <p className="mb-0 mt-3 text-sm leading-7 text-text-secondary">
            个人区用于承接你的资产状态、自选重点和下一步关注内容。市场信息看完后，可以在这里继续查看持仓、账户表现和需要优先处理的提醒。
          </p>
          <div className="mt-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
            <div className="metric-tile rounded-[22px] p-4">
              <div className="metric-label">总资产</div>
              <div className="mt-3 text-lg font-semibold text-text-primary">
                {fmtAmount(paperSummary.total_value ?? paperAccount.total_value)}
              </div>
              <div className="mt-1 text-xs text-text-secondary">首页直接给出当前资金规模</div>
            </div>
            <div className="metric-tile rounded-[22px] p-4">
              <div className="metric-label">总收益率</div>
              <div
                className={`mt-3 text-lg font-semibold ${Number(paperSummary.total_return_pct ?? 0) >= 0 ? 'text-danger' : 'text-success'}`}
              >
                {fmtPct(paperSummary.total_return_pct ?? 0)}
              </div>
              <div className="mt-1 text-xs text-text-secondary">帮助快速判断仓位状态</div>
            </div>
            <div className="metric-tile rounded-[22px] p-4">
              <div className="metric-label">持仓数</div>
              <div className="mt-3 text-lg font-semibold text-text-primary">{paperPositions.length}</div>
              <div className="mt-1 text-xs text-text-secondary">当前进入模拟盘管理的标的数量</div>
            </div>
            <div className="metric-tile rounded-[22px] p-4">
              <div className="metric-label">活跃告警</div>
              <div
                className={`mt-3 text-lg font-semibold ${activeAlerts.length > 0 ? 'text-danger' : 'text-text-primary'}`}
              >
                {activeAlerts.length}
              </div>
              <div className="mt-1 text-xs text-text-secondary">和持仓风险联动的即时提醒</div>
            </div>
          </div>
        </div>
        <div className="panel-soft rounded-[32px] p-5">
          <div className="eyebrow">关注提示</div>
          <div className="mt-4 space-y-3 text-sm text-text-secondary">
            <div className="metric-tile rounded-[20px] p-4">
              <div className="metric-label">活跃告警</div>
              <div className="mt-2 text-lg font-semibold text-text-primary">{activeAlerts.length}</div>
              <div className="mt-1 text-xs">优先处理仍在触发中的策略和持仓提醒，不建议把异常带到盘后再处理。</div>
            </div>
            <div className="metric-tile rounded-[20px] p-4">
              <div className="metric-label">在场资产</div>
              <div className="mt-2 text-lg font-semibold text-text-primary">
                {fmtAmount(paperSummary.total_value ?? paperAccount.total_value)}
              </div>
              <div className="mt-1 text-xs">如果现在还没有持仓，建议先回到看盘或模拟交易入口，建立今天的观察重点。</div>
            </div>
            <div className="metric-tile rounded-[20px] p-4">
              <div className="metric-label">今日节奏</div>
              <div className="mt-2 text-sm font-semibold text-text-primary">
                {paperPositions.length > 0 ? '先看持仓，再看自选' : '先看自选，再决定是否建仓'}
              </div>
              <div className="mt-1 text-xs">让首页的后半段阅读更聚焦，不需要在多个入口之间来回切换。</div>
            </div>
          </div>
        </div>
      </div>

    </>
  );
}

/* ------------------------------------------------------------------ */
/* 3-column: watchlist / positions / news                              */
/* ------------------------------------------------------------------ */

export function PersonalSecondaryCards({
  watchlistItems,
  paperPositions,
  marketNews,
  quoteMap,
}: Pick<PersonalDashboardProps, 'watchlistItems' | 'paperPositions' | 'marketNews' | 'quoteMap'>) {
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
      {/* Watchlist */}
      <SectionCard className="min-h-[220px] xl:col-span-1">
        <div className="flex items-center justify-between mb-2">
          <div>
            <div className="eyebrow">Watchlist Focus</div>
            <h2 className="mt-2">自选股行情</h2>
          </div>
          <Link href="/watchlist" className="text-sm text-primary no-underline">
            更多
          </Link>
        </div>
        <div className="space-y-2">
          {watchlistItems.slice(0, 5).map((item) => {
            const q = quoteMap.get(item.code);
            const chg = Number(q?.changePercent ?? q?.change_pct ?? 0);
            return (
              <div
                key={item.code}
                className="flex items-center justify-between rounded-[18px] border border-white/50 bg-white/28 px-3 py-2 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
              >
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
                  <Link
                    href="/market"
                    className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline"
                  >
                    去市场页
                  </Link>
                  <Link
                    href="/watchlist"
                    className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline"
                  >
                    管理自选
                  </Link>
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
            <div className="eyebrow">Position Watch</div>
            <h2 className="mt-2">持仓概览</h2>
          </div>
          <Link href="/paper-trading" className="text-sm text-primary no-underline">
            更多
          </Link>
        </div>
        <div className="space-y-2">
          {paperPositions.slice(0, 5).map((item, i) => (
            <div
              key={String(item.stock_code ?? i)}
              className="flex items-center justify-between rounded-[18px] border border-white/50 bg-white/28 px-3 py-2 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
            >
              <StockLink code={String(item.stock_code ?? '')} name={String(item.stock_name ?? item.stock_code ?? '')} />
              <span className={Number(item.profit_rate ?? 0) >= 0 ? 'text-danger text-xs' : 'text-success text-xs'}>
                {fmtPct(item.profit_rate ?? 0)}
              </span>
            </div>
          ))}
          {paperPositions.length === 0 ? (
            <EmptyState
              text="模拟盘还没有持仓"
              hint="先创建账户或载入示例委托后，这里会显示持仓收益与盈亏变化。"
              action={
                <Link
                  href="/paper-trading"
                  className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline"
                >
                  去模拟盘建仓
                </Link>
              }
            />
          ) : null}
        </div>
      </SectionCard>

      {/* Market news */}
      <SectionCard className="min-h-[220px] xl:col-span-1">
        <div className="flex items-center justify-between mb-2">
          <div>
            <div className="eyebrow">News Feed</div>
            <h2 className="mt-2">市场快讯</h2>
          </div>
          <Link href="/research" className="text-sm text-primary no-underline">
            更多
          </Link>
        </div>
        <div className="space-y-2">
          {marketNews.slice(0, 5).map((item, i) => (
            <div
              key={String(item.id ?? item.title ?? i)}
              className="rounded-[18px] border border-white/50 bg-white/28 p-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
            >
              <div className="font-medium line-clamp-2">{String(item.title ?? item.name ?? '未命名快讯')}</div>
              <div className="text-xs text-text-secondary mt-1">
                {String(item.publish_time ?? item.time ?? item.date ?? '-')}
              </div>
            </div>
          ))}
          {marketNews.length === 0 ? (
            <EmptyState
              text="当前没有市场快讯"
              hint="可以去研究页查看完整资讯源，或稍后返回首页等待快讯更新。"
              action={
                <Link
                  href="/research"
                  className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline"
                >
                  去研究页
                </Link>
              }
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

function WatchlistRecent({
  mounted,
  watchlistItems,
  recentStocks,
  quoteMap,
  batchQIsFetching,
}: Pick<PersonalDashboardProps, 'mounted' | 'watchlistItems' | 'recentStocks' | 'quoteMap' | 'batchQIsFetching'>) {
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
                <div
                  key={`watchlist-recent-skeleton-row-${index}-${itemIndex}`}
                  className="flex items-center justify-between border-b border-border/30 py-1.5"
                >
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
                <div
                  key={item.code}
                  className="flex items-center justify-between text-sm py-1 border-b border-border/30"
                >
                  <StockLink code={item.code} name={item.name || item.code} />
                  <div className="flex items-center gap-2">
                    {q ? (
                      <span className={`text-xs font-medium ${chg >= 0 ? 'text-danger' : 'text-success'}`}>
                        {fmtNum(q.price, 2)} {chg >= 0 ? '+' : ''}
                        {chg.toFixed(2)}%
                      </span>
                    ) : batchQIsFetching ? (
                      <Skeleton width={80} height={16} />
                    ) : null}
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
                <div
                  key={item.code}
                  className="flex items-center justify-between text-sm py-1 border-b border-border/30"
                >
                  <StockLink code={item.code} name={item.name ? `${item.name} ${item.code}` : item.code} />
                  {q ? (
                    <span className={`text-xs font-medium ${chg >= 0 ? 'text-danger' : 'text-success'}`}>
                      {fmtNum(q.price, 2)} {chg >= 0 ? '+' : ''}
                      {chg.toFixed(2)}%
                    </span>
                  ) : batchQIsFetching ? (
                    <Skeleton width={80} height={16} />
                  ) : (
                    <span className="text-xs text-text-muted">{new Date(item.ts).toLocaleDateString('zh-CN')}</span>
                  )}
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
        <div className="eyebrow">常用入口</div>
        <h2 className="mt-2">快捷操作</h2>
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
  const showSecondaryCards = props.showSecondaryCards ?? true;

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
      {showSecondaryCards ? (
        <PersonalSecondaryCards
          watchlistItems={props.watchlistItems}
          paperPositions={props.paperPositions}
          marketNews={props.marketNews}
          quoteMap={props.quoteMap}
        />
      ) : null}
    </>
  );
}

export { WatchlistRecent };
