import type { ResultAction, ResultFreshness, ResultLink } from '@aiask/shared-types';

export type CopilotActionScope = 'global' | 'page';

export type CopilotActionPayload = Record<string, unknown>;

export type CopilotActionMeta = {
  id: string;
  label: string;
  description?: string;
  keywords?: string[];
  scope: CopilotActionScope;
  pageKey?: string;
};

export type CopilotPageContext = {
  pageKey: string;
  title: string;
  summary: string;
  primaryGoal?: string;
  requiredInputs?: string[];
  stockCode?: string;
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
