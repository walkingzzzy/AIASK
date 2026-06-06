import "@testing-library/jest-dom/vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAgentWorkbench } from "./useAgentWorkbench";
import type { DesktopWorkbenchSummary } from "../types";

// Mock AiaskApi
vi.mock("../services/aiaskApi", () => {
  function AiaskApi() {
    return {
      workbenchSummary: vi.fn().mockResolvedValue({
        recent_sessions: [
          {
            session_id: "sess_001",
            title: "Test Session",
            last_message_at: "2026-06-04T10:00:00Z",
            status: "completed",
          },
        ],
        recent_runs: [
          {
            run_id: "run_001",
            status: "completed",
            tool_call_count: 3,
            approval_count: 1,
          },
        ],
        queues: {
          pending_intents: 0,
          pending_approvals: 0,
          gateway_failed: 0,
          mcp_degraded: 0,
        },
        access: {
          full_mode_active: false,
          control_token_configured: false,
          sessions_admin_available: false,
        },
      } as DesktopWorkbenchSummary),
      response: vi.fn().mockResolvedValue({
        id: "resp_001",
        object: "response",
        status: "completed",
        output_text: "Test response",
        metadata: { session_id: "sess_001", run_id: "run_001" },
      }),
      sessionMessages: vi.fn().mockResolvedValue({ data: [] }),
      runEvents: vi.fn().mockResolvedValue([]),
      getIntent: vi.fn().mockResolvedValue({ success: true, data: {} }),
      confirmIntent: vi.fn().mockResolvedValue({ success: true }),
      denyIntent: vi.fn().mockResolvedValue({ success: true }),
    };
  }

  return { AiaskApi: vi.fn(AiaskApi) };
});

const mockOnAgentStatus = vi.fn();
const mockOnInspectorTab = vi.fn();
const mockOnRunEventsLoaded = vi.fn();

function renderWorkbench(overrides = {}) {
  return renderHook(() =>
    useAgentWorkbench({
      endpoint: "http://127.0.0.1:8767",
      apiToken: "test-token",
      controlToken: "control-token",
      agentMode: "finance_safe",
      canLoadHistory: true,
      userId: "local",
      onAgentStatus: mockOnAgentStatus,
      onInspectorTab: mockOnInspectorTab,
      onRunEventsLoaded: mockOnRunEventsLoaded,
      ...overrides,
    })
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("useAgentWorkbench", () => {
  it("initializes with empty state", () => {
    const { result } = renderWorkbench();

    expect(result.current.prompt).toBe("");
    expect(result.current.sessionId).toBe("");
    expect(result.current.threads).toEqual([]);
    expect(result.current.busy).toBe(false);
    expect(result.current.selectedThread).toBeNull();
  });

  it("loads workbench summary on mount when canLoadHistory is true", async () => {
    const { result } = renderWorkbench({ canLoadHistory: true });

    await waitFor(() => {
      expect(result.current.summary).not.toBeNull();
    });

    expect(result.current.summary?.recent_sessions).toHaveLength(1);
    expect(result.current.summary?.recent_sessions[0].session_id).toBe("sess_001");
    expect(result.current.recentRuns).toHaveLength(1);
  });

  it("does not load summary when canLoadHistory is false", () => {
    const { result } = renderWorkbench({ canLoadHistory: false });

    expect(result.current.summary).toBeNull();
    expect(result.current.recentRuns).toEqual([]);
  });

  it("provides prompt and sessionId setters", () => {
    const { result } = renderWorkbench();

    expect(result.current.setPrompt).toBeInstanceOf(Function);
    expect(result.current.setSessionId).toBeInstanceOf(Function);

    act(() => {
      result.current.setPrompt("test prompt");
    });
    expect(result.current.prompt).toBe("test prompt");

    act(() => {
      result.current.setSessionId("test-session");
    });
    expect(result.current.sessionId).toBe("test-session");
  });

  it("returns timeline events from selected thread", () => {
    const { result } = renderWorkbench();

    expect(result.current.timelineEvents).toEqual([]);
    expect(Array.isArray(result.current.timelineEvents)).toBe(true);
  });

  it("exposes intent management functions", () => {
    const { result } = renderWorkbench();

    expect(result.current.fetchIntent).toBeInstanceOf(Function);
    expect(result.current.updateIntent).toBeInstanceOf(Function);
    expect(result.current.intentEnvelope).toBeNull();
    expect(result.current.intentMessage).toBe("");
  });

  it("provides thread management functions", () => {
    const { result } = renderWorkbench();

    expect(result.current.selectThread).toBeInstanceOf(Function);
    expect(result.current.removeResponseThread).toBeInstanceOf(Function);
    expect(result.current.startNewTask).toBeInstanceOf(Function);
  });

  it("exposes run event loading", () => {
    const { result } = renderWorkbench();

    expect(result.current.loadRunEvents).toBeInstanceOf(Function);
  });
});
