import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { authedFetch, extractApiErrorMessage, unwrapApiEnvelope } from '@/lib/api';
import type {
  WorkspaceLayout,
  WorkspaceLayoutPreset,
  WorkspacePagePanelLayout,
  WorkspacePagePanelMode,
  WorkspacePageKey,
  WorkspaceRecord,
  WorkspaceSharedContext,
  WorkspaceStateSnapshot,
  WorkspaceTask,
  WorkspaceTaskStatus,
} from '@aiask/shared-types';

export type {
  WorkspaceLayout,
  WorkspaceLayoutDensity,
  WorkspaceLayoutPreset,
  WorkspacePagePanelLayout,
  WorkspacePagePanelMode,
  WorkspacePagePanelPlacement,
  WorkspacePageKey,
  WorkspaceRecord,
  WorkspaceSavedView,
  WorkspaceSharedContext,
  WorkspaceStateSnapshot,
  WorkspaceTask,
  WorkspaceTaskStatus,
} from '@aiask/shared-types';

export type WorkspaceContextPatch = Partial<{
  [K in keyof WorkspaceSharedContext]: WorkspaceSharedContext[K] | null;
}>;

type AddTaskInput = {
  pageKey: WorkspacePageKey;
  title: string;
  href?: string;
  kind?: string;
  payload?: Record<string, unknown>;
  status?: WorkspaceTaskStatus;
};

type LayoutPatch = Partial<WorkspaceLayout>;
type PagePanelPatch = Partial<WorkspacePagePanelLayout>;

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

type WorkspaceTaskTemplateStep = {
  pageKey: WorkspacePageKey;
  title: string | ((context: WorkspaceSharedContext) => string);
  href?: string | ((context: WorkspaceSharedContext) => string | null);
  kind?: string;
  payload?: Record<string, unknown> | ((context: WorkspaceSharedContext) => Record<string, unknown> | undefined);
  status?: WorkspaceTaskStatus;
};

type WorkspaceTaskTemplateDefinition = {
  id: WorkspaceTaskTemplateId;
  label: string;
  description: string;
  fields?: WorkspaceTemplateFieldDefinition[];
  steps: WorkspaceTaskTemplateStep[];
};

type WorkspaceTemplateWorkflowStep = {
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

type WorkbenchState = {
  hydrated: boolean;
  remoteReady: boolean;
  syncing: boolean;
  lastSyncedAt: string | null;
  activeWorkspaceId: string;
  workspaces: WorkspaceRecord[];
  templateRuns: WorkspaceTemplateRunRecord[];
  setHydrated: (hydrated: boolean) => void;
  replaceSnapshot: (snapshot: WorkspaceStateSnapshot) => void;
  createWorkspace: (name?: string) => string;
  renameWorkspace: (id: string, name: string) => void;
  switchWorkspace: (id: string) => void;
  updateLayout: (patch: LayoutPatch) => void;
  applyLayoutPreset: (preset: WorkspaceLayoutPreset) => void;
  resetLayout: () => void;
  updatePagePanel: (pageKey: WorkspacePageKey, patch: PagePanelPatch) => void;
  resetPagePanel: (pageKey: WorkspacePageKey) => void;
  createWorkspaceFromBlueprint: (blueprintId: WorkspaceBlueprintId, overrides?: WorkspaceContextOverrides) => string;
  applyTaskTemplate: (templateId: WorkspaceTaskTemplateId, overrides?: WorkspaceContextOverrides) => string[];
  applyTemplateWorkflow: (
    workflowId: WorkspaceTemplateWorkflowId,
    overrides?: WorkspaceContextOverrides,
  ) => ApplyTemplateWorkflowResult;
  rollbackTemplateRun: (runId: string) => boolean;
  clearTemplateRuns: () => void;
  updateContext: (patch: WorkspaceContextPatch) => void;
  replaceContext: (next: WorkspaceSharedContext) => void;
  saveView: (pageKey: WorkspacePageKey, name: string, snapshot: Record<string, unknown>) => string;
  deleteView: (pageKey: WorkspacePageKey, viewId: string) => void;
  addTask: (input: AddTaskInput) => string;
  updateTask: (taskId: string, patch: Partial<Omit<WorkspaceTask, 'id' | 'createdAt'>>) => void;
  removeTask: (taskId: string) => void;
  clearDoneTasks: () => void;
  syncFromServer: () => Promise<void>;
  pushToServer: () => Promise<void>;
};

const STORAGE_KEY = 'aiask.workbench.v1';
const DEFAULT_WORKSPACE_ID = 'default-workspace';
const WORKSPACE_PATH = '/workspace/state';

export const WORKSPACE_LAYOUT_PRESETS: Record<WorkspaceLayoutPreset, WorkspaceLayout> = {
  research: {
    preset: 'research',
    navCollapsed: false,
    navWidth: 208,
    dockVisible: false,
    dockWidth: 380,
    density: 'comfortable',
    pageWidth: 'wide',
  },
  trading: {
    preset: 'trading',
    navCollapsed: false,
    navWidth: 220,
    dockVisible: false,
    dockWidth: 430,
    density: 'compact',
    pageWidth: 'wide',
  },
  focus: {
    preset: 'focus',
    navCollapsed: true,
    navWidth: 208,
    dockVisible: false,
    dockWidth: 360,
    density: 'comfortable',
    pageWidth: 'focused',
  },
  custom: {
    preset: 'custom',
    navCollapsed: false,
    navWidth: 208,
    dockVisible: false,
    dockWidth: 380,
    density: 'comfortable',
    pageWidth: 'wide',
  },
};

const DEFAULT_WORKSPACE_LAYOUT = WORKSPACE_LAYOUT_PRESETS.research;
const DEFAULT_PAGE_PANEL_LAYOUT: WorkspacePagePanelLayout = {
  mode: 'single',
  secondaryPlacement: 'right',
  secondarySize: 34,
};

const STOCK_CODE_FIELD: WorkspaceTemplateFieldDefinition = {
  key: 'stockCode',
  label: '股票代码',
  description: '单票研究、执行与事件联动的主标的。',
  input: 'text',
  placeholder: '如 600519',
};

const EVENT_CODE_FIELD: WorkspaceTemplateFieldDefinition = {
  key: 'eventCode',
  label: '事件代码',
  description: '不填时默认继承股票代码。',
  input: 'text',
  placeholder: '默认跟随股票代码',
};

const ACCOUNT_ID_FIELD: WorkspaceTemplateFieldDefinition = {
  key: 'accountId',
  label: '账户 ID',
  description: '执行、绩效和 artifact 联动时会带入账户上下文。',
  input: 'text',
  placeholder: '如 default',
};

const EXECUTION_ID_FIELD: WorkspaceTemplateFieldDefinition = {
  key: 'executionId',
  label: '执行单号',
  description: '用于执行复盘、风险与绩效联动。',
  input: 'text',
  placeholder: '如 exec_xxx',
};

const ARTIFACT_ID_FIELD: WorkspaceTemplateFieldDefinition = {
  key: 'artifactId',
  label: 'Artifact ID',
  description: '用于直接跳转执行产物详情。',
  input: 'text',
  placeholder: '如 art_demo_001',
};

const PORTFOLIO_ID_FIELD: WorkspaceTemplateFieldDefinition = {
  key: 'portfolioId',
  label: '组合 ID',
  description: '用于组合风险、绩效和事件巡检联动。',
  input: 'text',
  placeholder: '如 1',
};

const BENCHMARK_FIELD: WorkspaceTemplateFieldDefinition = {
  key: 'benchmark',
  label: '基准代码',
  description: '组合绩效默认基准，不填时使用 000300。',
  input: 'text',
  placeholder: '如 000300',
};

const MODE_FIELD: WorkspaceTemplateFieldDefinition = {
  key: 'mode',
  label: '绩效模式',
  description: '选择账户绩效还是组合绩效联动方式。',
  input: 'select',
  options: [
    { value: 'account', label: '账户' },
    { value: 'portfolio', label: '组合' },
  ],
};

const DAYS_FIELD: WorkspaceTemplateFieldDefinition = {
  key: 'days',
  label: '绩效窗口',
  description: '绩效页默认观察窗口，单位天。',
  input: 'number',
  min: 7,
  max: 720,
  placeholder: '如 30',
};

const LOOKBACK_DAYS_FIELD: WorkspaceTemplateFieldDefinition = {
  key: 'lookbackDays',
  label: '风险窗口',
  description: '风险页默认回看天数，单位天。',
  input: 'number',
  min: 30,
  max: 720,
  placeholder: '如 90',
};

const RESEARCH_TEMPLATE_FIELDS = [STOCK_CODE_FIELD, EVENT_CODE_FIELD, ACCOUNT_ID_FIELD];
const EXECUTION_TEMPLATE_FIELDS = [
  STOCK_CODE_FIELD,
  ACCOUNT_ID_FIELD,
  EXECUTION_ID_FIELD,
  ARTIFACT_ID_FIELD,
  PORTFOLIO_ID_FIELD,
  MODE_FIELD,
  DAYS_FIELD,
  LOOKBACK_DAYS_FIELD,
  BENCHMARK_FIELD,
];
const PORTFOLIO_TEMPLATE_FIELDS = [
  PORTFOLIO_ID_FIELD,
  BENCHMARK_FIELD,
  STOCK_CODE_FIELD,
  EVENT_CODE_FIELD,
  DAYS_FIELD,
  LOOKBACK_DAYS_FIELD,
];

function mergeFieldDefinitions(...groups: Array<WorkspaceTemplateFieldDefinition[] | undefined>) {
  const fieldMap = new Map<keyof WorkspaceSharedContext, WorkspaceTemplateFieldDefinition>();
  groups.forEach((group) => {
    group?.forEach((field) => {
      if (!fieldMap.has(field.key)) {
        fieldMap.set(field.key, field);
      }
    });
  });
  return Array.from(fieldMap.values());
}
const WORKSPACE_CONTEXT_KEYS: Array<keyof WorkspaceSharedContext> = [
  'stockCode',
  'accountId',
  'executionId',
  'artifactId',
  'copilotConversationId',
  'portfolioId',
  'benchmark',
  'mode',
  'days',
  'lookbackDays',
  'eventCode',
  'strategyId',
  'strategyName',
];

function buildPath(pathname: string, params: Record<string, string | number | null | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value == null || value === '') return;
    search.set(key, String(value));
  });
  const query = search.toString();
  return query ? `${pathname}?${query}` : pathname;
}

function normalizeWorkspaceContextValue(
  key: keyof WorkspaceSharedContext,
  value: WorkspaceContextOverrides[keyof WorkspaceContextOverrides],
): WorkspaceSharedContext[keyof WorkspaceSharedContext] | null {
  if (value == null) return null;

  if (key === 'days' || key === 'lookbackDays') {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) return null;
    return Math.trunc(parsed);
  }

  if (key === 'mode') {
    return value === 'portfolio' ? 'portfolio' : value === 'account' ? 'account' : null;
  }

  const normalized = String(value).trim();
  return normalized ? normalized : null;
}

export function normalizeWorkspaceContextOverrides(
  overrides?: WorkspaceContextOverrides | null,
): WorkspaceContextPatch {
  if (!overrides) return {};

  return WORKSPACE_CONTEXT_KEYS.reduce<WorkspaceContextPatch>((acc, key) => {
    if (!(key in overrides)) return acc;
    const normalizedValue = normalizeWorkspaceContextValue(key, overrides[key]);
    (acc as Record<string, unknown>)[key] = normalizedValue;
    return acc;
  }, {});
}

export function pickWorkspaceContextOverrides(
  overrides: WorkspaceContextOverrides | null | undefined,
  fields: WorkspaceTemplateFieldDefinition[] | undefined,
): WorkspaceContextOverrides {
  if (!overrides || !fields?.length) return {};
  const allowedKeys = new Set(fields.map((field) => field.key));
  return Object.entries(overrides).reduce<WorkspaceContextOverrides>((acc, [key, value]) => {
    if (allowedKeys.has(key as keyof WorkspaceSharedContext)) {
      acc[key as keyof WorkspaceSharedContext] = value;
    }
    return acc;
  }, {});
}

function resolveTemplateContext(context: WorkspaceSharedContext): WorkspaceSharedContext {
  return {
    ...context,
    eventCode: context.eventCode ?? context.stockCode,
    mode: context.mode ?? (context.portfolioId ? 'portfolio' : 'account'),
    days: typeof context.days === 'number' && context.days > 0 ? context.days : 30,
    lookbackDays: typeof context.lookbackDays === 'number' && context.lookbackDays > 0 ? context.lookbackDays : 90,
  };
}

export function resolveWorkspaceTemplateContext(
  context: WorkspaceSharedContext,
  overrides?: WorkspaceContextOverrides,
): WorkspaceSharedContext {
  return resolveTemplateContext(applyContextPatch(context, normalizeWorkspaceContextOverrides(overrides)));
}

function applyDefaultsStrategy(
  context: WorkspaceSharedContext,
  patch: WorkspaceContextPatch,
  defaultsStrategy: WorkspaceTemplateDefaultsStrategy,
) {
  if (defaultsStrategy === 'fill-missing') {
    const filteredPatch = Object.entries(patch).reduce<WorkspaceContextPatch>((acc, [key, value]) => {
      const currentValue = context[key as keyof WorkspaceSharedContext];
      if ((currentValue == null || currentValue === '') && value != null) {
        (acc as Record<string, unknown>)[key] = value;
      }
      return acc;
    }, {});
    return applyContextPatch(context, filteredPatch);
  }

  return applyContextPatch(context, patch);
}

function missingRequiredContext(
  context: WorkspaceSharedContext,
  requiredAll: Array<keyof WorkspaceSharedContext>,
  requiredAny: Array<keyof WorkspaceSharedContext>,
) {
  const missingAll = requiredAll.filter((key) => {
    const value = context[key];
    return value == null || value === '';
  });

  if (missingAll.length > 0) {
    return `缺少 ${missingAll.join(' / ')} 上下文`;
  }

  if (requiredAny.length > 0) {
    const hasAny = requiredAny.some((key) => {
      const value = context[key];
      return value != null && value !== '';
    });
    if (!hasAny) {
      return `至少需要 ${requiredAny.join(' / ')} 其中一项`;
    }
  }

  return null;
}

function renderWorkflowStepOverrides(
  overrides: WorkspaceTemplateWorkflowStep['overrides'],
  context: WorkspaceSharedContext,
) {
  if (!overrides) return undefined;
  return typeof overrides === 'function' ? overrides(context) : overrides;
}

function buildPerformanceHref(context: WorkspaceSharedContext) {
  const resolved = resolveTemplateContext(context);
  if (resolved.mode === 'portfolio' || resolved.portfolioId) {
    return buildPath('/performance', {
      mode: 'portfolio',
      portfolio_id: resolved.portfolioId,
      benchmark: resolved.benchmark ?? '000300',
      days: resolved.days ?? 30,
      execution_id: resolved.executionId,
    });
  }
  return buildPath('/performance', {
    mode: 'account',
    account_id: resolved.accountId,
    days: resolved.days ?? 30,
    execution_id: resolved.executionId,
  });
}

function buildRiskHref(context: WorkspaceSharedContext) {
  const resolved = resolveTemplateContext(context);
  return buildPath('/risk', {
    portfolioId: resolved.portfolioId,
    lookbackDays: resolved.lookbackDays ?? 90,
  });
}

function buildExecutionHref(context: WorkspaceSharedContext) {
  const resolved = resolveTemplateContext(context);
  return buildPath('/execution', {
    code: resolved.stockCode,
    account_id: resolved.accountId,
    execution_id: resolved.executionId,
    artifact_id: resolved.artifactId,
  });
}

function buildArtifactHref(context: WorkspaceSharedContext) {
  if (!context.artifactId) return null;
  return buildPath(`/execution/artifacts/${encodeURIComponent(context.artifactId)}`, {
    account_id: context.accountId,
  });
}

export const WORKSPACE_TASK_TEMPLATES: Record<WorkspaceTaskTemplateId, WorkspaceTaskTemplateDefinition> = {
  'research-flow': {
    id: 'research-flow',
    label: '研究到执行',
    description: '从行情、事件、研究一路推进到决策和执行，适合单票深度研究。',
    fields: RESEARCH_TEMPLATE_FIELDS,
    steps: [
      {
        pageKey: 'market',
        title: (context) => `检查 ${context.stockCode ?? '目标股票'} 的行情面板`,
        href: (context) => buildPath('/market', { code: context.stockCode }),
        kind: 'market-scan',
      },
      {
        pageKey: 'research',
        title: (context) => `整理 ${context.stockCode ?? '目标股票'} 的研报公告`,
        href: (context) => buildPath('/research', { code: context.stockCode }),
        kind: 'research-review',
      },
      {
        pageKey: 'events',
        title: (context) => `跟踪 ${context.eventCode ?? context.stockCode ?? '目标股票'} 的重要事件`,
        href: (context) => buildPath('/events', { code: context.eventCode ?? context.stockCode }),
        kind: 'event-watch',
      },
      {
        pageKey: 'decision',
        title: (context) => `形成 ${context.stockCode ?? '目标股票'} 的决策结论`,
        href: (context) => buildPath('/decision', { code: context.stockCode }),
        kind: 'decision-review',
      },
      {
        pageKey: 'execution',
        title: (context) => `准备 ${context.stockCode ?? '目标股票'} 的执行方案`,
        href: (context) => buildExecutionHref(context),
        kind: 'execution-plan',
      },
    ],
  },
  'execution-followup': {
    id: 'execution-followup',
    label: '执行复盘',
    description: '围绕执行任务继续查看 artifact、风险和绩效，适合盘中与盘后追踪。',
    fields: EXECUTION_TEMPLATE_FIELDS,
    steps: [
      {
        pageKey: 'execution',
        title: (context) => (context.executionId ? `跟踪执行 ${context.executionId}` : '打开执行中心'),
        href: (context) => buildExecutionHref(context),
        kind: 'execution-review',
      },
      {
        pageKey: 'execution',
        title: (context) => (context.artifactId ? `查看 artifact ${context.artifactId}` : '查看最近 artifact'),
        href: (context) => buildArtifactHref(context),
        kind: 'artifact-review',
      },
      {
        pageKey: 'risk',
        title: '核查风险暴露与异常来源',
        href: (context) => buildRiskHref(context),
        kind: 'risk-review',
        payload: (context) => ({
          portfolioId: context.portfolioId,
          lookbackDays: context.lookbackDays ?? 90,
        }),
      },
      {
        pageKey: 'performance',
        title: '查看执行后的绩效表现',
        href: (context) => buildPerformanceHref(context),
        kind: 'performance-review',
      },
    ],
  },
  'portfolio-audit': {
    id: 'portfolio-audit',
    label: '组合巡检',
    description: '围绕组合、风险、绩效做固定节奏的巡检和复盘。',
    fields: PORTFOLIO_TEMPLATE_FIELDS,
    steps: [
      {
        pageKey: 'portfolio',
        title: (context) => (context.portfolioId ? `核对组合 ${context.portfolioId}` : '查看组合列表'),
        href: '/portfolio',
        kind: 'portfolio-review',
      },
      {
        pageKey: 'risk',
        title: '刷新组合风险窗口',
        href: (context) =>
          buildRiskHref({
            ...context,
            mode: 'portfolio',
          }),
        kind: 'risk-review',
      },
      {
        pageKey: 'performance',
        title: '复盘组合归因与基准对比',
        href: (context) =>
          buildPerformanceHref({
            ...context,
            mode: 'portfolio',
          }),
        kind: 'performance-review',
      },
      {
        pageKey: 'events',
        title: '检查组合相关事件与催化',
        href: (context) => buildPath('/events', { code: context.eventCode ?? context.stockCode }),
        kind: 'event-watch',
      },
    ],
  },
};

export const WORKSPACE_BLUEPRINTS: Record<WorkspaceBlueprintId, WorkspaceBlueprintDefinition> = {
  'stock-research': {
    id: 'stock-research',
    label: '单票研究工作区',
    description: '偏研究布局，自动生成行情-研究-事件-决策-执行链路。',
    layoutPreset: 'research',
    taskTemplateId: 'research-flow',
    fields: RESEARCH_TEMPLATE_FIELDS,
    workspaceName: (context) => (context.stockCode ? `${context.stockCode} 研究` : '单票研究'),
    context: (context) => ({
      ...resolveTemplateContext(context),
      eventCode: context.eventCode ?? context.stockCode,
    }),
  },
  'execution-pulse': {
    id: 'execution-pulse',
    label: '执行追踪工作区',
    description: '偏交易布局，适合盯执行任务、artifact、风险和绩效。',
    layoutPreset: 'trading',
    taskTemplateId: 'execution-followup',
    fields: EXECUTION_TEMPLATE_FIELDS,
    workspaceName: (context) => (context.executionId ? `执行 ${context.executionId}` : '执行追踪'),
    context: (context) => ({
      ...resolveTemplateContext(context),
      mode: context.portfolioId ? 'portfolio' : 'account',
    }),
  },
  'portfolio-review': {
    id: 'portfolio-review',
    label: '组合复盘工作区',
    description: '偏聚焦布局，围绕组合风险、绩效和事件做固定巡检。',
    layoutPreset: 'focus',
    taskTemplateId: 'portfolio-audit',
    fields: PORTFOLIO_TEMPLATE_FIELDS,
    workspaceName: (context) => (context.portfolioId ? `组合 ${context.portfolioId} 复盘` : '组合复盘'),
    context: (context) => ({
      ...resolveTemplateContext(context),
      mode: 'portfolio',
    }),
  },
};

export const WORKSPACE_TEMPLATE_WORKFLOWS: Record<WorkspaceTemplateWorkflowId, WorkspaceTemplateWorkflowDefinition> = {
  'research-command': {
    id: 'research-command',
    label: '研究指挥流',
    description: '先创建单票研究工作区，再按上下文续接执行复盘和组合巡检。',
    fields: mergeFieldDefinitions(RESEARCH_TEMPLATE_FIELDS, EXECUTION_TEMPLATE_FIELDS, PORTFOLIO_TEMPLATE_FIELDS),
    steps: [
      {
        id: 'research-workspace',
        label: '创建研究工作区',
        description: '以单票研究模板作为起点，生成基础工作区和首批研究任务。',
        kind: 'blueprint',
        blueprintId: 'stock-research',
        requiredAll: ['stockCode'],
        defaultsStrategy: 'override',
      },
      {
        id: 'research-execution-followup',
        label: '续接执行复盘',
        description: '在研究工作区里补执行、artifact、风险和绩效追踪任务。',
        kind: 'task-template',
        templateId: 'execution-followup',
        dependsOn: ['research-workspace'],
        requiredAny: ['accountId', 'executionId', 'artifactId', 'portfolioId'],
        defaultsStrategy: 'fill-missing',
        condition: (context) =>
          Boolean(context.accountId || context.executionId || context.artifactId || context.portfolioId),
        conditionDescription: '仅当已有账户、执行、artifact 或组合上下文时续接执行复盘。',
      },
      {
        id: 'research-portfolio-audit',
        label: '补组合巡检',
        description: '如果已经有组合上下文，继续补组合风险、绩效与事件巡检。',
        kind: 'task-template',
        templateId: 'portfolio-audit',
        dependsOn: ['research-workspace'],
        requiredAll: ['portfolioId'],
        defaultsStrategy: 'fill-missing',
        condition: (context) => Boolean(context.portfolioId),
        conditionDescription: '仅当提供组合 ID 时补充组合巡检。',
      },
    ],
  },
  'execution-command': {
    id: 'execution-command',
    label: '执行指挥流',
    description: '先创建执行追踪工作区，再串行补研究链路与组合巡检。',
    fields: mergeFieldDefinitions(EXECUTION_TEMPLATE_FIELDS, RESEARCH_TEMPLATE_FIELDS, PORTFOLIO_TEMPLATE_FIELDS),
    steps: [
      {
        id: 'execution-workspace',
        label: '创建执行工作区',
        description: '以执行追踪模板为中心建立交易侧工作区。',
        kind: 'blueprint',
        blueprintId: 'execution-pulse',
        requiredAny: ['stockCode', 'accountId', 'executionId', 'artifactId'],
        defaultsStrategy: 'override',
      },
      {
        id: 'execution-research-flow',
        label: '回补研究链路',
        description: '若有股票代码，则把行情、研究、事件与决策任务补回当前执行工作区。',
        kind: 'task-template',
        templateId: 'research-flow',
        dependsOn: ['execution-workspace'],
        requiredAll: ['stockCode'],
        defaultsStrategy: 'fill-missing',
        condition: (context) => Boolean(context.stockCode),
        conditionDescription: '仅当已有股票代码时补研究链路。',
      },
      {
        id: 'execution-portfolio-audit',
        label: '续接组合巡检',
        description: '若执行任务已经挂到组合上下文，继续补风险、绩效与事件巡检。',
        kind: 'task-template',
        templateId: 'portfolio-audit',
        dependsOn: ['execution-workspace'],
        requiredAll: ['portfolioId'],
        defaultsStrategy: 'fill-missing',
        condition: (context) => Boolean(context.portfolioId),
        conditionDescription: '仅当执行任务带有组合 ID 时续接组合巡检。',
      },
    ],
  },
  'portfolio-command': {
    id: 'portfolio-command',
    label: '组合指挥流',
    description: '以组合复盘为主干，再按上下文补单票研究和执行跟踪。',
    fields: mergeFieldDefinitions(PORTFOLIO_TEMPLATE_FIELDS, RESEARCH_TEMPLATE_FIELDS, EXECUTION_TEMPLATE_FIELDS),
    steps: [
      {
        id: 'portfolio-workspace',
        label: '创建组合工作区',
        description: '先建立组合复盘工作区，沉淀风险、绩效和事件的固定巡检路径。',
        kind: 'blueprint',
        blueprintId: 'portfolio-review',
        requiredAll: ['portfolioId'],
        defaultsStrategy: 'override',
      },
      {
        id: 'portfolio-research-flow',
        label: '补单票研究',
        description: '如果组合已有领头标的上下文，再补行情、研究、事件和决策链路。',
        kind: 'task-template',
        templateId: 'research-flow',
        dependsOn: ['portfolio-workspace'],
        requiredAll: ['stockCode'],
        defaultsStrategy: 'fill-missing',
        condition: (context) => Boolean(context.stockCode),
        conditionDescription: '仅当组合上下文中已有主标的时补单票研究。',
      },
      {
        id: 'portfolio-execution-followup',
        label: '补执行跟踪',
        description: '如果组合复盘已经定位到账户、执行或 artifact，则续接执行复盘。',
        kind: 'task-template',
        templateId: 'execution-followup',
        dependsOn: ['portfolio-workspace'],
        requiredAny: ['accountId', 'executionId', 'artifactId'],
        defaultsStrategy: 'fill-missing',
        condition: (context) => Boolean(context.accountId || context.executionId || context.artifactId),
        conditionDescription: '仅当已有账户、执行或 artifact 上下文时补执行跟踪。',
      },
    ],
  },
};

function now() {
  return Date.now();
}

function makeId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

function clamp(value: unknown, min: number, max: number, fallback: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, Math.trunc(parsed)));
}

function normalizePagePanelMode(value: unknown): WorkspacePagePanelMode {
  return value === 'split' ? 'split' : 'single';
}

function resolveWorkspacePagePanels(value: unknown): Record<string, WorkspacePagePanelLayout> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }

  return Object.entries(value as Record<string, unknown>).reduce<Record<string, WorkspacePagePanelLayout>>(
    (acc, [pageKey, panel]) => {
      if (!pageKey.trim()) return acc;
      acc[pageKey] = resolveWorkspacePagePanel(panel);
      return acc;
    },
    {},
  );
}

export function resolveWorkspacePagePanel(panel?: WorkspacePagePanelLayout | null | unknown): WorkspacePagePanelLayout {
  const normalizedPanel =
    panel && typeof panel === 'object' && !Array.isArray(panel) ? (panel as WorkspacePagePanelLayout) : null;
  const normalizedSecondarySize = clamp(
    normalizedPanel?.secondarySize,
    24,
    60,
    DEFAULT_PAGE_PANEL_LAYOUT.secondarySize ?? 34,
  );
  return {
    mode: normalizePagePanelMode(normalizedPanel?.mode),
    secondaryPlacement: normalizedPanel?.secondaryPlacement === 'left' ? 'left' : 'right',
    // 38% 是早期默认值，会让主画布在工作台布局里显得过窄，统一迁移到新的更保守基线。
    secondarySize: normalizedSecondarySize === 38 ? 34 : normalizedSecondarySize,
  };
}

function normalizeLayoutPreset(value: unknown): WorkspaceLayoutPreset {
  return value === 'trading' || value === 'focus' || value === 'custom' ? value : 'research';
}

export function resolveWorkspaceLayout(layout?: Partial<WorkspaceLayout> | null): WorkspaceLayout {
  const preset = normalizeLayoutPreset(layout?.preset);
  const base = WORKSPACE_LAYOUT_PRESETS[preset] ?? DEFAULT_WORKSPACE_LAYOUT;
  return {
    ...base,
    ...layout,
    preset,
    navCollapsed: typeof layout?.navCollapsed === 'boolean' ? layout.navCollapsed : base.navCollapsed,
    navWidth: clamp(layout?.navWidth, 188, 280, base.navWidth ?? 208),
    dockVisible: typeof layout?.dockVisible === 'boolean' ? layout.dockVisible : base.dockVisible,
    dockWidth: clamp(layout?.dockWidth, 320, 480, base.dockWidth ?? 380),
    density: layout?.density === 'compact' ? 'compact' : base.density,
    pageWidth: layout?.pageWidth === 'focused' ? 'focused' : base.pageWidth,
    pagePanels: resolveWorkspacePagePanels(layout?.pagePanels),
  };
}

function createWorkspaceRecord(id = DEFAULT_WORKSPACE_ID, name = '默认工作区'): WorkspaceRecord {
  const timestamp = now();
  return {
    id,
    name,
    createdAt: timestamp,
    updatedAt: timestamp,
    layout: { ...DEFAULT_WORKSPACE_LAYOUT },
    context: {},
    savedViews: [],
    tasks: [],
  };
}

function renderTaskTitle(title: WorkspaceTaskTemplateStep['title'], context: WorkspaceSharedContext) {
  return typeof title === 'function' ? title(context) : title;
}

function renderTaskHref(href: WorkspaceTaskTemplateStep['href'], context: WorkspaceSharedContext) {
  if (!href) return undefined;
  const nextHref = typeof href === 'function' ? href(context) : href;
  return nextHref || undefined;
}

function renderTaskPayload(payload: WorkspaceTaskTemplateStep['payload'], context: WorkspaceSharedContext) {
  if (!payload) return undefined;
  return typeof payload === 'function' ? payload(context) : payload;
}

function buildTemplatePreviewSteps(
  templateId: WorkspaceTaskTemplateId,
  context: WorkspaceSharedContext,
): WorkspaceTaskPreview[] {
  const template = WORKSPACE_TASK_TEMPLATES[templateId];
  const resolvedContext = resolveTemplateContext(context);

  return template.steps.reduce<WorkspaceTaskPreview[]>((steps, step) => {
    const href = renderTaskHref(step.href, resolvedContext);
    if (step.href && !href) return steps;

    const payload = renderTaskPayload(step.payload, resolvedContext);
    steps.push({
      pageKey: step.pageKey,
      title: renderTaskTitle(step.title, resolvedContext),
      status: step.status ?? 'todo',
      href,
      kind: step.kind,
      payload,
    });
    return steps;
  }, []);
}

export function previewTaskTemplate(
  templateId: WorkspaceTaskTemplateId,
  context: WorkspaceSharedContext,
  overrides?: WorkspaceContextOverrides,
) {
  const resolvedContext = resolveWorkspaceTemplateContext(context, overrides);
  return {
    context: resolvedContext,
    steps: buildTemplatePreviewSteps(templateId, resolvedContext),
  };
}

export function previewWorkspaceBlueprint(
  blueprintId: WorkspaceBlueprintId,
  context: WorkspaceSharedContext,
  overrides?: WorkspaceContextOverrides,
) {
  const blueprint = WORKSPACE_BLUEPRINTS[blueprintId];
  const baseContext = resolveWorkspaceTemplateContext(context, overrides);
  const resolvedContext = blueprint.context ? blueprint.context(baseContext) : baseContext;

  return {
    context: resolvedContext,
    layoutPreset: blueprint.layoutPreset,
    taskTemplateId: blueprint.taskTemplateId,
    workspaceName: blueprint.workspaceName(resolvedContext),
    steps: buildTemplatePreviewSteps(blueprint.taskTemplateId, resolvedContext),
  };
}

function buildWorkflowStepPreview(
  step: WorkspaceTemplateWorkflowStep,
  context: WorkspaceSharedContext,
): Omit<WorkspaceTemplateWorkflowPreviewStep, 'status' | 'reason'> {
  const defaultsStrategy = step.defaultsStrategy ?? 'override';

  if (step.kind === 'blueprint') {
    const blueprintId = step.blueprintId as WorkspaceBlueprintId;
    const blueprint = WORKSPACE_BLUEPRINTS[blueprintId];
    const preview = previewWorkspaceBlueprint(blueprintId, context);
    return {
      id: step.id,
      label: step.label,
      description: step.description,
      kind: 'blueprint',
      targetId: blueprintId,
      targetLabel: blueprint.label,
      defaultsStrategy,
      dependsOn: step.dependsOn ?? [],
      requiredAll: step.requiredAll ?? [],
      requiredAny: step.requiredAny ?? [],
      context: preview.context,
      workspaceName: preview.workspaceName,
      layoutPreset: preview.layoutPreset,
      taskTemplateId: preview.taskTemplateId,
      steps: preview.steps,
    };
  }

  const templateId = step.templateId as WorkspaceTaskTemplateId;
  const template = WORKSPACE_TASK_TEMPLATES[templateId];
  const preview = previewTaskTemplate(templateId, context);
  return {
    id: step.id,
    label: step.label,
    description: step.description,
    kind: 'task-template',
    targetId: templateId,
    targetLabel: template.label,
    defaultsStrategy,
    dependsOn: step.dependsOn ?? [],
    requiredAll: step.requiredAll ?? [],
    requiredAny: step.requiredAny ?? [],
    context: preview.context,
    steps: preview.steps,
  };
}

export function previewTemplateWorkflow(
  workflowId: WorkspaceTemplateWorkflowId,
  context: WorkspaceSharedContext,
  overrides?: WorkspaceContextOverrides,
): WorkspaceTemplateWorkflowPreview {
  const workflow = WORKSPACE_TEMPLATE_WORKFLOWS[workflowId];
  let currentContext = resolveWorkspaceTemplateContext(context, overrides);
  const readyStepIds = new Set<string>();
  let createdWorkspaceCount = 0;
  let executableStepCount = 0;
  let blockedStepCount = 0;
  let skippedStepCount = 0;
  let latestWorkspaceName: string | undefined;

  const steps = workflow.steps.map<WorkspaceTemplateWorkflowPreviewStep>((step) => {
    const defaultsStrategy = step.defaultsStrategy ?? 'override';
    const stepOverrides = renderWorkflowStepOverrides(step.overrides, currentContext);
    const stepContext = resolveTemplateContext(
      applyDefaultsStrategy(currentContext, normalizeWorkspaceContextOverrides(stepOverrides), defaultsStrategy),
    );
    const previewBase = buildWorkflowStepPreview(step, stepContext);
    const blockedDependency = (step.dependsOn ?? []).find((dependencyId) => !readyStepIds.has(dependencyId));

    if (blockedDependency) {
      blockedStepCount += 1;
      return {
        ...previewBase,
        status: 'blocked',
        reason: `依赖步骤 ${blockedDependency} 尚未就绪`,
      };
    }

    const missingReason = missingRequiredContext(previewBase.context, step.requiredAll ?? [], step.requiredAny ?? []);
    if (missingReason) {
      blockedStepCount += 1;
      return {
        ...previewBase,
        status: 'blocked',
        reason: missingReason,
      };
    }

    if (step.condition && !step.condition(previewBase.context)) {
      skippedStepCount += 1;
      return {
        ...previewBase,
        status: 'skipped',
        reason: step.conditionDescription ?? '当前上下文未命中执行条件',
      };
    }

    readyStepIds.add(step.id);
    executableStepCount += 1;
    currentContext = previewBase.context;
    if (previewBase.kind === 'blueprint') {
      createdWorkspaceCount += 1;
      latestWorkspaceName = previewBase.workspaceName;
    }

    return {
      ...previewBase,
      status: 'ready',
    };
  });

  return {
    context: currentContext,
    workspaceName: latestWorkspaceName,
    createdWorkspaceCount,
    executableStepCount,
    blockedStepCount,
    skippedStepCount,
    steps,
  };
}

function taskFingerprint(task: Pick<WorkspaceTask, 'pageKey' | 'title' | 'href' | 'kind'>) {
  return `${task.pageKey}::${task.title}::${task.href ?? ''}::${task.kind ?? ''}`;
}

function buildTemplateTasks(
  templateId: WorkspaceTaskTemplateId,
  context: WorkspaceSharedContext,
  timestamp: number,
): WorkspaceTask[] {
  return buildTemplatePreviewSteps(templateId, context).map((step, index) => {
    const task: WorkspaceTask = {
      id: makeId(`task-${templateId}-${index + 1}`),
      pageKey: step.pageKey,
      title: step.title,
      status: step.status,
      createdAt: timestamp,
      updatedAt: timestamp,
    };

    if (step.href) task.href = step.href;
    if (step.kind) task.kind = step.kind;
    if (step.payload) task.payload = step.payload;
    return task;
  });
}

function prependTasks(existing: WorkspaceTask[], incoming: WorkspaceTask[]) {
  const existingKeys = new Set(existing.map((task) => taskFingerprint(task)));
  const dedupedIncoming = incoming.filter((task) => !existingKeys.has(taskFingerprint(task)));
  return [...dedupedIncoming, ...existing].slice(0, 50);
}

function prependTemplateRuns(existing: WorkspaceTemplateRunRecord[], incoming: WorkspaceTemplateRunRecord) {
  return [incoming, ...existing.filter((item) => item.id !== incoming.id)].slice(0, 12);
}

function ensureWorkspaceList(workspaces: WorkspaceRecord[]) {
  const normalized = workspaces.map((workspace) => ({
    ...workspace,
    layout: resolveWorkspaceLayout(workspace.layout),
  }));
  return normalized.length > 0 ? normalized : [createWorkspaceRecord()];
}

export function selectActiveWorkspace(
  state: Pick<WorkbenchState, 'activeWorkspaceId' | 'workspaces'>,
): WorkspaceRecord {
  return (
    state.workspaces.find((workspace) => workspace.id === state.activeWorkspaceId) ??
    state.workspaces[0] ??
    createWorkspaceRecord()
  );
}

function updateActiveWorkspace(
  state: Pick<WorkbenchState, 'activeWorkspaceId' | 'workspaces'>,
  updater: (workspace: WorkspaceRecord) => WorkspaceRecord,
) {
  const workspaces = ensureWorkspaceList(state.workspaces);
  const activeWorkspace = selectActiveWorkspace({
    activeWorkspaceId: state.activeWorkspaceId,
    workspaces,
  });
  return workspaces.map((workspace) => (workspace.id === activeWorkspace.id ? updater(workspace) : workspace));
}

function updateWorkspaceById(
  workspaces: WorkspaceRecord[],
  workspaceId: string,
  updater: (workspace: WorkspaceRecord) => WorkspaceRecord,
) {
  return ensureWorkspaceList(workspaces).map((workspace) =>
    workspace.id === workspaceId ? updater(workspace) : workspace,
  );
}

function mergeLayout(current: WorkspaceLayout | null | undefined, patch: LayoutPatch) {
  const resolvedCurrent = resolveWorkspaceLayout(current);
  const nextPreset = patch.preset ? normalizeLayoutPreset(patch.preset) : 'custom';
  return resolveWorkspaceLayout({
    ...resolvedCurrent,
    ...patch,
    preset: nextPreset,
  });
}

function mergePagePanel(current: WorkspaceLayout['pagePanels'], pageKey: WorkspacePageKey, patch: PagePanelPatch) {
  const nextPanels = resolveWorkspacePagePanels(current);
  nextPanels[pageKey] = resolveWorkspacePagePanel({
    ...resolveWorkspacePagePanel(nextPanels[pageKey]),
    ...patch,
  });
  return nextPanels;
}

function applyContextPatch(current: WorkspaceSharedContext, patch: WorkspaceContextPatch): WorkspaceSharedContext {
  const next: Record<string, unknown> = { ...current };
  Object.entries(patch).forEach(([key, value]) => {
    if (value == null) {
      delete next[key];
      return;
    }
    next[key] = value;
  });
  return next as WorkspaceSharedContext;
}

function contextsEqual(left: WorkspaceSharedContext, right: WorkspaceSharedContext) {
  const leftEntries = Object.entries(left);
  const rightEntries = Object.entries(right);
  if (leftEntries.length !== rightEntries.length) return false;
  return leftEntries.every(([key, value]) => right[key as keyof WorkspaceSharedContext] === value);
}

function cloneWorkspaceSnapshot(snapshot: WorkspaceStateSnapshot): WorkspaceStateSnapshot {
  if (typeof structuredClone === 'function') {
    return structuredClone(snapshot);
  }
  return JSON.parse(JSON.stringify(snapshot)) as WorkspaceStateSnapshot;
}

function formatTemplateRunSummary(
  label: string,
  createdWorkspaceIds: string[],
  taskIds: string[],
  skippedStepIds: string[] = [],
  blockedStepIds: string[] = [],
) {
  const parts = [
    createdWorkspaceIds.length > 0 ? `创建 ${createdWorkspaceIds.length} 个工作区` : null,
    taskIds.length > 0 ? `注入 ${taskIds.length} 条任务` : null,
    skippedStepIds.length > 0 ? `跳过 ${skippedStepIds.length} 步` : null,
    blockedStepIds.length > 0 ? `阻塞 ${blockedStepIds.length} 步` : null,
  ].filter(Boolean);
  return parts.length > 0 ? `${label}：${parts.join('，')}` : `${label}：无可执行变更`;
}

async function requestWorkspaceSnapshot(
  method: 'GET' | 'PUT',
  body?: WorkspaceStateSnapshot,
): Promise<WorkspaceStateSnapshot | null> {
  try {
    const response = await authedFetch(
      WORKSPACE_PATH,
      {
        method,
        cache: 'no-store',
        headers: body ? { 'content-type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      },
      { redirectOnUnauthorized: false },
    );

    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      console.warn('[workbench] workspace sync failed:', extractApiErrorMessage(payload, `HTTP ${response.status}`));
      return null;
    }

    const unwrapped = unwrapApiEnvelope<WorkspaceStateSnapshot>(payload);
    if (unwrapped.errorMessage) {
      console.warn('[workbench] workspace sync failed:', unwrapped.errorMessage);
      return null;
    }

    return unwrapped.data && typeof unwrapped.data === 'object' ? (unwrapped.data as WorkspaceStateSnapshot) : null;
  } catch (error) {
    console.warn('[workbench] workspace sync failed:', error instanceof Error ? error.message : String(error));
    return null;
  }
}

export const useWorkbenchStore = create<WorkbenchState>()(
  persist(
    (set, get) => ({
      hydrated: false,
      remoteReady: false,
      syncing: false,
      lastSyncedAt: null,
      activeWorkspaceId: DEFAULT_WORKSPACE_ID,
      workspaces: [createWorkspaceRecord()],
      templateRuns: [],

      setHydrated: (hydrated) => set({ hydrated }),

      replaceSnapshot: (snapshot) => {
        set({
          activeWorkspaceId: snapshot.activeWorkspaceId || DEFAULT_WORKSPACE_ID,
          workspaces: ensureWorkspaceList(Array.isArray(snapshot.workspaces) ? snapshot.workspaces : []),
          remoteReady: true,
          lastSyncedAt: snapshot.updatedAt ?? new Date().toISOString(),
        });
      },

      createWorkspace: (name) => {
        const id = makeId('workspace');
        const workspace = createWorkspaceRecord(
          id,
          String(name || '').trim() || `工作区 ${get().workspaces.length + 1}`,
        );
        set((state) => ({
          activeWorkspaceId: id,
          workspaces: [...ensureWorkspaceList(state.workspaces), workspace],
        }));
        return id;
      },

      renameWorkspace: (id, name) => {
        const nextName = String(name).trim();
        if (!nextName) return;
        set((state) => ({
          workspaces: ensureWorkspaceList(state.workspaces).map((workspace) =>
            workspace.id === id ? { ...workspace, name: nextName, updatedAt: now() } : workspace,
          ),
        }));
      },

      switchWorkspace: (id) => {
        set((state) => {
          const exists = ensureWorkspaceList(state.workspaces).some((workspace) => workspace.id === id);
          return exists ? { activeWorkspaceId: id } : state;
        });
      },

      updateLayout: (patch) => {
        set((state) => ({
          workspaces: updateActiveWorkspace(state, (workspace) => ({
            ...workspace,
            updatedAt: now(),
            layout: mergeLayout(workspace.layout, patch),
          })),
        }));
      },

      applyLayoutPreset: (preset) => {
        set((state) => ({
          workspaces: updateActiveWorkspace(state, (workspace) => ({
            ...workspace,
            updatedAt: now(),
            layout: resolveWorkspaceLayout({
              ...workspace.layout,
              preset,
            }),
          })),
        }));
      },

      resetLayout: () => {
        set((state) => ({
          workspaces: updateActiveWorkspace(state, (workspace) => ({
            ...workspace,
            updatedAt: now(),
            layout: resolveWorkspaceLayout({
              ...workspace.layout,
              preset: 'research',
              navCollapsed: DEFAULT_WORKSPACE_LAYOUT.navCollapsed,
              navWidth: DEFAULT_WORKSPACE_LAYOUT.navWidth,
              dockVisible: DEFAULT_WORKSPACE_LAYOUT.dockVisible,
              dockWidth: DEFAULT_WORKSPACE_LAYOUT.dockWidth,
              density: DEFAULT_WORKSPACE_LAYOUT.density,
              pageWidth: DEFAULT_WORKSPACE_LAYOUT.pageWidth,
            }),
          })),
        }));
      },

      updatePagePanel: (pageKey, patch) => {
        set((state) => ({
          workspaces: updateActiveWorkspace(state, (workspace) => ({
            ...workspace,
            updatedAt: now(),
            layout: resolveWorkspaceLayout({
              ...workspace.layout,
              pagePanels: mergePagePanel(workspace.layout.pagePanels, pageKey, patch),
            }),
          })),
        }));
      },

      resetPagePanel: (pageKey) => {
        set((state) => ({
          workspaces: updateActiveWorkspace(state, (workspace) => {
            const nextPanels = resolveWorkspacePagePanels(workspace.layout.pagePanels);
            delete nextPanels[pageKey];
            return {
              ...workspace,
              updatedAt: now(),
              layout: resolveWorkspaceLayout({
                ...workspace.layout,
                pagePanels: nextPanels,
              }),
            };
          }),
        }));
      },

      createWorkspaceFromBlueprint: (blueprintId, overrides) => {
        const timestamp = now();
        const state = get();
        const activeWorkspace = selectActiveWorkspace(state);
        const rollbackSnapshot = cloneWorkspaceSnapshot({
          activeWorkspaceId: state.activeWorkspaceId,
          workspaces: state.workspaces,
          updatedAt: new Date().toISOString(),
        });
        const preview = previewWorkspaceBlueprint(blueprintId, activeWorkspace.context, overrides);
        const workspaceId = makeId('workspace');
        const blueprint = WORKSPACE_BLUEPRINTS[blueprintId];
        const workspace: WorkspaceRecord = {
          id: workspaceId,
          name: preview.workspaceName,
          createdAt: timestamp,
          updatedAt: timestamp,
          layout: resolveWorkspaceLayout({ preset: preview.layoutPreset }),
          context: preview.context,
          savedViews: [],
          tasks: buildTemplateTasks(preview.taskTemplateId, preview.context, timestamp),
        };

        set((currentState) => ({
          activeWorkspaceId: workspaceId,
          workspaces: [...ensureWorkspaceList(currentState.workspaces), workspace],
          templateRuns: prependTemplateRuns(currentState.templateRuns, {
            id: makeId('template-run'),
            kind: 'blueprint',
            status: 'applied',
            targetId: blueprintId,
            label: blueprint.label,
            summary: formatTemplateRunSummary(
              blueprint.label,
              [workspaceId],
              workspace.tasks.map((task) => task.id),
            ),
            context: preview.context,
            targetWorkspaceId: workspaceId,
            createdWorkspaceIds: [workspaceId],
            taskIds: workspace.tasks.map((task) => task.id),
            appliedStepIds: [blueprint.taskTemplateId],
            blockedStepIds: [],
            skippedStepIds: [],
            createdAt: timestamp,
            updatedAt: timestamp,
            rollbackSnapshot,
          }),
        }));

        return workspaceId;
      },

      applyTaskTemplate: (templateId, overrides) => {
        const timestamp = now();
        const state = get();
        const activeWorkspace = selectActiveWorkspace(state);
        const rollbackSnapshot = cloneWorkspaceSnapshot({
          activeWorkspaceId: state.activeWorkspaceId,
          workspaces: state.workspaces,
          updatedAt: new Date().toISOString(),
        });
        const preview = previewTaskTemplate(templateId, activeWorkspace.context, overrides);
        const nextTasks = buildTemplateTasks(templateId, preview.context, timestamp);
        if (nextTasks.length === 0) return [];
        const template = WORKSPACE_TASK_TEMPLATES[templateId];

        set((currentState) => ({
          workspaces: updateActiveWorkspace(currentState, (workspace) => ({
            ...workspace,
            updatedAt: timestamp,
            tasks: prependTasks(workspace.tasks, nextTasks),
          })),
          templateRuns: prependTemplateRuns(currentState.templateRuns, {
            id: makeId('template-run'),
            kind: 'task-template',
            status: 'applied',
            targetId: templateId,
            label: template.label,
            summary: formatTemplateRunSummary(
              template.label,
              [],
              nextTasks.map((task) => task.id),
            ),
            context: preview.context,
            targetWorkspaceId: activeWorkspace.id,
            createdWorkspaceIds: [],
            taskIds: nextTasks.map((task) => task.id),
            appliedStepIds: [templateId],
            blockedStepIds: [],
            skippedStepIds: [],
            createdAt: timestamp,
            updatedAt: timestamp,
            rollbackSnapshot,
          }),
        }));

        return nextTasks.map((task) => task.id);
      },

      applyTemplateWorkflow: (workflowId, overrides) => {
        const timestamp = now();
        const state = get();
        const activeWorkspace = selectActiveWorkspace(state);
        const rollbackSnapshot = cloneWorkspaceSnapshot({
          activeWorkspaceId: state.activeWorkspaceId,
          workspaces: state.workspaces,
          updatedAt: new Date().toISOString(),
        });
        const preview = previewTemplateWorkflow(workflowId, activeWorkspace.context, overrides);
        const readySteps = preview.steps.filter((step) => step.status === 'ready');
        const workflow = WORKSPACE_TEMPLATE_WORKFLOWS[workflowId];

        const result: ApplyTemplateWorkflowResult = {
          workflowId,
          createdWorkspaceIds: [],
          targetWorkspaceId: null,
          taskIds: [],
          appliedStepIds: [],
          skippedStepIds: preview.steps.filter((step) => step.status === 'skipped').map((step) => step.id),
          blockedStepIds: preview.steps.filter((step) => step.status === 'blocked').map((step) => step.id),
        };

        if (readySteps.length === 0) {
          return result;
        }

        let nextWorkspaces = ensureWorkspaceList(state.workspaces);
        let targetWorkspaceId = activeWorkspace.id;

        readySteps.forEach((step) => {
          if (step.kind === 'blueprint') {
            const workspaceId = makeId('workspace');
            const workspace: WorkspaceRecord = {
              id: workspaceId,
              name: step.workspaceName ?? `工作区 ${nextWorkspaces.length + 1}`,
              createdAt: timestamp,
              updatedAt: timestamp,
              layout: resolveWorkspaceLayout({ preset: step.layoutPreset ?? 'research' }),
              context: step.context,
              savedViews: [],
              tasks: step.taskTemplateId ? buildTemplateTasks(step.taskTemplateId, step.context, timestamp) : [],
            };
            nextWorkspaces = [...nextWorkspaces, workspace];
            targetWorkspaceId = workspaceId;
            result.createdWorkspaceIds.push(workspaceId);
            result.taskIds.push(...workspace.tasks.map((task) => task.id));
            result.appliedStepIds.push(step.id);
            result.targetWorkspaceId = workspaceId;
            return;
          }

          const nextTasks = buildTemplateTasks(step.targetId as WorkspaceTaskTemplateId, step.context, timestamp);
          if (nextTasks.length === 0) return;

          nextWorkspaces = updateWorkspaceById(nextWorkspaces, targetWorkspaceId, (workspace) => ({
            ...workspace,
            updatedAt: timestamp,
            context: step.context,
            tasks: prependTasks(workspace.tasks, nextTasks),
          }));
          result.taskIds.push(...nextTasks.map((task) => task.id));
          result.appliedStepIds.push(step.id);
          result.targetWorkspaceId = targetWorkspaceId;
        });

        if (result.createdWorkspaceIds.length === 0) {
          nextWorkspaces = updateWorkspaceById(nextWorkspaces, activeWorkspace.id, (workspace) => ({
            ...workspace,
            updatedAt: timestamp,
            context: preview.context,
          }));
          result.targetWorkspaceId = activeWorkspace.id;
        }

        set((currentState) => ({
          activeWorkspaceId: result.targetWorkspaceId ?? currentState.activeWorkspaceId,
          workspaces: nextWorkspaces,
          templateRuns: prependTemplateRuns(currentState.templateRuns, {
            id: makeId('template-run'),
            kind: 'workflow',
            status: 'applied',
            targetId: workflowId,
            label: workflow.label,
            summary: formatTemplateRunSummary(
              workflow.label,
              result.createdWorkspaceIds,
              result.taskIds,
              result.skippedStepIds,
              result.blockedStepIds,
            ),
            context: preview.context,
            targetWorkspaceId: result.targetWorkspaceId,
            createdWorkspaceIds: result.createdWorkspaceIds,
            taskIds: result.taskIds,
            appliedStepIds: result.appliedStepIds,
            blockedStepIds: result.blockedStepIds,
            skippedStepIds: result.skippedStepIds,
            createdAt: timestamp,
            updatedAt: timestamp,
            rollbackSnapshot,
          }),
        }));

        return result;
      },

      rollbackTemplateRun: (runId) => {
        const run = get().templateRuns.find((item) => item.id === runId);
        if (!run?.rollbackSnapshot || run.status === 'rolled-back') {
          return false;
        }

        const rollbackAt = now();
        set((state) => ({
          activeWorkspaceId: run.rollbackSnapshot?.activeWorkspaceId || DEFAULT_WORKSPACE_ID,
          workspaces: ensureWorkspaceList(run.rollbackSnapshot?.workspaces ?? []),
          templateRuns: state.templateRuns.map((item) =>
            item.createdAt >= run.createdAt
              ? {
                  ...item,
                  status: 'rolled-back',
                  rolledBackAt: rollbackAt,
                  updatedAt: rollbackAt,
                }
              : item,
          ),
        }));
        return true;
      },

      clearTemplateRuns: () => {
        set({ templateRuns: [] });
      },

      updateContext: (patch) => {
        set((state) => ({
          workspaces: updateActiveWorkspace(state, (workspace) => ({
            ...(function () {
              const nextContext = applyContextPatch(workspace.context, patch);
              if (contextsEqual(workspace.context, nextContext)) {
                return workspace;
              }
              return {
                ...workspace,
                updatedAt: now(),
                context: nextContext,
              };
            })(),
          })),
        }));
      },

      replaceContext: (next) => {
        set((state) => ({
          workspaces: updateActiveWorkspace(state, (workspace) => ({
            ...(function () {
              const nextContext = { ...next };
              if (contextsEqual(workspace.context, nextContext)) {
                return workspace;
              }
              return {
                ...workspace,
                updatedAt: now(),
                context: nextContext,
              };
            })(),
          })),
        }));
      },

      saveView: (pageKey, name, snapshot) => {
        const viewId = makeId('view');
        const timestamp = now();
        const safeName = String(name).trim() || `${pageKey} 视图 ${new Date(timestamp).toLocaleTimeString()}`;
        set((state) => ({
          workspaces: updateActiveWorkspace(state, (workspace) => ({
            ...workspace,
            updatedAt: timestamp,
            savedViews: [
              {
                id: viewId,
                pageKey,
                name: safeName,
                snapshot,
                createdAt: timestamp,
                updatedAt: timestamp,
              },
              ...workspace.savedViews.filter((view) => view.pageKey !== pageKey || view.name !== safeName),
            ].slice(0, 20),
          })),
        }));
        return viewId;
      },

      deleteView: (pageKey, viewId) => {
        set((state) => ({
          workspaces: updateActiveWorkspace(state, (workspace) => ({
            ...workspace,
            updatedAt: now(),
            savedViews: workspace.savedViews.filter((view) => !(view.pageKey === pageKey && view.id === viewId)),
          })),
        }));
      },

      addTask: (input) => {
        const taskId = makeId('task');
        const timestamp = now();
        const task: WorkspaceTask = {
          id: taskId,
          pageKey: input.pageKey,
          title: input.title.trim(),
          status: input.status ?? 'todo',
          href: input.href,
          kind: input.kind,
          payload: input.payload,
          createdAt: timestamp,
          updatedAt: timestamp,
        };
        set((state) => ({
          workspaces: updateActiveWorkspace(state, (workspace) => ({
            ...workspace,
            updatedAt: timestamp,
            tasks: prependTasks(workspace.tasks, [task]),
          })),
        }));
        return taskId;
      },

      updateTask: (taskId, patch) => {
        set((state) => ({
          workspaces: updateActiveWorkspace(state, (workspace) => ({
            ...workspace,
            updatedAt: now(),
            tasks: workspace.tasks.map((task) =>
              task.id === taskId
                ? {
                    ...task,
                    ...patch,
                    updatedAt: now(),
                  }
                : task,
            ),
          })),
        }));
      },

      removeTask: (taskId) => {
        set((state) => ({
          workspaces: updateActiveWorkspace(state, (workspace) => ({
            ...workspace,
            updatedAt: now(),
            tasks: workspace.tasks.filter((task) => task.id !== taskId),
          })),
        }));
      },

      clearDoneTasks: () => {
        set((state) => ({
          workspaces: updateActiveWorkspace(state, (workspace) => ({
            ...workspace,
            updatedAt: now(),
            tasks: workspace.tasks.filter((task) => task.status !== 'done'),
          })),
        }));
      },

      syncFromServer: async () => {
        set({ syncing: true });
        try {
          const data = await requestWorkspaceSnapshot('GET');
          if (data) {
            get().replaceSnapshot(data);
            return;
          }
          set({ remoteReady: true });
        } finally {
          set({ syncing: false });
        }
      },

      pushToServer: async () => {
        const state = get();
        set({ syncing: true });
        try {
          const snapshot: WorkspaceStateSnapshot = {
            activeWorkspaceId: state.activeWorkspaceId,
            workspaces: state.workspaces,
            updatedAt: new Date().toISOString(),
          };
          const data = await requestWorkspaceSnapshot('PUT', snapshot);
          if (data) {
            set({ lastSyncedAt: data.updatedAt ?? new Date().toISOString(), remoteReady: true });
            return;
          }
          set({ remoteReady: true });
        } finally {
          set({ syncing: false });
        }
      },
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      skipHydration: true,
      partialize: (state) => ({
        activeWorkspaceId: state.activeWorkspaceId,
        workspaces: state.workspaces,
        templateRuns: state.templateRuns,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHydrated(true);
      },
    },
  ),
);

if (typeof window !== 'undefined') {
  useWorkbenchStore.persist.rehydrate();
}
