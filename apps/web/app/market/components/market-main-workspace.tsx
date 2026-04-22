import Link from 'next/link';
import { Badge } from '@/components/ui';
import { CandlestickChart } from '@/components/charts';
import { EmptyState } from '@/components/status-state';
import { useHydrated } from '@/hooks/use-hydrated';
import { useMobile } from '@/hooks/use-mobile';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { fmtAmount, fmtNum, fmtPct } from '@/lib/data-utils';
import {
  marketLinkChipCls,
  marketNoteCardCls,
  marketPanelCls,
  marketPrimaryButtonCls,
  marketSecondaryButtonCls,
  marketSidebarActionCardCls,
} from '@/app/market/components/market-panel-styles';
import type { SavedMarketView } from '@/app/market/lib/market-view';
import type { NormalizedQuote } from '@aiask/shared-types';

type CandleDatum = {
  date: string;
  open: number;
  close: number;
  low: number;
  high: number;
  volume: number;
};

type OrderBookView = {
  bids: Array<{ price: number; volume: number }>;
  asks: Array<{ price: number; volume: number }>;
  timestamp: string | null;
};

type MarketMainWorkspaceProps = {
  pageOffline: boolean;
  quoteErrorMessage: string | null;
  tabErrorMessage: string | null;
  activePeriodLabel: string;
  chartDescription: string;
  activeTaskLabel: string;
  activeChange: number;
  activeChangeTone: string;
  activeQuote: NormalizedQuote | null;
  candleData: CandleDatum[];
  activeDisplayCode: string;
  quickJumpLinks: Array<{ label: string; href: string }>;
  onApplyPreset: (preset: Partial<SavedMarketView>) => void;
  obView: OrderBookView;
  compactSummaryOnly?: boolean;
};

export default function MarketMainWorkspace({
  pageOffline,
  quoteErrorMessage,
  tabErrorMessage,
  activePeriodLabel,
  chartDescription,
  activeTaskLabel,
  activeChange,
  activeChangeTone,
  activeQuote,
  candleData,
  activeDisplayCode,
  quickJumpLinks,
  onApplyPreset,
  obView,
  compactSummaryOnly = false,
}: MarketMainWorkspaceProps) {
  const hydrated = useHydrated();
  const compactLayoutDetected = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
  const mobileOnlyDetected = useMobile(RESPONSIVE_BREAKPOINTS.mobile);
  const compactLayout = hydrated ? compactLayoutDetected : true;
  const mobileOnly = hydrated ? mobileOnlyDetected : true;
  const chartHeight = compactLayout ? (mobileOnly ? 180 : 200) : 420;

  return (
    <>
      {pageOffline || quoteErrorMessage || tabErrorMessage ? (
        <div className="grid gap-3 md:grid-cols-2">
          {pageOffline ? (
            <div className={`${marketNoteCardCls} border-danger/15 px-4 py-3 text-danger md:col-span-2`}>
              数据服务当前未连接，行情工作区不会展示离线壳层结果；请等服务恢复后重新查询。
            </div>
          ) : null}
          {quoteErrorMessage ? (
            <div className={`${marketNoteCardCls} border-danger/15 px-4 py-3 text-danger`}>{quoteErrorMessage}</div>
          ) : null}
          {tabErrorMessage ? (
            <div className={`${marketNoteCardCls} border-danger/15 px-4 py-3 text-danger`}>{tabErrorMessage}</div>
          ) : null}
        </div>
      ) : null}

      <section className="page-hero p-4 sm:p-5">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)] xl:items-start">
          <div className={`${marketPanelCls} ${compactLayout ? 'min-h-[220px]' : 'min-h-[560px]'} rounded-[30px]`}>
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="eyebrow">主图工作区</div>
                <h2 className="mt-2">{compactLayout ? `K 线 · ${activePeriodLabel}` : `K 线主图 · ${activePeriodLabel}`}</h2>
                {!compactLayout ? <p className="mt-2 text-sm leading-6 text-text-secondary">{chartDescription}</p> : null}
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="neutral">{activeTaskLabel}</Badge>
                <Badge variant={activeChange >= 0 ? 'success' : 'danger'}>
                  {activeQuote ? `${fmtPct(activeQuote.changePercent as number | null)}` : '等待行情'}
                </Badge>
              </div>
            </div>

            {compactLayout && compactSummaryOnly ? (
              <div className="rounded-[26px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.56),rgba(240,246,255,0.3))] p-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className={`${marketNoteCardCls} px-4 py-3`}>
                    <div className="metric-label">当前视角</div>
                    <div className="mt-2 text-base font-semibold text-text-primary">{activeTaskLabel}</div>
                    <div className="mt-1 text-xs text-text-secondary">{chartDescription}</div>
                  </div>
                  <div className={`${marketNoteCardCls} px-4 py-3`}>
                    <div className="metric-label">下一步</div>
                    <div className="mt-2 text-sm leading-6 text-text-secondary">
                      非主行情标签下，主图先收成摘要；需要时可切回“基础行情”继续看 K 线与实时摘要。
                    </div>
                  </div>
                </div>
              </div>
            ) : candleData.length ? (
              <div className="overflow-hidden rounded-[26px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.56),rgba(240,246,255,0.3))] p-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.76)]">
                <CandlestickChart data={candleData} height={chartHeight} />
              </div>
            ) : (
              <div className={`flex ${compactLayout ? 'min-h-[150px]' : 'min-h-[380px]'} items-center rounded-[26px] border border-dashed border-white/75 bg-white/24 p-4`}>
                <EmptyState
                  variant="full"
                  className="w-full border-white/70 bg-white/44"
                  text="当前还没有可展示的 K 线"
                  hint="请先输入并查询一只真实标的，或切换到指数、板块等无需个股代码的视图。"
                  action={
                    <>
                      <button
                        type="button"
                        onClick={() => onApplyPreset({ activeTab: 'index', indexCode: '000300' })}
                        className={marketSecondaryButtonCls}
                      >
                        切到指数盯盘
                      </button>
                    </>
                  }
                />
              </div>
            )}

            {compactLayout ? (
              <details className={`${marketNoteCardCls} mt-4 px-4 py-4`}>
                <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开读图提醒、实时摘要与下一步</summary>
                <div className="mt-3 grid gap-3">
                  <div className="text-sm leading-6 text-text-secondary">
                    先看趋势方向和波动区间，再结合实时摘要里的价格、涨跌幅和成交额确认当前判断是否成立。
                  </div>
                  {activeQuote ? (
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className={`${marketNoteCardCls} px-4 py-3`}>
                        <div className="metric-label">现价</div>
                        <div className={`mt-2 text-xl font-semibold ${activeChangeTone}`}>
                          {fmtNum(activeQuote.price as number | null, 2)}
                        </div>
                      </div>
                      <div className={`${marketNoteCardCls} px-4 py-3`}>
                        <div className="metric-label">涨跌幅</div>
                        <div className={`mt-2 text-xl font-semibold ${activeChangeTone}`}>
                          {fmtPct(activeQuote.changePercent as number | null)}
                        </div>
                      </div>
                    </div>
                  ) : null}
                  <div className="flex flex-wrap gap-2">
                    {quickJumpLinks.slice(0, 3).map((link) => (
                      <Link key={`chart-${link.href}`} href={link.href} className={marketLinkChipCls}>
                        {link.label}
                      </Link>
                    ))}
                  </div>
                </div>
              </details>
            ) : (
              <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_clamp(240px,22vw,320px)]">
                <div className={`${marketNoteCardCls} px-4 py-4`}>
                  <div className="metric-label">读图提醒</div>
                  <div className="mt-2 text-sm leading-6 text-text-secondary">
                    先看趋势方向和波动区间，再结合右侧摘要里的价格、涨跌幅和成交额确认当前判断是否成立。
                  </div>
                </div>
                <div className={`${marketNoteCardCls} px-4 py-4`}>
                  <div className="metric-label">快捷联动</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {quickJumpLinks.slice(0, 3).map((link) => (
                      <Link key={`chart-${link.href}`} href={link.href} className={marketLinkChipCls}>
                        {link.label}
                      </Link>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {compactLayout ? null : (
            <aside className="grid gap-4 xl:sticky xl:top-24">
              <div className={`${marketPanelCls} rounded-[30px]`}>
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <div className="eyebrow">即时摘要</div>
                    <h2 className="mt-2">实时行情</h2>
                  </div>
                  <Badge variant="info">主任务</Badge>
                </div>
                {activeQuote ? (
                  <div className="space-y-3 text-sm">
                    <div className="flex flex-wrap items-center gap-2 rounded-[20px] border border-white/65 bg-white/42 px-4 py-3">
                      <StockLink code={String(activeQuote.code)} name={String(activeQuote.name ?? '')} />
                      <WatchlistButton code={String(activeQuote.code)} name={String(activeQuote.name ?? '')} />
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-2">
                      <div className="metric-tile px-4 py-3">
                        <div className="metric-label">现价</div>
                        <div className={`mt-2 text-2xl font-semibold ${activeChangeTone}`}>
                          {fmtNum(activeQuote.price as number | null, 2)}
                        </div>
                      </div>
                      <div className="metric-tile px-4 py-3">
                        <div className="metric-label">涨跌幅</div>
                        <div className={`mt-2 text-2xl font-semibold ${activeChangeTone}`}>
                          {fmtPct(activeQuote.changePercent as number | null)}
                        </div>
                      </div>
                      <div className="metric-tile px-4 py-3 text-text-secondary">
                        <div className="metric-label">成交额</div>
                        <div className="mt-2 text-base font-semibold text-text-primary">
                          {fmtAmount(activeQuote.amount as number | null)}
                        </div>
                      </div>
                      <div className="metric-tile px-4 py-3 text-text-secondary">
                        <div className="metric-label">成交量</div>
                        <div className="mt-2 text-base font-semibold text-text-primary">
                          {fmtAmount(activeQuote.volume as number | null)}
                        </div>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                      <div className="metric-tile px-3 py-2">
                        涨跌：<span className={activeChangeTone}>{fmtNum(activeQuote.change as number | null, 2)}</span>
                      </div>
                      <div className="metric-tile px-3 py-2">开盘：{fmtNum(activeQuote.open as number | null, 2)}</div>
                      <div className="metric-tile px-3 py-2">最高：{fmtNum(activeQuote.high as number | null, 2)}</div>
                      <div className="metric-tile px-3 py-2">最低：{fmtNum(activeQuote.low as number | null, 2)}</div>
                      <div className="metric-tile px-3 py-2">昨收：{fmtNum(activeQuote.prevClose as number | null, 2)}</div>
                    </div>
                  </div>
                ) : (
                  <div className="flex min-h-[280px] items-center rounded-[26px] border border-dashed border-white/75 bg-white/24 p-4">
                    <EmptyState
                      variant="full"
                      className="w-full border-white/70 bg-white/44"
                      text="当前没有可展示的行情摘要"
                      hint="请先查询真实标的；如果你想先看整体环境，也可以切到板块或涨停复盘视图。"
                      action={
                        <>
                          <button
                            type="button"
                            onClick={() => onApplyPreset({ activeTab: 'blocks' })}
                            className={marketPrimaryButtonCls}
                          >
                            去看板块轮动
                          </button>
                          <button
                            type="button"
                            onClick={() => onApplyPreset({ activeTab: 'limitup' })}
                            className={marketSecondaryButtonCls}
                          >
                            去看涨停复盘
                          </button>
                        </>
                      }
                    />
                  </div>
                )}
              </div>

              <div className={`${marketPanelCls} rounded-[30px]`}>
                <div className="mb-4">
                  <div className="eyebrow">执行动作</div>
                  <h2 className="mt-2">下一步</h2>
                </div>
                <div className="grid gap-2">
                  <button
                    type="button"
                    onClick={() => onApplyPreset({ activeTab: 'main' })}
                    className={marketSidebarActionCardCls}
                  >
                    <div className="text-sm font-medium text-text-primary">回基础行情</div>
                    <div className="mt-1 text-xs text-text-secondary">回到价格、K 线和实时摘要主视图。</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => onApplyPreset({ activeTab: 'blocks' })}
                    className={marketSidebarActionCardCls}
                  >
                    <div className="text-sm font-medium text-text-primary">看板块轮动</div>
                    <div className="mt-1 text-xs text-text-secondary">先看强弱板块，再决定是否切回个股。</div>
                  </button>
                  <Link
                    href={
                      activeDisplayCode
                        ? `/paper-trading?code=${encodeURIComponent(activeDisplayCode)}&from=market`
                        : '/paper-trading?from=market'
                    }
                    className={marketSidebarActionCardCls}
                  >
                    <div className="text-sm font-medium text-text-primary">去模拟交易</div>
                    <div className="mt-1 text-xs text-text-secondary">把当前观察标的直接带入交易工作流。</div>
                  </Link>
                  <Link
                    href={
                      activeDisplayCode
                        ? `/research?code=${encodeURIComponent(activeDisplayCode)}&from=market`
                        : '/research?from=market'
                    }
                    className={marketSidebarActionCardCls}
                  >
                    <div className="text-sm font-medium text-text-primary">去研究页补充信息</div>
                    <div className="mt-1 text-xs text-text-secondary">把行情判断补上研报、公告和资讯背景。</div>
                  </Link>
                </div>
              </div>

              <div className={`${marketPanelCls} rounded-[30px]`}>
                <div className="mb-4">
                  <div className="eyebrow">盘口深度</div>
                  <h2 className="mt-2">五档盘口</h2>
                </div>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <div className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-danger">卖盘</div>
                    {[...obView.asks].reverse().map((x, i, arr) => (
                      <div
                        key={`a${i}`}
                        className="metric-tile mb-2 flex justify-between rounded-[18px] px-3 py-2 text-danger/80"
                      >
                        <span>卖{arr.length - i}</span>
                        <span>{fmtNum(x.price, 2)}</span>
                        <span>{fmtAmount(x.volume)}</span>
                      </div>
                    ))}
                  </div>
                  <div>
                    <div className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-success">买盘</div>
                    {obView.bids.map((x, i) => (
                      <div
                        key={`b${i}`}
                        className="metric-tile mb-2 flex justify-between rounded-[18px] px-3 py-2 text-success/80"
                      >
                        <span>买{i + 1}</span>
                        <span>{fmtNum(x.price, 2)}</span>
                        <span>{fmtAmount(x.volume)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </aside>
          )}
        </div>
      </section>
    </>
  );
}
