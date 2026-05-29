import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DecisionWorkspace } from "./DecisionWorkspace";

const catalog = {
  object: "aiask.desktop.financial_manager.catalog",
  groups: [{ id: "decision", label: "买卖决策" }],
  actions: [
    {
      capability_id: "decision",
      action_id: "should_buy",
      group: "decision",
      label: "买入建议",
      mode: "read_only",
      status: "ready",
      available: true,
      default_params: { code: "600519" }
    },
    {
      capability_id: "decision",
      action_id: "unified",
      group: "decision",
      label: "统一决策",
      mode: "read_only",
      status: "ready",
      available: true,
      default_params: { code: "600519", detail_level: "summary" }
    }
  ],
  summary: { ready: 2 },
  safety: { mode: "read_only_plus_intents" }
};

describe("DecisionWorkspace", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("uses the Financial Manager facade with the selected decision action", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url.endsWith("/v1/desktop/financial-manager/catalog")) {
        return new Response(JSON.stringify(catalog), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/v1/desktop/financial-manager/query")) {
        return new Response(JSON.stringify({ object: "query", success: true, data: { decision: "watch" }, error: null }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({ error: "unexpected" }), { status: 404 });
    });

    render(<DecisionWorkspace endpoint="http://127.0.0.1:8767" apiToken="api" controlToken="control" userId="local" />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "决策建议与共识" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /统一决策/ }));
    fireEvent.click(screen.getByRole("button", { name: "运行查询" }));

    await waitFor(() => expect(screen.getByText(/watch/)).toBeInTheDocument());
    const queryCall = calls.find((call) => call.url.endsWith("/query"));
    expect(JSON.parse(String(queryCall?.init?.body))).toMatchObject({
      capability_id: "decision",
      action_id: "unified",
      params: { code: "600519", detail_level: "summary" }
    });
  });
});
