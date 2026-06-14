import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StockDataSourcesPanel } from "./StockDataSourcesPanel";

function ok(payload: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    })
  );
}

function pathFor(input: RequestInfo | URL) {
  return new URL(String(input)).pathname;
}

function requestBody(init?: RequestInit): Record<string, unknown> {
  return init?.body ? JSON.parse(String(init.body)) : {};
}

const presets = [
  {
    provider: "duckduckgo",
    label: "DuckDuckGo HTML Search",
    markets: ["Global"],
    categories: ["web_search", "research"],
    auth_type: "none",
    default_base_url: "https://duckduckgo.com/html/",
    required_fields: [],
    optional_fields: ["base_url"],
    env_keys: []
  },
  {
    provider: "tavily",
    label: "Tavily Search",
    markets: ["Global"],
    categories: ["web_search", "deep_research"],
    auth_type: "bearer",
    default_base_url: "https://api.tavily.com",
    required_fields: ["api_key"],
    optional_fields: ["search_depth"],
    env_keys: ["TAVILY_API_KEY"],
    documentation_url: "https://docs.tavily.com/documentation/api-reference/endpoint/search"
  },
  {
    provider: "tushare",
    label: "Tushare Pro",
    markets: ["CN"],
    categories: ["quote", "kline", "fundamental"],
    auth_type: "token",
    default_base_url: "http://api.tushare.pro",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "symbol", "timeout_seconds"],
    env_keys: ["TUSHARE_TOKEN"],
    documentation_url: "https://tushare.pro"
  },
  {
    provider: "akshare",
    label: "AKShare / AKTools",
    markets: ["CN"],
    categories: ["quote", "kline"],
    auth_type: "none",
    required_fields: [],
    optional_fields: [],
    env_keys: []
  }
];

describe("StockDataSourcesPanel", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("saves a search data source, runs search, and keeps secrets redacted", async () => {
    let savedTavily = false;
    const statusPayload = () => ({
      object: "aiask.stock_data_sources",
      status: "ready",
      configured_count: 1,
      ready_count: 1,
      presets,
      sources: savedTavily
        ? [
            {
              id: "mock:tavily",
              provider: "tavily",
              name: "Tavily Search",
              api_key_configured: true,
              enabled: true,
              status: "ready",
              configured: true,
              categories: ["web_search", "deep_research"],
              markets: ["Global"],
              search_depth: "advanced",
              secrets_redacted: true
            }
          ]
        : [
            {
              id: "mock:duckduckgo",
              provider: "duckduckgo",
              name: "DuckDuckGo fallback",
              enabled: true,
              status: "ready",
              configured: true,
              categories: ["web_search", "research"],
              markets: ["Global"],
              secrets_redacted: true
            }
          ],
      config_path: "mock://stock_data_sources.json",
      secrets_redacted: true
    });
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = pathFor(input);
      if (path === "/v1/desktop/stock-data-sources" && init?.method === "POST") {
        savedTavily = true;
        return ok({
          object: "aiask.stock_data_source",
          source: {
            id: "mock:tavily",
            provider: "tavily",
            name: "Tavily Search",
            api_key: "[redacted]",
            api_key_configured: true,
            enabled: true,
            status: "ready",
            configured: true,
            categories: ["web_search", "deep_research"],
            markets: ["Global"],
            search_depth: "advanced",
            secrets_redacted: true
          },
          secrets_redacted: true
        });
      }
      if (path === "/v1/desktop/stock-data-sources/test") {
        return ok({ object: "aiask.stock_data_source_test", provider: "tavily", mode: "connectivity", success: true, status: "ready", secrets_redacted: true });
      }
      if (path === "/v1/desktop/stock-data-sources") return ok(statusPayload());
      if (path === "/v1/tools/agent_web_search") {
        return ok({
          success: true,
          data: {
            provider: "tavily",
            results: [{ title: "AIASK result", url: "https://example.com/aiask" }]
          },
          error: null,
          meta: {}
        });
      }
      return Promise.resolve(new Response(JSON.stringify({ error: path }), { status: 404 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<StockDataSourcesPanel apiToken="api-token" controlToken="control-token" endpoint="http://127.0.0.1:8767" />);

    await screen.findByRole("button", { name: /Tavily Search/ });
    fireEvent.click(screen.getByRole("button", { name: /Tavily Search/ }));
    expect(screen.getByRole("button", { name: "调用搜索" })).toBeDisabled();
    expect(screen.getAllByText(/待填写密钥/).length).toBeGreaterThan(0);

    fireEvent.change(screen.getByPlaceholderText("粘贴数据服务的 API Key 或 Token"), { target: { value: "tvly-secret-value" } });
    expect(screen.getAllByText(/本次将写入新密钥/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "保存数据源" }));

    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(([input, init]) => pathFor(input) === "/v1/desktop/stock-data-sources" && init?.method === "POST");
      expect(saveCall?.[1]?.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
      expect(requestBody(saveCall?.[1])).toEqual(expect.objectContaining({ provider: "tavily", api_key: "tvly-secret-value", search_depth: "advanced" }));
    });

    await waitFor(() => expect(screen.getAllByText(/已配置，已脱敏/).length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("button", { name: "调用搜索" }));
    await screen.findByText("搜索调用成功");

    const searchCall = fetchMock.mock.calls.find(([input]) => pathFor(input) === "/v1/tools/agent_web_search");
    expect(searchCall?.[1]?.headers).toEqual(expect.objectContaining({ Authorization: "Bearer api-token" }));
    expect(requestBody(searchCall?.[1])).toEqual(expect.objectContaining({ provider: "tavily", source_id: "mock:tavily", search_depth: "advanced" }));
    const body = document.body.textContent || "";
    expect(body).toContain("已脱敏");
    expect(body).not.toContain("tvly-secret-value");
  });

  it("saves and tests a market data source with a redacted configured state", async () => {
    let savedTushare = false;
    const statusPayload = () => ({
      object: "aiask.stock_data_sources",
      status: "ready",
      configured_count: 1,
      ready_count: 1,
      presets,
      sources: [
        {
          id: savedTushare ? "mock:tushare:saved" : "mock:tushare",
          provider: "tushare",
          name: "Tushare 主账号",
          base_url: "http://api.tushare.pro",
          api_key: "[redacted]",
          api_key_configured: true,
          enabled: true,
          status: "ready",
          configured: true,
          categories: ["quote", "kline", "fundamental"],
          markets: ["CN"],
          symbol: "600519",
          secrets_redacted: true
        }
      ],
      config_path: "mock://stock_data_sources.json",
      secrets_redacted: true
    });
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = pathFor(input);
      if (path === "/v1/desktop/stock-data-sources" && init?.method === "POST") {
        savedTushare = true;
        return ok({
          object: "aiask.stock_data_source",
          source: {
            id: "mock:tushare:saved",
            provider: "tushare",
            name: "Tushare 主账号",
            api_key: "[redacted]",
            api_key_configured: true,
            enabled: true,
            status: "ready",
            configured: true,
            categories: ["quote", "kline", "fundamental"],
            markets: ["CN"],
            secrets_redacted: true
          },
          secrets_redacted: true
        });
      }
      if (path === "/v1/desktop/stock-data-sources/test") {
        return ok({
          object: "aiask.stock_data_source_test",
          provider: "tushare",
          mode: "connectivity",
          success: true,
          status: "ready",
          configured: true,
          latency_ms: 12,
          sample_count: 2,
          source: { provider: "tushare", api_key: "[redacted]", api_key_configured: true, secrets_redacted: true },
          secrets_redacted: true
        });
      }
      if (path === "/v1/desktop/stock-data-sources") return ok(statusPayload());
      return Promise.resolve(new Response(JSON.stringify({ error: path }), { status: 404 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<StockDataSourcesPanel apiToken="api-token" controlToken="control-token" endpoint="http://127.0.0.1:8767" />);

    await screen.findByRole("button", { name: /Tushare 主账号/ });
    expect(screen.queryByRole("button", { name: "调用搜索" })).not.toBeInTheDocument();
    expect(screen.getAllByText(/密钥已配置|已配置，已脱敏/).length).toBeGreaterThan(0);

    fireEvent.change(screen.getByPlaceholderText("已配置，留空则沿用现有密钥"), { target: { value: "tushare-secret-value" } });
    fireEvent.change(screen.getByPlaceholderText("AAPL / IBM / 600519"), { target: { value: "000001" } });
    fireEvent.click(screen.getByRole("button", { name: "保存数据源" }));

    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(([input, init]) => pathFor(input) === "/v1/desktop/stock-data-sources" && init?.method === "POST");
      expect(saveCall?.[1]?.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
      expect(requestBody(saveCall?.[1])).toEqual(expect.objectContaining({ provider: "tushare", api_key: "tushare-secret-value", symbol: "000001" }));
    });

    await waitFor(() => expect(screen.getAllByText(/已配置，已脱敏/).length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("button", { name: "测试连接" }));
    await screen.findByText("数据源测试通过");
    await screen.findByText("12 ms");

    const testCall = fetchMock.mock.calls.find(([input]) => pathFor(input) === "/v1/desktop/stock-data-sources/test");
    expect(testCall?.[1]?.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
    expect(requestBody(testCall?.[1])).toEqual({ mode: "connectivity", id: "mock:tushare:saved", provider: "tushare" });
    const body = document.body.textContent || "";
    expect(body).toContain("已脱敏");
    expect(body).not.toContain("tushare-secret-value");
  });

  it("tests edited saved sources with the current draft payload and redacted stored secrets", async () => {
    const testBodies: Record<string, unknown>[] = [];
    const statusPayload = () => ({
      object: "aiask.stock_data_sources",
      status: "ready",
      configured_count: 1,
      ready_count: 1,
      presets,
      sources: [
        {
          id: "mock:tushare",
          provider: "tushare",
          name: "Tushare 主账号",
          base_url: "http://api.tushare.pro",
          api_key: "[redacted]",
          api_key_configured: true,
          enabled: true,
          status: "ready",
          configured: true,
          categories: ["quote", "kline", "fundamental"],
          markets: ["CN"],
          symbol: "600519",
          timeout_seconds: 8,
          secrets_redacted: true
        }
      ],
      config_path: "mock://stock_data_sources.json",
      secrets_redacted: true
    });
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = pathFor(input);
      if (path === "/v1/desktop/stock-data-sources/test") {
        const body = requestBody(init);
        testBodies.push(body);
        return ok({
          object: "aiask.stock_data_source_test",
          provider: "tushare",
          mode: "connectivity",
          success: true,
          status: "ready",
          configured: true,
          latency_ms: 12,
          sample_count: 2,
          source: { provider: "tushare", api_key: "[redacted]", api_key_configured: true, secrets_redacted: true },
          secrets_redacted: true
        });
      }
      if (path === "/v1/desktop/stock-data-sources") return ok(statusPayload());
      return Promise.resolve(new Response(JSON.stringify({ error: path }), { status: 404 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<StockDataSourcesPanel apiToken="api-token" controlToken="control-token" endpoint="http://127.0.0.1:8767" />);

    await screen.findByRole("button", { name: /Tushare 主账号/ });
    fireEvent.change(screen.getByPlaceholderText("AAPL / IBM / 600519"), { target: { value: "000001" } });
    await screen.findByText("未保存变更");
    fireEvent.click(screen.getByRole("button", { name: "测试连接" }));
    await screen.findByText("数据源测试通过");

    expect(testBodies).toHaveLength(1);
    expect(testBodies[0]).toEqual({
      mode: "connectivity",
      id: "mock:tushare",
      provider: "tushare",
      source: expect.objectContaining({
        id: "mock:tushare",
        provider: "tushare",
        symbol: "000001",
        timeout_seconds: 8
      })
    });
    expect((testBodies[0].source as Record<string, unknown>).api_key).toBeUndefined();
    expect(document.body.textContent || "").not.toContain("tushare-secret-value");
  });
});
