import { create } from 'zustand';
import type { CopilotActionMeta, CopilotPageContext, CopilotPageContextPatch } from '@/lib/copilot-types';

export type PendingInject = {
  /** 预填入 Copilot 输入框的问题文本 */
  prompt: string;
  /** 可选：额外的局部上下文 patch，合并到当前 pageContext */
  contextPatch?: CopilotPageContextPatch;
};

type CopilotState = {
  dockOpen: boolean;
  pageContext: CopilotPageContext | null;
  globalActions: CopilotActionMeta[];
  pageActions: CopilotActionMeta[];
  /** AskAiButton 注入的待处理提示，Dock 消费后置 null */
  pendingInject: PendingInject | null;
  nextContextPatch: CopilotPageContextPatch | null;
  setDockOpen: (open: boolean) => void;
  setPageContext: (context: CopilotPageContext) => void;
  clearPageContext: (pageKey?: string) => void;
  setGlobalActions: (actions: CopilotActionMeta[]) => void;
  setPageActions: (actions: CopilotActionMeta[]) => void;
  setPendingInject: (inject: PendingInject | null) => void;
  setNextContextPatch: (patch: CopilotPageContextPatch | null) => void;
};

export const useCopilotStore = create<CopilotState>((set) => ({
  dockOpen: false,
  pageContext: null,
  globalActions: [],
  pageActions: [],
  pendingInject: null,
  nextContextPatch: null,

  setDockOpen: (dockOpen) => set({ dockOpen }),

  setPageContext: (pageContext) => set({ pageContext }),

  clearPageContext: (pageKey) => set((state) => {
    if (!state.pageContext) return state;
    if (pageKey && state.pageContext.pageKey !== pageKey) return state;
    return { pageContext: null, pageActions: [] };
  }),

  setGlobalActions: (globalActions) => set({ globalActions }),
  setPageActions: (pageActions) => set({ pageActions }),
  setPendingInject: (pendingInject) => set({ pendingInject }),
  setNextContextPatch: (nextContextPatch) => set({ nextContextPatch }),
}));
