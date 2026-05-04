export type WorkspaceLayoutDensity = 'comfortable' | 'compact' | 'dense';

export type WorkspaceLayoutPreset = 'research' | 'trading' | 'focus' | 'custom';
export type WorkspaceDockPreference = 'auto' | 'hidden' | 'persistent';
export type WorkspacePageLayoutMode = 'overview' | 'workspace' | 'utility';

export type WorkspacePagePanelMode = 'single' | 'split';

export type WorkspacePagePanelPlacement = 'left' | 'right';

export type WorkspacePageKey = string;

export type WorkspaceTaskStatus = 'todo' | 'active' | 'done';

export type WorkspaceSharedContext = {
    stockCode?: string;
    stockConfirmedAt?: string;
    eventCode?: string;
    accountId?: string;
    executionId?: string;
    artifactId?: string;
    portfolioId?: string;
    benchmark?: string;
    mode?: 'account' | 'portfolio' | 'personal-strategy';
    days?: number;
    lookbackDays?: number;
    strategyId?: string;
    strategyName?: string;
    linkedStrategyId?: string;
    linkedStrategyName?: string;
    copilotConversationId?: string;
    screenerQuery?: string;
    sourcePage?: string;
    taskType?: string;
    resultType?: string;
    strategyTestMode?: 'personal-strategy' | 'factory-incubation';
};

export type WorkspacePagePanelLayout = {
    mode: WorkspacePagePanelMode;
    secondaryPlacement: WorkspacePagePanelPlacement;
    secondarySize: number;
};

export type WorkspaceLayout = {
    preset: WorkspaceLayoutPreset;
    navCollapsed: boolean;
    navWidth: number;
    dockVisible: boolean;
    dockWidth: number;
    dockPreference: WorkspaceDockPreference;
    density: WorkspaceLayoutDensity;
    pageWidth: 'wide' | 'focused';
    pageLayoutMode: WorkspacePageLayoutMode;
    minMainWidth: number;
    pagePanels?: Record<WorkspacePageKey, WorkspacePagePanelLayout>;
};

export type WorkspaceSavedView = {
    id: string;
    pageKey: WorkspacePageKey;
    name: string;
    snapshot: Record<string, unknown>;
    createdAt: number;
    updatedAt: number;
};

export type WorkspaceTask = {
    id: string;
    pageKey: WorkspacePageKey;
    title: string;
    href?: string;
    kind?: string;
    payload?: Record<string, unknown>;
    status: WorkspaceTaskStatus;
    createdAt: number;
    updatedAt: number;
};

export type WorkspaceRecord = {
    id: string;
    name: string;
    createdAt: number;
    updatedAt: number;
    layout: WorkspaceLayout;
    context: WorkspaceSharedContext;
    savedViews: WorkspaceSavedView[];
    tasks: WorkspaceTask[];
};

export type WorkspaceStateSnapshot = {
    activeWorkspaceId: string;
    workspaces: WorkspaceRecord[];
    updatedAt: string | null;
};
