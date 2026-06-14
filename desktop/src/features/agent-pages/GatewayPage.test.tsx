import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GatewayPage } from "./GatewayPage";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("GatewayPage", () => {
  const props = {
    endpoint: "mock://aiask",
    apiToken: "test-token",
    controlToken: "mock-control-token",
    userId: "local",
  };

  it("renders gateway health, daemon, messages, directory, and failed retry state", async () => {
    render(<GatewayPage {...props} />);

    expect(screen.getByRole("heading", { name: "Gateway", level: 1 })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("Gateway 已加载").length).toBeGreaterThan(0));

    expect(screen.getByText("守护进程状态")).toBeInTheDocument();
    expect(screen.getByText("平台健康")).toBeInTheDocument();
    expect(screen.getByText("目录刷新")).toBeInTheDocument();
    expect(screen.getAllByText("msg_gateway_failed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("missing DISCORD_BOT_TOKEN").length).toBeGreaterThan(0);
    expect(screen.getByText("失败消息 (1)")).toBeInTheDocument();
  });

  it("keeps management data gated without a control token", async () => {
    render(<GatewayPage {...props} controlToken="" />);

    await waitFor(() => expect(screen.getByText("缺少控制令牌")).toBeInTheDocument());
    expect(screen.getByText(/Gateway 管理详情需要控制令牌/)).toBeInTheDocument();
    expect(screen.getByText("暂无 Gateway 消息。")).toBeInTheDocument();
    expect(screen.queryByText("msg_gateway_failed")).not.toBeInTheDocument();
  });

  it("retries failed messages and creates send intents only", async () => {
    render(<GatewayPage {...props} />);

    await waitFor(() => expect(screen.getAllByText("msg_gateway_failed").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole("button", { name: "重试" })[0]);
    await waitFor(() => expect(screen.getAllByText("Gateway 已加载").length).toBeGreaterThan(0));

    fireEvent.change(screen.getByPlaceholderText("channel/user/room"), { target: { value: "ops-alerts" } });
    fireEvent.click(screen.getByRole("button", { name: "创建发送审批" }));
    await waitFor(() => expect(screen.getByText("发送审批已创建")).toBeInTheDocument());
    expect(screen.getAllByText(/gateway\.send_message/).length).toBeGreaterThan(0);
  });
});
