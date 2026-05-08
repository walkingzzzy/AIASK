import { Badge, TabBar } from '@/components/ui';
import { stockPanelCls } from '@/app/stock/components/stock-panel-styles';
import { useHydrated } from '@/hooks/use-hydrated';
import { useMobile } from '@/hooks/use-mobile';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import StockAiTab from '@/app/stock/components/stock-ai-tab';
import StockChartTab from '@/app/stock/components/stock-chart-tab';
import StockFundamentalTab from '@/app/stock/components/stock-fundamental-tab';
import StockFundFlowTab from '@/app/stock/components/stock-fund-flow-tab';
import StockNewsTab from '@/app/stock/components/stock-news-tab';
import StockPeersTab from '@/app/stock/components/stock-peers-tab';
import StockSharesTab from '@/app/stock/components/stock-shares-tab';
import StockTechnicalTab from '@/app/stock/components/stock-technical-tab';
import StockValuationTab from '@/app/stock/components/stock-valuation-tab';
import {
  STOCK_INFO_TABS,
  type Period,
  type StockInfoTab,
} from '@/app/stock/lib/stock-detail-view';
import type {
  NormalizedOrderBook,
  StockFundFlowEntry,
  StockFundamentalOverview,
  StockNewsItem,
  StockValuationOverview,
} from '@aiask/shared-types';

type CandlePoint = {
  date: string;
  open: number;
  close: number;
  low: number;
  high: number;
  volume: number;
};

type StockDetailTabsProps = {
  infoTab: StockInfoTab;
  onInfoTabChange: (tab: StockInfoTab) => void;
  activeTabLabel: string;
  submittedPeriod: Period;
  klineFetching: boolean;
  candleData: CandlePoint[];
  klineEmptyHint?: string | null;
  orderBook: NormalizedOrderBook;
  technicalData: unknown;
  patternData: unknown;
  showSentiment: boolean;
  sentimentScore: number;
  fundFlowChart: Array<{ label: string; value: number }>;
  fundFlowItems: StockFundFlowEntry[];
  fundFlowFetching: boolean;
  hasFundFlowResponse: boolean;
  fundFlowHasDatedSamples: boolean;
  fundamental: StockFundamentalOverview | null;
  fundamentalFetching: boolean;
  hasFundamentalResponse: boolean;
  skipKeys: string[];
  newsItems: StockNewsItem[];
  newsFetching: boolean;
  valuationMetrics: StockValuationOverview;
  hasValuationResponse: boolean;
  valuationFetching: boolean;
  activeCode: string | null;
};

export default function StockDetailTabs({
  infoTab,
  onInfoTabChange,
  activeTabLabel,
  submittedPeriod,
  klineFetching,
  candleData,
  klineEmptyHint,
  orderBook,
  technicalData,
  patternData,
  showSentiment,
  sentimentScore,
  fundFlowChart,
  fundFlowItems,
  fundFlowFetching,
  hasFundFlowResponse,
  fundFlowHasDatedSamples,
  fundamental,
  fundamentalFetching,
  hasFundamentalResponse,
  skipKeys,
  newsItems,
  newsFetching,
  valuationMetrics,
  hasValuationResponse,
  valuationFetching,
  activeCode,
}: StockDetailTabsProps) {
  const hydrated = useHydrated();
  const compactLayoutDetected = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
  const compactLayout = hydrated ? compactLayoutDetected : true;
  const primaryTabs = compactLayout
    ? STOCK_INFO_TABS.filter((tab) => ['chart', 'tech', 'fund', 'valuation'].includes(tab.key))
    : STOCK_INFO_TABS;
  const secondaryTabs = compactLayout
    ? STOCK_INFO_TABS.filter((tab) => ['basic', 'shares', 'peers', 'ai', 'news'].includes(tab.key))
    : [];
  const primaryActiveTab = primaryTabs.some((tab) => tab.key === infoTab) ? infoTab : 'chart';
  const secondaryActiveTab = secondaryTabs.some((tab) => tab.key === infoTab) ? infoTab : secondaryTabs[0]?.key ?? 'basic';

  return (
    <>
      <div className={stockPanelCls}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="eyebrow">分析维度</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">分层阅读各个分析维度</h2>
            {!compactLayout ? (
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                建议先看主图和技术面，再看资金、估值、AI 诊断和资讯。这样更容易把价格位置、交易结构和基本面叙事串起来。
              </p>
            ) : null}
          </div>
          <Badge variant="neutral">{activeTabLabel}</Badge>
        </div>
        <div className="mt-4">
          <TabBar tabs={primaryTabs} active={primaryActiveTab} onChange={onInfoTabChange} />
        </div>
        {compactLayout && secondaryTabs.length > 0 ? (
          <details className="mt-3 rounded-[22px] border border-white/45 bg-white/24 px-4 py-3">
            <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开更多维度</summary>
            <div className="mt-3">
              <TabBar tabs={secondaryTabs} active={secondaryActiveTab} onChange={onInfoTabChange} />
            </div>
          </details>
        ) : null}
      </div>

      {infoTab === 'chart' ? (
        <StockChartTab
          period={submittedPeriod}
          isFetching={klineFetching}
          candleData={candleData}
          emptyHint={klineEmptyHint}
          orderBook={orderBook}
        />
      ) : null}
      {infoTab === 'tech' ? (
        <StockTechnicalTab
          technicalData={technicalData}
          patternData={patternData}
          showSentiment={showSentiment}
          sentimentScore={sentimentScore}
        />
      ) : null}
      {infoTab === 'fund' ? (
        <StockFundFlowTab
          fundFlowChart={fundFlowChart}
          fundFlowItems={fundFlowItems}
          isFetching={fundFlowFetching}
          hasResponse={hasFundFlowResponse}
          hasDatedSamples={fundFlowHasDatedSamples}
        />
      ) : null}
      {infoTab === 'basic' ? (
        <StockFundamentalTab
          fundamental={fundamental}
          isFetching={fundamentalFetching}
          hasResponse={hasFundamentalResponse}
          skipKeys={skipKeys}
        />
      ) : null}
      {infoTab === 'news' ? <StockNewsTab newsItems={newsItems} isFetching={newsFetching} /> : null}
      {infoTab === 'shares' ? <StockSharesTab activeCode={activeCode} /> : null}
      {infoTab === 'valuation' ? (
        <StockValuationTab
          valuationMetrics={valuationMetrics}
          hasResponse={hasValuationResponse}
          isFetching={valuationFetching}
        />
      ) : null}
      {infoTab === 'ai' ? <StockAiTab activeCode={activeCode} /> : null}
      {infoTab === 'peers' ? <StockPeersTab activeCode={activeCode} /> : null}
    </>
  );
}
