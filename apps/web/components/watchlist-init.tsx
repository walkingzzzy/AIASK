'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { useWatchlistStore } from '@/store/watchlist-store';
import { hasLoggedInHint } from '@/lib/auth';
import { isPublicPathname } from '@/lib/public-routes';

/**
 * 全局自选股同步初始化组件。
 * 在 layout 中挂载，确保应用启动时自动从服务端拉取自选股数据。
 */
export function WatchlistInit() {
    const pathname = usePathname();
    const syncFromServer = useWatchlistStore((s) => s.syncFromServer);
    const synced = useWatchlistStore((s) => s.synced);

    useEffect(() => {
        if (isPublicPathname(pathname)) return;
        if (!hasLoggedInHint()) return;
        if (!synced) {
            syncFromServer();
        }
    }, [pathname, synced, syncFromServer]);

    return null;
}
