export function marketTemperatureSnapshot(body: Record<string, unknown> = {}) {
  const topN = Math.max(1, Math.min(Number(body.top_n || 8), 12));
  const asOf = String(body.as_of || "2026-06-08");
  const industries = [
    {
      code: "801750",
      name: "计算机",
      date: asOf,
      stock_count: 48,
      trend_known_count: 48,
      above_ma20_count: 37,
      ma20_breadth: 0.7708,
      advance_count: 34,
      decline_count: 11,
      flat_count: 3,
      advance_ratio: 0.7083,
      avg_pct_change: 1.28,
      weighted_pct_change: 1.16,
      amount: 428.35,
      market_cap: 18342.5,
      market_cap_weight: 0.118,
      temperature: 74.42,
      state: "warm"
    },
    {
      code: "801080",
      name: "电子",
      date: asOf,
      stock_count: 62,
      trend_known_count: 61,
      above_ma20_count: 45,
      ma20_breadth: 0.7377,
      advance_count: 41,
      decline_count: 18,
      flat_count: 3,
      advance_ratio: 0.6613,
      avg_pct_change: 0.94,
      weighted_pct_change: 1.02,
      amount: 512.9,
      market_cap: 22640.2,
      market_cap_weight: 0.146,
      temperature: 71.83,
      state: "warm"
    },
    {
      code: "801780",
      name: "银行",
      date: asOf,
      stock_count: 34,
      trend_known_count: 34,
      above_ma20_count: 18,
      ma20_breadth: 0.5294,
      advance_count: 17,
      decline_count: 15,
      flat_count: 2,
      advance_ratio: 0.5,
      avg_pct_change: 0.18,
      weighted_pct_change: 0.12,
      amount: 216.72,
      market_cap: 31200.8,
      market_cap_weight: 0.201,
      temperature: 53.27,
      state: "neutral"
    },
    {
      code: "801120",
      name: "食品饮料",
      date: asOf,
      stock_count: 42,
      trend_known_count: 41,
      above_ma20_count: 14,
      ma20_breadth: 0.3415,
      advance_count: 12,
      decline_count: 28,
      flat_count: 2,
      advance_ratio: 0.2857,
      avg_pct_change: -0.84,
      weighted_pct_change: -0.71,
      amount: 148.42,
      market_cap: 17420.1,
      market_cap_weight: 0.112,
      temperature: 32.06,
      state: "cool"
    },
    {
      code: "801730",
      name: "电力设备",
      date: asOf,
      stock_count: 55,
      trend_known_count: 52,
      above_ma20_count: 13,
      ma20_breadth: 0.25,
      advance_count: 15,
      decline_count: 37,
      flat_count: 3,
      advance_ratio: 0.2727,
      avg_pct_change: -1.12,
      weighted_pct_change: -1.28,
      amount: 276.54,
      market_cap: 20680.7,
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
      above_ma20_count: 162,
      ma20_breadth: 0.5473,
      advance_count: 151,
      decline_count: 136,
      flat_count: 13,
      advance_ratio: 0.5033,
      avg_pct_change: 0.12,
      weighted_pct_change: 0.18,
      amount: 4280.6,
      market_cap: 155080.4,
      temperature: 55.84,
      state: "neutral"
    },
    industries,
    hot_industries: industries.slice(0, topN),
    cold_industries: [...industries].sort((left, right) => Number(left.temperature) - Number(right.temperature)).slice(0, topN),
    quality: {
      status: "healthy",
      warnings: [],
      input_rows: 300,
      valid_stock_count: 300,
      invalid_stock_rows: 0,
      industry_count: industries.length,
      unknown_industry_count: 0,
      trend_coverage: 0.9867,
      universe_limit: Number(body.limit || 300),
      universe_count: 300,
      loaded_stock_rows: 300,
      missing_kline_rows: 0,
      contract_version: "market_temperature.v1"
    },
    source_chain: ["desktop.mockApi", "market_temperature.fixture"]
  };
}

export function marketTemperatureCacheReadiness(body: Record<string, unknown> = {}) {
  const snapshot = marketTemperatureSnapshot(body);
  const asOf = String(body.as_of || snapshot.as_of || "2026-06-08");
  const maxStaleDays = Math.max(0, Math.trunc(Number(body.max_stale_days ?? 1)));
  return {
    ready: true,
    status: "fresh",
    read_only: true,
    as_of: asOf,
    requested_as_of: body.as_of ? asOf : null,
    max_stale_days: maxStaleDays,
    staleness_days: 1,
    quality_status: snapshot.quality.status,
    degraded: false,
    warnings: [],
    market_temperature: snapshot.market.temperature,
    market_state: snapshot.market.state,
    stock_count: snapshot.market.stock_count,
    industry_count: snapshot.quality.industry_count,
    cache: {
      created_at: `${asOf}T15:00:00Z`,
      updated_at: `${asOf}T15:05:00Z`,
      source: "market_temperature_snapshots"
    },
    blockers: [],
    source_chain: ["desktop.mockApi", "market_temperature.cache_readiness.fixture"]
  };
}

export function marketTemperatureCacheHistory(body: Record<string, unknown> = {}) {
  const limit = Math.max(1, Math.min(Math.trunc(Number(body.limit || 10)), 365));
  const includeSnapshot = Boolean(body.include_snapshot);
  const rows = [
    {
      as_of: "2026-06-08",
      market_temperature: 55.84,
      market_state: "neutral",
      stock_count: 300,
      industry_count: 5,
      quality_status: "healthy",
      warnings: [],
      created_at: "2026-06-08T15:00:00Z",
      updated_at: "2026-06-08T15:05:00Z"
    },
    {
      as_of: "2026-06-07",
      market_temperature: 47.2,
      market_state: "neutral",
      stock_count: 298,
      industry_count: 5,
      quality_status: "healthy",
      warnings: [],
      created_at: "2026-06-07T15:00:00Z",
      updated_at: "2026-06-07T15:04:00Z"
    },
    {
      as_of: "2026-06-06",
      market_temperature: 32.4,
      market_state: "cool",
      stock_count: 294,
      industry_count: 5,
      quality_status: "degraded",
      warnings: ["partial_kline_coverage"],
      created_at: "2026-06-06T15:00:00Z",
      updated_at: "2026-06-06T15:03:00Z"
    }
  ].slice(0, limit);
  const items = includeSnapshot
    ? rows.map((row) => ({ ...row, snapshot: marketTemperatureSnapshot({ ...body, as_of: row.as_of }) }))
    : rows;
  return {
    items,
    count: items.length,
    limit,
    include_snapshot: includeSnapshot,
    source_chain: ["desktop.mockApi", "market_temperature.cache_history.fixture"]
  };
}

export function marketTemperatureIndustryHistory(body: Record<string, unknown> = {}) {
  const limit = Math.max(1, Math.min(Math.trunc(Number(body.limit || 3)), 365));
  const topN = Math.max(1, Math.min(Math.trunc(Number(body.top_n || 3)), 50));
  const query = String(body.industry || "").trim().toLowerCase();
  const matchMode = String(body.match_mode || "exact").toLowerCase() === "contains" ? "contains" : "exact";
  const includeSourceChain = Boolean(body.include_source_chain);
  const dateRows = [
    { as_of: "2026-06-06", offset: -8, market_temperature: 32.4, market_state: "cool" },
    { as_of: "2026-06-07", offset: -3, market_temperature: 47.2, market_state: "neutral" },
    { as_of: "2026-06-08", offset: 0, market_temperature: 55.84, market_state: "neutral" }
  ].slice(-limit);
  const matchesQuery = (item: Record<string, unknown>) => {
    if (!query) return true;
    const tokens = [item.code, item.name].map((value) => String(value || "").trim().toLowerCase()).filter(Boolean);
    return matchMode === "contains" ? tokens.some((token) => token.includes(query)) : tokens.some((token) => token === query);
  };
  const items = dateRows.flatMap((dateRow) => {
    const snapshot = marketTemperatureSnapshot({ ...body, as_of: dateRow.as_of });
    const industries = (snapshot.industries || []).filter(matchesQuery);
    const selected = query ? industries : industries.slice(0, topN);
    return selected.map((industry) => ({
      as_of: dateRow.as_of,
      code: industry.code,
      name: industry.name,
      temperature: Number(industry.temperature || 0) + dateRow.offset,
      state: industry.state,
      ma20_breadth: industry.ma20_breadth,
      advance_count: industry.advance_count,
      decline_count: industry.decline_count,
      flat_count: industry.flat_count,
      stock_count: industry.stock_count,
      market_cap_weight: industry.market_cap_weight,
      market_temperature: dateRow.market_temperature,
      market_state: dateRow.market_state,
      quality_status: snapshot.quality.status,
      warnings: snapshot.quality.warnings,
      updated_at: `${dateRow.as_of}T15:05:00Z`,
      ...(includeSourceChain ? { source_chain: snapshot.source_chain } : {})
    }));
  });
  return {
    items,
    count: items.length,
    limit,
    top_n: topN,
    industry: query || null,
    match_mode: matchMode,
    include_source_chain: includeSourceChain,
    source_chain: ["desktop.mockApi", "market_temperature.industry_history.fixture"]
  };
}

export function marketTemperatureIndustryConstituents(body: Record<string, unknown> = {}) {
  const limit = Math.max(1, Math.min(Math.trunc(Number(body.limit || 50)), 1000));
  const offset = Math.max(0, Math.min(Math.trunc(Number(body.offset || 0)), 10000));
  const query = String(body.industry || "").trim().toLowerCase();
  const matchMode = String(body.match_mode || "contains").toLowerCase() === "exact" ? "exact" : "contains";
  const includeSourceChain = Boolean(body.include_source_chain);
  const snapshot = marketTemperatureSnapshot(body);
  const industryRows = snapshot.industries || [];
  const rows = industryRows.flatMap((industry, industryIndex) => {
    const baseCode = String(industry.code || `801${industryIndex}`);
    const industryName = String(industry.name || baseCode);
    return [
      {
        code: industryIndex === 2 ? "000001" : `${industryIndex + 1}00001`,
        name: industryIndex === 2 ? "Ping An Bank" : `${industryName} Leader`,
        industry: industryName,
        sector: industryName,
        market: industryIndex === 2 ? "SZ" : "SH",
        market_cap: Number(industry.market_cap || 1000) * 0.18,
        pe_ratio: 8.4 + industryIndex,
        pb_ratio: 0.7 + industryIndex / 10,
        list_date: "2001-01-01",
        industry_code: baseCode
      },
      {
        code: industryIndex === 2 ? "600036" : `${industryIndex + 1}00002`,
        name: industryIndex === 2 ? "CMB" : `${industryName} Growth`,
        industry: industryName,
        sector: industryName,
        market: "SH",
        market_cap: Number(industry.market_cap || 1000) * 0.12,
        pe_ratio: 11.2 + industryIndex,
        pb_ratio: 1.1 + industryIndex / 10,
        list_date: "2004-01-01",
        industry_code: baseCode
      }
    ];
  });
  const matchesQuery = (item: Record<string, unknown>) => {
    if (!query) return false;
    const tokens = [item.industry, item.sector, item.industry_code].map((value) => String(value || "").trim().toLowerCase()).filter(Boolean);
    return matchMode === "exact" ? tokens.some((token) => token === query) : tokens.some((token) => token.includes(query));
  };
  const matches = rows.filter(matchesQuery);
  const items = matches.slice(offset, offset + limit).map((item) => ({
    code: item.code,
    name: item.name,
    industry_code: item.industry_code,
    industry: item.industry,
    sector: item.sector,
    market: item.market,
    market_cap: item.market_cap,
    pe_ratio: item.pe_ratio,
    pb_ratio: item.pb_ratio,
    list_date: item.list_date,
    ...(includeSourceChain ? { source_chain: ["desktop.mockApi", "market_temperature.industry_constituents.fixture"] } : {})
  }));
  return {
    items,
    count: items.length,
    total_matches: matches.length,
    limit,
    offset,
    industry: String(body.industry || ""),
    match_mode: matchMode,
    include_source_chain: includeSourceChain,
    source_chain: ["desktop.mockApi", "market_temperature.industry_constituents.fixture"]
  };
}

export function marketTemperatureForwardValidation(body: Record<string, unknown> = {}) {
  const limit = Math.max(2, Math.min(Math.trunc(Number(body.limit || 180)), 365));
  const rawHorizons = Array.isArray(body.horizons) ? body.horizons : [1, 3, 5];
  const horizons = rawHorizons.map((item) => Math.max(1, Math.min(Math.trunc(Number(item || 1)), 20))).filter((item, index, items) => items.indexOf(item) === index);
  const targetField = String(body.target_field || "benchmark_return");
  const benchmarkCode = String(body.benchmark_code || "000300");
  const matrix = {
    warm: {
      "1d": { sample_n: 18, direction_hits: 12, reliable: true, avg_forward_return: 0.42, hit_rate: 0.6667, min_forward_return: -1.1, max_forward_return: 1.8 },
      "3d": { sample_n: 16, direction_hits: 10, reliable: true, avg_forward_return: 0.76, hit_rate: 0.625, min_forward_return: -1.6, max_forward_return: 2.7 },
      "5d": { sample_n: 12, direction_hits: 7, reliable: true, avg_forward_return: 0.94, hit_rate: 0.5833, min_forward_return: -2.2, max_forward_return: 3.5 }
    },
    neutral: {
      "1d": { sample_n: 24, direction_hits: 15, reliable: true, avg_forward_return: 0.06, hit_rate: 0.625, min_forward_return: -0.8, max_forward_return: 0.9 },
      "3d": { sample_n: 22, direction_hits: 12, reliable: true, avg_forward_return: 0.18, hit_rate: 0.5455, min_forward_return: -1.2, max_forward_return: 1.3 },
      "5d": { sample_n: 18, direction_hits: 10, reliable: true, avg_forward_return: 0.25, hit_rate: 0.5556, min_forward_return: -1.9, max_forward_return: 2.0 }
    },
    cool: {
      "1d": { sample_n: 14, direction_hits: 8, reliable: true, avg_forward_return: -0.31, hit_rate: 0.5714, min_forward_return: -1.7, max_forward_return: 1.0 },
      "3d": { sample_n: 12, direction_hits: 8, reliable: true, avg_forward_return: -0.64, hit_rate: 0.6667, min_forward_return: -2.3, max_forward_return: 1.4 },
      "5d": { sample_n: 9, direction_hits: 6, reliable: true, avg_forward_return: -0.72, hit_rate: 0.6667, min_forward_return: -2.8, max_forward_return: 1.9 }
    }
  };
  return {
    matrix,
    states: Object.keys(matrix),
    horizons,
    count: 145,
    snapshot_count: 72,
    limit,
    target_field: targetField,
    requested_target_field: targetField,
    benchmark_code: benchmarkCode,
    benchmark_status: targetField === "benchmark_return" ? "available" : "not_requested",
    benchmark_bar_count: targetField === "benchmark_return" ? 76 : 0,
    min_samples: Number(body.min_samples || 3),
    neutral_band_pct: Number(body.neutral_band_pct ?? 0.2),
    include_samples: Boolean(body.include_samples),
    samples: [],
    source_chain: ["desktop.mockApi", "market_temperature.forward_validation.fixture"]
  };
}
