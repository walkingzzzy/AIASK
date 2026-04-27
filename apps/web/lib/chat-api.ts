import { authedFetch, authedStreamFetch, buildApiError, rejectFallbackPayload } from './api';
import type { CopilotActionMeta, CopilotPageContext } from './copilot-types';
import type { ChatToolTrace } from './tool-trace-types';

export type ChatEvent =
  | { type: 'delta'; content: string }
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | { type: 'tool_result'; name: string; result: unknown }
  | { type: 'tool_trace'; trace: ChatToolTrace }
  | { type: 'action'; actionId: string; label: string; description?: string; reason?: string; payload?: Record<string, unknown>; autoExecute?: boolean }
  | { type: 'final_fallback'; content: string }
  | { type: 'error'; message: string }
  | { type: 'done' };

export type LlmConfig = {
  baseUrl: string;
  model: string;
  hasStoredApiKey: boolean;
  apiKeyMasked: string;
};
export type ProbeCompatibility = {
  modelsEndpoint: { ok: boolean; error?: string; models: string[] };
  chatCompletions: { ok: boolean; error?: string; probeModel?: string; contentPreview?: string };
};
export type SaveLlmConfigInput = {
  apiKey?: string;
  baseUrl: string;
  model: string;
};
export type SaveLlmConfigResult = {
  saved: boolean;
  normalizedBaseUrl: string;
  hasStoredApiKey?: boolean;
  apiKeyMasked?: string;
  compatibility?: ProbeCompatibility;
};
export type ModelPreset = { provider: string; baseUrl: string; models: string[] };
export type StreamChatOptions = {
  mode?: 'chat' | 'copilot' | 'assistant';
  pageContext?: CopilotPageContext | null;
  availableActions?: CopilotActionMeta[];
};

export async function getLlmConfig(): Promise<LlmConfig | null> {
  try {
    const r = await authedFetch('/chat/config', { cache: 'no-store' }, { redirectOnUnauthorized: false });
    if (!r.ok) return null;
    const d = await r.json().catch(() => null);
    return d?.data ?? null;
  } catch {
    return null;
  }
}

export async function saveLlmConfig(config: SaveLlmConfigInput): Promise<SaveLlmConfigResult> {
  const r = await authedFetch('/chat/config', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(config),
  });
  const payload = await r.json().catch(() => null);
  if (!r.ok) {
    throw buildApiError(payload, {
      status: r.status,
      path: '/chat/config',
      fallbackMessage: '保存失败',
    });
  }
  const fallbackReason = rejectFallbackPayload(payload);
  if (fallbackReason) {
    throw new Error(`AI 配置保存未完成: ${fallbackReason}`);
  }
  return (payload?.data ?? {}) as SaveLlmConfigResult;
}

export async function getModelPresets(): Promise<ModelPreset[]> {
  try {
    const r = await authedFetch('/chat/models', { cache: 'no-store' }, { redirectOnUnauthorized: false });
    if (!r.ok) return [];
    const d = await r.json().catch(() => null);
    return d?.data ?? [];
  } catch {
    return [];
  }
}

export async function probeModels(
  baseUrl: string,
  apiKey: string,
  model?: string,
): Promise<{ success: boolean; models: string[]; error?: string; normalizedBaseUrl?: string; compatibility?: ProbeCompatibility }> {
  try {
    const r = await authedFetch('/chat/probe-models', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ baseUrl: baseUrl.trim(), apiKey: apiKey.trim(), model: model?.trim() }),
    }, { redirectOnUnauthorized: false });
    const d = await r.json().catch(() => null);
    const fallbackReason = rejectFallbackPayload(d);
    if (fallbackReason) {
      return { success: false, models: [], error: fallbackReason, normalizedBaseUrl: d?.normalizedBaseUrl, compatibility: d?.compatibility };
    }
    return {
      success: d?.success ?? r.ok,
      models: d?.models ?? [],
      error: d?.error,
      normalizedBaseUrl: d?.normalizedBaseUrl,
      compatibility: d?.compatibility,
    };
  } catch (error) {
    return {
      success: false,
      models: [],
      error: error instanceof Error ? error.message : '模型探测失败',
    };
  }
}

export async function streamChat(
  messages: Array<{ role: string; content: string }>,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
  options?: StreamChatOptions,
): Promise<void> {
  let resp: Response;
  try {
    resp = await authedStreamFetch('/chat/completions', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        messages,
        mode: options?.mode,
        pageContext: options?.pageContext,
        availableActions: options?.availableActions,
      }),
      signal,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    onEvent({ type: 'error', message });
    return;
  }

  if (!resp.ok) {
    onEvent({ type: 'error', message: `HTTP ${resp.status}` });
    return;
  }

  const reader = resp.body?.getReader();
  if (!reader) {
    onEvent({ type: 'error', message: '无法读取响应流' });
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';
  const handleLine = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed.startsWith('data: ')) return;
    try {
      const event = JSON.parse(trimmed.slice(6)) as ChatEvent;
      onEvent(event);
    } catch {
      // skip malformed SSE payloads
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    lines.forEach(handleLine);
  }

  const tail = `${decoder.decode()}${buffer}`.trim();
  if (tail) {
    tail.split('\n').forEach(handleLine);
  }
}
