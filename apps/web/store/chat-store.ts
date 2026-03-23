import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { authedFetch } from '@/lib/api';

export type ChatMsg = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: Array<{ name: string; args?: Record<string, unknown>; result?: unknown; pending?: boolean }>;
};

type ChatConversation = { id: string; title: string; updatedAt: string; messages: ChatMsg[] };

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
  setStreaming: (v: boolean) => void;
  setConfigLoaded: (loaded: boolean, has: boolean) => void;
  setShowConfig: (v: boolean) => void;
  clearMessages: () => void;
  initSync: () => Promise<void>;
  pushToServer: () => Promise<void>;
};

let counter = 0;
const uid = () => `msg_${Date.now()}_${++counter}`;
const conversationOf = (messages: ChatMsg[], id = 'default'): ChatConversation => ({ id, title: '当前会话', updatedAt: new Date().toISOString(), messages });
let syncTimer: number | null = null;
const CHAT_SYNC_INTERVAL_KEY = '__aiaskChatSyncInterval';

function scheduleSync() {
  if (typeof window === 'undefined') return;
  if (syncTimer) window.clearTimeout(syncTimer);
  syncTimer = window.setTimeout(() => { void useChatStore.getState().pushToServer(); }, 2000);
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

export const useChatStore = create<ChatState>()(persist((set, get) => ({
  messages: [], conversations: [], currentConversationId: 'default', streaming: false, configLoaded: false, hasConfig: false, showConfig: false, syncReady: false,

  initSync: async () => {
    if (get().syncReady) return;
    const resp = await authedFetch('/chat/conversations');
    const json = await resp.json().catch(() => ({ data: { conversations: [] } }));
    const remote = Array.isArray(json?.data?.conversations) ? json.data.conversations : [];
    const local = get().conversations.length ? get().conversations : [conversationOf(get().messages, get().currentConversationId)];
    const mergedMap = new Map<string, ChatConversation>();
    [...local, ...remote].forEach((item: ChatConversation) => {
      const prev = mergedMap.get(item.id);
      if (!prev || new Date(item.updatedAt).getTime() >= new Date(prev.updatedAt).getTime()) mergedMap.set(item.id, item);
    });
    const conversations = Array.from(mergedMap.values()).filter((item) => item.messages.length > 0 || item.id === 'default');
    const current = conversations[0] ?? conversationOf([], 'default');
    set({ conversations, currentConversationId: current.id, messages: current.messages, syncReady: true });
    ensureBackgroundSync();
  },

  pushToServer: async () => {
    const conversations = get().conversations.length ? get().conversations : [conversationOf(get().messages, get().currentConversationId)];
    await authedFetch('/chat/conversations/sync', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ conversations }) });
  },

  addUserMessage: (content) => {
    const id = uid();
    set((s) => {
      const nextMessage: ChatMsg = { id, role: 'user', content };
      const messages: ChatMsg[] = [...s.messages, nextMessage];
      const current = conversationOf(messages, s.currentConversationId);
      return { messages, conversations: [current, ...s.conversations.filter((item) => item.id !== current.id)] };
    });
    scheduleSync();
    return id;
  },

  addAssistantMessage: () => {
    const id = uid();
    set((s) => {
      const nextMessage: ChatMsg = { id, role: 'assistant', content: '', toolCalls: [] };
      const messages: ChatMsg[] = [...s.messages, nextMessage];
      const current = conversationOf(messages, s.currentConversationId);
      return { messages, conversations: [current, ...s.conversations.filter((item) => item.id !== current.id)] };
    });
    scheduleSync();
    return id;
  },

  appendAssistantDelta: (id, delta) => {
    set((s) => {
      const messages = s.messages.map((m) => m.id === id ? { ...m, content: m.content + delta } : m);
      const current = conversationOf(messages, s.currentConversationId);
      return { messages, conversations: [current, ...s.conversations.filter((item) => item.id !== current.id)] };
    });
  },

  addToolCall: (msgId, name, args) => {
    set((s) => {
      const messages = s.messages.map((m) => m.id === msgId ? { ...m, toolCalls: [...(m.toolCalls ?? []), { name, args, pending: true }] } : m);
      const current = conversationOf(messages, s.currentConversationId);
      return { messages, conversations: [current, ...s.conversations.filter((item) => item.id !== current.id)] };
    });
  },

  resolveToolCall: (msgId, name, result) => {
    set((s) => {
      const messages = s.messages.map((m) => m.id === msgId ? { ...m, toolCalls: (m.toolCalls ?? []).map((tc) => tc.name === name && tc.pending ? { ...tc, result, pending: false } : tc) } : m);
      const current = conversationOf(messages, s.currentConversationId);
      return { messages, conversations: [current, ...s.conversations.filter((item) => item.id !== current.id)] };
    });
    scheduleSync();
  },

  setStreaming: (v) => set({ streaming: v }),
  setConfigLoaded: (loaded, has) => set({ configLoaded: loaded, hasConfig: has }),
  setShowConfig: (v) => set({ showConfig: v }),
  clearMessages: () => { set({ messages: [], currentConversationId: uid() }); scheduleSync(); },
}), { name: 'aiask-chat', storage: createJSONStorage(() => localStorage), partialize: (s) => ({ messages: s.messages, conversations: s.conversations, currentConversationId: s.currentConversationId }), onRehydrateStorage: () => (state) => { if (state) state.syncReady = false; } }));
