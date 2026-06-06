/**
 * FE-111: SessionsPage 组件测试
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionsPage } from "./SessionsPage";

afterEach(() => {
  cleanup();
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
    expect(screen.getByText("Sessions")).toBeInTheDocument();
  });

  it("无权限时应显示锁定提示", () => {
    render(<SessionsPage {...mockProps} fullModeActive={false} controlToken="" />);
    expect(screen.getByText(/需要 full mode \+ control token/)).toBeInTheDocument();
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

    await waitFor(() => expect(screen.getByText("Mock research session")).toBeInTheDocument());
    expect(screen.getAllByText("approval").length).toBeGreaterThan(0);
    expect(screen.getByText("run_mock")).toBeInTheDocument();
    expect(screen.getByText("approval.intent_created")).toBeInTheDocument();

    fireEvent.click(screen.getByText("继续会话"));
    expect(onResumeSession).toHaveBeenCalledWith("sess_mock");
  });

  it("应该支持有审批筛选", async () => {
    render(<SessionsPage {...mockProps} />);

    await waitFor(() => expect(screen.getByText("Mock research session")).toBeInTheDocument());
    fireEvent.change(screen.getByDisplayValue("所有会话"), { target: { value: "has_pending_approval" } });

    expect(screen.getByText("Mock research session")).toBeInTheDocument();
    expect(screen.getByText(/1 \/ 1 个会话/)).toBeInTheDocument();
  });
});
