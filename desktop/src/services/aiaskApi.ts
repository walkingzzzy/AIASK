import { mockApiPayloads, mockRunEvents, mockToolResponse } from "../mock/mockData";
import type { ConnectionSettings, RunEvent, UnknownRecord } from "../types";
import { objectData, parseSsePayload, requestJson, requestText } from "./api/core";

export class AiaskApi {
  private settings: ConnectionSettings;

  constructor(settings: ConnectionSettings) {
    this.settings = settings;
  }

  updateSettings(settings: ConnectionSettings) {
    this.settings = settings;
  }

  private async get<T = unknown>(path: string, query?: Record<string, unknown>, control = false): Promise<T> {
    if (this.settings.mode === "mock" && path in mockApiPayloads) {
      return mockApiPayloads[path] as T;
    }
    if (this.settings.mode === "mock") {
      return { object: "mock", data: [], query: query ?? {}, control } as T;
    }
    return requestJson<T>(this.settings, path, { query, control });
  }

  private async post<T = unknown>(path: string, body?: unknown, control = false): Promise<T> {
    if (this.settings.mode === "mock") {
      if (path.startsWith("/v1/tools/")) {
        return mockToolResponse(decodeURIComponent(path.split("/").pop() || ""), body) as T;
      }
      if (path === "/v1/responses") {
        return {
          object: "response",
          id: `resp_${Date.now()}`,
          response: {
            role: "assistant",
            content: "Mock 模式已生成响应。Live 模式会通过 Agent HTTP 调用模型和工具。"
          },
          run: { id: "run_mock_response", status: "completed" },
          session: { id: "sess_research_001" },
          events: mockRunEvents
        } as T;
      }
      if (path.endsWith("/sync-plan")) {
        return {
          object: "aiask.desktop.sync_plan",
          data: {
            dry_run: true,
            commands: ["sync_stock_basic", "sync_daily_kline", "sync_market_temperature_snapshot_cache"],
            side_effect: "requires_intent",
            payload: body
          }
        } as T;
      }
      if (path.includes("/quant/research-runs")) {
        return {
          object: "aiask.quant_research_run",
          data: {
            id: "quant_mock_001",
            status: "completed",
            preset: objectData<UnknownRecord>(body, {}).preset || "momentum_research",
            metrics: { annual_return: 0.18, max_drawdown: -0.07, sharpe: 1.21 }
          }
        } as T;
      }
      if (path.includes("/financial-manager/query")) {
        return {
          object: "aiask.financial_manager.result",
          data: { answer: "查询已在 mock 模式返回，只读结果可用于页面验收。", read_only: true, payload: body }
        } as T;
      }
      if (path.includes("/financial-manager/intent") || path === "/intents") {
        return {
          object: "action_intent",
          success: true,
          data: { id: `intent_${Date.now()}`, status: "pending", side_effect: "approval_required", payload: body }
        } as T;
      }
      return { object: "mock", success: true, data: body ?? {} } as T;
    }
    return requestJson<T>(this.settings, path, { method: "POST", body, control });
  }

  private async patch<T = unknown>(path: string, body?: unknown, control = true): Promise<T> {
    if (this.settings.mode === "mock") {
      return { object: "mock.patch", success: true, data: body ?? {} } as T;
    }
    return requestJson<T>(this.settings, path, { method: "PATCH", body, control });
  }

  private async delete<T = unknown>(path: string, control = true): Promise<T> {
    if (this.settings.mode === "mock") {
      return { object: "mock.delete", success: true, deleted: true } as T;
    }
    return requestJson<T>(this.settings, path, { method: "DELETE", control });
  }

  health = () => this.get("/health");
  healthDetailed = () => this.get("/health/detailed");
  capabilities = () => this.get("/v1/desktop/capabilities");
  parity = () => this.get("/v1/capabilities/parity");
  settingsStatus = () => this.get("/v1/desktop/settings/status");

  aiStatus = () => this.get("/v1/ai/status");
  aiConfig = () => this.get("/v1/ai/config");
  aiConfigSave = (body: unknown) => this.patch("/v1/ai/config", body, true);
  aiModels = () => this.get("/v1/ai/models");
  aiSmoke = (body: unknown) => this.post("/v1/ai/smoke", body);
  response = (body: unknown) => this.post("/v1/responses", body);

  workbenchSummary = () => this.get("/v1/desktop/workbench/summary", { user_id: this.settings.userId, session_limit: 8, run_limit: 8 });
  sessions = () => this.get("/v1/hermes/sessions", { user_id: this.settings.userId, limit: 100 });
  desktopRuns = (query?: Record<string, unknown>) => this.get("/v1/desktop/runs", query);
  sessionMessages = (sessionId: string) => this.get(`/v1/sessions/${encodeURIComponent(sessionId)}/messages`);
  runArtifacts = (runId: string) => this.get(`/v1/runs/${encodeURIComponent(runId)}/artifacts`);
  runSources = (runId: string) => this.get(`/v1/runs/${encodeURIComponent(runId)}/sources`);
  runToolInvocations = (runId: string) => this.get(`/v1/runs/${encodeURIComponent(runId)}/tool-invocations`);
  runCancel = (runId: string) => this.post(`/v1/runs/${encodeURIComponent(runId)}/cancel`, {}, true);
  runStop = (runId: string) => this.post(`/v1/runs/${encodeURIComponent(runId)}/stop`, {}, true);
  runSteer = (runId: string, instruction: string) => this.post(`/v1/runs/${encodeURIComponent(runId)}/steer`, { instruction }, true);
  sessionUndo = (sessionId: string, body: unknown) => this.post(`/v1/sessions/${encodeURIComponent(sessionId)}/undo`, body, true);
  sessionArchive = (sessionId: string, body: unknown) => this.post(`/v1/sessions/${encodeURIComponent(sessionId)}/archive`, body, true);

  async runEvents(runId: string): Promise<RunEvent[]> {
    if (this.settings.mode === "mock") return mockRunEvents;
    const text = await requestText(this.settings, `/v1/runs/${encodeURIComponent(runId)}/events`);
    return parseSsePayload(text) as RunEvent[];
  }

  tools = () => this.get("/v1/tools");
  callTool = (name: string, body: unknown) => this.post(`/v1/tools/${encodeURIComponent(name)}`, body);
  intents = () => this.get("/intents");
  intentGet = (intentId: string) => this.get(`/intents/${encodeURIComponent(intentId)}`);
  createIntent = (body: unknown) => this.post("/intents", body, true);
  intentConfirm = (intentId: string) => this.post(`/intents/${encodeURIComponent(intentId)}/confirm`, {}, true);
  intentDeny = (intentId: string, reason = "denied from desktop V1") => this.post(`/intents/${encodeURIComponent(intentId)}/deny`, { reason }, true);
  approvals = () => this.get("/v1/approvals", undefined, true);
  approvalDecision = (approvalId: string, decision: "approve" | "deny", reason = "desktop V1 decision") =>
    this.post(`/v1/approvals/${encodeURIComponent(approvalId)}/${decision}`, { reason }, true);

  mcpServers = () => this.get("/v1/mcp/servers");
  mcpTools = () => this.get("/v1/mcp/tools", undefined, true);
  mcpResources = () => this.get("/v1/mcp/resources", undefined, true);
  mcpPrompts = () => this.get("/v1/mcp/prompts", undefined, true);
  mcpOauth = () => this.get("/v1/mcp/oauth_status", undefined, true);
  mcpResourceRead = (body: unknown) => this.post("/v1/mcp/resources/read", body, true);
  mcpPromptGet = (body: unknown) => this.post("/v1/mcp/prompts/get", body, true);
  mcpDiscover = (body: unknown) => this.post("/v1/mcp/discover", body, true);
  mcpOauthStart = (body: unknown) => this.post("/v1/mcp/oauth/start", body, true);
  connectors = () => this.get("/v1/connectors", undefined, true);
  connectorsSummary = () => this.get("/v1/connectors/summary", undefined, true);
  connectorTest = (connectorType: string, name: string, body: unknown = {}) =>
    this.post(`/v1/connectors/${encodeURIComponent(connectorType)}/${encodeURIComponent(name)}/test`, body, true);
  skills = () => this.get("/v1/skills", undefined, true);
  skillCreate = (body: unknown) => this.post("/v1/skills", body, true);
  skillUpdate = (name: string, body: unknown) => this.patch(`/v1/skills/${encodeURIComponent(name)}`, body, true);
  skillDelete = (name: string) => this.delete(`/v1/skills/${encodeURIComponent(name)}`, true);
  plugins = () => this.get("/v1/plugins", undefined, true);
  pluginUpsert = (body: unknown) => this.post("/v1/plugins", body, true);
  pluginToggle = (name: string, enabled: boolean) => this.patch(`/v1/plugins/${encodeURIComponent(name)}`, { enabled }, true);
  pluginToolTest = (name: string, tool = "__manifest__", body: unknown = {}) =>
    this.post(`/v1/plugins/${encodeURIComponent(name)}/tools/${encodeURIComponent(tool)}/test`, body, true);
  pluginCommands = (name: string) => this.get(`/v1/plugins/${encodeURIComponent(name)}/commands`, undefined, true);
  pluginCommandTest = (name: string, command: string, body: unknown = {}) =>
    this.post(`/v1/plugins/${encodeURIComponent(name)}/commands/${encodeURIComponent(command)}/test`, body, true);

  gatewayStatus = () => this.get("/v1/gateway/status", undefined, true);
  gatewayDaemon = () => this.get("/v1/gateway/daemon/status", undefined, true);
  gatewayPlatforms = () => this.get("/v1/gateway/platforms", undefined, true);
  gatewayMessages = () => this.get("/v1/gateway/messages", undefined, true);
  gatewayDirectory = () => this.get("/v1/gateway/directory", undefined, true);
  webhooks = () => this.get("/v1/webhooks");
  gatewaySend = (body: unknown) => this.post("/v1/gateway/send", body, true);
  gatewayRetry = (messageId: string) => this.post(`/v1/gateway/messages/${encodeURIComponent(messageId)}/retry`, {}, true);
  gatewayDirectoryRefresh = () => this.post("/v1/gateway/directory/refresh", {}, true);
  gatewayPlatformStart = (platform: string) => this.post(`/v1/gateway/platforms/${encodeURIComponent(platform)}/start`, {}, true);
  gatewayPlatformStop = (platform: string) => this.post(`/v1/gateway/platforms/${encodeURIComponent(platform)}/stop`, {}, true);
  gatewayPlatformHealth = (platform: string) => this.get(`/v1/gateway/platforms/${encodeURIComponent(platform)}/health`, undefined, true);
  webhookCreate = (body: unknown) => this.post("/v1/webhooks", body, true);
  webhookDelete = (webhookId: string) => this.delete(`/v1/webhooks/${encodeURIComponent(webhookId)}`, true);
  webhookTrigger = (webhookId: string, body: unknown) => this.post(`/v1/webhooks/${encodeURIComponent(webhookId)}/trigger`, body, true);

  dataStatus = () => this.get("/v1/desktop/data/status");
  dataSyncPlan = (body: unknown) => this.post("/v1/desktop/data/sync-plan", body);
  stockDataSources = () => this.get("/v1/desktop/stock-data-sources");
  stockDataSourceSave = (body: unknown) => this.post("/v1/desktop/stock-data-sources", body, true);
  stockDataSourceTest = (body: unknown) => this.post("/v1/desktop/stock-data-sources/test", body, true);

  stockRadarStatus = () => this.get("/v1/desktop/stock-radar/status");
  stockRadarCandidates = () => this.get("/v1/desktop/stock-radar/candidates");
  stockRadarDigest = () => this.get("/v1/desktop/stock-radar/digest");
  marketTemperatureSnapshot = () => this.callTool("agent_market_temperature_snapshot", { top_n: 8 });
  marketTemperatureReadiness = () => this.callTool("agent_market_temperature_cache_readiness", {});
  quantPresets = () => this.get("/v1/desktop/quant/presets");
  quantRun = (body: unknown) => this.post("/v1/desktop/quant/research-runs", body);
  quantRunGet = (researchId: string) => this.get(`/v1/desktop/quant/research-runs/${encodeURIComponent(researchId)}`);
  quantReport = (researchId: string) => this.get(`/v1/desktop/quant/research-runs/${encodeURIComponent(researchId)}/report`);
  financialManagerCatalog = () => this.get("/v1/desktop/financial-manager/catalog");
  financialManagerStatus = () => this.get("/v1/desktop/financial-manager/status");
  financialManagerQuery = (body: unknown) => this.post("/v1/desktop/financial-manager/query", body);
  financialManagerIntent = (body: unknown) => this.post("/v1/desktop/financial-manager/intent", body, true);
  brokerReadiness = () => this.get("/v1/desktop/broker-readiness");
  brokerAccounts = () => this.get("/v1/desktop/broker/accounts");
  brokerPositions = () => this.get("/v1/desktop/broker/positions");
  brokerOrders = () => this.get("/v1/desktop/broker/orders");
  brokerSync = (body: unknown) => this.post("/v1/desktop/broker/sync", body, true);
  brokerAnalyticsRun = (body: unknown) => this.post("/v1/desktop/broker/analytics/run", body, true);
  brokerAnalyticsLatest = () => this.get("/v1/desktop/broker/analytics/latest", undefined, true);

  jobs = () => this.get("/v1/jobs");
  createJob = (body: unknown) => this.post("/v1/jobs", body, true);
  updateJob = (jobId: string, body: unknown) => this.patch(`/v1/jobs/${encodeURIComponent(jobId)}`, body, true);
  deleteJob = (jobId: string) => this.delete(`/v1/jobs/${encodeURIComponent(jobId)}`, true);
  runJob = (jobId: string) => this.post(`/v1/jobs/${encodeURIComponent(jobId)}/run`, {}, true);
  jobRuns = (jobId: string) => this.get(`/v1/jobs/${encodeURIComponent(jobId)}/runs`, undefined, true);
  localProfile = () => this.get("/v1/desktop/users/local-profile");
  saveLocalProfile = (body: unknown) => this.patch("/v1/desktop/users/local-profile", body, false);
  userActivity = (userId: string) => this.get(`/v1/desktop/users/${encodeURIComponent(userId)}/activity`);
  userDataPolicy = (userId: string) => this.get(`/v1/desktop/users/${encodeURIComponent(userId)}/data-policy`);
  userDataPolicySave = (userId: string, body: unknown) => this.patch(`/v1/desktop/users/${encodeURIComponent(userId)}/data-policy`, body, true);
  userExport = (userId: string) => this.get(`/v1/desktop/users/${encodeURIComponent(userId)}/export`, undefined, true);
  userDelete = (userId: string, body: unknown) => this.post(`/v1/desktop/users/${encodeURIComponent(userId)}/delete`, body, true);
  learningStatus = () => this.get("/v1/learning/status", undefined, true);
  learningReview = () => this.get("/v1/learning/review", undefined, true);
  learningApply = (body: unknown) => this.post("/v1/learning/apply", body, true);
  rlEnvironments = () => this.get("/v1/rl/environments", undefined, true);
  rlConfig = () => this.get("/v1/rl/config", undefined, true);
  rlConfigSave = (body: unknown) => this.patch("/v1/rl/config", body, true);
  rlRuns = () => this.get("/v1/rl/runs", undefined, true);
  rlRunCreate = (body: unknown) => this.post("/v1/rl/runs", body, true);
  rlRunGet = (runId: string) => this.get(`/v1/rl/runs/${encodeURIComponent(runId)}`, undefined, true);
  rlRunStop = (runId: string) => this.post(`/v1/rl/runs/${encodeURIComponent(runId)}/stop`, {}, true);
  rlRunResults = (runId: string) => this.get(`/v1/rl/runs/${encodeURIComponent(runId)}/results`, undefined, true);
  rlRunLogs = (runId: string) => this.get(`/v1/rl/runs/${encodeURIComponent(runId)}/logs`, undefined, true);
  processes = () => this.get("/v1/processes", undefined, true);
  terminalBackends = () => this.get("/v1/terminal/backends", undefined, true);
  terminalSessions = () => this.get("/v1/terminal/sessions", undefined, true);
  browserSessions = () => this.get("/v1/browser/sessions", undefined, true);
  hermesReadiness = () => this.get("/v1/hermes/readiness");
  financialReadiness = () => this.get("/v1/financial-system/readiness");
}
