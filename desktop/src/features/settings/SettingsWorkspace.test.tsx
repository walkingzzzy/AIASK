import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SettingsWorkspace } from "./SettingsWorkspace";

describe("SettingsWorkspace", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders the settings shell and section-driven connection fields", () => {
    const onEndpointChange = vi.fn();
    const onAgentModeChange = vi.fn();
    const onBackToApp = vi.fn();

    render(
      <SettingsWorkspace
        agentMode="finance_safe"
        apiToken="api-secret"
        busy={false}
        controlToken="control-secret"
        endpoint="http://127.0.0.1:8767"
        health={{ status: "ok", service: "aiask", hermes: { full_mode_enabled: true }, tools: { toolset: "general_full" }, control: { token_configured: true } }}
        onAgentModeChange={onAgentModeChange}
        onApiTokenChange={vi.fn()}
        onBackToApp={onBackToApp}
        onControlTokenChange={vi.fn()}
        onEndpointChange={onEndpointChange}
        onProfileChange={vi.fn()}
        onRefresh={vi.fn()}
        profileName="本地操作者"
        userId="local"
      />
    );

    expect(screen.getByRole("heading", { name: "设置中心" })).toBeInTheDocument();
    expect(screen.getByText("基础设置")).toBeInTheDocument();
    expect(screen.getByText("高级管理")).toBeInTheDocument();
    expect(screen.getByText("状态与入口")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "常规" })).toHaveClass("active");
    expect(screen.getByRole("button", { name: "技能管理" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "自动化管理" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "模型状态" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "MCP 管理入口" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "工作流入口" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "数据路径" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "高级诊断入口" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "外观" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Git / 环境" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "工作树" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "浏览器" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "电脑操控" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "归档" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "返回对话" }));
    expect(onBackToApp).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByDisplayValue("finance_safe"), { target: { value: "hermes_full" } });
    expect(onAgentModeChange).toHaveBeenCalledWith("hermes_full");

    fireEvent.click(screen.getByRole("button", { name: "连接" }));
    expect(screen.getByDisplayValue("http://127.0.0.1:8767")).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue("http://127.0.0.1:8767"), { target: { value: "http://127.0.0.1:9000" } });
    expect(onEndpointChange).toHaveBeenCalledWith("http://127.0.0.1:9000");

    fireEvent.click(screen.getByRole("button", { name: "令牌与权限" }));
    expect(screen.getByDisplayValue("api-secret")).toHaveAttribute("type", "password");
    expect(screen.getByDisplayValue("control-secret")).toHaveAttribute("type", "password");

    fireEvent.click(screen.getByRole("button", { name: "工作流入口" }));
    expect(screen.getByRole("button", { name: /数据与同步/ })).toBeInTheDocument();
    expect(screen.getByText("打开页面")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "高级诊断入口" }));
    expect(screen.getByRole("button", { name: /能力中心/ })).toBeInTheDocument();
  });

  it("shows a stale endpoint recovery action and full-mode setup hints", () => {
    const onResetEndpoint = vi.fn();

    render(
      <SettingsWorkspace
        agentMode="finance_safe"
        apiToken=""
        busy={false}
        connectionStatus="AIASK_OFFLINE"
        controlToken=""
        defaultEndpoint="http://127.0.0.1:8767"
        endpoint="http://127.0.0.1:8769"
        health={{ status: "offline", service: "aiask", hermes: { full_mode_enabled: false }, control: { token_configured: false } }}
        onAgentModeChange={vi.fn()}
        onApiTokenChange={vi.fn()}
        onControlTokenChange={vi.fn()}
        onEndpointChange={vi.fn()}
        onProfileChange={vi.fn()}
        onRefresh={vi.fn()}
        onResetEndpoint={onResetEndpoint}
        profileName="本地操作者"
        userId="local"
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "连接" }));
    expect(screen.getByText(/当前端点 http:\/\/127\.0\.0\.1:8769 不可达/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "恢复默认 Agent 端点" }));
    expect(onResetEndpoint).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "令牌与权限" }));
    expect(screen.getAllByText(/AIASK_AGENT_TOOLSET=general_full/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/AIASK_LOCAL_CONTROL_TOKEN/).length).toBeGreaterThan(0);
  });
});
