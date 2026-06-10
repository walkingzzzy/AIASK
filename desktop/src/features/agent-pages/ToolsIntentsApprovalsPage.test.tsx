/**
 * FE-111: ToolsIntentsApprovalsPage 组件测试
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ToolsIntentsApprovalsPage } from "./ToolsIntentsApprovalsPage";
import type { ToolCatalogItem } from "../../types";

afterEach(() => {
  cleanup();
});

describe("ToolsIntentsApprovalsPage", () => {
  const mockTools: ToolCatalogItem[] = [
    {
      name: "agent_test",
      capability: "test",
      description: "测试工具",
      side_effect: "read_only",
      visibility: "api_safe",
      interaction_mode: "read_only",
    },
    {
      name: "agent_stateful",
      capability: "stateful",
      description: "intent tool",
      side_effect: "stateful",
      visibility: "full_mode_only",
      interaction_mode: "intent",
      confirmation_required: true,
    },
    {
      name: "agent_blocked",
      capability: "blocked",
      description: "blocked tool",
      side_effect: "trade_risk",
      visibility: "full_mode_only",
      interaction_mode: "blocked",
      blocked_reason: "blocked in test",
    },
  ];

  const mockProps = {
    endpoint: "mock://aiask",
    apiToken: "test-token",
    controlToken: "mock-control-token",
    tools: mockTools,
    hermesTools: [
      {
        name: "agent_full_only",
        capability: "full",
        description: "Hermes full reference only",
        side_effect: "read_only",
        visibility: "full_mode_only",
      },
    ] as ToolCatalogItem[],
  };

  it("应该渲染页面标题", () => {
    render(<ToolsIntentsApprovalsPage {...mockProps} />);
    expect(screen.getByText("工具 / 意图 / 审批")).toBeInTheDocument();
  });

  it("应该显示工具目录", () => {
    render(<ToolsIntentsApprovalsPage {...mockProps} />);
    expect(screen.getByText("工具目录")).toBeInTheDocument();
  });

  it("应该显示工具数量", () => {
    render(<ToolsIntentsApprovalsPage {...mockProps} />);
    expect(screen.getByText(/3 \/ 3 个工具/)).toBeInTheDocument();
  });

  it("应该显示工具搜索框", () => {
    render(<ToolsIntentsApprovalsPage {...mockProps} />);
    expect(screen.getByPlaceholderText(/搜索工具名称/)).toBeInTheDocument();
  });

  it("应该显示筛选选项", () => {
    render(<ToolsIntentsApprovalsPage {...mockProps} />);
    expect(screen.getByText("所有工具")).toBeInTheDocument();
    expect(screen.getByText("金融安全")).toBeInTheDocument();
    expect(screen.getByText("Intent")).toBeInTheDocument();
    expect(screen.getByText("需审批")).toBeInTheDocument();
    expect(screen.getAllByText("已阻塞").length).toBeGreaterThan(0);
  });

  it("应该显示 Intents 区域", () => {
    render(<ToolsIntentsApprovalsPage {...mockProps} />);
    expect(screen.getByText("Intents")).toBeInTheDocument();
  });

  it("应该明确显示安全标签并只保留单一工具目录", async () => {
    render(<ToolsIntentsApprovalsPage {...mockProps} />);

    expect(screen.getByText("agent_test")).toBeInTheDocument();
    expect(screen.getAllByText("金融安全").length).toBeGreaterThan(0);
    expect(screen.getAllByText("只读").length).toBeGreaterThan(0);
    expect(screen.getAllByText("full_mode_only").length).toBeGreaterThan(0);
    expect(screen.getAllByText("已阻塞").length).toBeGreaterThan(0);
    expect(screen.queryByText("可用操作与安全探测")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/Hermes full 工具只作为契约对照数据读取/)).toBeInTheDocument());
  });

  it("应该支持 blocked 筛选和详情面板", () => {
    render(<ToolsIntentsApprovalsPage {...mockProps} />);

    fireEvent.change(screen.getByDisplayValue("所有工具"), { target: { value: "blocked" } });
    expect(screen.getByText("agent_blocked")).toBeInTheDocument();
    expect(screen.queryByText("agent_test")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("详情"));
    expect(screen.getByText("blocked in test")).toBeInTheDocument();
  });
});
