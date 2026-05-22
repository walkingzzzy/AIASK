import { formatApiError, normalizeEndpoint, parseSseEvents, requestJson } from "../api";
import { isMockEndpoint } from "../mockApi";
import type {
  AgentResponse,
  AiSmokeResult,
  AiStatus,
  CapabilityParity,
  CapabilityWorkbenchPayload,
  DesktopDataStatus,
  DesktopDataSyncPlan,
  DesktopSettingsStatus,
  FactorFactoryStatus,
  FullModeConsoleData,
  HealthDetailed,
  HermesConsoleSnapshot,
  HermesStatus,
  LocalProfile,
  QuantPresetPayload,
  QuantResearchReport,
  QuantResearchRun,
  ToolCatalogItem,
  ToolEnvelope
} from "../types";

export interface AiaskClientOptions {
  endpoint: string;
  apiToken?: string;
  controlToken?: string;
}

function controlOrApiToken(options: AiaskClientOptions): string {
  return options.controlToken?.trim() || options.apiToken?.trim() || "";
}

function compactForSearch(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export class AiaskApi {
  endpoint: string;
  apiToken: string;
  controlToken: string;

  constructor(options: AiaskClientOptions) {
    this.endpoint = normalizeEndpoint(options.endpoint);
    this.apiToken = options.apiToken || "";
    this.controlToken = options.controlToken || "";
  }

  health(): Promise<HealthDetailed> {
    return requestJson<HealthDetailed>(this.endpoint, "/health/detailed", { token: this.apiToken });
  }

  tools(): Promise<{ data: ToolCatalogItem[] }> {
    return requestJson<{ data: ToolCatalogItem[] }>(this.endpoint, "/v1/tools", { token: this.apiToken });
  }

  capabilities(): Promise<CapabilityWorkbenchPayload> {
    return requestJson<CapabilityWorkbenchPayload>(this.endpoint, "/v1/desktop/capabilities", { token: controlOrApiToken(this) });
  }

  hermesStatus(): Promise<HermesStatus> {
    return requestJson<HermesStatus>(this.endpoint, "/v1/hermes/status", { token: this.apiToken });
  }

  capabilityParity(): Promise<CapabilityParity> {
    return requestJson<CapabilityParity>(this.endpoint, "/v1/capabilities/parity", { token: this.apiToken });
  }

  hermesReadiness(): Promise<unknown> {
    return requestJson<unknown>(this.endpoint, "/v1/hermes/readiness", { token: this.apiToken });
  }

  private async controlData<T>(path: string, fallback: T): Promise<T> {
    try {
      return await requestJson<T>(this.endpoint, path, { token: this.controlToken });
    } catch (error) {
      // Distinguish three failure modes so the UI can show a useful message:
      //   401/403 -> control token missing or invalid
      //   503     -> server has not configured AIASK_AGENT_CONTROL_TOKEN
      //   other   -> network or server-side error
      // formatApiError already maps to AIASK_UNAUTHORIZED / AIASK_FORBIDDEN /
      // AIASK_HTTP_503 / etc., so we just attach a `reason` field that
      // panels can read instead of guessing from the error string.
      const reason = (() => {
        if (typeof (error as { status?: number })?.status === "number") {
          const status = (error as { status: number }).status;
          if (status === 401) return "control_token_invalid";
          if (status === 403) return "control_token_forbidden";
          if (status === 503) return "control_token_unconfigured";
          return `http_${status}`;
        }
        return "network";
      })();
      if (fallback && typeof fallback === "object" && !Array.isArray(fallback)) {
        return {
          ...(fallback as Record<string, unknown>),
          status: "degraded",
          error: formatApiError(error),
          reason
        } as T;
      }
      return fallback;
    }
  }

  async fullConsoleSnapshot(): Promise<HermesConsoleSnapshot> {
    const [hermesStatus, parity, readiness] = await Promise.all([
      this.hermesStatus(),
      this.capabilityParity(),
      this.hermesReadiness()
    ]);
    const fullConsole: FullModeConsoleData = {
      parity,
      readiness,
      providers: hermesStatus.providers,
      memory: hermesStatus.memory,
      acp: hermesStatus.acp,
      security: hermesStatus.security,
      skillPacks: hermesStatus.skill_packs
    };

    if (!this.controlToken.trim()) {
      return {
        hermesStatus,
        hermesTools: [],
        fullConsole,
        message: "CONTROL_TOKEN_REQUIRED"
      };
    }

    const [
      catalog,
      processes,
      browserSessions,
      skills,
      plugins,
      mcpServers,
      mcpTools,
      mcpResources,
      mcpPrompts,
      mcpOauth,
      webhooks,
      approvals,
      jobs,
      gatewayStatus,
      gatewayPlatforms,
      gatewayMessages,
      gatewayDirectory,
      terminalBackends,
      terminalSessions,
      learningStatus,
      learningReview,
      rlEnvironments,
      rlRuns
    ] = await Promise.all([
      this.controlData<{ data: ToolCatalogItem[] }>("/v1/hermes/tools", { data: [] }),
      this.controlData<{ data: unknown[] }>("/v1/processes", { data: [] }),
      this.controlData<{ data: unknown[] }>("/v1/browser/sessions", { data: [] }),
      this.controlData<{ data: unknown }>("/v1/skills", { data: {} }),
      this.controlData<{ data: unknown[] }>("/v1/plugins", { data: [] }),
      this.controlData<{ data: unknown[] }>("/v1/mcp/servers?all=true", { data: [] }),
      this.controlData<{ data: unknown[] }>("/v1/mcp/tools?all=true", { data: [] }),
      this.controlData<{ data: unknown[] }>("/v1/mcp/resources?all=true", { data: [] }),
      this.controlData<{ data: unknown[] }>("/v1/mcp/prompts?all=true", { data: [] }),
      this.controlData<{ data: unknown[] }>("/v1/mcp/oauth_status?all=true", { data: [] }),
      this.controlData<{ data: unknown[] }>("/v1/webhooks", { data: [] }),
      this.controlData<{ data: unknown[] }>("/v1/approvals", { data: [] }),
      this.controlData<{ data: unknown[] }>("/v1/jobs", { data: [] }),
      this.controlData<unknown>("/v1/gateway/status", {}),
      this.controlData<{ data: unknown[] }>("/v1/gateway/platforms", { data: [] }),
      this.controlData<{ data: unknown[] }>("/v1/gateway/messages", { data: [] }),
      this.controlData<{ data: unknown[] }>("/v1/gateway/directory", { data: [] }),
      this.controlData<{ data: unknown[] }>("/v1/terminal/backends", { data: [] }),
      this.controlData<{ data: unknown[] }>("/v1/terminal/sessions", { data: [] }),
      this.controlData<unknown>("/v1/learning/status", {}),
      this.controlData<{ data: unknown[] }>("/v1/learning/review", { data: [] }),
      this.controlData<{ data: unknown }>("/v1/rl/environments", { data: {} }),
      this.controlData<{ data: unknown[] }>("/v1/rl/runs", { data: [] })
    ]);

    Object.assign(fullConsole, {
      processes: processes.data || [],
      browserSessions: browserSessions.data || [],
      skills: skills.data,
      plugins: plugins.data || [],
      mcpServers: mcpServers.data || [],
      mcpTools: mcpTools.data || [],
      mcpResources: mcpResources.data || [],
      mcpPrompts: mcpPrompts.data || [],
      mcpOauth: mcpOauth.data || [],
      webhooks: webhooks.data || [],
      approvals: approvals.data || [],
      jobs: jobs.data || [],
      gatewayStatus,
      gatewayPlatforms: gatewayPlatforms.data || [],
      gatewayMessages: gatewayMessages.data || [],
      gatewayDirectory: gatewayDirectory.data || [],
      terminalBackends: terminalBackends.data || [],
      terminalSessions: terminalSessions.data || [],
      learningStatus,
      learningReview: learningReview.data || [],
      rlEnvironments: rlEnvironments.data,
      rlRuns: rlRuns.data || [],
      homeAssistant: (hermesStatus.parity?.matrix || []).filter((item) => item.reference === "homeassistant"),
      moa: (catalog.data || []).filter((tool) => tool.name === "agent_moa"),
      dynamicMcpTools: (mcpTools.data || []).filter((tool) => compactForSearch(tool).includes("agent_mcp_")),
      dynamicPluginTools: (plugins.data || []).filter((plugin) => compactForSearch(plugin).includes("tools")),
      pluginHooks: (readiness as { plugins?: unknown }).plugins,
      tuiController: (readiness as { tui?: unknown }).tui || hermesStatus.tui || {},
      rlReadiness: (readiness as { rl?: unknown }).rl,
      providers: hermesStatus.providers || (readiness as { providers?: unknown }).providers,
      memory: hermesStatus.memory || (readiness as { memory?: unknown }).memory,
      acp: hermesStatus.acp || (readiness as { acp?: unknown }).acp,
      security: hermesStatus.security || (readiness as { security?: unknown }).security,
      skillPacks: hermesStatus.skill_packs || (readiness as { skill_packs?: unknown }).skill_packs
    });

    return {
      hermesStatus,
      hermesTools: catalog.data || [],
      fullConsole,
      message: "FULL_CONSOLE_SYNCED"
    };
  }

  aiStatus(): Promise<AiStatus> {
    return requestJson<AiStatus>(this.endpoint, "/v1/ai/status", { token: this.apiToken });
  }

  aiSmoke(prompt?: string, model?: string): Promise<AiSmokeResult> {
    return requestJson<AiSmokeResult>(this.endpoint, "/v1/ai/smoke", {
      method: "POST",
      token: this.apiToken,
      body: { prompt, model }
    });
  }

  aiModels(): Promise<{ data: Array<Record<string, unknown>>; configured: boolean; unsupported?: boolean; error?: string }> {
    return requestJson(this.endpoint, "/v1/ai/models", { token: this.apiToken });
  }

  response(body: Record<string, unknown>, token?: string): Promise<AgentResponse> {
    return requestJson<AgentResponse>(this.endpoint, "/v1/responses", { method: "POST", token: token || this.apiToken, body });
  }

  async runEvents(runId: string, token?: string): Promise<Record<string, unknown>[]> {
    if (isMockEndpoint(this.endpoint)) {
      const payload = await requestJson<{ data?: Record<string, unknown>[] }>(
        this.endpoint,
        `/v1/runs/${encodeURIComponent(runId)}/events`,
        { token: token || this.apiToken }
      );
      return payload.data || [];
    }
    const response = await fetch(`${this.endpoint}/v1/runs/${encodeURIComponent(runId)}/events`, {
      headers: token?.trim() ? { Authorization: `Bearer ${token.trim()}` } : {}
    });
    if (!response.ok) throw new Error(`AIASK_HTTP_${response.status}`);
    return parseSseEvents<Record<string, unknown>>(await response.text());
  }

  callTool<T = unknown>(tool: string, body: Record<string, unknown>, token?: string): Promise<ToolEnvelope & { data: T }> {
    return requestJson<ToolEnvelope & { data: T }>(this.endpoint, `/v1/tools/${tool}`, {
      method: "POST",
      token: token ?? this.apiToken,
      body
    });
  }

  readOnlyTool<T = unknown>(tool: string, body: Record<string, unknown>): Promise<ToolEnvelope & { data: T }> {
    return this.callTool<T>(tool, body, this.apiToken);
  }

  hermesToolCall<T = unknown>(tool: string, body: Record<string, unknown>): Promise<ToolEnvelope & { data: T }> {
    return requestJson<ToolEnvelope & { data: T }>(this.endpoint, `/v1/hermes/admin/tools/${encodeURIComponent(tool)}`, {
      method: "POST",
      token: this.controlToken,
      body
    });
  }

  strategyDomainEvents(body: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.readOnlyTool<Record<string, unknown>>("agent_strategy_domain_events", body);
  }

  incubationFactoryStatus(): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.readOnlyTool<Record<string, unknown>>("agent_incubation_factory_status", {});
  }

  createActionIntent(action: string, params: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestJson<ToolEnvelope & { data: Record<string, unknown> }>(this.endpoint, "/intents", {
      method: "POST",
      token: this.controlToken,
      body: {
        action,
        params,
        rationale,
        ttl_seconds: 86400
      }
    });
  }

  factoryIntentCreate(action: string, params: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent(action, params, rationale);
  }

  settingsStatus(): Promise<DesktopSettingsStatus> {
    return requestJson<DesktopSettingsStatus>(this.endpoint, "/v1/desktop/settings/status", { token: controlOrApiToken(this) });
  }

  modelProviderStatus(): Promise<unknown> {
    return this.settingsStatus().then((payload) => payload.llm.providers);
  }

  memoryStatus(): Promise<unknown> {
    return this.settingsStatus().then((payload) => payload.memory);
  }

  memorySearch(body: Record<string, unknown>): Promise<ToolEnvelope & { data: unknown }> {
    return this.readOnlyTool("agent_memory_search", body);
  }

  dataStatus(body: { codes?: string[]; max_stale_days?: number } = {}): Promise<DesktopDataStatus> {
    const params = new URLSearchParams();
    if (body.codes?.length) params.set("codes", body.codes.join(","));
    if (body.max_stale_days) params.set("max_stale_days", String(body.max_stale_days));
    const query = params.toString();
    return requestJson<DesktopDataStatus>(this.endpoint, `/v1/desktop/data/status${query ? `?${query}` : ""}`, {
      token: this.apiToken
    });
  }

  dataGate(body: Record<string, unknown>): Promise<ToolEnvelope & { data: unknown }> {
    return this.readOnlyTool("agent_quant_data_gate", body);
  }

  dataSyncPlan(body: Record<string, unknown>): Promise<DesktopDataSyncPlan> {
    return requestJson<DesktopDataSyncPlan>(this.endpoint, "/v1/desktop/data/sync-plan", {
      method: "POST",
      token: this.apiToken,
      body
    });
  }

  localProfileGet(): Promise<LocalProfile> {
    return requestJson<LocalProfile>(this.endpoint, "/v1/desktop/users/local-profile", { token: this.apiToken });
  }

  localProfileSave(body: Pick<LocalProfile, "user_id" | "profile_name">): Promise<LocalProfile> {
    return requestJson<LocalProfile>(this.endpoint, "/v1/desktop/users/local-profile", {
      method: "PATCH",
      token: this.apiToken,
      body
    });
  }

  factorFactoryStatus(limit = 50): Promise<FactorFactoryStatus> {
    return requestJson<FactorFactoryStatus>(this.endpoint, `/v1/desktop/factor-factory/status?limit=${encodeURIComponent(String(limit))}`, {
      token: this.apiToken
    });
  }

  factorFactoryRunIntent(params: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent("factor_factory.run_once", params, rationale || "Run Factor Mining Factory once from Desktop.");
  }

  factorFactoryMaintenanceIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent("factor_factory.maintenance", params, rationale || "Run Factor Mining Factory maintenance from Desktop.");
  }

  jobsList(): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
    return requestJson<{ object: string; data: Array<Record<string, unknown>> }>(this.endpoint, "/v1/jobs", { token: this.apiToken });
  }

  jobCreate(body: Record<string, unknown>): Promise<Record<string, unknown>> {
    return requestJson<Record<string, unknown>>(this.endpoint, "/v1/jobs", {
      method: "POST",
      token: this.apiToken,
      body
    });
  }

  jobsCreate(body: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.jobCreate(body);
  }

  jobUpdate(jobId: string, body: Record<string, unknown>): Promise<Record<string, unknown>> {
    return requestJson<Record<string, unknown>>(this.endpoint, `/v1/jobs/${encodeURIComponent(jobId)}`, {
      method: "PATCH",
      token: this.apiToken,
      body
    });
  }

  jobsUpdate(jobId: string, body: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.jobUpdate(jobId, body);
  }

  jobDelete(jobId: string): Promise<Record<string, unknown>> {
    return requestJson<Record<string, unknown>>(this.endpoint, `/v1/jobs/${encodeURIComponent(jobId)}`, {
      method: "DELETE",
      token: this.apiToken
    });
  }

  jobsDelete(jobId: string): Promise<Record<string, unknown>> {
    return this.jobDelete(jobId);
  }

  jobRun(jobId: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestJson<ToolEnvelope & { data: Record<string, unknown> }>(this.endpoint, `/v1/jobs/${encodeURIComponent(jobId)}/run`, {
      method: "POST",
      token: this.apiToken,
      body: {}
    });
  }

  jobsRun(jobId: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.jobRun(jobId);
  }

  sessionsList(userId?: string, limit = 100): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
    const params = new URLSearchParams();
    if (userId) params.set("user_id", userId);
    params.set("limit", String(limit));
    return requestJson<{ object: string; data: Array<Record<string, unknown>> }>(this.endpoint, `/v1/hermes/sessions?${params.toString()}`, {
      token: controlOrApiToken(this)
    });
  }

  sessionMessages(sessionId: string, limit = 200): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
    return requestJson<{ object: string; data: Array<Record<string, unknown>> }>(
      this.endpoint,
      `/v1/sessions/${encodeURIComponent(sessionId)}/messages?limit=${encodeURIComponent(String(limit))}`,
      { token: this.apiToken }
    );
  }

  search(query: string, body: { session_id?: string; user_id?: string; limit?: number } = {}): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
    const params = new URLSearchParams();
    params.set("query", query);
    if (body.session_id) params.set("session_id", body.session_id);
    if (body.user_id) params.set("user_id", body.user_id);
    if (body.limit) params.set("limit", String(body.limit));
    return requestJson<{ object: string; data: Array<Record<string, unknown>> }>(this.endpoint, `/v1/search?${params.toString()}`, {
      token: this.apiToken
    });
  }

  skillInstall(body: Record<string, unknown>): Promise<unknown> {
    return requestJson(this.endpoint, "/v1/skills", { method: "POST", token: this.controlToken, body });
  }

  skillUpdate(name: string, body: Record<string, unknown>): Promise<unknown> {
    return requestJson(this.endpoint, `/v1/skills/${encodeURIComponent(name)}`, {
      method: "PATCH",
      token: this.controlToken,
      body
    });
  }

  skillDelete(name: string): Promise<unknown> {
    return requestJson(this.endpoint, `/v1/skills/${encodeURIComponent(name)}`, {
      method: "DELETE",
      token: this.controlToken
    });
  }

  pluginToggle(name: string, enabled: boolean): Promise<unknown> {
    return requestJson(this.endpoint, `/v1/plugins/${encodeURIComponent(name)}`, {
      method: "PATCH",
      token: this.controlToken,
      body: { enabled }
    });
  }

  pluginToolTest(name: string, tool: string, body: Record<string, unknown> = {}): Promise<unknown> {
    return requestJson(this.endpoint, `/v1/plugins/${encodeURIComponent(name)}/tools/${encodeURIComponent(tool)}/test`, {
      method: "POST",
      token: this.controlToken,
      body
    });
  }

  connectorsSummary(): Promise<{ data: unknown; status?: string; error?: string }> {
    return requestJson<{ data: unknown; status?: string; error?: string }>(this.endpoint, "/v1/connectors/summary", {
      token: controlOrApiToken(this)
    });
  }

  quantPresets(): Promise<QuantPresetPayload> {
    return requestJson<QuantPresetPayload>(this.endpoint, "/v1/desktop/quant/presets", { token: this.apiToken });
  }

  quantResearchRun(body: Record<string, unknown>): Promise<ToolEnvelope & { data: { research?: QuantResearchRun } }> {
    return requestJson<ToolEnvelope & { data: { research?: QuantResearchRun } }>(
      this.endpoint,
      "/v1/desktop/quant/research-runs",
      {
        method: "POST",
        token: this.apiToken,
        body
      }
    );
  }

  quantResearchReport(researchId: string): Promise<QuantResearchReport> {
    return requestJson<QuantResearchReport>(
      this.endpoint,
      `/v1/desktop/quant/research-runs/${encodeURIComponent(researchId)}/report`,
      { token: this.apiToken }
    );
  }

  mcpRegisterLocal(body: Record<string, unknown> = {}): Promise<unknown> {
    return requestJson(this.endpoint, "/v1/mcp/register-local", {
      method: "POST",
      token: this.controlToken,
      body
    });
  }

  mcpDiscover(server: string): Promise<unknown> {
    return requestJson(this.endpoint, "/v1/mcp/discover", {
      method: "POST",
      token: this.controlToken,
      body: { server }
    });
  }

  mcpResourceRead(uri: string, server?: string): Promise<unknown> {
    return requestJson(this.endpoint, "/v1/mcp/resources/read", {
      method: "POST",
      token: this.controlToken,
      body: { uri, server }
    });
  }

  mcpPromptGet(name: string, argumentsValue: Record<string, unknown> = {}, server?: string): Promise<unknown> {
    return requestJson(this.endpoint, "/v1/mcp/prompts/get", {
      method: "POST",
      token: this.controlToken,
      body: { name, arguments: argumentsValue, server }
    });
  }

  mcpOauthStart(server: string): Promise<unknown> {
    return requestJson(this.endpoint, "/v1/mcp/oauth/start", {
      method: "POST",
      token: this.controlToken,
      body: { server }
    });
  }
}
