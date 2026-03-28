'use client';

import { useEffect, useMemo, useRef } from 'react';
import { hasLoggedInHint } from '@/lib/auth';
import { useWorkbenchStore } from '@/store/workbench-store';

function snapshotSignature() {
  const state = useWorkbenchStore.getState();
  return JSON.stringify({
    activeWorkspaceId: state.activeWorkspaceId,
    workspaces: state.workspaces,
  });
}

export function WorkspaceSync() {
  const hydrated = useWorkbenchStore((state) => state.hydrated);
  const remoteReady = useWorkbenchStore((state) => state.remoteReady);
  const syncing = useWorkbenchStore((state) => state.syncing);
  const lastSyncedAt = useWorkbenchStore((state) => state.lastSyncedAt);
  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const workspaces = useWorkbenchStore((state) => state.workspaces);
  const syncFromServer = useWorkbenchStore((state) => state.syncFromServer);
  const pushToServer = useWorkbenchStore((state) => state.pushToServer);

  const initialSyncStartedRef = useRef(false);
  const lastPushedSignatureRef = useRef<string | null>(null);

  const currentSignature = useMemo(
    () =>
      JSON.stringify({
        activeWorkspaceId,
        workspaces,
      }),
    [activeWorkspaceId, workspaces],
  );

  useEffect(() => {
    if (!hydrated || initialSyncStartedRef.current) return;
    if (!hasLoggedInHint()) return;

    initialSyncStartedRef.current = true;
    void syncFromServer().finally(() => {
      const state = useWorkbenchStore.getState();
      if (state.lastSyncedAt) {
        lastPushedSignatureRef.current = snapshotSignature();
      }
    });
  }, [hydrated, syncFromServer]);

  useEffect(() => {
    if (!hydrated || !remoteReady || syncing) return;
    if (!hasLoggedInHint()) return;
    if (currentSignature === lastPushedSignatureRef.current) return;

    const timer = window.setTimeout(() => {
      void pushToServer().then(() => {
        if (useWorkbenchStore.getState().lastSyncedAt) {
          lastPushedSignatureRef.current = snapshotSignature();
        }
      });
    }, 900);

    return () => window.clearTimeout(timer);
  }, [currentSignature, hydrated, lastSyncedAt, pushToServer, remoteReady, syncing]);

  return null;
}
