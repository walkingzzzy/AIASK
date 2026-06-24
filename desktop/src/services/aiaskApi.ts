import {
  mockApiPayloads,
  mockRunArtifactsPayload,
  mockRunEvents,
  mockRunSourcesPayload,
  mockRunToolInvocationsPayload,
  mockSessionMessagesPayload,
  mockToolResponse
} from "../mock/mockData";
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

  private mockSessionId(body?: unknown) {
    const payload = objectData<UnknownRecord>(body, {});
    return String(payload.session_id || payload.sessionId || "sess_research_001");
  }

  private mockRunId(sessionId: string) {
    return sessionId === "sess_ops_001" ? "run_20260621_002" : "run_20260621_001";
  }

  private async get<T = unknown>(path: string, query?: Record<string, unknown>, control = false): Promise<T> {
    if (this.settings.mode === "mock") {
      const sessionMatch = path.match(/^\/v1\/sessions\/([^/]+)\/messages$/);
      if (sessionMatch) {
        return mockSessionMessagesPayload(decodeURIComponent(sessionMatch[1])) as T;
      }

      const runArtifactsMatch = path.match(/^\/v1\/runs\/([^/]+)\/artifacts$/);
      if (runArtifactsMatch) {
        return mockRunArtifactsPayload(decodeURIComponent(runArtifactsMatch[1])) as T;
      }

      const runSourcesMatch = path.match(/^\/v1\/runs\/([^/]+)\/sources$/);
      if (runSourcesMatch) {
        return mockRunSourcesPayload(decodeURIComponent(runSourcesMatch[1])) as T;
      }

      const runToolsMatch = path.match(/^\/v1\/runs\/([^/]+)\/tool-invocations$/);
      if (runToolsMatch) {
        return mockRunToolInvocationsPayload(decodeURIComponent(runToolsMatch[1])) as T;
      }

      const quantRunMatch = path.match(/^\/v1\/desktop\/quant\/research-runs\/([^/]+)$/);
      if (quantRunMatch) {
        return {
          object: "aiask.quant_research_run",
          data: {
            id: decodeURIComponent(quantRunMatch[1]),
            status: "completed",
            preset: "momentum_research",
            metrics: { annual_return: 0.18, max_drawdown: -0.07, sharpe: 1.21 }
          }
        } as T;
      }

      const quantReportMatch = path.match(/^\/v1\/desktop\/quant\/research-runs\/([^/]+)\/report$/);
      if (quantReportMatch) {
        return {
          object: "aiask.quant_research_report",
          data: {
            id: `report_${decodeURIComponent(quantReportMatch[1])}`,
            summary: "Mock 量化报告已生成，可用于页面验收。",
            metrics: { annual_return: 0.18, max_drawdown: -0.07, sharpe: 1.21 },
            read_only: true
          }
        } as T;
      }

      const gatewayHealthMatch = path.match(/^\/v1\/gateway\/platforms\/([^/]+)\/health$/);
      if (gatewayHealthMatch) {
        return {
          object: "gateway.platform.health",
          data: {
            platform: decodeURIComponent(gatewayHealthMatch[1]),
            status: "ready",
            checked_at: new Date().toISOString(),
            mock: true
          }
        } as T;
      }

      const userActivityMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/activity$/);
      if (userActivityMatch) {
        return {
          object: "list",
          data: [
            {
              id: "activity_001",
              user_id: decodeURIComponent(userActivityMatch[1]),
              type: "workbench.response",
              title: "Workbench 响应验收",
              created_at: new Date().toISOString()
            }
          ]
        } as T;
      }

      const userPolicyMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/data-policy$/);
      if (userPolicyMatch) {
        return {
          object: "aiask.user_data_policy",
          data: {
            user_id: decodeURIComponent(userPolicyMatch[1]),
            retention_days: 90,
            allow_learning: false,
            updated_from: "mock"
          }
        } as T;
      }

      const userExportMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/export$/);
      if (userExportMatch) {
        return {
          object: "aiask.user_export",
          data: {
            user_id: decodeURIComponent(userExportMatch[1]),
            export_ready: true,
            format: "json",
            generated_at: new Date().toISOString()
          }
        } as T;
      }

      const jobRunsMatch = path.match(/^\/v1\/jobs\/([^/]+)\/runs$/);
      if (jobRunsMatch) {
        return {
          object: "list",
          data: [
            {
              id: `job_run_${decodeURIComponent(jobRunsMatch[1])}_001`,
              job_id: decodeURIComponent(jobRunsMatch[1]),
              status: "completed",
              started_at: new Date().toISOString()
            }
          ]
        } as T;
      }

      const rlRunMatch = path.match(/^\/v1\/rl\/runs\/([^/]+)$/);
      if (rlRunMatch) {
        return {
          object: "aiask.rl.run",
          data: {
            id: decodeURIComponent(rlRunMatch[1]),
            status: "completed",
            score: 0.72,
            environment: "market_research_mock"
          }
        } as T;
      }

      const rlResultsMatch = path.match(/^\/v1\/rl\/runs\/([^/]+)\/results$/);
      if (rlResultsMatch) {
        return {
          object: "aiask.rl.results",
          data: {
            run_id: decodeURIComponent(rlResultsMatch[1]),
            reward: 0.72,
            summary: "Mock RL 结果已生成。"
          }
        } as T;
      }

      const rlLogsMatch = path.match(/^\/v1\/rl\/runs\/([^/]+)\/logs$/);
      if (rlLogsMatch) {
        return {
          object: "aiask.rl.logs",
          data: {
            run_id: decodeURIComponent(rlLogsMatch[1]),
            entries: ["environment initialized", "dry-run episode completed"],
            summary: "Mock RL 日志可用于页面验收。"
          }
        } as T;
      }
    }

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
      if (path === "/v1/ai/smoke") {
        const payload = objectData<UnknownRecord>(body, {});
        return {
          object: "aiask.ai_smoke",
          success: true,
          data: {
            provider: payload.provider || "openai-compatible",
            model: payload.model || "gpt-4.1-compatible",
            status: "passed",
            message: "Mock smoke 测试通过。"
          }
        } as T;
      }
      if (path.startsWith("/v1/tools/")) {
        return mockToolResponse(decodeURIComponent(path.split("/").pop() || ""), body) as T;
      }
      if (path === "/v1/responses") {
        const payload = objectData<UnknownRecord>(body, {});
        const sessionId = this.mockSessionId(body);
        const runId = this.mockRunId(sessionId);
        const prompt = String(payload.prompt || payload.input || "");
        return {
          object: "response",
          id: `resp_${Date.now()}`,
          response: {
            role: "assistant",
            content: prompt
              ? `Mock 模式已收到任务“${prompt}”，并按当前线程上下文生成验收用响应。`
              : "Mock 模式已生成响应。Live 模式会通过 Agent HTTP 调用模型和工具。"
          },
          run: { id: runId, status: "completed" },
          session: { id: sessionId },
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
        const payload = objectData<UnknownRecord>(body, {});
        return {
          object: "action_intent",
          success: true,
          data: {
            id: `intent_${Date.now()}`,
            action: String(payload.action || payload.title || "mock.intent"),
            status: "pending",
            side_effect: "approval_required",
            risk_level: "medium",
            payload: body,
            created_at: new Date().toISOString()
          }
        } as T;
      }
      if (path === "/v1/gateway/send") {
        return {
          object: "gateway.intent_preview",
          success: true,
          data: {
            id: `gateway_msg_${Date.now()}`,
            status: "pending",
            delivery_mode: "intent_preview",
            payload: body
          }
        } as T;
      }
      if (path === "/v1/desktop/broker/analytics/run") {
        return {
          object: "aiask.broker.analytics",
          success: true,
          data: {
            report_id: `broker_report_${Date.now()}`,
            status: "completed",
            read_only: true,
            payload: body
          }
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
  aiSmoke = (body: unknown) =>
    this.settings.mode === "mock"
      ? this.post("/v1/ai/smoke", body)
      : requestJson(this.settings, "/v1/ai/smoke", { method: "POST", body, timeoutMs: 120_000 });
  response = (body: unknown) => this.post("/v1/responses", body);

  workbenchSummary = () => this.get("/v1/desktop/workbench/summary", { user_id: this.settings.userId, session_limit: 8, run_limit: 8 });
  sessions = () => this.get("/v1/hermes/sessions", { user_id: this.settings.userId, limit: 100 });
  desktopRuns = (query?: Record<string, unknown>) => this.get("/v1/desktop/runs", { user_id: this.settings.userId, ...query });
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
  approvals = () => this.get("/v1/approvals");
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
  webhooks = () => this.get("/v1/webhooks", undefined, true);
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
