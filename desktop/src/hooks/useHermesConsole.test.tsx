import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useHermesConsole } from "./useHermesConsole";

const hermesStatus = {
  object: "aiask.hermes_status",
  implementation: "aiask_native",
  baseline: "Hermes v0.16.0 full runtime capability reference",
  embedded_vendor_runtime: false,
  full_mode_enabled: true,
  full_mode_active: false,
  parity: {
    object: "aiask.capability_parity",
    baseline: "Hermes v0.16.0 full runtime capability reference",
    baseline_version: "0.16.0",
    baseline_release_tag: "v2026.6.5",
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
  providers: { status: "ready" },
  memory: { status: "ready" },
  acp: { status: "ready" },
  security: { status: "ready" },
  skill_packs: { status: "ready" }
};

function parityPayload() {
  return hermesStatus.parity;
}

function mockResponse(value: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(value), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    })
  );
}

function Harness({ controlToken = "" }: { controlToken?: string }) {
  const consoleState = useHermesConsole("http://127.0.0.1:8767", "", controlToken);
  return (
    <div>
      <button onClick={() => consoleState.refresh().catch(() => undefined)} type="button">refresh</button>
      <span data-testid="message">{consoleState.message}</span>
      <span data-testid="tool-count">{consoleState.hermesTools.length}</span>
    </div>
  );
}

describe("useHermesConsole", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("returns a gated snapshot without control token", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/v1/hermes/status")) return mockResponse(hermesStatus);
      if (url.includes("/v1/capabilities/parity")) return mockResponse(parityPayload());
      if (url.includes("/v1/hermes/readiness")) return mockResponse({ plugins: [] });
      return mockResponse({ data: [] });
    });

    render(<Harness />);
    fireEvent.click(screen.getByText("refresh"));

    await waitFor(() => expect(screen.getByTestId("message")).toHaveTextContent("CONTROL_TOKEN_REQUIRED"));
    expect(screen.getByTestId("tool-count")).toHaveTextContent("0");
    expect(fetchMock.mock.calls.map((call) => String(call[0])).join(" ")).not.toContain("/v1/hermes/tools");
  });

  it("loads full mode control surfaces when a control token is present", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/v1/hermes/status")) return mockResponse(hermesStatus);
      if (url.includes("/v1/capabilities/parity")) return mockResponse(parityPayload());
      if (url.includes("/v1/hermes/readiness")) return mockResponse({ plugins: [{ status: "ready" }] });
      if (url.includes("/v1/hermes/tools")) {
        return mockResponse({ data: [{ name: "agent_moa", capability: "delegate", side_effect: "read_only", description: "MOA" }] });
      }
      if (url.includes("/v1/rl/environments")) return mockResponse({ data: {} });
      return mockResponse({ data: [] });
    });

    render(<Harness controlToken="secret" />);
    fireEvent.click(screen.getByText("refresh"));

    await waitFor(() => expect(screen.getByTestId("message")).toHaveTextContent("FULL_CONSOLE_SYNCED"));
    expect(screen.getByTestId("tool-count")).toHaveTextContent("1");
  });
});
