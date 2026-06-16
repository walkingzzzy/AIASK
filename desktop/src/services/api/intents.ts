import { requestJson } from "../../api";
import type { ApprovalItem, ToolEnvelope } from "../../types";
import type { AiaskApiCore } from "./core";
import { controlOrApiToken } from "./core";

export function readOnlyTool<T = unknown>(
  client: AiaskApiCore,
  tool: string,
  body: Record<string, unknown>
): Promise<ToolEnvelope & { data: T }> {
  return requestJson<ToolEnvelope & { data: T }>(client.endpoint, `/v1/tools/${encodeURIComponent(tool)}`, {
    method: "POST",
    token: client.apiToken,
    body
  });
}

export function createActionIntent(
  client: AiaskApiCore,
  action: string,
  params: Record<string, unknown>,
  rationale?: string
): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return requestJson<ToolEnvelope & { data: Record<string, unknown> }>(client.endpoint, "/intents", {
    method: "POST",
    token: client.controlToken,
    body: {
      action,
      params,
      rationale,
      ttl_seconds: 86400
    }
  });
}

export function confirmIntent(client: AiaskApiCore, intentId: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return requestJson<ToolEnvelope & { data: Record<string, unknown> }>(
    client.endpoint,
    `/intents/${encodeURIComponent(intentId)}/confirm`,
    { method: "POST", token: client.controlToken, body: {} }
  );
}

export function getIntent(client: AiaskApiCore, intentId: string): Promise<ToolEnvelope> {
  return requestJson<ToolEnvelope>(client.endpoint, `/intents/${encodeURIComponent(intentId)}`, {
    token: client.apiToken
  });
}

export function denyIntent(client: AiaskApiCore, intentId: string, reason?: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return requestJson<ToolEnvelope & { data: Record<string, unknown> }>(
    client.endpoint,
    `/intents/${encodeURIComponent(intentId)}/deny`,
    { method: "POST", token: client.controlToken, body: { reason: reason || "" } }
  );
}

export function intentsList(client: AiaskApiCore, status?: string, limit = 100): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("limit", String(limit));
  return requestJson<{ object: string; data: Array<Record<string, unknown>> }>(client.endpoint, `/intents?${params.toString()}`, {
    token: controlOrApiToken(client)
  });
}

export function approvalsList(client: AiaskApiCore, status?: string, limit = 100): Promise<{ object: string; data: ApprovalItem[] }> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("limit", String(limit));
  return requestJson(client.endpoint, `/v1/approvals?${params.toString()}`, { token: controlOrApiToken(client) });
}

export function approvalDecide(
  client: AiaskApiCore,
  approvalId: string,
  decision: "approve" | "deny",
  reason = "desktop_decision"
): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, `/v1/approvals/${encodeURIComponent(approvalId)}/${decision}`, {
    method: "POST",
    token: client.controlToken,
    body: { reason }
  });
}
