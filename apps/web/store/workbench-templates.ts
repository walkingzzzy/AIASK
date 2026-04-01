import type { WorkspaceSharedContext, WorkspaceTask } from '@aiask/shared-types';
import {
  applyDefaultsStrategy,
  applyContextPatch,
  missingRequiredContext,
  normalizeWorkspaceContextOverrides,
  pickWorkspaceContextOverrides,
  renderWorkflowStepOverrides,
  resolveTemplateContext,
  resolveWorkspaceTemplateContext,
} from './workbench-template-context';
import {
  WORKSPACE_BLUEPRINTS,
  WORKSPACE_TASK_TEMPLATES,
  WORKSPACE_TEMPLATE_WORKFLOWS,
} from './workbench-template-definitions';
import type {
  WorkspaceBlueprintId,
  WorkspaceContextOverrides,
  WorkspaceTaskPreview,
  WorkspaceTaskTemplateId,
  WorkspaceTaskTemplateStep,
  WorkspaceTemplateWorkflowId,
  WorkspaceTemplateWorkflowPreview,
  WorkspaceTemplateWorkflowPreviewStep,
} from './workbench-template-types';

export type {
  ApplyTemplateWorkflowResult,
  WorkspaceBlueprintDefinition,
  WorkspaceBlueprintId,
  WorkspaceContextOverrides,
  WorkspaceContextPatch,
  WorkspaceTaskPreview,
  WorkspaceTaskTemplateDefinition,
  WorkspaceTaskTemplateId,
  WorkspaceTaskTemplateStep,
  WorkspaceTemplateDefaultsStrategy,
  WorkspaceTemplateFieldDefinition,
  WorkspaceTemplateRunKind,
  WorkspaceTemplateRunRecord,
  WorkspaceTemplateRunStatus,
  WorkspaceTemplateWorkflowDefinition,
  WorkspaceTemplateWorkflowId,
  WorkspaceTemplateWorkflowPreview,
  WorkspaceTemplateWorkflowPreviewStep,
  WorkspaceTemplateWorkflowStep,
} from './workbench-template-types';
export {
  applyContextPatch,
  normalizeWorkspaceContextOverrides,
  pickWorkspaceContextOverrides,
  resolveWorkspaceTemplateContext,
} from './workbench-template-context';
export {
  WORKSPACE_BLUEPRINTS,
  WORKSPACE_TASK_TEMPLATES,
  WORKSPACE_TEMPLATE_WORKFLOWS,
} from './workbench-template-definitions';

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
  step: (typeof WORKSPACE_TEMPLATE_WORKFLOWS)[WorkspaceTemplateWorkflowId]['steps'][number],
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

export function buildTemplateTasks(
  templateId: WorkspaceTaskTemplateId,
  context: WorkspaceSharedContext,
  timestamp: number,
  makeId: (prefix: string) => string,
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

export function formatTemplateRunSummary(
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
