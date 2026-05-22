import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WorkbenchView } from "./WorkbenchView";

const noop = vi.fn();

function renderWorkbench(options: { controlToken?: string; prompt?: string } = {}) {
  render(
    <WorkbenchView
      agentMode="finance_safe"
      busy={false}
      controlToken={options.controlToken || ""}
      endpoint="http://127.0.0.1:8768"
      health={{ status: "ok", service: "aiask-agent" }}
      onAgentModeChange={noop}
      onComposerKeyDown={noop}
      onPromptChange={noop}
      onRefresh={noop}
      onSessionIdChange={noop}
      onSubmit={noop}
      prompt={options.prompt || ""}
      selectedThread={null}
      sessionId=""
      status="AIASK_ONLINE"
      timelineEvents={[]}
      tools={[
        { name: "agent_quote", capability: "market", category: "finance", side_effect: "read_only", description: "Read quote" },
        {
          name: "agent_structured",
          capability: "mcp",
          category: "mcp_financial",
          side_effect: { level: "read_only", target: "sector_manager" },
          description: "Structured tool"
        }
      ]}
    />
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("WorkbenchView", () => {
  it("renders Codex-style review queue counts and composer disabled state", () => {
    renderWorkbench();

    expect(screen.getByText("Current thread state")).toBeInTheDocument();
    expect(screen.getByText("2 read-only actions available.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hermes full" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Run" })).toBeDisabled();
  });

  it("enables Hermes full mode selector when a control token exists", () => {
    renderWorkbench({ controlToken: "secret", prompt: "inspect tools" });

    expect(screen.getByRole("button", { name: "Hermes full" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Run" })).toBeEnabled();
  });
});
