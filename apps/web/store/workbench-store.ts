import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { authedFetch, extractApiErrorMessage, unwrapApiEnvelope } from '@/lib/api';
import type {
  WorkspaceLayout,
  WorkspaceLayoutPreset,
  WorkspacePagePanelLayout,
  WorkspacePageKey,
  WorkspaceRecord,
  WorkspaceSharedContext,
  WorkspaceStateSnapshot,
  WorkspaceTask,
  WorkspaceTaskStatus,
} from '@aiask/shared-types';
import {
  DEFAULT_WORKSPACE_LAYOUT,
  resolveWorkspaceLayout,
  resolveWorkspacePagePanel,
  resolveWorkspacePagePanels,
  WORKSPACE_LAYOUT_PRESETS,
} from './workbench-layout';
import {
  WORKSPACE_BLUEPRINTS,
  WORKSPACE_TASK_TEMPLATES,
  WORKSPACE_TEMPLATE_WORKFLOWS,
  applyContextPatch,
  buildTemplateTasks,
  formatTemplateRunSummary,
  normalizeWorkspaceContextOverrides,
  pickWorkspaceContextOverrides,
  previewTaskTemplate,
  previewTemplateWorkflow,
  previewWorkspaceBlueprint,
  resolveWorkspaceTemplateContext,
  type ApplyTemplateWorkflowResult,
  type WorkspaceBlueprintId,
  type WorkspaceContextOverrides,
  type WorkspaceContextPatch,
  type WorkspaceTaskTemplateId,
  type WorkspaceTemplateRunRecord,
  type WorkspaceTemplateWorkflowId,
} from './workbench-templates';

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
export {
  normalizeWorkspaceContextOverrides,
  pickWorkspaceContextOverrides,
  previewTaskTemplate,
  previewTemplateWorkflow,
  previewWorkspaceBlueprint,
  resolveWorkspaceLayout,
  resolveWorkspacePagePanel,
  resolveWorkspaceTemplateContext,
  WORKSPACE_BLUEPRINTS,
  WORKSPACE_LAYOUT_PRESETS,
  WORKSPACE_TASK_TEMPLATES,
  WORKSPACE_TEMPLATE_WORKFLOWS,
};
export type {
  ApplyTemplateWorkflowResult,
  WorkspaceBlueprintId,
  WorkspaceContextOverrides,
  WorkspaceContextPatch,
  WorkspaceTemplateFieldDefinition,
  WorkspaceTaskTemplateId,
  WorkspaceTemplateRunRecord,
  WorkspaceTemplateWorkflowId,
} from './workbench-templates';

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
function now() {
  return Date.now();
}

function makeId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
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

function taskFingerprint(task: Pick<WorkspaceTask, 'pageKey' | 'title' | 'href' | 'kind'>) {
  return `${task.pageKey}::${task.title}::${task.href ?? ''}::${task.kind ?? ''}`;
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
  const nextPreset = patch.preset ?? 'custom';
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
          tasks: buildTemplateTasks(preview.taskTemplateId, preview.context, timestamp, makeId),
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
        const nextTasks = buildTemplateTasks(templateId, preview.context, timestamp, makeId);
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
              tasks: step.taskTemplateId ? buildTemplateTasks(step.taskTemplateId, step.context, timestamp, makeId) : [],
            };
            nextWorkspaces = [...nextWorkspaces, workspace];
            targetWorkspaceId = workspaceId;
            result.createdWorkspaceIds.push(workspaceId);
            result.taskIds.push(...workspace.tasks.map((task) => task.id));
            result.appliedStepIds.push(step.id);
            result.targetWorkspaceId = workspaceId;
            return;
          }

          const nextTasks = buildTemplateTasks(step.targetId as WorkspaceTaskTemplateId, step.context, timestamp, makeId);
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
          set({ remoteReady: false });
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
          set({ remoteReady: false });
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
