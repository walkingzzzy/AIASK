/**
 * FE-110: WorkbenchView 组件测试
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WorkbenchView } from "./WorkbenchView";
import type { DesktopRunSummary, DesktopWorkbenchSummary, HealthDetailed, TaskThread, TimelineEvent, ToolCatalogItem } from "../types";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("WorkbenchView", () => {
  const mockProps = {
    agentMode: "finance_safe" as const,
    apiToken: "test-token",
    busy: false,
    controlToken: "",
    endpoint: "http://127.0.0.1:8767",
    health: {
      status: "online",
      service: "aiask",
    } as HealthDetailed,
    onAgentModeChange: vi.fn(),
    onComposerKeyDown: vi.fn(),
    onOpenView: vi.fn(),
    onPromptChange: vi.fn(),
    onRefresh: vi.fn(),
    onSessionIdChange: vi.fn(),
    onSubmit: vi.fn(),
    prompt: "",
    profileName: "测试用户",
    recentRuns: [] as DesktopRunSummary[],
    selectedThread: null as TaskThread | null,
    sessionId: "",
    status: "AIASK_ONLINE",
    summary: null as DesktopWorkbenchSummary | null,
    timelineEvents: [] as TimelineEvent[],
    tools: [] as ToolCatalogItem[],
    userId: "local",
  };

  it("应该渲染 Workbench 标题", () => {
    render(<WorkbenchView {...mockProps} />);
    expect(screen.getByText("AIASK Workbench")).toBeInTheDocument();
  });

  it("应该显示端点信息", () => {
    render(<WorkbenchView {...mockProps} />);
    expect(screen.getByText("http://127.0.0.1:8767")).toBeInTheDocument();
  });

  it("应该显示用户信息", () => {
    render(<WorkbenchView {...mockProps} />);
    expect(screen.getByText(/测试用户/)).toBeInTheDocument();
    expect(screen.getByText(/local/)).toBeInTheDocument();
  });

  it("应该显示当前模式", () => {
    render(<WorkbenchView {...mockProps} />);
    expect(screen.getAllByText("finance_safe").length).toBeGreaterThan(0);
  });

  it("应该显示最近会话区域", () => {
    const summaryWithSessions: DesktopWorkbenchSummary = {
      access: {
        full_mode_active: false,
        sessions_admin_available: false,
      },
      queues: {
        pending_intents: 0,
        pending_approvals: 0,
        gateway_failed: 0,
        mcp_degraded: 0,
      },
      recent_sessions: [
        {
          session_id: "sess_001",
          title: "测试会话",
          last_message_at: "2026-06-04T10:00:00Z",
        },
      ],
    };

    render(<WorkbenchView {...mockProps} summary={summaryWithSessions} />);
    expect(screen.getByText("最近会话")).toBeInTheDocument();
    expect(screen.getByText("测试会话")).toBeInTheDocument();
  });

  it("应该显示最近运行摘要", () => {
    const runs: DesktopRunSummary[] = [
      {
        run_id: "run_001",
        status: "completed",
        tool_call_count: 3,
        approval_count: 1,
        error_count: 0,
      },
    ];

    render(<WorkbenchView {...mockProps} recentRuns={runs} />);
    expect(screen.getByText("最近运行")).toBeInTheDocument();
    expect(screen.getByText("run_001")).toBeInTheDocument();
  });

  it("应该显示待处理队列", () => {
    const summaryWithQueues: DesktopWorkbenchSummary = {
      access: {
        full_mode_active: false,
        sessions_admin_available: false,
      },
      queues: {
        pending_intents: 2,
        pending_approvals: 1,
        gateway_failed: 0,
        mcp_degraded: 0,
      },
      recent_sessions: [],
    };

    render(<WorkbenchView {...mockProps} summary={summaryWithQueues} />);
    expect(screen.getByText("待处理队列")).toBeInTheDocument();
    expect(screen.getByText("Intents")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("应该显示快速链接", () => {
    render(<WorkbenchView {...mockProps} />);
    expect(screen.getAllByText("Readiness").length).toBeGreaterThan(0);
    expect(screen.getByText("Tools / Intents / Approvals")).toBeInTheDocument();
    expect(screen.getByText("MCP / Connectors")).toBeInTheDocument();
    expect(screen.getAllByText("Gateway").length).toBeGreaterThan(0);
  });

  it("Hermes full 模式需要 control token", () => {
    render(<WorkbenchView {...mockProps} agentMode="hermes_full" controlToken="" />);
    expect(screen.getByText(/Hermes full 模式需要先在 Settings/)).toBeInTheDocument();
  });

  it("Full mode 激活时应显示可用状态", () => {
    const summaryWithFullMode: DesktopWorkbenchSummary = {
      access: {
        full_mode_active: true,
        sessions_admin_available: true,
      },
      queues: {
        pending_intents: 0,
        pending_approvals: 0,
        gateway_failed: 0,
        mcp_degraded: 0,
      },
      recent_sessions: [],
    };

    render(<WorkbenchView {...mockProps} summary={summaryWithFullMode} controlToken="test-control" />);
    expect(screen.getByText("可用")).toBeInTheDocument();
  });

  it("应该显示工具数量", () => {
    const tools: ToolCatalogItem[] = [
      {
        name: "agent_test",
        capability: "test",
        description: "测试工具",
        side_effect: "read_only",
      },
    ];

    render(<WorkbenchView {...mockProps} tools={tools} />);
    expect(screen.getByText("1 个工具可用")).toBeInTheDocument();
  });
});
