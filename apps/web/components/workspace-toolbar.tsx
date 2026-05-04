'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Badge, SectionCard } from '@/components/ui';
import { useMobile } from '@/hooks/use-mobile';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import {
  WORKSPACE_BLUEPRINTS,
  resolveWorkspacePagePanel,
  WORKSPACE_TASK_TEMPLATES,
  resolveWorkspaceLayout,
  selectActiveWorkspace,
  useWorkbenchStore,
  type WorkspaceBlueprintId,
  type WorkspaceLayoutPreset,
  type WorkspacePagePanelMode,
  type WorkspacePageKey,
  type WorkspaceTask,
  type WorkspaceTaskTemplateId,
} from '@/store/workbench-store';

type WorkspaceToolbarProps = {
  pageKey: WorkspacePageKey;
  currentView: Record<string, unknown>;
  onApplyView: (snapshot: Record<string, unknown>) => void;
  supportsPagePanels?: boolean;
  mobileSummaryMode?: 'full' | 'hidden';
};

function nextTaskStatus(status: WorkspaceTask['status']): WorkspaceTask['status'] {
  if (status === 'todo') return 'active';
  if (status === 'active') return 'done';
  return 'todo';
}

function taskBadgeVariant(status: WorkspaceTask['status']) {
  if (status === 'done') return 'success' as const;
  if (status === 'active') return 'warning' as const;
  return 'neutral' as const;
}

function contextChips(context: ReturnType<typeof selectActiveWorkspace>['context']) {
  return [
    context.stockCode ? `股票 ${context.stockCode}` : null,
    context.strategyName ? `策略 ${context.strategyName}` : context.strategyId ? `策略 ${context.strategyId}` : null,
    context.accountId ? `账户 ${context.accountId}` : null,
    context.executionId ? `执行 ${context.executionId}` : null,
    context.artifactId ? `制品 ${context.artifactId}` : null,
    context.portfolioId ? `组合 ${context.portfolioId}` : null,
    context.benchmark ? `基准 ${context.benchmark}` : null,
    context.days ? `${context.days} 天绩效` : null,
    context.lookbackDays ? `${context.lookbackDays} 天风险` : null,
  ].filter((item): item is string => Boolean(item));
}

const LAYOUT_PRESETS: Array<{ id: WorkspaceLayoutPreset; label: string }> = [
  { id: 'research', label: '研究布局' },
  { id: 'trading', label: '交易布局' },
  { id: 'focus', label: '专注布局' },
];

const WORKSPACE_BLUEPRINT_OPTIONS = Object.values(WORKSPACE_BLUEPRINTS) as Array<{
  id: WorkspaceBlueprintId;
  label: string;
  description: string;
}>;

const TASK_TEMPLATE_OPTIONS = Object.values(WORKSPACE_TASK_TEMPLATES) as Array<{
  id: WorkspaceTaskTemplateId;
  label: string;
  description: string;
}>;

const PAGE_KEY_LABELS: Record<string, string> = {
  events: '事件中心',
  execution: '执行工作台',
  performance: '绩效中心',
  portfolio: '组合管理',
  strategy: '策略工作台',
  research: '研究工作台',
  search: '智能搜索',
  skills: '技能中心',
  screener: '条件选股',
  'strategy-detail': '策略详情',
};

function formatSyncAt(value: string | null) {
  if (!value) return '尚未同步';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '尚未同步';
  return `${parsed.toLocaleDateString('zh-CN')} ${parsed.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`;
}

export default function WorkspaceToolbar({
  pageKey,
  currentView,
  onApplyView,
  supportsPagePanels = false,
  mobileSummaryMode = 'full',
}: WorkspaceToolbarProps) {
  const router = useRouter();
  const hydrated = useWorkbenchStore((state) => state.hydrated);
  const remoteReady = useWorkbenchStore((state) => state.remoteReady);
  const syncing = useWorkbenchStore((state) => state.syncing);
  const lastSyncedAt = useWorkbenchStore((state) => state.lastSyncedAt);
  const workspaces = useWorkbenchStore((state) => state.workspaces);
  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const createWorkspace = useWorkbenchStore((state) => state.createWorkspace);
  const createWorkspaceFromBlueprint = useWorkbenchStore((state) => state.createWorkspaceFromBlueprint);
  const renameWorkspace = useWorkbenchStore((state) => state.renameWorkspace);
  const switchWorkspace = useWorkbenchStore((state) => state.switchWorkspace);
  const updateLayout = useWorkbenchStore((state) => state.updateLayout);
  const applyLayoutPreset = useWorkbenchStore((state) => state.applyLayoutPreset);
  const resetLayout = useWorkbenchStore((state) => state.resetLayout);
  const updatePagePanel = useWorkbenchStore((state) => state.updatePagePanel);
  const resetPagePanel = useWorkbenchStore((state) => state.resetPagePanel);
  const applyTaskTemplate = useWorkbenchStore((state) => state.applyTaskTemplate);
  const saveView = useWorkbenchStore((state) => state.saveView);
  const deleteView = useWorkbenchStore((state) => state.deleteView);
  const addTask = useWorkbenchStore((state) => state.addTask);
  const updateTask = useWorkbenchStore((state) => state.updateTask);
  const removeTask = useWorkbenchStore((state) => state.removeTask);
  const clearDoneTasks = useWorkbenchStore((state) => state.clearDoneTasks);
  const syncFromServer = useWorkbenchStore((state) => state.syncFromServer);
  const pushToServer = useWorkbenchStore((state) => state.pushToServer);

  const activeWorkspace = useMemo(
    () => selectActiveWorkspace({ activeWorkspaceId, workspaces }),
    [activeWorkspaceId, workspaces],
  );
  const savedViews = useMemo(
    () => activeWorkspace.savedViews.filter((view) => view.pageKey === pageKey),
    [activeWorkspace.savedViews, pageKey],
  );
  const tasks = activeWorkspace.tasks;
  const chips = useMemo(() => contextChips(activeWorkspace.context), [activeWorkspace.context]);
  const layout = useMemo(() => resolveWorkspaceLayout(activeWorkspace.layout), [activeWorkspace.layout]);
  const pagePanel = useMemo(
    () => resolveWorkspacePagePanel(layout.pagePanels?.[pageKey], pageKey),
    [layout.pagePanels, pageKey],
  );

  const [workspaceName, setWorkspaceName] = useState('');
  const [viewName, setViewName] = useState('');
  const [taskTitle, setTaskTitle] = useState('');
  const [expanded, setExpanded] = useState(false);
  const isCompactViewport = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);
  const hideOnMobile = mobileSummaryMode === 'hidden' && isCompactViewport;

  if (!hydrated) {
    return null;
  }

  if (hideOnMobile) {
    return null;
  }

  const syncVariant = syncing ? 'warning' : remoteReady ? 'success' : 'neutral';
  const activeTaskCount = tasks.filter((task) => task.status === 'active').length;
  const doneTaskCount = tasks.filter((task) => task.status === 'done').length;
  const visibleChips = chips.slice(0, 4);
  const hiddenChipCount = Math.max(0, chips.length - visibleChips.length);
  const pageLabel = PAGE_KEY_LABELS[pageKey] ?? pageKey;
  const pagePanelSummary = supportsPagePanels
    ? pagePanel.mode === 'split'
      ? `${pagePanel.secondaryPlacement === 'left' ? '左侧摘要' : '右侧摘要'} · ${pagePanel.secondarySize}%`
      : '单栏画布'
    : '标准工作台';

  return (
    <SectionCard className="mb-4 overflow-hidden p-0">
      <div className="flex flex-col gap-4 px-4 py-4 sm:px-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={syncVariant}>
                {syncing ? '同步中' : remoteReady ? '已接入云端' : '本地工作区'}
              </Badge>
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                工作区摘要
              </span>
            </div>

            <div className="mt-3 min-w-0">
              <div className="truncate text-lg font-semibold text-text-primary">{activeWorkspace.name}</div>
              <div className="mt-1 text-sm text-text-secondary">
                页面 {pageLabel} · 最近同步 {formatSyncAt(lastSyncedAt)}
              </div>
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              {visibleChips.length > 0 ? (
                visibleChips.map((chip) => (
                  <Badge key={chip} variant="neutral">
                    {chip}
                  </Badge>
                ))
              ) : (
                <span className="text-xs text-text-secondary">当前工作区还没有沉淀联动上下文。</span>
              )}
              {hiddenChipCount > 0 ? (
                <Badge variant="neutral">+{hiddenChipCount} 项上下文</Badge>
              ) : null}
            </div>
          </div>

          <div className="grid gap-2 sm:grid-cols-3 xl:w-[440px]">
            <div className="rounded-2xl border border-glass-border bg-surface-alt/44 p-3">
              <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-text-muted">当前页面</div>
              <div className="mt-2 text-sm font-medium text-text-primary">{pageLabel}</div>
              <div className="mt-1 text-xs text-text-secondary">{pagePanelSummary}</div>
            </div>
            <div className="rounded-2xl border border-glass-border bg-surface-alt/44 p-3">
              <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-text-muted">已保存视图</div>
              <div className="mt-2 text-sm font-medium text-text-primary">{savedViews.length} 个</div>
              <div className="mt-1 text-xs text-text-secondary">
                {savedViews.length > 0 ? '可直接回放当前页面状态' : '建议保存一套常用视图'}
              </div>
            </div>
            <div className="rounded-2xl border border-glass-border bg-surface-alt/44 p-3">
              <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-text-muted">跨页任务</div>
              <div className="mt-2 text-sm font-medium text-text-primary">
                {activeTaskCount} 进行中 / {doneTaskCount} 完成
              </div>
              <div className="mt-1 text-xs text-text-secondary">
                {tasks.length > 0 ? `共 ${tasks.length} 条任务` : '还没有沉淀任务编排'}
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-glass-border/80 pt-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
            <span>当前工作区支持跨页上下文、布局和任务同步。</span>
            {supportsPagePanels ? <span>双栏页面可在展开后细调摘要面板。</span> : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void syncFromServer()}
              className="rounded-full border border-glass-border px-3 py-1.5 text-xs text-text-secondary"
            >
              拉取云端
            </button>
            <button
              type="button"
              onClick={() => void pushToServer()}
              className="rounded-full border border-glass-border px-3 py-1.5 text-xs text-text-secondary"
            >
              立即同步
            </button>
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              aria-expanded={expanded}
              className="rounded-full border border-primary/30 bg-primary/8 px-3 py-1.5 text-xs text-primary"
            >
              {expanded ? '收起工作区设置' : '展开工作区设置'}
            </button>
          </div>
        </div>
      </div>

      {expanded ? (
        <div className="border-t border-glass-border bg-surface-alt/20 px-4 py-4 sm:px-5">
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)]">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-sm font-medium text-text-primary">工作区</div>
                <select
                  value={activeWorkspace.id}
                  onChange={(event) => switchWorkspace(event.target.value)}
                  className="rounded border border-glass-border px-2 py-1.5 text-sm"
                >
                  {workspaces.map((workspace) => (
                    <option key={workspace.id} value={workspace.id}>
                      {workspace.name}
                    </option>
                  ))}
                </select>
                <input
                  value={workspaceName}
                  onChange={(event) => setWorkspaceName(event.target.value)}
                  placeholder={activeWorkspace.name}
                  className="min-w-[180px] rounded border border-glass-border px-2 py-1.5 text-sm"
                />
                <button
                  type="button"
                  onClick={() => {
                    if (workspaceName.trim()) {
                      renameWorkspace(activeWorkspace.id, workspaceName.trim());
                      setWorkspaceName('');
                      return;
                    }
                    createWorkspace();
                  }}
                  className="rounded border border-glass-border px-3 py-1.5 text-sm"
                >
                  {workspaceName.trim() ? '重命名' : '新建工作区'}
                </button>
              </div>

              <div className="mt-3 rounded-xl border border-glass-border bg-surface-alt/40 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium text-text-primary">工作区模板</div>
                  <span className="text-xs text-text-secondary">基于当前上下文快速创建新工作区</span>
                </div>
                <div className="mt-3 grid gap-3 xl:grid-cols-3">
                  {WORKSPACE_BLUEPRINT_OPTIONS.map((blueprint) => (
                    <div key={blueprint.id} className="rounded-xl border border-glass-border bg-surface/60 p-3">
                      <div className="text-sm font-medium text-text-primary">{blueprint.label}</div>
                      <div className="mt-1 text-xs leading-5 text-text-secondary">{blueprint.description}</div>
                      <button
                        type="button"
                        onClick={() => createWorkspaceFromBlueprint(blueprint.id)}
                        className="mt-3 rounded border border-glass-border px-3 py-1.5 text-xs"
                      >
                        新建该工作区
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-2">
                <input
                  value={viewName}
                  onChange={(event) => setViewName(event.target.value)}
                  placeholder={`${pageKey} 视图`}
                  aria-label="工作区视图名称"
                  className="min-w-[180px] rounded border border-glass-border px-2 py-1.5 text-sm"
                />
                <button
                  type="button"
                  onClick={() => {
                    saveView(pageKey, viewName.trim(), currentView);
                    setViewName('');
                  }}
                  className="rounded border border-glass-border px-3 py-1.5 text-sm"
                >
                  保存当前视图
                </button>
                {savedViews.map((view) => (
                  <div key={view.id} className="flex items-center gap-1 rounded-full border border-glass-border px-2 py-1">
                    <button type="button" onClick={() => onApplyView(view.snapshot)} className="text-xs text-text-primary">
                      {view.name}
                    </button>
                    <button
                      type="button"
                      onClick={() => deleteView(pageKey, view.id)}
                      className="text-[11px] text-text-muted"
                      aria-label={`删除视图 ${view.name}`}
                    >
                      删除
                    </button>
                  </div>
                ))}
                {savedViews.length === 0 ? (
                  <span className="text-xs text-text-secondary">当前页面还没有保存视图。</span>
                ) : null}
              </div>

              <div className="mt-4 rounded-xl border border-glass-border bg-surface-alt/40 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium text-text-primary">工作区布局</div>
                  <button
                    type="button"
                    onClick={() => resetLayout()}
                    className="rounded border border-glass-border px-2 py-1 text-xs text-text-secondary"
                  >
                    重置布局
                  </button>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {LAYOUT_PRESETS.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => applyLayoutPreset(preset.id)}
                      className={`rounded-full border px-3 py-1 text-xs ${layout.preset === preset.id ? 'border-primary text-primary' : 'border-glass-border text-text-secondary'}`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>

                <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <label className="flex items-center justify-between gap-3 rounded-xl border border-glass-border px-3 py-2 text-xs text-text-secondary">
                    <span>左栏折叠</span>
                    <input
                      type="checkbox"
                      checked={layout.navCollapsed}
                      onChange={(event) => updateLayout({ navCollapsed: event.target.checked })}
                    />
                  </label>
                  <label className="flex items-center justify-between gap-3 rounded-xl border border-glass-border px-3 py-2 text-xs text-text-secondary">
                    <span>右栏 Copilot</span>
                    <input
                      type="checkbox"
                      checked={layout.dockVisible}
                      onChange={(event) => updateLayout({ dockVisible: event.target.checked })}
                    />
                  </label>
                  <label className="flex items-center gap-2 rounded-xl border border-glass-border px-3 py-2 text-xs text-text-secondary">
                    <span className="shrink-0">页面宽度</span>
                    <select
                      value={layout.pageWidth}
                      onChange={(event) =>
                        updateLayout({ pageWidth: event.target.value === 'focused' ? 'focused' : 'wide' })
                      }
                      className="min-w-0 flex-1 rounded border border-glass-border px-2 py-1 text-xs"
                    >
                      <option value="wide">宽版</option>
                      <option value="focused">聚焦</option>
                    </select>
                  </label>
                  <label className="flex items-center gap-2 rounded-xl border border-glass-border px-3 py-2 text-xs text-text-secondary">
                    <span className="shrink-0">信息密度</span>
                    <select
                      value={layout.density}
                      onChange={(event) =>
                        updateLayout({ density: event.target.value === 'compact' ? 'compact' : 'comfortable' })
                      }
                      className="min-w-0 flex-1 rounded border border-glass-border px-2 py-1 text-xs"
                    >
                      <option value="comfortable">舒适</option>
                      <option value="compact">紧凑</option>
                    </select>
                  </label>
                </div>

                <div className="mt-3 grid gap-3 xl:grid-cols-2">
                  <label className="rounded-xl border border-glass-border px-3 py-2 text-xs text-text-secondary">
                    <div className="flex items-center justify-between gap-2">
                      <span>左栏宽度</span>
                      <span>{layout.navWidth}px</span>
                    </div>
                    <input
                      type="range"
                      min={188}
                      max={280}
                      step={4}
                      value={layout.navWidth}
                      onChange={(event) => updateLayout({ navWidth: Number(event.target.value) })}
                      className="mt-2 w-full"
                    />
                  </label>
                  <label className="rounded-xl border border-glass-border px-3 py-2 text-xs text-text-secondary">
                    <div className="flex items-center justify-between gap-2">
                      <span>右栏宽度</span>
                      <span>{layout.dockWidth}px</span>
                    </div>
                    <input
                      type="range"
                      min={320}
                      max={480}
                      step={4}
                      value={layout.dockWidth}
                      onChange={(event) => updateLayout({ dockWidth: Number(event.target.value) })}
                      className="mt-2 w-full"
                    />
                  </label>
                </div>
              </div>

              {supportsPagePanels ? (
                <div className="mt-4 rounded-xl border border-glass-border bg-surface-alt/40 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-medium text-text-primary">当前页面板</div>
                    <button
                      type="button"
                      onClick={() => resetPagePanel(pageKey)}
                      className="rounded border border-glass-border px-2 py-1 text-xs text-text-secondary"
                    >
                      重置面板
                    </button>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {(
                      [
                        { id: 'single', label: '单栏' },
                        { id: 'split', label: '双栏' },
                      ] as Array<{ id: WorkspacePagePanelMode; label: string }>
                    ).map((option) => (
                      <button
                        key={option.id}
                        type="button"
                        onClick={() => updatePagePanel(pageKey, { mode: option.id })}
                        className={`rounded-full border px-3 py-1 text-xs ${pagePanel.mode === option.id ? 'border-primary text-primary' : 'border-glass-border text-text-secondary'}`}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>

                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <label className="flex items-center gap-2 rounded-xl border border-glass-border px-3 py-2 text-xs text-text-secondary">
                      <span className="shrink-0">子面板位置</span>
                      <select
                        value={pagePanel.secondaryPlacement}
                        onChange={(event) =>
                          updatePagePanel(pageKey, { secondaryPlacement: event.target.value === 'left' ? 'left' : 'right' })
                        }
                        className="min-w-0 flex-1 rounded border border-glass-border px-2 py-1 text-xs"
                      >
                        <option value="right">右侧</option>
                        <option value="left">左侧</option>
                      </select>
                    </label>
                    <label className="rounded-xl border border-glass-border px-3 py-2 text-xs text-text-secondary">
                      <div className="flex items-center justify-between gap-2">
                        <span>子面板宽度</span>
                        <span>{pagePanel.secondarySize}%</span>
                      </div>
                      <input
                        type="range"
                        min={24}
                        max={60}
                        step={1}
                        value={pagePanel.secondarySize}
                        onChange={(event) => updatePagePanel(pageKey, { secondarySize: Number(event.target.value) })}
                        className="mt-2 w-full"
                      />
                    </label>
                  </div>
                </div>
              ) : null}
            </div>

            <div className="rounded-xl border border-glass-border bg-surface-alt/40 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-medium text-text-primary">跨页任务编排</div>
                <button type="button" onClick={() => clearDoneTasks()} className="text-xs text-text-secondary">
                  清理已完成
                </button>
              </div>

              <div className="mt-3 grid gap-3">
                {TASK_TEMPLATE_OPTIONS.map((template) => (
                  <div key={template.id} className="rounded-xl border border-glass-border bg-surface/60 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-text-primary">{template.label}</div>
                        <div className="mt-1 text-xs leading-5 text-text-secondary">{template.description}</div>
                      </div>
                      <button
                        type="button"
                        onClick={() => applyTaskTemplate(template.id)}
                        className="rounded border border-glass-border px-3 py-1.5 text-xs"
                      >
                        注入任务
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-3 flex gap-2">
                <input
                  value={taskTitle}
                  onChange={(event) => setTaskTitle(event.target.value)}
                  placeholder="例如：去绩效页复盘这笔执行"
                  className="min-w-0 flex-1 rounded border border-glass-border px-2 py-1.5 text-sm"
                />
                <button
                  type="button"
                  onClick={() => {
                    if (!taskTitle.trim()) return;
                    addTask({ pageKey, title: taskTitle.trim() });
                    setTaskTitle('');
                  }}
                  className="rounded border border-glass-border px-3 py-1.5 text-sm"
                >
                  记入任务
                </button>
              </div>

              <div className="mt-3 space-y-2">
                {tasks.length === 0 ? (
                  <div className="text-xs text-text-secondary">当前工作区还没有编排任务。</div>
                ) : (
                  tasks.slice(0, 6).map((task) => (
                    <div
                      key={task.id}
                      className="flex items-center justify-between gap-2 rounded-xl border border-glass-border px-3 py-2"
                    >
                      <div className="min-w-0">
                        <div className="truncate text-sm text-text-primary">{task.title}</div>
                        <div className="mt-1 flex items-center gap-2 text-[11px] text-text-secondary">
                          <Badge variant={taskBadgeVariant(task.status)}>{task.status}</Badge>
                          <span>{task.pageKey}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => updateTask(task.id, { status: nextTaskStatus(task.status) })}
                          className="rounded border border-glass-border px-2 py-1 text-[11px]"
                        >
                          切换状态
                        </button>
                        {task.href ? (
                          <button
                            type="button"
                            onClick={() => {
                              const href = task.href;
                              if (!href) return;
                              updateTask(task.id, { status: 'active' });
                              router.push(href);
                            }}
                            className="rounded border border-glass-border px-2 py-1 text-[11px]"
                          >
                            打开
                          </button>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => removeTask(task.id)}
                          className="rounded border border-glass-border px-2 py-1 text-[11px]"
                        >
                          删除
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </SectionCard>
  );
}
