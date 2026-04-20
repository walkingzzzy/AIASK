import { authedFetch, authedStreamFetch } from './api';
import type { CopilotActionMeta, CopilotPageContext } from './copilot-types';

export type ChatEvent =
  | { type: 'delta'; content: string }
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | { type: 'tool_result'; name: string; result: unknown }
  | { type: 'action'; actionId: string; label: string; description?: string; reason?: string; payload?: Record<string, unknown>; autoExecute?: boolean }
  | { type: 'error'; message: string }
  | { type: 'done' };

export type LlmConfig = { apiKey: string; baseUrl: string; model: string };
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

export async function saveLlmConfig(config: LlmConfig): Promise<void> {
  const r = await authedFetch('/chat/config', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!r.ok) throw new Error('保存失败');
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

export async function probeModels(baseUrl: string, apiKey: string): Promise<{ success: boolean; models: string[]; error?: string }> {
  try {
    const r = await authedFetch('/chat/probe-models', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ baseUrl: baseUrl.trim(), apiKey: apiKey.trim() }),
    }, { redirectOnUnauthorized: false });
    const d = await r.json().catch(() => null);
    return { success: d?.success ?? r.ok, models: d?.models ?? [], error: d?.error };
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

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith('data: ')) continue;
      try {
        const event = JSON.parse(trimmed.slice(6)) as ChatEvent;
        onEvent(event);
      } catch {
        // skip malformed SSE payloads
      }
    }
  }
}
