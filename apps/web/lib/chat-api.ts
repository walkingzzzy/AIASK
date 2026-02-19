import { ensureAccessToken, clearCookies, redirectToLogin } from './auth';

const BFF_BASE = process.env.NEXT_PUBLIC_BFF_BASE_URL ?? 'http://127.0.0.1:3001/api';

export type ChatEvent =
  | { type: 'delta'; content: string }
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | { type: 'tool_result'; name: string; result: unknown }
  | { type: 'error'; message: string }
  | { type: 'done' };

export type LlmConfig = { apiKey: string; baseUrl: string; model: string };
export type ModelPreset = { provider: string; baseUrl: string; models: string[] };

async function authHeaders(): Promise<Record<string, string>> {
  const token = await ensureAccessToken();
  if (!token) { clearCookies(); redirectToLogin(); throw new Error('未登录'); }
  return { authorization: `Bearer ${token}` };
}

export async function getLlmConfig(): Promise<LlmConfig | null> {
  const h = await authHeaders();
  const r = await fetch(`${BFF_BASE}/chat/config`, { headers: h, cache: 'no-store' });
  if (r.status === 401) { clearCookies(); redirectToLogin(); throw new Error('登录已过期'); }
  const d = await r.json();
  return d?.data ?? null;
}

export async function saveLlmConfig(config: LlmConfig): Promise<void> {
  const h = await authHeaders();
  const r = await fetch(`${BFF_BASE}/chat/config`, {
    method: 'POST', headers: { ...h, 'content-type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!r.ok) throw new Error('保存失败');
}

export async function getModelPresets(): Promise<ModelPreset[]> {
  const h = await authHeaders();
  const r = await fetch(`${BFF_BASE}/chat/models`, { headers: h, cache: 'no-store' });
  const d = await r.json();
  return d?.data ?? [];
}

export async function streamChat(
  messages: Array<{ role: string; content: string }>,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const h = await authHeaders();
  const resp = await fetch(`${BFF_BASE}/chat/completions`, {
    method: 'POST',
    headers: { ...h, 'content-type': 'application/json' },
    body: JSON.stringify({ messages }),
    signal,
  });

  if (resp.status === 401) { clearCookies(); redirectToLogin(); return; }
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
