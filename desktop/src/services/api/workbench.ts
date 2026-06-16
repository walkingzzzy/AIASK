import { parseSseEvents, requestJson } from "../../api";
import { isMockEndpoint } from "../../mockApi";
import type {
  AgentArtifactRecord,
  AgentSourceRecord,
  DesktopRunSummary,
  DesktopWorkbenchSummary,
  HandoffQueuePayload,
  NormalizedRunEvent,
  RecentSessionSummary,
  RunRecord,
  RunTraceEvalPayload,
  SessionArchivePayload,
  SessionResumeContextPayload,
  SessionUndoPayload
} from "../../types";
import type { AiaskApiCore } from "./core";
import { controlOrApiToken } from "./core";

export function runGet(client: AiaskApiCore, runId: string): Promise<RunRecord> {
  return requestJson<RunRecord>(client.endpoint, `/v1/runs/${encodeURIComponent(runId)}`, {
    token: controlOrApiToken(client)
  });
}

export function runTraceEval(client: AiaskApiCore, runId: string): Promise<RunTraceEvalPayload> {
  return requestJson<RunTraceEvalPayload>(client.endpoint, `/v1/runs/${encodeURIComponent(runId)}/trace-eval`, {
    token: controlOrApiToken(client)
  });
}

export function runArtifacts(
  client: AiaskApiCore,
  runId: string,
  filters: { kind?: string; limit?: number } = {}
): Promise<{ object: string; run_id: string; data: AgentArtifactRecord[] }> {
  const params = new URLSearchParams();
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.limit) params.set("limit", String(filters.limit));
  const query = params.toString();
  return requestJson<{ object: string; run_id: string; data: AgentArtifactRecord[] }>(
    client.endpoint,
    `/v1/runs/${encodeURIComponent(runId)}/artifacts${query ? `?${query}` : ""}`,
    { token: controlOrApiToken(client) }
  );
}

export function runSources(
  client: AiaskApiCore,
  runId: string,
  filters: { source_type?: string; limit?: number } = {}
): Promise<{ object: string; run_id: string; data: AgentSourceRecord[] }> {
  const params = new URLSearchParams();
  if (filters.source_type) params.set("source_type", filters.source_type);
  if (filters.limit) params.set("limit", String(filters.limit));
  const query = params.toString();
  return requestJson<{ object: string; run_id: string; data: AgentSourceRecord[] }>(
    client.endpoint,
    `/v1/runs/${encodeURIComponent(runId)}/sources${query ? `?${query}` : ""}`,
    { token: controlOrApiToken(client) }
  );
}

export function sessionArtifacts(
  client: AiaskApiCore,
  sessionId: string,
  filters: { kind?: string; limit?: number } = {}
): Promise<{ object: string; session_id: string; data: AgentArtifactRecord[] }> {
  const params = new URLSearchParams();
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.limit) params.set("limit", String(filters.limit));
  const query = params.toString();
  return requestJson<{ object: string; session_id: string; data: AgentArtifactRecord[] }>(
    client.endpoint,
    `/v1/sessions/${encodeURIComponent(sessionId)}/artifacts${query ? `?${query}` : ""}`,
    { token: client.apiToken }
  );
}

export function sessionSources(
  client: AiaskApiCore,
  sessionId: string,
  filters: { source_type?: string; limit?: number } = {}
): Promise<{ object: string; session_id: string; data: AgentSourceRecord[] }> {
  const params = new URLSearchParams();
  if (filters.source_type) params.set("source_type", filters.source_type);
  if (filters.limit) params.set("limit", String(filters.limit));
  const query = params.toString();
  return requestJson<{ object: string; session_id: string; data: AgentSourceRecord[] }>(
    client.endpoint,
    `/v1/sessions/${encodeURIComponent(sessionId)}/sources${query ? `?${query}` : ""}`,
    { token: client.apiToken }
  );
}

export function runCancel(client: AiaskApiCore, runId: string): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, `/v1/runs/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
    token: controlOrApiToken(client),
    body: {}
  });
}

export function runStop(client: AiaskApiCore, runId: string): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, `/v1/runs/${encodeURIComponent(runId)}/stop`, {
    method: "POST",
    token: controlOrApiToken(client),
    body: {}
  });
}

export function runSteer(client: AiaskApiCore, runId: string, instruction: string): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, `/v1/runs/${encodeURIComponent(runId)}/steer`, {
    method: "POST",
    token: controlOrApiToken(client),
    body: { instruction }
  });
}

export function workbenchSummary(client: AiaskApiCore): Promise<DesktopWorkbenchSummary> {
  return requestJson<DesktopWorkbenchSummary>(client.endpoint, "/v1/desktop/workbench/summary", {
    token: client.apiToken
  });
}

export function runsList(
  client: AiaskApiCore,
  filters: { session_id?: string; status?: string; limit?: number } = {}
): Promise<{ object: string; data: DesktopRunSummary[] }> {
  const params = new URLSearchParams();
  if (filters.session_id) params.set("session_id", filters.session_id);
  if (filters.status) params.set("status", filters.status);
  if (filters.limit) params.set("limit", String(filters.limit));
  const query = params.toString();
  return requestJson<{ object: string; data: DesktopRunSummary[] }>(
    client.endpoint,
    `/v1/desktop/runs${query ? `?${query}` : ""}`,
    { token: client.apiToken }
  );
}

export async function runEvents(client: AiaskApiCore, runId: string, token?: string): Promise<NormalizedRunEvent[]> {
  if (isMockEndpoint(client.endpoint)) {
    const payload = await requestJson<{ data?: NormalizedRunEvent[] }>(
      client.endpoint,
      `/v1/runs/${encodeURIComponent(runId)}/events`,
      { token: token || client.apiToken }
    );
    return payload.data || [];
  }
  const response = await fetch(`${client.endpoint}/v1/runs/${encodeURIComponent(runId)}/events`, {
    headers: token?.trim() ? { Authorization: `Bearer ${token.trim()}` } : {}
  });
  if (!response.ok) throw new Error(`AIASK_HTTP_${response.status}`);
  return parseSseEvents<NormalizedRunEvent>(await response.text());
}

export function sessionsList(
  client: AiaskApiCore,
  userId?: string,
  limit = 100,
  includeArchived = false
): Promise<{ object: string; data: RecentSessionSummary[] }> {
  const params = new URLSearchParams();
  if (userId) params.set("user_id", userId);
  params.set("limit", String(limit));
  if (includeArchived) params.set("include_archived", "true");
  return requestJson<{ object: string; data: RecentSessionSummary[] }>(
    client.endpoint,
    `/v1/hermes/sessions?${params.toString()}`,
    { token: controlOrApiToken(client) }
  );
}

export function handoffsList(
  client: AiaskApiCore,
  filters: { userId?: string; sessionId?: string; status?: string; limit?: number; includeCompleted?: boolean } = {}
): Promise<HandoffQueuePayload> {
  const params = new URLSearchParams();
  if (filters.userId) params.set("user_id", filters.userId);
  if (filters.sessionId) params.set("session_id", filters.sessionId);
  if (filters.status) params.set("status", filters.status);
  params.set("limit", String(filters.limit || 100));
  if (filters.includeCompleted) params.set("include_completed", "true");
  return requestJson<HandoffQueuePayload>(client.endpoint, `/v1/hermes/handoffs?${params.toString()}`, {
    token: controlOrApiToken(client)
  });
}

export function sessionResumeContext(client: AiaskApiCore, sessionId: string): Promise<SessionResumeContextPayload> {
  return requestJson<SessionResumeContextPayload>(
    client.endpoint,
    `/v1/hermes/sessions/${encodeURIComponent(sessionId)}/resume-context`,
    { token: controlOrApiToken(client) }
  );
}

export function sessionMessages(
  client: AiaskApiCore,
  sessionId: string,
  limit = 200
): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
  return requestJson<{ object: string; data: Array<Record<string, unknown>> }>(
    client.endpoint,
    `/v1/sessions/${encodeURIComponent(sessionId)}/messages?limit=${encodeURIComponent(String(limit))}`,
    { token: client.apiToken }
  );
}

export function sessionUndo(
  client: AiaskApiCore,
  sessionId: string,
  turns = 1,
  reason = "desktop session undo"
): Promise<SessionUndoPayload> {
  return requestJson<SessionUndoPayload>(client.endpoint, `/v1/sessions/${encodeURIComponent(sessionId)}/undo`, {
    method: "POST",
    token: client.controlToken,
    body: { turns, reason }
  });
}

export function search(
  client: AiaskApiCore,
  query: string,
  body: { session_id?: string; user_id?: string; limit?: number; include_archived?: boolean } = {}
): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
  const params = new URLSearchParams();
  params.set("query", query);
  if (body.session_id) params.set("session_id", body.session_id);
  if (body.user_id) params.set("user_id", body.user_id);
  if (body.limit) params.set("limit", String(body.limit));
  if (body.include_archived) params.set("include_archived", "true");
  return requestJson<{ object: string; data: Array<Record<string, unknown>> }>(client.endpoint, `/v1/search?${params.toString()}`, {
    token: client.apiToken
  });
}

export function sessionArchive(
  client: AiaskApiCore,
  sessionId: string,
  archived = true,
  reason = "desktop session archive"
): Promise<SessionArchivePayload> {
  return requestJson<SessionArchivePayload>(client.endpoint, `/v1/sessions/${encodeURIComponent(sessionId)}/archive`, {
    method: "POST",
    token: client.controlToken,
    body: { archived, reason }
  });
}
