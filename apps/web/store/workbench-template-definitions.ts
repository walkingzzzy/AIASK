import type { WorkspaceSharedContext } from '@aiask/shared-types';
import { resolveTemplateContext } from './workbench-template-context';
import type {
  WorkspaceBlueprintDefinition,
  WorkspaceBlueprintId,
  WorkspaceTaskTemplateDefinition,
  WorkspaceTaskTemplateId,
  WorkspaceTemplateFieldDefinition,
  WorkspaceTemplateWorkflowDefinition,
  WorkspaceTemplateWorkflowId,
} from './workbench-template-types';

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

function buildPath(pathname: string, params: Record<string, string | number | null | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value == null || value === '') return;
    search.set(key, String(value));
  });
  const query = search.toString();
  return query ? `${pathname}?${query}` : pathname;
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
