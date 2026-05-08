'use client';

import { useEffect } from 'react';
import { useStablePathname } from '@/hooks/use-stable-pathname';
import { useBffAvailability } from '@/lib/bff-availability';
import { getDataEffectEventName } from '@/lib/data-effects';
import { useWatchlistStore } from '@/store/watchlist-store';
import { hasLoggedInHint } from '@/lib/auth';
import { isPublicPathname } from '@/lib/public-routes';

/**
 * 全局自选股同步初始化组件。
 * 在 layout 中挂载，确保应用启动时自动从服务端拉取自选股数据。
 */
export function WatchlistInit() {
  const pathname = useStablePathname();
  const syncFromServer = useWatchlistStore((s) => s.syncFromServer);
  const synced = useWatchlistStore((s) => s.synced);
  const bffAvailability = useBffAvailability();

  useEffect(() => {
    if (isPublicPathname(pathname)) return;
    if (!hasLoggedInHint()) return;
    if (!bffAvailability.reachable) return;
    if (!synced) {
      void syncFromServer();
    }
  }, [bffAvailability.reachable, pathname, synced, syncFromServer]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const handleWatchlistChanged = () => {
      if (isPublicPathname(pathname)) return;
      if (!hasLoggedInHint()) return;
      if (!bffAvailability.reachable) return;
      void syncFromServer(true);
    };
    const eventName = getDataEffectEventName('watchlist.changed');
    window.addEventListener(eventName, handleWatchlistChanged);
    return () => window.removeEventListener(eventName, handleWatchlistChanged);
  }, [bffAvailability.reachable, pathname, syncFromServer]);

  return null;
}
