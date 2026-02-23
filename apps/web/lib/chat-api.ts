import { refreshAuth, clearLoggedIn, redirectToLogin } from './auth';

const BFF_BASE = process.env.NEXT_PUBLIC_BFF_BASE_URL ?? 'http://localhost:3001/api';

export type ChatEvent =
  | { type: 'delta'; content: string }
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | { type: 'tool_result'; name: string; result: unknown }
  | { type: 'error'; message: string }
  | { type: 'done' };

export type LlmConfig = { apiKey: string; baseUrl: string; model: string };
export type ModelPreset = { provider: string; baseUrl: string; models: string[] };

async function authedChatFetch(url: string, init?: RequestInit): Promise<Response> {
  const resp = await fetch(url, { ...init, credentials: 'include', cache: 'no-store' });
  if (resp.status === 401) {
    const ok = await refreshAuth();
    if (ok) return fetch(url, { ...init, credentials: 'include', cache: 'no-store' });
    clearLoggedIn();
    redirectToLogin();
    throw new Error('登录已过期');
  }
  return resp;
}

export async function getLlmConfig(): Promise<LlmConfig | null> {
  const r = await authedChatFetch(`${BFF_BASE}/chat/config`);
  const d = await r.json();
  return d?.data ?? null;
}

export async function saveLlmConfig(config: LlmConfig): Promise<void> {
  const r = await authedChatFetch(`${BFF_BASE}/chat/config`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!r.ok) throw new Error('保存失败');
}

export async function getModelPresets(): Promise<ModelPreset[]> {
  const r = await authedChatFetch(`${BFF_BASE}/chat/models`);
  const d = await r.json();
  return d?.data ?? [];
}

export async function streamChat(
  messages: Array<{ role: string; content: string }>,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(`${BFF_BASE}/chat/completions`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ messages }),
    credentials: 'include',
    signal,
  });

  if (resp.status === 401) { clearLoggedIn(); redirectToLogin(); return; }
  if (!resp.ok) { onEvent({ type: 'error', message: `HTTP ${resp.status}` }); return; }

  const reader = resp.body?.getReader();
  if (!reader) { onEvent({ type: 'error', message: '无法读取响应流' }); return; }

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
      } catch { /* skip malformed */ }
    }
  }
}
