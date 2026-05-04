import type { ResultAction, ResultFreshness, ResultLink } from '@aiask/shared-types';

export type CopilotActionScope = 'global' | 'page';

export type CopilotActionPayload = Record<string, unknown>;

export type CopilotStrategyActionKind =
  | 'view'
  | 'optimize'
  | 'generate_update_suggestion'
  | 'persist_update';

export type CopilotActionEffect = 'readonly' | 'advisory' | 'stateful';
export type CopilotActionDisplayStatus = 'pending' | 'scheduled' | 'auto_executed' | 'running' | 'done' | 'error';

export type CopilotActionMeta = {
  id: string;
  label: string;
  description?: string;
  keywords?: string[];
  scope: CopilotActionScope;
  pageKey?: string;
  strategyActionKind?: CopilotStrategyActionKind;
  mutationEffect?: CopilotActionEffect;
};

export type CopilotPageContext = {
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
  updatedAt: number;
};

export type CopilotPageContextPatch = Partial<
  Pick<
    CopilotPageContext,
    | 'primaryGoal'
    | 'requiredInputs'
    | 'stockCode'
    | 'selectedCode'
    | 'accountId'
    | 'strategyId'
    | 'workspaceId'
    | 'pageKey'
    | 'title'
    | 'summary'
    | 'objectType'
    | 'objectId'
    | 'resultType'
    | 'recommendedNextActions'
    | 'recommendedActions'
    | 'recommendedLinks'
    | 'evidenceSummary'
    | 'riskNotes'
    | 'freshness'
    | 'dataFreshness'
    | 'degradedReason'
    | 'raw'
    | 'tags'
  >
>;

export type CopilotActionRequest = CopilotActionMeta & {
  payload?: CopilotActionPayload;
  reason?: string;
  autoExecute?: boolean;
};
