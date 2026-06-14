import { formatApiError, normalizeEndpoint, parseSseEvents, requestJson } from "../api";
import { isMockEndpoint } from "../mockApi";
import type {
  AgentResponse,
  AgentArtifactRecord,
  AgentSourceRecord,
  AiConfigPayload,
  AiConfigSavePayload,
  AiConfigSaveResult,
  AiSmokeResult,
  AiStatus,
  ApprovalItem,
  BrokerAnalyticsPayload,
  BrokerReadinessPayload,
  BrokerSnapshotPayload,
  BrokerSyncPayload,
  CapabilityParity,
  CapabilityWorkbenchPayload,
  ConnectorDetail,
  DesktopDataStatus,
  DesktopDataSyncPlan,
  DesktopRunSummary,
  DesktopSettingsStatus,
  DesktopWorkbenchSummary,
  FactorFactoryStatus,
  FactoryEventRecord,
  FinancialManagerCatalog,
  FinancialManagerIntentResult,
  FinancialManagerQueryResult,
  FinancialManagerStatus,
  FullModeConsoleData,
  GatewayDaemonStatus,
  GatewayMessage,
  GatewayPlatform,
  HealthDetailed,
  HandoffQueuePayload,
  HermesConsoleSnapshot,
  HermesStatus,
  JobRunRecord,
  LearningProposal,
  LocalProfile,
  MarketTemperatureCacheHistory,
  MarketTemperatureForwardValidation,
  MarketTemperatureIndustryConstituents,
  MarketTemperatureIndustryHistory,
  MarketTemperatureCacheReadiness,
  MarketTemperatureSnapshot,
  PluginCommand,
  NormalizedRunEvent,
  QuantPresetPayload,
  QuantResearchReport,
  QuantResearchRun,
  RecentSessionSummary,
  ResponseRecord,
  RlRun,
  RunRecord,
  RunTraceEvalPayload,
  SessionArchivePayload,
  SessionResumeContextPayload,
  SessionUndoPayload,
  StockDataSourceConfig,
  StockDataSourcesStatus,
  StockDataSourceTestResult,
  FeedbackEvent,
  RetentionSweepResult,
  ToolCatalogItem,
  ToolEnvelope,
  TradePredictionMatrix,
  TradePredictionOutcomes,
  TradePredictionStatus,
  UserAnalyticsSummary,
  UserActivityEvent,
  UserActivityPayload,
  UserDataDeleteResult,
  UserDataExport,
  UserDataPolicy,
  UserLearningDataset,
  WorkflowRecommendationPayload,
  WebhookSubscription
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

  aiConfig(): Promise<AiConfigPayload> {
    return requestJson<AiConfigPayload>(this.endpoint, "/v1/ai/config", { token: this.apiToken });
  }

  aiConfigSave(body: AiConfigSavePayload): Promise<AiConfigSaveResult> {
    return requestJson<AiConfigSaveResult>(this.endpoint, "/v1/ai/config", {
      method: "PATCH",
      token: this.controlToken,
      body
    });
  }

  response(body: Record<string, unknown>, token?: string): Promise<AgentResponse> {
    return requestJson<AgentResponse>(this.endpoint, "/v1/responses", { method: "POST", token: token || this.apiToken, body });
  }

  responseGet(responseId: string): Promise<ResponseRecord> {
    return requestJson<ResponseRecord>(this.endpoint, `/v1/responses/${encodeURIComponent(responseId)}`, { token: this.apiToken });
  }

  responseDelete(responseId: string): Promise<{ id: string; object: string; deleted: boolean }> {
    return requestJson<{ id: string; object: string; deleted: boolean }>(
      this.endpoint,
      `/v1/responses/${encodeURIComponent(responseId)}`,
      { method: "DELETE", token: this.apiToken }
    );
  }

  runGet(runId: string): Promise<RunRecord> {
    return requestJson<RunRecord>(this.endpoint, `/v1/runs/${encodeURIComponent(runId)}`, { token: controlOrApiToken(this) });
  }

  runTraceEval(runId: string): Promise<RunTraceEvalPayload> {
    return requestJson<RunTraceEvalPayload>(
      this.endpoint,
      `/v1/runs/${encodeURIComponent(runId)}/trace-eval`,
      { token: controlOrApiToken(this) }
    );
  }

  runArtifacts(runId: string, filters: { kind?: string; limit?: number } = {}): Promise<{ object: string; run_id: string; data: AgentArtifactRecord[] }> {
    const params = new URLSearchParams();
    if (filters.kind) params.set("kind", filters.kind);
    if (filters.limit) params.set("limit", String(filters.limit));
    const query = params.toString();
    return requestJson<{ object: string; run_id: string; data: AgentArtifactRecord[] }>(
      this.endpoint,
      `/v1/runs/${encodeURIComponent(runId)}/artifacts${query ? `?${query}` : ""}`,
      { token: controlOrApiToken(this) }
    );
  }

  runSources(runId: string, filters: { source_type?: string; limit?: number } = {}): Promise<{ object: string; run_id: string; data: AgentSourceRecord[] }> {
    const params = new URLSearchParams();
    if (filters.source_type) params.set("source_type", filters.source_type);
    if (filters.limit) params.set("limit", String(filters.limit));
    const query = params.toString();
    return requestJson<{ object: string; run_id: string; data: AgentSourceRecord[] }>(
      this.endpoint,
      `/v1/runs/${encodeURIComponent(runId)}/sources${query ? `?${query}` : ""}`,
      { token: controlOrApiToken(this) }
    );
  }

  sessionArtifacts(sessionId: string, filters: { kind?: string; limit?: number } = {}): Promise<{ object: string; session_id: string; data: AgentArtifactRecord[] }> {
    const params = new URLSearchParams();
    if (filters.kind) params.set("kind", filters.kind);
    if (filters.limit) params.set("limit", String(filters.limit));
    const query = params.toString();
    return requestJson<{ object: string; session_id: string; data: AgentArtifactRecord[] }>(
      this.endpoint,
      `/v1/sessions/${encodeURIComponent(sessionId)}/artifacts${query ? `?${query}` : ""}`,
      { token: this.apiToken }
    );
  }

  sessionSources(sessionId: string, filters: { source_type?: string; limit?: number } = {}): Promise<{ object: string; session_id: string; data: AgentSourceRecord[] }> {
    const params = new URLSearchParams();
    if (filters.source_type) params.set("source_type", filters.source_type);
    if (filters.limit) params.set("limit", String(filters.limit));
    const query = params.toString();
    return requestJson<{ object: string; session_id: string; data: AgentSourceRecord[] }>(
      this.endpoint,
      `/v1/sessions/${encodeURIComponent(sessionId)}/sources${query ? `?${query}` : ""}`,
      { token: this.apiToken }
    );
  }

  runCancel(runId: string): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, `/v1/runs/${encodeURIComponent(runId)}/cancel`, {
      method: "POST",
      token: controlOrApiToken(this),
      body: {}
    });
  }

  runStop(runId: string): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, `/v1/runs/${encodeURIComponent(runId)}/stop`, {
      method: "POST",
      token: controlOrApiToken(this),
      body: {}
    });
  }

  runSteer(runId: string, instruction: string): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, `/v1/runs/${encodeURIComponent(runId)}/steer`, {
      method: "POST",
      token: controlOrApiToken(this),
      body: { instruction }
    });
  }

  workbenchSummary(): Promise<DesktopWorkbenchSummary> {
    return requestJson<DesktopWorkbenchSummary>(this.endpoint, "/v1/desktop/workbench/summary", {
      token: this.apiToken
    });
  }

  runsList(filters: { session_id?: string; status?: string; limit?: number } = {}): Promise<{ object: string; data: DesktopRunSummary[] }> {
    const params = new URLSearchParams();
    if (filters.session_id) params.set("session_id", filters.session_id);
    if (filters.status) params.set("status", filters.status);
    if (filters.limit) params.set("limit", String(filters.limit));
    const query = params.toString();
    return requestJson<{ object: string; data: DesktopRunSummary[] }>(
      this.endpoint,
      `/v1/desktop/runs${query ? `?${query}` : ""}`,
      { token: this.apiToken }
    );
  }

  async runEvents(runId: string, token?: string): Promise<NormalizedRunEvent[]> {
    if (isMockEndpoint(this.endpoint)) {
      const payload = await requestJson<{ data?: NormalizedRunEvent[] }>(
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
    return parseSseEvents<NormalizedRunEvent>(await response.text());
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

  marketTemperatureSnapshot(body: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: MarketTemperatureSnapshot }> {
    return this.readOnlyTool<MarketTemperatureSnapshot>("agent_market_temperature_snapshot", body);
  }

  marketTemperatureCacheReadiness(body: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: MarketTemperatureCacheReadiness }> {
    return this.readOnlyTool<MarketTemperatureCacheReadiness>("agent_market_temperature_cache_readiness", body);
  }

  marketTemperatureCacheHistory(body: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: MarketTemperatureCacheHistory }> {
    return this.readOnlyTool<MarketTemperatureCacheHistory>("agent_market_temperature_cache_history", body);
  }

  marketTemperatureIndustryHistory(body: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: MarketTemperatureIndustryHistory }> {
    return this.readOnlyTool<MarketTemperatureIndustryHistory>("agent_market_temperature_industry_history", body);
  }

  marketTemperatureIndustryConstituents(body: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: MarketTemperatureIndustryConstituents }> {
    return this.readOnlyTool<MarketTemperatureIndustryConstituents>("agent_market_temperature_industry_constituents", body);
  }

  marketTemperatureForwardValidation(body: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: MarketTemperatureForwardValidation }> {
    return this.readOnlyTool<MarketTemperatureForwardValidation>("agent_market_temperature_forward_validation", body);
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

  factoryEventList(filters: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: { events?: FactoryEventRecord[] } & Record<string, unknown> }> {
    const cleaned: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(filters)) {
      if (value === undefined || value === null || value === "") continue;
      cleaned[key === "event_source" ? "source" : key] = value;
    }
    return this.readOnlyTool("agent_factory_event_list", cleaned);
  }

  factoryEventPreviewTasks(eventId: string, extras: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.readOnlyTool<Record<string, unknown>>("agent_factory_event_preview_tasks", { event_id: eventId, ...extras });
  }

  factoryEventLineage(filters: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    const cleaned: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(filters)) {
      if (value === undefined || value === null || value === "") continue;
      cleaned[key] = value;
    }
    return this.readOnlyTool<Record<string, unknown>>("agent_factory_event_lineage", cleaned);
  }

  factoryThemeExposureStatus(body: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.readOnlyTool<Record<string, unknown>>("agent_factory_theme_exposure_status", body);
  }

  factoryEventOutboxStatus(body: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.readOnlyTool<Record<string, unknown>>("agent_factory_event_outbox_status", body);
  }

  stockRadarStatus(filters: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value === undefined || value === null || value === "") continue;
      params.set(key, String(value));
    }
    const query = params.toString();
    return requestJson<ToolEnvelope & { data: Record<string, unknown> }>(
      this.endpoint,
      `/v1/desktop/stock-radar/status${query ? `?${query}` : ""}`,
      { token: this.apiToken }
    );
  }

  stockRadarCandidates(filters: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value === undefined || value === null || value === "") continue;
      params.set(key, String(value));
    }
    const query = params.toString();
    return requestJson<ToolEnvelope & { data: Record<string, unknown> }>(
      this.endpoint,
      `/v1/desktop/stock-radar/candidates${query ? `?${query}` : ""}`,
      { token: this.apiToken }
    );
  }

  stockRadarDigest(filters: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value === undefined || value === null || value === "") continue;
      params.set(key, Array.isArray(value) ? value.join(",") : String(value));
    }
    const query = params.toString();
    return requestJson<ToolEnvelope & { data: Record<string, unknown> }>(
      this.endpoint,
      `/v1/desktop/stock-radar/digest${query ? `?${query}` : ""}`,
      { token: this.apiToken }
    );
  }

  stockRadarRunIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent("stock_radar.run_once", params, rationale || "Run AIASK stock radar once from Desktop.");
  }

  stockRadarPushDigestIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent("stock_radar.push_digest", params, rationale || "Create a stock radar digest delivery intent from Desktop.");
  }

  stockRadarScheduleUpdateIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent("stock_radar.schedule_update", params, rationale || "Update stock radar schedule from Desktop.");
  }

  // Write actions go through the ActionIntent chain enforced by PR-F:
  //   POST /intents (create) → POST /intents/{id}/confirm → adapter.
  // Desktop never touches ``ACTION_HANDLERS`` directly; it stays on
  // the read-only MCP tool surface for previews and on the intent
  // surface for writes.
  factoryEventCreateIntent(payload: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent("strategy_manager.factory_event_create", payload, rationale);
  }

  factoryEventApproveIntent(eventId: string, approverId: string, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent(
      "strategy_manager.factory_event_approve",
      { event_id: eventId, approver_id: approverId },
      rationale
    );
  }

  factoryEventUpdateIntent(eventId: string, updates: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent(
      "strategy_manager.factory_event_update",
      { event_id: eventId, ...updates },
      rationale
    );
  }

  factoryEventRecordOutcomeIntent(eventId: string, outcome: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent(
      "strategy_manager.factory_event_record_outcome",
      { event_id: eventId, ...outcome },
      rationale
    );
  }

  factoryEventBootstrapIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent(
      "strategy_manager.factory_event_bootstrap",
      params,
      rationale || "Bootstrap the default theme graph and refresh the exposure matrix from Desktop."
    );
  }

  factoryThemeExposureRefreshIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent(
      "strategy_manager.factory_theme_exposure_refresh",
      params,
      rationale || "Refresh the TDX-only theme exposure matrix from Desktop."
    );
  }

  factoryEventOutboxDrainIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent(
      "strategy_manager.factory_event_outbox_drain",
      params,
      rationale || "Drain event-driven task outbox from Desktop."
    );
  }

  factoryThemeRegressionRunIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent(
      "strategy_manager.factory_theme_regression_run",
      params,
      rationale || "Run theme-response regression from Desktop."
    );
  }

  confirmIntent(intentId: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestJson<ToolEnvelope & { data: Record<string, unknown> }>(
      this.endpoint,
      `/intents/${encodeURIComponent(intentId)}/confirm`,
      { method: "POST", token: this.controlToken, body: {} }
    );
  }

  denyIntent(intentId: string, reason?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestJson<ToolEnvelope & { data: Record<string, unknown> }>(
      this.endpoint,
      `/intents/${encodeURIComponent(intentId)}/deny`,
      { method: "POST", token: this.controlToken, body: { reason: reason || "" } }
    );
  }

  intentsList(status?: string, limit = 100): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    params.set("limit", String(limit));
    return requestJson<{ object: string; data: Array<Record<string, unknown>> }>(this.endpoint, `/intents?${params.toString()}`, {
      token: controlOrApiToken(this)
    });
  }

  incubationFactoryStatus(): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.readOnlyTool<Record<string, unknown>>("agent_incubation_factory_status", {});
  }

  tradePredictionStatus(filters: { strategy_id?: string; stock_code?: string; limit?: number } = {}): Promise<ToolEnvelope & { data: TradePredictionStatus }> {
    const params = new URLSearchParams();
    if (filters.strategy_id) params.set("strategy_id", filters.strategy_id);
    if (filters.stock_code) params.set("stock_code", filters.stock_code);
    if (filters.limit) params.set("limit", String(filters.limit));
    const query = params.toString();
    return requestJson<ToolEnvelope & { data: TradePredictionStatus }>(
      this.endpoint,
      `/v1/desktop/trade-predictions/status${query ? `?${query}` : ""}`,
      { token: this.apiToken }
    );
  }

  tradePredictionOutcomes(
    filters: {
      prediction_id?: string;
      strategy_id?: string;
      stock_code?: string;
      score_version?: string;
      score_status?: string;
      data_quality_status?: string;
      actual_trading_date_lte?: string;
      actual_trading_date_gte?: string;
      limit?: number;
    } = {}
  ): Promise<ToolEnvelope & { data: TradePredictionOutcomes }> {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value === undefined || value === null || value === "") continue;
      params.set(key, String(value));
    }
    const query = params.toString();
    return requestJson<ToolEnvelope & { data: TradePredictionOutcomes }>(
      this.endpoint,
      `/v1/desktop/trade-predictions/outcomes${query ? `?${query}` : ""}`,
      { token: this.apiToken }
    );
  }

  tradePredictionMatrix(
    filters: {
      strategy_id?: string;
      stock_code?: string;
      score_version?: string;
      dimensions?: string[];
      limit?: number;
    } = {}
  ): Promise<ToolEnvelope & { data: TradePredictionMatrix }> {
    const params = new URLSearchParams();
    if (filters.strategy_id) params.set("strategy_id", filters.strategy_id);
    if (filters.stock_code) params.set("stock_code", filters.stock_code);
    if (filters.score_version) params.set("score_version", filters.score_version);
    if (filters.dimensions?.length) params.set("dimensions", filters.dimensions.join(","));
    if (filters.limit) params.set("limit", String(filters.limit));
    const query = params.toString();
    return requestJson<ToolEnvelope & { data: TradePredictionMatrix }>(
      this.endpoint,
      `/v1/desktop/trade-predictions/matrix${query ? `?${query}` : ""}`,
      { token: this.apiToken }
    );
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

  getIntent(intentId: string): Promise<ToolEnvelope> {
    return requestJson<ToolEnvelope>(this.endpoint, `/intents/${encodeURIComponent(intentId)}`, {
      token: this.apiToken
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

  stockDataSources(): Promise<StockDataSourcesStatus> {
    return requestJson<StockDataSourcesStatus>(this.endpoint, "/v1/desktop/stock-data-sources", {
      token: controlOrApiToken(this)
    });
  }

  stockDataSourceSave(body: StockDataSourceConfig): Promise<{ object: string; source: StockDataSourceConfig; secrets_redacted?: boolean }> {
    return requestJson<{ object: string; source: StockDataSourceConfig; secrets_redacted?: boolean }>(
      this.endpoint,
      "/v1/desktop/stock-data-sources",
      {
        method: "POST",
        token: this.controlToken,
        body
      }
    );
  }

  stockDataSourceTest(body: Record<string, unknown>): Promise<StockDataSourceTestResult> {
    return requestJson<StockDataSourceTestResult>(this.endpoint, "/v1/desktop/stock-data-sources/test", {
      method: "POST",
      token: this.controlToken,
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

  recordEvents(events: UserActivityEvent | UserActivityEvent[]): Promise<{ object: string; data: UserActivityEvent[]; count: number; secrets_redacted?: boolean }> {
    const list = Array.isArray(events) ? events : [events];
    return requestJson<{ object: string; data: UserActivityEvent[]; count: number; secrets_redacted?: boolean }>(
      this.endpoint,
      "/v1/desktop/events",
      {
        method: "POST",
        token: this.apiToken,
        body: { events: list }
      }
    );
  }

  recordFeedback(body: FeedbackEvent): Promise<{ object: string; data: FeedbackEvent; secrets_redacted?: boolean }> {
    return requestJson<{ object: string; data: FeedbackEvent; secrets_redacted?: boolean }>(
      this.endpoint,
      "/v1/desktop/feedback",
      {
        method: "POST",
        token: this.apiToken,
        body
      }
    );
  }

  userActivity(userId: string, limit = 20): Promise<UserActivityPayload> {
    return requestJson<UserActivityPayload>(
      this.endpoint,
      `/v1/desktop/users/${encodeURIComponent(userId)}/activity?limit=${encodeURIComponent(String(limit))}`,
      { token: controlOrApiToken(this) }
    );
  }

  userAnalyticsSummary(userId?: string, limit = 20): Promise<UserAnalyticsSummary> {
    const params = new URLSearchParams();
    if (userId) params.set("user_id", userId);
    params.set("limit", String(limit));
    return requestJson<UserAnalyticsSummary>(this.endpoint, `/v1/desktop/analytics/summary?${params.toString()}`, {
      token: controlOrApiToken(this)
    });
  }

  userDataExport(userId: string, limit = 500): Promise<UserDataExport> {
    return requestJson<UserDataExport>(
      this.endpoint,
      `/v1/desktop/users/${encodeURIComponent(userId)}/export?limit=${encodeURIComponent(String(limit))}`,
      { token: controlOrApiToken(this) }
    );
  }

  userDataDelete(userId: string, body: { dry_run?: boolean; hard_delete?: boolean; include_conversations?: boolean; include_audit?: boolean; reason?: string } = {}): Promise<UserDataDeleteResult> {
    return requestJson<UserDataDeleteResult>(
      this.endpoint,
      `/v1/desktop/users/${encodeURIComponent(userId)}/delete`,
      {
        method: "POST",
        token: this.apiToken,
        body
      }
    );
  }

  retentionSweep(body: { user_id?: string; dry_run?: boolean } = { dry_run: true }): Promise<RetentionSweepResult> {
    return requestJson<RetentionSweepResult>(
      this.endpoint,
      "/v1/desktop/retention/sweep",
      {
        method: "POST",
        token: this.controlToken,
        body
      }
    );
  }

  userLearningDataset(userId: string, limit = 100): Promise<UserLearningDataset> {
    return requestJson<UserLearningDataset>(
      this.endpoint,
      `/v1/desktop/users/${encodeURIComponent(userId)}/learning-dataset?limit=${encodeURIComponent(String(limit))}`,
      { token: controlOrApiToken(this) }
    );
  }

  userRecommendations(userId: string, limit = 5): Promise<WorkflowRecommendationPayload> {
    return requestJson<WorkflowRecommendationPayload>(
      this.endpoint,
      `/v1/desktop/users/${encodeURIComponent(userId)}/recommendations?limit=${encodeURIComponent(String(limit))}`,
      { token: controlOrApiToken(this) }
    );
  }

  userDataPolicyGet(userId: string): Promise<{ object: string; data: UserDataPolicy }> {
    return requestJson<{ object: string; data: UserDataPolicy }>(
      this.endpoint,
      `/v1/desktop/users/${encodeURIComponent(userId)}/data-policy`,
      { token: controlOrApiToken(this) }
    );
  }

  userDataPolicySave(userId: string, patch: Partial<UserDataPolicy>): Promise<{ object: string; data: UserDataPolicy }> {
    return requestJson<{ object: string; data: UserDataPolicy }>(
      this.endpoint,
      `/v1/desktop/users/${encodeURIComponent(userId)}/data-policy`,
      {
        method: "PATCH",
        token: this.apiToken,
        body: patch
      }
    );
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

  jobRuns(jobId: string, limit = 100): Promise<{ object: string; job_id: string; data: JobRunRecord[] }> {
    return requestJson<{ object: string; job_id: string; data: JobRunRecord[] }>(
      this.endpoint,
      `/v1/jobs/${encodeURIComponent(jobId)}/runs?limit=${encodeURIComponent(String(limit))}`,
      { token: this.apiToken }
    );
  }

  sessionsList(userId?: string, limit = 100, includeArchived = false): Promise<{ object: string; data: RecentSessionSummary[] }> {
    const params = new URLSearchParams();
    if (userId) params.set("user_id", userId);
    params.set("limit", String(limit));
    if (includeArchived) params.set("include_archived", "true");
    return requestJson<{ object: string; data: RecentSessionSummary[] }>(this.endpoint, `/v1/hermes/sessions?${params.toString()}`, {
      token: controlOrApiToken(this)
    });
  }

  handoffsList(filters: { userId?: string; sessionId?: string; status?: string; limit?: number; includeCompleted?: boolean } = {}): Promise<HandoffQueuePayload> {
    const params = new URLSearchParams();
    if (filters.userId) params.set("user_id", filters.userId);
    if (filters.sessionId) params.set("session_id", filters.sessionId);
    if (filters.status) params.set("status", filters.status);
    params.set("limit", String(filters.limit || 100));
    if (filters.includeCompleted) params.set("include_completed", "true");
    return requestJson<HandoffQueuePayload>(this.endpoint, `/v1/hermes/handoffs?${params.toString()}`, {
      token: controlOrApiToken(this)
    });
  }

  sessionResumeContext(sessionId: string): Promise<SessionResumeContextPayload> {
    return requestJson<SessionResumeContextPayload>(
      this.endpoint,
      `/v1/hermes/sessions/${encodeURIComponent(sessionId)}/resume-context`,
      { token: controlOrApiToken(this) }
    );
  }

  sessionMessages(sessionId: string, limit = 200): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
    return requestJson<{ object: string; data: Array<Record<string, unknown>> }>(
      this.endpoint,
      `/v1/sessions/${encodeURIComponent(sessionId)}/messages?limit=${encodeURIComponent(String(limit))}`,
      { token: this.apiToken }
    );
  }

  sessionUndo(sessionId: string, turns = 1, reason = "desktop session undo"): Promise<SessionUndoPayload> {
    return requestJson<SessionUndoPayload>(
      this.endpoint,
      `/v1/sessions/${encodeURIComponent(sessionId)}/undo`,
      { method: "POST", token: this.controlToken, body: { turns, reason } }
    );
  }

  sessionArchive(sessionId: string, archived = true, reason = "desktop session archive"): Promise<SessionArchivePayload> {
    return requestJson<SessionArchivePayload>(
      this.endpoint,
      `/v1/sessions/${encodeURIComponent(sessionId)}/archive`,
      { method: "POST", token: this.controlToken, body: { archived, reason } }
    );
  }

  search(query: string, body: { session_id?: string; user_id?: string; limit?: number; include_archived?: boolean } = {}): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
    const params = new URLSearchParams();
    params.set("query", query);
    if (body.session_id) params.set("session_id", body.session_id);
    if (body.user_id) params.set("user_id", body.user_id);
    if (body.limit) params.set("limit", String(body.limit));
    if (body.include_archived) params.set("include_archived", "true");
    return requestJson<{ object: string; data: Array<Record<string, unknown>> }>(this.endpoint, `/v1/search?${params.toString()}`, {
      token: this.apiToken
    });
  }

  skillInstall(body: Record<string, unknown>): Promise<unknown> {
    return requestJson(this.endpoint, "/v1/skills", { method: "POST", token: this.controlToken, body });
  }

  async skillsList(): Promise<CapabilityWorkbenchPayload["skills"]> {
    const payload = await requestJson<{ data: CapabilityWorkbenchPayload["skills"] }>(this.endpoint, "/v1/skills", {
      token: controlOrApiToken(this)
    });
    return payload.data;
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

  pluginUpsert(body: Record<string, unknown>): Promise<unknown> {
    return requestJson(this.endpoint, "/v1/plugins", {
      method: "POST",
      token: this.controlToken,
      body
    });
  }

  pluginToolTest(name: string, tool: string, body: Record<string, unknown> = {}): Promise<unknown> {
    return requestJson(this.endpoint, `/v1/plugins/${encodeURIComponent(name)}/tools/${encodeURIComponent(tool)}/test`, {
      method: "POST",
      token: this.controlToken,
      body
    });
  }

  pluginCommands(name: string): Promise<{ object: string; data: PluginCommand[] }> {
    return requestJson(this.endpoint, `/v1/plugins/${encodeURIComponent(name)}/commands`, { token: this.controlToken });
  }

  pluginCommandTest(name: string, command: string, body: Record<string, unknown> = {}): Promise<unknown> {
    return requestJson(this.endpoint, `/v1/plugins/${encodeURIComponent(name)}/commands/${encodeURIComponent(command)}/test`, {
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

  connectorsList(type?: string, category?: string): Promise<{ object: string; data: ConnectorDetail[] }> {
    const params = new URLSearchParams();
    if (type) params.set("type", type);
    if (category) params.set("category", category);
    const query = params.toString();
    return requestJson<{ object: string; data: ConnectorDetail[] }>(this.endpoint, `/v1/connectors${query ? `?${query}` : ""}`, {
      token: controlOrApiToken(this)
    });
  }

  connectorDetail(connectorType: string, name: string): Promise<{ object: string; data: ConnectorDetail }> {
    return requestJson<{ object: string; data: ConnectorDetail }>(
      this.endpoint,
      `/v1/connectors/${encodeURIComponent(connectorType)}/${encodeURIComponent(name)}`,
      { token: controlOrApiToken(this) }
    );
  }

  connectorTest(connectorType: string, name: string): Promise<{ object: string; data: ConnectorDetail }> {
    return requestJson<{ object: string; data: ConnectorDetail }>(
      this.endpoint,
      `/v1/connectors/${encodeURIComponent(connectorType)}/${encodeURIComponent(name)}/test`,
      { method: "POST", token: controlOrApiToken(this), body: {} }
    );
  }

  gatewayStatus(): Promise<{ object?: string; data?: unknown; [key: string]: unknown }> {
    return requestJson(this.endpoint, "/v1/gateway/status", { token: controlOrApiToken(this) });
  }

  gatewayDaemonStatus(): Promise<GatewayDaemonStatus> {
    return requestJson(this.endpoint, "/v1/gateway/daemon/status", { token: this.controlToken });
  }

  gatewayPlatforms(): Promise<{ object: string; data: GatewayPlatform[] }> {
    return requestJson(this.endpoint, "/v1/gateway/platforms", { token: controlOrApiToken(this) });
  }

  gatewayMessages(platform?: string, limit = 100): Promise<{ object: string; data: GatewayMessage[] }> {
    const params = new URLSearchParams();
    if (platform) params.set("platform", platform);
    params.set("limit", String(limit));
    return requestJson(this.endpoint, `/v1/gateway/messages?${params.toString()}`, { token: controlOrApiToken(this) });
  }

  gatewayDirectory(platform?: string, kind?: string, limit = 200): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
    const params = new URLSearchParams();
    if (platform) params.set("platform", platform);
    if (kind) params.set("kind", kind);
    params.set("limit", String(limit));
    return requestJson(this.endpoint, `/v1/gateway/directory?${params.toString()}`, { token: controlOrApiToken(this) });
  }

  gatewayDirectoryRefresh(): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, "/v1/gateway/directory/refresh", { method: "POST", token: controlOrApiToken(this), body: {} });
  }

  gatewayMessageRetry(messageId: string): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, `/v1/gateway/messages/${encodeURIComponent(messageId)}/retry`, {
      method: "POST",
      token: this.controlToken,
      body: {}
    });
  }

  gatewayPlatformStart(platform: string): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, `/v1/gateway/platforms/${encodeURIComponent(platform)}/start`, { method: "POST", token: controlOrApiToken(this), body: {} });
  }

  gatewayPlatformStop(platform: string): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, `/v1/gateway/platforms/${encodeURIComponent(platform)}/stop`, { method: "POST", token: controlOrApiToken(this), body: {} });
  }

  gatewayPlatformHealth(platform: string): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, `/v1/gateway/platforms/${encodeURIComponent(platform)}/health`, { token: controlOrApiToken(this) });
  }

  gatewaySendIntent(payload: Record<string, unknown>, direct = false): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent(direct ? "gateway.direct_deliver" : "gateway.send_message", payload, "Desktop gateway message preview + approval.");
  }

  webhooksList(): Promise<{ object: string; data: WebhookSubscription[] }> {
    return requestJson(this.endpoint, "/v1/webhooks", { token: controlOrApiToken(this) });
  }

  webhookCreate(body: Record<string, unknown>): Promise<unknown> {
    return requestJson(this.endpoint, "/v1/webhooks", { method: "POST", token: this.controlToken, body });
  }

  webhookDelete(webhookId: string): Promise<unknown> {
    return requestJson(this.endpoint, `/v1/webhooks/${encodeURIComponent(webhookId)}`, { method: "DELETE", token: this.controlToken });
  }

  webhookTriggerIntent(webhookId: string, body: Record<string, unknown>): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent("webhook.trigger", { webhook_id: webhookId, ...body }, "Desktop webhook trigger preview + approval.");
  }

  approvalsList(status?: string, limit = 100): Promise<{ object: string; data: ApprovalItem[] }> {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    params.set("limit", String(limit));
    return requestJson(this.endpoint, `/v1/approvals?${params.toString()}`, { token: controlOrApiToken(this) });
  }

  approvalDecide(approvalId: string, decision: "approve" | "deny", reason = "desktop_decision"): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, `/v1/approvals/${encodeURIComponent(approvalId)}/${decision}`, {
      method: "POST",
      token: this.controlToken,
      body: { reason }
    });
  }

  learningStatus(): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, "/v1/learning/status", { token: controlOrApiToken(this) });
  }

  learningReview(status?: string, limit = 100): Promise<{ object: string; data: LearningProposal[] }> {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    params.set("limit", String(limit));
    return requestJson(this.endpoint, `/v1/learning/review?${params.toString()}`, { token: controlOrApiToken(this) });
  }

  learningApply(proposalId: string): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, "/v1/learning/apply", {
      method: "POST",
      token: this.controlToken,
      body: { proposal_id: proposalId }
    });
  }

  rlEnvironments(): Promise<{ object: string; data: unknown }> {
    return requestJson(this.endpoint, "/v1/rl/environments", { token: controlOrApiToken(this) });
  }

  rlConfig(): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, "/v1/rl/config", { token: controlOrApiToken(this) });
  }

  rlConfigUpdate(config: Record<string, unknown>): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, "/v1/rl/config", { method: "PATCH", token: this.controlToken, body: { config } });
  }

  rlRuns(limit = 100): Promise<{ object: string; data: RlRun[] }> {
    return requestJson(this.endpoint, `/v1/rl/runs?limit=${encodeURIComponent(String(limit))}`, { token: controlOrApiToken(this) });
  }

  rlRunStart(environment?: string, config: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, "/v1/rl/runs", { method: "POST", token: this.controlToken, body: { environment, config } });
  }

  rlRunStop(runId: string): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, `/v1/rl/runs/${encodeURIComponent(runId)}/stop`, { method: "POST", token: this.controlToken, body: {} });
  }

  rlRunGet(runId: string): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, `/v1/rl/runs/${encodeURIComponent(runId)}`, { token: controlOrApiToken(this) });
  }

  rlRunResults(runId: string): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, `/v1/rl/runs/${encodeURIComponent(runId)}/results`, { token: controlOrApiToken(this) });
  }

  rlRunLogs(runId: string): Promise<Record<string, unknown>> {
    return requestJson(this.endpoint, `/v1/rl/runs/${encodeURIComponent(runId)}/logs`, { token: controlOrApiToken(this) });
  }

  terminalBackends(): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
    return requestJson<{ object: string; data: Array<Record<string, unknown>> }>(
      this.endpoint,
      "/v1/terminal/backends",
      { token: this.controlToken }
    );
  }

  terminalBackendSessions(name: string, limit = 200): Promise<{ object: string; backend: string; data: Array<Record<string, unknown>> }> {
    return requestJson<{ object: string; backend: string; data: Array<Record<string, unknown>> }>(
      this.endpoint,
      `/v1/terminal/backends/${encodeURIComponent(name)}/sessions?limit=${encodeURIComponent(String(limit))}`,
      { token: this.controlToken }
    );
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

  quantResearchGet(researchId: string): Promise<{ object?: string; research?: QuantResearchRun; data?: { research?: QuantResearchRun } }> {
    return requestJson<{ object?: string; research?: QuantResearchRun; data?: { research?: QuantResearchRun } }>(
      this.endpoint,
      `/v1/desktop/quant/research-runs/${encodeURIComponent(researchId)}`,
      { token: this.apiToken }
    );
  }

  quantResearchReport(researchId: string): Promise<QuantResearchReport> {
    return requestJson<QuantResearchReport>(
      this.endpoint,
      `/v1/desktop/quant/research-runs/${encodeURIComponent(researchId)}/report`,
      { token: this.apiToken }
    );
  }

  financialManagerCatalog(): Promise<FinancialManagerCatalog> {
    return requestJson<FinancialManagerCatalog>(this.endpoint, "/v1/desktop/financial-manager/catalog", { token: controlOrApiToken(this) });
  }

  financialManagerStatus(): Promise<FinancialManagerStatus> {
    return requestJson<FinancialManagerStatus>(this.endpoint, "/v1/desktop/financial-manager/status", { token: controlOrApiToken(this) });
  }

  financialManagerQuery(body: {
    capability_id: string;
    action_id: string;
    params?: Record<string, unknown>;
  }): Promise<FinancialManagerQueryResult> {
    return requestJson<FinancialManagerQueryResult>(this.endpoint, "/v1/desktop/financial-manager/query", {
      method: "POST",
      token: controlOrApiToken(this),
      body
    });
  }

  financialManagerIntent(body: {
    capability_id: string;
    action_id: string;
    params?: Record<string, unknown>;
    rationale?: string;
    user_id?: string;
  }): Promise<FinancialManagerIntentResult> {
    return requestJson<FinancialManagerIntentResult>(this.endpoint, "/v1/desktop/financial-manager/intent", {
      method: "POST",
      token: this.controlToken,
      body
    });
  }

  brokerReadiness(): Promise<BrokerReadinessPayload> {
    return requestJson<BrokerReadinessPayload>(this.endpoint, "/v1/desktop/broker-readiness", {
      token: controlOrApiToken(this)
    });
  }

  brokerSync(body: {
    provider?: string;
    consent: boolean;
    user_id?: string;
    session_id?: string;
    run_id?: string;
    trace_id?: string;
  }): Promise<BrokerSyncPayload> {
    return requestJson<BrokerSyncPayload>(this.endpoint, "/v1/desktop/broker/sync", {
      method: "POST",
      token: controlOrApiToken(this),
      body
    });
  }

  brokerAccounts(userId?: string, provider?: string): Promise<BrokerSnapshotPayload> {
    const params = new URLSearchParams();
    if (userId) params.set("user_id", userId);
    if (provider) params.set("provider", provider);
    const query = params.toString();
    return requestJson<BrokerSnapshotPayload>(
      this.endpoint,
      `/v1/desktop/broker/accounts${query ? `?${query}` : ""}`,
      { token: controlOrApiToken(this) }
    );
  }

  brokerPositions(userId?: string, provider?: string): Promise<BrokerSnapshotPayload> {
    const params = new URLSearchParams();
    if (userId) params.set("user_id", userId);
    if (provider) params.set("provider", provider);
    const query = params.toString();
    return requestJson<BrokerSnapshotPayload>(
      this.endpoint,
      `/v1/desktop/broker/positions${query ? `?${query}` : ""}`,
      { token: controlOrApiToken(this) }
    );
  }

  brokerOrders(userId?: string, provider?: string): Promise<BrokerSnapshotPayload> {
    const params = new URLSearchParams();
    if (userId) params.set("user_id", userId);
    if (provider) params.set("provider", provider);
    const query = params.toString();
    return requestJson<BrokerSnapshotPayload>(
      this.endpoint,
      `/v1/desktop/broker/orders${query ? `?${query}` : ""}`,
      { token: controlOrApiToken(this) }
    );
  }

  brokerAnalyticsRun(body: {
    user_id?: string;
    provider?: string;
    broker_profile_id?: string;
    period_start?: string;
    period_end?: string;
  } = {}): Promise<BrokerAnalyticsPayload> {
    return requestJson<BrokerAnalyticsPayload>(this.endpoint, "/v1/desktop/broker/analytics/run", {
      method: "POST",
      token: controlOrApiToken(this),
      body
    });
  }

  brokerAnalyticsLatest(userId?: string, provider?: string): Promise<BrokerAnalyticsPayload> {
    const params = new URLSearchParams();
    if (userId) params.set("user_id", userId);
    if (provider) params.set("provider", provider);
    const query = params.toString();
    return requestJson<BrokerAnalyticsPayload>(
      this.endpoint,
      `/v1/desktop/broker/analytics/latest${query ? `?${query}` : ""}`,
      { token: controlOrApiToken(this) }
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
