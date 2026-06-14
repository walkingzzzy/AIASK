import { Activity, BarChart3, Database, RefreshCw, Thermometer } from "lucide-react";
import { CSSProperties, FormEvent, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { MetricCard, RawEvidencePanel, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type {
  MarketTemperatureCacheHistory,
  MarketTemperatureCacheHistoryItem,
  MarketTemperatureCacheReadiness,
  MarketTemperatureForwardValidation,
  MarketTemperatureIndustry,
  MarketTemperatureIndustryConstituent,
  MarketTemperatureIndustryConstituents,
  MarketTemperatureIndustryHistory,
  MarketTemperatureIndustryHistoryItem,
  MarketTemperatureSnapshot,
  ToolEnvelope
} from "../../types";

interface Props {
  endpoint: string;
  apiToken: string;
}

function numeric(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function boundedInteger(value: string, fallback: number, min: number, max: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(Math.trunc(parsed), max));
}

function ratio(value: unknown): string {
  const number = numeric(value);
  return number === null ? "-" : `${(number * 100).toFixed(1)}%`;
}

function pct(value: unknown): string {
  const number = numeric(value);
  return number === null ? "-" : `${number.toFixed(2)}%`;
}

function fixed(value: unknown, digits = 1): string {
  const number = numeric(value);
  return number === null ? "-" : number.toFixed(digits);
}

function temperatureStatus(value: unknown): string {
  const number = numeric(value);
  if (number === null) return "not_loaded";
  if (number >= 80 || number <= 20) return "warning";
  if (number >= 65 || number <= 35) return "partial";
  return "ready";
}

function stateLabel(state?: string | null): string {
  const labels: Record<string, string> = {
    hot: "过热",
    warm: "偏热",
    neutral: "中性",
    cool: "偏冷",
    cold: "过冷",
    unknown: "未知"
  };
  return labels[String(state || "unknown").toLowerCase()] || String(state || "未知");
}

function qualityLabel(value?: string | null): string {
  const labels: Record<string, string> = {
    available: "可用",
    degraded: "降级",
    failed: "失败",
    fresh: "新鲜",
    healthy: "健康",
    invalid: "无效",
    missing: "缺失",
    not_loaded: "未加载",
    not_ready: "未就绪",
    stale: "陈旧",
    unavailable: "不可用",
    unavailable_fallback_to_weighted_pct_change: "基准不可用，已降级",
    unknown: "未知"
  };
  const normalized = String(value || "unknown").toLowerCase();
  return labels[normalized] || String(value || "未知");
}

function messageLabel(value: string): string {
  const labels: Record<string, string> = {
    MARKET_TEMPERATURE_FAILED: "快照加载失败",
    MARKET_TEMPERATURE_LOADED: "快照已加载",
    NOT_LOADED: "未加载"
  };
  return labels[value] || qualityLabel(value);
}

function fieldLabel(value?: string | null): string {
  const labels: Record<string, string> = {
    benchmark_return: "基准收益",
    weighted_pct_change: "加权涨跌"
  };
  return labels[String(value || "").toLowerCase()] || String(value || "-");
}

function stateOrQualityLabel(state?: string | null, quality?: string | null): string {
  return state ? stateLabel(state) : qualityLabel(quality);
}

function stateStatus(state?: string | null): string {
  const normalized = String(state || "").toLowerCase();
  if (normalized === "hot" || normalized === "cold") return "warning";
  if (normalized === "warm" || normalized === "cool") return "partial";
  if (normalized === "neutral") return "ready";
  return "not_loaded";
}

function readinessStatus(readiness?: MarketTemperatureCacheReadiness | null): string {
  if (!readiness) return "not_loaded";
  if (readiness.ready) return readiness.degraded ? "partial" : "ready";
  const status = String(readiness.status || "").toLowerCase();
  if (["missing", "stale", "failed", "unavailable", "invalid", "not_ready"].includes(status)) return "warning";
  return "not_loaded";
}

function historyItemStatus(item: MarketTemperatureCacheHistoryItem): string {
  const qualityStatus = String(item.quality_status || "").toLowerCase();
  if (qualityStatus === "degraded" || (Array.isArray(item.warnings) && item.warnings.length)) return "partial";
  if (qualityStatus === "healthy" || qualityStatus === "available") return stateStatus(String(item.market_state || ""));
  return "not_loaded";
}

function industryHistoryItemStatus(item: MarketTemperatureIndustryHistoryItem): string {
  const qualityStatus = String(item.quality_status || "").toLowerCase();
  if (qualityStatus === "degraded" || (Array.isArray(item.warnings) && item.warnings.length)) return "partial";
  if (qualityStatus === "healthy" || qualityStatus === "available") return stateStatus(String(item.state || ""));
  return stateStatus(String(item.state || ""));
}

function IndustryList({
  icon,
  items,
  title,
  total
}: {
  icon: JSX.Element;
  items: MarketTemperatureIndustry[];
  title: string;
  total: number;
}) {
  return (
    <article className="capability-section">
      <div className="section-header">
        <div>
          <span>共 {total} 个行业</span>
          <h3>{title}</h3>
        </div>
        {icon}
      </div>
      <div className="mini-list">
        {items.map((item, index) => (
          <article key={`${item.code || item.name || index}-${index}`}>
            <div className="section-header inline-section-header">
              <div>
                <span>{item.code || item.date || "industry"}</span>
                <strong>{item.name || `行业-${index + 1}`}</strong>
              </div>
              <StatusBadge status={stateStatus(item.state)} label={stateLabel(item.state)} />
            </div>
            <span>
              温度 {fixed(item.temperature, 1)} | MA20 {ratio(item.ma20_breadth)} | 涨跌 {item.advance_count ?? 0}/
              {item.decline_count ?? 0}
            </span>
            <p>
              样本 {item.stock_count ?? 0} | 成交额 {fixed(item.amount, 2)} | 市值权重 {ratio(item.market_cap_weight)}
            </p>
          </article>
        ))}
        {!items.length && <p className="muted">暂无行业排行。</p>}
      </div>
    </article>
  );
}

function heatmapIndustryKey(item: MarketTemperatureIndustry, index: number): string {
  return String(item.code || item.name || item.date || `industry-${index}`);
}

function presentIndustryFields(item: MarketTemperatureIndustry): MarketTemperatureIndustry {
  return Object.fromEntries(
    Object.entries(item).filter(([, value]) => value !== undefined && value !== null && value !== "")
  ) as MarketTemperatureIndustry;
}

function heatmapWeight(item: MarketTemperatureIndustry): number {
  const marketCapWeight = numeric(item.market_cap_weight);
  if (marketCapWeight !== null && marketCapWeight > 0) return marketCapWeight * 1000;
  const amount = numeric(item.amount);
  if (amount !== null && amount > 0) return amount;
  const stockCount = numeric(item.stock_count);
  if (stockCount !== null && stockCount > 0) return stockCount;
  return 1;
}

function heatmapTone(item: MarketTemperatureIndustry): string {
  const state = String(item.state || "").toLowerCase();
  if (["hot", "warm", "neutral", "cool", "cold"].includes(state)) return state;
  const temperature = numeric(item.temperature);
  if (temperature === null) return "unknown";
  if (temperature >= 80) return "hot";
  if (temperature >= 65) return "warm";
  if (temperature <= 20) return "cold";
  if (temperature <= 35) return "cool";
  return "neutral";
}

function heatmapTileStyle(item: MarketTemperatureIndustry, maxWeight: number): CSSProperties {
  const relative = maxWeight > 0 ? heatmapWeight(item) / maxWeight : 0;
  const grow = Math.max(1, Math.min(4, Math.round(relative * 4)));
  const minHeight = Math.max(96, Math.min(172, 92 + relative * 80));
  return {
    flex: `${grow} 1 ${grow >= 3 ? "220px" : "150px"}`,
    minHeight: `${minHeight}px`
  };
}

function IndustryHeatmap({
  coldIndustries,
  hotIndustries,
  industries
}: {
  coldIndustries: MarketTemperatureIndustry[];
  hotIndustries: MarketTemperatureIndustry[];
  industries: MarketTemperatureIndustry[];
}) {
  const items = useMemo(() => {
    const merged = new Map<string, MarketTemperatureIndustry>();
    [...industries, ...hotIndustries, ...coldIndustries].forEach((item, index) => {
      const key = heatmapIndustryKey(item, index);
      const previous = merged.get(key) || {};
      merged.set(key, { ...previous, ...presentIndustryFields(item) });
    });
    return Array.from(merged.values())
      .sort((left, right) => heatmapWeight(right) - heatmapWeight(left))
      .slice(0, 24);
  }, [coldIndustries, hotIndustries, industries]);
  const maxWeight = items.reduce((max, item) => Math.max(max, heatmapWeight(item)), 0);

  return (
    <section className="capability-section market-heatmap-section" data-testid="market-industry-heatmap">
      <div className="section-header">
        <div>
          <span>{items.length}/{industries.length || items.length} industries</span>
          <h3>行业热力图</h3>
        </div>
        <BarChart3 size={18} />
      </div>
      <div className="market-heatmap" role="list" aria-label="行业热力图">
        {items.map((item, index) => (
          <article
            className={`market-heatmap-tile heatmap-${heatmapTone(item)}`}
            key={`${heatmapIndustryKey(item, index)}-${index}`}
            role="listitem"
            style={heatmapTileStyle(item, maxWeight)}
          >
            <div className="market-heatmap-tile-header">
              <span>{item.code || item.date || "industry"}</span>
              <StatusBadge status={stateStatus(item.state)} label={stateLabel(item.state)} />
            </div>
            <strong>{item.name || `行业-${index + 1}`}</strong>
            <div className="market-heatmap-metrics">
              <span>
                <small>温度</small>
                {fixed(item.temperature, 1)}
              </span>
              <span>
                <small>MA20</small>
                {ratio(item.ma20_breadth)}
              </span>
              <span>
                <small>涨跌</small>
                {(item.advance_count ?? 0)}/{(item.decline_count ?? 0)}
              </span>
            </div>
          </article>
        ))}
        {!items.length && <p className="muted">暂无行业热力图数据。</p>}
      </div>
    </section>
  );
}

export function MarketTemperatureWorkspace({ endpoint, apiToken }: Props) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken }), [apiToken, endpoint]);
  const [snapshot, setSnapshot] = useState<MarketTemperatureSnapshot | null>(null);
  const [envelope, setEnvelope] = useState<(ToolEnvelope & { data: MarketTemperatureSnapshot }) | null>(null);
  const [cacheReadiness, setCacheReadiness] = useState<MarketTemperatureCacheReadiness | null>(null);
  const [cacheEnvelope, setCacheEnvelope] = useState<(ToolEnvelope & { data: MarketTemperatureCacheReadiness }) | null>(null);
  const [cacheHistory, setCacheHistory] = useState<MarketTemperatureCacheHistory | null>(null);
  const [cacheHistoryEnvelope, setCacheHistoryEnvelope] = useState<(ToolEnvelope & { data: MarketTemperatureCacheHistory }) | null>(null);
  const [industryHistory, setIndustryHistory] = useState<MarketTemperatureIndustryHistory | null>(null);
  const [industryHistoryEnvelope, setIndustryHistoryEnvelope] = useState<(ToolEnvelope & { data: MarketTemperatureIndustryHistory }) | null>(null);
  const [industryConstituents, setIndustryConstituents] = useState<MarketTemperatureIndustryConstituents | null>(null);
  const [industryConstituentsEnvelope, setIndustryConstituentsEnvelope] = useState<(ToolEnvelope & { data: MarketTemperatureIndustryConstituents }) | null>(null);
  const [forwardValidation, setForwardValidation] = useState<MarketTemperatureForwardValidation | null>(null);
  const [forwardValidationEnvelope, setForwardValidationEnvelope] = useState<(ToolEnvelope & { data: MarketTemperatureForwardValidation }) | null>(null);
  const [limit, setLimit] = useState("300");
  const [topN, setTopN] = useState("8");
  const [minBars, setMinBars] = useState("20");
  const [asOf, setAsOf] = useState("");
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh(event?: FormEvent) {
    event?.preventDefault();
    setBusy(true);
    const body: Record<string, unknown> = {
      limit: boundedInteger(limit, 300, 1, 1000),
      top_n: boundedInteger(topN, 8, 1, 20),
      min_bars: boundedInteger(minBars, 20, 2, 120),
      use_cache: true
    };
    if (asOf.trim()) body.as_of = asOf.trim();
    const readinessBody: Record<string, unknown> = { max_stale_days: 1 };
    if (asOf.trim()) readinessBody.as_of = asOf.trim();
    const historyBody: Record<string, unknown> = { limit: 10, include_snapshot: false };
    const industryHistoryBody: Record<string, unknown> = { limit: 10, top_n: 3, match_mode: "exact", include_source_chain: false };
    const forwardValidationBody: Record<string, unknown> = {
      limit: 120,
      horizons: [1, 3, 5],
      target_field: "benchmark_return",
      benchmark_code: "000300",
      min_samples: 3,
      include_samples: false
    };

    try {
      const [snapshotResult, readinessResult, historyResult, industryHistoryResult, forwardValidationResult] = await Promise.allSettled([
        api.marketTemperatureSnapshot(body),
        api.marketTemperatureCacheReadiness(readinessBody),
        api.marketTemperatureCacheHistory(historyBody),
        api.marketTemperatureIndustryHistory(industryHistoryBody),
        api.marketTemperatureForwardValidation(forwardValidationBody)
      ]);

      if (snapshotResult.status === "fulfilled") {
        const payload = snapshotResult.value;
        setEnvelope(payload);
        setSnapshot(payload.success && payload.data ? payload.data : null);
        setMessage(payload.success ? "MARKET_TEMPERATURE_LOADED" : payload.error || "MARKET_TEMPERATURE_FAILED");
      } else {
        setEnvelope(null);
        setSnapshot(null);
        setMessage(formatApiError(snapshotResult.reason));
      }

      if (readinessResult.status === "fulfilled") {
        setCacheEnvelope(readinessResult.value);
        setCacheReadiness(readinessResult.value.data);
      } else {
        setCacheEnvelope(null);
        setCacheReadiness({
          ready: false,
          status: "failed",
          read_only: true,
          blockers: [formatApiError(readinessResult.reason)]
        });
      }

      if (historyResult.status === "fulfilled") {
        setCacheHistoryEnvelope(historyResult.value);
        setCacheHistory(historyResult.value.data);
      } else {
        setCacheHistoryEnvelope(null);
        setCacheHistory({
          items: [],
          count: 0,
          limit: 10,
          include_snapshot: false,
          error: formatApiError(historyResult.reason)
        });
      }

      if (industryHistoryResult.status === "fulfilled") {
        setIndustryHistoryEnvelope(industryHistoryResult.value);
        setIndustryHistory(industryHistoryResult.value.data);
      } else {
        setIndustryHistoryEnvelope(null);
        setIndustryHistory({
          items: [],
          count: 0,
          limit: 10,
          top_n: 3,
          error: formatApiError(industryHistoryResult.reason)
        });
      }

      if (forwardValidationResult.status === "fulfilled") {
        setForwardValidationEnvelope(forwardValidationResult.value);
        setForwardValidation(forwardValidationResult.value.data);
      } else {
        setForwardValidationEnvelope(null);
        setForwardValidation({
          matrix: {},
          states: [],
          horizons: [1, 3, 5],
          count: 0,
          limit: 120,
          target_field: "weighted_pct_change",
          requested_target_field: "benchmark_return",
          benchmark_code: "000300",
          benchmark_status: "failed",
          error: formatApiError(forwardValidationResult.reason)
        });
      }

      const leadIndustry =
        snapshotResult.status === "fulfilled"
          ? snapshotResult.value.data?.hot_industries?.[0]?.name || snapshotResult.value.data?.hot_industries?.[0]?.code
          : undefined;
      if (leadIndustry) {
        try {
          const constituentsResult = await api.marketTemperatureIndustryConstituents({
            industry: leadIndustry,
            limit: 8,
            offset: 0,
            match_mode: "contains",
            include_source_chain: false
          });
          setIndustryConstituentsEnvelope(constituentsResult);
          setIndustryConstituents(constituentsResult.data);
        } catch (error) {
          setIndustryConstituentsEnvelope(null);
          setIndustryConstituents({
            items: [],
            count: 0,
            limit: 8,
            offset: 0,
            industry: String(leadIndustry),
            error: formatApiError(error)
          });
        }
      } else {
        setIndustryConstituentsEnvelope(null);
        setIndustryConstituents({
          items: [],
          count: 0,
          limit: 8,
          offset: 0,
          industry: ""
        });
      }
    } catch (error) {
      setEnvelope(null);
      setSnapshot(null);
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken]);

  const market = snapshot?.market || {};
  const quality = snapshot?.quality || {};
  const warnings = Array.isArray(quality.warnings) ? quality.warnings : [];
  const cacheBlockers = Array.isArray(cacheReadiness?.blockers) ? cacheReadiness.blockers : [];
  const cacheWarnings = Array.isArray(cacheReadiness?.warnings) ? cacheReadiness.warnings : [];
  const cacheIssues = [...cacheBlockers, ...cacheWarnings];
  const cacheStatus = cacheReadiness?.status || "not_loaded";
  const cacheHistoryItems = Array.isArray(cacheHistory?.items) ? cacheHistory.items : [];
  const industryHistoryItems = Array.isArray(industryHistory?.items) ? industryHistory.items : [];
  const industryConstituentItems = Array.isArray(industryConstituents?.items) ? industryConstituents.items : [];
  const forwardValidationMatrix = forwardValidation?.matrix || {};
  const forwardValidationStates = (forwardValidation?.states || Object.keys(forwardValidationMatrix)).slice(0, 4);
  const hotIndustries = snapshot?.hot_industries || [];
  const coldIndustries = snapshot?.cold_industries || [];
  const industries = snapshot?.industries || [];
  const statusForMessage = message.startsWith("MARKET_TEMPERATURE") ? message : quality.status || market.state || "not_loaded";

  return (
    <section className="quant-workspace" data-testid="market-temperature-workspace">
      <header className="quant-header">
        <div>
          <span>{snapshot?.contract_version || "market_temperature.v1"}</span>
          <h1>市场温度</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={statusForMessage} label={messageLabel(message)} />
          <button className="small-button" disabled={busy} onClick={() => refresh()} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="quant-body data-sync-layout">
        <form className="quant-params-panel" onSubmit={refresh}>
          <div className="section-header">
            <div>
              <span>只读快照</span>
              <h3>采样参数</h3>
            </div>
            <Thermometer size={18} />
          </div>
          <div className="quant-form-grid">
            <label className="field-row">
              <span>样本上限</span>
              <input aria-label="样本上限" inputMode="numeric" value={limit} onChange={(event) => setLimit(event.target.value)} />
            </label>
            <label className="field-row">
              <span>排行数量</span>
              <input aria-label="排行数量" inputMode="numeric" value={topN} onChange={(event) => setTopN(event.target.value)} />
            </label>
            <label className="field-row">
              <span>最少 K 线</span>
              <input aria-label="最少 K 线" inputMode="numeric" value={minBars} onChange={(event) => setMinBars(event.target.value)} />
            </label>
            <label className="field-row">
              <span>日期</span>
              <input aria-label="日期" placeholder="YYYY-MM-DD" value={asOf} onChange={(event) => setAsOf(event.target.value)} />
            </label>
          </div>
          <button className="primary-button" disabled={busy} type="submit">
            <RefreshCw size={15} className={busy ? "spin" : ""} />
            更新快照
          </button>

          <section className="capability-section compact-section">
            <div className="section-header">
              <div>
                <span>质量</span>
                <h3>数据质量</h3>
              </div>
              <StatusBadge status={quality.status === "healthy" ? "ready" : quality.status || "not_loaded"} label={qualityLabel(quality.status)} />
            </div>
            <div className="kv-grid">
              <span>交易日</span>
              <strong>{snapshot?.as_of || "-"}</strong>
              <span>趋势覆盖</span>
              <strong>{ratio(quality.trend_coverage)}</strong>
              <span>已加载</span>
              <strong>{compact(quality.loaded_stock_rows ?? quality.valid_stock_count)}</strong>
              <span>缺失 K 线</span>
              <strong>{compact(quality.missing_kline_rows ?? 0)}</strong>
            </div>
          </section>

          <section className="capability-section compact-section">
            <div className="section-header">
              <div>
                <span>缓存</span>
                <h3>缓存就绪</h3>
              </div>
              <StatusBadge status={readinessStatus(cacheReadiness)} label={qualityLabel(cacheStatus)} />
            </div>
            <div className="kv-grid">
              <span>就绪</span>
              <strong>{cacheReadiness ? (cacheReadiness.ready ? "是" : "否") : "-"}</strong>
              <span>日期</span>
              <strong>{cacheReadiness?.as_of || "-"}</strong>
              <span>滞后天数</span>
              <strong>{cacheReadiness?.staleness_days ?? "-"}</strong>
              <span>更新时间</span>
              <strong>{cacheReadiness?.cache?.updated_at || "-"}</strong>
            </div>
          </section>

          {!!cacheIssues.length && (
            <div className="notice warn">
              <Activity size={15} />
              {cacheIssues.join(", ")}
            </div>
          )}

          <section className="capability-section compact-section">
            <div className="section-header">
              <div>
                <span>{cacheHistory?.count ?? 0} 条缓存</span>
                <h3>缓存历史</h3>
              </div>
              <Database size={18} />
            </div>
            <div className="mini-list">
              {cacheHistoryItems.map((item, index) => (
                <article key={`${item.as_of || "cache"}-${index}`}>
                  <div className="section-header inline-section-header">
                    <div>
                      <span>{item.as_of || "-"}</span>
                      <strong>{fixed(item.market_temperature, 1)}</strong>
                    </div>
                    <StatusBadge status={historyItemStatus(item)} label={qualityLabel(item.quality_status || item.market_state || "unknown")} />
                  </div>
                  <span>
                    状态 {stateLabel(item.market_state)} | 样本 {compact(item.stock_count)} | 行业 {compact(item.industry_count)}
                  </span>
                  <p>{item.updated_at || item.created_at || "-"}</p>
                </article>
              ))}
              {!cacheHistoryItems.length && <p className="muted">暂无缓存的市场温度快照。</p>}
            </div>
          </section>

          <section className="capability-section compact-section">
            <div className="section-header">
              <div>
                <span>{industryHistory?.count ?? 0} 条记录</span>
                <h3>行业历史</h3>
              </div>
              <BarChart3 size={18} />
            </div>
            <div className="mini-list">
              {industryHistoryItems.slice(-6).map((item, index) => (
                <article key={`${item.as_of || "industry"}-${item.code || item.name || index}`}>
                  <div className="section-header inline-section-header">
                    <div>
                      <span>{item.as_of || "-"}</span>
                      <strong>{item.name || item.code || "行业"}</strong>
                    </div>
                    <StatusBadge status={industryHistoryItemStatus(item)} label={stateOrQualityLabel(item.state, item.quality_status)} />
                  </div>
                  <span>
                    温度 {fixed(item.temperature, 1)} | 市场 {fixed(item.market_temperature, 1)} | MA20 {ratio(item.ma20_breadth)}
                  </span>
                  <p>
                    样本 {compact(item.stock_count)} | 上涨/下跌 {item.advance_count ?? 0}/{item.decline_count ?? 0}
                  </p>
                </article>
              ))}
              {!industryHistoryItems.length && <p className="muted">暂无缓存的行业温度历史。</p>}
            </div>
          </section>

          <section className="capability-section compact-section">
            <div className="section-header">
              <div>
                <span>{forwardValidation?.benchmark_status ? qualityLabel(forwardValidation.benchmark_status) : `${forwardValidation?.snapshot_count ?? 0} 个快照`}</span>
                <h3>前向验证</h3>
              </div>
              <Activity size={18} />
            </div>
            <div className="mini-list">
              {forwardValidationStates.map((state) => {
                const cells = forwardValidationMatrix[state] || {};
                const oneDay = cells["1d"];
                const threeDay = cells["3d"];
                return (
                  <article key={state}>
                    <div className="section-header inline-section-header">
                      <div>
                        <span>{fieldLabel(forwardValidation?.target_field || "weighted_pct_change")}</span>
                        <strong>{stateLabel(state)}</strong>
                      </div>
                      <StatusBadge status={oneDay?.reliable ? "ready" : "partial"} label={`${oneDay?.sample_n ?? 0} 样本`} />
                    </div>
                    <span>
                      1日命中 {ratio(oneDay?.hit_rate)} | 均值 {pct(oneDay?.avg_forward_return)}
                    </span>
                    <p>3日命中 {ratio(threeDay?.hit_rate)} | 均值 {pct(threeDay?.avg_forward_return)}</p>
                  </article>
                );
              })}
              {!forwardValidationStates.length && <p className="muted">暂无前向验证样本。</p>}
            </div>
          </section>

          <section className="capability-section compact-section">
            <div className="section-header">
              <div>
                <span>{industryConstituents?.count ?? 0} 只股票</span>
                <h3>行业成分股</h3>
              </div>
              <Database size={18} />
            </div>
            <div className="mini-list">
              {industryConstituentItems.map((item: MarketTemperatureIndustryConstituent, index) => (
                <article key={`${item.code || "stock"}-${index}`}>
                  <div className="section-header inline-section-header">
                    <div>
                      <span>{item.code || "-"}</span>
                      <strong>{item.name || item.code || "股票"}</strong>
                    </div>
                    <StatusBadge status={item.market_cap ? "ready" : "not_loaded"} label={item.market || item.sector || "local"} />
                  </div>
                  <span>
                    市值 {fixed(item.market_cap, 1)} | PE {fixed(item.pe_ratio, 1)} | PB {fixed(item.pb_ratio, 2)}
                  </span>
                  <p>
                    {item.industry || item.sector || "-"} | 上市 {item.list_date || "-"}
                  </p>
                </article>
              ))}
              {!industryConstituentItems.length && <p className="muted">暂无本地行业成分股。</p>}
            </div>
          </section>

          {!!warnings.length && (
            <div className="notice warn">
              <Activity size={15} />
              {warnings.join(", ")}
            </div>
          )}
        </form>

        <section className="quant-center-panel">
          <div className="diagnostics-summary wide">
            <MetricCard label="市场温度" value={fixed(market.temperature, 1)} status={temperatureStatus(market.temperature)} />
            <MetricCard label="MA20 宽度" value={ratio(market.ma20_breadth)} status={quality.status || "not_loaded"} />
            <MetricCard label="上涨 / 下跌" value={`${market.advance_count ?? 0}/${market.decline_count ?? 0}`} status={stateStatus(market.state)} />
            <MetricCard label="样本" value={market.stock_count ?? 0} status={market.stock_count ? "ready" : "not_loaded"} />
          </div>

          <IndustryHeatmap coldIndustries={coldIndustries} hotIndustries={hotIndustries} industries={industries} />

          <section className="capability-grid two">
            <IndustryList icon={<BarChart3 size={18} />} items={hotIndustries} title="热行业" total={industries.length} />
            <IndustryList icon={<Database size={18} />} items={coldIndustries} title="冷行业" total={industries.length} />
          </section>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>{snapshot?.source_chain?.join(" / ") || "source_chain"}</span>
                <h3>市场宽度</h3>
              </div>
              <StatusBadge status={stateStatus(market.state)} label={stateLabel(market.state)} />
            </div>
            <div className="diagnostics-summary wide">
              <MetricCard label="均涨跌" value={pct(market.avg_pct_change)} status={stateStatus(market.state)} />
              <MetricCard label="加权涨跌" value={pct(market.weighted_pct_change)} status={stateStatus(market.state)} />
              <MetricCard label="上涨占比" value={ratio(market.advance_ratio)} status={stateStatus(market.state)} />
              <MetricCard label="行业数" value={quality.industry_count ?? industries.length} status={industries.length ? "ready" : "not_loaded"} />
            </div>
          </section>

          <RawEvidencePanel
            title="市场温度原始证据"
            value={{
              envelope,
              snapshot,
              cacheEnvelope,
              cacheReadiness,
              cacheHistoryEnvelope,
              cacheHistory,
              industryHistoryEnvelope,
              industryHistory,
              industryConstituentsEnvelope,
              industryConstituents,
              forwardValidationEnvelope,
              forwardValidation
            }}
          />
        </section>
      </div>
    </section>
  );
}

export default MarketTemperatureWorkspace;
