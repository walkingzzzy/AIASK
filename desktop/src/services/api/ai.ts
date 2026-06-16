import { requestJson } from "../../api";
import type {
  AgentResponse,
  AiConfigPayload,
  AiConfigSavePayload,
  AiConfigSaveResult,
  AiSmokeResult,
  AiStatus,
  ResponseRecord
} from "../../types";
import type { AiaskApiCore } from "./core";

export type AiModelsPayload = {
  data: Array<Record<string, unknown>>;
  configured: boolean;
  unsupported?: boolean;
  error?: string;
};

export function aiStatus(client: AiaskApiCore): Promise<AiStatus> {
  return requestJson<AiStatus>(client.endpoint, "/v1/ai/status", { token: client.apiToken });
}

export function aiSmoke(client: AiaskApiCore, prompt?: string, model?: string): Promise<AiSmokeResult> {
  return requestJson<AiSmokeResult>(client.endpoint, "/v1/ai/smoke", {
    method: "POST",
    token: client.apiToken,
    body: { prompt, model }
  });
}

export function aiModels(client: AiaskApiCore): Promise<AiModelsPayload> {
  return requestJson<AiModelsPayload>(client.endpoint, "/v1/ai/models", { token: client.apiToken });
}

export function aiConfig(client: AiaskApiCore): Promise<AiConfigPayload> {
  return requestJson<AiConfigPayload>(client.endpoint, "/v1/ai/config", { token: client.apiToken });
}

export function aiConfigSave(client: AiaskApiCore, body: AiConfigSavePayload): Promise<AiConfigSaveResult> {
  return requestJson<AiConfigSaveResult>(client.endpoint, "/v1/ai/config", {
    method: "PATCH",
    token: client.controlToken,
    body
  });
}

export function response(client: AiaskApiCore, body: Record<string, unknown>, token?: string): Promise<AgentResponse> {
  return requestJson<AgentResponse>(client.endpoint, "/v1/responses", {
    method: "POST",
    token: token || client.apiToken,
    body
  });
}

export function responseGet(client: AiaskApiCore, responseId: string): Promise<ResponseRecord> {
  return requestJson<ResponseRecord>(client.endpoint, `/v1/responses/${encodeURIComponent(responseId)}`, {
    token: client.apiToken
  });
}

export function responseDelete(client: AiaskApiCore, responseId: string): Promise<{ id: string; object: string; deleted: boolean }> {
  return requestJson<{ id: string; object: string; deleted: boolean }>(
    client.endpoint,
    `/v1/responses/${encodeURIComponent(responseId)}`,
    { method: "DELETE", token: client.apiToken }
  );
}
