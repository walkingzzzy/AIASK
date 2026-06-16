import { requestJson } from "../../api";
import type {
  BrokerAnalyticsPayload,
  BrokerReadinessPayload,
  BrokerSnapshotPayload,
  BrokerSyncPayload,
  FactorFactoryStatus,
  FinancialManagerCatalog,
  FinancialManagerIntentResult,
  FinancialManagerQueryResult,
  FinancialManagerStatus,
  QuantPresetPayload,
  QuantResearchReport,
  QuantResearchRun,
  ToolEnvelope,
  TradePredictionMatrix,
  TradePredictionOutcomes,
  TradePredictionStatus
} from "../../types";
import type { AiaskApiCore } from "./core";
import { controlOrApiToken } from "./core";
import { createActionIntent } from "./intents";

function queryFromRecord(filters: Record<string, unknown>, arrayMode: "join" | "string" = "string"): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, Array.isArray(value) && arrayMode === "join" ? value.join(",") : String(value));
  }
  return params.toString();
}

export function stockRadarStatus(
  client: AiaskApiCore,
  filters: Record<string, unknown> = {}
): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  const query = queryFromRecord(filters);
  return requestJson<ToolEnvelope & { data: Record<string, unknown> }>(
    client.endpoint,
    `/v1/desktop/stock-radar/status${query ? `?${query}` : ""}`,
    { token: client.apiToken }
  );
}

export function stockRadarCandidates(
  client: AiaskApiCore,
  filters: Record<string, unknown> = {}
): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  const query = queryFromRecord(filters);
  return requestJson<ToolEnvelope & { data: Record<string, unknown> }>(
    client.endpoint,
    `/v1/desktop/stock-radar/candidates${query ? `?${query}` : ""}`,
    { token: client.apiToken }
  );
}

export function stockRadarDigest(
  client: AiaskApiCore,
  filters: Record<string, unknown> = {}
): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  const query = queryFromRecord(filters, "join");
  return requestJson<ToolEnvelope & { data: Record<string, unknown> }>(
    client.endpoint,
    `/v1/desktop/stock-radar/digest${query ? `?${query}` : ""}`,
    { token: client.apiToken }
  );
}

export function stockRadarRunIntent(client: AiaskApiCore, params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return createActionIntent(client, "stock_radar.run_once", params, rationale || "Run AIASK stock radar once from Desktop.");
}

export function stockRadarPushDigestIntent(client: AiaskApiCore, params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return createActionIntent(client, "stock_radar.push_digest", params, rationale || "Create a stock radar digest delivery intent from Desktop.");
}

export function stockRadarScheduleUpdateIntent(client: AiaskApiCore, params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return createActionIntent(client, "stock_radar.schedule_update", params, rationale || "Update stock radar schedule from Desktop.");
}

export function factoryEventCreateIntent(client: AiaskApiCore, payload: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return createActionIntent(client, "strategy_manager.factory_event_create", payload, rationale);
}

export function factoryEventApproveIntent(client: AiaskApiCore, eventId: string, approverId: string, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return createActionIntent(client, "strategy_manager.factory_event_approve", { event_id: eventId, approver_id: approverId }, rationale);
}

export function factoryEventUpdateIntent(client: AiaskApiCore, eventId: string, updates: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return createActionIntent(client, "strategy_manager.factory_event_update", { event_id: eventId, ...updates }, rationale);
}

export function factoryEventRecordOutcomeIntent(client: AiaskApiCore, eventId: string, outcome: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return createActionIntent(client, "strategy_manager.factory_event_record_outcome", { event_id: eventId, ...outcome }, rationale);
}

export function factoryEventBootstrapIntent(client: AiaskApiCore, params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return createActionIntent(client, "strategy_manager.factory_event_bootstrap", params, rationale || "Bootstrap the default theme graph and refresh the exposure matrix from Desktop.");
}

export function factoryThemeExposureRefreshIntent(client: AiaskApiCore, params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return createActionIntent(client, "strategy_manager.factory_theme_exposure_refresh", params, rationale || "Refresh the TDX-only theme exposure matrix from Desktop.");
}

export function factoryEventOutboxDrainIntent(client: AiaskApiCore, params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return createActionIntent(client, "strategy_manager.factory_event_outbox_drain", params, rationale || "Drain event-driven task outbox from Desktop.");
}

export function factoryThemeRegressionRunIntent(client: AiaskApiCore, params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return createActionIntent(client, "strategy_manager.factory_theme_regression_run", params, rationale || "Run theme-response regression from Desktop.");
}

export function tradePredictionStatus(
  client: AiaskApiCore,
  filters: { strategy_id?: string; stock_code?: string; limit?: number } = {}
): Promise<ToolEnvelope & { data: TradePredictionStatus }> {
  const query = queryFromRecord(filters);
  return requestJson<ToolEnvelope & { data: TradePredictionStatus }>(
    client.endpoint,
    `/v1/desktop/trade-predictions/status${query ? `?${query}` : ""}`,
    { token: client.apiToken }
  );
}

export function tradePredictionOutcomes(
  client: AiaskApiCore,
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
  const query = queryFromRecord(filters);
  return requestJson<ToolEnvelope & { data: TradePredictionOutcomes }>(
    client.endpoint,
    `/v1/desktop/trade-predictions/outcomes${query ? `?${query}` : ""}`,
    { token: client.apiToken }
  );
}

export function tradePredictionMatrix(
  client: AiaskApiCore,
  filters: {
    strategy_id?: string;
    stock_code?: string;
    score_version?: string;
    dimensions?: string[];
    limit?: number;
  } = {}
): Promise<ToolEnvelope & { data: TradePredictionMatrix }> {
  const query = queryFromRecord(filters, "join");
  return requestJson<ToolEnvelope & { data: TradePredictionMatrix }>(
    client.endpoint,
    `/v1/desktop/trade-predictions/matrix${query ? `?${query}` : ""}`,
    { token: client.apiToken }
  );
}

export function factorFactoryStatus(client: AiaskApiCore, limit = 50): Promise<FactorFactoryStatus> {
  return requestJson<FactorFactoryStatus>(
    client.endpoint,
    `/v1/desktop/factor-factory/status?limit=${encodeURIComponent(String(limit))}`,
    { token: client.apiToken }
  );
}

export function factorFactoryRunIntent(client: AiaskApiCore, params: Record<string, unknown>, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return createActionIntent(client, "factor_factory.run_once", params, rationale || "Run Factor Mining Factory once from Desktop.");
}

export function factorFactoryMaintenanceIntent(client: AiaskApiCore, params: Record<string, unknown> = {}, rationale?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return createActionIntent(client, "factor_factory.maintenance", params, rationale || "Run Factor Mining Factory maintenance from Desktop.");
}

export function quantPresets(client: AiaskApiCore): Promise<QuantPresetPayload> {
  return requestJson<QuantPresetPayload>(client.endpoint, "/v1/desktop/quant/presets", { token: client.apiToken });
}

export function quantResearchRun(
  client: AiaskApiCore,
  body: Record<string, unknown>
): Promise<ToolEnvelope & { data: { research?: QuantResearchRun } }> {
  return requestJson<ToolEnvelope & { data: { research?: QuantResearchRun } }>(
    client.endpoint,
    "/v1/desktop/quant/research-runs",
    {
      method: "POST",
      token: client.apiToken,
      body
    }
  );
}

export function quantResearchGet(
  client: AiaskApiCore,
  researchId: string
): Promise<{ object?: string; research?: QuantResearchRun; data?: { research?: QuantResearchRun } }> {
  return requestJson<{ object?: string; research?: QuantResearchRun; data?: { research?: QuantResearchRun } }>(
    client.endpoint,
    `/v1/desktop/quant/research-runs/${encodeURIComponent(researchId)}`,
    { token: client.apiToken }
  );
}

export function quantResearchReport(client: AiaskApiCore, researchId: string): Promise<QuantResearchReport> {
  return requestJson<QuantResearchReport>(
    client.endpoint,
    `/v1/desktop/quant/research-runs/${encodeURIComponent(researchId)}/report`,
    { token: client.apiToken }
  );
}

export function financialManagerCatalog(client: AiaskApiCore): Promise<FinancialManagerCatalog> {
  return requestJson<FinancialManagerCatalog>(client.endpoint, "/v1/desktop/financial-manager/catalog", {
    token: controlOrApiToken(client)
  });
}

export function financialManagerStatus(client: AiaskApiCore): Promise<FinancialManagerStatus> {
  return requestJson<FinancialManagerStatus>(client.endpoint, "/v1/desktop/financial-manager/status", {
    token: controlOrApiToken(client)
  });
}

export function financialManagerQuery(
  client: AiaskApiCore,
  body: {
    capability_id: string;
    action_id: string;
    params?: Record<string, unknown>;
  }
): Promise<FinancialManagerQueryResult> {
  return requestJson<FinancialManagerQueryResult>(client.endpoint, "/v1/desktop/financial-manager/query", {
    method: "POST",
    token: controlOrApiToken(client),
    body
  });
}

export function financialManagerIntent(
  client: AiaskApiCore,
  body: {
    capability_id: string;
    action_id: string;
    params?: Record<string, unknown>;
    rationale?: string;
    user_id?: string;
  }
): Promise<FinancialManagerIntentResult> {
  return requestJson<FinancialManagerIntentResult>(client.endpoint, "/v1/desktop/financial-manager/intent", {
    method: "POST",
    token: client.controlToken,
    body
  });
}

export function brokerReadiness(client: AiaskApiCore): Promise<BrokerReadinessPayload> {
  return requestJson<BrokerReadinessPayload>(client.endpoint, "/v1/desktop/broker-readiness", {
    token: controlOrApiToken(client)
  });
}

export function brokerSync(
  client: AiaskApiCore,
  body: {
    provider?: string;
    consent: boolean;
    user_id?: string;
    session_id?: string;
    run_id?: string;
    trace_id?: string;
  }
): Promise<BrokerSyncPayload> {
  return requestJson<BrokerSyncPayload>(client.endpoint, "/v1/desktop/broker/sync", {
    method: "POST",
    token: controlOrApiToken(client),
    body
  });
}

export function brokerAccounts(client: AiaskApiCore, userId?: string, provider?: string): Promise<BrokerSnapshotPayload> {
  const params = new URLSearchParams();
  if (userId) params.set("user_id", userId);
  if (provider) params.set("provider", provider);
  const query = params.toString();
  return requestJson<BrokerSnapshotPayload>(client.endpoint, `/v1/desktop/broker/accounts${query ? `?${query}` : ""}`, {
    token: controlOrApiToken(client)
  });
}

export function brokerPositions(client: AiaskApiCore, userId?: string, provider?: string): Promise<BrokerSnapshotPayload> {
  const params = new URLSearchParams();
  if (userId) params.set("user_id", userId);
  if (provider) params.set("provider", provider);
  const query = params.toString();
  return requestJson<BrokerSnapshotPayload>(client.endpoint, `/v1/desktop/broker/positions${query ? `?${query}` : ""}`, {
    token: controlOrApiToken(client)
  });
}

export function brokerOrders(client: AiaskApiCore, userId?: string, provider?: string): Promise<BrokerSnapshotPayload> {
  const params = new URLSearchParams();
  if (userId) params.set("user_id", userId);
  if (provider) params.set("provider", provider);
  const query = params.toString();
  return requestJson<BrokerSnapshotPayload>(client.endpoint, `/v1/desktop/broker/orders${query ? `?${query}` : ""}`, {
    token: controlOrApiToken(client)
  });
}

export function brokerAnalyticsRun(
  client: AiaskApiCore,
  body: {
    user_id?: string;
    provider?: string;
    broker_profile_id?: string;
    period_start?: string;
    period_end?: string;
  } = {}
): Promise<BrokerAnalyticsPayload> {
  return requestJson<BrokerAnalyticsPayload>(client.endpoint, "/v1/desktop/broker/analytics/run", {
    method: "POST",
    token: controlOrApiToken(client),
    body
  });
}

export function brokerAnalyticsLatest(
  client: AiaskApiCore,
  userId?: string,
  provider?: string
): Promise<BrokerAnalyticsPayload> {
  const params = new URLSearchParams();
  if (userId) params.set("user_id", userId);
  if (provider) params.set("provider", provider);
  const query = params.toString();
  return requestJson<BrokerAnalyticsPayload>(
    client.endpoint,
    `/v1/desktop/broker/analytics/latest${query ? `?${query}` : ""}`,
    { token: controlOrApiToken(client) }
  );
}
