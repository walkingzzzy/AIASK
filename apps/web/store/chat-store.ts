import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { authedFetch } from '@/lib/api';

export type ChatToolCall = {
  id: string;
  name: string;
  args?: Record<string, unknown>;
  result?: unknown;
  pending?: boolean;
};

export type ChatActionStatus = 'pending' | 'running' | 'done' | 'error';

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

function normalizeActionBlock(input: unknown): ChatActionBlock | null {
  const record = asObject(input);
  const id = String(record.id ?? uid('action')).trim();
  const actionId = String(record.actionId ?? '').trim();
  const label = String(record.label ?? '').trim();
  const status = record.status;
  if (!id || !actionId || !label || !['pending', 'running', 'done', 'error'].includes(String(status))) {
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
    autoExecute: record.autoExecute === true,
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

  return {
    id: String(record.id ?? uid()).trim() || uid(),
    role: role as 'user' | 'assistant',
    content: typeof record.content === 'string' ? record.content : '',
    ...(toolCalls && toolCalls.length > 0 ? { toolCalls } : {}),
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
        const resp = await authedFetch('/chat/conversations');
        const json = await resp.json().catch(() => ({ data: { conversations: [] } }));
        const remote = Array.isArray(json?.data?.conversations)
          ? (json.data.conversations as ChatConversation[])
          : [];
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
        await authedFetch('/chat/conversations/sync', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            conversations: conversations.map((conversation) => ({
              id: conversation.id,
              title: conversation.title,
              updatedAt: conversation.updatedAt,
              workspaceId: conversation.workspaceId,
              messages: conversation.messages.map((message) => ({
                id: message.id,
                role: message.role,
                content: message.content,
                toolCalls: message.toolCalls,
                actions: message.actions,
              })),
            })),
          }),
        });
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
