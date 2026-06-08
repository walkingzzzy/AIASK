import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ToolCatalog } from "./InspectorPanels";

afterEach(() => cleanup());

describe("ToolCatalog", () => {
  it("deduplicates Hermes tools and filters by side effect", () => {
    render(
      <ToolCatalog
        hermesTools={[
          {
            name: "agent_quote",
            capability: "market",
            category: "finance",
            status: "ready",
            side_effect: "read_only",
            description: "Duplicate quote tool from full mode"
          }
        ]}
        tools={[
          {
            name: "agent_quote",
            capability: "market",
            category: "finance",
            status: "ready",
            side_effect: "read_only",
            description: "Read market quote"
          },
          {
            name: "agent_strategy_submit",
            capability: "strategy",
            category: "strategy_factory",
            status: "gated",
            side_effect: "stateful",
            description: "Submit strategy candidate"
          }
        ]}
      />
    );

    expect(screen.getAllByText("agent_quote")).toHaveLength(1);
    expect(screen.getByText("agent_strategy_submit")).toBeInTheDocument();
    expect(screen.getAllByText("read_only").length).toBeGreaterThan(0);
    expect(screen.getAllByText("stateful").length).toBeGreaterThan(0);

    const [, statusFilter, sideEffectFilter] = screen.getAllByRole("combobox");
    fireEvent.change(statusFilter, { target: { value: "ready" } });
    expect(screen.getByText("agent_quote")).toBeInTheDocument();
    expect(screen.queryByText("agent_strategy_submit")).not.toBeInTheDocument();

    fireEvent.change(statusFilter, { target: { value: "all" } });
    fireEvent.change(sideEffectFilter, { target: { value: "read_only" } });
    expect(screen.getByText("agent_quote")).toBeInTheDocument();
    expect(screen.queryByText("agent_strategy_submit")).not.toBeInTheDocument();
    expect(screen.queryByText("契约")).not.toBeInTheDocument();
  });

  it("shows optional provider contract metadata without requiring it", () => {
    render(
      <ToolCatalog
        hermesTools={[]}
        tools={[
          {
            name: "agent_mcp_akshare_get_realtime_quote",
            capability: "market",
            category: "mcp_financial",
            status: "ready",
            side_effect: "read_only",
            description: "Read market quote",
            input_schema: { type: "object", properties: { code: { type: "string" } } },
            output_schema: { type: "object", properties: { price: { type: "number" } } },
            freshness: { expectation: "intraday_or_latest_quote_snapshot" },
            source_policy: { priority: ["tdx_local", "akshare"] },
            examples: [{ arguments: { code: "600519" } }],
            contract_version: "ai_tool_contract_v1",
            contract_source: "akshare_mcp.tool_catalog",
            standard_model: "EquityQuote",
            provider_choices: [{ rank: 1, source: "tdx_local", provider: "tdx_local" }],
            provider_status: { providers: [{ provider: "tdx_local", available: true }] },
            quality_gate: { status: "passed", mode: "report_only" },
            reconciliation: { enabled: true, mode: "sampled_report_only" },
            form_schema: { type: "object", properties: { code: { type: "string", title: "Code" } }, required: ["code"], examples: [{ code: "600519" }] }
          },
          {
            name: "agent_plain",
            capability: "plain",
            category: "general",
            status: "ready",
            side_effect: "read_only",
            description: "Plain tool"
          }
        ]}
      />
    );

    expect(screen.getByText("contract akshare_mcp.tool_catalog")).toBeInTheDocument();
    expect(screen.getByText("model EquityQuote")).toBeInTheDocument();
    expect(screen.getByText("freshness intraday_or_latest_quote_snapshot")).toBeInTheDocument();
    expect(screen.getByText("source tdx_local > akshare")).toBeInTheDocument();
    expect(screen.getByText("quality passed report_only")).toBeInTheDocument();
    expect(screen.getByText("providers 1")).toBeInTheDocument();
    expect(screen.getByText("契约")).toBeInTheDocument();
    expect(screen.getByText("参数")).toBeInTheDocument();
    expect(screen.getByText("agent_plain")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "为 agent_mcp_akshare_get_realtime_quote 填充示例" }));
    expect(screen.getByPlaceholderText("code")).toHaveValue("600519");

    const search = screen.getByPlaceholderText("搜索工具");
    fireEvent.change(search, { target: { value: "tdx_local" } });
    expect(screen.getByText("agent_mcp_akshare_get_realtime_quote")).toBeInTheDocument();
    expect(screen.queryByText("agent_plain")).not.toBeInTheDocument();
  });

  it("searches contract metadata for macro, fund flow, and options tools", () => {
    render(
      <ToolCatalog
        hermesTools={[]}
        tools={[
          {
            name: "agent_mcp_akshare_get_macro_indicator",
            capability: "macro",
            category: "mcp_financial",
            status: "ready",
            side_effect: "read_only",
            description: "Read macro indicator",
            freshness: { expectation: "latest_published_macro_indicator_snapshot" },
            source_policy: { priority: ["tushare_pro.macro", "akshare.macro"] },
            contract_version: "ai_tool_contract_v1",
            contract_source: "akshare_mcp.tool_catalog"
          },
          {
            name: "agent_mcp_akshare_get_stock_fund_flow",
            capability: "fund_flow",
            category: "mcp_financial",
            status: "ready",
            side_effect: "read_only",
            description: "Read stock fund flow",
            freshness: { expectation: "intraday_or_latest_trading_day_fund_flow_snapshot" },
            source_policy: { priority: ["db.stock_fund_flow", "tqcenter.more_info", "tushare.moneyflow"] },
            contract_version: "ai_tool_contract_v1",
            contract_source: "akshare_mcp.tool_catalog"
          },
          {
            name: "agent_mcp_akshare_get_option_chain",
            capability: "options",
            category: "mcp_financial",
            status: "ready",
            side_effect: "read_only",
            description: "Read option chain",
            freshness: { expectation: "near_real_time_option_chain_snapshot" },
            source_policy: { priority: ["akshare.option_sse_list_sina", "akshare.option_sse_codes_sina"] },
            contract_version: "ai_tool_contract_v1",
            contract_source: "akshare_mcp.tool_catalog"
          }
        ]}
      />
    );

    expect(screen.getByText("freshness latest_published_macro_indicator_snapshot")).toBeInTheDocument();
    expect(screen.getByText("source db.stock_fund_flow > tqcenter.more_info > tushare.moneyflow")).toBeInTheDocument();
    expect(screen.getByText("freshness near_real_time_option_chain_snapshot")).toBeInTheDocument();

    const search = screen.getByPlaceholderText("搜索工具");
    fireEvent.change(search, { target: { value: "akshare.option_sse" } });
    expect(screen.getByText("agent_mcp_akshare_get_option_chain")).toBeInTheDocument();
    expect(screen.queryByText("agent_mcp_akshare_get_macro_indicator")).not.toBeInTheDocument();
    expect(screen.queryByText("agent_mcp_akshare_get_stock_fund_flow")).not.toBeInTheDocument();
  });

  it("renders structured side effect metadata from full mode tools", () => {
    render(
      <ToolCatalog
        hermesTools={[]}
        tools={[
          {
            name: "agent_mcp_structured_tool",
            capability: "mcp_financial",
            category: "mcp_financial",
            status: "ready",
            side_effect: {
              level: "read_only",
              target: "sector_manager",
              confirmation_required: false,
              idempotent: true
            },
            description: "Structured side effect metadata"
          }
        ]}
      />
    );

    expect(screen.getByText("agent_mcp_structured_tool")).toBeInTheDocument();
    expect(screen.getAllByText("read_only").length).toBeGreaterThan(0);
    expect(screen.getByText("目标 sector_manager")).toBeInTheDocument();
  });
});
