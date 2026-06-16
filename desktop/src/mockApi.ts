import type { ApiHeaders } from "./api";
import { mockAiConfig, mockAiModels, mockAiSmoke, mockAiStatus, mockResponseCreate, mockResponseDelete, mockResponseGet, saveMockAiConfig } from "./mock/ai";
import { mockBrokerAnalyticsPayload, mockBrokerReadiness, mockBrokerSnapshotPayload, mockBrokerSync } from "./mock/brokerReadonly";
import { mockFinancialSystemReadiness, mockHermesCapabilities, mockMcpCapabilitySection, mockStaticCapabilitySections } from "./mock/capabilities";
import {
  mockDesktopDataStatus,
  mockDesktopDataSyncPlan,
  mockSaveStockDataSourceData,
  mockStockDataSourcesStatusData,
  mockTestStockDataSourceData
} from "./mock/desktopData";
import { mockFinancialManagerCatalog, mockFinancialManagerIntent, mockFinancialManagerQuery, mockFinancialManagerStatus } from "./mock/financialManager";
import { mockGatewayDaemonStatus, mockGatewayDirectory, mockGatewayDirectoryRefresh, mockGatewayMessages, mockGatewayPlatformAction, mockGatewayPlatforms, mockGatewayRetry, mockGatewayStatus } from "./mock/gateway";
import { incubationFactoryStatusPayload, strategyDomainEventsPayload } from "./mock/incubation";
import { mockConnectorDetail, mockConnectorsList, mockConnectorsSummary, mockMcpDiscover, mockMcpOauthStart, mockMcpOauthStatus, mockMcpPromptGet, mockMcpPrompts, mockMcpRegisterLocal, mockMcpResourceRead, mockMcpResources, mockMcpServers, mockMcpTools, mockPluginCommandTest, mockPluginCommands, mockPluginsList, mockPluginToolTest, mockPluginUpdate, mockPluginUpsert, mockSkillDelete, mockSkillInstall, mockSkillsList, mockSkillUpdate } from "./mock/integrations";
import { mockJobCreate, mockJobDelete, mockJobRun, mockJobRuns, mockJobsData, mockJobsList, mockJobUpdate } from "./mock/jobs";
import { marketTemperatureCacheHistory, marketTemperatureCacheReadiness, marketTemperatureForwardValidation, marketTemperatureIndustryConstituents, marketTemperatureIndustryHistory, marketTemperatureSnapshot } from "./mock/marketTemperature";
import { mockBrowserSessions, mockProcesses, mockTerminalBackendSessions, mockTerminalBackends, mockTerminalSessions } from "./mock/nativeTools";
import { mockLearningApply, mockLearningReview, mockLearningStatus, mockRlConfig, mockRlEnvironments, mockRlRunArtifact, mockRlRunGet, mockRlRunsList, mockRlRunStart, mockWebhookCreate, mockWebhookDelete, mockWebhooksList, mockWebhookTrigger } from "./mock/ops";
import { mockQuantPresets, mockQuantResearchArtifact } from "./mock/quantResearch";
import { mockBodyRecord, normalizeMockMethod, ok, parseMockPath } from "./mock/routing";
import { mockSettingsStatus } from "./mock/settings";
import { stockRadarCandidatesPayload, stockRadarPayload } from "./mock/stockRadar";
import {
  factoryEventLineagePayload,
  factoryEventListPayload,
  factoryEventOutboxStatusPayload,
  factoryEventPreviewTasksPayload,
  factoryThemeExposureStatusPayload,
  mockStrategyFactory,
  strategyFactoryRunsPayload,
  strategyFactoryStatusPayload,
  strategyManagerPayload,
  strategyReviewSnapshotPayload
} from "./mock/strategyFactory";
import { allMockTools, financeTools } from "./mock/toolCatalog";
import { tradePredictionMatrix, tradePredictionOutcomes, tradePredictionStatus } from "./mock/tradePrediction";
import {
  mockActivityEventsData,
  mockCreateActivityEvents,
  mockCreateFeedback,
  mockDeleteUserState,
  mockFeedbackEventsData,
  mockNow,
  mockRecordToolInvocation,
  mockToolInvocationsData,
  mockUpdateUserPolicy,
  mockUserPolicy
} from "./mock/userState";
import {
  currentMockSessionSummaries,
  filterMockArtifacts,
  filterMockSources,
  mockAgentArtifactsData,
  mockAgentSourcesData,
  mockArtifactContent,
  mockArtifactRecord,
  mockHandoffQueue,
  mockRunEventsData,
  mockRunSummariesData,
  mockSessionArchive,
  mockSessionMessagesData,
  mockSessionResumeContext,
  mockSessionUndo,
  mockSourceRecord,
  mockWorkbenchSummary,
  resetMockWorkbenchState,
} from "./mock/workbench";
import type {
  CapabilityWorkbenchPayload,
  RunTraceEvalPayload,
} from "./types";

interface MockOptions {
  method?: string;
  token?: string;
  body?: unknown;
  headers?: ApiHeaders;
}

const CONTROL_TOKEN = "mock-control-token";
let profile = {
  object: "aiask.local_profile",
  user_id: "local",
  profile_name: "Mock 本地操作者",
  storage: "local_json",
  path: "mock://aiask/local-profile.json",
  updated_at: "2026-05-22T09:00:00Z",
  status: "ready",
  secrets_redacted: true
};

const intents = new Map<string, Record<string, unknown>>();
export function resetMockApiState(): void {
  resetMockWorkbenchState(profile.user_id);
}
function mockRunTraceEval(runId: string): RunTraceEvalPayload {
  const runEvents = mockRunEventsData();
  const runSources = filterMockSources({ runId, limit: 100 });
  const runArtifacts = filterMockArtifacts({ runId, limit: 100 });
  const runToolInvocations = mockToolInvocationsData().filter((item) => item.run_id === runId);
  const toolInvocationCount = Math.max(1, runToolInvocations.length);
  return {
    object: "aiask.run_trace_eval",
    implementation: "desktop_mock",
    run_id: runId,
    session_id: runId === "run_mock" ? "sess_mock" : null,
    status: "healthy",
    score: 100,
    checks: [
      {
        id: "model_trace",
        label: "Model call trace",
        status: "pass",
        detail: "model.started=1, model.completed=1",
        evidence: { started: 1, completed: 1 },
      },
      {
        id: "tool_trace",
        label: "Tool invocation trace",
        status: "pass",
        detail: `tool_invocations=${toolInvocationCount}, failed=0`,
        evidence: { invocations: toolInvocationCount, failed: 0 },
      },
      {
        id: "context_snapshot",
        label: "Context snapshot",
        status: "pass",
        detail: "context snapshot present",
        evidence: {
          context_snapshot_id: "ctxsnap_mock_source",
          source_message_count: 2,
          source_count: runSources.length,
          artifact_count: runArtifacts.length,
          risk_flags: [],
        },
      },
      {
        id: "evidence_chain",
        label: "Evidence chain",
        status: "pass",
        detail: `sources=${runSources.length}, artifacts=${runArtifacts.length}`,
        evidence: { sources: runSources.length, artifacts: runArtifacts.length },
      },
      {
        id: "handoff_trace",
        label: "Handoff trace",
        status: "pass",
        detail: "handoff_events=1",
        evidence: { events: ["handoff.policy_applied"] },
      },
      {
        id: "guardrail_trace",
        label: "Guardrail trace",
        status: "pass",
        detail: "guardrail_events=0",
        evidence: { events: [] },
      },
    ],
    summary: {
      event_count: runEvents.filter((item) => item.run_id === runId).length || runEvents.length,
      tool_invocation_count: toolInvocationCount,
      failed_tool_invocation_count: 0,
      context_snapshot_count: 1,
      source_count: runSources.length,
      artifact_count: runArtifacts.length,
      handoff_event_count: 1,
      guardrail_event_count: 0,
      error_event_count: 0,
    },
    latest_context_snapshot: {
      snapshot_id: "ctxsnap_mock_source",
      session_id: "sess_mock",
      run_id: runId,
      trace_id: "trace_mock",
      context_summary_id: "ctxsum_mock",
      compacted: false,
      message_count: 2,
      source_message_ids: ["msg_user", "msg_assistant"],
      source_ids: runSources.map((item) => item.source_id),
      artifact_ids: runArtifacts.map((item) => item.artifact_id),
      risk_flags: [],
      created_at: "2026-05-22T09:00:02Z",
    },
    risk_flags: [],
    secrets_redacted: true,
  };
}

export function isMockEndpoint(endpoint: string): boolean {
  return endpoint.trim().replace(/\/+$/, "") === "mock://aiask";
}

function authorized(options: MockOptions): boolean {
  return Boolean((options.token || "").trim());
}

function envelope(tool: string, data: unknown, success = true) {
  return {
    success,
    data,
    error: success ? null : "mock_error",
    ...(success ? {} : { error_code: "MOCK_ERROR" }),
    meta: {
      trace_id: `mock_trace_${Date.now()}`,
      source_chain: ["desktop.mockApi"],
      side_effect: { level: "read_only", target: tool, confirmation_required: false, idempotent: true }
    }
  };
}

function aiStatus() {
  return mockAiStatus();
}

function aiConfig() {
  return mockAiConfig();
}

function dataStatus() {
  return mockDesktopDataStatus(envelope);
}

function stockDataSourcesStatus() {
  return mockStockDataSourcesStatusData();
}

function saveMockStockDataSource(body: Record<string, unknown>) {
  return mockSaveStockDataSourceData(body);
}

function testMockStockDataSource(body: Record<string, unknown>) {
  return mockTestStockDataSourceData(body);
}

function queryRecord(query?: URLSearchParams): Record<string, unknown> {
  const record: Record<string, unknown> = {};
  query?.forEach((value, key) => {
    record[key] = value;
  });
  return record;
}

function capabilities(): CapabilityWorkbenchPayload {
  const allTools = allMockTools();
  return {
    object: "aiask.desktop_capabilities",
    summary: {
      status: "implemented",
      source: "mock_fixture",
      counts: { implemented: 42, live_unverified: 3, unconfigured: 2, failed: 0 },
      issue_count: 0,
      control: {
        authorized: true,
        full_mode_enabled: true,
        control_token_configured: true,
        control_authorized: true,
        reason: null
      },
      refreshed_at: Date.now() / 1000
    },
    hermes: mockHermesCapabilities(allTools),
    mcp: mockMcpCapabilitySection(),
    strategy_factory: mockStrategyFactory(envelope),
    quant: { data_status: { status: "ready" }, status: "ready" },
    financial_system: mockFinancialSystemReadiness(),
    ...mockStaticCapabilitySections(aiStatus())
  };
}

function settingsStatus() {
  return mockSettingsStatus(aiStatus(), stockDataSourcesStatus(), profile);
}

function createIntent(body: Record<string, unknown>) {
  const id = `intent_mock_${intents.size + 1}`;
  const intent = {
    intent_id: id,
    action: body.action || "mock.action",
    target_tool: "agent_action_intent_create",
    target_action: body.action || "mock.action",
    status: "awaiting_confirmation",
    params: body.params || {},
    created_at: "2026-05-22T09:00:00Z",
    updated_at: "2026-05-22T09:00:00Z"
  };
  intents.set(id, intent);
  return envelope("agent_action_intent_create", { intent });
}

function toolResult(tool: string, body: Record<string, unknown>) {
  if (tool === "agent_tool_catalog") return envelope(tool, { tools: allMockTools() });
  if (tool === "agent_quant_data_gate") return envelope(tool, { status: "passed", codes: body.codes || ["600519"], missing: [], stale: [] });
  if (tool === "agent_market_temperature_snapshot") return envelope(tool, marketTemperatureSnapshot(body));
  if (tool === "agent_market_temperature_cache_readiness") return envelope(tool, marketTemperatureCacheReadiness(body));
  if (tool === "agent_market_temperature_cache_history") return envelope(tool, marketTemperatureCacheHistory(body));
  if (tool === "agent_market_temperature_industry_history") return envelope(tool, marketTemperatureIndustryHistory(body));
  if (tool === "agent_market_temperature_industry_constituents") return envelope(tool, marketTemperatureIndustryConstituents(body));
  if (tool === "agent_market_temperature_forward_validation") return envelope(tool, marketTemperatureForwardValidation(body));
  if (tool === "agent_factor_validation") return envelope(tool, { status: "passed", ic_mean: 0.04, factors: body.factors || ["momentum"] });
  if (tool === "agent_backtest_suite") return envelope(tool, { status: "completed", sharpe: 1.2, max_drawdown: -0.08 });
  if (tool === "agent_portfolio_risk") return envelope(tool, { status: "completed", var_95: -0.021, stress: "passed" });
  if (tool === "agent_analyze_stock") {
    const code = String(body.code || body.stock_code || body.symbol || "600519");
    return envelope(tool, {
      status: "ready",
      code,
      rating: "mock_watch",
      risk: "medium",
      decision: body.include_decision ? "observe_only" : "not_requested",
      summary: { signal: "watch", source: "desktop.mockApi", investment_advice: false }
    });
  }
  if (tool === "agent_stock_live_quote") {
    const code = String(body.code || body.stock_code || body.symbol || body.ticker || "600519");
    return envelope(tool, {
      code,
      price: 123.45,
      change: 1.5,
      change_pct: 1.23,
      volume: 1200000,
      amount: 148140000,
      provider: "sina",
      data_timestamp: "2026-05-22T09:00:00+08:00",
      source_chain: ["desktop.mockApi", "akshare", "sina"],
      fallback_reason: null
    });
  }
  if (tool === "agent_stock_news_digest") {
    const code = String(body.code || body.stock_code || body.symbol || body.ticker || "600519");
    return envelope(tool, {
      code,
      items: [
        {
          title: "Mock 财经新闻",
          url: "https://example.com/aiask/mock-news",
          provider: "eastmoney",
          published_at: "2026-05-22T08:55:00+08:00",
          excerpt: "Mock 新闻来源链接，用于验证 Desktop 证据展示。"
        }
      ],
      source_chain: ["desktop.mockApi", "eastmoney"],
      fetched_at: "2026-05-22T09:00:00Z"
    });
  }
  if (tool === "agent_factory_status") return envelope(tool, strategyFactoryStatusPayload());
  if (tool === "agent_factory_runs") return envelope(tool, strategyFactoryRunsPayload());
  if (tool === "agent_strategy_review_snapshot") return envelope(tool, strategyReviewSnapshotPayload());
  if (tool === "agent_incubation_factory_status") return envelope(tool, incubationFactoryStatusPayload());
  if (tool === "agent_strategy_domain_events") return envelope(tool, strategyDomainEventsPayload(body));
  if (tool === "agent_trade_prediction_status") return envelope(tool, tradePredictionStatus(body));
  if (tool === "agent_trade_prediction_outcomes") return envelope(tool, tradePredictionOutcomes(body));
  if (tool === "agent_trade_prediction_matrix") return envelope(tool, tradePredictionMatrix(body));
  if (tool === "agent_stock_radar_status") return envelope(tool, stockRadarPayload());
  if (tool === "agent_stock_radar_candidates") return envelope(tool, stockRadarCandidatesPayload(body));
  if (tool === "agent_stock_radar_digest") return envelope(tool, stockRadarPayload());
  if (tool === "agent_factory_event_list") return envelope(tool, factoryEventListPayload(body));
  if (tool === "agent_factory_event_preview_tasks") return envelope(tool, factoryEventPreviewTasksPayload(body));
  if (tool === "agent_factory_event_lineage") return envelope(tool, factoryEventLineagePayload(body));
  if (tool === "agent_factory_theme_exposure_status") return envelope(tool, factoryThemeExposureStatusPayload(body));
  if (tool === "agent_factory_event_outbox_status") return envelope(tool, factoryEventOutboxStatusPayload());
  if (tool === "agent_strategy_manager") return envelope(tool, strategyManagerPayload(body));
  if (tool === "agent_memory_search") return envelope(tool, { items: [{ memory_id: "mem_mock", content: "mock memory hit", user_id: body.user_id || "local" }] });
  if (tool === "agent_session_search") return envelope(tool, { items: [{ session_id: "sess_mock", content: "mock session hit", user_id: body.user_id || "local" }] });
  if (tool === "agent_file_list") return envelope(tool, { entries: [{ path: "README.md", type: "file" }, { path: "desktop", type: "directory" }] });
  if (tool === "agent_file_read") return envelope(tool, { path: body.path || "README.md", text: "Mock file content preview." });
  if (tool === "agent_terminal_backends") return envelope(tool, { backends: [{ name: "local-powershell", status: "ready" }] });
  if (tool === "agent_browser_snapshot") return envelope(tool, { title: "AIASK Desktop Mock", url: "mock://browser", nodes: [{ role: "main", name: "Unified console" }] });
  if (tool === "agent_browser_console") return envelope(tool, { messages: [] });
  if (tool === "agent_web_search") return envelope(tool, { results: [{ title: "AIASK mock result", url: "https://example.com/aiask" }] });
  if (tool === "agent_skill_list") return envelope(tool, capabilities().skills);
  if (tool === "agent_plugin_list") return envelope(tool, { plugins: capabilities().plugins });
  if (tool === "agent_mcp_manage") return envelope(tool, { servers: capabilities().mcp.servers, tools: capabilities().mcp.tools });
  if (tool === "agent_model_manage") return envelope(tool, aiStatus());
  if (tool === "agent_memory_manage") return envelope(tool, { status: "ready", provider: "sqlite", user_id: body.user_id || profile.user_id });
  if (tool === "agent_gateway_status") return envelope(tool, { status: "ready", enabled_platforms: ["desktop"] });
  if (tool === "agent_gateway_platforms") return envelope(tool, { platforms: [{ platform: "desktop", status: "ready" }] });
  if (tool === "agent_learning_status") return envelope(tool, { status: "ready", proposal_count: 1 });
  if (tool === "agent_learning_review") return envelope(tool, { proposals: [{ proposal_id: "learn_mock", status: "pending_review" }] });
  if (tool === "agent_rl_list_environments") return envelope(tool, { environments: [{ id: "finance_safe_eval", status: "ready" }] });
  if (tool === "agent_rl_get_config") return envelope(tool, { status: "configured", secrets_redacted: true });
  if (tool === "agent_security_scan") {
    return envelope(tool, {
      status: "completed",
      target: body.text ? "text" : body.path || ".",
      include_env: false,
      findings: [],
      secrets_redacted: true,
      arguments: body
    });
  }
  if (tool === "agent_job_list") return envelope(tool, { jobs: mockJobsData() });
  return envelope(tool, { status: "mock_ok", arguments: body });
}

export async function mockRequestJson<T>(path: string, options: MockOptions = {}): Promise<T> {
  const method = normalizeMockMethod(options.method);
  const body = mockBodyRecord(options.body);
  const { cleanPath, query } = parseMockPath(path);

  if (cleanPath === "/health" || cleanPath === "/health/detailed") {
    return ok({
      status: "ok",
      service: "AIASK Agent Mock",
      runtime: { model: "gpt-5.4", max_iterations: 8 },
      tools: { count: allMockTools().length, names: allMockTools().map((tool) => tool.name), toolset: "general_full" },
      hermes: { mode: "hermes_full", full_mode_enabled: true, full_mode_active: true, parity: capabilities().hermes.parity },
      control: { loopback_only: true, token_configured: true }
    } as T);
  }
  if (cleanPath === "/v1/tools" || cleanPath === "/v1/hermes/tools") return ok({ data: cleanPath.includes("hermes") ? allMockTools() : financeTools } as T);
  if (cleanPath === "/v1/desktop/capabilities") return ok(capabilities() as T);
  if (cleanPath === "/v1/desktop/workbench/summary") return ok({ object: "aiask.desktop.workbench.summary", ...mockWorkbenchSummary() } as T);
  if (cleanPath === "/v1/desktop/runs") return ok({ object: "list", data: mockRunSummariesData() } as T);
  if (cleanPath === "/v1/desktop/settings/status") return ok(settingsStatus() as T);
  if (cleanPath === "/v1/desktop/data/status") return ok(dataStatus() as T);
  if (cleanPath === "/v1/desktop/stock-data-sources" && method === "GET") return ok(stockDataSourcesStatus() as T);
  if (cleanPath === "/v1/desktop/stock-data-sources" && method === "POST") return ok(saveMockStockDataSource(body) as T);
  if (cleanPath === "/v1/desktop/stock-data-sources/test") return ok(testMockStockDataSource(body) as T);
  if (cleanPath === "/v1/desktop/data/sync-plan") {
    return ok(mockDesktopDataSyncPlan(body, dataStatus()) as T);
  }
  if (cleanPath === "/v1/desktop/users/local-profile" && method === "GET") return ok(profile as T);
  if (cleanPath === "/v1/desktop/users/local-profile" && ["POST", "PATCH"].includes(method)) {
    profile = { ...profile, user_id: String(body.user_id || profile.user_id), profile_name: String(body.profile_name || profile.profile_name), updated_at: "2026-05-22T09:05:00Z" };
    return ok(profile as T);
  }
  if (cleanPath === "/v1/desktop/events" && method === "POST") {
    return ok(mockCreateActivityEvents(body, String(profile.user_id || "local")) as T);
  }
  if (cleanPath === "/v1/desktop/feedback" && method === "POST") {
    return ok(mockCreateFeedback(body, String(profile.user_id || "local")) as T);
  }
  const userActivityMatch = cleanPath.match(/^\/v1\/desktop\/users\/([^/]+)\/activity$/);
  if (userActivityMatch) {
    const userId = decodeURIComponent(userActivityMatch[1]);
    const limit = Number(query.get("limit") || 20);
    return ok({
      object: "aiask.user_activity",
      user_id: userId,
      sessions: currentMockSessionSummaries().filter((session) => !session.user_id || session.user_id === userId).slice(0, limit),
      runs: mockRunSummariesData().slice(0, limit),
      events: mockActivityEventsData().filter((event) => !event.user_id || event.user_id === userId).slice(0, limit),
      tool_invocations: mockToolInvocationsData().filter((item) => !item.user_id || item.user_id === userId).slice(0, limit),
      feedback: mockFeedbackEventsData().filter((item) => !item.user_id || item.user_id === userId).slice(0, limit),
      policy: mockUserPolicy(userId),
      secrets_redacted: true
    } as T);
  }
  if (cleanPath === "/v1/desktop/analytics/summary") {
    const userId = query.get("user_id") || undefined;
    const events = mockActivityEventsData().filter((event) => !userId || event.user_id === userId);
    const tools = mockToolInvocationsData().filter((item) => !userId || item.user_id === userId);
    const feedback = mockFeedbackEventsData().filter((item) => !userId || item.user_id === userId);
    const toolNames = Array.from(new Set(tools.map((item) => String(item.tool_name || "tool"))));
    return ok({
      object: "aiask.analytics_summary",
      scope: userId ? "user" : "aggregate",
      user_id: userId || null,
      totals: { events: events.length, tool_invocations: tools.length, feedback: feedback.length },
      events_by_type: Array.from(new Set(events.map((event) => event.event_type))).map((event_type) => ({
        event_type,
        count: events.filter((event) => event.event_type === event_type).length
      })),
      pages: Array.from(new Set(events.map((event) => event.page_key || event.route || "unknown"))).map((page_key) => ({
        page_key,
        count: events.filter((event) => (event.page_key || event.route || "unknown") === page_key).length
      })),
      tools: toolNames.map((tool_name) => {
        const rows = tools.filter((item) => item.tool_name === tool_name);
        const failed = rows.filter((item) => item.status !== "succeeded").length;
        return { tool_name, count: rows.length, succeeded: rows.length - failed, failed, failure_rate: rows.length ? failed / rows.length : 0, avg_duration_ms: 5 };
      }),
      feedback: Array.from(new Set(feedback.map((item) => `${item.target_type}:${item.feedback_type}`))).map((key) => {
        const [target_type, feedback_type] = key.split(":");
        return { target_type, feedback_type, count: feedback.filter((item) => `${item.target_type}:${item.feedback_type}` === key).length, avg_rating: null };
      }),
      secrets_redacted: true
    } as T);
  }
  const userExportMatch = cleanPath.match(/^\/v1\/desktop\/users\/([^/]+)\/export$/);
  if (userExportMatch) {
    const userId = decodeURIComponent(userExportMatch[1]);
    return ok({
      object: "aiask.user_data_export",
      user_id: userId,
      exported_at: mockNow(),
      profile_policy: mockUserPolicy(userId),
      sessions: currentMockSessionSummaries().filter((session) => !session.user_id || session.user_id === userId),
      messages: mockSessionMessagesData(),
      runs: mockRunSummariesData(),
      run_events: mockRunEventsData(),
      activity_events: mockActivityEventsData().filter((event) => !event.user_id || event.user_id === userId),
      tool_invocations: mockToolInvocationsData().filter((item) => !item.user_id || item.user_id === userId),
      feedback: mockFeedbackEventsData().filter((item) => !item.user_id || item.user_id === userId),
      sources: mockAgentSourcesData().filter((item) => !item.user_id || item.user_id === userId),
      artifacts: mockAgentArtifactsData().filter((item) => !item.user_id || item.user_id === userId),
      analytics: {
        object: "aiask.analytics_summary",
        scope: "user",
        user_id: userId,
        totals: { events: mockActivityEventsData().length, tool_invocations: mockToolInvocationsData().length, feedback: mockFeedbackEventsData().length },
        events_by_type: [],
        pages: [],
        tools: [],
        feedback: [],
        secrets_redacted: true
      },
      secrets_redacted: true
    } as T);
  }
  const userDeleteMatch = cleanPath.match(/^\/v1\/desktop\/users\/([^/]+)\/delete$/);
  if (userDeleteMatch && method === "POST") {
    const userId = decodeURIComponent(userDeleteMatch[1]);
    const dryRun = body.dry_run !== false;
    const counts = {
      sessions: currentMockSessionSummaries().filter((session) => !session.user_id || session.user_id === userId).length,
      messages: mockSessionMessagesData().length,
      responses: 0,
      runs: mockRunSummariesData().length,
      run_events: mockRunEventsData().length,
      activity_events: mockActivityEventsData().filter((event) => !event.user_id || event.user_id === userId).length,
      tool_invocations: mockToolInvocationsData().filter((item) => !item.user_id || item.user_id === userId).length,
      feedback: mockFeedbackEventsData().filter((item) => !item.user_id || item.user_id === userId).length,
      sources: mockAgentSourcesData().filter((item) => !item.user_id || item.user_id === userId).length,
      artifacts: mockAgentArtifactsData().filter((item) => !item.user_id || item.user_id === userId).length,
      search_rows: 0
    };
    if (!dryRun) {
      mockDeleteUserState(userId);
    }
    return ok({
      object: "aiask.user_data_delete",
      user_id: userId,
      dry_run: dryRun,
      hard_delete: Boolean(body.hard_delete),
      anonymized_user_id: body.hard_delete ? null : `deleted:${userId}`,
      counts,
      deleted_at: dryRun ? undefined : mockNow(),
      external_side_effects: "not_rolled_back",
      secrets_redacted: true
    } as T);
  }
  if (cleanPath === "/v1/desktop/retention/sweep" && method === "POST") {
    return ok({
      object: "aiask.retention_sweep",
      dry_run: body.dry_run !== false,
      user_id: body.user_id || null,
      counts: { user_activity_events: 0, tool_invocations_payloads: 0, run_events: 0, feedback_events: 0, messages: 0 },
      tables: ["user_activity_events", "tool_invocations_payloads", "run_events", "feedback_events", "messages"],
      market_data_affected: false,
      secrets_redacted: true
    } as T);
  }
  const learningMatch = cleanPath.match(/^\/v1\/desktop\/users\/([^/]+)\/learning-dataset$/);
  if (learningMatch) {
    const userId = decodeURIComponent(learningMatch[1]);
    const policy = mockUserPolicy(userId);
    const items = policy.allow_learning ? mockFeedbackEventsData().filter((item) => item.user_id === userId && item.allow_learning) : [];
    return ok({
      object: "aiask.learning_dataset",
      user_id: userId,
      allowed: Boolean(policy.allow_learning),
      items,
      count: items.length,
      reason: policy.allow_learning ? undefined : "learning_not_allowed",
      secrets_redacted: true
    } as T);
  }
  const recommendationMatch = cleanPath.match(/^\/v1\/desktop\/users\/([^/]+)\/recommendations$/);
  if (recommendationMatch) {
    const userId = decodeURIComponent(recommendationMatch[1]);
    return ok({
      object: "aiask.workflow_recommendations",
      user_id: userId,
      data_source: "local_user_activity",
      data: [
        { id: "feedback:collect", kind: "feedback_collection", priority: "medium", title: "Collect explicit feedback", reason: "Mock recommendation." }
      ],
      count: 1,
      secrets_redacted: true
    } as T);
  }
  const userPolicyMatch = cleanPath.match(/^\/v1\/desktop\/users\/([^/]+)\/data-policy$/);
  if (userPolicyMatch) {
    const userId = decodeURIComponent(userPolicyMatch[1]);
    if (method === "PATCH") {
      mockUpdateUserPolicy(userId, body);
    }
    return ok({ object: "aiask.user_data_policy", data: mockUserPolicy(userId) } as T);
  }
  if (cleanPath === "/v1/desktop/factor-factory/status") {
    return ok({
      object: "aiask.factor_factory_status",
      status: "ready",
      configured: true,
      factory: { initialized: true, pool_loaded_from_db: true, pool_size: 2, run_count: 4 },
      active_factors: [{ factor_id: "factor_momentum", name: "momentum_20d", family: "momentum", quality_score: 0.74 }],
      engine_health: { llm_primary: "ready", gp_classic: "ready", rule_seed: "ready" },
      pool_health: { active_promoted_count: 1, quarantine_count: 0 },
      secrets_redacted: true
    } as T);
  }
  if (cleanPath === "/v1/desktop/trade-predictions/status") {
    return ok(envelope("agent_trade_prediction_status", tradePredictionStatus(queryRecord(query))) as T);
  }
  if (cleanPath === "/v1/desktop/trade-predictions/outcomes") {
    return ok(envelope("agent_trade_prediction_outcomes", tradePredictionOutcomes(queryRecord(query))) as T);
  }
  if (cleanPath === "/v1/desktop/trade-predictions/matrix") {
    return ok(envelope("agent_trade_prediction_matrix", tradePredictionMatrix(queryRecord(query))) as T);
  }
  if (cleanPath === "/v1/ai/status") return ok(aiStatus() as T);
  if (cleanPath === "/v1/ai/config" && method === "GET") return ok(aiConfig() as T);
  if (cleanPath === "/v1/ai/config" && method === "PATCH") return ok(saveMockAiConfig(body) as T);
  if (cleanPath === "/v1/ai/smoke") return ok(mockAiSmoke(body) as T);
  if (cleanPath === "/v1/ai/models") return ok(mockAiModels() as T);
  if (cleanPath === "/v1/responses") return ok(mockResponseCreate(body) as T);
  const responseMatch = cleanPath.match(/^\/v1\/responses\/([^/]+)$/);
  if (responseMatch) {
    const responseId = decodeURIComponent(responseMatch[1]);
    if (method === "DELETE") return ok(mockResponseDelete(responseId) as T);
    return ok(mockResponseGet(responseId) as T);
  }
  const runActionMatch = cleanPath.match(/^\/v1\/runs\/([^/]+)(?:\/(cancel|stop|steer))?$/);
  if (runActionMatch && !cleanPath.endsWith("/events")) {
    const runId = decodeURIComponent(runActionMatch[1]);
    const action = runActionMatch[2];
    if (!action) return ok({ object: "run", run_id: runId, status: "completed", payload: { mock: true } } as T);
    return ok({ object: action === "steer" ? "run.steer" : "run", run_id: runId, status: action === "steer" ? "running" : "cancelled", event: { event: `run.${action}`, data: body } } as T);
  }
  if (cleanPath === "/v1/runs/run_mock/events" || cleanPath === "/v1/runs/run_mock/events/stream") {
    return ok({ object: "list", data: mockRunEventsData() } as T);
  }
  const runTraceEvalMatch = cleanPath.match(/^\/v1\/runs\/([^/]+)\/trace-eval$/);
  if (runTraceEvalMatch) {
    return ok(mockRunTraceEval(decodeURIComponent(runTraceEvalMatch[1])) as T);
  }
  const runArtifactsMatch = cleanPath.match(/^\/v1\/runs\/([^/]+)\/artifacts$/);
  if (runArtifactsMatch) {
    const runId = decodeURIComponent(runArtifactsMatch[1]);
    return ok({
      object: "list",
      run_id: runId,
      data: filterMockArtifacts({
        runId,
        kind: query.get("kind"),
        limit: Number(query.get("limit") || 100)
      })
    } as T);
  }
  const runSourcesMatch = cleanPath.match(/^\/v1\/runs\/([^/]+)\/sources$/);
  if (runSourcesMatch) {
    const runId = decodeURIComponent(runSourcesMatch[1]);
    return ok({
      object: "list",
      run_id: runId,
      data: filterMockSources({
        runId,
        sourceType: query.get("source_type"),
        limit: Number(query.get("limit") || 100)
      })
    } as T);
  }
  const runToolInvocationsMatch = cleanPath.match(/^\/v1\/runs\/([^/]+)\/tool-invocations$/);
  if (runToolInvocationsMatch) {
    const runId = decodeURIComponent(runToolInvocationsMatch[1]);
    const limit = Number(query.get("limit") || 100);
    return ok({
      object: "list",
      run_id: runId,
      data: mockToolInvocationsData().filter((item) => item.run_id === runId).slice(0, Math.max(1, Math.min(limit || 100, 1000)))
    } as T);
  }
  const sessionArtifactsMatch = cleanPath.match(/^\/v1\/sessions\/([^/]+)\/artifacts$/);
  if (sessionArtifactsMatch) {
    const sessionId = decodeURIComponent(sessionArtifactsMatch[1]);
    return ok({
      object: "list",
      session_id: sessionId,
      data: filterMockArtifacts({
        sessionId,
        kind: query.get("kind"),
        limit: Number(query.get("limit") || 100)
      })
    } as T);
  }
  const sessionSourcesMatch = cleanPath.match(/^\/v1\/sessions\/([^/]+)\/sources$/);
  if (sessionSourcesMatch) {
    const sessionId = decodeURIComponent(sessionSourcesMatch[1]);
    return ok({
      object: "list",
      session_id: sessionId,
      data: filterMockSources({
        sessionId,
        sourceType: query.get("source_type"),
        limit: Number(query.get("limit") || 100)
      })
    } as T);
  }
  const artifactContentMatch = cleanPath.match(/^\/v1\/artifacts\/([^/]+)\/content$/);
  if (artifactContentMatch) {
    const artifactId = decodeURIComponent(artifactContentMatch[1]);
    const content = mockArtifactContent(artifactId);
    return ok((content || { object: "error", error: "artifact not found", artifact_id: artifactId }) as T);
  }
  const artifactMatch = cleanPath.match(/^\/v1\/artifacts\/([^/]+)$/);
  if (artifactMatch) {
    const artifactId = decodeURIComponent(artifactMatch[1]);
    return ok(({ object: "artifact", ...mockArtifactRecord(artifactId) }) as T);
  }
  const sourceMatch = cleanPath.match(/^\/v1\/sources\/([^/]+)$/);
  if (sourceMatch) {
    const sourceId = decodeURIComponent(sourceMatch[1]);
    return ok(({ object: "source", ...mockSourceRecord(sourceId) }) as T);
  }
  if (cleanPath === "/v1/search") {
    const includeArchived = query.get("include_archived") === "true";
    const activeSessions = currentMockSessionSummaries().filter((session) => includeArchived || !session.archived);
    return ok({
      object: "list",
      include_archived: includeArchived,
      data: activeSessions.map((session) => ({
        kind: "response",
        object_id: "resp_mock",
        session_id: session.session_id,
        user_id: session.user_id || profile.user_id,
        content: "Mock 回复命中",
      })),
    } as T);
  }
  if (cleanPath === "/v1/hermes/sessions") {
    const includeArchived = query.get("include_archived") === "true";
    return ok({
      object: "list",
      include_archived: includeArchived,
      data: currentMockSessionSummaries().filter((session) => includeArchived || !session.archived),
    } as T);
  }
  if (cleanPath === "/v1/hermes/handoffs") {
    return ok(mockHandoffQueue({
      userId: query.get("user_id"),
      sessionId: query.get("session_id"),
      status: query.get("status"),
      includeCompleted: query.get("include_completed") === "true",
      limit: Number(query.get("limit") || 100),
    }, profile.user_id) as T);
  }
  const sessionResumeContextMatch = cleanPath.match(/^\/v1\/hermes\/sessions\/([^/]+)\/resume-context$/);
  if (sessionResumeContextMatch) {
    return ok(mockSessionResumeContext(decodeURIComponent(sessionResumeContextMatch[1]), profile.user_id) as T);
  }
  const sessionUndoMatch = cleanPath.match(/^\/v1\/sessions\/([^/]+)\/undo$/);
  if (sessionUndoMatch && method === "POST") {
    const sessionId = decodeURIComponent(sessionUndoMatch[1]);
    return ok(mockSessionUndo(sessionId, body) as T);
  }
  const sessionArchiveMatch = cleanPath.match(/^\/v1\/sessions\/([^/]+)\/archive$/);
  if (sessionArchiveMatch && method === "POST") {
    const sessionId = decodeURIComponent(sessionArchiveMatch[1]);
    return ok(mockSessionArchive(sessionId, body) as T);
  }
  if (cleanPath.startsWith("/v1/sessions/") && cleanPath.endsWith("/messages")) {
    return ok({ object: "list", data: mockSessionMessagesData() } as T);
  }
  if (cleanPath === "/v1/hermes/status" || cleanPath === "/v1/capabilities/parity" || cleanPath === "/v1/hermes/readiness") {
    const payload = cleanPath.includes("parity") ? capabilities().hermes.parity : cleanPath.includes("readiness") ? capabilities().hermes.readiness : capabilities().hermes.status;
    return ok(payload as T);
  }
  if (cleanPath === "/v1/hermes/toolsets") {
    return ok({
      object: "list",
      data: [
        { name: "finance_safe", default: false, enabled: true },
        { name: "general_full", default: true, enabled: true }
      ]
    } as T);
  }
  if (cleanPath === "/v1/hermes/config") {
    return ok({
      object: "aiask.hermes_config",
      toolset: "general_full",
      general_tools_enabled: true,
      control_token_configured: true,
      secrets_redacted: true
    } as T);
  }
  if (cleanPath === "/v1/financial-system/readiness") return ok(capabilities().financial_system as T);

  if (cleanPath === "/v1/processes") {
    return ok(mockProcesses() as T);
  }
  if (cleanPath === "/v1/browser/sessions") {
    return ok(mockBrowserSessions() as T);
  }
  if (cleanPath === "/v1/terminal/backends") {
    return ok(mockTerminalBackends() as T);
  }
  const terminalBackendSessionsMatch = cleanPath.match(/^\/v1\/terminal\/backends\/([^/]+)\/sessions$/);
  if (terminalBackendSessionsMatch) {
    const backend = decodeURIComponent(terminalBackendSessionsMatch[1]);
    const limit = Number(query.get("limit") || 200);
    return ok(mockTerminalBackendSessions(backend, profile.user_id, limit) as T);
  }
  if (cleanPath === "/v1/terminal/sessions") {
    return ok(mockTerminalSessions(profile.user_id) as T);
  }
  if (cleanPath === "/v1/gateway/status") {
    return ok(mockGatewayStatus() as T);
  }
  if (cleanPath === "/v1/gateway/daemon/status") {
    return ok(mockGatewayDaemonStatus() as T);
  }
  if (cleanPath === "/v1/gateway/platforms") {
    return ok(mockGatewayPlatforms() as T);
  }
  const gatewayPlatformMatch = cleanPath.match(/^\/v1\/gateway\/platforms\/([^/]+)\/(start|stop|health)$/);
  if (gatewayPlatformMatch) {
    return ok(mockGatewayPlatformAction(decodeURIComponent(gatewayPlatformMatch[1]), gatewayPlatformMatch[2]) as T);
  }
  if (cleanPath === "/v1/gateway/messages") {
    return ok(mockGatewayMessages(profile.user_id) as T);
  }
  const gatewayRetryMatch = cleanPath.match(/^\/v1\/gateway\/messages\/([^/]+)\/retry$/);
  if (gatewayRetryMatch) {
    return ok(mockGatewayRetry(decodeURIComponent(gatewayRetryMatch[1])) as T);
  }
  if (cleanPath === "/v1/gateway/directory") {
    return ok(mockGatewayDirectory(profile.user_id, profile.profile_name) as T);
  }
  if (cleanPath === "/v1/gateway/directory/refresh") {
    return ok(mockGatewayDirectoryRefresh(profile.user_id) as T);
  }
  if (cleanPath === "/v1/learning/status") {
    return ok(mockLearningStatus() as T);
  }
  if (cleanPath === "/v1/learning/review") {
    return ok(mockLearningReview() as T);
  }
  if (cleanPath === "/v1/learning/apply") {
    return ok(mockLearningApply(body) as T);
  }
  if (cleanPath === "/v1/rl/environments") {
    return ok(mockRlEnvironments() as T);
  }
  if (cleanPath === "/v1/rl/config") {
    return ok(mockRlConfig() as T);
  }
  if (cleanPath === "/v1/rl/runs") {
    if (method === "POST") return ok(mockRlRunStart(body) as T);
    return ok(mockRlRunsList() as T);
  }
  const rlRunDetailMatch = cleanPath.match(/^\/v1\/rl\/runs\/([^/]+)$/);
  if (rlRunDetailMatch) {
    return ok(mockRlRunGet(decodeURIComponent(rlRunDetailMatch[1])) as T);
  }
  const rlRunMatch = cleanPath.match(/^\/v1\/rl\/runs\/([^/]+)\/(stop|results|logs)$/);
  if (rlRunMatch) {
    return ok(mockRlRunArtifact(decodeURIComponent(rlRunMatch[1]), rlRunMatch[2]) as T);
  }
  if (cleanPath === "/v1/webhooks") {
    if (method === "POST") return ok(mockWebhookCreate(body) as T);
    return ok(mockWebhooksList() as T);
  }
  const webhookMatch = cleanPath.match(/^\/v1\/webhooks\/([^/]+)(?:\/trigger)?$/);
  if (webhookMatch) {
    const webhookId = decodeURIComponent(webhookMatch[1]);
    if (method === "DELETE") return ok(mockWebhookDelete(webhookId) as T);
    if (cleanPath.endsWith("/trigger")) return ok(envelope("agent_webhook", mockWebhookTrigger(webhookId)) as T);
  }
  if (cleanPath === "/v1/approvals") {
    return ok({ object: "list", data: Array.from(intents.values()) } as T);
  }
  const approvalMatch = cleanPath.match(/^\/v1\/approvals\/([^/]+)\/(approve|deny)$/);
  if (approvalMatch) {
    return ok({ object: "approval", approval_id: decodeURIComponent(approvalMatch[1]), status: approvalMatch[2] === "approve" ? "approved" : "denied" } as T);
  }

  if (cleanPath === "/v1/jobs" && method === "GET") return ok(mockJobsList() as T);
  if (cleanPath === "/v1/jobs" && method === "POST") return ok(mockJobCreate(body, profile.user_id) as T);
  const jobRunsMatch = cleanPath.match(/^\/v1\/jobs\/([^/]+)\/runs$/);
  if (jobRunsMatch) {
    const jobId = decodeURIComponent(jobRunsMatch[1]);
    return ok(mockJobRuns(jobId) as T);
  }
  const jobMatch = cleanPath.match(/^\/v1\/jobs\/([^/]+)(?:\/run)?$/);
  if (jobMatch) {
    const jobId = decodeURIComponent(jobMatch[1]);
    if (cleanPath.endsWith("/run")) return ok(envelope("agent_job_run", mockJobRun(jobId)) as T);
    if (method === "PATCH") return ok(mockJobUpdate(jobId, body) as T);
    if (method === "DELETE") return ok(mockJobDelete(jobId) as T);
  }

  if (cleanPath === "/intents" && method === "GET") {
    return ok({ object: "list", data: Array.from(intents.values()) } as T);
  }
  if (cleanPath === "/intents" && method === "POST") {
    if (!authorized(options)) throw new Error("AIASK_UNAUTHORIZED");
    return ok(createIntent(body) as T);
  }
  const intentMatch = cleanPath.match(/^\/intents\/([^/]+)(?:\/(confirm|deny))?$/);
  if (intentMatch) {
    const id = decodeURIComponent(intentMatch[1]);
    const action = intentMatch[2];
    const intent = intents.get(id) || { intent_id: id, action: "mock.action", target_tool: "agent_action_intent_create", target_action: "mock.action", status: "awaiting_confirmation", params: {} };
    if (action) intent.status = action === "confirm" ? "confirmed" : "denied";
    intents.set(id, intent);
    return ok(envelope("agent_action_intent_get", { intent }) as T);
  }

  const toolMatch = cleanPath.match(/^\/v1\/tools\/([^/]+)$/);
  if (toolMatch) {
    const toolName = decodeURIComponent(toolMatch[1]);
    mockRecordToolInvocation(toolName, body, String(profile.user_id || "local"));
    return ok(toolResult(toolName, body) as T);
  }
  const hermesToolMatch = cleanPath.match(/^\/v1\/hermes\/admin\/tools\/([^/]+)$/);
  if (hermesToolMatch) {
    const toolName = decodeURIComponent(hermesToolMatch[1]);
    mockRecordToolInvocation(toolName, body, String(profile.user_id || "local"));
    return ok(toolResult(toolName, body) as T);
  }

  if (cleanPath === "/v1/skills" && method === "GET") return ok(mockSkillsList(capabilities().skills) as T);
  if (cleanPath === "/v1/skills" && method === "POST") return ok(mockSkillInstall(body) as T);
  if (cleanPath.startsWith("/v1/skills/") && method === "PATCH") return ok(mockSkillUpdate() as T);
  if (cleanPath.startsWith("/v1/skills/") && method === "DELETE") return ok(mockSkillDelete() as T);
  if (cleanPath === "/v1/plugins" && method === "GET") return ok(mockPluginsList(capabilities().plugins) as T);
  if (cleanPath === "/v1/plugins" && method === "POST") return ok(mockPluginUpsert(body) as T);
  if (cleanPath.startsWith("/v1/plugins/") && method === "PATCH") return ok(mockPluginUpdate(body) as T);
  const pluginCommandsMatch = cleanPath.match(/^\/v1\/plugins\/([^/]+)\/commands$/);
  if (pluginCommandsMatch) return ok(mockPluginCommands() as T);
  const pluginCommandTestMatch = cleanPath.match(/^\/v1\/plugins\/([^/]+)\/commands\/([^/]+)\/test$/);
  if (pluginCommandTestMatch) {
    return ok(mockPluginCommandTest(decodeURIComponent(pluginCommandTestMatch[1]), decodeURIComponent(pluginCommandTestMatch[2])) as T);
  }
  if (cleanPath.includes("/tools/") && cleanPath.endsWith("/test")) return ok(mockPluginToolTest() as T);

  if (cleanPath === "/v1/mcp/servers") return ok(mockMcpServers(capabilities().mcp) as T);
  if (cleanPath === "/v1/mcp/tools") return ok(mockMcpTools(capabilities().mcp) as T);
  if (cleanPath === "/v1/mcp/resources") return ok(mockMcpResources(capabilities().mcp) as T);
  if (cleanPath === "/v1/mcp/prompts") return ok(mockMcpPrompts(capabilities().mcp) as T);
  if (cleanPath === "/v1/mcp/oauth_status") return ok(mockMcpOauthStatus(capabilities().mcp) as T);
  if (cleanPath === "/v1/mcp/register-local") return ok(mockMcpRegisterLocal(body) as T);
  if (cleanPath === "/v1/mcp/discover") return ok(mockMcpDiscover(body, capabilities().mcp.tools) as T);
  if (cleanPath === "/v1/mcp/resources/read") return ok(mockMcpResourceRead(body) as T);
  if (cleanPath === "/v1/mcp/prompts/get") return ok(mockMcpPromptGet(body) as T);
  if (cleanPath === "/v1/mcp/oauth/start") return ok(mockMcpOauthStart(body) as T);

  if (cleanPath === "/v1/connectors/summary") return ok(mockConnectorsSummary() as T);
  if (cleanPath === "/v1/connectors") {
    return ok(mockConnectorsList() as T);
  }
  const connectorMatch = cleanPath.match(/^\/v1\/connectors\/([^/]+)\/([^/]+)(?:\/test)?$/);
  if (connectorMatch) {
    return ok(mockConnectorDetail(decodeURIComponent(connectorMatch[1]), decodeURIComponent(connectorMatch[2]), cleanPath.endsWith("/test") ? "connector.test" : "connector.detail") as T);
  }
  if (cleanPath === "/v1/desktop/financial-manager/catalog") return ok(mockFinancialManagerCatalog() as T);
  if (cleanPath === "/v1/desktop/financial-manager/status") {
    return ok(mockFinancialManagerStatus(capabilities(), Array.from(intents.values()).slice(-5)) as T);
  }
  if (cleanPath === "/v1/desktop/broker-readiness") {
    return ok(mockBrokerReadiness() as T);
  }
  if (cleanPath === "/v1/desktop/broker/sync") {
    return ok(mockBrokerSync(body) as T);
  }
  if (cleanPath === "/v1/desktop/broker/accounts" || cleanPath === "/v1/desktop/broker/positions" || cleanPath === "/v1/desktop/broker/orders") {
    return ok(mockBrokerSnapshotPayload(String(query.get("provider") || "qmt")) as T);
  }
  if (cleanPath === "/v1/desktop/broker/analytics/latest" || cleanPath === "/v1/desktop/broker/analytics/run") {
    const provider = cleanPath.endsWith("/run") ? String(body.provider || "qmt") : String(query.get("provider") || "qmt");
    return ok(mockBrokerAnalyticsPayload(provider) as T);
  }
  if (cleanPath === "/v1/desktop/financial-manager/query") {
    return ok(mockFinancialManagerQuery(body) as T);
  }
  if (cleanPath === "/v1/desktop/financial-manager/intent") {
    return ok(mockFinancialManagerIntent(body, (id, intent) => intents.set(id, intent)) as T);
  }
  if (cleanPath === "/v1/desktop/quant/presets") {
    return ok(mockQuantPresets(dataStatus().database) as T);
  }
  if (cleanPath === "/v1/desktop/quant/research-runs") {
    return ok(envelope("agent_quant_research_run", { research: mockQuantResearchArtifact() }) as T);
  }
  const quantReportMatch = cleanPath.match(/^\/v1\/desktop\/quant\/research-runs\/([^/]+)\/report$/);
  if (quantReportMatch) return ok(mockQuantResearchArtifact(decodeURIComponent(quantReportMatch[1])).report as T);
  if (cleanPath === "/v1/desktop/stock-radar/status") return ok(envelope("agent_stock_radar_status", stockRadarPayload()) as T);
  if (cleanPath === "/v1/desktop/stock-radar/candidates") {
    const filters = queryRecord(query);
    return ok(envelope("agent_stock_radar_candidates", stockRadarCandidatesPayload(filters)) as T);
  }
  if (cleanPath === "/v1/desktop/stock-radar/digest") return ok(envelope("agent_stock_radar_digest", stockRadarPayload()) as T);

  return ok({ object: "mock.unhandled", path: cleanPath, method, data: {}, status: "ready" } as T);
}

export { CONTROL_TOKEN as MOCK_CONTROL_TOKEN };
