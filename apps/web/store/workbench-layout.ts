import type {
  WorkspaceLayout,
  WorkspaceLayoutPreset,
  WorkspacePagePanelLayout,
  WorkspacePagePanelMode,
} from '@aiask/shared-types';

export const WORKSPACE_LAYOUT_PRESETS: Record<WorkspaceLayoutPreset, WorkspaceLayout> = {
  research: {
    preset: 'research',
    navCollapsed: false,
    navWidth: 208,
    dockVisible: false,
    dockWidth: 380,
    density: 'comfortable',
    pageWidth: 'wide',
  },
  trading: {
    preset: 'trading',
    navCollapsed: false,
    navWidth: 220,
    dockVisible: false,
    dockWidth: 430,
    density: 'compact',
    pageWidth: 'wide',
  },
  focus: {
    preset: 'focus',
    navCollapsed: true,
    navWidth: 208,
    dockVisible: false,
    dockWidth: 360,
    density: 'comfortable',
    pageWidth: 'focused',
  },
  custom: {
    preset: 'custom',
    navCollapsed: false,
    navWidth: 208,
    dockVisible: false,
    dockWidth: 380,
    density: 'comfortable',
    pageWidth: 'wide',
  },
};

export const DEFAULT_WORKSPACE_LAYOUT = WORKSPACE_LAYOUT_PRESETS.research;

const DEFAULT_PAGE_PANEL_LAYOUT: WorkspacePagePanelLayout = {
  mode: 'single',
  secondaryPlacement: 'right',
  secondarySize: 34,
};

function clamp(value: unknown, min: number, max: number, fallback: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, Math.trunc(parsed)));
}

function normalizePagePanelMode(value: unknown): WorkspacePagePanelMode {
  return value === 'split' ? 'split' : 'single';
}

export function resolveWorkspacePagePanels(value: unknown): Record<string, WorkspacePagePanelLayout> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }

  return Object.entries(value as Record<string, unknown>).reduce<Record<string, WorkspacePagePanelLayout>>(
    (acc, [pageKey, panel]) => {
      if (!pageKey.trim()) return acc;
      acc[pageKey] = resolveWorkspacePagePanel(panel);
      return acc;
    },
    {},
  );
}

export function resolveWorkspacePagePanel(panel?: WorkspacePagePanelLayout | null | unknown): WorkspacePagePanelLayout {
  const normalizedPanel =
    panel && typeof panel === 'object' && !Array.isArray(panel) ? (panel as WorkspacePagePanelLayout) : null;
  const normalizedSecondarySize = clamp(
    normalizedPanel?.secondarySize,
    24,
    60,
    DEFAULT_PAGE_PANEL_LAYOUT.secondarySize ?? 34,
  );
  return {
    mode: normalizePagePanelMode(normalizedPanel?.mode),
    secondaryPlacement: normalizedPanel?.secondaryPlacement === 'left' ? 'left' : 'right',
    // 38% 是早期默认值，会让主画布在工作台布局里显得过窄，统一迁移到新的更保守基线。
    secondarySize: normalizedSecondarySize === 38 ? 34 : normalizedSecondarySize,
  };
}

function normalizeLayoutPreset(value: unknown): WorkspaceLayoutPreset {
  return value === 'trading' || value === 'focus' || value === 'custom' ? value : 'research';
}

export function resolveWorkspaceLayout(layout?: Partial<WorkspaceLayout> | null): WorkspaceLayout {
  const preset = normalizeLayoutPreset(layout?.preset);
  const base = WORKSPACE_LAYOUT_PRESETS[preset] ?? DEFAULT_WORKSPACE_LAYOUT;
  return {
    ...base,
    ...layout,
    preset,
    navCollapsed: typeof layout?.navCollapsed === 'boolean' ? layout.navCollapsed : base.navCollapsed,
    navWidth: clamp(layout?.navWidth, 188, 280, base.navWidth ?? 208),
    dockVisible: typeof layout?.dockVisible === 'boolean' ? layout.dockVisible : base.dockVisible,
    dockWidth: clamp(layout?.dockWidth, 320, 480, base.dockWidth ?? 380),
    density: layout?.density === 'compact' ? 'compact' : base.density,
    pageWidth: layout?.pageWidth === 'focused' ? 'focused' : base.pageWidth,
    pagePanels: resolveWorkspacePagePanels(layout?.pagePanels),
  };
}
