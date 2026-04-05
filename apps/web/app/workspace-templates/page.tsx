'use client';

import { useCallback, useMemo, useState } from 'react';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { PageContainer, useToast } from '@/components/ui';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import {
  WORKSPACE_BLUEPRINTS,
  WORKSPACE_TASK_TEMPLATES,
  WORKSPACE_TEMPLATE_WORKFLOWS,
  pickWorkspaceContextOverrides,
  previewTaskTemplate,
  previewTemplateWorkflow,
  previewWorkspaceBlueprint,
  selectActiveWorkspace,
  useWorkbenchStore,
  type WorkspaceBlueprintId,
  type WorkspaceContextOverrides,
  type WorkspaceTaskTemplateId,
  type WorkspaceTemplateWorkflowId,
} from '@/store/workbench-store';
import {
  BlueprintCatalogCard,
  BlueprintPreviewCard,
  TaskTemplateCatalogCard,
  TaskTemplatePreviewCard,
} from './components/workspace-template-catalog-panels';
import { TemplateFieldEditor } from './components/workspace-template-field-editor';
import {
  TemplateRunsCard,
  TemplateWorkflowCatalogCard,
  TemplateWorkflowPreviewCard,
  WorkspaceTemplateContextCard,
} from './components/workspace-template-overview-sections';
import {
  BLUEPRINT_OPTIONS,
  TEMPLATE_OPTIONS,
  WORKFLOW_OPTIONS,
  collectTemplateErrors,
  contextChips,
  isWorkspaceBlueprintId,
  isWorkspaceTaskTemplateId,
  isWorkspaceTemplateWorkflowId,
  restoreOverrides,
  updateOverrideValue,
} from './components/workspace-template-support';

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
      const nextBlueprintId = isWorkspaceBlueprintId(snapshot.selectedBlueprintId)
        ? snapshot.selectedBlueprintId
        : selectedBlueprintId;
      const nextTemplateId = isWorkspaceTaskTemplateId(snapshot.selectedTemplateId)
        ? snapshot.selectedTemplateId
        : selectedTemplateId;
      const nextWorkflowId = isWorkspaceTemplateWorkflowId(snapshot.selectedWorkflowId)
        ? snapshot.selectedWorkflowId
        : selectedWorkflowId;

      setSelectedBlueprintId(nextBlueprintId);
      setSelectedTemplateId(nextTemplateId);
      setSelectedWorkflowId(nextWorkflowId);
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
        label: '回滚最近执行',
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

      <WorkspaceTemplateContextCard baseContextChips={baseContextChips} />

      <div className="mt-4 space-y-4">
        <TemplateWorkflowCatalogCard
          selectedWorkflowId={selectedWorkflowId}
          onSelect={setSelectedWorkflowId}
        />

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

        <TemplateWorkflowPreviewCard
          selectedWorkflow={selectedWorkflow}
          selectedWorkflowPreview={selectedWorkflowPreview}
          hasWorkflowErrors={hasWorkflowErrors}
          onApplyWorkflow={handleApplyWorkflow}
        />

        <TemplateRunsCard
          templateRuns={templateRuns}
          latestTemplateRun={latestTemplateRun}
          onClear={clearTemplateRuns}
          onSwitchWorkspace={switchWorkspace}
          onRollbackRun={handleRollbackRun}
        />
      </div>

      <WorkspaceSplitLayout
        pageKey="workspace-templates"
        primary={
          <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pr-1">
            <BlueprintCatalogCard
              selectedBlueprintId={selectedBlueprintId}
              onSelect={setSelectedBlueprintId}
            />

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

            <BlueprintPreviewCard
              selectedBlueprint={selectedBlueprint}
              selectedBlueprintPreview={selectedBlueprintPreview}
              hasBlueprintErrors={hasBlueprintErrors}
              onCreateBlueprint={handleCreateBlueprint}
            />
          </div>
        }
        secondary={
          <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pl-1">
            <TaskTemplateCatalogCard
              selectedTemplateId={selectedTemplateId}
              onSelect={setSelectedTemplateId}
            />

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

            <TaskTemplatePreviewCard
              activeWorkspaceName={activeWorkspace.name}
              selectedTemplate={selectedTemplate}
              selectedTemplatePreview={selectedTemplatePreview}
              hasTemplateErrors={hasTemplateErrors}
              onApplyTemplate={handleApplyTemplate}
            />
          </div>
        }
      />
    </PageContainer>
  );
}
