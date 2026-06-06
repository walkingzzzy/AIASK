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

    expect(screen.getByText("MCP / Connectors")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("CAPABILITIES_SYNCED").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText("CONNECTORS_LOADED").length).toBeGreaterThan(0));

    expect(screen.getByText("MCP servers")).toBeInTheDocument();
    expect(screen.getByText("MCP tools")).toBeInTheDocument();
    expect(screen.getByText("MCP resources")).toBeInTheDocument();
    expect(screen.getByText("Prompts / OAuth")).toBeInTheDocument();
    expect(screen.getByText("Connectors summary")).toBeInTheDocument();
    expect(screen.getByText("Connector list")).toBeInTheDocument();
    expect(screen.getAllByText("agent_mcp_akshare_get_realtime_quote").length).toBeGreaterThan(0);
    expect(screen.getAllByText("AIASK_MCP_AKSHARE_LOCAL_AUTHORIZATION").length).toBeGreaterThan(0);
    expect(screen.getAllByText("discord").length).toBeGreaterThan(0);
  });

  it("loads connector detail and test result through Agent HTTP routes", async () => {
    render(<McpConnectorsPage {...props} />);

    await waitFor(() => expect(screen.getAllByText("akshare-local").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole("button", { name: "详情" })[0]);
    await waitFor(() => expect(screen.getAllByText("CONNECTOR_DETAIL_LOADED").length).toBeGreaterThan(0));
    expect(screen.getByText("Connector detail")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "测试" })[0]);
    await waitFor(() => expect(screen.getAllByText("CONNECTOR_TESTED").length).toBeGreaterThan(0));
    expect(screen.getByText(/connector\.test/)).toBeInTheDocument();
  });
});
