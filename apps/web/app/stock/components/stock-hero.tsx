import Link from 'next/link';
import { AskAiButton } from '@/components/ask-ai-button';
import LightOverviewHero from '@/components/light-overview-hero';
import { Badge } from '@/components/ui';
import { WatchlistButton } from '@/components/watchlist-button';
import { useMobile } from '@/hooks/use-mobile';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import {
  stockLinkChipCls,
  stockNoteCardCls,
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
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);

  return (
    <LightOverviewHero
      eyebrow="个股工作台"
      title={title}
      summary="先锁定代码和周期，再看报价、主图和行动卡，最后跳转到资金流、研究、交易或 AI 诊断。"
      badges={(
        <>
          <Badge variant="info">个股工作台</Badge>
          <Badge variant="neutral">{activeTabLabel}</Badge>
          <Badge variant={hasQuote ? 'success' : loading ? 'warning' : 'neutral'}>
            {hasQuote ? '报价已加载' : loading ? '加载中' : '等待查询'}
          </Badge>
        </>
      )}
      actions={(
        <>
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
        </>
      )}
      status={(
        <div
          data-testid="page-primary-status"
          className="rounded-[20px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
        >
          <div className="font-medium text-text-primary">
            当前代码 {currentFocusCode} ｜ 当前标签 {activeTabLabel}
          </div>
          <p className="mb-0 mt-1 text-xs leading-6 text-text-secondary">
            刷新状态 {refreshStatus} ｜ 振幅 {amplitude}
          </p>
        </div>
      )}
      metrics={[
        { key: 'stock-code', label: '当前代码', value: currentFocusCode },
        { key: 'stock-tab', label: '当前标签', value: activeTabLabel },
        { key: 'stock-refresh', label: '刷新状态', value: refreshStatus, hint: refreshTimeText },
        { key: 'stock-amplitude', label: '当前振幅', value: amplitude },
      ]}
      compact={compactLayout}
      detailsTitle="展开阅读建议与快捷动作"
      detailsContent={(
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            {heroNotes.map((note) => (
              <div key={note} className={stockNoteCardCls}>
                {note}
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
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
            {quickLinks.map((link) => (
              <Link key={link.href} href={link.href} className={stockLinkChipCls}>
                {link.label}
              </Link>
            ))}
          </div>
        </div>
      )}
    />
  );
}
