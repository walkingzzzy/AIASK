import { requestJson } from "../../api";
import type {
  CapabilityWorkbenchPayload,
  JobRunRecord,
  LearningProposal,
  PluginCommand,
  RlRun,
  ToolEnvelope
} from "../../types";
import type { AiaskApiCore } from "./core";
import { controlOrApiToken } from "./core";

export function jobsList(client: AiaskApiCore): Promise<{ object: string; data: Array<Record<string, unknown>> }> {
  return requestJson<{ object: string; data: Array<Record<string, unknown>> }>(client.endpoint, "/v1/jobs", {
    token: client.apiToken
  });
}

export function jobCreate(client: AiaskApiCore, body: Record<string, unknown>): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>(client.endpoint, "/v1/jobs", {
    method: "POST",
    token: client.apiToken,
    body
  });
}

export function jobUpdate(
  client: AiaskApiCore,
  jobId: string,
  body: Record<string, unknown>
): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>(client.endpoint, `/v1/jobs/${encodeURIComponent(jobId)}`, {
    method: "PATCH",
    token: client.apiToken,
    body
  });
}

export function jobDelete(client: AiaskApiCore, jobId: string): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>(client.endpoint, `/v1/jobs/${encodeURIComponent(jobId)}`, {
    method: "DELETE",
    token: client.apiToken
  });
}

export function jobRun(client: AiaskApiCore, jobId: string): Promise<ToolEnvelope & { data: Record<string, unknown> }> {
  return requestJson<ToolEnvelope & { data: Record<string, unknown> }>(
    client.endpoint,
    `/v1/jobs/${encodeURIComponent(jobId)}/run`,
    {
      method: "POST",
      token: client.apiToken,
      body: {}
    }
  );
}

export function jobRuns(
  client: AiaskApiCore,
  jobId: string,
  limit = 100
): Promise<{ object: string; job_id: string; data: JobRunRecord[] }> {
  return requestJson<{ object: string; job_id: string; data: JobRunRecord[] }>(
    client.endpoint,
    `/v1/jobs/${encodeURIComponent(jobId)}/runs?limit=${encodeURIComponent(String(limit))}`,
    { token: client.apiToken }
  );
}

export function skillInstall(client: AiaskApiCore, body: Record<string, unknown>): Promise<unknown> {
  return requestJson(client.endpoint, "/v1/skills", { method: "POST", token: client.controlToken, body });
}

export async function skillsList(client: AiaskApiCore): Promise<CapabilityWorkbenchPayload["skills"]> {
  const payload = await requestJson<{ data: CapabilityWorkbenchPayload["skills"] }>(client.endpoint, "/v1/skills", {
    token: controlOrApiToken(client)
  });
  return payload.data;
}

export function skillUpdate(client: AiaskApiCore, name: string, body: Record<string, unknown>): Promise<unknown> {
  return requestJson(client.endpoint, `/v1/skills/${encodeURIComponent(name)}`, {
    method: "PATCH",
    token: client.controlToken,
    body
  });
}

export function skillDelete(client: AiaskApiCore, name: string): Promise<unknown> {
  return requestJson(client.endpoint, `/v1/skills/${encodeURIComponent(name)}`, {
    method: "DELETE",
    token: client.controlToken
  });
}

export function pluginToggle(client: AiaskApiCore, name: string, enabled: boolean): Promise<unknown> {
  return requestJson(client.endpoint, `/v1/plugins/${encodeURIComponent(name)}`, {
    method: "PATCH",
    token: client.controlToken,
    body: { enabled }
  });
}

export function pluginUpsert(client: AiaskApiCore, body: Record<string, unknown>): Promise<unknown> {
  return requestJson(client.endpoint, "/v1/plugins", {
    method: "POST",
    token: client.controlToken,
    body
  });
}

export function pluginToolTest(
  client: AiaskApiCore,
  name: string,
  tool: string,
  body: Record<string, unknown> = {}
): Promise<unknown> {
  return requestJson(client.endpoint, `/v1/plugins/${encodeURIComponent(name)}/tools/${encodeURIComponent(tool)}/test`, {
    method: "POST",
    token: client.controlToken,
    body
  });
}

export function pluginCommands(client: AiaskApiCore, name: string): Promise<{ object: string; data: PluginCommand[] }> {
  return requestJson(client.endpoint, `/v1/plugins/${encodeURIComponent(name)}/commands`, { token: client.controlToken });
}

export function pluginCommandTest(
  client: AiaskApiCore,
  name: string,
  command: string,
  body: Record<string, unknown> = {}
): Promise<unknown> {
  return requestJson(
    client.endpoint,
    `/v1/plugins/${encodeURIComponent(name)}/commands/${encodeURIComponent(command)}/test`,
    {
      method: "POST",
      token: client.controlToken,
      body
    }
  );
}

export function learningStatus(client: AiaskApiCore): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, "/v1/learning/status", { token: controlOrApiToken(client) });
}

export function learningReview(
  client: AiaskApiCore,
  status?: string,
  limit = 100
): Promise<{ object: string; data: LearningProposal[] }> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("limit", String(limit));
  return requestJson(client.endpoint, `/v1/learning/review?${params.toString()}`, { token: controlOrApiToken(client) });
}

export function learningApply(client: AiaskApiCore, proposalId: string): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, "/v1/learning/apply", {
    method: "POST",
    token: client.controlToken,
    body: { proposal_id: proposalId }
  });
}

export function rlEnvironments(client: AiaskApiCore): Promise<{ object: string; data: unknown }> {
  return requestJson(client.endpoint, "/v1/rl/environments", { token: controlOrApiToken(client) });
}

export function rlConfig(client: AiaskApiCore): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, "/v1/rl/config", { token: controlOrApiToken(client) });
}

export function rlConfigUpdate(client: AiaskApiCore, config: Record<string, unknown>): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, "/v1/rl/config", {
    method: "PATCH",
    token: client.controlToken,
    body: { config }
  });
}

export function rlRuns(client: AiaskApiCore, limit = 100): Promise<{ object: string; data: RlRun[] }> {
  return requestJson(client.endpoint, `/v1/rl/runs?limit=${encodeURIComponent(String(limit))}`, {
    token: controlOrApiToken(client)
  });
}

export function rlRunStart(
  client: AiaskApiCore,
  environment?: string,
  config: Record<string, unknown> = {}
): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, "/v1/rl/runs", {
    method: "POST",
    token: client.controlToken,
    body: { environment, config }
  });
}

export function rlRunStop(client: AiaskApiCore, runId: string): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, `/v1/rl/runs/${encodeURIComponent(runId)}/stop`, {
    method: "POST",
    token: client.controlToken,
    body: {}
  });
}

export function rlRunGet(client: AiaskApiCore, runId: string): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, `/v1/rl/runs/${encodeURIComponent(runId)}`, { token: controlOrApiToken(client) });
}

export function rlRunResults(client: AiaskApiCore, runId: string): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, `/v1/rl/runs/${encodeURIComponent(runId)}/results`, {
    token: controlOrApiToken(client)
  });
}

export function rlRunLogs(client: AiaskApiCore, runId: string): Promise<Record<string, unknown>> {
  return requestJson(client.endpoint, `/v1/rl/runs/${encodeURIComponent(runId)}/logs`, {
    token: controlOrApiToken(client)
  });
}
