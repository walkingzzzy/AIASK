import { Badge, TabBar } from '@/components/ui';
import { stockPanelCls } from '@/app/stock/components/stock-panel-styles';
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
  orderBook: NormalizedOrderBook;
  technicalData: unknown;
  patternData: unknown;
  showSentiment: boolean;
  sentimentScore: number;
  fundFlowChart: Array<{ label: string; value: number }>;
  fundFlowItems: StockFundFlowEntry[];
  fundFlowFetching: boolean;
  hasFundFlowResponse: boolean;
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
  orderBook,
  technicalData,
  patternData,
  showSentiment,
  sentimentScore,
  fundFlowChart,
  fundFlowItems,
  fundFlowFetching,
  hasFundFlowResponse,
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
  return (
    <>
      <div className={stockPanelCls}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="eyebrow">Detail Tabs</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">分层阅读各个分析维度</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              建议先看主图和技术面，再看资金、估值、AI 诊断和资讯。这样更容易把价格位置、交易结构和基本面叙事串起来。
            </p>
          </div>
          <Badge variant="neutral">{activeTabLabel}</Badge>
        </div>
        <div className="mt-4">
          <TabBar tabs={STOCK_INFO_TABS} active={infoTab} onChange={onInfoTabChange} />
        </div>
      </div>

      {infoTab === 'chart' ? (
        <StockChartTab period={submittedPeriod} isFetching={klineFetching} candleData={candleData} orderBook={orderBook} />
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
