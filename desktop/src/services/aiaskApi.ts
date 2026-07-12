import {
  mockApiPayloads,
  mockMessages,
  mockRunArtifactsPayload,
  mockRunEvents,
  mockRunSourcesPayload,
  mockRunToolInvocationsPayload,
  mockRuns,
  mockSessionMessagesPayload,
  mockSessions,
  mockToolResponse
} from "../mock/mockData";
import type { ConnectionSettings, RunEvent, UnknownRecord, WorkbenchMessage } from "../types";
import { ApiError, objectData, parseSsePayload, redactSecrets, requestJson, requestText, toList } from "./api/core";

type MockStore = {
  sessions: UnknownRecord[];
  runs: UnknownRecord[];
  messagesBySession: Record<string, WorkbenchMessage[]>;
  strategies: UnknownRecord[];
  stockPools: UnknownRecord[];
  files: UnknownRecord[];
  mcpServers: UnknownRecord[];
  skills: UnknownRecord[];
  plugins: UnknownRecord[];
  jobs: UnknownRecord[];
  intents: UnknownRecord[];
  approvals: UnknownRecord[];
  aiConfig: UnknownRecord;
  localProfile: UnknownRecord;
  userPolicies: Record<string, UnknownRecord>;
  pairings: Record<string, UnknownRecord>;
  gatewayMessages: UnknownRecord[];
  webhooks: UnknownRecord[];
  rlRuns: UnknownRecord[];
};

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function nowIso() {
  return new Date().toISOString();
}

function findId(item: UnknownRecord, fallback: string) {
  return String(item.id || item.session_id || item.run_id || item.name || fallback);
}

function authHeaders(settings: ConnectionSettings, needsControl: boolean): HeadersInit {
  const headers: Record<string, string> = { Accept: "application/json" };
  const apiToken = settings.apiToken.trim();
  const controlToken = settings.controlToken.trim();
  const userId = settings.userId.trim();
  if (apiToken) {
    headers.Authorization = `Bearer ${apiToken}`;
    headers["X-AIASK-Agent-Token"] = apiToken;
  }
  if (needsControl && controlToken) {
    headers["X-AIASK-Agent-Control-Token"] = controlToken;
    headers["X-AIASK-Local-Control-Token"] = controlToken;
  }
  if (userId) {
    headers["X-AIASK-User-Id"] = userId;
  }
  return headers;
}

async function parseMultipartError(response: Response) {
  let raw: unknown;
  try {
    raw = await response.json();
  } catch {
    raw = await response.text().catch(() => undefined);
  }
  const record = raw && typeof raw === "object" ? (raw as UnknownRecord) : {};
  throw new ApiError({
    status: response.status,
    title: String(record.title || response.statusText || "Request failed"),
    detail: String(record.detail || record.error || raw || ""),
    code: typeof record.error_code === "string" ? record.error_code : typeof record.code === "string" ? record.code : undefined,
    raw: redactSecrets(raw)
  });
}

function stockRows() {
  return [
    { code: "600519", name: "贵州茅台", tags: ["核心", "白酒"], note: "高确定性龙头", added_at: nowIso() },
    { code: "300750", name: "宁德时代", tags: ["成长", "新能源"], note: "波动较高", added_at: nowIso() },
    { code: "000858", name: "五粮液", tags: ["消费"], note: "估值修复观察", added_at: nowIso() }
  ];
}

function createInitialMockStore(settings: ConnectionSettings): MockStore {
  const userId = settings.userId || "local-user";
  const sessions = clone(mockSessions).map((item, index) => ({
    ...item,
    id: String(item.id || item.session_id || `sess_${index + 1}`),
    session_id: String(item.id || item.session_id || `sess_${index + 1}`),
    archived: Boolean(item.archived) || String(item.status || "").toLowerCase() === "archived"
  }));
  const runs = clone(mockRuns).map((item, index) => ({
    ...item,
    id: String(item.id || item.run_id || `run_${index + 1}`),
    run_id: String(item.id || item.run_id || `run_${index + 1}`)
  }));
  const messagesBySession: Record<string, WorkbenchMessage[]> = {};
  for (const session of sessions) {
    const sessionId = String(session.id || "");
    messagesBySession[sessionId] = clone(toList<WorkbenchMessage>(mockSessionMessagesPayload(sessionId)));
  }
  const mcpServers = clone(toList<UnknownRecord>(mockApiPayloads["/v1/mcp/servers"])).map((item) => ({
    ...item,
    id: String(item.id || item.name || ""),
    enabled: item.enabled ?? true
  }));
  const installedSkills = objectData<UnknownRecord>(mockApiPayloads["/v1/skills"], {}).data;
  const skillNames = Array.isArray((installedSkills as UnknownRecord)?.skills)
    ? ((installedSkills as UnknownRecord).skills as UnknownRecord[]).map((item) => String(item.name || item.id || ""))
    : Array.isArray((installedSkills as UnknownRecord)?.installed)
      ? ((installedSkills as UnknownRecord).installed as unknown[]).map((item) => String(item))
      : ["aiask-repo-orientation", "aiask-desktop-workbench"];
  const skills = skillNames.map((name) => ({
    id: name,
    name,
    type: "local",
    path: `C:/skills/${name}/SKILL.md`,
    status: "enabled",
    enabled: true
  }));
  const plugins = clone(toList<UnknownRecord>(mockApiPayloads["/v1/plugins"])).map((item) => ({
    ...item,
    id: String(item.id || item.name || ""),
    enabled: item.enabled ?? true
  }));
  const jobs = clone(toList<UnknownRecord>(mockApiPayloads["/v1/jobs"])).map((item) => ({
    ...item,
    id: String(item.id || item.job_id || ""),
    enabled: item.enabled ?? false
  }));
  const aiConfig = clone(objectData<UnknownRecord>(mockApiPayloads["/v1/ai/config"], {}));
  const localProfile = clone(objectData<UnknownRecord>(mockApiPayloads["/v1/desktop/users/local-profile"], {}));
  return {
    sessions,
    runs,
    messagesBySession,
    strategies: [
      {
        id: "strategy_value_core",
        user_id: userId,
        name: "核心价值组合",
        type: "value",
        description: "以消费龙头和高现金流公司为主。",
        stocks: ["600519", "000858"],
        config: {},
        status: "active",
        performance: { return: 0.126, sharpe: 1.08 },
        created_at: nowIso(),
        updated_at: nowIso(),
        sort_order: 0
      },
      {
        id: "strategy_growth_watch",
        user_id: userId,
        name: "成长观察组合",
        type: "growth",
        description: "跟踪新能源与高端制造主线。",
        stocks: ["300750"],
        config: {},
        status: "active",
        performance: { return: 0.082, sharpe: 0.94 },
        created_at: nowIso(),
        updated_at: nowIso(),
        sort_order: 1
      }
    ],
    stockPools: [
      {
        id: "pool_core",
        user_id: userId,
        name: "核心持仓",
        description: "中长期跟踪池",
        stocks: stockRows().slice(0, 2),
        created_at: nowIso(),
        updated_at: nowIso(),
        sort_order: 0
      },
      {
        id: "pool_watchlist",
        user_id: userId,
        name: "机会观察池",
        description: "题材和轮动观察",
        stocks: stockRows().slice(1),
        created_at: nowIso(),
        updated_at: nowIso(),
        sort_order: 1
      }
    ],
    files: [],
    mcpServers,
    skills,
    plugins,
    jobs,
    intents: clone(toList<UnknownRecord>(mockApiPayloads["/intents"])),
    approvals: clone(toList<UnknownRecord>(mockApiPayloads["/v1/approvals"])),
    aiConfig,
    localProfile,
    userPolicies: {
      [userId]: {
        user_id: userId,
        retention_days: 90,
        allow_learning: false,
        updated_from: "mock"
      }
    },
    pairings: {},
    gatewayMessages: clone(toList<UnknownRecord>(mockApiPayloads["/v1/gateway/messages"])),
    webhooks: clone(toList<UnknownRecord>(mockApiPayloads["/v1/webhooks"])),
    rlRuns: clone(toList<UnknownRecord>(mockApiPayloads["/v1/rl/runs"]))
  };
}

export class AiaskApi {
  private settings: ConnectionSettings;
  private mockStore: MockStore | null;

  constructor(settings: ConnectionSettings) {
    this.settings = settings;
    this.mockStore = settings.mode === "mock" ? createInitialMockStore(settings) : null;
  }

  updateSettings(settings: ConnectionSettings) {
    const modeChanged = settings.mode !== this.settings.mode;
    this.settings = settings;
    if (settings.mode === "mock") {
      if (!this.mockStore || modeChanged) {
        this.mockStore = createInitialMockStore(settings);
      }
    } else {
      this.mockStore = null;
    }
  }

  private userId() {
    return this.settings.userId || "default";
  }

  private ensureMockStore() {
    if (!this.mockStore) {
      this.mockStore = createInitialMockStore(this.settings);
    }
    return this.mockStore;
  }

  private mockPayloadRecord(path: string) {
    const payload = mockApiPayloads[path];
    return payload && typeof payload === "object" ? clone(payload as UnknownRecord) : {};
  }

  private mockSessionId(body?: unknown) {
    const payload = objectData<UnknownRecord>(body, {});
    return String(payload.session_id || payload.sessionId || "sess_research_001");
  }

  private mockRunId(sessionId: string) {
    return sessionId === "sess_ops_001" ? "run_20260621_002" : `run_${Date.now()}`;
  }

  private sortedRows(rows: UnknownRecord[]) {
    return [...rows].sort((a, b) => Number(a.sort_order ?? 0) - Number(b.sort_order ?? 0));
  }

  private nextSortOrder(rows: UnknownRecord[]) {
    return rows.reduce((max, item) => Math.max(max, Number(item.sort_order ?? -1)), -1) + 1;
  }

  private mockWorkbenchSummary() {
    const store = this.ensureMockStore();
    return {
      object: "aiask.desktop.workbench_summary",
      data: {
        sessions: clone(store.sessions),
        runs: clone(store.runs),
        messages: clone(mockMessages),
        stats: {
          active_sessions: store.sessions.filter((item) => !item.archived).length,
          runs_today: store.runs.length,
          pending_approvals: store.approvals.filter((item) => /pending/i.test(String(item.status || ""))).length,
          data_gates: 2
        }
      }
    };
  }

  private mockStockRadarCandidates(query?: Record<string, unknown>) {
    const payload = this.mockPayloadRecord("/v1/desktop/stock-radar/candidates");
    const data = objectData<UnknownRecord>(payload.data, {});
    const rows = Array.isArray(data.candidates) ? ([...data.candidates] as UnknownRecord[]) : [];
    const tier = String(query?.tier || "").trim().toLowerCase();
    const symbol = String(query?.symbol || "").trim().toLowerCase();
    const minScore = Number(query?.min_score);
    const limit = Number(query?.limit ?? rows.length);
    const filtered = rows.filter((item) => {
      const rowTier = String(item.tier || "").trim().toLowerCase();
      const rowSymbol = String(item.symbol || "").trim().toLowerCase();
      const rowName = String(item.name || "").trim().toLowerCase();
      const rowScore = Number(item.score ?? 0);
      if (tier && rowTier !== tier) return false;
      if (symbol && !rowSymbol.includes(symbol) && !rowName.includes(symbol)) return false;
      if (Number.isFinite(minScore) && rowScore < minScore) return false;
      return true;
    });
    return {
      object: payload.object || "tool_result",
      success: true,
      data: {
        ...data,
        candidates: filtered.slice(0, Number.isFinite(limit) && limit > 0 ? limit : filtered.length),
        count: filtered.length,
        query: query ?? {}
      },
      error: null
    };
  }

  private async multipartRequest<T>(path: string, formData: FormData, control = true): Promise<T> {
    const response = await fetch(new URL(path, this.settings.baseUrl.endsWith("/") ? this.settings.baseUrl : `${this.settings.baseUrl}/`).toString(), {
      method: "POST",
      headers: authHeaders(this.settings, control),
      body: formData
    });
    if (!response.ok) {
      await parseMultipartError(response);
    }
    return redactSecrets((await response.json()) as T);
  }

  private async get<T = unknown>(path: string, query?: Record<string, unknown>, control = false): Promise<T> {
    if (this.settings.mode === "mock") {
      const store = this.ensureMockStore();
      const sessionMatch = path.match(/^\/v1\/sessions\/([^/]+)\/messages$/);
      if (sessionMatch) {
        return { object: "list", data: clone(store.messagesBySession[decodeURIComponent(sessionMatch[1])] || []) } as T;
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
            checked_at: nowIso(),
            mock: true
          }
        } as T;
      }

      if (path === "/v1/gateway/pairing") {
        const platform = String(query?.platform || "local");
        const userId = String(query?.user_id || this.userId());
        const sessionId = String(query?.session_id || "sess_ops_001");
        const key = `${platform}:${userId}:${sessionId}`;
        const existing = store.pairings[key];
        return {
          object: "gateway.pairing",
          success: true,
          data: existing
            ? clone(existing)
            : {
                action: "status",
                platform,
                user_id: userId,
                session_id: sessionId,
                configured: true
              },
          error: null,
          secrets_redacted: true
        } as T;
      }

      if (path === "/v1/desktop/workbench/summary") {
        return this.mockWorkbenchSummary() as T;
      }

      if (path === "/v1/hermes/sessions") {
        const includeArchived = Boolean(query?.include_archived);
        const limit = Number(query?.limit ?? 100);
        const rows = store.sessions.filter((item) => includeArchived || !item.archived);
        return { object: "list", data: clone(rows.slice(0, limit)) } as T;
      }

      if (path === "/v1/desktop/runs") {
        const sessionId = String(query?.session_id || "");
        const status = String(query?.status || "").toLowerCase();
        let rows = [...store.runs];
        if (sessionId) rows = rows.filter((item) => String(item.session_id || "") === sessionId);
        if (status) rows = rows.filter((item) => String(item.status || "").toLowerCase() === status);
        return { object: "list", data: clone(rows) } as T;
      }

      if (path === "/v1/desktop/users/local-profile") {
        return { object: "aiask.local_profile", data: clone(store.localProfile) } as T;
      }

      const strategyMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/strategies$/);
      if (strategyMatch) {
        const userId = decodeURIComponent(strategyMatch[1]);
        return { object: "list", data: clone(this.sortedRows(store.strategies.filter((item) => String(item.user_id || "") === userId))) } as T;
      }

      const poolMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/stock-pools$/);
      if (poolMatch) {
        const userId = decodeURIComponent(poolMatch[1]);
        return { object: "list", data: clone(this.sortedRows(store.stockPools.filter((item) => String(item.user_id || "") === userId))) } as T;
      }

      if (path === "/v1/desktop/files") {
        const userId = String(query?.user_id || this.userId());
        return { object: "list", data: clone(store.files.filter((item) => String(item.user_id || userId) === userId)) } as T;
      }

      if (path === "/v1/mcp/servers") {
        return { object: "list", data: clone(store.mcpServers) } as T;
      }

      if (path === "/v1/skills") {
        return { object: "list", data: { skills: clone(store.skills), count: store.skills.length }, meta: { count: store.skills.length } } as T;
      }

      if (path === "/v1/plugins") {
        return { object: "list", data: clone(store.plugins) } as T;
      }

      if (path === "/v1/jobs") {
        return { object: "list", data: clone(store.jobs) } as T;
      }

      if (path === "/v1/rl/runs") {
        return { object: "list", data: clone(store.rlRuns) } as T;
      }

      if (path === "/v1/desktop/stock-radar/status") {
        const payload = this.mockPayloadRecord(path);
        const data = objectData<UnknownRecord>(payload.data, {});
        return {
          ...payload,
          data: {
            ...data,
            latest_run_id: String(query?.run_id || data.latest_run_id || "radar_20260621"),
            limit: Number(query?.limit ?? 20)
          }
        } as T;
      }

      if (path === "/v1/desktop/stock-radar/candidates") {
        return this.mockStockRadarCandidates(query) as T;
      }

      if (path === "/v1/desktop/stock-radar/digest") {
        const payload = this.mockPayloadRecord(path);
        const data = objectData<UnknownRecord>(payload.data, {});
        const channels = String(query?.channels || "local,preview")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
        return {
          ...payload,
          data: {
            ...data,
            run_id: String(query?.run_id || "radar_20260621"),
            channels,
            limit: Number(query?.limit ?? 20)
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
              created_at: nowIso()
            }
          ]
        } as T;
      }

      const userPolicyMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/data-policy$/);
      if (userPolicyMatch) {
        const userId = decodeURIComponent(userPolicyMatch[1]);
        return {
          object: "aiask.user_data_policy",
          data: clone(store.userPolicies[userId] || store.userPolicies[this.userId()])
        } as T;
      }

      const userExportMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/export$/);
      if (userExportMatch) {
        const userId = decodeURIComponent(userExportMatch[1]);
        return {
          object: "aiask.user_export",
          data: {
            user_id: userId,
            export_ready: true,
            format: "json",
            generated_at: nowIso(),
            stats: {
              sessions: store.sessions.length,
              strategies: store.strategies.length,
              stock_pools: store.stockPools.length
            }
          },
          secrets_redacted: true
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
              started_at: nowIso()
            }
          ]
        } as T;
      }

      if (path === "/v1/ai/status") {
        return {
          object: "aiask.ai_status",
          configured: true,
          provider: String(store.aiConfig.provider || "openai-compatible"),
          model: String(store.aiConfig.model || "gpt-4.1-compatible"),
          base_url: String(store.aiConfig.base_url || "mock://openai-compatible"),
          source_mode: "mock",
          mock: true
        } as T;
      }

      if (path === "/v1/ai/config") {
        return {
          ...clone(store.aiConfig),
          object: "aiask.ai_config",
          provider: String(store.aiConfig.provider || "openai-compatible"),
          model: String(store.aiConfig.model || "gpt-4.1-compatible"),
          base_url_configured: true,
          api_key_configured: true,
          secrets_redacted: true
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
          object: "rl.results",
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
          object: "rl.logs",
          data: {
            run_id: decodeURIComponent(rlLogsMatch[1]),
            entries: ["environment initialized", "dry-run episode completed"],
            summary: "Mock RL 日志可用于页面验收。"
          }
        } as T;
      }

      if (path in mockApiPayloads) {
        return clone(mockApiPayloads[path] as T);
      }
      return { object: "mock", data: [], query: query ?? {}, control } as T;
    }

    return requestJson<T>(this.settings, path, { query, control });
  }

  private async post<T = unknown>(path: string, body?: unknown, control = false): Promise<T> {
    if (this.settings.mode === "mock") {
      const store = this.ensureMockStore();
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

      if (path.startsWith("/v1/hermes/admin/tools/")) {
        const toolName = decodeURIComponent(path.split("/").pop() || "");
        if (toolName === "agent_terminal") {
          const payload = objectData<UnknownRecord>(body, {});
          const command = String(payload.command || "pwd");
          return {
            success: true,
            data: {
              process_id: `proc_${Date.now()}`,
              command,
              cwd: String(payload.cwd || "."),
              returncode: 0,
              stdout: `mock terminal executed: ${command}`,
              stderr: "",
              timed_out: false,
              truncated: false,
              backend: String(payload.backend || "local"),
              session_id: String(payload.session_id || ""),
              pty: false
            }
          } as T;
        }
        return { success: true, data: { tool: toolName, payload: body, mock: true } } as T;
      }

      if (path === "/v1/responses") {
        const payload = objectData<UnknownRecord>(body, {});
        const sessionId = this.mockSessionId(body);
        const runId = this.mockRunId(sessionId);
        const prompt = String(payload.prompt || payload.input || "");
        const model = String(payload.model || store.aiConfig.model || "gpt-4.1-compatible");
        const attachments = toList<UnknownRecord>(payload.attachments).map((item) => ({
          id: String(item.id || item.file_id || item.name || ""),
          name: String(item.name || item.filename || item.id || "attachment"),
          mime_type: String(item.mime_type || item.type || "application/octet-stream"),
          size: Number(item.size || 0),
          parse_status: String(item.parse_status || item.status || "uploaded"),
          text_preview: typeof item.text_preview === "string" ? item.text_preview : undefined
        }));
        const attachmentNote = attachments.length
          ? ` Attachments: ${attachments.map((item) => `${item.name}(${item.parse_status})`).join(", ")}.`
          : "";
        const assistantMessage = {
          id: `msg_ai_${Date.now()}`,
          role: "assistant" as const,
          content: prompt ? `Mock response received: ${prompt}.${attachmentNote}` : `Mock response generated.${attachmentNote}`,
          created_at: nowIso(),
          status: "completed"
        };
        store.messagesBySession[sessionId] = [...(store.messagesBySession[sessionId] || []), assistantMessage];
        const run = {
          id: runId,
          run_id: runId,
          session_id: sessionId,
          title: prompt ? `${prompt.slice(0, 20)}...` : "Mock response run",
          status: "completed",
          started_at: nowIso(),
          updated_at: nowIso(),
          toolset: "finance_safe",
          model
        };
        store.runs = [run, ...store.runs.filter((item) => String(item.id || item.run_id || "") !== runId)].slice(0, 30);
        store.sessions = store.sessions.map((item) =>
          String(item.id || "") === sessionId
            ? {
                ...item,
                updated_at: nowIso(),
                message_count: (Number(item.message_count || 0) || 0) + 1
              }
            : item
        );
        return {
          object: "response",
          id: `resp_${Date.now()}`,
          response: { role: "assistant", content: assistantMessage.content },
          output_text: assistantMessage.content,
          run: { id: runId, status: "completed" },
          session: { id: sessionId },
          events: mockRunEvents,
          metadata: {
            model,
            requested_model: payload.model || null,
            attachments,
            attachment_count: attachments.length,
            session_id: sessionId,
            run_id: runId
          }
        } as T;
      }

      if (path === "/v1/hermes/sessions") {
        const payload = objectData<UnknownRecord>(body, {});
        const sessionId = `sess_${Date.now()}`;
        const session = {
          id: sessionId,
          session_id: sessionId,
          title: String(payload.title || "新会话"),
          status: "active",
          archived: false,
          message_count: 0,
          updated_at: nowIso(),
          created_at: nowIso()
        };
        store.sessions = [session, ...store.sessions];
        store.messagesBySession[sessionId] = [];
        if (payload.initial_context) {
          store.messagesBySession[sessionId].push({
            id: `msg_system_${Date.now()}`,
            role: "system",
            content: String(payload.initial_context),
            created_at: nowIso(),
            status: "completed"
          });
        }
        return { object: "aiask.session", success: true, data: clone(session) } as T;
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
          success: true,
          data: {
            id: `quant_mock_${Date.now()}`,
            research: { id: `quant_mock_${Date.now()}`, research_id: `quant_mock_${Date.now()}` },
            status: "completed",
            preset: objectData<UnknownRecord>(body, {}).preset || "momentum_research",
            metrics: { annual_return: 0.18, max_drawdown: -0.07, sharpe: 1.21 }
          }
        } as T;
      }

      if (path.includes("/financial-manager/query")) {
        return {
          object: "aiask.financial_manager.result",
          success: true,
          data: { answer: "查询已在 mock 模式返回，只读结果可用于页面验收。", read_only: true, payload: body }
        } as T;
      }

      if (path.includes("/financial-manager/intent") || path === "/intents") {
        const payload = objectData<UnknownRecord>(body, {});
        const item = {
          id: `intent_${Date.now()}`,
          action: String(payload.action || payload.title || "mock.intent"),
          status: "pending",
          side_effect: "approval_required",
          risk_level: "medium",
          payload: body,
          created_at: nowIso()
        };
        store.intents = [item, ...store.intents];
        return { object: "action_intent", success: true, data: item } as T;
      }

      if (path === "/v1/gateway/send") {
        const payload = objectData<UnknownRecord>(body, {});
        const message = {
          id: `gateway_msg_${Date.now()}`,
          platform: String(payload.platform || "local"),
          target: String(payload.target || ""),
          user_id: String(payload.user_id || this.userId()),
          session_id: String(payload.session_id || ""),
          direction: "outbound",
          status: "pending",
          delivery_mode: "intent_preview",
          message: String(payload.message || ""),
          created_at: nowIso()
        };
        store.gatewayMessages = [message, ...store.gatewayMessages].slice(0, 30);
        return {
          object: "gateway.intent_preview",
          success: true,
          data: {
            id: message.id,
            status: "pending",
            adapter: { ok: true },
            message,
            delivery_mode: "intent_preview",
            payload: body
          }
        } as T;
      }

      if (path === "/v1/gateway/messages") {
        return { object: "list", data: clone(store.gatewayMessages) } as T;
      }

      if (path === "/v1/gateway/pairing") {
        const payload = objectData<UnknownRecord>(body, {});
        const platform = String(payload.platform || "local");
        const userId = String(payload.user_id || this.userId());
        const sessionId = String(payload.session_id || `pair_${Date.now()}`);
        const key = `${platform}:${userId}:${sessionId}`;
        const pairing = {
          action: String(payload.action || "create"),
          platform,
          user_id: userId,
          session_id: sessionId,
          configured: true,
          created_at: nowIso()
        };
        store.pairings[key] = pairing;
        return { object: "gateway.pairing", success: true, data: pairing, error: null, secrets_redacted: true } as T;
      }

      if (path === "/v1/desktop/broker/analytics/run") {
        return {
          object: "aiask.broker.analytics",
          success: true,
          data: {
            report_id: `broker_report_${Date.now()}`,
            status: "completed",
            analytics: {
              total_asset: 268000,
              cash_ratio: 0.22,
              position_count: 3,
              order_count: 1
            },
            read_only: true,
            payload: body
          }
        } as T;
      }

      if (path === "/v1/sessions/batch/archive") {
        const payload = objectData<UnknownRecord>(body, {});
        const sessionIds = Array.isArray(payload.session_ids) ? payload.session_ids.map((item) => String(item)) : [];
        const results = sessionIds.map((sessionId) => {
          const exists = store.sessions.some((item) => String(item.id || "") === sessionId);
          if (!exists) {
            return { session_id: sessionId, success: false, error: "session_not_found", error_code: "SESSION_NOT_FOUND" };
          }
          store.sessions = store.sessions.map((item) =>
            String(item.id || "") === sessionId ? { ...item, archived: true, status: "archived", updated_at: nowIso() } : item
          );
          return { session_id: sessionId, success: true, data: { archived: true } };
        });
        return {
          object: "aiask.session_archive_batch",
          success: true,
          data: {
            results,
            archived_count: results.filter((item) => item.success).length,
            failed_count: results.filter((item) => !item.success).length
          }
        } as T;
      }

      const sessionArchiveMatch = path.match(/^\/v1\/sessions\/([^/]+)\/archive$/);
      if (sessionArchiveMatch) {
        const sessionId = decodeURIComponent(sessionArchiveMatch[1]);
        store.sessions = store.sessions.map((item) =>
          String(item.id || "") === sessionId ? { ...item, archived: true, status: "archived", updated_at: nowIso() } : item
        );
        return { object: "aiask.session_archive", success: true, data: { session_id: sessionId, archived: true } } as T;
      }

      const strategyCreateMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/strategies$/);
      if (strategyCreateMatch) {
        const userId = decodeURIComponent(strategyCreateMatch[1]);
        const payload = objectData<UnknownRecord>(body, {});
        const item = {
          id: `strategy_${Date.now()}`,
          user_id: userId,
          name: String(payload.name || "未命名策略"),
          type: String(payload.type || "custom"),
          description: String(payload.description || ""),
          stocks: Array.isArray(payload.stocks) ? payload.stocks : [],
          config: objectData<UnknownRecord>(payload.config, {}),
          status: String(payload.status || "active"),
          performance: {},
          created_at: nowIso(),
          updated_at: nowIso(),
          sort_order: this.nextSortOrder(store.strategies.filter((item) => String(item.user_id || "") === userId))
        };
        store.strategies.push(item);
        return { object: "strategy", success: true, data: clone(item) } as T;
      }

      const strategyReorderMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/strategies\/reorder$/);
      if (strategyReorderMatch) {
        const userId = decodeURIComponent(strategyReorderMatch[1]);
        const payload = objectData<UnknownRecord>(body, {});
        const orderedIds = Array.isArray(payload.ordered_ids) ? payload.ordered_ids.map((item) => String(item)) : [];
        const current = store.strategies.filter((item) => String(item.user_id || "") === userId).map((item) => String(item.id || ""));
        if (orderedIds.length !== current.length || orderedIds.some((id) => !current.includes(id))) {
          throw new Error("ordered_ids must contain the complete strategy id set");
        }
        store.strategies = store.strategies.map((item) => {
          const index = orderedIds.indexOf(String(item.id || ""));
          return index >= 0 ? { ...item, sort_order: index, updated_at: nowIso() } : item;
        });
        return { object: "strategy.reorder", success: true, data: { ordered_ids: orderedIds } } as T;
      }

      const poolCreateMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/stock-pools$/);
      if (poolCreateMatch) {
        const userId = decodeURIComponent(poolCreateMatch[1]);
        const payload = objectData<UnknownRecord>(body, {});
        const item = {
          id: `pool_${Date.now()}`,
          user_id: userId,
          name: String(payload.name || "未命名股票池"),
          description: String(payload.description || ""),
          stocks: [],
          created_at: nowIso(),
          updated_at: nowIso(),
          sort_order: this.nextSortOrder(store.stockPools.filter((row) => String(row.user_id || "") === userId))
        };
        store.stockPools.push(item);
        return { object: "stock_pool", success: true, data: clone(item) } as T;
      }

      const poolReorderMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/stock-pools\/reorder$/);
      if (poolReorderMatch) {
        const userId = decodeURIComponent(poolReorderMatch[1]);
        const payload = objectData<UnknownRecord>(body, {});
        const orderedIds = Array.isArray(payload.ordered_ids) ? payload.ordered_ids.map((item) => String(item)) : [];
        const current = store.stockPools.filter((item) => String(item.user_id || "") === userId).map((item) => String(item.id || ""));
        if (orderedIds.length !== current.length || orderedIds.some((id) => !current.includes(id))) {
          throw new Error("ordered_ids must contain the complete stock pool id set");
        }
        store.stockPools = store.stockPools.map((item) => {
          const index = orderedIds.indexOf(String(item.id || ""));
          return index >= 0 ? { ...item, sort_order: index, updated_at: nowIso() } : item;
        });
        return { object: "stock_pool.reorder", success: true, data: { ordered_ids: orderedIds } } as T;
      }

      const addStockMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/stock-pools\/([^/]+)\/stocks$/);
      if (addStockMatch) {
        const poolId = decodeURIComponent(addStockMatch[2]);
        const payload = objectData<UnknownRecord>(body, {});
        const newStock = {
          code: String(payload.code || ""),
          name: String(payload.name || payload.code || ""),
          tags: Array.isArray(payload.tags) ? payload.tags : [],
          note: String(payload.note || ""),
          added_at: nowIso()
        };
        store.stockPools = store.stockPools.map((item) =>
          String(item.id || "") === poolId
            ? {
                ...item,
                stocks: [...(Array.isArray(item.stocks) ? item.stocks : []), newStock],
                updated_at: nowIso()
              }
            : item
        );
        return { object: "stock_pool.stock", success: true, data: { status: "added", stock: newStock } } as T;
      }

      const batchRemoveMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/stock-pools\/([^/]+)\/stocks\/batch-remove$/);
      if (batchRemoveMatch) {
        const poolId = decodeURIComponent(batchRemoveMatch[2]);
        const payload = objectData<UnknownRecord>(body, {});
        const codes = Array.isArray(payload.codes) ? payload.codes.map((item) => String(item)) : [];
        const pool = store.stockPools.find((item) => String(item.id || "") === poolId);
        const stocks = Array.isArray(pool?.stocks) ? [...pool.stocks] : [];
        const results = codes.map((code) =>
          stocks.some((item) => String((item as UnknownRecord).code || "") === code)
            ? { code, success: true, removed: true }
            : { code, success: false, removed: false, error: "stock_not_found" }
        );
        const remaining = stocks.filter((item) => !codes.includes(String((item as UnknownRecord).code || "")));
        store.stockPools = store.stockPools.map((item) =>
          String(item.id || "") === poolId ? { ...item, stocks: remaining, updated_at: nowIso() } : item
        );
        return {
          object: "stock_pool.batch_remove",
          success: true,
          data: { pool_id: poolId, results, remaining }
        } as T;
      }

      if (path === "/v1/mcp/servers") {
        const payload = objectData<UnknownRecord>(body, {});
        const item = {
          id: String(payload.name || `mcp_${Date.now()}`),
          name: String(payload.name || `mcp_${Date.now()}`),
          command: String(payload.command || ""),
          args: Array.isArray(payload.args) ? payload.args : [],
          env: objectData<UnknownRecord>(payload.env, {}),
          transport: String(payload.transport || "stdio"),
          status: "configured",
          enabled: true
        };
        store.mcpServers.push(item);
        return { object: "mcp.server", success: true, data: clone(item) } as T;
      }

      if (path === "/v1/skills") {
        const payload = objectData<UnknownRecord>(body, {});
        const name = String(payload.name || `skill_${Date.now()}`);
        const item = {
          id: name,
          name,
          type: String(payload.type || "local"),
          path: String(payload.path || payload.url || `C:/skills/${name}/SKILL.md`),
          status: "enabled",
          enabled: true
        };
        store.skills = [item, ...store.skills.filter((row) => String(row.name || "") !== name)];
        return { object: "skill", success: true, data: clone(item) } as T;
      }

      if (path === "/v1/plugins") {
        return { object: "plugin", success: true, data: clone(body) } as T;
      }

      if (path === "/v1/gateway/directory/refresh") {
        return { object: "gateway.directory.refresh", success: true, data: { refreshed_at: nowIso() } } as T;
      }

      if (/^\/v1\/gateway\/messages\/[^/]+\/retry$/.test(path)) {
        const messageId = decodeURIComponent(path.split("/")[4]);
        store.gatewayMessages = store.gatewayMessages.map((item) =>
          String(item.id || item.message_id || "") === messageId ? { ...item, status: "retry_pending", retried_at: nowIso() } : item
        );
        return { object: "gateway.retry", success: true, data: { retried: true, id: messageId } } as T;
      }

      if (/^\/v1\/gateway\/platforms\/[^/]+\/(start|stop)$/.test(path)) {
        return { object: "gateway.platform", success: true, data: { status: path.endsWith("/start") ? "started" : "stopped" } } as T;
      }

      if (path === "/v1/jobs") {
        const payload = objectData<UnknownRecord>(body, {});
        const item = {
          id: `job_${Date.now()}`,
          name: String(payload.name || "desktop-job"),
          prompt: String(payload.prompt || ""),
          enabled: Boolean(payload.enabled),
          schedule: payload.interval_seconds ? `every ${payload.interval_seconds}s` : String(payload.schedule || "manual"),
          interval_seconds: payload.interval_seconds,
          template: String(payload.template || "generic_prompt"),
          watch: payload.watch,
          dry_run: Boolean(payload.dry_run ?? true),
          source: String(payload.source || "desktop_v1"),
          toolset: "ops_safe",
          created_at: nowIso(),
          updated_at: nowIso()
        };
        store.jobs = [item, ...store.jobs];
        return { object: "job", success: true, data: clone(item) } as T;
      }

      const runJobMatch = path.match(/^\/v1\/jobs\/([^/]+)\/run$/);
      if (runJobMatch) {
        return { object: "job.run", success: true, data: { job_id: decodeURIComponent(runJobMatch[1]), status: "completed" } } as T;
      }

      if (path === "/v1/desktop/files/save") {
        const payload = objectData<UnknownRecord>(body, {});
        const item = {
          id: `saved_${Date.now()}`,
          name: String(payload.filename || "untitled.txt"),
          filename: String(payload.filename || "untitled.txt"),
          size: String(payload.content || "").length,
          path: String(payload.path || "./"),
          user_id: this.userId(),
          saved_at: nowIso(),
          status: "saved"
        };
        store.files = [item, ...store.files];
        return { object: "file", ...item } as T;
      }

      if (path === "/v1/learning/apply") {
        return { object: "learning.apply", success: true, data: { applied: true, payload: body } } as T;
      }

      if (path === "/v1/rl/runs") {
        const payload = objectData<UnknownRecord>(body, {});
        const item = {
          id: `rl_run_${Date.now()}`,
          environment: String(payload.environment || "market_research_mock"),
          status: "running",
          score: 0
        };
        store.rlRuns = [item, ...store.rlRuns];
        return { object: "rl.run", success: true, data: item } as T;
      }

      const userDeleteMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/delete$/);
      if (userDeleteMatch) {
        return {
          object: "aiask.user_delete",
          dry_run: Boolean(objectData<UnknownRecord>(body, {}).dry_run ?? true),
          success: true,
          secrets_redacted: true
        } as T;
      }

      return { object: "mock", success: true, data: body ?? {} } as T;
    }

    return requestJson<T>(this.settings, path, { method: "POST", body, control });
  }

  private async patch<T = unknown>(path: string, body?: unknown, control = true): Promise<T> {
    if (this.settings.mode === "mock") {
      const store = this.ensureMockStore();
      if (path === "/v1/ai/config") {
        const payload = objectData<UnknownRecord>(body, {});
        store.aiConfig = {
          ...store.aiConfig,
          provider: String(payload.provider || store.aiConfig.provider || "openai-compatible"),
          model: String(payload.model || store.aiConfig.model || "gpt-4.1-compatible"),
          base_url: String(payload.base_url || store.aiConfig.base_url || "mock://openai-compatible")
        };
        return {
          object: "aiask.ai_config",
          saved: true,
          provider: String(store.aiConfig.provider || "openai-compatible"),
          model: String(store.aiConfig.model || "gpt-4.1-compatible"),
          base_url_configured: true,
          api_key_configured: true,
          updated_keys: ["AIASK_AGENT_MODEL_PROVIDER", "AIASK_AGENT_MODEL"],
          secrets_redacted: true
        } as T;
      }

      if (path === "/v1/desktop/users/local-profile") {
        const payload = objectData<UnknownRecord>(body, {});
        store.localProfile = {
          ...store.localProfile,
          ...payload,
          preferences: { ...objectData<UnknownRecord>(store.localProfile.preferences, {}), ...objectData<UnknownRecord>(payload.preferences, {}) },
          behavior: { ...objectData<UnknownRecord>(store.localProfile.behavior, {}), ...objectData<UnknownRecord>(payload.behavior, {}) },
          secrets_redacted: true
        };
        return { object: "aiask.local_profile", data: clone(store.localProfile) } as T;
      }

      const strategyUpdateMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/strategies\/([^/]+)$/);
      if (strategyUpdateMatch) {
        const strategyId = decodeURIComponent(strategyUpdateMatch[2]);
        const payload = objectData<UnknownRecord>(body, {});
        store.strategies = store.strategies.map((item) =>
          String(item.id || "") === strategyId ? { ...item, ...payload, updated_at: nowIso() } : item
        );
        return { object: "strategy", success: true, data: clone(store.strategies.find((item) => String(item.id || "") === strategyId) || {}) } as T;
      }

      const poolUpdateMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/stock-pools\/([^/]+)$/);
      if (poolUpdateMatch) {
        const poolId = decodeURIComponent(poolUpdateMatch[2]);
        const payload = objectData<UnknownRecord>(body, {});
        store.stockPools = store.stockPools.map((item) =>
          String(item.id || "") === poolId ? { ...item, ...payload, updated_at: nowIso() } : item
        );
        return { object: "stock_pool", success: true, data: clone(store.stockPools.find((item) => String(item.id || "") === poolId) || {}) } as T;
      }

      const mcpUpdateMatch = path.match(/^\/v1\/mcp\/servers\/([^/]+)$/);
      if (mcpUpdateMatch) {
        const serverId = decodeURIComponent(mcpUpdateMatch[1]);
        const payload = objectData<UnknownRecord>(body, {});
        store.mcpServers = store.mcpServers.map((item) =>
          String(item.id || item.name || "") === serverId ? { ...item, ...payload } : item
        );
        return { object: "mcp.server", success: true, data: clone(store.mcpServers.find((item) => String(item.id || item.name || "") === serverId) || {}) } as T;
      }

      const skillUpdateMatch = path.match(/^\/v1\/skills\/([^/]+)$/);
      if (skillUpdateMatch) {
        const name = decodeURIComponent(skillUpdateMatch[1]);
        const payload = objectData<UnknownRecord>(body, {});
        store.skills = store.skills.map((item) =>
          String(item.name || "") === name
            ? { ...item, ...payload, enabled: Boolean(payload.enabled ?? item.enabled), status: Boolean(payload.enabled ?? item.enabled) ? "enabled" : "disabled" }
            : item
        );
        return { object: "skill", success: true, data: clone(store.skills.find((item) => String(item.name || "") === name) || {}) } as T;
      }

      const pluginUpdateMatch = path.match(/^\/v1\/plugins\/([^/]+)$/);
      if (pluginUpdateMatch) {
        const name = decodeURIComponent(pluginUpdateMatch[1]);
        const payload = objectData<UnknownRecord>(body, {});
        store.plugins = store.plugins.map((item) =>
          String(item.name || item.id || "") === name ? { ...item, ...payload, enabled: Boolean(payload.enabled) } : item
        );
        return { object: "plugin", success: true, data: clone(store.plugins.find((item) => String(item.name || item.id || "") === name) || {}) } as T;
      }

      const jobUpdateMatch = path.match(/^\/v1\/jobs\/([^/]+)$/);
      if (jobUpdateMatch) {
        const jobId = decodeURIComponent(jobUpdateMatch[1]);
        const payload = objectData<UnknownRecord>(body, {});
        store.jobs = store.jobs.map((item) => (String(item.id || "") === jobId ? { ...item, ...payload, updated_at: nowIso() } : item));
        return { object: "job", success: true, data: clone(store.jobs.find((item) => String(item.id || "") === jobId) || {}) } as T;
      }

      const userPolicyMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/data-policy$/);
      if (userPolicyMatch) {
        const userId = decodeURIComponent(userPolicyMatch[1]);
        const payload = objectData<UnknownRecord>(body, {});
        store.userPolicies[userId] = { ...store.userPolicies[userId], ...payload, user_id: userId };
        return { object: "aiask.user_data_policy", data: clone(store.userPolicies[userId]) } as T;
      }

      if (path === "/v1/rl/config") {
        return { object: "rl.config", success: true, data: body ?? {} } as T;
      }

      return { object: "mock.patch", success: true, data: body ?? {} } as T;
    }

    return requestJson<T>(this.settings, path, { method: "PATCH", body, control });
  }

  private async delete<T = unknown>(path: string, control = true): Promise<T> {
    if (this.settings.mode === "mock") {
      const store = this.ensureMockStore();
      const strategyDeleteMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/strategies\/([^/]+)$/);
      if (strategyDeleteMatch) {
        const strategyId = decodeURIComponent(strategyDeleteMatch[2]);
        store.strategies = store.strategies.filter((item) => String(item.id || "") !== strategyId);
        return { object: "strategy", success: true, deleted: true, id: strategyId } as T;
      }

      const poolDeleteMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/stock-pools\/([^/]+)$/);
      if (poolDeleteMatch) {
        const poolId = decodeURIComponent(poolDeleteMatch[2]);
        store.stockPools = store.stockPools.filter((item) => String(item.id || "") !== poolId);
        return { object: "stock_pool", success: true, deleted: true, id: poolId } as T;
      }

      const removeStockMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/stock-pools\/([^/]+)\/stocks\/([^/]+)$/);
      if (removeStockMatch) {
        const poolId = decodeURIComponent(removeStockMatch[2]);
        const stockCode = decodeURIComponent(removeStockMatch[3]);
        store.stockPools = store.stockPools.map((item) =>
          String(item.id || "") === poolId
            ? {
                ...item,
                stocks: (Array.isArray(item.stocks) ? item.stocks : []).filter((stock) => String((stock as UnknownRecord).code || "") !== stockCode),
                updated_at: nowIso()
              }
            : item
        );
        return { object: "stock_pool.stock", success: true, deleted: true, code: stockCode } as T;
      }

      const fileDeleteMatch = path.match(/^\/v1\/desktop\/files\/([^/]+)$/);
      if (fileDeleteMatch) {
        const fileId = decodeURIComponent(fileDeleteMatch[1]);
        store.files = store.files.filter((item) => String(item.id || "") !== fileId);
        return { object: "file", deleted: true, id: fileId } as T;
      }

      const mcpDeleteMatch = path.match(/^\/v1\/mcp\/servers\/([^/]+)$/);
      if (mcpDeleteMatch) {
        const serverId = decodeURIComponent(mcpDeleteMatch[1]);
        store.mcpServers = store.mcpServers.filter((item) => String(item.id || item.name || "") !== serverId);
        return { object: "mcp.server", success: true, data: { id: serverId, deleted: true } } as T;
      }

      const skillDeleteMatch = path.match(/^\/v1\/skills\/([^/]+)$/);
      if (skillDeleteMatch) {
        const name = decodeURIComponent(skillDeleteMatch[1]);
        store.skills = store.skills.filter((item) => String(item.name || "") !== name);
        return { object: "skill", success: true, data: { id: name, deleted: true } } as T;
      }

      const jobDeleteMatch = path.match(/^\/v1\/jobs\/([^/]+)$/);
      if (jobDeleteMatch) {
        const jobId = decodeURIComponent(jobDeleteMatch[1]);
        store.jobs = store.jobs.filter((item) => String(item.id || "") !== jobId);
        return { object: "job.deleted", success: true, deleted: true, id: jobId } as T;
      }

      const webhookDeleteMatch = path.match(/^\/v1\/webhooks\/([^/]+)$/);
      if (webhookDeleteMatch) {
        const webhookId = decodeURIComponent(webhookDeleteMatch[1]);
        store.webhooks = store.webhooks.filter((item) => String(item.id || "") !== webhookId);
        return { object: "webhook", success: true, data: { id: webhookId, deleted: true } } as T;
      }

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

  workbenchSummary = () => this.get("/v1/desktop/workbench/summary", { user_id: this.userId(), session_limit: 8, run_limit: 8 });
  sessions = (query?: { include_archived?: boolean; limit?: number }) =>
    this.get("/v1/hermes/sessions", {
      user_id: this.userId(),
      limit: query?.limit ?? 100,
      include_archived: Boolean(query?.include_archived)
    });
  desktopRuns = (query?: Record<string, unknown>) => this.get("/v1/desktop/runs", { user_id: this.userId(), ...query });
  sessionMessages = (sessionId: string) => this.get(`/v1/sessions/${encodeURIComponent(sessionId)}/messages`);
  runArtifacts = (runId: string) => this.get(`/v1/runs/${encodeURIComponent(runId)}/artifacts`);
  runSources = (runId: string) => this.get(`/v1/runs/${encodeURIComponent(runId)}/sources`);
  runToolInvocations = (runId: string) => this.get(`/v1/runs/${encodeURIComponent(runId)}/tool-invocations`);
  runCancel = (runId: string) => this.post(`/v1/runs/${encodeURIComponent(runId)}/cancel`, {}, true);
  runStop = (runId: string) => this.post(`/v1/runs/${encodeURIComponent(runId)}/stop`, {}, true);
  runSteer = (runId: string, instruction: string) => this.post(`/v1/runs/${encodeURIComponent(runId)}/steer`, { instruction }, true);
  sessionUndo = (sessionId: string, body: unknown) => this.post(`/v1/sessions/${encodeURIComponent(sessionId)}/undo`, body, true);
  sessionArchive = (sessionId: string, body: unknown) => this.post(`/v1/sessions/${encodeURIComponent(sessionId)}/archive`, body, true);
  sessionBatchArchive = (body: { session_ids: string[]; reason?: string; actor?: string; user_id?: string }) =>
    this.post("/v1/sessions/batch/archive", body, true);
  hermesSessionCreate = (body: { title: string; description?: string; initial_context?: string; user_id?: string }) =>
    this.post("/v1/hermes/sessions", body, true);

  userStrategies = () => this.get(`/v1/desktop/users/${encodeURIComponent(this.userId())}/strategies`);
  strategyCreate = (body: unknown) => this.post(`/v1/desktop/users/${encodeURIComponent(this.userId())}/strategies`, body, true);
  strategyUpdate = (id: string, body: unknown) =>
    this.patch(`/v1/desktop/users/${encodeURIComponent(this.userId())}/strategies/${encodeURIComponent(id)}`, body, true);
  strategyDelete = (id: string) => this.delete(`/v1/desktop/users/${encodeURIComponent(this.userId())}/strategies/${encodeURIComponent(id)}`, true);
  strategyReorder = (ordered_ids: string[]) =>
    this.post(`/v1/desktop/users/${encodeURIComponent(this.userId())}/strategies/reorder`, { ordered_ids }, true);

  userStockPools = () => this.get(`/v1/desktop/users/${encodeURIComponent(this.userId())}/stock-pools`);
  stockPoolCreate = (body: unknown) => this.post(`/v1/desktop/users/${encodeURIComponent(this.userId())}/stock-pools`, body, true);
  stockPoolUpdate = (id: string, body: unknown) =>
    this.patch(`/v1/desktop/users/${encodeURIComponent(this.userId())}/stock-pools/${encodeURIComponent(id)}`, body, true);
  stockPoolDelete = (id: string) => this.delete(`/v1/desktop/users/${encodeURIComponent(this.userId())}/stock-pools/${encodeURIComponent(id)}`, true);
  stockPoolReorder = (ordered_ids: string[]) =>
    this.post(`/v1/desktop/users/${encodeURIComponent(this.userId())}/stock-pools/reorder`, { ordered_ids }, true);
  stockPoolAddStock = (poolId: string, body: { code: string; name: string; tags?: string[]; note?: string }) =>
    this.post(`/v1/desktop/users/${encodeURIComponent(this.userId())}/stock-pools/${encodeURIComponent(poolId)}/stocks`, body, true);
  stockPoolRemoveStock = (poolId: string, stockCode: string) =>
    this.delete(`/v1/desktop/users/${encodeURIComponent(this.userId())}/stock-pools/${encodeURIComponent(poolId)}/stocks/${encodeURIComponent(stockCode)}`, true);
  stockPoolBatchRemove = (poolId: string, codes: string[]) =>
    this.post(
      `/v1/desktop/users/${encodeURIComponent(this.userId())}/stock-pools/${encodeURIComponent(poolId)}/stocks/batch-remove`,
      { codes },
      true
    );

  fileSave = (body: { filename: string; content: string; path?: string }) => this.post("/v1/desktop/files/save", body, true);
  async fileUpload(files: File[], context?: { session_id?: string; thread_id?: string }): Promise<unknown> {
    if (this.settings.mode === "mock") {
      const store = this.ensureMockStore();
      const uploaded = await Promise.all(
        files.map(async (file, index) => {
          const mimeType = file.type || "application/octet-stream";
          const isTextLike = /^(text\/|application\/(json|csv|xml))/.test(mimeType) || /\.(txt|md|json|csv|xml|log)$/i.test(file.name);
          const textPreview = isTextLike ? (await file.text()).slice(0, 4000) : "";
          return {
            id: `file_${Date.now()}_${index}`,
            name: file.name,
            filename: file.name,
            size: file.size,
            type: mimeType,
            mime_type: mimeType,
            uploaded_at: nowIso(),
            status: "uploaded",
            parse_status: isTextLike ? "parsed_text_preview" : "uploaded_unparsed",
            text_preview: textPreview || undefined,
            user_id: this.userId(),
            session_id: context?.session_id,
            thread_id: context?.thread_id
          };
        })
      );
      store.files = [...uploaded, ...store.files];
      return { object: "list", data: uploaded };
    }

    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    if (context?.session_id) formData.append("session_id", context.session_id);
    if (context?.thread_id) formData.append("thread_id", context.thread_id);
    return this.multipartRequest("/v1/desktop/files/upload", formData, true);
  }
  userFiles = () => this.get("/v1/desktop/files", { user_id: this.userId() });
  fileDelete = (fileId: string) => this.delete(`/v1/desktop/files/${encodeURIComponent(fileId)}`, true);

  async runEvents(runId: string): Promise<RunEvent[]> {
    if (this.settings.mode === "mock") return clone(mockRunEvents);
    const text = await requestText(this.settings, `/v1/runs/${encodeURIComponent(runId)}/events`);
    return parseSsePayload(text) as RunEvent[];
  }

  tools = () => this.get("/v1/tools");
  callTool = (name: string, body: unknown) => this.post(`/v1/tools/${encodeURIComponent(name)}`, body);
  callAdminTool = (name: string, body: unknown) => this.post(`/v1/hermes/admin/tools/${encodeURIComponent(name)}`, body, true);
  intents = () => this.get("/intents");
  intentGet = (intentId: string) => this.get(`/intents/${encodeURIComponent(intentId)}`);
  createIntent = (body: unknown) => this.post("/intents", body, true);
  intentConfirm = (intentId: string) => this.post(`/intents/${encodeURIComponent(intentId)}/confirm`, {}, true);
  intentDeny = (intentId: string, reason = "denied from desktop V1") => this.post(`/intents/${encodeURIComponent(intentId)}/deny`, { reason }, true);
  approvals = () => this.get("/v1/approvals");
  approvalDecision = (approvalId: string, decision: "approve" | "deny", reason = "desktop V1 decision") =>
    this.post(`/v1/approvals/${encodeURIComponent(approvalId)}/${decision}`, { reason }, true);

  mcpServers = () => this.get("/v1/mcp/servers");
  mcpServerAdd = (body: { name: string; command?: string; args?: string[]; env?: Record<string, string>; transport?: string; url?: string }) =>
    this.post("/v1/mcp/servers", body, true);
  mcpServerUpdate = (id: string, body: unknown) => this.patch(`/v1/mcp/servers/${encodeURIComponent(id)}`, body, true);
  mcpServerDelete = (id: string) => this.delete(`/v1/mcp/servers/${encodeURIComponent(id)}`, true);
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
  skillUpdate = (id: string, body: unknown) => this.patch(`/v1/skills/${encodeURIComponent(id)}`, body, true);
  skillDelete = (id: string) => this.delete(`/v1/skills/${encodeURIComponent(id)}`, true);

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
  gatewayPairing = (query?: { platform?: string; user_id?: string; session_id?: string }) => this.get("/v1/gateway/pairing", query, true);
  gatewayPairingCreate = (body: { action?: "create"; platform?: string; user_id?: string; session_id?: string }) =>
    this.post("/v1/gateway/pairing", body, true);
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

  stockRadarStatus = (query?: { run_id?: string; limit?: number }) => this.get("/v1/desktop/stock-radar/status", query);
  stockRadarCandidates = (query?: { run_id?: string; tier?: string; symbol?: string; min_score?: number; limit?: number }) =>
    this.get("/v1/desktop/stock-radar/candidates", query);
  stockRadarDigest = (query?: { run_id?: string; channels?: string; limit?: number }) => this.get("/v1/desktop/stock-radar/digest", query);
  stockLiveQuote = (code: string) => this.callTool("agent_stock_live_quote", { code, include_source_chain: true });
  stockNewsDigest = (code?: string, limit = 5) =>
    this.callTool("agent_stock_news_digest", code ? { code, limit, include_links: true } : { limit, include_links: true });
  marketTemperatureSnapshot = () => this.callTool("agent_market_temperature_snapshot", { top_n: 8 });
  marketTemperatureReadiness = () => this.callTool("agent_market_temperature_cache_readiness", {});
  marketTemperatureHistory = (limit = 30, includeSnapshot = false) =>
    this.callTool("agent_market_temperature_cache_history", { limit, include_snapshot: includeSnapshot });
  strategyFactoryStatus = (recentRunLimit = 5) =>
    this.callTool("agent_factory_status", { recent_run_limit: recentRunLimit, _timeout_seconds: 10 });
  strategyFactoryRuns = (limit = 10) => this.callTool("agent_factory_runs", { limit });
  strategyFactoryFormalDiagnostics = (topN = 15) =>
    this.callTool("agent_factory_formal_diagnostics", { top_n: topN, _timeout_seconds: 12 });
  strategyDomainEvents = (limit = 20) => this.callTool("agent_strategy_domain_events", { limit });
  factorFactoryStatus = (limit = 20) => this.get("/v1/desktop/factor-factory/status", { limit });
  incubationFactoryStatus = () => this.callTool("agent_incubation_factory_status", {});
  factoryEventList = (query?: { event_id?: string; source?: string; status?: string; event_type?: string; limit?: number }) =>
    this.callTool("agent_factory_event_list", { limit: 20, ...query });
  factoryEventPreviewTasks = (eventId: string, limit = 20) =>
    this.callTool("agent_factory_event_preview_tasks", { event_id: eventId, limit });
  factoryEventLineage = (query?: { event_id?: string; strategy_id?: string; limit?: number }) =>
    this.callTool("agent_factory_event_lineage", { limit: 20, ...query });
  factoryThemeExposureStatus = (query?: { theme?: string; limit?: number }) =>
    this.callTool("agent_factory_theme_exposure_status", { limit: 20, ...query });
  factoryEventOutboxStatus = (query?: { status?: string; limit?: number }) =>
    this.callTool("agent_factory_event_outbox_status", { limit: 20, ...query });
  tradePredictionStatus = (query?: { strategy_id?: string; stock_code?: string; limit?: number }) =>
    this.get("/v1/desktop/trade-predictions/status", query);
  tradePredictionOutcomes = (query?: {
    prediction_id?: string;
    strategy_id?: string;
    stock_code?: string;
    score_version?: string;
    score_status?: string;
    data_quality_status?: string;
    actual_trading_date_lte?: string;
    actual_trading_date_gte?: string;
    limit?: number;
  }) => this.get("/v1/desktop/trade-predictions/outcomes", query);
  tradePredictionMatrix = (query?: { strategy_id?: string; stock_code?: string; score_version?: string; dimensions?: string; limit?: number }) =>
    this.get("/v1/desktop/trade-predictions/matrix", query);
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
  terminalExecute = (body: { command: string; backend?: string; session_id?: string; cwd?: string; timeout_seconds?: number }) =>
    this.callAdminTool("agent_terminal", {
      command: body.command,
      backend: body.backend || "local",
      session_id: body.session_id,
      cwd: body.cwd || ".",
      timeout_seconds: body.timeout_seconds ?? 30,
      max_output_bytes: 131072
    });
  browserSessions = () => this.get("/v1/browser/sessions", undefined, true);
  hermesReadiness = () => this.get("/v1/hermes/readiness");
  financialReadiness = () => this.get("/v1/financial-system/readiness");
}
