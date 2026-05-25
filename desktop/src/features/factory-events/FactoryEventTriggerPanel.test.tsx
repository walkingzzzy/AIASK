// PR-G (Phase 5, 2026-05-24) — Factory Event Trigger console test.
//
// Coverage maps to plan §6 Phase 5 acceptance:
//   - View registry exposes a ``factory-events`` route for navigation.
//   - API client helpers send the right URL + payload for the four
//     write actions and for the read tools (factory_event_list /
//     factory_event_preview_tasks).
//   - Without a control token, write buttons are disabled and the UI
//     surfaces a "Read-only" banner — Desktop never bypasses the
//     ActionIntent chain landed in PR-F.
//   - With a control token, the read path renders the mock event list,
//     lineage/status reads, and the maintenance intent buttons.

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AiaskApi } from "../../services/aiaskApi";
import { VIEW_REGISTRY } from "../../views";
import { FactoryEventTriggerPanel } from "./FactoryEventTriggerPanel";

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

function requestBody(call: { init: RequestInit }): Record<string, unknown> {
  return JSON.parse(String(call.init.body || "{}")) as Record<string, unknown>;
}

function makeFetchMock() {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init: init || {} });
    if (url.includes("/v1/tools/agent_strategy_manager")) {
      const body = init && typeof init.body === "string" ? JSON.parse(init.body) : {};
      const action = String(body.action || "");
      if (action === "factory_event_list") {
        return jsonResponse({
          success: true,
          error: null,
          data: {
            events: [
              {
                event_id: "evt_test_001",
                event_name: "稀土出口管制(test)",
                event_type: "policy_shock",
                event_source: "manual",
                status: "active",
                direction: "bullish",
                intensity: 0.85,
                confidence: 0.7,
                primary_themes: ["critical_minerals"],
                operator_id: "operator_alice",
                approver_id: "approver_bob",
                created_at: "2026-05-24T08:00:00Z"
              }
            ],
            count: 1
          }
        });
      }
      if (action === "factory_event_preview_tasks") {
        return jsonResponse({
          success: true,
          error: null,
          data: {
            event_id: "evt_test_001",
            impacts: [{ theme_code: "critical_minerals", depth: 0, magnitude: 0.85 }],
            candidate_symbols: ["600111", "600259"],
            target_count: 2,
            warnings: [],
            preview_mode: "real_bfs"
          }
        });
      }
      if (action === "factory_event_lineage") {
        return jsonResponse({
          success: true,
          error: null,
          data: {
            lineage: [
              {
                lineage_id: 1,
                dedupe_key: "evt_test_001:critical_minerals:600111-600259",
                event_id: "evt_test_001",
                event_name: "lineage test",
                event_status: "active",
                task_id: "event_evt_test_001_critical_minerals_abcd1234",
                theme_code: "critical_minerals",
                impact_direction: "positive",
                impact_magnitude: 0.85,
                target_symbols: ["600111", "600259"],
                target_count: 2,
                breadth_resolved: "narrow",
                generated_at: "2026-05-24T08:10:00Z",
                gate_1_passed: 1,
                strategies_submitted: 1
              }
            ],
            count: 1
          }
        });
      }
      if (action === "factory_theme_exposure_status") {
        return jsonResponse({
          success: true,
          error: null,
          data: {
            row_count: 42,
            symbol_count: 12,
            theme_count: 3,
            latest_updated_at: "2026-05-24T08:20:00Z"
          }
        });
      }
      if (action === "factory_event_outbox_status") {
        return jsonResponse({
          success: true,
          error: null,
          data: {
            counts: { processed: 2, failed: 0 },
            latest: []
          }
        });
      }
      return jsonResponse({ success: true, error: null, data: {} });
    }
    if (url.includes("/intents") && url.endsWith("/confirm")) {
      return jsonResponse({ success: true, error: null, data: { intent: { status: "succeeded" } } });
    }
    if (url.includes("/intents") && !url.includes("/confirm") && !url.includes("/deny")) {
      return jsonResponse({
        success: true,
        error: null,
        data: { intent: { intent_id: "intent_phase5_test", status: "awaiting_confirmation" } }
      });
    }
    return jsonResponse({ success: true, error: null, data: {} });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

describe("VIEW_REGISTRY", () => {
  it("includes the factory-events route exposed by Phase 5", () => {
    const ids = VIEW_REGISTRY.map((entry) => entry.id);
    expect(ids).toContain("factory-events");
    const entry = VIEW_REGISTRY.find((item) => item.id === "factory-events");
    expect(entry?.label).toBe("Factory Events");
  });
});

describe("AiaskApi factory event helpers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
  });

  it("calls agent_strategy_manager with action=factory_event_list and JSON kwargs", async () => {
    const { calls } = makeFetchMock();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767", apiToken: "api-token", controlToken: "control-token" });

    await api.factoryEventList({ status: "active", event_source: "manual", limit: 50 });

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("http://127.0.0.1:8767/v1/tools/agent_strategy_manager");
    expect(calls[0].init.method).toBe("POST");
    const body = requestBody(calls[0]);
    expect(body.action).toBe("factory_event_list");
    // ``kwargs`` is a JSON string per the strategy_manager contract.
    const kwargs = JSON.parse(String(body.kwargs)) as Record<string, unknown>;
    expect(kwargs).toEqual({ status: "active", event_source: "manual", limit: 50 });
    // empty / undefined values are stripped before serialization.
    await api.factoryEventList({ status: "active", event_source: "", event_type: undefined });
    const trimmed = JSON.parse(String(requestBody(calls[1]).kwargs));
    expect(trimmed).toEqual({ status: "active" });
  });

  it("preview helper carries event_id in kwargs", async () => {
    const { calls } = makeFetchMock();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767", apiToken: "api-token", controlToken: "control-token" });
    await api.factoryEventPreviewTasks("evt_xyz");
    const body = requestBody(calls[0]);
    expect(body.action).toBe("factory_event_preview_tasks");
    expect(JSON.parse(String(body.kwargs))).toEqual({ event_id: "evt_xyz" });
  });

  it("write helpers create ActionIntents with the strategy_manager prefix", async () => {
    const { calls } = makeFetchMock();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767", apiToken: "api-token", controlToken: "control-token" });

    await api.factoryEventCreateIntent({ event_name: "n", primary_themes: ["t"] }, "create test");
    await api.factoryEventApproveIntent("evt_1", "approver_bob", "approve test");
    await api.factoryEventUpdateIntent("evt_1", { status: "paused" }, "pause test");
    await api.factoryEventRecordOutcomeIntent("evt_1", { outcome_description: "x" }, "outcome test");

    expect(calls).toHaveLength(4);
    expect(calls.every((call) => call.url === "http://127.0.0.1:8767/intents")).toBe(true);
    expect(calls.every((call) => call.init.method === "POST")).toBe(true);
    expect(
      calls.every(
        (call) => (call.init.headers as Record<string, string>).Authorization === "Bearer control-token"
      )
    ).toBe(true);
    const actions = calls.map((call) => requestBody(call).action);
    expect(actions).toEqual([
      "strategy_manager.factory_event_create",
      "strategy_manager.factory_event_approve",
      "strategy_manager.factory_event_update",
      "strategy_manager.factory_event_record_outcome"
    ]);
    // approve carries event_id + approver_id (the self-approval guard
    // depends on both fields being present).
    expect(requestBody(calls[1]).params).toEqual({ event_id: "evt_1", approver_id: "approver_bob" });
    expect(requestBody(calls[2]).params).toEqual({ event_id: "evt_1", status: "paused" });
    expect(requestBody(calls[3]).params).toEqual({ event_id: "evt_1", outcome_description: "x" });
  });

  it("lineage/status helpers use read-only manager actions", async () => {
    const { calls } = makeFetchMock();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767", apiToken: "api-token", controlToken: "control-token" });

    await api.factoryEventLineage({ event_id: "evt_1", limit: 20 });
    await api.factoryThemeExposureStatus({});
    await api.factoryEventOutboxStatus({ limit: 10 });

    const actions = calls.map((call) => requestBody(call).action);
    expect(actions).toEqual([
      "factory_event_lineage",
      "factory_theme_exposure_status",
      "factory_event_outbox_status"
    ]);
    expect(JSON.parse(String(requestBody(calls[0]).kwargs))).toEqual({ event_id: "evt_1", limit: 20 });
    expect(JSON.parse(String(requestBody(calls[2]).kwargs))).toEqual({ limit: 10 });
  });

  it("maintenance helpers create confirm-required Strategy Manager intents", async () => {
    const { calls } = makeFetchMock();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767", apiToken: "api-token", controlToken: "control-token" });

    await api.factoryThemeExposureRefreshIntent({ batch_size: 1000 });
    await api.factoryEventOutboxDrainIntent({ limit: 20 });
    await api.factoryThemeRegressionRunIntent({});

    const actions = calls.map((call) => requestBody(call).action);
    expect(actions).toEqual([
      "strategy_manager.factory_theme_exposure_refresh",
      "strategy_manager.factory_event_outbox_drain",
      "strategy_manager.factory_theme_regression_run"
    ]);
    expect(requestBody(calls[0]).params).toEqual({ batch_size: 1000 });
    expect(requestBody(calls[1]).params).toEqual({ limit: 20 });
  });

  it("confirm/deny helpers use the right intent route and control token", async () => {
    const { calls } = makeFetchMock();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767", apiToken: "api-token", controlToken: "control-token" });

    await api.confirmIntent("intent_xyz");
    await api.denyIntent("intent_abc", "stale");

    expect(calls[0].url).toBe("http://127.0.0.1:8767/intents/intent_xyz/confirm");
    expect(calls[1].url).toBe("http://127.0.0.1:8767/intents/intent_abc/deny");
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBe("Bearer control-token");
    expect(requestBody(calls[1])).toEqual({ reason: "stale" });
  });
});

describe("FactoryEventTriggerPanel render", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
  });

  it("renders the read-only banner when controlToken is empty", async () => {
    makeFetchMock();
    render(
      <FactoryEventTriggerPanel
        endpoint="http://127.0.0.1:8767"
        apiToken="api-token"
        controlToken=""
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("factory-event-trigger-panel")).toBeInTheDocument();
    });
    // Status cluster shows the read-only banner.
    expect(screen.getByText("Read-only (no control token)")).toBeInTheDocument();
    // Banner copy explains the boundary.
    expect(
      screen.getByText(/All write actions \(create \/ approve \/ pause \/ record outcome\)/i)
    ).toBeInTheDocument();
  });

  it("loads the mock event list and switches between tabs with a control token", async () => {
    const { calls } = makeFetchMock();
    render(
      <FactoryEventTriggerPanel
        endpoint="http://127.0.0.1:8767"
        apiToken="api-token"
        controlToken="control-token"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("稀土出口管制(test)")).toBeInTheDocument();
    });
    // factory_event_list was called via agent_strategy_manager.
    expect(calls.some((call) => call.url.includes("/v1/tools/agent_strategy_manager"))).toBe(true);

    // Switch to Create tab.
    fireEvent.click(screen.getByRole("tab", { name: "Create" }));
    expect(screen.getByText("All writes go through ActionIntent")).toBeInTheDocument();
    // Switch to Preview tab — empty until an event is selected.
    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    expect(screen.getByText("BFS propagation + candidate basket")).toBeInTheDocument();
    // Switch to Lineage tab.
    fireEvent.click(screen.getByRole("tab", { name: "Lineage" }));
    expect(screen.getByText("Persisted event lineage")).toBeInTheDocument();
    expect(screen.getByText("event_evt_test_001_critical_minerals_abcd1234")).toBeInTheDocument();
    expect(screen.getByText("Recent intent dispatches")).toBeInTheDocument();
  });

  it("disables Approve / Pause when controlToken is missing", async () => {
    makeFetchMock();
    render(
      <FactoryEventTriggerPanel
        endpoint="http://127.0.0.1:8767"
        apiToken="api-token"
        controlToken=""
      />
    );
    await waitFor(() => {
      // The mock event list still renders without control token, since
      // factory_event_list is read-only.
      expect(screen.getByText("稀土出口管制(test)")).toBeInTheDocument();
    });
    // The active mock event has status=active, so the visible action
    // button is "Pause" — and it must be disabled without a control token.
    const pauseButton = screen.getByRole("button", { name: /Pause/i });
    expect(pauseButton).toBeDisabled();
  });
});
