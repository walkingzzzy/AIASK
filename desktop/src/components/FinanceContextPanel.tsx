import { Newspaper, RefreshCw, TrendingUp, Zap } from "lucide-react";
import { useMemo } from "react";

import { MarketHeatmap, type HeatmapData } from "./FinancialChart";
import { Button, EmptyState, JsonPanel, StatusBadge } from "./ui";
import { dataObject, firstArray, list, valueOf } from "../pages/pageUtils";
import type { ApiProblem, UnknownRecord, WorkbenchContext, WorkbenchMessage } from "../types";

function normalizeText(value: unknown) {
  return String(value || "").trim();
}

function extractStockMentions(messages: WorkbenchMessage[]) {
  const stockCodePattern = /\b(?:SH|SZ)?\s?(60\d{4}|68\d{4}|30\d{4}|00\d{4})\b/gi;
  const chineseStockPattern = /[\u4e00-\u9fa5]{2,10}(?:股份|银行|证券|科技|集团|能源|药业|汽车|电子|白酒|电力)/g;
  const found = new Set<string>();

  for (const message of messages) {
    const content = normalizeText(message.content);
    for (const match of content.matchAll(stockCodePattern)) {
      const code = String(match[1] || "").trim();
      if (code) found.add(code);
    }
    for (const match of content.matchAll(chineseStockPattern)) {
      const name = normalizeText(match[0]);
      if (name) found.add(name);
    }
  }

  return Array.from(found).slice(0, 5);
}

function normalizeQuote(quotePayload: unknown) {
  const envelope = dataObject(quotePayload, {});
  const quote = dataObject(envelope.quote, {});
  return {
    code: valueOf(envelope, ["code", "symbol"], "-"),
    name: valueOf(envelope, ["name"], valueOf(quote, ["name"], "-")),
    price: Number(envelope.price ?? quote.price ?? quote.last_price ?? Number.NaN),
    change: Number(envelope.change ?? quote.change ?? Number.NaN),
    changePct: Number(envelope.change_pct ?? quote.change_pct ?? quote.changePercent ?? Number.NaN),
    volume: Number(quote.volume ?? quote.amount ?? 0),
    provider: valueOf(envelope, ["provider"], valueOf(quote, ["provider"], "-")),
    timestamp: valueOf(envelope, ["data_timestamp", "timestamp"], "-")
  };
}

function normalizeNews(newsPayload: unknown) {
  const envelope = dataObject(newsPayload, {});
  const items = firstArray(envelope, ["items", "news", "sources"]);
  return items.slice(0, 5).map((item, index) => ({
    id: String(item.id || item.news_id || `news_${index}`),
    title: valueOf(item, ["title", "headline", "summary"], "未命名资讯"),
    source: valueOf(item, ["source", "provider", "publisher"], "-"),
    publishedAt: valueOf(item, ["published_at", "datetime", "time"], "-"),
    url: valueOf(item, ["url", "link"], "")
  }));
}

function buildHeatmapData(snapshotPayload: unknown): HeatmapData[] {
  const snapshotEnvelope = dataObject(snapshotPayload, {});
  const snapshot = dataObject(snapshotEnvelope.snapshot, snapshotEnvelope);
  const hot = firstArray(snapshot, ["hot_industries"]);
  const cold = firstArray(snapshot, ["cold_industries"]);
  const merged = [...hot, ...cold];

  return merged.map((item, index) => {
    const stocks = Number(item.stock_count ?? item.stocks ?? item.breadth_count ?? 0);
    const breadth = Number(item.ma20_breadth ?? item.breadth ?? 0);
    return {
      industry: valueOf(item, ["name", "industry", "code"], `行业 ${index + 1}`),
      temperature: Number(item.temperature ?? 0),
      stocks: stocks > 0 ? stocks : Math.max(1, Math.round(breadth * 20)),
      avgChange: Number(item.change ?? item.avg_change ?? (breadth - 0.5) * 10)
    };
  });
}

export function FinanceContextBody({
  workbench,
  quotePayload,
  newsPayload,
  snapshotPayload,
  realtimeConnected,
  loading,
  error,
  onRefresh
}: {
  workbench: WorkbenchContext;
  quotePayload: unknown;
  newsPayload: unknown;
  snapshotPayload: unknown;
  realtimeConnected: boolean;
  loading: boolean;
  error: ApiProblem | null;
  onRefresh: () => void;
}) {
  const mentionedStocks = useMemo(() => extractStockMentions(workbench.selectedSessionMessages || []), [workbench.selectedSessionMessages]);
  const quote = useMemo(() => normalizeQuote(quotePayload), [quotePayload]);
  const news = useMemo(() => normalizeNews(newsPayload), [newsPayload]);
  const heatmapData = useMemo(() => buildHeatmapData(snapshotPayload), [snapshotPayload]);
  const currentRun = workbench.currentRun || {};
  const sources = list<UnknownRecord>(workbench.selectedRunSources || []);
  const tools = list<UnknownRecord>(workbench.selectedRunTools || []);
  const hasQuote = quote.code !== "-" || quote.name !== "-";

  return (
    <div className="rail-stack">
      <section className="rail-card">
        <span className="rail-card-title">实时连接</span>
        <strong>{realtimeConnected ? "事件流已连接" : "快照模式"}</strong>
        <p>{realtimeConnected ? "运行事件正在通过 Agent SSE 通道更新。" : "市场上下文将按需刷新。"}</p>
        <div className="page-actions" style={{ marginTop: 10 }}>
          <StatusBadge tone={realtimeConnected ? "success" : "warning"}>
            <Zap size={14} />
            {realtimeConnected ? "实时更新" : "手动刷新"}
          </StatusBadge>
          <Button icon={<RefreshCw size={16} />} onClick={onRefresh} busy={loading}>
            刷新
          </Button>
        </div>
        {error ? <p>{error.detail || error.title}</p> : null}
      </section>

      <section className="rail-card">
        <span className="rail-card-title">提到的股票</span>
        {mentionedStocks.length ? (
          <div className="tool-chips">
            {mentionedStocks.map((stock) => (
              <span className="tool-chip" key={stock}>
                {stock}
              </span>
            ))}
          </div>
        ) : (
          <p>当前会话还没有识别到股票实体。</p>
        )}
      </section>

      <section className="rail-card">
        <span className="rail-card-title">行情焦点</span>
        {hasQuote ? (
          <div className="financial-context">
            <div className="financial-context-header">
              <div>
                <h4>{quote.name !== "-" ? quote.name : quote.code}</h4>
                <span className="stock-code">{quote.code}</span>
              </div>
              <div className="financial-context-price">
                <strong>{Number.isFinite(quote.price) ? quote.price.toFixed(2) : "暂无"}</strong>
                <StatusBadge tone={!Number.isFinite(quote.changePct) || quote.changePct >= 0 ? "success" : "danger"}>
                  <TrendingUp size={14} />
                  {Number.isFinite(quote.changePct) && quote.changePct >= 0 ? "+" : ""}
                  {Number.isFinite(quote.changePct) ? quote.changePct.toFixed(2) : "0.00"}%
                </StatusBadge>
              </div>
            </div>
            <div className="financial-context-metrics">
              <div className="metric-item">
                <span>涨跌额</span>
                <strong>
                  {Number.isFinite(quote.change) && quote.change >= 0 ? "+" : ""}
                  {Number.isFinite(quote.change) ? quote.change.toFixed(2) : "0.00"}
                </strong>
              </div>
              <div className="metric-item">
                <span>成交量</span>
                <strong>{quote.volume ? quote.volume.toLocaleString("zh-CN") : "-"}</strong>
              </div>
              <div className="metric-item">
                <span>数据来源</span>
                <strong>{quote.provider}</strong>
              </div>
              <div className="metric-item">
                <span>时间</span>
                <strong>{quote.timestamp}</strong>
              </div>
            </div>
          </div>
        ) : (
          <EmptyState title="暂无行情焦点" detail="在会话中提到股票后，这里会加载对应行情卡片。" />
        )}
      </section>

      <section className="rail-card">
        <span className="rail-card-title">市场热度</span>
        {heatmapData.length ? <MarketHeatmap data={heatmapData.slice(0, 8)} /> : <p>市场温度快照暂不可用。</p>}
      </section>

      <section className="rail-card">
        <span className="rail-card-title">相关新闻</span>
        {news.length ? (
          <div className="financial-context">
            {news.map((item) => (
              <div className="recent-run-item" key={item.id} style={{ alignItems: "flex-start" }}>
                <Newspaper size={14} />
                <div style={{ flex: 1 }}>
                  <strong style={{ display: "block", fontSize: 13 }}>{item.title}</strong>
                  <span style={{ display: "block", fontSize: 12, color: "var(--text-muted)" }}>
                    {item.source}
                    {item.publishedAt !== "-" ? ` | ${item.publishedAt}` : ""}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p>当前焦点暂无相关新闻。</p>
        )}
      </section>

      <JsonPanel
        title="金融上下文证据"
        data={{
          current_run: currentRun,
          mentioned_stocks: mentionedStocks,
          quote: quotePayload,
          news: newsPayload,
          snapshot: snapshotPayload,
          sources,
          tools
        }}
      />
    </div>
  );
}

export function FinanceContextPanel({
  workbench,
  quotePayload,
  newsPayload,
  snapshotPayload,
  realtimeConnected,
  loading,
  error,
  onRefresh
}: {
  workbench: WorkbenchContext;
  quotePayload: unknown;
  newsPayload: unknown;
  snapshotPayload: unknown;
  realtimeConnected: boolean;
  loading: boolean;
  error: ApiProblem | null;
  onRefresh: () => void;
}) {
  return (
    <aside className="right-rail page-context-drawer" data-testid="finance-context-panel" aria-label="金融上下文面板">
      <div className="rail-header">
        <h3>金融上下文</h3>
        <p>当前会话关联的市场信息和股票线索</p>
      </div>
      <FinanceContextBody
        workbench={workbench}
        quotePayload={quotePayload}
        newsPayload={newsPayload}
        snapshotPayload={snapshotPayload}
        realtimeConnected={realtimeConnected}
        loading={loading}
        error={error}
        onRefresh={onRefresh}
      />
    </aside>
  );
}
