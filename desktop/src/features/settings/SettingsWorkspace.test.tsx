import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SettingsWorkspace } from "./SettingsWorkspace";

describe("SettingsWorkspace", () => {
  it("renders local schema-driven connection fields", () => {
    const onEndpointChange = vi.fn();
    const onAgentModeChange = vi.fn();

    render(
      <SettingsWorkspace
        agentMode="finance_safe"
        apiToken="api-secret"
        busy={false}
        controlToken="control-secret"
        endpoint="http://127.0.0.1:8767"
        health={{ status: "ok", service: "aiask", hermes: { full_mode_enabled: true }, control: { token_configured: true } }}
        onAgentModeChange={onAgentModeChange}
        onApiTokenChange={vi.fn()}
        onControlTokenChange={vi.fn()}
        onEndpointChange={onEndpointChange}
        onProfileChange={vi.fn()}
        onRefresh={vi.fn()}
        profileName="Local Operator"
        userId="local"
      />
    );

    expect(screen.getByText("Configuration center")).toBeInTheDocument();
    expect(screen.getByDisplayValue("http://127.0.0.1:8767")).toBeInTheDocument();
    expect(screen.getByDisplayValue("api-secret")).toHaveAttribute("type", "password");
    expect(screen.getByDisplayValue("control-secret")).toHaveAttribute("type", "password");

    fireEvent.change(screen.getByDisplayValue("http://127.0.0.1:8767"), { target: { value: "http://127.0.0.1:9000" } });
    expect(onEndpointChange).toHaveBeenCalledWith("http://127.0.0.1:9000");

    fireEvent.change(screen.getByDisplayValue("finance_safe"), { target: { value: "hermes_full" } });
    expect(onAgentModeChange).toHaveBeenCalledWith("hermes_full");
  });
});
