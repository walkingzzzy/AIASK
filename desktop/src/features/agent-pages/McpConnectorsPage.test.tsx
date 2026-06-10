import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { McpConnectorsPage } from "./McpConnectorsPage";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("McpConnectorsPage", () => {
  const props = {
    endpoint: "mock://aiask",
    apiToken: "test-token",
    controlToken: "mock-control-token",
  };

  it("renders MCP aggregate sections and connector summary/list state", async () => {
    render(<McpConnectorsPage {...props} />);

    expect(screen.getByText("MCP / 连接器")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("能力已同步").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText("连接器已加载").length).toBeGreaterThan(0));

    expect(screen.getByText("MCP 服务器")).toBeInTheDocument();
    expect(screen.getByText("MCP 工具")).toBeInTheDocument();
    expect(screen.getByText("MCP 资源")).toBeInTheDocument();
    expect(screen.getByText("提示词 / OAuth")).toBeInTheDocument();
    expect(screen.getByText("连接器摘要")).toBeInTheDocument();
    expect(screen.getByText("连接器列表")).toBeInTheDocument();
    expect(screen.getAllByText("agent_mcp_akshare_get_realtime_quote").length).toBeGreaterThan(0);
    expect(screen.getAllByText("AIASK_MCP_AKSHARE_LOCAL_AUTHORIZATION").length).toBeGreaterThan(0);
    expect(screen.getAllByText("discord").length).toBeGreaterThan(0);
  });

  it("loads connector detail and test result through Agent HTTP routes", async () => {
    render(<McpConnectorsPage {...props} />);

    await waitFor(() => expect(screen.getAllByText("akshare-local").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole("button", { name: "详情" })[0]);
    await waitFor(() => expect(screen.getAllByText("连接器详情已加载").length).toBeGreaterThan(0));
    expect(screen.getByText("连接器详情")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "测试" })[0]);
    await waitFor(() => expect(screen.getAllByText("连接器测试完成").length).toBeGreaterThan(0));
    expect(screen.getByText(/connector\.test/)).toBeInTheDocument();
  });

  it("runs the read-only MCP smoke through resource and prompt Agent routes", async () => {
    render(<McpConnectorsPage {...props} />);

    await waitFor(() => expect(screen.getAllByText("连接器已加载").length).toBeGreaterThan(0));
    expect(screen.getByRole("heading", { name: "MCP 只读调用冒烟测试" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "运行 MCP 只读冒烟测试" }));

    await waitFor(() => expect(screen.getAllByText("只读冒烟测试已完成").length).toBeGreaterThan(0));
    expect(screen.getAllByText(/quote resource ok/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/risk prompt ok/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("/v1/mcp/resources/read").length).toBeGreaterThan(0);
    expect(screen.getAllByText("/v1/mcp/prompts/get").length).toBeGreaterThan(0);
  });
});
