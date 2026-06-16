import { requestJson } from "../../api";
import type {
  DesktopDataStatus,
  DesktopDataSyncPlan,
  DesktopSettingsStatus,
  FeedbackEvent,
  LocalProfile,
  RetentionSweepResult,
  StockDataSourceConfig,
  StockDataSourcesStatus,
  StockDataSourceTestResult,
  UserActivityEvent,
  UserActivityPayload,
  UserAnalyticsSummary,
  UserDataDeleteResult,
  UserDataExport,
  UserDataPolicy,
  UserLearningDataset,
  WorkflowRecommendationPayload
} from "../../types";
import type { AiaskApiCore } from "./core";
import { controlOrApiToken } from "./core";

export function settingsStatus(client: AiaskApiCore): Promise<DesktopSettingsStatus> {
  return requestJson<DesktopSettingsStatus>(client.endpoint, "/v1/desktop/settings/status", {
    token: controlOrApiToken(client)
  });
}

export function modelProviderStatus(client: AiaskApiCore): Promise<unknown> {
  return settingsStatus(client).then((payload) => payload.llm.providers);
}

export function memoryStatus(client: AiaskApiCore): Promise<unknown> {
  return settingsStatus(client).then((payload) => payload.memory);
}

export function dataStatus(
  client: AiaskApiCore,
  body: { codes?: string[]; max_stale_days?: number } = {}
): Promise<DesktopDataStatus> {
  const params = new URLSearchParams();
  if (body.codes?.length) params.set("codes", body.codes.join(","));
  if (body.max_stale_days) params.set("max_stale_days", String(body.max_stale_days));
  const query = params.toString();
  return requestJson<DesktopDataStatus>(client.endpoint, `/v1/desktop/data/status${query ? `?${query}` : ""}`, {
    token: client.apiToken
  });
}

export function dataSyncPlan(client: AiaskApiCore, body: Record<string, unknown>): Promise<DesktopDataSyncPlan> {
  return requestJson<DesktopDataSyncPlan>(client.endpoint, "/v1/desktop/data/sync-plan", {
    method: "POST",
    token: client.apiToken,
    body
  });
}

export function stockDataSources(client: AiaskApiCore): Promise<StockDataSourcesStatus> {
  return requestJson<StockDataSourcesStatus>(client.endpoint, "/v1/desktop/stock-data-sources", {
    token: controlOrApiToken(client)
  });
}

export function stockDataSourceSave(
  client: AiaskApiCore,
  body: StockDataSourceConfig
): Promise<{ object: string; source: StockDataSourceConfig; secrets_redacted?: boolean }> {
  return requestJson<{ object: string; source: StockDataSourceConfig; secrets_redacted?: boolean }>(
    client.endpoint,
    "/v1/desktop/stock-data-sources",
    {
      method: "POST",
      token: client.controlToken,
      body
    }
  );
}

export function stockDataSourceTest(
  client: AiaskApiCore,
  body: Record<string, unknown>
): Promise<StockDataSourceTestResult> {
  return requestJson<StockDataSourceTestResult>(client.endpoint, "/v1/desktop/stock-data-sources/test", {
    method: "POST",
    token: client.controlToken,
    body
  });
}

export function localProfileGet(client: AiaskApiCore): Promise<LocalProfile> {
  return requestJson<LocalProfile>(client.endpoint, "/v1/desktop/users/local-profile", { token: client.apiToken });
}

export function localProfileSave(
  client: AiaskApiCore,
  body: Pick<LocalProfile, "user_id" | "profile_name">
): Promise<LocalProfile> {
  return requestJson<LocalProfile>(client.endpoint, "/v1/desktop/users/local-profile", {
    method: "PATCH",
    token: client.apiToken,
    body
  });
}

export function recordEvents(
  client: AiaskApiCore,
  events: UserActivityEvent | UserActivityEvent[]
): Promise<{ object: string; data: UserActivityEvent[]; count: number; secrets_redacted?: boolean }> {
  const list = Array.isArray(events) ? events : [events];
  return requestJson<{ object: string; data: UserActivityEvent[]; count: number; secrets_redacted?: boolean }>(
    client.endpoint,
    "/v1/desktop/events",
    {
      method: "POST",
      token: client.apiToken,
      body: { events: list }
    }
  );
}

export function recordFeedback(
  client: AiaskApiCore,
  body: FeedbackEvent
): Promise<{ object: string; data: FeedbackEvent; secrets_redacted?: boolean }> {
  return requestJson<{ object: string; data: FeedbackEvent; secrets_redacted?: boolean }>(
    client.endpoint,
    "/v1/desktop/feedback",
    {
      method: "POST",
      token: client.apiToken,
      body
    }
  );
}

export function userActivity(client: AiaskApiCore, userId: string, limit = 20): Promise<UserActivityPayload> {
  return requestJson<UserActivityPayload>(
    client.endpoint,
    `/v1/desktop/users/${encodeURIComponent(userId)}/activity?limit=${encodeURIComponent(String(limit))}`,
    { token: controlOrApiToken(client) }
  );
}

export function userAnalyticsSummary(
  client: AiaskApiCore,
  userId?: string,
  limit = 20
): Promise<UserAnalyticsSummary> {
  const params = new URLSearchParams();
  if (userId) params.set("user_id", userId);
  params.set("limit", String(limit));
  return requestJson<UserAnalyticsSummary>(client.endpoint, `/v1/desktop/analytics/summary?${params.toString()}`, {
    token: controlOrApiToken(client)
  });
}

export function userDataExport(client: AiaskApiCore, userId: string, limit = 500): Promise<UserDataExport> {
  return requestJson<UserDataExport>(
    client.endpoint,
    `/v1/desktop/users/${encodeURIComponent(userId)}/export?limit=${encodeURIComponent(String(limit))}`,
    { token: controlOrApiToken(client) }
  );
}

export function userDataDelete(
  client: AiaskApiCore,
  userId: string,
  body: { dry_run?: boolean; hard_delete?: boolean; include_conversations?: boolean; include_audit?: boolean; reason?: string } = {}
): Promise<UserDataDeleteResult> {
  return requestJson<UserDataDeleteResult>(client.endpoint, `/v1/desktop/users/${encodeURIComponent(userId)}/delete`, {
    method: "POST",
    token: client.apiToken,
    body
  });
}

export function retentionSweep(
  client: AiaskApiCore,
  body: { user_id?: string; dry_run?: boolean } = { dry_run: true }
): Promise<RetentionSweepResult> {
  return requestJson<RetentionSweepResult>(client.endpoint, "/v1/desktop/retention/sweep", {
    method: "POST",
    token: client.controlToken,
    body
  });
}

export function userLearningDataset(
  client: AiaskApiCore,
  userId: string,
  limit = 100
): Promise<UserLearningDataset> {
  return requestJson<UserLearningDataset>(
    client.endpoint,
    `/v1/desktop/users/${encodeURIComponent(userId)}/learning-dataset?limit=${encodeURIComponent(String(limit))}`,
    { token: controlOrApiToken(client) }
  );
}

export function userRecommendations(
  client: AiaskApiCore,
  userId: string,
  limit = 5
): Promise<WorkflowRecommendationPayload> {
  return requestJson<WorkflowRecommendationPayload>(
    client.endpoint,
    `/v1/desktop/users/${encodeURIComponent(userId)}/recommendations?limit=${encodeURIComponent(String(limit))}`,
    { token: controlOrApiToken(client) }
  );
}

export function userDataPolicyGet(
  client: AiaskApiCore,
  userId: string
): Promise<{ object: string; data: UserDataPolicy }> {
  return requestJson<{ object: string; data: UserDataPolicy }>(
    client.endpoint,
    `/v1/desktop/users/${encodeURIComponent(userId)}/data-policy`,
    { token: controlOrApiToken(client) }
  );
}

export function userDataPolicySave(
  client: AiaskApiCore,
  userId: string,
  patch: Partial<UserDataPolicy>
): Promise<{ object: string; data: UserDataPolicy }> {
  return requestJson<{ object: string; data: UserDataPolicy }>(
    client.endpoint,
    `/v1/desktop/users/${encodeURIComponent(userId)}/data-policy`,
    {
      method: "PATCH",
      token: client.apiToken,
      body: patch
    }
  );
}
