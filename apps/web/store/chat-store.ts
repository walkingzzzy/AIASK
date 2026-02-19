import { create } from 'zustand';

export type ChatMsg = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: Array<{ name: string; args?: Record<string, unknown>; result?: unknown; pending?: boolean }>;
};

type ChatState = {
  messages: ChatMsg[];
  streaming: boolean;
  configLoaded: boolean;
  hasConfig: boolean;
  showConfig: boolean;
  addUserMessage: (content: string) => string;
  appendAssistantDelta: (id: string, delta: string) => void;
  addAssistantMessage: () => string;
  addToolCall: (msgId: string, name: string, args: Record<string, unknown>) => void;
  resolveToolCall: (msgId: string, name: string, result: unknown) => void;
  setStreaming: (v: boolean) => void;
  setConfigLoaded: (loaded: boolean, has: boolean) => void;
  setShowConfig: (v: boolean) => void;
  clearMessages: () => void;
};

let counter = 0;
const uid = () => `msg_${Date.now()}_${++counter}`;

export const useChatStore = create<ChatState>((set, _get) => ({
  messages: [],
  streaming: false,
  configLoaded: false,
  hasConfig: false,
  showConfig: false,

  addUserMessage: (content) => {
    const id = uid();
    set((s) => ({ messages: [...s.messages, { id, role: 'user', content }] }));
    return id;
  },

  addAssistantMessage: () => {
    const id = uid();
    set((s) => ({ messages: [...s.messages, { id, role: 'assistant', content: '', toolCalls: [] }] }));
    return id;
  },

  appendAssistantDelta: (id, delta) => {
    set((s) => ({
      messages: s.messages.map((m) => m.id === id ? { ...m, content: m.content + delta } : m),
    }));
  },

  addToolCall: (msgId, name, args) => {
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === msgId ? { ...m, toolCalls: [...(m.toolCalls ?? []), { name, args, pending: true }] } : m,
      ),
    }));
  },

  resolveToolCall: (msgId, name, result) => {
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === msgId
          ? { ...m, toolCalls: (m.toolCalls ?? []).map((tc) => tc.name === name && tc.pending ? { ...tc, result, pending: false } : tc) }
          : m,
      ),
    }));
  },

  setStreaming: (v) => set({ streaming: v }),
  setConfigLoaded: (loaded, has) => set({ configLoaded: loaded, hasConfig: has }),
  setShowConfig: (v) => set({ showConfig: v }),
  clearMessages: () => set({ messages: [] }),
}));
