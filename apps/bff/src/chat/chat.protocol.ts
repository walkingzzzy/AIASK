import type { ResultAction, ResultFreshness, ResultLink } from '@aiask/shared-types';
import type { ChatToolTraceDto } from './tool-trace';

export type ChatMode = 'chat' | 'copilot' | 'assistant';
export type ClientStrategyActionKind =
  | 'view'
  | 'optimize'
  | 'generate_update_suggestion'
  | 'persist_update';
export type ClientActionEffect = 'readonly' | 'advisory' | 'stateful';

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
