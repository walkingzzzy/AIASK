import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { authedFetch } from '@/lib/api';
import type { ChatToolTrace } from '@/lib/tool-trace-types';

export type ChatToolCall = {
  id: string;
  name: string;
  args?: Record<string, unknown>;
  result?: unknown;
  pending?: boolean;
};

export type ChatActionStatus = 'pending' | 'scheduled' | 'auto_executed' | 'running' | 'done' | 'error';

export type ChatActionBlock = {
  id: string;
  kind: 'action';
  actionId: string;
  label: string;
  description?: string;
  reason?: string;
  payload?: Record<string, unknown>;
  status: ChatActionStatus;
  autoExecute?: boolean;
  resultMessage?: string;
};

export type ChatMsg = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: ChatToolCall[];
  toolTrace?: ChatToolTrace;
  actions?: ChatActionBlock[];
};

export type ChatConversation = {
  id: string;
  title: string;
  updatedAt: string;
  workspaceId?: string;
  messages: ChatMsg[];
};

type CreateConversationInput = {
  title?: string;
  workspaceId?: string;
};

type ChatState = {
  messages: ChatMsg[];
  conversations: ChatConversation[];
  currentConversationId: string;
  streaming: boolean;
  configLoaded: boolean;
  hasConfig: boolean;
  showConfig: boolean;
  syncReady: boolean;
  addUserMessage: (content: string) => string;
  appendAssistantDelta: (id: string, delta: string) => void;
  addAssistantMessage: () => string;
  addToolCall: (msgId: string, name: string, args: Record<string, unknown>) => void;
  resolveToolCall: (msgId: string, name: string, result: unknown) => void;
  setToolTrace: (msgId: string, trace: ChatToolTrace) => void;
  addActionBlock: (msgId: string, action: Omit<ChatActionBlock, 'id' | 'kind'>) => string;
  updateActionBlock: (msgId: string, actionId: string, patch: Partial<Omit<ChatActionBlock, 'id' | 'kind'>>) => void;
  switchConversation: (conversationId: string) => void;
  createConversation: (input?: CreateConversationInput) => string;
  assignConversationWorkspace: (conversationId: string, workspaceId: string, fallbackTitle?: string) => void;
  ensureWorkspaceConversation: (workspaceId: string, title: string, preferredId?: string | null) => string;
  setStreaming: (v: boolean) => void;
  setConfigLoaded: (loaded: boolean, has: boolean) => void;
  setShowConfig: (v: boolean) => void;
  clearMessages: () => void;
  initSync: () => Promise<void>;
  pushToServer: () => Promise<void>;
};

let counter = 0;
const MAX_SYNC_CONVERSATIONS = 20;
const MAX_SYNC_MESSAGES_PER_CONVERSATION = 40;
const MAX_SYNC_CONTENT_LENGTH = 8000;
const MAX_SYNC_TEXT_LENGTH = 320;

function uid(prefix = 'msg') {
  return `${prefix}_${Date.now()}_${++counter}`;
}

function nowIso() {
  return new Date().toISOString();
}

function createConversationRecord(id: string, input: CreateConversationInput = {}): ChatConversation {
  return {
    id,
    title: input.title?.trim() || '当前会话',
    workspaceId: input.workspaceId?.trim() || undefined,
    updatedAt: nowIso(),
    messages: [],
  };
}

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function normalizeToolCall(input: unknown): ChatToolCall | null {
  const record = asObject(input);
  const id = String(record.id ?? uid('tool')).trim();
  const name = String(record.name ?? '').trim();
  if (!id || !name) {
    return null;
  }

  const args = record.args && typeof record.args === 'object' && !Array.isArray(record.args)
    ? record.args as Record<string, unknown>
    : undefined;

  return {
    id,
    name,
    args,
    result: record.result,
    pending: record.pending === true,
  };
}

function normalizeStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value
        .map((item) => String(item ?? '').trim())
        .filter(Boolean)
        .slice(0, 12)
    : [];
}

function normalizeToolTrace(input: unknown): ChatToolTrace | undefined {
  const record = asObject(input);
  if (record.schemaVersion !== 'tool_trace.v1') return undefined;

  const scope = asObject(record.scope) ?? {};
  const items: ChatToolTrace['items'] = Array.isArray(record.items)
    ? record.items.map((item): ChatToolTrace['items'][number] | null => {
        const source = asObject(item);
        const kind = String(source.kind ?? '');
        const status = String(source.status ?? '');
        if (!['mcp', 'local_context', 'client_action', 'compliance'].includes(kind)) return null;
        if (!['pending', 'success', 'error'].includes(status)) return null;
        const id = String(source.id ?? uid('trace_item')).trim();
        const toolName = String(source.toolName ?? '').trim();
        if (!id || !toolName) return null;
        const normalizedItem: ChatToolTrace['items'][number] = {
          id,
          referenceLabel: String(source.referenceLabel ?? '').trim() || 'T?',
          kind: kind as ChatToolTrace['items'][number]['kind'],
          toolName,
          status: status as ChatToolTrace['items'][number]['status'],
          startedAt: String(source.startedAt ?? '').trim(),
          inputSummary: normalizeStringArray(source.inputSummary),
          outputSummary: normalizeStringArray(source.outputSummary),
          citedInAnswer: source.citedInAnswer === true,
        };
        if (typeof source.finishedAt === 'string') normalizedItem.finishedAt = source.finishedAt;
        if (typeof source.durationMs === 'number') normalizedItem.durationMs = source.durationMs;
        if (typeof source.errorMessage === 'string') normalizedItem.errorMessage = source.errorMessage;
        return normalizedItem;
      }).filter((item): item is ChatToolTrace['items'][number] => item != null)
    : [];

  const answerReferences = Array.isArray(record.answerReferences)
    ? record.answerReferences.map((item) => {
        const source = asObject(item);
        const itemId = String(source.itemId ?? '').trim();
        const toolName = String(source.toolName ?? '').trim();
        if (!itemId || !toolName) return null;
        return {
          itemId,
          referenceLabel: String(source.referenceLabel ?? '').trim() || 'T?',
          toolName,
          evidenceSummary: String(source.evidenceSummary ?? '').trim(),
        };
      }).filter((item): item is ChatToolTrace['answerReferences'][number] => item != null)
    : [];

  const status = String(record.status ?? '');
  const evidenceMode = String(record.evidenceMode ?? '');
  return {
    schemaVersion: 'tool_trace.v1',
    id: String(record.id ?? uid('trace')).trim() || uid('trace'),
    visibility: 'owner_only',
    generatedAt: String(record.generatedAt ?? '').trim(),
    status: ['empty', 'running', 'completed', 'partial_error'].includes(status)
      ? status as ChatToolTrace['status']
      : 'empty',
    scope: {
      mode: typeof scope.mode === 'string' ? scope.mode : undefined,
      pageKey: typeof scope.pageKey === 'string' ? scope.pageKey : undefined,
      objectType: typeof scope.objectType === 'string' ? scope.objectType : undefined,
      objectId: typeof scope.objectId === 'string' ? scope.objectId : undefined,
      stockCode: typeof scope.stockCode === 'string' ? scope.stockCode : undefined,
    },
    items,
    answerReferences,
    evidenceMode: ['mcp_supported', 'tool_supported', 'page_context_supported', 'advisory_only'].includes(evidenceMode)
      ? evidenceMode as ChatToolTrace['evidenceMode']
      : 'advisory_only',
    advisoryOnly: record.advisoryOnly === true,
    advisoryReason: typeof record.advisoryReason === 'string' ? record.advisoryReason : undefined,
  };
}

function normalizeActionBlock(input: unknown): ChatActionBlock | null {
  const record = asObject(input);
  const id = String(record.id ?? uid('action')).trim();
  const actionId = String(record.actionId ?? '').trim();
  const label = String(record.label ?? '').trim();
  const status = record.status;
  if (!id || !actionId || !label || !['pending', 'scheduled', 'auto_executed', 'running', 'done', 'error'].includes(String(status))) {
    return null;
  }

  const payload = record.payload && typeof record.payload === 'object' && !Array.isArray(record.payload)
    ? record.payload as Record<string, unknown>
    : undefined;

  return {
    id,
    kind: 'action',
    actionId,
    label,
    description: typeof record.description === 'string' ? record.description : undefined,
    reason: typeof record.reason === 'string' ? record.reason : undefined,
    payload,
    status: String(status) as ChatActionStatus,
    autoExecute: record.autoExecute === true ? true : record.autoExecute === false ? false : undefined,
    resultMessage: typeof record.resultMessage === 'string' ? record.resultMessage : undefined,
  };
}

function normalizeMessage(input: unknown): ChatMsg | null {
  const record = asObject(input);
  const role = String(record.role ?? '').trim();
  if (role !== 'user' && role !== 'assistant') {
    return null;
  }

  const toolCalls = Array.isArray(record.toolCalls)
    ? record.toolCalls.map((item) => normalizeToolCall(item)).filter((item): item is ChatToolCall => item != null)
    : undefined;
  const actions = Array.isArray(record.actions)
    ? record.actions.map((item) => normalizeActionBlock(item)).filter((item): item is ChatActionBlock => item != null)
    : undefined;
  const toolTrace = normalizeToolTrace(record.toolTrace);

  return {
    id: String(record.id ?? uid()).trim() || uid(),
    role: role as 'user' | 'assistant',
    content: typeof record.content === 'string' ? record.content : '',
    ...(toolCalls && toolCalls.length > 0 ? { toolCalls } : {}),
    ...(toolTrace ? { toolTrace } : {}),
    ...(actions && actions.length > 0 ? { actions } : {}),
  };
}

function normalizeConversation(input: ChatConversation): ChatConversation {
  const messages = Array.isArray(input.messages)
    ? input.messages.map((item) => normalizeMessage(item)).filter((item): item is ChatMsg => item != null)
    : [];
  return {
    id: String(input.id || uid('conv')),
    title: String(input.title || '当前会话'),
    updatedAt: input.updatedAt || nowIso(),
    workspaceId: input.workspaceId || undefined,
    messages,
  };
}

function truncateText(value: unknown, maxLength = MAX_SYNC_TEXT_LENGTH): string {
  const text = String(value ?? '').trim();
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

function compactObjectFields(value: unknown, maxKeys = 12): Record<string, unknown> | undefined {
  const record = asObject(value);
  const entries = Object.entries(record).slice(0, maxKeys);
  if (entries.length === 0) return undefined;
  return Object.fromEntries(entries.map(([key, item]) => {
    if (item == null || typeof item === 'number' || typeof item === 'boolean') return [key, item];
    if (typeof item === 'string') return [key, truncateText(item)];
    if (Array.isArray(item)) return [key, `[array:${item.length}]`];
    if (typeof item === 'object') return [key, '[object]'];
    return [key, String(item)];
  }));
}

function summarizeUnknown(value: unknown): string | number | boolean | null | undefined {
  if (value == null || typeof value === 'number' || typeof value === 'boolean') return value;
  if (typeof value === 'string') return truncateText(value, 1000);
  if (Array.isArray(value)) return `[array:${value.length}]`;
  if (typeof value === 'object') {
    const keys = Object.keys(value as Record<string, unknown>).slice(0, 8);
    return `[object:${keys.join(',')}]`;
  }
  return String(value);
}

function compactToolTraceForSync(trace: ChatToolTrace | undefined): ChatToolTrace | undefined {
  if (!trace) return undefined;
  return {
    ...trace,
    scope: {
      mode: truncateText(trace.scope.mode, 80) || undefined,
      pageKey: truncateText(trace.scope.pageKey, 120) || undefined,
      objectType: truncateText(trace.scope.objectType, 120) || undefined,
      objectId: truncateText(trace.scope.objectId, 160) || undefined,
      stockCode: truncateText(trace.scope.stockCode, 32) || undefined,
    },
    items: trace.items.slice(0, 20).map((item) => ({
      ...item,
      referenceLabel: truncateText(item.referenceLabel, 16),
      toolName: truncateText(item.toolName, 160),
      inputSummary: item.inputSummary.slice(0, 8).map((text) => truncateText(text, 240)),
      outputSummary: item.outputSummary.slice(0, 8).map((text) => truncateText(text, 320)),
      errorMessage: item.errorMessage ? truncateText(item.errorMessage, 320) : undefined,
    })),
    answerReferences: trace.answerReferences.slice(0, 20).map((item) => ({
      itemId: truncateText(item.itemId, 120),
      referenceLabel: truncateText(item.referenceLabel, 16),
      toolName: truncateText(item.toolName, 160),
      evidenceSummary: truncateText(item.evidenceSummary, 320),
    })),
    advisoryReason: trace.advisoryReason ? truncateText(trace.advisoryReason, 320) : undefined,
  };
}

function compactMessageForSync(message: ChatMsg) {
  const toolCalls = message.toolCalls?.slice(0, 8).map((call) => ({
    id: truncateText(call.id, 120),
    name: truncateText(call.name, 160),
    args: compactObjectFields(call.args),
    result: summarizeUnknown(call.result),
    pending: call.pending === true,
  })).filter((call) => call.id && call.name);
  const actions = message.actions?.slice(0, 8).map((action) => ({
    id: truncateText(action.id, 120),
    actionId: truncateText(action.actionId, 160),
    label: truncateText(action.label, 160),
    description: action.description ? truncateText(action.description, 320) : undefined,
    reason: action.reason ? truncateText(action.reason, 320) : undefined,
    payload: compactObjectFields(action.payload),
    status: action.status,
    autoExecute: action.autoExecute === true,
    resultMessage: action.resultMessage ? truncateText(action.resultMessage, 320) : undefined,
  })).filter((action) => action.id && action.actionId && action.label);
  const toolTrace = compactToolTraceForSync(message.toolTrace);
  const content = truncateText(message.content, MAX_SYNC_CONTENT_LENGTH);
  if (!content && !toolCalls?.length && !actions?.length && !toolTrace) return null;
  return {
    id: truncateText(message.id, 120),
    role: message.role,
    content,
    ...(toolCalls?.length ? { toolCalls } : {}),
    ...(actions?.length ? { actions } : {}),
    ...(toolTrace ? { toolTrace } : {}),
  };
}

function compactConversationForSync(conversation: ChatConversation) {
  const normalized = normalizeConversation(conversation);
  const messages = normalized.messages
    .slice(-MAX_SYNC_MESSAGES_PER_CONVERSATION)
    .map((message) => compactMessageForSync(message))
    .filter((message): message is NonNullable<ReturnType<typeof compactMessageForSync>> => message != null);
  return {
    id: truncateText(normalized.id, 120),
    title: truncateText(normalized.title || '当前会话', 160),
    updatedAt: normalized.updatedAt,
    workspaceId: normalized.workspaceId ? truncateText(normalized.workspaceId, 120) : undefined,
    messages,
  };
}

function compactConversationsForSync(conversations: ChatConversation[]) {
  return conversations
    .map((conversation) => normalizeConversation(conversation))
    .sort((left, right) => new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime())
    .slice(0, MAX_SYNC_CONVERSATIONS)
    .map((conversation) => compactConversationForSync(conversation));
}

function upsertConversation(
  conversations: ChatConversation[],
  conversation: ChatConversation,
) {
  const next = [normalizeConversation(conversation), ...conversations.filter((item) => item.id !== conversation.id)];
  return next.sort((left, right) => new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime());
}

function conversationOf(
  state: Pick<ChatState, 'conversations' | 'currentConversationId'>,
  messages: ChatMsg[],
  patch?: Partial<ChatConversation>,
): ChatConversation {
  const current =
    state.conversations.find((item) => item.id === state.currentConversationId) ??
    createConversationRecord(state.currentConversationId);

  return normalizeConversation({
    ...current,
    ...patch,
    id: patch?.id ?? current.id,
    messages,
    updatedAt: nowIso(),
  });
}

function fallbackConversation(state: Pick<ChatState, 'conversations' | 'currentConversationId' | 'messages'>) {
  if (state.conversations.length > 0) {
    return state.conversations.find((item) => item.id === state.currentConversationId) ?? state.conversations[0];
  }
  return {
    id: state.currentConversationId || uid('conv'),
    title: '当前会话',
    updatedAt: nowIso(),
    messages: state.messages,
  } satisfies ChatConversation;
}

let syncTimer: number | null = null;
const CHAT_SYNC_INTERVAL_KEY = '__aiaskChatSyncInterval';

function scheduleSync() {
  if (typeof window === 'undefined') return;
  if (syncTimer) window.clearTimeout(syncTimer);
  syncTimer = window.setTimeout(() => {
    void useChatStore.getState().pushToServer();
  }, 2000);
}

function ensureBackgroundSync() {
  if (typeof window === 'undefined') return;
  const globalWindow = window as unknown as Window & Record<string, number | undefined>;
  const existing = globalWindow[CHAT_SYNC_INTERVAL_KEY];
  if (typeof existing === 'number') {
    window.clearInterval(existing);
  }
  globalWindow[CHAT_SYNC_INTERVAL_KEY] = window.setInterval(() => {
    void useChatStore.getState().pushToServer();
  }, 300000);
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      messages: [],
      conversations: [],
      currentConversationId: 'default',
      streaming: false,
      configLoaded: false,
      hasConfig: false,
      showConfig: false,
      syncReady: false,

      initSync: async () => {
        if (get().syncReady) return;
        let remote: ChatConversation[] = [];
        try {
          const resp = await authedFetch('/chat/conversations', undefined, { redirectOnUnauthorized: false });
          if (resp.ok) {
            const json = await resp.json().catch(() => ({ data: { conversations: [] } }));
            remote = Array.isArray(json?.data?.conversations)
              ? (json.data.conversations as ChatConversation[])
              : [];
          }
        } catch {
          remote = [];
        }
        const local = get().conversations.length > 0
          ? get().conversations
          : [fallbackConversation(get())];

        const merged = new Map<string, ChatConversation>();
        [...remote, ...local].forEach((conversation) => {
          const normalized = normalizeConversation(conversation);
          const existing = merged.get(normalized.id);
          if (!existing || new Date(normalized.updatedAt).getTime() >= new Date(existing.updatedAt).getTime()) {
            merged.set(normalized.id, normalized);
          }
        });

        const conversations = Array.from(merged.values());
        const current =
          conversations.find((item) => item.id === get().currentConversationId) ??
          conversations[0] ??
          createConversationRecord('default');

        set({
          conversations,
          currentConversationId: current.id,
          messages: current.messages,
          syncReady: true,
        });
        ensureBackgroundSync();
      },

      pushToServer: async () => {
        const fallback = fallbackConversation(get());
        const conversations = get().conversations.length > 0 ? get().conversations : [fallback];
        try {
          await authedFetch('/chat/conversations/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              conversations: compactConversationsForSync(conversations),
            }),
          }, { redirectOnUnauthorized: false });
        } catch {
          // 壳层同步失败时保留本地会话，不打断页面主流程。
        }
      },

      addUserMessage: (content) => {
        const id = uid();
        set((state) => {
          const nextMessage: ChatMsg = { id, role: 'user', content };
          const messages = [...state.messages, nextMessage];
          const current = conversationOf(state, messages);
          return {
            messages,
            conversations: upsertConversation(state.conversations, current),
          };
        });
        scheduleSync();
        return id;
      },

      addAssistantMessage: () => {
        const id = uid();
        set((state) => {
          const nextMessage: ChatMsg = { id, role: 'assistant', content: '', toolCalls: [], actions: [] };
          const messages = [...state.messages, nextMessage];
          const current = conversationOf(state, messages);
          return {
            messages,
            conversations: upsertConversation(state.conversations, current),
          };
        });
        scheduleSync();
        return id;
      },

      appendAssistantDelta: (id, delta) => {
        set((state) => {
          const messages = state.messages.map((message) =>
            message.id === id ? { ...message, content: message.content + delta } : message,
          );
          const current = conversationOf(state, messages);
          return {
            messages,
            conversations: upsertConversation(state.conversations, current),
          };
        });
      },

      addToolCall: (msgId, name, args) => {
        set((state) => {
          const messages = state.messages.map((message) =>
            message.id === msgId
              ? {
                  ...message,
                  toolCalls: [
                    ...(message.toolCalls ?? []),
                    { id: uid('tool'), name, args, pending: true },
                  ],
                }
              : message,
          );
          const current = conversationOf(state, messages);
          return {
            messages,
            conversations: upsertConversation(state.conversations, current),
          };
        });
        scheduleSync();
      },

      resolveToolCall: (msgId, name, result) => {
        set((state) => {
          const messages = state.messages.map((message) =>
            message.id === msgId
              ? {
                  ...message,
                  toolCalls: (message.toolCalls ?? []).map((toolCall) =>
                    toolCall.name === name && toolCall.pending
                      ? { ...toolCall, result, pending: false }
                      : toolCall,
                  ),
                }
              : message,
          );
          const current = conversationOf(state, messages);
          return {
            messages,
            conversations: upsertConversation(state.conversations, current),
          };
        });
        scheduleSync();
      },

      setToolTrace: (msgId, trace) => {
        const normalized = normalizeToolTrace(trace);
        if (!normalized) return;
        set((state) => {
          const messages = state.messages.map((message) =>
            message.id === msgId ? { ...message, toolTrace: normalized } : message,
          );
          const current = conversationOf(state, messages);
          return {
            messages,
            conversations: upsertConversation(state.conversations, current),
          };
        });
        scheduleSync();
      },

      addActionBlock: (msgId, action) => {
        const actionId = uid('action');
        set((state) => {
          const messages = state.messages.map((message) =>
            message.id === msgId
              ? (() => {
                  const nextAction: ChatActionBlock = {
                    id: actionId,
                    kind: 'action',
                    ...action,
                  };
                  return {
                    ...message,
                    actions: [...(message.actions ?? []), nextAction],
                  };
                })()
              : message,
          );
          const current = conversationOf(state, messages);
          return {
            messages,
            conversations: upsertConversation(state.conversations, current),
          };
        });
        scheduleSync();
        return actionId;
      },

      updateActionBlock: (msgId, actionId, patch) => {
        set((state) => {
          const messages = state.messages.map((message) =>
            message.id === msgId
              ? {
                  ...message,
                  actions: (message.actions ?? []).map((action) =>
                    action.id === actionId ? ({ ...action, ...patch } as ChatActionBlock) : action,
                  ),
                }
              : message,
          );
          const current = conversationOf(state, messages);
          return {
            messages,
            conversations: upsertConversation(state.conversations, current),
          };
        });
        scheduleSync();
      },

      switchConversation: (conversationId) => {
        set((state) => {
          const current =
            state.conversations.find((item) => item.id === conversationId) ??
            createConversationRecord(conversationId);
          return {
            currentConversationId: current.id,
            messages: current.messages,
            conversations: upsertConversation(state.conversations, current),
          };
        });
      },

      createConversation: (input = {}) => {
        const conversation = createConversationRecord(uid('conv'), input);
        set((state) => ({
          currentConversationId: conversation.id,
          messages: [],
          conversations: upsertConversation(state.conversations, conversation),
        }));
        scheduleSync();
        return conversation.id;
      },

      assignConversationWorkspace: (conversationId, workspaceId, fallbackTitle) => {
        set((state) => {
          const existing = state.conversations.find((item) => item.id === conversationId);
          if (!existing) return state;
          const patched = {
            ...existing,
            workspaceId,
            title: existing.title || fallbackTitle || '当前会话',
            updatedAt: nowIso(),
          };
          return {
            conversations: upsertConversation(state.conversations, patched),
          };
        });
        scheduleSync();
      },

      ensureWorkspaceConversation: (workspaceId, title, preferredId) => {
        const trimmedPreferred = preferredId?.trim();
        const state = get();
        const byPreferred = trimmedPreferred
          ? state.conversations.find((item) => item.id === trimmedPreferred)
          : null;
        if (byPreferred) {
          if (byPreferred.workspaceId !== workspaceId) {
            get().assignConversationWorkspace(byPreferred.id, workspaceId, title);
          }
          return byPreferred.id;
        }

        const byWorkspace = state.conversations.find((item) => item.workspaceId === workspaceId);
        if (byWorkspace) {
          return byWorkspace.id;
        }

        return get().createConversation({ title, workspaceId });
      },

      setStreaming: (streaming) => set({ streaming }),
      setConfigLoaded: (configLoaded, hasConfig) => set({ configLoaded, hasConfig }),
      setShowConfig: (showConfig) => set({ showConfig }),

      clearMessages: () => {
        set((state) => {
          const current =
            state.conversations.find((item) => item.id === state.currentConversationId) ??
            createConversationRecord(state.currentConversationId);
          const cleared = {
            ...current,
            messages: [],
            updatedAt: nowIso(),
          };
          return {
            messages: [],
            conversations: upsertConversation(state.conversations, cleared),
          };
        });
        scheduleSync();
      },
    }),
    {
      name: 'aiask-chat',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        messages: state.messages,
        conversations: state.conversations,
        currentConversationId: state.currentConversationId,
      }),
      onRehydrateStorage: () => (state) => {
        if (state) {
          state.syncReady = false;
        }
      },
    },
  ),
);
