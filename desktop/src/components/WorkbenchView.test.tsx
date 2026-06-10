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
    mockMode: true,
    onAgentModeChange: vi.fn(),
    onComposerKeyDown: vi.fn(),
    onOpenView: vi.fn(),
    onPromptChange: vi.fn(),
    onRefresh: vi.fn(),
    onSessionIdChange: vi.fn(),
    onSubmit: vi.fn(),
    prompt: "",
    profileName: "Test user",
    recentRuns: [] as DesktopRunSummary[],
    selectedThread: null as TaskThread | null,
    sessionId: "",
    status: "AIASK_ONLINE",
    summary: null as DesktopWorkbenchSummary | null,
    timelineEvents: [] as TimelineEvent[],
    tools: [] as ToolCatalogItem[],
    userId: "local",
  };

  it("renders the task object header", () => {
    render(<WorkbenchView {...mockProps} />);
    expect(screen.getByText("AIASK 工作台")).toBeInTheDocument();
    expect(screen.getByText("http://127.0.0.1:8767")).toBeInTheDocument();
    expect(screen.getAllByText("Mock").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Test user/).length).toBeGreaterThan(0);
  });

  it("shows current mode and access summary", () => {
    render(<WorkbenchView {...mockProps} />);
    expect(screen.getAllByText("finance_safe").length).toBeGreaterThan(0);
    expect(screen.getByText("权限")).toBeInTheDocument();
    expect(screen.getByText("安全模式")).toBeInTheDocument();
  });

  it("shows recent sessions and runs", () => {
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
          title: "Test session",
          last_message_at: "2026-06-04T10:00:00Z",
        },
      ],
    };
    const runs: DesktopRunSummary[] = [
      {
        run_id: "run_001",
        status: "completed",
        tool_call_count: 3,
        approval_count: 1,
        error_count: 0,
      },
    ];

    render(<WorkbenchView {...mockProps} summary={summaryWithSessions} recentRuns={runs} />);
    expect(screen.getByText("最近会话")).toBeInTheDocument();
    expect(screen.getByText("Test session")).toBeInTheDocument();
    expect(screen.getByText("最近运行")).toBeInTheDocument();
    expect(screen.getAllByText("run_001").length).toBeGreaterThan(0);
  });

  it("shows operational queue and context actions", () => {
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
    expect(screen.getByText("操作队列")).toBeInTheDocument();
    expect(screen.getByText("意图")).toBeInTheDocument();
    expect(screen.getAllByText("审批").length).toBeGreaterThan(0);
    expect(screen.getAllByText("项目 / 上下文").length).toBeGreaterThan(0);
    expect(screen.getAllByText("金融实验室").length).toBeGreaterThan(0);
    expect(screen.getAllByText("集成").length).toBeGreaterThan(0);
  });

  it("shows Hermes full guidance when control token is missing", () => {
    render(<WorkbenchView {...mockProps} agentMode="hermes_full" controlToken="" />);
    expect(screen.getByText(/Hermes full 需要先在 Settings 中填写控制令牌/)).toBeInTheDocument();
  });

  it("shows artifact and review panels", () => {
    const thread: TaskThread = {
      id: "thread_1",
      title: "Review a strategy",
      prompt: "Analyze strategy output",
      createdAt: "2026-06-08T10:00:00Z",
      status: "queued",
      sessionId: "sess_1",
      runId: "run_1"
    };

    render(<WorkbenchView {...mockProps} selectedThread={thread} />);
    expect(screen.getByText("任务产物")).toBeInTheDocument();
    expect(screen.getByText("审查队列")).toBeInTheDocument();
    expect(screen.getAllByText("Review a strategy").length).toBeGreaterThan(0);
  });

  it("shows tool count", () => {
    const tools: ToolCatalogItem[] = [
      {
        name: "agent_test",
        capability: "test",
        description: "test tool",
        side_effect: "read_only",
      },
    ];

    render(<WorkbenchView {...mockProps} tools={tools} />);
    expect(screen.getByText("1 个工具可用")).toBeInTheDocument();
  });
});
