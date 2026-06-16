export function quantPresetsPayload() {
  return {
    object: "aiask.quant_presets",
    data_status: {
      status: "unconfigured",
      database: {
        backend: "sqlite",
        path: "/tmp/akshare_mcp.sqlite3",
        configured: true,
        writable: false,
        sources: ["default"],
        required_for_full_quant: true,
        setup_hint: "Configure a writable SQLite database path to enable full quant research."
      }
    },
    templates: [
      {
        id: "balanced_factor_research",
        label: "Balanced factor research",
        universe: ["600519", "000001"],
        benchmark: "000300",
        factors: ["momentum"],
        rebalance_frequency: "monthly",
        cost_bps: 3,
        slippage_bps: 1,
        risk_limits: { max_weight: 0.35, var_limit: 0.08 }
      }
    ],
    factor_library: ["momentum", "volatility", "value"],
    risk_defaults: { lookback_days: 252, max_weight: 0.35 },
    disclaimer: "NOT_INVESTMENT_ADVICE: This research artifact is decision support only and is not a trading instruction."
  };
}

export function desktopDataStatusPayload(codes = ["600519", "000001", "000858"], maxStaleDays = 5) {
  return {
    object: "aiask.desktop_data_status",
    status: "partial",
    database: {
      backend: "sqlite",
      path: "/tmp/akshare_mcp.sqlite3",
      configured: true,
      writable: true,
      sources: ["akshare_fixture", "tdx_fixture"],
      setup_hint: "E2E mock database is writable."
    },
    presets: quantPresetsPayload(),
    quality_gate: {
      success: false,
      data: {
        status: "partial",
        checked: codes,
        missing: ["000858"],
        stale: ["000001"],
        max_stale_days: maxStaleDays
      },
      error: null,
      error_code: null
    },
    data_validation: { status: "partial", row_count: 1888 },
    freshness: {
      "600519": { status: "fresh", last_date: "2026-05-20" },
      "000001": { status: "stale", last_date: "2026-05-10" },
      "000858": { status: "missing", last_date: null }
    },
    codes,
    max_stale_days: maxStaleDays,
    missing_count: 1,
    stale_count: 1,
    secrets_redacted: true
  };
}

const stockDataSourcePresets = [
  {
    provider: "akshare",
    label: "AKShare / AKTools",
    markets: ["CN", "HK", "US"],
    categories: ["quote", "kline", "fundamental"],
    auth_type: "none",
    default_base_url: "",
    required_fields: [],
    optional_fields: ["base_url", "timeout_seconds"],
    documentation_url: "https://akshare.akfamily.xyz/introduction.html",
    note: "Open data source for local market data checks."
  },
  {
    provider: "tushare",
    label: "Tushare Pro",
    markets: ["CN"],
    categories: ["quote", "kline", "fundamental"],
    auth_type: "token",
    default_base_url: "http://api.tushare.pro",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "timeout_seconds", "rate_limit_per_minute"],
    documentation_url: "https://tushare.pro/document/1?doc_id=40",
    note: "Token based China market data source."
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
    documentation_url: null,
    note: "Read-only quote host or local vipdoc source."
  },
  {
    provider: "duckduckgo",
    label: "DuckDuckGo HTML Search",
    markets: ["Global"],
    categories: ["web_search", "research"],
    auth_type: "none",
    default_base_url: "https://duckduckgo.com/html/",
    required_fields: [],
    optional_fields: ["base_url", "timeout_seconds"],
    documentation_url: "https://duckduckgo.com/",
    note: "No-key web search fallback."
  },
  {
    provider: "tavily",
    label: "Tavily Search",
    markets: ["Global"],
    categories: ["web_search", "deep_research"],
    auth_type: "bearer",
    default_base_url: "https://api.tavily.com",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "search_depth"],
    documentation_url: "https://docs.tavily.com/documentation/api-reference/endpoint/search",
    note: "Deep web search API."
  }
];

export function redactStockDataSource(source: Record<string, unknown>): Record<string, unknown> {
  return {
    ...source,
    api_key: source.api_key ? "[redacted]" : "",
    password: source.password ? "[redacted]" : "",
    token: source.token ? "[redacted]" : "",
    api_key_configured: Boolean(source.api_key || source.token || source.password),
    configured: source.configured ?? true,
    status: source.enabled === false ? "disabled" : source.status || "ready",
    secrets_redacted: true
  };
}

export function mergeStockDataSourceDraft(base: Record<string, unknown> | undefined, draft: Record<string, unknown>): Record<string, unknown> {
  const merged = { ...(base || {}) };
  for (const [key, value] of Object.entries(draft)) {
    const lowered = key.toLowerCase();
    const secretField = lowered.includes("api_key") || lowered.includes("token") || lowered.includes("secret") || lowered.includes("password");
    if (secretField && (value === null || value === "" || value === undefined) && base) continue;
    merged[key] = value;
  }
  return merged;
}

export function stockDataSourcesPayload(sources: Array<Record<string, unknown>>) {
  const redactedSources = sources.map(redactStockDataSource);
  return {
    object: "aiask.stock_data_sources",
    status: "ready",
    configured_count: redactedSources.filter((source) => source.configured !== false).length,
    ready_count: redactedSources.filter((source) => source.status === "ready").length,
    presets: stockDataSourcePresets,
    sources: redactedSources,
    config_path: "/tmp/aiask-stock-data-sources.json",
    config_source: { source: "e2e_fixture", loaded: true },
    secrets_redacted: true
  };
}

export function dataSyncPlanPayload(body: Record<string, unknown> = {}) {
  const codes = Array.isArray(body.codes) ? body.codes.map(String) : ["600519", "000001", "000858"];
  const maxStaleDays = Number(body.max_stale_days || 5);
  const taskType = String(body.task_type || "kline");
  const period = String(body.period || "daily");
  return {
    object: "aiask.desktop_data_sync_plan",
    status: "ready",
    data_status: desktopDataStatusPayload(codes, maxStaleDays),
    intent_request: {
      action: "data_sync.run_once",
      params: { codes, max_stale_days: maxStaleDays, task_type: taskType, period },
      rationale: "E2E mock sync plan approval."
    },
    commands: [{ command: "sync", task_type: taskType, period, codes }],
    side_effect: { level: "stateful", confirmation_required: true },
    secrets_redacted: true
  };
}

export function stockRadarStatusPayload() {
  return {
    status: "ready",
    counts: { alert: 1, watch: 1, observe: 0, reject: 0 },
    degraded_flags: [],
    latest_run: {
      run_id: "radar_e2e_20260608",
      status: "completed",
      started_at: "2026-06-08T14:30:00+08:00",
      finished_at: "2026-06-08T14:31:00+08:00"
    },
    digest_preview: "企微 / Telegram 预览：北方稀土、工业富联进入观察池，不含交易指令。"
  };
}

export function stockRadarCandidatesPayload(tier = "") {
  const candidates = [
    {
      candidate_id: "radar_candidate_e2e_001",
      run_id: "radar_e2e_20260608",
      symbol: "600111",
      stock_name: "北方稀土",
      tier: "alert",
      radar_score: 84.5,
      event_id: "radar_event_e2e_001",
      event_type: "policy_shock",
      direction: "bullish",
      summary: "稀土出口管制事件触发观察池候选，证据链来自政策新闻与主题暴露。",
      source_doc_uids: ["doc_radar_policy_001", "doc_radar_theme_002"],
      source_chain: [{ uid: "doc_radar_policy_001", kind: "news", title: "稀土出口管制" }],
      extraction: { confidence: 0.82, event_type: "policy_shock" },
      confirmations: { cross_source: true, theme_exposure: "critical_minerals" },
      risk_flags: []
    },
    {
      candidate_id: "radar_candidate_e2e_002",
      run_id: "radar_e2e_20260608",
      symbol: "601138",
      stock_name: "工业富联",
      tier: "watch",
      radar_score: 66.0,
      event_id: "radar_event_e2e_002",
      event_type: "supply_chain",
      direction: "neutral",
      summary: "供应链文本触发观察级候选，仍需更多确认。",
      source_doc_uids: ["doc_radar_supply_001"],
      source_chain: [{ uid: "doc_radar_supply_001", kind: "filing", title: "供应链观察" }],
      extraction: { confidence: 0.64, event_type: "supply_chain" },
      confirmations: { cross_source: false },
      risk_flags: ["needs_confirmation"]
    }
  ];
  const filtered = tier ? candidates.filter((candidate) => candidate.tier === tier) : candidates;
  return { status: "ready", candidates: filtered, count: filtered.length };
}

export function stockRadarDigestPayload() {
  return {
    status: "ready",
    digest_preview: "企微 / Telegram 预览：北方稀土进入警报观察，工业富联进入观察列表。仅为观察池信息，不含买卖指令。",
    channels: ["wecom", "telegram"],
    push_logs: [{ push_id: "radar_push_e2e", channel: "preview", status: "preview", candidate_count: 2 }]
  };
}

export function marketTemperatureSnapshotPayload(body: Record<string, unknown> = {}) {
  const asOf = String(body.as_of || "2026-06-08");
  const industries = [
    {
      code: "801750",
      name: "计算机",
      stock_count: 48,
      ma20_breadth: 0.7708,
      advance_count: 34,
      decline_count: 11,
      amount: 428.35,
      market_cap_weight: 0.118,
      temperature: 74.42,
      state: "warm"
    },
    {
      code: "801080",
      name: "电子",
      stock_count: 62,
      ma20_breadth: 0.738,
      advance_count: 41,
      decline_count: 18,
      amount: 512.9,
      market_cap_weight: 0.146,
      temperature: 71.84,
      state: "warm"
    },
    {
      code: "801780",
      name: "银行",
      stock_count: 34,
      ma20_breadth: 0.5294,
      advance_count: 17,
      decline_count: 15,
      amount: 216.72,
      market_cap_weight: 0.201,
      temperature: 53.27,
      state: "neutral"
    },
    {
      code: "801730",
      name: "电力设备",
      stock_count: 55,
      ma20_breadth: 0.25,
      advance_count: 15,
      decline_count: 37,
      amount: 276.54,
      market_cap_weight: 0.133,
      temperature: 27.34,
      state: "cool"
    }
  ];
  return {
    contract_version: "market_temperature.v1",
    as_of: asOf,
    market: {
      stock_count: 300,
      trend_known_count: 296,
      ma20_breadth: 0.5473,
      advance_count: 151,
      decline_count: 136,
      flat_count: 13,
      advance_ratio: 0.5033,
      avg_pct_change: 0.12,
      weighted_pct_change: 0.18,
      temperature: 55.84,
      state: "neutral"
    },
    industries,
    hot_industries: industries.slice(0, 3),
    cold_industries: industries.slice().reverse(),
    quality: {
      status: "healthy",
      warnings: [],
      trend_coverage: 0.9867,
      loaded_stock_rows: 300,
      missing_kline_rows: 0,
      industry_count: industries.length
    },
    source_chain: ["desktop.e2e", "market_temperature.fixture"]
  };
}

export function marketTemperatureCacheReadinessPayload(body: Record<string, unknown> = {}) {
  return {
    ready: true,
    status: "fresh",
    read_only: true,
    as_of: String(body.as_of || "2026-06-08"),
    max_stale_days: 1,
    staleness_days: 1,
    quality_status: "healthy",
    degraded: false,
    warnings: [],
    blockers: [],
    cache: { updated_at: "2026-06-08T15:05:00Z", source: "market_temperature_snapshots" },
    source_chain: ["desktop.e2e", "cache_readiness"]
  };
}

export function marketTemperatureCacheHistoryPayload() {
  return {
    items: [
      { as_of: "2026-06-08", market_temperature: 55.84, market_state: "neutral", stock_count: 300, industry_count: 4, quality_status: "healthy", warnings: [], updated_at: "2026-06-08T15:05:00Z" },
      { as_of: "2026-06-07", market_temperature: 47.2, market_state: "neutral", stock_count: 298, industry_count: 4, quality_status: "healthy", warnings: [], updated_at: "2026-06-07T15:04:00Z" },
      { as_of: "2026-06-06", market_temperature: 32.4, market_state: "cool", stock_count: 294, industry_count: 4, quality_status: "degraded", warnings: ["partial data"], updated_at: "2026-06-06T15:03:00Z" }
    ],
    count: 3,
    limit: 10,
    include_snapshot: false,
    source_chain: ["desktop.e2e", "cache_history"]
  };
}

export function marketTemperatureIndustryHistoryPayload() {
  return {
    items: [
      { as_of: "2026-06-07", code: "801750", name: "计算机", temperature: 71.4, state: "warm", ma20_breadth: 0.771, advance_count: 34, decline_count: 11, stock_count: 48, market_temperature: 47.2, market_state: "neutral", quality_status: "healthy", warnings: [], updated_at: "2026-06-07T15:04:00Z" },
      { as_of: "2026-06-07", code: "801780", name: "银行", temperature: 50.3, state: "neutral", ma20_breadth: 0.529, advance_count: 17, decline_count: 15, stock_count: 34, market_temperature: 47.2, market_state: "neutral", quality_status: "healthy", warnings: [], updated_at: "2026-06-07T15:04:00Z" },
      { as_of: "2026-06-08", code: "801750", name: "计算机", temperature: 74.4, state: "warm", ma20_breadth: 0.771, advance_count: 34, decline_count: 11, stock_count: 48, market_temperature: 55.8, market_state: "neutral", quality_status: "healthy", warnings: [], updated_at: "2026-06-08T15:05:00Z" },
      { as_of: "2026-06-08", code: "801780", name: "银行", temperature: 53.3, state: "neutral", ma20_breadth: 0.529, advance_count: 17, decline_count: 15, stock_count: 34, market_temperature: 55.8, market_state: "neutral", quality_status: "healthy", warnings: [], updated_at: "2026-06-08T15:05:00Z" }
    ],
    count: 4,
    limit: 10,
    top_n: 3,
    include_source_chain: false,
    source_chain: ["desktop.e2e", "industry_history"]
  };
}

export function marketTemperatureIndustryConstituentsPayload(body: Record<string, unknown> = {}) {
  const industry = String(body.industry || "计算机");
  return {
    items: [
      { code: "300001", name: "计算机 Leader", industry, sector: industry, market: "SZ", market_cap: 1820.5, pe_ratio: 24.1, pb_ratio: 3.2, list_date: "2010-01-08" },
      { code: "600001", name: "计算机 Growth", industry, sector: industry, market: "SH", market_cap: 1302.4, pe_ratio: 19.7, pb_ratio: 2.8, list_date: "2008-04-21" }
    ],
    count: 2,
    total_matches: 2,
    limit: 8,
    offset: 0,
    industry,
    match_mode: "contains",
    include_source_chain: false,
    source_chain: ["desktop.e2e", "industry_constituents"]
  };
}

export function marketTemperatureForwardValidationPayload() {
  return {
    matrix: {
      warm: {
        "1d": { sample_n: 18, direction_hits: 12, reliable: true, avg_forward_return: 0.42, hit_rate: 0.667 },
        "3d": { sample_n: 16, direction_hits: 10, reliable: true, avg_forward_return: 0.76, hit_rate: 0.625 }
      },
      neutral: {
        "1d": { sample_n: 24, direction_hits: 15, reliable: true, avg_forward_return: 0.06, hit_rate: 0.625 },
        "3d": { sample_n: 22, direction_hits: 12, reliable: true, avg_forward_return: 0.18, hit_rate: 0.545 }
      },
      cool: {
        "1d": { sample_n: 14, direction_hits: 8, reliable: true, avg_forward_return: -0.31, hit_rate: 0.571 },
        "3d": { sample_n: 12, direction_hits: 8, reliable: true, avg_forward_return: -0.64, hit_rate: 0.667 }
      }
    },
    states: ["warm", "neutral", "cool"],
    horizons: [1, 3, 5],
    count: 56,
    snapshot_count: 30,
    limit: 120,
    target_field: "benchmark_return",
    requested_target_field: "benchmark_return",
    benchmark_code: "000300",
    benchmark_status: "available",
    benchmark_bar_count: 76,
    min_samples: 3,
    include_samples: false,
    samples: [],
    source_chain: ["desktop.e2e", "forward_validation"]
  };
}

export function factoryEventListPayload() {
  return {
    events: [
      {
        event_id: "evt_e2e_001",
        event_name: "稀土出口管制(e2e)",
        event_type: "policy_shock",
        event_source: "manual",
        status: "active",
        direction: "bullish",
        intensity: 0.85,
        confidence: 0.7,
        primary_themes: ["critical_minerals"],
        operator_id: "operator_e2e",
        approver_id: "approver_e2e",
        created_at: "2026-06-08T14:20:00+08:00"
      }
    ],
    count: 1
  };
}

export function factoryEventPreviewTasksPayload(eventId = "evt_e2e_001") {
  return {
    event_id: eventId,
    impacts: [{ theme_code: "critical_minerals", depth: 0, magnitude: 0.85 }],
    candidate_symbols: ["600111", "600259"],
    target_count: 2,
    warnings: [],
    preview_mode: "real_bfs"
  };
}

export function factoryEventLineagePayload(eventId = "evt_e2e_001") {
  return {
    lineage: [
      {
        lineage_id: 1,
        event_id: eventId,
        event_name: "稀土出口管制(e2e)",
        event_status: "active",
        task_id: "event_evt_e2e_001_critical_minerals",
        theme_code: "critical_minerals",
        impact_direction: "positive",
        impact_magnitude: 0.85,
        target_symbols: ["600111", "600259"],
        target_count: 2,
        breadth_resolved: "narrow",
        generated_at: "2026-06-08T14:22:00+08:00",
        gate_1_passed: 1,
        strategies_submitted: 1
      }
    ],
    count: 1
  };
}

export function quantResearchRunPayload() {
  return {
    success: true,
    data: {
      research: {
        research_id: "research_e2e_quant_1",
        status: "blocked",
        payload: {
          stages: [
            { name: "definition", status: "completed", output: { universe: ["600519", "000001"], factors: ["momentum"] }, error: null },
            { name: "data_gate", status: "blocked", output: { status: "unconfigured", blocking_reason: "LOCAL_DATABASE_REQUIRED" }, error: "LOCAL_DATABASE_REQUIRED" }
          ]
        },
        report: {
          object: "aiask.quant_research_report",
          research_id: "research_e2e_quant_1",
          status: "blocked",
          summary: {
            benchmark: "000300",
            universe_size: 2,
            factor_count: 1,
            failed_stage: "data_gate"
          },
          universe: ["600519", "000001"],
          backtest_assumptions: {
            cost_bps: 3,
            slippage_bps: 1,
            rebalance_frequency: "monthly"
          },
          strategy_factory: null,
          disclaimer: "NOT_INVESTMENT_ADVICE: This research artifact is decision support only and is not a trading instruction.",
          stages: [
            { name: "definition", status: "completed", output: { universe: ["600519", "000001"], factors: ["momentum"] }, error: null },
            { name: "data_gate", status: "blocked", output: { status: "unconfigured", blocking_reason: "LOCAL_DATABASE_REQUIRED" }, error: "LOCAL_DATABASE_REQUIRED" }
          ],
          limitations: ["Full quant mode requires a writable SQLite database."]
        }
      }
    },
    error: null
  };
}

export function factorFactoryStatusPayload() {
  return {
    object: "aiask.desktop.factor_factory_status",
    status: "ready",
    configured: true,
    factory: {
      initialized: true,
      pool_loaded_from_db: true,
      pool_size: 3,
      run_count: 7,
      last_run_id: "factor_run_e2e_1"
    },
    active_factors: [
      { factor_id: "factor_momentum_20d", name: "20d momentum", family: "momentum", quality_score: 0.73, status: "promoted" },
      { factor_id: "factor_value_cashflow", name: "cashflow value", family: "value", quality_score: 0.61, status: "candidate" }
    ],
    engine_health: {
      llm_primary: { status: "ready" },
      gp_classic: { status: "ready" },
      rule_seed: { status: "ready" }
    },
    pool_health: {
      active_promoted_count: 1,
      quarantine_count: 0
    },
    secrets_redacted: true
  };
}

export function jobsPayload() {
  return {
    object: "list",
    data: [
      {
        job_id: "job_e2e_research",
        name: "每日研究监控",
        prompt: "复盘最新市场数据，并总结需要关注的风险提醒。",
        schedule: "*/30 * * * *",
        toolset: "finance_safe",
        enabled: true,
        last_run_at: "2026-05-21T07:30:00.000Z",
        last_result: { status: "completed", run_id: "run_job_e2e" }
      }
    ]
  };
}

export function intentEnvelope(action = "factory_run_once") {
  return {
    success: true,
    data: {
      intent: {
        intent_id: "intent_e2e_approved_path",
        action,
        target_tool: "agent_action_intent_create",
        target_action: action,
        status: "awaiting_confirmation",
        params: { source: "desktop_e2e" },
        created_at: "2026-05-21T08:00:00.000Z",
        updated_at: "2026-05-21T08:00:00.000Z"
      }
    },
    error: null,
    error_code: null
  };
}

export function incubationStatusEnvelope() {
  return {
    success: true,
    data: {
      run_time: "nightly",
      dry_run: true,
      run_count: 12,
      error_count: 0,
      last_run_at: "2026-05-21T07:00:00.000Z",
      last_result_status: "completed",
      report: {
        report_date: "2026-05-21",
        summary: {
          total_incubating: 6,
          total_with_signals: 4,
          auto_promoted: 1,
          stage_counts: { warmup: 2, observe: 2, candidate: 1, promoted: 1 }
        },
        hit_rate_dashboard: {
          overall: {
            total_signals: 18,
            hit_count: 11,
            hit_rate: 0.61,
            avg_skill_lcb: 0.022,
            avg_forward_sharpe: 1.17,
            strategy_count: 6
          },
          by_family: {
            momentum: { hit_rate: 0.65, total_n: 10, avg_skill_lcb: 0.031, avg_forward_sharpe: 1.2, strategy_count: 3 },
            value: { hit_rate: 0.55, total_n: 8, avg_skill_lcb: 0.011, avg_forward_sharpe: 0.8, strategy_count: 2 }
          },
          trend: { available: true, improvement: 0.04, direction: "improving" }
        },
        feedback_actions: {
          families_to_boost: ["momentum"],
          families_to_cooldown: ["low_liquidity"],
          families_to_freeze: []
        }
      }
    },
    error: null,
    error_code: null
  };
}

export function strategyEventsEnvelope(eventType?: string | null) {
  const reportEvent = {
    id: "event_hit_rate_report",
    event_type: "incubation_factory.hit_rate_report_generated",
    severity: "info",
    created_at: "2026-05-21T07:00:00.000Z",
    payload: incubationStatusEnvelope().data.report
  };
  const stageEvent = {
    id: "event_stage_promoted",
    event_type: "incubation.stage_transitioned",
    severity: "info",
    created_at: "2026-05-21T07:10:00.000Z",
    strategy_id: "strategy_e2e_momentum",
    payload: {
      strategy_id: "strategy_e2e_momentum",
      strategy_name: "E2E momentum strategy",
      from_stage: "candidate",
      to_stage: "promoted",
      reason: "mock forward verification passed"
    }
  };
  const factoryEvent = {
    id: "event_factory_run_completed",
    event_type: "factory.run_completed",
    severity: "info",
    created_at: "2026-05-21T07:20:00.000Z",
    strategy_id: "strategy_e2e_factory",
    payload: { decision: "review", message: "mock factory cycle completed" }
  };
  const events = [reportEvent, stageEvent, factoryEvent].filter((event) => !eventType || event.event_type === eventType);
  return { success: true, data: { events }, error: null, error_code: null };
}

