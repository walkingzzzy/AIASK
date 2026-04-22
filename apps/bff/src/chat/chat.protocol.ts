import type { ResultAction, ResultFreshness, ResultLink } from '@aiask/shared-types';

export type ChatMode = 'chat' | 'copilot' | 'assistant';

export type ChatMessageInput = {
  role: 'user' | 'assistant' | 'system';
  content: string;
};

export type ChatPageContext = {
  pageKey: string;
  title: string;
  summary: string;
  stockCode?: string;
  objectType?: string;
  objectId?: string;
  resultType?: string;
  tags?: string[];
  suggestions?: string[];
  recommendedActions?: ResultAction[];
  recommendedLinks?: ResultLink[];
  evidenceSummary?: string[];
  riskNotes?: string[];
  freshness?: ResultFreshness | null;
  raw?: Record<string, unknown>;
};

export type ClientActionDescriptor = {
  id: string;
  label: string;
  description?: string;
  keywords?: string[];
  scope?: 'global' | 'page';
  pageKey?: string;
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
  | { type: 'action'; actionId: string; label: string; description?: string; reason?: string; payload?: Record<string, unknown>; autoExecute?: boolean }
  | { type: 'error'; message: string }
  | { type: 'done' };
