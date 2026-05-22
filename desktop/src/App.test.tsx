import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const capabilitiesPayload = {
  object: "aiask.desktop_capabilities",
  summary: {
    source: "gated",
    status: "in_progress",
    counts: { implemented: 1, live_unverified: 0, unconfigured: 0, failed: 0, missing: 0 },
    issue_count: 0,
    control: { authorized: false, reason: "control token is not configured", gated_reason: "control token is not configured" },
    refreshed_at: 1777392000
  },
  hermes: {
    status: { baseline: "Hermes v0.14.0 full runtime capability reference", embedded_vendor_runtime: false },
    parity: {
      object: "aiask.capability_parity",
      baseline: "Hermes v0.14.0 full runtime capability reference",
      scope: "hermes_full_runtime",
      embedded_vendor_runtime: false,
      required_count: 1,
      covered_count: 1,
      complete_count: 0,
      coverage_ratio: 1,
      complete_ratio: 0,
      status: "in_progress",
      matrix: []
    },
    readiness: {},
    tool_mapping: [],
    platform_mapping: [],
    feature_mapping: [],
    issues: []
  },
  mcp: { gated: true, servers: [], tools: [], resources: [], prompts: [], oauth: [] },
  strategy_factory: {},
  skills: { gated: true, reason: "control token is not configured" },
  plugins: { gated: true, reason: "control token is not configured" },
  ai: {
    object: "aiask.ai_status",
    provider: "mock",
    model: "gpt-4.1-mini",
    base_url_configured: false,
    api_key_configured: false,
    mock: true,
    configured: true,
    secrets_redacted: true
  },
  raw_refs: {}
};

describe("App", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("uses the view registry to navigate overview, workbench, capabilities, and settings", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(capabilitiesPayload), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );

    render(<App />);

    await waitFor(() => expect(screen.getByText("Unified command console")).toBeInTheDocument());
    expect(screen.getByText("Agent, model providers, databases, MCP, skills, automation, and the three factories are shown as one operator surface.")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Agent" })[0]);
    expect(screen.getByText("What should AIASK work on?")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Settings" })[0]);
    expect(screen.getByText("Configuration center")).toBeInTheDocument();
    expect(screen.getByDisplayValue("http://127.0.0.1:8767")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Capabilities" }));
    await waitFor(() => expect(screen.getByText("Runtime review")).toBeInTheDocument());
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8767/v1/desktop/capabilities",
      expect.objectContaining({ method: "GET" })
    );
  });

  it("does not auto-fetch a stale verified endpoint before explicit auto-connect is enabled", async () => {
    window.localStorage.setItem("aiask.endpoint.verified", "1");
    window.localStorage.setItem("aiask.endpoint", "http://127.0.0.1:8767");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(capabilitiesPayload), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );

    render(<App />);

    await waitFor(() => expect(screen.getByText("Unified command console")).toBeInTheDocument());
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
