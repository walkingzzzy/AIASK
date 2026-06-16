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
    expect(screen.getByRole("button", { name: "外观" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "API Keys" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "技能管理" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "自动化管理" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Gateway" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "模型配置" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "MCP 管理入口" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "工作流入口" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "市场温度配置" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "股票数据源" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "数据路径" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "高级诊断入口" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Git / 环境" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "工作树" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "浏览器" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "电脑操控" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "归档" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "关闭设置" }));
    expect(onBackToApp).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByDisplayValue("finance_safe"), { target: { value: "hermes_full" } });
    expect(onAgentModeChange).toHaveBeenCalledWith("hermes_full");

    fireEvent.click(screen.getByRole("button", { name: "外观" }));
    fireEvent.change(screen.getByDisplayValue("跟随系统"), { target: { value: "dark" } });
    expect(document.documentElement.dataset.aiaskTheme).toBe("dark");
    fireEvent.change(screen.getByDisplayValue("舒适"), { target: { value: "compact" } });
    expect(document.documentElement.dataset.aiaskDensity).toBe("compact");
    fireEvent.click(screen.getByRole("checkbox", { name: "减少动效" }));
    expect(document.documentElement.dataset.aiaskReduceMotion).toBe("true");

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
    fireEvent.click(screen.getByRole("button", { name: "Gateway" }));
    expect(screen.getByRole("button", { name: /打开 Gateway/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /打开消息审批/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "市场温度配置" }));
    expect(screen.getAllByText(/cache_max_stale_days/).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByDisplayValue("300"), { target: { value: "420" } });
    expect(screen.getByText(/\"limit\": 420/)).toBeInTheDocument();
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

  it("loads model settings through Agent HTTP, opens the model config page, and redacts raw secrets", async () => {
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

    fireEvent.click(screen.getByRole("button", { name: "模型配置" }));
    expect(screen.getByText("aiask_mock")).toBeInTheDocument();
    expect(screen.getByText("mock-live-model")).toBeInTheDocument();
    expect(document.body.textContent || "").not.toContain("sk-settings-secret-value");
    fireEvent.click(screen.getByRole("button", { name: /打开模型配置页/ }));
    expect(onOpenView).toHaveBeenCalledWith("models");

    fireEvent.click(screen.getByRole("button", { name: "API Keys" }));
    expect(screen.getByText(/OPENAI_API_KEY/)).toBeInTheDocument();
    expect(screen.getByText(/TUSHARE_TOKEN/)).toBeInTheDocument();
    expect(screen.getByText(/FEISHU_\*/)).toBeInTheDocument();
    expect(document.body.textContent || "").not.toContain("sk-settings-secret-value");
    expect(document.body.textContent || "").not.toContain("settings-provider-token");

    fireEvent.click(screen.getByRole("button", { name: "关于" }));
    expect(document.body.textContent || "").toContain("[redacted]");
    expect(document.body.textContent || "").not.toContain("settings-provider-token");
  });

  it("opens stock data source settings, saves a source, tests connectivity, and keeps secrets redacted", async () => {
    const onProfileChange = vi.fn();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      const body = init?.body ? JSON.parse(String(init.body)) : {};
      if (url.pathname === "/v1/desktop/settings/status") {
        return new Response(
          JSON.stringify({
            object: "aiask.desktop_settings_status",
            agent: { control_authorized: true, control_reason: "authorized" },
            llm: {
              ai_status: {
                provider: "mock",
                model: "mock",
                configured: true,
                api_key_configured: false,
                base_url_configured: false,
                mock: true,
                secrets_redacted: true
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
      if (url.pathname === "/v1/desktop/stock-data-sources" && init?.method !== "POST") {
        return new Response(
          JSON.stringify({
            object: "aiask.stock_data_sources",
            status: "ready",
            configured_count: 1,
            ready_count: 1,
            presets: [
              {
                provider: "tushare",
                label: "Tushare Pro",
                markets: ["CN"],
                categories: ["quote", "kline"],
                auth_type: "token",
                default_base_url: "http://api.tushare.pro",
                required_fields: ["api_key"],
                optional_fields: ["base_url", "timeout_seconds"],
                env_keys: ["TUSHARE_TOKEN"],
                documentation_url: "https://tushare.pro",
                note: "Token API"
              }
            ],
            sources: [
              {
                id: "stock_ds_tushare",
                provider: "tushare",
                name: "Tushare 主账号",
                enabled: true,
                configured: true,
                status: "ready",
                base_url: "http://api.tushare.pro",
                api_key: "[redacted]",
                api_key_configured: true,
                secrets_redacted: true
              }
            ],
            secrets_redacted: true
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (url.pathname === "/v1/desktop/stock-data-sources" && init?.method === "POST") {
        expect(body.api_key).toBe("secret-stock-token");
        return new Response(
          JSON.stringify({
            object: "aiask.stock_data_source",
            source: {
              id: "stock_ds_saved",
              provider: body.provider,
              name: body.name,
              enabled: true,
              configured: true,
              status: "ready",
              api_key: "[redacted]",
              api_key_configured: true,
              secrets_redacted: true
            },
            secrets_redacted: true
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (url.pathname === "/v1/desktop/stock-data-sources/test") {
        return new Response(
          JSON.stringify({
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
        onProfileChange={onProfileChange}
        onRefresh={vi.fn()}
        profileName="Local"
        userId="local"
      />
    );

    await waitFor(() => expect(onProfileChange).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "股票数据源" }));
    await screen.findByText("Tushare 主账号");
    fireEvent.change(screen.getByPlaceholderText("已配置，留空则沿用现有密钥"), { target: { value: "secret-stock-token" } });
    fireEvent.click(screen.getByRole("button", { name: "保存数据源" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/v1/desktop/stock-data-sources"), expect.objectContaining({ method: "POST" })));
    fireEvent.click(screen.getByRole("button", { name: "测试连接" }));
    await screen.findByText("12 ms");
    expect(document.body.textContent || "").toContain("[redacted]");
    expect(document.body.textContent || "").not.toContain("secret-stock-token");
  });
});
