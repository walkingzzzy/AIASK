import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
    expect(screen.getByText(/http:\/\/127\.0\.0\.1:8767/)).toBeInTheDocument();
    expect(screen.getAllByText("演示数据").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Test user/).length).toBeGreaterThan(0);
  });

  it("shows current mode and access summary", () => {
    render(<WorkbenchView {...mockProps} />);
    expect(screen.getAllByText("金融安全模式").length).toBeGreaterThan(0);
    expect(screen.getByText("可用范围")).toBeInTheDocument();
    expect(screen.getByText(/API 令牌已填写/)).toBeInTheDocument();
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

  it("surfaces the financial agent safe path from the workbench", () => {
    const onOpenView = vi.fn();
    const tools: ToolCatalogItem[] = [
      {
        name: "agent_memory_search",
        capability: "memory_search",
        description: "Search financial memory.",
        side_effect: "read_only",
      },
      {
        name: "agent_session_search",
        capability: "session_search",
        description: "Search sessions.",
        side_effect: "read_only",
      },
      {
        name: "agent_portfolio_risk",
        capability: "portfolio_risk",
        description: "Portfolio risk.",
        side_effect: "read_only",
      },
      {
        name: "agent_quant_data_gate",
        capability: "quant_data_gate",
        description: "Data gate.",
        side_effect: "read_only",
      },
      {
        name: "agent_factory_status",
        capability: "factory_status",
        description: "Factory status.",
        side_effect: "read_only",
      },
    ];

    render(<WorkbenchView {...mockProps} onOpenView={onOpenView} tools={tools} />);
    expect(screen.getByRole("region", { name: "金融 Agent 安全链路" })).toBeInTheDocument();
    expect(screen.getByText("现在可以复核什么")).toBeInTheDocument();
    expect(screen.getByText("3. 记忆 / 搜索")).toBeInTheDocument();
    expect(screen.getByText("6. 工厂接力")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "打开金融经理台" }));
    fireEvent.click(screen.getByRole("button", { name: "打开数据" }));
    expect(onOpenView).toHaveBeenCalledWith("financial-manager");
    expect(onOpenView).toHaveBeenCalledWith("data");
  });

  it("shows Hermes full guidance when control token is missing", () => {
    render(<WorkbenchView {...mockProps} agentMode="hermes_full" controlToken="" />);
    expect(screen.getByText(/Hermes full 需要先在 Settings 中填写控制令牌/)).toBeInTheDocument();
  });

  it("shows artifact and review panels from durable artifact records", () => {
    const thread: TaskThread = {
      id: "thread_1",
      title: "Review a strategy",
      prompt: "Analyze strategy output",
      createdAt: "2026-06-08T10:00:00Z",
      status: "queued",
      sessionId: "sess_1",
      runId: "run_1"
    };

    render(
      <WorkbenchView
        {...mockProps}
        selectedThread={thread}
        selectedRunArtifacts={[
          {
            artifact_id: "art_terminal",
            kind: "terminal_output",
            title: "Terminal output",
            preview_text: "pytest failed",
            status: "failed",
            run_id: "run_1",
          },
        ]}
      />
    );
    expect(screen.getByText("任务产物")).toBeInTheDocument();
    expect(screen.getByText("审查队列")).toBeInTheDocument();
    expect(screen.getAllByText("Terminal output").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Open evidence/ })).toHaveAttribute(
      "href",
      "http://127.0.0.1:8767/v1/artifacts/art_terminal/content?max_bytes=1048576"
    );
  });

  it("does not infer artifacts from the selected thread alone", () => {
    render(
      <WorkbenchView
        {...mockProps}
        selectedThread={{
          id: "thread_1",
          title: "Review a strategy",
          prompt: "Analyze strategy output",
          createdAt: "2026-06-08T10:00:00Z",
          status: "queued",
          sessionId: "sess_1",
          runId: "run_1",
        }}
      />
    );

    expect(screen.getByText("No durable artifacts")).toBeInTheDocument();
    expect(screen.queryByText("sessions/sess_1")).not.toBeInTheDocument();
  });

  it("shows durable source evidence with links", () => {
    render(
      <WorkbenchView
        {...mockProps}
        selectedRunSources={[
          {
            source_id: "src_1",
            source_type: "news",
            title: "Linked market news",
            url: "https://example.com/market-news",
            provider: "eastmoney",
            fetched_at: "2026-06-12T09:00:00Z",
          },
        ]}
      />
    );

    expect(screen.getAllByText("来源证据").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Linked market news").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /https:\/\/example\.com\/market-news/ })).toHaveAttribute("href", "https://example.com/market-news");
  });

  it("shows quote, news, script, and terminal evidence as clickable cards", () => {
    render(
      <WorkbenchView
        {...mockProps}
        selectedRunArtifacts={[
          {
            artifact_id: "art_quote",
            kind: "quote_snapshot",
            title: "600519 realtime quote",
            preview_text: "price 123.45",
            status: "ready",
          },
          {
            artifact_id: "art_script",
            kind: "script",
            title: "analysis_snippet.py",
            path: "C:/tmp/analysis_snippet.py",
            preview_text: "print('quote')",
            status: "ready",
          },
          {
            artifact_id: "art_terminal",
            kind: "terminal_output",
            title: "Terminal output",
            preview_text: "PASS evidence cards",
            status: "ready",
          },
        ]}
        selectedRunSources={[
          {
            source_id: "src_quote",
            source_type: "market_quote",
            title: "sina quote provider",
            provider: "sina",
          },
          {
            source_id: "src_news",
            source_type: "news",
            title: "Linked market news",
            url: "https://example.com/market-news",
            provider: "eastmoney",
          },
        ]}
      />
    );

    expect(screen.getByText("600519 realtime quote")).toBeInTheDocument();
    expect(screen.getByText("analysis_snippet.py")).toBeInTheDocument();
    expect(screen.getByText("Terminal output")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /src_quote/ })).toHaveAttribute("href", "http://127.0.0.1:8767/v1/sources/src_quote");
    expect(screen.getByRole("link", { name: /https:\/\/example\.com\/market-news/ })).toHaveAttribute("href", "https://example.com/market-news");
    const evidenceLinks = screen.getAllByRole("link", { name: /Open evidence/ }).map((link) => link.getAttribute("href"));
    expect(evidenceLinks).toEqual(expect.arrayContaining([
      "http://127.0.0.1:8767/v1/artifacts/art_quote/content?max_bytes=1048576",
      "http://127.0.0.1:8767/v1/artifacts/art_script/content?max_bytes=1048576",
      "http://127.0.0.1:8767/v1/artifacts/art_terminal/content?max_bytes=1048576",
    ]));
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
