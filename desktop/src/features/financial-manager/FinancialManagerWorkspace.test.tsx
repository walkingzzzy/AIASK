import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FinancialManagerWorkspace } from "./FinancialManagerWorkspace";

const catalog = {
  object: "aiask.desktop.financial_manager.catalog",
  groups: [
    { id: "overview", label: "Overview" },
    { id: "market-research", label: "Market & Research" },
    { id: "risk-performance", label: "Risk & Performance" },
    { id: "portfolio-watchlist", label: "Portfolio & Watchlist" },
    { id: "broker-readonly", label: "Broker Read-only" }
  ],
  actions: [
    {
      capability_id: "portfolio",
      action_id: "risk",
      group: "risk-performance",
      label: "Portfolio risk",
      mode: "read_only",
      status: "ready",
      available: true,
      default_params: { codes: ["600519"], weights: [1] },
      availability: { reason_code: "agent_tool_ready", required_tool: "agent_portfolio_risk", agent_registry_has_tool: true }
    },
    {
      capability_id: "stock-analysis",
      action_id: "analyze_stock",
      group: "market-research",
      label: "Stock analysis",
      mode: "read_only",
      status: "ready",
      available: true,
      tool: "agent_analyze_stock",
      default_params: { code: "600519", include_decision: false },
      availability: { reason_code: "agent_tool_ready", required_tool: "agent_analyze_stock", agent_registry_has_tool: true }
    },
    {
      capability_id: "research",
      action_id: "reports",
      group: "risk-performance",
      label: "Research reports",
      mode: "read_only",
      status: "missing_mcp_tool",
      available: false,
      mcp_tool: "research_manager",
      default_params: { code: "600519", limit: 5 },
      availability: { reason_code: "mcp_tool_not_discovered", required_mcp_tool: "research_manager" }
    },
    {
      capability_id: "quant",
      action_id: "data_gate",
      group: "risk-performance",
      label: "Quant data gate",
      mode: "read_only",
      status: "ready",
      available: true,
      tool: "agent_quant_data_gate",
      default_params: { codes: ["600519", "000001"], max_stale_days: 5 },
      availability: { reason_code: "agent_tool_ready", required_tool: "agent_quant_data_gate", agent_registry_has_tool: true }
    },
    {
      capability_id: "portfolio",
      action_id: "create",
      group: "portfolio-watchlist",
      label: "Create portfolio intent",
      mode: "stateful_intent",
      status: "intent_ready",
      available: true,
      default_params: { name: "Desk" }
    },
    {
      capability_id: "broker-live",
      action_id: "place_order",
      group: "broker-readonly",
      label: "Live place order",
      mode: "blocked",
      status: "blocked",
      available: false,
      blocked_reason: "Live broker order placement is disabled in Financial Manager V1."
    }
  ],
  summary: { ready: 2, missing_mcp_tool: 1, intent_ready: 1, blocked: 1 },
  safety: { live_trading_enabled: false },
  secrets_redacted: true
};

const status = {
  object: "aiask.desktop.financial_manager.status",
  status: "ready",
  mcp: { registration: "registered", servers: [{ name: "akshare-local", domain: "finance" }] },
  broker: { live_trading_enabled: false },
  secrets_redacted: true
};

describe("FinancialManagerWorkspace", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("runs read-only actions, creates intents, and keeps live trading blocked", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url.endsWith("/v1/desktop/financial-manager/catalog")) {
        return new Response(JSON.stringify(catalog), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/v1/desktop/financial-manager/status")) {
        return new Response(JSON.stringify(status), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/v1/search?")) {
        return new Response(
          JSON.stringify({
            object: "list",
            data: [{ kind: "response", object_id: "resp_mock", session_id: "sess_mock", user_id: "local", content: "mock response hit" }]
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (url.endsWith("/v1/tools/agent_memory_search")) {
        return new Response(
          JSON.stringify({
            success: true,
            data: { items: [{ memory_id: "mem_mock", content: "mock memory hit", user_id: "local" }] },
            error: null,
            meta: { side_effect: { level: "read_only", target: "agent_memory_search", confirmation_required: false } }
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (url.endsWith("/v1/mcp/resources/read")) {
        return new Response(JSON.stringify({ success: true, data: { uri: "aiask://quotes", result: { text: "quote resource ok" } } }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (url.endsWith("/v1/mcp/prompts/get")) {
        return new Response(JSON.stringify({ success: true, data: { name: "risk-review", prompt: "risk prompt ok" } }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (url.endsWith("/v1/desktop/financial-manager/query")) {
        const body = JSON.parse(String(init?.body || "{}"));
        if (body.action_id === "analyze_stock") {
          return new Response(
            JSON.stringify({
              object: "query",
              capability_id: "stock-analysis",
              action_id: "analyze_stock",
              tool: "agent_analyze_stock",
              success: true,
              data: {
                status: "ready",
                code: body.params?.code || "600519",
                rating: "mock_watch",
                risk: "medium",
                decision: body.params?.include_decision ? "observe_only" : "not_requested"
              },
              error: null,
              meta: { side_effect: { level: "read_only", target: "agent_analyze_stock", confirmation_required: false } }
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (body.action_id === "reports") {
          return new Response(
            JSON.stringify({
              object: "query",
              success: false,
              data: {
                action: { capability_id: "research", action_id: "reports" },
                availability: { reason_code: "mcp_tool_not_discovered", required_mcp_tool: "research_manager" }
              },
              error: "financial manager tool is not available",
              error_code: "FINANCIAL_TOOL_UNAVAILABLE"
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (body.action_id === "data_gate") {
          return new Response(
            JSON.stringify({
              object: "query",
              capability_id: "quant",
              action_id: "data_gate",
              tool: "agent_quant_data_gate",
              success: true,
              data: { status: "ready", ready: true, coverage: { requested: 2, missing_count: 0, stale_count: 0 } },
              error: null,
              meta: { side_effect: { level: "read_only", target: "agent_quant_data_gate", confirmation_required: false } }
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        return new Response(
          JSON.stringify({
            object: "query",
            capability_id: "portfolio",
            action_id: "risk",
            tool: "agent_portfolio_risk",
            success: true,
            data: { status: "ready", var_95: -0.02 },
            error: null,
            meta: { side_effect: { level: "read_only", target: "agent_portfolio_risk", confirmation_required: false } }
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (url.endsWith("/v1/desktop/financial-manager/intent")) {
        return new Response(JSON.stringify({ object: "intent", success: true, data: { intent: { intent_id: "intent_fin_1", status: "awaiting_confirmation" } }, error: null }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({ error: "unexpected" }), { status: 404 });
    });

    render(<FinancialManagerWorkspace endpoint="http://127.0.0.1:8767" apiToken="api" controlToken="control" userId="local" />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "金融经理台" })).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "金融 Agent 只读工作流" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /运行只读工作流/ }));
    await waitFor(() => expect(screen.getAllByText(/FINANCIAL_WORKFLOW_DONE/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/agent_analyze_stock/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/agent_portfolio_risk/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/agent_quant_data_gate/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/agent_session_search/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/agent_memory_search/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/mock response hit/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/mock memory hit/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/quote resource ok/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/risk prompt ok/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/read_only/).length).toBeGreaterThan(0);

    expect(screen.getByText(/可运行 \(agent_tool_ready\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /运行查询/ }));
    await waitFor(() => expect(screen.getByText(/var_95/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /市场与研究/ }));
    fireEvent.click(screen.getByRole("button", { name: /个股分析/ }));
    fireEvent.change(screen.getByLabelText("stock analysis code"), { target: { value: "300750" } });
    fireEvent.click(screen.getByLabelText("include stock decision"));
    fireEvent.click(screen.getByRole("button", { name: /运行查询/ }));
    await waitFor(() => expect(screen.getAllByText(/mock_watch/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/300750/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/agent_analyze_stock/).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /风险与绩效/ }));
    fireEvent.click(screen.getByRole("button", { name: /研究报告/ }));
    expect(screen.getByText(/金融 MCP server 未提供目标工具 \(mcp_tool_not_discovered\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /运行查询/ }));
    await waitFor(() => expect(screen.getAllByText(/FINANCIAL_TOOL_UNAVAILABLE/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/research_manager/).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /组合与自选/ }));
    fireEvent.click(screen.getByRole("button", { name: /创建组合意图/ }));
    fireEvent.click(screen.getByRole("button", { name: /创建意图/ }));
    await waitFor(() => expect(screen.getByText(/intent_fin_1/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /券商只读/ }));
    fireEvent.click(screen.getByRole("button", { name: /实盘下单/ }));
    expect(screen.getByRole("button", { name: /运行查询/ })).toBeDisabled();
    expect(screen.getAllByText(/Live broker order placement is disabled/).length).toBeGreaterThan(0);

    const intentCall = calls.find((call) => call.url.endsWith("/intent"));
    expect(JSON.parse(String(intentCall?.init?.body))).toMatchObject({ capability_id: "portfolio", action_id: "create", user_id: "local" });
    const queryBodies = calls.filter((call) => call.url.endsWith("/query")).map((call) => JSON.parse(String(call.init?.body || "{}")));
    expect(queryBodies).toEqual(expect.arrayContaining([
      expect.objectContaining({ capability_id: "stock-analysis", action_id: "analyze_stock", params: expect.objectContaining({ code: "300750", include_decision: true }) }),
      expect.objectContaining({ capability_id: "portfolio", action_id: "risk" }),
      expect.objectContaining({ capability_id: "quant", action_id: "data_gate" })
    ]));
    expect(calls.some((call) => call.url.includes("/v1/search?"))).toBe(true);
    expect(calls.some((call) => call.url.endsWith("/v1/tools/agent_memory_search"))).toBe(true);
    expect(calls.some((call) => call.url.endsWith("/v1/mcp/resources/read"))).toBe(true);
    expect(calls.some((call) => call.url.endsWith("/v1/mcp/prompts/get"))).toBe(true);
  });
});
