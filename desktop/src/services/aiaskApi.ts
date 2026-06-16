import { requestJson } from "../api";
import {
  aiConfig as requestAiConfig,
  aiConfigSave as requestAiConfigSave,
  aiModels as requestAiModels,
  aiSmoke as requestAiSmoke,
  aiStatus as requestAiStatus,
  response as requestResponse,
  responseDelete as requestResponseDelete,
  responseGet as requestResponseGet
} from "./api/ai";
import { AiaskApiCore, controlOrApiToken } from "./api/core";
import type { AiaskClientOptions } from "./api/core";
import { fullConsoleSnapshot as requestFullConsoleSnapshot } from "./api/fullConsole";
import {
  approvalDecide as requestApprovalDecide,
  approvalsList as requestApprovalsList,
  confirmIntent as requestConfirmIntent,
  createActionIntent as requestCreateActionIntent,
  denyIntent as requestDenyIntent,
  getIntent as requestGetIntent,
  intentsList as requestIntentsList,
  readOnlyTool as requestReadOnlyTool
} from "./api/intents";
import {
  connectorDetail as requestConnectorDetail,
  connectorsList as requestConnectorsList,
  connectorsSummary as requestConnectorsSummary,
  connectorTest as requestConnectorTest,
  gatewayDaemonStatus as requestGatewayDaemonStatus,
  gatewayDirectory as requestGatewayDirectory,
  gatewayDirectoryRefresh as requestGatewayDirectoryRefresh,
  gatewayMessageRetry as requestGatewayMessageRetry,
  gatewayMessages as requestGatewayMessages,
  gatewayPlatformHealth as requestGatewayPlatformHealth,
  gatewayPlatforms as requestGatewayPlatforms,
  gatewayPlatformStart as requestGatewayPlatformStart,
  gatewayPlatformStop as requestGatewayPlatformStop,
  gatewayStatus as requestGatewayStatus,
  mcpDiscover as requestMcpDiscover,
  mcpOauthStart as requestMcpOauthStart,
  mcpPromptGet as requestMcpPromptGet,
  mcpRegisterLocal as requestMcpRegisterLocal,
  mcpResourceRead as requestMcpResourceRead,
  webhookCreate as requestWebhookCreate,
  webhookDelete as requestWebhookDelete,
  webhooksList as requestWebhooksList
} from "./api/integrations";
import {
  dataStatus as requestDataStatus,
  dataSyncPlan as requestDataSyncPlan,
  localProfileGet as requestLocalProfileGet,
  localProfileSave as requestLocalProfileSave,
  memoryStatus as requestMemoryStatus,
  modelProviderStatus as requestModelProviderStatus,
  recordEvents as requestRecordEvents,
  recordFeedback as requestRecordFeedback,
  retentionSweep as requestRetentionSweep,
  settingsStatus as requestSettingsStatus,
  stockDataSourceSave as requestStockDataSourceSave,
  stockDataSources as requestStockDataSources,
  stockDataSourceTest as requestStockDataSourceTest,
  userActivity as requestUserActivity,
  userAnalyticsSummary as requestUserAnalyticsSummary,
  userDataDelete as requestUserDataDelete,
  userDataExport as requestUserDataExport,
  userDataPolicyGet as requestUserDataPolicyGet,
  userDataPolicySave as requestUserDataPolicySave,
  userLearningDataset as requestUserLearningDataset,
  userRecommendations as requestUserRecommendations
} from "./api/desktopState";
import {
  brokerAccounts as requestBrokerAccounts,
  brokerAnalyticsLatest as requestBrokerAnalyticsLatest,
  brokerAnalyticsRun as requestBrokerAnalyticsRun,
  brokerOrders as requestBrokerOrders,
  brokerPositions as requestBrokerPositions,
  brokerReadiness as requestBrokerReadiness,
  brokerSync as requestBrokerSync,
  factorFactoryMaintenanceIntent as requestFactorFactoryMaintenanceIntent,
  factorFactoryRunIntent as requestFactorFactoryRunIntent,
  factorFactoryStatus as requestFactorFactoryStatus,
  factoryEventApproveIntent as requestFactoryEventApproveIntent,
  factoryEventBootstrapIntent as requestFactoryEventBootstrapIntent,
  factoryEventCreateIntent as requestFactoryEventCreateIntent,
  factoryEventOutboxDrainIntent as requestFactoryEventOutboxDrainIntent,
  factoryEventRecordOutcomeIntent as requestFactoryEventRecordOutcomeIntent,
  factoryEventUpdateIntent as requestFactoryEventUpdateIntent,
  factoryThemeExposureRefreshIntent as requestFactoryThemeExposureRefreshIntent,
  factoryThemeRegressionRunIntent as requestFactoryThemeRegressionRunIntent,
  financialManagerCatalog as requestFinancialManagerCatalog,
  financialManagerIntent as requestFinancialManagerIntent,
  financialManagerQuery as requestFinancialManagerQuery,
  financialManagerStatus as requestFinancialManagerStatus,
  quantPresets as requestQuantPresets,
  quantResearchGet as requestQuantResearchGet,
  quantResearchReport as requestQuantResearchReport,
  quantResearchRun as requestQuantResearchRun,
  stockRadarCandidates as requestStockRadarCandidates,
  stockRadarDigest as requestStockRadarDigest,
  stockRadarPushDigestIntent as requestStockRadarPushDigestIntent,
  stockRadarRunIntent as requestStockRadarRunIntent,
  stockRadarScheduleUpdateIntent as requestStockRadarScheduleUpdateIntent,
  stockRadarStatus as requestStockRadarStatus,
  tradePredictionMatrix as requestTradePredictionMatrix,
  tradePredictionOutcomes as requestTradePredictionOutcomes,
  tradePredictionStatus as requestTradePredictionStatus
} from "./api/finance";
import {
  jobCreate as requestJobCreate,
  jobDelete as requestJobDelete,
  jobRun as requestJobRun,
  jobRuns as requestJobRuns,
  jobsList as requestJobsList,
  jobUpdate as requestJobUpdate,
  learningApply as requestLearningApply,
  learningReview as requestLearningReview,
  learningStatus as requestLearningStatus,
  pluginCommandTest as requestPluginCommandTest,
  pluginCommands as requestPluginCommands,
  pluginToggle as requestPluginToggle,
  pluginToolTest as requestPluginToolTest,
  pluginUpsert as requestPluginUpsert,
  rlConfig as requestRlConfig,
  rlConfigUpdate as requestRlConfigUpdate,
  rlEnvironments as requestRlEnvironments,
  rlRunGet as requestRlRunGet,
  rlRunLogs as requestRlRunLogs,
  rlRunResults as requestRlRunResults,
  rlRuns as requestRlRuns,
  rlRunStart as requestRlRunStart,
  rlRunStop as requestRlRunStop,
  skillDelete as requestSkillDelete,
  skillInstall as requestSkillInstall,
  skillsList as requestSkillsList,
  skillUpdate as requestSkillUpdate
} from "./api/ops";
import {
  handoffsList as requestHandoffsList,
  runArtifacts as requestRunArtifacts,
  runCancel as requestRunCancel,
  runEvents as requestRunEvents,
  runGet as requestRunGet,
  runsList as requestRunsList,
  runSources as requestRunSources,
  runSteer as requestRunSteer,
  runStop as requestRunStop,
  runTraceEval as requestRunTraceEval,
  sessionArchive as requestSessionArchive,
  sessionArtifacts as requestSessionArtifacts,
  sessionMessages as requestSessionMessages,
  sessionResumeContext as requestSessionResumeContext,
  search as requestSearch,
  sessionsList as requestSessionsList,
  sessionSources as requestSessionSources,
  sessionUndo as requestSessionUndo,
  workbenchSummary as requestWorkbenchSummary
} from "./api/workbench";
import type {
  AgentArtifactRecord,
  AgentSourceRecord,
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

export type { AiaskClientOptions } from "./api/core";

export class AiaskApi extends AiaskApiCore {

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

  async fullConsoleSnapshot(): Promise<HermesConsoleSnapshot> {
    return requestFullConsoleSnapshot(this);
  }

  aiStatus() {
    return requestAiStatus(this);
  }

  aiSmoke(prompt?: string, model?: string) {
    return requestAiSmoke(this, prompt, model);
  }

  aiModels() {
    return requestAiModels(this);
  }

  aiConfig() {
    return requestAiConfig(this);
  }

  aiConfigSave(body: Parameters<typeof requestAiConfigSave>[1]) {
    return requestAiConfigSave(this, body);
  }

  response(body: Record<string, unknown>, token?: string) {
    return requestResponse(this, body, token);
  }

  responseGet(responseId: string) {
    return requestResponseGet(this, responseId);
  }

  responseDelete(responseId: string) {
    return requestResponseDelete(this, responseId);
  }

  runGet(runId: string): Promise<RunRecord> {
    return requestRunGet(this, runId);
  }

  runTraceEval(runId: string): Promise<RunTraceEvalPayload> {
    return requestRunTraceEval(this, runId);
  }

  runArtifacts(runId: string, filters: { kind?: string; limit?: number } = {}): Promise<{ object: string; run_id: string; data: AgentArtifactRecord[] }> {
    return requestRunArtifacts(this, runId, filters);
  }

  runSources(runId: string, filters: { source_type?: string; limit?: number } = {}): Promise<{ object: string; run_id: string; data: AgentSourceRecord[] }> {
    return requestRunSources(this, runId, filters);
  }

  sessionArtifacts(sessionId: string, filters: { kind?: string; limit?: number } = {}): Promise<{ object: string; session_id: string; data: AgentArtifactRecord[] }> {
    return requestSessionArtifacts(this, sessionId, filters);
  }

  sessionSources(sessionId: string, filters: { source_type?: string; limit?: number } = {}): Promise<{ object: string; session_id: string; data: AgentSourceRecord[] }> {
    return requestSessionSources(this, sessionId, filters);
  }

  runCancel(runId: string): Promise<Record<string, unknown>> {
    return requestRunCancel(this, runId);
  }

  runStop(runId: string): Promise<Record<string, unknown>> {
    return requestRunStop(this, runId);
  }

  runSteer(runId: string, instruction: string): Promise<Record<string, unknown>> {
    return requestRunSteer(this, runId, instruction);
  }

  workbenchSummary(): Promise<DesktopWorkbenchSummary> {
    return requestWorkbenchSummary(this);
  }

  runsList(filters: { session_id?: string; status?: string; limit?: number } = {}): Promise<{ object: string; data: DesktopRunSummary[] }> {
    return requestRunsList(this, filters);
  }

  async runEvents(runId: string, token?: string): Promise<NormalizedRunEvent[]> {
    return requestRunEvents(this, runId, token);
  }

  callTool<T = unknown>(tool: string, body: Record<string, unknown>, token?: string): Promise<ToolEnvelope & { data: T }> {
    return requestJson<ToolEnvelope & { data: T }>(this.endpoint, `/v1/tools/${tool}`, {
      method: "POST",
      token: token ?? this.apiToken,
      body
    });
  }

  readOnlyTool<T = unknown>(tool: string, body: Record<string, unknown>): Promise<ToolEnvelope & { data: T }> {
    return requestReadOnlyTool<T>(this, tool, body);
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
    return requestStockRadarStatus(this, filters);
  }

  stockRadarCandidates(filters: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestStockRadarCandidates(this, filters);
  }

  stockRadarDigest(filters: Record<string, unknown> = {}): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestStockRadarDigest(this, filters);
  }

  stockRadarRunIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestStockRadarRunIntent(this, params, rationale);
  }

  stockRadarPushDigestIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestStockRadarPushDigestIntent(this, params, rationale);
  }

  stockRadarScheduleUpdateIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestStockRadarScheduleUpdateIntent(this, params, rationale);
  }

  // Write actions go through the ActionIntent chain enforced by PR-F:
  //   POST /intents (create) → POST /intents/{id}/confirm → adapter.
  // Desktop never touches ``ACTION_HANDLERS`` directly; it stays on
  // the read-only MCP tool surface for previews and on the intent
  // surface for writes.
  factoryEventCreateIntent(payload: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestFactoryEventCreateIntent(this, payload, rationale);
  }

  factoryEventApproveIntent(eventId: string, approverId: string, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestFactoryEventApproveIntent(this, eventId, approverId, rationale);
  }

  factoryEventUpdateIntent(eventId: string, updates: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestFactoryEventUpdateIntent(this, eventId, updates, rationale);
  }

  factoryEventRecordOutcomeIntent(eventId: string, outcome: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestFactoryEventRecordOutcomeIntent(this, eventId, outcome, rationale);
  }

  factoryEventBootstrapIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestFactoryEventBootstrapIntent(this, params, rationale);
  }

  factoryThemeExposureRefreshIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestFactoryThemeExposureRefreshIntent(this, params, rationale);
  }

  factoryEventOutboxDrainIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestFactoryEventOutboxDrainIntent(this, params, rationale);
  }

  factoryThemeRegressionRunIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestFactoryThemeRegressionRunIntent(this, params, rationale);
  }

  confirmIntent(intentId: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestConfirmIntent(this, intentId);
  }

  denyIntent(intentId: string, reason?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestDenyIntent(this, intentId, reason);
  }

  intentsList(status?: string, limit = 100): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
    return requestIntentsList(this, status, limit);
  }

  incubationFactoryStatus(): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.readOnlyTool<Record<string, unknown>>("agent_incubation_factory_status", {});
  }

  tradePredictionStatus(filters: { strategy_id?: string; stock_code?: string; limit?: number } = {}): Promise<ToolEnvelope & { data: TradePredictionStatus }> {
    return requestTradePredictionStatus(this, filters);
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
    return requestTradePredictionOutcomes(this, filters);
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
    return requestTradePredictionMatrix(this, filters);
  }

  createActionIntent(action: string, params: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestCreateActionIntent(this, action, params, rationale);
  }

  getIntent(intentId: string): Promise<ToolEnvelope> {
    return requestGetIntent(this, intentId);
  }

  factoryIntentCreate(action: string, params: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent(action, params, rationale);
  }

  settingsStatus(): Promise<DesktopSettingsStatus> {
    return requestSettingsStatus(this);
  }

  modelProviderStatus(): Promise<unknown> {
    return requestModelProviderStatus(this);
  }

  memoryStatus(): Promise<unknown> {
    return requestMemoryStatus(this);
  }

  memorySearch(body: Record<string, unknown>): Promise<ToolEnvelope & { data: unknown }> {
    return this.readOnlyTool("agent_memory_search", body);
  }

  dataStatus(body: { codes?: string[]; max_stale_days?: number } = {}): Promise<DesktopDataStatus> {
    return requestDataStatus(this, body);
  }

  dataGate(body: Record<string, unknown>): Promise<ToolEnvelope & { data: unknown }> {
    return this.readOnlyTool("agent_quant_data_gate", body);
  }

  dataSyncPlan(body: Record<string, unknown>): Promise<DesktopDataSyncPlan> {
    return requestDataSyncPlan(this, body);
  }

  stockDataSources(): Promise<StockDataSourcesStatus> {
    return requestStockDataSources(this);
  }

  stockDataSourceSave(body: StockDataSourceConfig): Promise<{ object: string; source: StockDataSourceConfig; secrets_redacted?: boolean }> {
    return requestStockDataSourceSave(this, body);
  }

  stockDataSourceTest(body: Record<string, unknown>): Promise<StockDataSourceTestResult> {
    return requestStockDataSourceTest(this, body);
  }

  localProfileGet(): Promise<LocalProfile> {
    return requestLocalProfileGet(this);
  }

  localProfileSave(body: Pick<LocalProfile, "user_id" | "profile_name">): Promise<LocalProfile> {
    return requestLocalProfileSave(this, body);
  }

  recordEvents(events: UserActivityEvent | UserActivityEvent[]): Promise<{ object: string; data: UserActivityEvent[]; count: number; secrets_redacted?: boolean }> {
    return requestRecordEvents(this, events);
  }

  recordFeedback(body: FeedbackEvent): Promise<{ object: string; data: FeedbackEvent; secrets_redacted?: boolean }> {
    return requestRecordFeedback(this, body);
  }

  userActivity(userId: string, limit = 20): Promise<UserActivityPayload> {
    return requestUserActivity(this, userId, limit);
  }

  userAnalyticsSummary(userId?: string, limit = 20): Promise<UserAnalyticsSummary> {
    return requestUserAnalyticsSummary(this, userId, limit);
  }

  userDataExport(userId: string, limit = 500): Promise<UserDataExport> {
    return requestUserDataExport(this, userId, limit);
  }

  userDataDelete(userId: string, body: { dry_run?: boolean; hard_delete?: boolean; include_conversations?: boolean; include_audit?: boolean; reason?: string } = {}): Promise<UserDataDeleteResult> {
    return requestUserDataDelete(this, userId, body);
  }

  retentionSweep(body: { user_id?: string; dry_run?: boolean } = { dry_run: true }): Promise<RetentionSweepResult> {
    return requestRetentionSweep(this, body);
  }

  userLearningDataset(userId: string, limit = 100): Promise<UserLearningDataset> {
    return requestUserLearningDataset(this, userId, limit);
  }

  userRecommendations(userId: string, limit = 5): Promise<WorkflowRecommendationPayload> {
    return requestUserRecommendations(this, userId, limit);
  }

  userDataPolicyGet(userId: string): Promise<{ object: string; data: UserDataPolicy }> {
    return requestUserDataPolicyGet(this, userId);
  }

  userDataPolicySave(userId: string, patch: Partial<UserDataPolicy>): Promise<{ object: string; data: UserDataPolicy }> {
    return requestUserDataPolicySave(this, userId, patch);
  }

  factorFactoryStatus(limit = 50): Promise<FactorFactoryStatus> {
    return requestFactorFactoryStatus(this, limit);
  }

  factorFactoryRunIntent(params: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestFactorFactoryRunIntent(this, params, rationale);
  }

  factorFactoryMaintenanceIntent(params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestFactorFactoryMaintenanceIntent(this, params, rationale);
  }

  jobsList(): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
    return requestJobsList(this);
  }

  jobCreate(body: Record<string, unknown>): Promise<Record<string, unknown>> {
    return requestJobCreate(this, body);
  }

  jobsCreate(body: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.jobCreate(body);
  }

  jobUpdate(jobId: string, body: Record<string, unknown>): Promise<Record<string, unknown>> {
    return requestJobUpdate(this, jobId, body);
  }

  jobsUpdate(jobId: string, body: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.jobUpdate(jobId, body);
  }

  jobDelete(jobId: string): Promise<Record<string, unknown>> {
    return requestJobDelete(this, jobId);
  }

  jobsDelete(jobId: string): Promise<Record<string, unknown>> {
    return this.jobDelete(jobId);
  }

  jobRun(jobId: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return requestJobRun(this, jobId);
  }

  jobsRun(jobId: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.jobRun(jobId);
  }

  jobRuns(jobId: string, limit = 100): Promise<{ object: string; job_id: string; data: JobRunRecord[] }> {
    return requestJobRuns(this, jobId, limit);
  }

  sessionsList(userId?: string, limit = 100, includeArchived = false): Promise<{ object: string; data: RecentSessionSummary[] }> {
    return requestSessionsList(this, userId, limit, includeArchived);
  }

  handoffsList(filters: { userId?: string; sessionId?: string; status?: string; limit?: number; includeCompleted?: boolean } = {}): Promise<HandoffQueuePayload> {
    return requestHandoffsList(this, filters);
  }

  sessionResumeContext(sessionId: string): Promise<SessionResumeContextPayload> {
    return requestSessionResumeContext(this, sessionId);
  }

  sessionMessages(sessionId: string, limit = 200): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
    return requestSessionMessages(this, sessionId, limit);
  }

  sessionUndo(sessionId: string, turns = 1, reason = "desktop session undo"): Promise<SessionUndoPayload> {
    return requestSessionUndo(this, sessionId, turns, reason);
  }

  sessionArchive(sessionId: string, archived = true, reason = "desktop session archive"): Promise<SessionArchivePayload> {
    return requestSessionArchive(this, sessionId, archived, reason);
  }

  search(query: string, body: { session_id?: string; user_id?: string; limit?: number; include_archived?: boolean } = {}): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
    return requestSearch(this, query, body);
  }

  skillInstall(body: Record<string, unknown>): Promise<unknown> {
    return requestSkillInstall(this, body);
  }

  async skillsList(): Promise<CapabilityWorkbenchPayload["skills"]> {
    return requestSkillsList(this);
  }

  skillUpdate(name: string, body: Record<string, unknown>): Promise<unknown> {
    return requestSkillUpdate(this, name, body);
  }

  skillDelete(name: string): Promise<unknown> {
    return requestSkillDelete(this, name);
  }

  pluginToggle(name: string, enabled: boolean): Promise<unknown> {
    return requestPluginToggle(this, name, enabled);
  }

  pluginUpsert(body: Record<string, unknown>): Promise<unknown> {
    return requestPluginUpsert(this, body);
  }

  pluginToolTest(name: string, tool: string, body: Record<string, unknown> = {}): Promise<unknown> {
    return requestPluginToolTest(this, name, tool, body);
  }

  pluginCommands(name: string): Promise<{ object: string; data: PluginCommand[] }> {
    return requestPluginCommands(this, name);
  }

  pluginCommandTest(name: string, command: string, body: Record<string, unknown> = {}): Promise<unknown> {
    return requestPluginCommandTest(this, name, command, body);
  }

  connectorsSummary(): Promise<{ data: unknown; status?: string; error?: string }> {
    return requestConnectorsSummary(this);
  }

  connectorsList(type?: string, category?: string): Promise<{ object: string; data: ConnectorDetail[] }> {
    return requestConnectorsList(this, type, category);
  }

  connectorDetail(connectorType: string, name: string): Promise<{ object: string; data: ConnectorDetail }> {
    return requestConnectorDetail(this, connectorType, name);
  }

  connectorTest(connectorType: string, name: string): Promise<{ object: string; data: ConnectorDetail }> {
    return requestConnectorTest(this, connectorType, name);
  }

  gatewayStatus(): Promise<{ object?: string; data?: unknown; [key: string]: unknown }> {
    return requestGatewayStatus(this);
  }

  gatewayDaemonStatus(): Promise<GatewayDaemonStatus> {
    return requestGatewayDaemonStatus(this);
  }

  gatewayPlatforms(): Promise<{ object: string; data: GatewayPlatform[] }> {
    return requestGatewayPlatforms(this);
  }

  gatewayMessages(platform?: string, limit = 100): Promise<{ object: string; data: GatewayMessage[] }> {
    return requestGatewayMessages(this, platform, limit);
  }

  gatewayDirectory(platform?: string, kind?: string, limit = 200): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
    return requestGatewayDirectory(this, platform, kind, limit);
  }

  gatewayDirectoryRefresh(): Promise<Record<string, unknown>> {
    return requestGatewayDirectoryRefresh(this);
  }

  gatewayMessageRetry(messageId: string): Promise<Record<string, unknown>> {
    return requestGatewayMessageRetry(this, messageId);
  }

  gatewayPlatformStart(platform: string): Promise<Record<string, unknown>> {
    return requestGatewayPlatformStart(this, platform);
  }

  gatewayPlatformStop(platform: string): Promise<Record<string, unknown>> {
    return requestGatewayPlatformStop(this, platform);
  }

  gatewayPlatformHealth(platform: string): Promise<Record<string, unknown>> {
    return requestGatewayPlatformHealth(this, platform);
  }

  gatewaySendIntent(payload: Record<string, unknown>, direct = false): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent(direct ? "gateway.direct_deliver" : "gateway.send_message", payload, "Desktop gateway message preview + approval.");
  }

  webhooksList(): Promise<{ object: string; data: WebhookSubscription[] }> {
    return requestWebhooksList(this);
  }

  webhookCreate(body: Record<string, unknown>): Promise<unknown> {
    return requestWebhookCreate(this, body);
  }

  webhookDelete(webhookId: string): Promise<unknown> {
    return requestWebhookDelete(this, webhookId);
  }

  webhookTriggerIntent(webhookId: string, body: Record<string, unknown>): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
    return this.createActionIntent("webhook.trigger", { webhook_id: webhookId, ...body }, "Desktop webhook trigger preview + approval.");
  }

  approvalsList(status?: string, limit = 100): Promise<{ object: string; data: ApprovalItem[] }> {
    return requestApprovalsList(this, status, limit);
  }

  approvalDecide(approvalId: string, decision: "approve" | "deny", reason = "desktop_decision"): Promise<Record<string, unknown>> {
    return requestApprovalDecide(this, approvalId, decision, reason);
  }

  learningStatus(): Promise<Record<string, unknown>> {
    return requestLearningStatus(this);
  }

  learningReview(status?: string, limit = 100): Promise<{ object: string; data: LearningProposal[] }> {
    return requestLearningReview(this, status, limit);
  }

  learningApply(proposalId: string): Promise<Record<string, unknown>> {
    return requestLearningApply(this, proposalId);
  }

  rlEnvironments(): Promise<{ object: string; data: unknown }> {
    return requestRlEnvironments(this);
  }

  rlConfig(): Promise<Record<string, unknown>> {
    return requestRlConfig(this);
  }

  rlConfigUpdate(config: Record<string, unknown>): Promise<Record<string, unknown>> {
    return requestRlConfigUpdate(this, config);
  }

  rlRuns(limit = 100): Promise<{ object: string; data: RlRun[] }> {
    return requestRlRuns(this, limit);
  }

  rlRunStart(environment?: string, config: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    return requestRlRunStart(this, environment, config);
  }

  rlRunStop(runId: string): Promise<Record<string, unknown>> {
    return requestRlRunStop(this, runId);
  }

  rlRunGet(runId: string): Promise<Record<string, unknown>> {
    return requestRlRunGet(this, runId);
  }

  rlRunResults(runId: string): Promise<Record<string, unknown>> {
    return requestRlRunResults(this, runId);
  }

  rlRunLogs(runId: string): Promise<Record<string, unknown>> {
    return requestRlRunLogs(this, runId);
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
    return requestQuantPresets(this);
  }

  quantResearchRun(body: Record<string, unknown>): Promise<ToolEnvelope & { data: { research?: QuantResearchRun } }> {
    return requestQuantResearchRun(this, body);
  }

  quantResearchGet(researchId: string): Promise<{ object?: string; research?: QuantResearchRun; data?: { research?: QuantResearchRun } }> {
    return requestQuantResearchGet(this, researchId);
  }

  quantResearchReport(researchId: string): Promise<QuantResearchReport> {
    return requestQuantResearchReport(this, researchId);
  }

  financialManagerCatalog(): Promise<FinancialManagerCatalog> {
    return requestFinancialManagerCatalog(this);
  }

  financialManagerStatus(): Promise<FinancialManagerStatus> {
    return requestFinancialManagerStatus(this);
  }

  financialManagerQuery(body: {
    capability_id: string;
    action_id: string;
    params?: Record<string, unknown>;
  }): Promise<FinancialManagerQueryResult> {
    return requestFinancialManagerQuery(this, body);
  }

  financialManagerIntent(body: {
    capability_id: string;
    action_id: string;
    params?: Record<string, unknown>;
    rationale?: string;
    user_id?: string;
  }): Promise<FinancialManagerIntentResult> {
    return requestFinancialManagerIntent(this, body);
  }

  brokerReadiness(): Promise<BrokerReadinessPayload> {
    return requestBrokerReadiness(this);
  }

  brokerSync(body: {
    provider?: string;
    consent: boolean;
    user_id?: string;
    session_id?: string;
    run_id?: string;
    trace_id?: string;
  }): Promise<BrokerSyncPayload> {
    return requestBrokerSync(this, body);
  }

  brokerAccounts(userId?: string, provider?: string): Promise<BrokerSnapshotPayload> {
    return requestBrokerAccounts(this, userId, provider);
  }

  brokerPositions(userId?: string, provider?: string): Promise<BrokerSnapshotPayload> {
    return requestBrokerPositions(this, userId, provider);
  }

  brokerOrders(userId?: string, provider?: string): Promise<BrokerSnapshotPayload> {
    return requestBrokerOrders(this, userId, provider);
  }

  brokerAnalyticsRun(body: {
    user_id?: string;
    provider?: string;
    broker_profile_id?: string;
    period_start?: string;
    period_end?: string;
  } = {}): Promise<BrokerAnalyticsPayload> {
    return requestBrokerAnalyticsRun(this, body);
  }

  brokerAnalyticsLatest(userId?: string, provider?: string): Promise<BrokerAnalyticsPayload> {
    return requestBrokerAnalyticsLatest(this, userId, provider);
  }

  mcpRegisterLocal(body: Record<string, unknown> = {}): Promise<unknown> {
    return requestMcpRegisterLocal(this, body);
  }

  mcpDiscover(server: string): Promise<unknown> {
    return requestMcpDiscover(this, server);
  }

  mcpResourceRead(uri: string, server?: string): Promise<unknown> {
    return requestMcpResourceRead(this, uri, server);
  }

  mcpPromptGet(name: string, argumentsValue: Record<string, unknown> = {}, server?: string): Promise<unknown> {
    return requestMcpPromptGet(this, name, argumentsValue, server);
  }

  mcpOauthStart(server: string): Promise<unknown> {
    return requestMcpOauthStart(this, server);
  }
}
