type MockEnvelope = (tool: string, data: unknown, success?: boolean) => unknown;

type StockDataSource = Record<string, unknown>;

const stockDataSourcePresets: StockDataSource[] = [
  {
    provider: "akshare",
    label: "AKShare / AKTools",
    markets: ["CN", "HK", "US", "FX", "Futures", "Options"],
    categories: ["quote", "kline", "fundamental", "macro", "news"],
    auth_type: "none",
    default_base_url: "",
    required_fields: [],
    optional_fields: ["base_url", "timeout_seconds", "user_agent"],
    env_keys: ["AKSHARE_MCP_SQLITE_PATH", "AIASK_SQLITE_PATH"],
    documentation_url: "https://akshare.akfamily.xyz/introduction.html",
    note: "开源数据采集器；也可以配置 AKTools HTTP base_url。"
  },
  {
    provider: "tushare",
    label: "Tushare Pro",
    markets: ["CN"],
    categories: ["quote", "kline", "fundamental", "calendar", "finance"],
    auth_type: "token",
    default_base_url: "http://api.tushare.pro",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "timeout_seconds", "rate_limit_per_minute", "fields"],
    env_keys: ["TUSHARE_TOKEN"],
    documentation_url: "https://tushare.pro/document/1?doc_id=40",
    note: "Tushare Pro HTTP API；部分接口需要积分或权限。"
  },
  {
    provider: "tdx",
    label: "TongDaXin HQ",
    markets: ["CN"],
    categories: ["quote", "kline", "local_vipdoc"],
    auth_type: "host_port",
    default_host: "119.147.212.81",
    default_port: 7709,
    required_fields: ["host", "port"],
    optional_fields: ["timeout_seconds", "local_vipdoc_path"],
    env_keys: ["TDX_SERVER_IP", "TDX_SERVER_PORT", "TDX_LOCAL_ONLY", "TDX_VIPDOC_PATH"],
    documentation_url: null,
    note: "通达信行情 TCP 或本地 vipdoc 数据源；只读行情无需 API Key。"
  },
  {
    provider: "finnhub",
    label: "Finnhub",
    markets: ["US", "Global"],
    categories: ["quote", "kline", "fundamental", "news", "economic"],
    auth_type: "token",
    default_base_url: "https://finnhub.io/api/v1",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "symbol", "timeout_seconds", "rate_limit_per_minute"],
    env_keys: ["FINNHUB_API_KEY", "FINNHUB_TOKEN"],
    documentation_url: "https://finnhub.io/docs/api/introduction",
    note: "Token REST API；测试会使用示例股票代码。"
  },
  {
    provider: "duckduckgo",
    label: "DuckDuckGo HTML Search",
    markets: ["Global"],
    categories: ["web_search", "news", "research"],
    auth_type: "none",
    default_base_url: "https://duckduckgo.com/html/",
    required_fields: [],
    optional_fields: ["base_url", "timeout_seconds", "rate_limit_per_minute"],
    env_keys: [],
    documentation_url: "https://duckduckgo.com/",
    note: "无密钥公开搜索 fallback。"
  },
  {
    provider: "tavily",
    label: "Tavily Search",
    markets: ["Global"],
    categories: ["web_search", "deep_research", "news", "research"],
    auth_type: "bearer",
    default_base_url: "https://api.tavily.com",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "timeout_seconds", "search_depth"],
    env_keys: ["TAVILY_API_KEY"],
    documentation_url: "https://docs.tavily.com/documentation/api-reference/endpoint/search",
    note: "深度联网搜索 API；保存后可通过 agent_web_search 调用。"
  },
  {
    provider: "brave_search",
    label: "Brave Search API",
    markets: ["Global"],
    categories: ["web_search", "news", "research"],
    auth_type: "subscription_token",
    default_base_url: "https://api.search.brave.com/res/v1",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "timeout_seconds", "country", "search_lang"],
    env_keys: ["BRAVE_SEARCH_API_KEY", "BRAVE_SEARCH_SUBSCRIPTION_TOKEN"],
    documentation_url: "https://api-dashboard.search.brave.com/app/documentation/web-search/get-started",
    note: "使用 X-Subscription-Token 的搜索 API。"
  },
  {
    provider: "serpapi",
    label: "SerpApi",
    markets: ["Global"],
    categories: ["web_search", "search_engine_results", "news", "research"],
    auth_type: "api_key",
    default_base_url: "https://serpapi.com/search.json",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "engine", "location"],
    env_keys: ["SERPAPI_API_KEY"],
    documentation_url: "https://serpapi.com/search-api",
    note: "搜索引擎结果 API；适合 Google/Bing SERP。"
  },
  {
    provider: "exa",
    label: "Exa Search",
    markets: ["Global"],
    categories: ["web_search", "neural_search", "research"],
    auth_type: "api_key_header",
    default_base_url: "https://api.exa.ai",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "search_type"],
    env_keys: ["EXA_API_KEY"],
    documentation_url: "https://docs.exa.ai/reference/search",
    note: "神经/相似度搜索 API。"
  }
];

let mockStockDataSources: StockDataSource[] = [
  {
    id: "mock:akshare",
    provider: "akshare",
    name: "Mock AKShare 本地源",
    enabled: true,
    priority: 10,
    base_url: "",
    source: "mock",
    status: "ready",
    configured: true,
    categories: ["quote", "kline", "fundamental"],
    markets: ["CN", "HK", "US"],
    timeout_seconds: 8,
    notes: "Mock 默认数据源"
  },
  {
    id: "mock:tushare",
    provider: "tushare",
    name: "Mock Tushare Pro",
    enabled: true,
    priority: 20,
    base_url: "http://api.tushare.pro",
    api_key: "mock-tushare-token",
    source: "mock",
    status: "ready",
    configured: true,
    categories: ["quote", "kline", "fundamental"],
    markets: ["CN"],
    symbol: "600519",
    timeout_seconds: 8,
    rate_limit_per_minute: 120,
    notes: "用于前端连通性验证的脱敏条目"
  },
  {
    id: "mock:duckduckgo",
    provider: "duckduckgo",
    name: "DuckDuckGo fallback",
    enabled: true,
    priority: 50,
    base_url: "https://duckduckgo.com/html/",
    source: "mock",
    status: "ready",
    configured: true,
    categories: ["web_search", "research"],
    markets: ["Global"]
  }
];

function requiredFields(preset: StockDataSource | undefined): string[] {
  const fields = preset?.required_fields;
  return Array.isArray(fields) ? fields.map(String) : [];
}

export function mockDesktopDataStatus(envelope: MockEnvelope) {
  return {
    object: "aiask.desktop_data_status",
    status: "ready",
    database: {
      backend: "sqlite",
      path: "mock://aiask/akshare.sqlite3",
      configured: true,
      writable: true,
      sources: ["tdx_local", "tushare", "akshare"]
    },
    freshness: {
      "600519": { status: "fresh", source: "tdx_local" },
      "000001": { status: "fresh", source: "tushare" }
    },
    quality_gate: envelope("agent_quant_data_gate", { status: "passed", missing: [], stale: [] }),
    data_validation: { status: "passed" },
    codes: ["600519", "000001"],
    max_stale_days: 5,
    missing_count: 0,
    stale_count: 0,
    secrets_redacted: true
  };
}

export function mockDesktopDataSyncPlan(body: StockDataSource, dataStatus: unknown) {
  return {
    object: "aiask.desktop_data_sync_plan",
    status: "ready",
    data_status: dataStatus,
    intent_request: {
      action: "data_sync.sync",
      params: {
        codes: body.codes || ["600519"],
        task_type: body.task_type || "kline",
        period: body.period || "daily",
        limit: body.task_type === "market_temperature_snapshot_cache" ? 1000 : undefined,
        top_n: body.task_type === "market_temperature_snapshot_cache" ? 20 : undefined,
        min_bars: body.task_type === "market_temperature_snapshot_cache" ? 20 : undefined
      },
      rationale: "Mock sync plan approval."
    },
    side_effect: { level: "stateful", confirmation_required: true },
    secrets_redacted: true
  };
}

function stockDataSourceConfigured(source: StockDataSource, presets: StockDataSource[]): boolean {
  const preset = presets.find((item) => item.provider === source.provider);
  const required = requiredFields(preset);
  if (!required.length) return true;
  return required.every((field) => {
    if (field === "api_key") return Boolean(String(source.api_key || source.token || "").trim());
    if (field === "port") return Number(source.port || 0) > 0;
    return Boolean(String(source[field] || "").trim());
  });
}

function redactStockDataSource(source: StockDataSource, presets: StockDataSource[]): StockDataSource {
  const configured = stockDataSourceConfigured(source, presets);
  const enabled = source.enabled !== false;
  return {
    ...source,
    api_key: source.api_key ? "[redacted]" : "",
    token: source.token ? "[redacted]" : "",
    password: source.password ? "[redacted]" : "",
    api_key_configured: Boolean(String(source.api_key || source.token || source.password || "").trim()),
    configured,
    enabled,
    status: enabled ? configured ? "ready" : "unconfigured" : "disabled",
    secrets_redacted: true
  };
}

function mergeStockDataSourceDraft(
  base: StockDataSource | undefined,
  draft: StockDataSource
): StockDataSource {
  const merged: StockDataSource = { ...(base || {}) };
  for (const [key, value] of Object.entries(draft)) {
    const lowered = key.toLowerCase();
    const secretField = lowered.includes("api_key") || lowered.includes("token") || lowered.includes("secret") || lowered.includes("password");
    if (secretField && (value === null || value === "" || value === undefined) && base) continue;
    merged[key] = value;
  }
  return merged;
}

export function mockStockDataSourcesStatus(presets: StockDataSource[], sources: StockDataSource[]) {
  const redactedSources = sources.map((source) => redactStockDataSource(source, presets));
  return {
    object: "aiask.stock_data_sources",
    status: redactedSources.some((source) => source.status === "ready") ? "ready" : "unconfigured",
    configured_count: redactedSources.filter((source) => source.configured).length,
    ready_count: redactedSources.filter((source) => source.status === "ready").length,
    presets,
    sources: redactedSources,
    config_path: "mock://aiask/stock_data_sources.json",
    config_source: { source: "desktop.mockApi", loaded: true },
    secrets_redacted: true
  };
}

export function mockSaveStockDataSource(
  presets: StockDataSource[],
  sources: StockDataSource[],
  body: StockDataSource
): { payload: StockDataSource; sources: StockDataSource[] } {
  const provider = String(body.provider || "").trim();
  const preset = presets.find((item) => item.provider === provider);
  if (!provider || !preset) {
    return {
      payload: { object: "aiask.stock_data_source", source: { provider, status: "unsupported", configured: false }, secrets_redacted: true },
      sources
    };
  }
  const id = String(body.id || "").trim() || `mock:${provider}:${Date.now()}`;
  const existing = sources.find((source) => source.id === id);
  const next: StockDataSource = {
    ...(existing || {}),
    ...body,
    id,
    provider,
    name: String(body.name || existing?.name || preset.label),
    enabled: body.enabled !== false,
    updated_at: "2026-06-12T00:00:00Z",
    source: "mock"
  };
  if (!body.api_key && existing?.api_key) next.api_key = existing.api_key;
  if (!body.password && existing?.password) next.password = existing.password;
  const nextSources = existing
    ? sources.map((source) => source.id === id ? next : source)
    : [next, ...sources];
  return {
    payload: { object: "aiask.stock_data_source", source: redactStockDataSource(next, presets), secrets_redacted: true },
    sources: nextSources
  };
}

export function mockTestStockDataSource(
  presets: StockDataSource[],
  sources: StockDataSource[],
  body: StockDataSource
) {
  const inline = body.source && typeof body.source === "object" && !Array.isArray(body.source)
    ? body.source as StockDataSource
    : body;
  const inlineId = String(inline.id || body.id || "").trim();
  const stored = inlineId
    ? sources.find((item) => item.id === inlineId)
    : undefined;
  const source = body.source && typeof body.source === "object" && !Array.isArray(body.source)
    ? mergeStockDataSourceDraft(stored, inline)
    : String(inline.provider || "").trim()
      ? inline
      : sources.find((item) => item.id === body.id) || sources.find((item) => item.provider === body.provider) || {};
  const provider = String(source.provider || body.provider || "").trim();
  const configured = stockDataSourceConfigured(source, presets);
  const enabled = source.enabled !== false;
  const success = Boolean(provider && configured && enabled);
  return {
    object: "aiask.stock_data_source_test",
    provider,
    mode: String(body.mode || "connectivity"),
    success,
    status: success ? "ready" : enabled ? "unconfigured" : "disabled",
    configured,
    latency_ms: 8,
    sample_count: success ? 3 : 0,
    http_status: provider && !["akshare", "tdx"].includes(provider) ? 200 : undefined,
    error_code: success ? undefined : "MOCK_SOURCE_UNCONFIGURED",
    error: success ? null : "Mock 数据源缺少必填字段或已停用。",
    source: redactStockDataSource(source, presets),
    secrets_redacted: true
  };
}

export function mockStockDataSourcesStatusData() {
  return mockStockDataSourcesStatus(stockDataSourcePresets, mockStockDataSources);
}

export function mockSaveStockDataSourceData(body: StockDataSource) {
  const result = mockSaveStockDataSource(stockDataSourcePresets, mockStockDataSources, body);
  mockStockDataSources = result.sources;
  return result.payload;
}

export function mockTestStockDataSourceData(body: StockDataSource) {
  return mockTestStockDataSource(stockDataSourcePresets, mockStockDataSources, body);
}
