import type { WorkspaceSharedContext } from '@aiask/shared-types';
import type {
  WorkspaceContextOverrides,
  WorkspaceContextPatch,
  WorkspaceTemplateDefaultsStrategy,
  WorkspaceTemplateFieldDefinition,
  WorkspaceTemplateWorkflowStep,
} from './workbench-template-types';

const WORKSPACE_CONTEXT_KEYS: Array<keyof WorkspaceSharedContext> = [
  'stockCode',
  'stockConfirmedAt',
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
  'linkedStrategyId',
  'linkedStrategyName',
  'screenerQuery',
  'sourcePage',
  'taskType',
  'resultType',
  'strategyTestMode',
];

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
    return value === 'portfolio' ? 'portfolio' : value === 'account' ? 'account' : value === 'personal-strategy' ? 'personal-strategy' : null;
  }

  if (key === 'strategyTestMode') {
    return value === 'personal-strategy' || value === 'factory-incubation' ? value : null;
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

export function resolveTemplateContext(context: WorkspaceSharedContext): WorkspaceSharedContext {
  return {
    ...context,
    eventCode: context.eventCode ?? context.stockCode,
    mode: context.mode ?? (context.portfolioId ? 'portfolio' : 'account'),
    days: typeof context.days === 'number' && context.days > 0 ? context.days : 30,
    lookbackDays: typeof context.lookbackDays === 'number' && context.lookbackDays > 0 ? context.lookbackDays : 90,
  };
}

export function applyContextPatch(
  current: WorkspaceSharedContext,
  patch: WorkspaceContextPatch,
): WorkspaceSharedContext {
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

export function resolveWorkspaceTemplateContext(
  context: WorkspaceSharedContext,
  overrides?: WorkspaceContextOverrides,
): WorkspaceSharedContext {
  return resolveTemplateContext(applyContextPatch(context, normalizeWorkspaceContextOverrides(overrides)));
}

export function applyDefaultsStrategy(
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

export function missingRequiredContext(
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

export function renderWorkflowStepOverrides(
  overrides: WorkspaceTemplateWorkflowStep['overrides'],
  context: WorkspaceSharedContext,
) {
  if (!overrides) return undefined;
  return typeof overrides === 'function' ? overrides(context) : overrides;
}
