'use client';

import { useCallback, useMemo, useState } from 'react';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import { Badge, PageContainer, SectionCard, useToast } from '@/components/ui';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import {
  WORKSPACE_TEMPLATE_WORKFLOWS,
  WORKSPACE_BLUEPRINTS,
  WORKSPACE_TASK_TEMPLATES,
  previewTemplateWorkflow,
  pickWorkspaceContextOverrides,
  previewTaskTemplate,
  previewWorkspaceBlueprint,
  selectActiveWorkspace,
  useWorkbenchStore,
  type WorkspaceBlueprintId,
  type WorkspaceContextOverrides,
  type WorkspaceTemplateWorkflowId,
  type WorkspaceTaskTemplateId,
  type WorkspaceTemplateFieldDefinition,
} from '@/store/workbench-store';
import type { WorkspaceSharedContext } from '@aiask/shared-types';

function contextChips(context: WorkspaceSharedContext) {
  return [
    context.stockCode ? `股票 ${context.stockCode}` : null,
    context.strategyName ? `策略 ${context.strategyName}` : context.strategyId ? `策略 ${context.strategyId}` : null,
    context.eventCode ? `事件 ${context.eventCode}` : null,
    context.accountId ? `账户 ${context.accountId}` : null,
    context.executionId ? `执行 ${context.executionId}` : null,
    context.artifactId ? `Artifact ${context.artifactId}` : null,
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

function restoreOverrides(
  snapshotValue: unknown,
  fields: WorkspaceTemplateFieldDefinition[] | undefined,
): WorkspaceContextOverrides {
  return pickWorkspaceContextOverrides(
    isPlainObject(snapshotValue) ? (snapshotValue as WorkspaceContextOverrides) : {},
    fields,
  );
}

function updateOverrideValue(current: WorkspaceContextOverrides, key: keyof WorkspaceSharedContext, value: string) {
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

function collectTemplateErrors(
  fields: WorkspaceTemplateFieldDefinition[] | undefined,
  overrides: WorkspaceContextOverrides,
) {
  return (fields ?? []).reduce<Partial<Record<keyof WorkspaceSharedContext, string>>>((acc, field) => {
    const error = validateTemplateField(field, overrides);
    if (error) acc[field.key] = error;
    return acc;
  }, {});
}

function TemplateFieldEditor({
  title,
  description,
  fields,
  overrides,
  effectiveContext,
  errors,
  onChange,
  onReset,
}: {
  title: string;
  description: string;
  fields: WorkspaceTemplateFieldDefinition[] | undefined;
  overrides: WorkspaceContextOverrides;
  effectiveContext: WorkspaceSharedContext;
  errors: Partial<Record<keyof WorkspaceSharedContext, string>>;
  onChange: (key: keyof WorkspaceSharedContext, value: string) => void;
  onReset: () => void;
}) {
  const chips = contextChips(effectiveContext);
  const errorCount = Object.keys(errors).length;

  return (
    <SectionCard className="mt-4 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-text-primary">{title}</div>
          <div className="mt-1 text-xs leading-5 text-text-secondary">{description}</div>
        </div>
        <div className="flex items-center gap-2">
          {errorCount > 0 ? <Badge variant="warning">{errorCount} 个待修正</Badge> : null}
          <button
            type="button"
            onClick={onReset}
            className="rounded border border-glass-border px-3 py-1 text-xs text-text-secondary"
          >
            重置参数
          </button>
        </div>
      </div>

      {fields?.length ? (
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {fields.map((field) => {
            const value = overrides[field.key];
            const placeholderValue = effectiveContext[field.key];
            const placeholder =
              placeholderValue != null && placeholderValue !== ''
                ? String(placeholderValue)
                : (field.placeholder ?? '');

            if (field.input === 'select') {
              return (
                <label key={field.key} className="grid gap-1 text-xs text-text-secondary">
                  <span>{field.label}</span>
                  <select
                    value={typeof value === 'string' ? value : ''}
                    onChange={(event) => onChange(field.key, event.target.value)}
                    className="rounded border border-glass-border px-2 py-2 text-sm text-text-primary"
                  >
                    <option value="">沿用当前工作区</option>
                    {field.options?.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  {field.description ? <span>{field.description}</span> : null}
                  {errors[field.key] ? <span className="text-[11px] text-danger">{errors[field.key]}</span> : null}
                </label>
              );
            }

            return (
              <label key={field.key} className="grid gap-1 text-xs text-text-secondary">
                <span>{field.label}</span>
                <input
                  type={field.input === 'number' ? 'number' : 'text'}
                  value={value == null ? '' : String(value)}
                  onChange={(event) => onChange(field.key, event.target.value)}
                  placeholder={placeholder}
                  min={field.min}
                  max={field.max}
                  className="rounded border border-glass-border px-2 py-2 text-sm text-text-primary"
                />
                {field.description ? <span>{field.description}</span> : null}
                {errors[field.key] ? <span className="text-[11px] text-danger">{errors[field.key]}</span> : null}
              </label>
            );
          })}
        </div>
      ) : (
        <div className="mt-3 text-xs text-text-secondary">当前模板没有额外参数，将直接沿用当前工作区上下文。</div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {chips.length > 0 ? (
          chips.map((chip) => (
            <Badge key={`${title}-${chip}`} variant="neutral">
              {chip}
            </Badge>
          ))
        ) : (
          <span className="text-xs text-text-secondary">当前参数下还没有形成有效上下文。</span>
        )}
      </div>
    </SectionCard>
  );
}

const BLUEPRINT_OPTIONS = Object.values(WORKSPACE_BLUEPRINTS) as Array<
  (typeof WORKSPACE_BLUEPRINTS)[WorkspaceBlueprintId]
>;
const TEMPLATE_OPTIONS = Object.values(WORKSPACE_TASK_TEMPLATES) as Array<
  (typeof WORKSPACE_TASK_TEMPLATES)[WorkspaceTaskTemplateId]
>;
const WORKFLOW_OPTIONS = Object.values(WORKSPACE_TEMPLATE_WORKFLOWS) as Array<
  (typeof WORKSPACE_TEMPLATE_WORKFLOWS)[WorkspaceTemplateWorkflowId]
>;

export default function WorkspaceTemplatesPage() {
  const { toast } = useToast();
  const workspaces = useWorkbenchStore((state) => state.workspaces);
  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const templateRuns = useWorkbenchStore((state) => state.templateRuns);
  const createWorkspaceFromBlueprint = useWorkbenchStore((state) => state.createWorkspaceFromBlueprint);
  const applyTaskTemplate = useWorkbenchStore((state) => state.applyTaskTemplate);
  const applyTemplateWorkflow = useWorkbenchStore((state) => state.applyTemplateWorkflow);
  const rollbackTemplateRun = useWorkbenchStore((state) => state.rollbackTemplateRun);
  const clearTemplateRuns = useWorkbenchStore((state) => state.clearTemplateRuns);
  const switchWorkspace = useWorkbenchStore((state) => state.switchWorkspace);

  const activeWorkspace = useMemo(
    () => selectActiveWorkspace({ activeWorkspaceId, workspaces }),
    [activeWorkspaceId, workspaces],
  );
  const baseContextChips = useMemo(() => contextChips(activeWorkspace.context), [activeWorkspace.context]);
  const latestTemplateRun = templateRuns[0] ?? null;

  const [selectedBlueprintId, setSelectedBlueprintId] = useState<WorkspaceBlueprintId>('stock-research');
  const [selectedTemplateId, setSelectedTemplateId] = useState<WorkspaceTaskTemplateId>('research-flow');
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<WorkspaceTemplateWorkflowId>('research-command');
  const [blueprintOverrides, setBlueprintOverrides] = useState<WorkspaceContextOverrides>({});
  const [templateOverrides, setTemplateOverrides] = useState<WorkspaceContextOverrides>({});
  const [workflowOverrides, setWorkflowOverrides] = useState<WorkspaceContextOverrides>({});

  const selectedBlueprint = WORKSPACE_BLUEPRINTS[selectedBlueprintId] ?? BLUEPRINT_OPTIONS[0];
  const selectedTemplate = WORKSPACE_TASK_TEMPLATES[selectedTemplateId] ?? TEMPLATE_OPTIONS[0];
  const selectedWorkflow = WORKSPACE_TEMPLATE_WORKFLOWS[selectedWorkflowId] ?? WORKFLOW_OPTIONS[0];

  const selectedBlueprintOverrides = useMemo(
    () => pickWorkspaceContextOverrides(blueprintOverrides, selectedBlueprint.fields),
    [blueprintOverrides, selectedBlueprint.fields],
  );
  const selectedTemplateOverrides = useMemo(
    () => pickWorkspaceContextOverrides(templateOverrides, selectedTemplate.fields),
    [selectedTemplate.fields, templateOverrides],
  );
  const selectedWorkflowOverrides = useMemo(
    () => pickWorkspaceContextOverrides(workflowOverrides, selectedWorkflow.fields),
    [selectedWorkflow.fields, workflowOverrides],
  );

  const selectedBlueprintPreview = useMemo(
    () => previewWorkspaceBlueprint(selectedBlueprint.id, activeWorkspace.context, selectedBlueprintOverrides),
    [activeWorkspace.context, selectedBlueprint.id, selectedBlueprintOverrides],
  );
  const selectedTemplatePreview = useMemo(
    () => previewTaskTemplate(selectedTemplate.id, activeWorkspace.context, selectedTemplateOverrides),
    [activeWorkspace.context, selectedTemplate.id, selectedTemplateOverrides],
  );
  const selectedWorkflowPreview = useMemo(
    () => previewTemplateWorkflow(selectedWorkflow.id, activeWorkspace.context, selectedWorkflowOverrides),
    [activeWorkspace.context, selectedWorkflow.id, selectedWorkflowOverrides],
  );
  const blueprintErrors = useMemo(
    () => collectTemplateErrors(selectedBlueprint.fields, selectedBlueprintOverrides),
    [selectedBlueprint.fields, selectedBlueprintOverrides],
  );
  const templateErrors = useMemo(
    () => collectTemplateErrors(selectedTemplate.fields, selectedTemplateOverrides),
    [selectedTemplate.fields, selectedTemplateOverrides],
  );
  const workflowErrors = useMemo(
    () => collectTemplateErrors(selectedWorkflow.fields, selectedWorkflowOverrides),
    [selectedWorkflow.fields, selectedWorkflowOverrides],
  );
  const hasBlueprintErrors = Object.keys(blueprintErrors).length > 0;
  const hasTemplateErrors = Object.keys(templateErrors).length > 0;
  const hasWorkflowErrors = Object.keys(workflowErrors).length > 0;

  const applyView = useCallback(
    (snapshot: Record<string, unknown>) => {
      if (
        snapshot.selectedBlueprintId === 'stock-research' ||
        snapshot.selectedBlueprintId === 'execution-pulse' ||
        snapshot.selectedBlueprintId === 'portfolio-review'
      ) {
        setSelectedBlueprintId(snapshot.selectedBlueprintId);
      }
      if (
        snapshot.selectedTemplateId === 'research-flow' ||
        snapshot.selectedTemplateId === 'execution-followup' ||
        snapshot.selectedTemplateId === 'portfolio-audit'
      ) {
        setSelectedTemplateId(snapshot.selectedTemplateId);
      }
      if (
        snapshot.selectedWorkflowId === 'research-command' ||
        snapshot.selectedWorkflowId === 'execution-command' ||
        snapshot.selectedWorkflowId === 'portfolio-command'
      ) {
        setSelectedWorkflowId(snapshot.selectedWorkflowId);
      }

      const nextBlueprintId =
        snapshot.selectedBlueprintId === 'stock-research' ||
        snapshot.selectedBlueprintId === 'execution-pulse' ||
        snapshot.selectedBlueprintId === 'portfolio-review'
          ? snapshot.selectedBlueprintId
          : selectedBlueprintId;
      const nextTemplateId =
        snapshot.selectedTemplateId === 'research-flow' ||
        snapshot.selectedTemplateId === 'execution-followup' ||
        snapshot.selectedTemplateId === 'portfolio-audit'
          ? snapshot.selectedTemplateId
          : selectedTemplateId;
      const nextWorkflowId =
        snapshot.selectedWorkflowId === 'research-command' ||
        snapshot.selectedWorkflowId === 'execution-command' ||
        snapshot.selectedWorkflowId === 'portfolio-command'
          ? snapshot.selectedWorkflowId
          : selectedWorkflowId;

      setBlueprintOverrides(
        restoreOverrides(snapshot.selectedBlueprintOverrides, WORKSPACE_BLUEPRINTS[nextBlueprintId]?.fields),
      );
      setTemplateOverrides(
        restoreOverrides(snapshot.selectedTemplateOverrides, WORKSPACE_TASK_TEMPLATES[nextTemplateId]?.fields),
      );
      setWorkflowOverrides(
        restoreOverrides(snapshot.selectedWorkflowOverrides, WORKSPACE_TEMPLATE_WORKFLOWS[nextWorkflowId]?.fields),
      );
    },
    [selectedBlueprintId, selectedTemplateId, selectedWorkflowId],
  );

  const currentView = useMemo<Record<string, unknown>>(
    () => ({
      selectedBlueprintId,
      selectedTemplateId,
      selectedWorkflowId,
      selectedBlueprintOverrides,
      selectedTemplateOverrides,
      selectedWorkflowOverrides,
    }),
    [
      selectedBlueprintId,
      selectedTemplateId,
      selectedWorkflowId,
      selectedBlueprintOverrides,
      selectedTemplateOverrides,
      selectedWorkflowOverrides,
    ],
  );

  const handleCreateBlueprint = useCallback(
    (blueprintId: WorkspaceBlueprintId) => {
      if (hasBlueprintErrors) {
        toast('请先修正工作区模板参数', 'warning');
        return;
      }
      const blueprint = WORKSPACE_BLUEPRINTS[blueprintId];
      createWorkspaceFromBlueprint(blueprintId, selectedBlueprintOverrides);
      toast(`已创建 ${blueprint.label}`, 'success');
    },
    [createWorkspaceFromBlueprint, hasBlueprintErrors, selectedBlueprintOverrides, toast],
  );

  const handleApplyTemplate = useCallback(
    (templateId: WorkspaceTaskTemplateId) => {
      if (hasTemplateErrors) {
        toast('请先修正任务模板参数', 'warning');
        return;
      }
      const template = WORKSPACE_TASK_TEMPLATES[templateId];
      const createdTaskIds = applyTaskTemplate(templateId, selectedTemplateOverrides);
      toast(`已向当前工作区注入 ${createdTaskIds.length} 条 ${template.label} 任务`, 'success');
    },
    [applyTaskTemplate, hasTemplateErrors, selectedTemplateOverrides, toast],
  );

  const handleApplyWorkflow = useCallback(
    (workflowId: WorkspaceTemplateWorkflowId) => {
      if (hasWorkflowErrors) {
        toast('请先修正工作流参数', 'warning');
        return;
      }
      const workflow = WORKSPACE_TEMPLATE_WORKFLOWS[workflowId];
      const result = applyTemplateWorkflow(workflowId, selectedWorkflowOverrides);
      const summary = [
        result.createdWorkspaceIds.length > 0 ? `创建 ${result.createdWorkspaceIds.length} 个工作区` : null,
        result.taskIds.length > 0 ? `注入 ${result.taskIds.length} 条任务` : null,
        result.skippedStepIds.length > 0 ? `跳过 ${result.skippedStepIds.length} 步` : null,
      ].filter(Boolean);
      toast(
        summary.length > 0 ? `${workflow.label} 已执行：${summary.join('，')}` : `${workflow.label} 当前没有可执行步骤`,
        summary.length > 0 ? 'success' : 'warning',
      );
    },
    [applyTemplateWorkflow, hasWorkflowErrors, selectedWorkflowOverrides, toast],
  );

  const handleRollbackRun = useCallback(
    (runId: string) => {
      const ok = rollbackTemplateRun(runId);
      toast(ok ? '已回滚到该次执行前的工作区快照' : '当前记录不可回滚', ok ? 'success' : 'warning');
    },
    [rollbackTemplateRun, toast],
  );

  usePageContext({
    pageKey: 'workspace-templates',
    title: '模板中心',
    summary: `当前模板中心聚焦工作区 ${activeWorkspace.name}，已选工作流 ${selectedWorkflow.label}、工作区模板 ${selectedBlueprint.label}、任务模板 ${selectedTemplate.label}，支持跨模板串行编排、依赖条件、默认值策略与执行记录回滚。`,
    tags: [
      activeWorkspace.name,
      selectedWorkflow.label,
      selectedBlueprint.label,
      selectedTemplate.label,
      `${templateRuns.length} 条运行记录`,
    ],
    suggestions: [
      `执行 ${selectedWorkflow.label}`,
      `创建 ${selectedBlueprint.label}`,
      `把 ${selectedTemplate.label} 注入当前工作区`,
      '总结当前模板参数应如何填写',
    ],
    raw: {
      activeWorkspaceId: activeWorkspace.id,
      selectedWorkflowId,
      selectedBlueprintId,
      selectedTemplateId,
      latestTemplateRunId: latestTemplateRun?.id ?? null,
      selectedWorkflowOverrides,
      selectedBlueprintOverrides,
      selectedTemplateOverrides,
    },
  });

  const pageActions = useMemo(
    () => [
      {
        id: 'workspace-templates.run-workflow',
        label: `执行 ${selectedWorkflow.label}`,
        description: '按当前工作区上下文与覆盖参数，串行执行多模板工作流',
        keywords: ['工作流', '串行编排', '组合执行'],
        scope: 'page' as const,
        pageKey: 'workspace-templates',
        run: () => {
          handleApplyWorkflow(selectedWorkflow.id);
          return { message: `已执行 ${selectedWorkflow.label}` };
        },
      },
      {
        id: 'workspace-templates.rollback-latest',
        label: latestTemplateRun ? '回滚最近执行' : '回滚最近执行',
        description: '把工作区恢复到最近一次模板执行前的快照',
        keywords: ['回滚', '模板运行', '恢复'],
        scope: 'page' as const,
        pageKey: 'workspace-templates',
        run: () => {
          if (!latestTemplateRun) {
            throw new Error('当前没有可回滚的模板执行记录');
          }
          handleRollbackRun(latestTemplateRun.id);
          return { message: '已触发最近执行回滚' };
        },
      },
      {
        id: 'workspace-templates.create-selected',
        label: `创建 ${selectedBlueprint.label}`,
        description: '按当前工作区上下文和参数覆盖创建新的工作区模板实例',
        keywords: ['工作区模板', '新建工作区', '参数化'],
        scope: 'page' as const,
        pageKey: 'workspace-templates',
        run: () => {
          handleCreateBlueprint(selectedBlueprint.id);
          return { message: `已创建 ${selectedBlueprint.label}` };
        },
      },
      {
        id: 'workspace-templates.apply-selected',
        label: `注入 ${selectedTemplate.label}`,
        description: '把选中的任务模板按参数化上下文注入当前工作区任务列表',
        keywords: ['任务模板', '注入任务', '参数化'],
        scope: 'page' as const,
        pageKey: 'workspace-templates',
        run: () => {
          handleApplyTemplate(selectedTemplate.id);
          return { message: `已注入 ${selectedTemplate.label}` };
        },
      },
    ],
    [
      handleApplyWorkflow,
      handleApplyTemplate,
      handleRollbackRun,
      handleCreateBlueprint,
      latestTemplateRun,
      selectedWorkflow.id,
      selectedWorkflow.label,
      selectedBlueprint.id,
      selectedBlueprint.label,
      selectedTemplate.id,
      selectedTemplate.label,
    ],
  );

  usePageActions(pageActions);

  return (
    <PageContainer>
      <div className="mb-3">
        <h1 className="m-0 text-lg font-semibold">模板中心</h1>
        <p className="mb-0 mt-1 text-xs text-text-secondary">
          这里把工作区模板和任务模板从工具条里抽离出来，升级成可预览、可参数化、可直接执行的编排中心。
        </p>
      </div>

      <WorkspaceToolbar
        pageKey="workspace-templates"
        currentView={currentView}
        onApplyView={applyView}
        supportsPagePanels
      />

      <SectionCard className="p-4">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.05fr)_minmax(320px,0.95fr)]">
          <div>
            <div className="text-sm font-medium text-text-primary">当前工作区上下文</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {baseContextChips.length > 0 ? (
                baseContextChips.map((chip) => (
                  <Badge key={chip} variant="neutral">
                    {chip}
                  </Badge>
                ))
              ) : (
                <span className="text-xs text-text-secondary">
                  当前工作区没有显式上下文，模板会按默认命名和默认参数展开。
                </span>
              )}
            </div>
            <p className="mb-0 mt-3 text-sm leading-6 text-text-secondary">
              工作区模板用于“一键新建完整工作区”，任务模板用于“向当前工作区注入一组流程任务”。现在两者都支持覆盖股票、账户、执行、组合、窗口等参数，不再局限于固定注入。
            </p>
          </div>
          <div className="rounded-xl border border-glass-border bg-surface-alt/40 p-3 text-xs text-text-secondary">
            <div className="font-medium text-text-primary">使用建议</div>
            <ol className="mb-0 mt-2 space-y-1 pl-4">
              <li>先基于当前工作区上下文选择最接近的模板。</li>
              <li>再只覆盖当前这次编排真正需要改变的参数，避免污染原始工作区上下文。</li>
              <li>确认预览链接和步骤正确后，再创建工作区或注入任务。</li>
            </ol>
          </div>
        </div>
      </SectionCard>

      <div className="mt-4 space-y-4">
        <SectionCard className="p-4">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="text-sm font-medium text-text-primary">跨模板工作流</div>
              <div className="mt-1 text-xs text-text-secondary">
                把 blueprint 和 task template 串成一条执行链，支持依赖条件、默认值策略和组合执行。
              </div>
            </div>
            <Badge variant="info">{WORKFLOW_OPTIONS.length} 个工作流</Badge>
          </div>

          <div className="mt-3 grid gap-3 xl:grid-cols-3">
            {WORKFLOW_OPTIONS.map((workflow) => (
              <div
                key={workflow.id}
                className={`rounded-xl border p-3 ${selectedWorkflowId === workflow.id ? 'border-primary bg-primary/5' : 'border-glass-border bg-surface-alt/40'}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-text-primary">{workflow.label}</div>
                    <div className="mt-1 text-xs leading-5 text-text-secondary">{workflow.description}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedWorkflowId(workflow.id)}
                    className="rounded border border-glass-border px-3 py-1 text-xs"
                  >
                    预览
                  </button>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Badge variant="neutral">{workflow.steps.length} 步</Badge>
                  <Badge variant="neutral">
                    {workflow.steps.filter((step) => step.kind === 'blueprint').length} 个工作区步骤
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>

        <TemplateFieldEditor
          title={`${selectedWorkflow.label} 参数`}
          description="这些参数会作为整条工作流的共享上下文，按每一步的默认值策略继续向后传递。"
          fields={selectedWorkflow.fields}
          overrides={selectedWorkflowOverrides}
          effectiveContext={selectedWorkflowPreview.context}
          errors={workflowErrors}
          onReset={() => setWorkflowOverrides({})}
          onChange={(key, value) => setWorkflowOverrides((current) => updateOverrideValue(current, key, value))}
        />

        <SectionCard className="p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-text-primary">{selectedWorkflow.label}</div>
              <div className="mt-1 text-xs text-text-secondary">
                可执行 {selectedWorkflowPreview.executableStepCount} 步，阻塞 {selectedWorkflowPreview.blockedStepCount}{' '}
                步，跳过 {selectedWorkflowPreview.skippedStepCount} 步。
              </div>
            </div>
            <button
              type="button"
              onClick={() => handleApplyWorkflow(selectedWorkflow.id)}
              disabled={hasWorkflowErrors || selectedWorkflowPreview.executableStepCount === 0}
              className="rounded border border-primary px-3 py-1.5 text-xs text-primary disabled:opacity-50"
            >
              执行工作流
            </button>
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            {selectedWorkflowPreview.workspaceName ? (
              <Badge variant="neutral">目标工作区 {selectedWorkflowPreview.workspaceName}</Badge>
            ) : null}
            <Badge variant="neutral">新建工作区 {selectedWorkflowPreview.createdWorkspaceCount} 个</Badge>
            <Badge variant="neutral">最终上下文 {contextChips(selectedWorkflowPreview.context).length} 项</Badge>
          </div>

          <div className="mt-4 space-y-3">
            {selectedWorkflowPreview.steps.map((step, index) => (
              <div key={step.id} className="rounded-xl border border-glass-border bg-surface/60 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-xs font-medium text-text-primary">
                      步骤 {index + 1} · {step.label}
                    </div>
                    <div className="mt-1 text-sm text-text-secondary">{step.description}</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge
                      variant={step.status === 'ready' ? 'success' : step.status === 'blocked' ? 'warning' : 'neutral'}
                    >
                      {step.status === 'ready' ? '可执行' : step.status === 'blocked' ? '阻塞' : '跳过'}
                    </Badge>
                    <Badge variant="neutral">{step.kind === 'blueprint' ? '工作区模板' : '任务模板'}</Badge>
                    <Badge variant="neutral">默认值 {step.defaultsStrategy}</Badge>
                  </div>
                </div>
                {step.reason ? <div className="mt-2 text-xs text-warning">{step.reason}</div> : null}
                <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-text-secondary">
                  <span>目标：{step.targetLabel}</span>
                  {step.dependsOn.length > 0 ? <span>依赖：{step.dependsOn.join(' / ')}</span> : null}
                  {step.requiredAll.length > 0 ? <span>必填：{step.requiredAll.join(' / ')}</span> : null}
                  {step.requiredAny.length > 0 ? <span>任一：{step.requiredAny.join(' / ')}</span> : null}
                  {step.workspaceName ? <span>工作区：{step.workspaceName}</span> : null}
                </div>
                <div className="mt-3 space-y-2">
                  {step.steps.map((task, taskIndex) => (
                    <div
                      key={`${step.id}-${taskIndex + 1}`}
                      className="rounded-lg border border-glass-border bg-surface px-3 py-2"
                    >
                      <div className="text-[11px] font-medium text-text-primary">
                        {taskIndex + 1}. {task.pageKey}
                      </div>
                      <div className="mt-1 text-sm text-text-primary">{task.title}</div>
                      {task.href ? <div className="mt-1 break-all text-[11px] text-text-muted">{task.href}</div> : null}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard className="p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-text-primary">模板运行态</div>
              <div className="mt-1 text-xs text-text-secondary">
                保留最近执行结果、运行记录和回滚快照，方便继续调整编排而不是盲试。
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="info">{templateRuns.length} 条记录</Badge>
              <button
                type="button"
                onClick={() => clearTemplateRuns()}
                className="rounded border border-glass-border px-3 py-1 text-xs"
              >
                清空记录
              </button>
            </div>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(320px,1.05fr)]">
            <div className="rounded-xl border border-glass-border bg-surface/60 p-4">
              <div className="text-sm font-medium text-text-primary">最近运行结果</div>
              {latestTemplateRun ? (
                <div className="mt-3 space-y-2 text-sm text-text-secondary">
                  <div>
                    名称：<span className="font-medium text-text-primary">{latestTemplateRun.label}</span>
                  </div>
                  <div>
                    类型：<span className="font-medium text-text-primary">{latestTemplateRun.kind}</span>
                  </div>
                  <div>
                    状态：<span className="font-medium text-text-primary">{latestTemplateRun.status}</span>
                  </div>
                  <div>
                    摘要：<span className="font-medium text-text-primary">{latestTemplateRun.summary}</span>
                  </div>
                  <div>
                    时间：
                    <span className="font-medium text-text-primary">
                      {new Date(latestTemplateRun.createdAt).toLocaleString('zh-CN')}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2 pt-2">
                    {latestTemplateRun.targetWorkspaceId ? (
                      <button
                        type="button"
                        onClick={() => switchWorkspace(latestTemplateRun.targetWorkspaceId!)}
                        className="rounded border border-glass-border px-3 py-1 text-xs"
                      >
                        切到目标工作区
                      </button>
                    ) : null}
                    {latestTemplateRun.status === 'applied' ? (
                      <button
                        type="button"
                        onClick={() => handleRollbackRun(latestTemplateRun.id)}
                        className="rounded border border-primary px-3 py-1 text-xs text-primary"
                      >
                        回滚最近执行
                      </button>
                    ) : null}
                  </div>
                </div>
              ) : (
                <div className="mt-3 text-xs text-text-secondary">当前还没有模板执行记录。</div>
              )}
            </div>

            <div className="space-y-3">
              {templateRuns.length > 0 ? (
                templateRuns.map((run) => (
                  <div key={run.id} className="rounded-xl border border-glass-border bg-surface/60 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <div className="text-sm font-medium text-text-primary">{run.label}</div>
                        <div className="mt-1 text-[11px] text-text-secondary">
                          {new Date(run.createdAt).toLocaleString('zh-CN')}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Badge variant={run.status === 'applied' ? 'success' : 'warning'}>{run.status}</Badge>
                        <Badge variant="neutral">{run.kind}</Badge>
                      </div>
                    </div>
                    <div className="mt-2 text-xs leading-5 text-text-secondary">{run.summary}</div>
                    <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-text-secondary">
                      {run.createdWorkspaceIds.length > 0 ? (
                        <span>工作区 {run.createdWorkspaceIds.length} 个</span>
                      ) : null}
                      {run.taskIds.length > 0 ? <span>任务 {run.taskIds.length} 条</span> : null}
                      {run.appliedStepIds.length > 0 ? <span>执行步骤 {run.appliedStepIds.length} 个</span> : null}
                      {run.skippedStepIds.length > 0 ? <span>跳过 {run.skippedStepIds.length} 个</span> : null}
                      {run.blockedStepIds.length > 0 ? <span>阻塞 {run.blockedStepIds.length} 个</span> : null}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {run.targetWorkspaceId ? (
                        <button
                          type="button"
                          onClick={() => switchWorkspace(run.targetWorkspaceId!)}
                          className="rounded border border-glass-border px-3 py-1 text-xs"
                        >
                          切到工作区
                        </button>
                      ) : null}
                      {run.status === 'applied' ? (
                        <button
                          type="button"
                          onClick={() => handleRollbackRun(run.id)}
                          className="rounded border border-primary px-3 py-1 text-xs text-primary"
                        >
                          回滚到执行前
                        </button>
                      ) : null}
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-xl border border-glass-border bg-surface/60 p-4 text-xs text-text-secondary">
                  运行记录为空。执行任一工作流、工作区模板或任务模板后，这里会保留最近运行结果和回滚入口。
                </div>
              )}
            </div>
          </div>
        </SectionCard>
      </div>

      <WorkspaceSplitLayout
        pageKey="workspace-templates"
        primary={
          <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pr-1">
            <SectionCard className="p-4">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-medium text-text-primary">工作区模板</div>
                <Badge variant="info">{BLUEPRINT_OPTIONS.length} 个模板</Badge>
              </div>

              <div className="mt-3 grid gap-3">
                {BLUEPRINT_OPTIONS.map((blueprint) => (
                  <div
                    key={blueprint.id}
                    className={`rounded-xl border p-3 ${selectedBlueprintId === blueprint.id ? 'border-primary bg-primary/5' : 'border-glass-border bg-surface-alt/40'}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-text-primary">{blueprint.label}</div>
                        <div className="mt-1 text-xs leading-5 text-text-secondary">{blueprint.description}</div>
                      </div>
                      <button
                        type="button"
                        onClick={() => setSelectedBlueprintId(blueprint.id)}
                        className="rounded border border-glass-border px-3 py-1 text-xs"
                      >
                        预览
                      </button>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Badge variant="neutral">布局 {blueprint.layoutPreset}</Badge>
                      <Badge variant="neutral">任务 {WORKSPACE_TASK_TEMPLATES[blueprint.taskTemplateId].label}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </SectionCard>

            <TemplateFieldEditor
              title={`${selectedBlueprint.label} 参数`}
              description="这些参数只作用于这次工作区创建，默认优先继承当前工作区上下文。"
              fields={selectedBlueprint.fields}
              overrides={selectedBlueprintOverrides}
              effectiveContext={selectedBlueprintPreview.context}
              errors={blueprintErrors}
              onReset={() => setBlueprintOverrides({})}
              onChange={(key, value) => setBlueprintOverrides((current) => updateOverrideValue(current, key, value))}
            />

            <SectionCard className="p-4">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-medium text-text-primary">{selectedBlueprint.label}</div>
                  <div className="mt-1 text-xs text-text-secondary">
                    将创建工作区：{selectedBlueprintPreview.workspaceName}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleCreateBlueprint(selectedBlueprint.id)}
                  disabled={hasBlueprintErrors}
                  className="rounded border border-primary px-3 py-1.5 text-xs text-primary"
                >
                  创建工作区
                </button>
              </div>
              <div className="mt-3 space-y-2">
                {selectedBlueprintPreview.steps.map((step, index) => (
                  <div
                    key={`${selectedBlueprint.id}-${index + 1}`}
                    className="rounded-xl border border-glass-border bg-surface/60 px-3 py-2"
                  >
                    <div className="text-xs font-medium text-text-primary">
                      步骤 {index + 1} · {step.pageKey}
                    </div>
                    <div className="mt-1 text-sm text-text-primary">{step.title}</div>
                    {step.kind ? (
                      <div className="mt-1 text-[11px] text-text-secondary">任务类型：{step.kind}</div>
                    ) : null}
                    {step.href ? <div className="mt-1 break-all text-[11px] text-text-muted">{step.href}</div> : null}
                  </div>
                ))}
              </div>
            </SectionCard>
          </div>
        }
        secondary={
          <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pl-1">
            <SectionCard className="p-4">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-medium text-text-primary">任务模板</div>
                <Badge variant="info">{TEMPLATE_OPTIONS.length} 个模板</Badge>
              </div>

              <div className="mt-3 grid gap-3">
                {TEMPLATE_OPTIONS.map((template) => (
                  <div
                    key={template.id}
                    className={`rounded-xl border p-3 ${selectedTemplateId === template.id ? 'border-primary bg-primary/5' : 'border-glass-border bg-surface-alt/40'}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-text-primary">{template.label}</div>
                        <div className="mt-1 text-xs leading-5 text-text-secondary">{template.description}</div>
                      </div>
                      <button
                        type="button"
                        onClick={() => setSelectedTemplateId(template.id)}
                        className="rounded border border-glass-border px-3 py-1 text-xs"
                      >
                        预览
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </SectionCard>

            <TemplateFieldEditor
              title={`${selectedTemplate.label} 参数`}
              description="这些参数只作用于这次任务注入，适合在当前工作区里快速派生新的执行链路。"
              fields={selectedTemplate.fields}
              overrides={selectedTemplateOverrides}
              effectiveContext={selectedTemplatePreview.context}
              errors={templateErrors}
              onReset={() => setTemplateOverrides({})}
              onChange={(key, value) => setTemplateOverrides((current) => updateOverrideValue(current, key, value))}
            />

            <SectionCard className="p-4">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-medium text-text-primary">{selectedTemplate.label}</div>
                  <div className="mt-1 text-xs text-text-secondary">
                    将向当前工作区 {activeWorkspace.name} 注入以下步骤
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleApplyTemplate(selectedTemplate.id)}
                  disabled={hasTemplateErrors}
                  className="rounded border border-primary px-3 py-1.5 text-xs text-primary"
                >
                  注入当前工作区
                </button>
              </div>
              <div className="mt-3 space-y-2">
                {selectedTemplatePreview.steps.map((step, index) => (
                  <div
                    key={`${selectedTemplate.id}-${index + 1}`}
                    className="rounded-xl border border-glass-border bg-surface/60 px-3 py-2"
                  >
                    <div className="text-xs font-medium text-text-primary">
                      步骤 {index + 1} · {step.pageKey}
                    </div>
                    <div className="mt-1 text-sm text-text-primary">{step.title}</div>
                    {step.kind ? (
                      <div className="mt-1 text-[11px] text-text-secondary">任务类型：{step.kind}</div>
                    ) : null}
                    {step.href ? <div className="mt-1 break-all text-[11px] text-text-muted">{step.href}</div> : null}
                  </div>
                ))}
              </div>
            </SectionCard>
          </div>
        }
      />
    </PageContainer>
  );
}
