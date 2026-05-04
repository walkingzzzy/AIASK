import { Injectable } from '@nestjs/common';
import type {
  WorkspaceLayout,
  WorkspaceRecord,
  WorkspaceSavedView,
  WorkspaceSharedContext,
  WorkspaceStateSnapshot,
  WorkspaceTask,
} from '@aiask/shared-types';
import { PreferencesService } from '../auth/preferences.service';

type UserPreferencesRecord = Record<string, unknown> & {
  workspaceState?: unknown;
};

@Injectable()
export class WorkspaceService {
  private static readonly DEFAULT_WORKSPACE_ID = 'default-workspace';
  private static readonly MAX_WORKSPACES = 10;
  private static readonly MAX_SAVED_VIEWS = 20;
  private static readonly MAX_TASKS = 50;
  private static readonly NAV_WIDTH_MIN = 188;
  private static readonly NAV_WIDTH_MAX = 280;
  private static readonly DOCK_WIDTH_MIN = 320;
  private static readonly DOCK_WIDTH_MAX = 480;
  private static readonly PAGE_PANEL_SIZE_MIN = 24;
  private static readonly PAGE_PANEL_SIZE_MAX = 60;

  constructor(private readonly preferencesService: PreferencesService) {}

  async getState(userId: string): Promise<WorkspaceStateSnapshot> {
    const prefs = await this.preferencesService.getUserPreferences(userId) as UserPreferencesRecord;
    return this.normalizeSnapshot(prefs.workspaceState, false);
  }

  async saveState(userId: string, snapshot: unknown): Promise<WorkspaceStateSnapshot> {
    const normalized = this.normalizeSnapshot(snapshot, true);
    const prefs = await this.preferencesService.getUserPreferences(userId) as UserPreferencesRecord;
    await this.preferencesService.setUserPreferences(userId, {
      ...prefs,
      workspaceState: normalized,
    });
    return normalized;
  }

  private normalizeSnapshot(value: unknown, touchUpdatedAt: boolean): WorkspaceStateSnapshot {
    const record = this.asRecord(value);
    const rawWorkspaces = Array.isArray(record.workspaces) ? record.workspaces : [];
    const seenWorkspaceIds = new Set<string>();
    const workspaces = rawWorkspaces
      .map((item, index) => this.normalizeWorkspace(item, index))
      .filter((workspace) => {
        if (seenWorkspaceIds.has(workspace.id)) return false;
        seenWorkspaceIds.add(workspace.id);
        return true;
      })
      .slice(0, WorkspaceService.MAX_WORKSPACES);

    const safeWorkspaces = workspaces.length > 0
      ? workspaces
      : [this.createWorkspaceRecord()];
    const requestedActiveId = this.toNonEmptyString(record.activeWorkspaceId);
    const activeWorkspaceId = safeWorkspaces.some((workspace) => workspace.id === requestedActiveId)
      ? requestedActiveId!
      : safeWorkspaces[0].id;

    return {
      activeWorkspaceId,
      workspaces: safeWorkspaces,
      updatedAt: touchUpdatedAt
        ? new Date().toISOString()
        : this.toIsoString(record.updatedAt) ?? null,
    };
  }

  private normalizeWorkspace(value: unknown, index: number): WorkspaceRecord {
    const record = this.asRecord(value);
    const id = this.toNonEmptyString(record.id) ?? `workspace-${index + 1}`;
    const name = this.toNonEmptyString(record.name) ?? `工作区 ${index + 1}`;
    const createdAt = this.toTimestamp(record.createdAt);
    const updatedAt = this.toTimestamp(record.updatedAt) ?? createdAt;
    const layout = this.normalizeLayout(record.layout);
    const context = this.normalizeContext(record.context);
    const savedViews = this.normalizeSavedViews(record.savedViews);
    const tasks = this.normalizeTasks(record.tasks);

    return {
      id,
      name,
      createdAt,
      updatedAt,
      layout,
      context,
      savedViews,
      tasks,
    };
  }

  private normalizeLayout(value: unknown): WorkspaceLayout {
    const record = this.asRecord(value);
    const preset = this.toLayoutPreset(record.preset);
    const base = this.layoutPreset(preset);

    return {
      preset,
      navCollapsed: this.toBoolean(record.navCollapsed) ?? base.navCollapsed,
      navWidth: this.clampInteger(record.navWidth, WorkspaceService.NAV_WIDTH_MIN, WorkspaceService.NAV_WIDTH_MAX, base.navWidth ?? 208),
      dockVisible: this.toBoolean(record.dockVisible) ?? base.dockVisible,
      dockWidth: this.clampInteger(record.dockWidth, WorkspaceService.DOCK_WIDTH_MIN, WorkspaceService.DOCK_WIDTH_MAX, base.dockWidth ?? 380),
      dockPreference: this.toDockPreference(record.dockPreference) ?? base.dockPreference,
      density: this.toDensity(record.density) ?? base.density,
      pageWidth: this.toPageWidth(record.pageWidth) ?? base.pageWidth,
      pageLayoutMode: this.toPageLayoutMode(record.pageLayoutMode) ?? base.pageLayoutMode,
      minMainWidth: this.clampInteger(record.minMainWidth, 920, 1440, base.minMainWidth ?? 1080),
      pagePanels: this.normalizePagePanels(record.pagePanels),
    };
  }

  private normalizePagePanels(value: unknown): NonNullable<WorkspaceLayout['pagePanels']> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return {};
    }

    return Object.entries(value as Record<string, unknown>).reduce<NonNullable<WorkspaceLayout['pagePanels']>>((acc, [pageKey, panel]) => {
      const safePageKey = this.toNonEmptyString(pageKey);
      if (!safePageKey) return acc;
      const record = this.asRecord(panel);
      acc[safePageKey] = {
        mode: this.toPagePanelMode(record.mode) ?? 'single',
        secondaryPlacement: this.toPagePanelPlacement(record.secondaryPlacement) ?? 'right',
        secondarySize: this.clampInteger(
          record.secondarySize,
          WorkspaceService.PAGE_PANEL_SIZE_MIN,
          WorkspaceService.PAGE_PANEL_SIZE_MAX,
          38,
        ),
      };
      return acc;
    }, {});
  }

  private normalizeContext(value: unknown): WorkspaceSharedContext {
    const record = this.asRecord(value);
    const context: WorkspaceSharedContext = {};

    const stockCode = this.toNonEmptyString(record.stockCode);
    if (stockCode) context.stockCode = stockCode;

    const stockConfirmedAt = this.toIsoString(record.stockConfirmedAt);
    if (stockConfirmedAt) context.stockConfirmedAt = stockConfirmedAt;

    const accountId = this.toNonEmptyString(record.accountId);
    if (accountId) context.accountId = accountId;

    const executionId = this.toNonEmptyString(record.executionId);
    if (executionId) context.executionId = executionId;

    const artifactId = this.toNonEmptyString(record.artifactId);
    if (artifactId) context.artifactId = artifactId;

    const copilotConversationId = this.toNonEmptyString(record.copilotConversationId);
    if (copilotConversationId) context.copilotConversationId = copilotConversationId;

    const portfolioId = this.toNonEmptyString(record.portfolioId);
    if (portfolioId) context.portfolioId = portfolioId;

    const benchmark = this.toNonEmptyString(record.benchmark);
    if (benchmark) context.benchmark = benchmark;

    const mode = this.toNonEmptyString(record.mode);
    if (mode === 'account' || mode === 'portfolio') context.mode = mode;

    const days = this.toPositiveInteger(record.days);
    if (days != null) context.days = days;

    const lookbackDays = this.toPositiveInteger(record.lookbackDays);
    if (lookbackDays != null) context.lookbackDays = lookbackDays;

    const eventCode = this.toNonEmptyString(record.eventCode);
    if (eventCode) context.eventCode = eventCode;

    const strategyId = this.toNonEmptyString(record.strategyId);
    if (strategyId) context.strategyId = strategyId;

    const strategyName = this.toNonEmptyString(record.strategyName);
    if (strategyName) context.strategyName = strategyName;

    const linkedStrategyId = this.toNonEmptyString(record.linkedStrategyId);
    if (linkedStrategyId) context.linkedStrategyId = linkedStrategyId;

    const linkedStrategyName = this.toNonEmptyString(record.linkedStrategyName);
    if (linkedStrategyName) context.linkedStrategyName = linkedStrategyName;

    const screenerQuery = this.toNonEmptyString(record.screenerQuery);
    if (screenerQuery) context.screenerQuery = screenerQuery;

    const sourcePage = this.toNonEmptyString(record.sourcePage);
    if (sourcePage) context.sourcePage = sourcePage;

    const taskType = this.toNonEmptyString(record.taskType);
    if (taskType) context.taskType = taskType;

    const resultType = this.toNonEmptyString(record.resultType);
    if (resultType) context.resultType = resultType;

    const strategyTestMode = this.toNonEmptyString(record.strategyTestMode);
    if (strategyTestMode === 'personal-strategy' || strategyTestMode === 'factory-incubation') {
      context.strategyTestMode = strategyTestMode;
    }

    return context;
  }

  private normalizeSavedViews(value: unknown): WorkspaceSavedView[] {
    if (!Array.isArray(value)) return [];
    const seen = new Set<string>();
    return value
      .map((item, index) => {
        const record = this.asRecord(item);
        const pageKey = this.toNonEmptyString(record.pageKey) ?? 'workspace';
        const id = this.toNonEmptyString(record.id) ?? `view-${pageKey}-${index + 1}`;
        const name = this.toNonEmptyString(record.name) ?? `${pageKey} 视图 ${index + 1}`;
        const createdAt = this.toTimestamp(record.createdAt);
        const updatedAt = this.toTimestamp(record.updatedAt);
        const snapshot = this.toSerializableRecord(record.snapshot);

        return {
          id,
          pageKey,
          name,
          snapshot,
          createdAt,
          updatedAt,
        } satisfies WorkspaceSavedView;
      })
      .filter((view) => {
        if (seen.has(view.id)) return false;
        seen.add(view.id);
        return true;
      })
      .slice(0, WorkspaceService.MAX_SAVED_VIEWS);
  }

  private normalizeTasks(value: unknown): WorkspaceTask[] {
    if (!Array.isArray(value)) return [];
    const seen = new Set<string>();
    return value
      .map((item, index) => {
        const record = this.asRecord(item);
        const pageKey = this.toNonEmptyString(record.pageKey) ?? 'workspace';
        const id = this.toNonEmptyString(record.id) ?? `task-${pageKey}-${index + 1}`;
        const title = this.toNonEmptyString(record.title) ?? `任务 ${index + 1}`;
        const status = this.toTaskStatus(record.status);
        const href = this.toNonEmptyString(record.href);
        const kind = this.toNonEmptyString(record.kind);
        const payload = this.toSerializableRecord(record.payload);
        const createdAt = this.toTimestamp(record.createdAt);
        const updatedAt = this.toTimestamp(record.updatedAt) ?? createdAt;

        const task: WorkspaceTask = {
          id,
          pageKey,
          title,
          status,
          payload: Object.keys(payload).length > 0 ? payload : undefined,
          createdAt,
          updatedAt,
        };
        if (href) task.href = href;
        if (kind) task.kind = kind;
        return task;
      })
      .filter((task) => {
        if (seen.has(task.id)) return false;
        seen.add(task.id);
        return true;
      })
      .slice(0, WorkspaceService.MAX_TASKS);
  }

  private createWorkspaceRecord(): WorkspaceRecord {
    const timestamp = Date.now();
    return {
      id: WorkspaceService.DEFAULT_WORKSPACE_ID,
      name: '默认工作区',
      createdAt: timestamp,
      updatedAt: timestamp,
      layout: this.layoutPreset('research'),
      context: {},
      savedViews: [],
      tasks: [],
    };
  }

  private layoutPreset(preset: WorkspaceLayout['preset']): WorkspaceLayout {
    if (preset === 'trading') {
      return {
        preset: 'trading',
        navCollapsed: false,
        navWidth: 220,
        dockVisible: false,
        dockWidth: 430,
        dockPreference: 'auto',
        density: 'compact',
        pageWidth: 'wide',
        pageLayoutMode: 'workspace',
        minMainWidth: 1160,
      };
    }

    if (preset === 'focus') {
      return {
        preset: 'focus',
        navCollapsed: true,
        navWidth: 208,
        dockVisible: false,
        dockWidth: 360,
        dockPreference: 'hidden',
        density: 'comfortable',
        pageWidth: 'focused',
        pageLayoutMode: 'utility',
        minMainWidth: 960,
      };
    }

    if (preset === 'custom') {
      return {
        preset: 'custom',
        navCollapsed: false,
        navWidth: 208,
        dockVisible: false,
        dockWidth: 380,
        dockPreference: 'auto',
        density: 'comfortable',
        pageWidth: 'wide',
        pageLayoutMode: 'workspace',
        minMainWidth: 1080,
      };
    }

    return {
      preset: 'research',
      navCollapsed: false,
      navWidth: 208,
      dockVisible: false,
      dockWidth: 380,
      dockPreference: 'auto',
      density: 'comfortable',
      pageWidth: 'wide',
      pageLayoutMode: 'workspace',
      minMainWidth: 1080,
    };
  }

  private toSerializableRecord(value: unknown): Record<string, unknown> {
    const record = this.asRecord(value);
    try {
      return JSON.parse(JSON.stringify(record)) as Record<string, unknown>;
    } catch {
      return {};
    }
  }

  private toTaskStatus(value: unknown): WorkspaceTask['status'] {
    const status = this.toNonEmptyString(value);
    return status === 'active' || status === 'done' ? status : 'todo';
  }

  private toLayoutPreset(value: unknown): WorkspaceLayout['preset'] {
    const preset = this.toNonEmptyString(value);
    return preset === 'trading' || preset === 'focus' || preset === 'custom' ? preset : 'research';
  }

  private toDensity(value: unknown): WorkspaceLayout['density'] | null {
    const density = this.toNonEmptyString(value);
    return density === 'compact' || density === 'comfortable' ? density : null;
  }

  private toPageWidth(value: unknown): WorkspaceLayout['pageWidth'] | null {
    const pageWidth = this.toNonEmptyString(value);
    return pageWidth === 'focused' || pageWidth === 'wide' ? pageWidth : null;
  }

  private toDockPreference(value: unknown): WorkspaceLayout['dockPreference'] | null {
    const dockPreference = this.toNonEmptyString(value);
    return dockPreference === 'hidden' || dockPreference === 'persistent' || dockPreference === 'auto'
      ? dockPreference
      : null;
  }

  private toPageLayoutMode(value: unknown): WorkspaceLayout['pageLayoutMode'] | null {
    const pageLayoutMode = this.toNonEmptyString(value);
    return pageLayoutMode === 'overview' || pageLayoutMode === 'utility' || pageLayoutMode === 'workspace'
      ? pageLayoutMode
      : null;
  }

  private toPagePanelMode(value: unknown): NonNullable<WorkspaceLayout['pagePanels']>[string]['mode'] | null {
    const mode = this.toNonEmptyString(value);
    return mode === 'split' || mode === 'single' ? mode : null;
  }

  private toPagePanelPlacement(value: unknown): NonNullable<WorkspaceLayout['pagePanels']>[string]['secondaryPlacement'] | null {
    const placement = this.toNonEmptyString(value);
    return placement === 'left' || placement === 'right' ? placement : null;
  }

  private toBoolean(value: unknown): boolean | null {
    if (typeof value === 'boolean') return value;
    return null;
  }

  private toPositiveInteger(value: unknown): number | null {
    const numberValue = Number(value);
    if (!Number.isFinite(numberValue) || numberValue <= 0) return null;
    return Math.trunc(numberValue);
  }

  private clampInteger(value: unknown, min: number, max: number, fallback: number) {
    const numberValue = Number(value);
    if (!Number.isFinite(numberValue)) return fallback;
    return Math.min(max, Math.max(min, Math.trunc(numberValue)));
  }

  private toTimestamp(value: unknown): number {
    const numberValue = Number(value);
    if (Number.isFinite(numberValue) && numberValue > 0) {
      return Math.trunc(numberValue);
    }
    if (typeof value === 'string') {
      const parsed = Date.parse(value);
      if (Number.isFinite(parsed) && parsed > 0) {
        return parsed;
      }
    }
    return Date.now();
  }

  private toIsoString(value: unknown): string | null {
    if (typeof value === 'string' && value.trim()) return value;
    return null;
  }

  private toNonEmptyString(value: unknown): string | null {
    if (typeof value !== 'string') return null;
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  }

  private asRecord(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return {};
    }
    return value as Record<string, unknown>;
  }
}
