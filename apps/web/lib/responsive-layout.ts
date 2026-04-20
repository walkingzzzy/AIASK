import type { WorkspacePageKey, WorkspacePagePanelLayout } from '@aiask/shared-types';

export const RESPONSIVE_BREAKPOINTS = {
  mobile: 767,
  tablet: 1023,
  splitCollapse: 1279,
  dockOverlay: 1535,
} as const;

const FALLBACK_PAGE_PANEL_LAYOUT: WorkspacePagePanelLayout = {
  mode: 'single',
  secondaryPlacement: 'right',
  secondarySize: 34,
};

export const RESPONSIVE_WORKSPACE_PAGE_DEFAULTS: Record<string, WorkspacePagePanelLayout> = {
  research: { mode: 'split', secondaryPlacement: 'right', secondarySize: 30 },
  'paper-trading': { mode: 'split', secondaryPlacement: 'right', secondarySize: 30 },
  execution: { mode: 'split', secondaryPlacement: 'right', secondarySize: 32 },
  performance: { mode: 'split', secondaryPlacement: 'right', secondarySize: 30 },
  risk: { mode: 'split', secondaryPlacement: 'right', secondarySize: 30 },
  portfolio: { mode: 'split', secondaryPlacement: 'right', secondarySize: 28 },
  strategy: { mode: 'split', secondaryPlacement: 'right', secondarySize: 28 },
  screener: { mode: 'split', secondaryPlacement: 'right', secondarySize: 30 },
  search: { mode: 'split', secondaryPlacement: 'right', secondarySize: 30 },
  events: { mode: 'split', secondaryPlacement: 'right', secondarySize: 30 },
  skills: { mode: 'split', secondaryPlacement: 'right', secondarySize: 30 },
  decision: { mode: 'split', secondaryPlacement: 'right', secondarySize: 30 },
  'strategy-detail': { mode: 'split', secondaryPlacement: 'right', secondarySize: 30 },
  'workspace-templates': { mode: 'split', secondaryPlacement: 'right', secondarySize: 30 },
};

export function getResponsivePagePanelDefault(pageKey: WorkspacePageKey): WorkspacePagePanelLayout {
  return RESPONSIVE_WORKSPACE_PAGE_DEFAULTS[pageKey] ?? FALLBACK_PAGE_PANEL_LAYOUT;
}
