import type { ResultAction, ResultFreshness, ResultLink } from '@aiask/shared-types';
import type { ChatToolTraceDto } from './tool-trace';

export type ChatMode = 'chat' | 'copilot' | 'assistant';
export type ClientStrategyActionKind =
  | 'view'
  | 'optimize'
  | 'generate_update_suggestion'
  | 'persist_update';
export type ClientActionEffect = 'readonly' | 'advisory' | 'stateful';
export type FrontendSurfaceModule =
  | 'market'
  | 'research'
  | 'strategy'
  | 'trade'
  | 'ai'
  | 'workspace'
  | 'admin'
  | 'settings'
  | 'system';

export type ChatMessageInput = {
  role: 'user' | 'assistant' | 'system';
  content: string;
};

export type ChatPageContext = {
  pageKey: string;
  title: string;
  summary: string;
  primaryGoal?: string;
  requiredInputs?: string[];
  stockCode?: string;
  selectedCode?: string;
  accountId?: string;
  strategyId?: string;
  workspaceId?: string;
  objectType?: string;
  objectId?: string;
  resultType?: string;
  tags?: string[];
  suggestions?: string[];
  recommendedNextActions?: string[];
  recommendedActions?: ResultAction[];
  recommendedLinks?: ResultLink[];
  evidenceSummary?: string[];
  riskNotes?: string[];
  freshness?: ResultFreshness | null;
  dataFreshness?: string | null;
  degradedReason?: string[];
  raw?: Record<string, unknown>;
};

export type ChatSurfaceRoute = {
  pageKey: string;
  path: string;
  module: FrontendSurfaceModule;
  title: string;
  summary: string;
  primaryGoal: string;
  requiredInputs?: string[];
  coreEntities?: string[];
  dataSources?: string[];
  capabilities?: string[];
  commonQuestions?: string[];
  relatedPageKeys?: string[];
  aliases?: string[];
  stockAware?: boolean;
  codeParam?: string;
  adminOnly?: boolean;
  public?: boolean;
};

export type ChatTaskFlow = {
  id: string;
  title: string;
  summary: string;
  currentStepIndex?: number;
  steps: Array<{
    pageKey: string;
    title: string;
    goal: string;
    requiredContext?: string[];
    nextPageKey?: string;
  }>;
};

export type ChatFrontendContext = {
  generatedAt: number;
  route: string;
  appMap: {
    modules: Array<{ module: FrontendSurfaceModule; title: string; pageKeys: string[] }>;
    routes: Array<Pick<ChatSurfaceRoute, 'pageKey' | 'path' | 'module' | 'title' | 'summary' | 'aliases' | 'stockAware' | 'adminOnly'>>;
  };
  currentRoute?: ChatSurfaceRoute;
  relatedRoutes?: ChatSurfaceRoute[];
  taskFlow?: ChatTaskFlow;
  workspaceContext?: {
    workspaceId?: string;
    workspaceName?: string;
    stockCode?: string;
    sourcePage?: string;
    taskType?: string;
    resultType?: string;
  };
};

export type ClientActionDescriptor = {
  id: string;
  label: string;
  description?: string;
  keywords?: string[];
  scope?: 'global' | 'page';
  pageKey?: string;
  strategyActionKind?: ClientStrategyActionKind;
  mutationEffect?: ClientActionEffect;
};

export type ChatRequestPayload = {
  messages: ChatMessageInput[];
  mode?: ChatMode;
  pageContext?: ChatPageContext | null;
  frontendContext?: ChatFrontendContext | null;
  availableActions?: ClientActionDescriptor[];
};

export type ChatEvent =
  | { type: 'delta'; content: string }
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | { type: 'tool_result'; name: string; result: unknown }
  | { type: 'tool_trace'; trace: ChatToolTraceDto }
  | { type: 'action'; actionId: string; label: string; description?: string; reason?: string; payload?: Record<string, unknown>; autoExecute?: boolean }
  | { type: 'heartbeat'; at: string; scope?: string }
  | { type: 'final_fallback'; content: string }
  | { type: 'error'; message: string }
  | { type: 'done' };
