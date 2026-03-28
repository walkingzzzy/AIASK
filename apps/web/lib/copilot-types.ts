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
  stockCode?: string;
  tags?: string[];
  suggestions?: string[];
  raw?: Record<string, unknown>;
  updatedAt: number;
};

export type CopilotActionRequest = CopilotActionMeta & {
  payload?: CopilotActionPayload;
  reason?: string;
  autoExecute?: boolean;
};
