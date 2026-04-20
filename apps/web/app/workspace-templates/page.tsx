'use client';

import { useCallback, useMemo, useState } from 'react';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { Badge, PageContainer, SectionCard, TabBar, useToast } from '@/components/ui';
import { useHydrated } from '@/hooks/use-hydrated';
import { useMobile } from '@/hooks/use-mobile';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
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
  const hydrated = useHydrated();
  const compactLayoutDetected = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
  const compactLayout = hydrated ? compactLayoutDetected : true;
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
  const [lastPrimaryWorkflowAt, setLastPrimaryWorkflowAt] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<'workflow' | 'blueprint' | 'task'>('workflow');
  const [workflowCompactView, setWorkflowCompactView] = useState<'preview' | 'parameters' | 'catalog' | 'history'>(
    'preview',
  );
  const [blueprintCompactView, setBlueprintCompactView] = useState<'preview' | 'parameters' | 'catalog'>('preview');
  const [taskCompactView, setTaskCompactView] = useState<'preview' | 'parameters' | 'catalog'>('preview');

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
      setLastPrimaryWorkflowAt(new Date().toLocaleString('zh-CN'));
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
      {!compactLayout ? (
        <div className="mb-3">
          <h1 className="m-0 text-lg font-semibold">模板中心</h1>
          <p className="mb-0 mt-1 text-xs text-text-secondary">
            这里把工作区模板和任务模板从工具条里抽离出来，升级成可预览、可参数化、可直接执行的编排中心。
          </p>
        </div>
      ) : null}

      <SectionCard className={compactLayout ? 'p-3.5' : 'p-4'}>
        <div className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(320px,1.05fr)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">{templateRuns.length} 条运行记录</Badge>
              <Badge variant={hasWorkflowErrors ? 'warning' : 'success'}>
                {hasWorkflowErrors ? '工作流参数待修正' : '工作流可执行'}
              </Badge>
              <Badge variant="neutral">当前工作区 {activeWorkspace.name}</Badge>
            </div>
            {!compactLayout ? (
              <p className="mb-0 mt-3 text-sm leading-6 text-text-secondary">
                模板中心现在优先收口到“先预览当前工作流，再决定是否执行”。工作流仍然是主入口，蓝图创建和任务注入作为分区动作保留在下半屏。
              </p>
            ) : null}
            {compactLayout ? (
              <div className="mt-4">
                <TabBar
                  tabs={[
                    { key: 'workflow', label: '工作流执行' },
                    { key: 'blueprint', label: '蓝图创建' },
                    { key: 'task', label: '任务模板' },
                  ]}
                  active={activeSection}
                  onChange={setActiveSection}
                />
              </div>
            ) : null}
            <div className="mt-4 flex flex-wrap gap-2">
              {activeSection === 'workflow' ? (
                <button
                  type="button"
                  onClick={() => handleApplyWorkflow(selectedWorkflow.id)}
                  disabled={hasWorkflowErrors || selectedWorkflowPreview.executableStepCount === 0}
                  data-testid="page-primary-action"
                  data-action-testid="workspace-templates-run-action"
                  className="inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  执行 {selectedWorkflow.label}
                </button>
              ) : null}
              {activeSection === 'blueprint' ? (
                <button
                  type="button"
                  onClick={() => handleCreateBlueprint(selectedBlueprint.id)}
                  disabled={hasBlueprintErrors}
                  className="inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  创建 {selectedBlueprint.label}
                </button>
              ) : null}
              {activeSection === 'task' ? (
                <button
                  type="button"
                  onClick={() => handleApplyTemplate(selectedTemplate.id)}
                  disabled={hasTemplateErrors}
                  className="inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  注入 {selectedTemplate.label}
                </button>
              ) : null}
              {!compactLayout ? (
                <>
                  <button
                    type="button"
                    onClick={() => handleCreateBlueprint(selectedBlueprint.id)}
                    disabled={hasBlueprintErrors}
                    className="rounded-full border border-glass-border bg-white/35 px-4 py-2 text-sm text-text-primary shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    创建 {selectedBlueprint.label}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleApplyTemplate(selectedTemplate.id)}
                    disabled={hasTemplateErrors}
                    className="rounded-full border border-glass-border bg-white/35 px-4 py-2 text-sm text-text-primary shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    注入 {selectedTemplate.label}
                  </button>
                </>
              ) : null}
            </div>
            {compactLayout ? (
              <details className="mt-3 rounded-[22px] border border-white/50 bg-white/24 px-4 py-3 text-sm text-text-secondary">
                <summary className="cursor-pointer list-none font-medium text-text-primary">展开次要操作</summary>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => handleApplyWorkflow(selectedWorkflow.id)}
                    disabled={hasWorkflowErrors || selectedWorkflowPreview.executableStepCount === 0}
                    className="rounded-full border border-glass-border bg-white/35 px-4 py-2 text-sm text-text-primary shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    执行 {selectedWorkflow.label}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleCreateBlueprint(selectedBlueprint.id)}
                    disabled={hasBlueprintErrors}
                    className="rounded-full border border-glass-border bg-white/35 px-4 py-2 text-sm text-text-primary shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    创建 {selectedBlueprint.label}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleApplyTemplate(selectedTemplate.id)}
                    disabled={hasTemplateErrors}
                    className="rounded-full border border-glass-border bg-white/35 px-4 py-2 text-sm text-text-primary shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    注入 {selectedTemplate.label}
                  </button>
                </div>
              </details>
            ) : null}
            {compactLayout ? (
              <div data-testid="page-primary-status" className="mt-3 text-xs text-text-secondary">
                当前聚焦
                <span className="font-medium text-text-primary">
                  {' '}
                  {activeSection === 'workflow'
                    ? selectedWorkflow.label
                    : activeSection === 'blueprint'
                      ? selectedBlueprint.label
                      : selectedTemplate.label}
                </span>
                ，可执行 {selectedWorkflowPreview.executableStepCount} 步。
              </div>
            ) : (
              <div
                data-testid="page-primary-status"
                className="mt-4 rounded-[22px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
              >
                <>
                  <div className="font-medium text-text-primary">
                    当前工作流 {selectedWorkflow.label} ｜ 蓝图 {selectedBlueprint.label} ｜ 任务模板{' '}
                    {selectedTemplate.label}
                  </div>
                  <p className="mt-1 mb-0 text-xs leading-6 text-text-secondary">
                    可执行步骤 {selectedWorkflowPreview.executableStepCount} 个 ｜ 阻塞{' '}
                    {selectedWorkflowPreview.blockedStepCount} 个 ｜ 跳过 {selectedWorkflowPreview.skippedStepCount} 个
                  </p>
                  <p className="mt-2 mb-0 text-xs text-text-secondary">
                    最近运行：{latestTemplateRun ? latestTemplateRun.summary : '当前还没有模板执行记录'}
                    {lastPrimaryWorkflowAt ? ` ｜ 主动作时间：${lastPrimaryWorkflowAt}` : ''}
                  </p>
                </>
              </div>
            )}
          </div>
          {!compactLayout ? (
            <div className="rounded-xl border border-glass-border bg-surface-alt/40 p-3 text-xs text-text-secondary">
              <div className="font-medium text-text-primary">收口原则</div>
              <ol className="mb-0 mt-2 space-y-1 pl-4">
                <li>主动作只保留当前选中工作流的执行入口。</li>
                <li>蓝图创建和任务注入继续保留，但下沉为次动作。</li>
                <li>所有结果先看最近运行摘要，再决定是否下钻到具体步骤。</li>
              </ol>
            </div>
          ) : null}
        </div>
      </SectionCard>

      {!compactLayout ? (
        <WorkspaceToolbar
          pageKey="workspace-templates"
          currentView={currentView}
          onApplyView={applyView}
          supportsPagePanels
        />
      ) : null}
      <div className="mt-4 space-y-4">
        {!compactLayout ? (
          <SectionCard className="p-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="eyebrow">Main Sections</div>
              <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">按主任务切换模板中心</h2>
              <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">
                默认只展开一个主区域，先完成当前编排动作，再决定是否进入蓝图创建或任务注入，避免把整页堆成多层管理台。
              </p>
            </div>
            <TabBar
              tabs={[
                { key: 'workflow', label: '工作流执行' },
                { key: 'blueprint', label: '蓝图创建' },
                { key: 'task', label: '任务模板' },
              ]}
              active={activeSection}
              onChange={setActiveSection}
            />
          </div>
          </SectionCard>
        ) : null}

        {activeSection === 'workflow' && compactLayout ? (
          <SectionCard className="p-4">
            <div className="flex flex-col gap-4">
              <div>
                <div className="eyebrow">Workflow View</div>
                <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">当前工作流只展开一个子视图</h2>
                <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">默认先看预览，其他信息按需再切。</p>
              </div>
              <TabBar
                tabs={[
                  { key: 'preview', label: '预览' },
                  { key: 'parameters', label: '参数' },
                  { key: 'catalog', label: '目录' },
                  { key: 'history', label: '记录/上下文' },
                ]}
                active={workflowCompactView}
                onChange={(key) => setWorkflowCompactView(key as typeof workflowCompactView)}
              />
              {workflowCompactView === 'preview' ? (
                <TemplateWorkflowPreviewCard
                  selectedWorkflow={selectedWorkflow}
                  selectedWorkflowPreview={selectedWorkflowPreview}
                  hasWorkflowErrors={hasWorkflowErrors}
                  onApplyWorkflow={handleApplyWorkflow}
                />
              ) : null}
              {workflowCompactView === 'parameters' ? (
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
              ) : null}
              {workflowCompactView === 'catalog' ? (
                <TemplateWorkflowCatalogCard selectedWorkflowId={selectedWorkflowId} onSelect={setSelectedWorkflowId} />
              ) : null}
              {workflowCompactView === 'history' ? (
                <div className="space-y-4">
                  <WorkspaceTemplateContextCard baseContextChips={baseContextChips} />
                  <TemplateRunsCard
                    templateRuns={templateRuns}
                    latestTemplateRun={latestTemplateRun}
                    onClear={clearTemplateRuns}
                    onSwitchWorkspace={switchWorkspace}
                    onRollbackRun={handleRollbackRun}
                  />
                </div>
              ) : null}
            </div>
          </SectionCard>
        ) : null}

        {activeSection === 'workflow' && !compactLayout ? (
          <div className="space-y-4">
            <details className="overflow-hidden rounded-[24px] border border-white/45 bg-white/24 p-4">
              <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开工作区上下文</summary>
              <div className="mt-4">
                <WorkspaceTemplateContextCard baseContextChips={baseContextChips} />
              </div>
            </details>

            {compactLayout ? (
              <details className="overflow-hidden rounded-[24px] border border-white/45 bg-white/24 p-4">
                <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开工作流目录</summary>
                <div className="mt-4">
                  <TemplateWorkflowCatalogCard selectedWorkflowId={selectedWorkflowId} onSelect={setSelectedWorkflowId} />
                </div>
              </details>
            ) : (
              <TemplateWorkflowCatalogCard selectedWorkflowId={selectedWorkflowId} onSelect={setSelectedWorkflowId} />
            )}

            <details className="overflow-hidden rounded-[24px] border border-white/45 bg-white/24 p-4">
              <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">
                展开工作流参数编辑
              </summary>
              <div className="mt-4">
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
              </div>
            </details>

            <TemplateWorkflowPreviewCard
              selectedWorkflow={selectedWorkflow}
              selectedWorkflowPreview={selectedWorkflowPreview}
              hasWorkflowErrors={hasWorkflowErrors}
              onApplyWorkflow={handleApplyWorkflow}
            />

            <details className="overflow-hidden rounded-[24px] border border-white/45 bg-white/24 p-4">
              <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开运行记录</summary>
              <div className="mt-4">
                <TemplateRunsCard
                  templateRuns={templateRuns}
                  latestTemplateRun={latestTemplateRun}
                  onClear={clearTemplateRuns}
                  onSwitchWorkspace={switchWorkspace}
                  onRollbackRun={handleRollbackRun}
                />
              </div>
            </details>
          </div>
        ) : null}

        {activeSection === 'blueprint' && compactLayout ? (
          <SectionCard className="p-4">
            <div className="flex flex-col gap-4">
              <div>
                <div className="eyebrow">Blueprint View</div>
                <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">蓝图页默认只展开一个子视图</h2>
                <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">默认先看蓝图预览，再决定是否切到参数或目录。</p>
              </div>
              <TabBar
                tabs={[
                  { key: 'preview', label: '预览' },
                  { key: 'parameters', label: '参数' },
                  { key: 'catalog', label: '目录' },
                ]}
                active={blueprintCompactView}
                onChange={(key) => setBlueprintCompactView(key as typeof blueprintCompactView)}
              />
              {blueprintCompactView === 'preview' ? (
                <BlueprintPreviewCard
                  selectedBlueprint={selectedBlueprint}
                  selectedBlueprintPreview={selectedBlueprintPreview}
                  hasBlueprintErrors={hasBlueprintErrors}
                  onCreateBlueprint={handleCreateBlueprint}
                />
              ) : null}
              {blueprintCompactView === 'parameters' ? (
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
              ) : null}
              {blueprintCompactView === 'catalog' ? (
                <BlueprintCatalogCard selectedBlueprintId={selectedBlueprintId} onSelect={setSelectedBlueprintId} />
              ) : null}
            </div>
          </SectionCard>
        ) : null}

        {activeSection === 'blueprint' && !compactLayout ? (
          <div className="space-y-4">
            {compactLayout ? (
              <details className="overflow-hidden rounded-[24px] border border-white/45 bg-white/24 p-4">
                <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开蓝图目录</summary>
                <div className="mt-4">
                  <BlueprintCatalogCard selectedBlueprintId={selectedBlueprintId} onSelect={setSelectedBlueprintId} />
                </div>
              </details>
            ) : (
              <BlueprintCatalogCard selectedBlueprintId={selectedBlueprintId} onSelect={setSelectedBlueprintId} />
            )}

            <details className="overflow-hidden rounded-[24px] border border-white/45 bg-white/24 p-4">
              <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">
                展开蓝图参数编辑
              </summary>
              <div className="mt-4">
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
              </div>
            </details>

            <BlueprintPreviewCard
              selectedBlueprint={selectedBlueprint}
              selectedBlueprintPreview={selectedBlueprintPreview}
              hasBlueprintErrors={hasBlueprintErrors}
              onCreateBlueprint={handleCreateBlueprint}
            />
          </div>
        ) : null}

        {activeSection === 'task' && compactLayout ? (
          <SectionCard className="p-4">
            <div className="flex flex-col gap-4">
              <div>
                <div className="eyebrow">Task View</div>
                <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">任务模板页默认只展开一个子视图</h2>
                <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">先确认会注入什么，再在需要时调整参数或回看目录。</p>
              </div>
              <TabBar
                tabs={[
                  { key: 'preview', label: '预览' },
                  { key: 'parameters', label: '参数' },
                  { key: 'catalog', label: '目录' },
                ]}
                active={taskCompactView}
                onChange={(key) => setTaskCompactView(key as typeof taskCompactView)}
              />
              {taskCompactView === 'preview' ? (
                <TaskTemplatePreviewCard
                  activeWorkspaceName={activeWorkspace.name}
                  selectedTemplate={selectedTemplate}
                  selectedTemplatePreview={selectedTemplatePreview}
                  hasTemplateErrors={hasTemplateErrors}
                  onApplyTemplate={handleApplyTemplate}
                />
              ) : null}
              {taskCompactView === 'parameters' ? (
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
              ) : null}
              {taskCompactView === 'catalog' ? (
                <TaskTemplateCatalogCard selectedTemplateId={selectedTemplateId} onSelect={setSelectedTemplateId} />
              ) : null}
            </div>
          </SectionCard>
        ) : null}

        {activeSection === 'task' && !compactLayout ? (
          <div className="space-y-4">
            {compactLayout ? (
              <details className="overflow-hidden rounded-[24px] border border-white/45 bg-white/24 p-4">
                <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开任务模板目录</summary>
                <div className="mt-4">
                  <TaskTemplateCatalogCard selectedTemplateId={selectedTemplateId} onSelect={setSelectedTemplateId} />
                </div>
              </details>
            ) : (
              <TaskTemplateCatalogCard selectedTemplateId={selectedTemplateId} onSelect={setSelectedTemplateId} />
            )}

            <details className="overflow-hidden rounded-[24px] border border-white/45 bg-white/24 p-4">
              <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">
                展开任务模板参数编辑
              </summary>
              <div className="mt-4">
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
              </div>
            </details>

            <TaskTemplatePreviewCard
              activeWorkspaceName={activeWorkspace.name}
              selectedTemplate={selectedTemplate}
              selectedTemplatePreview={selectedTemplatePreview}
              hasTemplateErrors={hasTemplateErrors}
              onApplyTemplate={handleApplyTemplate}
            />
          </div>
        ) : null}
      </div>
    </PageContainer>
  );
}
