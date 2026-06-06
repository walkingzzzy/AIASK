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
    await waitFor(() => expect(screen.getAllByText("GATEWAY_LOADED").length).toBeGreaterThan(0));

    expect(screen.getByText("Daemon status")).toBeInTheDocument();
    expect(screen.getByText("Platform health")).toBeInTheDocument();
    expect(screen.getByText("Directory refresh")).toBeInTheDocument();
    expect(screen.getAllByText("msg_gateway_failed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("missing DISCORD_BOT_TOKEN").length).toBeGreaterThan(0);
    expect(screen.getByText("失败消息 (1)")).toBeInTheDocument();
  });

  it("retries failed messages and creates send intents only", async () => {
    render(<GatewayPage {...props} />);

    await waitFor(() => expect(screen.getAllByText("msg_gateway_failed").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole("button", { name: "重试" })[0]);
    await waitFor(() => expect(screen.getAllByText("GATEWAY_LOADED").length).toBeGreaterThan(0));

    fireEvent.change(screen.getByPlaceholderText("channel/user/room"), { target: { value: "ops-alerts" } });
    fireEvent.click(screen.getByRole("button", { name: "创建发送审批" }));
    await waitFor(() => expect(screen.getByText("GATEWAY_INTENT_CREATED")).toBeInTheDocument());
    expect(screen.getAllByText(/gateway\.send_message/).length).toBeGreaterThan(0);
  });
});
