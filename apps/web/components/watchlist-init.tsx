'use client';

import { useEffect } from 'react';
import { useStablePathname } from '@/hooks/use-stable-pathname';
import { useBffAvailability } from '@/lib/bff-availability';
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

  return null;
}
