import { requestJson } from "../../api";
import type {
  ConnectorDetail,
  GatewayDaemonStatus,
  GatewayMessage,
  GatewayPlatform,
  WebhookSubscription
} from "../../types";
import type { AiaskApiCore } from "./core";
import { controlOrApiToken } from "./core";

export function connectorsSummary(client: AiaskApiCore): Promise<{ data: unknown; status?: string; error?: string }> {
  return requestJson<{ data: unknown; status?: string; error?: string }>(client.endpoint, "/v1/connectors/summary", {
    token: controlOrApiToken(client)
  });
}

export function connectorsList(
  client: AiaskApiCore,
  type?: string,
  category?: string
): Promise<{ object: string; data: ConnectorDetail[] }> {
  const params = new URLSearchParams();
  if (type) params.set("type", type);
  if (category) params.set("category", category);
  const query = params.toString();
  return requestJson<{ object: string; data: ConnectorDetail[] }>(
    client.endpoint,
    `/v1/connectors${query ? `?${query}` : ""}`,
    { token: controlOrApiToken(client) }
  );
}

export function connectorDetail(
  client: AiaskApiCore,
  connectorType: string,
  name: string
): Promise<{ object: string; data: ConnectorDetail }> {
  return requestJson<{ object: string; data: ConnectorDetail }>(
    client.endpoint,
    `/v1/connectors/${encodeURIComponent(connectorType)}/${encodeURIComponent(name)}`,
    { token: controlOrApiToken(client) }
  );
}

export function connectorTest(
  client: AiaskApiCore,
  connectorType: string,
  name: string
): Promise<{ object: string; data: ConnectorDetail }> {
  return requestJson<{ object: string; data: ConnectorDetail }>(
    client.endpoint,
    `/v1/connectors/${encodeURIComponent(connectorType)}/${encodeURIComponent(name)}/test`,
    { method: "POST", token: controlOrApiToken(client), body: {} }
  );
}

export function gatewayStatus(client: AiaskApiCore): Promise<{ object?: string; data?: unknown; [key: string]: unknown }> {
  return requestJson(client.endpoint, "/v1/gateway/status", { token: controlOrApiToken(client) });
}

export function gatewayDaemonStatus(client: AiaskApiCore): Promise<GatewayDaemonStatus> {
  return requestJson(client.endpoint, "/v1/gateway/daemon/status", { token: client.controlToken });
}

export function gatewayPlatforms(client: AiaskApiCore): Promise<{ object: string; data: GatewayPlatform[] }> {
  return requestJson(client.endpoint, "/v1/gateway/platforms", { token: controlOrApiToken(client) });
}

export function gatewayMessages(
  client: AiaskApiCore,
  platform?: string,
  limit = 100
): Promise<{ object: string; data: GatewayMessage[] }> {
  const params = new URLSearchParams();
  if (platform) params.set("platform", platform);
  params.set("limit", String(limit));
  return requestJson(client.endpoint, `/v1/gateway/messages?${params.toString()}`, { token: controlOrApiToken(client) });
}

export function gatewayDirectory(
  client: AiaskApiCore,
  platform?: string,
  kind?: string,
  limit = 200
): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
  const params = new URLSearchParams();
  if (platform) params.set("platform", platform);
  if (kind) params.set("kind", kind);
  params.set("limit", String(limit));
  return requestJson(client.endpoint, `/v1/gateway/directory?${params.toString()}`, { token: controlOrApiToken(client) });
}

export function gatewayDirectoryRefresh(client: AiaskApiCore): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, "/v1/gateway/directory/refresh", {
    method: "POST",
    token: controlOrApiToken(client),
    body: {}
  });
}

export function gatewayMessageRetry(client: AiaskApiCore, messageId: string): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, `/v1/gateway/messages/${encodeURIComponent(messageId)}/retry`, {
    method: "POST",
    token: client.controlToken,
    body: {}
  });
}

export function gatewayPlatformStart(client: AiaskApiCore, platform: string): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, `/v1/gateway/platforms/${encodeURIComponent(platform)}/start`, {
    method: "POST",
    token: controlOrApiToken(client),
    body: {}
  });
}

export function gatewayPlatformStop(client: AiaskApiCore, platform: string): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, `/v1/gateway/platforms/${encodeURIComponent(platform)}/stop`, {
    method: "POST",
    token: controlOrApiToken(client),
    body: {}
  });
}

export function gatewayPlatformHealth(client: AiaskApiCore, platform: string): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, `/v1/gateway/platforms/${encodeURIComponent(platform)}/health`, {
    token: controlOrApiToken(client)
  });
}

export function webhooksList(client: AiaskApiCore): Promise<{ object: string; data: WebhookSubscription[] }> {
  return requestJson(client.endpoint, "/v1/webhooks", { token: controlOrApiToken(client) });
}

export function webhookCreate(client: AiaskApiCore, body: Record<string, unknown>): Promise<unknown> {
  return requestJson(client.endpoint, "/v1/webhooks", { method: "POST", token: client.controlToken, body });
}

export function webhookDelete(client: AiaskApiCore, webhookId: string): Promise<unknown> {
  return requestJson(client.endpoint, `/v1/webhooks/${encodeURIComponent(webhookId)}`, {
    method: "DELETE",
    token: client.controlToken
  });
}

export function mcpRegisterLocal(client: AiaskApiCore, body: Record<string, unknown> = {}): Promise<unknown> {
  return requestJson(client.endpoint, "/v1/mcp/register-local", {
    method: "POST",
    token: client.controlToken,
    body
  });
}

export function mcpDiscover(client: AiaskApiCore, server: string): Promise<unknown> {
  return requestJson(client.endpoint, "/v1/mcp/discover", {
    method: "POST",
    token: client.controlToken,
    body: { server }
  });
}

export function mcpResourceRead(client: AiaskApiCore, uri: string, server?: string): Promise<unknown> {
  return requestJson(client.endpoint, "/v1/mcp/resources/read", {
    method: "POST",
    token: client.controlToken,
    body: { uri, server }
  });
}

export function mcpPromptGet(
  client: AiaskApiCore,
  name: string,
  argumentsValue: Record<string, unknown> = {},
  server?: string
): Promise<unknown> {
  return requestJson(client.endpoint, "/v1/mcp/prompts/get", {
    method: "POST",
    token: client.controlToken,
    body: { name, arguments: argumentsValue, server }
  });
}

export function mcpOauthStart(client: AiaskApiCore, server: string): Promise<unknown> {
  return requestJson(client.endpoint, "/v1/mcp/oauth/start", {
    method: "POST",
    token: client.controlToken,
    body: { server }
  });
}
