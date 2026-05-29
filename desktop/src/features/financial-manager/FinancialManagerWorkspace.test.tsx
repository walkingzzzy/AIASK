import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FinancialManagerWorkspace } from "./FinancialManagerWorkspace";

const catalog = {
  object: "aiask.desktop.financial_manager.catalog",
  groups: [
    { id: "overview", label: "Overview" },
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
      default_params: { codes: ["600519"], weights: [1] }
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
  summary: { ready: 1, intent_ready: 1, blocked: 1 },
  safety: { live_trading_enabled: false },
  secrets_redacted: true
};

const status = {
  object: "aiask.desktop.financial_manager.status",
  status: "ready",
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
      if (url.endsWith("/v1/desktop/financial-manager/query")) {
        return new Response(JSON.stringify({ object: "query", success: true, data: { var_95: -0.02 }, error: null }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/v1/desktop/financial-manager/intent")) {
        return new Response(JSON.stringify({ object: "intent", success: true, data: { intent: { intent_id: "intent_fin_1", status: "awaiting_confirmation" } }, error: null }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({ error: "unexpected" }), { status: 404 });
    });

    render(<FinancialManagerWorkspace endpoint="http://127.0.0.1:8767" apiToken="api" controlToken="control" userId="local" />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "金融经理台" })).toBeInTheDocument());
    expect(screen.getByText("搜索与状态过滤")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("搜索能力、工具、action 或 group"), { target: { value: "live" } });
    expect(screen.getByText("Live place order")).toBeInTheDocument();
    expect(screen.queryByText("Create portfolio intent")).not.toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("搜索能力、工具、action 或 group"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /运行查询/ }));
    await waitFor(() => expect(screen.getByText(/var_95/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Portfolio & Watchlist/ }));
    fireEvent.click(screen.getByRole("button", { name: /Create portfolio intent/ }));
    fireEvent.click(screen.getByRole("button", { name: /创建意图/ }));
    await waitFor(() => expect(screen.getByText(/intent_fin_1/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Broker Read-only/ }));
    fireEvent.click(screen.getByRole("button", { name: /Live place order/ }));
    expect(screen.getByRole("button", { name: /运行查询/ })).toBeDisabled();
    expect(screen.getAllByText(/Live broker order placement is disabled/).length).toBeGreaterThan(0);

    const queryCall = calls.find((call) => call.url.endsWith("/query"));
    const intentCall = calls.find((call) => call.url.endsWith("/intent"));
    expect(JSON.parse(String(queryCall?.init?.body))).toMatchObject({ capability_id: "portfolio", action_id: "risk" });
    expect(JSON.parse(String(intentCall?.init?.body))).toMatchObject({ capability_id: "portfolio", action_id: "create", user_id: "local" });
  });
});
