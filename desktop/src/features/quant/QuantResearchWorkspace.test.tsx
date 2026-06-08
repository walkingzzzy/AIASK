import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QuantResearchWorkspace } from "./QuantResearchWorkspace";

const presetsPayload = {
  object: "aiask.quant_presets",
  data_status: {
    status: "unconfigured",
    database: {
      backend: "sqlite",
      path: "/tmp/akshare_mcp.sqlite3",
      configured: true,
      writable: false,
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
      risk_limits: { max_weight: 0.35 }
    }
  ],
  factor_library: ["momentum", "volatility"],
  risk_defaults: { max_weight: 0.35 },
  disclaimer: "NOT_INVESTMENT_ADVICE: decision support only."
};

const blockedRunPayload = {
  success: true,
  data: {
    research: {
      research_id: "qr_test_1",
      status: "blocked",
      payload: {
        stages: [
          {
            name: "data_gate",
            status: "blocked",
            error: "LOCAL_DATABASE_REQUIRED"
          }
        ]
      },
      report: {
        object: "aiask.quant_research_report",
        research_id: "qr_test_1",
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
          benchmark: "000300"
        },
        strategy_factory: { status: "not_loaded" },
        disclaimer: "NOT_INVESTMENT_ADVICE: decision support only.",
        stages: [
          {
            name: "data_gate",
            status: "blocked",
            error: "LOCAL_DATABASE_REQUIRED"
          }
        ]
      }
    }
  },
  error: null
};

describe("QuantResearchWorkspace", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders database preflight and a blocked research artifact", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/v1/desktop/quant/presets")) {
        return new Response(JSON.stringify(presetsPayload), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (url.endsWith("/v1/desktop/quant/research-runs")) {
        expect(init?.method).toBe("POST");
        expect(JSON.parse(String(init?.body))).toMatchObject({
          universe: ["600519", "000001"],
          factors: ["momentum"],
          benchmark: "000300",
          include_strategy_review: true
        });
        return new Response(JSON.stringify(blockedRunPayload), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response(JSON.stringify({ error: "unexpected url" }), { status: 404 });
    });

    render(<QuantResearchWorkspace endpoint="http://127.0.0.1:8767" apiToken="" />);

    await waitFor(() =>
      expect(screen.getByText("Configure a writable SQLite database path to enable full quant research.")).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: /运行研究/ }));

    await waitFor(() => expect(screen.getByText("qr_test_1")).toBeInTheDocument());
    expect(screen.getByText("data gate")).toBeInTheDocument();
    expect(screen.getAllByText("blocked").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/NOT_INVESTMENT_ADVICE/).length).toBeGreaterThan(0);
    expect(screen.getByText("结构化报告").closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText("回测假设 JSON").closest("details")).not.toHaveAttribute("open");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("loads a historical quant report by research id", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/v1/desktop/quant/presets")) {
        return new Response(JSON.stringify(presetsPayload), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (url.endsWith("/v1/desktop/quant/research-runs/qr_history/report")) {
        return new Response(
          JSON.stringify({
            object: "aiask.quant_research_report",
            research_id: "qr_history",
            status: "completed",
            summary: { benchmark: "000905", universe_size: 3, factor_count: 2 },
            disclaimer: "NOT_INVESTMENT_ADVICE"
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response(JSON.stringify({ error: "unexpected url" }), { status: 404 });
    });

    render(<QuantResearchWorkspace endpoint="http://127.0.0.1:8767" apiToken="" />);

    await waitFor(() => expect(screen.getByPlaceholderText("research_id")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText("research_id"), { target: { value: "qr_history" } });
    fireEvent.click(screen.getByRole("button", { name: /加载报告/ }));

    await waitFor(() => expect(screen.getByText("qr_history")).toBeInTheDocument());
    expect(screen.getByText("000905")).toBeInTheDocument();
  });
});
