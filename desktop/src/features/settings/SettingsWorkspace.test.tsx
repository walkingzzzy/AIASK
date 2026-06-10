import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SettingsWorkspace } from "./SettingsWorkspace";

describe("SettingsWorkspace", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
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

  it("loads read-only model settings through Agent HTTP, opens the model page, and redacts raw secrets", async () => {
    const onOpenView = vi.fn();
    const onProfileChange = vi.fn();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      if (url.pathname === "/v1/desktop/settings/status") {
        return new Response(
          JSON.stringify({
            object: "aiask.desktop_settings_status",
            agent: {
              control_authorized: true,
              control_reason: "authorized"
            },
            llm: {
              ai_status: {
                provider: "aiask_mock",
                model: "mock-live-model",
                configured: true,
                api_key_configured: true,
                api_key: "sk-settings-secret-value-1234567890",
                base_url_configured: true,
                config_source: { loaded: true, source: "project" },
                secrets_redacted: true
              },
              providers: {
                status: "ready",
                configured_count: 1,
                providers: [
                  {
                    name: "project-root-api",
                    configured: true,
                    status: "ready",
                    token: "settings-provider-token-1234567890"
                  }
                ]
              }
            },
            memory: {},
            databases: {},
            profile: { user_id: "settings-user", profile_name: "Settings Operator" },
            secrets_redacted: true
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response(JSON.stringify({ error: url.pathname }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <SettingsWorkspace
        agentMode="finance_safe"
        apiToken="api-token"
        busy={false}
        connectionStatus="AIASK_ONLINE"
        controlToken="control-token"
        endpoint="http://127.0.0.1:8767"
        health={{ status: "ok", service: "aiask", hermes: { full_mode_enabled: true }, tools: { toolset: "general_full" }, control: { token_configured: true } }}
        onAgentModeChange={vi.fn()}
        onApiTokenChange={vi.fn()}
        onBackToApp={vi.fn()}
        onControlTokenChange={vi.fn()}
        onEndpointChange={vi.fn()}
        onOpenView={onOpenView}
        onProfileChange={onProfileChange}
        onRefresh={vi.fn()}
        profileName="Local"
        userId="local"
      />
    );

    await waitFor(() => expect(onProfileChange).toHaveBeenCalledWith({ user_id: "settings-user", profile_name: "Settings Operator" }));
    expect((fetchMock.mock.calls[0]?.[1]?.headers as Record<string, string>).Authorization).toBe("Bearer control-token");

    fireEvent.click(screen.getByRole("button", { name: "模型状态" }));
    expect(screen.getByText("aiask_mock")).toBeInTheDocument();
    expect(screen.getByText("mock-live-model")).toBeInTheDocument();
    expect(document.body.textContent || "").not.toContain("sk-settings-secret-value");
    fireEvent.click(screen.getByRole("button", { name: /打开模型状态页/ }));
    expect(onOpenView).toHaveBeenCalledWith("models");

    fireEvent.click(screen.getByRole("button", { name: "关于" }));
    expect(document.body.textContent || "").toContain("[redacted]");
    expect(document.body.textContent || "").not.toContain("settings-provider-token");
  });
});
