'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { useWatchlistStore } from '@/store/watchlist-store';

/**
 * 全局自选股同步初始化组件。
 * 在 layout 中挂载，确保应用启动时自动从服务端拉取自选股数据。
 */
export function WatchlistInit() {
    const pathname = usePathname();
    const syncFromServer = useWatchlistStore((s) => s.syncFromServer);
    const synced = useWatchlistStore((s) => s.synced);

    useEffect(() => {
        if (pathname === '/login' || pathname === '/register') return;
        if (!document.cookie.includes('logged_in=1')) return;
        if (!synced) {
            syncFromServer();
        }
    }, [pathname, synced, syncFromServer]);

    return null;
}
