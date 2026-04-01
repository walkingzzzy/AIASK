import type {
  WorkspaceLayoutPreset,
  WorkspacePageKey,
  WorkspaceSharedContext,
  WorkspaceStateSnapshot,
  WorkspaceTask,
  WorkspaceTaskStatus,
} from '@aiask/shared-types';

export type WorkspaceContextPatch = Partial<{
  [K in keyof WorkspaceSharedContext]: WorkspaceSharedContext[K] | null;
}>;

export type WorkspaceContextOverrides = Partial<{
  [K in keyof WorkspaceSharedContext]: WorkspaceSharedContext[K] | string | number | null | undefined;
}>;

export type WorkspaceTemplateFieldDefinition = {
  key: keyof WorkspaceSharedContext;
  label: string;
  description?: string;
  input: 'text' | 'number' | 'select';
  placeholder?: string;
  min?: number;
  max?: number;
  options?: Array<{
    value: string;
    label: string;
  }>;
};

export type WorkspaceBlueprintId = 'stock-research' | 'execution-pulse' | 'portfolio-review';
export type WorkspaceTaskTemplateId = 'research-flow' | 'execution-followup' | 'portfolio-audit';
export type WorkspaceTemplateDefaultsStrategy = 'override' | 'fill-missing' | 'strict';
export type WorkspaceTemplateWorkflowId = 'research-command' | 'execution-command' | 'portfolio-command';

export type WorkspaceTaskTemplateStep = {
  pageKey: WorkspacePageKey;
  title: string | ((context: WorkspaceSharedContext) => string);
  href?: string | ((context: WorkspaceSharedContext) => string | null);
  kind?: string;
  payload?: Record<string, unknown> | ((context: WorkspaceSharedContext) => Record<string, unknown> | undefined);
  status?: WorkspaceTaskStatus;
};

export type WorkspaceTaskTemplateDefinition = {
  id: WorkspaceTaskTemplateId;
  label: string;
  description: string;
  fields?: WorkspaceTemplateFieldDefinition[];
  steps: WorkspaceTaskTemplateStep[];
};

export type WorkspaceTemplateWorkflowStep = {
  id: string;
  label: string;
  description: string;
  kind: 'blueprint' | 'task-template';
  blueprintId?: WorkspaceBlueprintId;
  templateId?: WorkspaceTaskTemplateId;
  dependsOn?: string[];
  requiredAll?: Array<keyof WorkspaceSharedContext>;
  requiredAny?: Array<keyof WorkspaceSharedContext>;
  defaultsStrategy?: WorkspaceTemplateDefaultsStrategy;
  condition?: (context: WorkspaceSharedContext) => boolean;
  conditionDescription?: string;
  fields?: WorkspaceTemplateFieldDefinition[];
  overrides?: WorkspaceContextOverrides | ((context: WorkspaceSharedContext) => WorkspaceContextOverrides | undefined);
};

export type WorkspaceTemplateWorkflowDefinition = {
  id: WorkspaceTemplateWorkflowId;
  label: string;
  description: string;
  fields?: WorkspaceTemplateFieldDefinition[];
  steps: WorkspaceTemplateWorkflowStep[];
};

export type WorkspaceBlueprintDefinition = {
  id: WorkspaceBlueprintId;
  label: string;
  description: string;
  layoutPreset: WorkspaceLayoutPreset;
  taskTemplateId: WorkspaceTaskTemplateId;
  fields?: WorkspaceTemplateFieldDefinition[];
  workspaceName: (context: WorkspaceSharedContext) => string;
  context?: (context: WorkspaceSharedContext) => WorkspaceSharedContext;
};

export type WorkspaceTaskPreview = {
  pageKey: WorkspacePageKey;
  title: string;
  href?: string;
  kind?: string;
  payload?: Record<string, unknown>;
  status: WorkspaceTaskStatus;
};

export type WorkspaceTemplateWorkflowPreviewStep = {
  id: string;
  label: string;
  description: string;
  kind: 'blueprint' | 'task-template';
  targetId: WorkspaceBlueprintId | WorkspaceTaskTemplateId;
  targetLabel: string;
  defaultsStrategy: WorkspaceTemplateDefaultsStrategy;
  dependsOn: string[];
  requiredAll: Array<keyof WorkspaceSharedContext>;
  requiredAny: Array<keyof WorkspaceSharedContext>;
  status: 'ready' | 'blocked' | 'skipped';
  reason?: string;
  context: WorkspaceSharedContext;
  workspaceName?: string;
  layoutPreset?: WorkspaceLayoutPreset;
  taskTemplateId?: WorkspaceTaskTemplateId;
  steps: WorkspaceTaskPreview[];
};

export type WorkspaceTemplateWorkflowPreview = {
  context: WorkspaceSharedContext;
  workspaceName?: string;
  createdWorkspaceCount: number;
  executableStepCount: number;
  blockedStepCount: number;
  skippedStepCount: number;
  steps: WorkspaceTemplateWorkflowPreviewStep[];
};

export type WorkspaceTemplateRunKind = 'blueprint' | 'task-template' | 'workflow';
export type WorkspaceTemplateRunStatus = 'applied' | 'rolled-back';

export type WorkspaceTemplateRunRecord = {
  id: string;
  kind: WorkspaceTemplateRunKind;
  status: WorkspaceTemplateRunStatus;
  targetId: WorkspaceBlueprintId | WorkspaceTaskTemplateId | WorkspaceTemplateWorkflowId;
  label: string;
  summary: string;
  context: WorkspaceSharedContext;
  targetWorkspaceId: string | null;
  createdWorkspaceIds: string[];
  taskIds: string[];
  appliedStepIds: string[];
  blockedStepIds: string[];
  skippedStepIds: string[];
  createdAt: number;
  updatedAt: number;
  rolledBackAt?: number;
  rollbackSnapshot?: WorkspaceStateSnapshot;
};

export type ApplyTemplateWorkflowResult = {
  workflowId: WorkspaceTemplateWorkflowId;
  createdWorkspaceIds: string[];
  targetWorkspaceId: string | null;
  taskIds: string[];
  appliedStepIds: string[];
  skippedStepIds: string[];
  blockedStepIds: string[];
};

export type WorkspaceTemplateTaskBuilder = (
  templateId: WorkspaceTaskTemplateId,
  context: WorkspaceSharedContext,
  timestamp: number,
  makeId: (prefix: string) => string,
) => WorkspaceTask[];
