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

  it("renders the six readiness dimensions and fixed MCP remediation jump", async () => {
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

    await waitFor(() => expect(screen.getAllByText("CAPABILITIES_SYNCED").length).toBeGreaterThan(0));
    expect(screen.getByText("AI Provider")).toBeInTheDocument();
    expect(screen.getAllByText("Gateway").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Plugins").length).toBeGreaterThan(0);
    expect(screen.getAllByText("MCP").length).toBeGreaterThan(0);
    expect(screen.getByText("Financial")).toBeInTheDocument();
    expect(screen.getByText("Mode / Token")).toBeInTheDocument();
    expect(screen.getByText("MCP 服务需要重新认证")).toBeInTheDocument();
    expect(screen.getAllByText("AIASK_MCP_AKSHARE_LOCAL_AUTHORIZATION").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "前往 MCP / Connectors" }));
    expect(onOpenView).toHaveBeenCalledWith("mcp-connectors");
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

    await waitFor(() => expect(screen.getByText("Control Token 未配置")).toBeInTheDocument());
    expect(screen.getByText(/当前缺少 control token/)).toBeInTheDocument();
  });
});
