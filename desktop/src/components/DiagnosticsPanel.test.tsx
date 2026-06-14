import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DiagnosticsPanel } from "./DiagnosticsPanel";

afterEach(() => {
  cleanup();
});

describe("DiagnosticsPanel", () => {
  const baseProps = {
    apiToken: "api-token",
    busy: false,
    controlToken: "mock-control-token",
    endpoint: "mock://aiask",
    fullConsole: {
      gatewayStatus: { status: "ready" },
      terminalBackends: [{ name: "local-powershell", shell: "powershell", status: "ready" }],
      terminalSessions: [{ session_id: "terminal_mock", backend: "local-powershell", status: "idle" }],
      plugins: [],
      mcpTools: []
    },
    health: { status: "ok", service: "aiask" },
    hermesStatus: {
      object: "aiask.hermes_status",
      implementation: "aiask_native",
      baseline: "Hermes v0.16.0 full runtime capability reference",
      embedded_vendor_runtime: false,
      full_mode_enabled: true,
      full_mode_active: true,
      evaluated_toolset: "general_full"
    },
    message: "FULL_CONSOLE_SYNCED",
    onRefresh: vi.fn()
  };

  it("loads terminal backend sessions through the readonly API", async () => {
    render(<DiagnosticsPanel {...baseProps} />);

    fireEvent.click(screen.getByText("终端"));
    fireEvent.click(screen.getByRole("button", { name: "加载终端会话" }));

    await waitFor(() => expect(screen.getByText("TERMINAL_BACKEND_SESSIONS_LOADED")).toBeInTheDocument());
    expect(screen.getAllByText(/terminal_mock/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/local-powershell/).length).toBeGreaterThan(0);
  });

  it("loads terminal backends when the full console snapshot has not populated them yet", async () => {
    render(
      <DiagnosticsPanel
        {...baseProps}
        fullConsole={{ gatewayStatus: { status: "ready" }, plugins: [], mcpTools: [] }}
      />
    );

    fireEvent.click(screen.getByText("终端"));

    await waitFor(() => expect(screen.getByText("TERMINAL_BACKENDS_LOADED")).toBeInTheDocument());
    expect(screen.getAllByText(/local-powershell/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "加载终端会话" })).toBeEnabled();
  });
});
