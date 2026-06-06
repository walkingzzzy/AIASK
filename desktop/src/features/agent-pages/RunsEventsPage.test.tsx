/**
 * FE-111: RunsEventsPage 组件测试
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RunsEventsPage } from "./RunsEventsPage";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("RunsEventsPage", () => {
  const mockProps = {
    endpoint: "mock://aiask",
    apiToken: "test-token",
    controlToken: "mock-control-token",
    onOpenView: vi.fn(),
  };

  it("应该渲染页面标题", () => {
    render(<RunsEventsPage {...mockProps} />);
    expect(screen.getByText("Runs / Events")).toBeInTheDocument();
  });

  it("应该显示运行摘要区域", () => {
    render(<RunsEventsPage {...mockProps} />);
    expect(screen.getByText("运行摘要")).toBeInTheDocument();
  });

  it("应该显示运行事件区域", () => {
    render(<RunsEventsPage {...mockProps} />);
    expect(screen.getByText("运行事件")).toBeInTheDocument();
  });

  it("应该显示事件筛选器", () => {
    render(<RunsEventsPage {...mockProps} />);
    expect(screen.getByText("all")).toBeInTheDocument();
    expect(screen.getByText("tool")).toBeInTheDocument();
    expect(screen.getByText("approval")).toBeInTheDocument();
  });

  it("应该显示视图模式切换", () => {
    render(<RunsEventsPage {...mockProps} />);
    expect(screen.getByText("Timeline")).toBeInTheDocument();
    expect(screen.getByText("List")).toBeInTheDocument();
  });

  it("应该展示归一化事件字段和固定跳转目标", async () => {
    render(<RunsEventsPage {...mockProps} />);

    await waitFor(() => expect(screen.getAllByText("run_mock").length).toBeGreaterThan(0));
    expect(screen.getByText("tool.called: agent_analyze_stock")).toBeInTheDocument();
    expect(screen.getByText("approval.intent_created")).toBeInTheDocument();
    expect(screen.getByText("agent_analyze_stock")).toBeInTheDocument();
    expect(screen.getAllByText(/跳转到 tools-intents-approvals/).length).toBeGreaterThan(0);
  });

  it("应该按 approval 事件筛选并触发跳转", async () => {
    const onOpenView = vi.fn();
    render(<RunsEventsPage {...mockProps} onOpenView={onOpenView} />);

    await waitFor(() => expect(screen.getByText("approval.intent_created")).toBeInTheDocument());
    fireEvent.change(screen.getByDisplayValue("all"), { target: { value: "approval" } });

    expect(screen.queryByText("tool.called: agent_analyze_stock")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/跳转到 tools-intents-approvals/));
    expect(onOpenView).toHaveBeenCalledWith("tools-intents-approvals");
  });
});
