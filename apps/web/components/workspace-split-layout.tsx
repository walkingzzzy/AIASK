'use client';

import { type PointerEvent as ReactPointerEvent, ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import { TabBar } from '@/components/ui';
import { useMobile } from '@/hooks/use-mobile';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { resolveWorkspaceLayout, resolveWorkspacePagePanel, selectActiveWorkspace, useWorkbenchStore, type WorkspacePageKey } from '@/store/workbench-store';

type WorkspaceResponsivePanel = {
  key: string;
  label: string;
  content: ReactNode;
};

type WorkspaceSplitLayoutProps = {
  pageKey: WorkspacePageKey;
  primary: ReactNode;
  secondary: ReactNode;
  className?: string;
  collapseSecondaryBelow?: number;
  defaultMobileTab?: string;
  primaryLabel?: string;
  secondaryLabel?: string;
  secondaryPanels?: WorkspaceResponsivePanel[];
  mobileSummary?: ReactNode;
  maxDefaultSections?: number;
};

function clampSize(value: number) {
  return Math.min(60, Math.max(24, Math.round(value)));
}

export default function WorkspaceSplitLayout({
  pageKey,
  primary,
  secondary,
  className = '',
  collapseSecondaryBelow = RESPONSIVE_BREAKPOINTS.splitCollapse,
  defaultMobileTab = 'primary',
  primaryLabel = '主画布',
  secondaryLabel = '摘要',
  secondaryPanels,
  mobileSummary,
  maxDefaultSections = 0,
}: WorkspaceSplitLayoutProps) {
  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const workspaces = useWorkbenchStore((state) => state.workspaces);
  const updatePagePanel = useWorkbenchStore((state) => state.updatePagePanel);
  const collapseSecondary = useMobile(collapseSecondaryBelow);

  const activeWorkspace = useMemo(
    () => selectActiveWorkspace({ activeWorkspaceId, workspaces }),
    [activeWorkspaceId, workspaces],
  );
  const layout = useMemo(() => resolveWorkspaceLayout(activeWorkspace.layout), [activeWorkspace.layout]);
  const pagePanel = useMemo(
    () => resolveWorkspacePagePanel(layout.pagePanels?.[pageKey], pageKey),
    [layout.pagePanels, pageKey],
  );

  const containerRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const latestSizeRef = useRef(pagePanel.secondarySize ?? 34);
  const [dragSecondarySize, setDragSecondarySize] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const stackedPanels = useMemo<WorkspaceResponsivePanel[]>(
    () => [
      { key: 'primary', label: primaryLabel, content: primary },
      ...(secondaryPanels?.length ? secondaryPanels : [{ key: 'secondary', label: secondaryLabel, content: secondary }]),
    ],
    [primary, primaryLabel, secondary, secondaryLabel, secondaryPanels],
  );
  const [mobileTabState, setMobileTabState] = useState({
    defaultMobileTab,
    pageKey,
    selected: defaultMobileTab,
  });
  const mobileTabCandidate =
    mobileTabState.pageKey === pageKey && mobileTabState.defaultMobileTab === defaultMobileTab
      ? mobileTabState.selected
      : defaultMobileTab;
  const mobileTab = stackedPanels.some((panel) => panel.key === mobileTabCandidate)
    ? mobileTabCandidate
    : stackedPanels[0]?.key ?? 'primary';
  const selectMobileTab = (selected: string) => {
    setMobileTabState({ defaultMobileTab, pageKey, selected });
  };

  useEffect(() => () => {
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, []);

  const handlePointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (pagePanel.mode !== 'split') return;
    event.preventDefault();

    draggingRef.current = true;
    setIsDragging(true);
    latestSizeRef.current = pagePanel.secondarySize ?? 34;
    setDragSecondarySize(pagePanel.secondarySize ?? 34);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    const onMove = (moveEvent: PointerEvent) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect || rect.width <= 0) return;

      const rawSize = pagePanel.secondaryPlacement === 'left'
        ? ((moveEvent.clientX - rect.left) / rect.width) * 100
        : ((rect.right - moveEvent.clientX) / rect.width) * 100;
      const nextSize = clampSize(rawSize);
      latestSizeRef.current = nextSize;
      setDragSecondarySize(nextSize);
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      draggingRef.current = false;
      setIsDragging(false);
      setDragSecondarySize(null);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      updatePagePanel(pageKey, {
        mode: 'split',
        secondaryPlacement: pagePanel.secondaryPlacement,
        secondarySize: latestSizeRef.current,
      });
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
  };

  if (collapseSecondary) {
    const visiblePanels = Math.max(0, Math.min(maxDefaultSections, stackedPanels.length));
    const inlinePanels = stackedPanels.slice(0, visiblePanels);
    const tabPanels = stackedPanels.slice(visiblePanels);
    const activeTab = tabPanels.find((panel) => panel.key === mobileTab) ?? tabPanels[0] ?? null;

    return (
      <div className={`flex flex-col gap-4 ${className}`}>
        {mobileSummary}
        {inlinePanels.map((panel) => (
          <div key={panel.key}>{panel.content}</div>
        ))}
        {tabPanels.length > 0 ? (
          <div className="space-y-3">
            <TabBar
              tabs={tabPanels.map((panel) => ({ key: panel.key, label: panel.label }))}
              active={activeTab?.key ?? tabPanels[0].key}
              onChange={(key) => selectMobileTab(key)}
            />
            <div>{activeTab?.content}</div>
          </div>
        ) : null}
      </div>
    );
  }

  if (pagePanel.mode !== 'split') {
    return (
      <div className={`flex flex-col gap-4 ${className}`}>
        {primary}
        {secondary}
      </div>
    );
  }

  const secondarySize = clampSize(dragSecondarySize ?? pagePanel.secondarySize ?? 34);
  const primarySize = Math.max(40, 100 - secondarySize);

  const primaryPanel = (
    <div className="min-h-0 min-w-0 xl:h-full" style={{ flexBasis: `${primarySize}%`, width: `${primarySize}%` }}>
      {primary}
    </div>
  );

  const secondaryPanel = (
    <div className="min-h-0 min-w-0 xl:h-full" style={{ flexBasis: `${secondarySize}%`, width: `${secondarySize}%` }}>
      {secondary}
    </div>
  );

  const dragHandle = (
    <button
      type="button"
      onPointerDown={handlePointerDown}
      className={`group hidden w-3 shrink-0 cursor-col-resize items-stretch justify-center xl:flex ${isDragging ? 'opacity-100' : 'opacity-80'}`}
      aria-label="拖拽调整子面板宽度"
      title="拖拽调整子面板宽度"
    >
      <span className="my-1 w-px rounded-full bg-glass-border transition group-hover:bg-primary" />
    </button>
  );

  return (
    <div
      ref={containerRef}
      className={`flex min-h-0 flex-col gap-3 xl:h-[calc(100vh-236px)] xl:flex-row ${className}`}
    >
      {pagePanel.secondaryPlacement === 'left' ? secondaryPanel : primaryPanel}
      {dragHandle}
      {pagePanel.secondaryPlacement === 'left' ? primaryPanel : secondaryPanel}
    </div>
  );
}
