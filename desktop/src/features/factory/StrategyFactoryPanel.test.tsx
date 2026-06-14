import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CapabilityWorkbenchPayload } from "../../types";
import { StrategyFactoryPanel } from "./StrategyFactoryPanel";

const payload: CapabilityWorkbenchPayload = {
  object: "aiask.desktop_capabilities",
  summary: {
    status: "ready",
    counts: {},
    issue_count: 0,
    control: { authorized: true },
    refreshed_at: 0
  },
  hermes: {
    status: {},
    parity: {
      object: "aiask.capability_parity",
      baseline: "test",
      scope: "desktop",
      embedded_vendor_runtime: false,
      required_count: 0,
      covered_count: 0,
      complete_count: 0,
      coverage_ratio: 1,
      complete_ratio: 1,
      status: "ready",
      matrix: []
    },
    readiness: {},
    tool_mapping: [],
    platform_mapping: [],
    feature_mapping: [],
    issues: []
  },
  mcp: {
    gated: false,
    servers: [],
    tools: [],
    resources: [],
    prompts: [],
    oauth: []
  },
  strategy_factory: {
    status: {
      success: true,
      data: { configured: true, database_configured: true, database_backend: "sqlite", status: "ready" },
      error: null
    },
    runs: {
      success: true,
      data: { configured: true, database_configured: true, latest_run_id: "run_factory_1" },
      error: null
    },
    review_snapshot: {
      success: true,
      data: { configured: true, accepted_count: 2, rejected_count: 1 },
      error: null
    }
  },
  skills: { skills: [] },
  ai: {
    object: "aiask.ai_status",
    provider: "mock",
    model: "mock",
    base_url_configured: true,
    api_key_configured: true,
    mock: true,
    configured: true,
    secrets_redacted: true
  },
  raw_refs: {}
};

describe("StrategyFactoryPanel", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("creates a guarded run intent and renders a scan-friendly intent summary", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      if (url.pathname === "/intents") {
        return new Response(
          JSON.stringify({
            success: true,
            data: {
              intent: {
                intent_id: "intent_strategy_1",
                action: "factory_run_once",
                target_tool: "agent_action_intent_create",
                target_action: "factory_run_once",
                status: "awaiting_confirmation",
                params: { execution_mode: "desktop_approved_once", source: "desktop_strategy_factory" }
              }
            },
            error: null,
            meta: {
              side_effect: {
                level: "durable_intent",
                target: "factory_run_once",
                confirmation_required: true,
                control_token: "control-secret-value-1234567890"
              }
            }
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response(JSON.stringify({ error: url.pathname }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <StrategyFactoryPanel
        apiToken="api-token"
        controlToken="control-token"
        endpoint="http://127.0.0.1:8767"
        payload={payload}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "创建运行意图" }));

    await waitFor(() => expect(screen.getByText("intent_strategy_1")).toBeInTheDocument());
    expect(screen.getAllByText("factory_run_once").length).toBeGreaterThan(0);
    expect(screen.getByText("awaiting_confirmation")).toBeInTheDocument();
    expect(screen.getAllByText("agent_action_intent_create").length).toBeGreaterThan(0);
    expect(screen.getByText("desktop_approved_once")).toBeInTheDocument();
    expect(screen.getByText("durable_intent")).toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8767/intents",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ Authorization: "Bearer control-token" })
      })
    );
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toMatchObject({
      action: "factory_run_once",
      params: { execution_mode: "desktop_approved_once", source: "desktop_strategy_factory" },
      rationale: "从桌面控制面板运行一次策略工厂。"
    });
    expect(document.body.textContent || "").toContain("[redacted]");
    expect(document.body.textContent || "").not.toContain("control-secret-value");
  });

  it("surfaces recurring strict-incubation blockers from factory status", () => {
    const blockerPayload: CapabilityWorkbenchPayload = {
      ...payload,
      strategy_factory: {
        ...payload.strategy_factory,
        status: {
          success: true,
          error: null,
          data: {
            configured: true,
            database_configured: true,
            strict_incubation_blocker_summary: {
              status: "blocked",
              headline: "Recent runs still fail formal admission because strict incubation readiness is zero.",
              analyzed_run_count: 5,
              submitted_count: 35,
              strict_not_ready_count: 20,
              raw_b_or_above_count: 10,
              raw_b_or_above_rate: 0.5,
              strict_ready_given_raw_b_count: 0,
              strict_ready_given_raw_b_rate: 0,
              observe_lane_count: 18,
              diagnostic_lane_count: 2,
              next_action: "Persist the executable DSL/runtime contract and replay admission.",
              top_blockers: [
                {
                  reason_code: "diagnostic_only_not_allowed_for_incubation",
                  count: 15,
                  label: "Diagnostic-only runtime cannot enter formal incubation.",
                  next_action: "Route only non-diagnostic runtime evidence to formal incubation."
                },
                {
                  reason_code: "default_profile_not_allowed_for_single_name_runtime",
                  count: 10,
                  label: "Default runtime profile is not allowed for single-name formal runtime.",
                  next_action: "Attach a single-name runtime profile before requesting formal admission."
                },
                {
                  reason_code: "execution_readiness_tier:missing_executable_contract",
                  count: 10,
                  label: "Executable contract readiness is missing.",
                  next_action: "Persist the executable DSL/runtime contract and replay admission."
                }
              ],
              sample_blocked_strategies: [
                {
                  strategy_id: "factory_blocked_1",
                  family: "momentum",
                  grade: "A",
                  submission_lane: "observe_incubation",
                  blockers: [
                    "diagnostic_only_not_allowed_for_incubation",
                    "default_profile_not_allowed_for_single_name_runtime",
                    "execution_readiness_tier:missing_executable_contract"
                  ]
                }
              ]
            }
          }
        }
      }
    };

    render(
      <StrategyFactoryPanel
        apiToken="api-token"
        controlToken="control-token"
        endpoint="http://127.0.0.1:8767"
        payload={blockerPayload}
      />
    );

    expect(screen.getByRole("heading", { name: "Strict-incubation blockers" })).toBeInTheDocument();
    expect(screen.getByText("Recent runs still fail formal admission because strict incubation readiness is zero.")).toBeInTheDocument();
    expect(screen.getByText("Diagnostic-only runtime cannot enter formal incubation.")).toBeInTheDocument();
    expect(screen.getByText("Default runtime profile is not allowed for single-name formal runtime.")).toBeInTheDocument();
    expect(screen.getByText("Executable contract readiness is missing.")).toBeInTheDocument();
    expect(screen.getByText("factory_blocked_1")).toBeInTheDocument();
  });
});
