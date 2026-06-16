/**
 * FE-111: SessionsPage 组件测试
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { resetMockApiState } from "../../mockApi";
import { SessionsPage } from "./SessionsPage";

afterEach(() => {
  cleanup();
  resetMockApiState();
  vi.clearAllMocks();
});

describe("SessionsPage", () => {
  const mockProps = {
    endpoint: "mock://aiask",
    apiToken: "test-token",
    controlToken: "mock-control-token",
    userId: "local",
    fullModeActive: true,
    sessionsAdminAvailable: true,
  };

  it("应该渲染页面标题", () => {
    render(<SessionsPage {...mockProps} />);
    expect(screen.getByText("会话")).toBeInTheDocument();
  });

  it("无权限时应显示锁定提示", () => {
    render(<SessionsPage {...mockProps} fullModeActive={false} controlToken="" />);
    expect(screen.getByText(/需要完整模式和控制令牌/)).toBeInTheDocument();
  });

  it("应该显示搜索框", async () => {
    render(<SessionsPage {...mockProps} />);
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/搜索会话/)).toBeInTheDocument();
    });
  });

  it("应该显示筛选选项", async () => {
    render(<SessionsPage {...mockProps} />);
    await waitFor(() => {
      expect(screen.getByText("所有会话")).toBeInTheDocument();
      expect(screen.getByText("最近活跃（7天）")).toBeInTheDocument();
      expect(screen.getByText("有审批")).toBeInTheDocument();
    });
  });

  it("应该显示排序选项", async () => {
    render(<SessionsPage {...mockProps} />);
    await waitFor(() => {
      expect(screen.getByText("最近活跃")).toBeInTheDocument();
      expect(screen.getByText("创建时间")).toBeInTheDocument();
      expect(screen.getByText("消息数量")).toBeInTheDocument();
    });
  });

  it("应该展示最近运行摘要、审批标记和继续会话入口", async () => {
    const onResumeSession = vi.fn();
    render(<SessionsPage {...mockProps} onResumeSession={onResumeSession} />);

    await waitFor(() => expect(screen.getByText("Mock 研究会话")).toBeInTheDocument());
    expect(screen.getAllByText("有审批").length).toBeGreaterThan(0);
    expect(screen.getByText("run_mock")).toBeInTheDocument();
    expect(screen.getByText("approval.intent_created")).toBeInTheDocument();

    const resumeButton = screen.getByRole("button", { name: /继续会话/ });
    await waitFor(() => expect(resumeButton).not.toBeDisabled());
    fireEvent.click(resumeButton);
    await waitFor(() =>
      expect(onResumeSession).toHaveBeenCalledWith(
        "sess_mock",
        expect.objectContaining({
          resume_context: expect.objectContaining({ context_snapshot_id: "ctxsnap_mock_source" }),
        })
      )
    );
  });

  it("应该展示会话交接接管状态和上下文快照", async () => {
    render(<SessionsPage {...mockProps} />);

    await waitFor(() => expect(screen.getByText("Mock 研究会话")).toBeInTheDocument());

    expect(screen.getByText(/交接队列 1/)).toBeInTheDocument();
    expect(screen.getByText("接管: risk_specialist")).toBeInTheDocument();
    expect(screen.getByLabelText("会话交接状态")).toHaveTextContent("risk_specialist");
    expect(screen.getByLabelText("会话交接状态")).toHaveTextContent("ctxsnap_mock_source");
    expect(screen.getByText("risk escalation")).toBeInTheDocument();
    expect(screen.getByText("Continue with risk review.")).toBeInTheDocument();
  });

  it("应该在继续会话后展示恢复上下文", async () => {
    render(<SessionsPage {...mockProps} />);

    await waitFor(() => expect(screen.getByText("Mock 研究会话")).toBeInTheDocument());
    const resumeButton = screen.getByRole("button", { name: /继续会话/ });
    await waitFor(() => expect(resumeButton).not.toBeDisabled());
    fireEvent.click(resumeButton);

    await waitFor(() => expect(screen.getByText("RESUME_CONTEXT_LOADED")).toBeInTheDocument());
    expect(screen.getByLabelText("会话恢复上下文")).toHaveTextContent("ctxsnap_mock_source");
    expect(screen.getByLabelText("会话恢复上下文")).toHaveTextContent("risk_specialist");
    expect(screen.getByLabelText("会话恢复上下文")).toHaveTextContent("mock_resume");
  });

  it("应该支持有审批筛选", async () => {
    render(<SessionsPage {...mockProps} />);

    await waitFor(() => expect(screen.getByText("Mock 研究会话")).toBeInTheDocument());
    fireEvent.change(screen.getByDisplayValue("所有会话"), { target: { value: "has_pending_approval" } });

    expect(screen.getByText("Mock 研究会话")).toBeInTheDocument();
    expect(screen.getByText(/1 \/ 1 个会话/)).toBeInTheDocument();
  });

  it("supports undoing the last loaded turn", async () => {
    render(<SessionsPage {...mockProps} />);

    await waitFor(() => expect(screen.getByText("mock question")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Undo last turn"));

    await waitFor(() => expect(screen.getByText("UNDO_1_TURNS")).toBeInTheDocument());
    expect(screen.queryByText("mock question")).not.toBeInTheDocument();
  });

  it("supports archiving and restoring a session", async () => {
    render(<SessionsPage {...mockProps} />);

    await waitFor(() => expect(screen.getByText("Mock 研究会话")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Archive"));

    await waitFor(() => expect(screen.getByText("SESSION_ARCHIVED")).toBeInTheDocument());
    expect(screen.queryByText("Mock 研究会话")).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("显示归档"));
    await waitFor(() => expect(screen.getByText("Mock 研究会话")).toBeInTheDocument());
    expect(screen.getByText("已归档")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Restore"));
    await waitFor(() => expect(screen.getByText("SESSION_RESTORED")).toBeInTheDocument());
    expect(screen.queryByText("已归档")).not.toBeInTheDocument();
  });
});
