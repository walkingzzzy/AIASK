import Link from 'next/link';
import { AskAiButton } from '@/components/ask-ai-button';
import { Badge } from '@/components/ui';
import { WatchlistButton } from '@/components/watchlist-button';
import {
  stockLinkChipCls,
  stockNoteCardCls,
  stockPanelCls,
  stockPrimaryButtonCls,
  stockPrimaryLinkCls,
} from '@/app/stock/components/stock-panel-styles';

type StockHeroProps = {
  activeTabLabel: string;
  title: string;
  loading: boolean;
  hasQuote: boolean;
  askAiStockCode?: string;
  askAiSummary?: string;
  currentFocusCode: string;
  refreshStatus: string;
  refreshTimeText: string;
  amplitude: string;
  heroNotes: string[];
  quickLinks: Array<{ label: string; href: string }>;
  watchlistCode: string;
  watchlistName?: string;
};

export default function StockHero({
  activeTabLabel,
  title,
  loading,
  hasQuote,
  askAiStockCode,
  askAiSummary,
  currentFocusCode,
  refreshStatus,
  refreshTimeText,
  amplitude,
  heroNotes,
  quickLinks,
  watchlistCode,
  watchlistName,
}: StockHeroProps) {
  return (
    <section className="page-hero p-5 sm:p-6">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info">Stock Workspace</Badge>
            <Badge variant="neutral">{activeTabLabel}</Badge>
            <Badge variant={hasQuote ? 'success' : loading ? 'warning' : 'neutral'}>
              {hasQuote ? '报价已加载' : loading ? '加载中' : '等待查询'}
            </Badge>
          </div>
          <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
            {title}
          </h1>
          <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
            这次重构把个股页收束成一条更清晰的阅读路径：先锁定代码和周期，再看报价、主图和行动卡，最后跳转到资金流、研究、交易或
            AI 诊断，不再让加载态把主区打散。
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button
              type="submit"
              form="stock-query-form"
              disabled={loading}
              aria-label="刷新当前股票"
              className={stockPrimaryButtonCls}
            >
              {loading ? '加载中...' : '查询当前股票'}
            </button>
            <AskAiButton
              stockCode={askAiStockCode}
              summary={askAiSummary}
              prompt={askAiStockCode ? `请分析 ${askAiStockCode} 当前个股页信号` : '请分析当前个股页'}
              label="解读当前个股"
            />
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-4">
            <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前代码</div>
              <div className="mt-3 text-xl font-semibold text-text-primary">{currentFocusCode}</div>
              <div className="mt-1 text-xs text-text-secondary">当前工作区聚焦标的</div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前标签</div>
              <div className="mt-3 text-xl font-semibold text-text-primary">{activeTabLabel}</div>
              <div className="mt-1 text-xs text-text-secondary">当前正在阅读的分析视角</div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">刷新状态</div>
              <div className="mt-3 text-sm font-semibold leading-6 text-text-primary">{refreshStatus}</div>
              <div className="mt-1 text-xs text-text-secondary">{refreshTimeText}</div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前振幅</div>
              <div className="mt-3 text-xl font-semibold text-text-primary">{amplitude}</div>
              <div className="mt-1 text-xs text-text-secondary">用于判断短线波动强弱</div>
            </div>
          </div>
        </div>

        <div className="grid gap-3">
          <div className={stockPanelCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">阅读建议</div>
            <div className="mt-4 space-y-3">
              {heroNotes.map((note) => (
                <div key={note} className={stockNoteCardCls}>
                  {note}
                </div>
              ))}
            </div>
          </div>
          <div className={stockPanelCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">快捷动作</div>
            <div className="mt-4 flex flex-wrap gap-2">
              {watchlistCode && watchlistName ? <WatchlistButton code={watchlistCode} name={watchlistName} size="md" /> : null}
              {askAiStockCode ? (
                <>
                  <Link href={`/paper-trading?code=${askAiStockCode}`} className={stockPrimaryLinkCls}>
                    去模拟交易
                  </Link>
                  <Link href={`/backtest?code=${askAiStockCode}`} className={stockLinkChipCls}>
                    策略回测
                  </Link>
                  <Link href={`/assistant?code=${askAiStockCode}`} className={stockLinkChipCls}>
                    AI诊断
                  </Link>
                </>
              ) : null}
            </div>
            {quickLinks.length > 0 ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {quickLinks.map((link) => (
                  <Link key={link.href} href={link.href} className={stockLinkChipCls}>
                    {link.label}
                  </Link>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
