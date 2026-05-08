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

export type CopilotSurfaceModule =
  | 'market'
  | 'research'
  | 'strategy'
  | 'trade'
  | 'ai'
  | 'workspace'
  | 'admin'
  | 'settings'
  | 'system';

export type CopilotSurfaceRoute = {
  pageKey: string;
  path: string;
  module: CopilotSurfaceModule;
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

export type CopilotTaskFlowStep = {
  pageKey: string;
  title: string;
  goal: string;
  requiredContext?: string[];
  nextPageKey?: string;
};

export type CopilotTaskFlow = {
  id: string;
  title: string;
  summary: string;
  steps: CopilotTaskFlowStep[];
};

export type CopilotFrontendContext = {
  generatedAt: number;
  route: string;
  appMap: {
    modules: Array<{ module: CopilotSurfaceModule; title: string; pageKeys: string[] }>;
    routes: Array<Pick<CopilotSurfaceRoute, 'pageKey' | 'path' | 'module' | 'title' | 'summary' | 'aliases' | 'stockAware' | 'adminOnly'>>;
  };
  currentRoute?: CopilotSurfaceRoute;
  relatedRoutes?: CopilotSurfaceRoute[];
  taskFlow?: CopilotTaskFlow & { currentStepIndex?: number };
  workspaceContext?: {
    workspaceId?: string;
    workspaceName?: string;
    stockCode?: string;
    sourcePage?: string;
    taskType?: string;
    resultType?: string;
  };
};

export type CopilotRouteActionPayload = {
  pageKey?: string;
  href?: string;
  code?: string;
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
