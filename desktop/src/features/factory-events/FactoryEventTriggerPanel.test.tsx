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

function intentRequests(calls: Array<{ url: string; init: RequestInit }>) {
  return calls.filter((call) => call.url.endsWith("/intents"));
}

function makeFetchMock(options: { failRadarCandidatesAfter?: number } = {}) {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  let radarCandidatesCalls = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init: init || {} });
    if (url.includes("/v1/tools/agent_factory_event_list")) {
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
            },
            {
              event_id: "evt_test_002",
              event_name: "AI 芯片新规(test)",
              event_type: "regulation",
              event_source: "news_llm",
              status: "pending_review",
              direction: "bearish",
              intensity: 0.6,
              confidence: 0.65,
              primary_themes: ["AI_chip"],
              operator_id: "operator_charlie",
              approver_id: "",
              created_at: "2026-05-24T07:30:00Z"
            }
          ],
          count: 2
        }
      });
    }
    if (url.includes("/v1/tools/agent_factory_event_preview_tasks")) {
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
    if (url.includes("/v1/tools/agent_factory_event_lineage")) {
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
    if (url.includes("/v1/tools/agent_factory_theme_exposure_status")) {
      return jsonResponse({ success: true, error: null, data: { row_count: 42, symbol_count: 12, theme_count: 3, latest_updated_at: "2026-05-24T08:20:00Z" } });
    }
    if (url.includes("/v1/tools/agent_factory_event_outbox_status")) {
      return jsonResponse({ success: true, error: null, data: { counts: { processed: 2, failed: 0 }, latest: [] } });
    }
    if (url.includes("/v1/desktop/stock-radar/status")) {
      return jsonResponse({
        success: true,
        error: null,
        data: {
          status: "ready",
          counts: { alert: 1, watch: 1, observe: 0, reject: 0 },
          degraded_flags: [],
          latest_run: { run_id: "radar_component_test", status: "completed" },
          digest_preview: "雷达摘要：观察池只读预览。"
        }
      });
    }
    if (url.includes("/v1/desktop/stock-radar/candidates")) {
      radarCandidatesCalls += 1;
      if (options.failRadarCandidatesAfter && radarCandidatesCalls > options.failRadarCandidatesAfter) {
        return new Response(JSON.stringify({ error: "radar candidates failed" }), {
          status: 500,
          headers: { "Content-Type": "application/json" }
        });
      }
      return jsonResponse({
        success: true,
        error: null,
        data: {
          status: "ready",
          candidates: [
            {
              candidate_id: "radar_candidate_component_001",
              run_id: "radar_component_test",
              symbol: "600111",
              stock_name: "北方稀土",
              tier: "alert",
              radar_score: 84.5,
              event_type: "policy_shock",
              direction: "bullish",
              summary: "稀土出口管制事件触发观察池候选。",
              source_doc_uids: ["doc_radar_001", "doc_radar_002"],
              source_chain: [{ uid: "doc_radar_001", kind: "news" }],
              extraction: { confidence: 0.82 },
              confirmations: { cross_source: true },
              risk_flags: []
            }
          ],
          count: 1
        }
      });
    }
    if (url.includes("/v1/desktop/stock-radar/digest")) {
      return jsonResponse({
        success: true,
        error: null,
        data: {
          status: "ready",
          digest_preview: "企微 / Telegram 预览：北方稀土进入观察池，不含交易指令。"
        }
      });
    }
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
              },
              {
                event_id: "evt_test_002",
                event_name: "AI 芯片新规(test)",
                event_type: "regulation",
                event_source: "news_llm",
                status: "pending_review",
                direction: "bearish",
                intensity: 0.6,
                confidence: 0.65,
                primary_themes: ["AI_chip"],
                operator_id: "operator_charlie",
                approver_id: "",
                created_at: "2026-05-24T07:30:00Z"
              }
            ],
            count: 2
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
      const body = init && typeof init.body === "string" ? JSON.parse(init.body) : {};
      return jsonResponse({
        success: true,
        error: null,
        data: { intent: { intent_id: "intent_phase5_test", status: "awaiting_confirmation", action: body.action, target_action: body.action } }
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
    expect(entry?.label).toBe("工厂事件");
    expect(entry?.route).toBe("/factory-events");
  });
});

describe("AiaskApi factory event helpers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
  });

  it("calls the Agent factory event facade with cleaned filters", async () => {
    const { calls } = makeFetchMock();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767", apiToken: "api-token", controlToken: "control-token" });

    await api.factoryEventList({ status: "active", event_source: "manual", limit: 50 });

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("http://127.0.0.1:8767/v1/tools/agent_factory_event_list");
    expect(calls[0].init.method).toBe("POST");
    const body = requestBody(calls[0]);
    expect(body).toEqual({ status: "active", source: "manual", limit: 50 });
    // empty / undefined values are stripped before serialization.
    await api.factoryEventList({ status: "active", event_source: "", event_type: undefined });
    expect(requestBody(calls[1])).toEqual({ status: "active" });
  });

  it("preview helper carries event_id to the facade", async () => {
    const { calls } = makeFetchMock();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767", apiToken: "api-token", controlToken: "control-token" });
    await api.factoryEventPreviewTasks("evt_xyz");
    const body = requestBody(calls[0]);
    expect(calls[0].url).toBe("http://127.0.0.1:8767/v1/tools/agent_factory_event_preview_tasks");
    expect(body).toEqual({ event_id: "evt_xyz" });
  });

  it("write helpers create ActionIntents with the strategy_manager prefix", async () => {
    const { calls } = makeFetchMock();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767", apiToken: "api-token", controlToken: "control-token" });

    await api.factoryEventCreateIntent({ event_name: "n", source: "manual", primary_themes: ["t"] }, "create test");
    await api.factoryEventApproveIntent("evt_1", "approver_bob", "approve test");
    await api.factoryEventUpdateIntent("evt_1", { status: "paused" }, "pause test");
    await api.factoryEventRecordOutcomeIntent(
      "evt_1",
      { actual_outcome: "positive", outcome_notes: "x" },
      "outcome test"
    );

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
    expect(requestBody(calls[0]).params).toEqual({ event_name: "n", source: "manual", primary_themes: ["t"] });
    expect((requestBody(calls[0]).params as Record<string, unknown>).event_source).toBeUndefined();
    // approve carries event_id + approver_id (the self-approval guard
    // depends on both fields being present).
    expect(requestBody(calls[1]).params).toEqual({ event_id: "evt_1", approver_id: "approver_bob" });
    expect(requestBody(calls[2]).params).toEqual({ event_id: "evt_1", status: "paused" });
    expect(requestBody(calls[3]).params).toEqual({
      event_id: "evt_1",
      actual_outcome: "positive",
      outcome_notes: "x"
    });
  });

  it("lineage/status helpers use read-only Agent facade tools", async () => {
    const { calls } = makeFetchMock();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767", apiToken: "api-token", controlToken: "control-token" });

    await api.factoryEventLineage({ event_id: "evt_1", limit: 20 });
    await api.factoryThemeExposureStatus({});
    await api.factoryEventOutboxStatus({ limit: 10 });

    const urls = calls.map((call) => call.url);
    expect(urls).toEqual([
      "http://127.0.0.1:8767/v1/tools/agent_factory_event_lineage",
      "http://127.0.0.1:8767/v1/tools/agent_factory_theme_exposure_status",
      "http://127.0.0.1:8767/v1/tools/agent_factory_event_outbox_status"
    ]);
    expect(requestBody(calls[0])).toEqual({ event_id: "evt_1", limit: 20 });
    expect(requestBody(calls[2])).toEqual({ limit: 10 });
  });

  it("maintenance helpers create confirm-required Strategy Manager intents", async () => {
    const { calls } = makeFetchMock();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767", apiToken: "api-token", controlToken: "control-token" });

    await api.factoryEventBootstrapIntent({ batch_size: 1000, refresh_exposure: true });
    await api.factoryThemeExposureRefreshIntent({ batch_size: 1000 });
    await api.factoryEventOutboxDrainIntent({ limit: 20 });
    await api.factoryThemeRegressionRunIntent({});

    const actions = calls.map((call) => requestBody(call).action);
    expect(actions).toEqual([
      "strategy_manager.factory_event_bootstrap",
      "strategy_manager.factory_theme_exposure_refresh",
      "strategy_manager.factory_event_outbox_drain",
      "strategy_manager.factory_theme_regression_run"
    ]);
    expect(requestBody(calls[0]).params).toEqual({ batch_size: 1000, refresh_exposure: true });
    expect(requestBody(calls[1]).params).toEqual({ batch_size: 1000 });
    expect(requestBody(calls[2]).params).toEqual({ limit: 20 });
  });

  it("stock radar helpers use read routes and confirm-required radar intents", async () => {
    const { calls } = makeFetchMock();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767", apiToken: "api-token", controlToken: "control-token" });

    await api.stockRadarStatus({ limit: 10 });
    await api.stockRadarCandidates({ tier: "alert", limit: 5 });
    await api.stockRadarDigest({ channels: ["wecom", "telegram"] });
    await api.stockRadarRunIntent({ days: 3, allow_network: false });
    await api.stockRadarPushDigestIntent({ run_id: "radar_1", dry_run: true });
    await api.stockRadarScheduleUpdateIntent({ schedule: "manual", enabled: false });

    expect(calls[0].url).toBe("http://127.0.0.1:8767/v1/desktop/stock-radar/status?limit=10");
    expect(calls[1].url).toBe("http://127.0.0.1:8767/v1/desktop/stock-radar/candidates?tier=alert&limit=5");
    expect(calls[2].url).toBe("http://127.0.0.1:8767/v1/desktop/stock-radar/digest?channels=wecom%2Ctelegram");
    expect(calls.slice(3).map((call) => requestBody(call).action)).toEqual([
      "stock_radar.run_once",
      "stock_radar.push_digest",
      "stock_radar.schedule_update"
    ]);
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
    expect(screen.getByText("只读模式（无控制令牌）")).toBeInTheDocument();
    // Banner copy explains the boundary.
    expect(
      screen.getByText(/所有写操作（创建 \/ 批准 \/ 暂停 \/ 记录结果）/)
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
    // factory_event_list is read through the Agent facade, not the raw manager.
    expect(calls.some((call) => call.url.includes("/v1/tools/agent_factory_event_list"))).toBe(true);

    fireEvent.click(screen.getByRole("tab", { name: "雷达" }));
    expect(screen.getByText("股票雷达观察池")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("证据排序候选")).toBeInTheDocument();
    });
    expect(screen.getByText("企微 / Telegram 载荷预览")).toBeInTheDocument();
    expect(screen.getByText("北方稀土")).toBeInTheDocument();
    expect(screen.getByText(/不含交易指令/)).toBeInTheDocument();

    // Switch to Create tab.
    fireEvent.click(screen.getByRole("tab", { name: "创建" }));
    expect(screen.getByText("所有写操作都通过 ActionIntent")).toBeInTheDocument();
    // Switch to Preview tab — empty until an event is selected.
    fireEvent.click(screen.getByRole("tab", { name: "预览" }));
    expect(screen.getByText("BFS 传播与候选篮子")).toBeInTheDocument();
    // Switch to Lineage tab.
    fireEvent.click(screen.getByRole("tab", { name: "血缘" }));
    expect(screen.getByText("已持久化的事件血缘")).toBeInTheDocument();
    expect(screen.getByText("event_evt_test_001_critical_minerals_abcd1234")).toBeInTheDocument();
    expect(screen.getByText("最近意图派发")).toBeInTheDocument();
  });

  it("applies event filters locally when the facade returns a wider payload", async () => {
    makeFetchMock();
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
    expect(screen.queryByText("AI 芯片新规(test)")).not.toBeInTheDocument();
    expect(screen.getByText("1 个匹配事件")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/^状态$/), { target: { value: "pending_review" } });

    await waitFor(() => {
      expect(screen.getByText("AI 芯片新规(test)")).toBeInTheDocument();
    });
    expect(screen.queryByText("稀土出口管制(test)")).not.toBeInTheDocument();
    expect(screen.getByText("1 个匹配事件")).toBeInTheDocument();
  });

  it("submits create intent payload with source from the form", async () => {
    const { calls } = makeFetchMock();
    render(
      <FactoryEventTriggerPanel
        endpoint="http://127.0.0.1:8767"
        apiToken="api-token"
        controlToken="control-token"
      />
    );

    fireEvent.click(screen.getByRole("tab", { name: "创建" }));
    fireEvent.change(screen.getByLabelText(/事件名称/), { target: { value: "Desktop source event" } });
    fireEvent.change(screen.getByLabelText(/^来源$/), { target: { value: "news_llm" } });
    fireEvent.change(screen.getByLabelText(/Primary themes/i), { target: { value: "ai_compute, chip_domestic" } });
    fireEvent.click(screen.getByRole("button", { name: /仅创建意图/ }));

    await waitFor(() => {
      expect(
        intentRequests(calls).some(
          (call) => requestBody(call).action === "strategy_manager.factory_event_create"
        )
      ).toBe(true);
    });
    const createCall = intentRequests(calls).find(
      (call) => requestBody(call).action === "strategy_manager.factory_event_create"
    );
    expect(createCall).toBeDefined();
    const params = requestBody(createCall!).params as Record<string, unknown>;
    expect(params).toMatchObject({
      event_name: "Desktop source event",
      event_type: "policy_shock",
      source: "news_llm",
      primary_themes: ["ai_compute", "chip_domestic"],
      operator_id: "operator_local"
    });
    expect(params.event_source).toBeUndefined();
  });

  it("Bootstrap maintenance button creates and confirms a bootstrap intent", async () => {
    const { calls } = makeFetchMock();
    render(
      <FactoryEventTriggerPanel
        endpoint="http://127.0.0.1:8767"
        apiToken="api-token"
        controlToken="control-token"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("引导未运行")).toBeInTheDocument();
    });
    const bootstrapButton = screen.getByRole("button", { name: /^初始化引导$/ });
    await waitFor(() => {
      expect(bootstrapButton).toBeEnabled();
    });
    fireEvent.click(bootstrapButton);

    await waitFor(() => {
      expect(
        calls.some((call) => call.url === "http://127.0.0.1:8767/intents/intent_phase5_test/confirm")
      ).toBe(true);
    });
    const bootstrapCall = intentRequests(calls).find(
      (call) => requestBody(call).action === "strategy_manager.factory_event_bootstrap"
    );
    expect(bootstrapCall).toBeDefined();
    expect(requestBody(bootstrapCall!).params).toEqual({ batch_size: 1000, refresh_exposure: true });
    await waitFor(() => {
      expect(screen.getByText("引导已确认")).toBeInTheDocument();
    });
  });

  it("clicks stock radar refresh and confirms all radar ActionIntent buttons", async () => {
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
    fireEvent.click(screen.getByRole("tab", { name: "雷达" }));
    await waitFor(() => {
      expect(screen.getByText(/雷达已加载/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "刷新雷达" }));
    await waitFor(() => {
      expect(calls.filter((call) => call.url.includes("/v1/desktop/stock-radar/status")).length).toBeGreaterThanOrEqual(2);
    });

    const runButton = screen.getByRole("button", { name: "创建雷达运行意图" });
    const pushButton = screen.getByRole("button", { name: "创建推送预览意图" });
    const scheduleButton = screen.getByRole("button", { name: "创建调度意图" });

    fireEvent.click(runButton);
    await waitFor(() => {
      expect(screen.getByText(/股票雷达运行 意图 intent_phase5_test 已确认/)).toBeInTheDocument();
    });
    await waitFor(() => expect(runButton).toBeEnabled());

    fireEvent.click(pushButton);
    await waitFor(() => {
      expect(screen.getByText(/股票雷达推送预览 意图 intent_phase5_test 已确认/)).toBeInTheDocument();
    });
    await waitFor(() => expect(pushButton).toBeEnabled());

    fireEvent.click(scheduleButton);
    await waitFor(() => {
      expect(screen.getByText(/股票雷达调度预览 意图 intent_phase5_test 已确认/)).toBeInTheDocument();
    });

    const radarActions = intentRequests(calls).map((call) => requestBody(call).action);
    expect(radarActions).toEqual(expect.arrayContaining([
      "stock_radar.run_once",
      "stock_radar.push_digest",
      "stock_radar.schedule_update"
    ]));
    const scheduleIntent = intentRequests(calls).find((call) => requestBody(call).action === "stock_radar.schedule_update");
    expect(requestBody(scheduleIntent!).params).toMatchObject({
      interval_seconds: 86400,
      enabled: true,
      allow_network: false,
      allow_llm: false
    });
  });

  it("clears stale stock radar candidates and digest when refresh fails", async () => {
    const { calls } = makeFetchMock({ failRadarCandidatesAfter: 1 });
    render(
      <FactoryEventTriggerPanel
        endpoint="http://127.0.0.1:8767"
        apiToken="api-token"
        controlToken="control-token"
      />
    );

    fireEvent.click(screen.getAllByRole("tab")[0]);
    await waitFor(() => {
      expect(screen.getByText(/600111/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "刷新雷达" }));

    await waitFor(() => {
      expect(calls.filter((call) => call.url.includes("/v1/desktop/stock-radar/candidates")).length).toBeGreaterThanOrEqual(2);
    });
    await waitFor(() => {
      expect(screen.queryByText(/600111/)).not.toBeInTheDocument();
    });
    expect(screen.getByText(/AIASK_HTTP_500/)).toBeInTheDocument();
  });

  it("shows event-list ActionIntent feedback without leaving the events tab", async () => {
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

    fireEvent.click(screen.getByRole("button", { name: /^暂停$/ }));

    await waitFor(() => {
      expect(screen.getByText(/意图 intent_phase5_test 已确认/)).toBeInTheDocument();
    });
    expect(screen.getByText("最近意图派发")).toBeInTheDocument();

    const pauseIntent = intentRequests(calls).find(
      (call) => requestBody(call).action === "strategy_manager.factory_event_update"
    );
    expect(pauseIntent).toBeDefined();
    expect(requestBody(pauseIntent!).params).toEqual({ event_id: "evt_test_001", status: "paused" });
    expect(
      calls.some((call) => call.url === "http://127.0.0.1:8767/intents/intent_phase5_test/confirm")
    ).toBe(true);
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
    // button is "暂停" — and it must be disabled without a control token.
    const pauseButton = screen.getByRole("button", { name: /暂停/ });
    expect(pauseButton).toBeDisabled();
  });
});
