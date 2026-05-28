import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const capabilitiesPayload = {
  object: "aiask.desktop_capabilities",
  summary: {
    source: "gated",
    status: "in_progress",
    counts: { implemented: 1, live_unverified: 0, unconfigured: 0, failed: 0, missing: 0 },
    issue_count: 0,
    control: { authorized: false, reason: "control token is not configured", gated_reason: "control token is not configured" },
    refreshed_at: 1777392000
  },
  hermes: {
    status: { baseline: "Hermes v0.14.0 full runtime capability reference", embedded_vendor_runtime: false },
    parity: {
      object: "aiask.capability_parity",
      baseline: "Hermes v0.14.0 full runtime capability reference",
      scope: "hermes_full_runtime",
      embedded_vendor_runtime: false,
      required_count: 1,
      covered_count: 1,
      complete_count: 0,
      coverage_ratio: 1,
      complete_ratio: 0,
      status: "in_progress",
      matrix: []
    },
    readiness: {},
    tool_mapping: [],
    platform_mapping: [],
    feature_mapping: [],
    issues: []
  },
  mcp: { gated: true, servers: [], tools: [], resources: [], prompts: [], oauth: [] },
  strategy_factory: {},
  skills: { gated: true, reason: "control token is not configured" },
  plugins: { gated: true, reason: "control token is not configured" },
  ai: {
    object: "aiask.ai_status",
    provider: "mock",
    model: "gpt-4.1-mini",
    base_url_configured: false,
    api_key_configured: false,
    mock: true,
    configured: true,
    secrets_redacted: true
  },
  raw_refs: {}
};

const settingsPayload = {
  object: "aiask.desktop_settings",
  agent: {},
  llm: {
    ai_status: capabilitiesPayload.ai,
    providers: {}
  },
  databases: {},
  profile: { user_id: "local", profile_name: "本地操作者" },
  secrets_redacted: true
};

describe("App", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("uses AI-first navigation, settings mode, and advanced shortcuts", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      const payload = url.includes("/v1/desktop/settings/status") ? settingsPayload : capabilitiesPayload;
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    });

    render(<App />);

    await waitFor(() => expect(screen.getByText("你想让 AIASK 做什么？")).toBeInTheDocument());
    expect(screen.getAllByRole("button", { name: "对话" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "技能" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "自动化" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "工作流" }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "总览" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "工作流" }));
    expect(screen.getByRole("heading", { name: "AI 可调用的量化流程" })).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "设置" })[0]);
    expect(screen.getByRole("heading", { name: "设置中心" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "常规" })).toHaveClass("active");
    expect(screen.getByRole("button", { name: "技能管理" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "自动化管理" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "高级诊断入口" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "连接" }));
    expect(screen.getByDisplayValue("http://127.0.0.1:8767")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "高级诊断入口" }));
    fireEvent.click(screen.getByRole("button", { name: /能力中心/ }));
    await waitFor(() => expect(screen.getByText("运行时评审")).toBeInTheDocument());
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8767/v1/desktop/capabilities",
      expect.objectContaining({ method: "GET" })
    );
  });

  it("does not auto-fetch a stale verified endpoint before explicit auto-connect is enabled", async () => {
    window.localStorage.setItem("aiask.endpoint.verified", "1");
    window.localStorage.setItem("aiask.endpoint", "http://127.0.0.1:8767");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(capabilitiesPayload), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );

    render(<App />);

    await waitFor(() => expect(screen.getByText("你想让 AIASK 做什么？")).toBeInTheDocument());
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("offers a reset path when a previously verified non-default endpoint is offline", async () => {
    window.localStorage.setItem("aiask.endpoint.verified", "1");
    window.localStorage.setItem("aiask.endpoint.autoconnect", "1");
    window.localStorage.setItem("aiask.endpoint", "http://127.0.0.1:8769");
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("offline"));

    render(<App />);

    fireEvent.click((await screen.findAllByRole("button", { name: "设置" }))[0]);
    fireEvent.click(screen.getByRole("button", { name: "连接" }));
    expect(screen.getByDisplayValue("http://127.0.0.1:8769")).toBeInTheDocument();
    expect(screen.getByText(/当前端点 http:\/\/127\.0\.0\.1:8769 不可达/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "恢复默认 Agent 端点" }));

    expect(screen.getByDisplayValue("http://127.0.0.1:8767")).toBeInTheDocument();
    expect(window.localStorage.getItem("aiask.endpoint")).toBeNull();
    expect(window.localStorage.getItem("aiask.endpoint.verified")).toBeNull();
    expect(window.localStorage.getItem("aiask.endpoint.autoconnect")).toBeNull();
  });
});
