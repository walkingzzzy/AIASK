import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MarketTemperatureWorkspace } from "./MarketTemperatureWorkspace";

function response(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

function errorResponse(status = 500) {
  return new Response(JSON.stringify({ error: "snapshot failed" }), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

function requestBody(call: { init?: RequestInit }): Record<string, unknown> {
  return JSON.parse(String(call.init?.body || "{}")) as Record<string, unknown>;
}

function marketEnvelope() {
  return {
    success: true,
    data: {
      contract_version: "market_temperature.v1",
      as_of: "2026-06-08",
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
        temperature: 55.84,
        state: "neutral"
      },
      hot_industries: [
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
        }
      ],
      cold_industries: [
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
      ],
      industries: [{ name: "计算机" }, { name: "电力设备" }],
      quality: {
        status: "healthy",
        warnings: [],
        trend_coverage: 0.9867,
        loaded_stock_rows: 300,
        missing_kline_rows: 0,
        industry_count: 2
      },
      source_chain: ["db.stocks", "db.kline_1d", "market_temperature.service"]
    },
    error: null,
    meta: { side_effect: { level: "read_only", target: "market_temperature_snapshot" } }
  };
}

function readinessEnvelope() {
  return {
    success: true,
    data: {
      ready: true,
      status: "fresh",
      read_only: true,
      as_of: "2026-06-08",
      max_stale_days: 1,
      staleness_days: 1,
      quality_status: "healthy",
      degraded: false,
      warnings: [],
      blockers: [],
      cache: {
        updated_at: "2026-06-08T15:05:00Z",
        source: "market_temperature_snapshots"
      },
      source_chain: ["db.market_temperature_snapshots", "db_freshness"]
    },
    error: null,
    meta: { side_effect: { level: "read_only", target: "market_temperature_cache_readiness" } }
  };
}

function historyEnvelope() {
  return {
    success: true,
    data: {
      items: [
        {
          as_of: "2026-06-08",
          market_temperature: 55.84,
          market_state: "neutral",
          stock_count: 300,
          industry_count: 2,
          quality_status: "healthy",
          warnings: [],
          updated_at: "2026-06-08T15:05:00Z"
        },
        {
          as_of: "2026-06-07",
          market_temperature: 47.2,
          market_state: "neutral",
          stock_count: 298,
          industry_count: 2,
          quality_status: "healthy",
          warnings: [],
          updated_at: "2026-06-07T15:04:00Z"
        }
      ],
      count: 2,
      limit: 10,
      include_snapshot: false,
      source_chain: ["db.market_temperature_snapshots"]
    },
    error: null,
    meta: { side_effect: { level: "read_only", target: "market_temperature_cache_history" } }
  };
}

function industryHistoryEnvelope() {
  return {
    success: true,
    data: {
      items: [
        {
          as_of: "2026-06-07",
          code: "801780",
          name: "银行",
          temperature: 49.2,
          state: "neutral",
          ma20_breadth: 0.48,
          advance_count: 14,
          decline_count: 17,
          stock_count: 34,
          market_temperature: 47.2,
          market_state: "neutral",
          quality_status: "healthy",
          warnings: [],
          updated_at: "2026-06-07T15:04:00Z"
        },
        {
          as_of: "2026-06-08",
          code: "801780",
          name: "银行",
          temperature: 53.27,
          state: "neutral",
          ma20_breadth: 0.5294,
          advance_count: 17,
          decline_count: 15,
          stock_count: 34,
          market_temperature: 55.84,
          market_state: "neutral",
          quality_status: "healthy",
          warnings: [],
          updated_at: "2026-06-08T15:05:00Z"
        }
      ],
      count: 2,
      limit: 10,
      top_n: 3,
      industry: null,
      match_mode: "exact",
      include_source_chain: false,
      source_chain: ["db.market_temperature_snapshots", "market_temperature.industry_history"]
    },
    error: null,
    meta: { side_effect: { level: "read_only", target: "market_temperature_snapshots" } }
  };
}

function constituentsEnvelope() {
  const leadIndustry = marketEnvelope().data.hot_industries[0].name;
  return {
    success: true,
    data: {
      items: [
        {
          code: "300001",
          name: "Leader Soft",
          industry: leadIndustry,
          sector: leadIndustry,
          market: "SZ",
          market_cap: 1820.5,
          pe_ratio: 24.1,
          pb_ratio: 3.2,
          list_date: "2010-01-08"
        },
        {
          code: "600001",
          name: "Growth Cloud",
          industry: leadIndustry,
          sector: leadIndustry,
          market: "SH",
          market_cap: 1302.4,
          pe_ratio: 19.7,
          pb_ratio: 2.8,
          list_date: "2008-04-21"
        }
      ],
      count: 2,
      total_matches: 2,
      limit: 8,
      offset: 0,
      industry: leadIndustry,
      match_mode: "contains",
      include_source_chain: false,
      source_chain: ["db.stocks", "market_temperature.industry_constituents"]
    },
    error: null,
    meta: { side_effect: { level: "read_only", target: "stocks" } }
  };
}

function forwardValidationEnvelope() {
  return {
    success: true,
    data: {
      matrix: {
        warm: {
          "1d": { sample_n: 8, direction_hits: 5, reliable: true, avg_forward_return: 0.42, hit_rate: 0.625 },
          "3d": { sample_n: 7, direction_hits: 4, reliable: true, avg_forward_return: 0.76, hit_rate: 0.5714 }
        },
        cool: {
          "1d": { sample_n: 6, direction_hits: 4, reliable: true, avg_forward_return: -0.31, hit_rate: 0.6667 },
          "3d": { sample_n: 5, direction_hits: 3, reliable: true, avg_forward_return: -0.64, hit_rate: 0.6 }
        }
      },
      states: ["warm", "cool"],
      horizons: [1, 3, 5],
      count: 26,
      snapshot_count: 18,
      limit: 120,
      target_field: "benchmark_return",
      requested_target_field: "benchmark_return",
      benchmark_code: "000300",
      benchmark_status: "available",
      benchmark_bar_count: 76,
      min_samples: 3,
      neutral_band_pct: 0.2,
      include_samples: false,
      samples: [],
      source_chain: ["market_temperature_snapshots", "market_temperature.forward_validation"]
    },
    error: null,
    meta: { side_effect: { level: "read_only", target: "market_temperature_snapshots" } }
  };
}

function fallbackForwardValidationEnvelope() {
  return {
    success: true,
    data: {
      ...forwardValidationEnvelope().data,
      benchmark_status: "unavailable_fallback_to_weighted_pct_change",
      benchmark_bar_count: 0,
      quality: {
        status: "degraded",
        warnings: ["benchmark_kline_unavailable"]
      }
    },
    error: null,
    meta: { side_effect: { level: "read_only", target: "market_temperature_snapshots" } }
  };
}

describe("MarketTemperatureWorkspace", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders the read-only snapshot and refreshes with bounded request parameters", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url.includes("agent_market_temperature_cache_readiness")) return response(readinessEnvelope());
      if (url.includes("agent_market_temperature_cache_history")) return response(historyEnvelope());
      if (url.includes("agent_market_temperature_industry_history")) return response(industryHistoryEnvelope());
      if (url.includes("agent_market_temperature_industry_constituents")) return response(constituentsEnvelope());
      if (url.includes("agent_market_temperature_forward_validation")) return response(forwardValidationEnvelope());
      return response(marketEnvelope());
    });

    render(<MarketTemperatureWorkspace endpoint="http://127.0.0.1:8767" apiToken="api-token" />);

    await waitFor(() => expect(screen.getByTestId("market-temperature-workspace")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId("market-industry-heatmap")).toBeInTheDocument());
    await waitFor(() =>
      expect(within(screen.getByTestId("market-industry-heatmap")).getAllByRole("listitem").length).toBeGreaterThanOrEqual(2)
    );
    await waitFor(() => expect(screen.getAllByText("计算机").length).toBeGreaterThan(0));

    expect(screen.getByRole("heading", { name: "市场温度" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "热行业" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "冷行业" })).toBeInTheDocument();
    expect(screen.getAllByText("电力设备").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "缓存就绪" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "缓存历史" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "行业历史" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "前向验证" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "行业成分股" })).toBeInTheDocument();
    expect(screen.getAllByText("银行").length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getAllByText("2026-06-08T15:05:00Z").length).toBeGreaterThan(0));
    expect(screen.getByText("2026-06-07T15:04:00Z")).toBeInTheDocument();
    expect(screen.getAllByText(/55.8/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("偏热").length).toBeGreaterThan(0);
    expect(screen.getByText("可用")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Leader Soft")).toBeInTheDocument());
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(6));
    const [initialSnapshotCall, initialReadinessCall, initialHistoryCall, initialIndustryHistoryCall, initialForwardValidationCall, initialConstituentsCall] = calls.slice(-6);
    expect(initialSnapshotCall.url).toBe("http://127.0.0.1:8767/v1/tools/agent_market_temperature_snapshot");
    expect(initialSnapshotCall.init?.method).toBe("POST");
    expect(initialSnapshotCall.init?.headers).toEqual(expect.objectContaining({ Authorization: "Bearer api-token" }));
    expect(requestBody(initialSnapshotCall)).toEqual({ limit: 300, top_n: 8, min_bars: 20, use_cache: true });
    expect(initialReadinessCall.url).toBe("http://127.0.0.1:8767/v1/tools/agent_market_temperature_cache_readiness");
    expect(initialReadinessCall.init?.method).toBe("POST");
    expect(requestBody(initialReadinessCall)).toEqual({ max_stale_days: 1 });
    expect(initialHistoryCall.url).toBe("http://127.0.0.1:8767/v1/tools/agent_market_temperature_cache_history");
    expect(initialHistoryCall.init?.method).toBe("POST");
    expect(requestBody(initialHistoryCall)).toEqual({ limit: 10, include_snapshot: false });
    expect(initialIndustryHistoryCall.url).toBe("http://127.0.0.1:8767/v1/tools/agent_market_temperature_industry_history");
    expect(initialIndustryHistoryCall.init?.method).toBe("POST");
    expect(requestBody(initialIndustryHistoryCall)).toEqual({ limit: 10, top_n: 3, match_mode: "exact", include_source_chain: false });
    expect(initialForwardValidationCall.url).toBe("http://127.0.0.1:8767/v1/tools/agent_market_temperature_forward_validation");
    expect(initialForwardValidationCall.init?.method).toBe("POST");
    expect(requestBody(initialForwardValidationCall)).toEqual({
      limit: 120,
      horizons: [1, 3, 5],
      target_field: "benchmark_return",
      benchmark_code: "000300",
      min_samples: 3,
      include_samples: false
    });
    expect(initialConstituentsCall.url).toBe("http://127.0.0.1:8767/v1/tools/agent_market_temperature_industry_constituents");
    expect(initialConstituentsCall.init?.method).toBe("POST");
    expect(requestBody(initialConstituentsCall)).toEqual({
      industry: marketEnvelope().data.hot_industries[0].name,
      limit: 8,
      offset: 0,
      match_mode: "contains",
      include_source_chain: false
    });
    const initialCallCount = calls.length;

    fireEvent.change(screen.getByLabelText("排行数量"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("日期"), { target: { value: "2026-06-08" } });
    fireEvent.click(screen.getByRole("button", { name: /更新快照/ }));

    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(initialCallCount + 6));
    const [refreshSnapshotCall, refreshReadinessCall, refreshHistoryCall, refreshIndustryHistoryCall, refreshForwardValidationCall, refreshConstituentsCall] = calls.slice(-6);
    expect(requestBody(refreshSnapshotCall)).toEqual({ limit: 300, top_n: 2, min_bars: 20, use_cache: true, as_of: "2026-06-08" });
    expect(requestBody(refreshReadinessCall)).toEqual({ max_stale_days: 1, as_of: "2026-06-08" });
    expect(requestBody(refreshHistoryCall)).toEqual({ limit: 10, include_snapshot: false });
    expect(requestBody(refreshIndustryHistoryCall)).toEqual({ limit: 10, top_n: 3, match_mode: "exact", include_source_chain: false });
    expect(requestBody(refreshForwardValidationCall)).toEqual({
      limit: 120,
      horizons: [1, 3, 5],
      target_field: "benchmark_return",
      benchmark_code: "000300",
      min_samples: 3,
      include_samples: false
    });
    expect(requestBody(refreshConstituentsCall)).toEqual({
      industry: marketEnvelope().data.hot_industries[0].name,
      limit: 8,
      offset: 0,
      match_mode: "contains",
      include_source_chain: false
    });
  });

  it("keeps snapshot reads cache-first and clears stale snapshot content after a refresh failure", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    let snapshotCalls = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url.includes("agent_market_temperature_snapshot")) {
        snapshotCalls += 1;
        return snapshotCalls === 1 ? response(marketEnvelope()) : errorResponse(500);
      }
      if (url.includes("agent_market_temperature_cache_readiness")) return response(readinessEnvelope());
      if (url.includes("agent_market_temperature_cache_history")) return response(historyEnvelope());
      if (url.includes("agent_market_temperature_industry_history")) return response(industryHistoryEnvelope());
      if (url.includes("agent_market_temperature_industry_constituents")) return response(constituentsEnvelope());
      if (url.includes("agent_market_temperature_forward_validation")) return response(forwardValidationEnvelope());
      return response({});
    });

    render(<MarketTemperatureWorkspace endpoint="http://127.0.0.1:8767" apiToken="api-token" />);

    await waitFor(() => expect(screen.getAllByText("计算机").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("button", { name: /更新快照/ }));

    await waitFor(() => expect(screen.getByText("AIASK_HTTP_500")).toBeInTheDocument());
    expect(screen.queryByText("计算机")).not.toBeInTheDocument();
    const snapshotBodies = calls
      .filter((call) => call.url.includes("agent_market_temperature_snapshot"))
      .map((call) => requestBody(call));
    expect(snapshotBodies).toEqual([
      { limit: 300, top_n: 8, min_bars: 20, use_cache: true },
      { limit: 300, top_n: 8, min_bars: 20, use_cache: true }
    ]);
  });

  it("renders the benchmark fallback status as a localized degraded state", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("agent_market_temperature_cache_readiness")) return response(readinessEnvelope());
      if (url.includes("agent_market_temperature_cache_history")) return response(historyEnvelope());
      if (url.includes("agent_market_temperature_industry_history")) return response(industryHistoryEnvelope());
      if (url.includes("agent_market_temperature_industry_constituents")) return response(constituentsEnvelope());
      if (url.includes("agent_market_temperature_forward_validation")) return response(fallbackForwardValidationEnvelope());
      return response(marketEnvelope());
    });

    render(<MarketTemperatureWorkspace endpoint="http://127.0.0.1:8767" apiToken="api-token" />);

    await waitFor(() => expect(screen.getByText("基准不可用，已降级")).toBeInTheDocument());
    expect(screen.queryByText("unavailable_fallback_to_weighted_pct_change")).not.toBeInTheDocument();
  });
});
