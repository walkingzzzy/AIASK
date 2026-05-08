import { authedFetch, authedStreamFetch, buildApiError, rejectFallbackPayload } from './api';
import { hasLoggedInHint } from './auth';
import type { CopilotActionMeta, CopilotFrontendContext, CopilotPageContext } from './copilot-types';
import type { ChatToolTrace } from './tool-trace-types';

export type ChatEvent =
  | { type: 'delta'; content: string }
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | { type: 'tool_result'; name: string; result: unknown }
  | { type: 'tool_trace'; trace: ChatToolTrace }
  | { type: 'action'; actionId: string; label: string; description?: string; reason?: string; payload?: Record<string, unknown>; autoExecute?: boolean }
  | { type: 'heartbeat'; at: string; scope?: string }
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
  frontendContext?: CopilotFrontendContext | null;
  availableActions?: CopilotActionMeta[];
};

const CHAT_CONTEXT_TEXT_LIMIT = 600;
const CHAT_CONTEXT_ARRAY_LIMIT = 8;
const CHAT_CONTEXT_OBJECT_KEY_LIMIT = 24;
const LLM_CONFIG_CACHE_TTL_MS = 30_000;
let llmConfigCache: { value: LlmConfig | null; expiresAt: number } | null = null;
let llmConfigPromise: Promise<LlmConfig | null> | null = null;

function truncateContextText(value: string, limit = CHAT_CONTEXT_TEXT_LIMIT): string {
  return value.length > limit ? `${value.slice(0, limit)}...` : value;
}

function compactContextValue(value: unknown, depth = 0): unknown {
  if (value == null) return value;
  if (typeof value === 'string') return truncateContextText(value);
  if (typeof value === 'number' || typeof value === 'boolean') return value;
  if (depth >= 3) return '[truncated]';
  if (Array.isArray(value)) {
    return value.slice(0, CHAT_CONTEXT_ARRAY_LIMIT).map((item) => compactContextValue(item, depth + 1));
  }
  if (typeof value === 'object') {
    const result: Record<string, unknown> = {};
    for (const [key, nested] of Object.entries(value as Record<string, unknown>).slice(0, CHAT_CONTEXT_OBJECT_KEY_LIMIT)) {
      result[key] = compactContextValue(nested, depth + 1);
    }
    return result;
  }
  return String(value);
}

function pickCompactRecord(record: Record<string, unknown>, keys: string[]): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const key of keys) {
    if (record[key] !== undefined) result[key] = compactContextValue(record[key]);
  }
  return result;
}

function compactPersonalStrategyContext(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const record = value as Record<string, unknown>;
  const compact = pickCompactRecord(record, [
    'strategy_id',
    'strategy_name',
    'strategy_type',
    'status',
    'actor_id',
    'actor_roles',
    'personal_strategy',
    'editable',
    'source_strategy_id',
    'owner_state',
    'favorite_state',
    'paper_session_state',
    'mutation_guard',
  ]);
  const draft = record.draft_snapshot;
  if (draft && typeof draft === 'object' && !Array.isArray(draft)) {
    compact.draft_snapshot = pickCompactRecord(draft as Record<string, unknown>, [
      'id',
      'name',
      'description',
      'strategy_type',
      'status',
      'author_id',
      'tags',
      'factor_weights',
      'target_symbols',
    ]);
  }
  return compact;
}

function compactPageContextRaw(raw: Record<string, unknown> | undefined): Record<string, unknown> | undefined {
  if (!raw) return undefined;
  const compact = pickCompactRecord(raw, [
    'strategyId',
    'emptyDetailContract',
    'activeTab',
    'factorySection',
    'favorited',
    'riskEvents',
    'vectorProfiles',
    'promotionReady',
    'marketStatus',
    'incubationStage',
    'ownerState',
    'paperSessionState',
    'accountId',
    'selectedCode',
    'workspaceId',
  ]);
  const personalStrategyContext = compactPersonalStrategyContext(raw.personalStrategyContext);
  if (personalStrategyContext) compact.personalStrategyContext = personalStrategyContext;
  return Object.keys(compact).length ? compact : undefined;
}

function compactPageContextForChat(pageContext: CopilotPageContext | null | undefined): CopilotPageContext | null | undefined {
  if (!pageContext) return pageContext;
  return {
    ...pageContext,
    summary: truncateContextText(pageContext.summary, 1200),
    tags: pageContext.tags?.slice(0, 12),
    suggestions: pageContext.suggestions?.slice(0, 8).map((item) => truncateContextText(item, 240)),
    recommendedNextActions: pageContext.recommendedNextActions?.slice(0, 8).map((item) => truncateContextText(item, 240)),
    recommendedActions: pageContext.recommendedActions?.slice(0, 8),
    recommendedLinks: pageContext.recommendedLinks?.slice(0, 8),
    evidenceSummary: pageContext.evidenceSummary?.slice(0, 8).map((item) => truncateContextText(item, 320)),
    riskNotes: pageContext.riskNotes?.slice(0, 8).map((item) => truncateContextText(item, 320)),
    raw: compactPageContextRaw(pageContext.raw),
  };
}

function compactSurfaceRoute(route: CopilotFrontendContext['currentRoute']): CopilotFrontendContext['currentRoute'] {
  if (!route) return route;
  return {
    ...route,
    summary: truncateContextText(route.summary, 360),
    primaryGoal: truncateContextText(route.primaryGoal, 240),
    requiredInputs: route.requiredInputs?.slice(0, 5),
    coreEntities: route.coreEntities?.slice(0, 6),
    dataSources: route.dataSources?.slice(0, 6),
    capabilities: route.capabilities?.slice(0, 6).map((item) => truncateContextText(item, 120)),
    commonQuestions: route.commonQuestions?.slice(0, 5).map((item) => truncateContextText(item, 120)),
    relatedPageKeys: route.relatedPageKeys?.slice(0, 8),
    aliases: route.aliases?.slice(0, 8),
  };
}

function compactFrontendContextForChat(
  frontendContext: CopilotFrontendContext | null | undefined,
): CopilotFrontendContext | null | undefined {
  if (!frontendContext) return frontendContext;
  return {
    ...frontendContext,
    appMap: {
      modules: frontendContext.appMap.modules.slice(0, 12),
      routes: frontendContext.appMap.routes.slice(0, 80).map((route) => ({
        ...route,
        summary: truncateContextText(route.summary, 180),
        aliases: route.aliases?.slice(0, 6),
      })),
    },
    currentRoute: compactSurfaceRoute(frontendContext.currentRoute),
    relatedRoutes: frontendContext.relatedRoutes?.slice(0, 8).map((route) => compactSurfaceRoute(route)!),
    taskFlow: frontendContext.taskFlow
      ? {
          ...frontendContext.taskFlow,
          summary: truncateContextText(frontendContext.taskFlow.summary, 360),
          steps: frontendContext.taskFlow.steps.slice(0, 8).map((step) => ({
            ...step,
            goal: truncateContextText(step.goal, 180),
            requiredContext: step.requiredContext?.slice(0, 5),
          })),
        }
      : undefined,
  };
}

export async function getLlmConfig(): Promise<LlmConfig | null> {
  const now = Date.now();
  if (llmConfigCache && llmConfigCache.expiresAt > now) {
    return llmConfigCache.value;
  }
  if (llmConfigPromise) return llmConfigPromise;
  if (typeof window !== 'undefined' && !hasLoggedInHint()) {
    return null;
  }

  llmConfigPromise = (async () => {
    let value: LlmConfig | null = null;
    const cacheUntil = Date.now() + LLM_CONFIG_CACHE_TTL_MS;
    try {
      const r = await authedFetch('/chat/config', { cache: 'no-store' }, { redirectOnUnauthorized: false });
      if (r.ok) {
        const d = await r.json().catch(() => null);
        value = d?.data ?? null;
      }
    } catch {
      value = null;
    } finally {
      llmConfigCache = { value, expiresAt: cacheUntil };
      llmConfigPromise = null;
    }
    return value;
  })();

  return llmConfigPromise;
}

export function clearLlmConfigCache() {
  llmConfigCache = null;
  llmConfigPromise = null;
}

export async function getLlmConfigUncached(): Promise<LlmConfig | null> {
  clearLlmConfigCache();
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
  clearLlmConfigCache();
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
        pageContext: compactPageContextForChat(options?.pageContext),
        frontendContext: compactFrontendContextForChat(options?.frontendContext),
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
