import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReadinessHealthPage } from "./ReadinessHealthPage";
import type { FullModeConsoleData, HealthDetailed, HermesStatus } from "../../types";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ReadinessHealthPage", () => {
  const health: HealthDetailed = {
    status: "ok",
    service: "aiask",
    tools: { toolset: "finance_safe" },
    hermes: { full_mode_active: true, full_mode_enabled: true },
    control: { token_configured: true },
  };
  const hermesStatus: HermesStatus = {
    object: "aiask.hermes_status",
    implementation: "aiask_native",
    baseline: "Hermes v0.15.1 full runtime capability reference",
    embedded_vendor_runtime: false,
    full_mode_enabled: true,
    full_mode_active: true,
    evaluated_toolset: "finance_safe",
  };
  const fullConsole: FullModeConsoleData = {
    gatewayStatus: { status: "ready" },
    plugins: [{ name: "audit-plugin" }],
    providers: { status: "ready" },
  };

  it("renders readiness dimensions, live-smoke coverage, and fixed MCP remediation jump", async () => {
    const onOpenView = vi.fn();
    render(
      <ReadinessHealthPage
        endpoint="mock://aiask"
        apiToken="test-token"
        controlToken="mock-control-token"
        fullConsole={fullConsole}
        health={health}
        hermesStatus={hermesStatus}
        onOpenView={onOpenView}
        onRefreshHermes={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getAllByText("能力已同步").length).toBeGreaterThan(0));
    expect(screen.getByText("AI 提供方")).toBeInTheDocument();
    expect(screen.getAllByText("Gateway").length).toBeGreaterThan(0);
    expect(screen.getAllByText("插件").length).toBeGreaterThan(0);
    expect(screen.getAllByText("MCP").length).toBeGreaterThan(0);
    expect(screen.getByText("金融系统")).toBeInTheDocument();
    expect(screen.getByText("记忆 / 搜索")).toBeInTheDocument();
    expect(screen.getByText("模式 / 令牌")).toBeInTheDocument();
    expect(screen.getByText("MCP 服务需要补齐授权变量")).toBeInTheDocument();
    expect(screen.getAllByText("AIASK_MCP_AKSHARE_LOCAL_AUTHORIZATION").length).toBeGreaterThan(0);
    expect(screen.getByText("现在最该做什么")).toBeInTheDocument();
    expect(screen.getByText("运行一次只读金融工作流")).toBeInTheDocument();
    expect(screen.getByText("真实联调检查清单")).toBeInTheDocument();
    expect(screen.getByText("scripts/ops/live_readiness_smoke.py")).toBeInTheDocument();
    expect(screen.getByText("market_temperature_cache")).toBeInTheDocument();
    expect(screen.getByText("market_temperature_forward_validation")).toBeInTheDocument();
    expect(screen.getByText("观测字段：ready, status, blockers, warnings")).toBeInTheDocument();
    expect(screen.getByText("观测字段：benchmark_status, quality_status, warnings, sample_count")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "真实金融流程前置检查" })).toBeInTheDocument();
    expect(screen.getByText("1. 模式与模型")).toBeInTheDocument();
    expect(screen.getByText("2. MCP 与连接器")).toBeInTheDocument();
    expect(screen.getByText("3. 记忆与搜索")).toBeInTheDocument();
    expect(screen.getByText("4. 金融 Agent 流程")).toBeInTheDocument();
    expect(screen.getByText("5. 数据与量化研究")).toBeInTheDocument();
    expect(screen.getByText("6. 工厂接力")).toBeInTheDocument();
    expect(screen.getByText(/这些步骤都是只读导航检查/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "前往 MCP / 连接器：配置 MCP 授权变量" }));
    expect(screen.getByText("memory_status")).toBeInTheDocument();
    expect(screen.getByText("memory_search")).toBeInTheDocument();
    expect(screen.getAllByText(/语义搜索/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/向量提供方/).length).toBeGreaterThan(0);
    expect(onOpenView).toHaveBeenCalledWith("mcp-connectors");
    fireEvent.click(screen.getByRole("button", { name: "打开数据：5. 数据与量化研究" }));
    expect(onOpenView).toHaveBeenCalledWith("data");
    fireEvent.click(screen.getByRole("button", { name: "打开金融实验室：6. 工厂接力" }));
    expect(onOpenView).toHaveBeenCalledWith("finance-lab");
  });

  it("shows control-token guidance when management data is gated", async () => {
    render(
      <ReadinessHealthPage
        endpoint="mock://aiask"
        apiToken="test-token"
        controlToken=""
        fullConsole={{ gatewayStatus: { status: "ready" }, providers: { status: "ready" } }}
        health={{ ...health, control: { token_configured: false } }}
        hermesStatus={hermesStatus}
        onOpenView={vi.fn()}
        onRefreshHermes={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByText("控制令牌未配置")).toBeInTheDocument());
    expect(screen.getByText(/当前缺少控制令牌/)).toBeInTheDocument();
  });
});
