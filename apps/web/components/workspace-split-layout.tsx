'use client';

import { type PointerEvent as ReactPointerEvent, ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import { resolveWorkspaceLayout, resolveWorkspacePagePanel, selectActiveWorkspace, useWorkbenchStore, type WorkspacePageKey } from '@/store/workbench-store';

type WorkspaceSplitLayoutProps = {
  pageKey: WorkspacePageKey;
  primary: ReactNode;
  secondary: ReactNode;
  className?: string;
};

function clampSize(value: number) {
  return Math.min(60, Math.max(24, Math.round(value)));
}

export default function WorkspaceSplitLayout({
  pageKey,
  primary,
  secondary,
  className = '',
}: WorkspaceSplitLayoutProps) {
  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const workspaces = useWorkbenchStore((state) => state.workspaces);
  const updatePagePanel = useWorkbenchStore((state) => state.updatePagePanel);

  const activeWorkspace = useMemo(
    () => selectActiveWorkspace({ activeWorkspaceId, workspaces }),
    [activeWorkspaceId, workspaces],
  );
  const layout = useMemo(() => resolveWorkspaceLayout(activeWorkspace.layout), [activeWorkspace.layout]);
  const pagePanel = useMemo(
    () => resolveWorkspacePagePanel(layout.pagePanels?.[pageKey]),
    [layout.pagePanels, pageKey],
  );

  const containerRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const latestSizeRef = useRef(pagePanel.secondarySize ?? 34);
  const [dragSecondarySize, setDragSecondarySize] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);

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
