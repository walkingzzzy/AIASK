import {
  WORKSPACE_BLUEPRINTS,
  WORKSPACE_TASK_TEMPLATES,
  WORKSPACE_TEMPLATE_WORKFLOWS,
  pickWorkspaceContextOverrides,
  type WorkspaceBlueprintId,
  type WorkspaceContextOverrides,
  type WorkspaceTaskTemplateId,
  type WorkspaceTemplateFieldDefinition,
  type WorkspaceTemplateWorkflowId,
} from '@/store/workbench-store';
import type { WorkspaceSharedContext } from '@aiask/shared-types';

export type TemplateFieldErrors = Partial<Record<keyof WorkspaceSharedContext, string>>;

export const BLUEPRINT_OPTIONS = Object.values(WORKSPACE_BLUEPRINTS) as Array<
  (typeof WORKSPACE_BLUEPRINTS)[WorkspaceBlueprintId]
>;
export const TEMPLATE_OPTIONS = Object.values(WORKSPACE_TASK_TEMPLATES) as Array<
  (typeof WORKSPACE_TASK_TEMPLATES)[WorkspaceTaskTemplateId]
>;
export const WORKFLOW_OPTIONS = Object.values(WORKSPACE_TEMPLATE_WORKFLOWS) as Array<
  (typeof WORKSPACE_TEMPLATE_WORKFLOWS)[WorkspaceTemplateWorkflowId]
>;

export function contextChips(context: WorkspaceSharedContext) {
  return [
    context.stockCode ? `股票 ${context.stockCode}` : null,
    context.strategyName ? `策略 ${context.strategyName}` : context.strategyId ? `策略 ${context.strategyId}` : null,
    context.eventCode ? `事件 ${context.eventCode}` : null,
    context.accountId ? `账户 ${context.accountId}` : null,
    context.executionId ? `执行 ${context.executionId}` : null,
    context.artifactId ? `制品 ${context.artifactId}` : null,
    context.portfolioId ? `组合 ${context.portfolioId}` : null,
    context.benchmark ? `基准 ${context.benchmark}` : null,
    context.mode ? `模式 ${context.mode}` : null,
    context.days ? `绩效 ${context.days} 天` : null,
    context.lookbackDays ? `风险 ${context.lookbackDays} 天` : null,
  ].filter((item): item is string => Boolean(item));
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export function isWorkspaceBlueprintId(value: unknown): value is WorkspaceBlueprintId {
  return typeof value === 'string' && value in WORKSPACE_BLUEPRINTS;
}

export function isWorkspaceTaskTemplateId(value: unknown): value is WorkspaceTaskTemplateId {
  return typeof value === 'string' && value in WORKSPACE_TASK_TEMPLATES;
}

export function isWorkspaceTemplateWorkflowId(value: unknown): value is WorkspaceTemplateWorkflowId {
  return typeof value === 'string' && value in WORKSPACE_TEMPLATE_WORKFLOWS;
}

export function restoreOverrides(
  snapshotValue: unknown,
  fields: WorkspaceTemplateFieldDefinition[] | undefined,
): WorkspaceContextOverrides {
  return pickWorkspaceContextOverrides(
    isPlainObject(snapshotValue) ? (snapshotValue as WorkspaceContextOverrides) : {},
    fields,
  );
}

export function updateOverrideValue(
  current: WorkspaceContextOverrides,
  key: keyof WorkspaceSharedContext,
  value: string,
) {
  const next = { ...current };
  if (!value.trim()) {
    delete next[key];
    return next;
  }
  next[key] = value;
  return next;
}

function validateTemplateField(
  field: WorkspaceTemplateFieldDefinition,
  overrides: WorkspaceContextOverrides,
): string | null {
  const rawValue = overrides[field.key];
  if (rawValue == null || rawValue === '') return null;

  if (field.input === 'number') {
    const numericValue = Number(rawValue);
    if (!Number.isFinite(numericValue)) return `${field.label}必须是数字`;
    if (field.min != null && numericValue < field.min) return `${field.label}不能小于 ${field.min}`;
    if (field.max != null && numericValue > field.max) return `${field.label}不能大于 ${field.max}`;
  }

  const normalized = String(rawValue).trim();
  if (!normalized) return null;

  if (field.key === 'stockCode' || field.key === 'eventCode' || field.key === 'benchmark') {
    if (!/^\d{6}$/.test(normalized)) return `${field.label}必须为 6 位数字`;
  }

  if (field.key === 'portfolioId' && !/^\d+$/.test(normalized)) {
    return `${field.label}必须为正整数`;
  }

  return null;
}

export function collectTemplateErrors(
  fields: WorkspaceTemplateFieldDefinition[] | undefined,
  overrides: WorkspaceContextOverrides,
) {
  return (fields ?? []).reduce<TemplateFieldErrors>((acc, field) => {
    const error = validateTemplateField(field, overrides);
    if (error) acc[field.key] = error;
    return acc;
  }, {});
}
